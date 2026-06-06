"""Summary update builders for grit-console status documents."""

import gritlib.command_queue as command_queue_module
from gritlib.event_log import event_status_summary
import gritlib.file_transfers as file_transfers
from gritlib.release_artifact_workflow_actions import (
    release_artifact_workflow_action_status_summary,
)
from gritlib.session_records import session_record_summary
import gritlib.service_status as service_status
from gritlib.target_commands import target_command_status_summary


def _build_status_summary_updates(**sources):
    return {
        **_build_path_operator_summary_updates(
            **_summary_source_kwargs(
                sources,
                "path_context",
                "bridge_profile_context",
                "path_warning_context",
                "operator_state_file_summary_doc",
                "operator_state_summary",
                "staged_file_workflow_context",
            )
        ),
        **_build_service_file_summary_updates(
            **_summary_source_kwargs(
                sources,
                "services",
                "service_manager",
                "service_manager_status_doc",
                "ports",
                "warning_summary_context",
                "uploads",
                "fetches",
                "target_attribution",
                "target_file_transfer_records",
                "file_service_workflow_context",
                "target_activity_feed_context",
            )
        ),
        **_build_target_session_summary_updates(
            **_summary_source_kwargs(
                sources,
                "target_summary",
                "target_registry_summary",
                "target_filter_context",
                "target_attribution_context",
                "sessions",
                "session_root_state",
                "session_root_state_records",
                "target_attribution",
                "target_command_summary",
                "target_command_state_record",
                "target_command_state_records",
                "rshell_session_policy_record_item",
                "rshell_session_policy_records",
            )
        ),
        **_build_event_workflow_summary_updates(
            **_summary_source_kwargs(
                sources,
                "workflow_context",
                "event_stats",
                "event_log_state",
                "event_log_state_records",
                "events",
                "event_summary_stats",
                "operator_network_context",
                "command_queue",
                "command_queue_policy_records",
                "target_activity_context",
                "release_context_doc",
                "release_artifact_workflow_actions",
                "operator_console_workflow_context",
                "workbench_config_context",
                "command_queue_workflow_context",
                "service_probe_workflow_context",
            )
        ),
    }

def _summary_source_kwargs(sources, *names):
    return {name: sources[name] for name in names}

def _build_path_operator_summary_updates(
    *,
    path_context,
    bridge_profile_context,
    path_warning_context,
    operator_state_file_summary_doc,
    operator_state_summary,
    staged_file_workflow_context,
):
    return {
        **path_context["path_summary"],
        **bridge_profile_context["summary"],
        **path_context["browser_status_summary"],
        **path_warning_context["summary"],
        **operator_state_file_summary_doc,
        **operator_state_summary,
        **staged_file_workflow_context["summary"],
    }

def _build_service_file_summary_updates(
    *,
    services,
    service_manager,
    service_manager_status_doc,
    ports,
    warning_summary_context,
    uploads,
    fetches,
    target_attribution,
    target_file_transfer_records,
    file_service_workflow_context,
    target_activity_feed_context,
):
    return {
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
    }

def _build_target_session_summary_updates(
    *,
    target_summary,
    target_registry_summary,
    target_filter_context,
    target_attribution_context,
    sessions,
    session_root_state,
    session_root_state_records,
    target_attribution,
    target_command_summary,
    target_command_state_record,
    target_command_state_records,
    rshell_session_policy_record_item,
    rshell_session_policy_records,
):
    return {
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
    }

def _build_event_workflow_summary_updates(
    *,
    workflow_context,
    event_stats,
    event_log_state,
    event_log_state_records,
    events,
    event_summary_stats,
    operator_network_context,
    command_queue,
    command_queue_policy_records,
    target_activity_context,
    release_context_doc,
    release_artifact_workflow_actions,
    operator_console_workflow_context,
    workbench_config_context,
    command_queue_workflow_context,
    service_probe_workflow_context,
):
    return {
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
        **release_artifact_workflow_action_status_summary(
            release_artifact_workflow_actions
        ),
        **operator_console_workflow_context["summary"],
        **workbench_config_context["summary"],
        **command_queue_workflow_context["summary"],
        **service_probe_workflow_context["summary"],
    }


def build_status_summary_updates(**sources):
    return _build_status_summary_updates(**sources)
