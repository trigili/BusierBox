"""Line REPL search callback adapters."""

from gritlib.line_search import (
    line_search_results,
    run_line_search,
    use_line_search_result,
)


def build_line_search_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    service_records_func,
    route_records_func,
    action_records_func,
    route_command_builder,
    job_cancel_command_builder,
    select_target_func,
    select_service_func,
    select_route_func,
    select_action_func,
    select_queue_action_func,
    select_session_func,
    select_job_func,
    probe_result_config_func,
    append_event_fn,
    quote,
):
    def search_line_resources(query):
        run_line_search(
            cfg,
            query,
            snapshot=workbench_snapshot_func(cfg),
            service_records=service_records_func(cfg),
            route_records=route_records_func(cfg),
            action_records=action_records_func(),
            route_command_builder=route_command_builder,
            job_cancel_command_builder=job_cancel_command_builder,
            quote=quote,
            append_event_fn=append_event_fn,
        )

    def use_search_result(selector):
        return use_line_search_result(
            selector,
            line_search_results(cfg),
            select_target=select_target_func,
            select_service=select_service_func,
            select_route=select_route_func,
            select_action=select_action_func,
            select_queue_action=select_queue_action_func,
            select_session=select_session_func,
            select_job=select_job_func,
            probe_result_config=probe_result_config_func,
        )

    return {
        "search_line_resources": search_line_resources,
        "use_line_search_result": use_search_result,
    }
