"""Workflow action index, summary, and display helpers for grit-console."""

import shlex

from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, record_sum_by_key, records_by_key,
)


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


def select_workbench_action(records, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("workbench action is required")
    records = records or []
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"workbench action number out of range: {text}")
        return records[idx]
    for rec in records:
        if text == str(rec.get("id") or ""):
            return rec
    raise ValueError(f"unknown workbench action: {text}")


def workflow_action_count(records):
    return len([rec for rec in records or [] if isinstance(rec, dict)])


def workflow_enter_count(records):
    return len([
        rec for rec in records or []
        if isinstance(rec, dict) and rec.get("can_run_from_curses_enter") is True
    ])


def workflow_queue_count(records):
    return len([
        rec for rec in records or []
        if isinstance(rec, dict) and rec.get("queues_offline_work") is True
    ])


def operator_console_headless_command(kind, base_command):
    commands = {
        "targets": base_command + " --status",
        "target-actions": base_command + " --status",
        "mailbox": base_command + " --list-command-queue",
        "bridges": base_command + " --status",
        "files": base_command + " --status",
        "survey": base_command + " --status",
        "daemon": base_command + " --status",
        "release": base_command + " --status",
        "build-config": base_command + " --status",
        "jobs": base_command + " --status",
        "events": base_command + " --status",
        "activity": base_command + " --status",
    }
    return commands.get(kind, base_command + " --status")


def annotate_operator_console_workflows(records, target_records, overdue_targets):
    target_records = list(target_records or [])
    overdue_targets = list(overdue_targets or [])
    fleet_connectivity_state_counts = record_count_by_key(target_records, "connectivity_state")
    fleet_offline_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "offline"
    ])
    fleet_stale_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "stale"
    ])
    fleet_mailbox_pending_target_count = len([
        rec for rec in target_records
        if int(rec.get("mailbox_pending_work_count") or 0) > 0
    ])
    fleet_mailbox_pending_work_count = sum(
        int(rec.get("mailbox_pending_work_count") or 0)
        for rec in target_records
    )
    fleet_poll_overdue_target_count = len(overdue_targets)
    for idx, rec in enumerate(records or []):
        pending = int(rec.get("pending_work_count") or 0)
        warning_count = int(rec.get("warning_count") or 0)
        rec["ordinal"] = idx
        rec["fleet_target_count"] = len(target_records)
        rec["fleet_connectivity_state_counts"] = fleet_connectivity_state_counts
        rec["fleet_offline_target_count"] = fleet_offline_target_count
        rec["fleet_stale_target_count"] = fleet_stale_target_count
        rec["fleet_mailbox_pending_target_count"] = fleet_mailbox_pending_target_count
        rec["fleet_mailbox_pending_work_count"] = fleet_mailbox_pending_work_count
        rec["fleet_poll_overdue_target_count"] = fleet_poll_overdue_target_count
        rec["fleet_has_offline_targets"] = fleet_offline_target_count > 0
        rec["fleet_has_stale_targets"] = fleet_stale_target_count > 0
        rec["fleet_has_mailbox_pending_work"] = fleet_mailbox_pending_work_count > 0
        rec["fleet_has_poll_overdue_targets"] = fleet_poll_overdue_target_count > 0
        rec["has_records"] = int(rec.get("record_count") or 0) > 0
        rec["has_actions"] = int(rec.get("action_count") or 0) > 0
        rec["has_enter_runnable_actions"] = int(rec.get("enter_runnable_action_count") or 0) > 0
        rec["has_pending_work"] = pending > 0
        rec["has_warnings"] = warning_count > 0
        rec["operator_action_state"] = "needs-attention" if warning_count else ("pending-work" if pending else "ready")
        rec["operator_action_reason"] = "warnings-present" if warning_count else ("pending-work" if pending else "workflow-ready")
        rec["api_resource_key"] = "api_collections." + str(rec.get("primary_collection") or "")
        rec["status_command"] = rec.get("headless_command", "")
    return records


def annotate_workbench_actions(records, cfg, run_command_builder, start_job_command_builder):
    placeholder_tokens = {
        "NAME", "ARTIFACT", "KEY=VALUE", "VALUE", "LOCAL_PATH",
        "REQUEST_NAME", "RELEASE_SELECTOR", "FIND_ARGS", "TOOL",
        "PATH", "MIRROR_DIR", "SOURCE", "ARCHIVE",
    }
    for rec in records or []:
        action_id = str(rec.get("id") or "")
        command = str(rec.get("command") or "")
        try:
            command_tokens = shlex.split(command)
        except ValueError:
            command_tokens = command.split()
        has_placeholder = any(token in placeholder_tokens for token in command_tokens)
        background = rec.get("background_supported") is True
        foreground_runnable = bool(command and not background and not has_placeholder)
        requires_confirmation = rec.get("requires_confirmation") is True
        if has_placeholder:
            operator_action_state = "needs-input"
            operator_action_reason = "input-placeholder"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        elif background:
            operator_action_state = "background-ready"
            operator_action_reason = "start-background-job"
            can_run_from_curses_enter = True
            curses_enter_action = "start-job"
        elif requires_confirmation:
            operator_action_state = "confirm-required"
            operator_action_reason = "confirmation-required"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        elif foreground_runnable:
            operator_action_state = "ready"
            operator_action_reason = "run-now"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        else:
            operator_action_state = "unavailable"
            operator_action_reason = "no-runnable-command"
            can_run_from_curses_enter = False
            curses_enter_action = "none"
        rec["has_placeholder"] = bool(has_placeholder)
        rec["foreground_runnable"] = foreground_runnable
        rec["dry_run_supported"] = foreground_runnable
        rec["has_run_command"] = foreground_runnable
        rec["has_dry_run_command"] = foreground_runnable
        rec["has_start_job_command"] = background
        rec["operator_action_state"] = operator_action_state
        rec["operator_action_reason"] = operator_action_reason
        rec["can_run_from_curses_enter"] = bool(can_run_from_curses_enter)
        rec["curses_enter_action"] = curses_enter_action
        rec["run_command"] = run_command_builder(cfg, action_id) if foreground_runnable else ""
        rec["dry_run_command"] = run_command_builder(cfg, action_id, dry_run=True) if foreground_runnable else ""
        rec["start_job_command"] = start_job_command_builder(cfg, action_id) if background else ""
    return records


def target_workflow_action_readiness(
    target,
    requires_input=False,
    available=True,
    requires_target_online=False,
    queues_offline_work=False,
    target_phone_home_required=False,
):
    target_state = str((target or {}).get("connectivity_state") or "")
    if not available:
        return "unavailable", "unavailable", False
    if requires_target_online and target_state not in ("online", "recent"):
        return "blocked", "target-not-online", False
    if requires_input:
        return "needs-input", "input-required", False
    if queues_offline_work and target_phone_home_required:
        return "queueable-offline", "queues-until-phone-home", True
    return "ready", "run-now", True


def target_workflow_action_record(
    target,
    action_id,
    category,
    label,
    command,
    workflow,
    requires_input=False,
    available=True,
    bridge_profile="",
    offline_supported=True,
    requires_target_online=False,
    queues_offline_work=False,
    target_phone_home_required=False,
):
    target_id = str((target or {}).get("target_id") or "")
    if not target_id:
        return None
    action_state, action_reason, can_run_from_curses_enter = target_workflow_action_readiness(
        target,
        requires_input=requires_input,
        available=available,
        requires_target_online=requires_target_online,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
    )
    return {
        "id": f"{target_id}:{action_id}",
        "action_id": action_id,
        "target_id": target_id,
        "target_label": str(target.get("label") or ""),
        "target_connectivity_state": str(target.get("connectivity_state") or ""),
        "target_last_seen": str(target.get("last_seen") or target.get("last_seen_at") or ""),
        "target_last_seen_via": str(target.get("last_seen_via") or ""),
        "target_offline_age_bucket": str(target.get("offline_age_bucket") or ""),
        "target_next_expected_poll": str(target.get("next_expected_poll") or ""),
        "target_poll_overdue": bool(target.get("poll_overdue", False)),
        "target_poll_overdue_for_sec": target.get("poll_overdue_for_sec", ""),
        "target_mailbox_command_count": int_value(target.get("mailbox_command_count", 0)),
        "target_mailbox_pending_work_count": int_value(target.get("mailbox_pending_work_count", 0)),
        "target_latest_phone_home_at": str(target.get("latest_phone_home_at") or ""),
        "target_latest_phone_home_status": str(target.get("latest_phone_home_status") or ""),
        "target_latest_phone_home_kind": str(target.get("latest_phone_home_kind") or ""),
        "target_latest_phone_home_contact_path": str(target.get("latest_phone_home_contact_path") or ""),
        "target_latest_successful_phone_home_at": str(target.get("latest_successful_phone_home_at") or ""),
        "target_latest_successful_phone_home_status": str(target.get("latest_successful_phone_home_status") or ""),
        "target_latest_successful_phone_home_kind": str(target.get("latest_successful_phone_home_kind") or ""),
        "target_latest_successful_phone_home_contact_path": str(target.get("latest_successful_phone_home_contact_path") or ""),
        "target_last_failed_phone_home_at": str(target.get("last_failed_phone_home_at") or ""),
        "target_last_failed_phone_home_status": str(target.get("last_failed_phone_home_status") or ""),
        "target_last_failed_phone_home_reason": str(target.get("last_failed_phone_home_reason") or ""),
        "target_last_failed_phone_home_contact_path": str(target.get("last_failed_phone_home_contact_path") or ""),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "requires_input": bool(requires_input),
        "available": bool(available),
        "bridge_profile": str(bridge_profile or ""),
        "offline_supported": bool(offline_supported),
        "requires_target_online": bool(requires_target_online),
        "queues_offline_work": bool(queues_offline_work),
        "target_phone_home_required": bool(target_phone_home_required),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side target workflow; target execution still requires explicit target-side command or poll",
    }


def workflow_fleet_metrics(target_records):
    target_records = [rec for rec in target_records or [] if isinstance(rec, dict)]
    fleet_mailbox_pending_work_count = sum(
        int_value(rec.get("mailbox_pending_work_count", 0))
        for rec in target_records
    )
    fleet_offline_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "offline"
    ])
    fleet_stale_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "stale"
    ])
    fleet_mailbox_pending_target_count = len([
        rec for rec in target_records
        if int_value(rec.get("mailbox_pending_work_count", 0)) > 0
    ])
    fleet_poll_overdue_target_count = len([
        rec for rec in target_records
        if rec.get("poll_overdue") is True
    ])
    return {
        "fleet_target_count": len(target_records),
        "fleet_connectivity_state_counts": record_count_by_key(target_records, "connectivity_state"),
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_mailbox_pending_target_count,
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
        "fleet_has_offline_targets": fleet_offline_target_count > 0,
        "fleet_has_stale_targets": fleet_stale_target_count > 0,
        "fleet_has_mailbox_pending_work": fleet_mailbox_pending_work_count > 0,
        "fleet_has_poll_overdue_targets": fleet_poll_overdue_target_count > 0,
    }


def service_workflow_action_record(
    service,
    action_id,
    category,
    label,
    command,
    run_command,
    dry_run_command,
    fleet_metrics,
    action_state,
    action_reason,
    can_run_from_curses_enter=False,
    curses_enter_action="",
    requires_confirmation=False,
):
    name = str((service or {}).get("name") or "")
    if not name:
        return None
    actual = str(service.get("actual") or "")
    configured = str(service.get("configured") or "")
    return {
        "id": f"{name}:{action_id}",
        "action_id": action_id,
        "service": name,
        "category": category,
        "workflow": "service-lifecycle",
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "dry_run_command": dry_run_command,
        "actual": actual,
        "configured": configured,
        "port": service.get("port", ""),
        "bind_address": str(service.get("bind_address") or ""),
        "tls": bool(service.get("tls", False)),
        "pid": service.get("pid", ""),
        "pid_alive": bool(service.get("pid_alive", False)),
        "pid_managed": bool(service.get("pid_managed", False)),
        "listener_pids": service.get("listener_pids") or [],
        "stale": bool(service.get("stale", False)),
        "has_error": bool(service.get("error")),
        "has_warnings": bool(service.get("warning_count", 0)),
        **(fleet_metrics or {}),
        "available": True,
        "requires_input": False,
        "requires_confirmation": bool(requires_confirmation),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side service lifecycle; starts/stops local griTTYkit listener processes only",
    }


def service_lifecycle_action_states(service):
    actual = str((service or {}).get("actual") or "")
    configured = str((service or {}).get("configured") or "")
    pid = (service or {}).get("pid", "")
    can_stop = actual == "listening" or configured in ("listening", "starting", "error") or bool(pid)
    if actual == "listening":
        start_state = "already-running"
        start_reason = "already-listening"
        start_enter = False
    else:
        start_state = "ready"
        start_reason = "start-listener"
        start_enter = True
    if can_stop:
        stop_state = "ready"
        stop_reason = "stop-listener"
        stop_enter = True
    else:
        stop_state = "not-running"
        stop_reason = "no-recorded-listener"
        stop_enter = False
    return {
        "start_state": start_state,
        "start_reason": start_reason,
        "start_enter": start_enter,
        "stop_state": stop_state,
        "stop_reason": stop_reason,
        "stop_enter": stop_enter,
    }


def file_service_workflow_action_record(
    action_id,
    category,
    label,
    command,
    workflow,
    run_command,
    target_filter_id,
    route,
    service_row,
    listen_port,
    fallback_bind_address,
    staged_count,
    upload_count,
    fetch_count,
    transfer_count,
    fleet_metrics,
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
    route = route or {}
    service_row = service_row or {}
    return {
        "id": f"file-service:{action_id}",
        "action_id": action_id,
        "service": "file-service",
        "actual": str(service_row.get("actual") or "unknown"),
        "configured": str(service_row.get("configured") or ""),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "target_id_filter": target_filter_id,
        "target_filter_active": bool(target_filter_id),
        "route_kind": str(route.get("route_kind") or "direct"),
        "route_host": str(route.get("host") or ""),
        "route_port": route.get("port", ""),
        "bridge_profile": str(route.get("bridge_profile") or ""),
        "bridge_route_path": str(route.get("bridge_route_path") or ""),
        "requires_bridge": bool(route.get("requires_bridge", False)),
        "port": service_row.get("port", listen_port),
        "bind_address": str(service_row.get("bind_address") or fallback_bind_address or ""),
        "tls": bool(service_row.get("tls", False)),
        "pid": service_row.get("pid", ""),
        "pid_alive": bool(service_row.get("pid_alive", False)),
        "staged_count": staged_count,
        "upload_count": upload_count,
        "fetch_count": fetch_count,
        "target_file_transfer_record_count": transfer_count,
        **(fleet_metrics or {}),
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
        "safety_boundary": "operator-side file workflow metadata; target upload/fetch still requires explicit target-side command or poll",
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


def probe_workflow_action_record(
    action_id,
    category,
    label,
    command,
    run_command,
    service_row,
    target_command,
    script_name,
    listen_host,
    listen_port,
    fleet_metrics,
    action_state,
    action_reason,
    available=True,
    requires_confirmation=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    service_row = service_row or {}
    return {
        "id": f"probe:{action_id}",
        "action_id": action_id,
        "service": "probe",
        "actual": str(service_row.get("actual") or "unknown"),
        "category": category,
        "workflow": "probe",
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "target_command": target_command,
        "script_name": str(script_name or "probe.sh").lstrip("/") or "probe.sh",
        "listen_host": str(listen_host or ""),
        "listen_port": listen_port,
        **(fleet_metrics or {}),
        "available": bool(available),
        "requires_input": False,
        "requires_confirmation": bool(requires_confirmation),
        "requires_target_online": False,
        "queues_offline_work": False,
        "target_phone_home_required": True,
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side probe service; target execution still requires explicit target-side wget pipe",
    }


def probe_listener_action_states(service_row):
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
