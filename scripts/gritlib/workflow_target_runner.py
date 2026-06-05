"""Target workflow action runner for grit-console."""

import hashlib
from pathlib import Path

import gritlib.bridge_routes as bridge_routes
import gritlib.command_queue as command_queue_module
from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command, render_file_service_command
from gritlib.probe_commands import render_probe_command
from gritlib.release_artifacts import stage_release_selection
import gritlib.staged_files as staged_files
from gritlib.target_records import scoped_target_cfg
from gritlib.workflow_actions import select_workflow_action


def _target_workflow_action_details(rec, action_id, target_id, target_label):
    return {
        "id": rec.get("id", ""),
        "action_id": action_id,
        "target_id": target_id,
        "target_label": target_label,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "headless_command": rec.get("headless_command", rec.get("command", "")),
        "offline_supported": bool(rec.get("offline_supported")),
        "requires_target_online": bool(rec.get("requires_target_online")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
    }


def _target_workflow_action_selected_details(rec, action_id, target_id, target_label):
    details = _target_workflow_action_details(rec, action_id, target_id, target_label)
    selected_details = {
        "id": details["id"],
        "action_id": details["action_id"],
        "target_id": details["target_id"],
        "target_label": details["target_label"],
        "workflow": details["workflow"],
        "category": details["category"],
        "requires_input": bool(rec.get("requires_input")),
        "headless_command": details["headless_command"],
        "offline_supported": details["offline_supported"],
        "requires_target_online": details["requires_target_online"],
        "queues_offline_work": details["queues_offline_work"],
        "target_phone_home_required": details["target_phone_home_required"],
    }
    return selected_details


def _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, extra_details=None):
    details = _target_workflow_action_details(rec, action_id, target_id, target_label)
    details.update(extra_details or {})
    append_event(cfg, "workbench", "target_workflow_action_completed", details=details)


def _run_target_queue_command_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    command_input="",
    input_func=None,
):
    command = str(command_input or "")
    if not command and input_func:
        value = input_func("command to queue> ")
        command = value if value is not None else ""
    if not command.strip():
        raise ValueError("queue-command target workflow action requires a command")
    queued = command_queue_module.queue_command(scoped, command)
    print(f"queued {queued['id']}: {queued['command']}")
    print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "queued-command",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
    })
    return 0


def _run_target_queue_probe_action(cfg, scoped, rec, action_id, target_id, target_label):
    command = render_probe_command(scoped)
    queued = command_queue_module.queue_command(scoped, command, metadata={
        "work_kind": "probe",
        "workflow": "probe",
        "request_name": str(scoped.get("GRIT_PROBE_NAME") or "probe.sh"),
        "route_kind": "bridge" if scoped.get("bridge_profile") else "direct",
        "bridge_profile": str(scoped.get("bridge_profile") or ""),
    })
    print(f"queued {queued['id']}: {queued['command']}")
    print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "queued-probe",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queued_command": queued.get("command", ""),
    })
    return 0


def _run_target_stage_file_fetch_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    local_file="",
    request_name="",
    input_func=None,
):
    path = str(local_file or "")
    if not path and input_func:
        value = input_func("local file> ")
        path = value if value is not None else ""
    request = str(request_name or "")
    if not request and input_func:
        value = input_func("target request name> ")
        request = value if value is not None else ""
    if not path.strip():
        raise ValueError("stage-file-fetch target workflow action requires a local file")
    if not request.strip():
        request = Path(path).name
    staged = staged_files.stage_file(scoped, path, request)
    print(f"staged {staged['request_name']} <- {staged['source_path']}")
    print(f"target={staged.get('target_id', '')} label={staged.get('target_label', '')}")
    print(render_fetch_command(staged["request_name"], scoped))
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "staged-file-fetch",
        "request_name": staged.get("request_name", ""),
        "source_path": staged.get("source_path", ""),
        "sha256": staged.get("sha256", ""),
    })
    return 0


def _run_target_show_upload_command_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    command_input="",
    input_func=None,
):
    target_path = str(command_input or "")
    if not target_path and input_func:
        value = input_func("target file to upload> ")
        target_path = value if value is not None else ""
    target_path = target_path.strip() or "/etc/config/network"
    command = render_file_service_command(["put", target_path], scoped)
    print(f"target_upload_path={target_path}")
    print(f"target_command={command}")
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "shown-upload-command",
        "target_upload_path": target_path,
        "target_command": command,
        "target_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else "",
    })
    return 0


def _run_target_stage_release_artifact_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    command_input="",
    input_func=None,
):
    selector = str(command_input or "")
    if not selector and input_func:
        value = input_func("release artifact selector> ")
        selector = value if value is not None else ""
    selector = selector.strip()
    if not selector:
        raise ValueError("stage-release-artifact target workflow action requires a release selector")
    staged = stage_release_selection(scoped, selector)
    print(f"staged {staged['request_name']} <- {staged['source_path']}")
    print(f"target={staged.get('target_id', '')} label={staged.get('target_label', '')}")
    print(f"release_path={staged.get('release_path', '')} tuple_path={staged.get('tuple_path', '')} payload_preset={staged.get('payload_preset', '')}")
    print(render_fetch_command(staged["request_name"], scoped))
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "staged-release-artifact",
        "selector": selector,
        "request_name": staged.get("request_name", ""),
        "source_path": staged.get("source_path", ""),
        "sha256": staged.get("sha256", ""),
        "release_artifact_name": staged.get("release_artifact_name", ""),
        "release_path": staged.get("release_path", ""),
        "tuple_path": staged.get("tuple_path", ""),
        "payload_preset": staged.get("payload_preset", ""),
        "compatibility": staged.get("compatibility") or {},
    })
    return 0


def _run_target_queue_staged_fetch_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    request_name="",
    input_func=None,
):
    request = str(request_name or "")
    if not request and input_func:
        value = input_func("staged request name> ")
        request = value if value is not None else ""
    request = request.strip()
    if not request:
        raise ValueError("queue-staged-fetch target workflow action requires a staged request name")
    staged = (staged_files.load_staged(cfg).get("staged") or {}).get(request) or {}
    if not isinstance(staged, dict) or not staged:
        raise ValueError(f"staged request not found: {request}")
    staged_target = str(staged.get("target_id") or "")
    if staged_target and staged_target != target_id:
        raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
    command = render_fetch_command(request, scoped)
    queued = command_queue_module.queue_command(scoped, command, metadata={
        "work_kind": "staged-fetch",
        "workflow": "file-service",
        "request_name": request,
        "route_kind": str(staged.get("route_kind") or "direct"),
        "bridge_profile": str(staged.get("bridge_profile") or ""),
        "bridge_route_path": str(staged.get("bridge_route_path") or ""),
    })
    print(f"queued {queued['id']}: {queued['command']}")
    print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "queued-staged-fetch",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "request_name": request,
        "queued_command": queued.get("command", ""),
    })
    return 0


def _run_target_start_service_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    service,
    start_service_process_func,
):
    start_service_process_func(scoped, service)
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "started-service",
        "service": service,
    })
    return 0


def _target_bridge_profile_from_action(rec, action_id, action_name):
    profile = str(rec.get("bridge_profile") or action_id.split(":", 1)[1])
    if not profile:
        raise ValueError(f"{action_name} target workflow action is missing a bridge profile")
    return profile


def _run_target_start_bridge_action(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    start_service_process_func,
):
    profile = _target_bridge_profile_from_action(rec, action_id, "start-bridge")
    start_service_process_func(
        scoped,
        "bridge",
        argv_extra=["--bridge-profile", profile],
        state_service=bridge_routes.bridge_profile_service_name(profile),
    )
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "started-service",
        "service": "bridge",
        "bridge_profile": profile,
    })
    return 0


def _run_target_queue_bridge_start_action(cfg, scoped, rec, action_id, target_id, target_label):
    profile = _target_bridge_profile_from_action(rec, action_id, "queue-bridge-start")
    bridge_profiles = bridge_routes.load_bridge_profiles(cfg).get("profiles") or {}
    profile_rec = bridge_profiles.get(profile) if isinstance(bridge_profiles, dict) else {}
    if not isinstance(profile_rec, dict) or not profile_rec:
        raise ValueError(f"bridge profile not found: {profile}")
    profile_info = bridge_routes.bridge_profile_record(cfg, profile, profile_rec)
    command = "grit rshell start"
    queued = command_queue_module.queue_command(scoped, command, metadata={
        "work_kind": "bridge-start",
        "workflow": "bridge",
        "bridge_profile": profile,
        "bridge_route_path": profile_info.get("route_path", ""),
        "bridge_requires_target_online": bool(profile_info.get("requires_target_online")),
        "route_kind": "bridge",
    })
    print(f"queued: {queued['id']}")
    print(f"command: {queued['command']}")
    print(f"target: {queued.get('target_id', '')} ({queued.get('target_label', '') or '-'})")
    print(f"bridge profile: {profile}")
    print(f"route: {profile_info.get('route_path', '')}")
    _append_target_workflow_completed(cfg, rec, action_id, target_id, target_label, {
        "result": "queued-bridge-start",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queued_command": queued.get("command", ""),
        "bridge_profile": profile,
        "bridge_route_path": profile_info.get("route_path", ""),
        "bridge_requires_target_online": bool(profile_info.get("requires_target_online")),
    })
    return 0


def _target_workflow_context(cfg, rec):
    action_id = str(rec.get("action_id") or "")
    target_id = str(rec.get("target_id") or "")
    target_label = str(rec.get("target_label") or "")
    return {
        "action_id": action_id,
        "target_id": target_id,
        "target_label": target_label,
        "scoped": scoped_target_cfg(cfg, target_id, target_label=target_label),
    }


def _append_target_workflow_selected_event(cfg, rec, context):
    append_event(
        cfg,
        "workbench",
        "target_workflow_action_selected",
        details=_target_workflow_action_selected_details(
            rec,
            context["action_id"],
            context["target_id"],
            context["target_label"],
        ),
    )


def _print_target_workflow_header(rec, show_commands=True):
    print(f"target workflow action: {rec.get('id', '')}")
    if show_commands:
        print(f"command={rec.get('command') or rec.get('headless_command') or ''}")


def _run_target_workflow_side_effect(
    cfg,
    rec,
    context,
    *,
    print_status_func,
    print_workbench_func,
    start_service_process_func,
    command_input="",
    local_file="",
    request_name="",
    input_func=None,
):
    action_id = context["action_id"]
    target_id = context["target_id"]
    target_label = context["target_label"]
    scoped = context["scoped"]
    if action_id == "inspect-status":
        return print_status_func(scoped, json_output=False)
    if action_id == "open-workbench":
        print_workbench_func(scoped)
        return 0
    rc = _run_target_queue_workflow_side_effect(
        cfg,
        scoped,
        rec,
        action_id,
        target_id,
        target_label,
        command_input=command_input,
        input_func=input_func,
    )
    if rc is not None:
        return rc
    rc = _run_target_file_release_workflow_side_effect(
        cfg,
        scoped,
        rec,
        action_id,
        target_id,
        target_label,
        command_input=command_input,
        local_file=local_file,
        request_name=request_name,
        input_func=input_func,
    )
    if rc is not None:
        return rc
    rc = _run_target_service_bridge_workflow_side_effect(
        cfg,
        scoped,
        rec,
        action_id,
        target_id,
        target_label,
        start_service_process_func=start_service_process_func,
    )
    if rc is not None:
        return rc
    raise ValueError(f"unsupported target workflow action: {action_id}")


def _run_target_queue_workflow_side_effect(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    command_input="",
    input_func=None,
):
    if action_id == "queue-command":
        return _run_target_queue_command_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            command_input=command_input,
            input_func=input_func,
        )
    if action_id == "queue-probe":
        return _run_target_queue_probe_action(cfg, scoped, rec, action_id, target_id, target_label)
    return None


def _run_target_file_release_workflow_side_effect(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    command_input="",
    local_file="",
    request_name="",
    input_func=None,
):
    if action_id == "stage-file-fetch":
        return _run_target_stage_file_fetch_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            local_file=local_file,
            request_name=request_name,
            input_func=input_func,
        )
    if action_id == "show-upload-command":
        return _run_target_show_upload_command_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            command_input=command_input,
            input_func=input_func,
        )
    if action_id == "stage-release-artifact":
        return _run_target_stage_release_artifact_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            command_input=command_input,
            input_func=input_func,
        )
    if action_id == "queue-staged-fetch":
        return _run_target_queue_staged_fetch_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            request_name=request_name,
            input_func=input_func,
        )
    return None


def _run_target_service_bridge_workflow_side_effect(
    cfg,
    scoped,
    rec,
    action_id,
    target_id,
    target_label,
    start_service_process_func,
):
    if action_id == "start-file-service":
        return _run_target_start_service_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            "file-service",
            start_service_process_func,
        )
    if action_id == "serve-probe":
        return _run_target_start_service_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            "probe",
            start_service_process_func,
        )
    if action_id.startswith("start-bridge:"):
        return _run_target_start_bridge_action(
            cfg,
            scoped,
            rec,
            action_id,
            target_id,
            target_label,
            start_service_process_func,
        )
    if action_id.startswith("queue-bridge-start:"):
        return _run_target_queue_bridge_start_action(cfg, scoped, rec, action_id, target_id, target_label)
    return None


def run_target_workflow_action(
    cfg,
    selector,
    *,
    print_status_func,
    print_workbench_func,
    start_service_process_func,
    command_input="",
    local_file="",
    request_name="",
    input_func=None,
    show_commands=True,
):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("target_workflow_actions") or [], selector, "target")
    context = _target_workflow_context(cfg, rec)
    _append_target_workflow_selected_event(cfg, rec, context)
    _print_target_workflow_header(rec, show_commands=show_commands)
    return _run_target_workflow_side_effect(
        cfg,
        rec,
        context,
        print_status_func=print_status_func,
        print_workbench_func=print_workbench_func,
        start_service_process_func=start_service_process_func,
        command_input=command_input,
        local_file=local_file,
        request_name=request_name,
        input_func=input_func,
    )
