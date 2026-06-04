"""Runtime launch helpers for grit-console."""

from pathlib import Path


def timeout_from_args(args):
    return None if args.timeout == 0 else args.timeout


def session_timeout_from_args(args):
    return None if args.session_timeout == 0 else args.session_timeout


def script_bytes_from_args(args, path_class=Path):
    if not args.script:
        return None
    script_bytes = path_class(args.script).read_bytes()
    if script_bytes and not script_bytes.endswith(b"\n"):
        script_bytes += b"\n"
    return script_bytes


def listener_action_from_args(cfg, args, resolve_transport_func):
    if args.file_service:
        return "file-service"
    return resolve_transport_func(cfg, args.transport)


def serve_listener_action(
    cfg,
    args,
    action,
    *,
    timeout,
    script_bytes,
    session_timeout,
    shell_listener_max_sessions_func,
    serve_ssh_func,
    serve_tls_shell_func,
    serve_plain_shell_func,
    serve_file_service_func,
    serve_command_queue_func,
    serve_bridge_func,
    serve_probe_func,
    serve_probe_tftp_func,
    serve_probe_ftp_func,
    serve_probe_dns_func,
):
    one_shot_max_sessions = 1 if args.one_shot else 0
    if action == "ssh":
        return serve_ssh_func(cfg, timeout)
    if action == "tls-shell":
        return serve_tls_shell_func(
            cfg,
            timeout,
            use_stdin=not (args.no_stdin or args.log_only),
            max_sessions=shell_listener_max_sessions_func(
                cfg,
                explicit_one_shot=args.one_shot,
                scripted=bool(args.script),
            ),
            script_bytes=script_bytes,
            expect=args.expect,
            session_timeout=session_timeout,
        )
    if action == "plain-shell":
        return serve_plain_shell_func(
            cfg,
            timeout,
            use_stdin=not (args.no_stdin or args.log_only),
            max_sessions=shell_listener_max_sessions_func(
                cfg,
                explicit_one_shot=args.one_shot,
                scripted=bool(args.script),
            ),
            script_bytes=script_bytes,
            expect=args.expect,
            session_timeout=session_timeout,
        )
    if action == "file-service":
        return serve_file_service_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    if action == "command-queue":
        return serve_command_queue_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    if action == "bridge":
        return serve_bridge_func(
            cfg,
            timeout,
            max_sessions=one_shot_max_sessions,
            session_timeout=session_timeout,
        )
    if action == "probe":
        return serve_probe_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    if action == "probe-tftp":
        return serve_probe_tftp_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    if action == "probe-ftp":
        return serve_probe_ftp_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    if action == "probe-dns":
        return serve_probe_dns_func(cfg, timeout, max_sessions=one_shot_max_sessions)
    return None
