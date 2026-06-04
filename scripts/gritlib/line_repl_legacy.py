"""Line REPL legacy choice dispatch callback adapters."""

import inspect

from gritlib.line_legacy_dispatch import dispatch_legacy_line_choice
from gritlib.service_status import (
    service_start_headless_command,
    service_stop_headless_command,
)


def _accepts_two_positional_args(func):
    needs_cfg_for_one_arg = False
    try:
        signature = inspect.signature(func)
        positional = [
            param for param in signature.parameters.values()
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        accepts_varargs = any(
            param.kind == inspect.Parameter.VAR_POSITIONAL
            for param in signature.parameters.values()
        )
        if accepts_varargs or len(positional) >= 2:
            needs_cfg_for_one_arg = True
    except (TypeError, ValueError):
        pass
    return needs_cfg_for_one_arg


def _line_legacy_start_service_callback(cfg, start_service_func, line_start_service_func=None):
    needs_cfg_for_one_arg = _accepts_two_positional_args(start_service_func)

    def start_service(*args, **kwargs):
        if len(args) == 1 and not kwargs and line_start_service_func:
            return line_start_service_func(args[0])
        if len(args) == 1 and not kwargs and needs_cfg_for_one_arg:
            service = args[0]
            return start_service_func(
                cfg,
                service,
                headless_command=service_start_headless_command(cfg, service),
            )
        return start_service_func(*args, **kwargs)

    return start_service


def _line_legacy_stop_service_callback(cfg, stop_service_func, line_stop_service_func=None):
    needs_cfg_for_one_arg = _accepts_two_positional_args(stop_service_func)

    def stop_service(*args, **kwargs):
        if len(args) == 1 and not kwargs and line_stop_service_func:
            return line_stop_service_func(args[0])
        if len(args) == 1 and not kwargs and needs_cfg_for_one_arg:
            service = args[0]
            return stop_service_func(
                cfg,
                service,
                headless_command=service_stop_headless_command(cfg, service),
            )
        return stop_service_func(*args, **kwargs)

    return stop_service


def build_line_legacy_dispatch_callback(
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
    view_path_func=None,
    stage_binary_func,
    actions_func=None,
    run_workbench_action_func=None,
    run_target_workflow_func=None,
    scoped_target_cfg_func,
    print_target_summary_func,
    bridge_command_builder,
    print_bridge_profile_func,
    delete_bridge_profile_func,
    action_state_text_func,
    print_queue_func,
    line_start_service_func=None,
    line_stop_service_func=None,
):
    def dispatch_legacy(choice):
        start_service = _line_legacy_start_service_callback(
            cfg,
            start_service_func,
            line_start_service_func=line_start_service_func,
        )
        stop_service = _line_legacy_stop_service_callback(
            cfg,
            stop_service_func,
            line_stop_service_func=line_stop_service_func,
        )
        return dispatch_legacy_line_choice(
            choice,
            cfg,
            input_func=input_func,
            use_result_func=use_result_func,
            clear_results_func=lambda: clear_results_func(cfg),
            start_service_func=start_service,
            stop_service_func=stop_service,
            service_rows_func=lambda: service_rows_func(cfg),
            service_record_func=service_record_func,
            sleep_func=sleep_func,
            append_event_fn=append_event_fn,
            print_staged_func=print_staged_func,
            snapshot_func=snapshot_func,
            view_path_func=view_path_func,
            stage_binary_func=stage_binary_func,
            actions_func=lambda: actions_func(cfg),
            run_workbench_action_func=run_workbench_action_func,
            run_target_workflow_func=run_target_workflow_func,
            scoped_target_cfg_func=scoped_target_cfg_func,
            print_target_summary_func=print_target_summary_func,
            save_bridge_profile_headless_command_builder=bridge_command_builder,
            print_bridge_profile_func=print_bridge_profile_func,
            delete_bridge_profile_func=delete_bridge_profile_func,
            action_state_text_func=action_state_text_func,
            print_line_command_queue_view_func=print_queue_func,
        )

    return dispatch_legacy


def build_line_legacy_callbacks(
    cfg,
    *,
    input_func,
    use_result_func=None,
    clear_results_func,
    start_service_func=None,
    stop_service_func=None,
    service_rows_func=None,
    service_record_func=None,
    sleep_func,
    append_event_fn,
    print_staged_func,
    snapshot_func,
    view_path_func=None,
    actions_func=None,
    run_workbench_action_func=None,
    run_target_workflow_func=None,
    scoped_target_cfg_func=None,
    print_target_summary_func=None,
    print_bridge_profile_func=None,
    delete_bridge_profile_func=None,
    action_state_text_func=None,
    route_service_callbacks,
    target_callbacks=None,
    file_callbacks,
    queue_callbacks,
    bridge_command_builder=None,
    search_callbacks=None,
    action_callbacks=None,
):
    if use_result_func is None and search_callbacks is not None:
        use_result_func = search_callbacks["use_line_search_result"]
    if bridge_command_builder is None:
        bridge_command_builder = route_service_callbacks["bridge_profile_headless_command"]
    if start_service_func is None:
        start_service_func = route_service_callbacks["start_line_service"]
    if stop_service_func is None:
        stop_service_func = route_service_callbacks["stop_line_service"]
    if service_rows_func is None:
        service_rows_func = lambda _cfg: route_service_callbacks["service_rows"]()
    if service_record_func is None:
        service_record_func = route_service_callbacks["service_record"]
    if print_bridge_profile_func is None:
        print_bridge_profile_func = route_service_callbacks["print_bridge_profile"]
    if delete_bridge_profile_func is None:
        delete_bridge_profile_func = route_service_callbacks["delete_bridge_profile"]
    if view_path_func is None:
        view_path_func = file_callbacks["view_path"]
    if scoped_target_cfg_func is None:
        scoped_target_cfg = file_callbacks["scoped_target_cfg"]
        scoped_target_cfg_func = lambda _cfg, target_id, target_label="": scoped_target_cfg(
            target_id,
            target_label=target_label,
        )
    if print_target_summary_func is None and target_callbacks is not None:
        print_target_summary_func = target_callbacks["print_target_summary"]
    if action_callbacks is not None:
        if actions_func is None:
            actions_func = lambda _cfg: action_callbacks["workbench_actions"]()
        if run_workbench_action_func is None:
            run_workbench_action_func = action_callbacks["run_workbench_action"]
        if run_target_workflow_func is None:
            run_target_workflow_func = action_callbacks["run_target_workflow"]
        if action_state_text_func is None:
            action_state_text_func = action_callbacks["action_state_text"]
    dispatch_legacy = build_line_legacy_dispatch_callback(
        cfg,
        input_func=input_func,
        use_result_func=use_result_func,
        clear_results_func=clear_results_func,
        start_service_func=start_service_func,
        stop_service_func=stop_service_func,
        line_start_service_func=route_service_callbacks["start_line_service"],
        line_stop_service_func=route_service_callbacks["stop_line_service"],
        service_rows_func=service_rows_func,
        service_record_func=service_record_func,
        sleep_func=sleep_func,
        append_event_fn=append_event_fn,
        print_staged_func=print_staged_func,
        snapshot_func=snapshot_func,
        view_path_func=view_path_func,
        stage_binary_func=file_callbacks["stage_binary"],
        actions_func=actions_func,
        run_workbench_action_func=run_workbench_action_func,
        run_target_workflow_func=run_target_workflow_func,
        scoped_target_cfg_func=scoped_target_cfg_func,
        print_target_summary_func=print_target_summary_func,
        bridge_command_builder=bridge_command_builder,
        print_bridge_profile_func=print_bridge_profile_func,
        delete_bridge_profile_func=delete_bridge_profile_func,
        action_state_text_func=action_state_text_func,
        print_queue_func=queue_callbacks["print_line_command_queue_view"],
    )
    return {"dispatch_line_legacy": dispatch_legacy}
