"""Line-console context helpers."""

from gritlib.event_log import append_event
from gritlib.target_records import configured_target_filter, set_workbench_target_filter


def clear_line_module_context(cfg):
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    if cfg.pop("_line_console_module", None):
        print("module context cleared")
    else:
        print("module context already root")


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
