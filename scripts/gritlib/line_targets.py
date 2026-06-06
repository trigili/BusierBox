"""Line-console target rendering helpers."""

from pathlib import Path

from gritlib.console_display import console_display_mode, console_table
from gritlib.event_log import append_event
from gritlib.line_search import set_line_search_results
from gritlib.target_context import configured_target_filter
from gritlib.target_records import (
    target_filter_brief_text,
)
from gritlib.target_selection import set_workbench_target_filter


LINE_TARGET_COMMANDS = (
    {"action": "list", "commands": ("targets", "agents", "hosts")},
    {"action": "select", "commands": ("target", "agent", "host")},
)


def line_target_command_records():
    return [
        {
            "family": "target",
            "action": rec["action"],
            "commands": list(rec["commands"]),
            "primary": rec["commands"][0],
            "aliases": list(rec["commands"][1:]),
        }
        for rec in LINE_TARGET_COMMANDS
    ]


def parse_line_target_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    for rec in line_target_command_records():
        if cmd not in rec["commands"]:
            continue
        selector = " ".join(args).strip()
        action = rec["action"]
        if action == "select" and not selector:
            action = "list"
        return {"action": action, "selector": selector, "command": cmd}
    return {}


def dispatch_line_target_command(
    target_cmd,
    *,
    list_func=None,
    select_func=None,
):
    action = (target_cmd or {}).get("action")
    try:
        if action == "list" and list_func:
            return list_func()
        if action == "select" and select_func:
            return select_func(target_cmd.get("selector", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported target command")


def line_target_seen_text(rec):
    iso = rec.get("last_seen") or rec.get("last_seen_at") or ""
    if iso and len(iso) >= 16 and "T" in iso:
        date, rest = iso.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return iso or "-"


def line_target_value_text(value):
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text or "-"


def line_target_work_text(rec):
    return (
        rec.get("command")
        or rec.get("work_kind")
        or rec.get("request_name")
        or rec.get("bridge_profile")
        or "-"
    )


def line_target_mailbox_summary_text(rec):
    command_id = rec.get("command_id") or "-"
    status = line_target_value_text(rec.get("status"))
    waiting = line_target_value_text(rec.get("waiting_for"))
    work = line_target_work_text(rec)
    return f"{command_id}  {status}; waiting for {waiting}; {work}"


def line_target_session_summary_text(rec):
    session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name or "-"
    service = rec.get("service") or "-"
    state = line_target_value_text(rec.get("state"))
    updated = line_target_seen_text({"last_seen": rec.get("updated_at")})
    return f"{session_id}  {service}; {state}; updated {updated}"


def print_line_target_records(targets, current_target_id="", quote=None):
    rows = list(targets or [])
    current = str(current_target_id or "")
    quote = quote or (lambda text: str(text))

    def _label(rec):
        sel = "*" if str(rec.get("target_id") or "") == current else " "
        return sel + (rec.get("label") or rec.get("target_id") or "-")

    cols = [
        ("Target", _label),
        ("State", lambda r: r.get("connectivity_state") or "-"),
        ("Pending", lambda r: str(r.get("mailbox_pending_work_count") or 0)),
        ("Overdue", lambda r: "yes" if r.get("poll_overdue") else "no"),
        ("Seen", line_target_seen_text),
    ]
    console_table(
        f"Targets  ({len(rows)} total)" if rows else "Targets  (none)",
        rows, cols,
        footer="use N or agent ID to select  |  * = currently selected  |  targets ? for help",
    )
    return [
        {
            "kind": "target",
            "label": (
                f"{rec.get('target_id','')} label={rec.get('label','') or '-'} "
                f"state={rec.get('connectivity_state','') or '-'}"
            ),
            "rec": rec,
            "command": "",
            "use_hint": f"use target {quote(str(rec.get('target_id', '')))}",
        }
        for rec in rows
    ]


def line_target_filter_brief_text(target_filter, prefix="selected agent:"):
    if console_display_mode() == "normal":
        return target_filter_brief_text(target_filter, prefix=prefix)
    if not isinstance(target_filter, dict) or not target_filter.get("active"):
        return ""
    counts = target_filter.get("filtered_counts") or {}
    label = target_filter.get("selected_target_label") or "-"
    state = target_filter.get("selected_target_connectivity_state") or "-"
    pending = target_filter.get("selected_target_mailbox_pending_work_count", 0)
    sessions = counts.get("sessions", 0)
    uploads = counts.get("uploads", 0)
    return (
        f"{prefix} {label} ({state})  "
        f"mailbox {pending}  sessions {sessions}  uploads {uploads}"
    )


def print_selected_line_target(rec):
    rec = rec or {}
    if rec.get("selected"):
        tid = rec.get("target_id", "")
        label = rec.get("target_label") or ""
        display = f"{label}  ({tid})" if label and label != tid else tid
        if console_display_mode() != "normal":
            display = label or tid
        print(f"  {display}")
        if console_display_mode() != "normal":
            print("  next: options | queue | mailbox | back")
        else:
            print("  options / next / sessions / queue / mailbox / back")
    else:
        print("  target filter cleared  —  showing all targets")


def current_line_target_record(cfg, snapshot_func):
    target_id = configured_target_filter(cfg)
    if not target_id:
        return {}
    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    for rec in snapshot_func(unfiltered_cfg).get("targets") or []:
        if str(rec.get("target_id") or "") == target_id:
            return rec
    return {"target_id": target_id}


def print_line_targets(cfg, snapshot_func, quote=None):
    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg)
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    search_records = print_line_target_records(targets, current_target_id=current, quote=quote)
    set_line_search_results(cfg, search_records)
    return targets


def select_line_target(cfg, selector, snapshot_func, targets=None, quote=None):
    targets = targets if targets is not None else print_line_targets(cfg, snapshot_func, quote=quote)
    rec = set_workbench_target_filter(cfg, selector, targets=targets)
    print_selected_line_target(rec)
    return rec


def interact_line_target(cfg, selector, snapshot_func, quote=None):
    text = str(selector or "").strip()
    if text:
        targets = print_line_targets(cfg, snapshot_func, quote=quote)
        select_line_target(cfg, text, snapshot_func, targets=targets, quote=quote)
    target_id = configured_target_filter(cfg)
    if not target_id:
        raise ValueError("usage: interact agent ID|LABEL|NUMBER or select an agent first")
    snap = snapshot_func(cfg)
    target = current_line_target_record(cfg, snapshot_func)
    target_filter = snap.get("target_filter") or {}
    print_line_target_interaction(
        cfg,
        target_id,
        target,
        target_filter,
        snap.get("target_mailbox_records") or [],
        snap.get("sessions") or [],
    )


def print_line_target_interaction(
    cfg, target_id, target, target_filter, mailbox_records, sessions
):
    label = target.get("label") or target_filter.get("target_label") or "-"
    state = target.get("connectivity_state") or target_filter.get("connectivity_state") or "-"
    display = f"{label} ({target_id})" if label and label != "-" and label != target_id else target_id
    print(f"Agent interaction: {display}")
    print(f"  state: {state}")
    print(line_target_filter_brief_text(target_filter, prefix="  selected agent:"))
    if console_display_mode() != "normal":
        print("  commands: queue COMMAND | probe queue | mailbox | files | sessions | back")
    else:
        print("  commands: queue COMMAND, probe queue, download --queue TARGET_PATH, mailbox, upload --start LOCAL [NAME], fetch --queue NAME, serve-binary --start PATH [NAME], sessions, show activity, clear target")
    pending = [rec for rec in mailbox_records or [] if rec.get("pending_work")]
    if pending:
        print("  pending work:")
        for rec in pending[:3]:
            print(f"    {line_target_mailbox_summary_text(rec)}")
    else:
        print("  pending work: none")
    target_sessions = [
        rec for rec in sessions or []
        if str(rec.get("target_id") or "") == target_id
    ]
    if target_sessions:
        print("  recent sessions:")
        for rec in target_sessions[:3]:
            print(f"    {line_target_session_summary_text(rec)}")
    else:
        print("  recent sessions: none")
    append_event(cfg, "workbench", "workbench_target_interaction_viewed", details={
        "target_id": target_id,
        "target_label": label,
        "pending_work_count": len(pending),
        "session_count": len(target_sessions),
    })
