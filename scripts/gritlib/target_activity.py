"""Target activity record helpers for grit-console."""

import hashlib
from pathlib import Path

from gritlib.command_queue import (
    command_queue_expired, command_result_output_size_bucket,
)
from gritlib.record_utils import int_value, records_by_key
from gritlib.session_state import parse_utc_timestamp


def mailbox_wait_bucket(seconds):
    if seconds in ("", None):
        return ""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return ""
    if value < 60:
        return "under-minute"
    if value < 3600:
        return "under-hour"
    if value < 86400:
        return "under-day"
    return "day-plus"


def mailbox_elapsed_seconds(start, end):
    start_epoch = parse_utc_timestamp(str(start or ""))
    end_epoch = parse_utc_timestamp(str(end or ""))
    if start_epoch is None or end_epoch is None:
        return ""
    return max(int(end_epoch - start_epoch), 0)


def target_mailbox_record_from_command(rec, targets_by_id=None, now_epoch=None):
    if not isinstance(rec, dict):
        return None
    target_id = str(rec.get("target_id") or "")
    if not target_id:
        return None
    target_rec = (targets_by_id or {}).get(target_id) or {}
    command_id = str(rec.get("id") or "")
    status = str(rec.get("status") or "")
    expired = status == "expired" or command_queue_expired(rec, now_epoch=now_epoch)
    if expired:
        status = "expired"
    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    result_status = str(result.get("status") or "")
    result_exit_code = result.get("exit_code")
    command_text = str(rec.get("command") or "")
    command_sha256 = str(rec.get("command_sha256") or "")
    if command_text and not command_sha256:
        command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
    has_result = bool(str(rec.get("result_received_at") or "") or status == "result-received")
    pending_work = status == "queued"
    created_at = str(rec.get("created_at") or "")
    delivered_at = str(rec.get("delivered_at") or "")
    result_received_at = str(rec.get("result_received_at") or "")
    expires_at = str(rec.get("expires_at") or "")
    age_sec = ""
    created_epoch = parse_utc_timestamp(created_at)
    if created_epoch is not None and now_epoch is not None:
        age_sec = max(int(now_epoch - created_epoch), 0)
    pending_delivery_for_sec = age_sec if pending_work else ""
    delivered_without_result = status == "delivered" and not has_result
    delivered_without_result_for_sec = ""
    if delivered_without_result and now_epoch is not None:
        delivered_epoch = parse_utc_timestamp(delivered_at)
        if delivered_epoch is not None:
            delivered_without_result_for_sec = max(int(now_epoch - delivered_epoch), 0)
    result_latency_sec = mailbox_elapsed_seconds(delivered_at, result_received_at)
    if pending_work:
        waiting_for = "target-poll"
    elif expired:
        waiting_for = "none"
    elif delivered_without_result:
        waiting_for = "result-upload"
    elif has_result:
        waiting_for = "none"
    else:
        waiting_for = "unknown"
    if pending_work:
        target_state = str(target_rec.get("connectivity_state") or "")
        if not target_rec:
            pending_reason = "target-not-registered"
        elif target_rec.get("poll_overdue") is True:
            pending_reason = "target-poll-overdue"
        elif target_state == "offline":
            pending_reason = "target-offline"
        elif target_state == "stale":
            pending_reason = "target-stale"
        elif target_state == "unknown":
            pending_reason = "target-not-seen"
        else:
            pending_reason = "waiting-for-next-poll"
    elif delivered_without_result:
        pending_reason = "awaiting-result-upload"
    elif expired:
        pending_reason = "expired"
    elif has_result:
        pending_reason = ""
    else:
        pending_reason = "unknown"
    output_bytes = rec.get("result_output_bytes")
    output_bucket = command_result_output_size_bucket(output_bytes) if has_result else ""
    return {
        "id": command_id,
        "command_id": command_id,
        "target_id": target_id,
        "target_label": str(target_rec.get("label") or ""),
        "target_last_seen": str(target_rec.get("last_seen") or target_rec.get("last_seen_at") or ""),
        "target_last_seen_via": str(target_rec.get("last_seen_via") or ""),
        "target_offline_for_sec": target_rec.get("offline_for_sec", ""),
        "target_offline_age_bucket": str(target_rec.get("offline_age_bucket") or ""),
        "target_connectivity_state": str(target_rec.get("connectivity_state") or ""),
        "target_next_expected_poll": str(target_rec.get("next_expected_poll") or ""),
        "has_target_next_expected_poll": bool(str(target_rec.get("next_expected_poll") or "")),
        "target_poll_overdue": bool(target_rec.get("poll_overdue") is True),
        "target_poll_overdue_for_sec": target_rec.get("poll_overdue_for_sec", ""),
        "status": status,
        "waiting_for": waiting_for,
        "pending_reason": pending_reason,
        "has_pending_reason": bool(pending_reason),
        "work_kind": str(rec.get("work_kind") or ""),
        "workflow": str(rec.get("workflow") or ""),
        "request_name": str(rec.get("request_name") or ""),
        "bridge_profile": str(rec.get("bridge_profile") or ""),
        "bridge_route_path": str(rec.get("bridge_route_path") or ""),
        "bridge_requires_target_online": bool(rec.get("bridge_requires_target_online") is True),
        "route_kind": str(rec.get("route_kind") or ""),
        "command": command_text,
        "command_sha256": command_sha256,
        "created_at": created_at,
        "delivered_at": delivered_at,
        "result_received_at": result_received_at,
        "expires_at": expires_at,
        "expired": expired,
        "age_sec": age_sec,
        "age_bucket": mailbox_wait_bucket(age_sec),
        "pending_delivery_for_sec": pending_delivery_for_sec,
        "pending_delivery_age_bucket": mailbox_wait_bucket(pending_delivery_for_sec),
        "delivered_without_result_for_sec": delivered_without_result_for_sec,
        "delivered_without_result_age_bucket": mailbox_wait_bucket(delivered_without_result_for_sec),
        "result_latency_sec": result_latency_sec,
        "result_latency_bucket": mailbox_wait_bucket(result_latency_sec),
        "result_status": result_status,
        "result_exit_code": result_exit_code if result_exit_code not in (None, "") else "",
        "result_source_path": str(rec.get("result_source_path") or ""),
        "result_output_bytes": int_value(output_bytes),
        "result_output_size_bucket": output_bucket,
        "result_output_exceeded_limit": rec.get("result_output_exceeded_limit") is True,
        "max_output_bytes": rec.get("max_output_bytes", ""),
        "timeout_sec": rec.get("timeout_sec", ""),
        "pending_work": pending_work,
        "pending_delivery": pending_work,
        "delivered_without_result": delivered_without_result,
        "has_result": has_result,
    }


def target_mailbox_records_from_commands(commands, targets_by_id=None, now_epoch=None):
    records = []
    for rec in commands or []:
        item = target_mailbox_record_from_command(rec, targets_by_id, now_epoch=now_epoch)
        if item:
            records.append(item)
    records.sort(
        key=lambda rec: (
            str(rec.get("created_at") or ""),
            str(rec.get("command_id") or ""),
        ),
        reverse=True,
    )
    return records


def target_activity_records_from_sources(targets, mailbox_records, phone_home_records, file_transfer_records, bridge_profiles, sessions):
    records = []
    targets_by_id = {
        str(rec.get("target_id") or ""): rec
        for rec in targets or []
        if isinstance(rec, dict) and str(rec.get("target_id") or "")
    }

    def add(record):
        if not isinstance(record, dict):
            return
        target_id = str(record.get("target_id") or "")
        if not target_id:
            return
        target_rec = targets_by_id.get(target_id) or {}
        if not str(record.get("target_label") or ""):
            record["target_label"] = str(target_rec.get("label") or target_rec.get("target_label") or "")
        for field in (
            "target_connectivity_state",
            "target_last_seen",
            "target_last_seen_via",
            "target_offline_age_bucket",
            "target_next_expected_poll",
        ):
            source_field = field.replace("target_", "", 1)
            if not str(record.get(field) or ""):
                record[field] = str(target_rec.get(source_field) or "")
        if not str(record.get("target_offline_for_sec") or ""):
            record["target_offline_for_sec"] = target_rec.get("offline_for_sec", "")
        record["target_poll_overdue"] = bool(record.get("target_poll_overdue") is True or target_rec.get("poll_overdue") is True)
        if not str(record.get("target_poll_overdue_for_sec") or ""):
            record["target_poll_overdue_for_sec"] = target_rec.get("poll_overdue_for_sec", "")
        if not str(record.get("target_mailbox_pending_work_count") or ""):
            record["target_mailbox_pending_work_count"] = int_value(target_rec.get("mailbox_pending_work_count", 0))
        records.append(record)

    for rec in targets or []:
        if not isinstance(rec, dict):
            continue
        target_id = str(rec.get("target_id") or "")
        target_label = str(rec.get("label") or rec.get("target_label") or "")
        if rec.get("latest_activity_at") or rec.get("last_seen"):
            add({
                "id": f"target:{target_id}:heartbeat",
                "target_id": target_id,
                "target_label": target_label,
                "category": "heartbeat",
                "source_collection": "targets",
                "operation": str(rec.get("latest_activity_operation") or "heartbeat"),
                "status": str(rec.get("connectivity_state") or ""),
                "timestamp": str(rec.get("last_seen") or rec.get("latest_activity_at") or ""),
                "summary": f"last seen via {rec.get('last_seen_via') or '-'}",
                "route_kind": "",
                "bridge_profile": "",
                "session_id": str(rec.get("latest_session_id") or ""),
                "command_id": str(rec.get("latest_command_result_id") or ""),
                "request_name": "",
                "filename": "",
                "pending_work": bool(int_value(rec.get("mailbox_pending_work_count")) > 0),
                "waiting_for": "target-poll" if int_value(rec.get("mailbox_pending_work_count")) > 0 else "none",
            })
        if rec.get("latest_survey_result_at"):
            add({
                "id": f"target:{target_id}:survey:{rec.get('latest_survey_result_id') or rec.get('latest_survey_result_at')}",
                "target_id": target_id,
                "target_label": target_label,
                "category": "survey",
                "source_collection": "targets",
                "operation": str(rec.get("latest_survey_result_kind") or "survey-result"),
                "status": str(rec.get("latest_survey_result_status") or ""),
                "timestamp": str(rec.get("latest_survey_result_at") or ""),
                "summary": str(rec.get("latest_survey_result_id") or ""),
                "route_kind": str(rec.get("latest_survey_result_route_kind") or ""),
                "bridge_profile": str(rec.get("latest_survey_result_bridge_profile") or ""),
                "session_id": str(rec.get("latest_session_id") or ""),
                "command_id": "",
                "request_name": "",
                "filename": "",
                "pending_work": False,
                "waiting_for": "none",
            })
    for rec in mailbox_records or []:
        add({
            "id": f"mailbox:{rec.get('command_id') or rec.get('id')}",
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "category": "mailbox",
            "source_collection": "target_mailbox_records",
            "operation": str(rec.get("waiting_for") or "mailbox"),
            "status": str(rec.get("status") or ""),
            "timestamp": str(rec.get("result_received_at") or rec.get("delivered_at") or rec.get("created_at") or ""),
            "summary": str(rec.get("pending_reason") or rec.get("result_status") or rec.get("command") or ""),
            "route_kind": "",
            "bridge_profile": "",
            "session_id": "",
            "command_id": str(rec.get("command_id") or ""),
            "request_name": "",
            "filename": "",
            "pending_work": bool(rec.get("pending_work")),
            "waiting_for": str(rec.get("waiting_for") or ""),
        })
    for rec in phone_home_records or []:
        add({
            "id": f"phone-home:{rec.get('id') or rec.get('event_id')}",
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "category": "phone-home",
            "source_collection": "target_phone_home_records",
            "operation": str(rec.get("kind") or rec.get("operation") or ""),
            "status": str(rec.get("status") or ""),
            "timestamp": str(rec.get("timestamp") or ""),
            "summary": str(rec.get("pending_reason") or rec.get("reason") or rec.get("contact_path") or ""),
            "route_kind": "",
            "bridge_profile": "",
            "session_id": str(rec.get("session_id") or ""),
            "command_id": str(rec.get("command_id") or ""),
            "request_name": "",
            "filename": "",
            "pending_work": bool(rec.get("pending_work_remaining")),
            "waiting_for": "remaining-work" if rec.get("pending_work_remaining") else "none",
        })
    for rec in file_transfer_records or []:
        add({
            "id": f"file:{rec.get('id')}",
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "category": "file-transfer",
            "source_collection": "target_file_transfer_records",
            "operation": str(rec.get("operation") or ""),
            "status": str(rec.get("status") or ""),
            "timestamp": str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or ""),
            "summary": str(rec.get("filename") or rec.get("request_name") or rec.get("source_path") or rec.get("stored_path") or ""),
            "route_kind": str(rec.get("route_kind") or ""),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "session_id": str(rec.get("session_id") or ""),
            "command_id": "",
            "request_name": str(rec.get("request_name") or ""),
            "filename": str(rec.get("filename") or ""),
            "pending_work": False,
            "waiting_for": "none",
        })
    for rec in bridge_profiles or []:
        timestamp = str(rec.get("last_successful_relay_at") or rec.get("last_failure_at") or "")
        if not timestamp:
            continue
        add({
            "id": f"bridge:{rec.get('name') or len(records)}:{timestamp}",
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "category": "bridge",
            "source_collection": "bridge_profiles",
            "operation": "bridge-relay" if rec.get("has_last_successful_relay") else "bridge-failure",
            "status": str(rec.get("current_state") or ""),
            "timestamp": timestamp,
            "summary": str(rec.get("last_failure_reason") or rec.get("route_path") or ""),
            "route_kind": "bridge",
            "bridge_profile": str(rec.get("name") or ""),
            "session_id": "",
            "command_id": "",
            "request_name": "",
            "filename": "",
            "pending_work": bool(rec.get("requires_target_online") and not rec.get("active")),
            "waiting_for": "target-online" if rec.get("requires_target_online") and not rec.get("active") else "none",
        })
    for rec in sessions or []:
        add({
            "id": f"session:{rec.get('session_id') or Path(str(rec.get('path') or '')).name}",
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "category": "session",
            "source_collection": "sessions",
            "operation": str(rec.get("service") or ""),
            "status": str(rec.get("state") or rec.get("exit_reason") or ""),
            "timestamp": str(rec.get("updated_at") or rec.get("started_at") or ""),
            "summary": str(rec.get("exit_reason") or rec.get("path") or ""),
            "route_kind": "",
            "bridge_profile": "",
            "session_id": str(rec.get("session_id") or Path(str(rec.get("path") or "")).name),
            "command_id": "",
            "request_name": "",
            "filename": "",
            "pending_work": False,
            "waiting_for": "none",
        })
    records.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("id") or "")), reverse=True)
    return records


def target_activity_record_indexes(records):
    return {
        "target_activity_records_by_id": {rec.get("id", ""): rec for rec in records or [] if isinstance(rec, dict) and rec.get("id")},
        "target_activity_records_by_target_id": records_by_key(records, "target_id"),
        "target_activity_records_by_target_label": records_by_key(records, "target_label"),
        "target_activity_records_by_category": records_by_key(records, "category"),
        "target_activity_records_by_source_collection": records_by_key(records, "source_collection"),
        "target_activity_records_by_operation": records_by_key(records, "operation"),
        "target_activity_records_by_status": records_by_key(records, "status"),
        "target_activity_records_by_route_kind": records_by_key(records, "route_kind"),
        "target_activity_records_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_activity_records_by_session_id": records_by_key(records, "session_id"),
        "target_activity_records_by_command_id": records_by_key(records, "command_id"),
        "target_activity_records_by_request_name": records_by_key(records, "request_name"),
        "target_activity_records_by_filename": records_by_key(records, "filename"),
        "target_activity_records_by_pending_work": records_by_key(records, "pending_work"),
        "target_activity_records_by_waiting_for": records_by_key(records, "waiting_for"),
        "target_activity_records_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "target_activity_records_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "target_activity_records_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "target_activity_records_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
    }


def target_mailbox_record_indexes(records):
    return {
        "target_mailbox_records_by_id": {
            rec.get("id", ""): rec for rec in records or [] if rec.get("id")
        },
        "target_mailbox_records_by_command_id": {
            rec.get("command_id", ""): rec for rec in records or [] if rec.get("command_id")
        },
        "target_mailbox_records_by_target_id": records_by_key(records, "target_id"),
        "target_mailbox_records_by_target_label": records_by_key(records, "target_label"),
        "target_mailbox_records_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "target_mailbox_records_by_target_last_seen_via": records_by_key(records, "target_last_seen_via"),
        "target_mailbox_records_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "target_mailbox_records_by_has_target_next_expected_poll": records_by_key(records, "has_target_next_expected_poll"),
        "target_mailbox_records_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "target_mailbox_records_by_status": records_by_key(records, "status"),
        "target_mailbox_records_by_waiting_for": records_by_key(records, "waiting_for"),
        "target_mailbox_records_by_pending_reason": records_by_key(records, "pending_reason"),
        "target_mailbox_records_by_has_pending_reason": records_by_key(records, "has_pending_reason"),
        "target_mailbox_records_by_work_kind": records_by_key(records, "work_kind"),
        "target_mailbox_records_by_workflow": records_by_key(records, "workflow"),
        "target_mailbox_records_by_request_name": records_by_key(records, "request_name"),
        "target_mailbox_records_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_mailbox_records_by_bridge_requires_target_online": records_by_key(records, "bridge_requires_target_online"),
        "target_mailbox_records_by_route_kind": records_by_key(records, "route_kind"),
        "target_mailbox_records_by_expired": records_by_key(records, "expired"),
        "target_mailbox_records_by_age_bucket": records_by_key(records, "age_bucket"),
        "target_mailbox_records_by_pending_delivery_age_bucket": records_by_key(records, "pending_delivery_age_bucket"),
        "target_mailbox_records_by_delivered_without_result_age_bucket": records_by_key(records, "delivered_without_result_age_bucket"),
        "target_mailbox_records_by_result_latency_bucket": records_by_key(records, "result_latency_bucket"),
        "target_mailbox_records_by_pending_work": records_by_key(records, "pending_work"),
        "target_mailbox_records_by_pending_delivery": records_by_key(records, "pending_delivery"),
        "target_mailbox_records_by_delivered_without_result": records_by_key(records, "delivered_without_result"),
        "target_mailbox_records_by_has_result": records_by_key(records, "has_result"),
        "target_mailbox_records_by_result_status": records_by_key(records, "result_status"),
        "target_mailbox_records_by_result_exit_code": records_by_key(records, "result_exit_code"),
        "target_mailbox_records_by_result_output_exceeded_limit": records_by_key(records, "result_output_exceeded_limit"),
        "target_mailbox_records_by_result_output_size_bucket": records_by_key(records, "result_output_size_bucket"),
        "target_mailbox_records_by_command_sha256": records_by_key(records, "command_sha256"),
    }


def target_phone_home_record_indexes(records):
    return {
        "target_phone_home_records_by_id": {
            rec.get("id", ""): rec for rec in records or [] if rec.get("id")
        },
        "target_phone_home_records_by_event_id": {
            rec.get("event_id", ""): rec for rec in records or [] if rec.get("event_id")
        },
        "target_phone_home_records_by_kind": records_by_key(records, "kind"),
        "target_phone_home_records_by_status": records_by_key(records, "status"),
        "target_phone_home_records_by_successful": records_by_key(records, "successful"),
        "target_phone_home_records_by_failed": records_by_key(records, "failed"),
        "target_phone_home_records_by_target_id": records_by_key(records, "target_id"),
        "target_phone_home_records_by_target_label": records_by_key(records, "target_label"),
        "target_phone_home_records_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "target_phone_home_records_by_target_last_seen_via": records_by_key(records, "target_last_seen_via"),
        "target_phone_home_records_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "target_phone_home_records_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "target_phone_home_records_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "target_phone_home_records_by_has_target_identity": records_by_key(records, "has_target_identity"),
        "target_phone_home_records_by_anonymous": records_by_key(records, "anonymous"),
        "target_phone_home_records_by_contact_path": records_by_key(records, "contact_path"),
        "target_phone_home_records_by_remote_addr": records_by_key(records, "remote_addr"),
        "target_phone_home_records_by_http_status": records_by_key(records, "http_status"),
        "target_phone_home_records_by_reason": records_by_key(records, "reason"),
        "target_phone_home_records_by_pending_reason": records_by_key(records, "pending_reason"),
        "target_phone_home_records_by_has_pending_reason": records_by_key(records, "has_pending_reason"),
        "target_phone_home_records_by_has_queued_remaining_count": records_by_key(records, "has_queued_remaining_count"),
        "target_phone_home_records_by_pending_work_remaining": records_by_key(records, "pending_work_remaining"),
        "target_phone_home_records_by_queued_remaining_count": records_by_key(records, "queued_remaining_count"),
        "target_phone_home_records_by_command_id": records_by_key(records, "command_id"),
        "target_phone_home_records_by_work_kind": records_by_key(records, "work_kind"),
        "target_phone_home_records_by_workflow": records_by_key(records, "workflow"),
        "target_phone_home_records_by_request_name": records_by_key(records, "request_name"),
        "target_phone_home_records_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_phone_home_records_by_bridge_requires_target_online": records_by_key(records, "bridge_requires_target_online"),
        "target_phone_home_records_by_route_kind": records_by_key(records, "route_kind"),
        "target_phone_home_records_by_poll_mode": records_by_key(records, "poll_mode"),
        "target_phone_home_records_by_poll_interval_sec": records_by_key(records, "poll_interval_sec"),
    }


def latest_target_phone_home_records(records):
    latest = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        target_id = str(rec.get("target_id") or "")
        if not target_id:
            continue
        bucket = latest.setdefault(target_id, {
            "latest": {},
            "latest_successful": {},
            "latest_failed": {},
            "record_count": 0,
            "successful_count": 0,
            "failed_count": 0,
        })
        bucket["record_count"] += 1
        if not bucket["latest"]:
            bucket["latest"] = rec
        if rec.get("successful") is True:
            bucket["successful_count"] += 1
            if not bucket["latest_successful"]:
                bucket["latest_successful"] = rec
        if rec.get("failed") is True:
            bucket["failed_count"] += 1
            if not bucket["latest_failed"]:
                bucket["latest_failed"] = rec
    return latest


def apply_target_phone_home_summary(targets, phone_home_records):
    by_target = latest_target_phone_home_records(phone_home_records)
    for rec in targets or []:
        if not isinstance(rec, dict):
            continue
        summary = by_target.get(str(rec.get("target_id") or ""), {})
        latest = summary.get("latest") or {}
        latest_success = summary.get("latest_successful") or {}
        latest_failed = summary.get("latest_failed") or {}
        rec["phone_home_record_count"] = int(summary.get("record_count", 0) or 0)
        rec["successful_phone_home_count"] = int(summary.get("successful_count", 0) or 0)
        rec["failed_phone_home_count"] = int(summary.get("failed_count", 0) or 0)
        rec["latest_phone_home_at"] = str(latest.get("timestamp") or "")
        rec["latest_phone_home_kind"] = str(latest.get("kind") or "")
        rec["latest_phone_home_status"] = str(latest.get("status") or "")
        rec["latest_phone_home_http_status"] = str(latest.get("http_status") or "")
        rec["latest_phone_home_contact_path"] = str(latest.get("contact_path") or "")
        rec["latest_phone_home_reason"] = str(latest.get("pending_reason") or latest.get("reason") or "")
        rec["latest_successful_phone_home_at"] = str(latest_success.get("timestamp") or "")
        rec["latest_successful_phone_home_kind"] = str(latest_success.get("kind") or "")
        rec["latest_successful_phone_home_status"] = str(latest_success.get("status") or "")
        rec["latest_successful_phone_home_contact_path"] = str(latest_success.get("contact_path") or "")
        rec["last_failed_phone_home_at"] = str(latest_failed.get("timestamp") or "")
        rec["last_failed_phone_home_kind"] = str(latest_failed.get("kind") or "")
        rec["last_failed_phone_home_status"] = str(latest_failed.get("status") or "")
        rec["last_failed_phone_home_http_status"] = str(latest_failed.get("http_status") or "")
        rec["last_failed_phone_home_contact_path"] = str(latest_failed.get("contact_path") or "")
        rec["last_failed_phone_home_reason"] = str(latest_failed.get("pending_reason") or latest_failed.get("reason") or "")
        rec["has_last_failed_phone_home"] = bool(rec["last_failed_phone_home_at"])
    return targets
