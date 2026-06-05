"""Workflow action runners for grit-console."""

import hashlib
import subprocess
from pathlib import Path
import gritlib.bridge_routes as bridge_routes
import gritlib.command_queue as command_queue_module
from gritlib.console_display import print_dry_run_notice
from gritlib.console_workbench import status_document, workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import (
    render_fetch_command, render_file_service_command,
)
from gritlib.probe_commands import (
    render_probe_command,
)
from gritlib.release_artifacts import (
    stage_release_selection,
)
import gritlib.service_lifecycle as service_lifecycle
from gritlib.service_runtime import current_shutdown_reason, start_child_process
from gritlib.service_status import (
    run_service_workflow_action_headless_command, service_status_rows,
)
import gritlib.staged_files as staged_files
from gritlib.status_print import print_status_document, print_workbench_snapshot
from gritlib.target_records import (
    configured_target_filter, scoped_target_cfg,
)
from gritlib.workbench_jobs import (
    run_workbench_action_record, start_workbench_job_record,
)
from gritlib.workflow_actions import (
    select_workflow_action, workbench_action_records,
)

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
        rc = print_status(cfg, json_output=False)
    elif action_id == "start-service":
        start_service_process(cfg, context["service"], headless_command=context["headless"])
        rc = 0
    elif action_id == "stop-service":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"service workflow action requires --confirm-service-workflow-action: {context['rec_id']}")
        stop_recorded_service(
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
    print_workflow_action_header(
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


def _operator_daemon_workflow_context(rec):
    action_id = str(rec.get("action_id") or rec.get("workbench_action_id") or "")
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": action_id,
        "workbench_action_id": str(rec.get("workbench_action_id") or action_id),
        "command": str(rec.get("command") or ""),
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


def _operator_daemon_headless_command(rec, context):
    return context["run_command"] or rec.get("headless_command", "") or context["command"]


def _append_operator_daemon_workflow_selected_event(cfg, rec, context, dry_run=False, confirmed=False):
    append_event(cfg, "workbench", "operator_daemon_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "daemon_status": rec.get("daemon_status", ""),
        "daemon_attached": bool(rec.get("daemon_attached")),
        "daemon_child_alive_count": rec.get("daemon_child_alive_count", 0),
        "systemd_user_action": rec.get("systemd_user_action", ""),
        "background_supported": bool(rec.get("background_supported")),
        "requires_confirmation": bool(rec.get("requires_confirmation")),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        **context["fleet_details"],
    })


def _run_operator_daemon_workflow_dry_run(cfg, rec, context, confirmed=False, show_commands=True):
    if rec.get("workflow") == "systemd-user-service":
        rc = run_workbench_action_record(
            cfg,
            workbench_action_records(cfg),
            context["workbench_action_id"],
            dry_run=True,
            confirmed=confirmed,
            show_commands=show_commands,
        )
    else:
        print_dry_run_notice(machine=show_commands)
        rc = 0
    append_event(cfg, "workbench", "operator_daemon_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })
    return rc


def _run_operator_daemon_start(cfg, rec, context):
    started = start_workbench_job_record(
        cfg,
        workbench_action_records(cfg),
        context["workbench_action_id"],
        headless_command=_operator_daemon_headless_command(rec, context),
    )
    print(f"started workbench job {started.get('id', '')}: pid={started.get('pid', '')}")
    print(f"log={started.get('log_path', '')}")
    return 0


def _run_operator_daemon_workbench_action(cfg, context, confirmed=False):
    return run_workbench_action_record(
        cfg,
        workbench_action_records(cfg),
        context["workbench_action_id"],
        dry_run=False,
        confirmed=confirmed,
    )


def _append_operator_daemon_workflow_completed_event(cfg, rec, context, rc, confirmed=False):
    append_event(cfg, "workbench", "operator_daemon_workflow_action_completed", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workbench_action_id": context["workbench_action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "daemon_status": rec.get("daemon_status", ""),
        "daemon_attached": bool(rec.get("daemon_attached")),
        "systemd_user_action": rec.get("systemd_user_action", ""),
        "confirmed": bool(confirmed),
        "headless_command": _operator_daemon_headless_command(rec, context),
        "command": context["command"],
        "returncode": rc,
        **context["fleet_details"],
    })


def run_operator_daemon_workflow_action(cfg, selector, dry_run=False, confirmed=False, show_commands=True):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("operator_daemon_workflow_actions") or [],
        selector,
        "operator daemon",
        extra_keys=("workbench_action_id", "systemd_user_action"),
    )
    context = _operator_daemon_workflow_context(rec)
    print_workflow_action_header(
        "operator daemon",
        context["rec_id"],
        command=context["command"],
        headless_command=_operator_daemon_headless_command(rec, context),
        show_command=show_commands,
    )
    _append_operator_daemon_workflow_selected_event(cfg, rec, context, dry_run=dry_run, confirmed=confirmed)
    if dry_run:
        return _run_operator_daemon_workflow_dry_run(
            cfg,
            rec,
            context,
            confirmed=confirmed,
            show_commands=show_commands,
        )
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"operator daemon workflow action requires --confirm-operator-daemon-workflow-action: {context['rec_id']}")
    if context["action_id"] == "operator-daemon-start":
        rc = _run_operator_daemon_start(cfg, rec, context)
    else:
        rc = _run_operator_daemon_workbench_action(cfg, context, confirmed=confirmed)
    _append_operator_daemon_workflow_completed_event(cfg, rec, context, rc, confirmed=confirmed)
    return rc


def run_release_artifact_workflow_action(cfg, selector, dry_run=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("release_artifact_workflow_actions") or [],
        selector,
        "release artifact",
        extra_keys=("selector", "release_path", "recommendation_id"),
    )
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    selector_value = str(rec.get("selector") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header("release artifact", rec_id, command=command, headless_command=run_command or command)
    append_event(cfg, "workbench", "release_artifact_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "selector": selector_value,
        "selector_kind": rec.get("selector_kind", ""),
        "release_dir": rec.get("release_dir", ""),
        "release_name": rec.get("release_name", ""),
        "release_path": rec.get("release_path", ""),
        "artifact_name": rec.get("artifact_name", ""),
        "recommendation_id": rec.get("recommendation_id", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "headless_command": run_command or command,
        "command": command,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "release_artifact_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "selector": selector_value,
            "headless_command": run_command or command,
            "command": command,
        })
        return 0
    if action_id == "inspect-release":
        return print_status(cfg, json_output=False)
    if action_id == "self-test-release":
        release_dir = str(rec.get("release_dir") or cfg.get("release_dir") or ".")
        cmd = ["scripts/lib/release-self-test", "--release-dir", release_dir, "--json"]
        result = subprocess.run(cmd, text=True)
        append_event(cfg, "workbench", "release_artifact_workflow_action_completed", details={
            "id": rec_id,
            "action_id": action_id,
            "selector": selector_value,
            "headless_command": run_command or command,
            "command": command,
            "returncode": int(result.returncode),
        })
        return int(result.returncode)
    if action_id in ("stage-artifact", "stage-recommendation"):
        if not selector_value:
            raise ValueError(f"release artifact workflow action is missing selector: {rec_id}")
        staged = stage_release_selection(cfg, selector_value)
        print(f"staged {staged['request_name']} <- {staged['source_path']}")
        print(f"release_path={staged.get('release_path', '')} tuple_path={staged.get('tuple_path', '')} payload_preset={staged.get('payload_preset', '')}")
        print(render_fetch_command(staged["request_name"], cfg))
        append_event(cfg, "workbench", "release_artifact_workflow_action_completed", details={
            "id": rec_id,
            "action_id": action_id,
            "selector": selector_value,
            "selector_kind": rec.get("selector_kind", ""),
            "release_dir": rec.get("release_dir", ""),
            "release_name": rec.get("release_name", ""),
            "release_path": staged.get("release_path", ""),
            "artifact_name": staged.get("release_artifact_name", ""),
            "recommendation_id": rec.get("recommendation_id", ""),
            "request_name": staged.get("request_name", ""),
            "source_path": staged.get("source_path", ""),
            "sha256": staged.get("sha256", ""),
            "headless_command": run_command or command,
            "command": command,
            "returncode": 0,
        })
        return 0
    raise ValueError(f"unsupported release artifact workflow action: {action_id}")


def run_command_queue_workflow_action(cfg, selector, command_input="", dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("command_queue_workflow_actions") or [], selector, "command queue")
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header("command queue", rec_id, command=command, headless_command=run_command or command)
    append_event(cfg, "workbench", "command_queue_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
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
        "headless_command": run_command or command,
        "command": command,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "command_queue_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "headless_command": run_command or command,
            "command": command,
        })
        return 0
    if action_id == "inspect-command-queue":
        return print_status(cfg, json_output=False)
    if action_id == "list-command-queue":
        command_queue_module.print_command_queue(cfg, json_output=False)
        rc = 0
    elif action_id == "queue-command":
        text = str(command_input or "").strip()
        if not text:
            raise ValueError("queue-command workflow action requires --command-queue-workflow-command")
        queued = command_queue_module.queue_command(cfg, text)
        print(f"queued {queued['id']}: {queued['command']}")
        if queued.get("target_id"):
            print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
        rc = 0
        append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
            "id": rec_id,
            "action_id": action_id,
            "workflow": rec.get("workflow", ""),
            "category": rec.get("category", ""),
            "result": "queued-command",
            "command_id": queued.get("id", ""),
            "command_sha256": queued.get("command_sha256", ""),
            "queues_offline_work": bool(rec.get("queues_offline_work")),
            "target_phone_home_required": bool(rec.get("target_phone_home_required")),
            "headless_command": run_command or command,
            "command": command,
            "returncode": rc,
        })
        return rc
    elif action_id == "clear-command-queue":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {rec_id}")
        count = command_queue_module.clear_command_queue(cfg)
        print(f"cleared {count} command queue entr{'y' if count == 1 else 'ies'}")
        rc = 0
    elif action_id == "start-command-queue-listener":
        start_service_process(cfg, "command-queue", headless_command=run_command or command)
        rc = 0
    elif action_id == "stop-command-queue-listener":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"command queue workflow action requires --confirm-command-queue-workflow-action: {rec_id}")
        stop_recorded_service(
            cfg,
            "command-queue",
            via="command-queue-workflow-action",
            headless_command=run_command or command,
        )
        rc = 0
    else:
        raise ValueError(f"unsupported command queue workflow action: {action_id}")
    append_event(cfg, "workbench", "command_queue_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "returncode": rc,
    })
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
    proc = start_service_process(
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
    stop_recorded_service(
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
    print_workflow_action_header("bridge profile", rec_id, command=command, headless_command=run_command or command)
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


def _run_target_start_service_action(cfg, scoped, rec, action_id, target_id, target_label, service):
    start_service_process(scoped, service)
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


def _run_target_start_bridge_action(cfg, scoped, rec, action_id, target_id, target_label):
    profile = _target_bridge_profile_from_action(rec, action_id, "start-bridge")
    start_service_process(
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


def run_target_workflow_action(cfg, selector, command_input="", local_file="", request_name="", input_func=None, show_commands=True):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("target_workflow_actions") or [], selector, "target")
    action_id = str(rec.get("action_id") or "")
    target_id = str(rec.get("target_id") or "")
    target_label = str(rec.get("target_label") or "")
    scoped = scoped_target_cfg(cfg, target_id, target_label=target_label)
    append_event(
        cfg,
        "workbench",
        "target_workflow_action_selected",
        details=_target_workflow_action_selected_details(rec, action_id, target_id, target_label),
    )
    print(f"target workflow action: {rec.get('id', '')}")
    if show_commands:
        print(f"command={rec.get('command') or rec.get('headless_command') or ''}")

    if action_id == "inspect-status":
        return print_status(scoped, json_output=False)
    if action_id == "open-workbench":
        print_workbench(scoped)
        return 0
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
    if action_id == "start-file-service":
        return _run_target_start_service_action(cfg, scoped, rec, action_id, target_id, target_label, "file-service")
    if action_id == "serve-probe":
        return _run_target_start_service_action(cfg, scoped, rec, action_id, target_id, target_label, "probe")
    if action_id.startswith("start-bridge:"):
        return _run_target_start_bridge_action(cfg, scoped, rec, action_id, target_id, target_label)
    if action_id.startswith("queue-bridge-start:"):
        return _run_target_queue_bridge_start_action(cfg, scoped, rec, action_id, target_id, target_label)
    raise ValueError(f"unsupported target workflow action: {action_id}")
