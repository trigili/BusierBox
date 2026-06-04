"""Line REPL command queue callback adapters."""

from gritlib.line_command_queue import (
    print_line_command_queue_view,
    queue_line_command,
    run_line_queue_command,
)
from gritlib.line_search import clear_line_search_results, set_line_search_results


def build_line_queue_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    queue_summary_func,
    queue_func,
    clear_queue_func,
    target_filter_func=None,
    target_callbacks=None,
    append_event_fn,
    quote,
):
    if target_filter_func is None and target_callbacks is not None:
        target_filter = target_callbacks["target_filter"]
        target_filter_func = lambda _cfg: target_filter()

    def print_queue_view(detailed=False, mailbox_only=False):
        return print_line_command_queue_view(
            cfg,
            detailed=detailed,
            mailbox_only=mailbox_only,
            snapshot_func=workbench_snapshot_func,
            queue_summary_func=queue_summary_func,
            clear_results_func=clear_line_search_results,
            set_results_func=set_line_search_results,
            append_event_fn=append_event_fn,
            quote=quote,
        )

    def queue_command(command):
        return queue_line_command(
            cfg,
            command,
            queue_func,
            target_filter_func=target_filter_func,
            quote=quote,
        )

    def clear_selectable_results():
        return clear_line_search_results(cfg)

    def run_queue_command(args):
        return run_line_queue_command(
            cfg,
            args,
            queue_summary_func=queue_summary_func,
            queue_func=queue_func,
            clear_queue_func=clear_queue_func,
            view_func=print_queue_view,
            target_filter_func=target_filter_func,
            clear_selectable_results_func=clear_selectable_results,
            quote=quote,
        )

    return {
        "clear_line_selectable_results": clear_selectable_results,
        "print_line_command_queue_view": print_queue_view,
        "queue_line_command": queue_command,
        "run_line_queue_command": run_queue_command,
    }
