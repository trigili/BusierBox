"""Line-console daemon action helpers for grit-console."""

from gritlib.workflow_actions import (
    print_line_daemon_action_records,
    run_line_daemon_action as dispatch_line_daemon_action,
)


def print_line_daemon_actions(snapshot, verbose=False):
    actions = (snapshot or {}).get("operator_daemon_workflow_actions") or []
    return print_line_daemon_action_records(actions, verbose=verbose)


def run_line_daemon_action(args, *, snapshot_func=None, run_action_func=None):
    return dispatch_line_daemon_action(
        args,
        print_actions_func=lambda verbose=False: print_line_daemon_actions(
            snapshot_func() if snapshot_func else {},
            verbose=verbose,
        ),
        run_action_func=run_action_func,
    )
