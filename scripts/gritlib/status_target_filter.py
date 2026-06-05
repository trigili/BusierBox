"""Target-filter status schema helpers for grit-console status documents."""

from gritlib.record_utils import int_value
import gritlib.target_records as target_records


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
        **_build_selected_target_identity_filter_fields(selected_target),
        **_build_selected_target_activity_filter_fields(selected_target),
        **_build_selected_target_report_filter_fields(
            selected_target, target_filter_record
        ),
        "selected_target_notes_present": bool(str(selected_target.get("notes") or "").strip()),
        "applied_to": _target_filter_applied_sources(target_filter_id),
        "unfiltered_counts": unfiltered_counts,
        "filtered_counts": _target_filter_filtered_counts(
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
        "observed_activity_counts": _target_filter_observed_activity_counts(
            target_filter_record
        ),
    }

def _build_selected_target_identity_filter_fields(selected_target):
    return {
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
    }

def _build_selected_target_activity_filter_fields(selected_target):
    return {
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
    }

def _build_selected_target_report_filter_fields(selected_target, target_filter_record):
    return {
        "selected_target_latest_capability_check_count": target_filter_record.get("selected_target_latest_capability_check_count", 0),
        "selected_target_latest_capability_pass_count": target_filter_record.get("selected_target_latest_capability_pass_count", 0),
        "selected_target_latest_capability_fail_count": target_filter_record.get("selected_target_latest_capability_fail_count", 0),
        "selected_target_latest_compatibility_report_kind": str(selected_target.get("latest_compatibility_report_kind") or ""),
        "selected_target_latest_compatibility_label": str(selected_target.get("latest_compatibility_label") or ""),
        "selected_target_latest_compatibility_baseline_label": str(selected_target.get("latest_compatibility_baseline_label") or ""),
        "selected_target_latest_compatibility_release_name": str(selected_target.get("latest_compatibility_release_name") or ""),
        "selected_target_latest_compatibility_payload_preset": str(selected_target.get("latest_compatibility_payload_preset") or ""),
        "selected_target_latest_compatibility_reason_count": target_filter_record.get("selected_target_latest_compatibility_reason_count", 0),
    }

def _target_filter_applied_sources(target_filter_id):
    if not target_filter_id:
        return []
    return [
        "targets", "uploads", "fetches", "sessions", "events",
        "command_queue.commands", "staged_records", "staged_file_workflow_actions",
        "target_command_records", "target_phone_home_records",
    ]

def _target_filter_filtered_counts(
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
    }

def _target_filter_observed_activity_counts(target_filter_record):
    return {
        "unfiltered": target_filter_record.get("unfiltered_observed_activity_count", 0),
        "filtered": target_filter_record.get("filtered_observed_activity_count", 0),
        "has_unfiltered": bool(target_filter_record.get("has_unfiltered_observed_activity", False)),
        "has_filtered": bool(target_filter_record.get("has_filtered_observed_activity", False)),
        "filter_reduced": bool(target_filter_record.get("filter_reduced_observed_activity", False)),
    }


def build_target_filter_status_context(*args, **kwargs):
    return _build_target_filter_status_context(*args, **kwargs)


def build_target_filter_status_doc(*args, **kwargs):
    return _build_target_filter_status_doc(*args, **kwargs)
