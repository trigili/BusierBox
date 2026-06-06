"""Command queue workflow action helpers for grit-console."""

from pathlib import Path

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.shell_utils import shquote
from gritlib.target_context import configured_target_filter
from gritlib.workflow_support import (
    optional_target_id_arg, optional_target_scoped_command,
    scoped_service_workflow_run_command, workflow_fleet_metrics,
)


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def command_queue_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("command_queue_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "command-queue.json"
    ))


def command_queue_workflow_action_indexes(records):
    return {
        "command_queue_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "command_queue_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "command_queue_workflow_actions_by_category": records_by_key(records, "category"),
        "command_queue_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "command_queue_workflow_actions_by_actual": records_by_key(records, "actual"),
        "command_queue_workflow_actions_by_target_filter_active": records_by_key(records, "target_filter_active"),
        "command_queue_workflow_actions_by_policy_valid": records_by_key(records, "policy_valid"),
        "command_queue_workflow_actions_by_configured_for_polling": records_by_key(records, "configured_for_polling"),
        "command_queue_workflow_actions_by_poll_transport_supported": records_by_key(records, "poll_transport_supported"),
        "command_queue_workflow_actions_by_live_polling_supported": records_by_key(records, "live_polling_supported"),
        "command_queue_workflow_actions_by_result_upload_supported": records_by_key(records, "result_upload_supported"),
        "command_queue_workflow_actions_by_execution_supported": records_by_key(records, "execution_supported"),
        "command_queue_workflow_actions_by_delivery_supported": records_by_key(records, "delivery_supported"),
        "command_queue_workflow_actions_by_operator_queue_records_only": records_by_key(records, "operator_queue_records_only"),
        "command_queue_workflow_actions_by_target_mailbox_pending_target_count": records_by_key(records, "target_mailbox_pending_target_count"),
        "command_queue_workflow_actions_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "command_queue_workflow_actions_by_target_mailbox_pending_poll_overdue_count": records_by_key(records, "target_mailbox_pending_poll_overdue_count"),
        "command_queue_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "command_queue_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "command_queue_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "command_queue_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "command_queue_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "command_queue_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "command_queue_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "command_queue_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "command_queue_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "command_queue_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "command_queue_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "command_queue_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "command_queue_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "command_queue_workflow_actions_by_target_phone_home_required": records_by_key(records, "target_phone_home_required"),
        "command_queue_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "command_queue_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "command_queue_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "command_queue_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def command_queue_workflow_action_record(
    action_id,
    category,
    label,
    command,
    workflow,
    run_command,
    target_filter_id,
    service_row,
    queue_path,
    queued_count,
    total_count,
    result_count,
    mailbox_records,
    pending_mailbox_records,
    pending_mailbox_target_ids,
    fleet_metrics,
    command_queue,
    action_state,
    action_reason,
    available=True,
    requires_input=False,
    requires_confirmation=False,
    queues_offline_work=False,
    target_phone_home_required=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    service_row = service_row or {}
    mailbox_records = [rec for rec in mailbox_records or [] if isinstance(rec, dict)]
    pending_mailbox_records = [rec for rec in pending_mailbox_records or [] if isinstance(rec, dict)]
    command_queue = command_queue or {}
    return {
        "id": f"command-queue:{action_id}",
        "action_id": action_id,
        "service": "command-queue",
        "actual": str(service_row.get("actual") or "unknown"),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "target_id_filter": target_filter_id,
        "target_filter_active": bool(target_filter_id),
        "queue_path": str(queue_path),
        "queued_count": queued_count,
        "total_count": total_count,
        "result_count": result_count,
        "target_mailbox_record_count": len(mailbox_records),
        "target_mailbox_pending_work_count": len(pending_mailbox_records),
        "target_mailbox_pending_target_count": len(pending_mailbox_target_ids or []),
        "target_mailbox_pending_connectivity_state_counts": record_count_by_key(pending_mailbox_records, "target_connectivity_state"),
        "target_mailbox_pending_offline_age_bucket_counts": record_count_by_key(pending_mailbox_records, "target_offline_age_bucket"),
        "target_mailbox_pending_poll_overdue_count": len([rec for rec in pending_mailbox_records if rec.get("target_poll_overdue") is True]),
        **(fleet_metrics or {}),
        "policy_valid": bool(command_queue.get("policy_valid", True)),
        "configured_for_polling": bool(command_queue.get("configured_for_polling", False)),
        "poll_transport_supported": bool(command_queue.get("poll_transport_supported", False)),
        "live_polling_supported": bool(command_queue.get("live_polling_supported", False)),
        "result_upload_supported": bool(command_queue.get("result_upload_supported", False)),
        "execution_supported": bool(command_queue.get("execution_supported", False)),
        "delivery_supported": bool(command_queue.get("delivery_supported", False)),
        "operator_queue_records_only": bool(command_queue.get("operator_queue_records_only", True)),
        "available": bool(available),
        "requires_input": bool(requires_input),
        "requires_confirmation": bool(requires_confirmation),
        "requires_target_online": False,
        "queues_offline_work": bool(queues_offline_work),
        "target_phone_home_required": bool(target_phone_home_required),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side command queue metadata; target execution requires explicit target poll and execute policy",
    }


def command_queue_listener_action_states(service_row):
    actual = str((service_row or {}).get("actual") or "unknown")
    listening = actual == "listening"
    return {
        "start_state": "already-running" if listening else "ready",
        "start_reason": "service-already-listening" if listening else "run-now",
        "start_enter": not listening,
        "stop_state": "ready" if listening else "already-stopped",
        "stop_reason": "run-now" if listening else "service-not-listening",
        "stop_enter": listening,
    }


def _command_queue_workflow_context(
    cfg,
    command_queue,
    target_mailbox_records=None,
    service_row=None,
    targets=None,
):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    service_row = service_row if isinstance(service_row, dict) else {}
    target_filter_id = configured_target_filter(cfg)
    target_arg = optional_target_id_arg(target_filter_id)
    queued_count = int(command_queue.get("queued_count", 0) or 0)
    total_count = int(command_queue.get("total_count", 0) or 0)
    result_count = int(command_queue.get("result_count", 0) or 0)
    mailbox_records = [rec for rec in (target_mailbox_records or []) if isinstance(rec, dict)]
    pending_mailbox_records = [rec for rec in mailbox_records if rec.get("pending_work") is True]
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    pending_mailbox_target_ids = {
        str(rec.get("target_id") or "")
        for rec in pending_mailbox_records
        if str(rec.get("target_id") or "")
    }
    fleet_metrics = workflow_fleet_metrics(target_records)
    lifecycle_states = command_queue_listener_action_states(service_row)
    return {
        "base": base,
        "target_arg": target_arg,
        "target_filter_id": target_filter_id,
        "service_row": service_row,
        "queue_path": command_queue.get("path") or command_queue_path(cfg),
        "queued_count": queued_count,
        "total_count": total_count,
        "result_count": result_count,
        "mailbox_records": mailbox_records,
        "pending_mailbox_records": pending_mailbox_records,
        "pending_mailbox_target_ids": pending_mailbox_target_ids,
        "fleet_metrics": fleet_metrics,
        "command_queue": command_queue,
        "lifecycle_states": lifecycle_states,
    }


def _command_queue_workflow_action(
    context,
    action_id,
    category,
    label,
    command,
    workflow,
    action_state,
    action_reason,
    available=True,
    requires_input=False,
    requires_confirmation=False,
    queues_offline_work=False,
    target_phone_home_required=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
    run_command_suffix="",
):
    return command_queue_workflow_action_record(
        action_id,
        category,
        label,
        command,
        workflow,
        scoped_service_workflow_run_command(
            context["base"],
            context["target_arg"],
            "command-queue",
            action_id,
            run_command_suffix,
        ),
        context["target_filter_id"],
        context["service_row"],
        context["queue_path"],
        context["queued_count"],
        context["total_count"],
        context["result_count"],
        context["mailbox_records"],
        context["pending_mailbox_records"],
        context["pending_mailbox_target_ids"],
        context["fleet_metrics"],
        context["command_queue"],
        action_state,
        action_reason,
        available=available,
        requires_input=requires_input,
        requires_confirmation=requires_confirmation,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
        can_run_from_curses_enter=can_run_from_curses_enter,
        curses_enter_action=curses_enter_action,
    )


def _command_queue_inspect_workflow_actions(context):
    base = context["base"]
    target_arg = context["target_arg"]
    return [
        _command_queue_workflow_action(
            context,
            "inspect-command-queue",
            "inspect",
            "Inspect command queue, target mailbox, and policy state",
            optional_target_scoped_command(base, target_arg, " --status"),
            "command-queue",
            "ready",
            "run-now",
        )
    ]


def _command_queue_mailbox_workflow_actions(context):
    base = context["base"]
    target_arg = context["target_arg"]
    total_count = context["total_count"]
    return [
        _command_queue_workflow_action(
            context,
            "list-command-queue",
            "mailbox",
            "List command queue and mailbox records",
            optional_target_scoped_command(base, target_arg, " --list-command-queue"),
            "command-queue",
            "ready",
            "run-now",
            can_run_from_curses_enter=True,
            curses_enter_action="list-command-queue",
        ),
        _command_queue_workflow_action(
            context,
            "queue-command",
            "mailbox",
            "Queue command for target mailbox delivery",
            optional_target_scoped_command(base, target_arg, " --queue-command COMMAND"),
            "command-queue",
            "needs-input",
            "input-required",
            requires_input=True,
            queues_offline_work=True,
            target_phone_home_required=True,
            run_command_suffix=" --command-queue-workflow-command COMMAND",
        ),
        _command_queue_workflow_action(
            context,
            "clear-command-queue",
            "mailbox",
            "Clear queued command records",
            optional_target_scoped_command(base, target_arg, " --clear-command-queue --list-command-queue"),
            "command-queue",
            "confirm-required" if total_count else "already-empty",
            "confirmation-required" if total_count else "queue-empty",
            requires_confirmation=True,
            run_command_suffix=" --confirm-command-queue-workflow-action",
        ),
    ]


def _command_queue_listener_workflow_actions(context):
    base = context["base"]
    lifecycle_states = context["lifecycle_states"]
    return [
        _command_queue_workflow_action(
            context,
            "start-command-queue-listener",
            "service",
            "Start command queue poll listener",
            base + " --transport command-queue",
            "command-queue",
            lifecycle_states["start_state"],
            lifecycle_states["start_reason"],
            can_run_from_curses_enter=lifecycle_states["start_enter"],
            curses_enter_action="start-command-queue-listener" if lifecycle_states["start_enter"] else "stop-command-queue-listener",
        ),
        _command_queue_workflow_action(
            context,
            "stop-command-queue-listener",
            "service",
            "Stop command queue poll listener",
            base + " --stop-service command-queue",
            "command-queue",
            lifecycle_states["stop_state"],
            lifecycle_states["stop_reason"],
            requires_confirmation=True,
            can_run_from_curses_enter=lifecycle_states["stop_enter"],
            curses_enter_action="stop-command-queue-listener" if lifecycle_states["stop_enter"] else "start-command-queue-listener",
        ),
    ]


def command_queue_workflow_action_records(
    cfg,
    command_queue,
    target_mailbox_records=None,
    service_row=None,
    targets=None,
):
    context = _command_queue_workflow_context(
        cfg,
        command_queue,
        target_mailbox_records=target_mailbox_records,
        service_row=service_row,
        targets=targets,
    )
    records = []
    records.extend(_command_queue_inspect_workflow_actions(context))
    records.extend(_command_queue_mailbox_workflow_actions(context))
    records.extend(_command_queue_listener_workflow_actions(context))
    records.sort(key=lambda rec: (rec.get("category", ""), rec.get("action_id", "")))
    return records


def command_queue_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "target_phone_home_required_count": len([rec for rec in records or [] if rec.get("target_phone_home_required") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "target_filter_active_counts": record_count_by_key(records, "target_filter_active"),
        "policy_valid_counts": record_count_by_key(records, "policy_valid"),
        "configured_for_polling_counts": record_count_by_key(records, "configured_for_polling"),
        "poll_transport_supported_counts": record_count_by_key(records, "poll_transport_supported"),
        "live_polling_supported_counts": record_count_by_key(records, "live_polling_supported"),
        "result_upload_supported_counts": record_count_by_key(records, "result_upload_supported"),
        "execution_supported_counts": record_count_by_key(records, "execution_supported"),
        "delivery_supported_counts": record_count_by_key(records, "delivery_supported"),
        "operator_queue_records_only_counts": record_count_by_key(records, "operator_queue_records_only"),
        "target_mailbox_pending_target_count_counts": record_count_by_key(records, "target_mailbox_pending_target_count"),
        "target_mailbox_pending_work_count_counts": record_count_by_key(records, "target_mailbox_pending_work_count"),
        "target_mailbox_pending_poll_overdue_count_counts": record_count_by_key(records, "target_mailbox_pending_poll_overdue_count"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "requires_input_counts": record_count_by_key(records, "requires_input"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "queues_offline_work_counts": record_count_by_key(records, "queues_offline_work"),
        "target_phone_home_required_counts": record_count_by_key(records, "target_phone_home_required"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def command_queue_workflow_action_status_summary(records):
    summary = command_queue_workflow_action_summary(records)
    return {
        "command_queue_workflow_action_count": summary.get("total_count", 0),
        "command_queue_workflow_action_requires_input_count": summary.get("requires_input_count", 0),
        "command_queue_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "command_queue_workflow_action_queues_offline_work_count": summary.get("queues_offline_work_count", 0),
        "command_queue_workflow_action_target_phone_home_required_count": summary.get("target_phone_home_required_count", 0),
        "command_queue_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "command_queue_workflow_action_action_counts": summary.get("action_counts") or {},
        "command_queue_workflow_action_category_counts": summary.get("category_counts") or {},
        "command_queue_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "command_queue_workflow_action_actual_counts": summary.get("actual_counts") or {},
        "command_queue_workflow_action_target_filter_active_counts": summary.get("target_filter_active_counts") or {},
        "command_queue_workflow_action_policy_valid_counts": summary.get("policy_valid_counts") or {},
        "command_queue_workflow_action_configured_for_polling_counts": summary.get("configured_for_polling_counts") or {},
        "command_queue_workflow_action_poll_transport_supported_counts": summary.get("poll_transport_supported_counts") or {},
        "command_queue_workflow_action_live_polling_supported_counts": summary.get("live_polling_supported_counts") or {},
        "command_queue_workflow_action_result_upload_supported_counts": summary.get("result_upload_supported_counts") or {},
        "command_queue_workflow_action_execution_supported_counts": summary.get("execution_supported_counts") or {},
        "command_queue_workflow_action_delivery_supported_counts": summary.get("delivery_supported_counts") or {},
        "command_queue_workflow_action_operator_queue_records_only_counts": summary.get("operator_queue_records_only_counts") or {},
        "command_queue_workflow_action_target_mailbox_pending_target_count_counts": summary.get("target_mailbox_pending_target_count_counts") or {},
        "command_queue_workflow_action_target_mailbox_pending_work_count_counts": summary.get("target_mailbox_pending_work_count_counts") or {},
        "command_queue_workflow_action_target_mailbox_pending_poll_overdue_count_counts": summary.get("target_mailbox_pending_poll_overdue_count_counts") or {},
        "command_queue_workflow_action_fleet_target_count_counts": summary.get("fleet_target_count_counts") or {},
        "command_queue_workflow_action_fleet_offline_target_count_counts": summary.get("fleet_offline_target_count_counts") or {},
        "command_queue_workflow_action_fleet_stale_target_count_counts": summary.get("fleet_stale_target_count_counts") or {},
        "command_queue_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get("fleet_mailbox_pending_target_count_counts") or {},
        "command_queue_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get("fleet_mailbox_pending_work_count_counts") or {},
        "command_queue_workflow_action_fleet_poll_overdue_target_count_counts": summary.get("fleet_poll_overdue_target_count_counts") or {},
        "command_queue_workflow_action_fleet_has_offline_targets_counts": summary.get("fleet_has_offline_targets_counts") or {},
        "command_queue_workflow_action_fleet_has_stale_targets_counts": summary.get("fleet_has_stale_targets_counts") or {},
        "command_queue_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get("fleet_has_mailbox_pending_work_counts") or {},
        "command_queue_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get("fleet_has_poll_overdue_targets_counts") or {},
        "command_queue_workflow_action_requires_input_counts": summary.get("requires_input_counts") or {},
        "command_queue_workflow_action_requires_confirmation_counts": summary.get("requires_confirmation_counts") or {},
        "command_queue_workflow_action_queues_offline_work_counts": summary.get("queues_offline_work_counts") or {},
        "command_queue_workflow_action_target_phone_home_required_counts": summary.get("target_phone_home_required_counts") or {},
        "command_queue_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "command_queue_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "command_queue_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "command_queue_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
    }
