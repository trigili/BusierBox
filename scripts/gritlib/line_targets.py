"""Line-console target rendering helpers."""

from pathlib import Path

from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.target_records import (
    configured_target_filter,
    set_workbench_target_filter,
    target_filter_brief_text,
)


def parse_line_target_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd in {"targets", "agents", "hosts"}:
        return {"action": "list"}
    if cmd not in {"target", "agent", "host"}:
        return {}
    selector = " ".join(args).strip()
    return {"action": "select" if selector else "list", "selector": selector}


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


def print_selected_line_target(rec):
    rec = rec or {}
    if rec.get("selected"):
        tid = rec.get("target_id", "")
        label = rec.get("target_label") or ""
        display = f"{label}  ({tid})" if label and label != tid else tid
        print(f"  {display}")
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
    cfg["_line_console_search_results"] = search_records
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
    print(target_filter_brief_text(target_filter, prefix="  status:"))
    print("  commands: queue COMMAND, probe --queue, download --queue TARGET_PATH, mailbox, upload --start LOCAL [NAME], fetch --queue NAME, serve-binary --start PATH [NAME], sessions, show activity, clear target")
    pending = [rec for rec in mailbox_records or [] if rec.get("pending_work")]
    if pending:
        print("  pending work:")
        for rec in pending[:3]:
            print(
                f"    {rec.get('command_id', '')} status={rec.get('status', '') or '-'} "
                f"waiting_for={rec.get('waiting_for', '') or '-'} "
                f"command={rec.get('command', '') or rec.get('work_kind', '') or '-'}"
            )
    else:
        print("  pending work: none")
    target_sessions = [
        rec for rec in sessions or []
        if str(rec.get("target_id") or "") == target_id
    ]
    if target_sessions:
        print("  recent sessions:")
        for rec in target_sessions[:3]:
            session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
            print(
                f"    {session_id} service={rec.get('service', '') or '-'} "
                f"state={rec.get('state', '') or '-'} updated={rec.get('updated_at', '') or '-'}"
            )
    else:
        print("  recent sessions: none")
    append_event(cfg, "workbench", "workbench_target_interaction_viewed", details={
        "target_id": target_id,
        "target_label": label,
        "pending_work_count": len(pending),
        "session_count": len(target_sessions),
    })
