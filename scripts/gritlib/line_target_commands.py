"""Line-console generated target command helpers."""

from gritlib.command_copy import command_copy_path
from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.line_search import set_line_search_results
from gritlib.service_status import service_status_rows
from gritlib.target_commands import (
    copy_generated_command,
    generated_target_command_records,
    generated_target_commands,
    target_command_route_text,
)


def _service_actual_state(cfg, name):
    try:
        row = {rec.get("name"): rec for rec in service_status_rows(cfg)}.get(name) or {}
    except OSError:
        return ""
    return str(row.get("actual") or "")


def _target_command_prerequisite(cfg, rec):
    service = str(rec.get("service") or "")
    if service == "rshell":
        return "listener serve ssh start stages a reverse SSH artifact from the active profile; then rerun commands"
    if service == "file-service" and _service_actual_state(cfg, "file-service") != "listening":
        return "start file-service and wait until it is listening"
    return ""


def print_line_generated_commands(cfg):
    records = generated_target_command_records(cfg)
    file_service_prerequisite = "start file-service and wait until it is listening"

    def _cmd(rec):
        cmd = str(rec.get("command") or "")
        return cmd[:90] + "…" if len(cmd) > 90 else cmd

    def _detail(rec):
        cmd = str(rec.get("command") or "")
        details = []
        if len(cmd) > 90:
            details.append(("full", cmd))
        details.append(("copy command", f"copy {rec.get('ordinal', '')}"))
        prerequisite = _target_command_prerequisite(cfg, rec)
        if prerequisite and prerequisite != file_service_prerequisite:
            details.append(("prerequisite", prerequisite))
        return details

    def _transport(rec):
        if str(rec.get("service") or "") == "rshell":
            return "artifact settings"
        route = target_command_route_text(rec)
        if route.startswith("route=direct endpoint="):
            return "operator listener  " + route.split("endpoint=", 1)[1]
        if route.startswith("route=direct"):
            return "operator listener"
        return route or "-"

    cols = [
        ("Service", lambda r: r.get("service") or "-"),
        ("Direction", lambda r: r.get("direction") or "-"),
        ("Connection", _transport),
        ("Command", _cmd),
    ]
    console_table(
        f"Target commands  ({len(records)} total)" if records else "Target commands  (none)",
        records, cols, detail_fn=_detail,
        footer="copy 1, commands copy 1, back, help: commands ?",
    )
    if records:
        print("  Run these rows on the target device; use `copy 1` to copy the first row.")
        print("  Direction guide: console `retrieve` sends target files to the operator; console `deliver` sends staged operator files to the target.")
        if any(_target_command_prerequisite(cfg, rec) == file_service_prerequisite for rec in records):
            print(f"  Before running file-service rows: {file_service_prerequisite}.")
        print("  Use `back` to return to the previous menu.")
    if any("OPERATOR_IP" in str(rec.get("command") or "") for rec in records):
        print("  OPERATOR_IP is a placeholder; run `ip` to choose an address or `ip host IP` to set it.")
    search_records = []
    for rec in records:
        search_records.append({
            "kind": "target-command",
            "label": f"{rec.get('ordinal', '')}: {rec.get('service', '') or 'target'}",
            "rec": rec,
            "command": str(rec.get("command") or ""),
            "use_hint": f"copy {rec.get('ordinal', '')}",
        })
    set_line_search_results(cfg, search_records)
    append_event(cfg, "workbench", "workbench_generated_commands_listed", details={
        "command_count": len(records),
        "copy_supported_count": len([rec for rec in records if rec.get("copy_supported")]),
        "command_copy_file": str(command_copy_path(cfg)),
    })


def copy_line_generated_command(cfg, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage:\n  copy N")
    rec = copy_generated_command(cfg, text)
    print(f"Copied command to {rec['path']}")
    print(f"  clipboard: {'yes' if rec['clipboard'] else 'no'}")
    print(f"  command: {rec.get('text', '')}")
    prerequisite = _target_command_prerequisite(cfg, rec)
    if prerequisite:
        label = "prerequisite" if str(rec.get("service") or "") == "rshell" else "before running"
        print(f"  {label}: {prerequisite}")
    return rec


def dispatch_legacy_copy_choice(choice, cfg, *, input_func):
    if str(choice or "").strip() != "c":
        return False
    commands = generated_target_commands(cfg)
    for idx, cmd in enumerate(commands, 1):
        print(f"{idx}: {cmd}")
    chosen_line = input_func("copy command N; blank skips> ")
    chosen = chosen_line.strip() if chosen_line is not None else ""
    if chosen:
        try:
            rec = copy_generated_command(cfg, chosen)
            print(f"Copied command to {rec['path']}")
            print(f"  clipboard: {'yes' if rec['clipboard'] else 'no'}")
            print(f"  command: {rec.get('text', '')}")
        except ValueError as exc:
            print(exc)
    return True


def parse_line_copy_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "copy":
            return {}
    args = list(args or [])
    subcmd = str(args[0] if args else "").strip().lower()
    if subcmd in {"start", "stop"}:
        return {"action": "service", "subcmd": subcmd}
    return {"action": "generated", "selector": " ".join(args).strip()}


def parse_line_service_show_command(cmd, args=None):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd != "show":
        return {}
    subcmd = str(args[0] if args else "").strip().lower()
    if subcmd in {"start", "stop"}:
        return {"action": "service", "subcmd": subcmd}
    return {}


def parse_line_generated_commands_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd not in {"commands", "target-commands"}:
        return {}
    return {"action": "commands", "args": list(args or [])}


def dispatch_line_generated_commands_command(commands_cmd, *, run_func=None):
    try:
        if run_func:
            return run_func((commands_cmd or {}).get("args") or [])
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported generated commands command")


def dispatch_line_copy_command(
    copy_cmd,
    *,
    service_copy_func=None,
    generated_copy_func=None,
):
    try:
        action = (copy_cmd or {}).get("action")
        if action == "service" and service_copy_func:
            return service_copy_func(copy_cmd.get("subcmd", ""))
        if action == "generated" and generated_copy_func:
            return generated_copy_func(copy_cmd.get("selector", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported copy command")


def _line_service_command_text(cfg, subcmd, start_command=None, stop_command=None):
    subcmd = str(subcmd or "").strip().lower()
    if subcmd not in {"start", "stop"}:
        raise ValueError("usage:\n  show start\n  show stop\n  copy start\n  copy stop")
    key = f"_service_{subcmd}_command"
    command = str(cfg.get(key) or "")
    if not command:
        module = str(cfg.get("_line_console_module") or "")
        if module.startswith(("listener/", "service/")):
            svc = module.split("/", 1)[1]
            if subcmd == "start" and start_command:
                command = start_command(svc)
            elif subcmd == "stop" and stop_command:
                command = stop_command(svc)
    return command


def show_line_service_command(cfg, subcmd, start_command=None, stop_command=None):
    command = _line_service_command_text(cfg, subcmd, start_command=start_command, stop_command=stop_command)
    if not command:
        print(f"no {subcmd} command available - select a listener first")
        return {}
    repl_command = "start" if subcmd == "start" else "stop"
    print(f"{subcmd} command:")
    print(f"  console command: {repl_command}")
    print("  terminal shell command:")
    print(f"    {command}")
    return {"command": command}


def copy_line_service_command(cfg, subcmd, copy_func, start_command=None, stop_command=None):
    subcmd = str(subcmd or "").strip().lower()
    command = _line_service_command_text(cfg, subcmd, start_command=start_command, stop_command=stop_command)
    if not command:
        print(f"no {subcmd} command available - select a listener first")
        return {}
    rec = copy_func(command, label=f"{subcmd} command")
    print(f"Copied {subcmd} command")
    print(f"  clipboard: {'yes' if rec.get('clipboard') else 'no'}")
    print(f"  command: {command}")
    return rec


def run_line_generated_command(cfg, args):
    subcmd = str(args[0] if args else "").lower()
    if not subcmd or subcmd in {"list", "show"}:
        print_line_generated_commands(cfg)
        return
    if subcmd == "copy":
        copy_line_generated_command(cfg, " ".join(args[1:]).strip())
        return
    raise ValueError("usage:\n  commands\n  commands copy N")
