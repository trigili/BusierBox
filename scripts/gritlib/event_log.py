"""Event log storage, statistics, and index helpers for grit-console."""

import itertools
import json
import os
import time
from pathlib import Path

from gritlib.record_utils import format_counts, records_by_key


EVENT_COUNTER = itertools.count(1)
DEFAULT_OPERATOR_SESSION_DIR = "local/operator-session"

DETAIL_KEYS = (
    "status",
    "operation",
    "http_status",
    "request_name",
    "filename",
    "reason",
    "sha256",
    "command_id",
    "command_sha256",
    "job_id",
    "action_id",
    "key",
    "config_path",
    "target_id",
    "target_label",
    "expected_target_id",
    "target_identity_source",
    "target_identity_confidence",
    "poll_mode",
    "poll_interval_sec",
    "poll_jitter_pct",
    "poll_backoff",
    "poll_max_interval_sec",
    "max_polls",
)

TOP_INDEXES = (
    "service",
    "event",
    "level",
    "remote",
    "service_event",
    "session_event",
    "service_level",
    "session_level",
    "event_level",
    "remote_event",
    "remote_level",
)

DETAIL_INDEXES = tuple(f"detail_{key}" for key in DETAIL_KEYS)
EVENT_DETAIL_INDEXES = tuple(f"event_detail_{key}" for key in DETAIL_KEYS[:18])
SERVICE_DETAIL_INDEXES = tuple(f"service_detail_{key}" for key in DETAIL_KEYS[:18])


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _count(counts, name, key):
    if key:
        counts[name][key] = counts[name].get(key, 0) + 1


def _append(indexes, name, key, rec):
    if key:
        indexes[name].setdefault(key, []).append(rec)


def _event_details(rec):
    details = rec.get("details") if isinstance(rec.get("details"), dict) else {}
    return {key: str(details.get(key) or "") for key in DETAIL_KEYS}


def _event_fields(rec):
    details = _event_details(rec)
    fields = {
        "id": str(rec.get("id") or ""),
        "session": str(rec.get("session") or ""),
        "service": str(rec.get("service") or ""),
        "event": str(rec.get("event") or ""),
        "level": str(rec.get("level") or ""),
        "remote": str(rec.get("remote") or ""),
    }
    fields.update({f"detail_{key}": value for key, value in details.items()})
    return fields


def compact_event_details(event):
    details = event.get("details") if isinstance(event, dict) else {}
    if not isinstance(details, dict):
        return ""
    pieces = []
    for key in ("operation", "status", "http_status", "request_name", "filename", "sha256", "reason", "command_id", "command_sha256"):
        value = details.get(key)
        if value in (None, ""):
            continue
        label = "http" if key == "http_status" else key
        pieces.append(f"{label}={value}")
    return " ".join(pieces)


def print_event_log_summary(doc):
    print("Event log:")
    stats = (doc or {}).get("event_log_stats") or {}
    print(f"  path: {(doc or {}).get('event_log', '')}")
    print(f"  total={stats.get('total_count', 0)} tail={stats.get('tail_count', 0)} invalid={stats.get('invalid_count', 0)} limit={stats.get('tail_limit', 0)} truncated={'yes' if stats.get('tail_truncated') else 'no'} omitted={stats.get('tail_omitted_count', 0)}")
    print(f"  {event_tail_availability_text(doc)}")
    print(f"  first={stats.get('first_event_at', '') or '-'} latest={stats.get('latest_event_at', '') or '-'}")
    print(f"  services: {format_counts(stats.get('by_service') or {})}")
    print(f"  events: {format_counts(stats.get('by_event') or {})}")
    print(f"  levels: {format_counts(stats.get('by_level') or {})}")
    print(f"  remotes: {format_counts(stats.get('by_remote') or {})}")
    print(f"  detail_statuses: {format_counts(stats.get('by_detail_status') or {})}")
    print(f"  detail_operations: {format_counts(stats.get('by_detail_operation') or {})}")
    print(f"  detail_http_statuses: {format_counts(stats.get('by_detail_http_status') or {})}")
    print(f"  detail_reasons: {format_counts(stats.get('by_detail_reason') or {})}")
    print(f"  detail_sha256: {format_counts(stats.get('by_detail_sha256') or {})}")
    print(f"  detail_command_ids: {format_counts(stats.get('by_detail_command_id') or {})}")
    print(f"  detail_command_sha256: {format_counts(stats.get('by_detail_command_sha256') or {})}")
    if (doc or {}).get("events"):
        for event in ((doc or {}).get("events") or [])[-8:]:
            suffix = compact_event_details(event)
            if suffix:
                suffix = f" {suffix}"
            print(f"  {event.get('ts', '')} {event.get('level', '')} {event.get('service', '')}:{event.get('event', '')}{suffix}")
    else:
        print("  events_tail: none")


class EventLog:
    """Structured JSONL event log shared by status, line console, and frontends."""

    def __init__(self, cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR, now_func=utc_now):
        self.cfg = cfg
        self.now_func = now_func
        self.operator_dir = Path(str(cfg.get("operator_session_dir", default_operator_session_dir)))
        self.path = self.operator_dir / "events.jsonl"

    def write(self, service, event, level="info", session=None, remote=None, details=None):
        session_id = ""
        session_path_text = ""
        session_path = None
        if session:
            session_path = Path(str(session))
            session_id = session_path.name
            session_path_text = str(session_path)
        record = {
            "schema": 1,
            "id": f"evt-{os.getpid()}-{next(EVENT_COUNTER)}",
            "ts": self.now_func(),
            "service": service,
            "session": session_id,
            "session_path": session_path_text,
            "event": event,
            "level": level,
            "remote": remote or "",
            "details": details or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        if session_path:
            try:
                with (session_path / "events.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, sort_keys=True) + "\n")
            except OSError:
                pass
        return record

    def records(self):
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return [], 0
        out = []
        invalid = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                invalid += 1
        return out, invalid

    def tail(self, limit=12):
        records, _invalid = self.records()
        return records[-limit:]

    def stats(self, limit=12):
        records, invalid = self.records()
        limit = max(int(limit or 0), 0)
        tail = records[-limit:] if limit else []
        omitted = max(len(records) - len(tail), 0)
        counts = {name: {} for name in TOP_INDEXES + DETAIL_INDEXES + EVENT_DETAIL_INDEXES + SERVICE_DETAIL_INDEXES}
        first_ts = ""
        latest_ts = ""
        for rec in records:
            fields = _event_fields(rec)
            ts = str(rec.get("ts") or "")
            if ts and (not first_ts or ts < first_ts):
                first_ts = ts
            if ts > latest_ts:
                latest_ts = ts
            _count(counts, "service", fields["service"])
            _count(counts, "event", fields["event"])
            _count(counts, "level", fields["level"])
            _count(counts, "remote", fields["remote"])
            _count(counts, "service_event", f"{fields['service']}:{fields['event']}" if fields["service"] and fields["event"] else "")
            _count(counts, "session_event", f"{fields['session']}:{fields['event']}" if fields["session"] and fields["event"] else "")
            _count(counts, "service_level", f"{fields['service']}:{fields['level']}" if fields["service"] and fields["level"] else "")
            _count(counts, "session_level", f"{fields['session']}:{fields['level']}" if fields["session"] and fields["level"] else "")
            _count(counts, "event_level", f"{fields['event']}:{fields['level']}" if fields["event"] and fields["level"] else "")
            _count(counts, "remote_event", f"{fields['remote']}:{fields['event']}" if fields["remote"] and fields["event"] else "")
            _count(counts, "remote_level", f"{fields['remote']}:{fields['level']}" if fields["remote"] and fields["level"] else "")
            for key in DETAIL_KEYS:
                value = fields[f"detail_{key}"]
                _count(counts, f"detail_{key}", value)
                if key in DETAIL_KEYS[:18]:
                    _count(counts, f"event_detail_{key}", f"{fields['event']}:{value}" if fields["event"] and value else "")
                    _count(counts, f"service_detail_{key}", f"{fields['service']}:{value}" if fields["service"] and value else "")
        stats = {
            "path": str(self.path),
            "total_count": len(records),
            "tail_count": len(tail),
            "tail_truncated": omitted > 0,
            "tail_omitted_count": omitted,
            "invalid_count": invalid,
            "tail_limit": limit,
            "first_event_at": first_ts,
            "latest_event_at": latest_ts,
            "tail": tail,
        }
        for name in TOP_INDEXES + DETAIL_INDEXES + EVENT_DETAIL_INDEXES + SERVICE_DETAIL_INDEXES:
            stats[f"by_{name}"] = counts[name]
        return stats


def event_log_stats(cfg, limit=12):
    return EventLog(cfg).stats(limit)


def append_event(cfg, service, event, level="info", session=None, remote=None, details=None):
    return EventLog(cfg).write(service, event, level=level, session=session, remote=remote, details=details)


def event_tail(cfg, limit=12):
    return EventLog(cfg).tail(limit)


def event_log_state_record(cfg, stats=None):
    stats = stats or event_log_stats(cfg)
    path = Path(str(stats.get("path") or EventLog(cfg).path))
    exists = path.is_file()
    invalid_count = int(stats.get("invalid_count", 0) or 0)
    total_count = int(stats.get("total_count", 0) or 0)
    rec = {
        "path": str(path),
        "exists": exists,
        "valid": bool(exists and invalid_count == 0),
        "event_count": total_count,
        "invalid_count": invalid_count,
        "tail_count": int(stats.get("tail_count", 0) or 0),
        "tail_truncated": bool(stats.get("tail_truncated", False)),
        "tail_omitted_count": int(stats.get("tail_omitted_count", 0) or 0),
        "tail_limit": int(stats.get("tail_limit", 0) or 0),
        "first_event_at": stats.get("first_event_at", ""),
        "latest_event_at": stats.get("latest_event_at", ""),
        "error": "",
    }
    rec["tail_has_records"] = rec["tail_count"] > 0
    rec["tail_has_omitted_records"] = rec["tail_omitted_count"] > 0
    rec["tail_empty_due_to_limit"] = total_count > 0 and rec["tail_count"] == 0 and rec["tail_limit"] == 0
    if exists:
        try:
            rec["size"] = path.stat().st_size
        except OSError as exc:
            rec["error"] = str(exc)
    return rec


def event_log_state_status(cfg, stats=None):
    state_record = event_log_state_record(cfg, stats)
    state_record["has_invalid_records"] = int(state_record.get("invalid_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "event_log_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "event_log_state_records_by_exists": records_by_key(state_records, "exists"),
        "event_log_state_records_by_valid": records_by_key(state_records, "valid"),
        "event_log_state_records_by_tail_truncated": records_by_key(
            state_records, "tail_truncated"
        ),
        "event_log_state_records_by_has_invalid_records": records_by_key(
            state_records, "has_invalid_records"
        ),
        "event_log_state_records_by_tail_has_records": records_by_key(
            state_records, "tail_has_records"
        ),
        "event_log_state_records_by_tail_has_omitted_records": records_by_key(
            state_records, "tail_has_omitted_records"
        ),
        "event_log_state_records_by_tail_empty_due_to_limit": records_by_key(
            state_records, "tail_empty_due_to_limit"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def event_log_status_context(cfg, limit=12, target_filter_id="", target_filter_session_ids=None):
    event_stats = event_log_stats(cfg, limit)
    event_log_status = event_log_state_status(cfg, event_stats)
    events = event_stats["tail"]
    unfiltered_tail_count = len(events)
    if target_filter_id:
        from gritlib.target_records import event_for_target

        events = [
            event for event in events
            if event_for_target(event, target_filter_id, target_filter_session_ids)
        ]
    event_summary_stats = event_stats
    if target_filter_id:
        event_summary_stats = event_summary_stats_for_records(event_stats, events)
    return {
        "stats": event_stats,
        "summary_stats": event_summary_stats,
        "events": events,
        "unfiltered_tail_count": unfiltered_tail_count,
        "state_record": event_log_status["state_record"],
        "state_records": event_log_status["state_records"],
        "state_index_maps": event_log_status["state_index_maps"],
        "indexes": event_record_indexes(events),
    }


def event_tail_availability_text(doc):
    state = (doc or {}).get("event_log_state") or {}
    return (
        f"tail_has_records={'yes' if state.get('tail_has_records') else 'no'} "
        f"tail_has_omitted={'yes' if state.get('tail_has_omitted_records') else 'no'} "
        f"tail_empty_due_to_limit={'yes' if state.get('tail_empty_due_to_limit') else 'no'}"
    )


def event_record_indexes(records):
    indexes = event_record_index_maps(records)
    return (
        indexes["id"], indexes["session"], indexes["service"], indexes["event"], indexes["level"], indexes["remote"],
        indexes["service_event"], indexes["session_event"], indexes["service_level"], indexes["event_level"],
        indexes["session_level"], indexes["remote_event"], indexes["remote_level"], indexes["detail_status"],
        indexes["detail_operation"], indexes["detail_http_status"], indexes["detail_request_name"],
        indexes["detail_filename"], indexes["detail_reason"],
        indexes["detail_sha256"], indexes["detail_command_id"], indexes["detail_command_sha256"],
        indexes["detail_job_id"], indexes["detail_action_id"],
        indexes["detail_key"], indexes["detail_config_path"],
        indexes["detail_target_id"], indexes["detail_target_label"], indexes["detail_expected_target_id"],
        indexes["detail_target_identity_source"], indexes["detail_target_identity_confidence"],
        indexes["detail_poll_mode"], indexes["detail_poll_interval_sec"], indexes["detail_poll_jitter_pct"],
        indexes["detail_poll_backoff"], indexes["detail_poll_max_interval_sec"], indexes["detail_max_polls"],
        indexes["event_detail_status"], indexes["service_detail_status"],
        indexes["event_detail_operation"], indexes["service_detail_operation"],
        indexes["event_detail_http_status"], indexes["service_detail_http_status"],
        indexes["event_detail_request_name"], indexes["service_detail_request_name"],
        indexes["event_detail_filename"], indexes["service_detail_filename"],
        indexes["event_detail_reason"], indexes["service_detail_reason"],
        indexes["event_detail_sha256"], indexes["service_detail_sha256"],
        indexes["event_detail_command_id"], indexes["service_detail_command_id"],
        indexes["event_detail_command_sha256"], indexes["service_detail_command_sha256"],
        indexes["event_detail_job_id"], indexes["service_detail_job_id"],
        indexes["event_detail_action_id"], indexes["service_detail_action_id"],
        indexes["event_detail_key"], indexes["service_detail_key"],
        indexes["event_detail_config_path"], indexes["service_detail_config_path"],
        indexes["event_detail_target_id"], indexes["service_detail_target_id"],
        indexes["event_detail_target_label"], indexes["service_detail_target_label"],
        indexes["event_detail_expected_target_id"], indexes["service_detail_expected_target_id"],
        indexes["event_detail_target_identity_source"], indexes["service_detail_target_identity_source"],
        indexes["event_detail_target_identity_confidence"], indexes["service_detail_target_identity_confidence"],
    )


def event_record_index_maps(records):
    indexes = {name: {} for name in ("id", "session") + TOP_INDEXES + DETAIL_INDEXES + EVENT_DETAIL_INDEXES + SERVICE_DETAIL_INDEXES}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        fields = _event_fields(rec)
        if fields["id"]:
            indexes["id"][fields["id"]] = rec
        _append(indexes, "session", fields["session"], rec)
        _append(indexes, "service", fields["service"], rec)
        _append(indexes, "event", fields["event"], rec)
        _append(indexes, "level", fields["level"], rec)
        _append(indexes, "remote", fields["remote"], rec)
        _append(indexes, "service_event", f"{fields['service']}:{fields['event']}" if fields["service"] and fields["event"] else "", rec)
        _append(indexes, "session_event", f"{fields['session']}:{fields['event']}" if fields["session"] and fields["event"] else "", rec)
        _append(indexes, "service_level", f"{fields['service']}:{fields['level']}" if fields["service"] and fields["level"] else "", rec)
        _append(indexes, "session_level", f"{fields['session']}:{fields['level']}" if fields["session"] and fields["level"] else "", rec)
        _append(indexes, "event_level", f"{fields['event']}:{fields['level']}" if fields["event"] and fields["level"] else "", rec)
        _append(indexes, "remote_event", f"{fields['remote']}:{fields['event']}" if fields["remote"] and fields["event"] else "", rec)
        _append(indexes, "remote_level", f"{fields['remote']}:{fields['level']}" if fields["remote"] and fields["level"] else "", rec)
        for key in DETAIL_KEYS:
            value = fields[f"detail_{key}"]
            _append(indexes, f"detail_{key}", value, rec)
            if key in DETAIL_KEYS[:18]:
                _append(indexes, f"event_detail_{key}", f"{fields['event']}:{value}" if fields["event"] and value else "", rec)
                _append(indexes, f"service_detail_{key}", f"{fields['service']}:{value}" if fields["service"] and value else "", rec)
    return indexes


def event_summary_stats_for_records(event_stats, records):
    event_stats = event_stats if isinstance(event_stats, dict) else {}
    records = [rec for rec in records or [] if isinstance(rec, dict)]
    first_event_at = ""
    latest_event_at = ""
    for rec in records:
        ts = str(rec.get("ts") or "")
        if ts and (not first_event_at or ts < first_event_at):
            first_event_at = ts
        if ts > latest_event_at:
            latest_event_at = ts
    indexes = event_record_index_maps(records)

    def count_index(name):
        return {key: len(value) for key, value in (indexes.get(name) or {}).items()}

    summary = {
        "total_count": len(records),
        "tail_count": len(records),
        "tail_truncated": bool(event_stats.get("tail_truncated", False)),
        "tail_omitted_count": event_stats.get("tail_omitted_count", 0),
        "invalid_count": event_stats.get("invalid_count", 0),
        "first_event_at": first_event_at,
        "latest_event_at": latest_event_at,
    }
    for name in TOP_INDEXES + DETAIL_INDEXES + EVENT_DETAIL_INDEXES + SERVICE_DETAIL_INDEXES:
        summary[f"by_{name}"] = count_index(name)
    return summary


def event_status_summary(event_stats, event_state, event_state_records, events, summary_stats):
    event_stats = event_stats if isinstance(event_stats, dict) else {}
    event_state = event_state if isinstance(event_state, dict) else {}
    summary_stats = summary_stats if isinstance(summary_stats, dict) else {}
    out = {
        "event_count": summary_stats.get("total_count", 0),
        "event_log_total_count": event_stats.get("total_count", 0),
        "event_log_exists": bool(event_state.get("exists", False)),
        "event_log_valid": bool(event_state.get("valid", False)),
        "event_log_size": event_state.get("size", 0),
        "event_log_state_record_count": len(event_state_records or []),
        "event_log_has_invalid_records": bool(
            event_state.get("has_invalid_records", False)
        ),
        "event_tail_has_records": bool(event_state.get("tail_has_records", False)),
        "event_tail_has_omitted_records": bool(
            event_state.get("tail_has_omitted_records", False)
        ),
        "event_tail_empty_due_to_limit": bool(
            event_state.get("tail_empty_due_to_limit", False)
        ),
        "event_tail_count": len(events or []),
        "event_tail_truncated": bool(summary_stats.get("tail_truncated", False)),
        "event_tail_omitted_count": summary_stats.get("tail_omitted_count", 0),
        "event_invalid_count": event_stats.get("invalid_count", 0),
        "first_event_at": summary_stats.get("first_event_at", ""),
        "latest_event_at": summary_stats.get("latest_event_at", ""),
    }
    top_key_names = {
        "service": "event_service_counts",
        "event": "event_type_counts",
        "level": "event_level_counts",
        "remote": "event_remote_counts",
        "service_event": "event_service_event_counts",
        "session_event": "event_session_event_counts",
        "service_level": "event_service_level_counts",
        "event_level": "event_type_level_counts",
        "session_level": "event_session_level_counts",
        "remote_event": "event_remote_event_counts",
        "remote_level": "event_remote_level_counts",
    }
    for stats_key, summary_key in top_key_names.items():
        out[summary_key] = summary_stats.get(f"by_{stats_key}") or {}
    for key in DETAIL_KEYS:
        out[f"event_detail_{key}_counts"] = (
            summary_stats.get(f"by_detail_{key}") or {}
        )
    for key in DETAIL_KEYS[:18]:
        out[f"event_type_detail_{key}_counts"] = (
            summary_stats.get(f"by_event_detail_{key}") or {}
        )
        out[f"event_service_detail_{key}_counts"] = (
            summary_stats.get(f"by_service_detail_{key}") or {}
        )
    return out
