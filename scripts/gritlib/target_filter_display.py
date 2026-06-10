"""Target-filter human display helpers for grit-console."""


def target_filter_evidence_lines(target_filter):
    if not isinstance(target_filter, dict) or not target_filter.get("active"):
        return []
    lines = []
    file_operation = str(target_filter.get("selected_target_latest_file_transfer_operation") or "")
    phone_home_at = str(target_filter.get("selected_target_latest_phone_home_at") or "")
    successful_phone_home_at = str(target_filter.get("selected_target_latest_successful_phone_home_at") or "")
    failed_phone_home_at = str(target_filter.get("selected_target_last_failed_phone_home_at") or "")
    survey_kind = str(target_filter.get("selected_target_latest_survey_result_kind") or "")
    bridge_profile = str(target_filter.get("selected_target_latest_bridge_profile") or "")
    capability_kind = str(target_filter.get("selected_target_latest_capability_report_kind") or "")
    compatibility_label = str(target_filter.get("selected_target_latest_compatibility_label") or "")
    if phone_home_at:
        lines.append(
            "phone_home="
            f"{phone_home_at} "
            f"status={target_filter.get('selected_target_latest_phone_home_status') or '-'} "
            f"kind={target_filter.get('selected_target_latest_phone_home_kind') or '-'} "
            f"path={target_filter.get('selected_target_latest_phone_home_contact_path') or '-'}"
        )
    if successful_phone_home_at:
        lines.append(
            "successful_phone_home="
            f"{successful_phone_home_at} "
            f"status={target_filter.get('selected_target_latest_successful_phone_home_status') or '-'} "
            f"kind={target_filter.get('selected_target_latest_successful_phone_home_kind') or '-'} "
            f"path={target_filter.get('selected_target_latest_successful_phone_home_contact_path') or '-'}"
        )
    if failed_phone_home_at:
        lines.append(
            "failed_phone_home="
            f"{failed_phone_home_at} "
            f"status={target_filter.get('selected_target_last_failed_phone_home_status') or '-'} "
            f"reason={target_filter.get('selected_target_last_failed_phone_home_reason') or '-'} "
            f"path={target_filter.get('selected_target_last_failed_phone_home_contact_path') or '-'}"
        )
    if file_operation:
        lines.append(
            "file_transfer="
            f"{file_operation} "
            f"status={target_filter.get('selected_target_latest_file_transfer_status') or '-'} "
            f"route={target_filter.get('selected_target_latest_file_transfer_route_kind') or '-'} "
            f"bridge_profile={target_filter.get('selected_target_latest_file_transfer_bridge_profile') or '-'}"
        )
    if survey_kind:
        lines.append(
            "survey_result="
            f"{survey_kind} "
            f"status={target_filter.get('selected_target_latest_survey_result_status') or '-'} "
            f"route={target_filter.get('selected_target_latest_survey_result_route_kind') or '-'} "
            f"bridge_profile={target_filter.get('selected_target_latest_survey_result_bridge_profile') or '-'}"
        )
    if bridge_profile:
        lines.append(
            "bridge="
            f"{bridge_profile} "
            f"status={target_filter.get('selected_target_latest_bridge_status') or '-'} "
            f"path={target_filter.get('selected_target_latest_bridge_route_path') or '-'} "
            f"failure={target_filter.get('selected_target_latest_bridge_failure_reason') or '-'}"
        )
    if capability_kind:
        lines.append(
            "capability="
            f"{capability_kind} "
            f"checks={target_filter.get('selected_target_latest_capability_check_count', 0)} "
            f"pass={target_filter.get('selected_target_latest_capability_pass_count', 0)} "
            f"fail={target_filter.get('selected_target_latest_capability_fail_count', 0)}"
        )
    if compatibility_label:
        lines.append(
            "compatibility="
            f"{target_filter.get('selected_target_latest_compatibility_report_kind') or '-'} "
            f"label={compatibility_label} "
            f"baseline={target_filter.get('selected_target_latest_compatibility_baseline_label') or '-'} "
            f"release={target_filter.get('selected_target_latest_compatibility_release_name') or '-'} "
            f"payload={target_filter.get('selected_target_latest_compatibility_payload_preset') or '-'} "
            f"reasons={target_filter.get('selected_target_latest_compatibility_reason_count', 0)}"
        )
    return lines


def target_filter_summary_text(target_filter, prefix="target_filter:"):
    if not isinstance(target_filter, dict) or not target_filter.get("active"):
        return ""
    counts = target_filter.get("filtered_counts") or {}
    observed_counts = target_filter.get("observed_activity_counts") or {}
    label = target_filter.get("selected_target_label") or "-"
    confidence = target_filter.get("selected_target_identity_confidence") or "-"
    state = target_filter.get("selected_target_connectivity_state") or "-"
    phone_home_at = target_filter.get("selected_target_latest_phone_home_at") or "-"
    phone_home_status = target_filter.get("selected_target_latest_phone_home_status") or "-"
    successful_phone_home_at = target_filter.get("selected_target_latest_successful_phone_home_at") or "-"
    successful_phone_home_status = target_filter.get("selected_target_latest_successful_phone_home_status") or "-"
    failed_phone_home_at = target_filter.get("selected_target_last_failed_phone_home_at") or "-"
    failed_phone_home_status = target_filter.get("selected_target_last_failed_phone_home_status") or "-"
    offline_for = target_filter.get("selected_target_offline_for_sec", "")
    offline_age = target_filter.get("selected_target_offline_age_bucket") or "-"
    if offline_for == "":
        offline_for = "-"
    return (
        f"{prefix} {target_filter.get('target_id', '')} "
        f"targets={counts.get('targets', 0)} uploads={counts.get('uploads', 0)} "
        f"fetches={counts.get('fetches', 0)} sessions={counts.get('sessions', 0)} "
        f"commands={counts.get('command_queue_commands', 0)} "
        f"target_cmds={counts.get('target_command_records', 0)} "
        f"mailbox_pending={target_filter.get('selected_target_mailbox_pending_work_count', 0)} "
        f"poll_overdue={'yes' if target_filter.get('selected_target_poll_overdue') else 'no'} "
        f"offline_for={offline_for} "
        f"offline_age={offline_age} "
        f"phone_home={phone_home_status}@{phone_home_at} "
        f"successful_phone_home={successful_phone_home_status}@{successful_phone_home_at} "
        f"failed_phone_home={failed_phone_home_status}@{failed_phone_home_at} "
        f"observed={observed_counts.get('filtered', 0)}/{observed_counts.get('unfiltered', 0)} "
        f"observed_seen={'yes' if observed_counts.get('has_filtered') else 'no'} "
        f"state={state} label={label} confidence={confidence}"
    )


def target_filter_brief_text(target_filter, prefix="selected target:"):
    if not isinstance(target_filter, dict) or not target_filter.get("active"):
        return ""
    counts = target_filter.get("filtered_counts") or {}
    label = target_filter.get("selected_target_label") or "-"
    state = target_filter.get("selected_target_connectivity_state") or "-"
    pending = target_filter.get("selected_target_mailbox_pending_work_count", 0)
    sessions = counts.get("sessions", 0)
    uploads = counts.get("uploads", 0)
    poll = "overdue" if target_filter.get("selected_target_poll_overdue") else "current"
    offline_age = target_filter.get("selected_target_offline_age_bucket") or "-"
    return (
        f"{prefix} {target_filter.get('target_id', '')} ({label})  "
        f"state {state}  mailbox {pending} pending  sessions {sessions}  "
        f"uploads {uploads}  poll {poll}  offline {offline_age}"
    )
