"""Target phone-home record, index, and summary helpers for grit-console."""

from gritlib.record_utils import (
    int_value, latest_record_value, record_count_by_key, records_by_key,
)


def target_phone_home_pending_reason(kind, details):
    status = str((details or {}).get("status") or "")
    target_id = str((details or {}).get("target_id") or "")
    reason = str((details or {}).get("reason") or "")
    if reason:
        return reason
    if kind == "poll":
        queued_count = int_value((details or {}).get("queued_count"))
        queued_before = int_value((details or {}).get("queued_count_before"))
        delivered_count = int_value((details or {}).get("delivered_count"))
        if status == "delivered":
            remaining = max(queued_before - delivered_count, 0)
            return "more queued work remains" if remaining > 0 else ""
        if status == "no-command" and queued_count > 0:
            if target_id:
                return "queued work remains for another target or this target has no matching pending command"
            return "queued work requires a target identity"
    if kind == "result" and status == "result-received":
        return ""
    if status:
        return status
    return ""


def _target_phone_home_event_kind(event_name):
    if event_name == "command_queue_poll":
        return "poll"
    if event_name == "command_queue_result_upload":
        return "result"
    return ""


def _target_phone_home_queued_remaining_count(kind, status, details):
    if kind == "poll" and status == "delivered":
        return max(
            int_value(details.get("queued_count_before")) - int_value(details.get("delivered_count")),
            0,
        )
    if kind == "poll" and status == "no-command":
        return int_value(details.get("queued_count"))
    return ""


def _target_phone_home_target_fields(target_rec):
    return {
        "target_connectivity_state": str(target_rec.get("connectivity_state") or ""),
        "target_last_seen": str(target_rec.get("last_seen") or target_rec.get("last_seen_at") or ""),
        "target_last_seen_via": str(target_rec.get("last_seen_via") or ""),
        "target_offline_for_sec": target_rec.get("offline_for_sec", ""),
        "target_offline_age_bucket": str(target_rec.get("offline_age_bucket") or ""),
        "target_next_expected_poll": str(target_rec.get("next_expected_poll") or ""),
        "target_poll_overdue": bool(target_rec.get("poll_overdue") is True),
        "target_poll_overdue_for_sec": target_rec.get("poll_overdue_for_sec", ""),
        "target_mailbox_pending_work_count": int_value(target_rec.get("mailbox_pending_work_count", 0)),
    }


def target_phone_home_record_from_event(event, targets_by_id=None):
    if not isinstance(event, dict):
        return None
    event_name = str(event.get("event") or "")
    kind = _target_phone_home_event_kind(event_name)
    if not kind:
        return None
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    status = str(details.get("status") or "")
    target_id = str(details.get("target_id") or "")
    target_rec = (targets_by_id or {}).get(target_id) or {}
    remote = str(event.get("remote") or details.get("remote_addr") or "")
    success = status in ("delivered", "no-command", "result-received")
    failed = status in ("rejected", "error")
    pending_reason = target_phone_home_pending_reason(kind, details)
    queued_remaining_count = _target_phone_home_queued_remaining_count(kind, status, details)
    rec = {
        "id": str(event.get("id") or ""),
        "event_id": str(event.get("id") or ""),
        "kind": kind,
        "operation": str(details.get("operation") or ""),
        "status": status,
        "successful": success,
        "failed": failed,
        "timestamp": str(event.get("ts") or ""),
        "service": str(event.get("service") or ""),
        "event": event_name,
        "level": str(event.get("level") or ""),
        "session_id": str(event.get("session") or ""),
        "session_path": str(event.get("session_path") or ""),
        "remote_addr": remote,
        "contact_path": f"{event.get('service', '')}:{remote}" if remote else str(event.get("service") or ""),
        "target_id": target_id,
        "target_label": str(details.get("target_label") or ""),
        **_target_phone_home_target_fields(target_rec),
        "has_target_identity": bool(target_id),
        "target_identity_source": str(details.get("target_identity_source") or ""),
        "target_identity_confidence": str(details.get("target_identity_confidence") or ""),
        "http_status": str(details.get("http_status") or ""),
        "method": str(details.get("method") or ""),
        "reason": str(details.get("reason") or ""),
        "pending_reason": pending_reason,
        "has_pending_reason": bool(pending_reason),
        "command_id": str(details.get("command_id") or ""),
        "command_sha256": str(details.get("command_sha256") or ""),
        "delivered_command": kind == "poll" and status == "delivered",
        "delivered_count": int_value(details.get("delivered_count")),
        "queued_count": int_value(details.get("queued_count")),
        "queued_count_before": int_value(details.get("queued_count_before")),
        "queued_remaining_count": queued_remaining_count,
        "has_queued_remaining_count": queued_remaining_count != "",
        "pending_work_remaining": queued_remaining_count != "" and int_value(queued_remaining_count) > 0,
        "result_status": str(details.get("result_status") or ""),
        "result_exit_code": str(details.get("result_exit_code") or ""),
        "result_output_exceeded_limit": bool(details.get("result_output_exceeded_limit", False)),
        "work_kind": str(details.get("work_kind") or ""),
        "workflow": str(details.get("workflow") or ""),
        "request_name": str(details.get("request_name") or ""),
        "bridge_profile": str(details.get("bridge_profile") or ""),
        "bridge_route_path": str(details.get("bridge_route_path") or ""),
        "bridge_requires_target_online": bool(details.get("bridge_requires_target_online", False)),
        "route_kind": str(details.get("route_kind") or ""),
        "poll_mode": str(details.get("poll_mode") or ""),
        "poll_interval_sec": str(details.get("poll_interval_sec") or ""),
        "poll_jitter_pct": str(details.get("poll_jitter_pct") or ""),
        "poll_backoff": str(details.get("poll_backoff") or ""),
        "poll_max_interval_sec": str(details.get("poll_max_interval_sec") or ""),
        "max_polls": str(details.get("max_polls") or ""),
    }
    rec["uploaded_result"] = kind == "result" and status == "result-received"
    rec["anonymous"] = not rec["has_target_identity"]
    return rec


def target_phone_home_records_from_events(events, targets_by_id=None):
    records = []
    for event in events or []:
        rec = target_phone_home_record_from_event(event, targets_by_id=targets_by_id)
        if rec:
            records.append(rec)
    records.sort(key=lambda rec: (str(rec.get("timestamp") or ""), str(rec.get("id") or "")), reverse=True)
    return records


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


def target_phone_home_record_summary(records):
    records = records or []
    return {
        "target_phone_home_record_count": len(records),
        "target_phone_home_kind_counts": record_count_by_key(records, "kind"),
        "target_phone_home_status_counts": record_count_by_key(records, "status"),
        "target_phone_home_successful_counts": record_count_by_key(
            records, "successful"
        ),
        "target_phone_home_failed_counts": record_count_by_key(records, "failed"),
        "target_phone_home_target_counts": record_count_by_key(records, "target_id"),
        "target_phone_home_anonymous_counts": record_count_by_key(
            records, "anonymous"
        ),
        "target_phone_home_target_connectivity_state_counts": record_count_by_key(
            records, "target_connectivity_state"
        ),
        "target_phone_home_target_offline_age_bucket_counts": record_count_by_key(
            records, "target_offline_age_bucket"
        ),
        "target_phone_home_target_poll_overdue_counts": record_count_by_key(
            records, "target_poll_overdue"
        ),
        "target_phone_home_target_mailbox_pending_work_count_counts": record_count_by_key(
            records, "target_mailbox_pending_work_count"
        ),
        "target_phone_home_pending_reason_counts": record_count_by_key(
            records, "pending_reason"
        ),
        "target_phone_home_queued_remaining_count_counts": record_count_by_key(
            records, "queued_remaining_count"
        ),
        "target_phone_home_pending_work_remaining_counts": record_count_by_key(
            records, "pending_work_remaining"
        ),
        "target_phone_home_http_status_counts": record_count_by_key(
            records, "http_status"
        ),
        "target_phone_home_work_kind_counts": record_count_by_key(
            records, "work_kind"
        ),
        "target_phone_home_workflow_counts": record_count_by_key(records, "workflow"),
        "target_phone_home_request_name_counts": record_count_by_key(
            records, "request_name"
        ),
        "target_phone_home_bridge_profile_counts": record_count_by_key(
            records, "bridge_profile"
        ),
        "target_phone_home_bridge_requires_target_online_counts": record_count_by_key(
            records, "bridge_requires_target_online"
        ),
        "target_phone_home_route_kind_counts": record_count_by_key(
            records, "route_kind"
        ),
        "target_phone_home_latest_at": latest_record_value(records, ("timestamp",)),
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
