"""Status document and workbench snapshot composition for grit-console."""

from gritlib.config_utils import (
    DEFAULT_CONFIG,
)
import gritlib.session_state as session_state_module
import gritlib.status_activity_contexts as status_activity_contexts
import gritlib.status_api_collections as status_api_collections
import gritlib.status_api_payload as status_api_payload
import gritlib.status_foundation_contexts as status_foundation_contexts
import gritlib.status_payload_sections as status_payload_sections
import gritlib.status_summary_updates as status_summary_updates
import gritlib.status_tail_contexts as status_tail_contexts
import gritlib.status_transfer_contexts as status_transfer_contexts
import gritlib.target_records as target_records
from gritlib.workbench_jobs import (
    workbench_jobs_path, workbench_jobs_state_status,
)


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
    foundation_context = status_foundation_contexts.build_status_foundation_context(
        cfg, target_filter_id=target_filter_id
    )
    activity_queue_context = status_activity_contexts.build_status_activity_queue_context(
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
    tail_context = status_tail_contexts.build_status_tail_context(
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
    """Build the full status API document from domain-scoped contexts."""
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
