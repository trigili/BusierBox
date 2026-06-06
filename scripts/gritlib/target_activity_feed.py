"""Target activity feed record, index, and summary helpers for grit-console."""

from pathlib import Path

from gritlib.record_utils import (
    int_value, latest_record_value, record_count_by_key, records_by_key,
)


def _target_activity_targets_by_id(targets):
    return {
        str(rec.get("target_id") or ""): rec
        for rec in targets or []
        if isinstance(rec, dict) and str(rec.get("target_id") or "")
    }


def _enrich_target_activity_record(record, targets_by_id):
    if not isinstance(record, dict):
        return None
    target_id = str(record.get("target_id") or "")
    if not target_id:
        return None
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
    record["target_poll_overdue"] = bool(
        record.get("target_poll_overdue") is True or target_rec.get("poll_overdue") is True
    )
    if not str(record.get("target_poll_overdue_for_sec") or ""):
        record["target_poll_overdue_for_sec"] = target_rec.get("poll_overdue_for_sec", "")
    if not str(record.get("target_mailbox_pending_work_count") or ""):
        record["target_mailbox_pending_work_count"] = int_value(
            target_rec.get("mailbox_pending_work_count", 0)
        )
    return record


def _target_activity_records_from_targets(targets):
    records = []
    for rec in targets or []:
        if not isinstance(rec, dict):
            continue
        target_id = str(rec.get("target_id") or "")
        target_label = str(rec.get("label") or rec.get("target_label") or "")
        if rec.get("latest_activity_at") or rec.get("last_seen"):
            records.append(_target_heartbeat_activity_record(rec, target_id, target_label))
        if rec.get("latest_survey_result_at"):
            records.append(_target_survey_activity_record(rec, target_id, target_label))
    return records


def _target_heartbeat_activity_record(rec, target_id, target_label):
    pending_count = int_value(rec.get("mailbox_pending_work_count"))
    return {
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
        "pending_work": bool(pending_count > 0),
        "waiting_for": "target-poll" if pending_count > 0 else "none",
    }


def _target_survey_activity_record(rec, target_id, target_label):
    return {
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
    }


def _mailbox_activity_record(rec):
    return {
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
    }


def _phone_home_activity_record(rec):
    return {
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
    }


def _file_transfer_activity_record(rec):
    return {
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
    }


def _bridge_activity_record(rec, ordinal):
    timestamp = str(rec.get("last_successful_relay_at") or rec.get("last_failure_at") or "")
    if not timestamp:
        return None
    return {
        "id": f"bridge:{rec.get('name') or ordinal}:{timestamp}",
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
    }


def _session_activity_record(rec):
    session_id = str(rec.get("session_id") or Path(str(rec.get("path") or "")).name)
    return {
        "id": f"session:{session_id}",
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
        "session_id": session_id,
        "command_id": "",
        "request_name": "",
        "filename": "",
        "pending_work": False,
        "waiting_for": "none",
    }


def _append_target_activity_record(records, targets_by_id, record):
    enriched = _enrich_target_activity_record(record, targets_by_id)
    if enriched:
        records.append(enriched)


def target_activity_records_from_sources(
    targets,
    mailbox_records,
    phone_home_records,
    file_transfer_records,
    bridge_profiles,
    sessions,
):
    records = []
    targets_by_id = _target_activity_targets_by_id(targets)
    for record in _target_activity_records_from_targets(targets):
        _append_target_activity_record(records, targets_by_id, record)
    for rec in mailbox_records or []:
        _append_target_activity_record(records, targets_by_id, _mailbox_activity_record(rec))
    for rec in phone_home_records or []:
        _append_target_activity_record(records, targets_by_id, _phone_home_activity_record(rec))
    for rec in file_transfer_records or []:
        _append_target_activity_record(records, targets_by_id, _file_transfer_activity_record(rec))
    for rec in bridge_profiles or []:
        _append_target_activity_record(records, targets_by_id, _bridge_activity_record(rec, len(records)))
    for rec in sessions or []:
        _append_target_activity_record(records, targets_by_id, _session_activity_record(rec))
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


def target_activity_feed_status_context(
    targets=None,
    mailbox_records=None,
    phone_home_records=None,
    file_transfer_records=None,
    bridge_profiles=None,
    sessions=None,
):
    records = target_activity_records_from_sources(
        targets,
        mailbox_records,
        phone_home_records,
        file_transfer_records,
        bridge_profiles,
        sessions,
    )
    return {
        "records": records,
        "index_maps": target_activity_record_indexes(records),
    }


def target_activity_record_summary(records):
    records = records or []
    return {
        "target_activity_record_count": len(records),
        "target_activity_target_counts": record_count_by_key(records, "target_id"),
        "target_activity_category_counts": record_count_by_key(records, "category"),
        "target_activity_source_collection_counts": record_count_by_key(
            records, "source_collection"
        ),
        "target_activity_operation_counts": record_count_by_key(records, "operation"),
        "target_activity_status_counts": record_count_by_key(records, "status"),
        "target_activity_pending_work_counts": record_count_by_key(
            records, "pending_work"
        ),
        "target_activity_waiting_for_counts": record_count_by_key(
            records, "waiting_for"
        ),
        "target_activity_route_kind_counts": record_count_by_key(
            records, "route_kind"
        ),
        "target_activity_bridge_profile_counts": record_count_by_key(
            records, "bridge_profile"
        ),
        "target_activity_target_connectivity_state_counts": record_count_by_key(
            records, "target_connectivity_state"
        ),
        "target_activity_target_offline_age_bucket_counts": record_count_by_key(
            records, "target_offline_age_bucket"
        ),
        "target_activity_target_poll_overdue_counts": record_count_by_key(
            records, "target_poll_overdue"
        ),
        "target_activity_target_mailbox_pending_work_count_counts": record_count_by_key(
            records, "target_mailbox_pending_work_count"
        ),
        "latest_target_activity_record_at": latest_record_value(
            records, ("timestamp",)
        ),
    }
