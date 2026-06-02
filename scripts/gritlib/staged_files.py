"""Staged file state, index, and summary helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import record_count_by_key, records_by_key


def staged_file_path(cfg):
    return Path(str(cfg.get("staged_files", "local/operator-session/staged-files.json")))


def staged_files_state_record(cfg):
    path = staged_file_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "staged_count": 0,
        "request_names": [],
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "staged-files JSON is not an object"
            return rec
        staged = data.get("staged")
        if not isinstance(staged, dict):
            rec["error"] = "staged-files JSON staged field is not an object"
            return rec
        request_names = sorted(str(name) for name in staged if str(name))
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "staged_count": len(request_names),
            "request_names": request_names,
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def staged_record_indexes(records):
    by_request = {}
    by_kind = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_fetch_command = {}
    by_fetch_command_force = {}
    by_source_exists = {"yes": [], "no": []}
    by_kind_source_exists = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or rec.get("name") or "")
        kind = str(rec.get("stage_kind") or "file")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        fetch_command = str(rec.get("fetch_command") or "")
        fetch_command_force = str(rec.get("fetch_command_force") or "")
        source_exists = "yes" if rec.get("source_exists") is True else "no"
        if request_name:
            by_request[request_name] = rec
        if kind:
            by_kind.setdefault(kind, []).append(rec)
            by_kind_source_exists.setdefault(f"{kind}:{source_exists}", []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path[source_path] = rec
        if fetch_command:
            by_fetch_command[fetch_command] = rec
        if fetch_command_force:
            by_fetch_command_force[fetch_command_force] = rec
        by_source_exists[source_exists].append(rec)
    return (
        by_request, by_kind, by_sha256, by_target_id, by_source_path,
        by_fetch_command, by_fetch_command_force,
        by_source_exists, by_kind_source_exists,
    )

def staged_record_summary(records):
    total_size = 0
    source_exists_count = 0
    source_missing_count = 0
    fetch_command_count = 0
    fetch_command_force_count = 0
    source_exists_by_kind = {}
    source_missing_by_kind = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("stage_kind") or "file")
        try:
            total_size += int(rec.get("size", 0) or 0)
        except (TypeError, ValueError):
            pass
        if rec.get("fetch_command"):
            fetch_command_count += 1
        if rec.get("fetch_command_force"):
            fetch_command_force_count += 1
        if rec.get("source_exists") is True:
            source_exists_count += 1
            source_exists_by_kind[kind] = source_exists_by_kind.get(kind, 0) + 1
        else:
            source_missing_count += 1
            source_missing_by_kind[kind] = source_missing_by_kind.get(kind, 0) + 1
    return {
        "total_size": total_size,
        "source_exists_count": source_exists_count,
        "source_missing_count": source_missing_count,
        "fetch_command_count": fetch_command_count,
        "fetch_command_force_count": fetch_command_force_count,
        "target_counts": record_count_by_key(records, "target_id"),
        "source_exists_by_kind": source_exists_by_kind,
        "source_missing_by_kind": source_missing_by_kind,
    }


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
