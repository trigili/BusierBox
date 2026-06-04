"""Line REPL target callback adapters."""

from gritlib.line_targets import (
    interact_line_target,
    print_line_targets,
    select_line_target,
)


def build_line_target_callbacks(cfg, *, workbench_snapshot_func, print_target_summary_func=None, quote):
    def print_targets():
        return print_line_targets(cfg, workbench_snapshot_func, quote=quote)

    def select_target(selector, targets=None):
        return select_line_target(
            cfg,
            selector,
            workbench_snapshot_func,
            targets=targets,
            quote=quote,
        )

    def interact_target(selector=""):
        return interact_line_target(
            cfg,
            selector,
            workbench_snapshot_func,
            quote=quote,
        )

    return {
        "print_line_targets": print_targets,
        "select_line_target": select_target,
        "interact_line_target": interact_target,
        "print_target_summary": print_target_summary_func,
    }
