"""Line REPL action callback adapters."""

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.line_actions import (
    current_line_action_records,
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
from gritlib.shell_utils import shquote
from gritlib.workbench_jobs import run_workbench_action_record
from gritlib.workflow_actions import workbench_action_records
from gritlib import workflow_runners


def _build_line_action_selection_callbacks(cfg, snapshot, append_event_fn, quote):
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

    def current_action_records():
        return current_line_action_records(snapshot)

    return {
        "print_line_actions": print_line_actions,
        "select_line_action": select_line_action,
        "select_line_command_queue_action": select_line_command_queue_action,
        "selected_line_action": selected_line_action,
        "current_action_records": current_action_records,
    }


def _build_line_action_support_callbacks(cfg, snapshot, workbench_actions_func):
    def workbench_actions():
        return workbench_actions_func(cfg)

    return {
        "workbench_actions": workbench_actions,
        "current_action_records": lambda: current_line_action_records(snapshot),
    }


def _resolve_line_action_service_callbacks(
    cfg,
    service_status_rows_func,
    service_names_func,
    start_service_func,
    route_service_callbacks,
):
    if start_service_func is None and route_service_callbacks is not None:
        start_service_func = route_service_callbacks["start_line_service"]

    def service_names():
        if route_service_callbacks is not None and service_names_func is None:
            return route_service_callbacks["service_names"]()
        return service_names_func(service_status_rows_func(cfg))

    return service_names, start_service_func


def _build_line_action_run_callbacks(
    cfg,
    selected_line_action,
    select_line_action,
    service_names,
    start_service_func,
    service_runner,
    daemon_runner,
    workbench_runner,
    target_runner,
    workbench_actions,
    target_input_func,
):
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
        "run_line_module_or_service": run_line_module_or_service_callback,
        "run_line_selected_action": run_line_selected_action_callback,
    }


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

    selection_callbacks = _build_line_action_selection_callbacks(cfg, snapshot, append_event_fn, quote)
    support_callbacks = _build_line_action_support_callbacks(cfg, snapshot, workbench_actions_func)
    service_names, start_service_func = _resolve_line_action_service_callbacks(
        cfg,
        service_status_rows_func,
        service_names_func,
        start_service_func,
        route_service_callbacks,
    )
    run_callbacks = _build_line_action_run_callbacks(
        cfg,
        selection_callbacks["selected_line_action"],
        selection_callbacks["select_line_action"],
        service_names,
        start_service_func,
        service_runner,
        daemon_runner,
        workbench_runner,
        target_runner,
        support_callbacks["workbench_actions"],
        target_input_func,
    )

    return {
        "print_line_actions": selection_callbacks["print_line_actions"],
        "select_line_action": selection_callbacks["select_line_action"],
        "select_line_command_queue_action": selection_callbacks["select_line_command_queue_action"],
        "selected_line_action": selection_callbacks["selected_line_action"],
        "run_line_module_or_service": run_callbacks["run_line_module_or_service"],
        "run_line_selected_action": run_callbacks["run_line_selected_action"],
        "current_action_records": selection_callbacks["current_action_records"],
        "workbench_actions": support_callbacks["workbench_actions"],
        "run_workbench_action": workbench_runner,
        "run_target_workflow": target_runner,
        "action_state_text": line_action_state_text,
    }


def build_default_line_action_callbacks(
    cfg,
    *,
    line_input,
    line_route_service_callbacks,
):
    return build_line_action_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        route_service_callbacks=line_route_service_callbacks,
        service_runner=workflow_runners.run_service_workflow_action,
        daemon_runner=workflow_runners.run_operator_daemon_workflow_action,
        workbench_runner=run_workbench_action_record,
        target_runner=workflow_runners.run_target_workflow_action,
        workbench_actions_func=workbench_action_records,
        target_input_func=line_input,
        append_event_fn=append_event,
        quote=shquote,
    )
