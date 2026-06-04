"""Line REPL session callback adapters."""

from gritlib.line_sessions import (
    clear_line_sessions,
    current_line_session_record,
    interact_current_line_session,
    print_current_line_sessions,
    select_current_line_session,
)


def build_line_session_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    session_root_func,
    view_command_builder,
    append_event_fn,
    quote,
):
    def snapshot():
        return workbench_snapshot_func(cfg)

    def line_session_record(selector):
        return current_line_session_record(snapshot, selector)

    def select_line_session(selector):
        return select_current_line_session(
            cfg,
            snapshot,
            selector,
            append_event_fn=append_event_fn,
        )

    def print_line_sessions(verbose=False):
        return print_current_line_sessions(
            cfg,
            snapshot,
            verbose=verbose,
            view_command=view_command_builder,
            quote=quote,
            append_event_fn=append_event_fn,
        )

    def clear_sessions(all_sessions=False, confirm=False):
        return clear_line_sessions(
            cfg,
            session_root_func(cfg),
            all_sessions=all_sessions,
            confirm=confirm,
            append_event_fn=append_event_fn,
        )

    def interact_line_session(selector):
        return interact_current_line_session(
            cfg,
            snapshot,
            selector,
            view_command_builder=view_command_builder,
            append_event_fn=append_event_fn,
        )

    return {
        "line_session_record": line_session_record,
        "select_line_session": select_line_session,
        "print_line_sessions": print_line_sessions,
        "clear_line_sessions": clear_sessions,
        "interact_line_session": interact_line_session,
    }
