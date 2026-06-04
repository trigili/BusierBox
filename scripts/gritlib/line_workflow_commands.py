"""Grouped line-console workflow, file, queue, and job dispatch."""

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
):
    args = list(args or [])
    if download_cmd := parse_line_download_command(cmd, args):
        dispatch_line_download_command(
            download_cmd,
            download_func=download_func,
            set_context_func=lambda: set_context_func("files") if set_context_func else None,
        )
        return True
    if daemon_cmd := parse_line_daemon_command(cmd, args):
        dispatch_line_daemon_command(
            daemon_cmd,
            set_context_func=set_context_func,
            run_func=daemon_run_func,
        )
        return True
    if release_cmd := parse_line_release_alias_command(cmd, args):
        dispatch_line_release_command(
            release_cmd,
            list_func=release_list_func,
            stage_func=release_stage_func,
            help_func=release_help_func,
        )
        return True
    if file_cmd := parse_line_file_transfer_command(cmd, args):
        dispatch_line_file_command(
            file_cmd,
            upload_func=upload_file_func,
            fetch_func=fetch_file_func,
            unstage_func=unstage_file_func,
            set_context_func=lambda: set_context_func("files") if set_context_func else None,
        )
        return True
    if view_cmd := parse_line_view_command(cmd, args):
        dispatch_line_view_command(view_cmd, view_func=view_path_func)
        return True
    if files_cmd := parse_line_files_command(cmd, args):
        dispatch_line_file_command(
            files_cmd,
            upload_func=upload_file_func,
            fetch_func=fetch_file_func,
            unstage_func=unstage_file_func,
            clear_func=clear_files_func,
            list_func=list_files_func,
            set_context_func=lambda: set_context_func("files") if set_context_func else None,
        )
        return True
    if queue_cmd := parse_line_queue_command(cmd, args):
        dispatch_line_queue_command(
            queue_cmd,
            original_cmd=cmd,
            set_context_func=lambda: set_context_func("queue") if set_context_func else None,
            run_func=run_queue_func,
            view_func=view_queue_func,
        )
        return True
    if jobs_cmd := parse_line_jobs_command(cmd, args):
        dispatch_line_jobs_command(
            jobs_cmd,
            cancel_func=cancel_job_func,
            select_func=select_job_func,
            list_func=lambda verbose=False: (
                set_context_func("jobs") if set_context_func else None,
                list_jobs_func(verbose=verbose),
            ),
        )
        return True
    if binary_cmd := parse_line_binary_command(cmd, args):
        dispatch_line_binary_command(
            binary_cmd,
            stage_binary_func=stage_binary_func,
            set_context_func=lambda: set_context_func("files") if set_context_func else None,
        )
        return True
    if configure_cmd := parse_line_configure_command(cmd, args):
        dispatch_line_configure_command(
            configure_cmd,
            configure_func=configure_func,
            set_context_func=lambda: set_context_func("files") if set_context_func else None,
        )
        return True
    return False
