"""Target activity record helpers for grit-console."""

import time

from gritlib.command_queue import load_command_queue
from gritlib.event_log import event_for_target
from gritlib.session_state import parse_utc_timestamp, utc_now
import gritlib.target_activity_dispatch as target_activity_dispatch
import gritlib.target_activity_display as target_activity_display
import gritlib.target_activity_feed as target_activity_feed
import gritlib.target_mailbox as target_mailbox
import gritlib.target_phone_home as target_phone_home
from gritlib.target_context import (
    details_with_target, selected_target_context,
)
from gritlib.target_record_updates import record_target_activity


def dispatch_legacy_target_activity_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    append_event_fn=None,
    scoped_target_cfg_func=None,
):
    return target_activity_dispatch.dispatch_legacy_target_activity_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        scoped_target_cfg_func=scoped_target_cfg_func,
    )


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
    return target_activity_dispatch.dispatch_legacy_target_detail_number(
        choice,
        cfg,
        input_func=input_func,
        snapshot_func=snapshot_func,
        append_event_fn=append_event_fn,
        scoped_target_cfg_func=scoped_target_cfg_func,
        print_summary_func=print_summary_func,
        action_state_text_func=action_state_text_func,
    )


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
