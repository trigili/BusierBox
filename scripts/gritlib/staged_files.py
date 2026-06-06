"""Staged file state, index, and summary helpers for grit-console."""

import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import attach_target_route_fields, target_route_context
from gritlib.event_log import append_event
from gritlib.file_fetch_commands import (
    print_staged_fetch_target_options, render_fetch_command,
)
from gritlib.line_search import line_record_selection_result
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import (
    records_by_key,
)
from gritlib.session_state import atomic_write_json, read_json_file, utc_now
import gritlib.staged_file_records as staged_file_records
import gritlib.staged_file_workflow_actions as staged_file_workflow_actions
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
    records = [
        {
            "name": name,
            "rec": staged.get(name) if isinstance(staged.get(name), dict) else {},
        }
        for name in sorted(str(item or "") for item in staged.keys() if str(item or ""))
    ]
    selected = line_record_selection_result(
        text,
        records,
        label="staged file",
        match_func=lambda rec, value: value == str(rec.get("name") or ""),
    )
    if selected.selected:
        name = str(selected.item.get("name") or "")
        rec = selected.item.get("rec") if isinstance(selected.item.get("rec"), dict) else {}
        return name, rec
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
        "indexes": staged_file_records.staged_record_indexes(staged_records),
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
    return staged_file_records.staged_record_indexes(records)

def staged_record_summary(records):
    return staged_file_records.staged_record_summary(records)


def staged_status_summary(records, workflow_action_records=None):
    return staged_file_records.staged_status_summary(
        records, workflow_action_records
    )


def staged_file_workflow_action_records(cfg, staged_records, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    return staged_file_workflow_actions.staged_file_workflow_action_records(
        cfg,
        staged_records,
        targets=targets,
        default_config=default_config,
    )


def staged_file_workflow_action_indexes(records):
    return staged_file_workflow_actions.staged_file_workflow_action_indexes(records)


def staged_file_workflow_action_summary(records):
    return staged_file_workflow_actions.staged_file_workflow_action_summary(records)
