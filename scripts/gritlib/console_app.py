"""Application entrypoint for grit-console."""

import sys
from gritlib.bridge_routes import (
    attach_target_route_fields,
    bridge_hop_indexes, bridge_hop_records_from_profiles, bridge_hops_from_args,
    bridge_profile_indexes, bridge_profile_record, bridge_profile_records,
    bridge_profile_headless_command as bridge_routes_bridge_profile_headless_command,
    bridge_profile_service_name,
    bridge_profile_record_summary,
    bridge_profile_workflow_action_indexes, bridge_profile_workflow_action_records,
    bridge_profile_workflow_action_status_summary, bridge_profiles_path, bridge_route_path,
    default_bridge_hops, load_bridge_profiles, parse_bridge_hop, ROUTE_HELP_LINES,
    target_route_context,
    save_bridge_profile, delete_bridge_profile, apply_bridge_profile,
    print_bridge_profile, print_bridge_profiles, valid_profile_name,
)
from gritlib.command_queue import (
    append_command_queue_poll_events, append_command_queue_result_events,
    COMMAND_QUEUE_WORK_METADATA_FIELDS, command_queue_delivery_policy_snapshot,
    command_queue_execution_supported, command_queue_expired, command_queue_policy_snapshot,
    command_queue_mode_record_indexes, command_queue_mode_records,
    command_queue_mode_semantics, command_queue_mode_summary,
    command_queue_path, command_queue_policy_errors, command_queue_policy_status,
    command_queue_policy_yes_no, command_queue_state_status,
    command_queue_status_summary, command_queue_summary,
    command_queue_workflow_action_indexes, command_queue_workflow_action_records,
    command_queue_workflow_action_status_summary,
    clear_command_queue, load_command_queue, queue_command,
    handle_command_queue_args, print_command_queue, print_command_queue_mode_lines,
    print_workbench_command_queue_summary, save_command_queue, yes_no,
)
from gritlib.command_queue_service import serve_command_queue
from gritlib.console_actions import (
    handle_bridge_profile_args, handle_console_control_args,
    handle_console_utility_args, handle_file_staging_args,
    handle_workbench_job_args,
    handle_workflow_action_args,
)
from gritlib.console_artifact import handle_artifact_command
from gritlib.console_args import (
    apply_console_arg_overrides, build_arg_parser, handle_early_console_args,
    has_explicit_console_action,
)
from gritlib.console_bringup import handle_bringup_command
from gritlib.console_runtime import (
    handle_operator_daemon_args, listener_action_from_args, script_bytes_from_args,
    serve_listener_action, session_timeout_from_args, timeout_from_args,
)
from gritlib.console_help import print_concise_help, print_console_help_reference
from gritlib.config_utils import (
    DEFAULTS, DEFAULT_CONFIG, DEFAULT_OPERATOR_SESSION_DIR, load_config, yes,
)
from gritlib.build_config import (
    build_config_path, handle_build_config_args,
    unset_workbench_build_config, workbench_config_field_records,
    workbench_config_status_context,
)
from gritlib.event_log import (
    EventLog, append_event, compact_event_details, event_log_status_context,
    event_tail,
    event_status_summary,
    event_tail_availability_text,
    print_event_log_summary,
)
from gritlib.file_transfers import (
    fetch_record_summary, file_service_workflow_status_context,
    file_service_workflow_status_summary, file_transfer_status_context,
recent_fetch_metadata, recent_upload_metadata,
    print_recent_fetches, print_recent_uploads, print_staged_fetch_target_options,
    render_fetch_command,
    staged_fetch_output_name, staged_fetch_target_commands,
target_file_transfer_record_summary,
    target_file_transfer_status_context,
    upload_record_summary,
)
from gritlib.file_service import serve_file_service
from gritlib.service_runtime import (
    SERVICE_MANAGER,
    SESSION_MANAGER,
    SHUTDOWN,
    bind_listen_socket,
    current_shutdown_reason,
    current_stop_reason,
    install_shutdown_handlers,
    pipe,
    record_shutdown_event,
    register_socket,
    register_thread,
    register_transport,
    request_shutdown,
    start_child_process,
    unregister_socket,
    unregister_transport,
)
from gritlib.release_artifacts import (
    artifact_compatibility_lines, artifact_doom_wad_lines,
    artifact_provider_status_lines, discover_release_context,
    release_context,
    release_recommendation_lines,
    release_nav_records, print_release_summary, stage_release_artifact,
    stage_release_nav_item, stage_release_selection,
    release_artifact_workflow_action_status_summary, release_status_context,
)
from gritlib.session_state import (
    atomic_write_json, count_file_lines, elapsed_seconds, mark_service_error,
    mark_service_stopped, parse_utc_timestamp,
    read_json_file, server_state_status, state_file_path, update_server_state,
    utc_from_epoch, utc_now, utc_now_from_mtime,
)
from gritlib.service_status import (
    DAEMON_SERVICE_CHOICES, configured_daemon_services, daemon_child_command,
    operator_daemon_headless_command, operator_stop_headless_command,
    resolve_transport, service_port,
    port_status_summary,
    service_status_context, service_status_rows, service_status_summary,
    service_start_headless_command,
    service_stop_headless_command,
    service_tls_enabled, run_service_workflow_action_headless_command,
    service_workflow_action_indexes, service_workflow_action_records,
    service_workflow_action_status_summary,
    wait_service_port_released,
)
from gritlib.staged_files import (
    file_sha256, load_staged,
    prepare_staged_artifact_for_configure,
    print_staged, stage_dir, stage_file, staged_record_for_configure,
    staged_file_workflow_action_indexes, staged_file_workflow_action_records,
    staged_file_path,
    staged_files_state_status, staged_status_context,
    staged_status_summary, unstage_file,
)
from gritlib.systemd_user import (
    handle_systemd_user_action, systemd_user_unit_name,
)
from gritlib.target_commands import (
    generated_target_command_records,
    rshell_session_policy_record, rshell_session_policy_status,
    shell_listener_max_sessions,
    print_target_command_summary, target_command_display_line,
    target_command_status_context,
    target_command_route_text, target_command_status_summary,
)
from gritlib.version import grit_version
from gritlib.workbench_jobs import (
    cancel_workbench_job_headless_command, cancel_workbench_job_record,
    load_workbench_jobs,
    reconcile_workbench_job_completion_events,
    print_workbench_job_ownership, print_workbench_job_summary,
    run_workbench_action_headless_command,
    run_workbench_action_record,
    start_workbench_job_record,
    start_workbench_job_headless_command,
    workbench_jobs_path, workbench_jobs_state_status,
)
from gritlib.workflow_actions import (
    operator_daemon_workflow_action_status_context,
    operator_daemon_workflow_action_status_summary,
    optional_target_id_arg,
    optional_target_scoped_command,
    operator_console_workflow_records,
    operator_console_workflow_indexes,
    operator_console_workflow_summary,
    operator_console_workflow_status_summary,
    print_workbench_action_summary,
    probe_workflow_action_indexes,
    probe_workflow_run_command,
    probe_workflow_action_status_summary,
    scoped_service_workflow_run_command,
    select_workflow_action,
    target_workflow_action_status_context,
    target_workflow_action_status_summary,
    workbench_action_status_context,
    workbench_action_records,
    workbench_job_status_context,
)
from gritlib.shell_bridge_service import serve_bridge, serve_plain_shell, serve_ssh, serve_tls_shell
from gritlib.probe_service import serve_probe, serve_probe_dns, serve_probe_ftp, serve_probe_tftp
from gritlib.operator_daemon import run_operator_daemon
from gritlib.workflow_runners import (
    print_status,
    stop_managed_services,
    print_workbench,
    start_service_process,
    stop_workbench_started_services,
    stop_recorded_service,
    run_service_workflow_action,
    run_operator_daemon_workflow_action,
    run_release_artifact_workflow_action,
    run_command_queue_workflow_action,
    run_file_service_workflow_action,
    run_probe_workflow_action,
    run_bridge_profile_workflow_action,
    run_staged_file_workflow_action,
    run_target_workflow_action,
)
from gritlib.line_repl_app import run_line_console, run_line_repl

def main(argv=None):
    install_shutdown_handlers()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "artifact":
        return handle_artifact_command(raw_argv[1:], program="grit-console artifact")
    if raw_argv and raw_argv[0] == "bringup":
        return handle_bringup_command(raw_argv[1:])
    parser = build_arg_parser()
    early_args = handle_early_console_args(
        raw_argv,
        parser,
        version_text=f"griTTYkit {grit_version()}",
        print_concise_help_func=print_concise_help,
        print_console_help_reference_func=print_console_help_reference,
    )
    if early_args.handled:
        return early_args.code
    raw_argv = early_args.argv
    args = parser.parse_args(raw_argv)

    cfg = load_config(args.config)
    try:
        apply_console_arg_overrides(cfg, args)
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    try:
        bridge_profile_code = handle_bridge_profile_args(
            cfg,
            args,
            save_bridge_profile_func=save_bridge_profile,
            delete_bridge_profile_func=delete_bridge_profile,
            print_bridge_profile_func=print_bridge_profile,
            print_bridge_profiles_func=print_bridge_profiles,
            bridge_profiles_path_func=bridge_profiles_path,
        )
        if bridge_profile_code is not None:
            return bridge_profile_code
        workbench_job_code = handle_workbench_job_args(
            cfg,
            args,
            workbench_action_records_func=workbench_action_records,
            start_workbench_job_headless_command_func=start_workbench_job_headless_command,
            start_workbench_job_record_func=start_workbench_job_record,
            cancel_workbench_job_headless_command_func=cancel_workbench_job_headless_command,
            cancel_workbench_job_record_func=cancel_workbench_job_record,
            run_workbench_action_record_func=run_workbench_action_record,
        )
        if workbench_job_code is not None:
            return workbench_job_code
        workflow_code = handle_workflow_action_args(
            cfg,
            args,
            run_service_workflow_action_func=run_service_workflow_action,
            run_operator_daemon_workflow_action_func=run_operator_daemon_workflow_action,
            run_release_artifact_workflow_action_func=run_release_artifact_workflow_action,
            run_command_queue_workflow_action_func=run_command_queue_workflow_action,
            run_probe_workflow_action_func=run_probe_workflow_action,
            run_bridge_profile_workflow_action_func=run_bridge_profile_workflow_action,
            run_file_service_workflow_action_func=run_file_service_workflow_action,
            run_staged_file_workflow_action_func=run_staged_file_workflow_action,
            run_target_workflow_action_func=run_target_workflow_action,
        )
        if workflow_code is not None:
            return workflow_code
        build_config_code = handle_build_config_args(cfg, args, append_event_fn=append_event)
        if build_config_code is not None:
            return build_config_code
        utility_code = handle_console_utility_args(cfg, args, append_event_fn=append_event)
        if utility_code is not None:
            return utility_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    try:
        command_queue_code = handle_command_queue_args(cfg, args)
        if command_queue_code is not None:
            return command_queue_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    try:
        control_code = handle_console_control_args(
            cfg,
            args,
            print_status_func=print_status,
            stop_recorded_service_func=stop_recorded_service,
            stop_managed_services_func=stop_managed_services,
            service_stop_headless_command_func=service_stop_headless_command,
            systemd_user_action_func=handle_systemd_user_action,
        )
        if control_code is not None:
            return control_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    timeout = timeout_from_args(args)
    try:
        daemon_code = handle_operator_daemon_args(
            cfg,
            args,
            timeout=timeout,
            run_operator_daemon_func=run_operator_daemon,
        )
        if daemon_code is not None:
            return daemon_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2
    action = listener_action_from_args(cfg, args, resolve_transport)
    script_bytes = script_bytes_from_args(args)
    session_timeout = session_timeout_from_args(args)

    try:
        staging_code, action = handle_file_staging_args(
            cfg,
            args,
            action,
            stage_file_func=stage_file,
            stage_dir_func=stage_dir,
            stage_release_artifact_func=stage_release_artifact,
            unstage_file_func=unstage_file,
            print_staged_func=print_staged,
            render_fetch_command_func=render_fetch_command,
        )
        if staging_code is not None:
            return staging_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    if not has_explicit_console_action(args) and not args.no_console:
        return run_line_console(cfg)

    try:
        listen_code = serve_listener_action(
            cfg,
            args,
            action,
            timeout=timeout,
            script_bytes=script_bytes,
            session_timeout=session_timeout,
            shell_listener_max_sessions_func=shell_listener_max_sessions,
            serve_ssh_func=serve_ssh,
            serve_tls_shell_func=serve_tls_shell,
            serve_plain_shell_func=serve_plain_shell,
            serve_file_service_func=serve_file_service,
            serve_command_queue_func=serve_command_queue,
            serve_bridge_func=serve_bridge,
            serve_probe_func=serve_probe,
            serve_probe_tftp_func=serve_probe_tftp,
            serve_probe_ftp_func=serve_probe_ftp,
            serve_probe_dns_func=serve_probe_dns,
        )
        if listen_code is not None:
            return listen_code
    except KeyboardInterrupt:
        print("grit-console: interrupted, shutting down", file=sys.stderr)
        request_shutdown("keyboard_interrupt")
        record_shutdown_event(cfg, action)
        mark_service_stopped(cfg, action, "keyboard_interrupt")
        return 130
    except OSError:
        return 1
    print(f"unsupported transport: {action}", file=sys.stderr)
    return 2
