"""Command queue workflow action runner for grit-console."""

import gritlib.command_queue as command_queue_module
from gritlib.event_log import append_event
from gritlib.console_workbench import workbench_snapshot
from gritlib.workflow_actions import select_workflow_action


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _command_queue_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
    }


def _command_queue_headless_command(context):
    return context["run_command"] or context["command"]


def _append_command_queue_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "command_queue_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "requires_input": bool(rec.get("requires_input")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
    })


def _run_command_queue_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "command_queue_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
    })
    return 0


def _run_command_queue_command(cfg, rec, context, command_input=""):
    text = str(command_input or "").strip()
    if not text:
        raise ValueError("queue-command workflow action requires --command-queue-workflow-command")
    queued = command_queue_module.queue_command(cfg, text)
    print(f"queued {queued['id']}: {queued['command']}")
    if queued.get("target_id"):
        print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
    append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "result": "queued-command",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
        "returncode": 0,
    })
    return 0


def _run_command_queue_workflow_side_effect(
    cfg,
    rec,
    context,
    command_input="",
    confirmed=False,
    print_status_func=None,
    start_service_process_func=None,
    stop_recorded_service_func=None,
):
    action_id = context["action_id"]
    if action_id == "inspect-command-queue":
        return print_status_func(cfg, json_output=False)
    if action_id == "list-command-queue":
        command_queue_module.print_command_queue(cfg, json_output=False)
        rc = 0
    elif action_id == "queue-command":
        return _run_command_queue_command(cfg, rec, context, command_input=command_input)
    elif action_id == "clear-command-queue":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {context['rec_id']}")
        count = command_queue_module.clear_command_queue(cfg)
        print(f"cleared {count} command queue entr{'y' if count == 1 else 'ies'}")
        rc = 0
    elif action_id == "start-command-queue-listener":
        start_service_process_func(cfg, "command-queue", headless_command=_command_queue_headless_command(context))
        rc = 0
    elif action_id == "stop-command-queue-listener":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {context['rec_id']}")
        stop_recorded_service_func(
            cfg,
            "command-queue",
            via="command-queue-workflow-action",
            headless_command=_command_queue_headless_command(context),
        )
        rc = 0
    else:
        raise ValueError(f"unsupported command queue workflow action: {action_id}")
    return rc


def _append_command_queue_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "confirmed": bool(confirmed),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
        "returncode": rc,
    })


def run_command_queue_workflow_action(
    cfg,
    selector,
    command_input="",
    dry_run=False,
    confirmed=False,
    print_status_func=None,
    start_service_process_func=None,
    stop_recorded_service_func=None,
):
    if print_status_func is None:
        raise ValueError("command queue workflow runner requires print_status_func")
    if start_service_process_func is None:
        raise ValueError("command queue workflow runner requires start_service_process_func")
    if stop_recorded_service_func is None:
        raise ValueError("command queue workflow runner requires stop_recorded_service_func")
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("command_queue_workflow_actions") or [], selector, "command queue")
    context = _command_queue_workflow_context(rec)
    _print_workflow_action_header(
        "command queue",
        context["rec_id"],
        command=context["command"],
        headless_command=_command_queue_headless_command(context),
    )
    _append_command_queue_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_command_queue_workflow_dry_run(cfg, context)
    rc = _run_command_queue_workflow_side_effect(
        cfg,
        rec,
        context,
        command_input=command_input,
        confirmed=confirmed,
        print_status_func=print_status_func,
        start_service_process_func=start_service_process_func,
        stop_recorded_service_func=stop_recorded_service_func,
    )
    if context["action_id"] != "inspect-command-queue" and context["action_id"] != "queue-command":
        _append_command_queue_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc
