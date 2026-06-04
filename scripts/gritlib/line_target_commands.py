"""Line-console generated target command helpers."""

from gritlib.command_copy import command_copy_path
from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.target_commands import (
    copy_generated_command,
    generated_target_command_records,
    target_command_route_text,
)


def print_line_generated_commands(cfg):
    records = generated_target_command_records(cfg)

    def _cmd(rec):
        cmd = str(rec.get("command") or "")
        return cmd[:90] + "…" if len(cmd) > 90 else cmd

    def _detail(rec):
        cmd = str(rec.get("command") or "")
        details = []
        if len(cmd) > 90:
            details.append(("full", cmd))
        details.append(("copy", f"copy {rec.get('ordinal', '')}"))
        return details

    cols = [
        ("Service", lambda r: r.get("service") or "-"),
        ("Transport", lambda r: target_command_route_text(r) or "-"),
        ("Command", _cmd),
    ]
    console_table(
        f"Generated commands  ({len(records)} total)" if records else "Generated commands  (none)",
        records, cols, detail_fn=_detail,
        footer=f"copy N  |  copy file: {command_copy_path(cfg)}  |  commands ? for help",
    )
    search_records = []
    for rec in records:
        search_records.append({
            "kind": "target-command",
            "label": f"{rec.get('ordinal', '')}: {rec.get('service', '') or 'target'}",
            "rec": rec,
            "command": str(rec.get("command") or ""),
            "use_hint": f"copy {rec.get('ordinal', '')}",
        })
    cfg["_line_console_search_results"] = search_records
    append_event(cfg, "workbench", "workbench_generated_commands_listed", details={
        "command_count": len(records),
        "copy_supported_count": len([rec for rec in records if rec.get("copy_supported")]),
        "command_copy_file": str(command_copy_path(cfg)),
    })


def copy_line_generated_command(cfg, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage: copy N")
    rec = copy_generated_command(cfg, text)
    print(f"copied command to {rec['path']} clipboard={'yes' if rec['clipboard'] else 'no'}")
    print(f"command={rec.get('text', '')}")
    return rec


def parse_line_copy_command(args):
    args = list(args or [])
    subcmd = str(args[0] if args else "").strip().lower()
    if subcmd in {"start", "stop"}:
        return {"action": "service", "subcmd": subcmd}
    return {"action": "generated", "selector": " ".join(args).strip()}


def copy_line_service_command(cfg, subcmd, copy_func, start_command=None, stop_command=None):
    subcmd = str(subcmd or "").strip().lower()
    if subcmd not in {"start", "stop"}:
        raise ValueError("usage: copy start|stop|N")
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
    if not command:
        print(f"no {subcmd} command available - select a listener first")
        return {}
    rec = copy_func(command, label=f"{subcmd} command")
    print(f"copied {subcmd} command  clipboard={'yes' if rec.get('clipboard') else 'no'}")
    print(f"  {command}")
    return rec


def run_line_generated_command(cfg, args):
    subcmd = str(args[0] if args else "").lower()
    if not subcmd or subcmd in {"list", "show"}:
        print_line_generated_commands(cfg)
        return
    if subcmd == "copy":
        copy_line_generated_command(cfg, " ".join(args[1:]).strip())
        return
    raise ValueError("usage: commands [list|copy N]")
