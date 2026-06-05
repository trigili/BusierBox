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
import gritlib.status_api_collections as status_api_collections
import gritlib.status_api_payload as status_api_payload
import gritlib.status_indexes as status_indexes
import gritlib.status_operator_contexts as status_operator_contexts
import gritlib.status_payload_sections as status_payload_sections
import gritlib.status_summary_updates as status_summary_updates
import gritlib.status_target_filter as status_target_filter
import gritlib.status_transfer_contexts as status_transfer_contexts
import gritlib.status_warnings as status_warnings
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




























































































































































def _status_foundation_staged_fields(staged_context):
    return {
        "staged_context": staged_context,
        "staged_raw": staged_context["staged_raw"],
        "unfiltered_staged_raw": staged_context["unfiltered_staged_raw"],
        "staged": staged_context["staged"],
        "staged_records": staged_context["staged_records"],
        "unfiltered_staged_count": staged_context["unfiltered_staged_count"],
        "staged_by_request": staged_context["staged_by_request"],
        "staged_by_kind": staged_context["staged_by_kind"],
        "staged_by_sha256": staged_context["staged_by_sha256"],
        "staged_by_target_id": staged_context["staged_by_target_id"],
        "staged_by_source_path": staged_context["staged_by_source_path"],
        "staged_by_fetch_command": staged_context["staged_by_fetch_command"],
        "staged_by_fetch_command_force": staged_context[
            "staged_by_fetch_command_force"
        ],
        "staged_by_source_exists": staged_context["staged_by_source_exists"],
        "staged_by_kind_source_exists": staged_context[
            "staged_by_kind_source_exists"
        ],
    }


def _status_foundation_operator_network_fields(operator_network_context):
    return {
        "operator_network_context": operator_network_context,
        "ips": operator_network_context["ips"],
        "operator_network": operator_network_context["operator_network"],
        "selected_local_ip": operator_network_context["selected_local_ip"],
        "operator_network_records": operator_network_context[
            "operator_network_records"
        ],
        "operator_network_index_maps": operator_network_context[
            "operator_network_index_maps"
        ],
        "operator_network_state_record": operator_network_context[
            "operator_network_state_record"
        ],
        "operator_network_state_records": operator_network_context[
            "operator_network_state_records"
        ],
        "operator_network_state_index_maps": operator_network_context[
            "operator_network_state_index_maps"
        ],
        "operator_dir": operator_network_context["operator_dir"],
        "event_log_path": operator_network_context["event_log_path"],
        "session_root": operator_network_context["session_root"],
    }


def _status_foundation_service_fields(service_context):
    return {
        "service_context": service_context,
        "services": service_context["services"],
        "service_manager": service_context["service_manager"],
        "service_manager_status_doc": service_context[
            "service_manager_status_doc"
        ],
        "service_manager_resources": service_context["service_manager_resources"],
        "service_manager_resource_index_maps": service_context[
            "service_manager_resource_index_maps"
        ],
        "service_manager_state_record": service_context[
            "service_manager_state_record"
        ],
        "service_manager_state_records": service_context[
            "service_manager_state_records"
        ],
        "service_manager_state_index_maps": service_context[
            "service_manager_state_index_maps"
        ],
        "ports": service_context["ports"],
        "port_index_maps": service_context["port_index_maps"],
    }


def _status_foundation_event_source_fields(event_source_context):
    return {
        "event_source_context": event_source_context,
        "all_event_records": event_source_context["all_event_records"],
        "all_target_phone_home_records": event_source_context[
            "all_target_phone_home_records"
        ],
    }


def _status_foundation_target_fields(target_context):
    target_index_maps = target_context["target_index_maps"]
    return {
        "target_context": target_context,
        "uploads": target_context["uploads"],
        "fetches": target_context["fetches"],
        "targets": target_context["targets"],
        "unfiltered_counts": target_context["unfiltered_counts"],
        "target_index_maps": target_index_maps,
        "targets_by_id": target_index_maps["targets_by_id"],
        "target_summary": target_context["target_summary"],
        "selected_target": target_context["selected_target"],
        "target_registry_state_record": target_context[
            "target_registry_state_record"
        ],
        "target_registry_state_records": target_context[
            "target_registry_state_records"
        ],
        "target_registry_state_index_maps": target_context[
            "target_registry_state_index_maps"
        ],
        "target_registry_summary": target_context["target_registry_summary"],
    }


def _build_status_foundation_context(cfg, *, target_filter_id):
    staged_context = _build_staged_file_status_context(cfg, target_filter_id)
    operator_network_context = _build_operator_network_status_context(cfg)
    service_context = _build_service_status_context(cfg)
    event_source_context = _build_event_source_status_context(cfg)
    target_context = _build_target_registry_context(
        cfg,
        target_filter_id=target_filter_id,
        all_target_phone_home_records=event_source_context[
            "all_target_phone_home_records"
        ],
        unfiltered_staged_count=staged_context["unfiltered_staged_count"],
    )
    return {
        **_status_foundation_staged_fields(staged_context),
        **_status_foundation_operator_network_fields(operator_network_context),
        **_status_foundation_service_fields(service_context),
        **_status_foundation_event_source_fields(event_source_context),
        **_status_foundation_target_fields(target_context),
    }


def _status_activity_bridge_fields(bridge_profile_context):
    return {
        "bridge_profile_context": bridge_profile_context,
        "bridge_profiles": bridge_profile_context["bridge_profiles"],
        "bridge_profile_index_maps": bridge_profile_context[
            "bridge_profile_index_maps"
        ],
        "bridge_hop_records": bridge_profile_context["bridge_hop_records"],
        "bridge_hop_index_maps": bridge_profile_context["bridge_hop_index_maps"],
        "bridge_profile_workflow_actions": bridge_profile_context[
            "bridge_profile_workflow_actions"
        ],
        "bridge_profile_workflow_action_index_maps": bridge_profile_context[
            "bridge_profile_workflow_action_index_maps"
        ],
    }


def _status_activity_staged_workflow_fields(staged_file_workflow_context):
    return {
        "staged_file_workflow_context": staged_file_workflow_context,
        "staged_file_workflow_actions": staged_file_workflow_context[
            "staged_file_workflow_actions"
        ],
        "staged_file_workflow_action_index_maps": staged_file_workflow_context[
            "staged_file_workflow_action_index_maps"
        ],
    }


def _status_activity_session_fields(session_context, target_filter_session_ids):
    return {
        "session_context": session_context,
        "sessions": session_context["sessions"],
        "target_filter_session_ids": target_filter_session_ids,
        "session_root_state": session_context["session_root_state"],
        "session_root_state_records": session_context["session_root_state_records"],
        "session_root_state_index_maps": session_context[
            "session_root_state_index_maps"
        ],
        "session_index_maps": session_context["session_index_maps"],
    }


def _status_activity_event_fields(event_context):
    return {
        "event_context": event_context,
        "event_stats": event_context["event_stats"],
        "event_log_state": event_context["event_log_state"],
        "event_log_state_records": event_context["event_log_state_records"],
        "event_log_state_index_maps": event_context["event_log_state_index_maps"],
        "events": event_context["events"],
        "event_index_maps": event_context["event_index_maps"],
        "event_summary_stats": event_context["event_summary_stats"],
    }


def _status_activity_command_queue_fields(command_queue_context):
    return {
        "command_queue_context": command_queue_context,
        "command_queue": command_queue_context["command_queue"],
        "command_queue_policy_records": command_queue_context[
            "command_queue_policy_records"
        ],
        "command_queue_policy_index_maps": command_queue_context[
            "command_queue_policy_index_maps"
        ],
        "command_queue_index_maps": command_queue_context["command_queue_index_maps"],
        "command_queue_mode_records": command_queue_context[
            "command_queue_mode_records"
        ],
        "command_queue_mode_index_maps": command_queue_context[
            "command_queue_mode_index_maps"
        ],
    }


def _status_activity_target_activity_fields(target_activity_context):
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
    }


def _status_activity_release_fields(release_context_doc):
    return {
        "release_context_doc": release_context_doc,
        "release": release_context_doc["release"],
        "release_state": release_context_doc["release_state"],
        "release_state_records": release_context_doc["release_state_records"],
        "release_state_index_maps": release_context_doc["release_state_index_maps"],
        "release_artifact_workflow_actions": release_context_doc[
            "release_artifact_workflow_actions"
        ],
        "release_artifact_workflow_action_index_maps": release_context_doc[
            "release_artifact_workflow_action_index_maps"
        ],
    }


def _status_activity_rshell_policy_fields(rshell_session_policy_context):
    return {
        "rshell_session_policy_context": rshell_session_policy_context,
        "rshell_session_policy": rshell_session_policy_context[
            "rshell_session_policy"
        ],
        "rshell_session_policy_record_item": rshell_session_policy_context[
            "rshell_session_policy_record_item"
        ],
        "rshell_session_policy_records": rshell_session_policy_context[
            "rshell_session_policy_records"
        ],
        "rshell_session_policy_index_maps": rshell_session_policy_context[
            "rshell_session_policy_index_maps"
        ],
    }


def _status_activity_workbench_config_fields(workbench_config_context):
    return {
        "workbench_config_context": workbench_config_context,
        "workbench_config_fields": workbench_config_context[
            "workbench_config_fields"
        ],
        "workbench_config_field_index_maps": workbench_config_context[
            "workbench_config_field_index_maps"
        ],
    }


def _status_activity_workflow_fields(workflow_context):
    return {
        "workflow_context": workflow_context,
        "workbench_action_context": workflow_context["workbench_action_context"],
        "workbench_actions": workflow_context["workbench_actions"],
        "workbench_action_index_maps": workflow_context[
            "workbench_action_index_maps"
        ],
        "operator_daemon_workflow_actions": workflow_context[
            "operator_daemon_workflow_actions"
        ],
        "operator_daemon_workflow_action_index_maps": workflow_context[
            "operator_daemon_workflow_action_index_maps"
        ],
        "target_workflow_actions": workflow_context["target_workflow_actions"],
        "target_workflow_action_index_maps": workflow_context[
            "target_workflow_action_index_maps"
        ],
        "workbench_job_context": workflow_context["workbench_job_context"],
        "workbench_jobs": workflow_context["workbench_jobs"],
        "workbench_job_index_maps": workflow_context["workbench_job_index_maps"],
    }


def _status_activity_target_command_fields(target_command_context):
    return {
        "target_command_context": target_command_context,
        "target_command_records": target_command_context["target_command_records"],
        "target_command_index_maps": target_command_context[
            "target_command_index_maps"
        ],
        "target_command_summary": target_command_context["target_command_summary"],
        "target_command_state_record": target_command_context[
            "target_command_state_record"
        ],
        "target_command_state_records": target_command_context[
            "target_command_state_records"
        ],
        "target_command_state_index_maps": target_command_context[
            "target_command_state_index_maps"
        ],
    }


def _status_activity_target_filter_fields(target_filter_context):
    return {
        "target_filter_context": target_filter_context,
        "target_filter_record": target_filter_context["target_filter_record"],
        "target_filter_records": target_filter_context["target_filter_records"],
        "target_filter_index_maps": target_filter_context[
            "target_filter_index_maps"
        ],
    }


def _build_status_session_event_activity_context(
    cfg,
    *,
    event_limit,
    target_filter_id,
    foundation_context,
    unfiltered_counts,
    command_queue,
):
    session_context = _build_session_status_context(
        cfg,
        target_filter_id=target_filter_id,
    )
    unfiltered_counts["sessions"] = session_context["unfiltered_count"]
    target_filter_session_ids = session_context["target_filter_session_ids"]
    reconcile_workbench_job_completion_events(cfg)
    event_context = _build_event_status_context(
        cfg,
        event_limit,
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    unfiltered_counts["event_tail"] = event_context["unfiltered_tail_count"]
    target_activity_context = _build_target_activity_status_context(
        command_queue,
        foundation_context["targets_by_id"],
        foundation_context["all_event_records"],
        target_filter_id=target_filter_id,
        target_filter_session_ids=target_filter_session_ids,
    )
    return {
        "session_context": session_context,
        "target_filter_session_ids": target_filter_session_ids,
        "event_context": event_context,
        "target_activity_context": target_activity_context,
    }


def _build_status_target_command_filter_context(
    cfg,
    *,
    target_filter_id,
    foundation_context,
    unfiltered_counts,
    session_context,
    event_context,
    command_queue,
    target_activity_context,
):
    f = foundation_context
    target_command_context = _build_target_command_status_context(
        cfg,
        staged_raw=f["staged_raw"],
        unfiltered_staged_raw=f["unfiltered_staged_raw"],
        target_filter_id=target_filter_id,
    )
    unfiltered_counts["target_command_records"] = target_command_context[
        "unfiltered_count"
    ]
    target_filter_context = status_target_filter.build_target_filter_status_context(
        target_filter_id,
        f["selected_target"],
        unfiltered_counts,
        targets=f["targets"],
        uploads=f["uploads"],
        fetches=f["fetches"],
        staged_records=f["staged_records"],
        sessions=session_context["sessions"],
        events=event_context["events"],
        command_queue=command_queue,
        target_command_summary=target_command_context["target_command_summary"],
        target_phone_home_records=target_activity_context[
            "target_phone_home_records"
        ],
        target_mailbox_records=target_activity_context["target_mailbox_records"],
    )
    return {
        "target_command_context": target_command_context,
        "target_filter_context": target_filter_context,
    }


def _build_status_activity_base_contexts(
    cfg,
    *,
    event_limit,
    target_filter_id,
    foundation_context,
):
    f = foundation_context
    bridge_profile_context = _build_bridge_profile_status_context(
        cfg, f["targets"]
    )
    staged_file_workflow_context = _build_staged_file_workflow_status_context(
        cfg,
        f["staged_records"],
        f["targets"],
    )
    command_queue_context = _build_command_queue_status_context(cfg)
    session_event_activity_context = _build_status_session_event_activity_context(
        cfg,
        event_limit=event_limit,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
        unfiltered_counts=f["unfiltered_counts"],
        command_queue=command_queue_context["command_queue"],
    )
    return {
        "bridge_profile_context": bridge_profile_context,
        "staged_file_workflow_context": staged_file_workflow_context,
        "command_queue_context": command_queue_context,
        "session_event_activity_context": session_event_activity_context,
    }


def _build_status_activity_workbench_contexts(cfg, targets, bridge_profiles):
    return {
        "release_context_doc": _build_release_status_context(cfg),
        "rshell_session_policy_context": (
            _build_rshell_session_policy_status_context(cfg)
        ),
        "workbench_config_context": _build_workbench_config_status_context(cfg),
        "workflow_context": _build_workbench_workflow_status_context(
            cfg,
            targets,
            bridge_profiles,
        ),
    }


def _build_status_activity_queue_context(
    cfg,
    *,
    event_limit,
    target_filter_id,
    foundation_context,
):
    f = foundation_context
    base_contexts = _build_status_activity_base_contexts(
        cfg,
        event_limit=event_limit,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
    )
    bridge_profile_context = base_contexts["bridge_profile_context"]
    bridge_profiles = bridge_profile_context["bridge_profiles"]
    staged_file_workflow_context = base_contexts["staged_file_workflow_context"]
    command_queue_context = base_contexts["command_queue_context"]
    command_queue = command_queue_context["command_queue"]
    session_event_activity_context = base_contexts["session_event_activity_context"]
    session_context = session_event_activity_context["session_context"]
    target_filter_session_ids = session_event_activity_context[
        "target_filter_session_ids"
    ]
    event_context = session_event_activity_context["event_context"]
    target_activity_context = session_event_activity_context[
        "target_activity_context"
    ]
    workbench_contexts = _build_status_activity_workbench_contexts(
        cfg, f["targets"], bridge_profiles
    )
    release_context_doc = workbench_contexts["release_context_doc"]
    rshell_session_policy_context = workbench_contexts[
        "rshell_session_policy_context"
    ]
    workbench_config_context = workbench_contexts["workbench_config_context"]
    workflow_context = workbench_contexts["workflow_context"]
    target_command_filter_context = _build_status_target_command_filter_context(
        cfg,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
        unfiltered_counts=f["unfiltered_counts"],
        session_context=session_context,
        event_context=event_context,
        command_queue=command_queue,
        target_activity_context=target_activity_context,
    )
    target_command_context = target_command_filter_context["target_command_context"]
    target_filter_context = target_command_filter_context["target_filter_context"]
    return {
        **_status_activity_bridge_fields(bridge_profile_context),
        **_status_activity_staged_workflow_fields(staged_file_workflow_context),
        **_status_activity_session_fields(
            session_context, target_filter_session_ids
        ),
        **_status_activity_event_fields(event_context),
        **_status_activity_command_queue_fields(command_queue_context),
        **_status_activity_target_activity_fields(target_activity_context),
        **_status_activity_release_fields(release_context_doc),
        **_status_activity_rshell_policy_fields(rshell_session_policy_context),
        **_status_activity_workbench_config_fields(workbench_config_context),
        **_status_activity_workflow_fields(workflow_context),
        **_status_activity_target_command_fields(target_command_context),
        **_status_activity_target_filter_fields(target_filter_context),
    }













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


def _build_status_tail_operator_path_context(cfg, foundation_context, activity_queue_context):
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


def _build_status_tail_queue_workflow_context(cfg, foundation_context, activity_queue_context, operator_path_context):
    return _build_command_queue_workflow_status_context(
        cfg,
        activity_queue_context["command_queue"],
        activity_queue_context["target_mailbox_records"],
        operator_path_context["services_by_name"].get("command-queue") or {},
        foundation_context["targets"],
    )


def _build_status_tail_service_probe_contexts(cfg, foundation_context, operator_path_context):
    service_probe_workflow_context = _build_service_probe_workflow_status_context(
        cfg,
        foundation_context["services"],
        operator_path_context["services_by_name"],
        foundation_context["targets"],
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
    return _build_operator_console_workflow_status_context(
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


def _build_status_tail_context(
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


def _apply_status_summary_updates(
    summary,
    *,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
    tail_context,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    tc = tail_context
    summary.update(status_summary_updates.build_status_summary_updates(
        path_context=tc["path_context"],
        bridge_profile_context=aq["bridge_profile_context"],
        path_warning_context=tc["path_warning_context"],
        operator_state_file_summary_doc=tc["operator_state_file_summary_doc"],
        operator_state_summary=tc["operator_state_summary"],
        staged_file_workflow_context=aq["staged_file_workflow_context"],
        services=f["services"],
        service_manager=f["service_manager"],
        service_manager_status_doc=f["service_manager_status_doc"],
        ports=f["ports"],
        warning_summary_context=tc["warning_summary_context"],
        uploads=f["uploads"],
        fetches=f["fetches"],
        target_attribution=ta["target_attribution"],
        target_file_transfer_records=ta["target_file_transfer_records"],
        file_service_workflow_context=ta["file_service_workflow_context"],
        target_activity_feed_context=ta["target_activity_feed_context"],
        target_summary=f["target_summary"],
        target_registry_summary=f["target_registry_summary"],
        target_filter_context=aq["target_filter_context"],
        target_attribution_context=ta["target_attribution_context"],
        sessions=aq["sessions"],
        session_root_state=aq["session_root_state"],
        session_root_state_records=aq["session_root_state_records"],
        target_command_summary=aq["target_command_summary"],
        target_command_state_record=aq["target_command_state_record"],
        target_command_state_records=aq["target_command_state_records"],
        rshell_session_policy_record_item=aq["rshell_session_policy_record_item"],
        rshell_session_policy_records=aq["rshell_session_policy_records"],
        workflow_context=aq["workflow_context"],
        event_stats=aq["event_stats"],
        event_log_state=aq["event_log_state"],
        event_log_state_records=aq["event_log_state_records"],
        events=aq["events"],
        event_summary_stats=aq["event_summary_stats"],
        operator_network_context=f["operator_network_context"],
        command_queue=aq["command_queue"],
        command_queue_policy_records=aq["command_queue_policy_records"],
        target_activity_context=aq["target_activity_context"],
        release_context_doc=aq["release_context_doc"],
        release_artifact_workflow_actions=aq["release_artifact_workflow_actions"],
        operator_console_workflow_context=tc["operator_console_workflow_context"],
        workbench_config_context=aq["workbench_config_context"],
        command_queue_workflow_context=tc["command_queue_workflow_context"],
        service_probe_workflow_context=tc["service_probe_workflow_context"],
    ))


def _build_status_api_collections_from_contexts(
    *,
    foundation_context,
    activity_queue_context,
    transfer_activity_context,
    tail_context,
):
    f = foundation_context
    aq = activity_queue_context
    ta = transfer_activity_context
    tc = tail_context
    return status_api_collections.build_status_api_collections(
        services=f["services"],
        service_workflow_actions=tc["service_workflow_actions"],
        probe_workflow_actions=tc["probe_workflow_actions"],
        service_manager_resources=f["service_manager_resources"],
        service_manager_state_records=f["service_manager_state_records"],
        bridge_profiles=aq["bridge_profiles"],
        bridge_profile_workflow_actions=aq["bridge_profile_workflow_actions"],
        bridge_hop_records=aq["bridge_hop_records"],
        ports=f["ports"],
        path_status_records=tc["path_status_records"],
        server_state_records=tc["server_state_records"],
        operator_state_records_list=tc["operator_state_records_list"],
        operator_network_records=f["operator_network_records"],
        operator_network_state_records=f["operator_network_state_records"],
        browser_paths=tc["browser_paths"],
        warnings=f["service_context"]["warnings"],
        target_command_records=aq["target_command_records"],
        target_workflow_actions=aq["target_workflow_actions"],
        target_command_state_records=aq["target_command_state_records"],
        rshell_session_policy_records=aq["rshell_session_policy_records"],
        targets=f["targets"],
        target_registry_state_records=f["target_registry_state_records"],
        target_filter_records=aq["target_filter_records"],
        target_attribution_records=ta["target_attribution_records"],
        staged_records=f["staged_records"],
        staged_file_workflow_actions=aq["staged_file_workflow_actions"],
        file_service_workflow_actions=ta["file_service_workflow_actions"],
        target_file_transfer_records=ta["target_file_transfer_records"],
        target_activity_records=ta["target_activity_records"],
        staged_files_state_records=tc["staged_files_state_records"],
        command_copy_records=tc["command_copy_records"],
        command_copy_state_records=tc["command_copy_state_records"],
        command_queue_state_records=tc["command_queue_state_records"],
        target_mailbox_records=aq["target_mailbox_records"],
        target_phone_home_records=aq["target_phone_home_records"],
        workbench_jobs_state_records=tc["workbench_jobs_state_records"],
        uploads=f["uploads"],
        fetches=f["fetches"],
        session_root_state_records=aq["session_root_state_records"],
        sessions=aq["sessions"],
        events=aq["events"],
        event_log_state_records=aq["event_log_state_records"],
        release=aq["release"],
        release_artifact_workflow_actions=aq["release_artifact_workflow_actions"],
        release_state_records=aq["release_state_records"],
        command_queue=aq["command_queue"],
        command_queue_workflow_actions=tc["command_queue_workflow_actions"],
        command_queue_policy_records=aq["command_queue_policy_records"],
        operator_console_workflows=tc["operator_console_workflows"],
        workbench_actions=aq["workbench_actions"],
        operator_daemon_workflow_actions=aq["operator_daemon_workflow_actions"],
        workbench_config_fields=aq["workbench_config_fields"],
        workbench_jobs=aq["workbench_jobs"],
    )














def _build_status_document_contexts(cfg):
    event_limit = int(cfg.get("_event_limit", 12))
    target_filter_id = target_records.configured_target_filter(cfg)
    foundation_context = _build_status_foundation_context(
        cfg, target_filter_id=target_filter_id
    )
    activity_queue_context = _build_status_activity_queue_context(
        cfg,
        event_limit=event_limit,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
    )
    transfer_activity_context = status_transfer_contexts.build_status_transfer_activity_context(
        cfg,
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
    )
    tail_context = _build_status_tail_context(
        cfg,
        target_filter_id=target_filter_id,
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
        transfer_activity_context=transfer_activity_context,
    )
    _apply_status_summary_updates(
        foundation_context["service_context"]["summary"],
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
        transfer_activity_context=transfer_activity_context,
        tail_context=tail_context,
    )
    api_collections = _build_status_api_collections_from_contexts(
        foundation_context=foundation_context,
        activity_queue_context=activity_queue_context,
        transfer_activity_context=transfer_activity_context,
        tail_context=tail_context,
    )
    return {
        "target_filter_id": target_filter_id,
        "foundation_context": foundation_context,
        "activity_queue_context": activity_queue_context,
        "transfer_activity_context": transfer_activity_context,
        "tail_context": tail_context,
        "api_collections": api_collections,
    }


def status_document(cfg):
    contexts = _build_status_document_contexts(cfg)
    target_filter_id = contexts["target_filter_id"]
    foundation_context = contexts["foundation_context"]
    activity_queue_context = contexts["activity_queue_context"]
    transfer_activity_context = contexts["transfer_activity_context"]
    tail_context = contexts["tail_context"]
    api_collections = contexts["api_collections"]
    summary = foundation_context["service_context"]["summary"]
    return {
        **status_payload_sections.build_status_api_payload_from_contexts(
            cfg=cfg,
            target_filter_id=target_filter_id,
            api_collections=api_collections,
            foundation_context=foundation_context,
            activity_queue_context=activity_queue_context,
            transfer_activity_context=transfer_activity_context,
            tail_context=tail_context,
        ),
        **status_payload_sections.build_status_operator_state_payload(
            cfg,
            foundation_context,
            tail_context,
        ),
        **status_payload_sections.build_status_path_service_payload(
            foundation_context=foundation_context,
            activity_queue_context=activity_queue_context,
            tail_context=tail_context,
        ),
        **status_payload_sections.build_status_warning_network_payload(
            summary,
            foundation_context,
            tail_context,
        ),
        **status_payload_sections.build_status_target_file_payload(
            foundation_context=foundation_context,
            activity_queue_context=activity_queue_context,
            transfer_activity_context=transfer_activity_context,
        ),
        **status_payload_sections.build_status_session_release_workbench_payload(
            activity_queue_context,
            tail_context,
        ),
    }
