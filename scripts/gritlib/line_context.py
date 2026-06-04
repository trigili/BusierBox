"""Line-console context helpers."""

from gritlib.event_log import append_event
from gritlib.target_records import configured_target_filter, set_workbench_target_filter


def parse_line_use_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    aliases = {
        "useagent": ("target", "use agent", "usage: useagent ID|LABEL|NUMBER|all"),
        "usehost": ("target", "use agent", "usage: useagent ID|LABEL|NUMBER|all"),
        "usetarget": ("target", "use agent", "usage: useagent ID|LABEL|NUMBER|all"),
        "uselistener": ("listener", "use listener", "usage: uselistener SERVICE"),
        "useservice": ("listener", "use listener", "usage: uselistener SERVICE"),
        "useroute": ("route", "use route", "usage: useroute NAME|NUMBER"),
        "usesession": ("session", "use session", "usage: usesession SESSION"),
        "usemodule": ("action", "use module", "usage: usemodule ACTION"),
        "useaction": ("action", "use module", "usage: usemodule ACTION"),
    }
    if cmd in aliases:
        kind, canonical, usage = aliases[cmd]
        selector = " ".join(args).strip()
        return {
            "kind": kind,
            "selector": selector,
            "usage": usage,
            "alias": cmd,
            "canonical": canonical,
        }
    if cmd != "use":
        return {}
    if len(args) == 1 and str(args[0]).isdigit():
        return {"kind": "number", "selector": str(args[0])}
    if not args:
        return {"kind": "", "selector": "", "usage": "usage: use KIND SELECTOR"}
    kind = str(args[0]).lower()
    selector = " ".join(args[1:]).strip()
    kind_aliases = {
        "target": ("target", "usage: use target ID|LABEL|NUMBER|all"),
        "agent": ("target", "usage: use agent ID|LABEL|NUMBER|all"),
        "host": ("target", "usage: use agent ID|LABEL|NUMBER|all"),
        "service": ("listener", "usage: use service SERVICE"),
        "listener": ("listener", "usage: use listener SERVICE"),
        "route": ("route", "usage: use route NAME|NUMBER"),
        "session": ("session", "usage: use session SESSION"),
        "job": ("job", "usage: use job ID|NUMBER"),
        "action": ("action", ""),
        "module": ("action", ""),
    }
    target_kind, usage = kind_aliases.get(kind, ("", "usage: use KIND SELECTOR"))
    return {
        "kind": target_kind,
        "selector": selector,
        "usage": usage,
    }


def clear_line_module_context(cfg, quiet=True):
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    if cfg.pop("_line_console_module", None):
        if quiet:
            return
        print("module context cleared")
    elif not quiet:
        print("module context already root")


def set_line_collection_context(cfg, module):
    module = str(module or "").strip()
    if not module:
        return
    cfg["_line_console_module"] = module
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)


def clear_line_console_context(cfg):
    had_module = bool(str(cfg.get("_line_console_module") or ""))
    had_target = bool(configured_target_filter(cfg))
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    cfg.pop("_line_console_module", None)
    cfg.pop("_target_id_filter", None)
    cfg.pop("_target_label_filter", None)
    set_workbench_target_filter(cfg, "all", targets=[])
    print("returned to main workspace")
    print(f"  cleared module: {'yes' if had_module else 'no'}")
    print(f"  cleared target: {'yes' if had_target else 'no'}")
    print("  next: workspace, agents, listeners, routes, sessions, show categories")
    append_event(cfg, "workbench", "workbench_console_main_selected", details={
        "cleared_module": had_module,
        "cleared_target": had_target,
    })


def line_module_parent(module):
    module = str(module or "").strip()
    if not module:
        return ""
    if "/" not in module:
        return ""
    parent = module.split("/", 1)[0]
    return {
        "action": "",
        "job": "jobs",
        "listener": "listeners",
        "service": "listeners",
        "route": "routes",
        "session": "sessions",
    }.get(parent, parent)


def back_line_module_context(cfg):
    module = str(cfg.get("_line_console_module") or "").strip()
    parent = line_module_parent(module)
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    if parent:
        cfg["_line_console_module"] = parent
        return parent
    if module:
        cfg.pop("_line_console_module", None)
        return ""
    if configured_target_filter(cfg):
        set_workbench_target_filter(cfg, "all", targets=[])
    return ""
