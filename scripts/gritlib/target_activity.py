"""Target activity record helpers for grit-console."""

import time

from gritlib.command_queue import load_command_queue
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.session_state import parse_utc_timestamp, utc_now
from gritlib.shell_utils import shquote
import gritlib.target_activity_display as target_activity_display
import gritlib.target_activity_feed as target_activity_feed
import gritlib.target_mailbox as target_mailbox
import gritlib.target_phone_home as target_phone_home
from gritlib.target_records import (
    configured_target_filter, details_with_target, event_for_target,
    print_workbench_target_selector, record_target_activity,
    select_workbench_target_record, selected_target_context,
)


def dispatch_legacy_target_activity_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    append_event_fn=None,
    scoped_target_cfg_func=None,
):
    if str(choice or "").strip() != "21":
        return False

    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg) if snapshot_func else {}
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    print_workbench_target_selector(targets, current_target_id=current)
    selected_line = input_func("target number/id/label, current, or all> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if not selected:
        return True
    try:
        selection = select_workbench_target_record(selected, targets, current_target_id=current)
        target = selection.get("target") or {}
        if selection.get("scope") == "all":
            headless = (
                "scripts/grit-console --config "
                + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                + " --json-status"
            )
            activity_doc = snap
            print("Target activity feed: all")
            print_target_activity_records(activity_doc, limit=12)
            activity_count = len(activity_doc.get("target_activity_records") or [])
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_target_activity_inspected", details={
                    "headless_command": headless,
                    "scope": "all",
                    "target_activity_record_count": activity_count,
                })
        else:
            target_id = str(target.get("target_id") or "")
            target_label = str(target.get("label") or target.get("target_label") or "")
            scoped = (
                scoped_target_cfg_func(cfg, target_id, target_label=target_label)
                if scoped_target_cfg_func else cfg
            )
            activity_doc = snapshot_func(scoped) if snapshot_func else {}
            headless = (
                "scripts/grit-console --config "
                + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                + " --target-id "
                + shquote(target_id)
                + " --json-status"
            )
            print(f"Target activity feed: {target_id} label={target_label or '-'}")
            print_target_activity_records(activity_doc, target_id=target_id, limit=12)
            activity_count = len(activity_doc.get("target_activity_records") or [])
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_target_activity_inspected", details={
                    "headless_command": headless,
                    "scope": "target",
                    "target_id": target_id,
                    "target_label": target_label,
                    "target_activity_record_count": activity_count,
                })
    except ValueError as exc:
        print(exc)
    return True


def dispatch_legacy_target_detail_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    append_event_fn=None,
    scoped_target_cfg_func=None,
    print_summary_func=None,
    action_state_text_func=None,
):
    if str(choice or "").strip() != "18":
        return False

    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg) if snapshot_func else {}
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    print_workbench_target_selector(targets, current_target_id=current)
    selected_line = input_func("target number/id/label, current, or all> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if not selected:
        return True
    try:
        selection = select_workbench_target_record(selected, targets, current_target_id=current)
        target = selection.get("target") or {}
        if selection.get("scope") == "all":
            headless = (
                "scripts/grit-console --config "
                + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                + " --status"
            )
            if print_summary_func:
                print_summary_func(snap)
            activity_count = len(snap.get("target_activity_records") or [])
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_targets_inspected", details={
                    "headless_command": headless,
                    "scope": "all",
                    "target_count": len(targets),
                    "target_activity_record_count": activity_count,
                })
            return True
        target_id = str(target.get("target_id") or "")
        target_label = str(target.get("label") or target.get("target_label") or "")
        scoped = (
            scoped_target_cfg_func(cfg, target_id, target_label=target_label)
            if scoped_target_cfg_func else cfg
        )
        scoped_snap = snapshot_func(scoped) if snapshot_func else {}
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --target-id "
            + shquote(target_id)
            + " --status"
        )
        print(f"Target detail: {target_id} label={target_label or '-'}")
        if print_summary_func:
            print_summary_func(scoped_snap, limit=3)
        target_activity_count = len(scoped_snap.get("target_activity_records") or [])
        print_target_activity_records(scoped_snap, target_id=target_id, limit=5)
        actions = scoped_snap.get("target_workflow_actions") or []
        if actions:
            print("Target workflow actions:")
            for idx, rec in enumerate(actions[:8], 1):
                state = action_state_text_func(rec) if action_state_text_func else str(rec.get("operator_action_state") or "-")
                print(f"  {idx}: {rec.get('id', '')} {rec.get('label', '')}")
                print(
                    f"     offline={'yes' if rec.get('offline_supported') else 'no'} "
                    f"requires_online={'yes' if rec.get('requires_target_online') else 'no'} "
                    f"queues_offline_work={'yes' if rec.get('queues_offline_work') else 'no'} "
                    f"state={state} "
                    f"reason={rec.get('operator_action_reason', '') or '-'} "
                    f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'}"
                )
        if append_event_fn:
            append_event_fn(cfg, "workbench", "workbench_target_inspected", details={
                "target_id": target_id,
                "target_label": target_label,
                "headless_command": headless,
                "mailbox_pending_work_count": target.get("mailbox_pending_work_count", 0),
                "last_seen": target.get("last_seen", "") or target.get("last_seen_at", ""),
                "target_activity_record_count": target_activity_count,
            })
    except ValueError as exc:
        print(exc)
    return True


def target_mailbox_record_from_command(rec, targets_by_id=None, now_epoch=None):
    return target_mailbox.target_mailbox_record_from_command(
        rec,
        targets_by_id,
        now_epoch=now_epoch,
    )


def target_mailbox_records_from_commands(commands, targets_by_id=None, now_epoch=None):
    return target_mailbox.target_mailbox_records_from_commands(
        commands,
        targets_by_id,
        now_epoch=now_epoch,
    )


def record_selected_target_activity(cfg, service, operation, remote="", details=None, session_id=""):
    ctx = selected_target_context(cfg)
    if not ctx:
        return {}
    metadata = details_with_target(cfg, {
        **(details or {}),
        "operation": operation,
        "remote_addr": remote or "",
    }, ctx)
    return record_target_activity(cfg, metadata, service, session_id=session_id)


def target_phone_home_pending_reason(kind, details):
    return target_phone_home.target_phone_home_pending_reason(kind, details)


def target_phone_home_record_from_event(event, targets_by_id=None):
    return target_phone_home.target_phone_home_record_from_event(
        event,
        targets_by_id=targets_by_id,
    )


def target_phone_home_records_from_events(events, targets_by_id=None):
    return target_phone_home.target_phone_home_records_from_events(
        events,
        targets_by_id=targets_by_id,
    )


def target_activity_status_context(
    command_queue,
    targets_by_id=None,
    event_records=None,
    *,
    target_filter_id="",
    target_filter_session_ids=None,
    now_epoch=None,
):
    if now_epoch is None:
        now_epoch = parse_utc_timestamp(utc_now()) or int(time.time())
    mailbox_records = target_mailbox_records_from_commands(
        (command_queue or {}).get("commands") or [],
        targets_by_id,
        now_epoch=now_epoch,
    )
    source_events = event_records or []
    if target_filter_id:
        source_events = [
            event for event in source_events
            if event_for_target(event, target_filter_id, target_filter_session_ids)
        ]
    phone_home_records = target_phone_home.target_phone_home_records_from_events(
        source_events,
        targets_by_id=targets_by_id,
    )
    return {
        "target_mailbox_records": mailbox_records,
        "target_mailbox_index_maps": target_mailbox_record_indexes(mailbox_records),
        "target_phone_home_records": phone_home_records,
        "target_phone_home_index_maps": target_phone_home.target_phone_home_record_indexes(
            phone_home_records
        ),
    }


def target_activity_records_from_sources(
    targets,
    mailbox_records,
    phone_home_records,
    file_transfer_records,
    bridge_profiles,
    sessions,
):
    return target_activity_feed.target_activity_records_from_sources(
        targets,
        mailbox_records,
        phone_home_records,
        file_transfer_records,
        bridge_profiles,
        sessions,
    )


def print_target_activity_records(doc, target_id=None, limit=8):
    return target_activity_display.print_target_activity_records(
        doc,
        target_id=target_id,
        limit=limit,
    )


def print_workbench_phone_home_attempts(snap, limit=5, include_work_details=False):
    return target_activity_display.print_workbench_phone_home_attempts(
        snap,
        limit=limit,
        include_work_details=include_work_details,
    )


def target_activity_record_indexes(records):
    return target_activity_feed.target_activity_record_indexes(records)


def target_activity_feed_status_context(
    targets=None,
    mailbox_records=None,
    phone_home_records=None,
    file_transfer_records=None,
    bridge_profiles=None,
    sessions=None,
):
    return target_activity_feed.target_activity_feed_status_context(
        targets,
        mailbox_records,
        phone_home_records,
        file_transfer_records,
        bridge_profiles,
        sessions,
    )


def target_activity_record_summary(records):
    return target_activity_feed.target_activity_record_summary(records)


def target_mailbox_record_indexes(records):
    return target_mailbox.target_mailbox_record_indexes(records)


def target_mailbox_record_summary(records):
    return target_mailbox.target_mailbox_record_summary(records)


def target_phone_home_record_indexes(records):
    return target_phone_home.target_phone_home_record_indexes(records)


def target_phone_home_record_summary(records):
    return target_phone_home.target_phone_home_record_summary(records)


def latest_target_phone_home_records(records):
    return target_phone_home.latest_target_phone_home_records(records)


def apply_target_phone_home_summary(targets, phone_home_records):
    return target_phone_home.apply_target_phone_home_summary(
        targets,
        phone_home_records,
    )
