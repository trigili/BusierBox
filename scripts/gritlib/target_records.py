"""Target record persistence and compatibility helpers for grit-console."""

import time
from pathlib import Path

from gritlib.session_state import (
    parse_utc_timestamp, utc_from_epoch, utc_now,
)
import gritlib.target_attribution as target_attribution
import gritlib.target_filter_display as target_filter_display
import gritlib.target_filter_records as target_filter_records
import gritlib.target_record_display as target_record_display
import gritlib.target_record_status as target_record_status
import gritlib.target_record_updates as target_record_updates
import gritlib.target_registry_state as target_registry_state
import gritlib.target_report_summary as target_report_summary
import gritlib.target_selection as target_selection
from gritlib.target_context import (
    configured_target_filter, details_with_target, records_for_target,
    selected_target_context, target_context_fields,
)
from gritlib.target_mailbox import mailbox_wait_bucket
from gritlib.target_store import load_targets, targets_path


DEFAULT_SERVER_CONFIG = Path("local/server-config.json")
TARGET_ONLINE_WINDOW_SEC = 300
TARGET_RECENT_WINDOW_SEC = 3600
TARGET_STALE_WINDOW_SEC = 86400


def scoped_target_cfg(cfg, target_id, target_label=""):
    return target_selection.scoped_target_cfg(cfg, target_id, target_label=target_label)


def target_mailbox_counts(cfg):
    # Local import preserves the command queue record ownership boundary while
    # reusing command expiry semantics for target summaries.
    from gritlib.command_queue_records import command_queue_expired, load_command_queue

    counts = {}
    latest_result = {}
    latest_result_at = {}
    now_epoch = parse_utc_timestamp(utc_now()) or int(time.time())
    for rec in (load_command_queue(cfg).get("commands") or []):
        if not isinstance(rec, dict):
            continue
        target_id = str(rec.get("target_id") or "")
        if not target_id:
            continue
        target_counts = counts.setdefault(target_id, {
            "queued": 0,
            "delivered": 0,
            "result-received": 0,
            "expired": 0,
            "total": 0,
        })
        status = str(rec.get("status") or "")
        if command_queue_expired(rec, now_epoch=now_epoch):
            status = "expired"
        target_counts["total"] = target_counts.get("total", 0) + 1
        if status in target_counts:
            target_counts[status] = target_counts.get(status, 0) + 1
        result_received_at = str(rec.get("result_received_at") or "")
        if result_received_at and result_received_at >= latest_result_at.get(target_id, ""):
            latest_result_at[target_id] = result_received_at
            latest_result[target_id] = rec
    return counts, latest_result


def print_target_summary(doc, limit=8):
    # Compatibility wrapper for the human "Targets:" summary renderer.
    return target_record_display.print_target_summary(doc, limit=limit)


def record_target_activity(cfg, metadata, service, session_id=""):
    return target_record_updates.record_target_activity(
        cfg,
        metadata,
        service,
        session_id=session_id,
    )


def set_target_label(cfg, target_id, label, aliases=None, notes=None):
    return target_record_updates.set_target_label(
        cfg,
        target_id,
        label,
        aliases=aliases,
        notes=notes,
    )


def set_workbench_target_filter(cfg, selector, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    return target_selection.set_workbench_target_filter(
        cfg,
        selector,
        targets=targets,
        default_config=default_config,
    )


def select_workbench_target_record(selector, targets, *, current_target_id=""):
    return target_selection.select_workbench_target_record(
        selector,
        targets,
        current_target_id=current_target_id,
    )


def print_workbench_target_selector(targets, *, current_target_id="", empty_message="no known targets"):
    return target_selection.print_workbench_target_selector(
        targets,
        current_target_id=current_target_id,
        empty_message=empty_message,
    )


def dispatch_legacy_target_filter_number(choice, cfg, *, input_func=None, snapshot_func=None):
    return target_selection.dispatch_legacy_target_filter_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
    )


def target_identity_from_headers(headers):
    headers = headers or {}
    target_id = str(headers.get("x-grit-target-id") or headers.get("x-grittykit-target-id") or headers.get("x-grit-target") or "").strip()
    if not target_id:
        return {}
    aliases = [
        item.strip()
        for item in str(headers.get("x-grit-target-alias") or headers.get("x-grittykit-target-alias") or "").split(",")
        if item.strip()
    ]
    return {
        "target_id": target_id,
        "target_label": str(headers.get("x-grit-target-label") or headers.get("x-grittykit-target-label") or "").strip(),
        "target_aliases": aliases,
        "target_identity_source": "http-header",
        "target_identity_confidence": "explicit",
    }


def attach_target_identity(metadata, headers):
    metadata = dict(metadata or {})
    metadata.update(target_identity_from_headers(headers))
    return metadata


def capability_report_summary(metadata):
    return target_report_summary.capability_report_summary(metadata)


def compatibility_report_summary(metadata):
    return target_report_summary.compatibility_report_summary(metadata)


def selected_target_record_for_update(cfg):
    return target_record_updates.selected_target_record_for_update(cfg)


def target_connectivity_state(offline_for_sec):
    if offline_for_sec is None:
        return "unknown"
    if offline_for_sec <= TARGET_ONLINE_WINDOW_SEC:
        return "online"
    if offline_for_sec <= TARGET_RECENT_WINDOW_SEC:
        return "recent"
    if offline_for_sec <= TARGET_STALE_WINDOW_SEC:
        return "stale"
    return "offline"


def target_last_seen_via(rec):
    service = str((rec or {}).get("latest_activity_service") or "")
    operation = str((rec or {}).get("latest_activity_operation") or "")
    if service and operation:
        return f"{service}:{operation}"
    return service or operation


def target_next_expected_poll_epoch(rec):
    if str((rec or {}).get("latest_activity_operation") or "") != "command_queue_poll":
        return None
    interval = str((rec or {}).get("latest_command_queue_poll_interval_sec") or "")
    if not interval.isdigit() or int(interval) <= 0:
        return None
    last_seen_epoch = parse_utc_timestamp((rec or {}).get("last_seen_at") or (rec or {}).get("latest_activity_at"))
    if last_seen_epoch is None:
        return None
    return last_seen_epoch + int(interval)


def target_next_expected_poll(rec):
    epoch = target_next_expected_poll_epoch(rec)
    if epoch is None:
        return ""
    return utc_from_epoch(epoch)


def int_value(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def enrich_target_record(rec, now_epoch, mailbox_counts, latest_result):
    last_seen = str(rec.get("last_seen_at") or rec.get("latest_activity_at") or "")
    last_seen_epoch = parse_utc_timestamp(last_seen)
    offline_for_sec = None if last_seen_epoch is None else max(int(now_epoch - last_seen_epoch), 0)
    next_expected_poll_epoch = target_next_expected_poll_epoch(rec)
    poll_overdue_for_sec = (
        None if next_expected_poll_epoch is None
        else max(int(now_epoch - next_expected_poll_epoch), 0)
    )
    counts = mailbox_counts.get(str(rec.get("target_id") or ""), {})
    latest_result_rec = latest_result.get(str(rec.get("target_id") or ""), {})
    stored_pending = rec.get("mailbox_pending_work_count")
    rec["last_seen"] = last_seen
    rec["last_seen_via"] = target_last_seen_via(rec)
    rec["offline_for_sec"] = offline_for_sec if offline_for_sec is not None else ""
    rec["offline_age_bucket"] = mailbox_wait_bucket(rec["offline_for_sec"])
    rec["connectivity_state"] = (
        target_connectivity_state(offline_for_sec)
        if offline_for_sec is not None
        else str(rec.get("connectivity_state") or "unknown")
    )
    rec["connectivity_online_window_sec"] = TARGET_ONLINE_WINDOW_SEC
    rec["connectivity_recent_window_sec"] = TARGET_RECENT_WINDOW_SEC
    rec["connectivity_stale_window_sec"] = TARGET_STALE_WINDOW_SEC
    rec["next_expected_poll"] = "" if next_expected_poll_epoch is None else utc_from_epoch(next_expected_poll_epoch)
    rec["poll_overdue"] = bool(poll_overdue_for_sec and poll_overdue_for_sec > 0)
    rec["poll_overdue_for_sec"] = poll_overdue_for_sec if poll_overdue_for_sec is not None else ""
    rec["mailbox_queued_command_count"] = int(counts.get("queued", 0) or 0)
    rec["mailbox_delivered_command_count"] = int(counts.get("delivered", 0) or 0)
    rec["mailbox_result_received_command_count"] = int(counts.get("result-received", 0) or 0)
    rec["mailbox_expired_command_count"] = int(counts.get("expired", 0) or 0)
    rec["mailbox_command_count"] = int(counts.get("total", 0) or 0)
    rec["mailbox_pending_work_count"] = (
        rec["mailbox_queued_command_count"]
        if counts
        else int_value(stored_pending)
    )
    rec["latest_command_result_at"] = str(latest_result_rec.get("result_received_at") or "")
    rec["latest_command_result_id"] = str(latest_result_rec.get("id") or "")
    return rec


def target_records(cfg):
    targets = load_targets(cfg).get("targets") or {}
    now_epoch = parse_utc_timestamp(utc_now()) or int(time.time())
    mailbox_counts, latest_result = target_mailbox_counts(cfg)
    records = [dict(rec) for rec in targets.values() if isinstance(rec, dict)]
    records = [enrich_target_record(rec, now_epoch, mailbox_counts, latest_result) for rec in records]
    records.sort(key=lambda rec: (str(rec.get("last_seen_at") or ""), str(rec.get("target_id") or "")), reverse=True)
    return records


def target_record_indexes(records):
    return target_record_status.target_record_indexes(records)


def target_record_summary(records):
    return target_record_status.target_record_summary(records)


def target_registry_state_status(target_summary, selected_target=None, target_filter_id="", unfiltered_target_count=0):
    return target_registry_state.target_registry_state_status(
        target_summary,
        selected_target,
        target_filter_id,
        unfiltered_target_count,
    )


def target_registry_state_summary(state_record=None, state_records=None):
    return target_registry_state.target_registry_state_summary(
        state_record,
        state_records,
    )


def target_filter_record_indexes(records):
    return target_filter_records.target_filter_record_indexes(records)


def target_filter_record_from_target(target_filter_id="", selected_target=None):
    return target_filter_records.target_filter_record_from_target(
        target_filter_id,
        selected_target,
    )


def apply_target_filter_activity_counts(
    record,
    target_filter_id="",
    unfiltered=None,
    filtered=None,
):
    return target_filter_records.apply_target_filter_activity_counts(
        record,
        target_filter_id,
        unfiltered,
        filtered,
    )


def target_filter_status_context(
    target_filter_id="",
    selected_target=None,
    unfiltered_counts=None,
    filtered_counts=None,
    target_mailbox_records=None,
):
    return target_filter_records.target_filter_status_context(
        target_filter_id,
        selected_target,
        unfiltered_counts,
        filtered_counts,
        target_mailbox_records,
    )


def target_filter_status_summary(
    record,
    records=None,
    target_filter_id="",
    target_mailbox_records=None,
):
    return target_filter_records.target_filter_status_summary(
        record,
        records,
        target_filter_id,
        target_mailbox_records,
    )


def target_attribution_record_indexes(records):
    return target_attribution.target_attribution_record_indexes(records)


def target_attribution_record_summary(records, attribution=None):
    return target_attribution.target_attribution_record_summary(records, attribution)


def target_attribution_status(uploads=None, fetches=None, sessions=None):
    return target_attribution.target_attribution_status(uploads, fetches, sessions)


def target_filter_evidence_lines(target_filter):
    return target_filter_display.target_filter_evidence_lines(target_filter)


def target_filter_summary_text(target_filter, prefix="target_filter:"):
    return target_filter_display.target_filter_summary_text(target_filter, prefix)


def target_filter_brief_text(target_filter, prefix="selected target:"):
    return target_filter_display.target_filter_brief_text(target_filter, prefix)
