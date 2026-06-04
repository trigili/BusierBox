"""Small headless console action dispatch helpers."""

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
        view_line_path(cfg, args.view_path, append_event_fn=append_event_fn)
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
