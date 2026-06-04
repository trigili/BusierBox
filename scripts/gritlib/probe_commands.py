"""Probe target command rendering helpers for grit-console."""

import base64

from .bridge_routes import attach_target_route_fields, target_route_context
from .operator_network import operator_advertised_host
from .shell_utils import shquote


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
        "After it runs, use: probe results",
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
        "After it runs, use: probe results",
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
        "    paste: probe paste",
        "",
        "  Current listeners: probe-http, probe-tftp, probe-ftp, probe-dns",
        "  DNS note: nslookup usually needs DNS exposed on port 53; dig can use custom ports.",
        "  If HTTP is blocked but nc works, use the nc command above against the same listener.",
        "  If the target only has a serial/admin shell, use: probe paste",
        "",
        "  probe results  — after running any of the above",
    ])


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
            raise ValueError("usage: probe [start|queue|--start|--queue]")
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
            raise ValueError("usage: probe delivery")
        return {"action": "delivery"}
    if subcmd in {"paste", "serial", "heredoc"}:
        base64_mode = False
        for item in rest:
            lower = str(item).lower()
            if lower in {"--base64", "base64", "-b"}:
                base64_mode = True
            else:
                raise ValueError("usage: probe paste [--base64]")
        return {"action": "paste", "base64": base64_mode}
    if subcmd in {"script", "raw"}:
        if rest:
            raise ValueError("usage: probe script")
        return {"action": "script"}
    if subcmd in {"help", "-h", "--help"}:
        return {"action": "help"}
    queue_probe, start_probe = parse_line_probe_args(args)
    return {
        "action": "start",
        "set_context": not subcmd,
        "queue": queue_probe,
        "start_service": start_probe,
    }


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
            return help_func("probe")
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

    from gritlib.config_utils import DEFAULT_CONFIG

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
    raise ValueError("usage: survey [results|config|preset]  —  see: survey ?")


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


def probe_workflow_action_records(cfg, service_row=None, targets=None):
    from gritlib.config_utils import DEFAULT_CONFIG
    from gritlib.workflow_actions import (
        probe_listener_action_states,
        probe_workflow_action_record,
        probe_workflow_run_command,
        workflow_fleet_metrics,
    )

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
    records = []

    def add(action_id, category, label, command, action_state, action_reason,
            available=True, requires_confirmation=False, can_run_from_curses_enter=False,
            curses_enter_action=""):
        records.append(attach_target_route_fields(probe_workflow_action_record(
            action_id,
            category,
            label,
            command,
            probe_workflow_run_command(base, bridge_arg, action_id),
            service_row,
            target_command,
            cfg.get("GRIT_PROBE_NAME", "probe.sh"),
            cfg.get("listen_host") or service_row.get("bind_address") or "",
            port,
            fleet_metrics,
            action_state,
            action_reason,
            available=available,
            requires_confirmation=requires_confirmation,
            can_run_from_curses_enter=can_run_from_curses_enter,
            curses_enter_action=curses_enter_action,
        ), route))

    add(
        "inspect-probe",
        "inspect",
        "Inspect probe route and target command",
        base + " --status",
        "ready",
        "run-now",
    )
    add(
        "show-target-command",
        "survey",
        "Show target-side probe command",
        base + " --status",
        "ready",
        "show-command",
        can_run_from_curses_enter=True,
        curses_enter_action="show-target-command",
    )
    add(
        "start-probe",
        "survey",
        "Start probe listener",
        start_command,
        lifecycle_states["start_state"],
        lifecycle_states["start_reason"],
        can_run_from_curses_enter=lifecycle_states["start_enter"],
        curses_enter_action="start-probe" if lifecycle_states["start_enter"] else "stop-probe",
    )
    add(
        "stop-probe",
        "survey",
        "Stop probe listener",
        stop_command,
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
