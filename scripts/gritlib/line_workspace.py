"""Line-console workspace rendering for grit-console."""

from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.record_utils import format_counts
from gritlib.target_records import target_filter_summary_text


def line_tui_prompt(target_id="", module="", target_context=None):
    target_id = str(target_id or "").strip()
    module = str(module or "").strip()
    module_suffix = f"/{module}" if module else ""
    if not target_id:
        return f"grit[all]{module_suffix}> "
    ctx = target_context or {}
    label = str(ctx.get("target_label") or "").strip()
    display = label or target_id
    if len(display) > 36:
        display = display[:33] + "..."
    return f"grit[{display}]{module_suffix}> "


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


def print_line_next(
    cfg, snap, module="", target_id="", prompt_text="",
    selected_action=None, job_record=None
):
    module = str(module or "").strip()
    target_id = str(target_id or "").strip()
    selected_action = selected_action or (lambda: {})
    job_record = job_record or (lambda _job_id: {})
    print("Next actions:")
    print(f"  context={str(prompt_text or '').strip()}")
    if module.startswith("action/"):
        action = selected_action()
        if action:
            print(f"  selected module={action.get('kind', '')}:{action.get('id', '')}")
            print("  commands: options, check, run, run --dry-run, run --confirm, background")
            if action.get("background_supported"):
                print("  background_job: run -j")
        else:
            print("  selected module is stale; commands: show modules, search TERM, back")
    elif module.startswith("service/"):
        service = module.split("/", 1)[1]
        print(f"  selected listener={service}")
        print("  options / start / stop / listeners -v / back")
    elif module.startswith("route/"):
        route_name = module.split("/", 1)[1]
        print(f"  selected route={route_name}")
        print("  options / start / stop / routes -v / back")
    elif module.startswith("session/"):
        session_id = module.split("/", 1)[1]
        print(f"  selected session={session_id}")
        print("  commands: info, options, interact, sessions -v, background")
    elif module.startswith("job/"):
        job_id = module.split("/", 1)[1]
        rec = job_record(job_id)
        print(f"  selected job={job_id}")
        if rec:
            print(f"  action={rec.get('action_id', '') or '-'} state={rec.get('effective_state', '') or rec.get('state', '') or '-'}")
        print("  commands: info, options, jobs, jobs -i ID, background")
    elif target_id:
        target_filter = snap.get("target_filter") or {}
        print(target_filter_summary_text(target_filter, prefix="  selected agent:"))
        print("  commands: interact, queue COMMAND, probe --queue, download --queue TARGET_PATH, upload --start LOCAL NAME, fetch --queue NAME, show activity, serve-binary --start PATH NAME, clear target")
    else:
        print("  selected agent=all")
        print("  commands: workspace, agents, listeners, routes, sessions, show categories, search TERM")
    sessions = snap.get("sessions") or []
    if sessions:
        print("  sessions: sessions -l, sessions -v, sessions -i ID, use session ID")
    print("  help: help use, help modules, help routes, help sessions")
    append_event(cfg, "workbench", "workbench_console_next_shown", details={
        "module": module or "root",
        "target_id": target_id,
        "session_count": len(sessions),
    })
