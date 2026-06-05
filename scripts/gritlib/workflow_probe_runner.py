"""Probe workflow action runner for grit-console."""

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.probe_commands import render_probe_command
from gritlib.workflow_actions import select_workflow_action


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def run_probe_workflow_action(
    cfg,
    selector,
    dry_run=False,
    confirmed=False,
    print_status_func=None,
    start_service_process_func=None,
    stop_recorded_service_func=None,
):
    if print_status_func is None:
        raise ValueError("probe workflow runner requires print_status_func")
    if start_service_process_func is None:
        raise ValueError("probe workflow runner requires start_service_process_func")
    if stop_recorded_service_func is None:
        raise ValueError("probe workflow runner requires stop_recorded_service_func")
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("probe_workflow_actions") or [], selector, "probe")
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    target_command = str(rec.get("target_command") or render_probe_command(cfg))
    _print_workflow_action_header("probe", rec_id, command=command, headless_command=run_command or command)
    print(f"target_command={target_command}")
    append_event(cfg, "workbench", "probe_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_kind": rec.get("route_kind", ""),
        "bridge_profile": rec.get("bridge_profile", ""),
        "bridge_route_path": rec.get("bridge_route_path", ""),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "target_command": target_command,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "probe_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "headless_command": run_command or command,
            "command": command,
            "target_command": target_command,
        })
        return 0
    if action_id == "inspect-probe":
        return print_status_func(cfg, json_output=False)
    if action_id == "show-target-command":
        rc = 0
    elif action_id == "start-probe":
        start_service_process_func(cfg, "probe", headless_command=run_command or command)
        rc = 0
    elif action_id == "stop-probe":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"probe workflow action requires --confirm-probe-workflow-action: {rec_id}")
        stop_recorded_service_func(
            cfg,
            "probe",
            via="probe-workflow-action",
            headless_command=run_command or command,
        )
        rc = 0
    else:
        raise ValueError(f"unsupported probe workflow action: {action_id}")
    append_event(cfg, "workbench", "probe_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_kind": rec.get("route_kind", ""),
        "bridge_profile": rec.get("bridge_profile", ""),
        "bridge_route_path": rec.get("bridge_route_path", ""),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "target_command": target_command,
        "returncode": rc,
    })
    return rc
