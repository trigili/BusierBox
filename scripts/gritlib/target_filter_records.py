"""Target-filter record, index, and summary helpers for grit-console."""

from gritlib.record_utils import int_value, records_by_key


def _target_filter_base_record_indexes(records):
    return {
        "target_filter_records_by_id": {rec["id"]: rec for rec in records},
        "target_filter_records_by_active": records_by_key(records, "active"),
        "target_filter_records_by_target_id": records_by_key(records, "target_id"),
        "target_filter_records_by_selected_target_found": records_by_key(
            records, "selected_target_found"
        ),
        "target_filter_records_by_selected_target_label": records_by_key(
            records, "selected_target_label"
        ),
    }


def _target_filter_selected_state_indexes(records):
    return {
        "target_filter_records_by_selected_target_identity_confidence": records_by_key(
            records, "selected_target_identity_confidence"
        ),
        "target_filter_records_by_selected_target_connectivity_state": records_by_key(
            records, "selected_target_connectivity_state"
        ),
        "target_filter_records_by_selected_target_offline_age_bucket": records_by_key(
            records, "selected_target_offline_age_bucket"
        ),
        "target_filter_records_by_selected_target_latest_phone_home_status": records_by_key(
            records, "selected_target_latest_phone_home_status"
        ),
        "target_filter_records_by_selected_target_latest_successful_phone_home_status": records_by_key(
            records, "selected_target_latest_successful_phone_home_status"
        ),
        "target_filter_records_by_selected_target_last_failed_phone_home_status": records_by_key(
            records, "selected_target_last_failed_phone_home_status"
        ),
        "target_filter_records_by_selected_target_poll_overdue": records_by_key(
            records, "selected_target_poll_overdue"
        ),
        "target_filter_records_by_selected_target_mailbox_pending_work_count": records_by_key(
            records, "selected_target_mailbox_pending_work_count"
        ),
        "target_filter_records_by_selected_target_notes_present": records_by_key(
            records, "selected_target_notes_present"
        ),
    }


def _target_filter_latest_activity_indexes(records):
    return {
        "target_filter_records_by_selected_target_latest_activity_service": records_by_key(
            records, "selected_target_latest_activity_service"
        ),
        "target_filter_records_by_selected_target_latest_activity_operation": records_by_key(
            records, "selected_target_latest_activity_operation"
        ),
        "target_filter_records_by_selected_target_latest_file_transfer_status": records_by_key(
            records, "selected_target_latest_file_transfer_status"
        ),
        "target_filter_records_by_selected_target_latest_file_transfer_route_kind": records_by_key(
            records, "selected_target_latest_file_transfer_route_kind"
        ),
        "target_filter_records_by_selected_target_latest_survey_result_status": records_by_key(
            records, "selected_target_latest_survey_result_status"
        ),
        "target_filter_records_by_selected_target_latest_survey_result_route_kind": records_by_key(
            records, "selected_target_latest_survey_result_route_kind"
        ),
        "target_filter_records_by_selected_target_latest_bridge_profile": records_by_key(
            records, "selected_target_latest_bridge_profile"
        ),
        "target_filter_records_by_selected_target_latest_bridge_status": records_by_key(
            records, "selected_target_latest_bridge_status"
        ),
    }


def _target_filter_report_indexes(records):
    return {
        "target_filter_records_by_selected_target_latest_capability_report_kind": records_by_key(
            records, "selected_target_latest_capability_report_kind"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_report_kind": records_by_key(
            records, "selected_target_latest_compatibility_report_kind"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_label": records_by_key(
            records, "selected_target_latest_compatibility_label"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_release_name": records_by_key(
            records, "selected_target_latest_compatibility_release_name"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_payload_preset": records_by_key(
            records, "selected_target_latest_compatibility_payload_preset"
        ),
    }


def _target_filter_activity_count_indexes(records):
    return {
        "target_filter_records_by_has_unfiltered_activity": records_by_key(
            records, "has_unfiltered_activity"
        ),
        "target_filter_records_by_has_filtered_activity": records_by_key(
            records, "has_filtered_activity"
        ),
        "target_filter_records_by_filter_reduced_activity": records_by_key(
            records, "filter_reduced_activity"
        ),
        "target_filter_records_by_has_unfiltered_observed_activity": records_by_key(
            records, "has_unfiltered_observed_activity"
        ),
        "target_filter_records_by_has_filtered_observed_activity": records_by_key(
            records, "has_filtered_observed_activity"
        ),
        "target_filter_records_by_filter_reduced_observed_activity": records_by_key(
            records, "filter_reduced_observed_activity"
        ),
    }


def target_filter_record_indexes(records):
    indexes = _target_filter_base_record_indexes(records)
    indexes.update(_target_filter_selected_state_indexes(records))
    indexes.update(_target_filter_latest_activity_indexes(records))
    indexes.update(_target_filter_report_indexes(records))
    indexes.update(_target_filter_activity_count_indexes(records))
    return indexes


def _selected_target_base_filter_fields(selected_target):
    return {
        "selected_target_found": bool(selected_target),
        "selected_target_label": str(selected_target.get("label") or ""),
        "selected_target_identity_confidence": str(
            selected_target.get("identity_confidence") or ""
        ),
        "selected_target_connectivity_state": str(
            selected_target.get("connectivity_state") or ""
        ),
        "selected_target_last_seen": str(
            selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""
        ),
        "selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "selected_target_offline_age_bucket": str(
            selected_target.get("offline_age_bucket") or ""
        ),
    }


def _selected_target_phone_home_filter_fields(selected_target):
    return {
        "selected_target_latest_phone_home_at": str(
            selected_target.get("latest_phone_home_at") or ""
        ),
        "selected_target_latest_phone_home_status": str(
            selected_target.get("latest_phone_home_status") or ""
        ),
        "selected_target_latest_phone_home_kind": str(
            selected_target.get("latest_phone_home_kind") or ""
        ),
        "selected_target_latest_phone_home_contact_path": str(
            selected_target.get("latest_phone_home_contact_path") or ""
        ),
        "selected_target_latest_successful_phone_home_at": str(
            selected_target.get("latest_successful_phone_home_at") or ""
        ),
        "selected_target_latest_successful_phone_home_status": str(
            selected_target.get("latest_successful_phone_home_status") or ""
        ),
        "selected_target_latest_successful_phone_home_kind": str(
            selected_target.get("latest_successful_phone_home_kind") or ""
        ),
        "selected_target_latest_successful_phone_home_contact_path": str(
            selected_target.get("latest_successful_phone_home_contact_path") or ""
        ),
        "selected_target_last_failed_phone_home_at": str(
            selected_target.get("last_failed_phone_home_at") or ""
        ),
        "selected_target_last_failed_phone_home_status": str(
            selected_target.get("last_failed_phone_home_status") or ""
        ),
        "selected_target_last_failed_phone_home_reason": str(
            selected_target.get("last_failed_phone_home_reason") or ""
        ),
        "selected_target_last_failed_phone_home_contact_path": str(
            selected_target.get("last_failed_phone_home_contact_path") or ""
        ),
        "selected_target_next_expected_poll": str(
            selected_target.get("next_expected_poll") or ""
        ),
        "selected_target_poll_overdue": bool(
            selected_target.get("poll_overdue", False)
        ),
        "selected_target_poll_overdue_for_sec": selected_target.get(
            "poll_overdue_for_sec", ""
        ),
    }


def _selected_target_mailbox_metadata_filter_fields(selected_target):
    selected_target_sources = selected_target.get("identity_sources") or []
    return {
        "selected_target_mailbox_command_count": int_value(
            selected_target.get("mailbox_command_count", 0)
        ),
        "selected_target_mailbox_pending_work_count": int_value(
            selected_target.get("mailbox_pending_work_count", 0)
        ),
        "selected_target_identity_source_count": len(selected_target_sources),
        "selected_target_alias_count": len(selected_target.get("aliases") or []),
        "selected_target_notes_present": bool(
            str(selected_target.get("notes") or "").strip()
        ),
    }


def _selected_target_identity_filter_fields(selected_target):
    return {
        **_selected_target_base_filter_fields(selected_target),
        **_selected_target_phone_home_filter_fields(selected_target),
        **_selected_target_mailbox_metadata_filter_fields(selected_target),
    }


def _selected_target_activity_filter_fields(selected_target):
    return {
        "selected_target_latest_activity_service": str(
            selected_target.get("latest_activity_service") or ""
        ),
        "selected_target_latest_activity_operation": str(
            selected_target.get("latest_activity_operation") or ""
        ),
    }


def _selected_target_file_survey_bridge_filter_fields(selected_target):
    return {
        "selected_target_latest_file_transfer_operation": str(
            selected_target.get("latest_file_transfer_operation") or ""
        ),
        "selected_target_latest_file_transfer_status": str(
            selected_target.get("latest_file_transfer_status") or ""
        ),
        "selected_target_latest_file_transfer_route_kind": str(
            selected_target.get("latest_file_transfer_route_kind") or ""
        ),
        "selected_target_latest_file_transfer_bridge_profile": str(
            selected_target.get("latest_file_transfer_bridge_profile") or ""
        ),
        "selected_target_latest_survey_result_kind": str(
            selected_target.get("latest_survey_result_kind") or ""
        ),
        "selected_target_latest_survey_result_status": str(
            selected_target.get("latest_survey_result_status") or ""
        ),
        "selected_target_latest_survey_result_route_kind": str(
            selected_target.get("latest_survey_result_route_kind") or ""
        ),
        "selected_target_latest_survey_result_bridge_profile": str(
            selected_target.get("latest_survey_result_bridge_profile") or ""
        ),
        "selected_target_latest_bridge_profile": str(
            selected_target.get("latest_bridge_profile") or ""
        ),
        "selected_target_latest_bridge_status": str(
            selected_target.get("latest_bridge_status") or ""
        ),
        "selected_target_latest_bridge_route_path": str(
            selected_target.get("latest_bridge_route_path") or ""
        ),
        "selected_target_latest_bridge_failure_reason": str(
            selected_target.get("latest_bridge_failure_reason") or ""
        ),
    }


def _selected_target_report_filter_fields(selected_target):
    selected_target_capability_summary = (
        selected_target.get("latest_capability_summary") or {}
    )
    if not isinstance(selected_target_capability_summary, dict):
        selected_target_capability_summary = {}
    selected_target_compatibility_summary = (
        selected_target.get("latest_compatibility_summary") or {}
    )
    if not isinstance(selected_target_compatibility_summary, dict):
        selected_target_compatibility_summary = {}
    return {
        "selected_target_latest_capability_report_kind": str(
            selected_target.get("latest_capability_report_kind") or ""
        ),
        "selected_target_latest_capability_check_count": int_value(
            selected_target_capability_summary.get("check_count", 0)
        ),
        "selected_target_latest_capability_pass_count": int_value(
            selected_target_capability_summary.get("capability_pass_count", 0)
        ),
        "selected_target_latest_capability_fail_count": int_value(
            selected_target_capability_summary.get("capability_fail_count", 0)
        ),
        "selected_target_latest_compatibility_report_kind": str(
            selected_target.get("latest_compatibility_report_kind") or ""
        ),
        "selected_target_latest_compatibility_label": str(
            selected_target.get("latest_compatibility_label") or ""
        ),
        "selected_target_latest_compatibility_baseline_label": str(
            selected_target.get("latest_compatibility_baseline_label") or ""
        ),
        "selected_target_latest_compatibility_release_name": str(
            selected_target.get("latest_compatibility_release_name") or ""
        ),
        "selected_target_latest_compatibility_payload_preset": str(
            selected_target.get("latest_compatibility_payload_preset") or ""
        ),
        "selected_target_latest_compatibility_reason_count": int_value(
            selected_target_compatibility_summary.get("reason_count", 0)
        ),
    }


def target_filter_record_from_target(target_filter_id="", selected_target=None):
    selected_target = selected_target if isinstance(selected_target, dict) else {}
    return {
        "id": target_filter_id or "all-targets",
        "active": bool(target_filter_id),
        "target_id": target_filter_id,
        **_selected_target_identity_filter_fields(selected_target),
        **_selected_target_activity_filter_fields(selected_target),
        **_selected_target_file_survey_bridge_filter_fields(selected_target),
        **_selected_target_report_filter_fields(selected_target),
    }


def _target_filter_activity_count_fields(prefix, counts):
    return {
        f"{prefix}_target_count": counts.get("targets", 0),
        f"{prefix}_upload_count": counts.get("uploads", 0),
        f"{prefix}_fetch_count": counts.get("fetches", 0),
        f"{prefix}_staged_count": counts.get("staged", 0),
        f"{prefix}_session_count": counts.get("sessions", 0),
        f"{prefix}_event_tail_count": counts.get("event_tail", 0),
        f"{prefix}_command_queue_command_count": counts.get(
            "command_queue_commands", 0
        ),
        f"{prefix}_target_command_record_count": counts.get(
            "target_command_records", 0
        ),
        f"{prefix}_target_phone_home_record_count": counts.get(
            "target_phone_home_records", 0
        ),
    }


def _target_filter_activity_total(record, prefix, *, include_command_records=True):
    total = (
        record[f"{prefix}_upload_count"] +
        record[f"{prefix}_fetch_count"] +
        record[f"{prefix}_staged_count"] +
        record[f"{prefix}_session_count"] +
        record[f"{prefix}_event_tail_count"] +
        record[f"{prefix}_command_queue_command_count"] +
        record[f"{prefix}_target_phone_home_record_count"]
    )
    if include_command_records:
        total += record[f"{prefix}_target_command_record_count"]
    return total


def _apply_target_filter_activity_totals(record):
    record["unfiltered_activity_count"] = _target_filter_activity_total(
        record,
        "unfiltered",
    )
    record["filtered_activity_count"] = _target_filter_activity_total(
        record,
        "filtered",
    )
    record["unfiltered_observed_activity_count"] = _target_filter_activity_total(
        record,
        "unfiltered",
        include_command_records=False,
    )
    record["filtered_observed_activity_count"] = _target_filter_activity_total(
        record,
        "filtered",
        include_command_records=False,
    )


def _apply_target_filter_activity_flags(record, target_filter_id=""):
    record["has_unfiltered_activity"] = record["unfiltered_activity_count"] > 0
    record["has_filtered_activity"] = record["filtered_activity_count"] > 0
    record["filter_reduced_activity"] = (
        bool(target_filter_id) and
        record["filtered_activity_count"] < record["unfiltered_activity_count"]
    )
    record["has_unfiltered_observed_activity"] = (
        record["unfiltered_observed_activity_count"] > 0
    )
    record["has_filtered_observed_activity"] = (
        record["filtered_observed_activity_count"] > 0
    )
    record["filter_reduced_observed_activity"] = (
        bool(target_filter_id) and
        record["filtered_observed_activity_count"] <
        record["unfiltered_observed_activity_count"]
    )


def apply_target_filter_activity_counts(
    record,
    target_filter_id="",
    unfiltered=None,
    filtered=None,
):
    record = record if isinstance(record, dict) else {}
    unfiltered = unfiltered if isinstance(unfiltered, dict) else {}
    filtered = filtered if isinstance(filtered, dict) else {}
    record.update(_target_filter_activity_count_fields("unfiltered", unfiltered))
    record.update(_target_filter_activity_count_fields("filtered", filtered))
    _apply_target_filter_activity_totals(record)
    _apply_target_filter_activity_flags(record, target_filter_id)
    return record


def target_filter_status_context(
    target_filter_id="",
    selected_target=None,
    unfiltered_counts=None,
    filtered_counts=None,
    target_mailbox_records=None,
):
    record = target_filter_record_from_target(target_filter_id, selected_target)
    apply_target_filter_activity_counts(
        record,
        target_filter_id,
        unfiltered_counts,
        filtered_counts,
    )
    records = [record]
    return {
        "record": record,
        "records": records,
        "index_maps": target_filter_record_indexes(records),
        "summary": target_filter_status_summary(
            record,
            records,
            target_filter_id=target_filter_id,
            target_mailbox_records=target_mailbox_records,
        ),
    }


def _target_filter_unfiltered_count_summary(record):
    return {
        "target_filter_unfiltered_target_count": record.get(
            "unfiltered_target_count", 0
        ),
        "target_filter_unfiltered_upload_count": record.get(
            "unfiltered_upload_count", 0
        ),
        "target_filter_unfiltered_fetch_count": record.get(
            "unfiltered_fetch_count", 0
        ),
        "target_filter_unfiltered_staged_count": record.get(
            "unfiltered_staged_count", 0
        ),
        "target_filter_unfiltered_session_count": record.get(
            "unfiltered_session_count", 0
        ),
        "target_filter_unfiltered_event_tail_count": record.get(
            "unfiltered_event_tail_count", 0
        ),
        "target_filter_unfiltered_command_queue_command_count": record.get(
            "unfiltered_command_queue_command_count", 0
        ),
        "target_filter_unfiltered_target_command_record_count": record.get(
            "unfiltered_target_command_record_count", 0
        ),
        "target_filter_unfiltered_target_phone_home_record_count": record.get(
            "unfiltered_target_phone_home_record_count", 0
        ),
    }


def _target_filter_observed_activity_summary(record):
    return {
        "target_filter_unfiltered_observed_activity_count": record.get(
            "unfiltered_observed_activity_count", 0
        ),
        "target_filter_observed_activity_count": record.get(
            "filtered_observed_activity_count", 0
        ),
        "target_filter_has_unfiltered_observed_activity": bool(
            record.get("has_unfiltered_observed_activity", False)
        ),
        "target_filter_has_observed_activity": bool(
            record.get("has_filtered_observed_activity", False)
        ),
        "target_filter_reduced_observed_activity": bool(
            record.get("filter_reduced_observed_activity", False)
        ),
    }


def _target_filter_filtered_count_summary(record, target_mailbox_records=None):
    return {
        "target_filter_event_tail_count": record.get("filtered_event_tail_count", 0),
        "target_filter_command_queue_command_count": record.get(
            "filtered_command_queue_command_count", 0
        ),
        "target_filter_target_mailbox_record_count": len(
            target_mailbox_records or []
        ),
        "target_filter_target_command_record_count": record.get(
            "filtered_target_command_record_count", 0
        ),
        "target_filter_target_phone_home_record_count": record.get(
            "filtered_target_phone_home_record_count", 0
        ),
    }


def _target_filter_selected_target_summary(record, records=None):
    return {
        "target_filter_record_count": len(records or []),
        "target_filter_selected_target_found": bool(
            record.get("selected_target_found", False)
        ),
        "target_filter_selected_target_identity_source_count": record.get(
            "selected_target_identity_source_count", 0
        ),
        "target_filter_selected_target_alias_count": record.get(
            "selected_target_alias_count", 0
        ),
        "target_filter_selected_target_notes_present": bool(
            record.get("selected_target_notes_present", False)
        ),
    }


def target_filter_status_summary(
    record,
    records=None,
    target_filter_id="",
    target_mailbox_records=None,
):
    record = record or {}
    records = records or []
    return {
        "target_filter_active": bool(target_filter_id),
        "target_filter_id": target_filter_id,
        **_target_filter_unfiltered_count_summary(record),
        **_target_filter_observed_activity_summary(record),
        **_target_filter_filtered_count_summary(record, target_mailbox_records),
        **_target_filter_selected_target_summary(record, records),
    }
