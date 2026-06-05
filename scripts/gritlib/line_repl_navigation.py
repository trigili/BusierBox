"""Line REPL navigation command callback adapters."""

from gritlib.event_log import append_event
import gritlib.line_context as line_context
import gritlib.line_help as line_help
from gritlib.line_navigation_commands import dispatch_line_navigation_command
from gritlib.line_search import clear_line_search_results


def build_default_line_navigation_callbacks(
    cfg,
    *,
    line_search_callbacks,
    line_target_callbacks,
    line_route_service_callbacks,
    line_session_callbacks,
    line_job_callbacks,
    line_action_callbacks,
    line_queue_callbacks,
):
    return build_line_navigation_callbacks(
        cfg,
        append_event_fn=append_event,
        clear_results_func=clear_line_search_results,
        set_context_func=line_context.set_line_collection_context,
        clear_console_context_func=line_context.clear_line_console_context,
        back_func=line_context.back_line_module_context,
        session_help_func=line_help.print_line_command_help,
        route_help_func=line_help.print_line_command_help,
        search_callbacks=line_search_callbacks,
        target_callbacks=line_target_callbacks,
        route_service_callbacks=line_route_service_callbacks,
        session_callbacks=line_session_callbacks,
        job_callbacks=line_job_callbacks,
        action_callbacks=line_action_callbacks,
        queue_callbacks=line_queue_callbacks,
    )


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


def _record_navigation_alias(ctx, alias, canonical):
    ctx["append_event_fn"](
        ctx["cfg"],
        "workbench",
        "workbench_console_alias_used",
        details={
            "alias": str(alias or ""),
            "canonical": str(canonical or ""),
        },
    )


def _select_navigation_number(ctx, selector):
    module = str(ctx["cfg"].get("_line_console_module") or "")
    if module.startswith("queue") and ctx["select_queue_action_func"]:
        return ctx["select_queue_action_func"](selector)
    return ctx["number_func"](selector)


def _navigation_context_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "target_selected": bool(ctx["target_filter_func"](cfg)),
        "module": cfg.get("_line_console_module"),
        "record_alias_func": lambda alias, canonical: _record_navigation_alias(ctx, alias, canonical),
        "clear_results_func": lambda: ctx["clear_results_func"](cfg),
        "set_listeners_context_func": lambda: ctx["set_context_func"](cfg, "listeners"),
        "print_listeners_func": ctx["print_listeners_func"],
        "select_listener_func": ctx["select_listener_func"],
        "set_targets_context_func": lambda: ctx["set_context_func"](cfg, "targets"),
        "print_targets_func": ctx["print_targets_func"],
        "select_target_func": ctx["select_target_func"],
        "set_sessions_context_func": lambda: ctx["set_context_func"](cfg, "sessions"),
        "print_sessions_func": ctx["print_sessions_func"],
        "clear_sessions_func": ctx["clear_sessions_func"],
        "session_help_func": ctx["session_help_func"],
        "select_session_func": ctx["select_session_func"],
        "interact_session_func": ctx["interact_session_func"],
    }


def _navigation_route_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "set_routes_context_func": lambda: ctx["set_context_func"](cfg, "routes"),
        "print_routes_func": ctx["print_routes_func"],
        "add_route_func": ctx["add_route_func"],
        "start_route_func": ctx["start_route_func"],
        "stop_route_func": ctx["stop_route_func"],
        "delete_route_func": ctx["delete_route_func"],
        "route_help_func": ctx["route_help_func"],
        "select_route_func": ctx["select_route_func"],
    }


def _navigation_action_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "number_func": lambda selector: _select_navigation_number(ctx, selector),
        "select_job_func": ctx["select_job_func"],
        "select_action_func": ctx["select_action_func"],
        "clear_target_func": lambda: ctx["select_target_func"]("all", targets=[]),
        "root_func": lambda quiet=False: ctx["clear_console_context_func"](cfg, quiet=quiet),
        "back_func": lambda: ctx["back_func"](cfg),
        "start_service_func": ctx["start_service_func"],
        "stop_service_func": ctx["stop_service_func"],
        "start_job_func": ctx["start_job_func"],
        "cancel_job_func": ctx["cancel_job_func"],
        "run_action_func": ctx["run_action_func"],
        "interact_target_func": ctx["interact_target_func"],
    }


def _navigation_dispatch_kwargs(ctx):
    kwargs = {}
    kwargs.update(_navigation_context_dispatch_kwargs(ctx))
    kwargs.update(_navigation_route_dispatch_kwargs(ctx))
    kwargs.update(_navigation_action_dispatch_kwargs(ctx))
    return kwargs


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
    ctx = locals()

    def dispatch_navigation(command, args):
        return dispatch_line_navigation_command(
            command,
            args,
            **_navigation_dispatch_kwargs(ctx),
        )

    return dispatch_navigation
