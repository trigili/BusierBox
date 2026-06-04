"""Grouped line-console navigation and action dispatch."""

from gritlib.bridge_routes import dispatch_line_route_command, parse_line_route_command
from gritlib.line_actions import dispatch_line_action_command, parse_line_action_command
from gritlib.line_context import (
    dispatch_line_context_command,
    dispatch_line_interact_command,
    dispatch_line_use_command,
    parse_line_context_command,
    parse_line_interact_command,
    parse_line_use_command,
)
from gritlib.line_services import (
    dispatch_line_listener_command,
    dispatch_line_service_control_command,
    parse_line_listener_command,
    parse_line_service_control_command,
)
from gritlib.line_sessions import dispatch_line_sessions_command, parse_line_sessions_command
from gritlib.line_targets import dispatch_line_target_command, parse_line_target_command


def dispatch_line_navigation_command(
    cmd,
    args,
    *,
    target_selected=False,
    module="",
    record_alias_func=None,
    clear_results_func=None,
    set_listeners_context_func=None,
    print_listeners_func=None,
    select_listener_func=None,
    set_targets_context_func=None,
    print_targets_func=None,
    select_target_func=None,
    set_sessions_context_func=None,
    print_sessions_func=None,
    clear_sessions_func=None,
    session_help_func=None,
    select_session_func=None,
    interact_session_func=None,
    set_routes_context_func=None,
    print_routes_func=None,
    add_route_func=None,
    start_route_func=None,
    stop_route_func=None,
    delete_route_func=None,
    route_help_func=None,
    select_route_func=None,
    number_func=None,
    select_job_func=None,
    select_action_func=None,
    clear_target_func=None,
    root_func=None,
    back_func=None,
    start_service_func=None,
    stop_service_func=None,
    start_job_func=None,
    cancel_job_func=None,
    run_action_func=None,
    interact_target_func=None,
):
    args = list(args or [])
    if listener_cmd := parse_line_listener_command(cmd, args):
        dispatch_line_listener_command(
            listener_cmd,
            list_func=lambda verbose=False: (
                set_listeners_context_func(),
                print_listeners_func(verbose=verbose),
            ),
            select_func=select_listener_func,
        )
        return True
    if target_cmd := parse_line_target_command(cmd, args):
        dispatch_line_target_command(
            target_cmd,
            list_func=lambda: (
                set_targets_context_func(),
                print_targets_func(),
            ),
            select_func=select_target_func,
        )
        return True
    if session_cmd := parse_line_sessions_command(cmd, args):
        dispatch_line_sessions_command(
            session_cmd,
            clear_func=clear_sessions_func,
            help_func=session_help_func,
            interact_func=interact_session_func,
            list_func=lambda verbose=False: (
                set_sessions_context_func(),
                print_sessions_func(verbose=verbose),
            ),
        )
        return True
    if route_cmd := parse_line_route_command(cmd, args):
        dispatch_line_route_command(
            route_cmd,
            add_func=add_route_func,
            start_func=start_route_func,
            stop_func=stop_route_func,
            delete_func=delete_route_func,
            help_func=route_help_func,
            select_func=select_route_func,
            list_func=lambda verbose=False: (
                set_routes_context_func(),
                print_routes_func(verbose=verbose),
            ),
        )
        return True
    if use_cmd := parse_line_use_command(cmd, args):
        dispatch_line_use_command(
            use_cmd,
            alias_recorder=record_alias_func,
            number_func=number_func,
            target_func=select_target_func,
            listener_func=select_listener_func,
            route_func=select_route_func,
            session_func=select_session_func,
            job_func=select_job_func,
            action_func=select_action_func,
            after_number_func=clear_results_func,
        )
        return True
    if context_cmd := parse_line_context_command(cmd, args):
        dispatch_line_context_command(
            context_cmd,
            clear_target_func=clear_target_func,
            root_func=root_func,
            back_func=back_func,
        )
        return True
    if service_cmd := parse_line_service_control_command(cmd, args):
        dispatch_line_service_control_command(
            service_cmd,
            start_func=start_service_func,
            stop_func=stop_service_func,
        )
        return True
    if action_cmd := parse_line_action_command(cmd, args):
        dispatch_line_action_command(
            action_cmd,
            alias_recorder=record_alias_func,
            start_job_func=start_job_func,
            cancel_job_func=cancel_job_func,
            run_func=run_action_func,
        )
        return True
    if interact_cmd := parse_line_interact_command(
        cmd,
        args,
        target_selected=target_selected,
        module=module,
    ):
        dispatch_line_interact_command(
            interact_cmd,
            target_func=interact_target_func,
            session_func=interact_session_func,
        )
        return True
    return False
