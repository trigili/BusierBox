"""Staged file workflow action runner for grit-console."""

import gritlib.command_queue as command_queue_module
from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command
import gritlib.staged_files as staged_files
from gritlib.target_records import configured_target_filter, scoped_target_cfg
from gritlib.workflow_actions import select_workflow_action


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _staged_file_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "request": str(rec.get("request_name") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
        "target_details": {
            "target_connectivity_state": rec.get("target_connectivity_state", ""),
            "target_offline_age_bucket": rec.get("target_offline_age_bucket", ""),
            "target_poll_overdue": bool(rec.get("target_poll_overdue")),
            "target_mailbox_pending_work_count": rec.get("target_mailbox_pending_work_count", 0),
            "target_latest_phone_home_status": rec.get("target_latest_phone_home_status", ""),
            "target_latest_successful_phone_home_status": rec.get("target_latest_successful_phone_home_status", ""),
            "target_last_failed_phone_home_status": rec.get("target_last_failed_phone_home_status", ""),
        },
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


def _staged_file_headless_command(context):
    return context["run_command"] or context["command"]


def _append_staged_file_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "staged_file_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "requires_target": bool(rec.get("requires_target")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _staged_file_headless_command(context),
        "command": context["command"],
        **context["target_details"],
        **context["fleet_details"],
    })


def _run_staged_file_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "staged_file_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "headless_command": _staged_file_headless_command(context),
        "command": context["command"],
        **context["target_details"],
        **context["fleet_details"],
    })
    return 0


def _run_staged_file_show_fetch_command(cfg, rec, request):
    fetch_command = str(rec.get("fetch_command") or render_fetch_command(request, cfg))
    print(f"request_name={request}")
    if rec.get("target_id"):
        print(f"target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
    print(f"target_command={fetch_command}")
    return 0


def _run_staged_file_queue_fetch(cfg, rec, context):
    request = context["request"]
    target_id = str(rec.get("target_id") or configured_target_filter(cfg) or "").strip()
    if not target_id:
        raise ValueError("queue-staged-fetch staged file workflow action requires --target-id")
    scoped = scoped_target_cfg(cfg, target_id, target_label=str(rec.get("target_label") or cfg.get("_target_label_filter") or ""))
    staged = (staged_files.load_staged(cfg).get("staged") or {}).get(request) or {}
    if not isinstance(staged, dict) or not staged:
        raise ValueError(f"staged request not found: {request}")
    staged_target = str(staged.get("target_id") or "")
    if staged_target and staged_target != target_id:
        raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
    fetch_command = render_fetch_command(request, scoped)
    queued = command_queue_module.queue_command(scoped, fetch_command, metadata={
        "work_kind": "staged-fetch",
        "workflow": "file-service",
        "request_name": request,
        "route_kind": str(staged.get("route_kind") or "direct"),
        "bridge_profile": str(staged.get("bridge_profile") or ""),
        "bridge_route_path": str(staged.get("bridge_route_path") or ""),
    })
    print(f"queued: {queued['id']}")
    print(f"command: {queued['command']}")
    print(f"target: {queued.get('target_id', '')} ({queued.get('target_label', '') or '-'})")
    append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": request,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": target_id,
        "target_label": queued.get("target_label", ""),
        "result": "queued-staged-fetch",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queued_command": queued.get("command", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": True,
        "headless_command": _staged_file_headless_command(context),
        "command": context["command"],
        "returncode": 0,
        **context["target_details"],
        **context["fleet_details"],
    })
    return 0


def _run_staged_file_unstage(cfg, rec, rec_id, request, confirmed=False):
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"staged file workflow action requires --confirm-staged-file-workflow-action: {rec_id}")
    existed = staged_files.unstage_file(cfg, request)
    print(f"unstaged {request}" if existed else f"not staged {request}")
    return 0


def _append_staged_file_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "confirmed": bool(confirmed),
        "headless_command": _staged_file_headless_command(context),
        "command": context["command"],
        "returncode": rc,
        **context["target_details"],
        **context["fleet_details"],
    })


def run_staged_file_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("staged_file_workflow_actions") or [],
        selector,
        "staged file",
        extra_keys=("request_name",),
    )
    context = _staged_file_workflow_context(rec)
    rec_id = context["rec_id"]
    action_id = context["action_id"]
    request = context["request"]
    command = context["command"]
    run_command = context["run_command"]
    _print_workflow_action_header("staged file", rec_id, command=command, headless_command=run_command or command)
    _append_staged_file_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_staged_file_workflow_dry_run(cfg, context)
    if not request:
        raise ValueError(f"staged file workflow action is missing request name: {rec_id}")
    if action_id == "inspect-staged":
        staged_files.print_staged(cfg)
        rc = 0
    elif action_id == "show-fetch-command":
        rc = _run_staged_file_show_fetch_command(cfg, rec, request)
    elif action_id == "queue-staged-fetch":
        return _run_staged_file_queue_fetch(cfg, rec, context)
    elif action_id == "unstage":
        rc = _run_staged_file_unstage(cfg, rec, rec_id, request, confirmed=confirmed)
    else:
        raise ValueError(f"unsupported staged file workflow action: {action_id}")
    _append_staged_file_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc
