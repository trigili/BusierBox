"""Line-console REPL application wiring for grit-console."""

import sys

from gritlib.event_log import append_event
import gritlib.line_context as line_context
import gritlib.line_help as line_help
import gritlib.line_resources as line_resources
import gritlib.line_repl_callbacks as line_repl_callbacks
import gritlib.line_repl_runtime as line_repl_runtime
import gritlib.line_workspace as line_workspace
import gritlib.service_runtime as service_runtime
import gritlib.session_state as session_state
from gritlib.version import grit_version
from gritlib.console_workbench import workbench_snapshot
import gritlib.workflow_runners as workflow_runners


def _setup_line_repl_runtime_io():
    repl_io = line_repl_runtime.setup_line_repl_io(
        shutdown_event=service_runtime.SHUTDOWN,
        request_shutdown_func=service_runtime.request_shutdown,
    )
    return repl_io, line_repl_runtime.line_repl_io_input(repl_io)


def _run_line_repl_loop(
    cfg,
    line_input,
    foundation_callbacks,
    operational_callbacks,
    dispatch_callbacks,
):
    return line_repl_runtime.run_configured_line_repl_loop(
        cfg,
        clear_console_context_func=line_context.clear_line_console_context,
        workbench_mark_stopped_func=session_state.mark_service_stopped,
        shutdown_event=service_runtime.SHUTDOWN,
        shutdown_reason_func=service_runtime.current_shutdown_reason,
        target_callbacks=foundation_callbacks.target,
        utility_callbacks=dispatch_callbacks.utility,
        search_callbacks=operational_callbacks.search,
        core_callbacks=dispatch_callbacks.core,
        navigation_callbacks=dispatch_callbacks.navigation,
        workflow_callbacks=dispatch_callbacks.workflow,
        legacy_callbacks=dispatch_callbacks.legacy,
        workbench_snapshot_func=workbench_snapshot,
        print_workbench_func=workflow_runners.print_workbench,
        print_banner_func=line_workspace.print_line_console_banner,
        version_func=grit_version,
        prompt_func=line_workspace.line_repl_prompt_for_config,
        input_func=line_input,
        history_command_func=line_resources.line_history_command,
        record_history_func=line_resources.record_line_history,
        command_help_printer=line_help.print_line_command_help,
        context_help_printer=line_help.print_context_line_help,
        unknown_message_func=line_help.line_unknown_command_message,
    )


def run_line_repl(cfg):
    repl_io, line_input = _setup_line_repl_runtime_io()

    callback_bundles = line_repl_callbacks.build_line_callback_bundles(
        cfg,
        line_input,
    )
    line_repl_runtime.set_line_repl_io_completion_func(
        repl_io,
        callback_bundles.foundation.completion["line_completion_candidates"],
    )

    try:
        result = _run_line_repl_loop(
            cfg,
            line_input=line_input,
            foundation_callbacks=callback_bundles.foundation,
            operational_callbacks=callback_bundles.operational,
            dispatch_callbacks=callback_bundles.dispatch,
        )
    finally:
        line_repl_runtime.restore_line_repl_io(repl_io)
    return result


def run_line_console(cfg):
    """Default interactive mode: prompt-toolkit line console."""
    return line_repl_runtime.run_line_console_lifecycle(
        cfg,
        stdin_isatty_func=sys.stdin.isatty,
        stdout_isatty_func=sys.stdout.isatty,
        state_file_path_func=session_state.state_file_path,
        update_server_state_func=session_state.update_server_state,
        append_event_func=append_event,
        print_workbench_func=workflow_runners.print_workbench,
        run_repl_func=run_line_repl,
        request_shutdown_func=service_runtime.request_shutdown,
        stop_services_func=workflow_runners.stop_workbench_started_services,
        mark_stopped_func=session_state.mark_service_stopped,
        shutdown_reason_func=service_runtime.current_shutdown_reason,
        stderr=sys.stderr,
    )
