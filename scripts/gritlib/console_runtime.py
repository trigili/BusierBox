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
