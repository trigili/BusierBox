"""Listener action preparation and serving for grit-console."""

import sys

from gritlib.command_queue_service import serve_command_queue
import gritlib.console_actions as console_actions
import gritlib.console_runtime as console_runtime
from gritlib.file_service import serve_file_service
from gritlib.file_transfers import render_fetch_command
import gritlib.probe_service as probe_service
from gritlib.release_artifacts import stage_release_artifact
from gritlib.service_runtime import record_shutdown_event, request_shutdown
from gritlib.service_status import resolve_transport
from gritlib.session_state import mark_service_stopped
import gritlib.shell_bridge_service as shell_bridge_service
import gritlib.staged_files as staged_files
from gritlib.target_commands import shell_listener_max_sessions


def prepare_listener_action(cfg, args):
    action = console_runtime.listener_action_from_args(cfg, args, resolve_transport)
    script_bytes = console_runtime.script_bytes_from_args(args)
    session_timeout = console_runtime.session_timeout_from_args(args)
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
    return staging_code, action, script_bytes, session_timeout


def serve_console_listener_action(
    cfg,
    args,
    action,
    *,
    timeout,
    script_bytes,
    session_timeout,
    stderr=sys.stderr,
):
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
        print("grit-console: interrupted, shutting down", file=stderr)
        request_shutdown("keyboard_interrupt")
        record_shutdown_event(cfg, action)
        mark_service_stopped(cfg, action, "keyboard_interrupt")
        return 130
    except OSError:
        return 1
    print(f"unsupported transport: {action}", file=stderr)
    return 2
