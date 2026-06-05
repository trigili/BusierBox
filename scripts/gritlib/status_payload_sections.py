"""Final payload section builders for grit-console status documents."""

import gritlib.bridge_routes as bridge_routes
from gritlib.build_config import build_config_path
import gritlib.command_copy as command_copy_module
import gritlib.command_queue as command_queue_module
from gritlib.record_utils import records_by_session
import gritlib.session_state as session_state_module
import gritlib.staged_files as staged_files
import gritlib.status_api_payload as status_api_payload
import gritlib.target_records as target_records
from gritlib.workbench_jobs import workbench_jobs_path


def _build_status_api_payload_from_contexts(
    *,
    cfg,
    target_filter_id,
    api_collections,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
    tail_context,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    tc = tail_context
    return status_api_payload.build_status_api_payload(
        cfg=cfg,
        target_filter_id=target_filter_id,
        selected_target=f["selected_target"],
        target_filter_record=aq["target_filter_record"],
        unfiltered_counts=f["unfiltered_counts"],
        api_collections=api_collections,
        targets=f["targets"],
        uploads=f["uploads"],
        fetches=f["fetches"],
        sessions=aq["sessions"],
        events=aq["events"],
        command_queue=aq["command_queue"],
        staged_records=f["staged_records"],
        staged_file_workflow_actions=aq["staged_file_workflow_actions"],
        target_command_records=aq["target_command_records"],
        target_phone_home_records=aq["target_phone_home_records"],
        target_filter_records=aq["target_filter_records"],
        target_filter_index_maps=aq["target_filter_index_maps"],
        target_attribution=ta["target_attribution"],
        target_attribution_records=ta["target_attribution_records"],
        target_attribution_index_maps=ta["target_attribution_index_maps"],
        rshell_session_policy=aq["rshell_session_policy"],
        rshell_session_policy_records=aq["rshell_session_policy_records"],
        rshell_session_policy_index_maps=aq["rshell_session_policy_index_maps"],
        operator_console_workflows=tc["operator_console_workflows"],
        operator_console_workflow_index_maps=tc[
            "operator_console_workflow_index_maps"
        ],
    )

def _build_status_operator_state_payload(cfg, foundation_context, tail_context):
    f = foundation_context
    tc = tail_context
    return {
        "operator_session_dir": str(f["operator_dir"]),
        "state_file": str(session_state_module.state_file_path(cfg)),
        "staged_files": str(staged_files.staged_file_path(cfg)),
        "command_queue_file": str(command_queue_module.command_queue_path(cfg)),
        "command_copy_file": str(command_copy_module.command_copy_path(cfg)),
        "bridge_profiles_file": str(bridge_routes.bridge_profiles_path(cfg)),
        "command_copy": tc["command_copy"],
        "command_copy_records": tc["command_copy_records"],
        **tc["command_copy_record_indexes"],
        "command_copy_state_records": tc["command_copy_state_records"],
        **tc["command_copy_state_index_maps"],
        "workbench_jobs_file": str(workbench_jobs_path(cfg)),
        "targets_file": str(target_records.targets_path(cfg)),
        "workbench_jobs_state": tc["workbench_jobs_state"],
        "workbench_jobs_state_records": tc["workbench_jobs_state_records"],
        **tc["workbench_jobs_state_index_maps"],
        "operator_state_records": tc["operator_state_records_list"],
        **tc["operator_state_index_maps"],
        "build_config": str(build_config_path(cfg)),
        "event_log": str(f["event_log_path"]),
        "session_root": f["session_root"],
        "tls_cert": str(cfg.get("tls_cert", "")),
        "tls_key": str(cfg.get("tls_key", "")),
    }

def _build_status_path_service_payload(
    *,
    foundation_context,
    activity_queue_context,
    tail_context,
):
    f = foundation_context
    aq = activity_queue_context
    tc = tail_context
    service_context = f["service_context"]
    return {
        "paths": tc["paths"],
        "path_status": tc["path_status"],
        "path_status_records": tc["path_status_records"],
        **tc["path_status_indexes"],
        "path_status_by_has_warnings": tc["path_status_by_has_warnings"],
        "path_status_by_warning_type": tc["path_status_by_warning_type"],
        "browser_paths": tc["browser_paths"],
        **tc["browser_path_index_maps"],
        "browser_paths_by_has_warnings": tc["browser_paths_by_has_warnings"],
        "browser_paths_by_warning_type": tc["browser_paths_by_warning_type"],
        "browser_path_summary": tc["browser_summary"],
        "server_state": tc["server_state"],
        "server_state_records": tc["server_state_records"],
        **tc["server_state_index_maps"],
        "staged_files_state": tc["staged_files_state"],
        "staged_files_state_records": tc["staged_files_state_records"],
        **tc["staged_files_state_index_maps"],
        "command_queue_state": tc["command_queue_state"],
        "command_queue_state_records": tc["command_queue_state_records"],
        **tc["command_queue_state_index_maps"],
        "service_manager": f["service_manager"],
        "service_manager_state_records": f["service_manager_state_records"],
        **f["service_manager_state_index_maps"],
        "service_manager_resources": f["service_manager_resources"],
        **f["service_manager_resource_index_maps"],
        "bridge_profiles": aq["bridge_profiles"],
        **aq["bridge_profile_index_maps"],
        "bridge_profile_workflow_actions": aq["bridge_profile_workflow_actions"],
        **aq["bridge_profile_workflow_action_index_maps"],
        "bridge_hop_records": aq["bridge_hop_records"],
        **aq["bridge_hop_index_maps"],
        "services": f["services"],
        "services_by_name": tc["services_by_name"],
        **service_context["service_index_maps"],
        "services_by_has_warnings": tc["services_by_has_warnings"],
        "services_by_warning_type": tc["services_by_warning_type"],
        "service_workflow_actions": tc["service_workflow_actions"],
        **tc["service_workflow_action_index_maps"],
        "probe_workflow_actions": tc["probe_workflow_actions"],
        **tc["probe_workflow_action_index_maps"],
        "ports": f["ports"],
        **f["port_index_maps"],
        "ports_by_has_warnings": tc["ports_by_has_warnings"],
        "ports_by_warning_type": tc["ports_by_warning_type"],
    }

def _build_status_warning_network_payload(summary, foundation_context, tail_context):
    f = foundation_context
    tc = tail_context
    service_context = f["service_context"]
    return {
        "summary": summary,
        "warnings": service_context["warnings"],
        "warnings_by_type": tc["warnings_by_type"],
        "warnings_by_severity": tc["warnings_by_severity"],
        "warnings_by_remediation_class": tc["warnings_by_remediation_class"],
        "warnings_by_type_severity": tc["warnings_by_type_severity"],
        "warnings_by_service": tc["warnings_by_service"],
        "warnings_by_port": tc["warnings_by_port"],
        "warnings_by_pid": tc["warnings_by_pid"],
        "warnings_by_listener_pid": tc["warnings_by_listener_pid"],
        "warnings_by_owner_pid": tc["warnings_by_owner_pid"],
        "warnings_by_path": tc["warnings_by_path"],
        "warnings_by_type_path": tc["warnings_by_type_path"],
        "warnings_by_service_port": tc["warnings_by_service_port"],
        "warnings_by_type_service_port": tc["warnings_by_type_service_port"],
        "warning_stats": tc["warning_summary"],
        "local_ips": f["ips"],
        "selected_local_ip": f["selected_local_ip"],
        "operator_network_records": f["operator_network_records"],
        **f["operator_network_index_maps"],
        "operator_network_state_records": f["operator_network_state_records"],
        **f["operator_network_state_index_maps"],
    }

def _build_status_target_file_payload(
    *,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    return {
        "target_commands": [rec["command"] for rec in aq["target_command_records"]],
        "target_command_records": aq["target_command_records"],
        "target_command_summary": aq["target_command_summary"],
        "target_command_state_records": aq["target_command_state_records"],
        **aq["target_command_state_index_maps"],
        "target_workflow_actions": aq["target_workflow_actions"],
        **aq["target_workflow_action_index_maps"],
        **aq["target_command_index_maps"],
        "targets": f["targets"],
        "target_summary": f["target_summary"],
        "target_registry_state_records": f["target_registry_state_records"],
        **f["target_registry_state_index_maps"],
        **f["target_index_maps"],
        "target_mailbox_records": aq["target_mailbox_records"],
        **aq["target_mailbox_index_maps"],
        "target_phone_home_records": aq["target_phone_home_records"],
        **aq["target_phone_home_index_maps"],
        "staged": f["staged"],
        "staged_records": f["staged_records"],
        "staged_by_request": f["staged_by_request"],
        "staged_by_kind": f["staged_by_kind"],
        "staged_by_sha256": f["staged_by_sha256"],
        "staged_by_target_id": f["staged_by_target_id"],
        "staged_by_source_path": f["staged_by_source_path"],
        "staged_by_fetch_command": f["staged_by_fetch_command"],
        "staged_by_fetch_command_force": f["staged_by_fetch_command_force"],
        "staged_by_source_exists": f["staged_by_source_exists"],
        "staged_by_kind_source_exists": f["staged_by_kind_source_exists"],
        "staged_file_workflow_actions": aq["staged_file_workflow_actions"],
        **aq["staged_file_workflow_action_index_maps"],
        "file_service_workflow_actions": ta["file_service_workflow_actions"],
        **ta["file_service_workflow_action_index_maps"],
        "target_file_transfer_records": ta["target_file_transfer_records"],
        **ta["target_file_transfer_index_maps"],
        "target_activity_records": ta["target_activity_records"],
        **ta["target_activity_index_maps"],
        "uploads": f["uploads"],
        "uploads_by_session": records_by_session(f["uploads"]),
        **ta["upload_index_maps"],
        "fetches": f["fetches"],
        "fetches_by_session": records_by_session(f["fetches"]),
        **ta["fetch_index_maps"],
    }

def _build_status_session_release_workbench_payload(
    activity_queue_context,
    tail_context,
):
    aq = activity_queue_context
    tc = tail_context
    release = aq["release"]
    return {
        "sessions": aq["sessions"],
        "session_root_state": aq["session_root_state"],
        "session_root_state_records": aq["session_root_state_records"],
        **aq["session_root_state_index_maps"],
        **aq["session_index_maps"],
        "events": aq["events"],
        **aq["event_index_maps"],
        "event_log_state": aq["event_log_state"],
        "event_log_state_records": aq["event_log_state_records"],
        **aq["event_log_state_index_maps"],
        "event_log_stats": {
            key: value for key, value in aq["event_stats"].items() if key != "tail"
        },
        "release_state": aq["release_state"],
        "release_state_records": aq["release_state_records"],
        **aq["release_state_index_maps"],
        "release": release,
        "release_artifact_workflow_actions": aq["release_artifact_workflow_actions"],
        **aq["release_artifact_workflow_action_index_maps"],
        "release_license_records": release.get("release_license_records") or [],
        "release_license_records_by_project_license": release.get("release_license_records_by_project_license") or {},
        "release_license_records_by_combined_gplv2_compatible": release.get("release_license_records_by_combined_gplv2_compatible") or {},
        "release_license_records_by_corresponding_source_required": release.get("release_license_records_by_corresponding_source_required") or {},
        "release_license_records_by_corresponding_source_status": release.get("release_license_records_by_corresponding_source_status") or {},
        "release_license_records_by_package_license_audit": release.get("release_license_records_by_package_license_audit") or {},
        "release_license_records_by_component": release.get("release_license_records_by_component") or {},
        "release_license_records_by_component_license": release.get("release_license_records_by_component_license") or {},
        "release_license_records_by_notice_file": release.get("release_license_records_by_notice_file") or {},
        "release_license_records_by_evidence_source": release.get("release_license_records_by_evidence_source") or {},
        "release_license_records_by_evidence_source_license": release.get("release_license_records_by_evidence_source_license") or {},
        "command_queue": aq["command_queue"],
        "command_queue_workflow_actions": tc["command_queue_workflow_actions"],
        **tc["command_queue_workflow_action_index_maps"],
        "command_queue_policy_records": aq["command_queue_policy_records"],
        **aq["command_queue_policy_index_maps"],
        **aq["command_queue_index_maps"],
        "command_queue_mode_records": aq["command_queue_mode_records"],
        **aq["command_queue_mode_index_maps"],
        "workbench_config_fields": aq["workbench_config_fields"],
        **aq["workbench_config_field_index_maps"],
        "workbench_actions": aq["workbench_actions"],
        **aq["workbench_action_index_maps"],
        "operator_daemon_workflow_actions": aq["operator_daemon_workflow_actions"],
        **aq["operator_daemon_workflow_action_index_maps"],
        "workbench_jobs": aq["workbench_jobs"],
        **aq["workbench_job_index_maps"],
    }


def build_status_api_payload_from_contexts(**kwargs):
    return _build_status_api_payload_from_contexts(**kwargs)


def build_status_operator_state_payload(*args, **kwargs):
    return _build_status_operator_state_payload(*args, **kwargs)


def build_status_path_service_payload(**kwargs):
    return _build_status_path_service_payload(**kwargs)


def build_status_warning_network_payload(*args, **kwargs):
    return _build_status_warning_network_payload(*args, **kwargs)


def build_status_target_file_payload(**kwargs):
    return _build_status_target_file_payload(**kwargs)


def build_status_session_release_workbench_payload(*args, **kwargs):
    return _build_status_session_release_workbench_payload(*args, **kwargs)
