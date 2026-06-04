"""Line-console context helpers."""

from gritlib.event_log import append_event
from gritlib.target_records import configured_target_filter, set_workbench_target_filter


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
    print(f"  cleared_module={'yes' if had_module else 'no'} cleared_target={'yes' if had_target else 'no'}")
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
    cfg.pop("_line_console_module", None)
    return ""
