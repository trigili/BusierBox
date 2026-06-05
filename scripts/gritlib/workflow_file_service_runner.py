"""File service workflow action runner for grit-console."""

import hashlib
from pathlib import Path

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command, render_file_service_command
import gritlib.staged_files as staged_files
from gritlib.workflow_actions import select_workflow_action


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


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


def _run_file_service_stop(cfg, rec, rec_id, headless_command, confirmed=False, stop_recorded_service_func=None):
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"file service workflow action requires --confirm-file-service-workflow-action: {rec_id}")
    stop_recorded_service_func(
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


def run_file_service_workflow_action(
    cfg,
    selector,
    local_file="",
    request_name="",
    target_path="",
    dry_run=False,
    confirmed=False,
    print_status_func=None,
    start_service_process_func=None,
    stop_recorded_service_func=None,
):
    if print_status_func is None:
        raise ValueError("file service workflow runner requires print_status_func")
    if start_service_process_func is None:
        raise ValueError("file service workflow runner requires start_service_process_func")
    if stop_recorded_service_func is None:
        raise ValueError("file service workflow runner requires stop_recorded_service_func")
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("file_service_workflow_actions") or [], selector, "file service")
    context = _file_service_workflow_context(rec)
    action_id = context["action_id"]
    _print_workflow_action_header(
        "file service",
        context["rec_id"],
        command=context["command"],
        headless_command=_file_service_headless_command(context),
    )
    _append_file_service_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_file_service_workflow_dry_run(cfg, context)
    if action_id == "inspect-file-workflows":
        return print_status_func(cfg, json_output=False)
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
        start_service_process_func(cfg, "file-service", headless_command=_file_service_headless_command(context))
        rc = 0
    elif action_id == "stop-file-service":
        rc = _run_file_service_stop(
            cfg,
            rec,
            context["rec_id"],
            _file_service_headless_command(context),
            confirmed=confirmed,
            stop_recorded_service_func=stop_recorded_service_func,
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
