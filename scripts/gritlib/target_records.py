"""Target record index and summary helpers for grit-console."""

def record_count_by_key(records, key):
    counts = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        value = rec.get(key)
        if value in (None, ""):
            continue
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return counts


def target_record_indexes(records):
    by_id = {}
    by_label = {}
    by_alias = {}
    by_remote_addr = {}
    by_service = {}
    by_identity_confidence = {}
    by_identity_source = {}
    by_latest_activity_service = {}
    by_latest_activity_operation = {}
    by_connectivity_state = {}
    by_last_seen_via = {}
    by_offline_age_bucket = {}
    by_has_next_expected_poll = {}
    by_poll_overdue = {}
    by_mailbox_pending_work = {}
    by_latest_phone_home_status = {}
    by_has_last_failed_phone_home = {}
    by_last_failed_phone_home_reason = {}
    by_last_failed_phone_home_status = {}
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
    by_has_notes = {}
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
        target_id = str(rec.get("target_id") or "")
        if target_id:
            by_id[target_id] = rec
        label = str(rec.get("label") or "")
        if label:
            by_label.setdefault(label, []).append(rec)
        by_has_notes.setdefault("yes" if str(rec.get("notes") or "").strip() else "no", []).append(rec)
        confidence = str(rec.get("identity_confidence") or "")
        if confidence:
            by_identity_confidence.setdefault(confidence, []).append(rec)
        for source in rec.get("identity_sources") or []:
            source = str(source or "")
            if source:
                by_identity_source.setdefault(source, []).append(rec)
        activity_service = str(rec.get("latest_activity_service") or "")
        if activity_service:
            by_latest_activity_service.setdefault(activity_service, []).append(rec)
        activity_operation = str(rec.get("latest_activity_operation") or "")
        if activity_operation:
            by_latest_activity_operation.setdefault(activity_operation, []).append(rec)
        connectivity_state = str(rec.get("connectivity_state") or "")
        if connectivity_state:
            by_connectivity_state.setdefault(connectivity_state, []).append(rec)
        last_seen_via = str(rec.get("last_seen_via") or "")
        if last_seen_via:
            by_last_seen_via.setdefault(last_seen_via, []).append(rec)
        offline_age_bucket = str(rec.get("offline_age_bucket") or "")
        if offline_age_bucket:
            by_offline_age_bucket.setdefault(offline_age_bucket, []).append(rec)
        by_has_next_expected_poll.setdefault("yes" if str(rec.get("next_expected_poll") or "") else "no", []).append(rec)
        by_poll_overdue.setdefault("yes" if rec.get("poll_overdue") is True else "no", []).append(rec)
        by_mailbox_pending_work.setdefault("yes" if int(rec.get("mailbox_pending_work_count") or 0) > 0 else "no", []).append(rec)
        by_has_last_failed_phone_home.setdefault("yes" if rec.get("has_last_failed_phone_home") is True else "no", []).append(rec)
        latest_phone_home_status = str(rec.get("latest_phone_home_status") or "")
        if latest_phone_home_status:
            by_latest_phone_home_status.setdefault(latest_phone_home_status, []).append(rec)
        last_failed_status = str(rec.get("last_failed_phone_home_status") or "")
        if last_failed_status:
            by_last_failed_phone_home_status.setdefault(last_failed_status, []).append(rec)
        last_failed_reason = str(rec.get("last_failed_phone_home_reason") or "")
        if last_failed_reason:
            by_last_failed_phone_home_reason.setdefault(last_failed_reason, []).append(rec)
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
        for alias in rec.get("aliases") or []:
            alias = str(alias or "")
            if alias:
                by_alias.setdefault(alias, []).append(rec)
        for remote in rec.get("remote_addresses") or []:
            remote = str(remote or "")
            if remote:
                by_remote_addr.setdefault(remote, []).append(rec)
        for service in rec.get("services_seen") or []:
            service = str(service or "")
            if service:
                by_service.setdefault(service, []).append(rec)
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


def target_record_summary(records):
    latest = (records or [{}])[0] if records else {}
    service_counts = {}
    identity_source_counts = {}
    latest_activity_service_counts = {}
    latest_activity_operation_counts = {}
    connectivity_state_counts = {}
    last_seen_via_counts = {}
    offline_age_bucket_counts = {}
    latest_file_transfer_operation_counts = {}
    latest_file_transfer_status_counts = {}
    latest_file_transfer_route_kind_counts = {}
    latest_file_transfer_bridge_profile_counts = {}
    latest_survey_result_kind_counts = {}
    latest_survey_result_status_counts = {}
    latest_survey_result_route_kind_counts = {}
    latest_survey_result_bridge_profile_counts = {}
    latest_bridge_profile_counts = {}
    latest_bridge_status_counts = {}
    report_kind_counts = {}
    compatibility_report_kind_counts = {}
    compatibility_label_counts = {}
    compatibility_baseline_label_counts = {}
    compatibility_release_counts = {}
    compatibility_payload_preset_counts = {}
    observed_capability_counts = {}
    missing_capability_counts = {}
    observed_constraint_counts = {}
    remote_count = 0
    report_count = 0
    notes_count = 0
    next_expected_poll_count = 0
    poll_overdue_count = 0
    mailbox_pending_target_count = 0
    mailbox_pending_work_count = 0
    phone_home_target_count = 0
    failed_phone_home_target_count = 0
    successful_phone_home_count = 0
    failed_phone_home_count = 0
    latest_file_transfer_count = 0
    latest_survey_result_count = 0
    latest_bridge_activity_count = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("notes") or "").strip():
            notes_count += 1
        remote_count += len(rec.get("remote_addresses") or [])
        for service in rec.get("services_seen") or []:
            service = str(service or "")
            if service:
                service_counts[service] = service_counts.get(service, 0) + 1
        for source in rec.get("identity_sources") or []:
            source = str(source or "")
            if source:
                identity_source_counts[source] = identity_source_counts.get(source, 0) + 1
        activity_service = str(rec.get("latest_activity_service") or "")
        if activity_service:
            latest_activity_service_counts[activity_service] = latest_activity_service_counts.get(activity_service, 0) + 1
        activity_operation = str(rec.get("latest_activity_operation") or "")
        if activity_operation:
            latest_activity_operation_counts[activity_operation] = latest_activity_operation_counts.get(activity_operation, 0) + 1
        connectivity_state = str(rec.get("connectivity_state") or "")
        if connectivity_state:
            connectivity_state_counts[connectivity_state] = connectivity_state_counts.get(connectivity_state, 0) + 1
        last_seen_via = str(rec.get("last_seen_via") or "")
        if last_seen_via:
            last_seen_via_counts[last_seen_via] = last_seen_via_counts.get(last_seen_via, 0) + 1
        offline_age_bucket = str(rec.get("offline_age_bucket") or "")
        if offline_age_bucket:
            offline_age_bucket_counts[offline_age_bucket] = offline_age_bucket_counts.get(offline_age_bucket, 0) + 1
        if str(rec.get("next_expected_poll") or ""):
            next_expected_poll_count += 1
        if rec.get("poll_overdue") is True:
            poll_overdue_count += 1
        pending_work = int(rec.get("mailbox_pending_work_count") or 0)
        mailbox_pending_work_count += pending_work
        if pending_work > 0:
            mailbox_pending_target_count += 1
        phone_home_count = int(rec.get("phone_home_record_count") or 0)
        if phone_home_count > 0:
            phone_home_target_count += 1
        failed_count = int(rec.get("failed_phone_home_count") or 0)
        successful_phone_home_count += int(rec.get("successful_phone_home_count") or 0)
        failed_phone_home_count += failed_count
        if failed_count > 0:
            failed_phone_home_target_count += 1
        if str(rec.get("latest_file_transfer_at") or ""):
            latest_file_transfer_count += 1
            file_operation = str(rec.get("latest_file_transfer_operation") or "")
            if file_operation:
                latest_file_transfer_operation_counts[file_operation] = latest_file_transfer_operation_counts.get(file_operation, 0) + 1
            file_status = str(rec.get("latest_file_transfer_status") or "")
            if file_status:
                latest_file_transfer_status_counts[file_status] = latest_file_transfer_status_counts.get(file_status, 0) + 1
            file_route_kind = str(rec.get("latest_file_transfer_route_kind") or "")
            if file_route_kind:
                latest_file_transfer_route_kind_counts[file_route_kind] = latest_file_transfer_route_kind_counts.get(file_route_kind, 0) + 1
            file_bridge_profile = str(rec.get("latest_file_transfer_bridge_profile") or "")
            if file_bridge_profile:
                latest_file_transfer_bridge_profile_counts[file_bridge_profile] = latest_file_transfer_bridge_profile_counts.get(file_bridge_profile, 0) + 1
        if str(rec.get("latest_survey_result_at") or ""):
            latest_survey_result_count += 1
            survey_kind = str(rec.get("latest_survey_result_kind") or "")
            if survey_kind:
                latest_survey_result_kind_counts[survey_kind] = latest_survey_result_kind_counts.get(survey_kind, 0) + 1
            survey_status = str(rec.get("latest_survey_result_status") or "")
            if survey_status:
                latest_survey_result_status_counts[survey_status] = latest_survey_result_status_counts.get(survey_status, 0) + 1
            survey_route_kind = str(rec.get("latest_survey_result_route_kind") or "")
            if survey_route_kind:
                latest_survey_result_route_kind_counts[survey_route_kind] = latest_survey_result_route_kind_counts.get(survey_route_kind, 0) + 1
            survey_bridge_profile = str(rec.get("latest_survey_result_bridge_profile") or "")
            if survey_bridge_profile:
                latest_survey_result_bridge_profile_counts[survey_bridge_profile] = latest_survey_result_bridge_profile_counts.get(survey_bridge_profile, 0) + 1
        if str(rec.get("latest_bridge_activity_at") or ""):
            latest_bridge_activity_count += 1
            bridge_profile = str(rec.get("latest_bridge_profile") or "")
            if bridge_profile:
                latest_bridge_profile_counts[bridge_profile] = latest_bridge_profile_counts.get(bridge_profile, 0) + 1
            bridge_status = str(rec.get("latest_bridge_status") or "")
            if bridge_status:
                latest_bridge_status_counts[bridge_status] = latest_bridge_status_counts.get(bridge_status, 0) + 1
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
        "target_count": len(records or []),
        "latest_target_id": latest.get("target_id", ""),
        "latest_target_label": latest.get("label", ""),
        "latest_target_seen_at": latest.get("last_seen_at", ""),
        "target_identity_confidence_counts": record_count_by_key(records, "identity_confidence"),
        "target_identity_source_counts": identity_source_counts,
        "target_service_counts": service_counts,
        "target_remote_address_count": remote_count,
        "target_notes_count": notes_count,
        "target_without_notes_count": max(len(records or []) - notes_count, 0),
        "target_latest_activity_service_counts": latest_activity_service_counts,
        "target_latest_activity_operation_counts": latest_activity_operation_counts,
        "target_connectivity_state_counts": connectivity_state_counts,
        "target_last_seen_via_counts": last_seen_via_counts,
        "target_offline_age_bucket_counts": offline_age_bucket_counts,
        "target_next_expected_poll_count": next_expected_poll_count,
        "target_poll_overdue_count": poll_overdue_count,
        "target_poll_overdue_counts": record_count_by_key(records, "poll_overdue"),
        "target_mailbox_pending_target_count": mailbox_pending_target_count,
        "target_mailbox_pending_work_count": mailbox_pending_work_count,
        "target_phone_home_target_count": phone_home_target_count,
        "target_successful_phone_home_count": successful_phone_home_count,
        "target_failed_phone_home_count": failed_phone_home_count,
        "target_failed_phone_home_target_count": failed_phone_home_target_count,
        "target_latest_phone_home_status_counts": record_count_by_key(records, "latest_phone_home_status"),
        "target_has_last_failed_phone_home_counts": record_count_by_key(records, "has_last_failed_phone_home"),
        "target_last_failed_phone_home_status_counts": record_count_by_key(records, "last_failed_phone_home_status"),
        "target_last_failed_phone_home_reason_counts": record_count_by_key(records, "last_failed_phone_home_reason"),
        "target_latest_file_transfer_count": latest_file_transfer_count,
        "target_latest_file_transfer_operation_counts": latest_file_transfer_operation_counts,
        "target_latest_file_transfer_status_counts": latest_file_transfer_status_counts,
        "target_latest_file_transfer_route_kind_counts": latest_file_transfer_route_kind_counts,
        "target_latest_file_transfer_bridge_profile_counts": latest_file_transfer_bridge_profile_counts,
        "target_latest_survey_result_count": latest_survey_result_count,
        "target_latest_survey_result_kind_counts": latest_survey_result_kind_counts,
        "target_latest_survey_result_status_counts": latest_survey_result_status_counts,
        "target_latest_survey_result_route_kind_counts": latest_survey_result_route_kind_counts,
        "target_latest_survey_result_bridge_profile_counts": latest_survey_result_bridge_profile_counts,
        "target_latest_bridge_activity_count": latest_bridge_activity_count,
        "target_latest_bridge_profile_counts": latest_bridge_profile_counts,
        "target_latest_bridge_status_counts": latest_bridge_status_counts,
        "target_capability_report_count": report_count,
        "target_capability_report_kind_counts": report_kind_counts,
        "target_compatibility_report_count": sum(compatibility_report_kind_counts.values()),
        "target_compatibility_report_kind_counts": compatibility_report_kind_counts,
        "target_compatibility_label_counts": compatibility_label_counts,
        "target_compatibility_baseline_label_counts": compatibility_baseline_label_counts,
        "target_compatibility_release_counts": compatibility_release_counts,
        "target_compatibility_payload_preset_counts": compatibility_payload_preset_counts,
        "target_observed_capability_counts": observed_capability_counts,
        "target_missing_capability_counts": missing_capability_counts,
        "target_observed_constraint_counts": observed_constraint_counts,
    }

