"""Staged-file record indexes and status summaries."""

from gritlib.record_utils import latest_record_value, record_count_by_key
import gritlib.staged_file_workflow_actions as staged_file_workflow_actions


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


def _staged_status_record_summary(records, staged_summary):
    return {
        "staged_count": len(records),
        "staged_total_size": staged_summary.get("total_size", 0),
        "staged_kind_counts": record_count_by_key(records, "stage_kind"),
        "staged_target_counts": staged_summary.get("target_counts") or {},
        "staged_source_exists_count": staged_summary.get("source_exists_count", 0),
        "staged_source_missing_count": staged_summary.get("source_missing_count", 0),
        "staged_fetch_command_count": staged_summary.get("fetch_command_count", 0),
        "staged_fetch_command_force_count": staged_summary.get(
            "fetch_command_force_count", 0
        ),
        "staged_source_exists_kind_counts": staged_summary.get(
            "source_exists_by_kind"
        ) or {},
        "staged_source_missing_kind_counts": staged_summary.get(
            "source_missing_by_kind"
        ) or {},
        "latest_staged_at": latest_record_value(records, ("staged_at",)),
    }


def _staged_status_workflow_total_summary(action_summary):
    return {
        "staged_file_workflow_action_count": action_summary.get("total_count", 0),
        "staged_file_workflow_action_available_count": action_summary.get(
            "available_count", 0
        ),
        "staged_file_workflow_action_requires_target_count": action_summary.get(
            "requires_target_count", 0
        ),
        "staged_file_workflow_action_queues_offline_work_count": action_summary.get(
            "queues_offline_work_count", 0
        ),
        "staged_file_workflow_action_requires_confirmation_count": action_summary.get(
            "requires_confirmation_count", 0
        ),
        "staged_file_workflow_action_can_run_from_curses_enter_count": action_summary.get(
            "can_run_from_curses_enter_count", 0
        ),
        "staged_file_workflow_action_request_counts": action_summary.get(
            "request_counts"
        ) or {},
        "staged_file_workflow_action_stage_kind_counts": action_summary.get(
            "stage_kind_counts"
        ) or {},
        "staged_file_workflow_action_category_counts": action_summary.get(
            "category_counts"
        ) or {},
        "staged_file_workflow_action_workflow_counts": action_summary.get(
            "workflow_counts"
        ) or {},
    }


def _staged_status_workflow_target_summary(action_summary):
    return {
        "staged_file_workflow_action_target_counts": action_summary.get(
            "target_counts"
        ) or {},
        "staged_file_workflow_action_target_connectivity_state_counts": action_summary.get(
            "target_connectivity_state_counts"
        ) or {},
        "staged_file_workflow_action_target_offline_age_bucket_counts": action_summary.get(
            "target_offline_age_bucket_counts"
        ) or {},
        "staged_file_workflow_action_target_poll_overdue_counts": action_summary.get(
            "target_poll_overdue_counts"
        ) or {},
        "staged_file_workflow_action_target_mailbox_pending_work_count_counts": action_summary.get(
            "target_mailbox_pending_work_count_counts"
        ) or {},
        "staged_file_workflow_action_target_latest_phone_home_status_counts": action_summary.get(
            "target_latest_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_target_latest_successful_phone_home_status_counts": action_summary.get(
            "target_latest_successful_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_target_last_failed_phone_home_status_counts": action_summary.get(
            "target_last_failed_phone_home_status_counts"
        ) or {},
        "staged_file_workflow_action_route_kind_counts": action_summary.get(
            "route_kind_counts"
        ) or {},
        "staged_file_workflow_action_bridge_profile_counts": action_summary.get(
            "bridge_profile_counts"
        ) or {},
    }


def _staged_status_workflow_action_summary(action_summary):
    return {
        "staged_file_workflow_action_action_counts": action_summary.get(
            "action_counts"
        ) or {},
    }


def _staged_status_workflow_fleet_summary(action_summary):
    return {
        "staged_file_workflow_action_fleet_target_count_counts": action_summary.get(
            "fleet_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_offline_target_count_counts": action_summary.get(
            "fleet_offline_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_stale_target_count_counts": action_summary.get(
            "fleet_stale_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_mailbox_pending_target_count_counts": action_summary.get(
            "fleet_mailbox_pending_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_mailbox_pending_work_count_counts": action_summary.get(
            "fleet_mailbox_pending_work_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_poll_overdue_target_count_counts": action_summary.get(
            "fleet_poll_overdue_target_count_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_offline_targets_counts": action_summary.get(
            "fleet_has_offline_targets_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_stale_targets_counts": action_summary.get(
            "fleet_has_stale_targets_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_mailbox_pending_work_counts": action_summary.get(
            "fleet_has_mailbox_pending_work_counts"
        ) or {},
        "staged_file_workflow_action_fleet_has_poll_overdue_targets_counts": action_summary.get(
            "fleet_has_poll_overdue_targets_counts"
        ) or {},
    }


def _staged_status_workflow_source_summary(action_summary):
    return {
        "staged_file_workflow_action_source_exists_counts": action_summary.get(
            "source_exists_counts"
        ) or {},
        "staged_file_workflow_action_available_counts": action_summary.get(
            "available_counts"
        ) or {},
        "staged_file_workflow_action_operator_action_state_counts": action_summary.get(
            "operator_action_state_counts"
        ) or {},
        "staged_file_workflow_action_operator_action_reason_counts": action_summary.get(
            "operator_action_reason_counts"
        ) or {},
        "staged_file_workflow_action_can_run_from_curses_enter_counts": action_summary.get(
            "can_run_from_curses_enter_counts"
        ) or {},
        "staged_file_workflow_action_curses_enter_action_counts": action_summary.get(
            "curses_enter_action_counts"
        ) or {},
    }


def staged_status_summary(records, workflow_action_records=None):
    records = records or []
    staged_summary = staged_record_summary(records)
    action_summary = staged_file_workflow_actions.staged_file_workflow_action_summary(
        workflow_action_records
    )
    summary = {}
    summary.update(_staged_status_record_summary(records, staged_summary))
    summary.update(_staged_status_workflow_total_summary(action_summary))
    summary.update(_staged_status_workflow_target_summary(action_summary))
    summary.update(_staged_status_workflow_action_summary(action_summary))
    summary.update(_staged_status_workflow_fleet_summary(action_summary))
    summary.update(_staged_status_workflow_source_summary(action_summary))
    return summary
