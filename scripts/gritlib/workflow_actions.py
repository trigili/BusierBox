"""Workflow action index, summary, and display helpers for grit-console."""

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.line_state import line_action_state_text
import gritlib.probe_commands as probe_commands
from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, record_sum_by_key, records_by_key,
)
from gritlib.release_contexts import release_context
from gritlib.shell_utils import shquote
from gritlib.target_records import load_targets
from gritlib.workflow_support import select_workbench_action
import gritlib.workflow_operator_console_actions as workflow_operator_console_actions
import gritlib.workflow_operator_daemon_actions as workflow_operator_daemon_actions
import gritlib.workflow_target_actions as workflow_target_actions
import gritlib.workflow_workbench_actions as workflow_workbench_actions
import gritlib.workbench_jobs as workbench_jobs
from gritlib.workbench_jobs import workbench_job_records


def select_workflow_action(records, selector, label, extra_keys=()):
    text = str(selector or "").strip()
    if not text:
        raise ValueError(f"{label} module is required")
    records = records or []
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"{label} module number out of range: {text}")
        return records[idx]
    keys = ("id", "action_id", *tuple(extra_keys or ()))
    for rec in records:
        if text in tuple(str(rec.get(key) or "") for key in keys):
            return rec
    raise ValueError(f"{label} module not found: {text}")


def _legacy_workbench_headless_status_command(cfg):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --status"
    )


def _print_legacy_workbench_action_summary(summary):
    print(
        "Workbench module summary: "
        f"total={summary.get('workbench_action_count', 0)} "
        f"background_supported={summary.get('workbench_action_background_supported_count', 0)} "
        f"foreground_runnable={summary.get('workbench_action_foreground_runnable_count', 0)} "
        f"requires_confirmation={summary.get('workbench_action_requires_confirmation_count', 0)}"
    )


def _print_legacy_operator_daemon_workflow_summary(summary):
    print(
        "Operator daemon module summary: "
        f"total={summary.get('operator_daemon_workflow_action_count', 0)} "
        f"attached={summary.get('operator_daemon_workflow_action_attached_count', 0)} "
        f"enter_runnable={summary.get('operator_daemon_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('operator_daemon_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('operator_daemon_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )


def _legacy_workbench_action_preview(records):
    preview = []
    seen_action_ids = set()
    for rec in records or []:
        rec_id = str(rec.get("id") or "")
        if rec_id in (
            "operator-daemon-start",
            "operator-daemon-status",
            "operator-daemon-stop",
            "systemd-user-status",
        ) or rec.get("background_supported") is True:
            if rec_id and rec_id not in seen_action_ids:
                seen_action_ids.add(rec_id)
                preview.append(rec)
        if len(preview) >= 8:
            break
    return preview


def _print_legacy_workbench_action_preview(records):
    for idx, rec in enumerate(records, 1):
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


def _legacy_service_action_preview(records):
    preview = []
    seen_service_action_ids = set()
    for rec in records or []:
        if rec.get("can_run_from_curses_enter") or rec.get("service") == "file-service":
            rec_id = str(rec.get("id") or "")
            if rec_id and rec_id not in seen_service_action_ids:
                seen_service_action_ids.add(rec_id)
                preview.append(rec)
        if len(preview) >= 10:
            break
    return preview


def _print_legacy_service_action_preview(service_actions, preview):
    if service_actions:
        print(
            "Service modules: "
            f"total={len(service_actions)} preview={len(preview)} "
            f"runnable/file-service actions shown"
        )
    for idx, rec in enumerate(preview, 1):
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


def _print_legacy_target_workflow_action_hint(target_actions):
    if target_actions:
        print(f"Target modules: total={len(target_actions)}; use module 15 for the prompted target module list")


def _append_legacy_workbench_actions_viewed(cfg, append_event_fn, headless, snap):
    append_event_fn(cfg, "workbench", "workbench_actions_viewed", details={
        "headless_command": headless,
        "action_count": len(snap.get("workbench_actions") or []),
        "service_workflow_action_count": len(snap.get("service_workflow_actions") or []),
        "target_workflow_action_count": len(snap.get("target_workflow_actions") or []),
    })


def _run_selected_legacy_workbench_action(cfg, selected, *, input_func, actions_func, run_action_func):
    try:
        actions = actions_func()
        action = select_workbench_action(actions, selected)
        if action.get("background_supported") is True:
            print("background module; use module 12 to start it as a managed job")
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

    headless = _legacy_workbench_headless_status_command(cfg)
    snap = snapshot_func(cfg)
    summary = snap.get("summary") or {}
    _print_legacy_workbench_action_summary(summary)
    _print_legacy_operator_daemon_workflow_summary(summary)
    _print_legacy_workbench_action_preview(
        _legacy_workbench_action_preview(snap.get("workbench_actions") or [])
    )
    service_actions = snap.get("service_workflow_actions") or []
    _print_legacy_service_action_preview(service_actions, _legacy_service_action_preview(service_actions))
    _print_legacy_target_workflow_action_hint(snap.get("target_workflow_actions") or [])
    _append_legacy_workbench_actions_viewed(cfg, append_event_fn, headless, snap)
    selected_line = input_func("operator module id/number to run, or blank> ")
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        return _run_selected_legacy_workbench_action(
            cfg,
            selected,
            input_func=input_func,
            actions_func=actions_func,
            run_action_func=run_action_func,
        )
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
    selected_line = input_func("target module id or number> ") if input_func else None
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
                print("Target activity after module:")
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
    "operator-daemon-start": "Start configured listeners in the background",
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
        if item in {"--dry-run", "dry-run", "preview"}:
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
        if daemon_cmd["dry_run"] or daemon_cmd["confirmed"]:
            raise ValueError("usage:\n  daemon status preview\n  daemon install confirm")
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
        print("daemon module complete: ok")
    else:
        print(f"daemon module failed: rc={rc_code}")
    return rc


def print_line_daemon_action_records(records, verbose=False):
    records = list(records or [])

    def _workflow_label(rec):
        return str(rec.get("workflow") or "-").replace("-", " ")

    def _detail(rec):
        if not verbose:
            return []
        run_cmd = rec.get("run_command") or rec.get("headless_command") or rec.get("command") or ""
        details = [("id", rec.get("id") or "-"), ("run", run_cmd)]
        if rec.get("dry_run_command"):
            details.append(("preview", rec["dry_run_command"]))
        return details

    def _confirm_text(rec):
        if not rec.get("requires_confirmation"):
            return "-"
        if str(rec.get("operator_action_state") or "") in {
            "already-empty", "already-stopped", "disabled", "missing-target", "not-running", "not-supported",
        }:
            return "-"
        alias = line_daemon_action_alias(rec)
        return f"daemon {alias} confirm" if alias and alias != "-" else "daemon ACTION confirm"

    cols = [
        ("Control", line_daemon_action_label),
        ("Use", line_daemon_action_alias),
        ("Purpose", line_daemon_action_purpose),
        ("Area", _workflow_label),
        ("Status", line_action_state_text),
        ("Daemon Attached", lambda r: "attached" if r.get("daemon_attached") else "not attached"),
        ("Confirm Command", _confirm_text),
    ]
    footer_lines = [
        "review daemon: daemon status",
        "preview status: daemon status preview",
        "list all controls: daemon verbose",
        "help: daemon ?",
    ]
    if any(_confirm_text(rec) != "-" for rec in records):
        footer_lines.append("confirm install: daemon install confirm")
    footer = "\n  ".join(footer_lines)
    console_table(
        f"Daemon controls  ({len(records)} total)" if records else "Daemon controls  (none)",
        records, cols, detail_fn=_detail,
        footer=footer,
    )


def workflow_action_count(records):
    return workflow_operator_console_actions.workflow_action_count(records)


def workflow_enter_count(records):
    return workflow_operator_console_actions.workflow_enter_count(records)


def workflow_queue_count(records):
    return workflow_operator_console_actions.workflow_queue_count(records)


def workflow_command_prefix_count(records, prefix):
    return workflow_operator_console_actions.workflow_command_prefix_count(records, prefix)


def operator_console_headless_command(kind, base_command):
    return workflow_operator_console_actions.operator_console_headless_command(kind, base_command)


def operator_console_workflow_context(targets=None, target_mailbox_records=None, release=None, warnings=None):
    return workflow_operator_console_actions.operator_console_workflow_context(
        targets, target_mailbox_records, release, warnings
    )


def annotate_operator_console_workflows(records, target_records, overdue_targets):
    return workflow_operator_console_actions.annotate_operator_console_workflows(
        records, target_records, overdue_targets
    )


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
    return workflow_operator_console_actions.operator_console_workflow_records(
        cfg,
        targets=targets,
        target_workflow_actions=target_workflow_actions,
        target_mailbox_records=target_mailbox_records,
        bridge_profiles=bridge_profiles,
        bridge_profile_workflow_actions=bridge_profile_workflow_actions,
        staged_records=staged_records,
        staged_file_workflow_actions=staged_file_workflow_actions,
        file_service_workflow_actions=file_service_workflow_actions,
        probe_workflow_actions=probe_workflow_actions,
        command_queue_workflow_actions=command_queue_workflow_actions,
        service_workflow_actions=service_workflow_actions,
        operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        workbench_actions=workbench_actions,
        workbench_config_fields=workbench_config_fields,
        workbench_jobs=workbench_jobs,
        target_activity_records=target_activity_records,
        release_artifact_workflow_actions=release_artifact_workflow_actions,
        release=release,
        warnings=warnings,
    )


def workbench_action_records(cfg):
    return workflow_workbench_actions.workbench_action_records(cfg)


def annotate_workbench_actions(records, cfg, run_command_builder, start_job_command_builder):
    return workflow_workbench_actions.annotate_workbench_actions(
        records, cfg, run_command_builder, start_job_command_builder
    )


def target_workflow_action_readiness(
    target,
    requires_input=False,
    available=True,
    requires_target_online=False,
    queues_offline_work=False,
    target_phone_home_required=False,
):
    return workflow_target_actions.target_workflow_action_readiness(
        target,
        requires_input=requires_input,
        available=available,
        requires_target_online=requires_target_online,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
    )


def bridge_profiles_by_target_id(bridge_profiles):
    return workflow_target_actions.bridge_profiles_by_target_id(bridge_profiles)


def target_workflow_run_command(base_command, target_id, action_id, extra_args=""):
    return workflow_target_actions.target_workflow_run_command(
        base_command, target_id, action_id, extra_args
    )


def bridge_profile_action_context(profile):
    return workflow_target_actions.bridge_profile_action_context(profile)


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
    return workflow_target_actions.target_workflow_action_record(
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


def target_workflow_action_records(cfg, targets, bridge_profiles=None):
    return workflow_target_actions.target_workflow_action_records(
        cfg, targets, bridge_profiles
    )


def operator_daemon_workflow_commands(config_path, action_id):
    return workflow_operator_daemon_actions.operator_daemon_workflow_commands(
        config_path, action_id
    )


def operator_daemon_action_state(action_id, action, daemon_attached):
    return workflow_operator_daemon_actions.operator_daemon_action_state(
        action_id, action, daemon_attached
    )


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
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_record(
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
        run_command=run_command,
        dry_run_command=dry_run_command,
        start_job_command=start_job_command,
    )


def workbench_action_indexes(records):
    return workflow_workbench_actions.workbench_action_indexes(records)


def workbench_action_summary(records):
    return workflow_workbench_actions.workbench_action_summary(records)


def workbench_action_status_summary(stats=None):
    return workflow_workbench_actions.workbench_action_status_summary(stats)


def workbench_action_status_context(cfg):
    return workflow_workbench_actions.workbench_action_status_context(cfg)


def workbench_job_indexes(records):
    return workbench_jobs.workbench_job_indexes(records)


def workbench_job_summary(records):
    return workbench_jobs.workbench_job_summary(records)


def workbench_job_status_summary(stats=None):
    return workbench_jobs.workbench_job_status_summary(stats)


def workbench_job_status_context(cfg, workbench_actions=None):
    return workbench_jobs.workbench_job_status_context(cfg, workbench_actions)


def operator_daemon_workflow_action_indexes(records):
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_indexes(records)


def operator_daemon_workflow_action_summary(records):
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_summary(records)


def operator_daemon_workflow_action_status_summary(records):
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_status_summary(records)


def operator_daemon_workflow_action_records(cfg, workbench_actions=None, targets=None):
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_records(
        cfg, workbench_actions, targets
    )


def operator_daemon_workflow_action_status_context(
    cfg,
    workbench_actions=None,
    targets=None,
):
    return workflow_operator_daemon_actions.operator_daemon_workflow_action_status_context(
        cfg, workbench_actions, targets
    )


def operator_console_workflow_indexes(records):
    return workflow_operator_console_actions.operator_console_workflow_indexes(records)


def operator_console_workflow_summary(records):
    return workflow_operator_console_actions.operator_console_workflow_summary(records)


def operator_console_workflow_status_summary(stats=None):
    return workflow_operator_console_actions.operator_console_workflow_status_summary(stats)


def target_workflow_action_indexes(records):
    return workflow_target_actions.target_workflow_action_indexes(records)


def target_workflow_action_status_context(cfg, targets, bridge_profiles=None):
    return workflow_target_actions.target_workflow_action_status_context(
        cfg, targets, bridge_profiles
    )


def target_workflow_action_summary(records):
    return workflow_target_actions.target_workflow_action_summary(records)


def target_workflow_action_status_summary(records):
    return workflow_target_actions.target_workflow_action_status_summary(records)


def probe_workflow_action_indexes(records):
    return probe_commands.probe_workflow_action_indexes(records)


def probe_workflow_action_summary(records):
    return probe_commands.probe_workflow_action_summary(records)


def probe_workflow_action_status_summary(records):
    return probe_commands.probe_workflow_action_status_summary(records)


def _print_operator_console_workflow_summary(summary):
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


def _print_build_config_field_summary(summary):
    print(
        "Build config field summary: "
        f"total={summary.get('workbench_config_field_count', 0)} "
        f"configured={summary.get('workbench_config_field_configured_count', 0)} "
        f"fixed_options={summary.get('workbench_config_field_fixed_option_count', 0)} "
        f"control_like={summary.get('workbench_config_field_control_like_count', 0)}"
    )
    print(f"  config categories: {format_counts(summary.get('workbench_config_field_category_counts') or {})}")
    print(f"  config safety: {format_counts(summary.get('workbench_config_field_safety_boundary_counts') or {})}")


def _print_workbench_action_record_summary(summary):
    print(
        "Workbench module summary: "
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
    print(f"  module states: {format_counts(summary.get('workbench_action_operator_action_state_counts') or {})}")


def _print_operator_daemon_workflow_action_summary(summary):
    print(
        "Operator daemon module summary: "
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
    print(f"  daemon module states: {format_counts(summary.get('operator_daemon_workflow_action_operator_action_state_counts') or {})}")


def _print_service_workflow_action_summary(summary):
    print(
        "Service module summary: "
        f"total={summary.get('service_workflow_action_count', 0)} "
        f"available={summary.get('service_workflow_action_available_count', 0)} "
        f"requires_confirmation={summary.get('service_workflow_action_requires_confirmation_count', 0)} "
        f"enter_runnable={summary.get('service_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"fleet_pending_work={format_counts(summary.get('service_workflow_action_fleet_mailbox_pending_work_count_counts') or {})} "
        f"fleet_offline={format_counts(summary.get('service_workflow_action_fleet_offline_target_count_counts') or {})} "
        f"fleet_poll_overdue={format_counts(summary.get('service_workflow_action_fleet_poll_overdue_target_count_counts') or {})}"
    )
    print(f"  service workflows: {format_counts(summary.get('service_workflow_action_workflow_counts') or {})}")
    print(f"  service module states: {format_counts(summary.get('service_workflow_action_operator_action_state_counts') or {})}")


def _print_target_workflow_action_summary(summary):
    print(
        "Target module summary: "
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
    print(f"  module states: {format_counts(summary.get('target_workflow_action_operator_action_state_counts') or {})}")


def _print_probe_workflow_action_summary(summary):
    print(
        "Probe module summary: "
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
    print(f"  probe module states: {format_counts(summary.get('probe_workflow_action_operator_action_state_counts') or {})}")


def _print_command_queue_workflow_action_summary(summary):
    print(
        "Command queue action summary: "
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


def _print_file_service_workflow_action_summary(summary):
    print(
        "File service shortcut summary: "
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
    print(f"  file shortcut states: {format_counts(summary.get('file_service_workflow_action_operator_action_state_counts') or {})}")


def print_workbench_action_summary(doc):
    doc = doc or {}
    summary = doc.get("summary") or {}
    _print_operator_console_workflow_summary(summary)
    _print_build_config_field_summary(summary)
    _print_workbench_action_record_summary(summary)
    _print_operator_daemon_workflow_action_summary(summary)
    _print_service_workflow_action_summary(summary)
    _print_target_workflow_action_summary(summary)
    _print_probe_workflow_action_summary(summary)
    _print_command_queue_workflow_action_summary(summary)
    _print_file_service_workflow_action_summary(summary)
