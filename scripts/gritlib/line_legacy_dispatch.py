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
from gritlib.target_selection import dispatch_legacy_target_filter_number
from gritlib.target_activity import (
    dispatch_legacy_target_activity_number,
    dispatch_legacy_target_detail_number,
)
from gritlib.workbench_jobs import (
    dispatch_legacy_line_job_number,
    dispatch_legacy_refresh_choice,
)
from gritlib.workflow_actions import (
    dispatch_legacy_target_workflow_number,
    dispatch_legacy_workbench_action_number,
)


def _handled(**extra):
    result = {"handled": True}
    result.update(extra)
    return result


def _dispatch_line_result_selection(choice, cfg, use_result_func, clear_results_func, *, require_active_results=False):
    kwargs = {
        "use_result_func": use_result_func,
        "clear_results_func": clear_results_func,
    }
    if require_active_results:
        kwargs["require_active_results"] = True
    if dispatch_line_number_selection(
        choice,
        cfg,
        **kwargs,
    ):
        return _handled(compact_next_prompt=True)
    return None


def _dispatch_legacy_service_choice(
    choice,
    input_func,
    start_service_func,
    stop_service_func,
    service_rows_func,
    service_record_func,
    sleep_func,
):
    if dispatch_legacy_line_service_number(
        choice,
        input_func=input_func,
        start_func=start_service_func,
        stop_func=stop_service_func,
        service_rows_func=service_rows_func,
        service_record_func=service_record_func,
        sleep_func=sleep_func,
    ):
        return _handled()
    return None


def _dispatch_legacy_file_release_choice(
    choice,
    cfg,
    input_func,
    append_event_fn,
    print_staged_func,
    snapshot_func,
    view_path_func,
    stage_binary_func,
):
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
        return _handled()
    if dispatch_legacy_line_release_number(
        choice,
        cfg,
        input_func=input_func,
        append_event_fn=append_event_fn,
    ):
        return _handled()
    return None


def _dispatch_legacy_workflow_choice(
    choice,
    cfg,
    input_func,
    snapshot_func,
    append_event_fn,
    actions_func,
    run_workbench_action_func,
    run_target_workflow_func,
    scoped_target_cfg_func,
    print_target_summary_func,
):
    if dispatch_legacy_workbench_action_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        actions_func=actions_func,
        run_action_func=run_workbench_action_func,
    ):
        return _handled()
    if dispatch_legacy_target_workflow_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        run_target_func=run_target_workflow_func,
        scoped_target_cfg_func=scoped_target_cfg_func,
        print_target_summary_func=print_target_summary_func,
    ):
        return _handled()
    return None


def _dispatch_legacy_target_job_build_choice(choice, cfg, input_func, snapshot_func, actions_func):
    if dispatch_legacy_target_filter_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
    ):
        return _handled()
    if dispatch_legacy_line_job_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        actions_func=actions_func,
    ):
        return _handled()
    if dispatch_legacy_line_build_number(choice, cfg, input_func=input_func):
        return _handled()
    if dispatch_legacy_refresh_choice(choice, cfg):
        return _handled(render_full=True)
    if dispatch_legacy_copy_choice(choice, cfg, input_func=input_func):
        return _handled()
    return None


def _dispatch_legacy_bridge_choice(
    choice,
    cfg,
    input_func,
    snapshot_func,
    save_bridge_profile_headless_command_builder,
    print_bridge_profile_func,
    start_service_func,
    stop_service_func,
    delete_bridge_profile_func,
    append_event_fn,
):
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
        return _handled()
    return None


def _dispatch_legacy_target_probe_queue_activity_choice(
    choice,
    cfg,
    input_func,
    snapshot_func,
    append_event_fn,
    scoped_target_cfg_func,
    print_target_summary_func,
    action_state_text_func,
    start_service_func,
    print_line_command_queue_view_func,
):
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
        return _handled()
    if dispatch_legacy_probe_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        start_service_func=start_service_func,
    ):
        return _handled()
    if dispatch_legacy_line_queue_number(choice, view_func=print_line_command_queue_view_func):
        return _handled()
    if dispatch_legacy_target_activity_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        scoped_target_cfg_func=scoped_target_cfg_func,
    ):
        return _handled()
    return None


def _dispatch_legacy_active_result_context(ctx):
    return _dispatch_line_result_selection(
        ctx["choice"],
        ctx["cfg"],
        ctx["use_result_func"],
        ctx["clear_results_func"],
        require_active_results=True,
    )


def _dispatch_legacy_service_context(ctx):
    return _dispatch_legacy_service_choice(
        ctx["choice"],
        ctx["input_func"],
        ctx["start_service_func"],
        ctx["stop_service_func"],
        ctx["service_rows_func"],
        ctx["service_record_func"],
        ctx["sleep_func"],
    )


def _dispatch_legacy_file_release_context(ctx):
    return _dispatch_legacy_file_release_choice(
        ctx["choice"],
        ctx["cfg"],
        ctx["input_func"],
        ctx["append_event_fn"],
        ctx["print_staged_func"],
        ctx["snapshot_func"],
        ctx["view_path_func"],
        ctx["stage_binary_func"],
    )


def _dispatch_legacy_workflow_context(ctx):
    return _dispatch_legacy_workflow_choice(
        ctx["choice"],
        ctx["cfg"],
        ctx["input_func"],
        ctx["snapshot_func"],
        ctx["append_event_fn"],
        ctx["actions_func"],
        ctx["run_workbench_action_func"],
        ctx["run_target_workflow_func"],
        ctx["scoped_target_cfg_func"],
        ctx["print_target_summary_func"],
    )


def _dispatch_legacy_target_job_build_context(ctx):
    return _dispatch_legacy_target_job_build_choice(
        ctx["choice"],
        ctx["cfg"],
        ctx["input_func"],
        ctx["snapshot_func"],
        ctx["actions_func"],
    )


def _dispatch_legacy_bridge_context(ctx):
    return _dispatch_legacy_bridge_choice(
        ctx["choice"],
        ctx["cfg"],
        ctx["input_func"],
        ctx["snapshot_func"],
        ctx["save_bridge_profile_headless_command_builder"],
        ctx["print_bridge_profile_func"],
        ctx["start_service_func"],
        ctx["stop_service_func"],
        ctx["delete_bridge_profile_func"],
        ctx["append_event_fn"],
    )


def _dispatch_legacy_target_probe_queue_activity_context(ctx):
    return _dispatch_legacy_target_probe_queue_activity_choice(
        ctx["choice"],
        ctx["cfg"],
        ctx["input_func"],
        ctx["snapshot_func"],
        ctx["append_event_fn"],
        ctx["scoped_target_cfg_func"],
        ctx["print_target_summary_func"],
        ctx["action_state_text_func"],
        ctx["start_service_func"],
        ctx["print_line_command_queue_view_func"],
    )


def _dispatch_legacy_fallback_result_context(ctx):
    return _dispatch_line_result_selection(
        ctx["choice"],
        ctx["cfg"],
        ctx["use_result_func"],
        ctx["clear_results_func"],
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
    ctx = locals()
    for dispatch in (
        _dispatch_legacy_active_result_context,
        _dispatch_legacy_service_context,
        _dispatch_legacy_file_release_context,
        _dispatch_legacy_workflow_context,
        _dispatch_legacy_target_job_build_context,
        _dispatch_legacy_bridge_context,
        _dispatch_legacy_target_probe_queue_activity_context,
        _dispatch_legacy_fallback_result_context,
    ):
        result = dispatch(ctx)
        if result:
            return result
    return {"handled": False}
