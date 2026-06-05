"""Staged file state, index, and summary helpers for grit-console."""

import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import attach_target_route_fields, target_route_context
from gritlib.event_log import append_event
from gritlib.file_transfers import print_staged_fetch_target_options, render_fetch_command
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import (
    int_value, latest_record_value, record_count_by_key, records_by_key,
)
from gritlib.session_state import atomic_write_json, read_json_file, utc_now
from gritlib.shell_utils import shquote
from gritlib.target_records import configured_target_filter, target_context_fields


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_SERVER_CONFIG = Path("local/server-config.json")


def staged_file_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("staged_files") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "staged-files.json"
    ))


def staged_files_state_record(cfg):
    path = staged_file_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "staged_count": 0,
        "request_names": [],
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "staged-files JSON is not an object"
            return rec
        staged = data.get("staged")
        if not isinstance(staged, dict):
            rec["error"] = "staged-files JSON staged field is not an object"
            return rec
        request_names = sorted(str(name) for name in staged if str(name))
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "staged_count": len(request_names),
            "request_names": request_names,
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def staged_files_state_status(cfg):
    state_record = staged_files_state_record(cfg)
    state_record["has_staged"] = int(state_record.get("staged_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "staged_files_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "staged_files_state_records_by_exists": records_by_key(
            state_records, "exists"
        ),
        "staged_files_state_records_by_valid": records_by_key(state_records, "valid"),
        "staged_files_state_records_by_has_staged": records_by_key(
            state_records, "has_staged"
        ),
        "staged_files_state_records_by_schema": records_by_key(
            state_records, "schema"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def load_staged(cfg):
    data = read_json_file(staged_file_path(cfg), {"schema": 1, "staged": {}})
    if not isinstance(data, dict):
        data = {"schema": 1, "staged": {}}
    if not isinstance(data.get("staged"), dict):
        data["staged"] = {}
    data.setdefault("schema", 1)
    return data


def staged_record_list(staged):
    records = []
    for name, rec in sorted((staged or {}).items()):
        if not isinstance(rec, dict):
            continue
        item = dict(rec)
        item["name"] = name
        item["request_name"] = item.get("request_name") or name
        item["stage_kind"] = str(item.get("stage_kind") or "file")
        records.append(item)
    return records


def staged_record_for_configure(cfg, selector):
    text = str(selector or "").strip()
    if not text:
        return "", {}
    staged = load_staged(cfg).get("staged") or {}
    if text in staged and isinstance(staged.get(text), dict):
        return text, staged[text]
    if text.isdigit():
        names = sorted(str(item or "") for item in staged.keys() if str(item or ""))
        idx = int(text) - 1
        if 0 <= idx < len(names):
            name = names[idx]
            rec = staged.get(name) or {}
            return name, rec if isinstance(rec, dict) else {}
    return "", {}


def configured_artifact_path_for_request(cfg, request_name, source_path):
    out_dir = Path(str(cfg.get("operator_session_dir", DEFAULT_OPERATOR_SESSION_DIR))) / "configured-artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = reject_traversal_request_name(request_name)
    suffix = Path(str(source_path or safe_name)).suffix
    target = out_dir / safe_name
    if suffix and not target.name.endswith(suffix):
        target = out_dir / f"{safe_name}{suffix}"
    return target


def prepare_staged_artifact_for_configure(cfg, request_name, rec):
    source = Path(str(rec.get("source_path") or "")).expanduser()
    if not source.is_file():
        raise ValueError(f"staged source is missing: {source}")
    configured_source = str(rec.get("configured_source_path") or "")
    if configured_source and Path(configured_source).is_file():
        return Path(configured_source)
    dest = configured_artifact_path_for_request(cfg, request_name, source)
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    dest.chmod(source.stat().st_mode & 0o777)
    data = load_staged(cfg)
    staged = data.setdefault("staged", {})
    updated = dict(staged.get(request_name) or rec)
    updated.update({
        "source_path": str(dest),
        "configured_source_path": str(dest),
        "configured_from_source_path": str(source),
        "configured_at": utc_now(),
        "size": dest.stat().st_size,
        "sha256": file_sha256(dest),
        "mtime": int(dest.stat().st_mtime),
    })
    staged[request_name] = updated
    atomic_write_json(staged_file_path(cfg), data)
    return dest


def enriched_staged_records(cfg, staged=None):
    staged = staged if staged is not None else load_staged(cfg).get("staged", {})
    host = operator_advertised_host(cfg)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=host,
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    out = {}
    for name, rec in sorted((staged or {}).items()):
        if not isinstance(rec, dict):
            continue
        item = dict(rec)
        request = item.get("request_name") or name
        source_path = item.get("source_path", "")
        item["request_name"] = request
        item["stage_kind"] = str(item.get("stage_kind") or "file")
        item["fetch_command"] = render_fetch_command(request, cfg, host=host)
        item["fetch_command_force"] = render_fetch_command(request, cfg, host=host, force=True)
        item["target_route"] = dict(route)
        item["route_kind"] = route.get("route_kind", "direct")
        item["bridge_profile"] = route.get("bridge_profile", "")
        item["bridge_route_path"] = route.get("bridge_route_path", "")
        item["source_exists"] = Path(str(source_path)).is_file() if source_path else False
        item["source_path"] = str(source_path)
        out[name] = item
    return out


def staged_status_context(cfg, target_filter_id=None):
    staged_raw = load_staged(cfg).get("staged", {})
    unfiltered_staged_raw = staged_raw if isinstance(staged_raw, dict) else {}
    unfiltered_staged_count = len(unfiltered_staged_raw)
    if target_filter_id and isinstance(staged_raw, dict):
        staged_raw = {
            name: rec for name, rec in unfiltered_staged_raw.items()
            if isinstance(rec, dict) and str(rec.get("target_id") or "") == target_filter_id
        }
    staged = enriched_staged_records(cfg, staged_raw)
    staged_records = staged_record_list(staged)
    return {
        "raw": staged_raw,
        "unfiltered_raw": unfiltered_staged_raw,
        "staged": staged,
        "records": staged_records,
        "indexes": staged_record_indexes(staged_records),
        "unfiltered_count": unfiltered_staged_count,
    }


def reject_traversal_request_name(name):
    text = urllib.parse.unquote(str(name or "")).strip()
    if not text:
        raise ValueError("staged request name must not be empty")
    parts = [part for part in text.replace("\\", "/").split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("staged request name must not contain path traversal")
    return text


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_file(cfg, path, request_name, metadata=None):
    src = Path(path).expanduser()
    if not src.is_file():
        raise ValueError(f"staged file does not exist or is not a regular file: {src}")
    request = reject_traversal_request_name(request_name)
    stat = src.stat()
    data = load_staged(cfg)
    record = {
        "request_name": request,
        "stage_kind": "file",
        "source_path": str(src),
        "size": stat.st_size,
        "sha256": file_sha256(src),
        "mtime": int(stat.st_mtime),
        "staged_at": utc_now(),
    }
    if metadata:
        record.update(metadata)
        record["request_name"] = request
        record["source_path"] = str(src)
        record["size"] = stat.st_size
        record["sha256"] = record.get("sha256") or file_sha256(src)
        record["mtime"] = int(stat.st_mtime)
        record["staged_at"] = record.get("staged_at") or utc_now()
        record["stage_kind"] = str(record.get("stage_kind") or "file")
    if configured_target_filter(cfg) and not record.get("target_id"):
        record.update(target_context_fields(cfg, configured_target_filter(cfg)))
    if "route_kind" not in record:
        host = operator_advertised_host(cfg)
        route = target_route_context(
            cfg,
            "file-service",
            direct_host=host,
            direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
        )
        record.update(attach_target_route_fields({}, route))
    data["staged"][request] = record
    atomic_write_json(staged_file_path(cfg), data)
    append_event(cfg, "file-service", "staged_file_add", details=data["staged"][request])
    return data["staged"][request]


def stage_dir(cfg, path):
    root = Path(path).expanduser()
    if not root.is_dir():
        raise ValueError(f"staged directory does not exist: {root}")
    records = []
    for child in sorted(root.iterdir()):
        if child.is_file():
            records.append(stage_file(cfg, child, child.name))
    return records


def unstage_file(cfg, request_name):
    request = reject_traversal_request_name(request_name)
    data = load_staged(cfg)
    existed = request in data.get("staged", {})
    data.get("staged", {}).pop(request, None)
    atomic_write_json(staged_file_path(cfg), data)
    append_event(
        cfg,
        "file-service",
        "staged_file_remove",
        details={"request_name": request, "existed": existed},
    )
    return existed


def print_staged(cfg):
    staged = load_staged(cfg).get("staged", {})
    target_filter_id = configured_target_filter(cfg)
    if target_filter_id and isinstance(staged, dict):
        staged = {
            name: rec for name, rec in staged.items()
            if isinstance(rec, dict) and str(rec.get("target_id") or "") == target_filter_id
        }
    if not staged:
        print("No staged files.")
        return
    for name in sorted(staged):
        rec = staged[name]
        print(f"{name}\t{rec.get('stage_kind', 'file')}\t{rec.get('source_path', '')}\t{rec.get('size', '')}\t{rec.get('sha256', '')}")
        if rec.get("release_path") or rec.get("tuple_path"):
            compatibility = rec.get("compatibility") if isinstance(rec.get("compatibility"), dict) else {}
            compat_label = compatibility.get("label", "")
            compat_text = f" compatibility={compat_label}" if compat_label else ""
            print(f"  release={rec.get('release_path', '')} tuple={rec.get('tuple_path', '')} preset={rec.get('payload_preset', '')}{compat_text}")
        if rec.get("target_id"):
            print(f"  target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
        print_staged_fetch_target_options(
            name,
            cfg,
            output_name=Path(str(rec.get("source_path") or name)).name,
            executable=bool(str(rec.get("stage_kind") or "") in {"release-artifact", "operator-binary"}),
        )


def staged_record_indexes(records):
    by_request = {}
    by_kind = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_fetch_command = {}
    by_fetch_command_force = {}
    by_source_exists = {"yes": [], "no": []}
    by_kind_source_exists = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or rec.get("name") or "")
        kind = str(rec.get("stage_kind") or "file")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        fetch_command = str(rec.get("fetch_command") or "")
        fetch_command_force = str(rec.get("fetch_command_force") or "")
        source_exists = "yes" if rec.get("source_exists") is True else "no"
        if request_name:
            by_request[request_name] = rec
        if kind:
            by_kind.setdefault(kind, []).append(rec)
            by_kind_source_exists.setdefault(f"{kind}:{source_exists}", []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path[source_path] = rec
        if fetch_command:
            by_fetch_command[fetch_command] = rec
        if fetch_command_force:
            by_fetch_command_force[fetch_command_force] = rec
        by_source_exists[source_exists].append(rec)
    return (
        by_request, by_kind, by_sha256, by_target_id, by_source_path,
        by_fetch_command, by_fetch_command_force,
        by_source_exists, by_kind_source_exists,
    )

def staged_record_summary(records):
    total_size = 0
    source_exists_count = 0
    source_missing_count = 0
    fetch_command_count = 0
    fetch_command_force_count = 0
    source_exists_by_kind = {}
    source_missing_by_kind = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("stage_kind") or "file")
        try:
            total_size += int(rec.get("size", 0) or 0)
        except (TypeError, ValueError):
            pass
        if rec.get("fetch_command"):
            fetch_command_count += 1
        if rec.get("fetch_command_force"):
            fetch_command_force_count += 1
        if rec.get("source_exists") is True:
            source_exists_count += 1
            source_exists_by_kind[kind] = source_exists_by_kind.get(kind, 0) + 1
        else:
            source_missing_count += 1
            source_missing_by_kind[kind] = source_missing_by_kind.get(kind, 0) + 1
    return {
        "total_size": total_size,
        "source_exists_count": source_exists_count,
        "source_missing_count": source_missing_count,
        "fetch_command_count": fetch_command_count,
        "fetch_command_force_count": fetch_command_force_count,
        "target_counts": record_count_by_key(records, "target_id"),
        "source_exists_by_kind": source_exists_by_kind,
        "source_missing_by_kind": source_missing_by_kind,
    }


def staged_status_summary(records, workflow_action_records=None):
    records = records or []
    staged_summary = staged_record_summary(records)
    action_summary = staged_file_workflow_action_summary(workflow_action_records)
    return {
        "staged_count": len(records),
        "staged_total_size": staged_summary.get("total_size", 0),
        "staged_kind_counts": record_count_by_key(records, "stage_kind"),
        "staged_target_counts": staged_summary.get("target_counts") or {},
        "staged_source_exists_count": staged_summary.get("source_exists_count", 0),
        "staged_source_missing_count": staged_summary.get("source_missing_count", 0),
        "staged_fetch_command_count": staged_summary.get("fetch_command_count", 0),
        "staged_fetch_command_force_count": staged_summary.get(
            "fetch_command_force_count", 0
        ),
        "staged_source_exists_kind_counts": staged_summary.get(
            "source_exists_by_kind"
        ) or {},
        "staged_source_missing_kind_counts": staged_summary.get(
            "source_missing_by_kind"
        ) or {},
        "latest_staged_at": latest_record_value(records, ("staged_at",)),
        "staged_file_workflow_action_count": action_summary.get("total_count", 0),
        "staged_file_workflow_action_available_count": action_summary.get(
            "available_count", 0
        ),
        "staged_file_workflow_action_requires_target_count": action_summary.get(
            "requires_target_count", 0
        ),
        "staged_file_workflow_action_queues_offline_work_count": action_summary.get(
            "queues_offline_work_count", 0
        ),
        "staged_file_workflow_action_requires_confirmation_count": action_summary.get(
            "requires_confirmation_count", 0
        ),
        "staged_file_workflow_action_can_run_from_curses_enter_count": action_summary.get(
            "can_run_from_curses_enter_count", 0
        ),
        "staged_file_workflow_action_request_counts": action_summary.get(
            "request_counts"
        ) or {},
        "staged_file_workflow_action_stage_kind_counts": action_summary.get(
            "stage_kind_counts"
        ) or {},
        "staged_file_workflow_action_category_counts": action_summary.get(
            "category_counts"
        ) or {},
        "staged_file_workflow_action_workflow_counts": action_summary.get(
            "workflow_counts"
        ) or {},
        "staged_file_workflow_action_target_counts": action_summary.get(
            "target_counts"
        ) or {},
        "staged_file_workflow_action_target_connectivity_state_counts": action_summary.get(
            "target_connectivity_state_counts"
        ) or {},
        "staged_file_workflow_action_target_offline_age_bucket_counts": action_summary.get(
            "target_offline_age_bucket_counts"
        ) or {},
        "staged_file_workflow_action_target_poll_overdue_counts": action_summary.get(
            "target_poll_overdue_counts"
        ) or {},
        "staged_file_workflow_action_target_mailbox_pending_work_count_counts": action_summary.get(
            "target_mailbox_pending_work_count_counts"
        ) or {},
        "staged_file_workflow_action_target_latest_phone_home_status_counts": action_summary.get(
            "target_latest_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_target_latest_successful_phone_home_status_counts": action_summary.get(
            "target_latest_successful_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_target_last_failed_phone_home_status_counts": action_summary.get(
            "target_last_failed_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_route_kind_counts": action_summary.get(
            "route_kind_counts"
        ) or {},
        "staged_file_workflow_action_bridge_profile_counts": action_summary.get(
            "bridge_profile_counts"
        ) or {},
        "staged_file_workflow_action_action_counts": action_summary.get(
            "action_counts"
        ) or {},
        "staged_file_workflow_action_fleet_target_count_counts": action_summary.get(
            "fleet_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_offline_target_count_counts": action_summary.get(
            "fleet_offline_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_stale_target_count_counts": action_summary.get(
            "fleet_stale_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_mailbox_pending_target_count_counts": action_summary.get(
            "fleet_mailbox_pending_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_mailbox_pending_work_count_counts": action_summary.get(
            "fleet_mailbox_pending_work_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_poll_overdue_target_count_counts": action_summary.get(
            "fleet_poll_overdue_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_offline_targets_counts": action_summary.get(
            "fleet_has_offline_targets_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_stale_targets_counts": action_summary.get(
            "fleet_has_stale_targets_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_mailbox_pending_work_counts": action_summary.get(
            "fleet_has_mailbox_pending_work_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_poll_overdue_targets_counts": action_summary.get(
            "fleet_has_poll_overdue_targets_counts"
        ) or {},
        "staged_file_workflow_action_source_exists_counts": action_summary.get(
            "source_exists_counts"
        ) or {},
        "staged_file_workflow_action_available_counts": action_summary.get(
            "available_counts"
        ) or {},
        "staged_file_workflow_action_operator_action_state_counts": action_summary.get(
            "operator_action_state_counts"
        ) or {},
        "staged_file_workflow_action_operator_action_reason_counts": action_summary.get(
            "operator_action_reason_counts"
        ) or {},
        "staged_file_workflow_action_can_run_from_curses_enter_counts": action_summary.get(
            "can_run_from_curses_enter_counts"
        ) or {},
        "staged_file_workflow_action_curses_enter_action_counts": action_summary.get(
            "curses_enter_action_counts"
        ) or {},
    }


def _staged_file_workflow_fleet_context(target_records):
    fleet_mailbox_pending_work_count = sum(
        int_value(rec.get("mailbox_pending_work_count", 0))
        for rec in target_records
    )
    fleet_offline_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "offline"
    ])
    fleet_stale_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "stale"
    ])
    fleet_mailbox_pending_target_count = len([
        rec for rec in target_records
        if int_value(rec.get("mailbox_pending_work_count", 0)) > 0
    ])
    fleet_poll_overdue_target_count = len([
        rec for rec in target_records
        if rec.get("poll_overdue") is True
    ])
    return {
        "target_records": target_records,
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_mailbox_pending_target_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
    }


def _staged_file_workflow_action_record(base, targets_by_id, fleet_context, rec, action_id,
                                        category, label, command, workflow, action_state,
                                        action_reason, available=True,
                                        requires_confirmation=False, requires_target=False,
                                        queues_offline_work=False,
                                        can_run_from_curses_enter=False,
                                        curses_enter_action=""):
    request = str(rec.get("request_name") or rec.get("name") or "")
    if not request:
        return None
    target_id = str(rec.get("target_id") or "")
    target = targets_by_id.get(target_id) or {}
    target_records = fleet_context["target_records"]
    fleet_offline_target_count = fleet_context["fleet_offline_target_count"]
    fleet_stale_target_count = fleet_context["fleet_stale_target_count"]
    fleet_mailbox_pending_work_count = fleet_context["fleet_mailbox_pending_work_count"]
    fleet_poll_overdue_target_count = fleet_context["fleet_poll_overdue_target_count"]
    return {
        "id": f"{request}:{action_id}",
        "action_id": action_id,
        "request_name": request,
        "name": str(rec.get("name") or request),
        "stage_kind": str(rec.get("stage_kind") or "file"),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": base + " --run-staged-file-workflow-action " + shquote(f"{request}:{action_id}"),
        "target_id": target_id,
        "target_label": str(rec.get("target_label") or ""),
        "target_connectivity_state": str(target.get("connectivity_state") or ""),
        "target_last_seen": str(target.get("last_seen") or target.get("last_seen_at") or ""),
        "target_last_seen_via": str(target.get("last_seen_via") or ""),
        "target_offline_age_bucket": str(target.get("offline_age_bucket") or ""),
        "target_next_expected_poll": str(target.get("next_expected_poll") or ""),
        "target_poll_overdue": bool(target.get("poll_overdue", False)),
        "target_poll_overdue_for_sec": target.get("poll_overdue_for_sec", ""),
        "target_mailbox_command_count": int_value(target.get("mailbox_command_count", 0)),
        "target_mailbox_pending_work_count": int_value(target.get("mailbox_pending_work_count", 0)),
        "target_latest_phone_home_at": str(target.get("latest_phone_home_at") or ""),
        "target_latest_phone_home_status": str(target.get("latest_phone_home_status") or ""),
        "target_latest_phone_home_kind": str(target.get("latest_phone_home_kind") or ""),
        "target_latest_phone_home_contact_path": str(target.get("latest_phone_home_contact_path") or ""),
        "target_latest_successful_phone_home_at": str(target.get("latest_successful_phone_home_at") or ""),
        "target_latest_successful_phone_home_status": str(target.get("latest_successful_phone_home_status") or ""),
        "target_latest_successful_phone_home_kind": str(target.get("latest_successful_phone_home_kind") or ""),
        "target_latest_successful_phone_home_contact_path": str(target.get("latest_successful_phone_home_contact_path") or ""),
        "target_last_failed_phone_home_at": str(target.get("last_failed_phone_home_at") or ""),
        "target_last_failed_phone_home_status": str(target.get("last_failed_phone_home_status") or ""),
        "target_last_failed_phone_home_reason": str(target.get("last_failed_phone_home_reason") or ""),
        "target_last_failed_phone_home_contact_path": str(target.get("last_failed_phone_home_contact_path") or ""),
        "route_kind": str(rec.get("route_kind") or ""),
        "bridge_profile": str(rec.get("bridge_profile") or ""),
        "bridge_route_path": str(rec.get("bridge_route_path") or ""),
        "source_path": str(rec.get("source_path") or ""),
        "source_exists": bool(rec.get("source_exists")),
        "release_path": str(rec.get("release_path") or ""),
        "tuple_path": str(rec.get("tuple_path") or ""),
        "payload_preset": str(rec.get("payload_preset") or ""),
        "sha256": str(rec.get("sha256") or ""),
        "size": rec.get("size", ""),
        "fetch_command": str(rec.get("fetch_command") or ""),
        "fetch_command_force": str(rec.get("fetch_command_force") or ""),
        "fleet_target_count": len(target_records),
        "fleet_connectivity_state_counts": record_count_by_key(target_records, "connectivity_state"),
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_context["fleet_mailbox_pending_target_count"],
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
        "fleet_has_offline_targets": fleet_offline_target_count > 0,
        "fleet_has_stale_targets": fleet_stale_target_count > 0,
        "fleet_has_mailbox_pending_work": fleet_mailbox_pending_work_count > 0,
        "fleet_has_poll_overdue_targets": fleet_poll_overdue_target_count > 0,
        "available": bool(available),
        "requires_input": False,
        "requires_confirmation": bool(requires_confirmation),
        "requires_target": bool(requires_target),
        "queues_offline_work": bool(queues_offline_work),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side staged file workflow; target fetch still requires explicit target-side command or poll",
    }


def _append_staged_file_workflow_action(records, base, targets_by_id, fleet_context, rec,
                                        action_id, category, label, command, workflow,
                                        action_state, action_reason, **kwargs):
    action = _staged_file_workflow_action_record(
        base,
        targets_by_id,
        fleet_context,
        rec,
        action_id,
        category,
        label,
        command,
        workflow,
        action_state,
        action_reason,
        **kwargs,
    )
    if action:
        records.append(action)


def _staged_file_single_request_workflow_actions(base, targets_by_id, fleet_context, rec):
    records = []
    request = str(rec.get("request_name") or rec.get("name") or "")
    if not request:
        return records
    target_id = str(rec.get("target_id") or "")
    add = lambda *args, **kwargs: _append_staged_file_workflow_action(
        records,
        base,
        targets_by_id,
        fleet_context,
        rec,
        *args,
        **kwargs,
    )
    add(
        "inspect-staged", "inspect", f"Inspect staged request {request}",
        base + " --list-staged", "file-service", "ready", "run-now",
    )
    add(
        "show-fetch-command", "file-transfer", f"Show target fetch command for {request}",
        base + " --list-staged", "file-service", "ready", "show-command",
        can_run_from_curses_enter=True, curses_enter_action="show-fetch-command",
    )
    if target_id:
        queue_command = (
            base + " --target-id " + shquote(target_id)
            + " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name "
            + shquote(request)
        )
        add(
            "queue-staged-fetch", "mailbox", f"Queue staged fetch for {target_id}",
            queue_command, "command-queue", "queueable-offline", "queues-until-phone-home",
            requires_target=True, queues_offline_work=True,
        )
        if records:
            records[-1]["run_command"] = base + " --run-staged-file-workflow-action " + shquote(f"{request}:queue-staged-fetch")
    else:
        add(
            "queue-staged-fetch", "mailbox", "Queue staged fetch for a selected target",
            base + " --target-id TARGET_ID --run-target-workflow-action queue-staged-fetch --target-workflow-request-name " + shquote(request),
            "command-queue", "needs-target", "target-required",
            available=False, requires_target=True, queues_offline_work=True,
        )
        if records:
            records[-1]["run_command"] = base + " --target-id TARGET_ID --run-staged-file-workflow-action " + shquote(f"{request}:queue-staged-fetch")
    add(
        "unstage", "configuration", f"Remove staged request {request}",
        base + " --unstage " + shquote(request) + " --list-staged",
        "file-service", "confirm-required", "confirmation-required",
        requires_confirmation=True,
    )
    if records:
        records[-1]["run_command"] = base + " --run-staged-file-workflow-action " + shquote(f"{request}:unstage") + " --confirm-staged-file-workflow-action"
    return records


def staged_file_workflow_action_records(cfg, staged_records, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    config_path = str(cfg.get("_config_path", default_config))
    base = "scripts/grit-console --config " + shquote(config_path)
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    targets_by_id = {str(rec.get("target_id") or ""): rec for rec in target_records if rec.get("target_id")}
    fleet_context = _staged_file_workflow_fleet_context(target_records)
    records = []
    for rec in staged_records or []:
        if not isinstance(rec, dict):
            continue
        records.extend(_staged_file_single_request_workflow_actions(
            base,
            targets_by_id,
            fleet_context,
            rec,
        ))
    records.sort(key=lambda rec: (rec.get("request_name", ""), rec.get("category", ""), rec.get("action_id", "")))
    return records


def staged_file_workflow_action_indexes(records):
    return {
        "staged_file_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "staged_file_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "staged_file_workflow_actions_by_request_name": records_by_key(records, "request_name"),
        "staged_file_workflow_actions_by_stage_kind": records_by_key(records, "stage_kind"),
        "staged_file_workflow_actions_by_category": records_by_key(records, "category"),
        "staged_file_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "staged_file_workflow_actions_by_target_id": records_by_key(records, "target_id"),
        "staged_file_workflow_actions_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "staged_file_workflow_actions_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "staged_file_workflow_actions_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "staged_file_workflow_actions_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "staged_file_workflow_actions_by_target_latest_phone_home_status": records_by_key(records, "target_latest_phone_home_status"),
        "staged_file_workflow_actions_by_target_latest_successful_phone_home_status": records_by_key(records, "target_latest_successful_phone_home_status"),
        "staged_file_workflow_actions_by_target_last_failed_phone_home_status": records_by_key(records, "target_last_failed_phone_home_status"),
        "staged_file_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "staged_file_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "staged_file_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "staged_file_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "staged_file_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "staged_file_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "staged_file_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "staged_file_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "staged_file_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "staged_file_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "staged_file_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "staged_file_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "staged_file_workflow_actions_by_source_exists": records_by_key(records, "source_exists"),
        "staged_file_workflow_actions_by_available": records_by_key(records, "available"),
        "staged_file_workflow_actions_by_requires_target": records_by_key(records, "requires_target"),
        "staged_file_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "staged_file_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "staged_file_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "staged_file_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "staged_file_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "staged_file_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def staged_file_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "request_counts": record_count_by_key(records, "request_name"),
        "stage_kind_counts": record_count_by_key(records, "stage_kind"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "target_counts": record_count_by_key(records, "target_id"),
        "target_connectivity_state_counts": record_count_by_key(records, "target_connectivity_state"),
        "target_offline_age_bucket_counts": record_count_by_key(records, "target_offline_age_bucket"),
        "target_poll_overdue_counts": record_count_by_key(records, "target_poll_overdue"),
        "target_mailbox_pending_work_count_counts": record_count_by_key(records, "target_mailbox_pending_work_count"),
        "target_latest_phone_home_status_counts": record_count_by_key(records, "target_latest_phone_home_status"),
        "target_latest_successful_phone_home_status_counts": record_count_by_key(records, "target_latest_successful_phone_home_status"),
        "target_last_failed_phone_home_status_counts": record_count_by_key(records, "target_last_failed_phone_home_status"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "action_counts": record_count_by_key(records, "action_id"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_target_count": len([rec for rec in records or [] if rec.get("requires_target") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "source_exists_counts": record_count_by_key(records, "source_exists"),
        "available_counts": record_count_by_key(records, "available"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }
