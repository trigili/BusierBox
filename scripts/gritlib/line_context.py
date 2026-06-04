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


def dispatch_line_use_command(
    use_cmd,
    *,
    alias_recorder=None,
    number_func=None,
    target_func=None,
    listener_func=None,
    route_func=None,
    session_func=None,
    job_func=None,
    action_func=None,
    after_number_func=None,
):
    selector = (use_cmd or {}).get("selector", "")
    if (use_cmd or {}).get("usage") and not selector:
        print(use_cmd["usage"])
        return None
    try:
        if use_cmd.get("alias") and alias_recorder:
            alias_recorder(use_cmd["alias"], use_cmd["canonical"])
        kind = use_cmd.get("kind")
        if kind == "number" and number_func:
            result = number_func(selector)
            if after_number_func:
                after_number_func()
            return result
        if kind == "target" and target_func:
            return target_func(selector)
        if kind == "listener" and listener_func:
            return listener_func(selector)
        if kind == "route" and route_func:
            return route_func(selector)
        if kind == "session" and session_func:
            return session_func(selector)
        if kind == "job" and job_func:
            return job_func(selector)
        if kind == "action" and action_func:
            return action_func(selector)
        print(use_cmd.get("usage") or "usage: use KIND SELECTOR")
        return None
    except ValueError as exc:
        print(exc)
        return None


def parse_line_interact_command(cmd, args=None, target_selected=False, module=""):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "interact":
            return {}
    args = list(args or [])
    first = str(args[0]).lower() if args else ""
    if first in {"agent", "target", "host"}:
        return {"kind": "target", "selector": " ".join(args[1:]).strip()}
    if not args and target_selected and not str(module or "").startswith("session/"):
        return {"kind": "target", "selector": ""}
    return {"kind": "session", "selector": " ".join(args).strip()}


def parse_line_context_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = [str(item).lower() for item in (args or [])]
    if cmd == "clear" and args[:1] == ["target"]:
        return {"action": "clear-target"}
    if cmd == "back" and args[:1] and args[0] in {"all", "main", "root"}:
        return {"action": "root"}
    if cmd in {"b", "back", "background", "bg", "unset"}:
        return {"action": "back"}
    return {}


def dispatch_line_context_command(
    context_cmd,
    *,
    clear_target_func=None,
    root_func=None,
    back_func=None,
):
    action = (context_cmd or {}).get("action")
    try:
        if action == "clear-target" and clear_target_func:
            return clear_target_func()
        if action == "root" and root_func:
            return root_func()
        if action == "back" and back_func:
            return back_func()
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported context command")


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
