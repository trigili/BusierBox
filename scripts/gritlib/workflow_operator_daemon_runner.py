"""Operator-daemon workflow action runner for grit-console."""

from gritlib.console_display import print_dry_run_notice
from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.workbench_jobs import (
    run_workbench_action_record,
    start_workbench_job_record,
)
from gritlib.workflow_actions import (
    select_workflow_action,
    workbench_action_records,
)


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} module: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _operator_daemon_workflow_context(rec):
    action_id = str(rec.get("action_id") or rec.get("workbench_action_id") or "")
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": action_id,
        "workbench_action_id": str(rec.get("workbench_action_id") or action_id),
        "command": str(rec.get("command") or ""),
        "run_command": str(rec.get("run_command") or ""),
        "fleet_details": {
            "fleet_target_count": rec.get("fleet_target_count", 0),
            "fleet_offline_target_count": rec.get("fleet_offline_target_count", 0),
            "fleet_stale_target_count": rec.get("fleet_stale_target_count", 0),
            "fleet_mailbox_pending_target_count": rec.get("fleet_mailbox_pending_target_count", 0),
            "fleet_mailbox_pending_work_count": rec.get("fleet_mailbox_pending_work_count", 0),
            "fleet_poll_overdue_target_count": rec.get("fleet_poll_overdue_target_count", 0),
            "fleet_has_offline_targets": bool(rec.get("fleet_has_offline_targets")),
            "fleet_has_stale_targets": bool(rec.get("fleet_has_stale_targets")),
            "fleet_has_mailbox_pending_work": bool(rec.get("fleet_has_mailbox_pending_work")),
            "fleet_has_poll_overdue_targets": bool(rec.get("fleet_has_poll_overdue_targets")),
        },
    }


def _operator_daemon_headless_command(rec, context):
    return context["run_command"] or rec.get("headless_command", "") or context["command"]


def _append_operator_daemon_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "operator_daemon_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "daemon_status": rec.get("daemon_status", ""),
        "daemon_attached": bool(rec.get("daemon_attached")),
        "daemon_child_alive_count": rec.get("daemon_child_alive_count", 0),
        "systemd_user_action": rec.get("systemd_user_action", ""),
        "background_supported": bool(rec.get("background_supported")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        **context["fleet_details"],
    })


def _run_operator_daemon_workflow_dry_run(cfg, rec, context, confirmed=False, show_commands=True):
    if rec.get("workflow") == "systemd-user-service":
        rc = run_workbench_action_record(
            cfg,
            workbench_action_records(cfg),
            context["workbench_action_id"],
            dry_run=True,
            confirmed=confirmed,
            show_commands=show_commands,
        )
    else:
        print_dry_run_notice(machine=show_commands)
        rc = 0
    append_event(cfg, "workbench", "operator_daemon_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })
    return rc


def _run_operator_daemon_start(cfg, rec, context):
    started = start_workbench_job_record(
        cfg,
        workbench_action_records(cfg),
        context["workbench_action_id"],
        headless_command=_operator_daemon_headless_command(rec, context),
    )
    print(f"started workbench job {started.get('id', '')}: pid={started.get('pid', '')}")
    print(f"log={started.get('log_path', '')}")
    return 0


def _run_operator_daemon_workbench_action(cfg, context, confirmed=False):
    return run_workbench_action_record(
        cfg,
        workbench_action_records(cfg),
        context["workbench_action_id"],
        dry_run=False,
        confirmed=confirmed,
    )


def _append_operator_daemon_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "operator_daemon_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "daemon_status": rec.get("daemon_status", ""),
        "daemon_attached": bool(rec.get("daemon_attached")),
        "systemd_user_action": rec.get("systemd_user_action", ""),
        "confirmed": bool(confirmed),
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })


def run_operator_daemon_workflow_action(cfg, selector, dry_run=False, confirmed=False, show_commands=True):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("operator_daemon_workflow_actions") or [],
        selector,
        "operator daemon",
        extra_keys=("workbench_action_id", "systemd_user_action"),
    )
    context = _operator_daemon_workflow_context(rec)
    _print_workflow_action_header(
        "operator daemon",
        context["rec_id"],
        command=context["command"],
        headless_command=_operator_daemon_headless_command(rec, context),
        show_command=show_commands,
    )
    _append_operator_daemon_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_operator_daemon_workflow_dry_run(
            cfg,
            rec,
            context,
            confirmed=confirmed,
            show_commands=show_commands,
        )
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"operator daemon workflow action requires --confirm-operator-daemon-workflow-action: {context['rec_id']}")
    if context["action_id"] == "operator-daemon-start":
        rc = _run_operator_daemon_start(cfg, rec, context)
    else:
        rc = _run_operator_daemon_workbench_action(cfg, context, confirmed=confirmed)
    _append_operator_daemon_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc
