"""Target record index and summary helpers for grit-console."""

import json
import time
from pathlib import Path

from gritlib.event_log import append_event, event_for_target
from gritlib.record_utils import (
    count_records_with_key, int_value, list_merge_unique, record_count_by_key,
    records_by_key,
)
from gritlib.shell_utils import shquote
from gritlib.session_state import (
    atomic_write_json, parse_utc_timestamp, read_json_file, update_server_state,
    utc_from_epoch, utc_now,
)
from gritlib.target_mailbox import mailbox_wait_bucket


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_SERVER_CONFIG = Path("local/server-config.json")
TARGET_ONLINE_WINDOW_SEC = 300
TARGET_RECENT_WINDOW_SEC = 3600
TARGET_STALE_WINDOW_SEC = 86400


def targets_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("targets_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "targets.json"
    ))


def load_targets(cfg):
    data = read_json_file(targets_path(cfg), {"schema": 1, "targets": {}})
    if not isinstance(data, dict):
        data = {"schema": 1, "targets": {}}
    if not isinstance(data.get("targets"), dict):
        data["targets"] = {}
    data.setdefault("schema", 1)
    return data


def scoped_target_cfg(cfg, target_id, target_label=""):
    scoped = dict(cfg)
    scoped["_target_id_filter"] = str(target_id or "").strip()
    if target_label:
        scoped["_target_label_filter"] = str(target_label or "")
    return scoped


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


def record_target_activity(cfg, metadata, service, session_id=""):
    target_id = str((metadata or {}).get("target_id") or "").strip()
    if not target_id:
        return {}
    now = utc_now()
    data = load_targets(cfg)
    targets = data.setdefault("targets", {})
    rec = targets.get(target_id)
    if not isinstance(rec, dict):
        rec = {"target_id": target_id, "first_seen_at": now, "notes": ""}
    rec.setdefault("target_id", target_id)
    rec.setdefault("first_seen_at", now)
    rec["last_seen_at"] = now
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
    if operation == "command_queue_poll":
        rec["latest_command_queue_poll_at"] = now
        for key in ("poll_mode", "poll_interval_sec", "poll_jitter_pct", "poll_backoff", "poll_max_interval_sec", "max_polls"):
            value = str((metadata or {}).get(key) or "")
            if value:
                rec[f"latest_command_queue_{key}"] = value
    if operation == "command_queue_result":
        rec["latest_command_result_activity_at"] = now
        rec["latest_command_result_status"] = str(metadata.get("result_status") or metadata.get("status") or "")
    if session_id:
        rec["latest_session_id"] = str(session_id)
    if operation in {"upload", "fetch"}:
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
    if operation == "upload":
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
    targets[target_id] = rec
    atomic_write_json(targets_path(cfg), data)
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
    return rec


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
    text = str(selector or "").strip()
    now = utc_now()
    config_path = str(cfg.get("_config_path", default_config))
    if text.lower() in ("", "all", "clear", "*"):
        cfg.pop("_target_id_filter", None)
        cfg.pop("_target_label_filter", None)
        update_server_state(cfg, "workbench", "open", {
            "selected_target_id": "",
            "selected_target_label": "",
            "selected_target_at": now,
        })
        headless = "scripts/grit-console --config " + shquote(config_path) + " --status"
        append_event(cfg, "workbench", "workbench_target_filter_cleared", details={
            "selected_at": now,
            "headless_command": headless,
        })
        return {"target_id": "", "target_label": "", "selected": False, "headless_command": headless}

    records = []
    if targets is not None:
        records = [rec for rec in targets or [] if isinstance(rec, dict)]
    else:
        for target_id, rec in sorted((load_targets(cfg).get("targets") or {}).items()):
            if isinstance(rec, dict):
                item = dict(rec)
                item.setdefault("target_id", target_id)
                records.append(item)
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"target number out of range: {text}")
        selected = records[idx]
    else:
        lower = text.lower()
        selected = {}
        for rec in records:
            target_id = str(rec.get("target_id") or "")
            label = str(rec.get("label") or rec.get("target_label") or "")
            aliases = [str(item) for item in rec.get("aliases") or []]
            if text == target_id or lower == label.lower() or lower in [alias.lower() for alias in aliases]:
                selected = rec
                break
        if not selected:
            raise ValueError(f"target not found: {text}")
    target_id = str(selected.get("target_id") or "").strip()
    if not target_id:
        raise ValueError(f"target not found: {text}")
    target_label = str(selected.get("label") or selected.get("target_label") or "")
    cfg["_target_id_filter"] = target_id
    if target_label:
        cfg["_target_label_filter"] = target_label
    else:
        cfg.pop("_target_label_filter", None)
    update_server_state(cfg, "workbench", "open", {
        "selected_target_id": target_id,
        "selected_target_label": target_label,
        "selected_target_at": now,
    })
    headless = (
        "scripts/grit-console --config "
        + shquote(config_path)
        + " --target-id "
        + shquote(target_id)
        + " --status"
    )
    append_event(cfg, "workbench", "workbench_target_selected", details={
        "target_id": target_id,
        "target_label": target_label,
        "selected_at": now,
        "headless_command": headless,
    })
    return {
        "target_id": target_id,
        "target_label": target_label,
        "selected": True,
        "headless_command": headless,
    }


def select_workbench_target_record(selector, targets, *, current_target_id=""):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("target selector is required")
    records = [rec for rec in targets or [] if isinstance(rec, dict)]
    current = str(current_target_id or "").strip()
    if text.lower() == "current":
        if not current:
            raise ValueError("no current target filter is selected")
        for rec in records:
            if str(rec.get("target_id") or "") == current:
                return {"scope": "target", "target": rec}
        raise ValueError(f"target not found: {current}")
    if text.lower() in ("all", "*"):
        return {"scope": "all", "target": {}}
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"target number out of range: {text}")
        return {"scope": "target", "target": records[idx]}
    lower = text.lower()
    for rec in records:
        target_id = str(rec.get("target_id") or "")
        label = str(rec.get("label") or rec.get("target_label") or "")
        aliases = [str(item) for item in rec.get("aliases") or []]
        if text == target_id or lower == label.lower() or lower in [alias.lower() for alias in aliases]:
            return {"scope": "target", "target": rec}
    raise ValueError(f"target not found: {text}")


def print_workbench_target_selector(targets, *, current_target_id="", empty_message="no known targets"):
    records = [rec for rec in targets or [] if isinstance(rec, dict)]
    current = str(current_target_id or "").strip()
    if not records:
        print(empty_message)
        return
    for idx, rec in enumerate(records, 1):
        marker = "*" if str(rec.get("target_id") or "") == current else " "
        print(
            f"{idx}:{marker} {rec.get('target_id', '')} "
            f"label={rec.get('label', '') or '-'} "
            f"state={rec.get('connectivity_state', '') or '-'} "
            f"mailbox_pending={rec.get('mailbox_pending_work_count', 0)} "
            f"poll_overdue={'yes' if rec.get('poll_overdue') else 'no'} "
            f"last_seen={rec.get('last_seen', '') or rec.get('last_seen_at', '') or '-'}"
        )


def dispatch_legacy_target_filter_number(choice, cfg, *, input_func=None, snapshot_func=None):
    if str(choice or "").strip() != "16":
        return False
    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg) if snapshot_func else {}
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    print_workbench_target_selector(
        targets,
        current_target_id=current,
        empty_message="no known targets; use all/clear to remove any current filter",
    )
    selected_line = input_func("target number/id/label, or all to clear> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        try:
            rec = set_workbench_target_filter(cfg, selected, targets=targets)
            if rec.get("selected"):
                print(f"selected target {rec.get('target_id', '')} label={rec.get('target_label', '') or '-'}")
            else:
                print("target filter cleared")
        except ValueError as exc:
            print(exc)
    return True


def dispatch_legacy_target_detail_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    append_event_fn=None,
    scoped_target_cfg_func=None,
    print_summary_func=None,
    action_state_text_func=None,
):
    if str(choice or "").strip() != "18":
        return False
    # Local import preserves the target_activity -> target_records top-level
    # boundary; this legacy prompt only needs the activity printer on demand.
    from gritlib.target_activity import print_target_activity_records

    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg) if snapshot_func else {}
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    print_workbench_target_selector(targets, current_target_id=current)
    selected_line = input_func("target number/id/label, current, or all> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if not selected:
        return True
    try:
        selection = select_workbench_target_record(selected, targets, current_target_id=current)
        target = selection.get("target") or {}
        if selection.get("scope") == "all":
            headless = (
                "scripts/grit-console --config "
                + shquote(str(cfg.get("_config_path", DEFAULT_SERVER_CONFIG)))
                + " --status"
            )
            if print_summary_func:
                print_summary_func(snap)
            activity_count = len(snap.get("target_activity_records") or [])
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_targets_inspected", details={
                    "headless_command": headless,
                    "scope": "all",
                    "target_count": len(targets),
                    "target_activity_record_count": activity_count,
                })
            return True
        target_id = str(target.get("target_id") or "")
        target_label = str(target.get("label") or target.get("target_label") or "")
        scoped = (
            scoped_target_cfg_func(cfg, target_id, target_label=target_label)
            if scoped_target_cfg_func else cfg
        )
        scoped_snap = snapshot_func(scoped) if snapshot_func else {}
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_SERVER_CONFIG)))
            + " --target-id "
            + shquote(target_id)
            + " --status"
        )
        print(f"Target detail: {target_id} label={target_label or '-'}")
        if print_summary_func:
            print_summary_func(scoped_snap, limit=3)
        target_activity_count = len(scoped_snap.get("target_activity_records") or [])
        print_target_activity_records(scoped_snap, target_id=target_id, limit=5)
        actions = scoped_snap.get("target_workflow_actions") or []
        if actions:
            print("Target workflow actions:")
            for idx, rec in enumerate(actions[:8], 1):
                state = action_state_text_func(rec) if action_state_text_func else str(rec.get("operator_action_state") or "-")
                print(f"  {idx}: {rec.get('id', '')} {rec.get('label', '')}")
                print(
                    f"     offline={'yes' if rec.get('offline_supported') else 'no'} "
                    f"requires_online={'yes' if rec.get('requires_target_online') else 'no'} "
                    f"queues_offline_work={'yes' if rec.get('queues_offline_work') else 'no'} "
                    f"state={state} "
                    f"reason={rec.get('operator_action_reason', '') or '-'} "
                    f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'}"
                )
        if append_event_fn:
            append_event_fn(cfg, "workbench", "workbench_target_inspected", details={
                "target_id": target_id,
                "target_label": target_label,
                "headless_command": headless,
                "mailbox_pending_work_count": target.get("mailbox_pending_work_count", 0),
                "last_seen": target.get("last_seen", "") or target.get("last_seen_at", ""),
                "target_activity_record_count": target_activity_count,
            })
    except ValueError as exc:
        print(exc)
    return True


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
    stored_path = str((metadata or {}).get("stored_path") or "").strip()
    if not stored_path:
        return {}
    path = Path(stored_path)
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, dict):
        return {}
    checks = [
        item for item in (report.get("checks") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    observed = {
        "schema": 1,
        "kind": str((metadata or {}).get("upload_kind") or ""),
        "path": stored_path,
        "metadata_path": str((metadata or {}).get("metadata_path") or ""),
        "sha256": str((metadata or {}).get("sha256") or ""),
        "check_count": len(checks),
        "pass_count": int(summary.get("pass", 0) or 0),
        "fail_count": int(summary.get("fail", 0) or 0),
        "skipped_count": int(summary.get("skipped", 0) or 0),
        "capability_pass_count": int(summary.get("capability_pass", 0) or 0),
        "capability_fail_count": int(summary.get("capability_fail", 0) or 0),
        "operator_pass_count": int(summary.get("operator_pass", 0) or 0),
        "operator_fail_count": int(summary.get("operator_fail", 0) or 0),
        "operator_skipped_count": int(summary.get("operator_skipped", 0) or 0),
        "available": [],
        "unavailable": [],
        "skipped": [],
        "constraints": summary.get("constraints") if isinstance(summary.get("constraints"), dict) else {},
    }
    for item in checks:
        name = str(item.get("name") or "")
        if not name:
            continue
        if item.get("skipped") is True:
            observed["skipped"].append(name)
        elif item.get("ok") is True or item.get("available") is True:
            observed["available"].append(name)
        elif item.get("ok") is False or item.get("available") is False:
            observed["unavailable"].append(name)
    return observed


def compatibility_report_summary(metadata):
    stored_path = str((metadata or {}).get("stored_path") or "").strip()
    if not stored_path:
        return {}
    path = Path(stored_path)
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, dict):
        return {}
    selected = report.get("selected") if isinstance(report.get("selected"), dict) else {}
    compatibility = report.get("effective_compatibility")
    if not isinstance(compatibility, dict):
        compatibility = selected.get("effective_compatibility")
    if not isinstance(compatibility, dict):
        compatibility = report.get("compatibility")
    if not isinstance(compatibility, dict):
        compatibility = selected.get("compatibility")
    if not isinstance(compatibility, dict):
        return {}
    label = str(compatibility.get("label") or "")
    if not label:
        return {}
    baseline = str(compatibility.get("baseline_label") or ((selected.get("compatibility") or {}).get("label") if isinstance(selected.get("compatibility"), dict) else "") or "")
    return {
        "schema": 1,
        "kind": str((metadata or {}).get("upload_kind") or ""),
        "path": stored_path,
        "metadata_path": str((metadata or {}).get("metadata_path") or ""),
        "sha256": str((metadata or {}).get("sha256") or ""),
        "label": label,
        "baseline_label": baseline,
        "source": str(compatibility.get("source") or report.get("command") or ""),
        "reason_count": len(compatibility.get("reasons") or []),
        "reasons": [str(item) for item in (compatibility.get("reasons") or [])],
        "release_name": str(selected.get("release_name") or report.get("release_name") or ""),
        "artifact": str(selected.get("artifact") or selected.get("artifact_path") or report.get("artifact") or ""),
        "tuple_path": str(selected.get("tuple_path") or report.get("tuple_path") or ""),
        "payload_preset": str(selected.get("payload_preset") or report.get("payload_preset") or ""),
    }


def configured_target_filter(cfg):
    return str(cfg.get("_target_id_filter") or "").strip()


def selected_target_record_for_update(cfg):
    target_id = configured_target_filter(cfg)
    if not target_id:
        raise ValueError("select a target before setting target options")
    rec = (load_targets(cfg).get("targets") or {}).get(target_id)
    if not isinstance(rec, dict):
        rec = {"target_id": target_id, "label": "", "aliases": [], "notes": ""}
    return target_id, rec


def records_for_target(records, target_id):
    if not target_id:
        return list(records or [])
    return [
        rec for rec in records or []
        if isinstance(rec, dict) and str(rec.get("target_id") or "") == target_id
    ]


def target_context_fields(cfg, target_id):
    target_id = str(target_id or "").strip()
    if not target_id:
        return {}
    rec = (load_targets(cfg).get("targets") or {}).get(target_id)
    if not isinstance(rec, dict):
        rec = {}
    aliases = list_merge_unique(rec.get("aliases") or [], cfg.get("_target_alias_filter") or [])
    return {
        "target_id": target_id,
        "target_label": str(cfg.get("_target_label_filter") or rec.get("label") or ""),
        "target_aliases": [
            str(item) for item in aliases
            if str(item or "")
        ],
        "target_identity_source": "operator-selection",
        "target_identity_confidence": "operator-assigned",
    }


def selected_target_context(cfg):
    return target_context_fields(cfg, configured_target_filter(cfg))


def details_with_target(cfg, details=None, target_context=None):
    out = dict(details or {})
    ctx = dict(target_context if target_context is not None else selected_target_context(cfg))
    for key, value in ctx.items():
        if value not in (None, ""):
            out.setdefault(key, value)
    return out


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


def _target_record_identity_indexes(records):
    by_id = {}
    by_label = {}
    by_alias = {}
    by_remote_addr = {}
    by_service = {}
    by_identity_confidence = {}
    by_identity_source = {}
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
    by_has_notes = {}
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
    return (
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
    )


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


def _target_record_activity_summary(records):
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
    remote_count = 0
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
    return {
        "service_counts": service_counts,
        "identity_source_counts": identity_source_counts,
        "latest_activity_service_counts": latest_activity_service_counts,
        "latest_activity_operation_counts": latest_activity_operation_counts,
        "connectivity_state_counts": connectivity_state_counts,
        "last_seen_via_counts": last_seen_via_counts,
        "offline_age_bucket_counts": offline_age_bucket_counts,
        "latest_file_transfer_operation_counts": latest_file_transfer_operation_counts,
        "latest_file_transfer_status_counts": latest_file_transfer_status_counts,
        "latest_file_transfer_route_kind_counts": latest_file_transfer_route_kind_counts,
        "latest_file_transfer_bridge_profile_counts": latest_file_transfer_bridge_profile_counts,
        "latest_survey_result_kind_counts": latest_survey_result_kind_counts,
        "latest_survey_result_status_counts": latest_survey_result_status_counts,
        "latest_survey_result_route_kind_counts": latest_survey_result_route_kind_counts,
        "latest_survey_result_bridge_profile_counts": latest_survey_result_bridge_profile_counts,
        "latest_bridge_profile_counts": latest_bridge_profile_counts,
        "latest_bridge_status_counts": latest_bridge_status_counts,
        "remote_count": remote_count,
        "notes_count": notes_count,
        "next_expected_poll_count": next_expected_poll_count,
        "poll_overdue_count": poll_overdue_count,
        "mailbox_pending_target_count": mailbox_pending_target_count,
        "mailbox_pending_work_count": mailbox_pending_work_count,
        "phone_home_target_count": phone_home_target_count,
        "failed_phone_home_target_count": failed_phone_home_target_count,
        "successful_phone_home_count": successful_phone_home_count,
        "failed_phone_home_count": failed_phone_home_count,
        "latest_file_transfer_count": latest_file_transfer_count,
        "latest_survey_result_count": latest_survey_result_count,
        "latest_bridge_activity_count": latest_bridge_activity_count,
    }


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


def target_registry_state_status(target_summary, selected_target=None, target_filter_id="", unfiltered_target_count=0):
    target_summary = target_summary if isinstance(target_summary, dict) else {}
    selected_target = selected_target if isinstance(selected_target, dict) else {}
    selected_target_sources = selected_target.get("identity_sources") or []
    selected_target_capability_summary = selected_target.get("latest_capability_summary") or {}
    if not isinstance(selected_target_capability_summary, dict):
        selected_target_capability_summary = {}
    selected_target_compatibility_summary = selected_target.get("latest_compatibility_summary") or {}
    if not isinstance(selected_target_compatibility_summary, dict):
        selected_target_compatibility_summary = {}
    state_record = {
        "id": "target-registry",
        "target_count": int_value(target_summary.get("target_count", 0)),
        "unfiltered_target_count": int_value(unfiltered_target_count),
        "filter_active": bool(target_filter_id),
        "filter_target_id": target_filter_id,
        "selected_target_found": bool(selected_target),
        "selected_target_label": str(selected_target.get("label") or ""),
        "selected_target_identity_confidence": str(selected_target.get("identity_confidence") or ""),
        "selected_target_connectivity_state": str(selected_target.get("connectivity_state") or ""),
        "selected_target_last_seen": str(selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""),
        "selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "selected_target_offline_age_bucket": str(selected_target.get("offline_age_bucket") or ""),
        "selected_target_latest_phone_home_at": str(selected_target.get("latest_phone_home_at") or ""),
        "selected_target_latest_phone_home_status": str(selected_target.get("latest_phone_home_status") or ""),
        "selected_target_latest_phone_home_kind": str(selected_target.get("latest_phone_home_kind") or ""),
        "selected_target_latest_phone_home_contact_path": str(selected_target.get("latest_phone_home_contact_path") or ""),
        "selected_target_latest_successful_phone_home_at": str(selected_target.get("latest_successful_phone_home_at") or ""),
        "selected_target_latest_successful_phone_home_status": str(selected_target.get("latest_successful_phone_home_status") or ""),
        "selected_target_latest_successful_phone_home_kind": str(selected_target.get("latest_successful_phone_home_kind") or ""),
        "selected_target_latest_successful_phone_home_contact_path": str(selected_target.get("latest_successful_phone_home_contact_path") or ""),
        "selected_target_last_failed_phone_home_at": str(selected_target.get("last_failed_phone_home_at") or ""),
        "selected_target_last_failed_phone_home_status": str(selected_target.get("last_failed_phone_home_status") or ""),
        "selected_target_last_failed_phone_home_reason": str(selected_target.get("last_failed_phone_home_reason") or ""),
        "selected_target_last_failed_phone_home_contact_path": str(selected_target.get("last_failed_phone_home_contact_path") or ""),
        "selected_target_next_expected_poll": str(selected_target.get("next_expected_poll") or ""),
        "selected_target_poll_overdue": bool(selected_target.get("poll_overdue", False)),
        "selected_target_poll_overdue_for_sec": selected_target.get("poll_overdue_for_sec", ""),
        "selected_target_mailbox_command_count": int_value(selected_target.get("mailbox_command_count", 0)),
        "selected_target_mailbox_pending_work_count": int_value(selected_target.get("mailbox_pending_work_count", 0)),
        "selected_target_identity_source_count": len(selected_target_sources),
        "selected_target_alias_count": len(selected_target.get("aliases") or []),
        "selected_target_notes_present": bool(str(selected_target.get("notes") or "").strip()),
        "selected_target_latest_file_transfer_operation": str(selected_target.get("latest_file_transfer_operation") or ""),
        "selected_target_latest_file_transfer_status": str(selected_target.get("latest_file_transfer_status") or ""),
        "selected_target_latest_file_transfer_route_kind": str(selected_target.get("latest_file_transfer_route_kind") or ""),
        "selected_target_latest_file_transfer_bridge_profile": str(selected_target.get("latest_file_transfer_bridge_profile") or ""),
        "selected_target_latest_survey_result_kind": str(selected_target.get("latest_survey_result_kind") or ""),
        "selected_target_latest_survey_result_status": str(selected_target.get("latest_survey_result_status") or ""),
        "selected_target_latest_survey_result_route_kind": str(selected_target.get("latest_survey_result_route_kind") or ""),
        "selected_target_latest_survey_result_bridge_profile": str(selected_target.get("latest_survey_result_bridge_profile") or ""),
        "selected_target_latest_bridge_profile": str(selected_target.get("latest_bridge_profile") or ""),
        "selected_target_latest_bridge_status": str(selected_target.get("latest_bridge_status") or ""),
        "selected_target_latest_bridge_route_path": str(selected_target.get("latest_bridge_route_path") or ""),
        "selected_target_latest_bridge_failure_reason": str(selected_target.get("latest_bridge_failure_reason") or ""),
        "selected_target_latest_capability_report_kind": str(selected_target.get("latest_capability_report_kind") or ""),
        "selected_target_latest_capability_check_count": int_value(selected_target_capability_summary.get("check_count", 0)),
        "selected_target_latest_capability_pass_count": int_value(selected_target_capability_summary.get("capability_pass_count", 0)),
        "selected_target_latest_capability_fail_count": int_value(selected_target_capability_summary.get("capability_fail_count", 0)),
        "selected_target_latest_compatibility_report_kind": str(selected_target.get("latest_compatibility_report_kind") or ""),
        "selected_target_latest_compatibility_label": str(selected_target.get("latest_compatibility_label") or ""),
        "selected_target_latest_compatibility_baseline_label": str(selected_target.get("latest_compatibility_baseline_label") or ""),
        "selected_target_latest_compatibility_release_name": str(selected_target.get("latest_compatibility_release_name") or ""),
        "selected_target_latest_compatibility_payload_preset": str(selected_target.get("latest_compatibility_payload_preset") or ""),
        "selected_target_latest_compatibility_reason_count": int_value(selected_target_compatibility_summary.get("reason_count", 0)),
        "latest_target_id": str(target_summary.get("latest_target_id") or ""),
        "latest_target_label": str(target_summary.get("latest_target_label") or ""),
        "latest_target_seen_at": str(target_summary.get("latest_target_seen_at") or ""),
        "remote_address_count": int_value(target_summary.get("target_remote_address_count", 0)),
        "notes_count": int_value(target_summary.get("target_notes_count", 0)),
        "without_notes_count": int_value(target_summary.get("target_without_notes_count", 0)),
        "identity_confidence_counts": target_summary.get("target_identity_confidence_counts") or {},
        "identity_source_counts": target_summary.get("target_identity_source_counts") or {},
        "service_counts": target_summary.get("target_service_counts") or {},
        "latest_activity_service_counts": target_summary.get("target_latest_activity_service_counts") or {},
        "latest_activity_operation_counts": target_summary.get("target_latest_activity_operation_counts") or {},
        "connectivity_state_counts": target_summary.get("target_connectivity_state_counts") or {},
        "last_seen_via_counts": target_summary.get("target_last_seen_via_counts") or {},
        "latest_phone_home_status_counts": target_summary.get("target_latest_phone_home_status_counts") or {},
        "last_failed_phone_home_status_counts": target_summary.get("target_last_failed_phone_home_status_counts") or {},
        "last_failed_phone_home_reason_counts": target_summary.get("target_last_failed_phone_home_reason_counts") or {},
        "failed_phone_home_target_count": int_value(target_summary.get("target_failed_phone_home_target_count", 0)),
        "failed_phone_home_count": int_value(target_summary.get("target_failed_phone_home_count", 0)),
        "next_expected_poll_count": int_value(target_summary.get("target_next_expected_poll_count", 0)),
        "poll_overdue_count": int_value(target_summary.get("target_poll_overdue_count", 0)),
        "poll_overdue_counts": target_summary.get("target_poll_overdue_counts") or {},
        "mailbox_pending_target_count": int_value(target_summary.get("target_mailbox_pending_target_count", 0)),
        "mailbox_pending_work_count": int_value(target_summary.get("target_mailbox_pending_work_count", 0)),
        "latest_file_transfer_count": int_value(target_summary.get("target_latest_file_transfer_count", 0)),
        "latest_survey_result_count": int_value(target_summary.get("target_latest_survey_result_count", 0)),
        "latest_bridge_activity_count": int_value(target_summary.get("target_latest_bridge_activity_count", 0)),
        "capability_report_count": int_value(target_summary.get("target_capability_report_count", 0)),
        "compatibility_report_count": int_value(target_summary.get("target_compatibility_report_count", 0)),
        "compatibility_label_counts": target_summary.get("target_compatibility_label_counts") or {},
        "compatibility_baseline_label_counts": target_summary.get("target_compatibility_baseline_label_counts") or {},
        "compatibility_release_counts": target_summary.get("target_compatibility_release_counts") or {},
        "compatibility_payload_preset_counts": target_summary.get("target_compatibility_payload_preset_counts") or {},
    }
    state_record.update({
        "has_targets": state_record.get("target_count", 0) > 0,
        "has_unfiltered_targets": state_record.get("unfiltered_target_count", 0) > 0,
        "has_selected_target": bool(selected_target),
        "has_latest_activity": bool(
            state_record.get("latest_activity_service_counts") or
            state_record.get("latest_activity_operation_counts")
        ),
        "has_next_expected_polls": state_record.get("next_expected_poll_count", 0) > 0,
        "has_poll_overdue": state_record.get("poll_overdue_count", 0) > 0,
        "has_mailbox_pending_work": state_record.get("mailbox_pending_work_count", 0) > 0,
        "has_failed_phone_home": state_record.get("failed_phone_home_target_count", 0) > 0,
        "has_latest_file_transfer": state_record.get("latest_file_transfer_count", 0) > 0,
        "has_latest_survey_result": state_record.get("latest_survey_result_count", 0) > 0,
        "has_latest_bridge_activity": state_record.get("latest_bridge_activity_count", 0) > 0,
        "has_identity_sources": bool(state_record.get("identity_source_counts")),
        "has_capability_reports": state_record.get("capability_report_count", 0) > 0,
        "has_compatibility_reports": state_record.get("compatibility_report_count", 0) > 0,
    })
    state_records = [state_record]
    state_index_maps = {
        "target_registry_state_records_by_id": {rec.get("id", ""): rec for rec in state_records if rec.get("id")},
        "target_registry_state_records_by_has_targets": records_by_key(state_records, "has_targets"),
        "target_registry_state_records_by_has_unfiltered_targets": records_by_key(state_records, "has_unfiltered_targets"),
        "target_registry_state_records_by_filter_active": records_by_key(state_records, "filter_active"),
        "target_registry_state_records_by_filter_target_id": records_by_key(state_records, "filter_target_id"),
        "target_registry_state_records_by_selected_target_found": records_by_key(state_records, "selected_target_found"),
        "target_registry_state_records_by_selected_target_identity_confidence": records_by_key(state_records, "selected_target_identity_confidence"),
        "target_registry_state_records_by_selected_target_connectivity_state": records_by_key(state_records, "selected_target_connectivity_state"),
        "target_registry_state_records_by_selected_target_offline_age_bucket": records_by_key(state_records, "selected_target_offline_age_bucket"),
        "target_registry_state_records_by_selected_target_latest_phone_home_status": records_by_key(state_records, "selected_target_latest_phone_home_status"),
        "target_registry_state_records_by_selected_target_latest_successful_phone_home_status": records_by_key(state_records, "selected_target_latest_successful_phone_home_status"),
        "target_registry_state_records_by_selected_target_last_failed_phone_home_status": records_by_key(state_records, "selected_target_last_failed_phone_home_status"),
        "target_registry_state_records_by_selected_target_poll_overdue": records_by_key(state_records, "selected_target_poll_overdue"),
        "target_registry_state_records_by_selected_target_mailbox_pending_work_count": records_by_key(state_records, "selected_target_mailbox_pending_work_count"),
        "target_registry_state_records_by_selected_target_latest_file_transfer_status": records_by_key(state_records, "selected_target_latest_file_transfer_status"),
        "target_registry_state_records_by_selected_target_latest_file_transfer_route_kind": records_by_key(state_records, "selected_target_latest_file_transfer_route_kind"),
        "target_registry_state_records_by_selected_target_latest_survey_result_status": records_by_key(state_records, "selected_target_latest_survey_result_status"),
        "target_registry_state_records_by_selected_target_latest_survey_result_route_kind": records_by_key(state_records, "selected_target_latest_survey_result_route_kind"),
        "target_registry_state_records_by_selected_target_latest_bridge_profile": records_by_key(state_records, "selected_target_latest_bridge_profile"),
        "target_registry_state_records_by_selected_target_latest_bridge_status": records_by_key(state_records, "selected_target_latest_bridge_status"),
        "target_registry_state_records_by_selected_target_latest_capability_report_kind": records_by_key(state_records, "selected_target_latest_capability_report_kind"),
        "target_registry_state_records_by_selected_target_latest_compatibility_label": records_by_key(state_records, "selected_target_latest_compatibility_label"),
        "target_registry_state_records_by_selected_target_latest_compatibility_release_name": records_by_key(state_records, "selected_target_latest_compatibility_release_name"),
        "target_registry_state_records_by_has_latest_activity": records_by_key(state_records, "has_latest_activity"),
        "target_registry_state_records_by_has_next_expected_polls": records_by_key(state_records, "has_next_expected_polls"),
        "target_registry_state_records_by_has_poll_overdue": records_by_key(state_records, "has_poll_overdue"),
        "target_registry_state_records_by_has_mailbox_pending_work": records_by_key(state_records, "has_mailbox_pending_work"),
        "target_registry_state_records_by_has_failed_phone_home": records_by_key(state_records, "has_failed_phone_home"),
        "target_registry_state_records_by_has_latest_file_transfer": records_by_key(state_records, "has_latest_file_transfer"),
        "target_registry_state_records_by_has_latest_survey_result": records_by_key(state_records, "has_latest_survey_result"),
        "target_registry_state_records_by_has_latest_bridge_activity": records_by_key(state_records, "has_latest_bridge_activity"),
        "target_registry_state_records_by_has_identity_sources": records_by_key(state_records, "has_identity_sources"),
        "target_registry_state_records_by_has_capability_reports": records_by_key(state_records, "has_capability_reports"),
        "target_registry_state_records_by_has_compatibility_reports": records_by_key(state_records, "has_compatibility_reports"),
    }
    summary = target_registry_state_summary(state_record, state_records)
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
        "summary": summary,
    }


def target_registry_state_summary(state_record=None, state_records=None):
    state_record = state_record or {}
    state_records = state_records or []
    return {
        "target_registry_state_record_count": len(state_records),
        "target_registry_has_targets": bool(state_record.get("has_targets", False)),
        "target_registry_has_unfiltered_targets": bool(
            state_record.get("has_unfiltered_targets", False)
        ),
        "target_registry_has_selected_target": bool(
            state_record.get("has_selected_target", False)
        ),
        "target_registry_has_latest_activity": bool(
            state_record.get("has_latest_activity", False)
        ),
        "target_registry_has_next_expected_polls": bool(
            state_record.get("has_next_expected_polls", False)
        ),
        "target_registry_has_poll_overdue": bool(
            state_record.get("has_poll_overdue", False)
        ),
        "target_registry_has_mailbox_pending_work": bool(
            state_record.get("has_mailbox_pending_work", False)
        ),
        "target_registry_has_identity_sources": bool(
            state_record.get("has_identity_sources", False)
        ),
        "target_registry_has_capability_reports": bool(
            state_record.get("has_capability_reports", False)
        ),
        "target_registry_has_compatibility_reports": bool(
            state_record.get("has_compatibility_reports", False)
        ),
    }


def target_filter_record_indexes(records):
    return {
        "target_filter_records_by_id": {rec["id"]: rec for rec in records},
        "target_filter_records_by_active": records_by_key(records, "active"),
        "target_filter_records_by_target_id": records_by_key(records, "target_id"),
        "target_filter_records_by_selected_target_found": records_by_key(
            records, "selected_target_found"
        ),
        "target_filter_records_by_selected_target_label": records_by_key(
            records, "selected_target_label"
        ),
        "target_filter_records_by_selected_target_identity_confidence": records_by_key(
            records, "selected_target_identity_confidence"
        ),
        "target_filter_records_by_selected_target_connectivity_state": records_by_key(
            records, "selected_target_connectivity_state"
        ),
        "target_filter_records_by_selected_target_offline_age_bucket": records_by_key(
            records, "selected_target_offline_age_bucket"
        ),
        "target_filter_records_by_selected_target_latest_phone_home_status": records_by_key(
            records, "selected_target_latest_phone_home_status"
        ),
        "target_filter_records_by_selected_target_latest_successful_phone_home_status": records_by_key(
            records, "selected_target_latest_successful_phone_home_status"
        ),
        "target_filter_records_by_selected_target_last_failed_phone_home_status": records_by_key(
            records, "selected_target_last_failed_phone_home_status"
        ),
        "target_filter_records_by_selected_target_poll_overdue": records_by_key(
            records, "selected_target_poll_overdue"
        ),
        "target_filter_records_by_selected_target_mailbox_pending_work_count": records_by_key(
            records, "selected_target_mailbox_pending_work_count"
        ),
        "target_filter_records_by_selected_target_notes_present": records_by_key(
            records, "selected_target_notes_present"
        ),
        "target_filter_records_by_selected_target_latest_activity_service": records_by_key(
            records, "selected_target_latest_activity_service"
        ),
        "target_filter_records_by_selected_target_latest_activity_operation": records_by_key(
            records, "selected_target_latest_activity_operation"
        ),
        "target_filter_records_by_selected_target_latest_file_transfer_status": records_by_key(
            records, "selected_target_latest_file_transfer_status"
        ),
        "target_filter_records_by_selected_target_latest_file_transfer_route_kind": records_by_key(
            records, "selected_target_latest_file_transfer_route_kind"
        ),
        "target_filter_records_by_selected_target_latest_survey_result_status": records_by_key(
            records, "selected_target_latest_survey_result_status"
        ),
        "target_filter_records_by_selected_target_latest_survey_result_route_kind": records_by_key(
            records, "selected_target_latest_survey_result_route_kind"
        ),
        "target_filter_records_by_selected_target_latest_bridge_profile": records_by_key(
            records, "selected_target_latest_bridge_profile"
        ),
        "target_filter_records_by_selected_target_latest_bridge_status": records_by_key(
            records, "selected_target_latest_bridge_status"
        ),
        "target_filter_records_by_selected_target_latest_capability_report_kind": records_by_key(
            records, "selected_target_latest_capability_report_kind"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_report_kind": records_by_key(
            records, "selected_target_latest_compatibility_report_kind"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_label": records_by_key(
            records, "selected_target_latest_compatibility_label"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_release_name": records_by_key(
            records, "selected_target_latest_compatibility_release_name"
        ),
        "target_filter_records_by_selected_target_latest_compatibility_payload_preset": records_by_key(
            records, "selected_target_latest_compatibility_payload_preset"
        ),
        "target_filter_records_by_has_unfiltered_activity": records_by_key(
            records, "has_unfiltered_activity"
        ),
        "target_filter_records_by_has_filtered_activity": records_by_key(
            records, "has_filtered_activity"
        ),
        "target_filter_records_by_filter_reduced_activity": records_by_key(
            records, "filter_reduced_activity"
        ),
        "target_filter_records_by_has_unfiltered_observed_activity": records_by_key(
            records, "has_unfiltered_observed_activity"
        ),
        "target_filter_records_by_has_filtered_observed_activity": records_by_key(
            records, "has_filtered_observed_activity"
        ),
        "target_filter_records_by_filter_reduced_observed_activity": records_by_key(
            records, "filter_reduced_observed_activity"
        ),
    }


def target_filter_record_from_target(target_filter_id="", selected_target=None):
    selected_target = selected_target if isinstance(selected_target, dict) else {}
    selected_target_sources = selected_target.get("identity_sources") or []
    selected_target_capability_summary = (
        selected_target.get("latest_capability_summary") or {}
    )
    if not isinstance(selected_target_capability_summary, dict):
        selected_target_capability_summary = {}
    selected_target_compatibility_summary = (
        selected_target.get("latest_compatibility_summary") or {}
    )
    if not isinstance(selected_target_compatibility_summary, dict):
        selected_target_compatibility_summary = {}
    return {
        "id": target_filter_id or "all-targets",
        "active": bool(target_filter_id),
        "target_id": target_filter_id,
        "selected_target_found": bool(selected_target),
        "selected_target_label": str(selected_target.get("label") or ""),
        "selected_target_identity_confidence": str(
            selected_target.get("identity_confidence") or ""
        ),
        "selected_target_connectivity_state": str(
            selected_target.get("connectivity_state") or ""
        ),
        "selected_target_last_seen": str(
            selected_target.get("last_seen") or selected_target.get("last_seen_at") or ""
        ),
        "selected_target_last_seen_via": str(selected_target.get("last_seen_via") or ""),
        "selected_target_offline_for_sec": selected_target.get("offline_for_sec", ""),
        "selected_target_offline_age_bucket": str(
            selected_target.get("offline_age_bucket") or ""
        ),
        "selected_target_latest_phone_home_at": str(
            selected_target.get("latest_phone_home_at") or ""
        ),
        "selected_target_latest_phone_home_status": str(
            selected_target.get("latest_phone_home_status") or ""
        ),
        "selected_target_latest_phone_home_kind": str(
            selected_target.get("latest_phone_home_kind") or ""
        ),
        "selected_target_latest_phone_home_contact_path": str(
            selected_target.get("latest_phone_home_contact_path") or ""
        ),
        "selected_target_latest_successful_phone_home_at": str(
            selected_target.get("latest_successful_phone_home_at") or ""
        ),
        "selected_target_latest_successful_phone_home_status": str(
            selected_target.get("latest_successful_phone_home_status") or ""
        ),
        "selected_target_latest_successful_phone_home_kind": str(
            selected_target.get("latest_successful_phone_home_kind") or ""
        ),
        "selected_target_latest_successful_phone_home_contact_path": str(
            selected_target.get("latest_successful_phone_home_contact_path") or ""
        ),
        "selected_target_last_failed_phone_home_at": str(
            selected_target.get("last_failed_phone_home_at") or ""
        ),
        "selected_target_last_failed_phone_home_status": str(
            selected_target.get("last_failed_phone_home_status") or ""
        ),
        "selected_target_last_failed_phone_home_reason": str(
            selected_target.get("last_failed_phone_home_reason") or ""
        ),
        "selected_target_last_failed_phone_home_contact_path": str(
            selected_target.get("last_failed_phone_home_contact_path") or ""
        ),
        "selected_target_next_expected_poll": str(
            selected_target.get("next_expected_poll") or ""
        ),
        "selected_target_poll_overdue": bool(
            selected_target.get("poll_overdue", False)
        ),
        "selected_target_poll_overdue_for_sec": selected_target.get(
            "poll_overdue_for_sec", ""
        ),
        "selected_target_mailbox_command_count": int_value(
            selected_target.get("mailbox_command_count", 0)
        ),
        "selected_target_mailbox_pending_work_count": int_value(
            selected_target.get("mailbox_pending_work_count", 0)
        ),
        "selected_target_identity_source_count": len(selected_target_sources),
        "selected_target_alias_count": len(selected_target.get("aliases") or []),
        "selected_target_notes_present": bool(
            str(selected_target.get("notes") or "").strip()
        ),
        "selected_target_latest_activity_service": str(
            selected_target.get("latest_activity_service") or ""
        ),
        "selected_target_latest_activity_operation": str(
            selected_target.get("latest_activity_operation") or ""
        ),
        "selected_target_latest_file_transfer_operation": str(
            selected_target.get("latest_file_transfer_operation") or ""
        ),
        "selected_target_latest_file_transfer_status": str(
            selected_target.get("latest_file_transfer_status") or ""
        ),
        "selected_target_latest_file_transfer_route_kind": str(
            selected_target.get("latest_file_transfer_route_kind") or ""
        ),
        "selected_target_latest_file_transfer_bridge_profile": str(
            selected_target.get("latest_file_transfer_bridge_profile") or ""
        ),
        "selected_target_latest_survey_result_kind": str(
            selected_target.get("latest_survey_result_kind") or ""
        ),
        "selected_target_latest_survey_result_status": str(
            selected_target.get("latest_survey_result_status") or ""
        ),
        "selected_target_latest_survey_result_route_kind": str(
            selected_target.get("latest_survey_result_route_kind") or ""
        ),
        "selected_target_latest_survey_result_bridge_profile": str(
            selected_target.get("latest_survey_result_bridge_profile") or ""
        ),
        "selected_target_latest_bridge_profile": str(
            selected_target.get("latest_bridge_profile") or ""
        ),
        "selected_target_latest_bridge_status": str(
            selected_target.get("latest_bridge_status") or ""
        ),
        "selected_target_latest_bridge_route_path": str(
            selected_target.get("latest_bridge_route_path") or ""
        ),
        "selected_target_latest_bridge_failure_reason": str(
            selected_target.get("latest_bridge_failure_reason") or ""
        ),
        "selected_target_latest_capability_report_kind": str(
            selected_target.get("latest_capability_report_kind") or ""
        ),
        "selected_target_latest_capability_check_count": int_value(
            selected_target_capability_summary.get("check_count", 0)
        ),
        "selected_target_latest_capability_pass_count": int_value(
            selected_target_capability_summary.get("capability_pass_count", 0)
        ),
        "selected_target_latest_capability_fail_count": int_value(
            selected_target_capability_summary.get("capability_fail_count", 0)
        ),
        "selected_target_latest_compatibility_report_kind": str(
            selected_target.get("latest_compatibility_report_kind") or ""
        ),
        "selected_target_latest_compatibility_label": str(
            selected_target.get("latest_compatibility_label") or ""
        ),
        "selected_target_latest_compatibility_baseline_label": str(
            selected_target.get("latest_compatibility_baseline_label") or ""
        ),
        "selected_target_latest_compatibility_release_name": str(
            selected_target.get("latest_compatibility_release_name") or ""
        ),
        "selected_target_latest_compatibility_payload_preset": str(
            selected_target.get("latest_compatibility_payload_preset") or ""
        ),
        "selected_target_latest_compatibility_reason_count": int_value(
            selected_target_compatibility_summary.get("reason_count", 0)
        ),
    }


def apply_target_filter_activity_counts(record, target_filter_id="", unfiltered=None, filtered=None):
    record = record if isinstance(record, dict) else {}
    unfiltered = unfiltered if isinstance(unfiltered, dict) else {}
    filtered = filtered if isinstance(filtered, dict) else {}
    record.update({
        "unfiltered_target_count": unfiltered.get("targets", 0),
        "unfiltered_upload_count": unfiltered.get("uploads", 0),
        "unfiltered_fetch_count": unfiltered.get("fetches", 0),
        "unfiltered_staged_count": unfiltered.get("staged", 0),
        "unfiltered_session_count": unfiltered.get("sessions", 0),
        "unfiltered_event_tail_count": unfiltered.get("event_tail", 0),
        "unfiltered_command_queue_command_count": unfiltered.get(
            "command_queue_commands", 0
        ),
        "unfiltered_target_command_record_count": unfiltered.get(
            "target_command_records", 0
        ),
        "unfiltered_target_phone_home_record_count": unfiltered.get(
            "target_phone_home_records", 0
        ),
        "filtered_target_count": filtered.get("targets", 0),
        "filtered_upload_count": filtered.get("uploads", 0),
        "filtered_fetch_count": filtered.get("fetches", 0),
        "filtered_staged_count": filtered.get("staged", 0),
        "filtered_session_count": filtered.get("sessions", 0),
        "filtered_event_tail_count": filtered.get("event_tail", 0),
        "filtered_command_queue_command_count": filtered.get(
            "command_queue_commands", 0
        ),
        "filtered_target_command_record_count": filtered.get(
            "target_command_records", 0
        ),
        "filtered_target_phone_home_record_count": filtered.get(
            "target_phone_home_records", 0
        ),
    })
    record["unfiltered_activity_count"] = (
        record["unfiltered_upload_count"] +
        record["unfiltered_fetch_count"] +
        record["unfiltered_staged_count"] +
        record["unfiltered_session_count"] +
        record["unfiltered_event_tail_count"] +
        record["unfiltered_command_queue_command_count"] +
        record["unfiltered_target_command_record_count"] +
        record["unfiltered_target_phone_home_record_count"]
    )
    record["filtered_activity_count"] = (
        record["filtered_upload_count"] +
        record["filtered_fetch_count"] +
        record["filtered_staged_count"] +
        record["filtered_session_count"] +
        record["filtered_event_tail_count"] +
        record["filtered_command_queue_command_count"] +
        record["filtered_target_command_record_count"] +
        record["filtered_target_phone_home_record_count"]
    )
    record["unfiltered_observed_activity_count"] = (
        record["unfiltered_upload_count"] +
        record["unfiltered_fetch_count"] +
        record["unfiltered_staged_count"] +
        record["unfiltered_session_count"] +
        record["unfiltered_event_tail_count"] +
        record["unfiltered_command_queue_command_count"] +
        record["unfiltered_target_phone_home_record_count"]
    )
    record["filtered_observed_activity_count"] = (
        record["filtered_upload_count"] +
        record["filtered_fetch_count"] +
        record["filtered_staged_count"] +
        record["filtered_session_count"] +
        record["filtered_event_tail_count"] +
        record["filtered_command_queue_command_count"] +
        record["filtered_target_phone_home_record_count"]
    )
    record["has_unfiltered_activity"] = record["unfiltered_activity_count"] > 0
    record["has_filtered_activity"] = record["filtered_activity_count"] > 0
    record["filter_reduced_activity"] = (
        bool(target_filter_id) and
        record["filtered_activity_count"] < record["unfiltered_activity_count"]
    )
    record["has_unfiltered_observed_activity"] = (
        record["unfiltered_observed_activity_count"] > 0
    )
    record["has_filtered_observed_activity"] = (
        record["filtered_observed_activity_count"] > 0
    )
    record["filter_reduced_observed_activity"] = (
        bool(target_filter_id) and
        record["filtered_observed_activity_count"] <
        record["unfiltered_observed_activity_count"]
    )
    return record


def target_filter_status_context(
    target_filter_id="",
    selected_target=None,
    unfiltered_counts=None,
    filtered_counts=None,
    target_mailbox_records=None,
):
    record = target_filter_record_from_target(target_filter_id, selected_target)
    apply_target_filter_activity_counts(
        record,
        target_filter_id,
        unfiltered_counts,
        filtered_counts,
    )
    records = [record]
    return {
        "record": record,
        "records": records,
        "index_maps": target_filter_record_indexes(records),
        "summary": target_filter_status_summary(
            record,
            records,
            target_filter_id=target_filter_id,
            target_mailbox_records=target_mailbox_records,
        ),
    }


def target_filter_status_summary(
    record,
    records=None,
    target_filter_id="",
    target_mailbox_records=None,
):
    record = record or {}
    records = records or []
    return {
        "target_filter_active": bool(target_filter_id),
        "target_filter_id": target_filter_id,
        "target_filter_unfiltered_target_count": record.get(
            "unfiltered_target_count", 0
        ),
        "target_filter_unfiltered_upload_count": record.get(
            "unfiltered_upload_count", 0
        ),
        "target_filter_unfiltered_fetch_count": record.get(
            "unfiltered_fetch_count", 0
        ),
        "target_filter_unfiltered_staged_count": record.get(
            "unfiltered_staged_count", 0
        ),
        "target_filter_unfiltered_session_count": record.get(
            "unfiltered_session_count", 0
        ),
        "target_filter_unfiltered_event_tail_count": record.get(
            "unfiltered_event_tail_count", 0
        ),
        "target_filter_unfiltered_command_queue_command_count": record.get(
            "unfiltered_command_queue_command_count", 0
        ),
        "target_filter_unfiltered_target_command_record_count": record.get(
            "unfiltered_target_command_record_count", 0
        ),
        "target_filter_unfiltered_target_phone_home_record_count": record.get(
            "unfiltered_target_phone_home_record_count", 0
        ),
        "target_filter_unfiltered_observed_activity_count": record.get(
            "unfiltered_observed_activity_count", 0
        ),
        "target_filter_observed_activity_count": record.get(
            "filtered_observed_activity_count", 0
        ),
        "target_filter_has_unfiltered_observed_activity": bool(
            record.get("has_unfiltered_observed_activity", False)
        ),
        "target_filter_has_observed_activity": bool(
            record.get("has_filtered_observed_activity", False)
        ),
        "target_filter_reduced_observed_activity": bool(
            record.get("filter_reduced_observed_activity", False)
        ),
        "target_filter_event_tail_count": record.get("filtered_event_tail_count", 0),
        "target_filter_command_queue_command_count": record.get(
            "filtered_command_queue_command_count", 0
        ),
        "target_filter_target_mailbox_record_count": len(
            target_mailbox_records or []
        ),
        "target_filter_target_command_record_count": record.get(
            "filtered_target_command_record_count", 0
        ),
        "target_filter_target_phone_home_record_count": record.get(
            "filtered_target_phone_home_record_count", 0
        ),
        "target_filter_record_count": len(records),
        "target_filter_selected_target_found": bool(
            record.get("selected_target_found", False)
        ),
        "target_filter_selected_target_identity_source_count": record.get(
            "selected_target_identity_source_count", 0
        ),
        "target_filter_selected_target_alias_count": record.get(
            "selected_target_alias_count", 0
        ),
        "target_filter_selected_target_notes_present": bool(
            record.get("selected_target_notes_present", False)
        ),
    }


def target_attribution_record_indexes(records):
    return {
        "target_attribution_records_by_scope": {
            rec["scope"]: rec for rec in records
        },
        "target_attribution_records_by_has_targeted_activity": records_by_key(
            records, "has_targeted_activity"
        ),
        "target_attribution_records_by_has_legacy_activity": records_by_key(
            records, "has_legacy_activity"
        ),
        "target_attribution_records_by_legacy_single_target_activity_present": records_by_key(
            records, "legacy_single_target_activity_present"
        ),
        "target_attribution_records_by_all_activity_has_target_id": records_by_key(
            records, "all_activity_has_target_id"
        ),
        "target_attribution_records_by_no_activity": records_by_key(
            records, "no_activity"
        ),
    }


def target_attribution_record_summary(records, attribution=None):
    records = records or []
    attribution = attribution or {}
    return {
        "target_attribution_record_count": len(records),
        "target_attribution_scope_counts": record_count_by_key(records, "scope"),
        "target_attribution_legacy_scope_count": len([
            rec for rec in records if rec.get("has_legacy_activity")
        ]),
        "target_attribution_targeted_scope_count": len([
            rec for rec in records if rec.get("has_targeted_activity")
        ]),
        "target_attribution_with_target_count": attribution.get("with_target_count", 0),
        "target_attribution_without_target_count": attribution.get(
            "without_target_count", 0
        ),
        "target_legacy_single_target_activity_present": attribution.get(
            "legacy_single_target_activity_present", False
        ),
    }


def target_attribution_status(uploads=None, fetches=None, sessions=None):
    uploads = uploads or []
    fetches = fetches or []
    sessions = sessions or []
    upload_with_target_count = count_records_with_key(uploads, "target_id")
    fetch_with_target_count = count_records_with_key(fetches, "target_id")
    session_with_target_count = count_records_with_key(sessions, "target_id")
    attribution = {
        "upload_with_target_count": upload_with_target_count,
        "upload_without_target_count": max(len(uploads) - upload_with_target_count, 0),
        "fetch_with_target_count": fetch_with_target_count,
        "fetch_without_target_count": max(len(fetches) - fetch_with_target_count, 0),
        "session_with_target_count": session_with_target_count,
        "session_without_target_count": max(
            len(sessions) - session_with_target_count, 0
        ),
    }
    attribution["with_target_count"] = (
        attribution["upload_with_target_count"] +
        attribution["fetch_with_target_count"] +
        attribution["session_with_target_count"]
    )
    attribution["without_target_count"] = (
        attribution["upload_without_target_count"] +
        attribution["fetch_without_target_count"] +
        attribution["session_without_target_count"]
    )
    attribution["legacy_single_target_activity_present"] = (
        attribution["without_target_count"] > 0
    )
    records = []
    for scope, with_count, without_count in (
        (
            "uploads",
            attribution["upload_with_target_count"],
            attribution["upload_without_target_count"],
        ),
        (
            "fetches",
            attribution["fetch_with_target_count"],
            attribution["fetch_without_target_count"],
        ),
        (
            "sessions",
            attribution["session_with_target_count"],
            attribution["session_without_target_count"],
        ),
        (
            "all",
            attribution["with_target_count"],
            attribution["without_target_count"],
        ),
    ):
        total = with_count + without_count
        records.append({
            "scope": scope,
            "with_target_count": with_count,
            "without_target_count": without_count,
            "total_count": total,
            "has_targeted_activity": with_count > 0,
            "has_legacy_activity": without_count > 0,
            "legacy_single_target_activity_present": without_count > 0,
            "all_activity_has_target_id": total > 0 and without_count == 0,
            "no_activity": total == 0,
        })
    return {
        "target_attribution": attribution,
        "target_attribution_records": records,
        "target_attribution_index_maps": target_attribution_record_indexes(records),
    }


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


def target_filter_brief_text(target_filter, prefix="selected agent:"):
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
