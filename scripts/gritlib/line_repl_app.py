"""Line-console REPL application wiring for grit-console."""

import sys
import time
from gritlib.command_copy import copy_text_for_operator
import gritlib.config_utils as config_utils
from gritlib.event_log import append_event
import gritlib.line_build as line_build
import gritlib.line_configure as line_configure
import gritlib.line_context as line_context
from gritlib.line_events import print_line_events_view
import gritlib.line_files as line_files
import gritlib.line_help as line_help
from gritlib.line_network import print_line_local_ips
import gritlib.line_resources as line_resources
import gritlib.line_repl_runtime as line_repl_runtime
from gritlib.line_repl_actions import build_default_line_action_callbacks
from gritlib.line_repl_completions import (
    setup_default_line_completion_bundle,
)
from gritlib.line_repl_core import build_line_core_callbacks
from gritlib.line_repl_files import build_default_line_file_workflow_callbacks
from gritlib.line_repl_jobs import build_default_line_job_callbacks
from gritlib.line_repl_legacy import build_line_legacy_callbacks
from gritlib.line_repl_navigation import build_line_navigation_callbacks
from gritlib.line_repl_options import build_default_line_option_callbacks
from gritlib.line_repl_probe import build_default_line_probe_callbacks
from gritlib.line_repl_queue import build_default_line_queue_callbacks
from gritlib.line_repl_routes import (
    build_default_line_route_service_callbacks,
)
from gritlib.line_repl_search import build_default_line_search_bundle
from gritlib.line_repl_sessions import build_default_line_session_callbacks
from gritlib.line_repl_show import build_default_line_display_show_callbacks
from gritlib.line_repl_survey import build_line_survey_callbacks
from gritlib.line_repl_targets import build_default_line_target_callbacks
from gritlib.line_repl_utility import build_line_utility_callbacks
from gritlib.line_repl_workflow import build_line_workflow_callbacks
from gritlib.line_repl_workspace import build_line_workspace_callbacks
import gritlib.line_release as line_release
from gritlib.line_search import (
    clear_line_search_results,
)
import gritlib.line_target_commands as line_target_commands
import gritlib.line_workspace as line_workspace
import gritlib.service_runtime as service_runtime
import gritlib.session_state as session_state
from gritlib.staged_files import (
    print_staged,
)
from gritlib.version import grit_version
from gritlib.console_workbench import workbench_snapshot
import gritlib.workflow_runners as workflow_runners

try:
    import readline as _readline
    HAVE_READLINE = True
except ImportError:
    _readline = None
    HAVE_READLINE = False


def _setup_line_repl_runtime_io():
    repl_io = line_repl_runtime.setup_line_repl_io(
        _readline,
        HAVE_READLINE,
        shutdown_event=service_runtime.SHUTDOWN,
        request_shutdown_func=service_runtime.request_shutdown,
    )
    return repl_io, line_repl_runtime.line_repl_io_input(repl_io)


def _run_line_repl_loop(
    cfg,
    line_input,
    line_target_callbacks,
    line_utility_callbacks,
    line_search_callbacks,
    line_core_callbacks,
    line_navigation_callbacks,
    line_workflow_callbacks,
    line_legacy_callbacks,
):
    return line_repl_runtime.run_configured_line_repl_loop(
        cfg,
        clear_console_context_func=line_context.clear_line_console_context,
        workbench_mark_stopped_func=session_state.mark_service_stopped,
        shutdown_event=service_runtime.SHUTDOWN,
        shutdown_reason_func=service_runtime.current_shutdown_reason,
        target_callbacks=line_target_callbacks,
        utility_callbacks=line_utility_callbacks,
        search_callbacks=line_search_callbacks,
        core_callbacks=line_core_callbacks,
        navigation_callbacks=line_navigation_callbacks,
        workflow_callbacks=line_workflow_callbacks,
        legacy_callbacks=line_legacy_callbacks,
        workbench_snapshot_func=workbench_snapshot,
        print_workbench_func=workflow_runners.print_workbench,
        print_banner_func=line_workspace.print_line_console_banner,
        version_func=grit_version,
        prompt_func=line_workspace.line_repl_prompt_for_config,
        input_func=line_input,
        history_command_func=line_resources.line_history_command,
        record_history_func=line_resources.record_line_history,
        readline_module=_readline if HAVE_READLINE else None,
        command_help_printer=line_help.print_line_command_help,
        context_help_printer=line_help.print_context_line_help,
        unknown_message_func=line_help.line_unknown_command_message,
    )


def _build_line_foundation_callbacks(cfg, line_input):
    line_target_callbacks = build_default_line_target_callbacks(cfg)

    line_route_service_callbacks = build_default_line_route_service_callbacks(cfg)

    line_option_callbacks = build_default_line_option_callbacks(cfg)

    line_action_callbacks = build_default_line_action_callbacks(
        cfg,
        line_input=line_input,
        line_route_service_callbacks=line_route_service_callbacks,
    )

    line_completion_callbacks = setup_default_line_completion_bundle(
        cfg,
        readline_module=_readline,
        have_readline=HAVE_READLINE,
        line_route_service_callbacks=line_route_service_callbacks,
        line_target_callbacks=line_target_callbacks,
        line_option_callbacks=line_option_callbacks,
        line_action_callbacks=line_action_callbacks,
    )

    return (
        line_target_callbacks,
        line_route_service_callbacks,
        line_option_callbacks,
        line_action_callbacks,
        line_completion_callbacks,
    )


def _build_line_operational_callbacks(
    cfg,
    line_input,
    line_target_callbacks,
    line_route_service_callbacks,
    line_option_callbacks,
    line_action_callbacks,
):
    line_job_callbacks = build_default_line_job_callbacks(
        cfg,
        line_action_callbacks=line_action_callbacks,
    )

    line_queue_callbacks = build_default_line_queue_callbacks(
        cfg,
        line_target_callbacks=line_target_callbacks,
    )

    line_probe_callbacks = build_default_line_probe_callbacks(
        cfg,
        line_input=line_input,
        line_route_service_callbacks=line_route_service_callbacks,
        line_target_callbacks=line_target_callbacks,
    )

    line_session_callbacks = build_default_line_session_callbacks(cfg)

    line_file_callbacks = build_default_line_file_workflow_callbacks(
        cfg,
        line_input=line_input,
        line_target_callbacks=line_target_callbacks,
        line_route_service_callbacks=line_route_service_callbacks,
    )

    line_search_callbacks = build_default_line_search_bundle(
        cfg,
        line_target_callbacks=line_target_callbacks,
        line_route_service_callbacks=line_route_service_callbacks,
        line_action_callbacks=line_action_callbacks,
        line_session_callbacks=line_session_callbacks,
        line_job_callbacks=line_job_callbacks,
        line_queue_callbacks=line_queue_callbacks,
    )
    line_display_show_callbacks = build_default_line_display_show_callbacks(
        cfg,
        line_action_callbacks=line_action_callbacks,
        line_option_callbacks=line_option_callbacks,
        line_target_callbacks=line_target_callbacks,
        line_route_service_callbacks=line_route_service_callbacks,
        line_probe_callbacks=line_probe_callbacks,
        line_file_callbacks=line_file_callbacks,
        line_job_callbacks=line_job_callbacks,
        line_session_callbacks=line_session_callbacks,
        line_queue_callbacks=line_queue_callbacks,
    )

    return (
        line_job_callbacks,
        line_queue_callbacks,
        line_probe_callbacks,
        line_session_callbacks,
        line_file_callbacks,
        line_search_callbacks,
        line_display_show_callbacks,
    )


def _build_line_dispatch_callbacks(
    cfg,
    line_input,
    line_target_callbacks,
    line_route_service_callbacks,
    line_option_callbacks,
    line_action_callbacks,
    line_completion_callbacks,
    line_job_callbacks,
    line_queue_callbacks,
    line_probe_callbacks,
    line_session_callbacks,
    line_file_callbacks,
    line_search_callbacks,
    line_display_show_callbacks,
):
    line_workspace_callbacks = build_line_workspace_callbacks(
        cfg,
        default_config=config_utils.DEFAULT_CONFIG,
        load_config_func=config_utils.load_config,
        defaults=config_utils.DEFAULTS,
        workbench_snapshot_func=workbench_snapshot,
        clear_module_context_func=line_context.clear_line_module_context,
        print_workspace_snapshot_func=line_workspace.print_line_workspace_snapshot,
        reload_config_func=line_workspace.reload_line_config_for_repl,
        clear_console_context_func=line_context.clear_line_console_context,
        local_ips_func=print_line_local_ips,
    )

    line_survey_callbacks = build_line_survey_callbacks(
        cfg,
        survey_results_func=line_configure.print_line_survey_status,
        find_survey_uploads_func=line_configure.find_survey_uploads,
        survey_config_func=line_configure.run_line_survey_config,
        survey_preset_func=line_configure.run_line_survey_preset,
    )

    line_utility_callbacks = build_line_utility_callbacks(
        cfg,
        completion_callbacks=line_completion_callbacks,
        resource_history_func=line_resources.print_line_history,
        resource_load_func=line_resources.load_line_resource,
        resource_save_func=line_resources.write_line_makerc,
        events_func=print_line_events_view,
        search_callbacks=line_search_callbacks,
        display_callbacks=line_display_show_callbacks,
        generated_run_func=line_target_commands.run_line_generated_command,
        copy_text_func=copy_text_for_operator,
        route_service_callbacks=line_route_service_callbacks,
        service_copy_command_func=line_target_commands.copy_line_service_command,
        generated_copy_func=line_target_commands.copy_line_generated_command,
    )
    line_core_callbacks = build_line_core_callbacks(
        cfg,
        clear_module_func=line_context.clear_line_module_context,
        probe_callbacks=line_probe_callbacks,
        file_callbacks=line_file_callbacks,
        display_callbacks=line_display_show_callbacks,
        option_callbacks=line_option_callbacks,
        workspace_callbacks=line_workspace_callbacks,
        survey_callbacks=line_survey_callbacks,
        set_context_func=line_context.set_line_collection_context,
        build_run_func=line_build.run_line_build_command,
        help_func=line_help.print_line_command_help,
        append_event_fn=append_event,
    )
    line_navigation_callbacks = build_line_navigation_callbacks(
        cfg,
        append_event_fn=append_event,
        clear_results_func=clear_line_search_results,
        set_context_func=line_context.set_line_collection_context,
        clear_console_context_func=line_context.clear_line_console_context,
        back_func=line_context.back_line_module_context,
        session_help_func=line_help.print_line_command_help,
        route_help_func=line_help.print_line_command_help,
        search_callbacks=line_search_callbacks,
        target_callbacks=line_target_callbacks,
        route_service_callbacks=line_route_service_callbacks,
        session_callbacks=line_session_callbacks,
        job_callbacks=line_job_callbacks,
        action_callbacks=line_action_callbacks,
        queue_callbacks=line_queue_callbacks,
    )
    line_workflow_callbacks = build_line_workflow_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        set_context_func=line_context.set_line_collection_context,
        daemon_runner_func=workflow_runners.run_operator_daemon_workflow_action,
        release_print_func=line_release.print_line_release,
        release_help_func=line_help.print_line_command_help,
        target_callbacks=line_target_callbacks,
        clear_files_func=line_files.clear_line_files,
        file_callbacks=line_file_callbacks,
        queue_callbacks=line_queue_callbacks,
        job_callbacks=line_job_callbacks,
        append_event_fn=append_event,
    )
    line_legacy_callbacks = build_line_legacy_callbacks(
        cfg,
        input_func=line_input,
        search_callbacks=line_search_callbacks,
        clear_results_func=clear_line_search_results,
        sleep_func=time.sleep,
        append_event_fn=append_event,
        print_staged_func=print_staged,
        snapshot_func=workbench_snapshot,
        route_service_callbacks=line_route_service_callbacks,
        target_callbacks=line_target_callbacks,
        file_callbacks=line_file_callbacks,
        queue_callbacks=line_queue_callbacks,
        action_callbacks=line_action_callbacks,
    )

    return (
        line_utility_callbacks,
        line_core_callbacks,
        line_navigation_callbacks,
        line_workflow_callbacks,
        line_legacy_callbacks,
    )


def run_line_repl(cfg):
    repl_io, line_input = _setup_line_repl_runtime_io()

    (
        line_target_callbacks,
        line_route_service_callbacks,
        line_option_callbacks,
        line_action_callbacks,
        line_completion_callbacks,
    ) = _build_line_foundation_callbacks(
        cfg,
        line_input,
    )

    (
        line_job_callbacks,
        line_queue_callbacks,
        line_probe_callbacks,
        line_session_callbacks,
        line_file_callbacks,
        line_search_callbacks,
        line_display_show_callbacks,
    ) = _build_line_operational_callbacks(
        cfg,
        line_input,
        line_target_callbacks,
        line_route_service_callbacks,
        line_option_callbacks,
        line_action_callbacks,
    )

    (
        line_utility_callbacks,
        line_core_callbacks,
        line_navigation_callbacks,
        line_workflow_callbacks,
        line_legacy_callbacks,
    ) = _build_line_dispatch_callbacks(
        cfg,
        line_input,
        line_target_callbacks,
        line_route_service_callbacks,
        line_option_callbacks,
        line_action_callbacks,
        line_completion_callbacks,
        line_job_callbacks,
        line_queue_callbacks,
        line_probe_callbacks,
        line_session_callbacks,
        line_file_callbacks,
        line_search_callbacks,
        line_display_show_callbacks,
    )

    try:
        result = _run_line_repl_loop(
            cfg,
            line_input=line_input,
            line_target_callbacks=line_target_callbacks,
            line_utility_callbacks=line_utility_callbacks,
            line_search_callbacks=line_search_callbacks,
            line_core_callbacks=line_core_callbacks,
            line_navigation_callbacks=line_navigation_callbacks,
            line_workflow_callbacks=line_workflow_callbacks,
            line_legacy_callbacks=line_legacy_callbacks,
        )
    finally:
        line_repl_runtime.restore_line_repl_io(repl_io)
    return result


def run_line_console(cfg):
    """Default interactive mode: readline line console."""
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
