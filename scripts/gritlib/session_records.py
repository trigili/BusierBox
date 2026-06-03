"""Session record index and summary helpers for grit-console."""

from pathlib import Path

from gritlib.record_utils import (
    int_value, latest_record_value, record_count_by_key, records_by_key,
)


def session_record_indexes(records):
    by_id = {}
    by_service = {}
    by_state = {}
    by_exit_reason = {}
    by_remote = {}
    by_service_state = {}
    by_service_exit_reason = {}
    by_service_remote = {}
    by_target_id = {}
    by_has_uploads = {"yes": [], "no": []}
    by_has_fetches = {"yes": [], "no": []}
    by_has_events = {"yes": [], "no": []}
    by_has_artifacts = {"yes": [], "no": []}
    by_has_session_log = {"yes": [], "no": []}
    by_duration_known = {"yes": [], "no": []}
    by_metadata_exists = {"yes": [], "no": []}
    by_event_log_exists = {"yes": [], "no": []}
    by_session_log_exists = {"yes": [], "no": []}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        session_id_value = str(rec.get("session_id") or Path(str(rec.get("path", ""))).name)
        service = str(rec.get("service") or "")
        state = str(rec.get("state") or "")
        exit_reason = str(rec.get("exit_reason") or "")
        remote = str(rec.get("remote") or "")
        target_id = str(rec.get("target_id") or "")
        if session_id_value:
            by_id[session_id_value] = rec
        if service:
            by_service.setdefault(service, []).append(rec)
        if state:
            by_state.setdefault(state, []).append(rec)
        if exit_reason:
            by_exit_reason.setdefault(exit_reason, []).append(rec)
        if remote:
            by_remote.setdefault(remote, []).append(rec)
        if service and state:
            by_service_state.setdefault(f"{service}:{state}", []).append(rec)
        if service and exit_reason:
            by_service_exit_reason.setdefault(f"{service}:{exit_reason}", []).append(rec)
        if service and remote:
            by_service_remote.setdefault(f"{service}:{remote}", []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        by_has_uploads["yes" if rec.get("has_uploads") is True or int_value(rec.get("upload_count")) > 0 else "no"].append(rec)
        by_has_fetches["yes" if rec.get("has_fetches") is True or int_value(rec.get("fetch_count")) > 0 else "no"].append(rec)
        by_has_events["yes" if rec.get("has_events") is True or int_value(rec.get("event_count")) > 0 else "no"].append(rec)
        by_has_artifacts["yes" if rec.get("has_artifacts") is True or int_value(rec.get("artifact_count")) > 0 else "no"].append(rec)
        by_has_session_log["yes" if rec.get("has_session_log") is True or int_value(rec.get("session_log_size")) > 0 else "no"].append(rec)
        by_duration_known["yes" if rec.get("duration_sec") not in (None, "") else "no"].append(rec)
        by_metadata_exists["yes" if rec.get("metadata_exists") is True else "no"].append(rec)
        by_event_log_exists["yes" if rec.get("event_log_exists") is True else "no"].append(rec)
        by_session_log_exists["yes" if rec.get("session_log_exists") is True else "no"].append(rec)
    return (
        by_id,
        by_service,
        by_state,
        by_exit_reason,
        by_remote,
        by_service_state,
        by_service_exit_reason,
        by_service_remote,
        by_target_id,
        by_has_uploads,
        by_has_fetches,
        by_has_events,
        by_has_artifacts,
        by_has_session_log,
        by_duration_known,
        by_metadata_exists,
        by_event_log_exists,
        by_session_log_exists,
    )


def print_recent_sessions(records, updated_on_header=False):
    print("Recent sessions:")
    if records:
        for session in records:
            updated = session.get("updated_at", "")
            updated_header = f" updated={updated}" if updated_on_header else ""
            print(
                f"  {session.get('service', '')} {session.get('path', '')} "
                f"state={session.get('state', '')} exit={session.get('exit_reason', '')}{updated_header}"
            )
            duration = session.get("duration_sec", "")
            duration_text = f" duration_sec={duration}" if duration not in (None, "") else ""
            updated_detail = "" if updated_on_header else f" updated={updated}"
            print(
                f"    uploads={session.get('upload_count', 0)} "
                f"fetches={session.get('fetch_count', 0)} "
                f"events={session.get('event_count', 0)} "
                f"artifacts={session.get('artifact_count', 0)}{updated_detail}{duration_text}"
            )
            print(f"    metadata: {session.get('metadata_path', '')}")
            if session.get("event_log"):
                print(f"    event_log: {session.get('event_log', '')}")
            if session.get("session_log"):
                print(
                    f"    session_log: {session.get('session_log', '')} "
                    f"size={session.get('session_log_size', 0)} "
                    f"lines={session.get('session_log_line_count', 0)}"
                )
    else:
        print("  none")


def _index_counts(index):
    return {key: len(value) for key, value in (index or {}).items()}


def session_record_summary(records, root_state=None, root_state_records=None, target_attribution=None):
    records = records or []
    root_state = root_state or {}
    root_state_records = root_state_records or []
    target_attribution = target_attribution or {}
    (
        _sessions_by_id,
        _sessions_by_service,
        _sessions_by_state,
        _sessions_by_exit_reason,
        _sessions_by_remote,
        sessions_by_service_state,
        sessions_by_service_exit_reason,
        sessions_by_service_remote,
        _sessions_by_target_id,
        sessions_by_has_uploads,
        sessions_by_has_fetches,
        sessions_by_has_events,
        sessions_by_has_artifacts,
        sessions_by_has_session_log,
        sessions_by_duration_known,
        sessions_by_metadata_exists,
        sessions_by_event_log_exists,
        sessions_by_session_log_exists,
    ) = session_record_indexes(records)
    return {
        "session_count": len(records),
        "session_root_exists": bool(root_state.get("exists", False)),
        "session_root_recent_count": root_state.get("recent_session_count", 0),
        "session_root_state_record_count": len(root_state_records),
        "session_root_has_recent_sessions": bool(root_state.get("has_recent_sessions", False)),
        "session_service_counts": record_count_by_key(records, "service"),
        "session_state_counts": record_count_by_key(records, "state"),
        "session_exit_reason_counts": record_count_by_key(records, "exit_reason"),
        "session_remote_counts": record_count_by_key(records, "remote"),
        "session_target_counts": record_count_by_key(records, "target_id"),
        "session_with_target_count": target_attribution.get("session_with_target_count", 0),
        "session_without_target_count": target_attribution.get("session_without_target_count", 0),
        "session_service_state_counts": _index_counts(sessions_by_service_state),
        "session_service_exit_reason_counts": _index_counts(sessions_by_service_exit_reason),
        "session_service_remote_counts": _index_counts(sessions_by_service_remote),
        "session_has_uploads_counts": _index_counts(sessions_by_has_uploads),
        "session_has_fetches_counts": _index_counts(sessions_by_has_fetches),
        "session_has_events_counts": _index_counts(sessions_by_has_events),
        "session_has_artifacts_counts": _index_counts(sessions_by_has_artifacts),
        "session_has_session_log_counts": _index_counts(sessions_by_has_session_log),
        "session_duration_known_counts": _index_counts(sessions_by_duration_known),
        "session_metadata_exists_counts": _index_counts(sessions_by_metadata_exists),
        "session_event_log_exists_counts": _index_counts(sessions_by_event_log_exists),
        "session_log_exists_counts": _index_counts(sessions_by_session_log_exists),
        "session_total_upload_count": root_state.get("total_upload_count", 0),
        "session_total_fetch_count": root_state.get("total_fetch_count", 0),
        "session_total_event_count": root_state.get("total_event_count", 0),
        "session_total_artifact_count": root_state.get("total_artifact_count", 0),
        "session_total_log_size": root_state.get("total_session_log_size", 0),
        "session_total_log_line_count": root_state.get("total_session_log_line_count", 0),
        "session_duration_known_count": root_state.get("duration_known_count", 0),
        "session_total_duration_sec": root_state.get("total_duration_sec", 0),
        "session_average_duration_sec": root_state.get("average_duration_sec", 0),
        "session_max_duration_sec": root_state.get("max_duration_sec", 0),
        "sessions_with_uploads_count": root_state.get("sessions_with_uploads_count", 0),
        "sessions_with_fetches_count": root_state.get("sessions_with_fetches_count", 0),
        "sessions_with_events_count": root_state.get("sessions_with_events_count", 0),
        "sessions_with_artifacts_count": root_state.get("sessions_with_artifacts_count", 0),
        "sessions_with_session_logs_count": root_state.get("sessions_with_session_logs_count", 0),
        "sessions_with_metadata_count": root_state.get("sessions_with_metadata_count", 0),
        "sessions_with_event_logs_count": root_state.get("sessions_with_event_logs_count", 0),
        "latest_session_updated_at": latest_record_value(records, ("updated_at", "ended_at", "started_at")),
    }


def session_root_record(cfg, records):
    path = Path(str(cfg.get("session_root", "local/sessions")))
    session_ids = []
    service_counts = {}
    state_counts = {}
    total_upload_count = 0
    total_fetch_count = 0
    total_event_count = 0
    total_artifact_count = 0
    total_duration_sec = 0
    max_duration_sec = 0
    duration_known_count = 0
    sessions_with_uploads = 0
    sessions_with_fetches = 0
    sessions_with_events = 0
    sessions_with_artifacts = 0
    sessions_with_session_logs = 0
    total_session_log_size = 0
    total_session_log_line_count = 0
    sessions_with_metadata = 0
    sessions_with_event_logs = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        session_id_value = str(rec.get("session_id") or Path(str(rec.get("path", ""))).name)
        service = str(rec.get("service") or "")
        state = str(rec.get("state") or "")
        if session_id_value:
            session_ids.append(session_id_value)
        if service:
            service_counts[service] = service_counts.get(service, 0) + 1
        if state:
            state_counts[state] = state_counts.get(state, 0) + 1
        upload_count = int_value(rec.get("upload_count"))
        fetch_count = int_value(rec.get("fetch_count"))
        event_count = int_value(rec.get("event_count"))
        artifact_count = int_value(rec.get("artifact_count"))
        session_log_size = int_value(rec.get("session_log_size"))
        session_log_line_count = int_value(rec.get("session_log_line_count"))
        duration_sec = int_value(rec.get("duration_sec"))
        total_upload_count += upload_count
        total_fetch_count += fetch_count
        total_event_count += event_count
        total_artifact_count += artifact_count
        total_session_log_size += session_log_size
        total_session_log_line_count += session_log_line_count
        if rec.get("duration_sec") not in (None, ""):
            duration_known_count += 1
            total_duration_sec += duration_sec
            max_duration_sec = max(max_duration_sec, duration_sec)
        if upload_count > 0:
            sessions_with_uploads += 1
        if fetch_count > 0:
            sessions_with_fetches += 1
        if event_count > 0:
            sessions_with_events += 1
        if artifact_count > 0:
            sessions_with_artifacts += 1
        if rec.get("session_log_exists") is True:
            sessions_with_session_logs += 1
        if rec.get("metadata_exists") is True:
            sessions_with_metadata += 1
        if rec.get("event_log_exists") is True:
            sessions_with_event_logs += 1
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "recent_session_ids": session_ids,
        "recent_session_count": len(session_ids),
        "service_counts": service_counts,
        "state_counts": state_counts,
        "total_upload_count": total_upload_count,
        "total_fetch_count": total_fetch_count,
        "total_event_count": total_event_count,
        "total_artifact_count": total_artifact_count,
        "total_session_log_size": total_session_log_size,
        "total_session_log_line_count": total_session_log_line_count,
        "total_duration_sec": total_duration_sec,
        "max_duration_sec": max_duration_sec,
        "duration_known_count": duration_known_count,
        "average_duration_sec": int(total_duration_sec / duration_known_count) if duration_known_count else 0,
        "sessions_with_uploads_count": sessions_with_uploads,
        "sessions_with_fetches_count": sessions_with_fetches,
        "sessions_with_events_count": sessions_with_events,
        "sessions_with_artifacts_count": sessions_with_artifacts,
        "sessions_with_session_logs_count": sessions_with_session_logs,
        "sessions_with_metadata_count": sessions_with_metadata,
        "sessions_with_event_logs_count": sessions_with_event_logs,
        "latest_session_updated_at": latest_record_value(records, ("updated_at", "ended_at", "started_at")),
    }


def session_root_state_status(cfg, records):
    state_record = session_root_record(cfg, records)
    state_record["has_recent_sessions"] = int(state_record.get("recent_session_count") or 0) > 0
    state_record["has_uploads"] = int(state_record.get("total_upload_count") or 0) > 0
    state_record["has_fetches"] = int(state_record.get("total_fetch_count") or 0) > 0
    state_record["has_events"] = int(state_record.get("total_event_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "session_root_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "session_root_state_records_by_exists": records_by_key(state_records, "exists"),
        "session_root_state_records_by_has_recent_sessions": records_by_key(
            state_records, "has_recent_sessions"
        ),
        "session_root_state_records_by_has_uploads": records_by_key(state_records, "has_uploads"),
        "session_root_state_records_by_has_fetches": records_by_key(state_records, "has_fetches"),
        "session_root_state_records_by_has_events": records_by_key(state_records, "has_events"),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }
