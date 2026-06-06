"""Mailbox record, index, summary, and timing helpers for grit-console."""

import hashlib

from gritlib.command_queue import (
    command_queue_expired, command_result_output_size_bucket,
)
from gritlib.record_utils import int_value, record_count_by_key, records_by_key
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


def _target_mailbox_command_text_and_hash(rec):
    command_text = str(rec.get("command") or "")
    command_sha256 = str(rec.get("command_sha256") or "")
    if command_text and not command_sha256:
        command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
    return command_text, command_sha256


def _target_mailbox_timing_context(rec, *, status, pending_work, has_result, now_epoch):
    created_at = str(rec.get("created_at") or "")
    delivered_at = str(rec.get("delivered_at") or "")
    result_received_at = str(rec.get("result_received_at") or "")
    age_sec = ""
    created_epoch = parse_utc_timestamp(created_at)
    if created_epoch is not None and now_epoch is not None:
        age_sec = max(int(now_epoch - created_epoch), 0)
    delivered_without_result = status == "delivered" and not has_result
    delivered_without_result_for_sec = ""
    if delivered_without_result and now_epoch is not None:
        delivered_epoch = parse_utc_timestamp(delivered_at)
        if delivered_epoch is not None:
            delivered_without_result_for_sec = max(int(now_epoch - delivered_epoch), 0)
    return {
        "created_at": created_at,
        "delivered_at": delivered_at,
        "result_received_at": result_received_at,
        "expires_at": str(rec.get("expires_at") or ""),
        "age_sec": age_sec,
        "pending_delivery_for_sec": age_sec if pending_work else "",
        "delivered_without_result": delivered_without_result,
        "delivered_without_result_for_sec": delivered_without_result_for_sec,
        "result_latency_sec": mailbox_elapsed_seconds(delivered_at, result_received_at),
    }


def _target_mailbox_pending_reason(
    target_rec,
    *,
    pending_work,
    delivered_without_result,
    expired,
    has_result,
):
    if pending_work:
        target_state = str(target_rec.get("connectivity_state") or "")
        if not target_rec:
            return "target-not-registered"
        if target_rec.get("poll_overdue") is True:
            return "target-poll-overdue"
        if target_state == "offline":
            return "target-offline"
        if target_state == "stale":
            return "target-stale"
        if target_state == "unknown":
            return "target-not-seen"
        return "waiting-for-next-poll"
    if delivered_without_result:
        return "awaiting-result-upload"
    if expired:
        return "expired"
    if has_result:
        return ""
    return "unknown"


def _target_mailbox_waiting_context(
    status,
    target_rec,
    *,
    expired,
    pending_work,
    has_result,
    delivered_without_result,
):
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
    return {
        "waiting_for": waiting_for,
        "pending_reason": _target_mailbox_pending_reason(
            target_rec,
            pending_work=pending_work,
            delivered_without_result=delivered_without_result,
            expired=expired,
            has_result=has_result,
        ),
    }


def _target_mailbox_result_output_context(rec, *, has_result):
    output_bytes = rec.get("result_output_bytes")
    return {
        "result_output_bytes": int_value(output_bytes),
        "result_output_size_bucket": (
            command_result_output_size_bucket(output_bytes) if has_result else ""
        ),
    }


def _target_mailbox_target_fields(target_rec):
    return {
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
    }


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
    command_text, command_sha256 = _target_mailbox_command_text_and_hash(rec)
    has_result = bool(str(rec.get("result_received_at") or "") or status == "result-received")
    pending_work = status == "queued"
    timing = _target_mailbox_timing_context(
        rec,
        status=status,
        pending_work=pending_work,
        has_result=has_result,
        now_epoch=now_epoch,
    )
    waiting = _target_mailbox_waiting_context(
        status,
        target_rec,
        expired=expired,
        pending_work=pending_work,
        has_result=has_result,
        delivered_without_result=timing["delivered_without_result"],
    )
    output = _target_mailbox_result_output_context(rec, has_result=has_result)
    return {
        "id": command_id,
        "command_id": command_id,
        "target_id": target_id,
        **_target_mailbox_target_fields(target_rec),
        "status": status,
        "waiting_for": waiting["waiting_for"],
        "pending_reason": waiting["pending_reason"],
        "has_pending_reason": bool(waiting["pending_reason"]),
        "work_kind": str(rec.get("work_kind") or ""),
        "workflow": str(rec.get("workflow") or ""),
        "request_name": str(rec.get("request_name") or ""),
        "bridge_profile": str(rec.get("bridge_profile") or ""),
        "bridge_route_path": str(rec.get("bridge_route_path") or ""),
        "bridge_requires_target_online": bool(rec.get("bridge_requires_target_online") is True),
        "route_kind": str(rec.get("route_kind") or ""),
        "command": command_text,
        "command_sha256": command_sha256,
        "created_at": timing["created_at"],
        "delivered_at": timing["delivered_at"],
        "result_received_at": timing["result_received_at"],
        "expires_at": timing["expires_at"],
        "expired": expired,
        "age_sec": timing["age_sec"],
        "age_bucket": mailbox_wait_bucket(timing["age_sec"]),
        "pending_delivery_for_sec": timing["pending_delivery_for_sec"],
        "pending_delivery_age_bucket": mailbox_wait_bucket(timing["pending_delivery_for_sec"]),
        "delivered_without_result_for_sec": timing["delivered_without_result_for_sec"],
        "delivered_without_result_age_bucket": mailbox_wait_bucket(timing["delivered_without_result_for_sec"]),
        "result_latency_sec": timing["result_latency_sec"],
        "result_latency_bucket": mailbox_wait_bucket(timing["result_latency_sec"]),
        "result_status": result_status,
        "result_exit_code": result_exit_code if result_exit_code not in (None, "") else "",
        "result_source_path": str(rec.get("result_source_path") or ""),
        "result_output_bytes": output["result_output_bytes"],
        "result_output_size_bucket": output["result_output_size_bucket"],
        "result_output_exceeded_limit": rec.get("result_output_exceeded_limit") is True,
        "max_output_bytes": rec.get("max_output_bytes", ""),
        "timeout_sec": rec.get("timeout_sec", ""),
        "pending_work": pending_work,
        "pending_delivery": pending_work,
        "delivered_without_result": timing["delivered_without_result"],
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


def target_mailbox_record_summary(records):
    records = records or []
    return {
        "target_mailbox_record_count": len(records),
        "target_mailbox_status_counts": record_count_by_key(records, "status"),
        "target_mailbox_waiting_for_counts": record_count_by_key(records, "waiting_for"),
        "target_mailbox_pending_reason_counts": record_count_by_key(
            records, "pending_reason"
        ),
        "target_mailbox_has_pending_reason_counts": record_count_by_key(
            records, "has_pending_reason"
        ),
        "target_mailbox_work_kind_counts": record_count_by_key(records, "work_kind"),
        "target_mailbox_workflow_counts": record_count_by_key(records, "workflow"),
        "target_mailbox_request_name_counts": record_count_by_key(
            records, "request_name"
        ),
        "target_mailbox_bridge_profile_counts": record_count_by_key(
            records, "bridge_profile"
        ),
        "target_mailbox_bridge_requires_target_online_counts": record_count_by_key(
            records, "bridge_requires_target_online"
        ),
        "target_mailbox_route_kind_counts": record_count_by_key(records, "route_kind"),
        "target_mailbox_expired_counts": record_count_by_key(records, "expired"),
        "target_mailbox_age_bucket_counts": record_count_by_key(records, "age_bucket"),
        "target_mailbox_pending_delivery_age_bucket_counts": record_count_by_key(
            records, "pending_delivery_age_bucket"
        ),
        "target_mailbox_delivered_without_result_age_bucket_counts": record_count_by_key(
            records, "delivered_without_result_age_bucket"
        ),
        "target_mailbox_result_latency_bucket_counts": record_count_by_key(
            records, "result_latency_bucket"
        ),
        "target_mailbox_pending_work_counts": record_count_by_key(
            records, "pending_work"
        ),
        "target_mailbox_has_result_counts": record_count_by_key(records, "has_result"),
        "target_mailbox_result_status_counts": record_count_by_key(
            records, "result_status"
        ),
        "target_mailbox_result_exit_code_counts": record_count_by_key(
            records, "result_exit_code"
        ),
        "target_mailbox_target_connectivity_state_counts": record_count_by_key(
            records, "target_connectivity_state"
        ),
        "target_mailbox_target_last_seen_via_counts": record_count_by_key(
            records, "target_last_seen_via"
        ),
        "target_mailbox_target_offline_age_bucket_counts": record_count_by_key(
            records, "target_offline_age_bucket"
        ),
        "target_mailbox_has_target_next_expected_poll_counts": record_count_by_key(
            records, "has_target_next_expected_poll"
        ),
        "target_mailbox_target_poll_overdue_counts": record_count_by_key(
            records, "target_poll_overdue"
        ),
    }
