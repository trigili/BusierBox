"""Line REPL completion callback adapters."""

from gritlib.line_completions import build_line_completion_callbacks


def build_line_completion_adapter(
    cfg,
    *,
    workbench_snapshot_func,
    current_action_records_func,
    bridge_profile_records_func,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func,
    workbench_config_field_records_func,
    service_status_rows_func,
    service_completion_names_func,
    service_names_func,
    load_staged_func,
    find_survey_uploads_func,
    append_event_fn,
):
    return build_line_completion_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        line_action_records_func=lambda: current_action_records_func(
            lambda: workbench_snapshot_func(cfg)
        ),
        bridge_profile_records_func=bridge_profile_records_func,
        release_context_func=release_context_func,
        command_queue_summary_func=command_queue_summary_func,
        generated_target_command_records_func=generated_target_command_records_func,
        workbench_config_field_records_func=workbench_config_field_records_func,
        service_status_rows_func=service_status_rows_func,
        service_completion_names_func=service_completion_names_func,
        service_names_func=service_names_func,
        load_staged_func=load_staged_func,
        find_survey_uploads_func=lambda limit=20: find_survey_uploads_func(cfg, limit=limit),
        append_event_func=lambda service, event, details=None: append_event_fn(
            cfg,
            service,
            event,
            details=details,
        ),
    )
