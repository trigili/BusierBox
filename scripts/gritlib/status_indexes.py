"""Status index and health summary helpers for grit-console."""

import os
from pathlib import Path

from gritlib.record_utils import (
    int_value, record_count_by_key, records_by_bool, records_by_composite,
    records_by_key,
)


def operator_state_indexes(records):
    return {
        "operator_state_records_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "operator_state_records_by_kind": records_by_key(records, "kind"),
        "operator_state_records_by_status": records_by_key(records, "status"),
        "operator_state_records_by_exists": records_by_key(records, "exists"),
        "operator_state_records_by_valid": records_by_key(records, "valid"),
        "operator_state_records_by_unhealthy": records_by_key(records, "unhealthy"),
        "operator_state_records_by_severity": records_by_key(records, "severity"),
        "operator_state_records_by_remediation_class": records_by_key(records, "remediation_class"),
        "operator_state_records_by_requires_operator_action": records_by_key(records, "requires_operator_action"),
        "operator_state_records_by_path": {rec.get("path", ""): rec for rec in records or [] if rec.get("path")},
        "operator_state_records_by_kind_status": records_by_composite(records, ("kind", "status")),
    }


def operator_state_record(name, kind, path, exists, valid, record_count=0, error="", extra=None):
    if exists and not valid:
        status = "invalid"
    elif not exists:
        status = "missing"
    elif error:
        status = "error"
    else:
        status = "ok"
    requires_operator_action = status in ("invalid", "error")
    severity = "error" if requires_operator_action else ("warning" if status == "missing" else "info")
    remediation_class = "repair_operator_state" if requires_operator_action else ("initialize_operator_state" if status == "missing" else "none")
    suggested_action = ""
    if status == "invalid":
        suggested_action = "inspect, repair, archive, or remove the invalid operator state file"
    elif status == "error":
        suggested_action = "inspect operator state file permissions and filesystem errors"
    elif status == "missing":
        suggested_action = "state will be created when the related operator workflow is used"
    rec = {
        "name": name,
        "kind": kind,
        "path": str(path),
        "exists": bool(exists),
        "valid": bool(valid),
        "status": status,
        "unhealthy": status in ("missing", "invalid", "error"),
        "severity": severity,
        "remediation_class": remediation_class,
        "requires_operator_action": requires_operator_action,
        "suggested_action": suggested_action,
        "record_count": int(record_count or 0),
        "error": str(error or ""),
    }
    if extra:
        rec.update(extra)
    return rec


def operator_state_health_counts(records):
    counts = record_count_by_key(records, "status")
    unhealthy = sum(int(counts.get(key, 0) or 0) for key in ("missing", "invalid", "error"))
    return {
        "ok": int(counts.get("ok", 0) or 0),
        "missing": int(counts.get("missing", 0) or 0),
        "invalid": int(counts.get("invalid", 0) or 0),
        "error": int(counts.get("error", 0) or 0),
        "unhealthy": unhealthy,
        "status_counts": counts,
        "severity_counts": record_count_by_key(records, "severity"),
        "remediation_class_counts": record_count_by_key(records, "remediation_class"),
        "requires_operator_action_counts": record_count_by_key(records, "requires_operator_action"),
    }


def status_path_records(paths):
    records = {}
    dir_keys = {"operator_session_dir", "session_root"}
    for name, raw_path in (paths or {}).items():
        path_text = str(raw_path or "")
        rec = {
            "name": name,
            "path": path_text,
            "expected_kind": "dir" if name in dir_keys else "file",
            "expected_kind_matches": False,
            "expected_kind_mismatch": False,
            "exists": False,
            "is_file": False,
            "is_dir": False,
            "parent": "",
            "parent_exists": False,
            "readable": False,
            "writable": False,
        }
        if not path_text:
            records[name] = rec
            continue
        path = Path(path_text)
        parent = path.parent
        rec["parent"] = str(parent)
        try:
            rec["exists"] = path.exists()
            rec["is_file"] = path.is_file()
            rec["is_dir"] = path.is_dir()
            rec["parent_exists"] = parent.exists()
            rec["readable"] = bool(rec["exists"] and os.access(path, os.R_OK))
            if rec["exists"]:
                rec["writable"] = os.access(path, os.W_OK)
            else:
                rec["writable"] = bool(rec["parent_exists"] and os.access(parent, os.W_OK))
            if rec["exists"]:
                if rec["expected_kind"] == "dir":
                    rec["expected_kind_matches"] = bool(rec["is_dir"])
                elif rec["expected_kind"] == "file":
                    rec["expected_kind_matches"] = bool(rec["is_file"])
                else:
                    rec["expected_kind_matches"] = True
                rec["expected_kind_mismatch"] = not rec["expected_kind_matches"]
        except OSError as exc:
            rec["error"] = str(exc)
        records[name] = rec
    return records


def status_path_summary(records):
    missing = 0
    parent_missing = 0
    not_writable = 0
    kind_mismatch = 0
    for rec in (records or {}).values():
        if not rec.get("exists"):
            missing += 1
        if not rec.get("parent_exists"):
            parent_missing += 1
        if not rec.get("writable"):
            not_writable += 1
        if rec.get("expected_kind_mismatch"):
            kind_mismatch += 1
    return {
        "path_status_count": len(records or {}),
        "path_missing_count": missing,
        "path_parent_missing_count": parent_missing,
        "path_not_writable_count": not_writable,
        "path_kind_mismatch_count": kind_mismatch,
    }


def status_path_record_list(records):
    return list((records or {}).values())


def status_path_record_indexes(records):
    return {
        "path_status_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "path_status_by_path": records_by_key(records, "path"),
        "path_status_by_expected_kind": records_by_key(records, "expected_kind"),
        "path_status_by_exists": records_by_bool(records, "exists"),
        "path_status_by_parent_exists": records_by_bool(records, "parent_exists"),
        "path_status_by_writable": records_by_bool(records, "writable"),
        "path_status_by_expected_kind_mismatch": records_by_bool(records, "expected_kind_mismatch"),
    }


def browser_path_status(path_text, expected_kind="file"):
    rec = {
        "path": str(path_text or ""),
        "expected_kind": expected_kind,
        "expected_kind_matches": False,
        "expected_kind_mismatch": False,
        "exists": False,
        "is_file": False,
        "is_dir": False,
        "parent": "",
        "parent_exists": False,
        "readable": False,
        "writable": False,
        "error": "",
    }
    if not rec["path"]:
        return rec
    path = Path(rec["path"])
    parent = path.parent
    rec["parent"] = str(parent)
    try:
        rec["exists"] = path.exists()
        rec["is_file"] = path.is_file()
        rec["is_dir"] = path.is_dir()
        rec["parent_exists"] = parent.exists()
        rec["readable"] = bool(rec["exists"] and os.access(path, os.R_OK))
        if rec["exists"]:
            rec["writable"] = os.access(path, os.W_OK)
        else:
            rec["writable"] = bool(rec["parent_exists"] and os.access(parent, os.W_OK))
        if rec["exists"]:
            if rec["expected_kind"] == "dir":
                rec["expected_kind_matches"] = bool(rec["is_dir"])
            elif rec["expected_kind"] == "file":
                rec["expected_kind_matches"] = bool(rec["is_file"])
            else:
                rec["expected_kind_matches"] = True
            rec["expected_kind_mismatch"] = not rec["expected_kind_matches"]
    except OSError as exc:
        rec["error"] = str(exc)
    return rec


def add_browser_path(records, kind, label, path_text, expected_kind="file", source_id="", description="", metadata=None):
    path_text = str(path_text or "")
    if not path_text:
        return
    rec = {
        "id": f"{kind}:{len(records) + 1}",
        "kind": kind,
        "label": str(label or kind),
        "path": path_text,
        "source_id": str(source_id or ""),
        "description": str(description or ""),
    }
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if value not in (None, ""):
                rec[key] = value
    rec.update(browser_path_status(path_text, expected_kind=expected_kind))
    records.append(rec)


def browser_path_indexes(records):
    by_kind = {}
    by_path = {}
    by_source_id = {}
    by_stage_kind = {}
    by_release_path = {}
    by_kind_source_id = {}
    by_exists = records_by_bool(records, "exists")
    by_readable = records_by_bool(records, "readable")
    by_writable = records_by_bool(records, "writable")
    by_expected_kind_mismatch = records_by_bool(records, "expected_kind_mismatch")
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        path = str(rec.get("path") or "")
        source_id = str(rec.get("source_id") or "")
        stage_kind = str(rec.get("stage_kind") or "")
        release_path = str(rec.get("release_path") or "")
        if kind:
            by_kind.setdefault(kind, []).append(rec)
        if path:
            by_path.setdefault(path, []).append(rec)
        if source_id:
            by_source_id.setdefault(source_id, []).append(rec)
        if stage_kind:
            by_stage_kind.setdefault(stage_kind, []).append(rec)
        if release_path:
            by_release_path.setdefault(release_path, []).append(rec)
        if kind and source_id:
            by_kind_source_id.setdefault(f"{kind}:{source_id}", []).append(rec)
    return (
        by_kind, by_path, by_source_id, by_stage_kind, by_release_path,
        by_kind_source_id, by_exists, by_readable, by_writable,
        by_expected_kind_mismatch,
    )


def browser_path_summary(records):
    exists_by_kind = {}
    missing_by_kind = {}
    readable_by_kind = {}
    writable_by_kind = {}
    kind_mismatch_by_kind = {}
    warning_by_kind = {}
    warning_by_type = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        if not kind:
            continue
        if rec.get("exists") is True:
            exists_by_kind[kind] = exists_by_kind.get(kind, 0) + 1
        else:
            missing_by_kind[kind] = missing_by_kind.get(kind, 0) + 1
        if rec.get("readable") is True:
            readable_by_kind[kind] = readable_by_kind.get(kind, 0) + 1
        if rec.get("writable") is True:
            writable_by_kind[kind] = writable_by_kind.get(kind, 0) + 1
        if rec.get("expected_kind_mismatch") is True:
            kind_mismatch_by_kind[kind] = kind_mismatch_by_kind.get(kind, 0) + 1
        warning_count = int(rec.get("warning_count") or 0)
        if warning_count:
            warning_by_kind[kind] = warning_by_kind.get(kind, 0) + warning_count
            for warning_type in rec.get("warning_types") or []:
                warning_type = str(warning_type or "")
                if warning_type:
                    warning_by_type[warning_type] = warning_by_type.get(warning_type, 0) + 1
    return {
        "total_count": len(records or []),
        "exists_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("exists") is True),
        "missing_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("exists") is not True),
        "readable_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("readable") is True),
        "writable_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("writable") is True),
        "kind_mismatch_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("expected_kind_mismatch") is True),
        "warning_count": sum(int(rec.get("warning_count") or 0) for rec in records or [] if isinstance(rec, dict)),
        "by_kind": record_count_by_key(records, "kind"),
        "by_stage_kind": record_count_by_key(records, "stage_kind"),
        "by_release_path": record_count_by_key(records, "release_path"),
        "exists_by_kind": exists_by_kind,
        "missing_by_kind": missing_by_kind,
        "readable_by_kind": readable_by_kind,
        "writable_by_kind": writable_by_kind,
        "kind_mismatch_by_kind": kind_mismatch_by_kind,
        "warning_by_kind": warning_by_kind,
        "warning_by_type": warning_by_type,
    }


def warning_health_indexes(records):
    by_has_warnings = {"yes": [], "no": []}
    by_warning_type = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        warning_count = int_value(rec.get("warning_count"))
        by_has_warnings["yes" if warning_count > 0 else "no"].append(rec)
        for warning_type in rec.get("warning_types") or []:
            warning_type = str(warning_type or "")
            if warning_type:
                by_warning_type.setdefault(warning_type, []).append(rec)
    return by_has_warnings, by_warning_type


def operator_network_status(ips):
    selected_local_ip = (ips or ["OPERATOR_IP"])[0]
    operator_network_records = [
        {
            "id": f"local-ip-{idx}",
            "kind": "local-ip",
            "ip": ip,
            "ordinal": idx,
            "selected": ip == selected_local_ip,
            "placeholder": ip == "OPERATOR_IP",
            "source": "detected" if ip != "OPERATOR_IP" else "placeholder",
            "usable_for_generated_commands": ip != "OPERATOR_IP",
        }
        for idx, ip in enumerate(ips or ["OPERATOR_IP"])
    ]
    operator_network_index_maps = {
        "operator_network_records_by_id": {rec["id"]: rec for rec in operator_network_records},
        "operator_network_records_by_kind": records_by_key(operator_network_records, "kind"),
        "operator_network_records_by_ip": records_by_key(operator_network_records, "ip"),
        "operator_network_records_by_selected": records_by_key(operator_network_records, "selected"),
        "operator_network_records_by_placeholder": records_by_key(operator_network_records, "placeholder"),
        "operator_network_records_by_source": records_by_key(operator_network_records, "source"),
        "operator_network_records_by_usable_for_generated_commands": records_by_key(
            operator_network_records, "usable_for_generated_commands"
        ),
    }
    selected_operator_network_record = next(
        (rec for rec in operator_network_records if rec.get("selected")),
        operator_network_records[0] if operator_network_records else {},
    )
    operator_network_state_record = {
        "id": "operator-network",
        "selected_ip": selected_local_ip,
        "selected_source": selected_operator_network_record.get("source", ""),
        "selected_placeholder": bool(selected_operator_network_record.get("placeholder", False)),
        "selected_usable_for_generated_commands": bool(
            selected_operator_network_record.get("usable_for_generated_commands", False)
        ),
        "record_count": len(operator_network_records),
        "detected_ip_count": len([rec for rec in operator_network_records if rec.get("source") == "detected"]),
        "placeholder_count": len([rec for rec in operator_network_records if rec.get("placeholder")]),
        "usable_for_generated_commands_count": len([
            rec for rec in operator_network_records
            if rec.get("usable_for_generated_commands")
        ]),
    }
    operator_network_state_record.update({
        "has_detected_ip": operator_network_state_record.get("detected_ip_count", 0) > 0,
        "uses_placeholder": bool(operator_network_state_record.get("selected_placeholder", False)),
        "has_generated_command_ip": bool(operator_network_state_record.get("selected_usable_for_generated_commands", False)),
        "has_multiple_ips": operator_network_state_record.get("record_count", 0) > 1,
    })
    operator_network_state_records = [operator_network_state_record]
    operator_network_state_index_maps = {
        "operator_network_state_records_by_id": {
            rec.get("id", ""): rec for rec in operator_network_state_records if rec.get("id")
        },
        "operator_network_state_records_by_selected_ip": records_by_key(operator_network_state_records, "selected_ip"),
        "operator_network_state_records_by_selected_source": records_by_key(operator_network_state_records, "selected_source"),
        "operator_network_state_records_by_selected_placeholder": records_by_key(
            operator_network_state_records, "selected_placeholder"
        ),
        "operator_network_state_records_by_has_detected_ip": records_by_key(operator_network_state_records, "has_detected_ip"),
        "operator_network_state_records_by_uses_placeholder": records_by_key(operator_network_state_records, "uses_placeholder"),
        "operator_network_state_records_by_has_generated_command_ip": records_by_key(
            operator_network_state_records, "has_generated_command_ip"
        ),
        "operator_network_state_records_by_has_multiple_ips": records_by_key(
            operator_network_state_records, "has_multiple_ips"
        ),
    }
    return {
        "selected_local_ip": selected_local_ip,
        "operator_network_records": operator_network_records,
        "operator_network_index_maps": operator_network_index_maps,
        "operator_network_state_record": operator_network_state_record,
        "operator_network_state_records": operator_network_state_records,
        "operator_network_state_index_maps": operator_network_state_index_maps,
    }
