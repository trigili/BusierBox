"""Staged file state, index, and summary helpers for grit-console."""

import hashlib
import json
import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import attach_target_route_fields, target_route_context
from gritlib.event_log import append_event
from gritlib.file_transfers import print_staged_fetch_target_options
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.session_state import atomic_write_json, read_json_file, utc_now
from gritlib.target_records import configured_target_filter, target_context_fields


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


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
