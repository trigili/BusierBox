"""Legacy target activity/detail dispatch helpers for grit-console."""

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.shell_utils import shquote
import gritlib.target_activity_display as target_activity_display
from gritlib.target_context import configured_target_filter
from gritlib.target_selection import (
    print_workbench_target_selector, select_workbench_target_record,
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
            target_activity_display.print_target_activity_records(activity_doc, limit=12)
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
            target_activity_display.print_target_activity_records(
                activity_doc,
                target_id=target_id,
                limit=12,
            )
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
        target_activity_display.print_target_activity_records(scoped_snap, target_id=target_id, limit=5)
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
