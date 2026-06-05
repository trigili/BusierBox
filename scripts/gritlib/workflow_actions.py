"""Workflow action index, summary, and display helpers for grit-console."""

import shlex

from gritlib.build_config import build_config_path
from gritlib.command_queue import command_queue_path, load_command_queue
from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.line_state import line_action_state_text
from gritlib.operator_network import operator_advertised_host
from gritlib.process_status import pid_alive
from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, record_sum_by_key, records_by_key,
)
from gritlib.release_artifacts import release_context
from gritlib.service_status import configured_daemon_services
from gritlib.session_state import read_json_file, state_file_path
from gritlib.shell_utils import shquote
from gritlib.staged_files import staged_file_path
from gritlib.systemd_user import systemd_user_unit_name
from gritlib.target_records import load_targets, selected_target_context, targets_path
from gritlib.workflow_support import (
    select_workbench_action, target_scoped_command, workflow_fleet_metrics,
)
from gritlib.workbench_jobs import (
    run_workbench_action_headless_command, start_workbench_job_headless_command,
    workbench_job_records, workbench_jobs_path,
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


def dispatch_legacy_workbench_action_number(
    choice,
    cfg,
    *,
    input_func,
    snapshot_func,
    append_event_fn,
    actions_func,
    run_action_func,
):
    if str(choice or "").strip() != "11":
        return False

    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --status"
    )
    snap = snapshot_func(cfg)
    summary = snap.get("summary") or {}
    print(
        "Workbench action summary: "
        f"total={summary.get('workbench_action_count', 0)} "
        f"background_supported={summary.get('workbench_action_background_supported_count', 0)} "
        f"foreground_runnable={summary.get('workbench_action_foreground_runnable_count', 0)} "
        f"requires_confirmation={summary.get('workbench_action_requires_confirmation_count', 0)}"
    )
    print(
        "Operator daemon workflow action summary: "
        f"total={summary.get('operator_daemon_workflow_action_count', 0)} "
        f"attached={summary.get('operator_daemon_workflow_action_attached_count', 0)} "
        f"enter_runnable={summary.get('operator_daemon_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('operator_daemon_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('operator_daemon_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    action_preview = []
    seen_action_ids = set()
    for rec in snap.get("workbench_actions") or []:
        rec_id = str(rec.get("id") or "")
        if rec_id in (
            "operator-daemon-start",
            "operator-daemon-status",
            "operator-daemon-stop",
            "systemd-user-status",
        ) or rec.get("background_supported") is True:
            if rec_id and rec_id not in seen_action_ids:
                seen_action_ids.add(rec_id)
                action_preview.append(rec)
        if len(action_preview) >= 8:
            break
    for idx, rec in enumerate(action_preview, 1):
        print(f"{idx}: {rec.get('id', '')} {rec.get('label', '')}")
        print(
            f"   category={rec.get('category', '')} background_supported={'yes' if rec.get('background_supported') else 'no'} "
            f"confirm={'yes' if rec.get('requires_confirmation') else 'no'} "
            f"foreground_runnable={'yes' if rec.get('foreground_runnable') else 'no'} "
            f"state={rec.get('operator_action_state', '') or '-'} "
            f"reason={rec.get('operator_action_reason', '') or '-'} "
            f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'} "
            f"enter_action={rec.get('curses_enter_action', '') or '-'} "
            f"pending_work={rec.get('fleet_mailbox_pending_work_count', 0)} "
            f"offline_targets={rec.get('fleet_offline_target_count', 0)} "
            f"poll_overdue={rec.get('fleet_poll_overdue_target_count', 0)}"
        )
    service_actions = snap.get("service_workflow_actions") or []
    service_action_preview = []
    seen_service_action_ids = set()
    for rec in service_actions:
        if rec.get("can_run_from_curses_enter") or rec.get("service") == "file-service":
            rec_id = str(rec.get("id") or "")
            if rec_id and rec_id not in seen_service_action_ids:
                seen_service_action_ids.add(rec_id)
                service_action_preview.append(rec)
        if len(service_action_preview) >= 10:
            break
    if service_actions:
        print(
            "Service workflow actions: "
            f"total={len(service_actions)} preview={len(service_action_preview)} "
            f"runnable/file-service actions shown"
        )
    for idx, rec in enumerate(service_action_preview, 1):
        print(f"service {idx}: {rec.get('id', '')} {rec.get('label', '')}")
        print(
            f"   service={rec.get('service', '')} category={rec.get('category', '')} "
            f"actual={rec.get('actual', '') or '-'} configured={rec.get('configured', '') or '-'} "
            f"confirm={'yes' if rec.get('requires_confirmation') else 'no'} "
            f"state={rec.get('operator_action_state', '') or '-'} "
            f"reason={rec.get('operator_action_reason', '') or '-'} "
            f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'} "
            f"enter_action={rec.get('curses_enter_action', '') or '-'} "
            f"pending_work={rec.get('fleet_mailbox_pending_work_count', 0)} "
            f"offline_targets={rec.get('fleet_offline_target_count', 0)} "
            f"poll_overdue={rec.get('fleet_poll_overdue_target_count', 0)}"
        )
    target_actions = snap.get("target_workflow_actions") or []
    if target_actions:
        print(f"Target workflow actions: total={len(target_actions)}; use action 15 for the prompted target workflow list")
    append_event_fn(cfg, "workbench", "workbench_actions_viewed", details={
        "headless_command": headless,
        "action_count": len(snap.get("workbench_actions") or []),
        "service_workflow_action_count": len(snap.get("service_workflow_actions") or []),
        "target_workflow_action_count": len(snap.get("target_workflow_actions") or []),
    })
    selected_line = input_func("operator action id/number to run, or blank> ")
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        try:
            actions = actions_func()
            action = select_workbench_action(actions, selected)
            if action.get("background_supported") is True:
                print("background action; use action 12 to start it as a managed job")
                return True
            dry_line = input_func("dry-run/preview only? [Y/n]> ")
            dry_run = dry_line is None or dry_line.strip().lower() not in ("n", "no")
            confirmed = False
            if not dry_run and action.get("requires_confirmation") is True:
                confirm_line = input_func("run confirmed action now? type yes> ")
                confirmed = confirm_line is not None and confirm_line.strip().lower() == "yes"
            rc = run_action_func(
                cfg,
                actions_func(),
                action.get("id", selected),
                dry_run=dry_run,
                confirmed=confirmed,
                show_commands=False,
            )
            print(f"workbench_action_returncode={rc}")
        except (ValueError, IndexError) as exc:
            print(exc)
    return True


def dispatch_legacy_target_workflow_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    run_target_func=None,
    scoped_target_cfg_func=None,
    print_target_summary_func=None,
):
    if str(choice or "").strip() != "15":
        return False
    snap = snapshot_func(cfg) if snapshot_func else {}
    actions = snap.get("target_workflow_actions") or []
    for idx, rec in enumerate(actions, 1):
        print(f"{idx}: {rec.get('id', '')} {rec.get('label', '')}")
        print(
            f"   target={rec.get('target_id', '')} "
            f"workflow={rec.get('workflow', '')} "
            f"input={'yes' if rec.get('requires_input') else 'no'}"
        )
    selected_line = input_func("target workflow action id or number> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        try:
            rec = select_workflow_action(actions, selected, "target")
            rc = run_target_func(
                cfg,
                rec.get("id", selected),
                input_func=input_func,
                show_commands=False,
            ) if run_target_func else 1
            print(f"target_workflow_action_returncode={rc}")
            target_id = str(rec.get("target_id") or "")
            if target_id and scoped_target_cfg_func and print_target_summary_func and snapshot_func:
                target_label = str(rec.get("target_label") or "")
                scoped = scoped_target_cfg_func(cfg, target_id, target_label=target_label)
                print("Target activity after action:")
                print_target_summary_func(snapshot_func(scoped), limit=2)
        except (ValueError, IndexError) as exc:
            print(exc)
    return True


LINE_DAEMON_ACTION_LABELS = {
    "operator-daemon-start": ("Start operator daemon", "start"),
    "operator-daemon-status": ("Check operator daemon", "status"),
    "operator-daemon-stop": ("Stop operator daemon", "stop"),
    "systemd-user-print": ("Print systemd unit", "print"),
    "systemd-user-install": ("Install systemd unit", "install"),
    "systemd-user-start": ("Start systemd unit", "systemd-start"),
    "systemd-user-stop": ("Stop systemd unit", "systemd-stop"),
    "systemd-user-restart": ("Restart systemd unit", "systemd-restart"),
    "systemd-user-status": ("Check systemd unit", "systemd-status"),
}


LINE_DAEMON_ACTION_PURPOSES = {
    "operator-daemon-start": "Run selected listener services in the background",
    "operator-daemon-status": "Show daemon health and managed service state",
    "operator-daemon-stop": "Stop the operator daemon and managed services",
    "systemd-user-print": "Preview a user systemd unit for the daemon",
    "systemd-user-install": "Install the user systemd unit",
    "systemd-user-start": "Start the user systemd unit",
    "systemd-user-stop": "Stop the user systemd unit",
    "systemd-user-restart": "Restart the user systemd unit",
    "systemd-user-status": "Show the user systemd unit status",
}


def line_daemon_action_label(rec):
    action_id = str((rec or {}).get("id") or "")
    label, _alias = LINE_DAEMON_ACTION_LABELS.get(action_id, ("", ""))
    if label:
        return label
    return action_id.replace("-", " ").strip().capitalize() or "-"


def line_daemon_action_alias(rec):
    action_id = str((rec or {}).get("id") or "")
    _label, alias = LINE_DAEMON_ACTION_LABELS.get(action_id, ("", ""))
    return alias or action_id or "-"


def line_daemon_action_purpose(rec):
    action_id = str((rec or {}).get("id") or "")
    return LINE_DAEMON_ACTION_PURPOSES.get(action_id, str((rec or {}).get("label") or "-"))


def parse_line_daemon_action_args(args):
    values = list(args or [])
    dry_run = False
    confirmed = False
    verbose = False
    filtered = []
    for item in values:
        if item == "--dry-run":
            dry_run = True
        elif item in ("--confirm", "confirm", "yes"):
            confirmed = True
        elif item in {"-v", "--verbose", "verbose"}:
            verbose = True
        else:
            filtered.append(item)
    aliases = {
        "start": "operator-daemon-start",
        "status": "operator-daemon-status",
        "stop": "operator-daemon-stop",
        "print": "systemd-user-print",
        "install": "systemd-user-install",
        "systemd-start": "systemd-user-start",
        "systemd-stop": "systemd-user-stop",
        "systemd-restart": "systemd-user-restart",
        "systemd-status": "systemd-user-status",
    }
    action = filtered[0] if filtered else ""
    return {
        "action": "run" if action else "list",
        "selector": aliases.get(action, action),
        "dry_run": dry_run,
        "confirmed": confirmed,
        "verbose": verbose,
    }


def parse_line_daemon_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "daemon":
            return {}
    args = list(args or [])
    action = parse_line_daemon_action_args(args)
    return {
        "action": action["action"],
        "args": args,
        "set_context": (
            not args
            or all(str(item).lower() in {"-v", "--verbose", "verbose"} for item in args)
        ),
    }


def dispatch_line_daemon_command(
    daemon_cmd,
    *,
    set_context_func=None,
    run_func=None,
):
    try:
        if daemon_cmd.get("set_context") and set_context_func:
            set_context_func("daemon")
        if run_func:
            return run_func(daemon_cmd.get("args") or [])
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported daemon command")


def run_line_daemon_action(
    args,
    *,
    print_actions_func=None,
    run_action_func=None,
):
    daemon_cmd = parse_line_daemon_action_args(args)
    if daemon_cmd["action"] == "list":
        if print_actions_func:
            return print_actions_func(verbose=daemon_cmd["verbose"])
        return None
    if not run_action_func:
        raise ValueError("daemon action runner is unavailable")
    rc = run_action_func(
        daemon_cmd["selector"],
        dry_run=daemon_cmd["dry_run"],
        confirmed=daemon_cmd["confirmed"],
        show_commands=False,
    )
    try:
        rc_code = int(rc)
    except (TypeError, ValueError):
        rc_code = 1
    if rc_code == 0:
        print("daemon action complete: ok")
    else:
        print(f"daemon action failed: rc={rc_code}")
    return rc


def print_line_daemon_action_records(records, verbose=False):
    records = list(records or [])

    def _detail(rec):
        if not verbose:
            return []
        run_cmd = rec.get("run_command") or rec.get("headless_command") or rec.get("command") or ""
        details = [("id", rec.get("id") or "-"), ("run", run_cmd)]
        if rec.get("dry_run_command"):
            details.append(("dry-run", rec["dry_run_command"]))
        return details

    cols = [
        ("Action", line_daemon_action_label),
        ("Use", line_daemon_action_alias),
        ("Purpose", line_daemon_action_purpose),
        ("Workflow", lambda r: r.get("workflow") or "-"),
        ("State", line_action_state_text),
        ("Attached", lambda r: "yes" if r.get("daemon_attached") else "no"),
        ("Confirm", lambda r: "yes" if r.get("requires_confirmation") else "no"),
    ]
    console_table(
        f"Daemon actions  ({len(records)} total)" if records else "Daemon actions  (none)",
        records, cols, detail_fn=_detail,
        footer="daemon ACTION  |  daemon ACTION --dry-run  |  daemon -v for commands  |  daemon ? for help",
    )


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


def workflow_command_prefix_count(records, prefix):
    return len([
        rec for rec in records or []
        if str((rec or {}).get("command") or "").startswith(prefix)
    ])


def render_daemon_service_args(daemon_services):
    services = list(daemon_services or [])
    if not services:
        services = ["file-service", "command-queue"]
    return " ".join("--daemon-service " + shquote(service) for service in services)


def bringup_recommend_command(config_path, operator_host, release_dir, target_ctx=None, stage_recommended=False):
    target_ctx = target_ctx or {}
    parts = [
        "scripts/grit-console",
        "bringup",
        "--recommend-only",
        "--json",
        "--operator-config", config_path,
        "--operator-host", operator_host,
    ]
    if release_dir:
        parts.extend(["--release-dir", release_dir])
    if target_ctx.get("target_id"):
        parts.extend(["--target-id", target_ctx.get("target_id", "")])
    if target_ctx.get("target_label"):
        parts.extend(["--target-label", target_ctx.get("target_label", "")])
    for alias in target_ctx.get("target_aliases") or []:
        parts.extend(["--target-alias", alias])
    if stage_recommended:
        parts.append("--stage-recommended-artifact")
    return " ".join(shquote(str(part)) for part in parts)


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


def operator_console_workflow_context(targets=None, target_mailbox_records=None, release=None, warnings=None):
    release = release or {}
    target_records = list(targets or [])
    mailbox_records = list(target_mailbox_records or [])
    pending_mailbox = [
        rec for rec in mailbox_records
        if rec.get("pending_work") is True or str(rec.get("status") or "") in ("queued", "delivered")
    ]
    overdue_targets = [rec for rec in target_records if rec.get("poll_overdue") is True]
    stale_or_offline_targets = [
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") in ("stale", "offline")
    ]
    return {
        "target_records": target_records,
        "mailbox_records": mailbox_records,
        "pending_mailbox": pending_mailbox,
        "overdue_targets": overdue_targets,
        "stale_or_offline_targets": stale_or_offline_targets,
        "warning_records": list(warnings or []),
        "release_artifacts": list(release.get("artifacts") or []),
        "release_recommendations": list(release.get("recommendation_records") or []),
        "release_devices": list(release.get("devices") or []),
        "release_tuples": list(release.get("tuples") or []),
    }


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


def _operator_console_fleet_workflow_records(base, context, target_workflow_actions=None):
    target_records = context["target_records"]
    pending_mailbox = context["pending_mailbox"]
    overdue_targets = context["overdue_targets"]
    return [
        {
            "id": "targets",
            "workflow": "targets",
            "group": "fleet",
            "label": "Target Fleet",
            "description": "Select targets and inspect connectivity, identity, and last phone-home state.",
            "primary_collection": "targets",
            "source_collections": ["targets", "target_registry_state_records", "target_filter_records"],
            "action_collections": ["target_workflow_actions"],
            "record_count": len(target_records),
            "action_count": workflow_action_count(target_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(target_workflow_actions),
            "pending_work_count": len(pending_mailbox),
            "warning_count": len(overdue_targets),
            "headless_command": operator_console_headless_command("targets", base),
            "tui_shortcut": "t",
            "line_mode_action": "15",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
        {
            "id": "target-actions",
            "workflow": "target-actions",
            "group": "fleet",
            "label": "Target Actions",
            "description": "Run target-scoped workflows such as queueing commands, staging files, and selecting release artifacts.",
            "primary_collection": "target_workflow_actions",
            "source_collections": ["target_workflow_actions", "targets"],
            "action_collections": ["target_workflow_actions"],
            "record_count": workflow_action_count(target_workflow_actions),
            "action_count": workflow_action_count(target_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(target_workflow_actions),
            "queueable_offline_action_count": workflow_queue_count(target_workflow_actions),
            "pending_work_count": len(pending_mailbox),
            "warning_count": 0,
            "headless_command": operator_console_headless_command("target-actions", base),
            "tui_shortcut": "a",
            "line_mode_action": "15",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
    ]


def _operator_console_work_workflow_records(
    base,
    context,
    target_workflow_actions=None,
    bridge_profiles=None,
    bridge_profile_workflow_actions=None,
    staged_records=None,
    staged_file_workflow_actions=None,
    file_service_workflow_actions=None,
    probe_workflow_actions=None,
    command_queue_workflow_actions=None,
):
    mailbox_records = context["mailbox_records"]
    pending_mailbox = context["pending_mailbox"]
    return [
        {
            "id": "mailbox",
            "workflow": "mailbox",
            "group": "work",
            "label": "Mailbox",
            "description": "Queue offline work and inspect delivered, completed, failed, expired, and pending target commands.",
            "primary_collection": "target_mailbox_records",
            "source_collections": ["target_mailbox_records", "command_queue.commands", "target_phone_home_records"],
            "action_collections": ["command_queue_workflow_actions"],
            "record_count": len(mailbox_records),
            "action_count": workflow_action_count(command_queue_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(command_queue_workflow_actions),
            "queueable_offline_action_count": workflow_queue_count(command_queue_workflow_actions),
            "pending_work_count": len(pending_mailbox),
            "warning_count": len([rec for rec in mailbox_records if rec.get("expired") is True]),
            "headless_command": operator_console_headless_command("mailbox", base),
            "tui_shortcut": "m",
            "line_mode_action": "20",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
        {
            "id": "bridges",
            "workflow": "bridges",
            "group": "routes",
            "label": "Bridge Routes",
            "description": "Inspect, start, stop, and audit one-hop or multi-hop bridge profiles.",
            "primary_collection": "bridge_profiles",
            "source_collections": ["bridge_profiles", "bridge_hop_records", "target_workflow_actions"],
            "action_collections": ["bridge_profile_workflow_actions", "target_workflow_actions"],
            "record_count": len(bridge_profiles or []),
            "action_count": workflow_action_count(bridge_profile_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(bridge_profile_workflow_actions),
            "queueable_offline_action_count": workflow_queue_count(target_workflow_actions),
            "pending_work_count": workflow_command_prefix_count(pending_mailbox, "bridge:"),
            "warning_count": len([
                rec for rec in bridge_profiles or []
                if rec.get("has_last_failure") is True
            ]),
            "headless_command": operator_console_headless_command("bridges", base),
            "tui_shortcut": "b",
            "line_mode_action": "19",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
        {
            "id": "files",
            "workflow": "files",
            "group": "work",
            "label": "Files",
            "description": "Stage files, show fetch/upload commands, and queue target file-transfer requests.",
            "primary_collection": "staged_records",
            "source_collections": ["staged_records", "target_file_transfer_records", "uploads", "fetches"],
            "action_collections": ["file_service_workflow_actions", "staged_file_workflow_actions"],
            "record_count": len(staged_records or []),
            "action_count": workflow_action_count(file_service_workflow_actions) + workflow_action_count(staged_file_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(file_service_workflow_actions) + workflow_enter_count(staged_file_workflow_actions),
            "queueable_offline_action_count": workflow_queue_count(staged_file_workflow_actions),
            "pending_work_count": workflow_command_prefix_count(pending_mailbox, "fetch:"),
            "warning_count": len([
                rec for rec in staged_records or []
                if rec.get("source_exists") is False
            ]),
            "headless_command": operator_console_headless_command("files", base),
            "tui_shortcut": "f",
            "line_mode_action": "7",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
        {
            "id": "survey",
            "workflow": "survey",
            "group": "work",
            "label": "Survey",
            "description": "Serve direct or bridged probe commands and queue probe requests.",
            "primary_collection": "probe_workflow_actions",
            "source_collections": ["probe_workflow_actions", "target_command_records"],
            "action_collections": ["probe_workflow_actions", "target_workflow_actions"],
            "record_count": workflow_action_count(probe_workflow_actions),
            "action_count": workflow_action_count(probe_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(probe_workflow_actions),
            "queueable_offline_action_count": workflow_queue_count(target_workflow_actions),
            "pending_work_count": workflow_command_prefix_count(pending_mailbox, "survey:"),
            "warning_count": 0,
            "headless_command": operator_console_headless_command("survey", base),
            "tui_shortcut": "w",
            "line_mode_action": "18",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
    ]


def _operator_console_control_artifact_workflow_records(
    base,
    context,
    release=None,
    service_workflow_actions=None,
    operator_daemon_workflow_actions=None,
    workbench_actions=None,
    workbench_config_fields=None,
    workbench_jobs=None,
    release_artifact_workflow_actions=None,
):
    release = release or {}
    warning_records = context["warning_records"]
    release_artifacts = context["release_artifacts"]
    release_recommendations = context["release_recommendations"]
    release_devices = context["release_devices"]
    release_tuples = context["release_tuples"]
    return [
        {
            "id": "daemon",
            "workflow": "daemon",
            "group": "control-plane",
            "label": "Operator Daemon",
            "description": "Start, stop, inspect, and install the optional systemd user service for daemon-owned workflows.",
            "primary_collection": "operator_daemon_workflow_actions",
            "source_collections": ["operator_daemon_workflow_actions", "service_workflow_actions", "services"],
            "action_collections": ["operator_daemon_workflow_actions", "service_workflow_actions"],
            "record_count": workflow_action_count(operator_daemon_workflow_actions),
            "action_count": workflow_action_count(operator_daemon_workflow_actions) + workflow_action_count(service_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(operator_daemon_workflow_actions) + workflow_enter_count(service_workflow_actions),
            "pending_work_count": 0,
            "warning_count": len(warning_records),
            "headless_command": operator_console_headless_command("daemon", base),
            "tui_shortcut": "o",
            "line_mode_action": "11",
            "target_scoped": False,
            "multi_target": True,
            "offline_queue_supported": True,
        },
        {
            "id": "release",
            "workflow": "release",
            "group": "artifacts",
            "label": "Release Artifacts",
            "description": "Inspect release artifacts, devices, tuples, compatibility recommendations, and staging choices.",
            "primary_collection": "release_artifacts",
            "source_collections": ["release_artifacts", "release_recommendations", "release_devices", "release_tuples"],
            "action_collections": ["release_artifact_workflow_actions", "workbench_actions", "target_workflow_actions"],
            "record_count": len(release_artifacts),
            "action_count": workflow_action_count(release_artifact_workflow_actions),
            "enter_runnable_action_count": workflow_enter_count(release_artifact_workflow_actions),
            "recommendation_count": len(release_recommendations),
            "device_count": len(release_devices),
            "tuple_count": len(release_tuples),
            "pending_work_count": 0,
            "warning_count": 0 if release.get("valid") or not release else 1,
            "headless_command": operator_console_headless_command("release", base),
            "tui_shortcut": "6",
            "line_mode_action": "6",
            "target_scoped": False,
            "multi_target": True,
            "offline_queue_supported": False,
        },
        {
            "id": "build-config",
            "workflow": "build-config",
            "group": "artifacts",
            "label": "Build Config",
            "description": "Configure compiled binary and payload options with equivalent headless commands.",
            "primary_collection": "workbench_config_fields",
            "source_collections": ["workbench_config_fields", "workbench_actions"],
            "action_collections": ["workbench_actions"],
            "record_count": len(workbench_config_fields or []),
            "action_count": len([
                rec for rec in workbench_actions or []
                if str(rec.get("category") or "") in ("configuration", "build", "trailer")
            ]),
            "enter_runnable_action_count": 0,
            "pending_work_count": 0,
            "warning_count": 0,
            "headless_command": operator_console_headless_command("build-config", base),
            "tui_shortcut": "3",
            "line_mode_action": "14",
            "target_scoped": False,
            "multi_target": False,
            "offline_queue_supported": False,
        },
        {
            "id": "jobs",
            "workflow": "jobs",
            "group": "control-plane",
            "label": "Jobs",
            "description": "Inspect and cancel background workbench jobs.",
            "primary_collection": "workbench_jobs",
            "source_collections": ["workbench_jobs", "workbench_jobs_state_records"],
            "action_collections": ["workbench_actions"],
            "record_count": len(workbench_jobs or []),
            "action_count": len([
                rec for rec in workbench_actions or []
                if rec.get("background_supported") is True
            ]),
            "enter_runnable_action_count": len([
                rec for rec in workbench_jobs or []
                if rec.get("cancel_supported") is True
            ]),
            "pending_work_count": len([
                rec for rec in workbench_jobs or []
                if str(rec.get("effective_state") or rec.get("state") or "") in ("running", "starting")
            ]),
            "warning_count": len([
                rec for rec in workbench_jobs or []
                if str(rec.get("effective_state") or rec.get("state") or "") in ("failed", "error")
            ]),
            "headless_command": operator_console_headless_command("jobs", base),
            "tui_shortcut": "9",
            "line_mode_action": "12",
            "target_scoped": False,
            "multi_target": False,
            "offline_queue_supported": False,
        },
    ]


def _operator_console_observability_workflow_records(base, context, target_activity_records=None):
    warning_records = context["warning_records"]
    stale_or_offline_targets = context["stale_or_offline_targets"]
    return [
        {
            "id": "events",
            "workflow": "events",
            "group": "observability",
            "label": "Events",
            "description": "Inspect operator events and warning context.",
            "primary_collection": "events",
            "source_collections": ["events", "event_log_state_records", "warnings"],
            "action_collections": [],
            "record_count": 0,
            "action_count": 0,
            "enter_runnable_action_count": 0,
            "pending_work_count": 0,
            "warning_count": len(warning_records),
            "headless_command": operator_console_headless_command("events", base),
            "tui_shortcut": "e",
            "line_mode_action": "1",
            "target_scoped": False,
            "multi_target": True,
            "offline_queue_supported": False,
        },
        {
            "id": "activity",
            "workflow": "activity",
            "group": "observability",
            "label": "Target Activity",
            "description": "Review combined per-target mailbox, phone-home, file, bridge, and session activity.",
            "primary_collection": "target_activity_records",
            "source_collections": ["target_activity_records", "targets"],
            "action_collections": [],
            "record_count": len(target_activity_records or []),
            "action_count": 0,
            "enter_runnable_action_count": 0,
            "pending_work_count": len([
                rec for rec in target_activity_records or []
                if rec.get("pending_work") is True
            ]),
            "warning_count": len(stale_or_offline_targets),
            "headless_command": operator_console_headless_command("activity", base),
            "tui_shortcut": "g",
            "line_mode_action": "21",
            "target_scoped": True,
            "multi_target": True,
            "offline_queue_supported": True,
        },
    ]


def operator_console_workflow_records(
    cfg,
    targets=None,
    target_workflow_actions=None,
    target_mailbox_records=None,
    bridge_profiles=None,
    bridge_profile_workflow_actions=None,
    staged_records=None,
    staged_file_workflow_actions=None,
    file_service_workflow_actions=None,
    probe_workflow_actions=None,
    command_queue_workflow_actions=None,
    service_workflow_actions=None,
    operator_daemon_workflow_actions=None,
    workbench_actions=None,
    workbench_config_fields=None,
    workbench_jobs=None,
    target_activity_records=None,
    release_artifact_workflow_actions=None,
    release=None,
    warnings=None,
):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    release = release or {}
    context = operator_console_workflow_context(targets, target_mailbox_records, release, warnings)
    records = []
    records.extend(_operator_console_fleet_workflow_records(base, context, target_workflow_actions))
    records.extend(_operator_console_work_workflow_records(
        base,
        context,
        target_workflow_actions,
        bridge_profiles,
        bridge_profile_workflow_actions,
        staged_records,
        staged_file_workflow_actions,
        file_service_workflow_actions,
        probe_workflow_actions,
        command_queue_workflow_actions,
    ))
    records.extend(_operator_console_control_artifact_workflow_records(
        base,
        context,
        release,
        service_workflow_actions,
        operator_daemon_workflow_actions,
        workbench_actions,
        workbench_config_fields,
        workbench_jobs,
        release_artifact_workflow_actions,
    ))
    records.extend(_operator_console_observability_workflow_records(base, context, target_activity_records))
    target_records = context["target_records"]
    overdue_targets = context["overdue_targets"]
    return annotate_operator_console_workflows(records, target_records, overdue_targets)


def _workbench_configuration_tooling_action_records(config_path, build_config):
    return [
        {
            "id": "configure-binary",
            "category": "configuration",
            "label": "Configure griTTYkit binary options",
            "script": "scripts/menuconfig",
            "command": "scripts/menuconfig",
            "config_path": build_config,
            "writes_config": True,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "resolve-target",
            "category": "configuration",
            "label": "Resolve target/device preset metadata",
            "script": "scripts/lib/resolve-target",
            "command": "scripts/lib/resolve-target --config " + shquote(config_path),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "tool-provider-check",
            "category": "tooling",
            "label": "Check payload tool provider compatibility",
            "script": "scripts/lib/check-tool-providers",
            "command": "scripts/lib/check-tool-providers --tool TOOL",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "dropin-tool-status",
            "category": "tooling",
            "label": "Inspect local drop-in tool status",
            "script": "scripts/tools/dropin-tool-status",
            "command": "scripts/tools/dropin-tool-status --tool TOOL --json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "check-dropin-tool",
            "category": "tooling",
            "label": "Validate a candidate drop-in tool",
            "script": "scripts/tools/check-dropin-tool",
            "command": "scripts/tools/check-dropin-tool --tool TOOL --path PATH",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "install-dropin-tool",
            "category": "tooling",
            "label": "Install a validated drop-in payload tool",
            "script": "scripts/tools/install-dropin-tool",
            "command": "scripts/tools/install-dropin-tool --tool TOOL --source SOURCE",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_build_action_records(config_path):
    return [
        {
            "id": "package-artifact",
            "category": "build",
            "label": "Build/package selected artifact",
            "script": "make",
            "command": "make package",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "release-current",
            "category": "release",
            "label": "Build current target and stage a small release",
            "script": "scripts/lib/release-current",
            "command": "scripts/lib/release-current --config",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
    ]


def _workbench_bringup_action_records(config_path, release_dir, operator_host, target_ctx):
    return [
        {
            "id": "bringup-recommend",
            "category": "bringup",
            "label": "Generate bringup recommendation with current operator route",
            "script": "scripts/grit-console",
            "command": bringup_recommend_command(config_path, operator_host, release_dir, target_ctx),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "bringup-stage-recommended",
            "category": "bringup",
            "label": "Select and stage recommended bringup artifact",
            "script": "scripts/grit-console",
            "command": bringup_recommend_command(config_path, operator_host, release_dir, target_ctx, stage_recommended=True),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
    ]


def _workbench_artifact_trailer_action_records(config_path):
    return [
        {
            "id": "inspect-artifact",
            "category": "artifact",
            "label": "Inspect artifact metadata without execution",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact inspect ARTIFACT",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "verify-artifact",
            "category": "artifact",
            "label": "Verify artifact integrity and execution",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact verify ARTIFACT",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "configure-trailer",
            "category": "trailer",
            "label": "Configure runtime trailer overrides",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact config set ARTIFACT KEY=VALUE",
            "config_path": config_path,
            "writes_config": True,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_release_action_records(config_path, release_dir):
    return [
        {
            "id": "make-release",
            "category": "release",
            "label": "Build release bundle",
            "script": "scripts/make-release",
            "command": "scripts/make-release --name NAME --targets native --payload-presets survey-core,default",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "release-index",
            "category": "release",
            "label": "Inspect release index",
            "script": "scripts/lib/release-index",
            "command": "scripts/lib/release-index --release-dir " + shquote(release_dir),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "release-find",
            "category": "release",
            "label": "Find compatible release artifacts",
            "script": "scripts/lib/release-find",
            "command": "scripts/lib/release-find --release-dir " + shquote(release_dir) + " FIND_ARGS",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "release-self-test",
            "category": "release",
            "label": "Validate release bundle",
            "script": "scripts/lib/release-self-test",
            "command": "scripts/lib/release-self-test --release-dir " + shquote(release_dir) + " --json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_build_artifact_release_action_records(config_path, release_dir, operator_host, target_ctx):
    records = []
    records.extend(_workbench_build_action_records(config_path))
    records.extend(_workbench_bringup_action_records(
        config_path,
        release_dir,
        operator_host,
        target_ctx,
    ))
    records.extend(_workbench_artifact_trailer_action_records(config_path))
    records.extend(_workbench_release_action_records(config_path, release_dir))
    return records


def _workbench_offline_action_records(config_path):
    return [
        {
            "id": "verify-sources",
            "category": "offline",
            "label": "Verify pinned source downloads",
            "script": "scripts/lib/verify-sources",
            "command": "scripts/lib/verify-sources",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "fetch-sources",
            "category": "offline",
            "label": "Fetch pinned source downloads",
            "script": "scripts/lib/fetch-sources",
            "command": "scripts/lib/fetch-sources",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "check-licensing",
            "category": "offline",
            "label": "Validate licensing and source policy",
            "script": "scripts/lib/check-licensing",
            "command": "scripts/lib/check-licensing",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "source-mirror-plan",
            "category": "offline",
            "label": "Plan source mirror for offline rebuilds",
            "script": "scripts/lib/mirror-sources",
            "command": "scripts/lib/mirror-sources --matrix tests/matrix/release-full.json --source-only --include-buildroot-packages --all-supported-tools --out MIRROR_DIR --dry-run",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "offline-readiness",
            "category": "offline",
            "label": "Check offline source mirror readiness",
            "script": "scripts/lib/check-offline-readiness",
            "command": "scripts/lib/check-offline-readiness --mirror MIRROR_DIR --matrix tests/matrix/release-full.json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "offline-pack",
            "category": "offline",
            "label": "Pack downloaded sources for transfer",
            "script": "scripts/lib/offline-pack",
            "command": "scripts/lib/offline-pack",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "offline-unpack",
            "category": "offline",
            "label": "Restore downloaded sources from offline pack",
            "script": "scripts/lib/offline-unpack",
            "command": "scripts/lib/offline-unpack ARCHIVE",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_daemon_action_records(config_path, daemon_service_args, daemon_command):
    return [
        {
            "id": "operator-daemon-start",
            "category": "daemon",
            "label": "Start operator daemon for selected services",
            "script": "scripts/grit-console",
            "command": daemon_command,
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "operator-daemon-status",
            "category": "daemon",
            "label": "Inspect operator daemon and managed listener state",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " --status",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "operator-daemon-stop",
            "category": "daemon",
            "label": "Stop managed operator daemon services",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " --stop",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-print",
            "category": "daemon",
            "label": "Print systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action print",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-install",
            "category": "daemon",
            "label": "Install systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action install",
            "config_path": config_path,
            "writes_config": True,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-start",
            "category": "daemon",
            "label": "Start systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action start",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-stop",
            "category": "daemon",
            "label": "Stop systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action stop",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-restart",
            "category": "daemon",
            "label": "Restart systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action restart",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "systemd-user-status",
            "category": "daemon",
            "label": "Check systemd user service for operator daemon",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action status",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def workbench_action_records(cfg):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    build_config = str(build_config_path(cfg))
    release_dir = str(cfg.get("release_dir") or ".")
    daemon_services = configured_daemon_services(cfg, [])
    daemon_service_args = render_daemon_service_args(daemon_services)
    daemon_command = "scripts/grit-console --config " + shquote(config_path) + " --daemon " + daemon_service_args
    target_ctx = selected_target_context(cfg)
    operator_host = operator_advertised_host(cfg)

    records = []
    records.extend(_workbench_configuration_tooling_action_records(config_path, build_config))
    records.extend(_workbench_build_artifact_release_action_records(config_path, release_dir, operator_host, target_ctx))
    records.extend(_workbench_offline_action_records(config_path))
    records.extend(_workbench_daemon_action_records(config_path, daemon_service_args, daemon_command))
    return annotate_workbench_actions(
        records,
        cfg,
        run_workbench_action_headless_command,
        start_workbench_job_headless_command,
    )


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


def bridge_profiles_by_target_id(bridge_profiles):
    bridge_by_target = {}
    for profile in bridge_profiles or []:
        if not isinstance(profile, dict):
            continue
        target_id = str(profile.get("target_id") or "")
        if target_id:
            bridge_by_target.setdefault(target_id, []).append(profile)
    return bridge_by_target


def target_workflow_run_command(base_command, target_id, action_id, extra_args=""):
    command = (
        str(base_command)
        + " --run-target-workflow-action "
        + shquote(f"{target_id}:{action_id}")
    )
    if extra_args:
        command += str(extra_args)
    return command


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


def bridge_profile_action_context(profile):
    profile = profile or {}
    profile_name = str(profile.get("name") or "")
    requires_target_online = bool(profile.get("requires_target_online"))
    route_path = str(profile.get("route_path") or "")
    return {
        "profile_name": profile_name,
        "requires_target_online": requires_target_online,
        "route_path": route_path,
        "label_suffix": f" ({route_path})" if route_path else "",
    }


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


def target_workflow_action_records(cfg, targets, bridge_profiles=None):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    release = release_context(cfg)
    bridge_by_target = bridge_profiles_by_target_id(bridge_profiles)
    records = []

    def add(target, action_id, category, label, command, workflow, requires_input=False,
            available=True, bridge_profile="", offline_supported=True,
            requires_target_online=False, queues_offline_work=False,
            target_phone_home_required=False):
        rec = target_workflow_action_record(
            target,
            action_id,
            category,
            label,
            command,
            workflow,
            requires_input=requires_input,
            available=available,
            bridge_profile=bridge_profile,
            offline_supported=offline_supported,
            requires_target_online=requires_target_online,
            queues_offline_work=queues_offline_work,
            target_phone_home_required=target_phone_home_required,
        )
        if rec:
            records.append(rec)

    for target in targets or []:
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("target_id") or "")
        if not target_id:
            continue
        add(
            target,
            "inspect-status",
            "inspect",
            "Inspect this target's status and activity",
            target_scoped_command(base, target_id, " --status"),
            "status",
        )
        add(
            target,
            "open-workbench",
            "inspect",
            "Open the workbench scoped to this target",
            target_scoped_command(base, target_id, ""),
            "workbench",
        )
        add(
            target,
            "queue-command",
            "mailbox",
            "Queue command for this target mailbox",
            target_scoped_command(base, target_id, " --queue-command COMMAND"),
            "command-queue",
            requires_input=True,
            queues_offline_work=True,
            target_phone_home_required=True,
        )
        add(
            target,
            "serve-probe",
            "survey",
            "Serve probe for this target",
            target_scoped_command(base, target_id, " --transport probe"),
            "probe",
            target_phone_home_required=True,
        )
        add(
            target,
            "queue-probe",
            "survey",
            "Queue probe command for this target mailbox",
            target_workflow_run_command(base, target_id, "queue-probe"),
            "probe",
            queues_offline_work=True,
            target_phone_home_required=True,
        )
        add(
            target,
            "stage-file-fetch",
            "file-transfer",
            "Stage a local file for this target to fetch",
            target_scoped_command(base, target_id, " --serve-file LOCAL_PATH --serve-as REQUEST_NAME"),
            "file-service",
            requires_input=True,
            queues_offline_work=True,
            target_phone_home_required=True,
        )
        add(
            target,
            "show-upload-command",
            "file-transfer",
            "Show target upload command for this target",
            target_workflow_run_command(base, target_id, "show-upload-command", " --target-workflow-command TARGET_PATH"),
            "file-service",
            requires_input=True,
            queues_offline_work=False,
            target_phone_home_required=True,
        )
        if release:
            add(
                target,
                "stage-release-artifact",
                "release",
                "Stage a release artifact for this target to fetch",
                target_workflow_run_command(base, target_id, "stage-release-artifact", " --target-workflow-command RELEASE_SELECTOR"),
                "release-artifact",
                requires_input=True,
                queues_offline_work=True,
                target_phone_home_required=True,
            )
        add(
            target,
            "queue-staged-fetch",
            "file-transfer",
            "Queue a staged file fetch command for this target mailbox",
            target_scoped_command(base, target_id, " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name REQUEST_NAME"),
            "file-service",
            requires_input=True,
            queues_offline_work=True,
            target_phone_home_required=True,
        )
        add(
            target,
            "start-file-service",
            "file-transfer",
            "Start file service for target uploads/downloads",
            target_scoped_command(base, target_id, " --file-service"),
            "file-service",
        )
        for profile in bridge_by_target.get(target_id) or []:
            profile_context = bridge_profile_action_context(profile)
            profile_name = profile_context["profile_name"]
            requires_target_online = profile_context["requires_target_online"]
            add(
                target,
                f"start-bridge:{profile_name}",
                "bridge",
                f"Start bridge profile {profile_name}",
                base + " --transport bridge --bridge-profile " + shquote(profile_name),
                "bridge",
                available=bool(profile_name),
                bridge_profile=profile_name,
                offline_supported=not requires_target_online,
                requires_target_online=requires_target_online,
            )
            add(
                target,
                f"queue-bridge-start:{profile_name}",
                "bridge",
                f"Queue bridge/reverse-access start for profile {profile_name}{profile_context['label_suffix']}",
                target_workflow_run_command(base, target_id, f"queue-bridge-start:{profile_name}"),
                "bridge",
                available=bool(profile_name),
                bridge_profile=profile_name,
                offline_supported=True,
                requires_target_online=False,
                queues_offline_work=True,
                target_phone_home_required=True,
            )
    records.sort(key=lambda rec: (rec.get("target_id", ""), rec.get("category", ""), rec.get("action_id", "")))
    return records


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


def workbench_action_status_summary(stats=None):
    stats = stats or {}
    return {
        "workbench_action_count": stats.get("total_count", 0),
        "workbench_action_background_supported_count": stats.get(
            "background_supported_count", 0
        ),
        "workbench_action_long_running_count": stats.get("long_running_count", 0),
        "workbench_action_writes_config_count": stats.get("writes_config_count", 0),
        "workbench_action_runs_build_count": stats.get("runs_build_count", 0),
        "workbench_action_requires_confirmation_count": stats.get(
            "requires_confirmation_count", 0
        ),
        "workbench_action_target_execution_count": stats.get(
            "target_execution_count", 0
        ),
        "workbench_action_foreground_runnable_count": stats.get(
            "foreground_runnable_count", 0
        ),
        "workbench_action_dry_run_supported_count": stats.get(
            "dry_run_supported_count", 0
        ),
        "workbench_action_has_placeholder_count": stats.get(
            "has_placeholder_count", 0
        ),
        "workbench_action_has_run_command_count": stats.get("has_run_command_count", 0),
        "workbench_action_has_dry_run_command_count": stats.get(
            "has_dry_run_command_count", 0
        ),
        "workbench_action_has_start_job_command_count": stats.get(
            "has_start_job_command_count", 0
        ),
        "workbench_action_can_run_from_curses_enter_count": stats.get(
            "can_run_from_curses_enter_count", 0
        ),
        "workbench_action_category_counts": stats.get("category_counts") or {},
        "workbench_action_script_counts": stats.get("script_counts") or {},
        "workbench_action_execution_default_counts": stats.get(
            "execution_default_counts"
        ) or {},
        "workbench_action_event_counts": stats.get("event_counts") or {},
        "workbench_action_config_path_counts": stats.get("config_path_counts") or {},
        "workbench_action_foreground_runnable_counts": stats.get(
            "foreground_runnable_counts"
        ) or {},
        "workbench_action_dry_run_supported_counts": stats.get(
            "dry_run_supported_counts"
        ) or {},
        "workbench_action_has_placeholder_counts": stats.get(
            "has_placeholder_counts"
        ) or {},
        "workbench_action_has_run_command_counts": stats.get(
            "has_run_command_counts"
        ) or {},
        "workbench_action_has_dry_run_command_counts": stats.get(
            "has_dry_run_command_counts"
        ) or {},
        "workbench_action_has_start_job_command_counts": stats.get(
            "has_start_job_command_counts"
        ) or {},
        "workbench_action_operator_action_state_counts": stats.get(
            "operator_action_state_counts"
        ) or {},
        "workbench_action_operator_action_reason_counts": stats.get(
            "operator_action_reason_counts"
        ) or {},
        "workbench_action_can_run_from_curses_enter_counts": stats.get(
            "can_run_from_curses_enter_counts"
        ) or {},
        "workbench_action_curses_enter_action_counts": stats.get(
            "curses_enter_action_counts"
        ) or {},
    }


def workbench_action_status_context(cfg):
    actions = workbench_action_records(cfg)
    stats = workbench_action_summary(actions)
    return {
        "actions": actions,
        "index_maps": workbench_action_indexes(actions),
        "stats": stats,
        "summary": workbench_action_status_summary(stats),
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


def workbench_job_status_summary(stats=None):
    stats = stats or {}
    return {
        "workbench_job_count": stats.get("total_count", 0),
        "workbench_job_running_count": stats.get("running_count", 0),
        "workbench_job_pid_managed_count": stats.get("pid_managed_count", 0),
        "workbench_job_cancel_supported_count": stats.get("cancel_supported_count", 0),
        "workbench_job_log_exists_count": stats.get("log_exists_count", 0),
        "workbench_job_log_total_size": stats.get("log_total_size", 0),
        "workbench_job_last_output_tail_truncated_count": stats.get(
            "last_output_tail_truncated_count", 0
        ),
        "workbench_job_exit_status_known_count": stats.get(
            "exit_status_known_count", 0
        ),
        "workbench_job_started_at_known_count": stats.get("started_at_known_count", 0),
        "workbench_job_finished_at_known_count": stats.get(
            "finished_at_known_count", 0
        ),
        "workbench_job_duration_known_count": stats.get("duration_known_count", 0),
        "workbench_job_elapsed_known_count": stats.get("elapsed_known_count", 0),
        "workbench_job_duration_total_sec": stats.get("duration_total_sec", 0),
        "workbench_job_elapsed_total_sec": stats.get("elapsed_total_sec", 0),
        "workbench_job_background_supported_count": stats.get(
            "background_supported_count", 0
        ),
        "workbench_job_long_running_count": stats.get("long_running_count", 0),
        "workbench_job_state_counts": stats.get("state_counts") or {},
        "workbench_job_effective_state_counts": stats.get("effective_state_counts")
        or {},
        "workbench_job_outcome_counts": stats.get("outcome_counts") or {},
        "workbench_job_exit_status_counts": stats.get("exit_status_counts") or {},
        "workbench_job_action_counts": stats.get("action_counts") or {},
        "workbench_job_category_counts": stats.get("category_counts") or {},
    }


def workbench_job_status_context(cfg, workbench_actions=None):
    jobs = workbench_job_records(cfg, workbench_actions)
    stats = workbench_job_summary(jobs)
    return {
        "jobs": jobs,
        "index_maps": workbench_job_indexes(jobs),
        "stats": stats,
        "summary": workbench_job_status_summary(stats),
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


def operator_daemon_workflow_action_records(cfg, workbench_actions=None, targets=None):
    from pathlib import Path

    actions = [
        rec for rec in (workbench_actions or [])
        if isinstance(rec, dict) and str(rec.get("category") or "") == "daemon"
    ]
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
    unit_name = systemd_user_unit_name("grit-operator.service")
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
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
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
    shared_state = {
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
    records = []

    for action in actions:
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
        action_state = operator_daemon_action_state(action_id, action, daemon_attached)
        records.append(operator_daemon_workflow_action_record(
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
            desired_services,
            child_services,
            daemon_status,
            daemon_attached,
            child_pids,
            child_alive_count,
            daemon_state,
            unit_name,
            action_state,
            run_command=run_command,
            dry_run_command=dry_run_command,
            start_job_command=start_job_command,
        ))
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


def operator_console_workflow_status_summary(stats=None):
    stats = stats or {}
    return {
        "operator_console_workflow_count": stats.get("total_count", 0),
        "operator_console_workflow_target_scoped_count": stats.get(
            "target_scoped_count", 0
        ),
        "operator_console_workflow_multi_target_count": stats.get(
            "multi_target_count", 0
        ),
        "operator_console_workflow_offline_queue_supported_count": stats.get(
            "offline_queue_supported_count", 0
        ),
        "operator_console_workflow_has_records_count": stats.get(
            "has_records_count", 0
        ),
        "operator_console_workflow_has_actions_count": stats.get(
            "has_actions_count", 0
        ),
        "operator_console_workflow_has_enter_runnable_actions_count": stats.get(
            "has_enter_runnable_actions_count", 0
        ),
        "operator_console_workflow_has_pending_work_count": stats.get(
            "has_pending_work_count", 0
        ),
        "operator_console_workflow_has_warnings_count": stats.get(
            "has_warnings_count", 0
        ),
        "operator_console_workflow_action_total_count": stats.get(
            "action_total_count", 0
        ),
        "operator_console_workflow_enter_runnable_action_total_count": stats.get(
            "enter_runnable_action_total_count", 0
        ),
        "operator_console_workflow_pending_work_total_count": stats.get(
            "pending_work_total_count", 0
        ),
        "operator_console_workflow_warning_total_count": stats.get(
            "warning_total_count", 0
        ),
        "operator_console_workflow_group_counts": stats.get("group_counts") or {},
        "operator_console_workflow_workflow_counts": stats.get("workflow_counts") or {},
        "operator_console_workflow_primary_collection_counts": stats.get(
            "primary_collection_counts"
        ) or {},
        "operator_console_workflow_target_scoped_counts": stats.get(
            "target_scoped_counts"
        ) or {},
        "operator_console_workflow_multi_target_counts": stats.get(
            "multi_target_counts"
        ) or {},
        "operator_console_workflow_offline_queue_supported_counts": stats.get(
            "offline_queue_supported_counts"
        ) or {},
        "operator_console_workflow_has_records_counts": stats.get(
            "has_records_counts"
        ) or {},
        "operator_console_workflow_has_actions_counts": stats.get(
            "has_actions_counts"
        ) or {},
        "operator_console_workflow_has_enter_runnable_actions_counts": stats.get(
            "has_enter_runnable_actions_counts"
        ) or {},
        "operator_console_workflow_has_pending_work_counts": stats.get(
            "has_pending_work_counts"
        ) or {},
        "operator_console_workflow_has_warnings_counts": stats.get(
            "has_warnings_counts"
        ) or {},
        "operator_console_workflow_fleet_target_count_counts": stats.get(
            "fleet_target_count_counts"
        ) or {},
        "operator_console_workflow_fleet_offline_target_count_counts": stats.get(
            "fleet_offline_target_count_counts"
        ) or {},
        "operator_console_workflow_fleet_stale_target_count_counts": stats.get(
            "fleet_stale_target_count_counts"
        ) or {},
        "operator_console_workflow_fleet_mailbox_pending_target_count_counts": stats.get(
            "fleet_mailbox_pending_target_count_counts"
        ) or {},
        "operator_console_workflow_fleet_mailbox_pending_work_count_counts": stats.get(
            "fleet_mailbox_pending_work_count_counts"
        ) or {},
        "operator_console_workflow_fleet_poll_overdue_target_count_counts": stats.get(
            "fleet_poll_overdue_target_count_counts"
        ) or {},
        "operator_console_workflow_fleet_has_offline_targets_counts": stats.get(
            "fleet_has_offline_targets_counts"
        ) or {},
        "operator_console_workflow_fleet_has_stale_targets_counts": stats.get(
            "fleet_has_stale_targets_counts"
        ) or {},
        "operator_console_workflow_fleet_has_mailbox_pending_work_counts": stats.get(
            "fleet_has_mailbox_pending_work_counts"
        ) or {},
        "operator_console_workflow_fleet_has_poll_overdue_targets_counts": stats.get(
            "fleet_has_poll_overdue_targets_counts"
        ) or {},
        "operator_console_workflow_operator_action_state_counts": stats.get(
            "operator_action_state_counts"
        ) or {},
        "operator_console_workflow_operator_action_reason_counts": stats.get(
            "operator_action_reason_counts"
        ) or {},
        "operator_console_workflow_tui_shortcut_counts": stats.get(
            "tui_shortcut_counts"
        ) or {},
        "operator_console_workflow_line_mode_action_counts": stats.get(
            "line_mode_action_counts"
        ) or {},
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


def target_workflow_action_status_context(cfg, targets, bridge_profiles=None):
    actions = target_workflow_action_records(cfg, targets, bridge_profiles)
    return {
        "actions": actions,
        "index_maps": target_workflow_action_indexes(actions),
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


def target_workflow_action_status_summary(records):
    summary = target_workflow_action_summary(records)
    return {
        "target_workflow_action_count": summary.get("total_count", 0),
        "target_workflow_action_available_count": summary.get("available_count", 0),
        "target_workflow_action_requires_input_count": summary.get("requires_input_count", 0),
        "target_workflow_action_offline_supported_count": summary.get("offline_supported_count", 0),
        "target_workflow_action_requires_target_online_count": summary.get("requires_target_online_count", 0),
        "target_workflow_action_queues_offline_work_count": summary.get("queues_offline_work_count", 0),
        "target_workflow_action_target_phone_home_required_count": summary.get("target_phone_home_required_count", 0),
        "target_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "target_workflow_action_target_counts": summary.get("target_counts") or {},
        "target_workflow_action_category_counts": summary.get("category_counts") or {},
        "target_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "target_workflow_action_bridge_profile_counts": summary.get("bridge_profile_counts") or {},
        "target_workflow_action_connectivity_state_counts": summary.get("target_connectivity_state_counts") or {},
        "target_workflow_action_target_offline_age_bucket_counts": summary.get("target_offline_age_bucket_counts") or {},
        "target_workflow_action_target_poll_overdue_counts": summary.get("target_poll_overdue_counts") or {},
        "target_workflow_action_target_mailbox_pending_work_count_counts": summary.get("target_mailbox_pending_work_count_counts") or {},
        "target_workflow_action_target_latest_phone_home_status_counts": summary.get("target_latest_phone_home_status_counts") or {},
        "target_workflow_action_target_latest_successful_phone_home_status_counts": summary.get("target_latest_successful_phone_home_status_counts") or {},
        "target_workflow_action_target_last_failed_phone_home_status_counts": summary.get("target_last_failed_phone_home_status_counts") or {},
        "target_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "target_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "target_workflow_action_offline_supported_counts": summary.get("offline_supported_counts") or {},
        "target_workflow_action_requires_target_online_counts": summary.get("requires_target_online_counts") or {},
        "target_workflow_action_queues_offline_work_counts": summary.get("queues_offline_work_counts") or {},
        "target_workflow_action_target_phone_home_required_counts": summary.get("target_phone_home_required_counts") or {},
        "target_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
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


def probe_workflow_action_status_summary(records):
    summary = probe_workflow_action_summary(records)
    return {
        "probe_workflow_action_count": summary.get("total_count", 0),
        "probe_workflow_action_available_count": summary.get("available_count", 0),
        "probe_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "probe_workflow_action_target_phone_home_required_count": summary.get("target_phone_home_required_count", 0),
        "probe_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "probe_workflow_action_action_counts": summary.get("action_counts") or {},
        "probe_workflow_action_category_counts": summary.get("category_counts") or {},
        "probe_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "probe_workflow_action_actual_counts": summary.get("actual_counts") or {},
        "probe_workflow_action_route_kind_counts": summary.get("route_kind_counts") or {},
        "probe_workflow_action_bridge_profile_counts": summary.get("bridge_profile_counts") or {},
        "probe_workflow_action_requires_bridge_counts": summary.get("requires_bridge_counts") or {},
        "probe_workflow_action_fleet_target_count_counts": summary.get("fleet_target_count_counts") or {},
        "probe_workflow_action_fleet_offline_target_count_counts": summary.get("fleet_offline_target_count_counts") or {},
        "probe_workflow_action_fleet_stale_target_count_counts": summary.get("fleet_stale_target_count_counts") or {},
        "probe_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get("fleet_mailbox_pending_target_count_counts") or {},
        "probe_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get("fleet_mailbox_pending_work_count_counts") or {},
        "probe_workflow_action_fleet_poll_overdue_target_count_counts": summary.get("fleet_poll_overdue_target_count_counts") or {},
        "probe_workflow_action_fleet_has_offline_targets_counts": summary.get("fleet_has_offline_targets_counts") or {},
        "probe_workflow_action_fleet_has_stale_targets_counts": summary.get("fleet_has_stale_targets_counts") or {},
        "probe_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get("fleet_has_mailbox_pending_work_counts") or {},
        "probe_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get("fleet_has_poll_overdue_targets_counts") or {},
        "probe_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "probe_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "probe_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "probe_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
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
