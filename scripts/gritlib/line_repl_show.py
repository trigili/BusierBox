"""Line REPL show-resource callback adapters."""

from gritlib.line_show import build_line_show_resource_callback
from gritlib.line_repl_display import build_line_display_callbacks


def build_line_display_show_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    service_status_rows_func=None,
    service_record_func=None,
    probe_delivery_func=None,
    display_name_func,
    build_fields_func,
    target_command_records_func,
    set_context_func,
    target_filter_func=None,
    action_callbacks,
    target_callbacks,
    route_service_callbacks,
    probe_callbacks=None,
    file_callbacks,
    job_callbacks,
    session_callbacks,
    queue_callbacks,
    print_daemon_func,
    print_categories_func,
    print_events_func,
    print_release_func,
    append_event_fn,
):
    if target_filter_func is None:
        target_filter = target_callbacks["target_filter"]
        target_filter_func = lambda _cfg: target_filter()

    selected_action_func = action_callbacks["selected_line_action"]
    route_record_func = route_service_callbacks["line_route_record"]
    session_record_func = session_callbacks["line_session_record"]
    job_record_func = job_callbacks["line_job_record"]
    bridge_command_builder = route_service_callbacks["bridge_profile_headless_command"]
    if service_status_rows_func is None:
        service_status_rows_func = lambda _cfg: route_service_callbacks["service_rows"]()
    if service_record_func is None:
        service_record_func = route_service_callbacks["service_record"]
    if probe_delivery_func is None and probe_callbacks is not None:
        probe_delivery_func = probe_callbacks["probe_delivery"]
    print_line_info, print_line_next, print_line_options = build_line_display_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        selected_action_func=selected_action_func,
        service_status_rows_func=service_status_rows_func,
        service_record_func=service_record_func,
        route_record_func=route_record_func,
        session_record_func=session_record_func,
        job_record_func=job_record_func,
        probe_delivery_func=probe_delivery_func,
        bridge_command_builder=bridge_command_builder,
        display_name_func=display_name_func,
        build_fields_func=build_fields_func,
        target_command_records_func=target_command_records_func,
    )
    show_line_resource = build_line_show_resource_adapter(
        cfg,
        set_context_func=set_context_func,
        snapshot_func=workbench_snapshot_func,
        target_filter_func=target_filter_func,
        action_callbacks=action_callbacks,
        target_callbacks=target_callbacks,
        route_service_callbacks=route_service_callbacks,
        file_callbacks=file_callbacks,
        job_callbacks=job_callbacks,
        session_callbacks=session_callbacks,
        queue_callbacks=queue_callbacks,
        display_callbacks=(print_line_info, print_line_next, print_line_options),
        print_daemon_func=print_daemon_func,
        print_categories_func=print_categories_func,
        print_events_func=print_events_func,
        print_release_func=print_release_func,
        append_event_fn=append_event_fn,
    )
    return {
        "print_line_info": print_line_info,
        "print_line_next": print_line_next,
        "print_line_options": print_line_options,
        "show_line_resource": show_line_resource,
    }


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
