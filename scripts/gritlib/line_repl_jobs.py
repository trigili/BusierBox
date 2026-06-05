"""Line REPL workbench job callback adapters."""

from gritlib.console_workbench import workbench_snapshot
from gritlib.shell_utils import shquote
from gritlib.workbench_jobs import (
    cancel_current_line_job,
    cancel_workbench_job_headless_command,
    current_line_job_record,
    print_current_line_jobs,
    select_current_line_job,
    start_line_job as workbench_jobs_start_line_job,
    start_workbench_job_headless_command,
    start_workbench_job_record,
)


def build_line_job_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    workbench_actions_func=None,
    action_callbacks,
    start_job_func,
    quote,
):
    select_action_func = action_callbacks["select_line_action"]
    selected_action_func = action_callbacks["selected_line_action"]
    if workbench_actions_func is None:
        workbench_actions_func = lambda _cfg: action_callbacks["workbench_actions"]()

    def snapshot():
        return workbench_snapshot_func(cfg)

    def line_job_record(selector):
        return current_line_job_record(snapshot, selector)

    def print_line_jobs(verbose=False):
        return print_current_line_jobs(
            cfg,
            snapshot,
            verbose=verbose,
            command_builder=lambda job_id: cancel_workbench_job_headless_command(cfg, job_id),
            quote=quote,
        )

    def select_line_job(selector):
        return select_current_line_job(cfg, snapshot, selector)

    def cancel_line_job(selector):
        return cancel_current_line_job(
            cfg,
            snapshot,
            lambda: workbench_actions_func(cfg),
            selector,
            command_builder=cancel_workbench_job_headless_command,
        )

    def start_job(action_selector=""):
        return workbench_jobs_start_line_job(
            cfg,
            action_selector,
            select_action_func=select_action_func,
            selected_action_func=selected_action_func,
            actions_func=lambda: workbench_actions_func(cfg),
            headless_command_func=start_workbench_job_headless_command,
            start_job_func=start_job_func,
        )

    return {
        "line_job_record": line_job_record,
        "print_line_jobs": print_line_jobs,
        "select_line_job": select_line_job,
        "cancel_line_job": cancel_line_job,
        "start_line_job": start_job,
    }


def build_default_line_job_callbacks(cfg, *, line_action_callbacks):
    return build_line_job_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        action_callbacks=line_action_callbacks,
        start_job_func=start_workbench_job_record,
        quote=shquote,
    )
