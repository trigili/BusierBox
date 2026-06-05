"""Tail status context assembly for grit-console."""

import gritlib.status_operator_contexts as status_operator_contexts
import gritlib.status_warnings as status_warnings
import gritlib.status_workflow_contexts as status_workflow_contexts


def _status_tail_operator_state_fields(operator_state_context):
    return {
        "operator_state_context": operator_state_context,
        "server_state": operator_state_context["server_state"],
        "server_state_records": operator_state_context["server_state_records"],
        "server_state_index_maps": operator_state_context["server_state_index_maps"],
        "staged_files_state": operator_state_context["staged_files_state"],
        "staged_files_state_records": operator_state_context[
            "staged_files_state_records"
        ],
        "staged_files_state_index_maps": operator_state_context[
            "staged_files_state_index_maps"
        ],
        "command_queue_state": operator_state_context["command_queue_state"],
        "command_queue_state_records": operator_state_context[
            "command_queue_state_records"
        ],
        "command_queue_state_index_maps": operator_state_context[
            "command_queue_state_index_maps"
        ],
        "command_copy": operator_state_context["command_copy"],
        "command_copy_records": operator_state_context["command_copy_records"],
        "command_copy_record_indexes": operator_state_context[
            "command_copy_record_indexes"
        ],
        "command_copy_state_record": operator_state_context[
            "command_copy_state_record"
        ],
        "command_copy_state_records": operator_state_context[
            "command_copy_state_records"
        ],
        "command_copy_state_index_maps": operator_state_context[
            "command_copy_state_index_maps"
        ],
        "workbench_jobs_state": operator_state_context["workbench_jobs_state"],
        "workbench_jobs_state_records": operator_state_context[
            "workbench_jobs_state_records"
        ],
        "workbench_jobs_state_index_maps": operator_state_context[
            "workbench_jobs_state_index_maps"
        ],
        "operator_state_records_list": operator_state_context[
            "operator_state_records_list"
        ],
        "operator_state_index_maps": operator_state_context[
            "operator_state_index_maps"
        ],
        "operator_state_summary": operator_state_context["operator_state_summary"],
        "operator_state_file_summary_doc": operator_state_context[
            "operator_state_file_summary_doc"
        ],
    }


def _status_tail_path_browser_fields(path_browser_context):
    return {
        "path_browser_context": path_browser_context,
        "path_context": path_browser_context["path_context"],
        "path_status": path_browser_context["path_status"],
        "path_status_records": path_browser_context["path_status_records"],
        "path_status_indexes": path_browser_context["path_status_indexes"],
        "browser_paths": path_browser_context["browser_paths"],
        "browser_path_index_maps": path_browser_context["browser_path_index_maps"],
        "browser_summary": path_browser_context["browser_summary"],
    }


def _status_tail_command_queue_workflow_fields(command_queue_workflow_context):
    return {
        "command_queue_workflow_context": command_queue_workflow_context,
        "command_queue_workflow_actions": command_queue_workflow_context[
            "command_queue_workflow_actions"
        ],
        "command_queue_workflow_action_index_maps": command_queue_workflow_context[
            "command_queue_workflow_action_index_maps"
        ],
    }


def _status_tail_warning_fields(warning_context):
    (
        warnings_by_type,
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
        warnings_by_type_service_port,
    ) = warning_context["warning_index_maps"]
    path_warning_context = warning_context["path_warning_context"]
    return {
        "warning_context": warning_context,
        "warnings_by_type": warnings_by_type,
        "warnings_by_severity": warnings_by_severity,
        "warnings_by_remediation_class": warnings_by_remediation_class,
        "warnings_by_type_severity": warnings_by_type_severity,
        "warnings_by_service": warnings_by_service,
        "warnings_by_port": warnings_by_port,
        "warnings_by_pid": warnings_by_pid,
        "warnings_by_listener_pid": warnings_by_listener_pid,
        "warnings_by_owner_pid": warnings_by_owner_pid,
        "warnings_by_path": warnings_by_path,
        "warnings_by_type_path": warnings_by_type_path,
        "warnings_by_service_port": warnings_by_service_port,
        "warnings_by_type_service_port": warnings_by_type_service_port,
        "path_warning_context": path_warning_context,
        "path_status_by_has_warnings": path_warning_context[
            "path_status_by_has_warnings"
        ],
        "path_status_by_warning_type": path_warning_context[
            "path_status_by_warning_type"
        ],
        "browser_paths_by_has_warnings": path_warning_context[
            "browser_paths_by_has_warnings"
        ],
        "browser_paths_by_warning_type": path_warning_context[
            "browser_paths_by_warning_type"
        ],
        "browser_summary": warning_context["browser_summary"],
        "services_by_has_warnings": warning_context["services_by_has_warnings"],
        "services_by_warning_type": warning_context["services_by_warning_type"],
        "ports_by_has_warnings": warning_context["ports_by_has_warnings"],
        "ports_by_warning_type": warning_context["ports_by_warning_type"],
    }


def _status_tail_service_probe_fields(service_probe_workflow_context):
    return {
        "service_probe_workflow_context": service_probe_workflow_context,
        "service_workflow_actions": service_probe_workflow_context[
            "service_workflow_actions"
        ],
        "service_workflow_action_index_maps": service_probe_workflow_context[
            "service_workflow_action_index_maps"
        ],
        "probe_workflow_actions": service_probe_workflow_context[
            "probe_workflow_actions"
        ],
        "probe_workflow_action_index_maps": service_probe_workflow_context[
            "probe_workflow_action_index_maps"
        ],
    }


def _status_tail_operator_console_fields(operator_console_workflow_context):
    return {
        "operator_console_workflow_context": operator_console_workflow_context,
        "operator_console_workflows": operator_console_workflow_context[
            "operator_console_workflows"
        ],
        "operator_console_workflow_index_maps": operator_console_workflow_context[
            "operator_console_workflow_index_maps"
        ],
        "operator_console_workflow_stats": operator_console_workflow_context[
            "operator_console_workflow_stats"
        ],
    }


def _status_tail_warning_summary_fields(warning_summary_context):
    return {
        "warning_summary_context": warning_summary_context,
        "warning_summary": warning_summary_context["warning_summary"],
    }


def _build_status_tail_operator_path_context(
    cfg, foundation_context, activity_queue_context
):
    f = foundation_context
    aq = activity_queue_context
    paths = status_operator_contexts.status_tail_paths(cfg, f)
    operator_state_context = status_operator_contexts.build_operator_state_status_context(
        cfg,
        event_log_state=aq["event_log_state"],
        session_root_state=aq["session_root_state"],
    )
    operator_state_fields = _status_tail_operator_state_fields(
        operator_state_context
    )
    path_browser_context = status_operator_contexts.build_path_browser_status_context(
        cfg,
        paths,
        staged_records=f["staged_records"],
        uploads=f["uploads"],
        fetches=f["fetches"],
        sessions=aq["sessions"],
        release=aq["release"],
    )
    path_browser_fields = _status_tail_path_browser_fields(path_browser_context)
    return {
        "paths": paths,
        "services_by_name": f["service_context"]["services_by_name"],
        **operator_state_fields,
        **path_browser_fields,
    }


def _build_status_tail_warning_context(
    cfg,
    *,
    target_filter_id,
    foundation_context,
    activity_queue_context,
    operator_path_context,
):
    f = foundation_context
    aq = activity_queue_context
    warning_context = status_warnings.build_warning_status_context(
        cfg,
        warnings=f["service_context"]["warnings"],
        path_status=operator_path_context["path_status"],
        path_status_records=operator_path_context["path_status_records"],
        browser_paths=operator_path_context["browser_paths"],
        server_state=operator_path_context["server_state"],
        staged_files_state=operator_path_context["staged_files_state"],
        command_queue_state=operator_path_context["command_queue_state"],
        release_state=aq["release_state"],
        target_filter_id=target_filter_id,
        selected_target=f["selected_target"],
        unfiltered_counts=f["unfiltered_counts"],
        event_stats=aq["event_stats"],
        command_queue=aq["command_queue"],
        target_command_records=aq["target_command_records"],
        services=f["services"],
        ports=f["ports"],
        services_by_name=operator_path_context["services_by_name"],
    )
    return _status_tail_warning_fields(warning_context)


def _build_status_tail_queue_workflow_context(
    cfg, foundation_context, activity_queue_context, operator_path_context
):
    return status_workflow_contexts.build_command_queue_workflow_status_context(
        cfg,
        activity_queue_context["command_queue"],
        activity_queue_context["target_mailbox_records"],
        operator_path_context["services_by_name"].get("command-queue") or {},
        foundation_context["targets"],
    )


def _build_status_tail_service_probe_contexts(
    cfg, foundation_context, operator_path_context
):
    service_probe_workflow_context = (
        status_workflow_contexts.build_service_probe_workflow_status_context(
            cfg,
            foundation_context["services"],
            operator_path_context["services_by_name"],
            foundation_context["targets"],
        )
    )
    return {
        "service_probe_workflow_context": service_probe_workflow_context,
        "service_probe_fields": _status_tail_service_probe_fields(
            service_probe_workflow_context
        ),
    }


def _build_status_tail_operator_console_context(
    cfg,
    *,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
    command_queue_workflow_context,
    service_probe_fields,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    return status_workflow_contexts.build_operator_console_workflow_status_context(
        cfg,
        targets=f["targets"],
        target_workflow_actions=aq["target_workflow_actions"],
        target_mailbox_records=aq["target_mailbox_records"],
        bridge_profiles=aq["bridge_profiles"],
        bridge_profile_workflow_actions=aq["bridge_profile_workflow_actions"],
        staged_records=f["staged_records"],
        staged_file_workflow_actions=aq["staged_file_workflow_actions"],
        file_service_workflow_actions=ta["file_service_workflow_actions"],
        probe_workflow_actions=service_probe_fields["probe_workflow_actions"],
        command_queue_workflow_actions=command_queue_workflow_context[
            "command_queue_workflow_actions"
        ],
        service_workflow_actions=service_probe_fields["service_workflow_actions"],
        operator_daemon_workflow_actions=aq["operator_daemon_workflow_actions"],
        workbench_actions=aq["workbench_actions"],
        workbench_config_fields=aq["workbench_config_fields"],
        workbench_jobs=aq["workbench_jobs"],
        target_activity_records=ta["target_activity_records"],
        release_artifact_workflow_actions=aq["release_artifact_workflow_actions"],
        release=aq["release"],
        warnings=f["service_context"]["warnings"],
    )


def _build_status_tail_warning_summary_context(foundation_context, warning_fields):
    return status_warnings.build_warning_summary_status_context(
        foundation_context["service_context"]["warnings"],
        services_by_has_warnings=warning_fields["services_by_has_warnings"],
        services_by_warning_type=warning_fields["services_by_warning_type"],
        ports_by_has_warnings=warning_fields["ports_by_has_warnings"],
        ports_by_warning_type=warning_fields["ports_by_warning_type"],
    )


def _build_status_tail_workflow_context(
    cfg,
    *,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
    operator_path_context,
    warning_fields,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    command_queue_workflow_context = _build_status_tail_queue_workflow_context(
        cfg, f, aq, operator_path_context
    )
    service_probe_contexts = _build_status_tail_service_probe_contexts(
        cfg, f, operator_path_context
    )
    service_probe_fields = service_probe_contexts["service_probe_fields"]
    operator_console_workflow_context = _build_status_tail_operator_console_context(
        cfg,
        foundation_context=f,
        activity_queue_context=aq,
        transfer_activity_context=ta,
        command_queue_workflow_context=command_queue_workflow_context,
        service_probe_fields=service_probe_fields,
    )
    warning_summary_context = _build_status_tail_warning_summary_context(
        f, warning_fields
    )
    return {
        **_status_tail_command_queue_workflow_fields(
            command_queue_workflow_context
        ),
        "service_probe_workflow_context": service_probe_contexts[
            "service_probe_workflow_context"
        ],
        **service_probe_fields,
        **_status_tail_operator_console_fields(operator_console_workflow_context),
        **_status_tail_warning_summary_fields(warning_summary_context),
    }


def build_status_tail_context(
    cfg,
    *,
    target_filter_id,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
):
    operator_path_context = _build_status_tail_operator_path_context(
        cfg,
        foundation_context,
        activity_queue_context,
    )
    warning_fields = _build_status_tail_warning_context(
        cfg,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
        operator_path_context=operator_path_context,
    )
    workflow_context = _build_status_tail_workflow_context(
        cfg,
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
        transfer_activity_context=transfer_activity_context,
        operator_path_context=operator_path_context,
        warning_fields=warning_fields,
    )
    return {
        **operator_path_context,
        **warning_fields,
        **workflow_context,
    }
