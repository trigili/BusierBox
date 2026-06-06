"""Line REPL show-resource callback adapters."""

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.line_actions import print_current_line_module_categories
import gritlib.line_context as line_context
import gritlib.line_daemon as line_daemon
import gritlib.line_release as line_release
from gritlib.line_show import build_line_show_resource_callback
from gritlib.line_repl_display import build_line_display_callbacks
from gritlib.line_services import line_service_display_name
from gritlib.target_activity_display import print_target_activity_records


def build_default_line_display_show_callbacks(
    cfg,
    *,
    line_action_callbacks,
    line_option_callbacks,
    line_target_callbacks,
    line_route_service_callbacks,
    line_probe_callbacks,
    line_file_callbacks,
    line_job_callbacks,
    line_session_callbacks,
    line_queue_callbacks,
):
    return build_line_display_show_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot,
        display_name_func=line_service_display_name,
        set_context_func=line_context.set_line_collection_context,
        action_callbacks=line_action_callbacks,
        option_callbacks=line_option_callbacks,
        target_callbacks=line_target_callbacks,
        route_service_callbacks=line_route_service_callbacks,
        probe_callbacks=line_probe_callbacks,
        file_callbacks=line_file_callbacks,
        job_callbacks=line_job_callbacks,
        session_callbacks=line_session_callbacks,
        queue_callbacks=line_queue_callbacks,
        print_daemon_func=line_daemon.print_line_daemon_actions,
        print_categories_func=print_current_line_module_categories,
        print_events_func=print_target_activity_records,
        print_release_func=line_release.print_line_release,
        append_event_fn=append_event,
    )


def _resolve_display_show_dependencies(
    build_fields_func,
    target_command_records_func,
    target_filter_func,
    option_callbacks,
    target_callbacks,
    route_service_callbacks,
    probe_callbacks,
    service_status_rows_func,
    service_record_func,
    probe_delivery_func,
):
    if build_fields_func is None and option_callbacks is not None:
        build_fields = option_callbacks["workbench_config_fields"]
        build_fields_func = lambda _cfg: build_fields()
    if target_command_records_func is None:
        target_command_records = target_callbacks["target_command_records"]
        target_command_records_func = lambda _cfg: target_command_records()
    if target_filter_func is None:
        target_filter = target_callbacks["target_filter"]
        target_filter_func = lambda _cfg: target_filter()
    if service_status_rows_func is None:
        service_status_rows_func = lambda _cfg: route_service_callbacks["service_rows"]()
    if service_record_func is None:
        service_record_func = route_service_callbacks["service_record"]
    if probe_delivery_func is None and probe_callbacks is not None:
        probe_delivery_func = probe_callbacks["probe_delivery"]
    return {
        "build_fields_func": build_fields_func,
        "target_command_records_func": target_command_records_func,
        "target_filter_func": target_filter_func,
        "service_status_rows_func": service_status_rows_func,
        "service_record_func": service_record_func,
        "probe_delivery_func": probe_delivery_func,
    }


def _build_line_display_triplet(
    cfg,
    workbench_snapshot_func,
    action_callbacks,
    route_service_callbacks,
    session_callbacks,
    job_callbacks,
    display_name_func,
    resolved,
):
    return build_line_display_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        selected_action_func=action_callbacks["selected_line_action"],
        service_status_rows_func=resolved["service_status_rows_func"],
        service_record_func=resolved["service_record_func"],
        route_record_func=route_service_callbacks["line_route_record"],
        session_record_func=session_callbacks["line_session_record"],
        job_record_func=job_callbacks["line_job_record"],
        probe_delivery_func=resolved["probe_delivery_func"],
        bridge_command_builder=route_service_callbacks["bridge_profile_headless_command"],
        display_name_func=display_name_func,
        build_fields_func=resolved["build_fields_func"],
        target_command_records_func=resolved["target_command_records_func"],
    )


def build_line_display_show_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    service_status_rows_func=None,
    service_record_func=None,
    probe_delivery_func=None,
    display_name_func,
    build_fields_func=None,
    target_command_records_func=None,
    set_context_func,
    target_filter_func=None,
    action_callbacks,
    option_callbacks=None,
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
    resolved = _resolve_display_show_dependencies(
        build_fields_func,
        target_command_records_func,
        target_filter_func,
        option_callbacks,
        target_callbacks,
        route_service_callbacks,
        probe_callbacks,
        service_status_rows_func,
        service_record_func,
        probe_delivery_func,
    )
    print_line_info, print_line_next, print_line_options = _build_line_display_triplet(
        cfg,
        workbench_snapshot_func,
        action_callbacks,
        route_service_callbacks,
        session_callbacks,
        job_callbacks,
        display_name_func,
        resolved,
    )
    show_line_resource = build_line_show_resource_adapter(
        cfg,
        set_context_func=set_context_func,
        snapshot_func=workbench_snapshot_func,
        target_filter_func=resolved["target_filter_func"],
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
