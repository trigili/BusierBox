"""Line-console workspace rendering for grit-console."""

from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.bridge_routes import line_route_context_commands
from gritlib.line_probe_guidance import print_open_probe_menu_steps, print_probe_menu_steps
from gritlib.line_services import line_service_context_commands
from gritlib.profiles import active_profile, profile_records
from gritlib.record_utils import format_counts
from gritlib.target_filter_display import (
    target_filter_brief_text, target_filter_evidence_lines,
    target_filter_summary_text,
)
from gritlib.target_records import (
    configured_target_filter,
    target_context_fields,
)


LINE_WORKSPACE_COMMANDS = (
    {"action": "status", "commands": ("status", "summary")},
    {"action": "ips", "commands": ("ips", "local-ips", "list-local-ips")},
    {"action": "workspace", "commands": ("workspace", "overview", "dashboard")},
    {"action": "reload", "commands": ("reload",)},
    {"action": "refresh", "commands": ("refresh",)},
    {"action": "root", "commands": ("main", "home", "root")},
    {"action": "info", "commands": ("info",)},
    {"action": "next", "commands": ("next",)},
    {"action": "options", "commands": ("options", "opts")},
)


def line_workspace_command_records():
    return [
        {
            "family": "workspace",
            "action": rec["action"],
            "commands": list(rec["commands"]),
            "primary": rec["commands"][0],
            "aliases": list(rec["commands"][1:]),
        }
        for rec in LINE_WORKSPACE_COMMANDS
    ]


def parse_line_workspace_command(cmd, args=None):
    cmd = str(cmd or "").strip().lower()
    for rec in line_workspace_command_records():
        if cmd in rec["commands"]:
            return {"action": rec["action"], "command": cmd}
    return {}


def dispatch_line_workspace_command(
    workspace_cmd,
    *,
    status_func=None,
    ips_func=None,
    workspace_func=None,
    reload_func=None,
    root_func=None,
    info_func=None,
    next_func=None,
    options_func=None,
):
    action = (workspace_cmd or {}).get("action")
    if action == "status" and status_func:
        return status_func()
    if action == "ips" and ips_func:
        return ips_func()
    if action == "workspace" and workspace_func:
        return workspace_func()
    if action == "reload" and reload_func:
        return reload_func()
    if action == "refresh":
        return "refresh"
    if action == "root" and root_func:
        return root_func()
    if action == "info" and info_func:
        return info_func()
    if action == "next" and next_func:
        return next_func()
    if action == "options" and options_func:
        return options_func()
    raise ValueError("unsupported workspace command")


def reload_line_config(cfg, config_path="", load_config_fn=None, defaults=None, append_event_fn=None):
    config_path = str(config_path or cfg.get("_config_path") or "")
    if load_config_fn is None:
        raise ValueError("config reload support is unavailable")
    new_cfg = load_config_fn(config_path)
    internal = {key: value for key, value in cfg.items() if str(key).startswith("_")}
    cfg.clear()
    cfg.update(new_cfg)
    cfg.update(internal)
    print(f"Config reloaded: {config_path}")
    defaults = defaults or {}
    changed = [
        key for key in new_cfg
        if not str(key).startswith("_") and new_cfg.get(key) != defaults.get(key)
    ]
    print(f"  {len(changed)} setting(s) active from config file")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_config_reloaded", details={
            "config_path": config_path,
            "changed_count": len(changed),
        })
    return new_cfg


def reload_line_config_for_repl(
    cfg,
    *,
    default_config,
    load_config_fn=None,
    defaults=None,
    append_event_fn=None,
):
    config_path = str(cfg.get("_config_path") or default_config)
    try:
        return reload_line_config(
            cfg,
            config_path=config_path,
            load_config_fn=load_config_fn,
            defaults=defaults,
            append_event_fn=append_event_fn,
        )
    except Exception as exc:
        print(f"reload failed: {exc}")
        return None


def line_listener_module_name(module):
    module = str(module or "").strip()
    if module.startswith("listener/") or module.startswith("service/"):
        return module.split("/", 1)[1]
    return ""


def _line_listener_bind_text(rec):
    rec = rec or {}
    host = str(rec.get("bind_address") or "")
    port = str(rec.get("port") or "-")
    protocol = str(rec.get("protocol") or "tcp").upper()
    bind = f"{host}:{port}" if host else port
    return f"{bind}/{protocol}" if protocol != "TCP" else bind


def line_display_module(module):
    module = str(module or "").strip()
    listener = line_listener_module_name(module)
    if listener:
        return f"listener/{listener}"
    if module.startswith("action/"):
        return f"module/{module.split('/', 1)[1]}"
    return module


def line_display_area(module):
    module = str(module or "").strip()
    listener = line_listener_module_name(module)
    if listener:
        return f"listener {listener}"
    if module.startswith("action/"):
        return f"module {module.split('/', 1)[1]}"
    if module.startswith("route/"):
        return f"route {module.split('/', 1)[1]}"
    if module.startswith("session/"):
        return f"session {module.split('/', 1)[1]}"
    if module.startswith("job/"):
        return f"job {module.split('/', 1)[1]}"
    return module or "workspace"


def line_display_location(prompt_text="", module=""):
    prompt = str(prompt_text or "").strip()
    target = "all targets"
    if prompt.startswith("grit[") and "]" in prompt:
        target = prompt.split("]", 1)[0].removeprefix("grit[").strip() or target
    if str(module or "").startswith("action/") and "]/" in prompt:
        prompt_area = prompt.split("]/", 1)[1].removesuffix(">").strip()
        if prompt_area:
            return f"workspace ({target}) > {prompt_area.replace('/', ' ', 1)}"
    area = line_display_area(module)
    if area and area != "workspace":
        return f"workspace ({target}) > {area}"
    return f"workspace ({target})"


def line_repl_prompt(target_id="", module="", target_context=None, module_display=""):
    target_id = str(target_id or "").strip()
    module = str(module_display or "").strip() or line_display_module(module)
    module_suffix = f"/{module}" if module else ""
    if not target_id:
        return f"grit[all]{module_suffix}> "
    ctx = target_context or {}
    label = str(ctx.get("target_label") or "").strip()
    display = label or target_id
    if len(display) > 36:
        display = display[:33] + "..."
    return f"grit[{display}]{module_suffix}> "


def line_repl_prompt_for_config(cfg):
    target_id = configured_target_filter(cfg)
    module = str((cfg or {}).get("_line_console_module") or "").strip()
    module_display = ""
    if module.startswith("action/"):
        action_label = str((cfg or {}).get("_line_console_action_label") or "").strip()
        if action_label:
            module_display = f"module/{action_label}"
    ctx = target_context_fields(cfg, target_id) if target_id else {}
    return line_repl_prompt(
        target_id=target_id,
        module=module,
        target_context=ctx,
        module_display=module_display,
    )


def line_repl_status_bar(snap):
    summary = snap.get("summary") or {}
    target_filter = snap.get("target_filter") or {}
    active_profile = snap.get("active_profile") or {}
    counts = summary.get("connectivity_state_counts") or summary.get("target_connectivity_state_counts") or {}
    state_text = format_counts(counts) if counts else "none"
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
    workspace_parts = [
        f"{summary.get('listening_count', 0)} listening",
        f"{summary.get('target_count', 0)} targets",
        f"states {state_text}",
        f"{summary.get('session_count', 0)} sessions",
        f"{summary.get('staged_count', 0)} staged",
        f"{summary.get('bridge_profile_count', 0)} routes",
    ]
    lines = ["Workspace: " + "  |  ".join(workspace_parts)]

    if target_filter.get("active"):
        label = (
            target_filter.get("selected_target_label")
            or target_filter.get("target_label")
            or target_filter.get("target_id")
            or target_filter.get("selected_target_id")
            or "-"
        )
        state = target_filter.get("selected_target_connectivity_state") or "-"
        selected_id = target_filter.get("target_id") or target_filter.get("selected_target_id") or ""
        if selected_id and label != selected_id:
            lines.append(f"Current target: {label} ({selected_id})  state {state}")
        else:
            lines.append(f"Current target: {label}  state {state}")
    if active_profile:
        lines.append(
            "Profile: "
            + str(active_profile.get("name") or "-")
            + "  "
            + str(active_profile.get("arch") or active_profile.get("uname_m") or "-")
            + "  operator "
            + str(active_profile.get("operator_host") or "-")
        )

    attention = []
    warnings = len(snap.get("warnings") or [])
    if warnings:
        attention.append(f"{warnings} warnings")
    if _count_value(pending_work):
        attention.append(f"{pending_work} pending work")
    elif _count_value(pending_targets):
        attention.append(f"{pending_targets} targets with pending work")
    if _count_value(poll_overdue):
        attention.append(f"{poll_overdue} poll overdue")
    event_count = summary.get("event_count", 0)
    if attention:
        lines.append("Attention: " + "  |  ".join(attention))
    lines.append(f"Events: {event_count}")
    lines.append(line_banner_hint(snap))
    return "\n".join(lines)


def _count_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def line_banner_hint(snap):
    summary = snap.get("summary") or {}
    warnings = snap.get("warnings") or []
    target_filter = snap.get("target_filter") or {}
    hints = ["?", "help"]

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
        hints.append(f"status ({len(warnings)} warning{'s' if len(warnings) != 1 else ''})")
    if target_filter.get("active"):
        if pending_work:
            hints.append(f"check-ins ({pending_work} pending)")
        else:
            hints.append("check-ins")
        hints.extend(["queue uname -a", "use listener probe", "retrieve queue /etc/hosts", "clear target"])
    elif target_count:
        hints.append(f"targets ({target_count})")
        hints.extend(["use N", "search listener"])
    else:
        hints.append("use listener probe")
    if pending_work or poll_overdue:
        if pending_work and poll_overdue:
            hints.append(f"queue ({pending_work} pending, {poll_overdue} overdue)")
        elif pending_work:
            hints.append(f"queue ({pending_work} pending)")
        else:
            hints.append(f"queue ({poll_overdue} overdue)")
    if staged_count:
        hints.append(f"files ({staged_count})")
    if session_count:
        hints.append(f"sessions ({session_count})")
    if route_count:
        hints.append(f"routes ({route_count})")
    if not listening:
        hints.append("listeners")
    deduped = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return "  next: " + ", ".join(deduped[:12])


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
        print(f"  current target: {label} ({state})")
    for w in warnings[:3]:
        svc = f" {w.get('service')}" if w.get("service") else ""
        msg = w.get("message") or ""
        hint = f"  -> {w.get('suggested_action')}" if w.get("suggested_action") else ""
        print(f"  [!]{svc}: {msg}{hint}")
    if len(warnings) > 3:
        print(f"  ... {len(warnings) - 3} more warning(s) — run: status")
    print("")
    print(line_banner_hint(snap))


def _line_workspace_seen_text(iso):
    if iso and len(iso) >= 16 and "T" in iso:
        date, rest = iso.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return iso or "-"


def _line_workspace_summary_parts(summary, targets, sessions, warnings):
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
    return parts


def _print_line_workspace_selected_target(target_filter):
    selected_id = target_filter.get("target_id") if target_filter.get("active") else None
    if selected_id:
        label = target_filter.get("selected_target_label") or selected_id
        state = target_filter.get("selected_target_connectivity_state") or "-"
        print(f"  current target: {label} ({state})")
    return selected_id


def _print_line_workspace_targets(targets, selected_id):
    if targets:
        print("")
        cols = [
            ("Target", lambda r: ("* " if str(r.get("target_id") or "") == (selected_id or "") else "  ")
                       + (r.get("label") or r.get("target_id") or "-")),
            ("State", lambda r: r.get("connectivity_state") or "-"),
            ("Pending", lambda r: str(r.get("mailbox_pending_work_count") or 0)),
            ("Seen", lambda r: _line_workspace_seen_text(r.get("last_seen") or r.get("last_seen_at"))),
        ]
        shown = targets[:6]
        console_table(
            f"Targets  ({len(targets)} total)",
            shown, cols,
        )
        if len(targets) > 6:
            print(f"  ... {len(targets) - 6} more — use targets")


def _print_line_workspace_warnings(warnings):
    for warning in warnings[:3]:
        svc = f" {warning.get('service')}" if warning.get("service") else ""
        print(f"  [!]{svc}: {warning.get('message', '')}")


def _print_line_workspace_empty_help(summary, targets, sessions, staged, routes, warnings):
    if (
        not targets
        and not sessions
        and not staged
        and not routes
        and not warnings
        and int(summary.get("listening_count", 0) or 0) == 0
    ):
        print("")
        print("  No targets, sessions, staged files, routes, or warnings yet.")
        print("  Start here:")
        print("    use listener probe  open the probe menu")
        print("    in probe menu     use start, results, and config")
        print("    after profile setup: listener serve start default  stage a release artifact and start file-service")
        print("    workflow ?       see the full probe, profile, serve, and staged-files flow")


def print_line_workspace_snapshot(snap):
    summary = snap.get("summary") or {}
    target_filter = snap.get("target_filter") or {}
    targets = snap.get("targets") or []
    sessions = snap.get("sessions") or []
    warnings = snap.get("warnings") or []
    staged = summary.get("staged_count", 0)
    routes = summary.get("bridge_profile_count", 0)
    active_profile = snap.get("active_profile") or {}

    parts = _line_workspace_summary_parts(summary, targets, sessions, warnings)
    print("Workspace  " + "  |  ".join(parts))
    print("  Main overview. `workspace` leaves menus and returns to grit[all]> without deleting saved state.")
    selected_id = _print_line_workspace_selected_target(target_filter)
    if active_profile:
        print(
            "  profile: "
            f"{active_profile.get('name') or '-'}  "
            f"{active_profile.get('arch') or active_profile.get('uname_m') or '-'}  "
            f"operator {active_profile.get('operator_host') or '-'}"
        )
    _print_line_workspace_targets(targets, selected_id)
    _print_line_workspace_warnings(warnings)
    _print_line_workspace_empty_help(summary, targets, sessions, staged, routes, warnings)
    print("")
    print("Commands:")
    print("  next         suggest next steps for where you are")
    print("  search listener  find targets, listeners, sessions, files, modules, jobs")
    print("  targets      show target devices")
    print("  listeners    configure operator listeners")
    print("  files        show staged files and commands to run on targets")
    print("  sessions     inspect captured sessions")
    print("  routes       configure bridge routes")
    print("  ?            show help for where you are")


def _print_line_action_info(action):
    action_kind = action.get("kind", "")
    action_id = action.get("id", "")
    action_name = f"{action_kind}:{action_id}" if action_kind else action_id
    label = action.get("label", "") or action_name or "-"
    readiness = action.get("operator_action_reason", "") or "-"
    if readiness == "run-now":
        readiness = "ready to run"
    workflow = str(action.get("workflow", "") or "-").replace("-", " ")
    print(f"Module: {label}")
    print(f"  select: use module {label}")
    print(f"  status: {action.get('operator_action_state', '') or '-'}")
    print(f"  run check: {readiness}")
    print(f"  type: {action.get('category', '') or '-'}")
    print(f"  area: {workflow}")
    print(f"  confirmation needed: {'yes' if action.get('requires_confirmation') else 'no'}")
    print(f"  can run in background: {'yes' if action.get('background_supported') else 'no'}")
    commands = ["check", "preview", "run"]
    if action.get("requires_confirmation"):
        commands.append("run confirm")
    print("  commands: " + ", ".join(commands))
    if action.get("background_supported"):
        print("  background command: run job")
    print("  next: options, check, run, back")


def _print_line_listener_info(module, service_record, probe_delivery_printer):
    service = line_listener_module_name(module)
    rec = service_record(service)
    actual = rec.get("actual") or "-" if rec else "-"
    bind = _line_listener_bind_text(rec) if rec else "-"
    pid = rec.get("pid") or "-" if rec else "-"
    print(f"  {service}  —  {actual}  |  {bind}  |  pid {pid}")
    if service in {"probe", "probe-tftp", "probe-ftp", "probe-dns"}:
        if probe_delivery_printer:
            probe_delivery_printer()
    else:
        print("    " + ", ".join(line_service_context_commands(rec)))


def _print_line_route_info(module, route_record):
    route_name = module.split("/", 1)[1]
    rec = route_record(route_name)
    print(f"Route: {route_name}")
    if rec:
        print(f"  status: {rec.get('current_state', '') or '-'}")
        print(f"  active: {'yes' if rec.get('active') else 'no'}")
        print(f"  listen: {rec.get('listen_host', '')}:{rec.get('listen_port', '')}")
        print(f"  destination: {rec.get('dest_host', '')}:{rec.get('dest_port', '')}")
        print(f"  path: {rec.get('route_path', '') or '-'}")
        print(f"  hops: {rec.get('hop_count', 0)}")
        print(f"  multi-hop: {'yes' if rec.get('multi_hop') else 'no'}")
        print(f"  target: {rec.get('target_id', '') or '-'}")
    if rec and rec.get("active"):
        print(f"  commands: route {route_name}, route stop {route_name}")
    else:
        print(f"  commands: route {route_name}, route start {route_name}")
    print(f"  delete: route delete {route_name}, route delete {route_name} confirm")
    print("  next: " + ", ".join(line_route_context_commands(rec)))


def _print_line_session_info(module, session_record):
    session_id = module.split("/", 1)[1]
    rec = session_record(session_id)
    print(f"Session: {session_id}")
    if rec:
        path = str(rec.get("path") or "")
        print(f"  service: {rec.get('service', '') or '-'}")
        print(f"  state: {rec.get('state', '') or '-'}")
        print(f"  exit reason: {rec.get('exit_reason', '') or '-'}")
        print(f"  updated: {rec.get('updated_at', '') or '-'}")
        print(f"  path: {path}")
        if rec.get("session_log"):
            print(f"  session log: {rec.get('session_log', '')}")
        if rec.get("event_log"):
            print(f"  event log: {rec.get('event_log', '')}")
    print("  next: options, interact, sessions verbose, view ./README.md, back")


def _print_line_job_info(module, job_record):
    job_id = module.split("/", 1)[1]
    rec = job_record(job_id)
    print(f"Job: {job_id}")
    if rec:
        print(f"  module: {rec.get('action_id', '') or '-'}")
        print(f"  state: {rec.get('effective_state', '') or rec.get('state', '') or '-'}")
        print(f"  pid: {rec.get('pid', '') or '-'}")
        print(f"  managed: {'yes' if rec.get('pid_managed') else 'no'}")
        print(f"  cancel supported: {'yes' if rec.get('cancel_supported') else 'no'}")
        if rec.get("log_path"):
            print(f"  log: {rec.get('log_path', '')}")
        if rec.get("last_output_tail"):
            print("  last output:")
            for line in rec.get("last_output_tail") or []:
                print(f"    {line}")
    if rec and rec.get("cancel_supported"):
        print("  next: options, cancel, jobs, jobs verbose, back")
    else:
        print("  next: options, jobs, jobs verbose, back")


def _print_line_selected_agent_info(snap):
    target_filter = (snap or {}).get("target_filter") or {}
    if target_filter.get("active"):
        print(target_filter_brief_text(target_filter, prefix="  current target:"))
        for line in target_filter_evidence_lines(target_filter):
            print(f"    {line}")
    else:
        print("  target scope: all targets")


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

    action = selected_action()
    print("Console location:")
    module = str(module or "root")
    print(f"  location: {line_display_location(prompt_text, module)}")
    if action and module.startswith("action/"):
        print(f"  area: module {action.get('label', '') or action.get('id', '')}")
    else:
        print(f"  area: {line_display_area(module)}")
    if action:
        _print_line_action_info(action)
    elif line_listener_module_name(module):
        _print_line_listener_info(module, service_record, probe_delivery_printer)
    elif module.startswith("route/"):
        _print_line_route_info(module, route_record)
    elif module.startswith("session/"):
        _print_line_session_info(module, session_record)
    elif module.startswith("job/"):
        _print_line_job_info(module, job_record)
    else:
        print("Current area: workspace")
        print("  start with: targets, listeners, routes, sessions, modules, jobs, or run ? for help")
    _print_line_selected_agent_info(snap)


def print_current_line_info(
    cfg, snap, *,
    selected_action=None, service_record=None, route_record=None,
    session_record=None, job_record=None, probe_delivery_printer=None,
    bridge_command_builder=None, view_command_builder=None,
    cancel_job_command_builder=None,
):
    return print_line_info(
        snap,
        module=str((cfg or {}).get("_line_console_module") or "root"),
        prompt_text=line_repl_prompt_for_config(cfg),
        selected_action=selected_action,
        service_record=service_record,
        route_record=route_record,
        session_record=session_record,
        job_record=job_record,
        probe_delivery_printer=probe_delivery_printer,
        bridge_command_builder=bridge_command_builder,
        view_command_builder=view_command_builder,
        cancel_job_command_builder=cancel_job_command_builder,
    )


def print_line_next(
    cfg, snap, module="", target_id="", prompt_text="",
    selected_action=None, route_record=None, job_record=None
):
    module = str(module or "").strip()
    target_id = str(target_id or "").strip()
    selected_action = selected_action or (lambda: {})
    route_record = route_record or (lambda _route_name: {})
    job_record = job_record or (lambda _job_id: {})
    print("Next steps:")
    print(f"  location: {line_display_location(prompt_text, module)}")
    context_specific = False
    if module.startswith("action/"):
        action = selected_action()
        if action:
            context_specific = True
            print(f"  current module: {action.get('kind', '')}:{action.get('id', '')}")
            here = ["options", "check", "preview", "run"]
            if action.get("requires_confirmation"):
                here.append("run confirm")
            here.append("background")
            print("  in this prompt: " + ", ".join(here))
            if action.get("background_supported"):
                print("  background job: run job")
            print("  also available: show modules, modules verbose, use module Inspect bridge status, use module N")
            print("  help: modules ?, jobs ?")
        else:
            print("  current module is stale; commands: show modules, search listener, back")
    elif line_listener_module_name(module):
        context_specific = True
        service = line_listener_module_name(module)
        print(f"  current listener: {service}")
        print("  in this prompt: options, start, stop, show start, show stop, copy start, copy stop, back")
        print(f"  also available: listener {service}, start {service}, stop {service}, listeners verbose")
        print("  help: listeners ?")
    elif module.startswith("route/"):
        context_specific = True
        route_name = module.split("/", 1)[1]
        print(f"  current route: {route_name}")
        route_rec = route_record(route_name) if route_record else {}
        print("  in this prompt: " + ", ".join(line_route_context_commands(route_rec)))
        print(f"  also available: route {route_name}, route start {route_name}, route stop {route_name}, route delete {route_name} confirm, routes verbose")
        print("  help: routes ?")
    elif module.startswith("session/"):
        context_specific = True
        session_id = module.split("/", 1)[1]
        print(f"  current session: {session_id}")
        print("  in this prompt: info, options, interact, back")
        print(f"  also available: sessions list, sessions verbose, sessions interact {session_id}, view ./README.md")
        print("  help: sessions ?")
    elif module.startswith("job/"):
        context_specific = True
        job_id = module.split("/", 1)[1]
        rec = job_record(job_id)
        print(f"  current job: {job_id}")
        if rec:
            print(f"  module: {rec.get('action_id', '') or '-'}")
            print(f"  state: {rec.get('effective_state', '') or rec.get('state', '') or '-'}")
        if rec.get("cancel_supported"):
            print("  in this prompt: info, options, cancel, back")
            print(f"  also available: jobs, jobs info {job_id}, jobs cancel {job_id}")
        else:
            print("  in this prompt: info, options, back")
            print(f"  also available: jobs, jobs info {job_id}")
        print("  help: jobs ?")
    elif module == "listeners":
        context_specific = True
        print("  showing: listeners list")
        print("  commands: listeners, listener probe, listener 1, start probe, start 1, stop probe, stop 1")
        print("  open probe menu: use listener probe")
        print("  discover target: listener probe start")
        print("  review probe data: listener probe results")
        print("  update active profile: listener probe config")
        print("  help: listeners ?")
    elif module == "routes":
        context_specific = True
        print("  showing: routes list")
        print("  commands: routes verbose, route NAME, route N, route add ssh-home 2222 127.0.0.1 22")
        print("  multi-hop: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222")
        print("  help: routes ?")
    elif module == "sessions":
        context_specific = True
        print("  showing: sessions list")
        print("  commands: sessions list, sessions verbose, session 1, use session 1")
        print("  cleanup: sessions clear, sessions clear confirm, sessions clear all confirm")
        print("  help: sessions ?")
    elif module == "jobs":
        context_specific = True
        print("  showing: jobs list")
        print("  commands: jobs, job 1, jobs info 1, use job 1")
        print("  cancel a cancellable job: jobs cancel 1")
        print("  background module example: modules operator, use module Build current target and stage a small release, run job")
        print("  help: jobs ?, modules ?")
    elif module == "modules":
        context_specific = True
        print("  showing: modules list")
        print("  commands: modules, modules service, modules verbose service, use module Inspect bridge status, use module N")
        print("  choose a module: use N, then info, options, check, preview, run, run confirm, background")
        print("  help: modules ?, jobs ?")
    elif module == "profiles":
        context_specific = True
        print("  showing: profiles")
        profiles = profile_records(cfg)
        if profiles:
            active = active_profile(cfg)
            example = str((active or {}).get("name") or (profiles[0] or {}).get("name") or "lab-router")
            print(f"  commands: profiles, profile, profile use {example}, profile use 1, profile create lab-router, profile set operator-host 192.168.8.241")
            print("  open probe menu: use listener probe")
            print("  discover target: listener probe start")
            print("  review probe data: listener probe results")
            print("  update active profile: listener probe config; or type profile from probe 1")
            print("  deployment: listener serve start default, listener serve ssh start")
        else:
            print("  commands: profiles, profile, profile create lab-router")
            print_probe_menu_steps()
            print("  deployment: configure or create a profile first")
        print("  help: profiles ?, workflow ?")
    elif module == "files":
        context_specific = True
        print("  showing: files")
        print("  commands: files, stage ./grit sample-file, deliver sample-file, deliver start sample-file, unstage sample-file")
        print("  target-to-operator: retrieve /etc/hosts")
        print("  artifact and release: artifact, artifact info sample-file, release, release stage by_device:gl-mt3000")
        print("  help: files ?, artifact ?, release ?")
    elif module == "artifact":
        context_specific = True
        print("  showing: artifact files")
        print("  commands: artifact, artifact info grit, artifact info 1, artifact info ./grit, artifact show grit")
        print("  stamp: artifact stamp grit transport builtin")
        print("  deliver command: files, deliver grit")
        print("  help: artifact ?, files ?")
    elif module == "release":
        context_specific = True
        print("  showing: release artifacts")
        print("  commands: release, release stage by_device:gl-mt3000, release stage start by_device:gl-mt3000")
        print("  active profile shortcut: release stage ssh start")
        print("  active profile: profiles, profile")
        print("  open probe menu: use listener probe")
        print("  update active profile: listener probe config")
        print("  after staging: files, deliver grit")
        print("  help: release ?, workflow ?")
    elif module == "survey":
        context_specific = True
        print("  showing: survey")
        print("  commands: survey, survey results, survey config PATH, survey preset PATH name NAME")
        print("  target-to-operator: deploy griTTYkit, then run grit survey retrieve on the target")
        print("  outputs: survey config write-config FILE, survey preset name NAME write-local")
        print("  help: survey ?, workflow ?")
    elif module == "build":
        context_specific = True
        print("  showing: build config")
        print("  commands: build, build verbose, build set GRIT_RUNTIME_ROOT ./.grit, build set 16 ssh, build unset GRIT_RUNTIME_ROOT, build unset 16")
        print("  here: options, set GRIT_RUNTIME_ROOT ./.grit, unset GRIT_RUNTIME_ROOT")
        print("  from anywhere: build set GRIT_RUNTIME_ROOT ./.grit, build unset GRIT_RUNTIME_ROOT")
        print("  help: build ?")
    elif module == "events":
        context_specific = True
        print("  showing: events")
        print("  commands: events, events n 50, events since 2h")
        print("  filters: events service=NAME, events level=warning, events status=TEXT")
        print("  detail filters: file=NAME, command=ID, job=ID, module=ID")
        print("  raw log: options, then view ./README.md")
        print("  help: events ?")
    elif module == "commands":
        context_specific = True
        print("  showing: target commands")
        print("  list: commands")
        print("  copy command: copy 1, commands copy 1")
        print("  return: back")
        print("  command sources: files, listener probe, listeners, survey")
        print("  help: commands ?")
    elif module == "console":
        context_specific = True
        print("  showing: console reference")
        print("  commands: history 50, resource ./commands.gritrc, makerc ./last-session.gritrc, complete listener")
        print("  works from any prompt; do not prefix these commands with console")
        print("  replay: !!, !1, repeat 1")
        print("  navigation: back")
        print("  return to root: main  (aliases: home/root)")
        print("  quit from root: quit  (alias: exit)")
        print("  help: console ?")
    elif module == "workflow":
        context_specific = True
        print("  showing: workflow guide")
        print_probe_menu_steps()
        print("  profile: profiles, profile")
        print("  after profile setup: listener serve start default, listener serve ssh start")
        print("  after staging: files, deliver sample-file")
        print("  help: workflow ?")
    elif module == "aliases":
        context_specific = True
        print("  showing: preferred forms and legacy aliases")
        print("  preferred forms: targets, listeners, routes, files, modules")
        print("  legacy aliases remain accepted for older command files")
        print("  selection: use target lab-router, use listener probe, use route ssh-home, use module Inspect bridge status")
        print("  help: aliases ?")
    elif module == "search":
        context_specific = True
        print("  showing: search results")
        print("  commands: search listener, use 1")
        print("  keep results: ?, options, next, complete listener")
        print("  numbered results stay active while using help/options/next")
        print("  replace results: targets, listeners, files, or search listener")
        print("  help: search ?")
    elif target_id:
        context_specific = True
        target_filter = snap.get("target_filter") or {}
        print(target_filter_brief_text(target_filter, prefix="  current target:"))
        print("  in this prompt: interact, queue uname -a, check-ins, show events, rename, note, alias")
        print("  target-to-operator retrieve: retrieve queue /etc/hosts")
        print("  staged-file command: stage start ./grit sample-file, deliver queue sample-file")
        print("  probe queue: listener probe queue")
        print("  also available: targets, clear target, files, listeners")
        print("  help: targets ?, queue ?, files ?")
    else:
        print("  target scope: all targets")
        print("  commands: workspace, targets, listeners, routes, sessions, modules, search listener")
        print_open_probe_menu_steps()
        print("  after profile setup: listener serve start default")
    sessions = snap.get("sessions") or []
    if not context_specific:
        if sessions:
            print("  sessions: sessions list, sessions verbose, sessions interact 1, use session 1")
        print("  help: workflow ?, listeners ?, files ?, use ?")
    append_event(cfg, "workbench", "workbench_console_next_shown", details={
        "module": module or "root",
        "target_id": target_id,
        "session_count": len(sessions),
    })


def print_current_line_next(
    cfg, snap, *,
    selected_action=None, route_record=None, job_record=None,
):
    module = str((cfg or {}).get("_line_console_module") or "").strip()
    target_id = configured_target_filter(cfg)
    return print_line_next(
        cfg,
        snap,
        module=module,
        target_id=target_id,
        prompt_text=line_repl_prompt_for_config(cfg),
        selected_action=selected_action,
        route_record=route_record,
        job_record=job_record,
    )
