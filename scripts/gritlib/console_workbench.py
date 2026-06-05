"""Status document and workbench snapshot composition for grit-console."""

from pathlib import Path
import gritlib.bridge_routes as bridge_routes
import gritlib.command_copy as command_copy_module
import gritlib.command_queue as command_queue_module
from gritlib.config_utils import (
    DEFAULT_CONFIG, DEFAULT_OPERATOR_SESSION_DIR,
)
from gritlib.build_config import (
    build_config_path, workbench_config_status_context,
)
from gritlib.event_log import (
    EventLog, event_log_status_context, event_status_summary,
)
import gritlib.file_transfers as file_transfers
from gritlib.operator_network import local_ips
from gritlib.probe_commands import (
    probe_workflow_action_records,
)
from gritlib.service_runtime import (
    SERVICE_MANAGER,
    SESSION_MANAGER,
)
from gritlib.record_utils import (
    int_value, records_by_session,
)
from gritlib.release_artifacts import (
    release_artifact_workflow_action_status_summary, release_status_context,
)
import gritlib.session_state as session_state_module
from gritlib.session_records import (
    session_record_summary, session_status_context,
)
import gritlib.service_status as service_status
import gritlib.staged_files as staged_files
import gritlib.status_indexes as status_indexes
import gritlib.target_activity as target_activity
from gritlib.target_commands import (
    rshell_session_policy_status,
    target_command_status_context,
    target_command_status_summary,
)
import gritlib.target_records as target_records
import gritlib.warnings as warnings_module
from gritlib.workbench_jobs import (
    reconcile_workbench_job_completion_events,
    workbench_jobs_path, workbench_jobs_state_status,
)
import gritlib.workflow_actions as workflow_actions

EVENT_INDEX_KEYS = (
    "events_by_id",
    "events_by_session",
    "events_by_service",
    "events_by_event",
    "events_by_level",
    "events_by_remote",
    "events_by_service_event",
    "events_by_session_event",
    "events_by_service_level",
    "events_by_event_level",
    "events_by_session_level",
    "events_by_remote_event",
    "events_by_remote_level",
    "events_by_detail_status",
    "events_by_detail_operation",
    "events_by_detail_http_status",
    "events_by_detail_request_name",
    "events_by_detail_filename",
    "events_by_detail_reason",
    "events_by_detail_sha256",
    "events_by_detail_command_id",
    "events_by_detail_command_sha256",
    "events_by_detail_job_id",
    "events_by_detail_action_id",
    "events_by_detail_key",
    "events_by_detail_config_path",
    "events_by_detail_target_id",
    "events_by_detail_target_label",
    "events_by_detail_expected_target_id",
    "events_by_detail_target_identity_source",
    "events_by_detail_target_identity_confidence",
    "events_by_detail_poll_mode",
    "events_by_detail_poll_interval_sec",
    "events_by_detail_poll_jitter_pct",
    "events_by_detail_poll_backoff",
    "events_by_detail_poll_max_interval_sec",
    "events_by_detail_max_polls",
    "events_by_event_detail_status",
    "events_by_service_detail_status",
    "events_by_event_detail_operation",
    "events_by_service_detail_operation",
    "events_by_event_detail_http_status",
    "events_by_service_detail_http_status",
    "events_by_event_detail_request_name",
    "events_by_service_detail_request_name",
    "events_by_event_detail_filename",
    "events_by_service_detail_filename",
    "events_by_event_detail_reason",
    "events_by_service_detail_reason",
    "events_by_event_detail_sha256",
    "events_by_service_detail_sha256",
    "events_by_event_detail_command_id",
    "events_by_service_detail_command_id",
    "events_by_event_detail_command_sha256",
    "events_by_service_detail_command_sha256",
    "events_by_event_detail_job_id",
    "events_by_service_detail_job_id",
    "events_by_event_detail_action_id",
    "events_by_service_detail_action_id",
    "events_by_event_detail_key",
    "events_by_service_detail_key",
    "events_by_event_detail_config_path",
    "events_by_service_detail_config_path",
    "events_by_event_detail_target_id",
    "events_by_service_detail_target_id",
    "events_by_event_detail_target_label",
    "events_by_service_detail_target_label",
    "events_by_event_detail_expected_target_id",
    "events_by_service_detail_expected_target_id",
    "events_by_event_detail_target_identity_source",
    "events_by_service_detail_target_identity_source",
    "events_by_event_detail_target_identity_confidence",
    "events_by_service_detail_target_identity_confidence",
)

TARGET_INDEX_KEYS = (
    "targets_by_id",
    "targets_by_label",
    "targets_by_alias",
    "targets_by_remote_addr",
    "targets_by_service",
    "targets_by_identity_confidence",
    "targets_by_identity_source",
    "targets_by_latest_activity_service",
    "targets_by_latest_activity_operation",
    "targets_by_connectivity_state",
    "targets_by_last_seen_via",
    "targets_by_offline_age_bucket",
    "targets_by_has_next_expected_poll",
    "targets_by_poll_overdue",
    "targets_by_mailbox_pending_work",
    "targets_by_latest_phone_home_status",
    "targets_by_has_last_failed_phone_home",
    "targets_by_last_failed_phone_home_reason",
    "targets_by_last_failed_phone_home_status",
    "targets_by_latest_file_transfer_operation",
    "targets_by_latest_file_transfer_status",
    "targets_by_latest_file_transfer_route_kind",
    "targets_by_latest_file_transfer_bridge_profile",
    "targets_by_latest_survey_result_kind",
    "targets_by_latest_survey_result_status",
    "targets_by_latest_survey_result_route_kind",
    "targets_by_latest_survey_result_bridge_profile",
    "targets_by_latest_bridge_profile",
    "targets_by_latest_bridge_status",
    "targets_by_has_latest_bridge_activity",
    "targets_by_has_notes",
    "targets_by_capability_report_kind",
    "targets_by_compatibility_report_kind",
    "targets_by_compatibility_label",
    "targets_by_compatibility_baseline_label",
    "targets_by_compatibility_release",
    "targets_by_compatibility_payload_preset",
    "targets_by_observed_capability",
    "targets_by_missing_capability",
    "targets_by_observed_constraint",
)

SESSION_INDEX_KEYS = (
    "sessions_by_id",
    "sessions_by_service",
    "sessions_by_state",
    "sessions_by_exit_reason",
    "sessions_by_remote",
    "sessions_by_service_state",
    "sessions_by_service_exit_reason",
    "sessions_by_service_remote",
    "sessions_by_target_id",
    "sessions_by_has_uploads",
    "sessions_by_has_fetches",
    "sessions_by_has_events",
    "sessions_by_has_artifacts",
    "sessions_by_has_session_log",
    "sessions_by_duration_known",
    "sessions_by_metadata_exists",
    "sessions_by_event_log_exists",
    "sessions_by_session_log_exists",
)

UPLOAD_INDEX_KEYS = (
    "uploads_by_filename",
    "uploads_by_kind",
    "uploads_by_sha256",
    "uploads_by_target_id",
    "uploads_by_source_path",
    "uploads_by_stored_path",
    "uploads_by_stored_exists",
    "uploads_by_metadata_exists",
    "uploads_by_event_log_exists",
    "uploads_by_remote_addr",
    "uploads_by_status",
    "uploads_by_kind_status",
    "uploads_by_filename_status",
    "uploads_by_status_stored_exists",
    "uploads_by_status_remote_addr",
)

FETCH_INDEX_KEYS = (
    "fetches_by_request",
    "fetches_by_sha256",
    "fetches_by_target_id",
    "fetches_by_source_path",
    "fetches_by_source_exists",
    "fetches_by_metadata_exists",
    "fetches_by_event_log_exists",
    "fetches_by_status",
    "fetches_by_http_status",
    "fetches_by_remote_addr",
    "fetches_by_request_status",
    "fetches_by_status_source_exists",
    "fetches_by_status_remote_addr",
    "fetches_by_http_status_remote_addr",
)

TARGET_COMMAND_INDEX_KEYS = (
    "target_commands_by_service",
    "target_commands_by_target_id",
    "target_commands_by_request",
    "target_commands_by_stage_kind",
    "target_commands_by_release_path",
    "target_commands_by_side",
    "target_commands_by_purpose",
    "target_commands_by_service_purpose",
    "target_commands_by_side_purpose",
    "target_commands_by_network",
    "target_commands_by_route_kind",
    "target_commands_by_bridge_profile",
    "target_commands_by_requires_bridge",
    "target_commands_by_requires_explicit_target_action",
    "target_commands_by_executes_operator_supplied_commands",
    "target_commands_by_ordinal",
    "target_commands_by_command_sha256",
    "target_commands_by_copy_supported",
    "target_commands_by_session_policy",
    "target_commands_by_session_policy_valid",
    "target_commands_by_retry_backoff",
    "target_commands_by_retry_interval_sec",
    "target_commands_by_retry_post_disconnect_count",
)

COMMAND_QUEUE_INDEX_KEYS = (
    "commands_by_target_id",
    "commands_by_timeout_sec",
    "commands_by_max_output_bytes",
    "commands_by_expire_sec",
    "commands_by_expires_at",
    "commands_by_expired",
    "commands_by_queue_policy_enabled",
    "commands_by_queue_policy_valid",
    "commands_by_queue_policy_execution_mode",
    "commands_by_queue_policy_allowed_commands",
    "commands_by_delivery_policy_enabled",
    "commands_by_delivery_policy_valid",
    "commands_by_delivery_policy_execution_mode",
    "commands_by_delivery_policy_delivery_supported",
    "commands_by_delivery_policy_result_upload_supported",
    "commands_by_delivery_policy_active_control_channel",
)

COMMAND_QUEUE_MODE_INDEX_KEYS = (
    "command_queue_modes_by_mode",
    "command_queue_modes_by_lifecycle",
    "command_queue_modes_by_requires_operator_host",
    "command_queue_modes_by_would_poll_if_configured",
    "command_queue_modes_by_live_supported",
    "command_queue_modes_by_live_transport_supported",
    "command_queue_modes_by_delivery_supported",
    "command_queue_modes_by_result_upload_supported",
    "command_queue_modes_by_execution_supported",
    "command_queue_modes_by_active_control_channel",
    "command_queue_modes_by_operator_supplied_command_execution",
)

SERVICE_INDEX_KEYS = (
    "services_by_actual",
    "services_by_configured",
    "services_by_bind_address",
    "services_by_port",
    "services_by_pid",
    "services_by_listener_pid",
    "services_by_tls",
    "services_by_stale",
    "services_by_pid_alive",
    "services_by_pid_managed",
    "services_by_listener_bind_mismatch",
    "services_by_session_log_exists",
    "services_by_process_log_exists",
    "services_by_has_error",
    "services_by_stopped_reason",
)

PORT_INDEX_KEYS = (
    "ports_by_number",
    "ports_by_service",
    "ports_by_actual",
)

BROWSER_PATH_INDEX_KEYS = (
    "browser_paths_by_kind",
    "browser_paths_by_path",
    "browser_paths_by_source_id",
    "browser_paths_by_stage_kind",
    "browser_paths_by_release_path",
    "browser_paths_by_kind_source_id",
    "browser_paths_by_exists",
    "browser_paths_by_readable",
    "browser_paths_by_writable",
    "browser_paths_by_expected_kind_mismatch",
)


def _build_path_browser_status_context(
    cfg,
    paths,
    *,
    staged_records,
    uploads,
    fetches,
    sessions,
    release,
):
    path_context = status_indexes.path_status_context(
        cfg,
        paths,
        staged_records,
        uploads,
        fetches,
        sessions,
        release,
    )
    return {
        "path_context": path_context,
        "path_status": path_context["path_status"],
        "path_status_records": path_context["path_status_records"],
        "path_status_indexes": path_context["path_status_index_maps"],
        "browser_paths": path_context["browser_paths"],
        "browser_path_index_maps": dict(zip(
            BROWSER_PATH_INDEX_KEYS,
            path_context["browser_path_indexes"],
        )),
        "browser_summary": path_context["browser_summary"],
    }


def _build_operator_state_status_context(
    cfg,
    *,
    event_log_state,
    session_root_state,
):
    server_status = session_state_module.server_state_status(cfg)
    server_state = server_status["state_record"]
    server_state_records = server_status["state_records"]
    staged_files_status = staged_files.staged_files_state_status(cfg)
    staged_files_state = staged_files_status["state_record"]
    staged_files_state_records = staged_files_status["state_records"]
    command_queue_status = command_queue_module.command_queue_state_status(cfg)
    command_queue_state = command_queue_status["state_record"]
    command_queue_state_records = command_queue_status["state_records"]
    command_copy = command_copy_module.command_copy_record(cfg)
    command_copy_state = command_copy_module.command_copy_state_status(command_copy)
    workbench_jobs_status = workbench_jobs_state_status(cfg)
    workbench_jobs_state = workbench_jobs_status["state_record"]
    workbench_jobs_state_records = workbench_jobs_status["state_records"]
    operator_state_context = status_indexes.operator_state_status_context(
        cfg,
        server_state,
        staged_files_state,
        command_queue_state,
        command_copy,
        workbench_jobs_state,
        event_log_state,
        session_root_state,
    )
    operator_state_file_summary_doc = status_indexes.operator_state_file_summary(
        server_state,
        server_state_records,
        staged_files_state,
        staged_files_state_records,
        command_queue_state,
        command_queue_state_records,
        command_copy,
        command_copy_state["state_record"],
        command_copy_state["state_records"],
        workbench_jobs_state,
        workbench_jobs_state_records,
    )
    return {
        "server_state": server_state,
        "server_state_records": server_state_records,
        "server_state_index_maps": server_status["state_index_maps"],
        "staged_files_state": staged_files_state,
        "staged_files_state_records": staged_files_state_records,
        "staged_files_state_index_maps": staged_files_status["state_index_maps"],
        "command_queue_state": command_queue_state,
        "command_queue_state_records": command_queue_state_records,
        "command_queue_state_index_maps": command_queue_status["state_index_maps"],
        "command_copy": command_copy,
        "command_copy_records": [command_copy],
        "command_copy_record_indexes": command_copy_module.command_copy_indexes(
            [command_copy]
        ),
        "command_copy_state_record": command_copy_state["state_record"],
        "command_copy_state_records": command_copy_state["state_records"],
        "command_copy_state_index_maps": command_copy_state["state_index_maps"],
        "workbench_jobs_state": workbench_jobs_state,
        "workbench_jobs_state_records": workbench_jobs_state_records,
        "workbench_jobs_state_index_maps": workbench_jobs_status["state_index_maps"],
        "operator_state_records_list": operator_state_context["records"],
        "operator_state_index_maps": operator_state_context["index_maps"],
        "operator_state_summary": operator_state_context["summary"],
        "operator_state_file_summary_doc": operator_state_file_summary_doc,
    }


def _build_release_status_context(cfg):
    release_context_doc = release_status_context(cfg)
    return {
        "release_context_doc": release_context_doc,
        "release": release_context_doc["release"],
        "release_state": release_context_doc["state_record"],
        "release_state_records": release_context_doc["state_records"],
        "release_state_index_maps": release_context_doc["state_index_maps"],
        "release_artifact_workflow_actions": release_context_doc["workflow_actions"],
        "release_artifact_workflow_action_index_maps": release_context_doc[
            "workflow_action_index_maps"
        ],
        "summary": release_context_doc["summary"],
    }


def _build_rshell_session_policy_status_context(cfg):
    policy_status_doc = rshell_session_policy_status(cfg)
    return {
        "rshell_session_policy_status_doc": policy_status_doc,
        "rshell_session_policy": policy_status_doc["policy"],
        "rshell_session_policy_record_item": policy_status_doc["policy_record"],
        "rshell_session_policy_records": policy_status_doc["policy_records"],
        "rshell_session_policy_index_maps": policy_status_doc["policy_index_maps"],
    }


def _build_workbench_config_status_context(cfg):
    workbench_config_context = workbench_config_status_context(cfg)
    return {
        "workbench_config_context": workbench_config_context,
        "workbench_config_fields": workbench_config_context["fields"],
        "workbench_config_field_index_maps": workbench_config_context["index_maps"],
        "summary": workbench_config_context["summary"],
    }


def _build_bridge_profile_status_context(cfg, targets):
    bridge_profiles = bridge_routes.bridge_profile_records(cfg)
    bridge_hop_records = bridge_routes.bridge_hop_records_from_profiles(
        bridge_profiles
    )
    bridge_profile_workflow_actions = (
        bridge_routes.bridge_profile_workflow_action_records(
            cfg, bridge_profiles, targets
        )
    )
    return {
        "bridge_profiles": bridge_profiles,
        "bridge_profile_index_maps": bridge_routes.bridge_profile_indexes(
            bridge_profiles
        ),
        "bridge_hop_records": bridge_hop_records,
        "bridge_hop_index_maps": bridge_routes.bridge_hop_indexes(
            bridge_hop_records
        ),
        "bridge_profile_workflow_actions": bridge_profile_workflow_actions,
        "bridge_profile_workflow_action_index_maps": (
            bridge_routes.bridge_profile_workflow_action_indexes(
                bridge_profile_workflow_actions
            )
        ),
        "summary": {
            **bridge_routes.bridge_profile_record_summary(
                bridge_profiles, bridge_hop_records
            ),
            **bridge_routes.bridge_profile_workflow_action_status_summary(
                bridge_profile_workflow_actions
            ),
        },
    }


def _build_workbench_workflow_status_context(cfg, targets, bridge_profiles):
    workbench_action_context = workflow_actions.workbench_action_status_context(cfg)
    workbench_actions = workbench_action_context["actions"]
    operator_daemon_workflow_context = (
        workflow_actions.operator_daemon_workflow_action_status_context(
            cfg,
            workbench_actions,
            targets,
        )
    )
    target_workflow_context = workflow_actions.target_workflow_action_status_context(
        cfg,
        targets,
        bridge_profiles,
    )
    workbench_job_context = workflow_actions.workbench_job_status_context(
        cfg, workbench_actions
    )
    operator_daemon_workflow_actions = operator_daemon_workflow_context["actions"]
    target_workflow_actions = target_workflow_context["actions"]
    workbench_jobs = workbench_job_context["jobs"]
    return {
        "workbench_action_context": workbench_action_context,
        "workbench_actions": workbench_actions,
        "workbench_action_index_maps": workbench_action_context["index_maps"],
        "operator_daemon_workflow_actions": operator_daemon_workflow_actions,
        "operator_daemon_workflow_action_index_maps": operator_daemon_workflow_context[
            "index_maps"
        ],
        "target_workflow_actions": target_workflow_actions,
        "target_workflow_action_index_maps": target_workflow_context["index_maps"],
        "workbench_job_context": workbench_job_context,
        "workbench_jobs": workbench_jobs,
        "workbench_job_index_maps": workbench_job_context["index_maps"],
        "summary": {
            **workflow_actions.target_workflow_action_status_summary(
                target_workflow_actions
            ),
            **workbench_action_context["summary"],
            **workflow_actions.operator_daemon_workflow_action_status_summary(
                operator_daemon_workflow_actions
            ),
            **workbench_job_context["summary"],
        },
    }


def _build_operator_network_status_context(cfg):
    ips = local_ips()
    operator_network = status_indexes.operator_network_status(ips)
    operator_dir = Path(str(cfg.get("operator_session_dir", DEFAULT_OPERATOR_SESSION_DIR)))
    event_log_path = operator_dir / "events.jsonl"
    return {
        "ips": ips,
        "operator_network": operator_network,
        "selected_local_ip": operator_network["selected_local_ip"],
        "operator_network_records": operator_network["operator_network_records"],
        "operator_network_index_maps": operator_network["operator_network_index_maps"],
        "operator_network_state_record": operator_network[
            "operator_network_state_record"
        ],
        "operator_network_state_records": operator_network[
            "operator_network_state_records"
        ],
        "operator_network_state_index_maps": operator_network[
            "operator_network_state_index_maps"
        ],
        "operator_dir": operator_dir,
        "event_log_path": event_log_path,
        "session_root": str(cfg.get("session_root", "local/sessions")),
        "summary": operator_network["summary"],
    }


def _build_service_status_context(cfg):
    service_context = service_status.service_status_context(
        cfg, SERVICE_MANAGER.snapshot()
    )
    return {
        "service_context": service_context,
        "services": service_context["services"],
        "service_manager": service_context["manager"],
        "service_manager_status_doc": service_context["manager_status"],
        "service_manager_resources": service_context["manager_resources"],
        "service_manager_resource_index_maps": service_context[
            "manager_resource_index_maps"
        ],
        "service_manager_state_record": service_context["manager_state_record"],
        "service_manager_state_records": service_context["manager_state_records"],
        "service_manager_state_index_maps": service_context["manager_state_index_maps"],
        "ports": service_context["ports"],
        "port_index_maps": dict(zip(PORT_INDEX_KEYS, service_context["port_indexes"])),
        "summary": service_context["summary"],
        "warnings": service_context["warnings"],
        "service_index_maps": dict(zip(
            SERVICE_INDEX_KEYS,
            service_context["service_indexes"],
        )),
        "services_by_name": service_context["services_by_name"],
    }


def _build_staged_file_status_context(cfg, target_filter_id):
    staged_context = staged_files.staged_status_context(
        cfg, target_filter_id=target_filter_id
    )
    (
        staged_by_request,
        staged_by_kind,
        staged_by_sha256,
        staged_by_target_id,
        staged_by_source_path,
        staged_by_fetch_command,
        staged_by_fetch_command_force,
        staged_by_source_exists,
        staged_by_kind_source_exists,
    ) = staged_context["indexes"]
    return {
        "staged_context": staged_context,
        "staged_raw": staged_context["raw"],
        "unfiltered_staged_raw": staged_context["unfiltered_raw"],
        "staged": staged_context["staged"],
        "staged_records": staged_context["records"],
        "unfiltered_staged_count": staged_context["unfiltered_count"],
        "staged_by_request": staged_by_request,
        "staged_by_kind": staged_by_kind,
        "staged_by_sha256": staged_by_sha256,
        "staged_by_target_id": staged_by_target_id,
        "staged_by_source_path": staged_by_source_path,
        "staged_by_fetch_command": staged_by_fetch_command,
        "staged_by_fetch_command_force": staged_by_fetch_command_force,
        "staged_by_source_exists": staged_by_source_exists,
        "staged_by_kind_source_exists": staged_by_kind_source_exists,
    }


def _build_staged_file_workflow_status_context(cfg, staged_records, targets):
    staged_file_workflow_actions = staged_files.staged_file_workflow_action_records(
        cfg,
        staged_records,
        targets,
    )
    return {
        "staged_file_workflow_actions": staged_file_workflow_actions,
        "staged_file_workflow_action_index_maps": (
            staged_files.staged_file_workflow_action_indexes(
                staged_file_workflow_actions
            )
        ),
        "summary": staged_files.staged_status_summary(
            staged_records,
            staged_file_workflow_actions,
        ),
    }


def _build_command_queue_status_context(cfg):
    queue_summary = command_queue_module.command_queue_summary(cfg)
    command_queue_policy = command_queue_module.command_queue_policy_status(
        queue_summary
    )
    return {
        "command_queue": queue_summary,
        "command_queue_policy_records": command_queue_policy["policy_records"],
        "command_queue_policy_index_maps": command_queue_policy["policy_index_maps"],
        "unfiltered_count": queue_summary.get(
            "unfiltered_total_count",
            len(queue_summary.get("commands") or []),
        ),
        "command_queue_index_maps": {
            key: queue_summary.get(key) or {} for key in COMMAND_QUEUE_INDEX_KEYS
        },
        "command_queue_mode_records": queue_summary.get("mode_records") or [],
        "command_queue_mode_index_maps": {
            key: queue_summary.get(key) or {}
            for key in COMMAND_QUEUE_MODE_INDEX_KEYS
        },
    }


def _build_command_queue_workflow_status_context(
    cfg,
    command_queue,
    target_mailbox_records,
    command_queue_service,
    targets,
):
    command_queue_workflow_actions = (
        command_queue_module.command_queue_workflow_action_records(
            cfg,
            command_queue,
            target_mailbox_records,
            command_queue_service,
            targets,
        )
    )
    return {
        "command_queue_workflow_actions": command_queue_workflow_actions,
        "command_queue_workflow_action_index_maps": (
            command_queue_module.command_queue_workflow_action_indexes(
                command_queue_workflow_actions
            )
        ),
        "summary": command_queue_module.command_queue_workflow_action_status_summary(
            command_queue_workflow_actions
        ),
    }


def _build_target_activity_status_context(
    command_queue,
    targets_by_id,
    all_event_records,
    *,
    target_filter_id,
    target_filter_session_ids,
):
    target_activity_context = target_activity.target_activity_status_context(
        command_queue,
        targets_by_id,
        all_event_records,
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    return {
        "target_activity_context": target_activity_context,
        "target_mailbox_records": target_activity_context["target_mailbox_records"],
        "target_mailbox_index_maps": target_activity_context[
            "target_mailbox_index_maps"
        ],
        "target_phone_home_records": target_activity_context[
            "target_phone_home_records"
        ],
        "target_phone_home_index_maps": target_activity_context[
            "target_phone_home_index_maps"
        ],
        "summary": {
            **target_activity.target_mailbox_record_summary(
                target_activity_context["target_mailbox_records"]
            ),
            **target_activity.target_phone_home_record_summary(
                target_activity_context["target_phone_home_records"]
            ),
        },
    }


def _build_target_activity_feed_status_context(
    targets,
    target_mailbox_records,
    target_phone_home_records,
    target_file_transfer_records,
    bridge_profiles,
    sessions,
):
    target_activity_feed_context = (
        target_activity.target_activity_feed_status_context(
            targets,
            target_mailbox_records,
            target_phone_home_records,
            target_file_transfer_records,
            bridge_profiles,
            sessions,
        )
    )
    target_activity_records = target_activity_feed_context["records"]
    return {
        "target_activity_feed_context": target_activity_feed_context,
        "target_activity_records": target_activity_records,
        "target_activity_index_maps": target_activity_feed_context["index_maps"],
        "summary": target_activity.target_activity_record_summary(
            target_activity_records
        ),
    }


def _build_target_command_status_context(
    cfg,
    *,
    staged_raw,
    unfiltered_staged_raw,
    target_filter_id,
):
    target_command_context = target_command_status_context(
        cfg,
        staged_raw=staged_raw,
        unfiltered_staged_raw=unfiltered_staged_raw,
        target_filter_id=target_filter_id,
    )
    return {
        "target_command_records": target_command_context["records"],
        "unfiltered_count": target_command_context["unfiltered_count"],
        "target_command_index_maps": dict(zip(
            TARGET_COMMAND_INDEX_KEYS,
            target_command_context["indexes"],
        )),
        "target_command_summary": target_command_context["summary"],
        "target_command_state_record": target_command_context["state_record"],
        "target_command_state_records": target_command_context["state_records"],
        "target_command_state_index_maps": target_command_context["state_index_maps"],
    }


def _build_target_filter_status_context(
    target_filter_id,
    selected_target,
    unfiltered_counts,
    *,
    targets,
    uploads,
    fetches,
    staged_records,
    sessions,
    events,
    command_queue,
    target_command_summary,
    target_phone_home_records,
    target_mailbox_records,
):
    target_filter_context = target_records.target_filter_status_context(
        target_filter_id,
        selected_target,
        unfiltered_counts,
        {
            "targets": len(targets),
            "uploads": len(uploads),
            "fetches": len(fetches),
            "staged": len(staged_records),
            "sessions": len(sessions),
            "event_tail": len(events),
            "command_queue_commands": len(command_queue.get("commands") or []),
            "target_command_records": target_command_summary.get("total_count", 0),
            "target_phone_home_records": len(target_phone_home_records),
        },
        target_mailbox_records=target_mailbox_records,
    )
    return {
        "target_filter_context": target_filter_context,
        "target_filter_record": target_filter_context["record"],
        "target_filter_records": target_filter_context["records"],
        "target_filter_index_maps": target_filter_context["index_maps"],
        "summary": target_filter_context["summary"],
    }


def _build_target_filter_status_doc(
    target_filter_id,
    selected_target,
    target_filter_record,
    unfiltered_counts,
    *,
    targets,
    uploads,
    fetches,
    sessions,
    events,
    command_queue,
    staged_records,
    staged_file_workflow_actions,
    target_command_records,
    target_phone_home_records,
):
    return {
        "active": bool(target_filter_id),
        "target_id": target_filter_id,
        "selected_target_found": bool(selected_target),
        "selected_target": selected_target,
        "selected_target_label": str(selected_target.get("label") or ""),
        "selected_target_aliases": selected_target.get("aliases") or [],
        "selected_target_identity_confidence": str(selected_target.get("identity_confidence") or ""),
        "selected_target_identity_sources": selected_target.get("identity_sources") or [],
        "selected_target_connectivity_state": str(selected_target.get("connectivity_state") or ""),
        "selected_target_last_seen": str(selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""),
        "selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "selected_target_offline_age_bucket": str(selected_target.get("offline_age_bucket") or ""),
        "selected_target_next_expected_poll": str(selected_target.get("next_expected_poll") or ""),
        "selected_target_latest_phone_home_at": str(selected_target.get("latest_phone_home_at") or ""),
        "selected_target_latest_phone_home_status": str(selected_target.get("latest_phone_home_status") or ""),
        "selected_target_latest_phone_home_kind": str(selected_target.get("latest_phone_home_kind") or ""),
        "selected_target_latest_phone_home_contact_path": str(selected_target.get("latest_phone_home_contact_path") or ""),
        "selected_target_latest_successful_phone_home_at": str(selected_target.get("latest_successful_phone_home_at") or ""),
        "selected_target_latest_successful_phone_home_status": str(selected_target.get("latest_successful_phone_home_status") or ""),
        "selected_target_latest_successful_phone_home_kind": str(selected_target.get("latest_successful_phone_home_kind") or ""),
        "selected_target_latest_successful_phone_home_contact_path": str(selected_target.get("latest_successful_phone_home_contact_path") or ""),
        "selected_target_last_failed_phone_home_at": str(selected_target.get("last_failed_phone_home_at") or ""),
        "selected_target_last_failed_phone_home_status": str(selected_target.get("last_failed_phone_home_status") or ""),
        "selected_target_last_failed_phone_home_reason": str(selected_target.get("last_failed_phone_home_reason") or ""),
        "selected_target_last_failed_phone_home_contact_path": str(selected_target.get("last_failed_phone_home_contact_path") or ""),
        "selected_target_poll_overdue": bool(selected_target.get("poll_overdue", False)),
        "selected_target_poll_overdue_for_sec": selected_target.get("poll_overdue_for_sec", ""),
        "selected_target_mailbox_command_count": int_value(selected_target.get("mailbox_command_count", 0)),
        "selected_target_mailbox_pending_work_count": int_value(selected_target.get("mailbox_pending_work_count", 0)),
        "selected_target_latest_activity_service": str(selected_target.get("latest_activity_service") or ""),
        "selected_target_latest_activity_operation": str(selected_target.get("latest_activity_operation") or ""),
        "selected_target_latest_file_transfer_operation": str(selected_target.get("latest_file_transfer_operation") or ""),
        "selected_target_latest_file_transfer_status": str(selected_target.get("latest_file_transfer_status") or ""),
        "selected_target_latest_file_transfer_route_kind": str(selected_target.get("latest_file_transfer_route_kind") or ""),
        "selected_target_latest_file_transfer_bridge_profile": str(selected_target.get("latest_file_transfer_bridge_profile") or ""),
        "selected_target_latest_survey_result_kind": str(selected_target.get("latest_survey_result_kind") or ""),
        "selected_target_latest_survey_result_status": str(selected_target.get("latest_survey_result_status") or ""),
        "selected_target_latest_survey_result_route_kind": str(selected_target.get("latest_survey_result_route_kind") or ""),
        "selected_target_latest_survey_result_bridge_profile": str(selected_target.get("latest_survey_result_bridge_profile") or ""),
        "selected_target_latest_bridge_profile": str(selected_target.get("latest_bridge_profile") or ""),
        "selected_target_latest_bridge_status": str(selected_target.get("latest_bridge_status") or ""),
        "selected_target_latest_bridge_route_path": str(selected_target.get("latest_bridge_route_path") or ""),
        "selected_target_latest_bridge_failure_reason": str(selected_target.get("latest_bridge_failure_reason") or ""),
        "selected_target_latest_capability_report_kind": str(selected_target.get("latest_capability_report_kind") or ""),
        "selected_target_latest_capability_check_count": target_filter_record.get("selected_target_latest_capability_check_count", 0),
        "selected_target_latest_capability_pass_count": target_filter_record.get("selected_target_latest_capability_pass_count", 0),
        "selected_target_latest_capability_fail_count": target_filter_record.get("selected_target_latest_capability_fail_count", 0),
        "selected_target_latest_compatibility_report_kind": str(selected_target.get("latest_compatibility_report_kind") or ""),
        "selected_target_latest_compatibility_label": str(selected_target.get("latest_compatibility_label") or ""),
        "selected_target_latest_compatibility_baseline_label": str(selected_target.get("latest_compatibility_baseline_label") or ""),
        "selected_target_latest_compatibility_release_name": str(selected_target.get("latest_compatibility_release_name") or ""),
        "selected_target_latest_compatibility_payload_preset": str(selected_target.get("latest_compatibility_payload_preset") or ""),
        "selected_target_latest_compatibility_reason_count": target_filter_record.get("selected_target_latest_compatibility_reason_count", 0),
        "selected_target_notes_present": bool(str(selected_target.get("notes") or "").strip()),
        "applied_to": [
            "targets", "uploads", "fetches", "sessions", "events",
            "command_queue.commands", "staged_records", "staged_file_workflow_actions",
            "target_command_records", "target_phone_home_records",
        ] if target_filter_id else [],
        "unfiltered_counts": unfiltered_counts,
        "filtered_counts": {
            "targets": len(targets),
            "uploads": len(uploads),
            "fetches": len(fetches),
            "sessions": len(sessions),
            "events": len(events),
            "command_queue_commands": len(command_queue.get("commands") or []),
            "staged_records": len(staged_records),
            "staged_file_workflow_actions": len(staged_file_workflow_actions),
            "target_command_records": len(target_command_records),
            "target_phone_home_records": len(target_phone_home_records),
        },
        "observed_activity_counts": {
            "unfiltered": target_filter_record.get("unfiltered_observed_activity_count", 0),
            "filtered": target_filter_record.get("filtered_observed_activity_count", 0),
            "has_unfiltered": bool(target_filter_record.get("has_unfiltered_observed_activity", False)),
            "has_filtered": bool(target_filter_record.get("has_filtered_observed_activity", False)),
            "filter_reduced": bool(target_filter_record.get("filter_reduced_observed_activity", False)),
        },
    }


def _build_target_attribution_status_context(uploads, fetches, sessions):
    target_attribution_status_doc = target_records.target_attribution_status(
        uploads,
        fetches,
        sessions,
    )
    target_attribution = target_attribution_status_doc["target_attribution"]
    target_attribution_records = target_attribution_status_doc[
        "target_attribution_records"
    ]
    return {
        "target_attribution_status_doc": target_attribution_status_doc,
        "target_attribution": target_attribution,
        "target_attribution_records": target_attribution_records,
        "target_attribution_index_maps": target_attribution_status_doc[
            "target_attribution_index_maps"
        ],
        "summary": target_records.target_attribution_record_summary(
            target_attribution_records,
            target_attribution,
        ),
    }


def _build_file_transfer_status_context(staged_records, uploads, fetches):
    file_transfer_context = file_transfers.file_transfer_status_context(
        uploads, fetches
    )
    target_file_transfer_context = file_transfers.target_file_transfer_status_context(
        staged_records,
        uploads,
        fetches,
    )
    return {
        "upload_index_maps": dict(zip(
            UPLOAD_INDEX_KEYS,
            file_transfer_context["upload_indexes"],
        )),
        "fetch_index_maps": dict(zip(
            FETCH_INDEX_KEYS,
            file_transfer_context["fetch_indexes"],
        )),
        "target_file_transfer_records": target_file_transfer_context["records"],
        "target_file_transfer_index_maps": target_file_transfer_context["index_maps"],
    }


def _build_file_service_workflow_status_context(
    cfg,
    services,
    staged_records,
    uploads,
    fetches,
    target_file_transfer_records,
    targets,
):
    file_service_row = next(
        (row for row in services if row.get("name") == "file-service"), {}
    )
    file_service_workflow_context = (
        file_transfers.file_service_workflow_status_context(
            cfg,
            file_service_row,
            staged_records,
            uploads,
            fetches,
            target_file_transfer_records,
            targets,
        )
    )
    file_service_workflow_actions = file_service_workflow_context["actions"]
    return {
        "file_service_row": file_service_row,
        "file_service_workflow_context": file_service_workflow_context,
        "file_service_workflow_actions": file_service_workflow_actions,
        "file_service_workflow_action_index_maps": file_service_workflow_context[
            "index_maps"
        ],
        "summary": file_transfers.file_service_workflow_status_summary(
            file_service_workflow_actions
        ),
    }


def _build_service_probe_workflow_status_context(
    cfg,
    services,
    services_by_name,
    targets,
):
    service_workflow_actions = service_status.service_workflow_action_records(
        cfg, services, targets
    )
    probe_workflow_actions = probe_workflow_action_records(
        cfg,
        services_by_name.get("probe") or {},
        targets,
    )
    return {
        "service_workflow_actions": service_workflow_actions,
        "service_workflow_action_index_maps": service_status.service_workflow_action_indexes(
            service_workflow_actions
        ),
        "probe_workflow_actions": probe_workflow_actions,
        "probe_workflow_action_index_maps": (
            workflow_actions.probe_workflow_action_indexes(
                probe_workflow_actions
            )
        ),
        "summary": {
            **service_status.service_workflow_action_status_summary(
                service_workflow_actions
            ),
            **workflow_actions.probe_workflow_action_status_summary(
                probe_workflow_actions
            ),
        },
    }


def _build_operator_console_workflow_status_context(
    cfg,
    *,
    targets,
    target_workflow_actions,
    target_mailbox_records,
    bridge_profiles,
    bridge_profile_workflow_actions,
    staged_records,
    staged_file_workflow_actions,
    file_service_workflow_actions,
    probe_workflow_actions,
    command_queue_workflow_actions,
    service_workflow_actions,
    operator_daemon_workflow_actions,
    workbench_actions,
    workbench_config_fields,
    workbench_jobs,
    target_activity_records,
    release_artifact_workflow_actions,
    release,
    warnings,
):
    operator_console_workflows = workflow_actions.operator_console_workflow_records(
        cfg,
        targets=targets,
        target_workflow_actions=target_workflow_actions,
        target_mailbox_records=target_mailbox_records,
        bridge_profiles=bridge_profiles,
        bridge_profile_workflow_actions=bridge_profile_workflow_actions,
        staged_records=staged_records,
        staged_file_workflow_actions=staged_file_workflow_actions,
        file_service_workflow_actions=file_service_workflow_actions,
        probe_workflow_actions=probe_workflow_actions,
        command_queue_workflow_actions=command_queue_workflow_actions,
        service_workflow_actions=service_workflow_actions,
        operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        workbench_actions=workbench_actions,
        workbench_config_fields=workbench_config_fields,
        workbench_jobs=workbench_jobs,
        target_activity_records=target_activity_records,
        release_artifact_workflow_actions=release_artifact_workflow_actions,
        release=release,
        warnings=warnings,
    )
    operator_console_workflow_stats = (
        workflow_actions.operator_console_workflow_summary(
            operator_console_workflows
        )
    )
    return {
        "operator_console_workflows": operator_console_workflows,
        "operator_console_workflow_index_maps": (
            workflow_actions.operator_console_workflow_indexes(
                operator_console_workflows
            )
        ),
        "operator_console_workflow_stats": operator_console_workflow_stats,
        "summary": workflow_actions.operator_console_workflow_status_summary(
            operator_console_workflow_stats
        ),
    }


def _build_session_status_context(cfg, *, target_filter_id):
    session_context = session_status_context(
        cfg,
        SESSION_MANAGER.recent_records(cfg),
        target_filter_id=target_filter_id,
    )
    return {
        "sessions": session_context["records"],
        "unfiltered_count": session_context["unfiltered_count"],
        "target_filter_session_ids": session_context["target_filter_session_ids"],
        "session_root_state": session_context["root_state"],
        "session_root_state_records": session_context["root_state_records"],
        "session_root_state_index_maps": session_context["root_state_index_maps"],
        "session_index_maps": dict(zip(SESSION_INDEX_KEYS, session_context["indexes"])),
    }


def _build_event_source_status_context(cfg):
    all_event_records, all_event_invalid = EventLog(cfg).records()
    all_target_phone_home_records = (
        target_activity.target_phone_home_records_from_events(all_event_records)
    )
    return {
        "all_event_records": all_event_records,
        "all_event_invalid": all_event_invalid,
        "all_target_phone_home_records": all_target_phone_home_records,
    }


def _build_target_registry_context(
    cfg,
    *,
    target_filter_id,
    all_target_phone_home_records,
    unfiltered_staged_count,
):
    uploads = file_transfers.recent_upload_metadata(cfg)
    fetches = file_transfers.recent_fetch_metadata(cfg)
    targets = target_records.target_records(cfg)
    targets = target_activity.apply_target_phone_home_summary(
        targets,
        all_target_phone_home_records,
    )
    unfiltered_counts = {
        "targets": len(targets),
        "uploads": len(uploads),
        "fetches": len(fetches),
        "staged": unfiltered_staged_count,
        "target_phone_home_records": len(all_target_phone_home_records),
    }
    if target_filter_id:
        uploads = target_records.records_for_target(uploads, target_filter_id)
        fetches = target_records.records_for_target(fetches, target_filter_id)
        targets = target_records.records_for_target(targets, target_filter_id)
    target_index_maps = dict(
        zip(TARGET_INDEX_KEYS, target_records.target_record_indexes(targets))
    )
    target_summary = target_records.target_record_summary(targets)
    selected_target = (
        dict(target_index_maps["targets_by_id"].get(target_filter_id) or {})
        if target_filter_id else {}
    )
    target_registry_state = target_records.target_registry_state_status(
        target_summary,
        selected_target,
        target_filter_id,
        unfiltered_counts.get("targets", 0),
    )
    return {
        "uploads": uploads,
        "fetches": fetches,
        "targets": targets,
        "unfiltered_counts": unfiltered_counts,
        "target_index_maps": target_index_maps,
        "target_summary": target_summary,
        "selected_target": selected_target,
        "target_registry_state_record": target_registry_state["state_record"],
        "target_registry_state_records": target_registry_state["state_records"],
        "target_registry_state_index_maps": target_registry_state["state_index_maps"],
        "target_registry_summary": target_registry_state["summary"],
    }


def _build_event_status_context(
    cfg,
    event_limit,
    *,
    target_filter_id,
    target_filter_session_ids,
):
    event_context = event_log_status_context(
        cfg,
        event_limit,
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    return {
        "event_stats": event_context["stats"],
        "event_log_state": event_context["state_record"],
        "event_log_state_records": event_context["state_records"],
        "event_log_state_index_maps": event_context["state_index_maps"],
        "events": event_context["events"],
        "unfiltered_tail_count": event_context["unfiltered_tail_count"],
        "event_index_maps": dict(zip(EVENT_INDEX_KEYS, event_context["indexes"])),
        "event_summary_stats": event_context["summary_stats"],
    }


def workbench_snapshot(cfg):
    doc = status_document(cfg)
    services = {}
    state = session_state_module.read_json_file(
        session_state_module.state_file_path(cfg), {"schema": 1, "services": {}}
    )
    workbench_state = (state.get("services") or {}).get("workbench", {})
    for row in doc["services"]:
        services[row["name"]] = {
            "port": row["port"],
            "listening": row["actual"] == "listening",
            "state": (state.get("services") or {}).get(row["name"], {}),
            "status_row": row,
        }
    return {
        **doc,
        "state": state,
        "services": services,
        "workbench": {
            "status": workbench_state.get("status", ""),
            "mode": workbench_state.get("workbench_mode", ""),
            "last_refresh_at": workbench_state.get("last_refresh_at", ""),
            "refresh_count": int(workbench_state.get("refresh_count", 0) or 0),
            "selected_target_id": workbench_state.get("selected_target_id", ""),
            "selected_target_label": workbench_state.get("selected_target_label", ""),
            "selected_target_at": workbench_state.get("selected_target_at", ""),
        },
    }


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


def _build_status_api_doc(cfg, target_filter_id, selected_target, api_resources):
    return {
        "schema": 1,
        "status_command": "scripts/grit-console --api-status",
        "json_status_command": "scripts/grit-console --json-status",
        "event_limit": int(cfg.get("_event_limit", 0) or 0),
        "target_filter_active": bool(target_filter_id),
        "target_filter_id": target_filter_id,
        "target_filter_selected_target_found": bool(selected_target),
        "target_filter_selected_target_label": str(selected_target.get("label") or ""),
        "target_filter_selected_target_identity_confidence": str(selected_target.get("identity_confidence") or ""),
        "target_filter_selected_target_connectivity_state": str(selected_target.get("connectivity_state") or ""),
        "target_filter_selected_target_last_seen": str(selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""),
        "target_filter_selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "target_filter_selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "target_filter_selected_target_offline_age_bucket": str(selected_target.get("offline_age_bucket") or ""),
        "target_filter_selected_target_next_expected_poll": str(selected_target.get("next_expected_poll") or ""),
        "target_filter_selected_target_latest_phone_home_at": str(selected_target.get("latest_phone_home_at") or ""),
        "target_filter_selected_target_latest_phone_home_status": str(selected_target.get("latest_phone_home_status") or ""),
        "target_filter_selected_target_latest_phone_home_kind": str(selected_target.get("latest_phone_home_kind") or ""),
        "target_filter_selected_target_latest_phone_home_contact_path": str(selected_target.get("latest_phone_home_contact_path") or ""),
        "target_filter_selected_target_latest_successful_phone_home_at": str(selected_target.get("latest_successful_phone_home_at") or ""),
        "target_filter_selected_target_latest_successful_phone_home_status": str(selected_target.get("latest_successful_phone_home_status") or ""),
        "target_filter_selected_target_latest_successful_phone_home_kind": str(selected_target.get("latest_successful_phone_home_kind") or ""),
        "target_filter_selected_target_latest_successful_phone_home_contact_path": str(selected_target.get("latest_successful_phone_home_contact_path") or ""),
        "target_filter_selected_target_last_failed_phone_home_at": str(selected_target.get("last_failed_phone_home_at") or ""),
        "target_filter_selected_target_last_failed_phone_home_status": str(selected_target.get("last_failed_phone_home_status") or ""),
        "target_filter_selected_target_last_failed_phone_home_reason": str(selected_target.get("last_failed_phone_home_reason") or ""),
        "target_filter_selected_target_last_failed_phone_home_contact_path": str(selected_target.get("last_failed_phone_home_contact_path") or ""),
        "target_filter_selected_target_poll_overdue": bool(selected_target.get("poll_overdue", False)),
        "target_filter_selected_target_mailbox_pending_work_count": int_value(selected_target.get("mailbox_pending_work_count", 0)),
        "target_filter_selected_target_latest_file_transfer_status": str(selected_target.get("latest_file_transfer_status") or ""),
        "target_filter_selected_target_latest_file_transfer_route_kind": str(selected_target.get("latest_file_transfer_route_kind") or ""),
        "target_filter_selected_target_latest_survey_result_status": str(selected_target.get("latest_survey_result_status") or ""),
        "target_filter_selected_target_latest_survey_result_route_kind": str(selected_target.get("latest_survey_result_route_kind") or ""),
        "target_filter_selected_target_latest_bridge_profile": str(selected_target.get("latest_bridge_profile") or ""),
        "target_filter_selected_target_latest_bridge_status": str(selected_target.get("latest_bridge_status") or ""),
        "target_filter_selected_target_latest_capability_report_kind": str(selected_target.get("latest_capability_report_kind") or ""),
        "target_filter_selected_target_latest_compatibility_label": str(selected_target.get("latest_compatibility_label") or ""),
        "target_filter_selected_target_latest_compatibility_release_name": str(selected_target.get("latest_compatibility_release_name") or ""),
        "resource_count": len(api_resources),
        "resources_key": "api_resources",
        "collections_key": "api_collections",
    }


def _build_service_bridge_api_collections(
    *,
    services,
    service_workflow_actions,
    probe_workflow_actions,
    service_manager_resources,
    service_manager_state_records,
    bridge_profiles,
    bridge_profile_workflow_actions,
    bridge_hop_records,
):
    return {
        "services": status_indexes.api_collection_record(
            "services", services, "name", (
                "services_by_name", "services_by_actual", "services_by_configured",
                "services_by_bind_address", "services_by_port", "services_by_pid",
                "services_by_listener_pid", "services_by_tls", "services_by_stale",
                "services_by_pid_alive", "services_by_pid_managed",
                "services_by_listener_bind_mismatch", "services_by_has_error",
                "services_by_session_log_exists", "services_by_process_log_exists",
                "services_by_stopped_reason", "services_by_has_warnings",
                "services_by_warning_type",
            ), "service_count",
        ),
        "service_workflow_actions": status_indexes.api_collection_record(
            "service_workflow_actions", service_workflow_actions, "id", (
                "service_workflow_actions_by_id",
                "service_workflow_actions_by_action_id",
                "service_workflow_actions_by_service",
                "service_workflow_actions_by_category",
                "service_workflow_actions_by_workflow",
                "service_workflow_actions_by_actual",
                "service_workflow_actions_by_configured",
                "service_workflow_actions_by_fleet_target_count",
                "service_workflow_actions_by_fleet_offline_target_count",
                "service_workflow_actions_by_fleet_stale_target_count",
                "service_workflow_actions_by_fleet_mailbox_pending_target_count",
                "service_workflow_actions_by_fleet_mailbox_pending_work_count",
                "service_workflow_actions_by_fleet_poll_overdue_target_count",
                "service_workflow_actions_by_fleet_has_offline_targets",
                "service_workflow_actions_by_fleet_has_stale_targets",
                "service_workflow_actions_by_fleet_has_mailbox_pending_work",
                "service_workflow_actions_by_fleet_has_poll_overdue_targets",
                "service_workflow_actions_by_available",
                "service_workflow_actions_by_requires_input",
                "service_workflow_actions_by_requires_confirmation",
                "service_workflow_actions_by_operator_action_state",
                "service_workflow_actions_by_operator_action_reason",
                "service_workflow_actions_by_can_run_from_curses_enter",
                "service_workflow_actions_by_curses_enter_action",
                "service_workflow_actions_by_has_error",
                "service_workflow_actions_by_has_warnings",
            ), "service_workflow_action_count",
        ),
        "probe_workflow_actions": status_indexes.api_collection_record(
            "probe_workflow_actions", probe_workflow_actions, "id", (
                "probe_workflow_actions_by_id",
                "probe_workflow_actions_by_action_id",
                "probe_workflow_actions_by_category",
                "probe_workflow_actions_by_workflow",
                "probe_workflow_actions_by_actual",
                "probe_workflow_actions_by_route_kind",
                "probe_workflow_actions_by_bridge_profile",
                "probe_workflow_actions_by_requires_bridge",
                "probe_workflow_actions_by_fleet_target_count",
                "probe_workflow_actions_by_fleet_offline_target_count",
                "probe_workflow_actions_by_fleet_stale_target_count",
                "probe_workflow_actions_by_fleet_mailbox_pending_target_count",
                "probe_workflow_actions_by_fleet_mailbox_pending_work_count",
                "probe_workflow_actions_by_fleet_poll_overdue_target_count",
                "probe_workflow_actions_by_fleet_has_offline_targets",
                "probe_workflow_actions_by_fleet_has_stale_targets",
                "probe_workflow_actions_by_fleet_has_mailbox_pending_work",
                "probe_workflow_actions_by_fleet_has_poll_overdue_targets",
                "probe_workflow_actions_by_available",
                "probe_workflow_actions_by_requires_confirmation",
                "probe_workflow_actions_by_target_phone_home_required",
                "probe_workflow_actions_by_operator_action_state",
                "probe_workflow_actions_by_operator_action_reason",
                "probe_workflow_actions_by_can_run_from_curses_enter",
                "probe_workflow_actions_by_curses_enter_action",
            ), "probe_workflow_action_count",
        ),
        "service_manager_resources": status_indexes.api_collection_record(
            "service_manager_resources", service_manager_resources, "id", (
                "service_manager_resources_by_id", "service_manager_resources_by_kind",
                "service_manager_resources_by_state", "service_manager_resources_by_active",
                "service_manager_resources_by_pid", "service_manager_resources_by_kind_state",
                "service_manager_resources_by_kind_active",
            ), "service_manager_resource_count",
        ),
        "service_manager_state_records": status_indexes.api_collection_record(
            "service_manager_state_records", service_manager_state_records, "id", (
                "service_manager_state_records_by_id",
                "service_manager_state_records_by_shutdown_requested",
                "service_manager_state_records_by_has_open_sockets",
                "service_manager_state_records_by_has_active_transports",
                "service_manager_state_records_by_has_alive_threads",
                "service_manager_state_records_by_has_running_children",
                "service_manager_state_records_by_has_resources",
            ), "service_manager_state_record_count",
        ),
        "bridge_profiles": status_indexes.api_collection_record(
            "bridge_profiles", bridge_profiles, "name", (
                "bridge_profiles_by_name", "bridge_profiles_by_target_id",
                "bridge_profiles_by_dest_host", "bridge_profiles_by_listen_port",
                "bridge_profiles_by_current_state", "bridge_profiles_by_active",
                "bridge_profiles_by_requires_target_online", "bridge_profiles_by_multi_hop",
                "bridge_profiles_by_hop_count", "bridge_profiles_by_route_path",
                "bridge_profiles_by_has_last_successful_relay",
                "bridge_profiles_by_has_last_failure",
            ), "bridge_profile_count",
        ),
        "bridge_profile_workflow_actions": status_indexes.api_collection_record(
            "bridge_profile_workflow_actions", bridge_profile_workflow_actions, "id", (
                "bridge_profile_workflow_actions_by_id",
                "bridge_profile_workflow_actions_by_action_id",
                "bridge_profile_workflow_actions_by_bridge_profile",
                "bridge_profile_workflow_actions_by_target_id",
                "bridge_profile_workflow_actions_by_category",
                "bridge_profile_workflow_actions_by_workflow",
                "bridge_profile_workflow_actions_by_current_state",
                "bridge_profile_workflow_actions_by_active",
                "bridge_profile_workflow_actions_by_requires_target_online",
                "bridge_profile_workflow_actions_by_multi_hop",
                "bridge_profile_workflow_actions_by_hop_count",
                "bridge_profile_workflow_actions_by_fleet_target_count",
                "bridge_profile_workflow_actions_by_fleet_offline_target_count",
                "bridge_profile_workflow_actions_by_fleet_stale_target_count",
                "bridge_profile_workflow_actions_by_fleet_mailbox_pending_target_count",
                "bridge_profile_workflow_actions_by_fleet_mailbox_pending_work_count",
                "bridge_profile_workflow_actions_by_fleet_poll_overdue_target_count",
                "bridge_profile_workflow_actions_by_fleet_has_offline_targets",
                "bridge_profile_workflow_actions_by_fleet_has_stale_targets",
                "bridge_profile_workflow_actions_by_fleet_has_mailbox_pending_work",
                "bridge_profile_workflow_actions_by_fleet_has_poll_overdue_targets",
                "bridge_profile_workflow_actions_by_has_last_successful_relay",
                "bridge_profile_workflow_actions_by_has_last_failure",
                "bridge_profile_workflow_actions_by_requires_confirmation",
                "bridge_profile_workflow_actions_by_operator_action_state",
                "bridge_profile_workflow_actions_by_operator_action_reason",
                "bridge_profile_workflow_actions_by_can_run_from_curses_enter",
                "bridge_profile_workflow_actions_by_curses_enter_action",
            ), "bridge_profile_workflow_action_count",
        ),
        "bridge_hop_records": status_indexes.api_collection_record(
            "bridge_hop_records", bridge_hop_records, "id", (
                "bridge_hops_by_id", "bridge_hops_by_profile",
                "bridge_hops_by_profile_name", "bridge_hops_by_ordinal",
                "bridge_hops_by_from", "bridge_hops_by_to",
                "bridge_hops_by_from_host", "bridge_hops_by_from_port",
                "bridge_hops_by_to_host", "bridge_hops_by_to_port",
                "bridge_hops_by_route_path", "bridge_hops_by_target_id",
                "bridge_hops_by_multi_hop", "bridge_hops_by_is_first_hop",
                "bridge_hops_by_is_last_hop", "bridge_hops_by_current_state",
                "bridge_hops_by_profile_active",
                "bridge_hops_by_profile_has_last_successful_relay",
                "bridge_hops_by_profile_has_last_failure",
            ), "bridge_hop_record_count",
        ),
    }


def _build_operator_health_api_collections(
    *,
    ports,
    path_status_records,
    server_state_records,
    operator_state_records_list,
    operator_network_records,
    operator_network_state_records,
    browser_paths,
    warnings,
):
    return {
        "ports": status_indexes.api_collection_record(
            "ports", ports, "service", (
                "ports_by_number", "ports_by_service", "ports_by_actual",
                "ports_by_has_warnings", "ports_by_warning_type",
            ), "port_count",
        ),
        "path_status_records": status_indexes.api_collection_record(
            "path_status_records", path_status_records, "name", (
                "path_status_by_name", "path_status_by_path",
                "path_status_by_expected_kind", "path_status_by_exists",
                "path_status_by_parent_exists", "path_status_by_writable",
                "path_status_by_expected_kind_mismatch",
                "path_status_by_has_warnings", "path_status_by_warning_type",
            ), "path_status_count",
        ),
        "server_state_records": status_indexes.api_collection_record(
            "server_state_records", server_state_records, "path", (
                "server_state_records_by_path",
                "server_state_records_by_exists",
                "server_state_records_by_valid",
                "server_state_records_by_has_services",
                "server_state_records_by_has_sessions",
                "server_state_records_by_schema",
            ), "server_state_record_count",
        ),
        "operator_state_records": status_indexes.api_collection_record(
            "operator_state_records", operator_state_records_list, "name", (
                "operator_state_records_by_name", "operator_state_records_by_kind",
                "operator_state_records_by_status", "operator_state_records_by_exists",
                "operator_state_records_by_valid", "operator_state_records_by_unhealthy",
                "operator_state_records_by_severity",
                "operator_state_records_by_remediation_class",
                "operator_state_records_by_requires_operator_action",
                "operator_state_records_by_path",
                "operator_state_records_by_kind_status",
            ), "operator_state_count",
        ),
        "operator_network_records": status_indexes.api_collection_record(
            "operator_network_records", operator_network_records, "id", (
                "operator_network_records_by_id",
                "operator_network_records_by_kind",
                "operator_network_records_by_ip",
                "operator_network_records_by_selected",
                "operator_network_records_by_placeholder",
                "operator_network_records_by_source",
                "operator_network_records_by_usable_for_generated_commands",
            ), "operator_network_record_count",
        ),
        "operator_network_state_records": status_indexes.api_collection_record(
            "operator_network_state_records", operator_network_state_records, "id", (
                "operator_network_state_records_by_id",
                "operator_network_state_records_by_selected_ip",
                "operator_network_state_records_by_selected_source",
                "operator_network_state_records_by_selected_placeholder",
                "operator_network_state_records_by_has_detected_ip",
                "operator_network_state_records_by_uses_placeholder",
                "operator_network_state_records_by_has_generated_command_ip",
                "operator_network_state_records_by_has_multiple_ips",
            ), "operator_network_state_record_count",
        ),
        "browser_paths": status_indexes.api_collection_record(
            "browser_paths", browser_paths, "id", (
                "browser_paths_by_kind", "browser_paths_by_path",
                "browser_paths_by_source_id", "browser_paths_by_stage_kind",
                "browser_paths_by_release_path", "browser_paths_by_kind_source_id",
                "browser_paths_by_exists", "browser_paths_by_readable",
                "browser_paths_by_writable", "browser_paths_by_expected_kind_mismatch",
                "browser_paths_by_has_warnings", "browser_paths_by_warning_type",
            ), "browser_path_count",
        ),
        "warnings": status_indexes.api_collection_record(
            "warnings", warnings, "type", (
                "warnings_by_type", "warnings_by_severity",
                "warnings_by_remediation_class", "warnings_by_type_severity",
                "warnings_by_service", "warnings_by_port",
                "warnings_by_pid", "warnings_by_listener_pid", "warnings_by_owner_pid",
                "warnings_by_path", "warnings_by_type_path",
                "warnings_by_service_port", "warnings_by_type_service_port",
            ), "warning_count",
        ),
    }


def _build_target_api_collections(
    *,
    target_command_records,
    target_workflow_actions,
    target_command_state_records,
    rshell_session_policy_records,
    targets,
    target_registry_state_records,
    target_filter_records,
    target_attribution_records,
):
    return {
        "target_command_records": status_indexes.api_collection_record(
            "target_command_records", target_command_records, "command", (
                "target_commands_by_service", "target_commands_by_request",
                "target_commands_by_target_id",
                "target_commands_by_stage_kind", "target_commands_by_release_path",
                "target_commands_by_side", "target_commands_by_purpose",
                "target_commands_by_service_purpose", "target_commands_by_side_purpose",
                "target_commands_by_network", "target_commands_by_route_kind",
                "target_commands_by_bridge_profile", "target_commands_by_requires_bridge",
                "target_commands_by_requires_explicit_target_action",
                "target_commands_by_executes_operator_supplied_commands",
                "target_commands_by_ordinal", "target_commands_by_command_sha256",
                "target_commands_by_copy_supported",
                "target_commands_by_session_policy", "target_commands_by_session_policy_valid",
                "target_commands_by_retry_backoff", "target_commands_by_retry_interval_sec",
                "target_commands_by_retry_post_disconnect_count",
            ), "target_command_count",
        ),
        "target_workflow_actions": status_indexes.api_collection_record(
            "target_workflow_actions", target_workflow_actions, "id", (
                "target_workflow_actions_by_id",
                "target_workflow_actions_by_action_id",
                "target_workflow_actions_by_target_id",
                "target_workflow_actions_by_category",
                "target_workflow_actions_by_workflow",
                "target_workflow_actions_by_available",
                "target_workflow_actions_by_requires_input",
                "target_workflow_actions_by_offline_supported",
                "target_workflow_actions_by_requires_target_online",
                "target_workflow_actions_by_queues_offline_work",
                "target_workflow_actions_by_target_phone_home_required",
                "target_workflow_actions_by_bridge_profile",
                "target_workflow_actions_by_target_connectivity_state",
                "target_workflow_actions_by_target_offline_age_bucket",
                "target_workflow_actions_by_target_poll_overdue",
                "target_workflow_actions_by_target_mailbox_pending_work_count",
                "target_workflow_actions_by_target_latest_phone_home_status",
                "target_workflow_actions_by_target_latest_successful_phone_home_status",
                "target_workflow_actions_by_target_last_failed_phone_home_status",
                "target_workflow_actions_by_operator_action_state",
                "target_workflow_actions_by_operator_action_reason",
                "target_workflow_actions_by_can_run_from_curses_enter",
            ), "target_workflow_action_count",
        ),
        "target_command_state_records": status_indexes.api_collection_record(
            "target_command_state_records", target_command_state_records, "id", (
                "target_command_state_records_by_id",
                "target_command_state_records_by_has_commands",
                "target_command_state_records_by_has_network_commands",
                "target_command_state_records_by_has_copy_supported_commands",
                "target_command_state_records_by_has_operator_supplied_command_execution",
                "target_command_state_records_by_all_require_explicit_target_action",
                "target_command_state_records_by_safe_explicit_target_action_boundary",
                "target_command_state_records_by_has_session_policy_errors",
            ), "target_command_state_record_count",
        ),
        "rshell_session_policy_records": status_indexes.api_collection_record(
            "rshell_session_policy_records", rshell_session_policy_records, "id", (
                "rshell_session_policy_records_by_id",
                "rshell_session_policy_records_by_session_policy",
                "rshell_session_policy_records_by_session_policy_valid",
                "rshell_session_policy_records_by_retry_scope",
                "rshell_session_policy_records_by_retry_backoff",
                "rshell_session_policy_records_by_reconnects_after_disconnect",
                "rshell_session_policy_records_by_persistent_lifecycle",
            ), "rshell_session_policy_record_count",
        ),
        "targets": status_indexes.api_collection_record(
            "targets", targets, "target_id", (
                "targets_by_id", "targets_by_label", "targets_by_alias",
                "targets_by_remote_addr", "targets_by_service",
                "targets_by_identity_confidence", "targets_by_identity_source",
                "targets_by_latest_activity_service",
                "targets_by_latest_activity_operation",
                "targets_by_connectivity_state",
                "targets_by_last_seen_via",
                "targets_by_offline_age_bucket",
                "targets_by_has_next_expected_poll",
                "targets_by_poll_overdue",
                "targets_by_mailbox_pending_work",
                "targets_by_latest_phone_home_status",
                "targets_by_has_last_failed_phone_home",
                "targets_by_last_failed_phone_home_reason",
                "targets_by_last_failed_phone_home_status",
                "targets_by_latest_file_transfer_operation",
                "targets_by_latest_file_transfer_status",
                "targets_by_latest_file_transfer_route_kind",
                "targets_by_latest_file_transfer_bridge_profile",
                "targets_by_latest_survey_result_kind",
                "targets_by_latest_survey_result_status",
                "targets_by_latest_survey_result_route_kind",
                "targets_by_latest_survey_result_bridge_profile",
                "targets_by_latest_bridge_profile",
                "targets_by_latest_bridge_status",
                "targets_by_has_latest_bridge_activity",
                "targets_by_has_notes",
                "targets_by_capability_report_kind",
                "targets_by_compatibility_report_kind",
                "targets_by_compatibility_label",
                "targets_by_compatibility_baseline_label",
                "targets_by_compatibility_release",
                "targets_by_compatibility_payload_preset",
                "targets_by_observed_capability",
                "targets_by_missing_capability",
                "targets_by_observed_constraint",
            ), "target_count",
        ),
        "target_registry_state_records": status_indexes.api_collection_record(
            "target_registry_state_records", target_registry_state_records, "id", (
                "target_registry_state_records_by_id",
                "target_registry_state_records_by_has_targets",
                "target_registry_state_records_by_has_unfiltered_targets",
                "target_registry_state_records_by_filter_active",
                "target_registry_state_records_by_filter_target_id",
                "target_registry_state_records_by_selected_target_found",
                "target_registry_state_records_by_selected_target_identity_confidence",
                "target_registry_state_records_by_selected_target_connectivity_state",
                "target_registry_state_records_by_selected_target_offline_age_bucket",
                "target_registry_state_records_by_selected_target_latest_phone_home_status",
                "target_registry_state_records_by_selected_target_latest_successful_phone_home_status",
                "target_registry_state_records_by_selected_target_last_failed_phone_home_status",
                "target_registry_state_records_by_selected_target_poll_overdue",
                "target_registry_state_records_by_selected_target_mailbox_pending_work_count",
                "target_registry_state_records_by_selected_target_latest_file_transfer_status",
                "target_registry_state_records_by_selected_target_latest_file_transfer_route_kind",
                "target_registry_state_records_by_selected_target_latest_survey_result_status",
                "target_registry_state_records_by_selected_target_latest_survey_result_route_kind",
                "target_registry_state_records_by_selected_target_latest_bridge_profile",
                "target_registry_state_records_by_selected_target_latest_bridge_status",
                "target_registry_state_records_by_selected_target_latest_capability_report_kind",
                "target_registry_state_records_by_selected_target_latest_compatibility_label",
                "target_registry_state_records_by_selected_target_latest_compatibility_release_name",
                "target_registry_state_records_by_has_latest_activity",
                "target_registry_state_records_by_has_next_expected_polls",
                "target_registry_state_records_by_has_poll_overdue",
                "target_registry_state_records_by_has_mailbox_pending_work",
                "target_registry_state_records_by_has_failed_phone_home",
                "target_registry_state_records_by_has_latest_file_transfer",
                "target_registry_state_records_by_has_latest_survey_result",
                "target_registry_state_records_by_has_latest_bridge_activity",
                "target_registry_state_records_by_has_identity_sources",
                "target_registry_state_records_by_has_capability_reports",
                "target_registry_state_records_by_has_compatibility_reports",
            ), "target_registry_state_record_count",
        ),
        "target_filter_records": status_indexes.api_collection_record(
            "target_filter_records", target_filter_records, "id", (
                "target_filter_records_by_id",
                "target_filter_records_by_active",
                "target_filter_records_by_target_id",
                "target_filter_records_by_selected_target_found",
                "target_filter_records_by_selected_target_label",
                "target_filter_records_by_selected_target_identity_confidence",
                "target_filter_records_by_selected_target_connectivity_state",
                "target_filter_records_by_selected_target_offline_age_bucket",
                "target_filter_records_by_selected_target_latest_phone_home_status",
                "target_filter_records_by_selected_target_latest_successful_phone_home_status",
                "target_filter_records_by_selected_target_last_failed_phone_home_status",
                "target_filter_records_by_selected_target_poll_overdue",
                "target_filter_records_by_selected_target_mailbox_pending_work_count",
                "target_filter_records_by_selected_target_notes_present",
                "target_filter_records_by_selected_target_latest_activity_service",
                "target_filter_records_by_selected_target_latest_activity_operation",
                "target_filter_records_by_selected_target_latest_file_transfer_status",
                "target_filter_records_by_selected_target_latest_file_transfer_route_kind",
                "target_filter_records_by_selected_target_latest_survey_result_status",
                "target_filter_records_by_selected_target_latest_survey_result_route_kind",
                "target_filter_records_by_selected_target_latest_bridge_profile",
                "target_filter_records_by_selected_target_latest_bridge_status",
                "target_filter_records_by_selected_target_latest_capability_report_kind",
                "target_filter_records_by_selected_target_latest_compatibility_report_kind",
                "target_filter_records_by_selected_target_latest_compatibility_label",
                "target_filter_records_by_selected_target_latest_compatibility_release_name",
                "target_filter_records_by_selected_target_latest_compatibility_payload_preset",
                "target_filter_records_by_has_unfiltered_activity",
                "target_filter_records_by_has_filtered_activity",
                "target_filter_records_by_filter_reduced_activity",
                "target_filter_records_by_has_unfiltered_observed_activity",
                "target_filter_records_by_has_filtered_observed_activity",
                "target_filter_records_by_filter_reduced_observed_activity",
            ), "target_filter_record_count",
        ),
        "target_attribution_records": status_indexes.api_collection_record(
            "target_attribution_records", target_attribution_records, "scope", (
                "target_attribution_records_by_scope",
                "target_attribution_records_by_has_targeted_activity",
                "target_attribution_records_by_has_legacy_activity",
                "target_attribution_records_by_legacy_single_target_activity_present",
                "target_attribution_records_by_all_activity_has_target_id",
                "target_attribution_records_by_no_activity",
            ), "target_attribution_record_count",
        ),
    }


def _build_staged_file_activity_api_collections(
    *,
    staged_records,
    staged_file_workflow_actions,
    file_service_workflow_actions,
    target_file_transfer_records,
    target_activity_records,
    staged_files_state_records,
):
    return {
        "staged_records": status_indexes.api_collection_record(
            "staged_records", staged_records, "request_name", (
                "staged_by_request", "staged_by_kind", "staged_by_sha256",
                "staged_by_target_id", "staged_by_source_path",
                "staged_by_fetch_command", "staged_by_fetch_command_force",
                "staged_by_source_exists", "staged_by_kind_source_exists",
            ), "staged_count",
        ),
        "staged_file_workflow_actions": status_indexes.api_collection_record(
            "staged_file_workflow_actions", staged_file_workflow_actions, "id", (
                "staged_file_workflow_actions_by_id",
                "staged_file_workflow_actions_by_action_id",
                "staged_file_workflow_actions_by_request_name",
                "staged_file_workflow_actions_by_stage_kind",
                "staged_file_workflow_actions_by_category",
                "staged_file_workflow_actions_by_workflow",
                "staged_file_workflow_actions_by_target_id",
                "staged_file_workflow_actions_by_target_connectivity_state",
                "staged_file_workflow_actions_by_target_offline_age_bucket",
                "staged_file_workflow_actions_by_target_poll_overdue",
                "staged_file_workflow_actions_by_target_mailbox_pending_work_count",
                "staged_file_workflow_actions_by_target_latest_phone_home_status",
                "staged_file_workflow_actions_by_target_latest_successful_phone_home_status",
                "staged_file_workflow_actions_by_target_last_failed_phone_home_status",
                "staged_file_workflow_actions_by_route_kind",
                "staged_file_workflow_actions_by_bridge_profile",
                "staged_file_workflow_actions_by_fleet_target_count",
                "staged_file_workflow_actions_by_fleet_offline_target_count",
                "staged_file_workflow_actions_by_fleet_stale_target_count",
                "staged_file_workflow_actions_by_fleet_mailbox_pending_target_count",
                "staged_file_workflow_actions_by_fleet_mailbox_pending_work_count",
                "staged_file_workflow_actions_by_fleet_poll_overdue_target_count",
                "staged_file_workflow_actions_by_fleet_has_offline_targets",
                "staged_file_workflow_actions_by_fleet_has_stale_targets",
                "staged_file_workflow_actions_by_fleet_has_mailbox_pending_work",
                "staged_file_workflow_actions_by_fleet_has_poll_overdue_targets",
                "staged_file_workflow_actions_by_source_exists",
                "staged_file_workflow_actions_by_available",
                "staged_file_workflow_actions_by_requires_target",
                "staged_file_workflow_actions_by_queues_offline_work",
                "staged_file_workflow_actions_by_requires_confirmation",
                "staged_file_workflow_actions_by_operator_action_state",
                "staged_file_workflow_actions_by_operator_action_reason",
                "staged_file_workflow_actions_by_can_run_from_curses_enter",
                "staged_file_workflow_actions_by_curses_enter_action",
            ), "staged_file_workflow_action_count",
        ),
        "file_service_workflow_actions": status_indexes.api_collection_record(
            "file_service_workflow_actions", file_service_workflow_actions, "id", (
                "file_service_workflow_actions_by_id",
                "file_service_workflow_actions_by_action_id",
                "file_service_workflow_actions_by_service",
                "file_service_workflow_actions_by_category",
                "file_service_workflow_actions_by_workflow",
                "file_service_workflow_actions_by_actual",
                "file_service_workflow_actions_by_configured",
                "file_service_workflow_actions_by_target_filter_active",
                "file_service_workflow_actions_by_route_kind",
                "file_service_workflow_actions_by_bridge_profile",
                "file_service_workflow_actions_by_requires_bridge",
                "file_service_workflow_actions_by_fleet_target_count",
                "file_service_workflow_actions_by_fleet_offline_target_count",
                "file_service_workflow_actions_by_fleet_stale_target_count",
                "file_service_workflow_actions_by_fleet_mailbox_pending_target_count",
                "file_service_workflow_actions_by_fleet_mailbox_pending_work_count",
                "file_service_workflow_actions_by_fleet_poll_overdue_target_count",
                "file_service_workflow_actions_by_fleet_has_offline_targets",
                "file_service_workflow_actions_by_fleet_has_stale_targets",
                "file_service_workflow_actions_by_fleet_has_mailbox_pending_work",
                "file_service_workflow_actions_by_fleet_has_poll_overdue_targets",
                "file_service_workflow_actions_by_available",
                "file_service_workflow_actions_by_requires_input",
                "file_service_workflow_actions_by_requires_confirmation",
                "file_service_workflow_actions_by_queues_offline_work",
                "file_service_workflow_actions_by_operator_action_state",
                "file_service_workflow_actions_by_operator_action_reason",
                "file_service_workflow_actions_by_can_run_from_curses_enter",
                "file_service_workflow_actions_by_curses_enter_action",
            ), "file_service_workflow_action_count",
        ),
        "target_file_transfer_records": status_indexes.api_collection_record(
            "target_file_transfer_records", target_file_transfer_records, "id", (
                "target_file_transfer_records_by_id",
                "target_file_transfer_records_by_target_id",
                "target_file_transfer_records_by_target_label",
                "target_file_transfer_records_by_operation",
                "target_file_transfer_records_by_source_collection",
                "target_file_transfer_records_by_status",
                "target_file_transfer_records_by_route_kind",
                "target_file_transfer_records_by_bridge_profile",
                "target_file_transfer_records_by_request_name",
                "target_file_transfer_records_by_filename",
                "target_file_transfer_records_by_sha256",
                "target_file_transfer_records_by_session_id",
            ), "target_file_transfer_record_count",
        ),
        "target_activity_records": status_indexes.api_collection_record(
            "target_activity_records", target_activity_records, "id", (
                "target_activity_records_by_id",
                "target_activity_records_by_target_id",
                "target_activity_records_by_target_label",
                "target_activity_records_by_category",
                "target_activity_records_by_source_collection",
                "target_activity_records_by_operation",
                "target_activity_records_by_status",
                "target_activity_records_by_route_kind",
                "target_activity_records_by_bridge_profile",
                "target_activity_records_by_session_id",
                "target_activity_records_by_command_id",
                "target_activity_records_by_request_name",
                "target_activity_records_by_filename",
                "target_activity_records_by_pending_work",
                "target_activity_records_by_waiting_for",
                "target_activity_records_by_target_connectivity_state",
                "target_activity_records_by_target_offline_age_bucket",
                "target_activity_records_by_target_poll_overdue",
                "target_activity_records_by_target_mailbox_pending_work_count",
            ), "target_activity_record_count",
        ),
        "staged_files_state_records": status_indexes.api_collection_record(
            "staged_files_state_records", staged_files_state_records, "path", (
                "staged_files_state_records_by_path",
                "staged_files_state_records_by_exists",
                "staged_files_state_records_by_valid",
                "staged_files_state_records_by_has_staged",
                "staged_files_state_records_by_schema",
            ), "staged_files_state_record_count",
        ),
    }


def _build_command_mailbox_api_collections(
    *,
    command_copy_records,
    command_copy_state_records,
    command_queue_state_records,
    target_mailbox_records,
    target_phone_home_records,
):
    return {
        "command_copy_records": status_indexes.api_collection_record(
            "command_copy_records", command_copy_records, "path", (
                "command_copy_records_by_path", "command_copy_records_by_exists",
                "command_copy_records_by_readable", "command_copy_records_by_has_command",
                "command_copy_records_by_command_sha256",
            ), "command_copy_exists_count",
        ),
        "command_copy_state_records": status_indexes.api_collection_record(
            "command_copy_state_records", command_copy_state_records, "id", (
                "command_copy_state_records_by_id",
                "command_copy_state_records_by_path",
                "command_copy_state_records_by_exists",
                "command_copy_state_records_by_readable",
                "command_copy_state_records_by_has_command",
                "command_copy_state_records_by_empty_or_missing",
                "command_copy_state_records_by_has_readable_command",
                "command_copy_state_records_by_command_sha256",
            ), "command_copy_state_record_count",
        ),
        "command_queue_state_records": status_indexes.api_collection_record(
            "command_queue_state_records", command_queue_state_records, "path", (
                "command_queue_state_records_by_path",
                "command_queue_state_records_by_exists",
                "command_queue_state_records_by_valid",
                "command_queue_state_records_by_has_commands",
            ), "command_queue_state_record_count",
        ),
        "target_mailbox_records": status_indexes.api_collection_record(
            "target_mailbox_records", target_mailbox_records, "command_id", (
                "target_mailbox_records_by_id",
                "target_mailbox_records_by_command_id",
                "target_mailbox_records_by_target_id",
                "target_mailbox_records_by_target_label",
                "target_mailbox_records_by_target_connectivity_state",
                "target_mailbox_records_by_target_last_seen_via",
                "target_mailbox_records_by_target_offline_age_bucket",
                "target_mailbox_records_by_has_target_next_expected_poll",
                "target_mailbox_records_by_target_poll_overdue",
                "target_mailbox_records_by_status",
                "target_mailbox_records_by_waiting_for",
                "target_mailbox_records_by_pending_reason",
                "target_mailbox_records_by_has_pending_reason",
                "target_mailbox_records_by_work_kind",
                "target_mailbox_records_by_workflow",
                "target_mailbox_records_by_request_name",
                "target_mailbox_records_by_bridge_profile",
                "target_mailbox_records_by_bridge_requires_target_online",
                "target_mailbox_records_by_route_kind",
                "target_mailbox_records_by_expired",
                "target_mailbox_records_by_age_bucket",
                "target_mailbox_records_by_pending_delivery_age_bucket",
                "target_mailbox_records_by_delivered_without_result_age_bucket",
                "target_mailbox_records_by_result_latency_bucket",
                "target_mailbox_records_by_pending_work",
                "target_mailbox_records_by_pending_delivery",
                "target_mailbox_records_by_delivered_without_result",
                "target_mailbox_records_by_has_result",
                "target_mailbox_records_by_result_status",
                "target_mailbox_records_by_result_exit_code",
                "target_mailbox_records_by_result_output_exceeded_limit",
                "target_mailbox_records_by_result_output_size_bucket",
                "target_mailbox_records_by_command_sha256",
            ), "target_mailbox_record_count",
        ),
        "target_phone_home_records": status_indexes.api_collection_record(
            "target_phone_home_records", target_phone_home_records, "id", (
                "target_phone_home_records_by_id",
                "target_phone_home_records_by_event_id",
                "target_phone_home_records_by_kind",
                "target_phone_home_records_by_status",
                "target_phone_home_records_by_successful",
                "target_phone_home_records_by_failed",
                "target_phone_home_records_by_target_id",
                "target_phone_home_records_by_target_label",
                "target_phone_home_records_by_target_connectivity_state",
                "target_phone_home_records_by_target_last_seen_via",
                "target_phone_home_records_by_target_offline_age_bucket",
                "target_phone_home_records_by_target_poll_overdue",
                "target_phone_home_records_by_target_mailbox_pending_work_count",
                "target_phone_home_records_by_has_target_identity",
                "target_phone_home_records_by_anonymous",
                "target_phone_home_records_by_contact_path",
                "target_phone_home_records_by_remote_addr",
                "target_phone_home_records_by_http_status",
                "target_phone_home_records_by_reason",
                "target_phone_home_records_by_pending_reason",
                "target_phone_home_records_by_has_pending_reason",
                "target_phone_home_records_by_has_queued_remaining_count",
                "target_phone_home_records_by_pending_work_remaining",
                "target_phone_home_records_by_queued_remaining_count",
                "target_phone_home_records_by_command_id",
                "target_phone_home_records_by_work_kind",
                "target_phone_home_records_by_workflow",
                "target_phone_home_records_by_request_name",
                "target_phone_home_records_by_bridge_profile",
                "target_phone_home_records_by_bridge_requires_target_online",
                "target_phone_home_records_by_route_kind",
                "target_phone_home_records_by_poll_mode",
                "target_phone_home_records_by_poll_interval_sec",
            ), "target_phone_home_record_count",
        ),
    }


def status_document(cfg):
    event_limit = int(cfg.get("_event_limit", 12))
    target_filter_id = target_records.configured_target_filter(cfg)
    staged_context = _build_staged_file_status_context(cfg, target_filter_id)
    staged_raw = staged_context["staged_raw"]
    unfiltered_staged_raw = staged_context["unfiltered_staged_raw"]
    staged = staged_context["staged"]
    staged_records = staged_context["staged_records"]
    unfiltered_staged_count = staged_context["unfiltered_staged_count"]
    staged_by_request = staged_context["staged_by_request"]
    staged_by_kind = staged_context["staged_by_kind"]
    staged_by_sha256 = staged_context["staged_by_sha256"]
    staged_by_target_id = staged_context["staged_by_target_id"]
    staged_by_source_path = staged_context["staged_by_source_path"]
    staged_by_fetch_command = staged_context["staged_by_fetch_command"]
    staged_by_fetch_command_force = staged_context["staged_by_fetch_command_force"]
    staged_by_source_exists = staged_context["staged_by_source_exists"]
    staged_by_kind_source_exists = staged_context["staged_by_kind_source_exists"]
    operator_network_context = _build_operator_network_status_context(cfg)
    ips = operator_network_context["ips"]
    operator_network = operator_network_context["operator_network"]
    selected_local_ip = operator_network_context["selected_local_ip"]
    operator_network_records = operator_network_context["operator_network_records"]
    operator_network_index_maps = operator_network_context["operator_network_index_maps"]
    operator_network_state_record = operator_network_context[
        "operator_network_state_record"
    ]
    operator_network_state_records = operator_network_context[
        "operator_network_state_records"
    ]
    operator_network_state_index_maps = operator_network_context[
        "operator_network_state_index_maps"
    ]
    operator_dir = operator_network_context["operator_dir"]
    event_log_path = operator_network_context["event_log_path"]
    session_root = operator_network_context["session_root"]
    service_context = _build_service_status_context(cfg)
    services = service_context["services"]
    service_manager = service_context["service_manager"]
    service_manager_status_doc = service_context["service_manager_status_doc"]
    service_manager_resources = service_context["service_manager_resources"]
    service_manager_resource_index_maps = service_context[
        "service_manager_resource_index_maps"
    ]
    service_manager_state_record = service_context["service_manager_state_record"]
    service_manager_state_records = service_context["service_manager_state_records"]
    service_manager_state_index_maps = service_context[
        "service_manager_state_index_maps"
    ]
    ports = service_context["ports"]
    port_index_maps = service_context["port_index_maps"]
    event_source_context = _build_event_source_status_context(cfg)
    all_event_records = event_source_context["all_event_records"]
    all_target_phone_home_records = event_source_context[
        "all_target_phone_home_records"
    ]
    target_context = _build_target_registry_context(
        cfg,
        target_filter_id=target_filter_id,
        all_target_phone_home_records=all_target_phone_home_records,
        unfiltered_staged_count=unfiltered_staged_count,
    )
    uploads = target_context["uploads"]
    fetches = target_context["fetches"]
    targets = target_context["targets"]
    unfiltered_counts = target_context["unfiltered_counts"]
    target_index_maps = target_context["target_index_maps"]
    targets_by_id = target_index_maps["targets_by_id"]
    target_summary = target_context["target_summary"]
    bridge_profile_context = _build_bridge_profile_status_context(cfg, targets)
    bridge_profiles = bridge_profile_context["bridge_profiles"]
    bridge_profile_index_maps = bridge_profile_context["bridge_profile_index_maps"]
    bridge_hop_records = bridge_profile_context["bridge_hop_records"]
    bridge_hop_index_maps = bridge_profile_context["bridge_hop_index_maps"]
    staged_file_workflow_context = _build_staged_file_workflow_status_context(
        cfg,
        staged_records,
        targets,
    )
    staged_file_workflow_actions = staged_file_workflow_context[
        "staged_file_workflow_actions"
    ]
    staged_file_workflow_action_index_maps = staged_file_workflow_context[
        "staged_file_workflow_action_index_maps"
    ]
    bridge_profile_workflow_actions = bridge_profile_context[
        "bridge_profile_workflow_actions"
    ]
    bridge_profile_workflow_action_index_maps = bridge_profile_context[
        "bridge_profile_workflow_action_index_maps"
    ]
    selected_target = target_context["selected_target"]
    target_registry_state_record = target_context["target_registry_state_record"]
    target_registry_state_records = target_context["target_registry_state_records"]
    target_registry_state_index_maps = target_context["target_registry_state_index_maps"]
    target_registry_summary = target_context["target_registry_summary"]
    session_context = _build_session_status_context(
        cfg,
        target_filter_id=target_filter_id,
    )
    sessions = session_context["sessions"]
    unfiltered_counts["sessions"] = session_context["unfiltered_count"]
    target_filter_session_ids = session_context["target_filter_session_ids"]
    session_root_state = session_context["session_root_state"]
    session_root_state_records = session_context["session_root_state_records"]
    session_root_state_index_maps = session_context["session_root_state_index_maps"]
    reconcile_workbench_job_completion_events(cfg)
    session_index_maps = session_context["session_index_maps"]
    event_context = _build_event_status_context(
        cfg,
        event_limit,
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    event_stats = event_context["event_stats"]
    event_log_state = event_context["event_log_state"]
    event_log_state_records = event_context["event_log_state_records"]
    event_log_state_index_maps = event_context["event_log_state_index_maps"]
    events = event_context["events"]
    unfiltered_counts["event_tail"] = event_context["unfiltered_tail_count"]
    event_index_maps = event_context["event_index_maps"]
    event_summary_stats = event_context["event_summary_stats"]
    command_queue_context = _build_command_queue_status_context(cfg)
    command_queue = command_queue_context["command_queue"]
    target_activity_context = _build_target_activity_status_context(
        command_queue,
        targets_by_id,
        all_event_records,
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    target_mailbox_records = target_activity_context["target_mailbox_records"]
    target_mailbox_index_maps = target_activity_context["target_mailbox_index_maps"]
    target_phone_home_records = target_activity_context["target_phone_home_records"]
    target_phone_home_index_maps = target_activity_context["target_phone_home_index_maps"]
    command_queue_policy_records = command_queue_context["command_queue_policy_records"]
    command_queue_policy_index_maps = command_queue_context[
        "command_queue_policy_index_maps"
    ]
    command_queue_index_maps = command_queue_context["command_queue_index_maps"]
    command_queue_mode_records = command_queue_context["command_queue_mode_records"]
    command_queue_mode_index_maps = command_queue_context[
        "command_queue_mode_index_maps"
    ]
    unfiltered_counts["command_queue_commands"] = command_queue_context["unfiltered_count"]
    release_context_doc = _build_release_status_context(cfg)
    release = release_context_doc["release"]
    release_state = release_context_doc["release_state"]
    release_state_records = release_context_doc["release_state_records"]
    release_state_index_maps = release_context_doc["release_state_index_maps"]
    release_artifact_workflow_actions = release_context_doc[
        "release_artifact_workflow_actions"
    ]
    release_artifact_workflow_action_index_maps = release_context_doc[
        "release_artifact_workflow_action_index_maps"
    ]
    rshell_session_policy_context = _build_rshell_session_policy_status_context(cfg)
    rshell_session_policy = rshell_session_policy_context["rshell_session_policy"]
    rshell_session_policy_record_item = rshell_session_policy_context[
        "rshell_session_policy_record_item"
    ]
    rshell_session_policy_records = rshell_session_policy_context[
        "rshell_session_policy_records"
    ]
    rshell_session_policy_index_maps = rshell_session_policy_context[
        "rshell_session_policy_index_maps"
    ]
    workbench_config_context = _build_workbench_config_status_context(cfg)
    workbench_config_fields = workbench_config_context["workbench_config_fields"]
    workbench_config_field_index_maps = workbench_config_context[
        "workbench_config_field_index_maps"
    ]
    workflow_context = _build_workbench_workflow_status_context(
        cfg,
        targets,
        bridge_profiles,
    )
    workbench_action_context = workflow_context["workbench_action_context"]
    workbench_actions = workflow_context["workbench_actions"]
    workbench_action_index_maps = workflow_context["workbench_action_index_maps"]
    operator_daemon_workflow_actions = workflow_context[
        "operator_daemon_workflow_actions"
    ]
    operator_daemon_workflow_action_index_maps = workflow_context[
        "operator_daemon_workflow_action_index_maps"
    ]
    target_workflow_actions = workflow_context["target_workflow_actions"]
    target_workflow_action_index_maps = workflow_context[
        "target_workflow_action_index_maps"
    ]
    workbench_job_context = workflow_context["workbench_job_context"]
    workbench_jobs = workflow_context["workbench_jobs"]
    workbench_job_index_maps = workflow_context["workbench_job_index_maps"]
    target_command_context = _build_target_command_status_context(
        cfg,
        staged_raw=staged_raw,
        unfiltered_staged_raw=unfiltered_staged_raw,
        target_filter_id=target_filter_id,
    )
    target_command_records = target_command_context["target_command_records"]
    unfiltered_counts["target_command_records"] = target_command_context["unfiltered_count"]
    target_command_index_maps = target_command_context["target_command_index_maps"]
    target_command_summary = target_command_context["target_command_summary"]
    target_filter_context = _build_target_filter_status_context(
        target_filter_id,
        selected_target,
        unfiltered_counts,
        targets=targets,
        uploads=uploads,
        fetches=fetches,
        staged_records=staged_records,
        sessions=sessions,
        events=events,
        command_queue=command_queue,
        target_command_summary=target_command_summary,
        target_phone_home_records=target_phone_home_records,
        target_mailbox_records=target_mailbox_records,
    )
    target_filter_record = target_filter_context["target_filter_record"]
    target_filter_records = target_filter_context["target_filter_records"]
    target_filter_index_maps = target_filter_context["target_filter_index_maps"]
    target_command_state_record = target_command_context["target_command_state_record"]
    target_command_state_records = target_command_context["target_command_state_records"]
    target_command_state_index_maps = target_command_context["target_command_state_index_maps"]
    file_transfer_context = _build_file_transfer_status_context(
        staged_records,
        uploads,
        fetches,
    )
    upload_index_maps = file_transfer_context["upload_index_maps"]
    fetch_index_maps = file_transfer_context["fetch_index_maps"]
    target_file_transfer_records = file_transfer_context["target_file_transfer_records"]
    target_file_transfer_index_maps = file_transfer_context["target_file_transfer_index_maps"]
    file_service_workflow_context = _build_file_service_workflow_status_context(
        cfg,
        services,
        staged_records,
        uploads,
        fetches,
        target_file_transfer_records,
        targets,
    )
    file_service_row = file_service_workflow_context["file_service_row"]
    file_service_workflow_actions = file_service_workflow_context[
        "file_service_workflow_actions"
    ]
    file_service_workflow_action_index_maps = file_service_workflow_context[
        "file_service_workflow_action_index_maps"
    ]
    target_activity_feed_context = _build_target_activity_feed_status_context(
        targets,
        target_mailbox_records,
        target_phone_home_records,
        target_file_transfer_records,
        bridge_profiles,
        sessions,
    )
    target_activity_records = target_activity_feed_context["target_activity_records"]
    target_activity_index_maps = target_activity_feed_context[
        "target_activity_index_maps"
    ]
    summary = service_context["summary"]
    warnings = service_context["warnings"]
    service_index_maps = service_context["service_index_maps"]
    target_attribution_context = _build_target_attribution_status_context(
        uploads,
        fetches,
        sessions,
    )
    target_attribution_status_doc = target_attribution_context[
        "target_attribution_status_doc"
    ]
    target_attribution = target_attribution_context["target_attribution"]
    target_attribution_records = target_attribution_context[
        "target_attribution_records"
    ]
    target_attribution_index_maps = target_attribution_context[
        "target_attribution_index_maps"
    ]
    paths = {
        "operator_session_dir": str(operator_dir),
        "state_file": str(session_state_module.state_file_path(cfg)),
        "staged_files": str(staged_files.staged_file_path(cfg)),
        "command_queue_file": str(command_queue_module.command_queue_path(cfg)),
        "command_copy_file": str(command_copy_module.command_copy_path(cfg)),
        "workbench_jobs_file": str(workbench_jobs_path(cfg)),
        "targets_file": str(target_records.targets_path(cfg)),
        "build_config": str(build_config_path(cfg)),
        "event_log": str(event_log_path),
        "session_root": session_root,
        "tls_cert": str(cfg.get("tls_cert", "")),
        "tls_key": str(cfg.get("tls_key", "")),
    }
    operator_state_context = _build_operator_state_status_context(
        cfg,
        event_log_state=event_log_state,
        session_root_state=session_root_state,
    )
    server_state = operator_state_context["server_state"]
    server_state_records = operator_state_context["server_state_records"]
    server_state_index_maps = operator_state_context["server_state_index_maps"]
    staged_files_state = operator_state_context["staged_files_state"]
    staged_files_state_records = operator_state_context["staged_files_state_records"]
    staged_files_state_index_maps = operator_state_context[
        "staged_files_state_index_maps"
    ]
    command_queue_state = operator_state_context["command_queue_state"]
    command_queue_state_records = operator_state_context["command_queue_state_records"]
    command_queue_state_index_maps = operator_state_context[
        "command_queue_state_index_maps"
    ]
    command_copy = operator_state_context["command_copy"]
    command_copy_records = operator_state_context["command_copy_records"]
    command_copy_record_indexes = operator_state_context["command_copy_record_indexes"]
    command_copy_state_record = operator_state_context["command_copy_state_record"]
    command_copy_state_records = operator_state_context["command_copy_state_records"]
    command_copy_state_index_maps = operator_state_context[
        "command_copy_state_index_maps"
    ]
    workbench_jobs_state = operator_state_context["workbench_jobs_state"]
    workbench_jobs_state_records = operator_state_context["workbench_jobs_state_records"]
    workbench_jobs_state_index_maps = operator_state_context[
        "workbench_jobs_state_index_maps"
    ]
    operator_state_records_list = operator_state_context["operator_state_records_list"]
    operator_state_index_maps = operator_state_context["operator_state_index_maps"]
    operator_state_summary = operator_state_context["operator_state_summary"]
    operator_state_file_summary_doc = operator_state_context[
        "operator_state_file_summary_doc"
    ]
    path_browser_context = _build_path_browser_status_context(
        cfg,
        paths,
        staged_records=staged_records,
        uploads=uploads,
        fetches=fetches,
        sessions=sessions,
        release=release,
    )
    path_context = path_browser_context["path_context"]
    path_status = path_browser_context["path_status"]
    path_status_records = path_browser_context["path_status_records"]
    path_status_indexes = path_browser_context["path_status_indexes"]
    browser_paths = path_browser_context["browser_paths"]
    browser_path_index_maps = path_browser_context["browser_path_index_maps"]
    browser_summary = path_browser_context["browser_summary"]
    services_by_name = service_context["services_by_name"]
    command_queue_workflow_context = _build_command_queue_workflow_status_context(
        cfg,
        command_queue,
        target_mailbox_records,
        services_by_name.get("command-queue") or {},
        targets,
    )
    command_queue_workflow_actions = command_queue_workflow_context[
        "command_queue_workflow_actions"
    ]
    command_queue_workflow_action_index_maps = command_queue_workflow_context[
        "command_queue_workflow_action_index_maps"
    ]
    warning_context = _build_warning_status_context(
        cfg,
        warnings=warnings,
        path_status=path_status,
        path_status_records=path_status_records,
        browser_paths=browser_paths,
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
        services=services,
        ports=ports,
        services_by_name=services_by_name,
    )
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
     warnings_by_type_service_port) = warning_context["warning_index_maps"]
    path_warning_context = warning_context["path_warning_context"]
    path_status_by_has_warnings = path_warning_context[
        "path_status_by_has_warnings"
    ]
    path_status_by_warning_type = path_warning_context["path_status_by_warning_type"]
    browser_paths_by_has_warnings = path_warning_context[
        "browser_paths_by_has_warnings"
    ]
    browser_paths_by_warning_type = path_warning_context[
        "browser_paths_by_warning_type"
    ]
    browser_summary = warning_context["browser_summary"]
    services_by_has_warnings = warning_context["services_by_has_warnings"]
    services_by_warning_type = warning_context["services_by_warning_type"]
    ports_by_has_warnings = warning_context["ports_by_has_warnings"]
    ports_by_warning_type = warning_context["ports_by_warning_type"]
    service_probe_workflow_context = _build_service_probe_workflow_status_context(
        cfg,
        services,
        services_by_name,
        targets,
    )
    service_workflow_actions = service_probe_workflow_context[
        "service_workflow_actions"
    ]
    service_workflow_action_index_maps = service_probe_workflow_context[
        "service_workflow_action_index_maps"
    ]
    probe_workflow_actions = service_probe_workflow_context["probe_workflow_actions"]
    probe_workflow_action_index_maps = service_probe_workflow_context[
        "probe_workflow_action_index_maps"
    ]
    operator_console_workflow_context = _build_operator_console_workflow_status_context(
        cfg,
        targets=targets,
        target_workflow_actions=target_workflow_actions,
        target_mailbox_records=target_mailbox_records,
        bridge_profiles=bridge_profiles,
        bridge_profile_workflow_actions=bridge_profile_workflow_actions,
        staged_records=staged_records,
        staged_file_workflow_actions=staged_file_workflow_actions,
        file_service_workflow_actions=file_service_workflow_actions,
        probe_workflow_actions=probe_workflow_actions,
        command_queue_workflow_actions=command_queue_workflow_actions,
        service_workflow_actions=service_workflow_actions,
        operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        workbench_actions=workbench_actions,
        workbench_config_fields=workbench_config_fields,
        workbench_jobs=workbench_jobs,
        target_activity_records=target_activity_records,
        release_artifact_workflow_actions=release_artifact_workflow_actions,
        release=release,
        warnings=warnings,
    )
    operator_console_workflows = operator_console_workflow_context[
        "operator_console_workflows"
    ]
    operator_console_workflow_index_maps = operator_console_workflow_context[
        "operator_console_workflow_index_maps"
    ]
    operator_console_workflow_stats = operator_console_workflow_context[
        "operator_console_workflow_stats"
    ]
    warning_summary_context = _build_warning_summary_status_context(
        warnings,
        services_by_has_warnings=services_by_has_warnings,
        services_by_warning_type=services_by_warning_type,
        ports_by_has_warnings=ports_by_has_warnings,
        ports_by_warning_type=ports_by_warning_type,
    )
    warning_summary = warning_summary_context["warning_summary"]
    summary.update({
        **path_context["path_summary"],
        **bridge_profile_context["summary"],
        **path_context["browser_status_summary"],
        **path_warning_context["summary"],
        **operator_state_file_summary_doc,
        **operator_state_summary,
        **staged_file_workflow_context["summary"],
        **service_status.service_status_summary(
            services, service_manager, service_manager_status_doc
        ),
        **service_status.port_status_summary(ports),
        **warning_summary_context["summary"],
        **file_transfers.upload_record_summary(uploads, target_attribution),
        **file_transfers.fetch_record_summary(fetches, target_attribution),
        **file_transfers.target_file_transfer_record_summary(
            target_file_transfer_records
        ),
        **file_service_workflow_context["summary"],
        **target_activity_feed_context["summary"],
        **target_summary,
        **target_registry_summary,
        **target_filter_context["summary"],
        **target_attribution_context["summary"],
        **session_record_summary(
            sessions, session_root_state, session_root_state_records, target_attribution
        ),
        **target_command_status_summary(
            target_command_summary,
            target_command_state_record,
            target_command_state_records,
            rshell_session_policy_record_item,
            rshell_session_policy_records,
        ),
        **workflow_context["summary"],
        **event_status_summary(
            event_stats, event_log_state, event_log_state_records,
            events, event_summary_stats,
        ),
        **operator_network_context["summary"],
        **command_queue_module.command_queue_status_summary(
            command_queue, command_queue_policy_records
        ),
        **target_activity_context["summary"],
        **release_context_doc["summary"],
        **release_artifact_workflow_action_status_summary(release_artifact_workflow_actions),
        **operator_console_workflow_context["summary"],
        **workbench_config_context["summary"],
        **command_queue_workflow_context["summary"],
        **service_probe_workflow_context["summary"],
    })
    api_collections = {
        **_build_service_bridge_api_collections(
            services=services,
            service_workflow_actions=service_workflow_actions,
            probe_workflow_actions=probe_workflow_actions,
            service_manager_resources=service_manager_resources,
            service_manager_state_records=service_manager_state_records,
            bridge_profiles=bridge_profiles,
            bridge_profile_workflow_actions=bridge_profile_workflow_actions,
            bridge_hop_records=bridge_hop_records,
        ),
        **_build_operator_health_api_collections(
            ports=ports,
            path_status_records=path_status_records,
            server_state_records=server_state_records,
            operator_state_records_list=operator_state_records_list,
            operator_network_records=operator_network_records,
            operator_network_state_records=operator_network_state_records,
            browser_paths=browser_paths,
            warnings=warnings,
        ),
        **_build_target_api_collections(
            target_command_records=target_command_records,
            target_workflow_actions=target_workflow_actions,
            target_command_state_records=target_command_state_records,
            rshell_session_policy_records=rshell_session_policy_records,
            targets=targets,
            target_registry_state_records=target_registry_state_records,
            target_filter_records=target_filter_records,
            target_attribution_records=target_attribution_records,
        ),
        **_build_staged_file_activity_api_collections(
            staged_records=staged_records,
            staged_file_workflow_actions=staged_file_workflow_actions,
            file_service_workflow_actions=file_service_workflow_actions,
            target_file_transfer_records=target_file_transfer_records,
            target_activity_records=target_activity_records,
            staged_files_state_records=staged_files_state_records,
        ),
        **_build_command_mailbox_api_collections(
            command_copy_records=command_copy_records,
            command_copy_state_records=command_copy_state_records,
            command_queue_state_records=command_queue_state_records,
            target_mailbox_records=target_mailbox_records,
            target_phone_home_records=target_phone_home_records,
        ),
        "workbench_jobs_state_records": status_indexes.api_collection_record(
            "workbench_jobs_state_records", workbench_jobs_state_records, "path", (
                "workbench_jobs_state_records_by_path",
                "workbench_jobs_state_records_by_exists",
                "workbench_jobs_state_records_by_valid",
                "workbench_jobs_state_records_by_has_jobs",
            ), "workbench_jobs_state_record_count",
        ),
        "uploads": status_indexes.api_collection_record(
            "uploads", uploads, "metadata_path", (
                "uploads_by_session", "uploads_by_filename", "uploads_by_kind", "uploads_by_sha256",
                "uploads_by_target_id", "uploads_by_source_path", "uploads_by_stored_path", "uploads_by_remote_addr",
                "uploads_by_status", "uploads_by_kind_status", "uploads_by_filename_status",
                "uploads_by_stored_exists", "uploads_by_status_stored_exists",
                "uploads_by_status_remote_addr", "uploads_by_metadata_exists",
                "uploads_by_event_log_exists",
            ), "upload_count",
        ),
        "fetches": status_indexes.api_collection_record(
            "fetches", fetches, "metadata_path", (
                "fetches_by_session", "fetches_by_request", "fetches_by_sha256", "fetches_by_target_id",
                "fetches_by_source_path", "fetches_by_status", "fetches_by_http_status",
                "fetches_by_source_exists", "fetches_by_remote_addr", "fetches_by_request_status",
                "fetches_by_status_source_exists", "fetches_by_metadata_exists",
                "fetches_by_event_log_exists",
                "fetches_by_status_remote_addr", "fetches_by_http_status_remote_addr",
            ), "fetch_count",
        ),
        "session_root_state_records": status_indexes.api_collection_record(
            "session_root_state_records", session_root_state_records, "path", (
                "session_root_state_records_by_path",
                "session_root_state_records_by_exists",
                "session_root_state_records_by_has_recent_sessions",
                "session_root_state_records_by_has_uploads",
                "session_root_state_records_by_has_fetches",
                "session_root_state_records_by_has_events",
            ), "session_root_state_record_count",
        ),
        "sessions": status_indexes.api_collection_record(
            "sessions", sessions, "session_id", (
                "sessions_by_id", "sessions_by_service", "sessions_by_state",
                "sessions_by_exit_reason", "sessions_by_remote",
                "sessions_by_service_state", "sessions_by_service_exit_reason",
                "sessions_by_service_remote", "sessions_by_target_id", "sessions_by_has_uploads",
                "sessions_by_has_fetches", "sessions_by_has_events",
                "sessions_by_has_artifacts", "sessions_by_has_session_log",
                "sessions_by_duration_known", "sessions_by_metadata_exists",
                "sessions_by_event_log_exists", "sessions_by_session_log_exists",
            ), "session_count",
        ),
        "events": status_indexes.api_collection_record(
            "events", events, "id", (
                "events_by_id", "events_by_session", "events_by_service",
                "events_by_event", "events_by_level", "events_by_remote",
                "events_by_service_event", "events_by_session_event",
                "events_by_service_level", "events_by_event_level",
                "events_by_session_level", "events_by_remote_event",
                "events_by_remote_level",
                "events_by_detail_status", "events_by_detail_operation",
                "events_by_detail_http_status", "events_by_detail_reason",
                "events_by_detail_command_id", "events_by_event_detail_status",
                "events_by_service_detail_status", "events_by_event_detail_operation",
                "events_by_service_detail_operation", "events_by_event_detail_http_status",
                "events_by_service_detail_http_status", "events_by_detail_request_name",
                "events_by_event_detail_request_name", "events_by_service_detail_request_name",
                "events_by_detail_filename", "events_by_event_detail_filename",
                "events_by_service_detail_filename", "events_by_event_detail_reason",
                "events_by_service_detail_reason", "events_by_detail_sha256",
                "events_by_event_detail_sha256", "events_by_service_detail_sha256",
                "events_by_event_detail_command_id",
                "events_by_service_detail_command_id", "events_by_detail_command_sha256",
                "events_by_event_detail_command_sha256", "events_by_service_detail_command_sha256",
                "events_by_detail_job_id",
                "events_by_event_detail_job_id", "events_by_service_detail_job_id",
                "events_by_detail_action_id", "events_by_event_detail_action_id",
                "events_by_service_detail_action_id",
                "events_by_detail_key", "events_by_event_detail_key",
                "events_by_service_detail_key", "events_by_detail_config_path",
                "events_by_event_detail_config_path", "events_by_service_detail_config_path",
                "events_by_detail_target_id", "events_by_detail_target_label",
                "events_by_detail_expected_target_id",
                "events_by_detail_target_identity_source",
                "events_by_detail_target_identity_confidence",
                "events_by_detail_poll_mode", "events_by_detail_poll_interval_sec",
                "events_by_detail_poll_jitter_pct", "events_by_detail_poll_backoff",
                "events_by_detail_poll_max_interval_sec", "events_by_detail_max_polls",
                "events_by_event_detail_target_id", "events_by_service_detail_target_id",
                "events_by_event_detail_target_label", "events_by_service_detail_target_label",
                "events_by_event_detail_expected_target_id",
                "events_by_service_detail_expected_target_id",
                "events_by_event_detail_target_identity_source",
                "events_by_service_detail_target_identity_source",
                "events_by_event_detail_target_identity_confidence",
                "events_by_service_detail_target_identity_confidence",
            ), "event_tail_count",
        ),
        "event_log_state_records": status_indexes.api_collection_record(
            "event_log_state_records", event_log_state_records, "path", (
                "event_log_state_records_by_path",
                "event_log_state_records_by_exists",
                "event_log_state_records_by_valid",
                "event_log_state_records_by_tail_truncated",
                "event_log_state_records_by_has_invalid_records",
                "event_log_state_records_by_tail_has_records",
                "event_log_state_records_by_tail_has_omitted_records",
                "event_log_state_records_by_tail_empty_due_to_limit",
            ), "event_log_state_record_count",
        ),
        "release_artifacts": status_indexes.api_collection_record(
            "release_artifacts", release.get("artifacts") or [], "path", (
                "artifacts_by_release_path", "artifacts_by_name", "artifacts_by_sha256",
                "artifacts_by_payload_preset", "artifacts_by_tool", "artifacts_by_feature",
                "artifacts_by_compatibility", "artifacts_by_source", "artifacts_by_tuple_path",
                "artifacts_by_tuple_payload_preset",
                "artifacts_by_device_alias",
                "artifacts_by_tool_payload_preset", "artifacts_by_device_payload_preset",
                "artifacts_by_feature_payload_preset",
                "artifacts_by_provider_tool", "artifacts_by_provider_status",
                "artifacts_by_doom_wad_filename", "artifacts_by_doom_wad_sha256",
                "artifacts_by_command_queue_enabled", "artifacts_by_command_queue_execution_supported",
                "artifacts_by_command_queue_operator_supplied_command_execution",
            ), "release_artifact_count",
        ),
        "release_recommendations": status_indexes.api_collection_record(
            "release_recommendations", release.get("recommendation_records") or [], "id", (
                "recommendations_by_id", "recommendations_by_scope", "recommendations_by_artifact",
                "recommendations_by_payload_preset", "recommendations_by_compatibility",
            ), "release_recommendation_count",
        ),
        "release_artifact_workflow_actions": status_indexes.api_collection_record(
            "release_artifact_workflow_actions", release_artifact_workflow_actions, "id", (
                "release_artifact_workflow_actions_by_id",
                "release_artifact_workflow_actions_by_action_id",
                "release_artifact_workflow_actions_by_category",
                "release_artifact_workflow_actions_by_workflow",
                "release_artifact_workflow_actions_by_selector_kind",
                "release_artifact_workflow_actions_by_release_dir",
                "release_artifact_workflow_actions_by_release_name",
                "release_artifact_workflow_actions_by_release_present",
                "release_artifact_workflow_actions_by_release_valid",
                "release_artifact_workflow_actions_by_artifact_name",
                "release_artifact_workflow_actions_by_release_path",
                "release_artifact_workflow_actions_by_payload_preset",
                "release_artifact_workflow_actions_by_compatibility_label",
                "release_artifact_workflow_actions_by_recommendation_scope",
                "release_artifact_workflow_actions_by_writes_staged_files",
                "release_artifact_workflow_actions_by_available",
                "release_artifact_workflow_actions_by_requires_input",
                "release_artifact_workflow_actions_by_requires_confirmation",
                "release_artifact_workflow_actions_by_operator_action_state",
                "release_artifact_workflow_actions_by_operator_action_reason",
                "release_artifact_workflow_actions_by_can_run_from_curses_enter",
                "release_artifact_workflow_actions_by_curses_enter_action",
            ), "release_artifact_workflow_action_count",
        ),
        "release_licenses": status_indexes.api_collection_record(
            "release_licenses", release.get("release_license_records") or [], "project_license", (
                "release_license_records_by_project_license",
                "release_license_records_by_combined_gplv2_compatible",
                "release_license_records_by_corresponding_source_required",
                "release_license_records_by_corresponding_source_status",
                "release_license_records_by_package_license_audit",
                "release_license_records_by_component",
                "release_license_records_by_component_license",
                "release_license_records_by_notice_file",
                "release_license_records_by_evidence_source",
                "release_license_records_by_evidence_source_license",
            ), "release_license_count",
        ),
        "release_devices": status_indexes.api_collection_record(
            "release_devices", release.get("devices") or [], "name", (
                "devices_by_name", "devices_by_tuple_path", "devices_by_artifact",
            ), "release_device_count",
        ),
        "release_tuples": status_indexes.api_collection_record(
            "release_tuples", release.get("tuples") or [], "path", (
                "tuples_by_path", "tuples_by_artifact",
            ), "release_tuple_count",
        ),
        "release_state_records": status_indexes.api_collection_record(
            "release_state_records", release_state_records, "release_dir", (
                "release_state_records_by_release_dir",
                "release_state_records_by_present",
                "release_state_records_by_valid",
                "release_state_records_by_detection_source",
                "release_state_records_by_detection_reason",
                "release_state_records_by_explicit_release_dir",
                "release_state_records_by_marker_count",
            ), "release_state_record_count",
        ),
        "command_queue_commands": status_indexes.api_collection_record(
            "command_queue_commands", command_queue.get("commands") or [], "id", (
                "commands_by_id", "commands_by_status", "commands_by_command_sha256",
                "commands_by_target_id", "commands_by_created_at",
                "commands_by_delivered_at", "commands_by_result_received_at",
                "commands_by_result_source_path", "commands_by_timeout_sec",
                "commands_by_max_output_bytes", "commands_by_expire_sec",
                "commands_by_expires_at", "commands_by_expired",
                "commands_by_execution_decision",
                "commands_by_result_status",
                "commands_by_result_exit_code", "commands_by_result_output_exceeded",
                "commands_by_result_output_size_bucket",
                "commands_by_queue_policy_enabled", "commands_by_queue_policy_valid",
                "commands_by_queue_policy_execution_mode", "commands_by_queue_policy_allowed_commands",
                "commands_by_delivery_policy_enabled", "commands_by_delivery_policy_valid",
                "commands_by_delivery_policy_execution_mode",
                "commands_by_delivery_policy_delivery_supported",
                "commands_by_delivery_policy_result_upload_supported",
                "commands_by_delivery_policy_active_control_channel",
            ), "command_queue_total_count",
        ),
        "command_queue_workflow_actions": status_indexes.api_collection_record(
            "command_queue_workflow_actions", command_queue_workflow_actions, "id", (
                "command_queue_workflow_actions_by_id",
                "command_queue_workflow_actions_by_action_id",
                "command_queue_workflow_actions_by_category",
                "command_queue_workflow_actions_by_workflow",
                "command_queue_workflow_actions_by_actual",
                "command_queue_workflow_actions_by_target_filter_active",
                "command_queue_workflow_actions_by_policy_valid",
                "command_queue_workflow_actions_by_configured_for_polling",
                "command_queue_workflow_actions_by_poll_transport_supported",
                "command_queue_workflow_actions_by_live_polling_supported",
                "command_queue_workflow_actions_by_result_upload_supported",
                "command_queue_workflow_actions_by_execution_supported",
                "command_queue_workflow_actions_by_delivery_supported",
                "command_queue_workflow_actions_by_operator_queue_records_only",
                "command_queue_workflow_actions_by_target_mailbox_pending_target_count",
                "command_queue_workflow_actions_by_target_mailbox_pending_work_count",
                "command_queue_workflow_actions_by_target_mailbox_pending_poll_overdue_count",
                "command_queue_workflow_actions_by_fleet_target_count",
                "command_queue_workflow_actions_by_fleet_offline_target_count",
                "command_queue_workflow_actions_by_fleet_stale_target_count",
                "command_queue_workflow_actions_by_fleet_mailbox_pending_target_count",
                "command_queue_workflow_actions_by_fleet_mailbox_pending_work_count",
                "command_queue_workflow_actions_by_fleet_poll_overdue_target_count",
                "command_queue_workflow_actions_by_fleet_has_offline_targets",
                "command_queue_workflow_actions_by_fleet_has_stale_targets",
                "command_queue_workflow_actions_by_fleet_has_mailbox_pending_work",
                "command_queue_workflow_actions_by_fleet_has_poll_overdue_targets",
                "command_queue_workflow_actions_by_requires_input",
                "command_queue_workflow_actions_by_requires_confirmation",
                "command_queue_workflow_actions_by_queues_offline_work",
                "command_queue_workflow_actions_by_target_phone_home_required",
                "command_queue_workflow_actions_by_operator_action_state",
                "command_queue_workflow_actions_by_operator_action_reason",
                "command_queue_workflow_actions_by_can_run_from_curses_enter",
                "command_queue_workflow_actions_by_curses_enter_action",
            ), "command_queue_workflow_action_count",
        ),
        "command_queue_policy_records": status_indexes.api_collection_record(
            "command_queue_policy_records", command_queue_policy_records, "id", (
                "command_queue_policy_records_by_id",
                "command_queue_policy_records_by_enabled",
                "command_queue_policy_records_by_valid",
                "command_queue_policy_records_by_configured_for_polling",
                "command_queue_policy_records_by_execution_mode",
                "command_queue_policy_records_by_allowed_commands",
                "command_queue_policy_records_by_token_required",
                "command_queue_policy_records_by_token_configured",
                "command_queue_policy_records_by_safe_disabled_default",
                "command_queue_policy_records_by_poll_transport_supported",
                "command_queue_policy_records_by_live_polling_supported",
                "command_queue_policy_records_by_active_control_channel",
                "command_queue_policy_records_by_arbitrary_execution_allowed",
            ), "command_queue_policy_record_count",
        ),
        "command_queue_modes": status_indexes.api_collection_record(
            "command_queue_modes", command_queue.get("mode_records") or [], "mode", (
                "command_queue_modes_by_mode", "command_queue_modes_by_lifecycle",
                "command_queue_modes_by_requires_operator_host",
                "command_queue_modes_by_would_poll_if_configured",
                "command_queue_modes_by_live_supported",
                "command_queue_modes_by_live_transport_supported",
                "command_queue_modes_by_delivery_supported",
                "command_queue_modes_by_result_upload_supported",
                "command_queue_modes_by_execution_supported",
                "command_queue_modes_by_active_control_channel",
                "command_queue_modes_by_operator_supplied_command_execution",
            ), "command_queue_mode_count",
        ),
        "operator_console_workflows": status_indexes.api_collection_record(
            "operator_console_workflows", operator_console_workflows, "id", (
                "operator_console_workflows_by_id",
                "operator_console_workflows_by_workflow",
                "operator_console_workflows_by_group",
                "operator_console_workflows_by_primary_collection",
                "operator_console_workflows_by_target_scoped",
                "operator_console_workflows_by_multi_target",
                "operator_console_workflows_by_offline_queue_supported",
                "operator_console_workflows_by_has_records",
                "operator_console_workflows_by_has_actions",
                "operator_console_workflows_by_has_enter_runnable_actions",
                "operator_console_workflows_by_has_pending_work",
                "operator_console_workflows_by_has_warnings",
                "operator_console_workflows_by_fleet_target_count",
                "operator_console_workflows_by_fleet_offline_target_count",
                "operator_console_workflows_by_fleet_stale_target_count",
                "operator_console_workflows_by_fleet_mailbox_pending_target_count",
                "operator_console_workflows_by_fleet_mailbox_pending_work_count",
                "operator_console_workflows_by_fleet_poll_overdue_target_count",
                "operator_console_workflows_by_fleet_has_offline_targets",
                "operator_console_workflows_by_fleet_has_stale_targets",
                "operator_console_workflows_by_fleet_has_mailbox_pending_work",
                "operator_console_workflows_by_fleet_has_poll_overdue_targets",
                "operator_console_workflows_by_operator_action_state",
                "operator_console_workflows_by_operator_action_reason",
                "operator_console_workflows_by_tui_shortcut",
                "operator_console_workflows_by_line_mode_action",
            ), "operator_console_workflow_count",
        ),
        "workbench_actions": status_indexes.api_collection_record(
            "workbench_actions", workbench_actions, "id", (
                "workbench_actions_by_id", "workbench_actions_by_category",
                "workbench_actions_by_script", "workbench_actions_by_background_supported",
                "workbench_actions_by_long_running", "workbench_actions_by_writes_config",
                "workbench_actions_by_runs_build", "workbench_actions_by_requires_confirmation",
                "workbench_actions_by_execution_default",
                "workbench_actions_by_target_execution",
                "workbench_actions_by_event", "workbench_actions_by_config_path",
                "workbench_actions_by_foreground_runnable",
                "workbench_actions_by_dry_run_supported",
                "workbench_actions_by_has_placeholder",
                "workbench_actions_by_has_run_command",
                "workbench_actions_by_has_dry_run_command",
                "workbench_actions_by_has_start_job_command",
                "workbench_actions_by_operator_action_state",
                "workbench_actions_by_operator_action_reason",
                "workbench_actions_by_can_run_from_curses_enter",
                "workbench_actions_by_curses_enter_action",
            ), "workbench_action_count",
        ),
        "operator_daemon_workflow_actions": status_indexes.api_collection_record(
            "operator_daemon_workflow_actions", operator_daemon_workflow_actions, "id", (
                "operator_daemon_workflow_actions_by_id",
                "operator_daemon_workflow_actions_by_action_id",
                "operator_daemon_workflow_actions_by_workbench_action_id",
                "operator_daemon_workflow_actions_by_category",
                "operator_daemon_workflow_actions_by_workflow",
                "operator_daemon_workflow_actions_by_daemon_status",
                "operator_daemon_workflow_actions_by_daemon_attached",
                "operator_daemon_workflow_actions_by_control_state_exists",
                "operator_daemon_workflow_actions_by_command_queue_file_exists",
                "operator_daemon_workflow_actions_by_command_queue_command_count",
                "operator_daemon_workflow_actions_by_command_queue_queued_count",
                "operator_daemon_workflow_actions_by_command_queue_result_received_count",
                "operator_daemon_workflow_actions_by_command_queue_target_count",
                "operator_daemon_workflow_actions_by_targets_file_exists",
                "operator_daemon_workflow_actions_by_target_count",
                "operator_daemon_workflow_actions_by_target_registry_record_count",
                "operator_daemon_workflow_actions_by_fleet_target_count",
                "operator_daemon_workflow_actions_by_fleet_offline_target_count",
                "operator_daemon_workflow_actions_by_fleet_stale_target_count",
                "operator_daemon_workflow_actions_by_fleet_mailbox_pending_target_count",
                "operator_daemon_workflow_actions_by_fleet_mailbox_pending_work_count",
                "operator_daemon_workflow_actions_by_fleet_poll_overdue_target_count",
                "operator_daemon_workflow_actions_by_fleet_has_offline_targets",
                "operator_daemon_workflow_actions_by_fleet_has_stale_targets",
                "operator_daemon_workflow_actions_by_fleet_has_mailbox_pending_work",
                "operator_daemon_workflow_actions_by_fleet_has_poll_overdue_targets",
                "operator_daemon_workflow_actions_by_staged_file_count",
                "operator_daemon_workflow_actions_by_workbench_job_count",
                "operator_daemon_workflow_actions_by_background_supported",
                "operator_daemon_workflow_actions_by_foreground_runnable",
                "operator_daemon_workflow_actions_by_dry_run_supported",
                "operator_daemon_workflow_actions_by_requires_confirmation",
                "operator_daemon_workflow_actions_by_writes_config",
                "operator_daemon_workflow_actions_by_systemd_user_action",
                "operator_daemon_workflow_actions_by_operator_action_state",
                "operator_daemon_workflow_actions_by_operator_action_reason",
                "operator_daemon_workflow_actions_by_can_run_from_curses_enter",
                "operator_daemon_workflow_actions_by_curses_enter_action",
            ), "operator_daemon_workflow_action_count",
        ),
        "workbench_config_fields": status_indexes.api_collection_record(
            "workbench_config_fields", workbench_config_fields, "key", (
                "workbench_config_fields_by_key", "workbench_config_fields_by_category",
                "workbench_config_fields_by_configured", "workbench_config_fields_by_fixed_options",
                "workbench_config_fields_by_writes_config", "workbench_config_fields_by_target_execution",
                "workbench_config_fields_by_source_format",
                "workbench_config_fields_by_has_set_command", "workbench_config_fields_by_set_command_kind",
                "workbench_config_fields_by_safety_boundary", "workbench_config_fields_by_control_like",
                "workbench_config_fields_by_reverse_access_related", "workbench_config_fields_by_command_queue_related",
                "workbench_config_fields_by_requires_explicit_operator_choice",
            ), "workbench_config_field_count",
        ),
        "workbench_jobs": status_indexes.api_collection_record(
            "workbench_jobs", workbench_jobs, "id", (
                "workbench_jobs_by_id", "workbench_jobs_by_action",
                "workbench_jobs_by_state", "workbench_jobs_by_effective_state",
                "workbench_jobs_by_category", "workbench_jobs_by_script",
                "workbench_jobs_by_pid", "workbench_jobs_by_pid_managed",
                "workbench_jobs_by_cancel_supported", "workbench_jobs_by_log_exists",
                "workbench_jobs_by_exit_status_known",
                "workbench_jobs_by_started_at_known", "workbench_jobs_by_finished_at_known",
                "workbench_jobs_by_duration_known", "workbench_jobs_by_elapsed_known",
                "workbench_jobs_by_background_supported", "workbench_jobs_by_long_running",
                "workbench_jobs_by_outcome", "workbench_jobs_by_exit_status",
                "workbench_jobs_by_last_output_tail_truncated",
            ), "workbench_job_count",
        ),
    }
    api_resources = status_indexes.api_resource_records(api_collections)
    api_resource_indexes = status_indexes.api_resource_record_indexes(api_resources)
    return {
        "schema": 1,
        "generated_at": session_state_module.utc_now(),
        "api": _build_status_api_doc(
            cfg,
            target_filter_id,
            selected_target,
            api_resources,
        ),
        "target_filter": _build_target_filter_status_doc(
            target_filter_id,
            selected_target,
            target_filter_record,
            unfiltered_counts,
            targets=targets,
            uploads=uploads,
            fetches=fetches,
            sessions=sessions,
            events=events,
            command_queue=command_queue,
            staged_records=staged_records,
            staged_file_workflow_actions=staged_file_workflow_actions,
            target_command_records=target_command_records,
            target_phone_home_records=target_phone_home_records,
        ),
        "target_filter_records": target_filter_records,
        **target_filter_index_maps,
        "target_attribution": target_attribution,
        "target_attribution_records": target_attribution_records,
        **target_attribution_index_maps,
        "GRIT_RSHELL_SESSION_POLICY": rshell_session_policy,
        "rshell_session_policy_records": rshell_session_policy_records,
        **rshell_session_policy_index_maps,
        "api_resources": api_resources,
        **api_resource_indexes,
        "api_collections": api_collections,
        "operator_console_workflows": operator_console_workflows,
        **operator_console_workflow_index_maps,
        "operator_session_dir": str(operator_dir),
        "state_file": str(session_state_module.state_file_path(cfg)),
        "staged_files": str(staged_files.staged_file_path(cfg)),
        "command_queue_file": str(command_queue_module.command_queue_path(cfg)),
        "command_copy_file": str(command_copy_module.command_copy_path(cfg)),
        "bridge_profiles_file": str(bridge_routes.bridge_profiles_path(cfg)),
        "command_copy": command_copy,
        "command_copy_records": command_copy_records,
        **command_copy_record_indexes,
        "command_copy_state_records": command_copy_state_records,
        **command_copy_state_index_maps,
        "workbench_jobs_file": str(workbench_jobs_path(cfg)),
        "targets_file": str(target_records.targets_path(cfg)),
        "workbench_jobs_state": workbench_jobs_state,
        "workbench_jobs_state_records": workbench_jobs_state_records,
        **workbench_jobs_state_index_maps,
        "operator_state_records": operator_state_records_list,
        **operator_state_index_maps,
        "build_config": str(build_config_path(cfg)),
        "event_log": str(event_log_path),
        "session_root": session_root,
        "tls_cert": str(cfg.get("tls_cert", "")),
        "tls_key": str(cfg.get("tls_key", "")),
        "paths": paths,
        "path_status": path_status,
        "path_status_records": path_status_records,
        **path_status_indexes,
        "path_status_by_has_warnings": path_status_by_has_warnings,
        "path_status_by_warning_type": path_status_by_warning_type,
        "browser_paths": browser_paths,
        **browser_path_index_maps,
        "browser_paths_by_has_warnings": browser_paths_by_has_warnings,
        "browser_paths_by_warning_type": browser_paths_by_warning_type,
        "browser_path_summary": browser_summary,
        "server_state": server_state,
        "server_state_records": server_state_records,
        **server_state_index_maps,
        "staged_files_state": staged_files_state,
        "staged_files_state_records": staged_files_state_records,
        **staged_files_state_index_maps,
        "command_queue_state": command_queue_state,
        "command_queue_state_records": command_queue_state_records,
        **command_queue_state_index_maps,
        "service_manager": service_manager,
        "service_manager_state_records": service_manager_state_records,
        **service_manager_state_index_maps,
        "service_manager_resources": service_manager_resources,
        **service_manager_resource_index_maps,
        "bridge_profiles": bridge_profiles,
        **bridge_profile_index_maps,
        "bridge_profile_workflow_actions": bridge_profile_workflow_actions,
        **bridge_profile_workflow_action_index_maps,
        "bridge_hop_records": bridge_hop_records,
        **bridge_hop_index_maps,
        "services": services,
        "services_by_name": services_by_name,
        **service_index_maps,
        "services_by_has_warnings": services_by_has_warnings,
        "services_by_warning_type": services_by_warning_type,
        "service_workflow_actions": service_workflow_actions,
        **service_workflow_action_index_maps,
        "probe_workflow_actions": probe_workflow_actions,
        **probe_workflow_action_index_maps,
        "ports": ports,
        **port_index_maps,
        "ports_by_has_warnings": ports_by_has_warnings,
        "ports_by_warning_type": ports_by_warning_type,
        "summary": summary,
        "warnings": warnings,
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
        "warning_stats": warning_summary,
        "local_ips": ips,
        "selected_local_ip": selected_local_ip,
        "operator_network_records": operator_network_records,
        **operator_network_index_maps,
        "operator_network_state_records": operator_network_state_records,
        **operator_network_state_index_maps,
        "target_commands": [rec["command"] for rec in target_command_records],
        "target_command_records": target_command_records,
        "target_command_summary": target_command_summary,
        "target_command_state_records": target_command_state_records,
        **target_command_state_index_maps,
        "target_workflow_actions": target_workflow_actions,
        **target_workflow_action_index_maps,
        **target_command_index_maps,
        "targets": targets,
        "target_summary": target_summary,
        "target_registry_state_records": target_registry_state_records,
        **target_registry_state_index_maps,
        **target_index_maps,
        "target_mailbox_records": target_mailbox_records,
        **target_mailbox_index_maps,
        "target_phone_home_records": target_phone_home_records,
        **target_phone_home_index_maps,
        "staged": staged,
        "staged_records": staged_records,
        "staged_by_request": staged_by_request,
        "staged_by_kind": staged_by_kind,
        "staged_by_sha256": staged_by_sha256,
        "staged_by_target_id": staged_by_target_id,
        "staged_by_source_path": staged_by_source_path,
        "staged_by_fetch_command": staged_by_fetch_command,
        "staged_by_fetch_command_force": staged_by_fetch_command_force,
        "staged_by_source_exists": staged_by_source_exists,
        "staged_by_kind_source_exists": staged_by_kind_source_exists,
        "staged_file_workflow_actions": staged_file_workflow_actions,
        **staged_file_workflow_action_index_maps,
        "file_service_workflow_actions": file_service_workflow_actions,
        **file_service_workflow_action_index_maps,
        "target_file_transfer_records": target_file_transfer_records,
        **target_file_transfer_index_maps,
        "target_activity_records": target_activity_records,
        **target_activity_index_maps,
        "uploads": uploads,
        "uploads_by_session": records_by_session(uploads),
        **upload_index_maps,
        "fetches": fetches,
        "fetches_by_session": records_by_session(fetches),
        **fetch_index_maps,
        "sessions": sessions,
        "session_root_state": session_root_state,
        "session_root_state_records": session_root_state_records,
        **session_root_state_index_maps,
        **session_index_maps,
        "events": events,
        **event_index_maps,
        "event_log_state": event_log_state,
        "event_log_state_records": event_log_state_records,
        **event_log_state_index_maps,
        "event_log_stats": {
            key: value for key, value in event_stats.items() if key != "tail"
        },
        "release_state": release_state,
        "release_state_records": release_state_records,
        **release_state_index_maps,
        "release": release,
        "release_artifact_workflow_actions": release_artifact_workflow_actions,
        **release_artifact_workflow_action_index_maps,
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
        "command_queue": command_queue,
        "command_queue_workflow_actions": command_queue_workflow_actions,
        **command_queue_workflow_action_index_maps,
        "command_queue_policy_records": command_queue_policy_records,
        **command_queue_policy_index_maps,
        **command_queue_index_maps,
        "command_queue_mode_records": command_queue_mode_records,
        **command_queue_mode_index_maps,
        "workbench_config_fields": workbench_config_fields,
        **workbench_config_field_index_maps,
        "workbench_actions": workbench_actions,
        **workbench_action_index_maps,
        "operator_daemon_workflow_actions": operator_daemon_workflow_actions,
        **operator_daemon_workflow_action_index_maps,
        "workbench_jobs": workbench_jobs,
        **workbench_job_index_maps,
    }
