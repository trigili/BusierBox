"""Line-console target rendering helpers."""

from gritlib.console_display import console_table


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
