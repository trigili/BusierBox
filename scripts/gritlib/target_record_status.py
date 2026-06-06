"""Target record index and summary helpers for grit-console."""

from gritlib.record_utils import record_count_by_key, records_by_key


def _target_record_report_indexes(records):
    by_capability_report_kind = {}
    by_compatibility_report_kind = {}
    by_compatibility_label = {}
    by_compatibility_baseline_label = {}
    by_compatibility_release = {}
    by_compatibility_payload_preset = {}
    by_observed_capability = {}
    by_missing_capability = {}
    by_observed_constraint = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        report_kind = str(rec.get("latest_capability_report_kind") or "")
        if report_kind:
            by_capability_report_kind.setdefault(report_kind, []).append(rec)
        compatibility_kind = str(rec.get("latest_compatibility_report_kind") or "")
        if compatibility_kind:
            by_compatibility_report_kind.setdefault(compatibility_kind, []).append(rec)
        compatibility_label = str(rec.get("latest_compatibility_label") or "")
        if compatibility_label:
            by_compatibility_label.setdefault(compatibility_label, []).append(rec)
        compatibility_baseline = str(rec.get("latest_compatibility_baseline_label") or "")
        if compatibility_baseline:
            by_compatibility_baseline_label.setdefault(compatibility_baseline, []).append(rec)
        compatibility_release = str(rec.get("latest_compatibility_release_name") or "")
        if compatibility_release:
            by_compatibility_release.setdefault(compatibility_release, []).append(rec)
        compatibility_payload = str(rec.get("latest_compatibility_payload_preset") or "")
        if compatibility_payload:
            by_compatibility_payload_preset.setdefault(compatibility_payload, []).append(rec)
        for capability in rec.get("observed_capabilities") or []:
            capability = str(capability or "")
            if capability:
                by_observed_capability.setdefault(capability, []).append(rec)
        for capability in rec.get("observed_missing_capabilities") or []:
            capability = str(capability or "")
            if capability:
                by_missing_capability.setdefault(capability, []).append(rec)
        constraints = rec.get("observed_constraints") if isinstance(rec.get("observed_constraints"), dict) else {}
        for name, value in sorted(constraints.items()):
            name = str(name or "")
            if name:
                by_observed_constraint.setdefault(f"{name}:{str(bool(value)).lower()}", []).append(rec)
    return (
        by_capability_report_kind,
        by_compatibility_report_kind,
        by_compatibility_label,
        by_compatibility_baseline_label,
        by_compatibility_release,
        by_compatibility_payload_preset,
        by_observed_capability,
        by_missing_capability,
        by_observed_constraint,
    )


def _target_record_activity_indexes(records):
    by_latest_activity_service = {}
    by_latest_activity_operation = {}
    by_latest_file_transfer_operation = {}
    by_latest_file_transfer_status = {}
    by_latest_file_transfer_route_kind = {}
    by_latest_file_transfer_bridge_profile = {}
    by_latest_survey_result_kind = {}
    by_latest_survey_result_status = {}
    by_latest_survey_result_route_kind = {}
    by_latest_survey_result_bridge_profile = {}
    by_latest_bridge_profile = {}
    by_latest_bridge_status = {}
    by_has_latest_bridge_activity = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        activity_service = str(rec.get("latest_activity_service") or "")
        if activity_service:
            by_latest_activity_service.setdefault(activity_service, []).append(rec)
        activity_operation = str(rec.get("latest_activity_operation") or "")
        if activity_operation:
            by_latest_activity_operation.setdefault(activity_operation, []).append(rec)
        by_has_latest_bridge_activity.setdefault("yes" if str(rec.get("latest_bridge_activity_at") or "") else "no", []).append(rec)
        file_op = str(rec.get("latest_file_transfer_operation") or "")
        if file_op:
            by_latest_file_transfer_operation.setdefault(file_op, []).append(rec)
        file_status = str(rec.get("latest_file_transfer_status") or "")
        if file_status:
            by_latest_file_transfer_status.setdefault(file_status, []).append(rec)
        file_route_kind = str(rec.get("latest_file_transfer_route_kind") or "")
        if file_route_kind:
            by_latest_file_transfer_route_kind.setdefault(file_route_kind, []).append(rec)
        file_bridge_profile = str(rec.get("latest_file_transfer_bridge_profile") or "")
        if file_bridge_profile:
            by_latest_file_transfer_bridge_profile.setdefault(file_bridge_profile, []).append(rec)
        survey_kind = str(rec.get("latest_survey_result_kind") or "")
        if survey_kind:
            by_latest_survey_result_kind.setdefault(survey_kind, []).append(rec)
        survey_status = str(rec.get("latest_survey_result_status") or "")
        if survey_status:
            by_latest_survey_result_status.setdefault(survey_status, []).append(rec)
        survey_route_kind = str(rec.get("latest_survey_result_route_kind") or "")
        if survey_route_kind:
            by_latest_survey_result_route_kind.setdefault(survey_route_kind, []).append(rec)
        survey_bridge_profile = str(rec.get("latest_survey_result_bridge_profile") or "")
        if survey_bridge_profile:
            by_latest_survey_result_bridge_profile.setdefault(survey_bridge_profile, []).append(rec)
        bridge_profile = str(rec.get("latest_bridge_profile") or "")
        if bridge_profile:
            by_latest_bridge_profile.setdefault(bridge_profile, []).append(rec)
        bridge_status = str(rec.get("latest_bridge_status") or "")
        if bridge_status:
            by_latest_bridge_status.setdefault(bridge_status, []).append(rec)
    return (
        by_latest_activity_service,
        by_latest_activity_operation,
        by_latest_file_transfer_operation,
        by_latest_file_transfer_status,
        by_latest_file_transfer_route_kind,
        by_latest_file_transfer_bridge_profile,
        by_latest_survey_result_kind,
        by_latest_survey_result_status,
        by_latest_survey_result_route_kind,
        by_latest_survey_result_bridge_profile,
        by_latest_bridge_profile,
        by_latest_bridge_status,
        by_has_latest_bridge_activity,
    )


def _empty_target_record_identity_indexes():
    return {
        "by_id": {},
        "by_label": {},
        "by_alias": {},
        "by_remote_addr": {},
        "by_service": {},
        "by_identity_confidence": {},
        "by_identity_source": {},
        "by_connectivity_state": {},
        "by_last_seen_via": {},
        "by_offline_age_bucket": {},
        "by_has_next_expected_poll": {},
        "by_poll_overdue": {},
        "by_mailbox_pending_work": {},
        "by_latest_phone_home_status": {},
        "by_has_last_failed_phone_home": {},
        "by_last_failed_phone_home_reason": {},
        "by_last_failed_phone_home_status": {},
        "by_has_notes": {},
    }


def _index_target_record_text(indexes, index_name, value, rec):
    value = str(value or "")
    if value:
        indexes[index_name].setdefault(value, []).append(rec)


def _index_target_record_iterable(indexes, index_name, values, rec):
    for value in values or []:
        _index_target_record_text(indexes, index_name, value, rec)


def _update_target_record_identity_indexes(indexes, rec):
    target_id = str(rec.get("target_id") or "")
    if target_id:
        indexes["by_id"][target_id] = rec
    _index_target_record_text(indexes, "by_label", rec.get("label"), rec)
    indexes["by_has_notes"].setdefault(
        "yes" if str(rec.get("notes") or "").strip() else "no", []
    ).append(rec)
    _index_target_record_text(indexes, "by_identity_confidence", rec.get("identity_confidence"), rec)
    _index_target_record_iterable(indexes, "by_identity_source", rec.get("identity_sources"), rec)
    _index_target_record_text(indexes, "by_connectivity_state", rec.get("connectivity_state"), rec)
    _index_target_record_text(indexes, "by_last_seen_via", rec.get("last_seen_via"), rec)
    _index_target_record_text(indexes, "by_offline_age_bucket", rec.get("offline_age_bucket"), rec)
    _update_target_record_presence_indexes(indexes, rec)
    _update_target_record_phone_home_indexes(indexes, rec)
    _index_target_record_iterable(indexes, "by_alias", rec.get("aliases"), rec)
    _index_target_record_iterable(indexes, "by_remote_addr", rec.get("remote_addresses"), rec)
    _index_target_record_iterable(indexes, "by_service", rec.get("services_seen"), rec)


def _update_target_record_presence_indexes(indexes, rec):
    indexes["by_has_next_expected_poll"].setdefault(
        "yes" if str(rec.get("next_expected_poll") or "") else "no", []
    ).append(rec)
    indexes["by_poll_overdue"].setdefault(
        "yes" if rec.get("poll_overdue") is True else "no", []
    ).append(rec)
    indexes["by_mailbox_pending_work"].setdefault(
        "yes" if int(rec.get("mailbox_pending_work_count") or 0) > 0 else "no", []
    ).append(rec)


def _update_target_record_phone_home_indexes(indexes, rec):
    indexes["by_has_last_failed_phone_home"].setdefault(
        "yes" if rec.get("has_last_failed_phone_home") is True else "no", []
    ).append(rec)
    _index_target_record_text(
        indexes,
        "by_latest_phone_home_status",
        rec.get("latest_phone_home_status"),
        rec,
    )
    _index_target_record_text(
        indexes,
        "by_last_failed_phone_home_status",
        rec.get("last_failed_phone_home_status"),
        rec,
    )
    _index_target_record_text(
        indexes,
        "by_last_failed_phone_home_reason",
        rec.get("last_failed_phone_home_reason"),
        rec,
    )


def _target_record_identity_index_tuple(indexes):
    return (
        indexes["by_id"],
        indexes["by_label"],
        indexes["by_alias"],
        indexes["by_remote_addr"],
        indexes["by_service"],
        indexes["by_identity_confidence"],
        indexes["by_identity_source"],
        indexes["by_connectivity_state"],
        indexes["by_last_seen_via"],
        indexes["by_offline_age_bucket"],
        indexes["by_has_next_expected_poll"],
        indexes["by_poll_overdue"],
        indexes["by_mailbox_pending_work"],
        indexes["by_latest_phone_home_status"],
        indexes["by_has_last_failed_phone_home"],
        indexes["by_last_failed_phone_home_reason"],
        indexes["by_last_failed_phone_home_status"],
        indexes["by_has_notes"],
    )


def _target_record_identity_indexes(records):
    indexes = _empty_target_record_identity_indexes()
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        _update_target_record_identity_indexes(indexes, rec)
    return _target_record_identity_index_tuple(indexes)


def target_record_indexes(records):
    (
        by_id,
        by_label,
        by_alias,
        by_remote_addr,
        by_service,
        by_identity_confidence,
        by_identity_source,
        by_connectivity_state,
        by_last_seen_via,
        by_offline_age_bucket,
        by_has_next_expected_poll,
        by_poll_overdue,
        by_mailbox_pending_work,
        by_latest_phone_home_status,
        by_has_last_failed_phone_home,
        by_last_failed_phone_home_reason,
        by_last_failed_phone_home_status,
        by_has_notes,
    ) = _target_record_identity_indexes(records)
    (
        by_latest_activity_service,
        by_latest_activity_operation,
        by_latest_file_transfer_operation,
        by_latest_file_transfer_status,
        by_latest_file_transfer_route_kind,
        by_latest_file_transfer_bridge_profile,
        by_latest_survey_result_kind,
        by_latest_survey_result_status,
        by_latest_survey_result_route_kind,
        by_latest_survey_result_bridge_profile,
        by_latest_bridge_profile,
        by_latest_bridge_status,
        by_has_latest_bridge_activity,
    ) = _target_record_activity_indexes(records)
    (
        by_capability_report_kind,
        by_compatibility_report_kind,
        by_compatibility_label,
        by_compatibility_baseline_label,
        by_compatibility_release,
        by_compatibility_payload_preset,
        by_observed_capability,
        by_missing_capability,
        by_observed_constraint,
    ) = _target_record_report_indexes(records)
    return (
        by_id, by_label, by_alias, by_remote_addr, by_service,
        by_identity_confidence, by_identity_source,
        by_latest_activity_service, by_latest_activity_operation,
        by_connectivity_state, by_last_seen_via, by_offline_age_bucket,
        by_has_next_expected_poll, by_poll_overdue, by_mailbox_pending_work,
        by_latest_phone_home_status, by_has_last_failed_phone_home,
        by_last_failed_phone_home_reason, by_last_failed_phone_home_status,
        by_latest_file_transfer_operation, by_latest_file_transfer_status,
        by_latest_file_transfer_route_kind, by_latest_file_transfer_bridge_profile,
        by_latest_survey_result_kind, by_latest_survey_result_status,
        by_latest_survey_result_route_kind, by_latest_survey_result_bridge_profile,
        by_latest_bridge_profile, by_latest_bridge_status,
        by_has_latest_bridge_activity,
        by_has_notes, by_capability_report_kind,
        by_compatibility_report_kind, by_compatibility_label,
        by_compatibility_baseline_label, by_compatibility_release,
        by_compatibility_payload_preset, by_observed_capability,
        by_missing_capability, by_observed_constraint,
    )


def _target_record_report_summary(records):
    report_kind_counts = {}
    compatibility_report_kind_counts = {}
    compatibility_label_counts = {}
    compatibility_baseline_label_counts = {}
    compatibility_release_counts = {}
    compatibility_payload_preset_counts = {}
    observed_capability_counts = {}
    missing_capability_counts = {}
    observed_constraint_counts = {}
    report_count = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        report_kind = str(rec.get("latest_capability_report_kind") or "")
        if report_kind:
            report_kind_counts[report_kind] = report_kind_counts.get(report_kind, 0) + 1
        if rec.get("latest_capability_report") or rec.get("latest_capability_report_path"):
            report_count += 1
        if rec.get("latest_compatibility_report") or rec.get("latest_compatibility_report_path"):
            compatibility_report_kind = str(rec.get("latest_compatibility_report_kind") or "")
            if compatibility_report_kind:
                compatibility_report_kind_counts[compatibility_report_kind] = compatibility_report_kind_counts.get(compatibility_report_kind, 0) + 1
            compatibility_label = str(rec.get("latest_compatibility_label") or "")
            if compatibility_label:
                compatibility_label_counts[compatibility_label] = compatibility_label_counts.get(compatibility_label, 0) + 1
            compatibility_baseline = str(rec.get("latest_compatibility_baseline_label") or "")
            if compatibility_baseline:
                compatibility_baseline_label_counts[compatibility_baseline] = compatibility_baseline_label_counts.get(compatibility_baseline, 0) + 1
            compatibility_release = str(rec.get("latest_compatibility_release_name") or "")
            if compatibility_release:
                compatibility_release_counts[compatibility_release] = compatibility_release_counts.get(compatibility_release, 0) + 1
            compatibility_payload = str(rec.get("latest_compatibility_payload_preset") or "")
            if compatibility_payload:
                compatibility_payload_preset_counts[compatibility_payload] = compatibility_payload_preset_counts.get(compatibility_payload, 0) + 1
        for capability in rec.get("observed_capabilities") or []:
            capability = str(capability or "")
            if capability:
                observed_capability_counts[capability] = observed_capability_counts.get(capability, 0) + 1
        for capability in rec.get("observed_missing_capabilities") or []:
            capability = str(capability or "")
            if capability:
                missing_capability_counts[capability] = missing_capability_counts.get(capability, 0) + 1
        constraints = rec.get("observed_constraints") if isinstance(rec.get("observed_constraints"), dict) else {}
        for name, value in sorted(constraints.items()):
            name = str(name or "")
            if name:
                key = f"{name}:{str(bool(value)).lower()}"
                observed_constraint_counts[key] = observed_constraint_counts.get(key, 0) + 1
    return {
        "report_count": report_count,
        "report_kind_counts": report_kind_counts,
        "compatibility_report_kind_counts": compatibility_report_kind_counts,
        "compatibility_label_counts": compatibility_label_counts,
        "compatibility_baseline_label_counts": compatibility_baseline_label_counts,
        "compatibility_release_counts": compatibility_release_counts,
        "compatibility_payload_preset_counts": compatibility_payload_preset_counts,
        "observed_capability_counts": observed_capability_counts,
        "missing_capability_counts": missing_capability_counts,
        "observed_constraint_counts": observed_constraint_counts,
    }


def _count_text_value(counts, value):
    value = str(value or "")
    if value:
        counts[value] = counts.get(value, 0) + 1


def _empty_target_record_activity_summary():
    return {
        "service_counts": {},
        "identity_source_counts": {},
        "latest_activity_service_counts": {},
        "latest_activity_operation_counts": {},
        "connectivity_state_counts": {},
        "last_seen_via_counts": {},
        "offline_age_bucket_counts": {},
        "latest_file_transfer_operation_counts": {},
        "latest_file_transfer_status_counts": {},
        "latest_file_transfer_route_kind_counts": {},
        "latest_file_transfer_bridge_profile_counts": {},
        "latest_survey_result_kind_counts": {},
        "latest_survey_result_status_counts": {},
        "latest_survey_result_route_kind_counts": {},
        "latest_survey_result_bridge_profile_counts": {},
        "latest_bridge_profile_counts": {},
        "latest_bridge_status_counts": {},
        "remote_count": 0,
        "notes_count": 0,
        "next_expected_poll_count": 0,
        "poll_overdue_count": 0,
        "mailbox_pending_target_count": 0,
        "mailbox_pending_work_count": 0,
        "phone_home_target_count": 0,
        "failed_phone_home_target_count": 0,
        "successful_phone_home_count": 0,
        "failed_phone_home_count": 0,
        "latest_file_transfer_count": 0,
        "latest_survey_result_count": 0,
        "latest_bridge_activity_count": 0,
    }


def _update_target_identity_activity_summary(summary, rec):
    if str(rec.get("notes") or "").strip():
        summary["notes_count"] += 1
    summary["remote_count"] += len(rec.get("remote_addresses") or [])
    for service in rec.get("services_seen") or []:
        _count_text_value(summary["service_counts"], service)
    for source in rec.get("identity_sources") or []:
        _count_text_value(summary["identity_source_counts"], source)
    _count_text_value(summary["latest_activity_service_counts"], rec.get("latest_activity_service"))
    _count_text_value(summary["latest_activity_operation_counts"], rec.get("latest_activity_operation"))
    _count_text_value(summary["connectivity_state_counts"], rec.get("connectivity_state"))
    _count_text_value(summary["last_seen_via_counts"], rec.get("last_seen_via"))
    _count_text_value(summary["offline_age_bucket_counts"], rec.get("offline_age_bucket"))
    if str(rec.get("next_expected_poll") or ""):
        summary["next_expected_poll_count"] += 1
    if rec.get("poll_overdue") is True:
        summary["poll_overdue_count"] += 1


def _update_target_mailbox_phone_home_summary(summary, rec):
    pending_work = int(rec.get("mailbox_pending_work_count") or 0)
    summary["mailbox_pending_work_count"] += pending_work
    if pending_work > 0:
        summary["mailbox_pending_target_count"] += 1
    if int(rec.get("phone_home_record_count") or 0) > 0:
        summary["phone_home_target_count"] += 1
    failed_count = int(rec.get("failed_phone_home_count") or 0)
    summary["successful_phone_home_count"] += int(rec.get("successful_phone_home_count") or 0)
    summary["failed_phone_home_count"] += failed_count
    if failed_count > 0:
        summary["failed_phone_home_target_count"] += 1


def _update_target_file_transfer_summary(summary, rec):
    if not str(rec.get("latest_file_transfer_at") or ""):
        return
    summary["latest_file_transfer_count"] += 1
    _count_text_value(
        summary["latest_file_transfer_operation_counts"],
        rec.get("latest_file_transfer_operation"),
    )
    _count_text_value(summary["latest_file_transfer_status_counts"], rec.get("latest_file_transfer_status"))
    _count_text_value(summary["latest_file_transfer_route_kind_counts"], rec.get("latest_file_transfer_route_kind"))
    _count_text_value(
        summary["latest_file_transfer_bridge_profile_counts"],
        rec.get("latest_file_transfer_bridge_profile"),
    )


def _update_target_survey_summary(summary, rec):
    if not str(rec.get("latest_survey_result_at") or ""):
        return
    summary["latest_survey_result_count"] += 1
    _count_text_value(summary["latest_survey_result_kind_counts"], rec.get("latest_survey_result_kind"))
    _count_text_value(summary["latest_survey_result_status_counts"], rec.get("latest_survey_result_status"))
    _count_text_value(summary["latest_survey_result_route_kind_counts"], rec.get("latest_survey_result_route_kind"))
    _count_text_value(
        summary["latest_survey_result_bridge_profile_counts"],
        rec.get("latest_survey_result_bridge_profile"),
    )


def _update_target_bridge_summary(summary, rec):
    if not str(rec.get("latest_bridge_activity_at") or ""):
        return
    summary["latest_bridge_activity_count"] += 1
    _count_text_value(summary["latest_bridge_profile_counts"], rec.get("latest_bridge_profile"))
    _count_text_value(summary["latest_bridge_status_counts"], rec.get("latest_bridge_status"))


def _target_record_activity_summary(records):
    summary = _empty_target_record_activity_summary()
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        _update_target_identity_activity_summary(summary, rec)
        _update_target_mailbox_phone_home_summary(summary, rec)
        _update_target_file_transfer_summary(summary, rec)
        _update_target_survey_summary(summary, rec)
        _update_target_bridge_summary(summary, rec)
    return summary


def target_record_summary(records):
    latest = (records or [{}])[0] if records else {}
    activity_summary = _target_record_activity_summary(records)
    report_summary = _target_record_report_summary(records)
    return {
        "target_count": len(records or []),
        "latest_target_id": latest.get("target_id", ""),
        "latest_target_label": latest.get("label", ""),
        "latest_target_seen_at": latest.get("last_seen_at", ""),
        "target_identity_confidence_counts": record_count_by_key(records, "identity_confidence"),
        "target_identity_source_counts": activity_summary["identity_source_counts"],
        "target_service_counts": activity_summary["service_counts"],
        "target_remote_address_count": activity_summary["remote_count"],
        "target_notes_count": activity_summary["notes_count"],
        "target_without_notes_count": max(len(records or []) - activity_summary["notes_count"], 0),
        "target_latest_activity_service_counts": activity_summary["latest_activity_service_counts"],
        "target_latest_activity_operation_counts": activity_summary["latest_activity_operation_counts"],
        "target_connectivity_state_counts": activity_summary["connectivity_state_counts"],
        "target_last_seen_via_counts": activity_summary["last_seen_via_counts"],
        "target_offline_age_bucket_counts": activity_summary["offline_age_bucket_counts"],
        "target_next_expected_poll_count": activity_summary["next_expected_poll_count"],
        "target_poll_overdue_count": activity_summary["poll_overdue_count"],
        "target_poll_overdue_counts": record_count_by_key(records, "poll_overdue"),
        "target_mailbox_pending_target_count": activity_summary["mailbox_pending_target_count"],
        "target_mailbox_pending_work_count": activity_summary["mailbox_pending_work_count"],
        "target_phone_home_target_count": activity_summary["phone_home_target_count"],
        "target_successful_phone_home_count": activity_summary["successful_phone_home_count"],
        "target_failed_phone_home_count": activity_summary["failed_phone_home_count"],
        "target_failed_phone_home_target_count": activity_summary["failed_phone_home_target_count"],
        "target_latest_phone_home_status_counts": record_count_by_key(records, "latest_phone_home_status"),
        "target_has_last_failed_phone_home_counts": record_count_by_key(records, "has_last_failed_phone_home"),
        "target_last_failed_phone_home_status_counts": record_count_by_key(records, "last_failed_phone_home_status"),
        "target_last_failed_phone_home_reason_counts": record_count_by_key(records, "last_failed_phone_home_reason"),
        "target_latest_file_transfer_count": activity_summary["latest_file_transfer_count"],
        "target_latest_file_transfer_operation_counts": activity_summary["latest_file_transfer_operation_counts"],
        "target_latest_file_transfer_status_counts": activity_summary["latest_file_transfer_status_counts"],
        "target_latest_file_transfer_route_kind_counts": activity_summary["latest_file_transfer_route_kind_counts"],
        "target_latest_file_transfer_bridge_profile_counts": activity_summary["latest_file_transfer_bridge_profile_counts"],
        "target_latest_survey_result_count": activity_summary["latest_survey_result_count"],
        "target_latest_survey_result_kind_counts": activity_summary["latest_survey_result_kind_counts"],
        "target_latest_survey_result_status_counts": activity_summary["latest_survey_result_status_counts"],
        "target_latest_survey_result_route_kind_counts": activity_summary["latest_survey_result_route_kind_counts"],
        "target_latest_survey_result_bridge_profile_counts": activity_summary["latest_survey_result_bridge_profile_counts"],
        "target_latest_bridge_activity_count": activity_summary["latest_bridge_activity_count"],
        "target_latest_bridge_profile_counts": activity_summary["latest_bridge_profile_counts"],
        "target_latest_bridge_status_counts": activity_summary["latest_bridge_status_counts"],
        "target_capability_report_count": report_summary["report_count"],
        "target_capability_report_kind_counts": report_summary["report_kind_counts"],
        "target_compatibility_report_count": sum(report_summary["compatibility_report_kind_counts"].values()),
        "target_compatibility_report_kind_counts": report_summary["compatibility_report_kind_counts"],
        "target_compatibility_label_counts": report_summary["compatibility_label_counts"],
        "target_compatibility_baseline_label_counts": report_summary["compatibility_baseline_label_counts"],
        "target_compatibility_release_counts": report_summary["compatibility_release_counts"],
        "target_compatibility_payload_preset_counts": report_summary["compatibility_payload_preset_counts"],
        "target_observed_capability_counts": report_summary["observed_capability_counts"],
        "target_missing_capability_counts": report_summary["missing_capability_counts"],
        "target_observed_constraint_counts": report_summary["observed_constraint_counts"],
    }
