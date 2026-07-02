"""Line-console event browser helpers."""

import time
from pathlib import Path

from gritlib.console_display import console_table
from gritlib.event_log import EventLog, append_event
from gritlib.session_state import parse_utc_timestamp


EVENT_FILTER_KEYS = (
    "service", "event", "level", "target", "remote", "session", "status",
    "operation", "request_name", "file", "filename", "command_id", "command", "job_id", "job",
    "module_id", "module", "action_id",
)
EVENT_FILTER_ALIASES = {
    "file": "request_name",
    "command": "command_id",
    "job": "job_id",
    "module": "action_id",
    "module_id": "action_id",
}
EVENT_NAME_LABELS = {
    "target-filter-cleared": "target selection cleared",
    "main-selected": "returned to root prompt",
    "next-shown": "next suggestions shown",
    "files-listed": "files listed",
    "command-queue-inspected": "queue inspected",
    "release-viewed": "release viewed",
    "sessions-listed": "sessions listed",
    "routes-listed": "routes listed",
}
EVENT_USAGE = "\n".join([
    "usage:",
    "  events",
    "  events n N",
    "  events since 2h",
    "  events service=NAME",
    "  events event=NAME",
    "  events level=LEVEL",
    "  events target=ID",
    "  events target=LABEL",
    "  events status=TEXT",
    "  events operation=TEXT",
    "  events file=NAME",
    "  events command=ID",
    "  events job=ID",
    "  events module=ID",
])


def line_event_normalized_name(event):
    name = str((event or {}).get("event") or "")
    if name.startswith("workbench_"):
        name = name[len("workbench_"):]
        if name.startswith("console_"):
            name = name[len("console_"):]
        name = name.replace("_console_", "_")
    return name.replace("_", "-") or "-"


def parse_line_event_since(text):
    value = str(text or "").strip().lower()
    if not value:
        raise ValueError("usage: events since 2h")
    unit = value[-1]
    number_text = value[:-1] if unit.isalpha() else value
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    multiplier = multipliers.get(unit, 1)
    if not number_text.isdigit() or int(number_text) <= 0:
        raise ValueError("usage:\n  events since 30m\n  events since 2h\n  events since 1d")
    return time.time() - (int(number_text) * multiplier)


def line_event_matches_filter(event, key, expected):
    expected = str(expected or "").lower()
    if not expected:
        return True
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    values = []
    if key in {"service", "event", "level", "remote", "session"}:
        values.append(event.get(key))
        if key == "service":
            values.append(line_event_service_label(event))
        elif key == "event":
            values.append(line_event_normalized_name(event))
            values.append(line_event_name_label(event))
    elif key == "target":
        values.extend([
            details.get("target_id"),
            details.get("target_label"),
            details.get("expected_target_id"),
            details.get("target"),
        ])
    else:
        values.append(details.get(key))
    return any(expected in str(value or "").lower() for value in values)


def line_event_service_label(event):
    service = str((event or {}).get("service") or "")
    if service == "workbench":
        return "console"
    return service or "-"


def line_event_name_label(event):
    raw_name = str((event or {}).get("event") or "")
    if not raw_name.startswith("workbench_"):
        return raw_name or "-"
    normalized = line_event_normalized_name(event)
    return EVENT_NAME_LABELS.get(normalized, normalized)


def line_event_summary_value(key, value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    if key in {"sha256", "command_sha256"} and len(text) > 16:
        return text[:12]
    return text


def line_event_summary(event):
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    hidden_keys = {
        "cleared_module", "cleared_target", "command", "dry_run_command", "headless_command",
        "release_dir", "run_command", "selected_at", "start_job_command", "verbose",
    }
    labels = {
        "http_status": "http",
        "request_name": "request",
        "command_id": "command",
        "command_sha256": "command sha",
        "shown_count": "shown",
        "matching_count": "matching",
        "total_count": "total",
        "invalid_count": "invalid",
    "target_mailbox_record_count": "target check-ins",
        "command_queue_workflow_action_count": "queue controls",
        "command_count": "commands",
        "has_result": "result",
        "module": "menu",
        "session_count": "sessions",
        "staged_count": "staged",
        "artifact_count": "artifacts",
        "device_count": "devices",
        "recommendation_count": "recommendations",
        "target_id": "target",
        "target_label": "label",
    }
    order = (
        "operation", "status", "http_status", "request_name", "filename", "sha256",
        "reason", "command_id", "command_sha256", "shown_count", "matching_count",
        "total_count", "invalid_count", "command_count", "command_queue_workflow_action_count",
        "target_mailbox_record_count",
    )
    interesting = []
    for key in order + tuple(sorted(k for k in details if k not in order)):
        if key in hidden_keys:
            continue
        value = details.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            continue
        interesting.append(f"{labels.get(key, key.replace('_', ' '))} {line_event_summary_value(key, value)}")
        if len(interesting) >= 4:
            break
    summary = "  ".join(interesting)
    if len(summary) > 120:
        summary = summary[:117] + "..."
    return summary or "-"


def parse_line_events_args(args):
    limit = 20
    since_epoch = None
    filters = []
    idx = 0
    while idx < len(args):
        arg = str(args[idx] or "")
        if arg in {"-h", "--help", "help"}:
            raise ValueError(EVENT_USAGE)
        if arg in {"-n", "--limit", "n", "limit"}:
            idx += 1
            if idx >= len(args) or not str(args[idx]).isdigit() or int(args[idx]) <= 0:
                raise ValueError("usage:\n  events n N")
            limit = int(args[idx])
        elif arg.startswith("-n") and arg[2:].isdigit():
            limit = int(arg[2:])
        elif arg.startswith("--limit=") or arg.startswith("limit="):
            value = arg.split("=", 1)[1]
            if not value.isdigit() or int(value) <= 0:
                raise ValueError("usage:\n  events n N")
            limit = int(value)
        elif arg in {"--since", "since"}:
            idx += 1
            if idx >= len(args):
                raise ValueError("usage: events since 2h")
            since_epoch = parse_line_event_since(args[idx])
        elif arg.startswith("--since=") or arg.startswith("since="):
            since_epoch = parse_line_event_since(arg.split("=", 1)[1])
        elif "=" in arg:
            key, value = arg.split("=", 1)
            key = key.strip().lower()
            if key not in EVENT_FILTER_KEYS:
                raise ValueError(f"unsupported event filter: {key}; supported filters: {', '.join(EVENT_FILTER_KEYS)}")
            key = EVENT_FILTER_ALIASES.get(key, key)
            filters.append((key, value.strip()))
        else:
            raise ValueError(EVENT_USAGE)
        idx += 1
    return limit, since_epoch, filters


def parse_line_events_command(cmd, args):
    if str(cmd or "").strip().lower() != "events":
        return None
    return {
        "action": "list",
        "args": [str(arg) for arg in (args or [])],
    }


def dispatch_line_events_command(events_cmd, *, print_func=None):
    try:
        if print_func:
            return print_func((events_cmd or {}).get("args") or [])
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported events command")


def line_event_time_text(iso):
    text = str(iso or "")
    if len(text) >= 16 and "T" in text:
        date, rest = text.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return text or "-"


def line_event_log_display_path(cfg, path):
    event_path = Path(path)
    session_dir = Path(str((cfg or {}).get("operator_session_dir") or "local/operator-session"))
    try:
        return str(event_path.relative_to(session_dir.parent))
    except ValueError:
        return str(event_path)


def print_line_events_view(cfg, args):
    limit, since_epoch, filters = parse_line_events_args(args)
    event_log = EventLog(cfg)
    records, invalid_count = event_log.records()
    filtered = []
    for event in records:
        ts_epoch = parse_utc_timestamp(event.get("ts"))
        if since_epoch is not None and (ts_epoch is None or ts_epoch < since_epoch):
            continue
        if all(line_event_matches_filter(event, key, expected) for key, expected in filters):
            filtered.append(event)
    shown = filtered[-limit:] if limit else filtered

    title = f"Events  ({len(shown)} shown of {len(filtered)} matching, {len(records)} total)"
    if invalid_count:
        title += f"  invalid={invalid_count}"
    footer = "Full event log: view event log"
    if filters or since_epoch is not None or limit != 20:
        active = []
        if limit != 20:
            active.append(f"limit {limit}")
        if since_epoch is not None:
            active.append("since set")
        active.extend(f"{key}={value}" for key, value in filters)
        footer += "  filters: " + " ".join(active)
    console_table(
        title,
        shown,
        [
            ("At", lambda r: line_event_time_text(r.get("ts"))),
            ("Service", line_event_service_label),
            ("Event", line_event_name_label),
            ("Level", lambda r: r.get("level") or "-"),
            ("Summary", line_event_summary),
        ],
        footer=footer,
    )
    append_event(cfg, "workbench", "workbench_events_viewed", details={
        "shown_count": len(shown),
        "matching_count": len(filtered),
        "total_count": len(records),
        "invalid_count": invalid_count,
        "limit": limit,
        "filters": {key: value for key, value in filters},
        "since": bool(since_epoch is not None),
    })
