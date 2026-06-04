"""Line REPL legacy choice dispatch callback adapters."""

from gritlib.line_legacy_dispatch import dispatch_legacy_line_choice


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
    view_path_func,
    stage_binary_func,
    actions_func,
    run_workbench_action_func,
    run_target_workflow_func,
    scoped_target_cfg_func,
    print_target_summary_func,
    bridge_command_builder,
    print_bridge_profile_func,
    delete_bridge_profile_func,
    action_state_text_func,
    print_queue_func,
):
    def dispatch_legacy(choice):
        return dispatch_legacy_line_choice(
            choice,
            cfg,
            input_func=input_func,
            use_result_func=use_result_func,
            clear_results_func=lambda: clear_results_func(cfg),
            start_service_func=start_service_func,
            stop_service_func=stop_service_func,
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
