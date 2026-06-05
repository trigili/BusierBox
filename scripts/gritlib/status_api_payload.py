"""API status payload builders for grit-console status documents."""

from gritlib.record_utils import int_value
import gritlib.session_state as session_state_module
import gritlib.status_indexes as status_indexes
import gritlib.status_target_filter as status_target_filter


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

def _status_api_metadata_payload(cfg, target_filter_id, selected_target, api_resources):
    return {
        "schema": 1,
        "generated_at": session_state_module.utc_now(),
        "api": _build_status_api_doc(
            cfg,
            target_filter_id,
            selected_target,
            api_resources,
        ),
    }

def _status_api_target_filter_payload(
    *,
    target_filter_id,
    selected_target,
    target_filter_record,
    unfiltered_counts,
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
    target_filter_records,
    target_filter_index_maps,
):
    return {
        "target_filter": status_target_filter.build_target_filter_status_doc(
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
    }

def _status_api_attribution_payload(
    target_attribution,
    target_attribution_records,
    target_attribution_index_maps,
):
    return {
        "target_attribution": target_attribution,
        "target_attribution_records": target_attribution_records,
        **target_attribution_index_maps,
    }

def _status_api_policy_resource_payload(
    *,
    rshell_session_policy,
    rshell_session_policy_records,
    rshell_session_policy_index_maps,
    api_resources,
    api_resource_indexes,
    api_collections,
    operator_console_workflows,
    operator_console_workflow_index_maps,
):
    return {
        "GRIT_RSHELL_SESSION_POLICY": rshell_session_policy,
        "rshell_session_policy_records": rshell_session_policy_records,
        **rshell_session_policy_index_maps,
        "api_resources": api_resources,
        **api_resource_indexes,
        "api_collections": api_collections,
        "operator_console_workflows": operator_console_workflows,
        **operator_console_workflow_index_maps,
    }

def _build_status_api_payload(**data):
    api_resources = status_indexes.api_resource_records(data["api_collections"])
    api_resource_indexes = status_indexes.api_resource_record_indexes(api_resources)
    return {
        **_status_api_metadata_payload(
            data["cfg"],
            data["target_filter_id"],
            data["selected_target"],
            api_resources,
        ),
        **_status_api_target_filter_payload(
            target_filter_id=data["target_filter_id"],
            selected_target=data["selected_target"],
            target_filter_record=data["target_filter_record"],
            unfiltered_counts=data["unfiltered_counts"],
            targets=data["targets"],
            uploads=data["uploads"],
            fetches=data["fetches"],
            sessions=data["sessions"],
            events=data["events"],
            command_queue=data["command_queue"],
            staged_records=data["staged_records"],
            staged_file_workflow_actions=data["staged_file_workflow_actions"],
            target_command_records=data["target_command_records"],
            target_phone_home_records=data["target_phone_home_records"],
            target_filter_records=data["target_filter_records"],
            target_filter_index_maps=data["target_filter_index_maps"],
        ),
        **_status_api_attribution_payload(
            data["target_attribution"],
            data["target_attribution_records"],
            data["target_attribution_index_maps"],
        ),
        **_status_api_policy_resource_payload(
            rshell_session_policy=data["rshell_session_policy"],
            rshell_session_policy_records=data["rshell_session_policy_records"],
            rshell_session_policy_index_maps=data[
                "rshell_session_policy_index_maps"
            ],
            api_resources=api_resources,
            api_resource_indexes=api_resource_indexes,
            api_collections=data["api_collections"],
            operator_console_workflows=data["operator_console_workflows"],
            operator_console_workflow_index_maps=data[
                "operator_console_workflow_index_maps"
            ],
        ),
    }


def build_status_api_payload(**data):
    return _build_status_api_payload(**data)
