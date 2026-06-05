"""Warning status context builders for grit-console status documents."""

from gritlib.config_utils import DEFAULT_CONFIG
import gritlib.command_queue as command_queue_module
import gritlib.status_indexes as status_indexes
import gritlib.target_records as target_records
import gritlib.warnings as warnings_module


def _build_warning_status_context(
    cfg,
    *,
    warnings,
    path_status,
    path_status_records,
    browser_paths,
    server_state,
    staged_files_state,
    command_queue_state,
    release_state,
    target_filter_id,
    selected_target,
    unfiltered_counts,
    event_stats,
    command_queue,
    target_command_records,
    services,
    ports,
    services_by_name,
):
    _append_warning_status_records(
        cfg,
        warnings=warnings,
        path_status=path_status,
        server_state=server_state,
        staged_files_state=staged_files_state,
        command_queue_state=command_queue_state,
        release_state=release_state,
        target_filter_id=target_filter_id,
        selected_target=selected_target,
        unfiltered_counts=unfiltered_counts,
        event_stats=event_stats,
        command_queue=command_queue,
        target_command_records=target_command_records,
    )
    return _build_warning_index_status_context(
        warnings=warnings,
        path_status=path_status,
        path_status_records=path_status_records,
        browser_paths=browser_paths,
        services=services,
        ports=ports,
        services_by_name=services_by_name,
    )

def _append_warning_status_records(
    cfg,
    *,
    warnings,
    path_status,
    server_state,
    staged_files_state,
    command_queue_state,
    release_state,
    target_filter_id,
    selected_target,
    unfiltered_counts,
    event_stats,
    command_queue,
    target_command_records,
):
    _append_path_warning_status_records(warnings, path_status)
    _append_state_warning_status_records(
        warnings,
        server_state=server_state,
        staged_files_state=staged_files_state,
        command_queue_state=command_queue_state,
    )
    _append_release_target_event_policy_warning_records(
        cfg,
        warnings=warnings,
        release_state=release_state,
        target_filter_id=target_filter_id,
        selected_target=selected_target,
        unfiltered_counts=unfiltered_counts,
        event_stats=event_stats,
        command_queue=command_queue,
    )
    _append_rshell_policy_warning_status_records(
        cfg, warnings=warnings, target_command_records=target_command_records
    )

def _append_path_warning_status_records(warnings, path_status):
    for name, rec in sorted((path_status or {}).items()):
        if not rec.get("expected_kind_mismatch"):
            continue
        warnings.append({
            "type": "operator_path_kind_mismatch",
            "path_name": name,
            "path": rec.get("path", ""),
            "expected_kind": rec.get("expected_kind", ""),
            "is_file": bool(rec.get("is_file", False)),
            "is_dir": bool(rec.get("is_dir", False)),
            "message": "operator path exists with the wrong filesystem kind",
            "suggested_action": "fix the configured path or remove the conflicting file/directory",
        })

def _append_state_warning_status_records(
    warnings,
    *,
    server_state,
    staged_files_state,
    command_queue_state,
):
    state_warning_records = (
        ("invalid_server_state", server_state, "server-state ledger is invalid"),
        ("invalid_staged_files_state", staged_files_state, "staged-files ledger is invalid"),
        ("invalid_command_queue_state", command_queue_state, "command queue ledger is invalid"),
    )
    for warning_type, rec, message in state_warning_records:
        if not rec.get("exists") or rec.get("valid"):
            continue
        warnings.append({
            "type": warning_type,
            "path": rec.get("path", ""),
            "error": rec.get("error", ""),
            "message": message,
            "suggested_action": "inspect, repair, archive, or remove the invalid operator state file",
        })

def _append_release_target_event_policy_warning_records(
    cfg,
    *,
    warnings,
    release_state,
    target_filter_id,
    selected_target,
    unfiltered_counts,
    event_stats,
    command_queue,
):
    if release_state.get("present") and not release_state.get("valid"):
        warnings.append({
            "type": "invalid_release_state",
            "path": release_state.get("release_dir", ""),
            "release_json": release_state.get("release_json", ""),
            "release_index": release_state.get("release_index", ""),
            "errors": release_state.get("errors") or [],
            "message": "release bundle state is invalid",
            "suggested_action": "inspect release.json, release-index.json, bin/, and scripts/ before using release browser results",
        })
    if target_filter_id and not selected_target:
        warnings.append({
            "type": "unknown_target_filter",
            "target_id": target_filter_id,
            "targets_file": str(target_records.targets_path(cfg)),
            "unfiltered_target_count": unfiltered_counts.get("targets", 0),
            "message": "target filter did not match any known target record",
            "suggested_action": "inspect targets.json, remove the filter, or set a label for the target id",
        })
    if event_stats["invalid_count"]:
        warnings.append({
            "type": "invalid_event_log",
            "path": event_stats["path"],
            "invalid_count": event_stats["invalid_count"],
            "message": "operator event log contains invalid JSONL records",
            "suggested_action": "inspect or archive the event log before relying on event history",
        })
    if not command_queue.get("policy_valid", True):
        warnings.append({
            "type": "invalid_command_queue_policy",
            "path": command_queue.get(
                "path", str(command_queue_module.command_queue_path(cfg))
            ),
            "policy_errors": command_queue.get("policy_errors") or [],
            "message": "command queue policy is invalid; target polling is not configured",
            "suggested_action": "fix command queue config or leave it fully disabled",
        })

def _append_rshell_policy_warning_status_records(
    cfg,
    *,
    warnings,
    target_command_records,
):
    rshell_policy_metadata = next((
        rec.get("metadata") for rec in target_command_records
        if rec.get("service") == "rshell" and isinstance(rec.get("metadata"), dict)
    ), {})
    if rshell_policy_metadata and not rshell_policy_metadata.get("session_policy_valid", True):
        warnings.append({
            "type": "invalid_rshell_session_policy",
            "path": str(cfg.get("_config_path", DEFAULT_CONFIG)),
            "session_policy": rshell_policy_metadata.get("session_policy", ""),
            "session_policy_errors": rshell_policy_metadata.get("session_policy_errors") or [],
            "message": "rshell session policy is invalid; generated target command metadata is not usable for reconnect decisions",
            "suggested_action": "set rshell_session_policy to single, reconnect, or persistent",
        })

def _build_warning_index_status_context(
    *,
    warnings,
    path_status,
    path_status_records,
    browser_paths,
    services,
    ports,
    services_by_name,
):
    warnings_module.annotate_warning_records(warnings)
    warning_index_maps = warnings_module.warning_record_indexes(warnings)
    (warnings_by_type,
     warnings_by_severity,
     warnings_by_remediation_class,
     warnings_by_type_severity,
     warnings_by_service,
     warnings_by_port,
     warnings_by_pid,
     warnings_by_listener_pid,
     warnings_by_owner_pid,
     warnings_by_path,
     warnings_by_type_path,
     warnings_by_service_port,
     warnings_by_type_service_port) = warning_index_maps
    warnings_module.annotate_path_records_with_warnings(
        path_status, browser_paths, warnings_by_path
    )
    path_warning_context = status_indexes.path_warning_status_context(
        path_status_records, browser_paths
    )
    warnings_module.annotate_service_port_records_with_warnings(
        services,
        ports,
        warnings_by_service,
        warnings_by_port,
        warnings_by_pid,
        warnings_by_listener_pid,
    )
    for row in services:
        mapped = services_by_name.get(row.get("name", ""))
        if mapped is not None:
            mapped["warning_count"] = row.get("warning_count", 0)
            mapped["warning_types"] = row.get("warning_types", [])
    services_by_has_warnings, services_by_warning_type = (
        status_indexes.warning_health_indexes(services)
    )
    ports_by_has_warnings, ports_by_warning_type = (
        status_indexes.warning_health_indexes(ports)
    )
    return {
        "warning_index_maps": warning_index_maps,
        "path_warning_context": path_warning_context,
        "browser_summary": path_warning_context["browser_summary"],
        "services_by_has_warnings": services_by_has_warnings,
        "services_by_warning_type": services_by_warning_type,
        "ports_by_has_warnings": ports_by_has_warnings,
        "ports_by_warning_type": ports_by_warning_type,
    }

def _build_warning_summary_status_context(
    warnings,
    *,
    services_by_has_warnings,
    services_by_warning_type,
    ports_by_has_warnings,
    ports_by_warning_type,
):
    warning_summary = warnings_module.warning_stats(warnings)
    return {
        "warning_summary": warning_summary,
        "summary": warnings_module.warning_status_summary(
            warning_summary,
            services_by_has_warnings,
            services_by_warning_type,
            ports_by_has_warnings,
            ports_by_warning_type,
        ),
    }


def build_warning_status_context(*args, **kwargs):
    return _build_warning_status_context(*args, **kwargs)


def build_warning_summary_status_context(*args, **kwargs):
    return _build_warning_summary_status_context(*args, **kwargs)
