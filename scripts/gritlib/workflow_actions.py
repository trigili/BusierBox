"""Workflow action index, summary, and display helpers for grit-console."""

from gritlib.record_utils import format_counts, record_count_by_key, record_sum_by_key, records_by_key


def select_workflow_action(records, selector, label, extra_keys=()):
    text = str(selector or "").strip()
    if not text:
        raise ValueError(f"{label} workflow action is required")
    records = records or []
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"{label} workflow action number out of range: {text}")
        return records[idx]
    keys = ("id", "action_id", *tuple(extra_keys or ()))
    for rec in records:
        if text in tuple(str(rec.get(key) or "") for key in keys):
            return rec
    raise ValueError(f"{label} workflow action not found: {text}")


def workbench_action_indexes(records):
    return {
        "workbench_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "workbench_actions_by_category": records_by_key(records, "category"),
        "workbench_actions_by_script": records_by_key(records, "script"),
        "workbench_actions_by_background_supported": records_by_key(records, "background_supported"),
        "workbench_actions_by_long_running": records_by_key(records, "long_running"),
        "workbench_actions_by_writes_config": records_by_key(records, "writes_config"),
        "workbench_actions_by_runs_build": records_by_key(records, "runs_build"),
        "workbench_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "workbench_actions_by_execution_default": records_by_key(records, "execution_default"),
        "workbench_actions_by_target_execution": records_by_key(records, "target_execution"),
        "workbench_actions_by_event": records_by_key(records, "event"),
        "workbench_actions_by_config_path": records_by_key(records, "config_path"),
        "workbench_actions_by_foreground_runnable": records_by_key(records, "foreground_runnable"),
        "workbench_actions_by_dry_run_supported": records_by_key(records, "dry_run_supported"),
        "workbench_actions_by_has_placeholder": records_by_key(records, "has_placeholder"),
        "workbench_actions_by_has_run_command": records_by_key(records, "has_run_command"),
        "workbench_actions_by_has_dry_run_command": records_by_key(records, "has_dry_run_command"),
        "workbench_actions_by_has_start_job_command": records_by_key(records, "has_start_job_command"),
        "workbench_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "workbench_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "workbench_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "workbench_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def workbench_action_summary(records):
    return {
        "total_count": len(records or []),
        "background_supported_count": len([rec for rec in records or [] if rec.get("background_supported") is True]),
        "long_running_count": len([rec for rec in records or [] if rec.get("long_running") is True]),
        "writes_config_count": len([rec for rec in records or [] if rec.get("writes_config") is True]),
        "runs_build_count": len([rec for rec in records or [] if rec.get("runs_build") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "target_execution_count": len([rec for rec in records or [] if rec.get("target_execution") is True]),
        "foreground_runnable_count": len([rec for rec in records or [] if rec.get("foreground_runnable") is True]),
        "dry_run_supported_count": len([rec for rec in records or [] if rec.get("dry_run_supported") is True]),
        "has_placeholder_count": len([rec for rec in records or [] if rec.get("has_placeholder") is True]),
        "has_run_command_count": len([rec for rec in records or [] if rec.get("has_run_command") is True]),
        "has_dry_run_command_count": len([rec for rec in records or [] if rec.get("has_dry_run_command") is True]),
        "has_start_job_command_count": len([rec for rec in records or [] if rec.get("has_start_job_command") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "category_counts": record_count_by_key(records, "category"),
        "script_counts": record_count_by_key(records, "script"),
        "execution_default_counts": record_count_by_key(records, "execution_default"),
        "event_counts": record_count_by_key(records, "event"),
        "config_path_counts": record_count_by_key(records, "config_path"),
        "foreground_runnable_counts": record_count_by_key(records, "foreground_runnable"),
        "dry_run_supported_counts": record_count_by_key(records, "dry_run_supported"),
        "has_placeholder_counts": record_count_by_key(records, "has_placeholder"),
        "has_run_command_counts": record_count_by_key(records, "has_run_command"),
        "has_dry_run_command_counts": record_count_by_key(records, "has_dry_run_command"),
        "has_start_job_command_counts": record_count_by_key(records, "has_start_job_command"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def workbench_job_indexes(records):
    return {
        "workbench_jobs_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "workbench_jobs_by_action": records_by_key(records, "action_id"),
        "workbench_jobs_by_state": records_by_key(records, "state"),
        "workbench_jobs_by_effective_state": records_by_key(records, "effective_state"),
        "workbench_jobs_by_category": records_by_key(records, "category"),
        "workbench_jobs_by_script": records_by_key(records, "script"),
        "workbench_jobs_by_pid": records_by_key(records, "pid"),
        "workbench_jobs_by_pid_managed": records_by_key(records, "pid_managed"),
        "workbench_jobs_by_cancel_supported": records_by_key(records, "cancel_supported"),
        "workbench_jobs_by_log_exists": records_by_key(records, "log_exists"),
        "workbench_jobs_by_exit_status_known": records_by_key(records, "exit_status_known"),
        "workbench_jobs_by_started_at_known": records_by_key(records, "started_at_known"),
        "workbench_jobs_by_finished_at_known": records_by_key(records, "finished_at_known"),
        "workbench_jobs_by_duration_known": records_by_key(records, "duration_known"),
        "workbench_jobs_by_elapsed_known": records_by_key(records, "elapsed_known"),
        "workbench_jobs_by_background_supported": records_by_key(records, "background_supported"),
        "workbench_jobs_by_long_running": records_by_key(records, "long_running"),
        "workbench_jobs_by_outcome": records_by_key(records, "outcome"),
        "workbench_jobs_by_exit_status": records_by_key(records, "exit_status"),
        "workbench_jobs_by_last_output_tail_truncated": records_by_key(records, "last_output_tail_truncated"),
    }


def workbench_job_summary(records):
    return {
        "total_count": len(records or []),
        "running_count": len([rec for rec in records or [] if rec.get("effective_state") in ("starting", "running")]),
        "pid_managed_count": len([rec for rec in records or [] if rec.get("pid_managed") is True]),
        "cancel_supported_count": len([rec for rec in records or [] if rec.get("cancel_supported") is True]),
        "log_exists_count": len([rec for rec in records or [] if rec.get("log_exists") is True]),
        "log_total_size": record_sum_by_key(records, "log_size"),
        "last_output_tail_truncated_count": len([rec for rec in records or [] if rec.get("last_output_tail_truncated") is True]),
        "exit_status_known_count": len([rec for rec in records or [] if rec.get("exit_status_known") is True]),
        "started_at_known_count": len([rec for rec in records or [] if rec.get("started_at_known") is True]),
        "finished_at_known_count": len([rec for rec in records or [] if rec.get("finished_at_known") is True]),
        "duration_known_count": len([rec for rec in records or [] if rec.get("duration_known") is True]),
        "elapsed_known_count": len([rec for rec in records or [] if rec.get("elapsed_known") is True]),
        "duration_total_sec": record_sum_by_key(records, "duration_sec"),
        "elapsed_total_sec": record_sum_by_key(records, "elapsed_sec"),
        "background_supported_count": len([rec for rec in records or [] if rec.get("background_supported") is True]),
        "long_running_count": len([rec for rec in records or [] if rec.get("long_running") is True]),
        "state_counts": record_count_by_key(records, "state"),
        "effective_state_counts": record_count_by_key(records, "effective_state"),
        "outcome_counts": record_count_by_key(records, "outcome"),
        "exit_status_counts": record_count_by_key(records, "exit_status"),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
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


def operator_console_workflow_indexes(records):
    return {
        "operator_console_workflows_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "operator_console_workflows_by_workflow": records_by_key(records, "workflow"),
        "operator_console_workflows_by_group": records_by_key(records, "group"),
        "operator_console_workflows_by_primary_collection": records_by_key(records, "primary_collection"),
        "operator_console_workflows_by_target_scoped": records_by_key(records, "target_scoped"),
        "operator_console_workflows_by_multi_target": records_by_key(records, "multi_target"),
        "operator_console_workflows_by_offline_queue_supported": records_by_key(records, "offline_queue_supported"),
        "operator_console_workflows_by_has_records": records_by_key(records, "has_records"),
        "operator_console_workflows_by_has_actions": records_by_key(records, "has_actions"),
        "operator_console_workflows_by_has_enter_runnable_actions": records_by_key(records, "has_enter_runnable_actions"),
        "operator_console_workflows_by_has_pending_work": records_by_key(records, "has_pending_work"),
        "operator_console_workflows_by_has_warnings": records_by_key(records, "has_warnings"),
        "operator_console_workflows_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "operator_console_workflows_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "operator_console_workflows_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "operator_console_workflows_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "operator_console_workflows_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "operator_console_workflows_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "operator_console_workflows_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "operator_console_workflows_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "operator_console_workflows_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "operator_console_workflows_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "operator_console_workflows_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "operator_console_workflows_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "operator_console_workflows_by_tui_shortcut": records_by_key(records, "tui_shortcut"),
        "operator_console_workflows_by_line_mode_action": records_by_key(records, "line_mode_action"),
    }


def operator_console_workflow_summary(records):
    return {
        "total_count": len(records or []),
        "target_scoped_count": len([rec for rec in records or [] if rec.get("target_scoped") is True]),
        "multi_target_count": len([rec for rec in records or [] if rec.get("multi_target") is True]),
        "offline_queue_supported_count": len([rec for rec in records or [] if rec.get("offline_queue_supported") is True]),
        "has_records_count": len([rec for rec in records or [] if rec.get("has_records") is True]),
        "has_actions_count": len([rec for rec in records or [] if rec.get("has_actions") is True]),
        "has_enter_runnable_actions_count": len([rec for rec in records or [] if rec.get("has_enter_runnable_actions") is True]),
        "has_pending_work_count": len([rec for rec in records or [] if rec.get("has_pending_work") is True]),
        "has_warnings_count": len([rec for rec in records or [] if rec.get("has_warnings") is True]),
        "action_total_count": sum(int(rec.get("action_count") or 0) for rec in records or []),
        "enter_runnable_action_total_count": sum(int(rec.get("enter_runnable_action_count") or 0) for rec in records or []),
        "pending_work_total_count": sum(int(rec.get("pending_work_count") or 0) for rec in records or []),
        "warning_total_count": sum(int(rec.get("warning_count") or 0) for rec in records or []),
        "group_counts": record_count_by_key(records, "group"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "primary_collection_counts": record_count_by_key(records, "primary_collection"),
        "target_scoped_counts": record_count_by_key(records, "target_scoped"),
        "multi_target_counts": record_count_by_key(records, "multi_target"),
        "offline_queue_supported_counts": record_count_by_key(records, "offline_queue_supported"),
        "has_records_counts": record_count_by_key(records, "has_records"),
        "has_actions_counts": record_count_by_key(records, "has_actions"),
        "has_enter_runnable_actions_counts": record_count_by_key(records, "has_enter_runnable_actions"),
        "has_pending_work_counts": record_count_by_key(records, "has_pending_work"),
        "has_warnings_counts": record_count_by_key(records, "has_warnings"),
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
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "tui_shortcut_counts": record_count_by_key(records, "tui_shortcut"),
        "line_mode_action_counts": record_count_by_key(records, "line_mode_action"),
    }


def target_workflow_action_indexes(records):
    return {
        "target_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "target_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "target_workflow_actions_by_target_id": records_by_key(records, "target_id"),
        "target_workflow_actions_by_category": records_by_key(records, "category"),
        "target_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "target_workflow_actions_by_available": records_by_key(records, "available"),
        "target_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "target_workflow_actions_by_offline_supported": records_by_key(records, "offline_supported"),
        "target_workflow_actions_by_requires_target_online": records_by_key(records, "requires_target_online"),
        "target_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "target_workflow_actions_by_target_phone_home_required": records_by_key(records, "target_phone_home_required"),
        "target_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_workflow_actions_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "target_workflow_actions_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "target_workflow_actions_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "target_workflow_actions_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "target_workflow_actions_by_target_latest_phone_home_status": records_by_key(records, "target_latest_phone_home_status"),
        "target_workflow_actions_by_target_latest_successful_phone_home_status": records_by_key(records, "target_latest_successful_phone_home_status"),
        "target_workflow_actions_by_target_last_failed_phone_home_status": records_by_key(records, "target_last_failed_phone_home_status"),
        "target_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "target_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "target_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
    }


def target_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "target_counts": record_count_by_key(records, "target_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "offline_supported_count": len([rec for rec in records or [] if rec.get("offline_supported") is True]),
        "requires_target_online_count": len([rec for rec in records or [] if rec.get("requires_target_online") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "target_phone_home_required_count": len([rec for rec in records or [] if rec.get("target_phone_home_required") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "target_connectivity_state_counts": record_count_by_key(records, "target_connectivity_state"),
        "target_offline_age_bucket_counts": record_count_by_key(records, "target_offline_age_bucket"),
        "target_poll_overdue_counts": record_count_by_key(records, "target_poll_overdue"),
        "target_mailbox_pending_work_count_counts": record_count_by_key(records, "target_mailbox_pending_work_count"),
        "target_latest_phone_home_status_counts": record_count_by_key(records, "target_latest_phone_home_status"),
        "target_latest_successful_phone_home_status_counts": record_count_by_key(records, "target_latest_successful_phone_home_status"),
        "target_last_failed_phone_home_status_counts": record_count_by_key(records, "target_last_failed_phone_home_status"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "offline_supported_counts": record_count_by_key(records, "offline_supported"),
        "requires_target_online_counts": record_count_by_key(records, "requires_target_online"),
        "queues_offline_work_counts": record_count_by_key(records, "queues_offline_work"),
        "target_phone_home_required_counts": record_count_by_key(records, "target_phone_home_required"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
    }


def probe_workflow_action_indexes(records):
    return {
        "probe_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "probe_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "probe_workflow_actions_by_category": records_by_key(records, "category"),
        "probe_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "probe_workflow_actions_by_actual": records_by_key(records, "actual"),
        "probe_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "probe_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "probe_workflow_actions_by_requires_bridge": records_by_key(records, "requires_bridge"),
        "probe_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "probe_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "probe_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "probe_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "probe_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "probe_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "probe_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "probe_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "probe_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "probe_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "probe_workflow_actions_by_available": records_by_key(records, "available"),
        "probe_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "probe_workflow_actions_by_target_phone_home_required": records_by_key(records, "target_phone_home_required"),
        "probe_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "probe_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "probe_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "probe_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def probe_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "target_phone_home_required_count": len([rec for rec in records or [] if rec.get("target_phone_home_required") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "requires_bridge_counts": record_count_by_key(records, "requires_bridge"),
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
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def print_workbench_action_summary(doc):
    doc = doc or {}
    summary = doc.get("summary") or {}
    print(
        "Operator console workflow summary: "
        f"total={summary.get('operator_console_workflow_count', 0)} "
        f"target_scoped={summary.get('operator_console_workflow_target_scoped_count', 0)} "
        f"multi_target={summary.get('operator_console_workflow_multi_target_count', 0)} "
        f"offline_queue={summary.get('operator_console_workflow_offline_queue_supported_count', 0)} "
        f"has_actions={summary.get('operator_console_workflow_has_actions_count', 0)} "
        f"pending={summary.get('operator_console_workflow_has_pending_work_count', 0)} "
        f"warnings={summary.get('operator_console_workflow_has_warnings_count', 0)}"
    )
    print(f"  workflow groups: {format_counts(summary.get('operator_console_workflow_group_counts') or {})}")
    print(f"  workflow states: {format_counts(summary.get('operator_console_workflow_operator_action_state_counts') or {})}")
    print(
        "Build config field summary: "
        f"total={summary.get('workbench_config_field_count', 0)} "
        f"configured={summary.get('workbench_config_field_configured_count', 0)} "
        f"fixed_options={summary.get('workbench_config_field_fixed_option_count', 0)} "
        f"control_like={summary.get('workbench_config_field_control_like_count', 0)}"
    )
    print(f"  config categories: {format_counts(summary.get('workbench_config_field_category_counts') or {})}")
    print(f"  config safety: {format_counts(summary.get('workbench_config_field_safety_boundary_counts') or {})}")
    print(
        "Workbench action summary: "
        f"total={summary.get('workbench_action_count', 0)} "
        f"background_supported={summary.get('workbench_action_background_supported_count', 0)} "
        f"long_running={summary.get('workbench_action_long_running_count', 0)} "
        f"writes_config={summary.get('workbench_action_writes_config_count', 0)} "
        f"runs_build={summary.get('workbench_action_runs_build_count', 0)} "
        f"requires_confirmation={summary.get('workbench_action_requires_confirmation_count', 0)} "
        f"target_execution={summary.get('workbench_action_target_execution_count', 0)} "
        f"foreground_runnable={summary.get('workbench_action_foreground_runnable_count', 0)} "
        f"dry_run_supported={summary.get('workbench_action_dry_run_supported_count', 0)} "
        f"enter_runnable={summary.get('workbench_action_can_run_from_curses_enter_count', 0)}"
    )
    print(f"  categories: {format_counts(summary.get('workbench_action_category_counts') or {})}")
    print(f"  execution defaults: {format_counts(summary.get('workbench_action_execution_default_counts') or {})}")
    print(f"  events: {format_counts(summary.get('workbench_action_event_counts') or {})}")
    print(f"  action states: {format_counts(summary.get('workbench_action_operator_action_state_counts') or {})}")
    print(
        "Operator daemon workflow action summary: "
        f"total={summary.get('operator_daemon_workflow_action_count', 0)} "
        f"attached={summary.get('operator_daemon_workflow_action_attached_count', 0)} "
        f"background_supported={summary.get('operator_daemon_workflow_action_background_supported_count', 0)} "
        f"requires_confirmation={summary.get('operator_daemon_workflow_action_requires_confirmation_count', 0)} "
        f"dry_run_supported={summary.get('operator_daemon_workflow_action_dry_run_supported_count', 0)} "
        f"enter_runnable={summary.get('operator_daemon_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('operator_daemon_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('operator_daemon_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  daemon workflows: {format_counts(summary.get('operator_daemon_workflow_action_workflow_counts') or {})}")
    print(f"  daemon action states: {format_counts(summary.get('operator_daemon_workflow_action_operator_action_state_counts') or {})}")
    print(
        "Service workflow action summary: "
        f"total={summary.get('service_workflow_action_count', 0)} "
        f"available={summary.get('service_workflow_action_available_count', 0)} "
        f"requires_confirmation={summary.get('service_workflow_action_requires_confirmation_count', 0)} "
        f"enter_runnable={summary.get('service_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('service_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('service_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('service_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  service workflows: {format_counts(summary.get('service_workflow_action_workflow_counts') or {})}")
    print(f"  service action states: {format_counts(summary.get('service_workflow_action_operator_action_state_counts') or {})}")
    print(
        "Target workflow action summary: "
        f"total={summary.get('target_workflow_action_count', 0)} "
        f"available={summary.get('target_workflow_action_available_count', 0)} "
        f"requires_input={summary.get('target_workflow_action_requires_input_count', 0)} "
        f"offline_supported={summary.get('target_workflow_action_offline_supported_count', 0)} "
        f"requires_online={summary.get('target_workflow_action_requires_target_online_count', 0)} "
        f"enter_runnable={summary.get('target_workflow_action_can_run_from_curses_enter_count', 0)}"
    )
    print(f"  target workflow categories: {format_counts(summary.get('target_workflow_action_category_counts') or {})}")
    print(f"  target workflows: {format_counts(summary.get('target_workflow_action_workflow_counts') or {})}")
    print(f"  offline work: {format_counts(summary.get('target_workflow_action_queues_offline_work_counts') or {})}")
    print(f"  action states: {format_counts(summary.get('target_workflow_action_operator_action_state_counts') or {})}")
    print(
        "Probe workflow action summary: "
        f"total={summary.get('probe_workflow_action_count', 0)} "
        f"available={summary.get('probe_workflow_action_available_count', 0)} "
        f"requires_confirmation={summary.get('probe_workflow_action_requires_confirmation_count', 0)} "
        f"target_phone_home_required={summary.get('probe_workflow_action_target_phone_home_required_count', 0)} "
        f"enter_runnable={summary.get('probe_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('probe_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('probe_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('probe_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  probe routes: {format_counts(summary.get('probe_workflow_action_route_kind_counts') or {})}")
    print(f"  probe bridges: {format_counts(summary.get('probe_workflow_action_bridge_profile_counts') or {})}")
    print(f"  probe action states: {format_counts(summary.get('probe_workflow_action_operator_action_state_counts') or {})}")
    print(
        "Command queue workflow action summary: "
        f"total={summary.get('command_queue_workflow_action_count', 0)} "
        f"requires_input={summary.get('command_queue_workflow_action_requires_input_count', 0)} "
        f"requires_confirmation={summary.get('command_queue_workflow_action_requires_confirmation_count', 0)} "
        f"queues_offline_work={summary.get('command_queue_workflow_action_queues_offline_work_count', 0)} "
        f"target_phone_home_required={summary.get('command_queue_workflow_action_target_phone_home_required_count', 0)} "
        f"enter_runnable={summary.get('command_queue_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('command_queue_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('command_queue_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('command_queue_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  command queue categories: {format_counts(summary.get('command_queue_workflow_action_category_counts') or {})}")
    print(f"  command queue action states: {format_counts(summary.get('command_queue_workflow_action_operator_action_state_counts') or {})}")
    print(
        "File service workflow action summary: "
        f"total={summary.get('file_service_workflow_action_count', 0)} "
        f"available={summary.get('file_service_workflow_action_available_count', 0)} "
        f"requires_input={summary.get('file_service_workflow_action_requires_input_count', 0)} "
        f"requires_confirmation={summary.get('file_service_workflow_action_requires_confirmation_count', 0)} "
        f"enter_runnable={summary.get('file_service_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('file_service_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('file_service_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('file_service_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  file workflows: {format_counts(summary.get('file_service_workflow_action_workflow_counts') or {})}")
    print(f"  file action states: {format_counts(summary.get('file_service_workflow_action_operator_action_state_counts') or {})}")
