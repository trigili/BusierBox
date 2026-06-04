"""Line REPL show-resource callback adapters."""

from gritlib.line_show import build_line_show_resource_callback


def build_line_show_resource_adapter(
    cfg,
    *,
    set_context_func,
    snapshot_func,
    target_filter_func,
    print_actions_func,
    print_targets_func,
    print_services_func,
    print_files_func,
    print_jobs_func,
    print_daemon_func,
    print_categories_func,
    print_sessions_func,
    print_routes_func,
    print_queue_func,
    print_events_func,
    print_release_func,
    print_options_func,
    print_info_func,
    append_event_fn,
):
    return build_line_show_resource_callback(
        cfg,
        set_context_func=set_context_func,
        snapshot_func=snapshot_func,
        target_filter_func=target_filter_func,
        print_actions_func=print_actions_func,
        print_targets_func=print_targets_func,
        print_services_func=print_services_func,
        print_files_func=print_files_func,
        print_jobs_func=print_jobs_func,
        print_daemon_func=print_daemon_func,
        print_categories_func=lambda: print_categories_func(
            cfg,
            lambda: snapshot_func(cfg),
        ),
        print_sessions_func=print_sessions_func,
        print_routes_func=print_routes_func,
        print_queue_func=print_queue_func,
        print_events_func=print_events_func,
        print_release_func=lambda: print_release_func(cfg, append_event_fn=append_event_fn),
        print_options_func=print_options_func,
        print_info_func=print_info_func,
    )
