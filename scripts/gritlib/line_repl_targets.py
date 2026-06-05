"""Line REPL target callback adapters."""

from gritlib.line_targets import (
    interact_line_target,
    print_line_targets,
    select_line_target,
)
from gritlib.console_workbench import workbench_snapshot
from gritlib.shell_utils import shquote
from gritlib.target_commands import generated_target_command_records
from gritlib import target_records


def build_line_target_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    target_filter_func=None,
    target_context_func=None,
    target_command_records_func=None,
    print_target_summary_func=None,
    quote,
):
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

    def target_filter():
        return target_filter_func(cfg) if target_filter_func else ""

    def target_context():
        return target_context_func(cfg) if target_context_func else {}

    def target_command_records():
        return target_command_records_func(cfg) if target_command_records_func else []

    return {
        "print_line_targets": print_targets,
        "select_line_target": select_target,
        "interact_line_target": interact_target,
        "target_filter": target_filter,
        "target_context": target_context,
        "target_command_records": target_command_records,
        "print_target_summary": print_target_summary_func,
    }


def build_default_line_target_callbacks(cfg):
    return build_line_target_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        target_filter_func=target_records.configured_target_filter,
        target_context_func=target_records.selected_target_context,
        target_command_records_func=generated_target_command_records,
        print_target_summary_func=target_records.print_target_summary,
        quote=shquote,
    )
