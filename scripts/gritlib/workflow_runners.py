"""Workflow action runners for grit-console."""

from pathlib import Path
from gritlib.console_workbench import status_document, workbench_snapshot
import gritlib.service_lifecycle as service_lifecycle
from gritlib.service_runtime import current_shutdown_reason, start_child_process
from gritlib.status_print import print_status_document, print_workbench_snapshot
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
    return print_status_document(status_document(cfg), json_output=json_output)


def stop_managed_services(cfg):
    return service_lifecycle.stop_managed_services(cfg)


def print_workbench(cfg, include_api_summary=True):
    return print_workbench_snapshot(cfg, workbench_snapshot(cfg), include_api_summary=include_api_summary)


def start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return service_lifecycle.start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
        start_child_process=start_child_process,
        script_path=Path(__file__).resolve().parents[1] / "grit-console",
    )


def stop_workbench_started_services(cfg):
    return service_lifecycle.stop_workbench_started_services(
        cfg,
        stop_service=stop_recorded_service,
    )


def stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", quiet=False):
    return service_lifecycle.stop_recorded_service(
        cfg,
        service,
        via=via,
        headless_command=headless_command,
        shutdown_reason=current_shutdown_reason(),
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
