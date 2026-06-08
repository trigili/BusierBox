"""Line-console event browser helpers."""

import time

from gritlib.console_display import console_table
from gritlib.event_log import EventLog, append_event
from gritlib.session_state import parse_utc_timestamp


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
        raise ValueError("usage: events since 30m|2h|1d")
    return time.time() - (int(number_text) * multiplier)


def line_event_matches_filter(event, key, expected):
    expected = str(expected or "").lower()
    if not expected:
        return True
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    values = []
    if key in {"service", "event", "level", "remote", "session"}:
        values.append(event.get(key))
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


def line_event_summary(event):
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    hidden_keys = {"command", "dry_run_command", "headless_command", "run_command", "start_job_command"}
    labels = {
        "http_status": "http",
        "request_name": "request",
        "command_id": "command",
        "command_sha256": "command sha",
        "shown_count": "shown",
        "matching_count": "matching",
        "total_count": "total",
        "invalid_count": "invalid",
        "target_mailbox_record_count": "mailbox records",
        "command_queue_workflow_action_count": "queue actions",
        "command_count": "commands",
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
        interesting.append(f"{labels.get(key, key.replace('_', ' '))} {value}")
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
            raise ValueError("usage: events [n N] [service=NAME] [event=NAME] [level=LEVEL] [target=ID|LABEL] [since 2h]")
        if arg in {"-n", "--limit", "n", "limit"}:
            idx += 1
            if idx >= len(args) or not str(args[idx]).isdigit() or int(args[idx]) <= 0:
                raise ValueError("usage: events n N")
            limit = int(args[idx])
        elif arg.startswith("-n") and arg[2:].isdigit():
            limit = int(arg[2:])
        elif arg.startswith("--limit=") or arg.startswith("limit="):
            value = arg.split("=", 1)[1]
            if not value.isdigit() or int(value) <= 0:
                raise ValueError("usage: events limit=N")
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
            if key not in {"service", "event", "level", "target", "remote", "session", "status", "operation", "request_name", "filename", "command_id", "job_id", "action_id"}:
                raise ValueError(f"unsupported event filter: {key}")
            filters.append((key, value.strip()))
        else:
            raise ValueError("usage: events [n N] [service=NAME] [event=NAME] [level=LEVEL] [target=ID|LABEL] [since 2h]")
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
    footer = f"Event log: view {event_log.path}"
    if filters or since_epoch is not None or limit != 20:
        active = []
        if limit != 20:
            active.append(f"limit {limit}")
        if since_epoch is not None:
            active.append("since set")
        active.extend(f"{key} {value}" for key, value in filters)
        footer += "  filters: " + " ".join(active)
    console_table(
        title,
        shown,
        [
            ("At", lambda r: line_event_time_text(r.get("ts"))),
            ("Service", lambda r: r.get("service") or "-"),
            ("Event", lambda r: r.get("event") or "-"),
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
