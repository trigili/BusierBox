"""Line REPL search callback adapters."""

from gritlib.line_actions import current_line_action_records
from gritlib.line_configure import run_line_probe_config
from gritlib.line_search import (
    clear_line_search_results,
    line_search_results,
    run_line_search,
    use_line_search_result,
)
from gritlib.workbench_jobs import cancel_workbench_job_headless_command


def build_line_search_bundle(
    cfg,
    *,
    workbench_snapshot_func,
    service_records_func,
    route_records_func,
    route_command_builder,
    target_callbacks,
    route_service_callbacks,
    action_callbacks,
    session_callbacks,
    job_callbacks,
    queue_callbacks=None,
    append_event_fn,
    quote,
):
    return build_line_search_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        service_records_func=service_records_func,
        route_records_func=route_records_func,
        route_command_builder=route_command_builder,
        select_target_func=target_callbacks["select_line_target"],
        select_service_func=route_service_callbacks["select_line_service"],
        select_route_func=route_service_callbacks["select_line_route"],
        select_action_func=action_callbacks["select_line_action"],
        select_queue_action_func=(
            (queue_callbacks or {}).get("select_line_command_queue_action")
            or action_callbacks["select_line_command_queue_action"]
        ),
        select_session_func=session_callbacks["select_line_session"],
        select_job_func=job_callbacks["select_line_job"],
        append_event_fn=append_event_fn,
        quote=quote,
    )


def build_line_search_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    service_records_func,
    route_records_func,
    route_command_builder,
    select_target_func,
    select_service_func,
    select_route_func,
    select_action_func,
    select_queue_action_func,
    select_session_func,
    select_job_func,
    append_event_fn,
    quote,
):
    def snapshot():
        return workbench_snapshot_func(cfg)

    def search_line_resources(query):
        run_line_search(
            cfg,
            query,
            snapshot=snapshot(),
            service_records=service_records_func(cfg),
            route_records=route_records_func(cfg),
            action_records=current_line_action_records(snapshot),
            route_command_builder=route_command_builder,
            job_cancel_command_builder=lambda job_id: cancel_workbench_job_headless_command(cfg, job_id),
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
            probe_result_config=lambda args: run_line_probe_config(
                cfg,
                args,
                append_event_fn=append_event_fn,
            ),
        )

    def clear_search_results():
        return clear_line_search_results(cfg)

    return {
        "clear_line_search_results": clear_search_results,
        "search_line_resources": search_line_resources,
        "use_line_search_result": use_search_result,
    }
