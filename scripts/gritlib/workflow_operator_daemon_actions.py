"""Operator daemon workflow action records for grit-console workflows."""

from pathlib import Path

from gritlib.command_queue_records import command_queue_path, load_command_queue
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.process_status import pid_alive
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.service_status import configured_daemon_services
from gritlib.session_state import read_json_file, state_file_path
from gritlib.shell_utils import shquote
from gritlib.staged_files import staged_file_path
from gritlib.systemd_user import systemd_user_unit_name
from gritlib.target_records import load_targets, targets_path
from gritlib.workflow_support import workflow_fleet_metrics
from gritlib.workbench_jobs import workbench_jobs_path


def operator_daemon_workflow_commands(config_path, action_id):
    run_command = (
        "scripts/grit-console --config "
        + shquote(str(config_path))
        + " --run-operator-daemon-workflow-action "
        + shquote(str(action_id))
    )
    return {
        "run": run_command,
        "dry_run": run_command + " --operator-daemon-workflow-dry-run",
        "confirm": run_command + " --confirm-operator-daemon-workflow-action",
    }


def operator_daemon_action_state(action_id, action, daemon_attached):
    state_text = str((action or {}).get("operator_action_state") or "")
    reason = str((action or {}).get("operator_action_reason") or "")
    can_run_enter = bool((action or {}).get("can_run_from_curses_enter", False))
    curses_enter_action = str((action or {}).get("curses_enter_action") or "")
    if action_id == "operator-daemon-start":
        if daemon_attached:
            state_text = "already-running"
            reason = "daemon-already-attached"
            can_run_enter = False
            curses_enter_action = "none"
        else:
            state_text = "background-ready"
            reason = "start-background-job"
            can_run_enter = True
            curses_enter_action = "start-job"
    elif action_id == "operator-daemon-status":
        state_text = "ready"
        reason = "run-now"
        can_run_enter = False
        curses_enter_action = "use-action-11"
    elif action_id == "operator-daemon-stop":
        if daemon_attached:
            state_text = "confirm-required"
            reason = "confirmation-required"
            can_run_enter = True
            curses_enter_action = "stop-daemon"
        else:
            state_text = "already-stopped"
            reason = "daemon-not-running"
            can_run_enter = False
            curses_enter_action = "none"
    return {
        "state": state_text,
        "reason": reason,
        "can_run_enter": can_run_enter,
        "curses_enter_action": curses_enter_action,
    }


def operator_daemon_workflow_action_record(
    action,
    action_id,
    workflow,
    category,
    command,
    headless_command,
    workflow_run_command,
    workflow_confirm_command,
    workflow_dry_run_command,
    shared_state,
    desired_services,
    child_services,
    daemon_status,
    daemon_attached,
    child_pids,
    child_alive_count,
    daemon_state,
    systemd_user_unit_name,
    action_state,
    run_command="",
    dry_run_command="",
    start_job_command="",
):
    action = action or {}
    requires_confirmation = bool(action.get("requires_confirmation", False))
    return {
        "id": action_id,
        "action_id": action_id,
        "workbench_action_id": action_id,
        "service": "operator-daemon",
        "category": category,
        "workflow": workflow,
        "label": action.get("label", ""),
        "script": action.get("script", ""),
        "command": command,
        "headless_command": headless_command,
        "run_command": workflow_confirm_command if requires_confirmation else workflow_run_command,
        "dry_run_command": workflow_dry_run_command,
        "start_job_command": start_job_command,
        "workbench_run_command": run_command,
        "workbench_dry_run_command": dry_run_command,
        "workbench_start_job_command": start_job_command,
        "desired_services": desired_services,
        "desired_service_count": len(desired_services or []),
        "daemon_services": child_services,
        "daemon_service_count": len(child_services or []),
        "daemon_status": daemon_status,
        "daemon_attached": bool(daemon_attached),
        "daemon_child_count": len(child_pids or []),
        "daemon_child_alive_count": child_alive_count,
        "daemon_child_pids": child_pids,
        "daemon_child_process_logs": (daemon_state or {}).get("child_process_logs") or {},
        **(shared_state or {}),
        "systemd_user_unit_name": systemd_user_unit_name,
        "systemd_user_action": action_id.removeprefix("systemd-user-") if action_id.startswith("systemd-user-") else "",
        "background_supported": bool(action.get("background_supported", False)),
        "foreground_runnable": bool(action.get("foreground_runnable", False)),
        "dry_run_supported": bool(action.get("dry_run_supported", False)),
        "requires_confirmation": requires_confirmation,
        "writes_config": bool(action.get("writes_config", False)),
        "long_running": bool(action.get("long_running", False)),
        "available": True,
        "operator_action_state": action_state["state"],
        "operator_action_reason": action_state["reason"],
        "can_run_from_curses_enter": bool(action_state["can_run_enter"]),
        "curses_enter_action": action_state["curses_enter_action"],
        "execution_default": action.get("execution_default", "show-command"),
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side daemon lifecycle only; root/system service control remains explicit and out of scope",
    }


def operator_daemon_workflow_action_indexes(records):
    return {
        "operator_daemon_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "operator_daemon_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "operator_daemon_workflow_actions_by_workbench_action_id": records_by_key(records, "workbench_action_id"),
        "operator_daemon_workflow_actions_by_category": records_by_key(records, "category"),
        "operator_daemon_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "operator_daemon_workflow_actions_by_daemon_status": records_by_key(records, "daemon_status"),
        "operator_daemon_workflow_actions_by_daemon_attached": records_by_key(records, "daemon_attached"),
        "operator_daemon_workflow_actions_by_control_state_exists": records_by_key(records, "control_state_exists"),
        "operator_daemon_workflow_actions_by_command_queue_file_exists": records_by_key(records, "command_queue_file_exists"),
        "operator_daemon_workflow_actions_by_command_queue_command_count": records_by_key(records, "command_queue_command_count"),
        "operator_daemon_workflow_actions_by_command_queue_queued_count": records_by_key(records, "command_queue_queued_count"),
        "operator_daemon_workflow_actions_by_command_queue_result_received_count": records_by_key(records, "command_queue_result_received_count"),
        "operator_daemon_workflow_actions_by_command_queue_target_count": records_by_key(records, "command_queue_target_count"),
        "operator_daemon_workflow_actions_by_targets_file_exists": records_by_key(records, "targets_file_exists"),
        "operator_daemon_workflow_actions_by_target_count": records_by_key(records, "target_count"),
        "operator_daemon_workflow_actions_by_target_registry_record_count": records_by_key(records, "target_registry_record_count"),
        "operator_daemon_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "operator_daemon_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "operator_daemon_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "operator_daemon_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "operator_daemon_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "operator_daemon_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "operator_daemon_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "operator_daemon_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "operator_daemon_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "operator_daemon_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "operator_daemon_workflow_actions_by_staged_file_count": records_by_key(records, "staged_file_count"),
        "operator_daemon_workflow_actions_by_workbench_job_count": records_by_key(records, "workbench_job_count"),
        "operator_daemon_workflow_actions_by_background_supported": records_by_key(records, "background_supported"),
        "operator_daemon_workflow_actions_by_foreground_runnable": records_by_key(records, "foreground_runnable"),
        "operator_daemon_workflow_actions_by_dry_run_supported": records_by_key(records, "dry_run_supported"),
        "operator_daemon_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "operator_daemon_workflow_actions_by_writes_config": records_by_key(records, "writes_config"),
        "operator_daemon_workflow_actions_by_systemd_user_action": records_by_key(records, "systemd_user_action"),
        "operator_daemon_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "operator_daemon_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "operator_daemon_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "operator_daemon_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def operator_daemon_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "attached_count": len([rec for rec in records or [] if rec.get("daemon_attached") is True]),
        "background_supported_count": len([rec for rec in records or [] if rec.get("background_supported") is True]),
        "foreground_runnable_count": len([rec for rec in records or [] if rec.get("foreground_runnable") is True]),
        "dry_run_supported_count": len([rec for rec in records or [] if rec.get("dry_run_supported") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "writes_config_count": len([rec for rec in records or [] if rec.get("writes_config") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "daemon_status_counts": record_count_by_key(records, "daemon_status"),
        "daemon_attached_counts": record_count_by_key(records, "daemon_attached"),
        "control_state_exists_counts": record_count_by_key(records, "control_state_exists"),
        "command_queue_file_exists_counts": record_count_by_key(records, "command_queue_file_exists"),
        "command_queue_command_count_counts": record_count_by_key(records, "command_queue_command_count"),
        "command_queue_queued_count_counts": record_count_by_key(records, "command_queue_queued_count"),
        "command_queue_result_received_count_counts": record_count_by_key(records, "command_queue_result_received_count"),
        "command_queue_target_count_counts": record_count_by_key(records, "command_queue_target_count"),
        "targets_file_exists_counts": record_count_by_key(records, "targets_file_exists"),
        "target_count_counts": record_count_by_key(records, "target_count"),
        "target_registry_record_count_counts": record_count_by_key(records, "target_registry_record_count"),
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
        "staged_file_count_counts": record_count_by_key(records, "staged_file_count"),
        "workbench_job_count_counts": record_count_by_key(records, "workbench_job_count"),
        "background_supported_counts": record_count_by_key(records, "background_supported"),
        "foreground_runnable_counts": record_count_by_key(records, "foreground_runnable"),
        "dry_run_supported_counts": record_count_by_key(records, "dry_run_supported"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "writes_config_counts": record_count_by_key(records, "writes_config"),
        "systemd_user_action_counts": record_count_by_key(records, "systemd_user_action"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def operator_daemon_workflow_action_status_summary(records):
    summary = operator_daemon_workflow_action_summary(records)
    return {
        "operator_daemon_workflow_action_count": summary.get("total_count", 0),
        "operator_daemon_workflow_action_attached_count": summary.get("attached_count", 0),
        "operator_daemon_workflow_action_background_supported_count": summary.get("background_supported_count", 0),
        "operator_daemon_workflow_action_foreground_runnable_count": summary.get("foreground_runnable_count", 0),
        "operator_daemon_workflow_action_dry_run_supported_count": summary.get("dry_run_supported_count", 0),
        "operator_daemon_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "operator_daemon_workflow_action_writes_config_count": summary.get("writes_config_count", 0),
        "operator_daemon_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "operator_daemon_workflow_action_action_counts": summary.get("action_counts") or {},
        "operator_daemon_workflow_action_category_counts": summary.get("category_counts") or {},
        "operator_daemon_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "operator_daemon_workflow_action_daemon_status_counts": summary.get("daemon_status_counts") or {},
        "operator_daemon_workflow_action_daemon_attached_counts": summary.get("daemon_attached_counts") or {},
        "operator_daemon_workflow_action_control_state_exists_counts": summary.get("control_state_exists_counts") or {},
        "operator_daemon_workflow_action_command_queue_file_exists_counts": summary.get("command_queue_file_exists_counts") or {},
        "operator_daemon_workflow_action_command_queue_command_count_counts": summary.get("command_queue_command_count_counts") or {},
        "operator_daemon_workflow_action_command_queue_queued_count_counts": summary.get("command_queue_queued_count_counts") or {},
        "operator_daemon_workflow_action_command_queue_result_received_count_counts": summary.get("command_queue_result_received_count_counts") or {},
        "operator_daemon_workflow_action_command_queue_target_count_counts": summary.get("command_queue_target_count_counts") or {},
        "operator_daemon_workflow_action_targets_file_exists_counts": summary.get("targets_file_exists_counts") or {},
        "operator_daemon_workflow_action_target_count_counts": summary.get("target_count_counts") or {},
        "operator_daemon_workflow_action_target_registry_record_count_counts": summary.get("target_registry_record_count_counts") or {},
        "operator_daemon_workflow_action_fleet_target_count_counts": summary.get("fleet_target_count_counts") or {},
        "operator_daemon_workflow_action_fleet_offline_target_count_counts": summary.get("fleet_offline_target_count_counts") or {},
        "operator_daemon_workflow_action_fleet_stale_target_count_counts": summary.get("fleet_stale_target_count_counts") or {},
        "operator_daemon_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get("fleet_mailbox_pending_target_count_counts") or {},
        "operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get("fleet_mailbox_pending_work_count_counts") or {},
        "operator_daemon_workflow_action_fleet_poll_overdue_target_count_counts": summary.get("fleet_poll_overdue_target_count_counts") or {},
        "operator_daemon_workflow_action_fleet_has_offline_targets_counts": summary.get("fleet_has_offline_targets_counts") or {},
        "operator_daemon_workflow_action_fleet_has_stale_targets_counts": summary.get("fleet_has_stale_targets_counts") or {},
        "operator_daemon_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get("fleet_has_mailbox_pending_work_counts") or {},
        "operator_daemon_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get("fleet_has_poll_overdue_targets_counts") or {},
        "operator_daemon_workflow_action_staged_file_count_counts": summary.get("staged_file_count_counts") or {},
        "operator_daemon_workflow_action_workbench_job_count_counts": summary.get("workbench_job_count_counts") or {},
        "operator_daemon_workflow_action_background_supported_counts": summary.get("background_supported_counts") or {},
        "operator_daemon_workflow_action_foreground_runnable_counts": summary.get("foreground_runnable_counts") or {},
        "operator_daemon_workflow_action_dry_run_supported_counts": summary.get("dry_run_supported_counts") or {},
        "operator_daemon_workflow_action_requires_confirmation_counts": summary.get("requires_confirmation_counts") or {},
        "operator_daemon_workflow_action_writes_config_counts": summary.get("writes_config_counts") or {},
        "operator_daemon_workflow_action_systemd_user_action_counts": summary.get("systemd_user_action_counts") or {},
        "operator_daemon_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "operator_daemon_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "operator_daemon_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "operator_daemon_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
    }


def _operator_daemon_workflow_runtime_context(cfg, targets=None):
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    daemon_state = (state.get("services") or {}).get("operator-daemon") or {}
    daemon_status = str(daemon_state.get("status") or "unknown")
    child_pids = [
        pid for pid in (daemon_state.get("child_pids") or [])
        if str(pid).strip()
    ]
    child_alive_count = len([pid for pid in child_pids if pid_alive(pid)])
    child_services = [
        str(service) for service in (daemon_state.get("daemon_services") or [])
        if str(service)
    ]
    desired_services = configured_daemon_services(cfg, [])
    if not desired_services:
        desired_services = ["file-service", "command-queue"]
    daemon_attached = daemon_status in ("starting", "listening") and bool(child_alive_count or child_pids)
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    return {
        "state": state,
        "daemon_state": daemon_state,
        "daemon_status": daemon_status,
        "child_pids": child_pids,
        "child_alive_count": child_alive_count,
        "child_services": child_services,
        "desired_services": desired_services,
        "daemon_attached": daemon_attached,
        "target_records": target_records,
        "unit_name": systemd_user_unit_name("grit-operator.service"),
    }


def _operator_daemon_workflow_shared_state(cfg, runtime):
    queue_data = load_command_queue(cfg)
    queue_commands = [
        rec for rec in queue_data.get("commands") or []
        if isinstance(rec, dict)
    ]
    command_queue_status_counts = {}
    command_queue_target_ids = set()
    for command_rec in queue_commands:
        status = str(command_rec.get("status") or "")
        if status:
            command_queue_status_counts[status] = command_queue_status_counts.get(status, 0) + 1
        target_id = str(command_rec.get("target_id") or "")
        if target_id:
            command_queue_target_ids.add(target_id)
    targets_data = load_targets(cfg)
    targets_map = targets_data.get("targets") if isinstance(targets_data, dict) else {}
    if not isinstance(targets_map, dict):
        targets_map = {}
    target_records = list(runtime.get("target_records") or [])
    if not target_records:
        target_records = [
            rec for rec in targets_map.values()
            if isinstance(rec, dict)
        ]
    fleet_metrics = workflow_fleet_metrics(target_records)
    staged_data = read_json_file(staged_file_path(cfg), {"schema": 1, "files": {}})
    staged_files = staged_data.get("files") if isinstance(staged_data, dict) else {}
    if not isinstance(staged_files, dict):
        staged_files = {}
    workbench_jobs_data = read_json_file(workbench_jobs_path(cfg), {"schema": 1, "jobs": {}})
    workbench_jobs = workbench_jobs_data.get("jobs") if isinstance(workbench_jobs_data, dict) else {}
    if not isinstance(workbench_jobs, dict):
        workbench_jobs = {}
    return {
        "control_state_file": str(state_file_path(cfg)),
        "control_state_exists": Path(state_file_path(cfg)).exists(),
        "command_queue_file": str(command_queue_path(cfg)),
        "command_queue_file_exists": Path(command_queue_path(cfg)).exists(),
        "command_queue_command_count": len(queue_commands),
        "command_queue_queued_count": int(command_queue_status_counts.get("queued", 0) or 0),
        "command_queue_delivered_count": int(command_queue_status_counts.get("delivered", 0) or 0),
        "command_queue_result_received_count": int(command_queue_status_counts.get("result-received", 0) or 0),
        "command_queue_status_counts": command_queue_status_counts,
        "command_queue_target_count": len(command_queue_target_ids),
        "targets_file": str(targets_path(cfg)),
        "targets_file_exists": Path(targets_path(cfg)).exists(),
        "target_count": len(target_records),
        "target_registry_record_count": len(targets_map),
        **fleet_metrics,
        "staged_files_file": str(staged_file_path(cfg)),
        "staged_files_file_exists": Path(staged_file_path(cfg)).exists(),
        "staged_file_count": len(staged_files),
        "workbench_jobs_file": str(workbench_jobs_path(cfg)),
        "workbench_jobs_file_exists": Path(workbench_jobs_path(cfg)).exists(),
        "workbench_job_count": len(workbench_jobs),
    }


def _operator_daemon_workflow_action_from_workbench_action(cfg, action, runtime, shared_state):
    action_id = str(action.get("id") or "")
    workflow = "systemd-user-service" if action_id.startswith("systemd-user-") else "operator-daemon"
    category = "systemd" if workflow == "systemd-user-service" else "daemon"
    run_command = str(action.get("run_command") or "")
    dry_run_command = str(action.get("dry_run_command") or "")
    start_job_command = str(action.get("start_job_command") or "")
    command = str(action.get("command") or "")
    workflow_commands = operator_daemon_workflow_commands(
        cfg.get("_config_path", DEFAULT_CONFIG),
        action_id,
    )
    workflow_run_command = workflow_commands["run"]
    workflow_dry_run_command = workflow_commands["dry_run"]
    workflow_confirm_command = workflow_commands["confirm"]
    headless = workflow_run_command or start_job_command or run_command or dry_run_command or command
    action_state = operator_daemon_action_state(action_id, action, runtime["daemon_attached"])
    return operator_daemon_workflow_action_record(
        action,
        action_id,
        workflow,
        category,
        command,
        headless,
        workflow_run_command,
        workflow_confirm_command,
        workflow_dry_run_command,
        shared_state,
        runtime["desired_services"],
        runtime["child_services"],
        runtime["daemon_status"],
        runtime["daemon_attached"],
        runtime["child_pids"],
        runtime["child_alive_count"],
        runtime["daemon_state"],
        runtime["unit_name"],
        action_state,
        run_command=run_command,
        dry_run_command=dry_run_command,
        start_job_command=start_job_command,
    )


def operator_daemon_workflow_action_records(cfg, workbench_actions=None, targets=None):
    actions = [
        rec for rec in (workbench_actions or [])
        if isinstance(rec, dict) and str(rec.get("category") or "") == "daemon"
    ]
    runtime = _operator_daemon_workflow_runtime_context(cfg, targets=targets)
    shared_state = _operator_daemon_workflow_shared_state(cfg, runtime)
    records = [
        _operator_daemon_workflow_action_from_workbench_action(cfg, action, runtime, shared_state)
        for action in actions
    ]
    records.sort(key=lambda rec: (rec.get("workflow", ""), rec.get("action_id", "")))
    return records


def operator_daemon_workflow_action_status_context(
    cfg,
    workbench_actions=None,
    targets=None,
):
    actions = operator_daemon_workflow_action_records(
        cfg,
        workbench_actions,
        targets,
    )
    return {
        "actions": actions,
        "index_maps": operator_daemon_workflow_action_indexes(actions),
    }
