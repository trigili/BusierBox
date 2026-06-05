"""Runtime control argument dispatch for grit-console."""

from gritlib.command_queue import handle_command_queue_args
import gritlib.console_actions as console_actions
import gritlib.console_runtime as console_runtime
from gritlib.operator_daemon import run_operator_daemon
from gritlib.service_status import service_stop_headless_command
from gritlib.systemd_user import handle_systemd_user_action
import gritlib.workflow_runners as workflow_runners


def handle_runtime_control_args(cfg, args, timeout):
    command_queue_code = handle_command_queue_args(cfg, args)
    if command_queue_code is not None:
        return command_queue_code

    control_code = console_actions.handle_console_control_args(
        cfg,
        args,
        print_status_func=workflow_runners.print_status,
        stop_recorded_service_func=workflow_runners.stop_recorded_service,
        stop_managed_services_func=workflow_runners.stop_managed_services,
        service_stop_headless_command_func=service_stop_headless_command,
        systemd_user_action_func=handle_systemd_user_action,
    )
    if control_code is not None:
        return control_code

    daemon_code = console_runtime.handle_operator_daemon_args(
        cfg,
        args,
        timeout=timeout,
        run_operator_daemon_func=run_operator_daemon,
    )
    if daemon_code is not None:
        return daemon_code
    return None
