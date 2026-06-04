"""Aggregate legacy numeric dispatch for the line console."""

from gritlib.bridge_routes import (
    dispatch_legacy_bridge_profile_number,
    prompt_line_bridge_profile_save,
)
from gritlib.line_build import dispatch_legacy_line_build_number
from gritlib.line_command_queue import dispatch_legacy_line_queue_number
from gritlib.line_files import dispatch_legacy_line_file_number
from gritlib.line_release import dispatch_legacy_line_release_number
from gritlib.line_search import dispatch_line_number_selection
from gritlib.line_services import dispatch_legacy_line_service_number
from gritlib.line_target_commands import dispatch_legacy_copy_choice
from gritlib.probe_commands import dispatch_legacy_probe_number
from gritlib.target_records import (
    dispatch_legacy_target_detail_number,
    dispatch_legacy_target_filter_number,
)
from gritlib.target_activity import dispatch_legacy_target_activity_number
from gritlib.workbench_jobs import (
    dispatch_legacy_line_job_number,
    dispatch_legacy_refresh_choice,
)
from gritlib.workflow_actions import (
    dispatch_legacy_target_workflow_number,
    dispatch_legacy_workbench_action_number,
)


def dispatch_legacy_line_choice(
    choice,
    cfg,
    *,
    input_func,
    use_result_func,
    clear_results_func,
    start_service_func,
    stop_service_func,
    service_rows_func,
    service_record_func,
    sleep_func,
    append_event_fn,
    print_staged_func,
    snapshot_func,
    view_path_func,
    stage_binary_func,
    actions_func,
    run_workbench_action_func,
    run_target_workflow_func,
    scoped_target_cfg_func,
    print_target_summary_func,
    save_bridge_profile_headless_command_builder,
    print_bridge_profile_func,
    delete_bridge_profile_func,
    action_state_text_func,
    print_line_command_queue_view_func,
):
    if dispatch_line_number_selection(
        choice,
        cfg,
        use_result_func=use_result_func,
        clear_results_func=clear_results_func,
        require_active_results=True,
    ):
        return {"handled": True, "compact_next_prompt": True}
    if dispatch_legacy_line_service_number(
        choice,
        input_func=input_func,
        start_func=start_service_func,
        stop_func=stop_service_func,
        service_rows_func=service_rows_func,
        service_record_func=service_record_func,
        sleep_func=sleep_func,
    ):
        return {"handled": True}
    if dispatch_legacy_line_file_number(
        choice,
        cfg,
        input_func=input_func,
        append_event_fn=append_event_fn,
        print_staged_func=print_staged_func,
        snapshot_func=snapshot_func,
        view_path_func=view_path_func,
        stage_binary_func=stage_binary_func,
    ):
        return {"handled": True}
    if dispatch_legacy_line_release_number(
        choice,
        cfg,
        input_func=input_func,
        append_event_fn=append_event_fn,
    ):
        return {"handled": True}
    if dispatch_legacy_workbench_action_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        actions_func=actions_func,
        run_action_func=run_workbench_action_func,
    ):
        return {"handled": True}
    if dispatch_legacy_target_workflow_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        run_target_func=run_target_workflow_func,
        scoped_target_cfg_func=scoped_target_cfg_func,
        print_target_summary_func=print_target_summary_func,
    ):
        return {"handled": True}
    if dispatch_legacy_target_filter_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
    ):
        return {"handled": True}
    if dispatch_legacy_line_job_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        actions_func=actions_func,
    ):
        return {"handled": True}
    if dispatch_legacy_line_build_number(choice, cfg, input_func=input_func):
        return {"handled": True}
    if dispatch_legacy_refresh_choice(choice, cfg):
        return {"handled": True, "render_full": True}
    if dispatch_legacy_copy_choice(choice, cfg, input_func=input_func):
        return {"handled": True}
    if dispatch_legacy_bridge_profile_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        save_profile_func=lambda: prompt_line_bridge_profile_save(
            cfg,
            input_func,
            headless_command_builder=save_bridge_profile_headless_command_builder,
        ),
        print_profile_func=print_bridge_profile_func,
        start_service_func=start_service_func,
        stop_service_func=stop_service_func,
        delete_profile_func=delete_bridge_profile_func,
        append_event_fn=append_event_fn,
    ):
        return {"handled": True}
    if dispatch_legacy_target_detail_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        scoped_target_cfg_func=scoped_target_cfg_func,
        print_summary_func=print_target_summary_func,
        action_state_text_func=action_state_text_func,
    ):
        return {"handled": True}
    if dispatch_legacy_probe_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        start_service_func=start_service_func,
    ):
        return {"handled": True}
    if dispatch_legacy_line_queue_number(choice, view_func=print_line_command_queue_view_func):
        return {"handled": True}
    if dispatch_legacy_target_activity_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        scoped_target_cfg_func=scoped_target_cfg_func,
    ):
        return {"handled": True}
    if dispatch_line_number_selection(
        choice,
        cfg,
        use_result_func=use_result_func,
        clear_results_func=clear_results_func,
    ):
        return {"handled": True, "compact_next_prompt": True}
    return {"handled": False}
