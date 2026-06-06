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


def _dispatch_listener_navigation(nav):
    if listener_cmd := parse_line_listener_command(nav["cmd"], nav["args"]):
        dispatch_line_listener_command(
            listener_cmd,
            list_func=lambda verbose=False: (
                nav["set_listeners_context_func"](),
                nav["print_listeners_func"](verbose=verbose),
            ),
            select_func=nav["select_listener_func"],
        )
        return True
    return False


def _dispatch_target_navigation(nav):
    if target_cmd := parse_line_target_command(nav["cmd"], nav["args"]):
        dispatch_line_target_command(
            target_cmd,
            list_func=lambda: (
                nav["set_targets_context_func"](),
                nav["print_targets_func"](),
            ),
            select_func=nav["select_target_func"],
        )
        return True
    return False


def _dispatch_session_navigation(nav):
    if session_cmd := parse_line_sessions_command(
        nav["cmd"],
        nav["args"],
        module=nav["module"],
    ):
        dispatch_line_sessions_command(
            session_cmd,
            clear_func=nav["clear_sessions_func"],
            help_func=nav["session_help_func"],
            interact_func=nav["interact_session_func"],
            list_func=lambda verbose=False: (
                nav["set_sessions_context_func"](),
                nav["print_sessions_func"](verbose=verbose),
            ),
        )
        return True
    return False


def _dispatch_route_navigation(nav):
    if route_cmd := parse_line_route_command(
        nav["cmd"],
        nav["args"],
        module=nav["module"],
    ):
        dispatch_line_route_command(
            route_cmd,
            add_func=nav["add_route_func"],
            start_func=nav["start_route_func"],
            stop_func=nav["stop_route_func"],
            delete_func=nav["delete_route_func"],
            help_func=nav["route_help_func"],
            select_func=nav["select_route_func"],
            list_func=lambda verbose=False: (
                nav["set_routes_context_func"](),
                nav["print_routes_func"](verbose=verbose),
            ),
        )
        return True
    return False


def _dispatch_use_navigation(nav):
    if use_cmd := parse_line_use_command(nav["cmd"], nav["args"]):
        dispatch_line_use_command(
            use_cmd,
            alias_recorder=nav["record_alias_func"],
            number_func=nav["number_func"],
            target_func=nav["select_target_func"],
            listener_func=nav["select_listener_func"],
            route_func=nav["select_route_func"],
            session_func=nav["select_session_func"],
            job_func=nav["select_job_func"],
            action_func=nav["select_action_func"],
            after_number_func=nav["clear_results_func"],
        )
        return True
    return False


def _dispatch_context_navigation(nav):
    if context_cmd := parse_line_context_command(nav["cmd"], nav["args"]):
        dispatch_line_context_command(
            context_cmd,
            clear_target_func=nav["clear_target_func"],
            root_func=nav["root_func"],
            back_func=nav["back_func"],
        )
        return True
    return False


def _dispatch_service_navigation(nav):
    if nav["module"] == "daemon":
        return False
    if service_cmd := parse_line_service_control_command(nav["cmd"], nav["args"]):
        dispatch_line_service_control_command(
            service_cmd,
            start_func=nav["start_service_func"],
            stop_func=nav["stop_service_func"],
        )
        return True
    return False


def _dispatch_action_navigation(nav):
    if action_cmd := parse_line_action_command(nav["cmd"], nav["args"]):
        dispatch_line_action_command(
            action_cmd,
            alias_recorder=nav["record_alias_func"],
            start_job_func=nav["start_job_func"],
            cancel_job_func=nav["cancel_job_func"],
            run_func=nav["run_action_func"],
        )
        return True
    return False


def _dispatch_interact_navigation(nav):
    if interact_cmd := parse_line_interact_command(
        nav["cmd"],
        nav["args"],
        target_selected=nav["target_selected"],
        module=nav["module"],
    ):
        dispatch_line_interact_command(
            interact_cmd,
            target_func=nav["interact_target_func"],
            session_func=nav["interact_session_func"],
        )
        return True
    return False


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
    nav = locals()
    for dispatch_func in (
        _dispatch_listener_navigation,
        _dispatch_target_navigation,
        _dispatch_session_navigation,
        _dispatch_route_navigation,
        _dispatch_use_navigation,
        _dispatch_context_navigation,
        _dispatch_service_navigation,
        _dispatch_action_navigation,
        _dispatch_interact_navigation,
    ):
        if dispatch_func(nav):
            return True
    return False
