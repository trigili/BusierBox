"""Line-console context helpers."""

from dataclasses import dataclass

from gritlib.event_log import append_event
from gritlib.target_context import configured_target_filter
from gritlib.target_selection import set_workbench_target_filter


@dataclass(frozen=True)
class LineContextState:
    module: str = ""
    target_id: str = ""
    target_label: str = ""
    action_kind: str = ""
    action_id: str = ""

    @property
    def has_module(self):
        return bool(self.module)

    @property
    def has_target(self):
        return bool(self.target_id)

    @property
    def active(self):
        return self.has_module or self.has_target


@dataclass(frozen=True)
class LineContextTransition:
    action: str
    module: str = ""
    clear_module: bool = False
    clear_target: bool = False


def line_context_state(cfg):
    cfg = cfg or {}
    return LineContextState(
        module=str(cfg.get("_line_console_module") or "").strip(),
        target_id=str(cfg.get("_target_id_filter") or "").strip(),
        target_label=str(cfg.get("_target_label_filter") or "").strip(),
        action_kind=str(cfg.get("_line_console_action_kind") or "").strip(),
        action_id=str(cfg.get("_line_console_action_id") or "").strip(),
    )


def line_context_back_transition(state):
    state = state if isinstance(state, LineContextState) else LineContextState()
    parent = line_module_parent(state.module)
    if parent:
        return LineContextTransition("parent", module=parent, clear_module=True)
    if state.module:
        return LineContextTransition("module-root", clear_module=True)
    if state.target_id:
        return LineContextTransition("target-root", clear_target=True)
    return LineContextTransition("root")


def _usage_lines(*commands):
    return "usage:\n" + "\n".join(f"  {command}" for command in commands)


def _use_target_usage(command):
    return _usage_lines(
        f"{command} ID",
        f"{command} LABEL",
        f"{command} N",
        f"{command} all",
    )


def _generic_use_usage():
    return _usage_lines(
        "use target ID",
        "use listener SERVICE",
        "use route NAME",
        "use module MODULE",
        "use N",
    )


def parse_line_use_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    aliases = {
        "useagent": ("target", "use target", _use_target_usage("use target")),
        "usehost": ("target", "use target", _use_target_usage("use target")),
        "usetarget": ("target", "use target", _use_target_usage("use target")),
        "uselistener": ("listener", "use listener", _usage_lines("use listener SERVICE")),
        "useservice": ("listener", "use listener", _usage_lines("use listener SERVICE")),
        "useroute": ("route", "use route", _usage_lines("use route NAME", "use route N")),
        "usesession": ("session", "use session", _usage_lines("use session SESSION")),
        "usemodule": ("action", "use module", "usage:\n  use module MODULE"),
        "useaction": ("action", "use module", "usage:\n  use module MODULE"),
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
        return {
            "kind": "",
            "selector": "",
            "usage": _generic_use_usage(),
        }
    kind = str(args[0]).lower()
    selector = " ".join(args[1:]).strip()
    kind_aliases = {
        "target": ("target", _use_target_usage("use target")),
        "agent": ("target", _use_target_usage("use agent")),
        "host": ("target", _use_target_usage("use host")),
        "service": ("listener", "usage: use service SERVICE"),
        "listener": ("listener", "usage: use listener SERVICE"),
        "route": ("route", _usage_lines("use route NAME", "use route N")),
        "session": ("session", "usage:\n  use session SESSION"),
    "job": ("job", _usage_lines("use job job-1", "use job 1")),
        "action": ("action", "usage:\n  use module MODULE"),
        "module": ("action", ""),
    }
    target_kind, usage = kind_aliases.get(
        kind,
        ("", _generic_use_usage()),
    )
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
        print(use_cmd.get("usage") or _generic_use_usage())
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


def dispatch_line_interact_command(
    interact_cmd,
    *,
    target_func=None,
    session_func=None,
):
    try:
        if interact_cmd.get("kind") == "target" and target_func:
            return target_func(interact_cmd.get("selector", ""))
        if session_func:
            return session_func(interact_cmd.get("selector", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported interact command")


def parse_line_context_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = [str(item).lower() for item in (args or [])]
    if cmd == "clear" and args[:1] == ["target"]:
        return {"action": "clear-target"}
    if cmd == "back" and args[:1] and args[0] in {"all", "main", "root"}:
        return {"action": "root"}
    if cmd in {"b", "back"}:
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
    cfg.pop("_line_console_module", None)
    cfg.pop("_line_console_return_module", None)


def set_line_collection_context(cfg, module, *, preserve_return=False):
    module = str(module or "").strip()
    if not module:
        return
    module = {
        "service": "listeners",
        "services": "listeners",
    }.get(module, module)
    current_module = str(cfg.get("_line_console_module") or "").strip()
    if preserve_return and current_module and current_module != module:
        cfg["_line_console_return_module"] = current_module
    elif not preserve_return:
        cfg.pop("_line_console_return_module", None)
    cfg["_line_console_module"] = module
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    cfg.pop("_line_console_action_label", None)


def set_line_action_context(cfg, kind, action_id):
    action_id = str(action_id or "").strip()
    if not action_id:
        return
    cfg["_line_console_action_kind"] = str(kind or "")
    cfg["_line_console_action_id"] = action_id
    cfg.pop("_line_console_action_label", None)
    cfg["_line_console_module"] = f"action/{action_id}"


def clear_line_console_context(cfg, quiet=False):
    state = line_context_state(cfg)
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    cfg.pop("_line_console_action_label", None)
    cfg.pop("_line_console_module", None)
    cfg.pop("_line_console_return_module", None)
    cfg.pop("_target_id_filter", None)
    cfg.pop("_target_label_filter", None)
    set_workbench_target_filter(cfg, "all", targets=[])
    if not quiet:
        print("returned to grit[all]>")
        print("  next: targets, listeners, routes, sessions, modules")
    append_event(cfg, "workbench", "workbench_console_main_selected", details={
        "cleared_module": state.has_module,
        "cleared_target": state.has_target,
    })


def line_module_parent(module):
    module = str(module or "").strip()
    if not module:
        return ""
    if "/" not in module:
        return ""
    parent = module.split("/", 1)[0]
    return {
        "action": "modules",
        "job": "jobs",
        "listener": "listeners",
        "service": "listeners",
        "route": "routes",
        "session": "sessions",
    }.get(parent, parent)


def back_line_module_context(cfg):
    state = line_context_state(cfg)
    return_module = str(cfg.pop("_line_console_return_module", "") or "").strip()
    if state.module == "commands" and return_module:
        cfg["_line_console_module"] = return_module
        print(f"returned to {return_module} menu")
        return return_module
    transition = line_context_back_transition(state)
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    if transition.module:
        cfg["_line_console_module"] = transition.module
        print(f"returned to {transition.module} menu")
        return transition.module
    if transition.clear_module:
        cfg.pop("_line_console_module", None)
        print("returned to grit[all]>")
        return ""
    if transition.clear_target:
        set_workbench_target_filter(cfg, "all", targets=[])
        print("target filter cleared")
        return ""
    print("already at grit[all]>")
    return ""
