"""Line-console REPL application wiring for grit-console."""

import sys

import gritlib.bridge_routes as bridge_routes
from gritlib.event_log import append_event
import gritlib.line_build as line_build
import gritlib.line_command_queue as line_command_queue
import gritlib.line_configure as line_configure
import gritlib.line_context as line_context
import gritlib.line_files as line_files
import gritlib.line_help as line_help
import gritlib.line_profiles as line_profiles
import gritlib.line_release as line_release
import gritlib.line_resources as line_resources
import gritlib.line_repl_callbacks as line_repl_callbacks
import gritlib.line_repl_runtime as line_repl_runtime
import gritlib.line_sessions as line_sessions
import gritlib.line_targets as line_targets
import gritlib.line_workspace as line_workspace
import gritlib.service_runtime as service_runtime
import gritlib.session_state as session_state
import gritlib.workbench_jobs as workbench_jobs
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
    def context_help_printer(module="", target_selected=False, command_help_printer=None):
        module_name = str(module or "").strip()
        if module_name == "profiles":
            line_profiles.print_profiles_context_help(cfg)
            return None
        if module_name == "jobs":
            snap = workbench_snapshot(cfg)
            workbench_jobs.print_jobs_context_help(snap.get("workbench_jobs") or [])
            return None
        if module_name == "sessions":
            snap = workbench_snapshot(cfg)
            line_sessions.print_sessions_context_help(snap.get("sessions") or [])
            return None
        if module_name == "targets":
            snap = workbench_snapshot(cfg)
            line_targets.print_targets_context_help(
                snap.get("targets") or [],
                target_selected=target_selected,
            )
            return None
        if module_name == "queue":
            snap = workbench_snapshot(cfg)
            line_command_queue.print_queue_context_help(
                snap.get("command_queue") or {},
                snap.get("target_mailbox_records") or [],
                target_selected=target_selected,
            )
            return None
        if module_name == "files":
            snap = workbench_snapshot(cfg)
            line_files.print_files_context_help(
                snap.get("staged_records") or [],
                target_selected=target_selected,
            )
            return None
        if module_name == "artifact":
            snap = workbench_snapshot(cfg)
            line_configure.print_artifact_context_help(snap.get("staged_records") or [], cfg)
            return None
        if module_name == "release":
            snap = workbench_snapshot(cfg)
            line_release.print_release_context_help(cfg, snap.get("staged_records") or [])
            return None
        if module_name == "survey":
            line_configure.print_survey_context_help(cfg)
            return None
        if module_name == "routes":
            snap = workbench_snapshot(cfg)
            bridge_routes.print_routes_context_help(snap.get("bridge_profiles") or [])
            return None
        if module_name.startswith("route/"):
            route_name = module_name.split("/", 1)[1]
            snap = workbench_snapshot(cfg)
            records = list(snap.get("bridge_profiles") or [])
            selected = [
                rec for rec in records
                if str(rec.get("name") or "") == route_name
            ]
            remaining = [
                rec for rec in records
                if str(rec.get("name") or "") != route_name
            ]
            bridge_routes.print_routes_context_help(selected + remaining)
            return None
        if module_name == "daemon":
            line_help.print_daemon_context_help()
            return None
        if module_name == "commands":
            line_help.print_commands_context_help()
            return None
        if module_name == "build":
            line_build.print_build_context_help()
            return None
        if module_name == "modules" or module_name.startswith("action/"):
            line_help.print_modules_context_help(
                module_name,
                selected_action=foundation_callbacks.action["selected_line_action"](),
            )
            return None
        return line_help.print_context_line_help(
            module,
            target_selected=target_selected,
            command_help_printer=command_help_printer,
        )

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
        context_help_printer=context_help_printer,
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
