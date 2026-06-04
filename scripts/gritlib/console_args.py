"""Argument-to-config helpers for grit-console."""

from dataclasses import dataclass

from gritlib.bridge_routes import apply_bridge_profile


EXPLICIT_CONSOLE_ACTION_ARGS = (
    "transport",
    "daemon",
    "file_service",
    "serve_file",
    "serve_dir",
    "stage_release_artifact",
    "list_staged",
    "unstage",
    "stop",
    "status",
    "json_status",
    "api_status",
    "systemd_user_action",
)


@dataclass(frozen=True)
class EarlyConsoleArgResult:
    handled: bool
    argv: list
    code: int = 0


def handle_early_console_args(
    raw_argv,
    parser,
    *,
    version_text,
    print_concise_help_func,
    print_console_help_reference_func,
):
    """Handle flags that intentionally bypass argparse's full parser."""
    argv = list(raw_argv or [])
    if "--version" in argv or "-V" in argv:
        print(version_text)
        return EarlyConsoleArgResult(True, argv, 0)
    if "--help-console" in argv:
        print_console_help_reference_func()
        return EarlyConsoleArgResult(True, argv, 0)
    if any(arg in ("-h", "--help") for arg in argv):
        print_concise_help_func()
        return EarlyConsoleArgResult(True, argv, 0)
    if "--help-all" in argv:
        argv = [arg for arg in argv if arg != "--help-all"]
        parser.print_help()
        return EarlyConsoleArgResult(True, argv, 0)
    return EarlyConsoleArgResult(False, argv, 0)


def apply_console_arg_overrides(cfg, args):
    """Apply argparse values that act as console configuration overrides."""
    cfg["_config_path"] = args.config
    cfg["_build_config_path"] = args.build_config

    scalar_overrides = (
        ("listen_host", "listen_host", None),
        ("ssh_port", "ssh_listen_port", None),
        ("forward_port", "GRIT_OPERATOR_REMOTE_FORWARD_PORT", None),
        ("file_port", "GRIT_OPERATOR_FILE_SERVICE_PORT", None),
        ("command_queue_port", "GRIT_COMMAND_QUEUE_PORT", str),
        ("bridge_port", "bridge_listen_port", None),
        ("bridge_dest_host", "bridge_dest_host", None),
        ("bridge_dest_port", "bridge_dest_port", None),
        ("probe_port", "GRIT_PROBE_PORT", None),
        ("probe_tftp_port", "GRIT_PROBE_TFTP_PORT", None),
        ("probe_ftp_port", "GRIT_PROBE_FTP_PORT", None),
        ("probe_dns_port", "GRIT_PROBE_DNS_PORT", None),
        ("probe_dns_name", "GRIT_PROBE_DNS_NAME", None),
        ("probe_name", "GRIT_PROBE_NAME", None),
        ("file_service_tls", "GRIT_OPERATOR_FILE_SERVICE_TLS", None),
        ("state_file", "server_state", None),
        ("staged_file", "staged_files", None),
        ("command_queue_file", "command_queue_file", None),
        ("command_copy_file", "command_copy_file", None),
        ("targets_file", "targets_file", None),
        ("bridge_profiles_file", "bridge_profiles_file", None),
        ("target_id", "_target_id_filter", None),
        ("target_label", "_target_label_filter", None),
        ("target_alias", "_target_alias_filter", None),
        ("release_dir", "release_dir", None),
        ("managed_by", "_managed_by", None),
        ("process_log", "_process_log", None),
    )
    for attr, key, transform in scalar_overrides:
        value = getattr(args, attr, None)
        if value:
            cfg[key] = transform(value) if transform else value

    shell_port = args.shell_port or args.socat_port
    if shell_port:
        cfg["GRIT_RSHELL_SOCAT_PORT"] = shell_port

    if args.bridge_profile:
        apply_bridge_profile(cfg, args.bridge_profile)

    if args.event_limit < 0:
        raise ValueError("--event-limit must be >= 0")
    cfg["_event_limit"] = args.event_limit
    return cfg


def has_explicit_console_action(args):
    """Return true when args request work instead of opening the line console."""
    return any(bool(getattr(args, attr, None)) for attr in EXPLICIT_CONSOLE_ACTION_ARGS)
