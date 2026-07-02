"""Grouped line-console utility command dispatch."""

from gritlib.line_completions import parse_line_completion_command
from gritlib.line_events import dispatch_line_events_command, parse_line_events_command
from gritlib.line_help import print_line_command_help
from gritlib.line_resources import dispatch_line_resource_command, parse_line_resource_command
from gritlib.line_search import dispatch_line_search_command, parse_line_search_command
from gritlib.line_show import dispatch_line_show_command, parse_line_show_command
from gritlib.line_target_commands import (
    dispatch_line_copy_command,
    dispatch_line_generated_commands_command,
    parse_line_copy_command,
    parse_line_generated_commands_command,
    parse_line_service_show_command,
)


def dispatch_line_utility_command(
    cmd,
    args,
    *,
    completion_func=None,
    resource_history_func=None,
    resource_load_func=None,
    resource_save_func=None,
    events_func=None,
    search_func=None,
    show_func=None,
    service_show_func=None,
    generated_run_func=None,
    service_copy_func=None,
    generated_copy_func=None,
    set_context_func=None,
):
    """Dispatch command groups that do not mutate console context directly."""
    args = list(args or [])
    if str(cmd or "").strip().lower() == "console":
        if set_context_func:
            set_context_func("console")
        print_line_command_help("console")
        return True
    if str(cmd or "").strip().lower() == "aliases":
        if set_context_func:
            set_context_func("aliases")
        print_line_command_help("aliases")
        return True
    if str(cmd or "").strip().lower() == "workflow":
        if set_context_func:
            set_context_func("workflow")
        print_line_command_help("workflow")
        return True
    if completion_cmd := parse_line_completion_command(cmd, args):
        if completion_func:
            completion_func(completion_cmd["prefix"])
        return True
    if resource_cmd := parse_line_resource_command(cmd, args):
        dispatch_line_resource_command(
            resource_cmd,
            history_func=resource_history_func,
            load_func=resource_load_func,
            save_func=resource_save_func,
        )
        return True
    if events_cmd := parse_line_events_command(cmd, args):
        if set_context_func:
            set_context_func("events")
        dispatch_line_events_command(events_cmd, print_func=events_func)
        return True
    if search_cmd := parse_line_search_command(cmd, args):
        if set_context_func:
            set_context_func("search")
        dispatch_line_search_command(search_cmd, search_func=search_func)
        return True
    if service_show_cmd := parse_line_service_show_command(cmd, args):
        if service_show_func:
            service_show_func(service_show_cmd.get("subcmd", ""))
        return True
    if show_cmd := parse_line_show_command(cmd, args):
        dispatch_line_show_command(show_cmd, show_func=show_func)
        return True
    if commands_cmd := parse_line_generated_commands_command(cmd, args):
        if set_context_func:
            set_context_func("commands")
        dispatch_line_generated_commands_command(
            commands_cmd,
            run_func=generated_run_func,
        )
        return True
    if copy_cmd := parse_line_copy_command(cmd, args):
        dispatch_line_copy_command(
            copy_cmd,
            service_copy_func=service_copy_func,
            generated_copy_func=generated_copy_func,
        )
        return True
    return False
