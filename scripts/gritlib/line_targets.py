"""Line-console target rendering helpers."""

from pathlib import Path

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.shell_utils import shquote
from gritlib.target_records import configured_target_filter, target_filter_summary_text


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


def print_line_target_interaction(
    cfg, target_id, target, target_filter, mailbox_records, sessions,
    quote=shquote, default_config=DEFAULT_CONFIG
):
    label = target.get("label") or target_filter.get("target_label") or "-"
    state = target.get("connectivity_state") or target_filter.get("connectivity_state") or "-"
    print(f"Agent interaction: {target_id} label={label} state={state}")
    print(target_filter_summary_text(target_filter, prefix="  status:"))
    print("  commands: queue COMMAND, probe --queue, download --queue TARGET_PATH, mailbox, upload --start LOCAL [NAME], fetch --queue NAME, serve-binary --start PATH [NAME], sessions, show activity, clear target")
    print(
        "  status_command: scripts/grit-console --config "
        + quote(str(cfg.get("_config_path", default_config)))
        + " --target-id "
        + quote(target_id)
        + " --status"
    )
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
