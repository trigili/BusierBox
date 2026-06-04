"""Line REPL action callback adapters."""

from gritlib.line_actions import (
    print_current_line_actions,
    run_line_module_or_service,
    run_line_selected_action,
    select_current_line_action,
    selected_current_line_action,
)
from gritlib.line_command_queue import (
    select_current_line_command_queue_action,
)
from gritlib.line_state import line_action_state_text


def build_line_action_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    service_status_rows_func=None,
    service_names_func=None,
    start_service_func=None,
    route_service_callbacks=None,
    service_runner,
    daemon_runner,
    workbench_runner,
    target_runner,
    workbench_actions_func,
    target_input_func,
    append_event_fn,
    quote,
):
    def snapshot():
        return workbench_snapshot_func(cfg)

    def print_line_actions(filter_text="", kind_filter="", verbose=False):
        return print_current_line_actions(
            cfg,
            snapshot,
            filter_text=filter_text,
            kind_filter=kind_filter,
            verbose=verbose,
            quote=quote,
        )

    def select_line_action(selector):
        return select_current_line_action(cfg, snapshot, selector)

    def select_line_command_queue_action(selector):
        return select_current_line_command_queue_action(
            cfg,
            snapshot,
            selector,
            append_event_fn=append_event_fn,
        )

    def selected_line_action():
        return selected_current_line_action(cfg, snapshot)

    def service_names():
        if route_service_callbacks is not None and service_names_func is None:
            return route_service_callbacks["service_names"]()
        return service_names_func(service_status_rows_func(cfg))

    def workbench_actions():
        return workbench_actions_func(cfg)

    if start_service_func is None and route_service_callbacks is not None:
        start_service_func = route_service_callbacks["start_line_service"]

    def run_line_selected_action_callback(args=None, dry_run_default=False):
        return run_line_selected_action(
            cfg,
            selected_line_action(),
            args=args,
            dry_run_default=dry_run_default,
            service_runner=service_runner,
            daemon_runner=daemon_runner,
            workbench_runner=workbench_runner,
            target_runner=target_runner,
            workbench_actions=workbench_actions(),
            target_input_func=target_input_func,
        )

    def run_line_module_or_service_callback(values=None, dry_run_default=False):
        return run_line_module_or_service(
            values,
            dry_run_default=dry_run_default,
            selected_action_func=selected_line_action,
            select_action_func=select_line_action,
            service_names_func=service_names,
            start_service_func=start_service_func,
            run_selected_action_func=run_line_selected_action_callback,
        )

    return {
        "print_line_actions": print_line_actions,
        "select_line_action": select_line_action,
        "select_line_command_queue_action": select_line_command_queue_action,
        "selected_line_action": selected_line_action,
        "run_line_module_or_service": run_line_module_or_service_callback,
        "run_line_selected_action": run_line_selected_action_callback,
        "workbench_actions": workbench_actions,
        "run_workbench_action": workbench_runner,
        "run_target_workflow": target_runner,
        "action_state_text": line_action_state_text,
    }
