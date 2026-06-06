"""Target record persistence and compatibility helpers for grit-console."""

import time
from pathlib import Path

from gritlib.event_log import append_event, event_for_target
from gritlib.record_utils import (
    int_value, list_merge_unique,
)
from gritlib.session_state import (
    atomic_write_json, parse_utc_timestamp, utc_from_epoch, utc_now,
)
import gritlib.target_attribution as target_attribution
import gritlib.target_filter_display as target_filter_display
import gritlib.target_filter_records as target_filter_records
import gritlib.target_record_display as target_record_display
import gritlib.target_record_status as target_record_status
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
    # Local import preserves the command_queue -> target_records top-level
    # boundary while reusing command expiry semantics for target summaries.
    from gritlib.command_queue import command_queue_expired, load_command_queue

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
    target_id = str((metadata or {}).get("target_id") or "").strip()
    if not target_id:
        return {}
    now = utc_now()
    data, targets, rec = _target_activity_record(cfg, target_id, now)
    confidence, operation = _apply_target_activity_identity(rec, metadata, service, now)
    _apply_command_queue_activity(rec, metadata, operation, now)
    if session_id:
        rec["latest_session_id"] = str(session_id)
    if operation in {"upload", "fetch"}:
        _apply_target_file_transfer_activity(rec, metadata, service, operation, now)
    _apply_target_operation_activity(rec, metadata, service, operation, now)
    targets[target_id] = rec
    atomic_write_json(targets_path(cfg), data)
    _append_target_activity_event(cfg, target_id, rec, metadata, service, session_id, confidence, operation)
    return rec


def _target_activity_record(cfg, target_id, now):
    data = load_targets(cfg)
    targets = data.setdefault("targets", {})
    rec = targets.get(target_id)
    if not isinstance(rec, dict):
        rec = {"target_id": target_id, "first_seen_at": now, "notes": ""}
    rec.setdefault("target_id", target_id)
    rec.setdefault("first_seen_at", now)
    rec["last_seen_at"] = now
    return data, targets, rec


def _apply_target_activity_identity(rec, metadata, service, now):
    label = str((metadata or {}).get("target_label") or "").strip()
    if label:
        rec["label"] = label
    rec["aliases"] = list_merge_unique(rec.get("aliases") or [], (metadata or {}).get("target_aliases") or [])
    rec["remote_addresses"] = list_merge_unique(rec.get("remote_addresses") or [], [metadata.get("remote_addr", "")])
    rec["services_seen"] = list_merge_unique(rec.get("services_seen") or [], [service])
    rec["identity_sources"] = list_merge_unique(rec.get("identity_sources") or [], [metadata.get("target_identity_source", "")])
    confidence = str((metadata or {}).get("target_identity_confidence") or "best-effort")
    rec["identity_confidence"] = confidence
    operation = str((metadata or {}).get("operation") or "seen")
    rec["latest_activity_at"] = now
    rec["latest_activity_service"] = str(service or "")
    rec["latest_activity_operation"] = operation
    rec["latest_activity_remote_addr"] = str(metadata.get("remote_addr") or "")
    rec["latest_activity_status"] = str(metadata.get("status") or "")
    return confidence, operation


def _apply_command_queue_activity(rec, metadata, operation, now):
    if operation == "command_queue_poll":
        rec["latest_command_queue_poll_at"] = now
        for key in ("poll_mode", "poll_interval_sec", "poll_jitter_pct", "poll_backoff", "poll_max_interval_sec", "max_polls"):
            value = str((metadata or {}).get(key) or "")
            if value:
                rec[f"latest_command_queue_{key}"] = value
    if operation == "command_queue_result":
        rec["latest_command_result_activity_at"] = now
        rec["latest_command_result_status"] = str(metadata.get("result_status") or metadata.get("status") or "")


def _apply_target_file_transfer_activity(rec, metadata, service, operation, now):
    rec["latest_file_transfer_at"] = now
    rec["latest_file_transfer_operation"] = operation
    rec["latest_file_transfer_status"] = str(metadata.get("transfer_status") or metadata.get("status") or "")
    rec["latest_file_transfer_service"] = str(service or "")
    rec["latest_file_transfer_id"] = str(
        metadata.get("metadata_path") or
        metadata.get("stored_path") or
        metadata.get("request_name") or
        metadata.get("source_path") or
        metadata.get("filename") or ""
    )
    rec["latest_file_transfer_path"] = str(metadata.get("stored_path") or metadata.get("source_path") or "")
    rec["latest_file_transfer_sha256"] = str(metadata.get("sha256") or "")
    rec["latest_file_transfer_route_kind"] = str(metadata.get("route_kind") or "")
    rec["latest_file_transfer_route_host"] = str(metadata.get("route_host") or "")
    rec["latest_file_transfer_route_port"] = metadata.get("route_port", "")
    rec["latest_file_transfer_bridge_profile"] = str(metadata.get("bridge_profile") or "")
    rec["latest_file_transfer_bridge_route_path"] = str(metadata.get("bridge_route_path") or "")


def _apply_target_operation_activity(rec, metadata, service, operation, now):
    if operation == "upload":
        _apply_target_upload_activity(rec, metadata, now)
    elif operation == "fetch":
        rec["fetch_count"] = int(rec.get("fetch_count", 0) or 0) + 1
        rec["latest_fetch_id"] = str(metadata.get("request_name") or metadata.get("source_path") or "")
        rec["latest_fetch_at"] = now
        rec["latest_fetch_status"] = str(metadata.get("status") or "")
    elif operation == "probe_result":
        rec["latest_survey_result_at"] = now
        rec["latest_survey_result_id"] = str(metadata.get("results_path") or "")
        rec["latest_survey_result_status"] = str(metadata.get("status") or "")
        rec["latest_survey_result_kind"] = "probe"
        rec["latest_survey_result_route_kind"] = str(metadata.get("route_kind") or "")
        rec["latest_survey_result_route_host"] = str(metadata.get("route_host") or "")
        rec["latest_survey_result_route_port"] = metadata.get("route_port", "")
        rec["latest_survey_result_bridge_profile"] = str(metadata.get("bridge_profile") or "")
        rec["latest_survey_result_bridge_route_path"] = str(metadata.get("bridge_route_path") or "")
    elif operation == "probe_script_fn":
        rec["latest_probe_script_at"] = now
        rec["latest_probe_script_status"] = str(metadata.get("status") or "")
        rec["latest_probe_script_route_kind"] = str(metadata.get("route_kind") or "")
        rec["latest_probe_script_bridge_profile"] = str(metadata.get("bridge_profile") or "")
        rec["latest_probe_script_bridge_route_path"] = str(metadata.get("bridge_route_path") or "")
    elif operation in {"bridge_listener", "bridge_relay", "bridge_error"}:
        rec["latest_bridge_activity_at"] = now
        rec["latest_bridge_operation"] = operation
        rec["latest_bridge_status"] = str(metadata.get("status") or "")
        rec["latest_bridge_profile"] = str(metadata.get("bridge_profile") or "")
        rec["latest_bridge_route_path"] = str(metadata.get("bridge_route_path") or "")
        rec["latest_bridge_dest_host"] = str(metadata.get("bridge_dest_host") or "")
        rec["latest_bridge_dest_port"] = str(metadata.get("bridge_dest_port") or "")
        rec["latest_bridge_failure_reason"] = str(metadata.get("reason") or "") if operation == "bridge_error" or metadata.get("status") == "error" else ""
        if metadata.get("status") in {"closed", "connected", "listening"}:
            rec["latest_bridge_success_at"] = now


def _apply_target_upload_activity(rec, metadata, now):
    rec["upload_count"] = int(rec.get("upload_count", 0) or 0) + 1
    rec["latest_upload_id"] = str(metadata.get("metadata_path") or metadata.get("stored_path") or metadata.get("filename") or "")
    rec["latest_upload_at"] = now
    rec["latest_upload_status"] = str(metadata.get("transfer_status") or metadata.get("status") or "")
    if str(metadata.get("upload_kind") or "") in {"reality-test", "capability-report", "survey"}:
        rec["latest_survey_result_at"] = now
        rec["latest_survey_result_id"] = str(metadata.get("metadata_path") or metadata.get("stored_path") or "")
        rec["latest_survey_result_status"] = str(metadata.get("transfer_status") or metadata.get("status") or "")
        rec["latest_survey_result_kind"] = str(metadata.get("upload_kind") or "")
        rec["latest_capability_report"] = str(metadata.get("metadata_path") or metadata.get("stored_path") or "")
        rec["latest_capability_report_path"] = str(metadata.get("stored_path") or "")
        rec["latest_capability_report_metadata_path"] = str(metadata.get("metadata_path") or "")
        rec["latest_capability_report_kind"] = str(metadata.get("upload_kind") or "")
        observed = capability_report_summary(metadata)
        if observed:
            rec["latest_capability_summary"] = observed
            rec["observed_capabilities"] = list_merge_unique(rec.get("observed_capabilities") or [], observed.get("available") or [])
            rec["observed_missing_capabilities"] = list_merge_unique(rec.get("observed_missing_capabilities") or [], observed.get("unavailable") or [])
            rec["observed_constraints"] = observed.get("constraints") or {}
    compatibility = compatibility_report_summary(metadata)
    if compatibility:
        rec["latest_compatibility_report"] = str(metadata.get("metadata_path") or metadata.get("stored_path") or "")
        rec["latest_compatibility_report_path"] = str(metadata.get("stored_path") or "")
        rec["latest_compatibility_report_metadata_path"] = str(metadata.get("metadata_path") or "")
        rec["latest_compatibility_report_kind"] = str(metadata.get("upload_kind") or "")
        rec["latest_compatibility_summary"] = compatibility
        rec["latest_compatibility_label"] = compatibility.get("label", "")
        rec["latest_compatibility_baseline_label"] = compatibility.get("baseline_label", "")
        rec["latest_compatibility_release_name"] = compatibility.get("release_name", "")
        rec["latest_compatibility_artifact"] = compatibility.get("artifact", "")
        rec["latest_compatibility_tuple_path"] = compatibility.get("tuple_path", "")
        rec["latest_compatibility_payload_preset"] = compatibility.get("payload_preset", "")


def _append_target_activity_event(cfg, target_id, rec, metadata, service, session_id, confidence, operation):
    append_event(cfg, "targets", "target_seen", details={
        "target_id": target_id,
        "target_label": rec.get("label", ""),
        "identity_confidence": confidence,
        "identity_source": metadata.get("target_identity_source", ""),
        "service": service,
        "activity_operation": operation,
        "remote_addr": metadata.get("remote_addr", ""),
        "session_id": session_id,
    })


def set_target_label(cfg, target_id, label, aliases=None, notes=None):
    target_id = str(target_id or "").strip()
    if not target_id:
        raise ValueError("target id is required")
    data = load_targets(cfg)
    targets = data.setdefault("targets", {})
    rec = targets.get(target_id)
    if not isinstance(rec, dict):
        now = utc_now()
        rec = {"target_id": target_id, "first_seen_at": now, "last_seen_at": now, "notes": ""}
    rec["label"] = str(label or "").strip()
    rec["aliases"] = list_merge_unique(rec.get("aliases") or [], aliases or [])
    if notes is not None:
        rec["notes"] = str(notes)
    targets[target_id] = rec
    atomic_write_json(targets_path(cfg), data)
    append_event(cfg, "targets", "target_label_set", details={
        "target_id": target_id,
        "target_label": rec.get("label", ""),
        "aliases": rec.get("aliases") or [],
    })
    return rec


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
    target_id = configured_target_filter(cfg)
    if not target_id:
        raise ValueError("select a target before setting target options")
    rec = (load_targets(cfg).get("targets") or {}).get(target_id)
    if not isinstance(rec, dict):
        rec = {"target_id": target_id, "label": "", "aliases": [], "notes": ""}
    return target_id, rec


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
    rec["last_seen"] = last_seen
    rec["last_seen_via"] = target_last_seen_via(rec)
    rec["offline_for_sec"] = offline_for_sec if offline_for_sec is not None else ""
    rec["offline_age_bucket"] = mailbox_wait_bucket(rec["offline_for_sec"])
    rec["connectivity_state"] = target_connectivity_state(offline_for_sec)
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
    rec["mailbox_pending_work_count"] = rec["mailbox_queued_command_count"]
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


def target_filter_brief_text(target_filter, prefix="selected agent:"):
    return target_filter_display.target_filter_brief_text(target_filter, prefix)
