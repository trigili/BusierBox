"""Staged-file workflow action helpers for grit-console."""

from pathlib import Path

from gritlib.record_utils import int_value, record_count_by_key, records_by_key
from gritlib.shell_utils import shquote


DEFAULT_SERVER_CONFIG = Path("local/server-config.json")


def _staged_file_workflow_fleet_context(target_records):
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
        "target_records": target_records,
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_mailbox_pending_target_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
    }


def _staged_file_workflow_action_record(base, targets_by_id, fleet_context, rec, action_id,
                                        category, label, command, workflow, action_state,
                                        action_reason, available=True,
                                        requires_confirmation=False, requires_target=False,
                                        queues_offline_work=False,
                                        can_run_from_curses_enter=False,
                                        curses_enter_action=""):
    request = str(rec.get("request_name") or rec.get("name") or "")
    if not request:
        return None
    target_id = str(rec.get("target_id") or "")
    target = targets_by_id.get(target_id) or {}
    target_records = fleet_context["target_records"]
    fleet_offline_target_count = fleet_context["fleet_offline_target_count"]
    fleet_stale_target_count = fleet_context["fleet_stale_target_count"]
    fleet_mailbox_pending_work_count = fleet_context["fleet_mailbox_pending_work_count"]
    fleet_poll_overdue_target_count = fleet_context["fleet_poll_overdue_target_count"]
    return {
        "id": f"{request}:{action_id}",
        "action_id": action_id,
        "request_name": request,
        "name": str(rec.get("name") or request),
        "stage_kind": str(rec.get("stage_kind") or "file"),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": base + " --run-staged-file-workflow-action " + shquote(f"{request}:{action_id}"),
        "target_id": target_id,
        "target_label": str(rec.get("target_label") or ""),
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
        "route_kind": str(rec.get("route_kind") or ""),
        "bridge_profile": str(rec.get("bridge_profile") or ""),
        "bridge_route_path": str(rec.get("bridge_route_path") or ""),
        "source_path": str(rec.get("source_path") or ""),
        "source_exists": bool(rec.get("source_exists")),
        "release_path": str(rec.get("release_path") or ""),
        "tuple_path": str(rec.get("tuple_path") or ""),
        "payload_preset": str(rec.get("payload_preset") or ""),
        "sha256": str(rec.get("sha256") or ""),
        "size": rec.get("size", ""),
        "fetch_command": str(rec.get("fetch_command") or ""),
        "fetch_command_force": str(rec.get("fetch_command_force") or ""),
        "fleet_target_count": len(target_records),
        "fleet_connectivity_state_counts": record_count_by_key(target_records, "connectivity_state"),
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_context["fleet_mailbox_pending_target_count"],
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
        "fleet_has_offline_targets": fleet_offline_target_count > 0,
        "fleet_has_stale_targets": fleet_stale_target_count > 0,
        "fleet_has_mailbox_pending_work": fleet_mailbox_pending_work_count > 0,
        "fleet_has_poll_overdue_targets": fleet_poll_overdue_target_count > 0,
        "available": bool(available),
        "requires_input": False,
        "requires_confirmation": bool(requires_confirmation),
        "requires_target": bool(requires_target),
        "queues_offline_work": bool(queues_offline_work),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side staged file workflow; delivery still requires explicit target-side command or poll",
    }


def _append_staged_file_workflow_action(records, base, targets_by_id, fleet_context, rec,
                                        action_id, category, label, command, workflow,
                                        action_state, action_reason, **kwargs):
    action = _staged_file_workflow_action_record(
        base,
        targets_by_id,
        fleet_context,
        rec,
        action_id,
        category,
        label,
        command,
        workflow,
        action_state,
        action_reason,
        **kwargs,
    )
    if action:
        records.append(action)


def _staged_file_single_request_workflow_actions(base, targets_by_id, fleet_context, rec):
    records = []
    request = str(rec.get("request_name") or rec.get("name") or "")
    if not request:
        return records
    target_id = str(rec.get("target_id") or "")
    add = lambda *args, **kwargs: _append_staged_file_workflow_action(
        records,
        base,
        targets_by_id,
        fleet_context,
        rec,
        *args,
        **kwargs,
    )
    add(
        "inspect-staged", "inspect", f"Inspect staged request {request}",
        base + " --list-staged", "file-service", "ready", "run-now",
    )
    add(
        "show-fetch-command", "file-transfer", f"Show command to run on target for {request}",
        base + " --list-staged", "file-service", "ready", "show-command",
        can_run_from_curses_enter=True, curses_enter_action="show-fetch-command",
    )
    if target_id:
        queue_command = (
            base + " --target-id " + shquote(target_id)
            + " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name "
            + shquote(request)
        )
        add(
            "queue-staged-fetch", "mailbox", f"Queue staged fetch for {target_id}",
            queue_command, "command-queue", "queueable-offline", "queues-until-phone-home",
            requires_target=True, queues_offline_work=True,
        )
        if records:
            records[-1]["run_command"] = base + " --run-staged-file-workflow-action " + shquote(f"{request}:queue-staged-fetch")
    else:
        add(
            "queue-staged-fetch", "mailbox", "Queue staged fetch for a selected target",
            base + " --target-id TARGET_ID --run-target-workflow-action queue-staged-fetch --target-workflow-request-name " + shquote(request),
            "command-queue", "needs-target", "target-required",
            available=False, requires_target=True, queues_offline_work=True,
        )
        if records:
            records[-1]["run_command"] = base + " --target-id TARGET_ID --run-staged-file-workflow-action " + shquote(f"{request}:queue-staged-fetch")
    add(
        "unstage", "configuration", f"Remove staged request {request}",
        base + " --unstage " + shquote(request) + " --list-staged",
        "file-service", "confirm-required", "confirmation-required",
        requires_confirmation=True,
    )
    if records:
        records[-1]["run_command"] = base + " --run-staged-file-workflow-action " + shquote(f"{request}:unstage") + " --confirm-staged-file-workflow-action"
    return records


def staged_file_workflow_action_records(cfg, staged_records, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    config_path = str(cfg.get("_config_path", default_config))
    base = "scripts/grit-console --config " + shquote(config_path)
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    targets_by_id = {str(rec.get("target_id") or ""): rec for rec in target_records if rec.get("target_id")}
    fleet_context = _staged_file_workflow_fleet_context(target_records)
    records = []
    for rec in staged_records or []:
        if not isinstance(rec, dict):
            continue
        records.extend(_staged_file_single_request_workflow_actions(
            base,
            targets_by_id,
            fleet_context,
            rec,
        ))
    records.sort(key=lambda rec: (rec.get("request_name", ""), rec.get("category", ""), rec.get("action_id", "")))
    return records


def staged_file_workflow_action_indexes(records):
    return {
        "staged_file_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "staged_file_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "staged_file_workflow_actions_by_request_name": records_by_key(records, "request_name"),
        "staged_file_workflow_actions_by_stage_kind": records_by_key(records, "stage_kind"),
        "staged_file_workflow_actions_by_category": records_by_key(records, "category"),
        "staged_file_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "staged_file_workflow_actions_by_target_id": records_by_key(records, "target_id"),
        "staged_file_workflow_actions_by_target_connectivity_state": records_by_key(records, "target_connectivity_state"),
        "staged_file_workflow_actions_by_target_offline_age_bucket": records_by_key(records, "target_offline_age_bucket"),
        "staged_file_workflow_actions_by_target_poll_overdue": records_by_key(records, "target_poll_overdue"),
        "staged_file_workflow_actions_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "staged_file_workflow_actions_by_target_latest_phone_home_status": records_by_key(records, "target_latest_phone_home_status"),
        "staged_file_workflow_actions_by_target_latest_successful_phone_home_status": records_by_key(records, "target_latest_successful_phone_home_status"),
        "staged_file_workflow_actions_by_target_last_failed_phone_home_status": records_by_key(records, "target_last_failed_phone_home_status"),
        "staged_file_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "staged_file_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "staged_file_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "staged_file_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "staged_file_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "staged_file_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "staged_file_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "staged_file_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "staged_file_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "staged_file_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "staged_file_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "staged_file_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "staged_file_workflow_actions_by_source_exists": records_by_key(records, "source_exists"),
        "staged_file_workflow_actions_by_available": records_by_key(records, "available"),
        "staged_file_workflow_actions_by_requires_target": records_by_key(records, "requires_target"),
        "staged_file_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "staged_file_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "staged_file_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "staged_file_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "staged_file_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "staged_file_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def staged_file_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "request_counts": record_count_by_key(records, "request_name"),
        "stage_kind_counts": record_count_by_key(records, "stage_kind"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "target_counts": record_count_by_key(records, "target_id"),
        "target_connectivity_state_counts": record_count_by_key(records, "target_connectivity_state"),
        "target_offline_age_bucket_counts": record_count_by_key(records, "target_offline_age_bucket"),
        "target_poll_overdue_counts": record_count_by_key(records, "target_poll_overdue"),
        "target_mailbox_pending_work_count_counts": record_count_by_key(records, "target_mailbox_pending_work_count"),
        "target_latest_phone_home_status_counts": record_count_by_key(records, "target_latest_phone_home_status"),
        "target_latest_successful_phone_home_status_counts": record_count_by_key(records, "target_latest_successful_phone_home_status"),
        "target_last_failed_phone_home_status_counts": record_count_by_key(records, "target_last_failed_phone_home_status"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "action_counts": record_count_by_key(records, "action_id"),
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
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_target_count": len([rec for rec in records or [] if rec.get("requires_target") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "source_exists_counts": record_count_by_key(records, "source_exists"),
        "available_counts": record_count_by_key(records, "available"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }
