"""Service workflow action runner for grit-console."""

from pathlib import Path

import gritlib.bridge_routes as bridge_routes
from gritlib.console_workbench import status_document, workbench_snapshot
from gritlib.event_log import append_event
import gritlib.service_lifecycle as service_lifecycle
from gritlib.service_runtime import current_shutdown_reason, start_child_process
from gritlib.service_status import (
    run_service_workflow_action_headless_command,
    service_status_rows,
)
from gritlib.status_print import print_status_document
from gritlib.workflow_actions import select_workflow_action


def _print_status(cfg, json_output=False):
    return print_status_document(status_document(cfg), json_output=json_output)


def _start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return service_lifecycle.start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
        start_child_process=start_child_process,
        script_path=Path(__file__).resolve().parents[1] / "grit-console",
    )


def _stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", quiet=False):
    return service_lifecycle.stop_recorded_service(
        cfg,
        service,
        via=via,
        headless_command=headless_command,
        shutdown_reason=current_shutdown_reason(),
        quiet=quiet,
    )


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _service_workflow_context(cfg, rec, dry_run=False, confirmed=False):
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    service = str(rec.get("service") or "")
    if not service:
        raise ValueError("service workflow action is missing service name")
    headless = run_service_workflow_action_headless_command(
        cfg,
        rec_id,
        dry_run=dry_run,
        confirmed=confirmed,
    )
    command = str(rec.get("headless_command") or rec.get("command") or "")
    return {
        "rec_id": rec_id,
        "action_id": action_id,
        "service": service,
        "headless": headless,
        "command": command,
        "fleet_details": {
            "fleet_target_count": rec.get("fleet_target_count", 0),
            "fleet_offline_target_count": rec.get("fleet_offline_target_count", 0),
            "fleet_stale_target_count": rec.get("fleet_stale_target_count", 0),
            "fleet_mailbox_pending_target_count": rec.get("fleet_mailbox_pending_target_count", 0),
            "fleet_mailbox_pending_work_count": rec.get("fleet_mailbox_pending_work_count", 0),
            "fleet_poll_overdue_target_count": rec.get("fleet_poll_overdue_target_count", 0),
            "fleet_has_offline_targets": bool(rec.get("fleet_has_offline_targets")),
            "fleet_has_stale_targets": bool(rec.get("fleet_has_stale_targets")),
            "fleet_has_mailbox_pending_work": bool(rec.get("fleet_has_mailbox_pending_work")),
            "fleet_has_poll_overdue_targets": bool(rec.get("fleet_has_poll_overdue_targets")),
        },
    }


def _append_service_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "service_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "service": context["service"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": context["headless"],
        "command": context["command"],
        **context["fleet_details"],
    })


def _run_service_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "service_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "service": context["service"],
        "headless_command": context["headless"],
        "command": context["command"],
        **context["fleet_details"],
    })
    return 0


def _run_service_workflow_side_effect(cfg, rec, context, confirmed=False):
    action_id = context["action_id"]
    if action_id == "inspect-status":
        rc = _print_status(cfg, json_output=False)
    elif action_id == "start-service":
        _start_service_process(cfg, context["service"], headless_command=context["headless"])
        rc = 0
    elif action_id == "stop-service":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"service workflow action requires --confirm-service-workflow-action: {context['rec_id']}")
        _stop_recorded_service(
            cfg,
            context["service"],
            via="service-workflow-action",
            headless_command=context["headless"],
        )
        rc = 0
    else:
        raise ValueError(f"unsupported service workflow action: {action_id}")
    return rc


def _append_service_workflow_completed_event(cfg, rec, context, rc, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "service_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "service": context["service"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": context["headless"],
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })


def run_service_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("service_workflow_actions") or [], selector, "service")
    context = _service_workflow_context(cfg, rec, dry_run=dry_run, confirmed=confirmed)
    _print_workflow_action_header(
        "service",
        context["rec_id"],
        command=context["command"],
        headless_command=context["headless"],
    )
    _append_service_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_service_workflow_dry_run(cfg, context)
    rc = _run_service_workflow_side_effect(cfg, rec, context, confirmed=confirmed)
    _append_service_workflow_completed_event(cfg, rec, context, rc, dry_run=dry_run, confirmed=confirmed)
    return rc


def _bridge_profile_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "profile": str(rec.get("bridge_profile") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
        "fleet_details": {
            "fleet_target_count": rec.get("fleet_target_count", 0),
            "fleet_offline_target_count": rec.get("fleet_offline_target_count", 0),
            "fleet_stale_target_count": rec.get("fleet_stale_target_count", 0),
            "fleet_mailbox_pending_target_count": rec.get("fleet_mailbox_pending_target_count", 0),
            "fleet_mailbox_pending_work_count": rec.get("fleet_mailbox_pending_work_count", 0),
            "fleet_poll_overdue_target_count": rec.get("fleet_poll_overdue_target_count", 0),
            "fleet_has_offline_targets": bool(rec.get("fleet_has_offline_targets")),
            "fleet_has_stale_targets": bool(rec.get("fleet_has_stale_targets")),
            "fleet_has_mailbox_pending_work": bool(rec.get("fleet_has_mailbox_pending_work")),
            "fleet_has_poll_overdue_targets": bool(rec.get("fleet_has_poll_overdue_targets")),
        },
    }


def _append_bridge_profile_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "bridge_profile_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "bridge_profile": context["profile"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_path": rec.get("route_path", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "requires_target_online": bool(rec.get("requires_target_online")),
        "multi_hop": bool(rec.get("multi_hop")),
        "hop_count": rec.get("hop_count", 0),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        **context["fleet_details"],
    })


def _run_bridge_profile_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "bridge_profile_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "bridge_profile": context["profile"],
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        **context["fleet_details"],
    })
    return 0


def _run_bridge_profile_start(cfg, context):
    profile = context["profile"]
    proc = _start_service_process(
        cfg,
        "bridge",
        argv_extra=["--bridge-profile", profile],
        headless_command=context["run_command"] or context["command"],
        state_service=bridge_routes.bridge_profile_service_name(profile),
    )
    if proc is not None:
        print(f"bridge started: {profile}")
    return 0


def _run_bridge_profile_stop(cfg, profile, headless_command):
    _stop_recorded_service(
        cfg,
        bridge_routes.bridge_profile_service_name(profile),
        via="bridge-profile-workflow-action",
        headless_command=headless_command,
    )
    current = {row["name"]: row for row in service_status_rows(cfg)}.get(
        bridge_routes.bridge_profile_service_name(profile),
        {},
    )
    if current.get("actual") == "stopped":
        print(f"bridge stopped; port released: {profile}")
    return 0


def _run_bridge_profile_delete(cfg, profile):
    deleted = bridge_routes.delete_bridge_profile(cfg, profile)
    print(f"deleted bridge profile {deleted.get('name', '')}: {deleted.get('route_path', '')}")
    print(f"bridge_profiles_file={bridge_routes.bridge_profiles_path(cfg)}")
    return 0


def _require_bridge_profile_workflow_confirmation(rec, rec_id, confirmed):
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"bridge profile workflow action requires --confirm-bridge-profile-workflow-action: {rec_id}")


def _append_bridge_profile_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "bridge_profile_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "bridge_profile": context["profile"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_path": rec.get("route_path", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "requires_target_online": bool(rec.get("requires_target_online")),
        "multi_hop": bool(rec.get("multi_hop")),
        "hop_count": rec.get("hop_count", 0),
        "confirmed": bool(confirmed),
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })


def run_bridge_profile_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("bridge_profile_workflow_actions") or [],
        selector,
        "bridge profile",
        extra_keys=("bridge_profile",),
    )
    context = _bridge_profile_workflow_context(rec)
    rec_id = context["rec_id"]
    action_id = context["action_id"]
    profile = context["profile"]
    command = context["command"]
    run_command = context["run_command"]
    _print_workflow_action_header("bridge profile", rec_id, command=command, headless_command=run_command or command)
    print(f"bridge_profile={profile} route={rec.get('route_path', '')}")
    _append_bridge_profile_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_bridge_profile_workflow_dry_run(cfg, context)
    if not profile:
        raise ValueError(f"bridge profile workflow action is missing profile name: {rec_id}")
    if action_id == "inspect-profile":
        return bridge_routes.print_bridge_profile(cfg, profile, json_output=False)
    if action_id == "start-profile":
        rc = _run_bridge_profile_start(cfg, context)
    elif action_id == "stop-profile":
        _require_bridge_profile_workflow_confirmation(rec, rec_id, confirmed)
        rc = _run_bridge_profile_stop(cfg, profile, run_command or command)
    elif action_id == "delete-profile":
        _require_bridge_profile_workflow_confirmation(rec, rec_id, confirmed)
        rc = _run_bridge_profile_delete(cfg, profile)
    else:
        raise ValueError(f"unsupported bridge profile workflow action: {action_id}")
    _append_bridge_profile_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc
