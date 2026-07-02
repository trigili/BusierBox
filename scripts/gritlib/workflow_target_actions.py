"""Target workflow action records for grit-console workflows."""

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.record_utils import int_value, record_count_by_key, records_by_key
from gritlib.release_contexts import release_context
from gritlib.shell_utils import shquote
from gritlib.workflow_support import target_scoped_command


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


def _append_target_workflow_action(records, target, action_id, category, label, command, workflow,
                                   requires_input=False, available=True, bridge_profile="",
                                   offline_supported=True, requires_target_online=False,
                                   queues_offline_work=False, target_phone_home_required=False):
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


def _target_inspect_workflow_action_records(base, target, target_id):
    records = []
    _append_target_workflow_action(
        records,
        target,
        "inspect-status",
        "inspect",
        "Inspect this target's status and activity",
        target_scoped_command(base, target_id, " --status"),
        "status",
    )
    _append_target_workflow_action(
        records,
        target,
        "open-workbench",
        "inspect",
        "Open operator modules for this target",
        target_scoped_command(base, target_id, ""),
        "workbench",
    )
    return records


def _target_mailbox_workflow_action_records(base, target, target_id):
    records = []
    _append_target_workflow_action(
        records,
        target,
        "queue-command",
        "mailbox",
        "Queue command for this target check-in path",
        target_scoped_command(base, target_id, " --queue-command COMMAND"),
        "command-queue",
        requires_input=True,
        queues_offline_work=True,
        target_phone_home_required=True,
    )
    return records


def _target_probe_workflow_action_records(base, target, target_id):
    records = []
    _append_target_workflow_action(
        records,
        target,
        "serve-probe",
        "survey",
        "Serve probe for this target",
        target_scoped_command(base, target_id, " --transport probe"),
        "probe",
        target_phone_home_required=True,
    )
    _append_target_workflow_action(
        records,
        target,
        "queue-probe",
        "survey",
        "Queue probe command for this target check-in path",
        target_workflow_run_command(base, target_id, "queue-probe"),
        "probe",
        queues_offline_work=True,
        target_phone_home_required=True,
    )
    return records


def _target_file_transfer_setup_workflow_action_records(base, target, target_id):
    records = []
    _append_target_workflow_action(
        records,
        target,
        "stage-file-fetch",
        "file-transfer",
        "Stage a local file for deliver commands",
        target_scoped_command(base, target_id, " --serve-file LOCAL_PATH --serve-as REQUEST_NAME"),
        "file-service",
        requires_input=True,
        queues_offline_work=True,
        target_phone_home_required=True,
    )
    _append_target_workflow_action(
        records,
        target,
        "show-upload-command",
        "file-transfer",
        "Show target-to-operator retrieve command",
        target_workflow_run_command(base, target_id, "show-upload-command", " --target-workflow-command TARGET_PATH"),
        "file-service",
        requires_input=True,
        queues_offline_work=False,
        target_phone_home_required=True,
    )
    return records


def _target_release_workflow_action_records(base, target, target_id, release):
    records = []
    if release:
        _append_target_workflow_action(
            records,
            target,
            "stage-release-artifact",
            "release",
        "Stage a release artifact for deliver commands",
            target_workflow_run_command(
                base,
                target_id,
                "stage-release-artifact",
                " --target-workflow-command RELEASE_SELECTOR",
            ),
            "release-artifact",
            requires_input=True,
            queues_offline_work=True,
            target_phone_home_required=True,
        )
    return records


def _target_staged_file_workflow_action_records(base, target, target_id):
    records = []
    _append_target_workflow_action(
        records,
        target,
        "queue-staged-fetch",
        "file-transfer",
        "Queue delivery of a staged file to this target",
        target_scoped_command(base, target_id, " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name REQUEST_NAME"),
        "file-service",
        requires_input=True,
        queues_offline_work=True,
        target_phone_home_required=True,
    )
    _append_target_workflow_action(
        records,
        target,
        "start-file-service",
        "file-transfer",
        "Start file service for deliver/retrieve transfers",
        target_scoped_command(base, target_id, " --file-service"),
        "file-service",
    )
    return records


def _target_standard_workflow_action_records(base, target, target_id, release):
    records = []
    records.extend(_target_inspect_workflow_action_records(base, target, target_id))
    records.extend(_target_mailbox_workflow_action_records(base, target, target_id))
    records.extend(_target_probe_workflow_action_records(base, target, target_id))
    records.extend(_target_file_transfer_setup_workflow_action_records(base, target, target_id))
    records.extend(_target_release_workflow_action_records(base, target, target_id, release))
    records.extend(_target_staged_file_workflow_action_records(base, target, target_id))
    return records


def _target_bridge_workflow_action_records(base, target, target_id, bridge_profiles):
    records = []
    for profile in bridge_profiles or []:
        profile_context = bridge_profile_action_context(profile)
        profile_name = profile_context["profile_name"]
        requires_target_online = profile_context["requires_target_online"]
        _append_target_workflow_action(
            records,
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
        _append_target_workflow_action(
            records,
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
    return records


def target_workflow_action_records(cfg, targets, bridge_profiles=None):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    release = release_context(cfg)
    bridge_by_target = bridge_profiles_by_target_id(bridge_profiles)
    records = []
    for target in targets or []:
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("target_id") or "")
        if not target_id:
            continue
        records.extend(_target_standard_workflow_action_records(base, target, target_id, release))
        records.extend(_target_bridge_workflow_action_records(
            base,
            target,
            target_id,
            bridge_by_target.get(target_id),
        ))
    records.sort(key=lambda rec: (rec.get("target_id", ""), rec.get("category", ""), rec.get("action_id", "")))
    return records


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
