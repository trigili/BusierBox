"""Line-console workspace rendering for grit-console."""

from gritlib.console_display import console_table
from gritlib.record_utils import format_counts


def line_tui_status_bar(snap):
    summary = snap.get("summary") or {}
    target_filter = snap.get("target_filter") or {}
    counts = summary.get("connectivity_state_counts") or summary.get("target_connectivity_state_counts") or {}
    state_text = format_counts(counts) if counts else "none"
    selected = "-"
    if target_filter.get("active"):
        selected = str(target_filter.get("target_id") or target_filter.get("selected_target_id") or "-")
    pending_targets = (
        summary.get("mailbox_pending_target_count", "")
        if summary.get("mailbox_pending_target_count", "") != ""
        else summary.get("target_mailbox_pending_target_count", 0)
    )
    pending_work = (
        summary.get("mailbox_pending_work_count", "")
        if summary.get("mailbox_pending_work_count", "") != ""
        else summary.get("target_mailbox_pending_work_count", 0)
    )
    poll_overdue = (
        summary.get("poll_overdue_count", "")
        if summary.get("poll_overdue_count", "") != ""
        else summary.get("target_poll_overdue_count", 0)
    )
    return (
        "Status bar: "
        f"services={summary.get('listening_count', 0)} "
        f"warnings={len(snap.get('warnings') or [])} "
        f"targets={summary.get('target_count', 0)} "
        f"states={state_text} "
        f"mailbox_pending_targets={pending_targets} "
        f"mailbox_pending_work={pending_work} "
        f"poll_overdue={poll_overdue} "
        f"selected_target={selected} "
        f"events={summary.get('event_count', 0)}"
    )


def print_line_console_banner(snap, version):
    summary = snap.get("summary") or {}
    warnings = snap.get("warnings") or []
    target_filter = snap.get("target_filter") or {}
    parts = [f"{summary.get('listening_count', 0)} listening"]
    targets = summary.get("target_count", 0)
    if targets:
        parts.append(f"{targets} target{'s' if targets != 1 else ''}")
    sessions = summary.get("session_count", 0)
    if sessions:
        parts.append(f"{sessions} session{'s' if sessions != 1 else ''}")
    staged = summary.get("staged_count", 0)
    if staged:
        parts.append(f"{staged} staged")
    if warnings:
        parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
    events = summary.get("event_count", 0)
    if events:
        parts.append(f"{events} events")
    print(f"griTTYkit v{version}  " + "  |  ".join(parts))
    if target_filter.get("active"):
        label = target_filter.get("selected_target_label") or target_filter.get("target_id", "")
        state = target_filter.get("selected_target_connectivity_state") or "-"
        print(f"  selected: {label} ({state})")
    for w in warnings[:3]:
        svc = f" {w.get('service')}" if w.get("service") else ""
        msg = w.get("message") or ""
        hint = f"  -> {w.get('suggested_action')}" if w.get("suggested_action") else ""
        print(f"  [!]{svc}: {msg}{hint}")
    if len(warnings) > 3:
        print(f"  ... {len(warnings) - 3} more warning(s) — run: status")
    print("")
    print("  ? help  workspace overview  targets/sessions/files  start ssh|tls|file-service")


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
