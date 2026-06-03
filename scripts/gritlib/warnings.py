"""Warning classification, index, annotation, and display helpers for grit-console."""

from gritlib.record_utils import format_counts


def warning_badge_suffix(row):
    count = int(row.get("warning_count") or 0)
    if count <= 0:
        return ""
    types = ",".join(str(item) for item in (row.get("warning_types") or []) if item)
    if types:
        return f" warnings={count}:{types}"
    return f" warnings={count}"


def print_warning_summary(summary):
    summary = summary or {}
    print(
        "Warning summary: "
        f"total={summary.get('warning_count', 0)} "
        f"types={format_counts(summary.get('warning_type_counts') or {})} "
        f"severity={format_counts(summary.get('warning_severity_counts') or {})} "
        f"remediation={format_counts(summary.get('warning_remediation_class_counts') or {})} "
        f"services={format_counts(summary.get('warning_service_counts') or {})} "
        f"ports={format_counts(summary.get('warning_port_counts') or {})}"
    )


def warning_stats(warnings):
    (by_type,
     by_severity,
     by_remediation_class,
     by_type_severity,
     by_service,
     by_port,
     by_pid,
     by_listener_pid,
     by_owner_pid,
     by_path,
     by_type_path,
     by_service_port,
     by_type_service_port) = warning_record_indexes(warnings)
    count_records = lambda records: {key: len(value) for key, value in records.items()}
    return {
        "total_count": len(warnings or []),
        "by_type": count_records(by_type),
        "by_severity": count_records(by_severity),
        "by_remediation_class": count_records(by_remediation_class),
        "by_type_severity": count_records(by_type_severity),
        "by_service": count_records(by_service),
        "by_port": count_records(by_port),
        "by_pid": count_records(by_pid),
        "by_listener_pid": count_records(by_listener_pid),
        "by_owner_pid": count_records(by_owner_pid),
        "by_path": count_records(by_path),
        "by_type_path": count_records(by_type_path),
        "by_service_port": count_records(by_service_port),
        "by_type_service_port": count_records(by_type_service_port),
    }


def warning_record_paths(item):
    paths = []
    for key in ("path", "release_json", "release_index", "process_log", "session_log"):
        value = str((item or {}).get(key) or "")
        if value and value not in paths:
            paths.append(value)
    return paths


def warning_classification(warning_type):
    mapping = {
        "service_error": ("error", "stop_or_reconfigure_service"),
        "stale_state": ("warning", "stop_or_clean_state"),
        "unexpected_listener": ("warning", "inspect_listener"),
        "listener_bind_mismatch": ("warning", "inspect_listener"),
        "unmanaged_recorded_pid": ("warning", "inspect_process"),
        "operator_path_kind_mismatch": ("error", "fix_operator_path"),
        "invalid_server_state": ("error", "repair_operator_state"),
        "invalid_staged_files_state": ("error", "repair_operator_state"),
        "invalid_command_queue_state": ("error", "repair_operator_state"),
        "invalid_release_state": ("error", "repair_release_state"),
        "invalid_event_log": ("warning", "inspect_event_log"),
        "invalid_command_queue_policy": ("error", "fix_policy"),
        "invalid_rshell_session_policy": ("error", "fix_policy"),
    }
    return mapping.get(str(warning_type or ""), ("warning", "inspect"))


def annotate_warning_records(warnings):
    for item in warnings or []:
        if not isinstance(item, dict):
            continue
        severity, remediation = warning_classification(item.get("type"))
        item.setdefault("severity", severity)
        item.setdefault("remediation_class", remediation)
        item.setdefault("requires_operator_action", item.get("severity") in ("error", "warning"))


def warning_record_indexes(warnings):
    by_type = {}
    by_severity = {}
    by_remediation_class = {}
    by_type_severity = {}
    by_service = {}
    by_port = {}
    by_pid = {}
    by_listener_pid = {}
    by_owner_pid = {}
    by_path = {}
    by_type_path = {}
    by_service_port = {}
    by_type_service_port = {}
    for item in warnings or []:
        if not isinstance(item, dict):
            continue
        warning_type = str(item.get("type") or "")
        severity = str(item.get("severity") or "")
        remediation_class = str(item.get("remediation_class") or "")
        service = str(item.get("service") or "")
        port = item.get("port")
        port_key = str(port) if port not in (None, "", 0) else ""
        pid = str(item.get("pid") or "")
        if warning_type:
            by_type.setdefault(warning_type, []).append(item)
        if severity:
            by_severity.setdefault(severity, []).append(item)
        if remediation_class:
            by_remediation_class.setdefault(remediation_class, []).append(item)
        if warning_type and severity:
            by_type_severity.setdefault(f"{warning_type}:{severity}", []).append(item)
        if service:
            by_service.setdefault(service, []).append(item)
        if port_key:
            by_port.setdefault(port_key, []).append(item)
        if service and port_key:
            service_port = f"{service}:{port_key}"
            by_service_port.setdefault(service_port, []).append(item)
            if warning_type:
                by_type_service_port.setdefault(f"{warning_type}:{service_port}", []).append(item)
        if pid:
            by_pid.setdefault(pid, []).append(item)
        for listener_pid in item.get("listener_pids") or []:
            listener_pid = str(listener_pid or "")
            if listener_pid:
                by_listener_pid.setdefault(listener_pid, []).append(item)
        for owner in item.get("owners") or []:
            if not isinstance(owner, dict):
                continue
            owner_pid = str(owner.get("pid") or "")
            if owner_pid:
                by_owner_pid.setdefault(owner_pid, []).append(item)
        for path in warning_record_paths(item):
            by_path.setdefault(path, []).append(item)
            if warning_type:
                by_type_path.setdefault(f"{warning_type}:{path}", []).append(item)
    return (
        by_type,
        by_severity,
        by_remediation_class,
        by_type_severity,
        by_service,
        by_port,
        by_pid,
        by_listener_pid,
        by_owner_pid,
        by_path,
        by_type_path,
        by_service_port,
        by_type_service_port,
    )


def annotate_path_records_with_warnings(path_status, browser_paths, warnings_by_path):
    warnings_by_path = warnings_by_path or {}
    for rec in (path_status or {}).values():
        if not isinstance(rec, dict):
            continue
        path = str(rec.get("path") or "")
        warnings = warnings_by_path.get(path) or []
        rec["warning_count"] = len(warnings)
        rec["warning_types"] = sorted({str(item.get("type") or "") for item in warnings if item.get("type")})
    for rec in browser_paths or []:
        if not isinstance(rec, dict):
            continue
        path = str(rec.get("path") or "")
        warnings = warnings_by_path.get(path) or []
        rec["warning_count"] = len(warnings)
        rec["warning_types"] = sorted({str(item.get("type") or "") for item in warnings if item.get("type")})


def annotate_service_port_records_with_warnings(services, ports, warnings_by_service, warnings_by_port, warnings_by_pid, warnings_by_listener_pid):
    def collect_warning_records(rec, service_key="name"):
        seen = set()
        out = []

        def add(items):
            for item in items or []:
                ident = id(item)
                if ident in seen:
                    continue
                seen.add(ident)
                out.append(item)

        service = str(rec.get(service_key) or "")
        port = rec.get("port")
        pid = str(rec.get("pid") or "")
        if service:
            add((warnings_by_service or {}).get(service))
        if port not in (None, "", 0):
            add((warnings_by_port or {}).get(str(port)))
        if pid:
            add((warnings_by_pid or {}).get(pid))
        for listener_pid in rec.get("listener_pids") or []:
            listener_pid = str(listener_pid or "")
            if listener_pid:
                add((warnings_by_listener_pid or {}).get(listener_pid))
        return out

    for rec in services or []:
        if not isinstance(rec, dict):
            continue
        warnings = collect_warning_records(rec, service_key="name")
        rec["warning_count"] = len(warnings)
        rec["warning_types"] = sorted({str(item.get("type") or "") for item in warnings if item.get("type")})
    for rec in ports or []:
        if not isinstance(rec, dict):
            continue
        warnings = collect_warning_records(rec, service_key="service")
        rec["warning_count"] = len(warnings)
        rec["warning_types"] = sorted({str(item.get("type") or "") for item in warnings if item.get("type")})
