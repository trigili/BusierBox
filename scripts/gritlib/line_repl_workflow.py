"""Line REPL workflow command callback adapters."""

from gritlib.line_daemon import run_line_daemon_action
from gritlib.line_workflow_commands import dispatch_line_workflow_command


def build_line_workflow_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    set_context_func,
    daemon_runner_func,
    release_print_func,
    release_help_func,
    target_filter_func,
    clear_files_func,
    file_callbacks,
    queue_callbacks,
    job_callbacks,
    append_event_fn,
):
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
    def run_daemon_action(daemon_args):
        return run_line_daemon_action(
            daemon_args,
            snapshot_func=lambda: workbench_snapshot_func(cfg),
            run_action_func=lambda selector, dry_run=False, confirmed=False, show_commands=False: (
                daemon_runner_func(
                    cfg,
                    selector,
                    dry_run=dry_run,
                    confirmed=confirmed,
                    show_commands=show_commands,
                )
            ),
        )

    def dispatch_workflow(command, args):
        return dispatch_line_workflow_command(
            command,
            args,
            set_context_func=lambda module: set_context_func(cfg, module),
            download_func=download_func,
            daemon_run_func=run_daemon_action,
            release_list_func=lambda: (
                set_context_func(cfg, "release"),
                release_print_func(cfg, append_event_fn=append_event_fn),
            ),
            release_stage_func=lambda selector, start_file_service=False: (
                release_stage_func(
                    selector,
                    start_file_service=start_file_service,
                ),
                set_context_func(cfg, "files"),
            ),
            release_help_func=release_help_func,
            upload_file_func=upload_file_func,
            fetch_file_func=fetch_file_func,
            unstage_file_func=unstage_file_func,
            view_path_func=view_path_func,
            clear_files_func=lambda confirm=False: clear_files_func(
                cfg,
                confirm=confirm,
                target_filter_id=target_filter_func(cfg),
                append_event_fn=append_event_fn,
            ),
            list_files_func=lambda verbose=False: list_files_func(verbose=verbose),
            run_queue_func=run_queue_func,
            view_queue_func=view_queue_func,
            cancel_job_func=cancel_job_func,
            select_job_func=select_job_func,
            list_jobs_func=list_jobs_func,
            stage_binary_func=stage_binary_func,
            configure_func=configure_func,
        )

    return dispatch_workflow
