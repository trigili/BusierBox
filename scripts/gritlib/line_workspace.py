"""Line-console workspace rendering for grit-console."""

from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.record_utils import format_counts
from gritlib.target_records import (
    target_filter_evidence_lines, target_filter_summary_text,
)


def line_listener_module_name(module):
    module = str(module or "").strip()
    if module.startswith("listener/") or module.startswith("service/"):
        return module.split("/", 1)[1]
    return ""


def line_display_module(module):
    module = str(module or "").strip()
    listener = line_listener_module_name(module)
    if listener:
        return f"listener/{listener}"
    return module


def line_repl_prompt(target_id="", module="", target_context=None):
    target_id = str(target_id or "").strip()
    module = line_display_module(module)
    module_suffix = f"/{module}" if module else ""
    if not target_id:
        return f"grit[all]{module_suffix}> "
    ctx = target_context or {}
    label = str(ctx.get("target_label") or "").strip()
    display = label or target_id
    if len(display) > 36:
        display = display[:33] + "..."
    return f"grit[{display}]{module_suffix}> "


def line_repl_status_bar(snap):
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
    parts = [
        f"{summary.get('listening_count', 0)} listening",
        f"{summary.get('target_count', 0)} targets",
        f"states {state_text}",
    ]
    warnings = len(snap.get("warnings") or [])
    if warnings:
        parts.append(f"{warnings} warnings")
    if _count_value(pending_work):
        parts.append(f"{pending_work} mailbox work")
    elif _count_value(pending_targets):
        parts.append(f"{pending_targets} mailbox targets")
    else:
        parts.append("mailbox clear")
    if _count_value(poll_overdue):
        parts.append(f"{poll_overdue} poll overdue")
    if selected != "-":
        parts.append(f"selected {selected}")
    parts.append(f"{summary.get('event_count', 0)} events")
    return "Status: " + "  |  ".join(parts) + "\n" + line_banner_hint(snap)


def _count_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def line_banner_hint(snap):
    summary = snap.get("summary") or {}
    warnings = snap.get("warnings") or []
    target_filter = snap.get("target_filter") or {}
    hints = ["? help", "next", "workspace"]

    pending_work = _count_value(
        summary.get("mailbox_pending_work_count")
        or summary.get("target_mailbox_pending_work_count")
    )
    poll_overdue = _count_value(
        summary.get("poll_overdue_count")
        or summary.get("target_poll_overdue_count")
    )
    listening = _count_value(summary.get("listening_count"))
    target_count = _count_value(summary.get("target_count"))
    session_count = _count_value(summary.get("session_count"))
    staged_count = _count_value(summary.get("staged_count"))
    route_count = _count_value(summary.get("bridge_profile_count"))

    if warnings:
        hints.append("status")
    if target_filter.get("active"):
        hints.extend(["mailbox", "sessions", "clear target"])
    elif target_count:
        hints.append("targets")
    else:
        hints.append("probe --start")
    if pending_work or poll_overdue:
        hints.append("queue")
    if staged_count:
        hints.append("files")
    if session_count:
        hints.append("sessions")
    if route_count:
        hints.append("routes")
    if not listening:
        hints.append("listeners")

    deduped = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return "  next: " + "  |  ".join(deduped[:8])


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
    print(line_banner_hint(snap))


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
    routes = summary.get("bridge_profile_count", 0)
    if routes:
        parts.append(f"{routes} route{'s' if routes != 1 else ''}")
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

    if (
        not targets
        and not sessions
        and not staged
        and not routes
        and not warnings
        and int(summary.get("listening_count", 0) or 0) == 0
    ):
        print("")
        print("  No active workspace items yet.")
        print("  Start here:")
        print("    probe --start        serve the shell probe and print target commands")
        print("    listeners            see services you can start")
        print("    upload --start FILE  stage a file for target fetch")
        print("    help workflow        see the probe-to-payload flow")

    print("")
    print("  search TERM  |  targets  sessions  files  listeners  routes  |  ? help")


def print_line_info(
    snap, module="root", prompt_text="", selected_action=None,
    service_record=None, route_record=None, session_record=None, job_record=None,
    probe_delivery_printer=None, bridge_command_builder=None,
    view_command_builder=None, cancel_job_command_builder=None
):
    selected_action = selected_action or (lambda: {})
    service_record = service_record or (lambda _name: {})
    route_record = route_record or (lambda _name: {})
    session_record = session_record or (lambda _id: {})
    job_record = job_record or (lambda _id: {})
    bridge_command_builder = bridge_command_builder or (
        lambda _action, _name="", extra=None: ""
    )
    view_command_builder = view_command_builder or (lambda _path: "")
    cancel_job_command_builder = cancel_job_command_builder or (lambda _job_id: "")

    print("Console context:")
    print(f"  prompt={str(prompt_text or '').strip()}")
    module = str(module or "root")
    print(f"  module={module}")
    action = selected_action()
    if action:
        print(
            f"  action={action.get('kind', '')}:{action.get('id', '')} "
            f"state={action.get('operator_action_state', '') or '-'} "
            f"reason={action.get('operator_action_reason', '') or '-'}"
        )
        print(f"    label={action.get('label', '') or '-'}")
        print(f"    category={action.get('category', '') or '-'} workflow={action.get('workflow', '') or '-'}")
        print(f"    confirm={'yes' if action.get('requires_confirmation') else 'no'} background={'yes' if action.get('background_supported') else 'no'}")
        print("    commands: check, run, run --dry-run, run --confirm")
        if action.get("background_supported"):
            print("    background: run -j")
        print("    next: options, check, run, back")
    elif line_listener_module_name(module):
        service = line_listener_module_name(module)
        rec = service_record(service)
        actual = rec.get("actual") or "-" if rec else "-"
        port = rec.get("port") or "-" if rec else "-"
        pid = rec.get("pid") or "-" if rec else "-"
        print(f"  {service}  —  {actual}  |  :{port}  |  pid {pid}")
        if service in {"probe", "probe-tftp", "probe-ftp", "probe-dns"}:
            if probe_delivery_printer:
                probe_delivery_printer()
        else:
            print("    options / start / stop / back")
    elif module.startswith("route/"):
        route_name = module.split("/", 1)[1]
        rec = route_record(route_name)
        print(f"  route={route_name}")
        if rec:
            print(
                f"    state={rec.get('current_state', '') or '-'} "
                f"active={'yes' if rec.get('active') else 'no'} "
                f"listen={rec.get('listen_host', '')}:{rec.get('listen_port', '')} "
                f"dest={rec.get('dest_host', '')}:{rec.get('dest_port', '')}"
            )
            print(f"    route_path={rec.get('route_path', '') or '-'}")
            print(
                f"    hops={rec.get('hop_count', 0)} "
                f"multi_hop={'yes' if rec.get('multi_hop') else 'no'} "
                f"target={rec.get('target_id', '') or '-'}"
            )
        print(f"    commands: route {route_name}, route start {route_name}, route stop {route_name}")
        print("    next: options, start, stop, routes -v, back")
    elif module.startswith("session/"):
        session_id = module.split("/", 1)[1]
        rec = session_record(session_id)
        print(f"  session={session_id}")
        if rec:
            path = str(rec.get("path") or "")
            print(
                f"    service={rec.get('service', '') or '-'} "
                f"state={rec.get('state', '') or '-'} "
                f"exit={rec.get('exit_reason', '') or '-'} "
                f"updated={rec.get('updated_at', '') or '-'}"
            )
            print(f"    path={path}")
            if rec.get("session_log"):
                print(f"    session_log={rec.get('session_log', '')}")
            if rec.get("event_log"):
                print(f"    event_log={rec.get('event_log', '')}")
        print("    next: options, interact, sessions -v, view PATH, back")
    elif module.startswith("job/"):
        job_id = module.split("/", 1)[1]
        rec = job_record(job_id)
        print(f"  job={job_id}")
        if rec:
            print(
                f"    action={rec.get('action_id', '') or '-'} "
                f"state={rec.get('effective_state', '') or rec.get('state', '') or '-'} "
                f"pid={rec.get('pid', '') or '-'} "
                f"managed={'yes' if rec.get('pid_managed') else 'no'} "
                f"cancel_supported={'yes' if rec.get('cancel_supported') else 'no'}"
            )
            print(f"    command={rec.get('command', '') or '-'}")
            if rec.get("log_path"):
                print(f"    log={rec.get('log_path', '')}")
            if rec.get("last_output_tail"):
                print("    last_output:")
                for line in rec.get("last_output_tail") or []:
                    print(f"      {line}")
        print("    next: options, jobs, jobs -v, back")
    else:
        print("  action=none")
    target_filter = (snap or {}).get("target_filter") or {}
    if target_filter.get("active"):
        print(target_filter_summary_text(target_filter, prefix="  target:"))
        for line in target_filter_evidence_lines(target_filter):
            print(f"    {line}")
    else:
        print("  target=all")


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
    elif line_listener_module_name(module):
        service = line_listener_module_name(module)
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
