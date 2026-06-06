"""Recent-session view record helpers for grit-console."""

import time
from pathlib import Path


def count_file_lines(path):
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _line in fh)
    except OSError:
        return 0


def utc_now_from_mtime(mtime):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(mtime)))


def recent_metadata_record(path, metadata_path, events_path, session_log_path, meta, elapsed_seconds_func):
    session_log_exists = session_log_path.is_file()
    meta.setdefault("service", path.name.split("-", 2)[-1] if "-" in path.name else "unknown")
    meta.setdefault("path", str(path))
    meta.setdefault("exit_reason", "")
    meta.setdefault("updated_at", utc_now_from_mtime(path.stat().st_mtime))
    if "duration_sec" not in meta:
        duration = elapsed_seconds_func(meta.get("started_at", ""), meta.get("ended_at", ""))
        if duration is not None:
            meta["duration_sec"] = duration
    meta["metadata_path"] = str(metadata_path)
    meta["metadata_exists"] = metadata_path.is_file()
    meta["event_log"] = str(events_path) if events_path.is_file() else ""
    meta["event_log_exists"] = events_path.is_file()
    meta["event_count"] = count_file_lines(events_path)
    meta["session_log"] = str(session_log_path) if session_log_exists else ""
    meta["session_log_exists"] = session_log_exists
    meta["session_log_size"] = session_log_path.stat().st_size if session_log_exists else 0
    meta["session_log_line_count"] = count_file_lines(session_log_path) if session_log_exists else 0
    meta["has_session_log"] = session_log_exists
    meta["upload_count"] = len(meta.get("uploads") or [])
    meta["fetch_count"] = len(meta.get("fetches") or [])
    meta["artifact_count"] = len(meta.get("artifacts") or [])
    meta["has_uploads"] = meta["upload_count"] > 0
    meta["has_fetches"] = meta["fetch_count"] > 0
    meta["has_events"] = meta["event_count"] > 0
    meta["has_artifacts"] = meta["artifact_count"] > 0
    return meta


def recent_legacy_record(path, metadata_path, events_path, session_log_path):
    session_log_exists = session_log_path.is_file()
    exit_reason = ""
    try:
        exit_reason = (path / "exit-reason").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    service = path.name.split("-", 2)[-1] if "-" in path.name else "unknown"
    event_count = count_file_lines(events_path)
    upload_count = len(list(path.glob("files/*.metadata.json")))
    return {
        "service": service,
        "path": str(path),
        "metadata_path": str(metadata_path) if metadata_path.is_file() else "",
        "metadata_exists": metadata_path.is_file(),
        "event_log": str(events_path) if events_path.is_file() else "",
        "event_log_exists": events_path.is_file(),
        "event_count": event_count,
        "session_log": str(session_log_path) if session_log_exists else "",
        "session_log_exists": session_log_exists,
        "session_log_size": session_log_path.stat().st_size if session_log_exists else 0,
        "session_log_line_count": count_file_lines(session_log_path) if session_log_exists else 0,
        "has_session_log": session_log_exists,
        "upload_count": upload_count,
        "fetch_count": 0,
        "artifact_count": 0,
        "has_uploads": upload_count > 0,
        "has_fetches": False,
        "has_events": event_count > 0,
        "has_artifacts": False,
        "exit_reason": exit_reason,
        "updated_at": utc_now_from_mtime(path.stat().st_mtime),
        "duration_sec": "",
    }


def recent_session_record(path, read_json_file_func, elapsed_seconds_func):
    metadata_path = path / "session.json"
    events_path = path / "events.jsonl"
    session_log_path = path / "session.log"
    meta = read_json_file_func(metadata_path, {})
    if isinstance(meta, dict) and meta:
        return recent_metadata_record(
            path,
            metadata_path,
            events_path,
            session_log_path,
            meta,
            elapsed_seconds_func,
        )
    return recent_legacy_record(path, metadata_path, events_path, session_log_path)
