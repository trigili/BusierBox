"""Shared workflow action command and fleet metric helpers."""

from gritlib.line_search import line_record_selection_result
from gritlib.record_utils import int_value, record_count_by_key
from gritlib.shell_utils import shquote


def target_id_arg(target_id):
    return " --target-id " + shquote(target_id)


def optional_target_id_arg(target_id):
    return target_id_arg(target_id) if target_id else ""


def target_scoped_command(base_command, target_id, suffix):
    return str(base_command) + target_id_arg(target_id) + str(suffix)


def optional_target_scoped_command(base_command, target_arg, suffix):
    return str(base_command) + str(target_arg or "") + str(suffix)


def scoped_service_workflow_run_command(base_command, target_arg, service_name, action_id, extra_args=""):
    command = (
        str(base_command)
        + str(target_arg or "")
        + " --run-"
        + str(service_name)
        + "-workflow-action "
        + shquote(f"{service_name}:{action_id}")
    )
    if extra_args:
        command += str(extra_args)
    return command


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


def select_workbench_action(records, selector):
    text = str(selector or "").strip()
    selection = line_record_selection_result(
        text,
        records,
        label="workbench action",
        usage_message="workbench action is required",
        match_func=lambda rec, value: value == str(rec.get("id") or ""),
    )
    if not selection.selected:
        if selection.reason == "not-found":
            raise ValueError(f"unknown workbench action: {text}")
        raise ValueError(selection.message)
    return selection.item
