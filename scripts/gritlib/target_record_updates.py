"""Target record mutation helpers for grit-console."""

from gritlib.event_log import append_event
from gritlib.record_utils import list_merge_unique
from gritlib.session_state import atomic_write_json, utc_now
import gritlib.target_report_summary as target_report_summary
from gritlib.target_context import configured_target_filter
from gritlib.target_store import load_targets, targets_path


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
        observed = target_report_summary.capability_report_summary(metadata)
        if observed:
            rec["latest_capability_summary"] = observed
            rec["observed_capabilities"] = list_merge_unique(rec.get("observed_capabilities") or [], observed.get("available") or [])
            rec["observed_missing_capabilities"] = list_merge_unique(rec.get("observed_missing_capabilities") or [], observed.get("unavailable") or [])
            rec["observed_constraints"] = observed.get("constraints") or {}
    compatibility = target_report_summary.compatibility_report_summary(metadata)
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


def selected_target_record_for_update(cfg):
    target_id = configured_target_filter(cfg)
    if not target_id:
        raise ValueError("select a target before setting target options")
    rec = (load_targets(cfg).get("targets") or {}).get(target_id)
    if not isinstance(rec, dict):
        rec = {"target_id": target_id, "label": "", "aliases": [], "notes": ""}
    return target_id, rec
