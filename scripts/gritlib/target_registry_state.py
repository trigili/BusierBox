"""Target registry state record helpers for grit-console."""

from gritlib.record_utils import int_value, records_by_key


def _target_registry_selected_target_fields(selected_target):
    selected_target_sources = selected_target.get("identity_sources") or []
    selected_target_capability_summary = selected_target.get("latest_capability_summary") or {}
    if not isinstance(selected_target_capability_summary, dict):
        selected_target_capability_summary = {}
    selected_target_compatibility_summary = selected_target.get("latest_compatibility_summary") or {}
    if not isinstance(selected_target_compatibility_summary, dict):
        selected_target_compatibility_summary = {}
    return {
        "selected_target_found": bool(selected_target),
        "selected_target_label": str(selected_target.get("label") or ""),
        "selected_target_identity_confidence": str(selected_target.get("identity_confidence") or ""),
        "selected_target_connectivity_state": str(selected_target.get("connectivity_state") or ""),
        "selected_target_last_seen": str(selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""),
        "selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "selected_target_offline_age_bucket": str(selected_target.get("offline_age_bucket") or ""),
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
        "selected_target_next_expected_poll": str(selected_target.get("next_expected_poll") or ""),
        "selected_target_poll_overdue": bool(selected_target.get("poll_overdue", False)),
        "selected_target_poll_overdue_for_sec": selected_target.get("poll_overdue_for_sec", ""),
        "selected_target_mailbox_command_count": int_value(selected_target.get("mailbox_command_count", 0)),
        "selected_target_mailbox_pending_work_count": int_value(selected_target.get("mailbox_pending_work_count", 0)),
        "selected_target_identity_source_count": len(selected_target_sources),
        "selected_target_alias_count": len(selected_target.get("aliases") or []),
        "selected_target_notes_present": bool(str(selected_target.get("notes") or "").strip()),
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
        "selected_target_latest_capability_check_count": int_value(selected_target_capability_summary.get("check_count", 0)),
        "selected_target_latest_capability_pass_count": int_value(selected_target_capability_summary.get("capability_pass_count", 0)),
        "selected_target_latest_capability_fail_count": int_value(selected_target_capability_summary.get("capability_fail_count", 0)),
        "selected_target_latest_compatibility_report_kind": str(selected_target.get("latest_compatibility_report_kind") or ""),
        "selected_target_latest_compatibility_label": str(selected_target.get("latest_compatibility_label") or ""),
        "selected_target_latest_compatibility_baseline_label": str(selected_target.get("latest_compatibility_baseline_label") or ""),
        "selected_target_latest_compatibility_release_name": str(selected_target.get("latest_compatibility_release_name") or ""),
        "selected_target_latest_compatibility_payload_preset": str(selected_target.get("latest_compatibility_payload_preset") or ""),
        "selected_target_latest_compatibility_reason_count": int_value(selected_target_compatibility_summary.get("reason_count", 0)),
    }


def _target_registry_summary_fields(target_summary):
    return {
        "latest_target_id": str(target_summary.get("latest_target_id") or ""),
        "latest_target_label": str(target_summary.get("latest_target_label") or ""),
        "latest_target_seen_at": str(target_summary.get("latest_target_seen_at") or ""),
        "remote_address_count": int_value(target_summary.get("target_remote_address_count", 0)),
        "notes_count": int_value(target_summary.get("target_notes_count", 0)),
        "without_notes_count": int_value(target_summary.get("target_without_notes_count", 0)),
        "identity_confidence_counts": target_summary.get("target_identity_confidence_counts") or {},
        "identity_source_counts": target_summary.get("target_identity_source_counts") or {},
        "service_counts": target_summary.get("target_service_counts") or {},
        "latest_activity_service_counts": target_summary.get("target_latest_activity_service_counts") or {},
        "latest_activity_operation_counts": target_summary.get("target_latest_activity_operation_counts") or {},
        "connectivity_state_counts": target_summary.get("target_connectivity_state_counts") or {},
        "last_seen_via_counts": target_summary.get("target_last_seen_via_counts") or {},
        "latest_phone_home_status_counts": target_summary.get("target_latest_phone_home_status_counts") or {},
        "last_failed_phone_home_status_counts": target_summary.get("target_last_failed_phone_home_status_counts") or {},
        "last_failed_phone_home_reason_counts": target_summary.get("target_last_failed_phone_home_reason_counts") or {},
        "failed_phone_home_target_count": int_value(target_summary.get("target_failed_phone_home_target_count", 0)),
        "failed_phone_home_count": int_value(target_summary.get("target_failed_phone_home_count", 0)),
        "next_expected_poll_count": int_value(target_summary.get("target_next_expected_poll_count", 0)),
        "poll_overdue_count": int_value(target_summary.get("target_poll_overdue_count", 0)),
        "poll_overdue_counts": target_summary.get("target_poll_overdue_counts") or {},
        "mailbox_pending_target_count": int_value(target_summary.get("target_mailbox_pending_target_count", 0)),
        "mailbox_pending_work_count": int_value(target_summary.get("target_mailbox_pending_work_count", 0)),
        "latest_file_transfer_count": int_value(target_summary.get("target_latest_file_transfer_count", 0)),
        "latest_survey_result_count": int_value(target_summary.get("target_latest_survey_result_count", 0)),
        "latest_bridge_activity_count": int_value(target_summary.get("target_latest_bridge_activity_count", 0)),
        "capability_report_count": int_value(target_summary.get("target_capability_report_count", 0)),
        "compatibility_report_count": int_value(target_summary.get("target_compatibility_report_count", 0)),
        "compatibility_label_counts": target_summary.get("target_compatibility_label_counts") or {},
        "compatibility_baseline_label_counts": target_summary.get("target_compatibility_baseline_label_counts") or {},
        "compatibility_release_counts": target_summary.get("target_compatibility_release_counts") or {},
        "compatibility_payload_preset_counts": target_summary.get("target_compatibility_payload_preset_counts") or {},
    }


def _apply_target_registry_state_flags(state_record, selected_target=None):
    state_record.update({
        "has_targets": state_record.get("target_count", 0) > 0,
        "has_unfiltered_targets": state_record.get("unfiltered_target_count", 0) > 0,
        "has_selected_target": bool(selected_target),
        "has_latest_activity": bool(
            state_record.get("latest_activity_service_counts") or
            state_record.get("latest_activity_operation_counts")
        ),
        "has_next_expected_polls": state_record.get("next_expected_poll_count", 0) > 0,
        "has_poll_overdue": state_record.get("poll_overdue_count", 0) > 0,
        "has_mailbox_pending_work": state_record.get("mailbox_pending_work_count", 0) > 0,
        "has_failed_phone_home": state_record.get("failed_phone_home_target_count", 0) > 0,
        "has_latest_file_transfer": state_record.get("latest_file_transfer_count", 0) > 0,
        "has_latest_survey_result": state_record.get("latest_survey_result_count", 0) > 0,
        "has_latest_bridge_activity": state_record.get("latest_bridge_activity_count", 0) > 0,
        "has_identity_sources": bool(state_record.get("identity_source_counts")),
        "has_capability_reports": state_record.get("capability_report_count", 0) > 0,
        "has_compatibility_reports": state_record.get("compatibility_report_count", 0) > 0,
    })


def _target_registry_state_record(target_summary, selected_target, target_filter_id, unfiltered_target_count):
    state_record = {
        "id": "target-registry",
        "target_count": int_value(target_summary.get("target_count", 0)),
        "unfiltered_target_count": int_value(unfiltered_target_count),
        "filter_active": bool(target_filter_id),
        "filter_target_id": target_filter_id,
        **_target_registry_selected_target_fields(selected_target),
        **_target_registry_summary_fields(target_summary),
    }
    _apply_target_registry_state_flags(state_record, selected_target)
    return state_record


def _target_registry_selected_state_indexes(state_records):
    return {
        "target_registry_state_records_by_filter_active": records_by_key(state_records, "filter_active"),
        "target_registry_state_records_by_filter_target_id": records_by_key(state_records, "filter_target_id"),
        "target_registry_state_records_by_selected_target_found": records_by_key(state_records, "selected_target_found"),
        "target_registry_state_records_by_selected_target_identity_confidence": records_by_key(state_records, "selected_target_identity_confidence"),
        "target_registry_state_records_by_selected_target_connectivity_state": records_by_key(state_records, "selected_target_connectivity_state"),
        "target_registry_state_records_by_selected_target_offline_age_bucket": records_by_key(state_records, "selected_target_offline_age_bucket"),
        "target_registry_state_records_by_selected_target_latest_phone_home_status": records_by_key(state_records, "selected_target_latest_phone_home_status"),
        "target_registry_state_records_by_selected_target_latest_successful_phone_home_status": records_by_key(state_records, "selected_target_latest_successful_phone_home_status"),
        "target_registry_state_records_by_selected_target_last_failed_phone_home_status": records_by_key(state_records, "selected_target_last_failed_phone_home_status"),
        "target_registry_state_records_by_selected_target_poll_overdue": records_by_key(state_records, "selected_target_poll_overdue"),
        "target_registry_state_records_by_selected_target_mailbox_pending_work_count": records_by_key(state_records, "selected_target_mailbox_pending_work_count"),
        "target_registry_state_records_by_selected_target_latest_file_transfer_status": records_by_key(state_records, "selected_target_latest_file_transfer_status"),
        "target_registry_state_records_by_selected_target_latest_file_transfer_route_kind": records_by_key(state_records, "selected_target_latest_file_transfer_route_kind"),
        "target_registry_state_records_by_selected_target_latest_survey_result_status": records_by_key(state_records, "selected_target_latest_survey_result_status"),
        "target_registry_state_records_by_selected_target_latest_survey_result_route_kind": records_by_key(state_records, "selected_target_latest_survey_result_route_kind"),
        "target_registry_state_records_by_selected_target_latest_bridge_profile": records_by_key(state_records, "selected_target_latest_bridge_profile"),
        "target_registry_state_records_by_selected_target_latest_bridge_status": records_by_key(state_records, "selected_target_latest_bridge_status"),
        "target_registry_state_records_by_selected_target_latest_capability_report_kind": records_by_key(state_records, "selected_target_latest_capability_report_kind"),
        "target_registry_state_records_by_selected_target_latest_compatibility_label": records_by_key(state_records, "selected_target_latest_compatibility_label"),
        "target_registry_state_records_by_selected_target_latest_compatibility_release_name": records_by_key(state_records, "selected_target_latest_compatibility_release_name"),
    }


def _target_registry_state_flag_indexes(state_records):
    return {
        "target_registry_state_records_by_has_latest_activity": records_by_key(state_records, "has_latest_activity"),
        "target_registry_state_records_by_has_next_expected_polls": records_by_key(state_records, "has_next_expected_polls"),
        "target_registry_state_records_by_has_poll_overdue": records_by_key(state_records, "has_poll_overdue"),
        "target_registry_state_records_by_has_mailbox_pending_work": records_by_key(state_records, "has_mailbox_pending_work"),
        "target_registry_state_records_by_has_failed_phone_home": records_by_key(state_records, "has_failed_phone_home"),
        "target_registry_state_records_by_has_latest_file_transfer": records_by_key(state_records, "has_latest_file_transfer"),
        "target_registry_state_records_by_has_latest_survey_result": records_by_key(state_records, "has_latest_survey_result"),
        "target_registry_state_records_by_has_latest_bridge_activity": records_by_key(state_records, "has_latest_bridge_activity"),
        "target_registry_state_records_by_has_identity_sources": records_by_key(state_records, "has_identity_sources"),
        "target_registry_state_records_by_has_capability_reports": records_by_key(state_records, "has_capability_reports"),
        "target_registry_state_records_by_has_compatibility_reports": records_by_key(state_records, "has_compatibility_reports"),
    }


def _target_registry_state_index_maps(state_records):
    indexes = {
        "target_registry_state_records_by_id": {rec.get("id", ""): rec for rec in state_records if rec.get("id")},
        "target_registry_state_records_by_has_targets": records_by_key(state_records, "has_targets"),
        "target_registry_state_records_by_has_unfiltered_targets": records_by_key(state_records, "has_unfiltered_targets"),
    }
    indexes.update(_target_registry_selected_state_indexes(state_records))
    indexes.update(_target_registry_state_flag_indexes(state_records))
    return indexes


def target_registry_state_status(target_summary, selected_target=None, target_filter_id="", unfiltered_target_count=0):
    target_summary = target_summary if isinstance(target_summary, dict) else {}
    selected_target = selected_target if isinstance(selected_target, dict) else {}
    state_record = _target_registry_state_record(
        target_summary,
        selected_target,
        target_filter_id,
        unfiltered_target_count,
    )
    state_records = [state_record]
    state_index_maps = _target_registry_state_index_maps(state_records)
    summary = target_registry_state_summary(state_record, state_records)
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
        "summary": summary,
    }


def target_registry_state_summary(state_record=None, state_records=None):
    state_record = state_record or {}
    state_records = state_records or []
    return {
        "target_registry_state_record_count": len(state_records),
        "target_registry_has_targets": bool(state_record.get("has_targets", False)),
        "target_registry_has_unfiltered_targets": bool(
            state_record.get("has_unfiltered_targets", False)
        ),
        "target_registry_has_selected_target": bool(
            state_record.get("has_selected_target", False)
        ),
        "target_registry_has_latest_activity": bool(
            state_record.get("has_latest_activity", False)
        ),
        "target_registry_has_next_expected_polls": bool(
            state_record.get("has_next_expected_polls", False)
        ),
        "target_registry_has_poll_overdue": bool(
            state_record.get("has_poll_overdue", False)
        ),
        "target_registry_has_mailbox_pending_work": bool(
            state_record.get("has_mailbox_pending_work", False)
        ),
        "target_registry_has_identity_sources": bool(
            state_record.get("has_identity_sources", False)
        ),
        "target_registry_has_capability_reports": bool(
            state_record.get("has_capability_reports", False)
        ),
        "target_registry_has_compatibility_reports": bool(
            state_record.get("has_compatibility_reports", False)
        ),
    }
