"""Line REPL workflow command callback adapters."""

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
import gritlib.line_context as line_context
from gritlib.line_daemon import run_line_daemon_action
import gritlib.line_files as line_files
import gritlib.line_help as line_help
import gritlib.line_release as line_release
from gritlib.line_workflow_commands import dispatch_line_workflow_command
import gritlib.workflow_runners as workflow_runners


def build_default_line_workflow_callbacks(
    cfg,
    *,
    line_target_callbacks,
    line_file_callbacks,
    line_queue_callbacks,
    line_job_callbacks,
):
    return build_line_workflow_callbacks(
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


def build_line_workflow_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    set_context_func,
    daemon_runner_func,
    release_print_func,
    release_help_func,
    target_filter_func=None,
    target_callbacks=None,
    clear_files_func,
    file_callbacks,
    queue_callbacks,
    job_callbacks,
    append_event_fn,
):
    if target_filter_func is None and target_callbacks is not None:
        target_filter = target_callbacks["target_filter"]
        target_filter_func = lambda _cfg: target_filter()

    dispatch_workflow = build_line_workflow_dispatch_callback(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        set_context_func=set_context_func,
        download_func=file_callbacks["download_target"],
        daemon_runner_func=daemon_runner_func,
        release_print_func=release_print_func,
        release_stage_func=file_callbacks["stage_release"],
        release_help_func=release_help_func,
        upload_file_func=file_callbacks["stage_file"],
        fetch_file_func=file_callbacks["fetch_staged"],
        unstage_file_func=file_callbacks["unstage_file"],
        view_path_func=file_callbacks["view_path"],
        clear_files_func=clear_files_func,
        target_filter_func=target_filter_func,
        list_files_func=file_callbacks["print_line_files"],
        run_queue_func=queue_callbacks["run_line_queue_command"],
        view_queue_func=queue_callbacks["print_line_command_queue_view"],
        cancel_job_func=job_callbacks["cancel_line_job"],
        select_job_func=job_callbacks["select_line_job"],
        list_jobs_func=job_callbacks["print_line_jobs"],
        stage_binary_func=file_callbacks["stage_binary"],
        configure_func=file_callbacks["configure_artifact"],
        append_event_fn=append_event_fn,
    )
    return {"dispatch_line_workflow": dispatch_workflow}


def _run_line_workflow_daemon_action(ctx, daemon_args):
    cfg = ctx["cfg"]
    return run_line_daemon_action(
        daemon_args,
        snapshot_func=lambda: ctx["workbench_snapshot_func"](cfg),
        run_action_func=lambda selector, dry_run=False, confirmed=False, show_commands=False: (
            ctx["daemon_runner_func"](
                cfg,
                selector,
                dry_run=dry_run,
                confirmed=confirmed,
                show_commands=show_commands,
            )
        ),
    )


def _workflow_release_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "release_list_func": lambda: (
            ctx["set_context_func"](cfg, "release"),
            ctx["release_print_func"](cfg, append_event_fn=ctx["append_event_fn"]),
        ),
        "release_stage_func": lambda selector, start_file_service=False: (
            ctx["release_stage_func"](
                selector,
                start_file_service=start_file_service,
            ),
            ctx["set_context_func"](cfg, "files"),
        ),
        "release_help_func": ctx["release_help_func"],
    }


def _workflow_file_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "upload_file_func": ctx["upload_file_func"],
        "fetch_file_func": ctx["fetch_file_func"],
        "unstage_file_func": ctx["unstage_file_func"],
        "view_path_func": ctx["view_path_func"],
        "clear_files_func": lambda confirm=False: ctx["clear_files_func"](
            cfg,
            confirm=confirm,
            target_filter_id=ctx["target_filter_func"](cfg),
            append_event_fn=ctx["append_event_fn"],
        ),
        "list_files_func": lambda verbose=False: ctx["list_files_func"](verbose=verbose),
    }


def _workflow_queue_job_dispatch_kwargs(ctx):
    return {
        "run_queue_func": ctx["run_queue_func"],
        "view_queue_func": ctx["view_queue_func"],
        "cancel_job_func": ctx["cancel_job_func"],
        "select_job_func": ctx["select_job_func"],
        "list_jobs_func": ctx["list_jobs_func"],
    }


def _workflow_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    kwargs = {
        "set_context_func": lambda module: ctx["set_context_func"](cfg, module),
        "download_func": ctx["download_func"],
        "daemon_run_func": lambda daemon_args: _run_line_workflow_daemon_action(ctx, daemon_args),
        "module": str((cfg or {}).get("_line_console_module") or ""),
    }
    kwargs.update(_workflow_release_dispatch_kwargs(ctx))
    kwargs.update(_workflow_file_dispatch_kwargs(ctx))
    kwargs.update(_workflow_queue_job_dispatch_kwargs(ctx))
    kwargs.update({
        "stage_binary_func": ctx["stage_binary_func"],
        "configure_func": ctx["configure_func"],
    })
    return kwargs


def build_line_workflow_dispatch_callback(
    cfg,
    *,
    workbench_snapshot_func,
    set_context_func,
    download_func,
    daemon_runner_func,
    release_print_func,
    release_stage_func,
    release_help_func,
    upload_file_func,
    fetch_file_func,
    unstage_file_func,
    view_path_func,
    clear_files_func,
    target_filter_func,
    list_files_func,
    run_queue_func,
    view_queue_func,
    cancel_job_func,
    select_job_func,
    list_jobs_func,
    stage_binary_func,
    configure_func,
    append_event_fn,
):
    ctx = locals()

    def dispatch_workflow(command, args):
        return dispatch_line_workflow_command(
            command,
            args,
            **_workflow_dispatch_kwargs(ctx),
        )

    return dispatch_workflow
