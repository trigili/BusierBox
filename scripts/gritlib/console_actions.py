"""Small headless console action dispatch helpers."""

from pathlib import Path

from gritlib.operator_io import view_line_path
from gritlib.target_commands import copy_generated_command
from gritlib.target_records import set_target_label, targets_path


def handle_console_utility_args(cfg, args, append_event_fn=None):
    if args.copy_target_command:
        rec = copy_generated_command(cfg, args.copy_target_command)
        print(f"copied target command {args.copy_target_command} to {rec['path']}")
        print(f"clipboard={'yes' if rec['clipboard'] else 'no'}")
        print(rec["text"])
        return 0
    if args.view_path:
        view_line_path(
            cfg,
            args.view_path,
            append_event_fn=append_event_fn,
            via="server-view-path",
        )
        return 0
    if args.set_target_label:
        if args.target_label is None:
            raise ValueError("--set-target-label requires --target-label")
        rec = set_target_label(
            cfg, args.set_target_label, args.target_label,
            aliases=args.target_alias or [], notes=args.target_notes,
        )
        print(f"target {rec.get('target_id', '')} label={rec.get('label', '')}")
        if str(rec.get("notes") or "").strip():
            print(f"notes={str(rec.get('notes') or '').strip()}")
        print(f"targets_file={targets_path(cfg)}")
        return 0
    return None


def handle_console_control_args(
    cfg,
    args,
    *,
    print_status_func,
    stop_recorded_service_func,
    stop_managed_services_func,
    service_stop_headless_command_func,
    systemd_user_action_func,
):
    if args.status or args.json_status or args.api_status:
        return print_status_func(cfg, json_output=args.json_status or args.api_status)
    if args.stop_service:
        stop_recorded_service_func(
            cfg,
            args.stop_service,
            via="server-stop-service",
            headless_command=service_stop_headless_command_func(cfg, args.stop_service),
        )
        return 0
    if args.stop:
        return stop_managed_services_func(cfg)
    if args.systemd_user_action:
        return systemd_user_action_func(
            cfg,
            args.systemd_user_action,
            args.daemon_service,
            args.systemd_user_unit_name,
            unit_dir=args.systemd_user_unit_dir,
            dry_run=args.systemd_user_dry_run,
        )
    return None


def handle_bridge_profile_args(
    cfg,
    args,
    *,
    save_bridge_profile_func,
    delete_bridge_profile_func,
    print_bridge_profile_func,
    print_bridge_profiles_func,
    bridge_profiles_path_func,
):
    if args.save_bridge_profile:
        rec = save_bridge_profile_func(
            cfg,
            args.save_bridge_profile,
            purpose=args.bridge_profile_purpose or "",
            notes=args.bridge_profile_notes or "",
            hop_args=args.bridge_hop,
        )
        print(f"saved bridge profile {rec.get('name', '')}: {rec.get('route_path', '')}")
        print(f"bridge_profiles_file={bridge_profiles_path_func(cfg)}")
        if not (
            args.inspect_bridge_profile or args.delete_bridge_profile or
            args.list_bridge_profiles or args.json_bridge_profiles
        ):
            return 0
    if args.delete_bridge_profile:
        rec = delete_bridge_profile_func(cfg, args.delete_bridge_profile)
        print(f"deleted bridge profile {rec.get('name', '')}: {rec.get('route_path', '')}")
        print(f"bridge_profiles_file={bridge_profiles_path_func(cfg)}")
        if not (args.inspect_bridge_profile or args.list_bridge_profiles or args.json_bridge_profiles):
            return 0
    if args.inspect_bridge_profile:
        return print_bridge_profile_func(
            cfg,
            args.inspect_bridge_profile,
            json_output=args.json_bridge_profiles,
        )
    if args.list_bridge_profiles or args.json_bridge_profiles:
        return print_bridge_profiles_func(cfg, json_output=args.json_bridge_profiles)
    return None


def handle_workbench_job_args(
    cfg,
    args,
    *,
    workbench_action_records_func,
    start_workbench_job_headless_command_func,
    start_workbench_job_record_func,
    cancel_workbench_job_headless_command_func,
    cancel_workbench_job_record_func,
    run_workbench_action_record_func,
):
    if args.start_workbench_job:
        print(f"workbench action: {args.start_workbench_job}")
        headless = start_workbench_job_headless_command_func(
            cfg,
            args.start_workbench_job,
            command_override=args.job_command,
        )
        rec = start_workbench_job_record_func(
            cfg,
            workbench_action_records_func(cfg),
            args.start_workbench_job,
            command_override=args.job_command,
            headless_command=headless,
        )
        print(f"started workbench job {rec.get('id', '')}: pid={rec.get('pid', '')}")
        print(f"log={rec.get('log_path', '')}")
        print(f"command={rec.get('command', '')}")
        return 0
    if args.cancel_workbench_job:
        headless = cancel_workbench_job_headless_command_func(cfg, args.cancel_workbench_job)
        rec = cancel_workbench_job_record_func(
            cfg,
            workbench_action_records_func(cfg),
            args.cancel_workbench_job,
            headless_command=headless,
        )
        print(f"cancel requested for workbench job {rec.get('id', args.cancel_workbench_job)}")
        print(f"pid={rec.get('pid', '')}")
        return 0
    if args.run_workbench_action:
        return run_workbench_action_record_func(
            cfg,
            workbench_action_records_func(cfg),
            args.run_workbench_action,
            dry_run=args.workbench_action_dry_run,
            confirmed=args.confirm_workbench_action,
        )
    return None


def handle_workflow_action_args(
    cfg,
    args,
    *,
    run_service_workflow_action_func,
    run_operator_daemon_workflow_action_func,
    run_release_artifact_workflow_action_func,
    run_command_queue_workflow_action_func,
    run_probe_workflow_action_func,
    run_bridge_profile_workflow_action_func,
    run_file_service_workflow_action_func,
    run_staged_file_workflow_action_func,
    run_target_workflow_action_func,
):
    if args.run_service_workflow_action:
        return run_service_workflow_action_func(
            cfg,
            args.run_service_workflow_action,
            dry_run=args.service_workflow_dry_run,
            confirmed=args.confirm_service_workflow_action,
        )
    if args.run_operator_daemon_workflow_action:
        return run_operator_daemon_workflow_action_func(
            cfg,
            args.run_operator_daemon_workflow_action,
            dry_run=args.operator_daemon_workflow_dry_run,
            confirmed=args.confirm_operator_daemon_workflow_action,
        )
    if args.run_release_artifact_workflow_action:
        return run_release_artifact_workflow_action_func(
            cfg,
            args.run_release_artifact_workflow_action,
            dry_run=args.release_artifact_workflow_dry_run,
        )
    if args.run_command_queue_workflow_action:
        return run_command_queue_workflow_action_func(
            cfg,
            args.run_command_queue_workflow_action,
            command_input=args.command_queue_workflow_command or "",
            dry_run=args.command_queue_workflow_dry_run,
            confirmed=args.confirm_command_queue_workflow_action,
        )
    if args.run_probe_workflow_action:
        return run_probe_workflow_action_func(
            cfg,
            args.run_probe_workflow_action,
            dry_run=args.probe_workflow_dry_run,
            confirmed=args.confirm_probe_workflow_action,
        )
    if args.run_bridge_profile_workflow_action:
        return run_bridge_profile_workflow_action_func(
            cfg,
            args.run_bridge_profile_workflow_action,
            dry_run=args.bridge_profile_workflow_dry_run,
            confirmed=args.confirm_bridge_profile_workflow_action,
        )
    if args.run_file_service_workflow_action:
        return run_file_service_workflow_action_func(
            cfg,
            args.run_file_service_workflow_action,
            local_file=args.file_service_workflow_local_file or "",
            request_name=args.file_service_workflow_request_name or "",
            target_path=args.file_service_workflow_target_path or "",
            dry_run=args.file_service_workflow_dry_run,
            confirmed=args.confirm_file_service_workflow_action,
        )
    if args.run_staged_file_workflow_action:
        return run_staged_file_workflow_action_func(
            cfg,
            args.run_staged_file_workflow_action,
            dry_run=args.staged_file_workflow_dry_run,
            confirmed=args.confirm_staged_file_workflow_action,
        )
    if args.run_target_workflow_action:
        return run_target_workflow_action_func(
            cfg,
            args.run_target_workflow_action,
            command_input=args.target_workflow_command or "",
            local_file=args.target_workflow_local_file or "",
            request_name=args.target_workflow_request_name or "",
        )
    return None


def print_staged_fetch_record(cfg, rec, render_fetch_command_func):
    print(f"staged {rec['request_name']} <- {rec['source_path']}")
    if rec.get("target_id"):
        print(f"target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
    print(render_fetch_command_func(rec["request_name"], cfg))


def handle_file_staging_args(
    cfg,
    args,
    action,
    *,
    stage_file_func,
    stage_dir_func,
    stage_release_artifact_func,
    unstage_file_func,
    print_staged_func,
    render_fetch_command_func,
):
    if args.serve_file:
        request_name = args.serve_as or Path(args.serve_file).name
        rec = stage_file_func(cfg, args.serve_file, request_name)
        print_staged_fetch_record(cfg, rec, render_fetch_command_func)
        action = "file-service"
    if args.serve_dir:
        records = stage_dir_func(cfg, args.serve_dir)
        for rec in records:
            print_staged_fetch_record(cfg, rec, render_fetch_command_func)
        action = "file-service"
    if args.stage_release_artifact:
        rec = stage_release_artifact_func(cfg, args.stage_release_artifact)
        print_staged_fetch_record(cfg, rec, render_fetch_command_func)
        action = "file-service"
    if args.unstage:
        existed = unstage_file_func(cfg, args.unstage)
        print(f"unstaged {args.unstage}" if existed else f"not staged {args.unstage}")
    if args.list_staged:
        print_staged_func(cfg)
        return 0, action
    return None, action
