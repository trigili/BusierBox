"""Line REPL workflow command callback adapters."""

from gritlib.line_workflow_commands import dispatch_line_workflow_command


def build_line_workflow_dispatch_callback(
    cfg,
    *,
    workbench_snapshot_func,
    set_context_func,
    download_func,
    daemon_action_func,
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
    def dispatch_workflow(command, args):
        return dispatch_line_workflow_command(
            command,
            args,
            set_context_func=lambda module: set_context_func(cfg, module),
            download_func=download_func,
            daemon_run_func=lambda daemon_args: daemon_action_func(
                daemon_args,
                snapshot_func=lambda: workbench_snapshot_func(cfg),
            ),
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
