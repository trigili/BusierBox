"""Line REPL show-resource callback adapters."""

from gritlib.line_show import build_line_show_resource_callback


def build_line_show_resource_adapter(
    cfg,
    *,
    set_context_func,
    snapshot_func,
    target_filter_func,
    action_callbacks,
    target_callbacks,
    route_service_callbacks,
    file_callbacks,
    job_callbacks,
    session_callbacks,
    queue_callbacks,
    display_callbacks,
    print_daemon_func,
    print_categories_func,
    print_events_func,
    print_release_func,
    append_event_fn,
):
    print_info_func, _print_next_func, print_options_func = display_callbacks
    return build_line_show_resource_callback(
        cfg,
        set_context_func=set_context_func,
        snapshot_func=snapshot_func,
        target_filter_func=target_filter_func,
        print_actions_func=action_callbacks["print_line_actions"],
        print_targets_func=target_callbacks["print_line_targets"],
        print_services_func=route_service_callbacks["print_line_services"],
        print_files_func=file_callbacks["print_line_files"],
        print_jobs_func=job_callbacks["print_line_jobs"],
        print_daemon_func=print_daemon_func,
        print_categories_func=lambda: print_categories_func(
            cfg,
            lambda: snapshot_func(cfg),
        ),
        print_sessions_func=session_callbacks["print_line_sessions"],
        print_routes_func=route_service_callbacks["print_line_routes"],
        print_queue_func=queue_callbacks["print_line_command_queue_view"],
        print_events_func=print_events_func,
        print_release_func=lambda: print_release_func(cfg, append_event_fn=append_event_fn),
        print_options_func=print_options_func,
        print_info_func=print_info_func,
    )
