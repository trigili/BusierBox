"""Staged file state, index, and summary helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import record_count_by_key


def staged_file_path(cfg):
    return Path(str(cfg.get("staged_files", "local/operator-session/staged-files.json")))


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
