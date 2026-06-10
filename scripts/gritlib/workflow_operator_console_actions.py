"""Operator-console workflow action records for grit-console workflows."""

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.shell_utils import shquote


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


def _operator_console_mailbox_workflow_record(base, context, command_queue_workflow_actions=None):
    mailbox_records = context["mailbox_records"]
    pending_mailbox = context["pending_mailbox"]
    return {
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
    }


def _operator_console_bridges_workflow_record(
    base,
    context,
    target_workflow_actions=None,
    bridge_profiles=None,
    bridge_profile_workflow_actions=None,
):
    pending_mailbox = context["pending_mailbox"]
    return {
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
    }


def _operator_console_files_workflow_record(
    base,
    context,
    staged_records=None,
    staged_file_workflow_actions=None,
    file_service_workflow_actions=None,
):
    pending_mailbox = context["pending_mailbox"]
    return {
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
    }


def _operator_console_survey_workflow_record(
    base,
    context,
    target_workflow_actions=None,
    probe_workflow_actions=None,
):
    pending_mailbox = context["pending_mailbox"]
    return {
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
    }


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
    return [
        _operator_console_mailbox_workflow_record(
            base,
            context,
            command_queue_workflow_actions=command_queue_workflow_actions,
        ),
        _operator_console_bridges_workflow_record(
            base,
            context,
            target_workflow_actions=target_workflow_actions,
            bridge_profiles=bridge_profiles,
            bridge_profile_workflow_actions=bridge_profile_workflow_actions,
        ),
        _operator_console_files_workflow_record(
            base,
            context,
            staged_records=staged_records,
            staged_file_workflow_actions=staged_file_workflow_actions,
            file_service_workflow_actions=file_service_workflow_actions,
        ),
        _operator_console_survey_workflow_record(
            base,
            context,
            target_workflow_actions=target_workflow_actions,
            probe_workflow_actions=probe_workflow_actions,
        ),
    ]


def _operator_console_daemon_workflow_record(
    base,
    context,
    service_workflow_actions=None,
    operator_daemon_workflow_actions=None,
):
    warning_records = context["warning_records"]
    return {
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
    }


def _operator_console_release_workflow_record(
    base,
    context,
    release=None,
    release_artifact_workflow_actions=None,
):
    release = release or {}
    release_artifacts = context["release_artifacts"]
    release_recommendations = context["release_recommendations"]
    release_devices = context["release_devices"]
    release_tuples = context["release_tuples"]
    return {
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
    }


def _operator_console_build_config_workflow_record(
    base,
    workbench_actions=None,
    workbench_config_fields=None,
):
    return {
        "id": "build-config",
        "workflow": "build-config",
        "group": "artifacts",
        "label": "Build Config",
        "description": "Configure compiled binary and payload options with equivalent generated commands.",
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
    }


def _operator_console_jobs_workflow_record(base, workbench_actions=None, workbench_jobs=None):
    return {
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
    }


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
    return [
        _operator_console_daemon_workflow_record(
            base,
            context,
            service_workflow_actions=service_workflow_actions,
            operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        ),
        _operator_console_release_workflow_record(
            base,
            context,
            release=release,
            release_artifact_workflow_actions=release_artifact_workflow_actions,
        ),
        _operator_console_build_config_workflow_record(
            base,
            workbench_actions=workbench_actions,
            workbench_config_fields=workbench_config_fields,
        ),
        _operator_console_jobs_workflow_record(
            base,
            workbench_actions=workbench_actions,
            workbench_jobs=workbench_jobs,
        ),
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


def _operator_console_workflow_status_count_summary(stats):
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
    }


def _operator_console_workflow_status_collection_summary(stats):
    return {
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
    }


def _operator_console_workflow_status_fleet_summary(stats):
    return {
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
    }


def _operator_console_workflow_status_action_summary(stats):
    return {
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


def operator_console_workflow_status_summary(stats=None):
    stats = stats or {}
    summary = {}
    summary.update(_operator_console_workflow_status_count_summary(stats))
    summary.update(_operator_console_workflow_status_collection_summary(stats))
    summary.update(_operator_console_workflow_status_fleet_summary(stats))
    summary.update(_operator_console_workflow_status_action_summary(stats))
    return summary
