"""Workflow action runners for grit-console."""

import gritlib.workflow_runtime as workflow_runtime
import gritlib.workflow_command_queue_runner as workflow_command_queue_runner
import gritlib.workflow_file_service_runner as workflow_file_service_runner
from gritlib.workflow_operator_daemon_runner import run_operator_daemon_workflow_action
import gritlib.workflow_probe_runner as workflow_probe_runner
import gritlib.workflow_release_runner as workflow_release_runner
from gritlib.workflow_service_runner import (
    run_bridge_profile_workflow_action, run_service_workflow_action,
)
import gritlib.workflow_staged_file_runner as workflow_staged_file_runner
import gritlib.workflow_target_runner as workflow_target_runner

def print_status(cfg, json_output=False):
    return workflow_runtime.print_status(cfg, json_output=json_output)


def stop_managed_services(cfg):
    return workflow_runtime.stop_managed_services(cfg)


def print_workbench(cfg, include_api_summary=True):
    return workflow_runtime.print_workbench(cfg, include_api_summary=include_api_summary)


def start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return workflow_runtime.start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
    )


def stop_workbench_started_services(cfg):
    return workflow_runtime.stop_workbench_started_services(cfg)


def stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", quiet=False):
    return workflow_runtime.stop_recorded_service(
        cfg,
        service,
        via=via,
        headless_command=headless_command,
        quiet=quiet,
    )


def run_release_artifact_workflow_action(cfg, selector, dry_run=False):
    return workflow_release_runner.run_release_artifact_workflow_action(
        cfg,
        selector,
        dry_run=dry_run,
        print_status_func=print_status,
    )


def run_command_queue_workflow_action(cfg, selector, command_input="", dry_run=False, confirmed=False):
    return workflow_command_queue_runner.run_command_queue_workflow_action(
        cfg,
        selector,
        command_input=command_input,
        dry_run=dry_run,
        confirmed=confirmed,
        print_status_func=print_status,
        start_service_process_func=start_service_process,
        stop_recorded_service_func=stop_recorded_service,
    )


def run_file_service_workflow_action(cfg, selector, local_file="", request_name="", target_path="", dry_run=False, confirmed=False):
    return workflow_file_service_runner.run_file_service_workflow_action(
        cfg,
        selector,
        local_file=local_file,
        request_name=request_name,
        target_path=target_path,
        dry_run=dry_run,
        confirmed=confirmed,
        print_status_func=print_status,
        start_service_process_func=start_service_process,
        stop_recorded_service_func=stop_recorded_service,
    )


def run_probe_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    return workflow_probe_runner.run_probe_workflow_action(
        cfg,
        selector,
        dry_run=dry_run,
        confirmed=confirmed,
        print_status_func=print_status,
        start_service_process_func=start_service_process,
        stop_recorded_service_func=stop_recorded_service,
    )


def run_staged_file_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    return workflow_staged_file_runner.run_staged_file_workflow_action(
        cfg,
        selector,
        dry_run=dry_run,
        confirmed=confirmed,
    )


def run_target_workflow_action(cfg, selector, command_input="", local_file="", request_name="", input_func=None, show_commands=True):
    return workflow_target_runner.run_target_workflow_action(
        cfg,
        selector,
        print_status_func=print_status,
        print_workbench_func=print_workbench,
        start_service_process_func=start_service_process,
        command_input=command_input,
        local_file=local_file,
        request_name=request_name,
        input_func=input_func,
        show_commands=show_commands,
    )
