"""Shared runtime helpers for workflow action composition."""

from pathlib import Path

from gritlib.console_workbench import status_document, workbench_snapshot
import gritlib.service_lifecycle as service_lifecycle
from gritlib.service_runtime import current_shutdown_reason, start_child_process
from gritlib.status_print import print_status_document, print_workbench_snapshot


def console_script_path():
    return Path(__file__).resolve().parents[1] / "grit-console"


def print_status(cfg, json_output=False):
    return print_status_document(status_document(cfg), json_output=json_output)


def print_workbench(cfg, include_api_summary=True):
    return print_workbench_snapshot(
        cfg,
        workbench_snapshot(cfg),
        include_api_summary=include_api_summary,
    )


def start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return service_lifecycle.start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
        start_child_process=start_child_process,
        script_path=console_script_path(),
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


def stop_managed_services(cfg):
    return service_lifecycle.stop_managed_services(cfg)


def stop_workbench_started_services(cfg):
    return service_lifecycle.stop_workbench_started_services(
        cfg,
        stop_service=stop_recorded_service,
    )
