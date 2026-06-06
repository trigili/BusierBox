"""Target record human-output helpers for grit-console."""


def _print_target_summary_header(doc, records):
    print("Targets:")
    if not records:
        print("  none")
        return False
    summary = doc.get("summary") or {}
    print(
        f"  count={summary.get('target_count', len(records))} "
        f"latest={summary.get('latest_target_id') or '-'} "
        f"latest_seen={summary.get('latest_target_seen_at') or '-'}"
    )
    return True


def _print_target_record_identity(rec):
    print(
        f"  {rec.get('target_id', '')} label={rec.get('label', '') or '-'} "
        f"confidence={rec.get('identity_confidence', '') or '-'} "
        f"state={rec.get('connectivity_state', '') or '-'} "
        f"last_seen={rec.get('last_seen', '') or rec.get('last_seen_at', '') or '-'}"
    )


def _print_target_heartbeat(rec):
    if rec.get("last_seen_via") or rec.get("next_expected_poll") or rec.get("offline_for_sec") not in ("", None):
        print(
            f"    heartbeat_via={rec.get('last_seen_via', '') or '-'} "
            f"offline_for_sec={rec.get('offline_for_sec', '') if rec.get('offline_for_sec') != '' else '-'} "
            f"next_expected_poll={rec.get('next_expected_poll', '') or '-'} "
            f"poll_overdue={'yes' if rec.get('poll_overdue') else 'no'} "
            f"poll_overdue_for_sec={rec.get('poll_overdue_for_sec', '') if rec.get('poll_overdue_for_sec') != '' else '-'}"
        )


def _print_target_phone_home_summary(rec):
    if rec.get("latest_phone_home_at") or rec.get("last_failed_phone_home_at"):
        print(
            f"    phone_home_latest={rec.get('latest_phone_home_at', '') or '-'} "
            f"kind={rec.get('latest_phone_home_kind', '') or '-'} "
            f"status={rec.get('latest_phone_home_status', '') or '-'} "
            f"failed_last={rec.get('last_failed_phone_home_at', '') or '-'} "
            f"failed_status={rec.get('last_failed_phone_home_status', '') or '-'} "
            f"failed_reason={rec.get('last_failed_phone_home_reason', '') or '-'}"
        )


def _print_target_mailbox_commands(rec, mailbox_by_target):
    if int(rec.get("mailbox_command_count") or 0) <= 0:
        return
    print(
        f"    mailbox queued={rec.get('mailbox_queued_command_count', 0)} "
        f"delivered={rec.get('mailbox_delivered_command_count', 0)} "
        f"results={rec.get('mailbox_result_received_command_count', 0)} "
        f"expired={rec.get('mailbox_expired_command_count', 0)} "
        f"pending={rec.get('mailbox_pending_work_count', 0)}"
    )
    target_id = str(rec.get("target_id") or "")
    for item in (mailbox_by_target.get(target_id) or [])[:3]:
        command_text = str(item.get("command") or "").replace("\n", "\\n")
        if len(command_text) > 96:
            command_text = f"{command_text[:93]}..."
        result_status = item.get("result_status", "") or "-"
        result_exit = item.get("result_exit_code", "")
        result_exit_text = result_exit if result_exit != "" else "-"
        print(
            f"      mailbox_command {item.get('command_id', '')} "
            f"status={item.get('status', '') or '-'} "
            f"waiting_for={item.get('waiting_for', '') or '-'} "
            f"reason={item.get('pending_reason', '') or '-'} "
            f"expired={'yes' if item.get('expired') else 'no'} "
            f"result={item.get('result_status', '') or '-'} "
            f"exit={item.get('result_exit_code', '') if item.get('result_exit_code') != '' else '-'} "
            f"age_sec={item.get('age_sec', '') if item.get('age_sec') != '' else '-'} "
            f"created={item.get('created_at', '') or '-'} "
            f"delivered={item.get('delivered_at', '') or '-'} "
            f"expires={item.get('expires_at', '') or '-'} "
            f"result_at={item.get('result_received_at', '') or '-'} "
            f"command={command_text}"
        )
        if item.get("status") == "result-received":
            print(
                f"      summary: status={item.get('status', '') or '-'} "
                f"result={result_status} exit={result_exit_text}"
            )


def _print_target_latest_activity(rec):
    if rec.get("latest_activity_operation") or rec.get("latest_activity_service"):
        print(
            f"    latest_activity={rec.get('latest_activity_operation', '') or '-'} "
            f"service={rec.get('latest_activity_service', '') or '-'} "
            f"remote={rec.get('latest_activity_remote_addr', '') or '-'} "
            f"at={rec.get('latest_activity_at', '') or '-'}"
        )


def _print_target_phone_home_attempts(rec, phone_home_by_target):
    target_id = str(rec.get("target_id") or "")
    for attempt in (phone_home_by_target.get(target_id) or [])[:3]:
        reason = attempt.get("pending_reason") or attempt.get("reason") or ""
        reason_text = f" reason={reason}" if reason else ""
        command = f" command={attempt.get('command_id', '')}" if attempt.get("command_id") else ""
        target_state = (
            f" target_state={attempt.get('target_connectivity_state', '')}"
            if attempt.get("target_connectivity_state") else ""
        )
        offline_age = (
            f" offline_age={attempt.get('target_offline_age_bucket', '')}"
            if attempt.get("target_offline_age_bucket") else ""
        )
        remaining = (
            f" queued_remaining={attempt.get('queued_remaining_count')}"
            if attempt.get("queued_remaining_count") != "" else ""
        )
        print(
            f"    phone_home {attempt.get('timestamp', '') or '-'} "
            f"{attempt.get('kind', '') or '-'} status={attempt.get('status', '') or '-'} "
            f"via={attempt.get('contact_path', '') or '-'}{target_state}{offline_age}{command}{remaining}{reason_text}"
        )


def _print_target_aliases_notes_and_latest_refs(rec):
    aliases = ",".join(str(item) for item in rec.get("aliases") or []) or "-"
    remotes = ",".join(str(item) for item in rec.get("remote_addresses") or []) or "-"
    services = ",".join(str(item) for item in rec.get("services_seen") or []) or "-"
    print(f"    aliases={aliases} services={services} remotes={remotes}")
    if str(rec.get("notes") or "").strip():
        print(f"    notes={str(rec.get('notes') or '').strip()}")
    if rec.get("latest_upload_id") or rec.get("latest_fetch_id") or rec.get("latest_session_id"):
        print(
            f"    latest_session={rec.get('latest_session_id', '') or '-'} "
            f"latest_upload={rec.get('latest_upload_id', '') or '-'} "
            f"latest_fetch={rec.get('latest_fetch_id', '') or '-'}"
        )


def _print_target_latest_file_transfer(rec):
    if rec.get("latest_file_transfer_at"):
        file_route = f"{rec.get('latest_file_transfer_route_kind', '') or '-'}"
        if rec.get("latest_file_transfer_bridge_profile"):
            file_route += f" bridge_profile={rec.get('latest_file_transfer_bridge_profile', '')}"
        if rec.get("latest_file_transfer_bridge_route_path"):
            file_route += f" path={rec.get('latest_file_transfer_bridge_route_path', '')}"
        print(
            f"    latest_file_transfer={rec.get('latest_file_transfer_operation', '') or '-'} "
            f"status={rec.get('latest_file_transfer_status', '') or '-'} "
            f"at={rec.get('latest_file_transfer_at', '') or '-'} "
            f"id={rec.get('latest_file_transfer_id', '') or '-'} "
            f"route={file_route}"
        )


def _print_target_file_transfers(rec, file_transfers_by_target):
    target_id = str(rec.get("target_id") or "")
    for item in (file_transfers_by_target.get(target_id) or [])[:3]:
        transfer_route = str(item.get("route_kind") or "-")
        if item.get("bridge_profile"):
            transfer_route += f" bridge_profile={item.get('bridge_profile', '')}"
        label = item.get("filename") or item.get("request_name") or item.get("source_path") or item.get("stored_path") or "-"
        print(
            f"      file_transfer {item.get('operation', '') or '-'} "
            f"status={item.get('status', '') or '-'} "
            f"at={item.get('timestamp', '') or '-'} "
            f"name={label} route={transfer_route}"
        )


def _representative_target_activity(activity_items):
    representative_activity = []
    seen_categories = set()
    preferred_categories = ("mailbox", "phone-home", "heartbeat", "file-transfer", "session")
    for category in preferred_categories:
        for item in activity_items:
            if item.get("category") == category and category not in seen_categories:
                representative_activity.append(item)
                seen_categories.add(category)
                break
        if len(representative_activity) >= 4:
            break
    for item in activity_items:
        if len(representative_activity) >= 4:
            break
        if item in representative_activity:
            continue
        representative_activity.append(item)
    return representative_activity


def _print_target_activity_items(rec, activity_by_target):
    target_id = str(rec.get("target_id") or "")
    activity_items = list(activity_by_target.get(target_id) or [])
    for item in _representative_target_activity(activity_items):
        print(
            f"      activity {item.get('category', '') or '-'} "
            f"{item.get('operation', '') or '-'} status={item.get('status', '') or '-'} "
            f"target_state={item.get('target_connectivity_state', '') or '-'} "
            f"offline_age={item.get('target_offline_age_bucket', '') or '-'} "
            f"at={item.get('timestamp', '') or '-'} waiting_for={item.get('waiting_for', '') or '-'}"
        )


def _print_target_survey_and_bridge(rec):
    if rec.get("latest_survey_result_at"):
        survey_route = f"{rec.get('latest_survey_result_route_kind', '') or '-'}"
        if rec.get("latest_survey_result_bridge_profile"):
            survey_route += f" bridge_profile={rec.get('latest_survey_result_bridge_profile', '')}"
        if rec.get("latest_survey_result_bridge_route_path"):
            survey_route += f" path={rec.get('latest_survey_result_bridge_route_path', '')}"
        print(
            f"    latest_survey_result={rec.get('latest_survey_result_kind', '') or '-'} "
            f"status={rec.get('latest_survey_result_status', '') or '-'} "
            f"at={rec.get('latest_survey_result_at', '') or '-'} "
            f"id={rec.get('latest_survey_result_id', '') or '-'} "
            f"route={survey_route}"
        )
    if rec.get("latest_bridge_activity_at"):
        print(
            f"    latest_bridge={rec.get('latest_bridge_profile', '') or '-'} "
            f"operation={rec.get('latest_bridge_operation', '') or '-'} "
            f"status={rec.get('latest_bridge_status', '') or '-'} "
            f"at={rec.get('latest_bridge_activity_at', '') or '-'} "
            f"route={rec.get('latest_bridge_route_path', '') or '-'} "
            f"failure={rec.get('latest_bridge_failure_reason', '') or '-'}"
        )


def _print_target_capability_and_compatibility(rec):
    if rec.get("latest_capability_report_kind") or rec.get("observed_capabilities") or rec.get("observed_missing_capabilities"):
        available = ",".join(str(item) for item in rec.get("observed_capabilities") or []) or "-"
        missing = ",".join(str(item) for item in rec.get("observed_missing_capabilities") or []) or "-"
        constraints = rec.get("observed_constraints") if isinstance(rec.get("observed_constraints"), dict) else {}
        constraint_text = ",".join(
            f"{name}:{str(bool(value)).lower()}" for name, value in sorted(constraints.items())
        ) or "-"
        print(
            f"    capability_report={rec.get('latest_capability_report_kind', '') or '-'} "
            f"available={available} missing={missing} constraints={constraint_text}"
        )
    if rec.get("latest_compatibility_label"):
        print(
            f"    compatibility_report={rec.get('latest_compatibility_report_kind', '') or '-'} "
            f"label={rec.get('latest_compatibility_label', '') or '-'} "
            f"baseline={rec.get('latest_compatibility_baseline_label', '') or '-'} "
            f"release={rec.get('latest_compatibility_release_name', '') or '-'} "
            f"payload={rec.get('latest_compatibility_payload_preset', '') or '-'}"
        )


def _print_target_record_summary(
    rec,
    mailbox_by_target,
    phone_home_by_target,
    file_transfers_by_target,
    activity_by_target,
):
    _print_target_record_identity(rec)
    _print_target_heartbeat(rec)
    _print_target_phone_home_summary(rec)
    _print_target_mailbox_commands(rec, mailbox_by_target)
    _print_target_latest_activity(rec)
    _print_target_phone_home_attempts(rec, phone_home_by_target)
    _print_target_aliases_notes_and_latest_refs(rec)
    _print_target_latest_file_transfer(rec)
    _print_target_file_transfers(rec, file_transfers_by_target)
    _print_target_activity_items(rec, activity_by_target)
    _print_target_survey_and_bridge(rec)
    _print_target_capability_and_compatibility(rec)


def print_target_summary(doc, limit=8):
    records = doc.get("targets") or []
    if not _print_target_summary_header(doc, records):
        return
    mailbox_by_target = doc.get("target_mailbox_records_by_target_id") or {}
    phone_home_by_target = doc.get("target_phone_home_records_by_target_id") or {}
    file_transfers_by_target = doc.get("target_file_transfer_records_by_target_id") or {}
    activity_by_target = doc.get("target_activity_records_by_target_id") or {}
    for rec in records[:limit]:
        _print_target_record_summary(
            rec,
            mailbox_by_target,
            phone_home_by_target,
            file_transfers_by_target,
            activity_by_target,
        )
