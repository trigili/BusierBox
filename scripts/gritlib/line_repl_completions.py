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
    bundle = build_line_completion_bundle(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        current_action_records_func=current_action_records_func,
        bridge_profile_records_func=bridge_profile_records_func,
        release_context_func=release_context_func,
        command_queue_summary_func=command_queue_summary_func,
        generated_target_command_records_func=generated_target_command_records_func,
        workbench_config_field_records_func=workbench_config_field_records_func,
        service_status_rows_func=service_status_rows_func,
        service_completion_names_func=service_completion_names_func,
        service_names_func=service_names_func,
        load_staged_func=load_staged_func,
        find_survey_uploads_func=find_survey_uploads_func,
        append_event_fn=append_event_fn,
    )
    return (
        bundle["line_completion_candidates"],
        bundle["print_line_completions"],
    )


def build_line_completion_bundle(
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
    line_completion_candidates, print_line_completions = build_line_completion_callbacks(
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
    return {
        "line_completion_candidates": line_completion_candidates,
        "print_line_completions": print_line_completions,
    }
