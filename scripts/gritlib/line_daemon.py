"""Line-console daemon action helpers for grit-console."""

from gritlib.workflow_actions import (
    print_line_daemon_action_records,
    run_line_daemon_action as dispatch_line_daemon_action,
)


def print_line_daemon_actions(snapshot, verbose=False):
    actions = (snapshot or {}).get("operator_daemon_workflow_actions") or []
    return print_line_daemon_action_records(actions, verbose=verbose)


def _line_daemon_action_record(snapshot, selector):
    selected = str(selector or "").strip()
    if not selected:
        return {}
    for rec in (snapshot or {}).get("operator_daemon_workflow_actions") or []:
        rec_id = str(rec.get("id") or rec.get("action_id") or "")
        systemd_action = str(rec.get("systemd_user_action") or "")
        if selected in {rec_id, rec.get("workbench_action_id"), systemd_action}:
            return rec
    return {}


def _confirm_line_daemon_action(rec, input_func):
    action_id = str((rec or {}).get("id") or (rec or {}).get("action_id") or "daemon action")
    label = str((rec or {}).get("label") or action_id)
    command = str((rec or {}).get("run_command") or (rec or {}).get("headless_command") or "")
    print(f"Daemon action: {label}")
    if command:
        print(f"  command: {command}")
    answer = str(input_func("Run this action? [y/N] ") or "").strip().lower()
    return answer in {"y", "yes"}


def run_line_daemon_action(args, *, snapshot_func=None, run_action_func=None, input_func=input):
    def run_confirmed_if_needed(selector, dry_run=False, confirmed=False, show_commands=False):
        snapshot = snapshot_func() if snapshot_func else {}
        rec = _line_daemon_action_record(snapshot, selector)
        if (
                rec.get("requires_confirmation") is True
                and not dry_run
                and not confirmed):
            if not _confirm_line_daemon_action(rec, input_func):
                print("Cancelled.")
                return 0
            confirmed = True
        return run_action_func(
            selector,
            dry_run=dry_run,
            confirmed=confirmed,
            show_commands=show_commands,
        )

    return dispatch_line_daemon_action(
        args,
        print_actions_func=lambda verbose=False: print_line_daemon_actions(
            snapshot_func() if snapshot_func else {},
            verbose=verbose,
        ),
        run_action_func=run_confirmed_if_needed if run_action_func else None,
    )
