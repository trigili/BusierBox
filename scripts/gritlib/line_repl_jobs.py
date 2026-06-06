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
    input_func=input,
):
    select_action_func = action_callbacks["select_line_action"]
    selected_action_func = action_callbacks["selected_line_action"]
    if workbench_actions_func is None:
        workbench_actions_func = lambda _cfg: action_callbacks["workbench_actions"]()

    def snapshot():
        return workbench_snapshot_func(cfg)

    def line_job_record(selector):
        return current_line_job_record(snapshot, selector)

    def cancel_selector(selector):
        text = str(selector or "").strip()
        if text:
            return text
        module = str(cfg.get("_line_console_module") or "")
        if module.startswith("job/"):
            return module.split("/", 1)[1]
        return text

    def confirm_cancel_job(selector):
        text = cancel_selector(selector)
        rec = line_job_record(text)
        if not rec:
            return True
        job_id = str(rec.get("id") or text)
        action = str(rec.get("action_id") or "")
        state = str(rec.get("effective_state") or rec.get("state") or "")
        print(f"Job: {job_id}")
        if action:
            print(f"  action: {action}")
        if state:
            print(f"  state: {state}")
        answer = str(input_func(f"Cancel workbench job {job_id}? [y/N] ") or "").strip().lower()
        if answer in {"y", "yes"}:
            return True
        print("Cancelled.")
        return False

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

    def cancel_line_job(selector, prompt=True, confirmed=False):
        if prompt and not confirmed and not confirm_cancel_job(selector):
            return 0
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


def build_default_line_job_callbacks(cfg, *, line_action_callbacks, line_input=input):
    return build_line_job_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        action_callbacks=line_action_callbacks,
        start_job_func=start_workbench_job_record,
        quote=shquote,
        input_func=line_input,
    )
