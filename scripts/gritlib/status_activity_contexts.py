"""Activity queue status context assembly for grit-console."""

import gritlib.bridge_routes as bridge_routes
import gritlib.command_queue as command_queue_module
import gritlib.command_queue_policy as command_queue_policy_module
from gritlib.build_config import workbench_config_status_context
from gritlib.event_log import event_log_status_context, event_status_summary
from gritlib.release_artifacts import (
    release_artifact_workflow_action_status_summary, release_status_context,
)
from gritlib.service_runtime import SESSION_MANAGER
from gritlib.session_records import session_record_summary, session_status_context
import gritlib.status_target_filter as status_target_filter
import gritlib.status_workflow_contexts as status_workflow_contexts
import gritlib.target_activity as target_activity
import gritlib.target_mailbox as target_mailbox
import gritlib.target_phone_home as target_phone_home
from gritlib.target_commands import (
    rshell_session_policy_status,
    target_command_status_context,
    target_command_status_summary,
)
import gritlib.target_records as target_records
from gritlib.workbench_jobs import reconcile_workbench_job_completion_events

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


def _build_command_queue_status_context(cfg):
    queue_summary = command_queue_module.command_queue_summary(cfg)
    command_queue_policy = command_queue_policy_module.command_queue_policy_status(
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
            **target_mailbox.target_mailbox_record_summary(
                target_activity_context["target_mailbox_records"]
            ),
            **target_phone_home.target_phone_home_record_summary(
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
    staged_file_workflow_context = (
        status_workflow_contexts.build_staged_file_workflow_status_context(
            cfg,
            f["staged_records"],
            f["targets"],
        )
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
        "workflow_context": (
            status_workflow_contexts.build_workbench_workflow_status_context(
                cfg,
                targets,
                bridge_profiles,
            )
        ),
    }


def build_status_activity_queue_context(
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
