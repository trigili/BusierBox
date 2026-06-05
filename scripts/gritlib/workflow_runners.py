"""Workflow action runners for grit-console."""

import hashlib
import subprocess
from pathlib import Path
from gritlib.bridge_routes import (
    bridge_profile_record, bridge_profile_service_name, bridge_profiles_path,
    delete_bridge_profile, load_bridge_profiles, print_bridge_profile,
)
from gritlib.command_queue import (
    clear_command_queue, print_command_queue, queue_command,
)
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
from gritlib.service_lifecycle import (
    start_service_process as lifecycle_start_service_process,
    stop_managed_services as lifecycle_stop_managed_services,
    stop_recorded_service as lifecycle_stop_recorded_service,
    stop_workbench_started_services as lifecycle_stop_workbench_started_services,
)
from gritlib.service_runtime import current_shutdown_reason, start_child_process
from gritlib.service_status import (
    run_service_workflow_action_headless_command, service_status_rows,
)
from gritlib.staged_files import (
    load_staged, print_staged, stage_file, unstage_file,
)
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
    return lifecycle_stop_managed_services(cfg)


def print_workbench(cfg, include_api_summary=True):
    return print_workbench_snapshot(cfg, workbench_snapshot(cfg), include_api_summary=include_api_summary)


def start_service_process(cfg, service, argv_extra=None, headless_command="", state_service=None):
    return lifecycle_start_service_process(
        cfg,
        service,
        argv_extra=argv_extra,
        headless_command=headless_command,
        state_service=state_service,
        start_child_process=start_child_process,
        script_path=Path(__file__).resolve().parents[1] / "grit-console",
    )


def stop_workbench_started_services(cfg):
    return lifecycle_stop_workbench_started_services(cfg, stop_service=stop_recorded_service)


def stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", quiet=False):
    return lifecycle_stop_recorded_service(
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


def run_service_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("service_workflow_actions") or [], selector, "service")
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
    print_workflow_action_header("service", rec_id, command=command, headless_command=headless)
    fleet_details = {
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
    }
    append_event(cfg, "workbench", "service_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "service": service,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": headless,
        "command": command,
        **fleet_details,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "service_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "service": service,
            "headless_command": headless,
            "command": command,
            **fleet_details,
        })
        return 0
    if action_id == "inspect-status":
        rc = print_status(cfg, json_output=False)
    elif action_id == "start-service":
        start_service_process(cfg, service, headless_command=headless)
        rc = 0
    elif action_id == "stop-service":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"service workflow action requires --confirm-service-workflow-action: {rec_id}")
        stop_recorded_service(
            cfg,
            service,
            via="service-workflow-action",
            headless_command=headless,
        )
        rc = 0
    else:
        raise ValueError(f"unsupported service workflow action: {action_id}")
    append_event(cfg, "workbench", "service_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "service": service,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": headless,
        "command": command,
        "returncode": rc,
        **fleet_details,
    })
    return rc


def run_operator_daemon_workflow_action(cfg, selector, dry_run=False, confirmed=False, show_commands=True):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("operator_daemon_workflow_actions") or [],
        selector,
        "operator daemon",
        extra_keys=("workbench_action_id", "systemd_user_action"),
    )
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or rec.get("workbench_action_id") or "")
    workbench_action_id = str(rec.get("workbench_action_id") or action_id)
    command = str(rec.get("command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header(
        "operator daemon",
        rec_id,
        command=command,
        headless_command=run_command or rec.get("headless_command", "") or command,
        show_command=show_commands,
    )
    fleet_details = {
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
    }
    append_event(cfg, "workbench", "operator_daemon_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "workbench_action_id": workbench_action_id,
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
        "headless_command": run_command or rec.get("headless_command", "") or command,
        "command": command,
        **fleet_details,
    })
    if dry_run:
        if rec.get("workflow") == "systemd-user-service":
            rc = run_workbench_action_record(
                cfg,
                workbench_action_records(cfg),
                workbench_action_id,
                dry_run=True,
                confirmed=confirmed,
                show_commands=show_commands,
            )
        else:
            print_dry_run_notice(machine=show_commands)
            rc = 0
        append_event(cfg, "workbench", "operator_daemon_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "workbench_action_id": workbench_action_id,
            "headless_command": run_command or rec.get("headless_command", "") or command,
            "command": command,
            "returncode": rc,
            **fleet_details,
        })
        return rc
    if rec.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"operator daemon workflow action requires --confirm-operator-daemon-workflow-action: {rec_id}")
    if action_id == "operator-daemon-start":
        started = start_workbench_job_record(
            cfg,
            workbench_action_records(cfg),
            workbench_action_id,
            headless_command=run_command or rec.get("headless_command", "") or command,
        )
        print(f"started workbench job {started.get('id', '')}: pid={started.get('pid', '')}")
        print(f"log={started.get('log_path', '')}")
        rc = 0
    else:
        rc = run_workbench_action_record(
            cfg,
            workbench_action_records(cfg),
            workbench_action_id,
            dry_run=False,
            confirmed=confirmed,
        )
    append_event(cfg, "workbench", "operator_daemon_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "workbench_action_id": workbench_action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "daemon_status": rec.get("daemon_status", ""),
        "daemon_attached": bool(rec.get("daemon_attached")),
        "systemd_user_action": rec.get("systemd_user_action", ""),
        "confirmed": bool(confirmed),
        "headless_command": run_command or rec.get("headless_command", "") or command,
        "command": command,
        "returncode": rc,
        **fleet_details,
    })
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
        print_command_queue(cfg, json_output=False)
        rc = 0
    elif action_id == "queue-command":
        text = str(command_input or "").strip()
        if not text:
            raise ValueError("queue-command workflow action requires --command-queue-workflow-command")
        queued = queue_command(cfg, text)
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
        count = clear_command_queue(cfg)
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


def run_file_service_workflow_action(cfg, selector, local_file="", request_name="", target_path="", dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("file_service_workflow_actions") or [], selector, "file service")
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header("file service", rec_id, command=command, headless_command=run_command or command)
    append_event(cfg, "workbench", "file_service_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
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
        "headless_command": run_command or command,
        "command": command,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "file_service_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "headless_command": run_command or command,
            "command": command,
        })
        return 0
    if action_id == "inspect-file-workflows":
        return print_status(cfg, json_output=False)
    if action_id == "list-staged-files":
        print_staged(cfg)
        rc = 0
    elif action_id == "stage-file":
        path = str(local_file or "").strip()
        if not path:
            raise ValueError("stage-file workflow action requires --file-service-workflow-local-file")
        request = str(request_name or "").strip() or Path(path).name
        staged = stage_file(cfg, path, request)
        print(f"staged {staged['request_name']} <- {staged['source_path']}")
        if staged.get("target_id"):
            print(f"target: {staged.get('target_id', '')} ({staged.get('target_label', '') or '-'})")
        print(render_fetch_command(staged["request_name"], cfg))
        rc = 0
        append_event(cfg, "workbench", "file_service_workflow_action_completed", details={
            "id": rec_id,
            "action_id": action_id,
            "workflow": rec.get("workflow", ""),
            "category": rec.get("category", ""),
            "result": "staged-file",
            "request_name": staged.get("request_name", ""),
            "source_path": staged.get("source_path", ""),
            "sha256": staged.get("sha256", ""),
            "headless_command": run_command or command,
            "command": command,
            "returncode": rc,
        })
        return rc
    elif action_id == "show-upload-command":
        path = str(target_path or "").strip()
        if not path:
            raise ValueError("show-upload-command workflow action requires --file-service-workflow-target-path")
        target_command = render_file_service_command(["put", path], cfg, host=rec.get("route_host"))
        print(f"target_upload_path={path}")
        print(f"target_command={target_command}")
        rc = 0
    elif action_id == "start-file-service":
        start_service_process(cfg, "file-service", headless_command=run_command or command)
        rc = 0
    elif action_id == "stop-file-service":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"file service workflow action requires --confirm-file-service-workflow-action: {rec_id}")
        stop_recorded_service(
            cfg,
            "file-service",
            via="file-service-workflow-action",
            headless_command=run_command or command,
        )
        rc = 0
    else:
        raise ValueError(f"unsupported file service workflow action: {action_id}")
    append_event(cfg, "workbench", "file_service_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_kind": rec.get("route_kind", ""),
        "bridge_profile": rec.get("bridge_profile", ""),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "target_upload_path": str(target_path or "").strip() if action_id == "show-upload-command" else "",
        "target_command": target_command if action_id == "show-upload-command" else "",
        "target_command_sha256": hashlib.sha256(target_command.encode("utf-8")).hexdigest() if action_id == "show-upload-command" and target_command else "",
        "returncode": rc,
    })
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


def run_bridge_profile_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("bridge_profile_workflow_actions") or [],
        selector,
        "bridge profile",
        extra_keys=("bridge_profile",),
    )
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    profile = str(rec.get("bridge_profile") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header("bridge profile", rec_id, command=command, headless_command=run_command or command)
    print(f"bridge_profile={profile} route={rec.get('route_path', '')}")
    fleet_details = {
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
    }
    append_event(cfg, "workbench", "bridge_profile_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "bridge_profile": profile,
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
        "headless_command": run_command or command,
        "command": command,
        **fleet_details,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "bridge_profile_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "bridge_profile": profile,
            "headless_command": run_command or command,
            "command": command,
            **fleet_details,
        })
        return 0
    if not profile:
        raise ValueError(f"bridge profile workflow action is missing profile name: {rec_id}")
    if action_id == "inspect-profile":
        return print_bridge_profile(cfg, profile, json_output=False)
    if action_id == "start-profile":
        proc = start_service_process(
            cfg,
            "bridge",
            argv_extra=["--bridge-profile", profile],
            headless_command=run_command or command,
            state_service=bridge_profile_service_name(profile),
        )
        if proc is not None:
            print(f"bridge started: {profile}")
        rc = 0
    elif action_id == "stop-profile":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"bridge profile workflow action requires --confirm-bridge-profile-workflow-action: {rec_id}")
        stop_recorded_service(
            cfg,
            bridge_profile_service_name(profile),
            via="bridge-profile-workflow-action",
            headless_command=run_command or command,
        )
        current = {row["name"]: row for row in service_status_rows(cfg)}.get(bridge_profile_service_name(profile), {})
        if current.get("actual") == "stopped":
            print(f"bridge stopped; port released: {profile}")
        rc = 0
    elif action_id == "delete-profile":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"bridge profile workflow action requires --confirm-bridge-profile-workflow-action: {rec_id}")
        deleted = delete_bridge_profile(cfg, profile)
        print(f"deleted bridge profile {deleted.get('name', '')}: {deleted.get('route_path', '')}")
        print(f"bridge_profiles_file={bridge_profiles_path(cfg)}")
        rc = 0
    else:
        raise ValueError(f"unsupported bridge profile workflow action: {action_id}")
    append_event(cfg, "workbench", "bridge_profile_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "bridge_profile": profile,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "route_path": rec.get("route_path", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "requires_target_online": bool(rec.get("requires_target_online")),
        "multi_hop": bool(rec.get("multi_hop")),
        "hop_count": rec.get("hop_count", 0),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "returncode": rc,
        **fleet_details,
    })
    return rc


def run_staged_file_workflow_action(cfg, selector, dry_run=False, confirmed=False):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("staged_file_workflow_actions") or [],
        selector,
        "staged file",
        extra_keys=("request_name",),
    )
    rec_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    request = str(rec.get("request_name") or "")
    command = str(rec.get("command") or rec.get("headless_command") or "")
    run_command = str(rec.get("run_command") or "")
    print_workflow_action_header("staged file", rec_id, command=command, headless_command=run_command or command)
    target_details = {
        "target_connectivity_state": rec.get("target_connectivity_state", ""),
        "target_offline_age_bucket": rec.get("target_offline_age_bucket", ""),
        "target_poll_overdue": bool(rec.get("target_poll_overdue")),
        "target_mailbox_pending_work_count": rec.get("target_mailbox_pending_work_count", 0),
        "target_latest_phone_home_status": rec.get("target_latest_phone_home_status", ""),
        "target_latest_successful_phone_home_status": rec.get("target_latest_successful_phone_home_status", ""),
        "target_last_failed_phone_home_status": rec.get("target_last_failed_phone_home_status", ""),
    }
    fleet_details = {
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
    }
    append_event(cfg, "workbench", "staged_file_workflow_action_selected", details={
        "id": rec_id,
        "action_id": action_id,
        "request_name": request,
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
        "headless_command": run_command or command,
        "command": command,
        **target_details,
        **fleet_details,
    })
    if dry_run:
        print("dry_run=yes")
        append_event(cfg, "workbench", "staged_file_workflow_action_dry_run", details={
            "id": rec_id,
            "action_id": action_id,
            "request_name": request,
            "headless_command": run_command or command,
            "command": command,
            **target_details,
            **fleet_details,
        })
        return 0
    if not request:
        raise ValueError(f"staged file workflow action is missing request name: {rec_id}")
    if action_id == "inspect-staged":
        print_staged(cfg)
        rc = 0
    elif action_id == "show-fetch-command":
        fetch_command = str(rec.get("fetch_command") or render_fetch_command(request, cfg))
        print(f"request_name={request}")
        if rec.get("target_id"):
            print(f"target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
        print(f"target_command={fetch_command}")
        rc = 0
    elif action_id == "queue-staged-fetch":
        target_id = str(rec.get("target_id") or configured_target_filter(cfg) or "").strip()
        if not target_id:
            raise ValueError("queue-staged-fetch staged file workflow action requires --target-id")
        scoped = scoped_target_cfg(cfg, target_id, target_label=str(rec.get("target_label") or cfg.get("_target_label_filter") or ""))
        staged = (load_staged(cfg).get("staged") or {}).get(request) or {}
        if not isinstance(staged, dict) or not staged:
            raise ValueError(f"staged request not found: {request}")
        staged_target = str(staged.get("target_id") or "")
        if staged_target and staged_target != target_id:
            raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
        fetch_command = render_fetch_command(request, scoped)
        queued = queue_command(scoped, fetch_command, metadata={
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
        rc = 0
        append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
            "id": rec_id,
            "action_id": action_id,
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
            "headless_command": run_command or command,
            "command": command,
            "returncode": rc,
            **target_details,
            **fleet_details,
        })
        return rc
    elif action_id == "unstage":
        if rec.get("requires_confirmation") is True and not confirmed:
            raise ValueError(f"staged file workflow action requires --confirm-staged-file-workflow-action: {rec_id}")
        existed = unstage_file(cfg, request)
        print(f"unstaged {request}" if existed else f"not staged {request}")
        rc = 0
    else:
        raise ValueError(f"unsupported staged file workflow action: {action_id}")
    append_event(cfg, "workbench", "staged_file_workflow_action_completed", details={
        "id": rec_id,
        "action_id": action_id,
        "request_name": request,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "confirmed": bool(confirmed),
        "headless_command": run_command or command,
        "command": command,
        "returncode": rc,
        **target_details,
        **fleet_details,
    })
    return rc


def run_target_workflow_action(cfg, selector, command_input="", local_file="", request_name="", input_func=None, show_commands=True):
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(snap.get("target_workflow_actions") or [], selector, "target")
    action_id = str(rec.get("action_id") or "")
    target_id = str(rec.get("target_id") or "")
    target_label = str(rec.get("target_label") or "")
    scoped = scoped_target_cfg(cfg, target_id, target_label=target_label)
    append_event(cfg, "workbench", "target_workflow_action_selected", details={
        "id": rec.get("id", ""),
        "action_id": action_id,
        "target_id": target_id,
        "target_label": target_label,
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "requires_input": bool(rec.get("requires_input")),
        "headless_command": rec.get("headless_command", rec.get("command", "")),
        "offline_supported": bool(rec.get("offline_supported")),
        "requires_target_online": bool(rec.get("requires_target_online")),
        "queues_offline_work": bool(rec.get("queues_offline_work")),
        "target_phone_home_required": bool(rec.get("target_phone_home_required")),
    })
    print(f"target workflow action: {rec.get('id', '')}")
    if show_commands:
        print(f"command={rec.get('command') or rec.get('headless_command') or ''}")

    if action_id == "inspect-status":
        return print_status(scoped, json_output=False)
    if action_id == "open-workbench":
        print_workbench(scoped)
        return 0
    if action_id == "queue-command":
        command = str(command_input or "")
        if not command and input_func:
            value = input_func("command to queue> ")
            command = value if value is not None else ""
        if not command.strip():
            raise ValueError("queue-command target workflow action requires a command")
        queued = queue_command(scoped, command)
        print(f"queued {queued['id']}: {queued['command']}")
        print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "queued-command",
            "command_id": queued.get("id", ""),
            "command_sha256": queued.get("command_sha256", ""),
        })
        return 0
    if action_id == "queue-probe":
        command = render_probe_command(scoped)
        queued = queue_command(scoped, command, metadata={
            "work_kind": "probe",
            "workflow": "probe",
            "request_name": str(scoped.get("GRIT_PROBE_NAME") or "probe.sh"),
            "route_kind": "bridge" if scoped.get("bridge_profile") else "direct",
            "bridge_profile": str(scoped.get("bridge_profile") or ""),
        })
        print(f"queued {queued['id']}: {queued['command']}")
        print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "queued-probe",
            "command_id": queued.get("id", ""),
            "command_sha256": queued.get("command_sha256", ""),
            "queued_command": queued.get("command", ""),
        })
        return 0
    if action_id == "stage-file-fetch":
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
        staged = stage_file(scoped, path, request)
        print(f"staged {staged['request_name']} <- {staged['source_path']}")
        print(f"target={staged.get('target_id', '')} label={staged.get('target_label', '')}")
        print(render_fetch_command(staged["request_name"], scoped))
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "staged-file-fetch",
            "request_name": staged.get("request_name", ""),
            "source_path": staged.get("source_path", ""),
            "sha256": staged.get("sha256", ""),
        })
        return 0
    if action_id == "show-upload-command":
        target_path = str(command_input or "")
        if not target_path and input_func:
            value = input_func("target file to upload> ")
            target_path = value if value is not None else ""
        target_path = target_path.strip() or "/etc/config/network"
        command = render_file_service_command(["put", target_path], scoped)
        print(f"target_upload_path={target_path}")
        print(f"target_command={command}")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "shown-upload-command",
            "target_upload_path": target_path,
            "target_command": command,
            "target_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else "",
        })
        return 0
    if action_id == "stage-release-artifact":
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
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
    if action_id == "queue-staged-fetch":
        request = str(request_name or "")
        if not request and input_func:
            value = input_func("staged request name> ")
            request = value if value is not None else ""
        request = request.strip()
        if not request:
            raise ValueError("queue-staged-fetch target workflow action requires a staged request name")
        staged = (load_staged(cfg).get("staged") or {}).get(request) or {}
        if not isinstance(staged, dict) or not staged:
            raise ValueError(f"staged request not found: {request}")
        staged_target = str(staged.get("target_id") or "")
        if staged_target and staged_target != target_id:
            raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
        command = render_fetch_command(request, scoped)
        queued = queue_command(scoped, command, metadata={
            "work_kind": "staged-fetch",
            "workflow": "file-service",
            "request_name": request,
            "route_kind": str(staged.get("route_kind") or "direct"),
            "bridge_profile": str(staged.get("bridge_profile") or ""),
            "bridge_route_path": str(staged.get("bridge_route_path") or ""),
        })
        print(f"queued {queued['id']}: {queued['command']}")
        print(f"target={queued.get('target_id', '')} label={queued.get('target_label', '')}")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "queued-staged-fetch",
            "command_id": queued.get("id", ""),
            "command_sha256": queued.get("command_sha256", ""),
            "request_name": request,
            "queued_command": queued.get("command", ""),
        })
        return 0
    if action_id == "start-file-service":
        start_service_process(scoped, "file-service")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "started-service",
            "service": "file-service",
        })
        return 0
    if action_id == "serve-probe":
        start_service_process(scoped, "probe")
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "started-service",
            "service": "probe",
        })
        return 0
    if action_id.startswith("start-bridge:"):
        profile = str(rec.get("bridge_profile") or action_id.split(":", 1)[1])
        if not profile:
            raise ValueError("start-bridge target workflow action is missing a bridge profile")
        start_service_process(
            scoped,
            "bridge",
            argv_extra=["--bridge-profile", profile],
            state_service=bridge_profile_service_name(profile),
        )
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "started-service",
            "service": "bridge",
            "bridge_profile": profile,
        })
        return 0
    if action_id.startswith("queue-bridge-start:"):
        profile = str(rec.get("bridge_profile") or action_id.split(":", 1)[1])
        if not profile:
            raise ValueError("queue-bridge-start target workflow action is missing a bridge profile")
        bridge_profiles = load_bridge_profiles(cfg).get("profiles") or {}
        profile_rec = bridge_profiles.get(profile) if isinstance(bridge_profiles, dict) else {}
        if not isinstance(profile_rec, dict) or not profile_rec:
            raise ValueError(f"bridge profile not found: {profile}")
        profile_info = bridge_profile_record(cfg, profile, profile_rec)
        command = "grit rshell start"
        queued = queue_command(scoped, command, metadata={
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
        append_event(cfg, "workbench", "target_workflow_action_completed", details={
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
            "result": "queued-bridge-start",
            "command_id": queued.get("id", ""),
            "command_sha256": queued.get("command_sha256", ""),
            "queued_command": queued.get("command", ""),
            "bridge_profile": profile,
            "bridge_route_path": profile_info.get("route_path", ""),
            "bridge_requires_target_online": bool(profile_info.get("requires_target_online")),
        })
        return 0
    raise ValueError(f"unsupported target workflow action: {action_id}")
