"""Status index and health summary helpers for grit-console."""

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
