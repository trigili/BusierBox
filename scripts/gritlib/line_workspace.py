"""Line-console workspace rendering for grit-console."""

from gritlib.console_display import console_table


def print_line_workspace_snapshot(snap):
    summary = snap.get("summary") or {}
    target_filter = snap.get("target_filter") or {}
    targets = snap.get("targets") or []
    sessions = snap.get("sessions") or []
    warnings = snap.get("warnings") or []

    def _fmt_seen(iso):
        if iso and len(iso) >= 16 and "T" in iso:
            date, rest = iso.split("T", 1)
            return f"{date[5:]} {rest[:5]}"
        return iso or "-"

    parts = [f"{summary.get('listening_count', 0)} listening"]
    if targets:
        parts.append(f"{len(targets)} target{'s' if len(targets) != 1 else ''}")
    if sessions:
        parts.append(f"{len(sessions)} session{'s' if len(sessions) != 1 else ''}")
    staged = summary.get("staged_count", 0)
    if staged:
        parts.append(f"{staged} staged")
    pending = summary.get("mailbox_pending_work_count") or summary.get("target_mailbox_pending_work_count") or 0
    if pending:
        parts.append(f"{pending} pending")
    if warnings:
        parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
    print("Workspace  " + "  |  ".join(parts))

    selected_id = target_filter.get("target_id") if target_filter.get("active") else None
    if selected_id:
        label = target_filter.get("selected_target_label") or selected_id
        state = target_filter.get("selected_target_connectivity_state") or "-"
        print(f"  selected: {label} ({state})")

    if targets:
        print("")
        cols = [
            ("Target", lambda r: ("* " if str(r.get("target_id") or "") == (selected_id or "") else "  ")
                       + (r.get("label") or r.get("target_id") or "-")),
            ("State", lambda r: r.get("connectivity_state") or "-"),
            ("Pending", lambda r: str(r.get("mailbox_pending_work_count") or 0)),
            ("Seen", lambda r: _fmt_seen(r.get("last_seen") or r.get("last_seen_at"))),
        ]
        shown = targets[:6]
        console_table(
            f"Agents  ({len(targets)} total)" if len(targets) > 6 else f"Agents  ({len(targets)} total)",
            shown, cols,
        )
        if len(targets) > 6:
            print(f"  ... {len(targets) - 6} more — use targets")

    for warning in warnings[:3]:
        svc = f" {warning.get('service')}" if warning.get("service") else ""
        print(f"  [!]{svc}: {warning.get('message', '')}")

    print("")
    print("  search TERM  |  targets  sessions  files  listeners  routes  |  ? help")
