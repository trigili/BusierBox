"""Workflow action runners for grit-console."""

import hashlib
import subprocess
from pathlib import Path
import gritlib.command_queue as command_queue_module
from gritlib.console_workbench import status_document, workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command, render_file_service_command
from gritlib.probe_commands import (
    render_probe_command,
)
from gritlib.release_artifacts import (
    stage_release_selection,
)
import gritlib.service_lifecycle as service_lifecycle
from gritlib.service_runtime import current_shutdown_reason, start_child_process
import gritlib.staged_files as staged_files
from gritlib.status_print import print_status_document, print_workbench_snapshot
from gritlib.target_records import (
    configured_target_filter, scoped_target_cfg,
)
from gritlib.workflow_actions import (
    select_workflow_action,
)
from gritlib.workflow_operator_daemon_runner import run_operator_daemon_workflow_action
from gritlib.workflow_service_runner import (
    run_bridge_profile_workflow_action, run_service_workflow_action,
)
import gritlib.workflow_target_runner as workflow_target_runner

def print_status(cfg, json_output=False):
    return print_status_document(status_document(cfg), json_output=json_output)


def stop_managed_services(cfg):
    return service_lifecycle.stop_managed_services(cfg)


def print_workbench(cfg, include_api_summary=True):
    return print_workbench_snapshot(cfg, workbench_snapshot(cfg), include_api_summary=include_api_summary)


def start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return service_lifecycle.start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
        start_child_process=start_child_process,
        script_path=Path(__file__).resolve().parents[1] / "grit-console",
    )


def stop_workbench_started_services(cfg):
    return service_lifecycle.stop_workbench_started_services(
        cfg,
        stop_service=stop_recorded_service,
    )


def stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", quiet=False):
    return service_lifecycle.stop_recorded_service(
        cfg,
        service,
        via=via,
        headless_command=headless_command,
        shutdown_reason=current_shutdown_reason(),
        quiet=quiet,
    )


def print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _release_artifact_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "selector": str(rec.get("selector") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
    }


def _release_artifact_headless_command(context):
    return context["run_command"] or context["command"]


def _append_release_artifact_workflow_selected_event(cfg, rec, context, dry_run=False):
    append_event(cfg, "workbench", "release_artifact_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "selector": context["selector"],
        "selector_kind": rec.get("selector_kind", ""),
        "release_dir": rec.get("release_dir", ""),
        "release_name": rec.get("release_name", ""),
        "release_path": rec.get("release_path", ""),
        "artifact_name": rec.get("artifact_name", ""),
        "recommendation_id": rec.get("recommendation_id", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
    })


def _run_release_artifact_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "release_artifact_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "selector": context["selector"],
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
    })
    return 0


def _append_release_artifact_workflow_completed_event(cfg, rec, context, rc, extra_details=None):
    details = {
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "selector": context["selector"],
    }
    details.update(extra_details or {})
    details.update({
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
        "returncode": rc,
    })
    append_event(cfg, "workbench", "release_artifact_workflow_action_completed", details=details)


def _run_release_artifact_self_test(cfg, rec, context):
    release_dir = str(rec.get("release_dir") or cfg.get("release_dir") or ".")
    cmd = ["scripts/lib/release-self-test", "--release-dir", release_dir, "--json"]
    result = subprocess.run(cmd, text=True)
    rc = int(result.returncode)
    _append_release_artifact_workflow_completed_event(cfg, rec, context, rc)
    return rc


def _run_release_artifact_stage_selection(cfg, rec, context):
    selector_value = context["selector"]
    if not selector_value:
        raise ValueError(f"release artifact workflow action is missing selector: {context['rec_id']}")
    staged = stage_release_selection(cfg, selector_value)
    print(f"staged {staged['request_name']} <- {staged['source_path']}")
    print(f"release_path={staged.get('release_path', '')} tuple_path={staged.get('tuple_path', '')} payload_preset={staged.get('payload_preset', '')}")
    print(render_fetch_command(staged["request_name"], cfg))
    _append_release_artifact_workflow_completed_event(cfg, rec, context, 0, {
        "selector_kind": rec.get("selector_kind", ""),
        "release_dir": rec.get("release_dir", ""),
        "release_name": rec.get("release_name", ""),
        "release_path": staged.get("release_path", ""),
        "artifact_name": staged.get("release_artifact_name", ""),
        "recommendation_id": rec.get("recommendation_id", ""),
        "request_name": staged.get("request_name", ""),
        "source_path": staged.get("source_path", ""),
        "sha256": staged.get("sha256", ""),
    })
    return 0


def _run_release_artifact_workflow_side_effect(cfg, rec, context):
    action_id = context["action_id"]
    if action_id == "inspect-release":
        return print_status(cfg, json_output=False)
    if action_id == "self-test-release":
        return _run_release_artifact_self_test(cfg, rec, context)
    if action_id in ("stage-artifact", "stage-recommendation"):
        return _run_release_artifact_stage_selection(cfg, rec, context)
    raise ValueError(f"unsupported release artifact workflow action: {action_id}")


def run_release_artifact_workflow_action(cfg, selector, dry_run=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("release_artifact_workflow_actions") or [],
        selector,
        "release artifact",
        extra_keys=("selector", "release_path", "recommendation_id"),
    )
    context = _release_artifact_workflow_context(rec)
    print_workflow_action_header(
        "release artifact",
        context["rec_id"],
        command=context["command"],
        headless_command=_release_artifact_headless_command(context),
    )
    _append_release_artifact_workflow_selected_event(cfg, rec, context, dry_run=dry_run)
    if dry_run:
        return _run_release_artifact_workflow_dry_run(cfg, context)
    return _run_release_artifact_workflow_side_effect(cfg, rec, context)


def _command_queue_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
    }


def _command_queue_headless_command(context):
    return context["run_command"] or context["command"]


def _append_command_queue_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "command_queue_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "requires_input": bool(rec.get("requires_input")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
    })


def _run_command_queue_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "command_queue_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
    })
    return 0


def _run_command_queue_command(cfg, rec, context, command_input=""):
    text = str(command_input or "").strip()
    if not text:
        raise ValueError("queue-command workflow action requires --command-queue-workflow-command")
    queued = command_queue_module.queue_command(cfg, text)
    print(f"queued {queued['id']}: {queued['command']}")
    if queued.get("target_id"):
        print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
    append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "result": "queued-command",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
        "returncode": 0,
    })
    return 0


def _run_command_queue_workflow_side_effect(cfg, rec, context, command_input="", confirmed=False):
    action_id = context["action_id"]
    if action_id == "inspect-command-queue":
        return print_status(cfg, json_output=False)
    if action_id == "list-command-queue":
        command_queue_module.print_command_queue(cfg, json_output=False)
        rc = 0
    elif action_id == "queue-command":
        return _run_command_queue_command(cfg, rec, context, command_input=command_input)
    elif action_id == "clear-command-queue":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {context['rec_id']}")
        count = command_queue_module.clear_command_queue(cfg)
        print(f"cleared {count} command queue entr{'y' if count == 1 else 'ies'}")
        rc = 0
    elif action_id == "start-command-queue-listener":
        start_service_process(cfg, "command-queue", headless_command=_command_queue_headless_command(context))
        rc = 0
    elif action_id == "stop-command-queue-listener":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {context['rec_id']}")
        stop_recorded_service(
            cfg,
            "command-queue",
            via="command-queue-workflow-action",
            headless_command=_command_queue_headless_command(context),
        )
        rc = 0
    else:
        raise ValueError(f"unsupported command queue workflow action: {action_id}")
    return rc


def _append_command_queue_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "confirmed": bool(confirmed),
        "headless_command": _command_queue_headless_command(context),
        "command": context["command"],
        "returncode": rc,
    })


def run_command_queue_workflow_action(cfg, selector, command_input="", dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("command_queue_workflow_actions") or [], selector, "command queue")
    context = _command_queue_workflow_context(rec)
    print_workflow_action_header(
        "command queue",
        context["rec_id"],
        command=context["command"],
        headless_command=_command_queue_headless_command(context),
    )
    _append_command_queue_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_command_queue_workflow_dry_run(cfg, context)
    rc = _run_command_queue_workflow_side_effect(
        cfg,
        rec,
        context,
        command_input=command_input,
        confirmed=confirmed,
    )
    if context["action_id"] != "inspect-command-queue" and context["action_id"] != "queue-command":
        _append_command_queue_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc


def _file_service_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
    }


def _file_service_headless_command(context):
    return context["run_command"] or context["command"]


def _append_file_service_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "file_service_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_kind": rec.get("route_kind", ""),
        "bridge_profile": rec.get("bridge_profile", ""),
        "requires_input": bool(rec.get("requires_input")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _file_service_headless_command(context),
        "command": context["command"],
    })


def _run_file_service_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "file_service_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "headless_command": _file_service_headless_command(context),
        "command": context["command"],
    })
    return 0


def _run_file_service_stage_file(cfg, rec, context, local_file="", request_name=""):
    path = str(local_file or "").strip()
    if not path:
        raise ValueError("stage-file workflow action requires --file-service-workflow-local-file")
    request = str(request_name or "").strip() or Path(path).name
    staged = staged_files.stage_file(cfg, path, request)
    print(f"staged {staged['request_name']} <- {staged['source_path']}")
    if staged.get("target_id"):
        print(f"target: {staged.get('target_id', '')} ({staged.get('target_label', '') or '-'})")
    print(render_fetch_command(staged["request_name"], cfg))
    append_event(cfg, "workbench", "file_service_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "result": "staged-file",
        "request_name": staged.get("request_name", ""),
        "source_path": staged.get("source_path", ""),
        "sha256": staged.get("sha256", ""),
        "headless_command": _file_service_headless_command(context),
        "command": context["command"],
        "returncode": 0,
    })
    return 0


def _run_file_service_show_upload_command(cfg, rec, target_path=""):
    path = str(target_path or "").strip()
    if not path:
        raise ValueError("show-upload-command workflow action requires --file-service-workflow-target-path")
    target_command = render_file_service_command(["put", path], cfg, host=rec.get("route_host"))
    print(f"target_upload_path={path}")
    print(f"target_command={target_command}")
    return target_command


def _run_file_service_stop(cfg, rec, rec_id, headless_command, confirmed=False):
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"file service workflow action requires --confirm-file-service-workflow-action: {rec_id}")
    stop_recorded_service(
        cfg,
        "file-service",
        via="file-service-workflow-action",
        headless_command=headless_command,
    )
    return 0


def _append_file_service_workflow_completed_event(
    cfg,
    rec,
    context,
    rc,
    confirmed=False,
    target_path="",
    target_command="",
):
    action_id = context["action_id"]
    append_event(cfg, "workbench", "file_service_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_kind": rec.get("route_kind", ""),
        "bridge_profile": rec.get("bridge_profile", ""),
        "confirmed": bool(confirmed),
        "headless_command": _file_service_headless_command(context),
        "command": context["command"],
        "target_upload_path": str(target_path or "").strip() if action_id == "show-upload-command" else "",
        "target_command": target_command if action_id == "show-upload-command" else "",
        "target_command_sha256": hashlib.sha256(target_command.encode("utf-8")).hexdigest() if action_id == "show-upload-command" and target_command else "",
        "returncode": rc,
    })


def run_file_service_workflow_action(cfg, selector, local_file="", request_name="", target_path="", dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("file_service_workflow_actions") or [], selector, "file service")
    context = _file_service_workflow_context(rec)
    action_id = context["action_id"]
    print_workflow_action_header(
        "file service",
        context["rec_id"],
        command=context["command"],
        headless_command=_file_service_headless_command(context),
    )
    _append_file_service_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_file_service_workflow_dry_run(cfg, context)
    if action_id == "inspect-file-workflows":
        return print_status(cfg, json_output=False)
    target_command = ""
    if action_id == "list-staged-files":
        staged_files.print_staged(cfg)
        rc = 0
    elif action_id == "stage-file":
        return _run_file_service_stage_file(cfg, rec, context, local_file=local_file, request_name=request_name)
    elif action_id == "show-upload-command":
        target_command = _run_file_service_show_upload_command(cfg, rec, target_path=target_path)
        rc = 0
    elif action_id == "start-file-service":
        start_service_process(cfg, "file-service", headless_command=_file_service_headless_command(context))
        rc = 0
    elif action_id == "stop-file-service":
        rc = _run_file_service_stop(
            cfg,
            rec,
            context["rec_id"],
            _file_service_headless_command(context),
            confirmed=confirmed,
        )
    else:
        raise ValueError(f"unsupported file service workflow action: {action_id}")
    _append_file_service_workflow_completed_event(
        cfg,
        rec,
        context,
        rc,
        confirmed=confirmed,
        target_path=target_path,
        target_command=target_command,
    )
    return rc


def run_probe_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("probe_workflow_actions") or [], selector, "probe")
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    target_command = str(rec.get("target_command") or render_probe_command(cfg))
    print_workflow_action_header("probe", rec_id, command=command, headless_command=run_command or command)
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
        return print_status(cfg, json_output=False)
    if action_id == "show-target-command":
        rc = 0
    elif action_id == "start-probe":
        start_service_process(cfg, "probe", headless_command=run_command or command)
        rc = 0
    elif action_id == "stop-probe":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"probe workflow action requires --confirm-probe-workflow-action: {rec_id}")
        stop_recorded_service(
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


def _staged_file_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "request": str(rec.get("request_name") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
        "target_details": {
            "target_connectivity_state": rec.get("target_connectivity_state", ""),
            "target_offline_age_bucket": rec.get("target_offline_age_bucket", ""),
            "target_poll_overdue": bool(rec.get("target_poll_overdue")),
            "target_mailbox_pending_work_count": rec.get("target_mailbox_pending_work_count", 0),
            "target_latest_phone_home_status": rec.get("target_latest_phone_home_status", ""),
            "target_latest_successful_phone_home_status": rec.get("target_latest_successful_phone_home_status", ""),
            "target_last_failed_phone_home_status": rec.get("target_last_failed_phone_home_status", ""),
        },
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


def _append_staged_file_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "staged_file_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "requires_target": bool(rec.get("requires_target")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        **context["target_details"],
        **context["fleet_details"],
    })


def _run_staged_file_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "staged_file_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        **context["target_details"],
        **context["fleet_details"],
    })
    return 0


def _run_staged_file_show_fetch_command(cfg, rec, request):
    fetch_command = str(rec.get("fetch_command") or render_fetch_command(request, cfg))
    print(f"request_name={request}")
    if rec.get("target_id"):
        print(f"target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
    print(f"target_command={fetch_command}")
    return 0


def _run_staged_file_queue_fetch(cfg, rec, context):
    request = context["request"]
    target_id = str(rec.get("target_id") or configured_target_filter(cfg) or "").strip()
    if not target_id:
        raise ValueError("queue-staged-fetch staged file workflow action requires --target-id")
    scoped = scoped_target_cfg(cfg, target_id, target_label=str(rec.get("target_label") or cfg.get("_target_label_filter") or ""))
    staged = (staged_files.load_staged(cfg).get("staged") or {}).get(request) or {}
    if not isinstance(staged, dict) or not staged:
        raise ValueError(f"staged request not found: {request}")
    staged_target = str(staged.get("target_id") or "")
    if staged_target and staged_target != target_id:
        raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
    fetch_command = render_fetch_command(request, scoped)
    queued = command_queue_module.queue_command(scoped, fetch_command, metadata={
        "work_kind": "staged-fetch",
        "workflow": "file-service",
        "request_name": request,
        "route_kind": str(staged.get("route_kind") or "direct"),
        "bridge_profile": str(staged.get("bridge_profile") or ""),
        "bridge_route_path": str(staged.get("bridge_route_path") or ""),
    })
    print(f"queued: {queued['id']}")
    print(f"command: {queued['command']}")
    print(f"target: {queued.get('target_id', '')} ({queued.get('target_label', '') or '-'})")
    append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": request,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": target_id,
        "target_label": queued.get("target_label", ""),
        "result": "queued-staged-fetch",
        "command_id": queued.get("id", ""),
        "command_sha256": queued.get("command_sha256", ""),
        "queued_command": queued.get("command", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": True,
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        "returncode": 0,
        **context["target_details"],
        **context["fleet_details"],
    })
    return 0


def _run_staged_file_unstage(cfg, rec, rec_id, request, confirmed=False):
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"staged file workflow action requires --confirm-staged-file-workflow-action: {rec_id}")
    existed = staged_files.unstage_file(cfg, request)
    print(f"unstaged {request}" if existed else f"not staged {request}")
    return 0


def _append_staged_file_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "request_name": context["request"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "confirmed": bool(confirmed),
        "headless_command": context["run_command"] or context["command"],
        "command": context["command"],
        "returncode": rc,
        **context["target_details"],
        **context["fleet_details"],
    })


def run_staged_file_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("staged_file_workflow_actions") or [],
        selector,
        "staged file",
        extra_keys=("request_name",),
    )
    context = _staged_file_workflow_context(rec)
    rec_id = context["rec_id"]
    action_id = context["action_id"]
    request = context["request"]
    command = context["command"]
    run_command = context["run_command"]
    print_workflow_action_header("staged file", rec_id, command=command, headless_command=run_command or command)
    _append_staged_file_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_staged_file_workflow_dry_run(cfg, context)
    if not request:
        raise ValueError(f"staged file workflow action is missing request name: {rec_id}")
    if action_id == "inspect-staged":
        staged_files.print_staged(cfg)
        rc = 0
    elif action_id == "show-fetch-command":
        rc = _run_staged_file_show_fetch_command(cfg, rec, request)
    elif action_id == "queue-staged-fetch":
        return _run_staged_file_queue_fetch(cfg, rec, context)
    elif action_id == "unstage":
        rc = _run_staged_file_unstage(cfg, rec, rec_id, request, confirmed=confirmed)
    else:
        raise ValueError(f"unsupported staged file workflow action: {action_id}")
    _append_staged_file_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc


def run_target_workflow_action(cfg, selector, command_input="", local_file="", request_name="", input_func=None, show_commands=True):
    return workflow_target_runner.run_target_workflow_action(
        cfg,
        selector,
        print_status_func=print_status,
        print_workbench_func=print_workbench,
        start_service_process_func=start_service_process,
        command_input=command_input,
        local_file=local_file,
        request_name=request_name,
        input_func=input_func,
        show_commands=show_commands,
    )
