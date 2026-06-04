"""Line REPL navigation command callback adapters."""

from gritlib.line_navigation_commands import dispatch_line_navigation_command


def build_line_navigation_callbacks(
    cfg,
    *,
    target_filter_func=None,
    append_event_fn,
    clear_results_func,
    set_context_func,
    clear_console_context_func,
    back_func,
    session_help_func,
    route_help_func,
    number_func=None,
    target_callbacks,
    route_service_callbacks,
    session_callbacks,
    job_callbacks,
    action_callbacks,
    queue_callbacks=None,
    search_callbacks=None,
):
    if target_filter_func is None:
        target_filter = target_callbacks["target_filter"]
        target_filter_func = lambda _cfg: target_filter()
    if number_func is None and search_callbacks is not None:
        number_func = search_callbacks["use_line_search_result"]
    dispatch_navigation = build_line_navigation_dispatch_callback(
        cfg,
        target_filter_func=target_filter_func,
        append_event_fn=append_event_fn,
        clear_results_func=clear_results_func,
        set_context_func=set_context_func,
        print_listeners_func=route_service_callbacks["print_line_services"],
        select_listener_func=route_service_callbacks["select_line_service"],
        print_targets_func=target_callbacks["print_line_targets"],
        select_target_func=target_callbacks["select_line_target"],
        print_sessions_func=session_callbacks["print_line_sessions"],
        clear_sessions_func=session_callbacks["clear_line_sessions"],
        session_help_func=session_help_func,
        select_session_func=session_callbacks["select_line_session"],
        interact_session_func=session_callbacks["interact_line_session"],
        print_routes_func=route_service_callbacks["print_line_routes"],
        add_route_func=route_service_callbacks["add_line_route"],
        start_route_func=route_service_callbacks["start_line_route"],
        stop_route_func=route_service_callbacks["stop_line_route"],
        delete_route_func=route_service_callbacks["delete_line_route"],
        route_help_func=route_help_func,
        select_route_func=route_service_callbacks["select_line_route"],
        number_func=number_func,
        select_queue_action_func=(
            (queue_callbacks or {}).get("select_line_command_queue_action")
            or action_callbacks.get("select_line_command_queue_action")
        ),
        select_job_func=job_callbacks["select_line_job"],
        select_action_func=action_callbacks["select_line_action"],
        clear_console_context_func=clear_console_context_func,
        back_func=back_func,
        start_service_func=route_service_callbacks["start_line_service"],
        stop_service_func=route_service_callbacks["stop_line_service"],
        start_job_func=job_callbacks["start_line_job"],
        cancel_job_func=job_callbacks["cancel_line_job"],
        run_action_func=action_callbacks["run_line_module_or_service"],
        interact_target_func=target_callbacks["interact_line_target"],
    )
    return {"dispatch_line_navigation": dispatch_navigation}


def build_line_navigation_dispatch_callback(
    cfg,
    *,
    target_filter_func,
    append_event_fn,
    clear_results_func,
    set_context_func,
    print_listeners_func,
    select_listener_func,
    print_targets_func,
    select_target_func,
    print_sessions_func,
    clear_sessions_func,
    session_help_func,
    select_session_func,
    interact_session_func,
    print_routes_func,
    add_route_func,
    start_route_func,
    stop_route_func,
    delete_route_func,
    route_help_func,
    select_route_func,
    number_func,
    select_job_func,
    select_action_func,
    clear_console_context_func,
    back_func,
    start_service_func,
    stop_service_func,
    start_job_func,
    cancel_job_func,
    run_action_func,
    interact_target_func,
    select_queue_action_func=None,
):
    def record_alias(alias, canonical):
        append_event_fn(
            cfg,
            "workbench",
            "workbench_console_alias_used",
            details={
                "alias": str(alias or ""),
                "canonical": str(canonical or ""),
            },
        )

    def dispatch_navigation(command, args):
        def select_number(selector):
            module = str(cfg.get("_line_console_module") or "")
            if module.startswith("queue") and select_queue_action_func:
                return select_queue_action_func(selector)
            return number_func(selector)

        return dispatch_line_navigation_command(
            command,
            args,
            target_selected=bool(target_filter_func(cfg)),
            module=cfg.get("_line_console_module"),
            record_alias_func=record_alias,
            clear_results_func=lambda: clear_results_func(cfg),
            set_listeners_context_func=lambda: set_context_func(cfg, "listeners"),
            print_listeners_func=print_listeners_func,
            select_listener_func=select_listener_func,
            set_targets_context_func=lambda: set_context_func(cfg, "targets"),
            print_targets_func=print_targets_func,
            select_target_func=select_target_func,
            set_sessions_context_func=lambda: set_context_func(cfg, "sessions"),
            print_sessions_func=print_sessions_func,
            clear_sessions_func=clear_sessions_func,
            session_help_func=session_help_func,
            select_session_func=select_session_func,
            interact_session_func=interact_session_func,
            set_routes_context_func=lambda: set_context_func(cfg, "routes"),
            print_routes_func=print_routes_func,
            add_route_func=add_route_func,
            start_route_func=start_route_func,
            stop_route_func=stop_route_func,
            delete_route_func=delete_route_func,
            route_help_func=route_help_func,
            select_route_func=select_route_func,
            number_func=select_number,
            select_job_func=select_job_func,
            select_action_func=select_action_func,
            clear_target_func=lambda: select_target_func("all", targets=[]),
            root_func=lambda quiet=False: clear_console_context_func(cfg, quiet=quiet),
            back_func=lambda: back_func(cfg),
            start_service_func=start_service_func,
            stop_service_func=stop_service_func,
            start_job_func=start_job_func,
            cancel_job_func=cancel_job_func,
            run_action_func=run_action_func,
            interact_target_func=interact_target_func,
        )

    return dispatch_navigation
