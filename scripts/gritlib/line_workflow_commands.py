"""Grouped line-console workflow, file, queue, and job dispatch."""

from gritlib.line_command_registry import dispatch_line_command_families
from gritlib.line_command_queue import dispatch_line_queue_command, parse_line_queue_command
from gritlib.line_configure import dispatch_line_configure_command, parse_line_configure_command
from gritlib.line_files import (
    dispatch_line_binary_command,
    dispatch_line_download_command,
    dispatch_line_file_command,
    parse_line_binary_command,
    parse_line_download_command,
    parse_line_file_transfer_command,
    parse_line_files_command,
)
from gritlib.line_release import dispatch_line_release_command, parse_line_release_alias_command
from gritlib.operator_io import dispatch_line_view_command, parse_line_view_command
from gritlib.workbench_jobs import dispatch_line_jobs_command, parse_line_jobs_command
from gritlib.workflow_actions import dispatch_line_daemon_command, parse_line_daemon_command


def _files_context_callback(callbacks):
    set_context_func = callbacks.get("set_context_func")
    return lambda: set_context_func("files") if set_context_func else None


def _dispatch_line_download_family(cmd, args, callbacks):
    download_cmd = parse_line_download_command(cmd, args)
    if not download_cmd:
        return False
    dispatch_line_download_command(
        download_cmd,
        download_func=callbacks.get("download_func"),
        set_context_func=_files_context_callback(callbacks),
    )
    return True


def _dispatch_line_daemon_family(cmd, args, callbacks):
    daemon_cmd = parse_line_daemon_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not daemon_cmd:
        return False
    dispatch_line_daemon_command(
        daemon_cmd,
        set_context_func=callbacks.get("set_context_func"),
        run_func=callbacks.get("daemon_run_func"),
    )
    return True


def _dispatch_line_release_family(cmd, args, callbacks):
    release_cmd = parse_line_release_alias_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not release_cmd:
        return False
    dispatch_line_release_command(
        release_cmd,
        list_func=callbacks.get("release_list_func"),
        stage_func=callbacks.get("release_stage_func"),
        help_func=callbacks.get("release_help_func"),
    )
    return True


def _dispatch_line_file_transfer_family(cmd, args, callbacks):
    file_cmd = parse_line_file_transfer_command(cmd, args)
    if not file_cmd:
        return False
    dispatch_line_file_command(
        file_cmd,
        upload_func=callbacks.get("upload_file_func"),
        fetch_func=callbacks.get("fetch_file_func"),
        unstage_func=callbacks.get("unstage_file_func"),
        set_context_func=_files_context_callback(callbacks),
    )
    return True


def _dispatch_line_view_family(cmd, args, callbacks):
    view_cmd = parse_line_view_command(cmd, args)
    if not view_cmd:
        return False
    dispatch_line_view_command(view_cmd, view_func=callbacks.get("view_path_func"))
    return True


def _dispatch_line_files_family(cmd, args, callbacks):
    files_cmd = parse_line_files_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not files_cmd:
        return False
    dispatch_line_file_command(
        files_cmd,
        upload_func=callbacks.get("upload_file_func"),
        fetch_func=callbacks.get("fetch_file_func"),
        unstage_func=callbacks.get("unstage_file_func"),
        clear_func=callbacks.get("clear_files_func"),
        list_func=callbacks.get("list_files_func"),
        set_context_func=_files_context_callback(callbacks),
    )
    return True


def _dispatch_line_queue_family(cmd, args, callbacks):
    queue_cmd = parse_line_queue_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not queue_cmd:
        return False
    set_context_func = callbacks.get("set_context_func")
    dispatch_line_queue_command(
        queue_cmd,
        original_cmd=cmd,
        set_context_func=lambda: set_context_func("queue") if set_context_func else None,
        run_func=callbacks.get("run_queue_func"),
        view_func=callbacks.get("view_queue_func"),
    )
    return True


def _dispatch_line_jobs_family(cmd, args, callbacks):
    jobs_cmd = parse_line_jobs_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not jobs_cmd:
        return False
    set_context_func = callbacks.get("set_context_func")
    list_jobs_func = callbacks.get("list_jobs_func")
    dispatch_line_jobs_command(
        jobs_cmd,
        cancel_func=callbacks.get("cancel_job_func"),
        select_func=callbacks.get("select_job_func"),
        list_func=lambda verbose=False: (
            set_context_func("jobs") if set_context_func else None,
            list_jobs_func(verbose=verbose),
        ),
    )
    return True


def _dispatch_line_binary_family(cmd, args, callbacks):
    binary_cmd = parse_line_binary_command(cmd, args)
    if not binary_cmd:
        return False
    dispatch_line_binary_command(
        binary_cmd,
        stage_binary_func=callbacks.get("stage_binary_func"),
        set_context_func=_files_context_callback(callbacks),
    )
    return True


def _dispatch_line_configure_family(cmd, args, callbacks):
    configure_cmd = parse_line_configure_command(cmd, args)
    if not configure_cmd:
        return False
    dispatch_line_configure_command(
        configure_cmd,
        configure_func=callbacks.get("configure_func"),
        set_context_func=_files_context_callback(callbacks),
    )
    return True


def dispatch_line_workflow_command(
    cmd,
    args,
    *,
    set_context_func=None,
    download_func=None,
    daemon_run_func=None,
    release_list_func=None,
    release_stage_func=None,
    release_help_func=None,
    upload_file_func=None,
    fetch_file_func=None,
    unstage_file_func=None,
    view_path_func=None,
    clear_files_func=None,
    list_files_func=None,
    run_queue_func=None,
    view_queue_func=None,
    cancel_job_func=None,
    select_job_func=None,
    list_jobs_func=None,
    stage_binary_func=None,
    configure_func=None,
    module="",
):
    args = list(args or [])
    callbacks = locals()
    return bool(dispatch_line_command_families(
        (
            _dispatch_line_download_family,
            _dispatch_line_daemon_family,
            _dispatch_line_release_family,
            _dispatch_line_file_transfer_family,
            _dispatch_line_view_family,
            _dispatch_line_files_family,
            _dispatch_line_queue_family,
            _dispatch_line_jobs_family,
            _dispatch_line_binary_family,
            _dispatch_line_configure_family,
        ),
        cmd,
        args,
        callbacks,
        default=False,
    ))
