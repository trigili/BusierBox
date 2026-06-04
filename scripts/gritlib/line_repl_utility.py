"""Line REPL utility command callback adapters."""

from gritlib.line_utility_commands import dispatch_line_utility_command


def build_line_utility_callbacks(
    cfg,
    *,
    completion_func=None,
    resource_history_func,
    resource_load_func,
    resource_save_func,
    events_func,
    search_func=None,
    show_func=None,
    generated_run_func,
    copy_text_func,
    service_start_command_func=None,
    service_stop_command_func=None,
    service_copy_command_func,
    generated_copy_func,
    completion_callbacks=None,
    search_callbacks=None,
    display_callbacks=None,
    route_service_callbacks=None,
):
    if completion_func is None and completion_callbacks is not None:
        completion_func = completion_callbacks["print_line_completions"]
    if search_func is None and search_callbacks is not None:
        search_func = search_callbacks["search_line_resources"]
    if show_func is None and display_callbacks is not None:
        show_func = display_callbacks["show_line_resource"]
    if route_service_callbacks is not None:
        if service_start_command_func is None:
            service_start_command = route_service_callbacks["service_start_command"]
            service_start_command_func = lambda _cfg, service: service_start_command(service)
        if service_stop_command_func is None:
            service_stop_command = route_service_callbacks["service_stop_command"]
            service_stop_command_func = lambda _cfg, service: service_stop_command(service)
    pending_console_lines = []
    line_history = []
    dispatch_utility = build_line_utility_dispatch_callback(
        cfg,
        line_history=line_history,
        pending_console_lines=pending_console_lines,
        completion_func=completion_func,
        resource_history_func=resource_history_func,
        resource_load_func=resource_load_func,
        resource_save_func=resource_save_func,
        events_func=events_func,
        search_func=search_func,
        show_func=show_func,
        generated_run_func=generated_run_func,
        copy_text_func=copy_text_func,
        service_start_command_func=service_start_command_func,
        service_stop_command_func=service_stop_command_func,
        service_copy_command_func=service_copy_command_func,
        generated_copy_func=generated_copy_func,
    )
    return {
        "dispatch_line_utility": dispatch_utility,
        "line_history": line_history,
        "pending_console_lines": pending_console_lines,
    }


def build_line_utility_dispatch_callback(
    cfg,
    *,
    line_history,
    pending_console_lines,
    completion_func,
    resource_history_func,
    resource_load_func,
    resource_save_func,
    events_func,
    search_func,
    show_func,
    generated_run_func,
    copy_text_func,
    service_start_command_func,
    service_stop_command_func,
    service_copy_command_func,
    generated_copy_func,
):
    def dispatch_utility(command, args):
        return dispatch_line_utility_command(
            command,
            args,
            completion_func=completion_func,
            resource_history_func=lambda limit="": resource_history_func(
                line_history,
                limit,
            ),
            resource_load_func=lambda path: pending_console_lines.extend(
                resource_load_func(cfg, path)
            ),
            resource_save_func=lambda path: resource_save_func(cfg, path, line_history),
            events_func=lambda event_args: events_func(cfg, event_args),
            search_func=search_func,
            show_func=show_func,
            generated_run_func=lambda generated_args: generated_run_func(cfg, generated_args),
            service_copy_func=lambda subcmd: service_copy_command_func(
                cfg,
                subcmd,
                lambda command_text, label: copy_text_func(
                    cfg,
                    command_text,
                    label=label,
                ),
                start_command=lambda service: service_start_command_func(cfg, service),
                stop_command=lambda service: service_stop_command_func(cfg, service),
            ),
            generated_copy_func=lambda selector: generated_copy_func(
                cfg,
                selector,
            ),
        )

    return dispatch_utility
