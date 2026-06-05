"""Application entrypoint for grit-console."""

import sys
import gritlib.bridge_routes as bridge_routes
from gritlib.build_config import handle_build_config_args
from gritlib.command_queue import handle_command_queue_args
from gritlib.command_queue_service import serve_command_queue
from gritlib.config_utils import load_config
import gritlib.console_actions as console_actions
from gritlib.console_artifact import handle_artifact_command
from gritlib.console_args import (
    apply_console_arg_overrides, build_arg_parser, handle_early_console_args,
    has_explicit_console_action,
)
from gritlib.console_bringup import handle_bringup_command
import gritlib.console_runtime as console_runtime
from gritlib.console_help import print_concise_help, print_console_help_reference
from gritlib.event_log import append_event
from gritlib.file_service import serve_file_service
from gritlib.file_transfers import render_fetch_command
from gritlib.line_repl_app import run_line_console
from gritlib.operator_daemon import run_operator_daemon
import gritlib.probe_service as probe_service
from gritlib.release_artifacts import stage_release_artifact
from gritlib.service_runtime import (
    install_shutdown_handlers, record_shutdown_event, request_shutdown,
)
from gritlib.service_status import resolve_transport, service_stop_headless_command
from gritlib.session_state import mark_service_stopped
import gritlib.shell_bridge_service as shell_bridge_service
import gritlib.staged_files as staged_files
from gritlib.systemd_user import handle_systemd_user_action
from gritlib.target_commands import shell_listener_max_sessions
from gritlib.version import grit_version
import gritlib.workbench_jobs as workbench_jobs
from gritlib.workflow_actions import workbench_action_records
import gritlib.workflow_runners as workflow_runners


def _handle_console_subcommand(raw_argv):
    if raw_argv and raw_argv[0] == "artifact":
        return handle_artifact_command(raw_argv[1:], program="grit-console artifact")
    if raw_argv and raw_argv[0] == "bringup":
        return handle_bringup_command(raw_argv[1:])
    return None


def _load_console_invocation(raw_argv):
    parser = build_arg_parser()
    early_args = handle_early_console_args(
        raw_argv,
        parser,
        version_text=f"griTTYkit {grit_version()}",
        print_concise_help_func=print_concise_help,
        print_console_help_reference_func=print_console_help_reference,
    )
    if early_args.handled:
        return early_args.code, None, None
    args = parser.parse_args(early_args.argv)

    cfg = load_config(args.config)
    try:
        apply_console_arg_overrides(cfg, args)
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2, None, None
    return None, cfg, args


def _handle_headless_action_args(cfg, args):
    bridge_profile_code = console_actions.handle_bridge_profile_args(
        cfg,
        args,
        save_bridge_profile_func=bridge_routes.save_bridge_profile,
        delete_bridge_profile_func=bridge_routes.delete_bridge_profile,
        print_bridge_profile_func=bridge_routes.print_bridge_profile,
        print_bridge_profiles_func=bridge_routes.print_bridge_profiles,
        bridge_profiles_path_func=bridge_routes.bridge_profiles_path,
    )
    if bridge_profile_code is not None:
        return bridge_profile_code
    workbench_job_code = console_actions.handle_workbench_job_args(
        cfg,
        args,
        workbench_action_records_func=workbench_action_records,
        start_workbench_job_headless_command_func=workbench_jobs.start_workbench_job_headless_command,
        start_workbench_job_record_func=workbench_jobs.start_workbench_job_record,
        cancel_workbench_job_headless_command_func=workbench_jobs.cancel_workbench_job_headless_command,
        cancel_workbench_job_record_func=workbench_jobs.cancel_workbench_job_record,
        run_workbench_action_record_func=workbench_jobs.run_workbench_action_record,
    )
    if workbench_job_code is not None:
        return workbench_job_code
    workflow_code = console_actions.handle_workflow_action_args(
        cfg,
        args,
        run_service_workflow_action_func=workflow_runners.run_service_workflow_action,
        run_operator_daemon_workflow_action_func=workflow_runners.run_operator_daemon_workflow_action,
        run_release_artifact_workflow_action_func=workflow_runners.run_release_artifact_workflow_action,
        run_command_queue_workflow_action_func=workflow_runners.run_command_queue_workflow_action,
        run_probe_workflow_action_func=workflow_runners.run_probe_workflow_action,
        run_bridge_profile_workflow_action_func=workflow_runners.run_bridge_profile_workflow_action,
        run_file_service_workflow_action_func=workflow_runners.run_file_service_workflow_action,
        run_staged_file_workflow_action_func=workflow_runners.run_staged_file_workflow_action,
        run_target_workflow_action_func=workflow_runners.run_target_workflow_action,
    )
    if workflow_code is not None:
        return workflow_code
    build_config_code = handle_build_config_args(cfg, args, append_event_fn=append_event)
    if build_config_code is not None:
        return build_config_code
    return console_actions.handle_console_utility_args(
        cfg, args, append_event_fn=append_event
    )


def main(argv=None):
    install_shutdown_handlers()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    subcommand_code = _handle_console_subcommand(raw_argv)
    if subcommand_code is not None:
        return subcommand_code
    invocation_code, cfg, args = _load_console_invocation(raw_argv)
    if invocation_code is not None:
        return invocation_code

    try:
        headless_code = _handle_headless_action_args(cfg, args)
        if headless_code is not None:
            return headless_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    try:
        command_queue_code = handle_command_queue_args(cfg, args)
        if command_queue_code is not None:
            return command_queue_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    try:
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
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    timeout = console_runtime.timeout_from_args(args)
    try:
        daemon_code = console_runtime.handle_operator_daemon_args(
            cfg,
            args,
            timeout=timeout,
            run_operator_daemon_func=run_operator_daemon,
        )
        if daemon_code is not None:
            return daemon_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2
    action = console_runtime.listener_action_from_args(cfg, args, resolve_transport)
    script_bytes = console_runtime.script_bytes_from_args(args)
    session_timeout = console_runtime.session_timeout_from_args(args)

    try:
        staging_code, action = console_actions.handle_file_staging_args(
            cfg,
            args,
            action,
            stage_file_func=staged_files.stage_file,
            stage_dir_func=staged_files.stage_dir,
            stage_release_artifact_func=stage_release_artifact,
            unstage_file_func=staged_files.unstage_file,
            print_staged_func=staged_files.print_staged,
            render_fetch_command_func=render_fetch_command,
        )
        if staging_code is not None:
            return staging_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    if not has_explicit_console_action(args) and not args.no_console:
        return run_line_console(cfg)

    try:
        listen_code = console_runtime.serve_listener_action(
            cfg,
            args,
            action,
            timeout=timeout,
            script_bytes=script_bytes,
            session_timeout=session_timeout,
            shell_listener_max_sessions_func=shell_listener_max_sessions,
            serve_ssh_func=shell_bridge_service.serve_ssh,
            serve_tls_shell_func=shell_bridge_service.serve_tls_shell,
            serve_plain_shell_func=shell_bridge_service.serve_plain_shell,
            serve_file_service_func=serve_file_service,
            serve_command_queue_func=serve_command_queue,
            serve_bridge_func=shell_bridge_service.serve_bridge,
            serve_probe_func=probe_service.serve_probe,
            serve_probe_tftp_func=probe_service.serve_probe_tftp,
            serve_probe_ftp_func=probe_service.serve_probe_ftp,
            serve_probe_dns_func=probe_service.serve_probe_dns,
        )
        if listen_code is not None:
            return listen_code
    except KeyboardInterrupt:
        print("grit-console: interrupted, shutting down", file=sys.stderr)
        request_shutdown("keyboard_interrupt")
        record_shutdown_event(cfg, action)
        mark_service_stopped(cfg, action, "keyboard_interrupt")
        return 130
    except OSError:
        return 1
    print(f"unsupported transport: {action}", file=sys.stderr)
    return 2
