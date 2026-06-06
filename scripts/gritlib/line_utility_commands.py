"""Grouped line-console utility command dispatch."""

from gritlib.line_command_registry import dispatch_line_command_families
from gritlib.line_completions import parse_line_completion_command
from gritlib.line_events import dispatch_line_events_command, parse_line_events_command
from gritlib.line_resources import dispatch_line_resource_command, parse_line_resource_command
from gritlib.line_search import dispatch_line_search_command, parse_line_search_command
from gritlib.line_show import dispatch_line_show_command, parse_line_show_command
from gritlib.line_target_commands import (
    dispatch_line_copy_command,
    dispatch_line_generated_commands_command,
    parse_line_copy_command,
    parse_line_generated_commands_command,
)


def _dispatch_line_completion_family(cmd, args, callbacks):
    completion_cmd = parse_line_completion_command(cmd, args)
    if not completion_cmd:
        return False
    completion_func = callbacks.get("completion_func")
    if completion_func:
        completion_func(completion_cmd["prefix"])
    return True


def _dispatch_line_resource_family(cmd, args, callbacks):
    resource_cmd = parse_line_resource_command(cmd, args)
    if not resource_cmd:
        return False
    dispatch_line_resource_command(
        resource_cmd,
        history_func=callbacks.get("resource_history_func"),
        load_func=callbacks.get("resource_load_func"),
        save_func=callbacks.get("resource_save_func"),
    )
    return True


def _dispatch_line_events_family(cmd, args, callbacks):
    events_cmd = parse_line_events_command(
        cmd,
        args,
        module=callbacks.get("module"),
    )
    if not events_cmd:
        return False
    dispatch_line_events_command(
        events_cmd,
        print_func=callbacks.get("events_func"),
    )
    return True


def _dispatch_line_search_family(cmd, args, callbacks):
    search_cmd = parse_line_search_command(cmd, args)
    if not search_cmd:
        return False
    dispatch_line_search_command(
        search_cmd,
        search_func=callbacks.get("search_func"),
    )
    return True


def _dispatch_line_show_family(cmd, args, callbacks):
    show_cmd = parse_line_show_command(cmd, args)
    if not show_cmd:
        return False
    dispatch_line_show_command(
        show_cmd,
        show_func=callbacks.get("show_func"),
    )
    return True


def _dispatch_line_generated_commands_family(cmd, args, callbacks):
    commands_cmd = parse_line_generated_commands_command(cmd, args)
    if not commands_cmd:
        return False
    dispatch_line_generated_commands_command(
        commands_cmd,
        run_func=callbacks.get("generated_run_func"),
    )
    return True


def _dispatch_line_copy_family(cmd, args, callbacks):
    copy_cmd = parse_line_copy_command(cmd, args)
    if not copy_cmd:
        return False
    dispatch_line_copy_command(
        copy_cmd,
        service_copy_func=callbacks.get("service_copy_func"),
        generated_copy_func=callbacks.get("generated_copy_func"),
    )
    return True


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
    generated_run_func=None,
    service_copy_func=None,
    generated_copy_func=None,
    module="",
):
    """Dispatch command groups that do not mutate console context directly."""
    args = list(args or [])
    callbacks = locals()
    return bool(dispatch_line_command_families(
        (
            _dispatch_line_completion_family,
            _dispatch_line_resource_family,
            _dispatch_line_events_family,
            _dispatch_line_search_family,
            _dispatch_line_show_family,
            _dispatch_line_generated_commands_family,
            _dispatch_line_copy_family,
        ),
        cmd,
        args,
        callbacks,
        default=False,
    ))
