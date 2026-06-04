"""Argument-to-config helpers for grit-console."""

import argparse
import textwrap

from dataclasses import dataclass

from gritlib.bridge_routes import apply_bridge_profile
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.service_status import DAEMON_SERVICE_CHOICES


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


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Catch griTTYkit reverse-access transports from a target.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
    Transport modes:
      ssh         — Paramiko reverse-forward listener for Dropbear/dbclient (GRIT_RSHELL_TRANSPORT=ssh)
      tls-shell   — TLS shell listener accepting builtin+tls AND socat+tls transports
      plain-shell — Plaintext shell listener (debug/insecure; socat+none or builtin+none)
      file-service — Receive-only TLS upload service for target-initiated files/evidence
      command-queue — Explicit command queue poll listener
      bridge      — Explicit TCP bridge from a local listener to a configured host:port
      probe — Serve a /bin/sh probe script over HTTP and receive its result
      probe-tftp — Serve the same probe script over UDP TFTP for first-contact fallback
      probe-ftp — Serve the same probe script over simple FTP RETR
      probe-dns — Serve the same probe script as DNS TXT chunks

    File staging:
      --transport file-service --serve-file ./tool --as /tmp/tool
      --transport file-service --serve-dir local/operator-files
      --stage-release-artifact by-tuple/.../bin/grit-target-full
      --release-dir dist/releases/lab --stage-release-artifact bin/grit-target-full
      --transport file-service --list-staged
      --save-bridge-profile lab-http --bridge-port 22206 --bridge-dest-host 10.0.0.8 --bridge-dest-port 80
      --inspect-bridge-profile lab-http
      --delete-bridge-profile lab-http
      --transport bridge --bridge-profile lab-http

    Command queue:
      --queue-command 'grit reality-test --json'
      --list-command-queue
      --record-command-result cq-id --result-json result.json
      --clear-command-queue

    Operator daemon:
      --daemon --daemon-service file-service --daemon-service command-queue
      --daemon --timeout 60
      --systemd-user-action print --daemon-service file-service
      --systemd-user-action install --systemd-user-unit-dir ~/.config/systemd/user

    Build configuration:
      --build-config configs/grit.conf --list-build-config
      --build-config configs/grit.conf --set-build-config GRIT_NORESIDUE_LEVEL=aggressive

    Aliases accepted: ssh-reverse=ssh, socat-tls=tls-shell, builtin-tls=tls-shell
    """),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="JSON config written by menuconfig")
    parser.add_argument("--build-config", default="configs/grit.conf",
                        help="griTTYkit shell build config used by scripts/menuconfig and make package")
    parser.add_argument("--transport",
                        choices=("ssh", "ssh-reverse", "tls-shell", "socat-tls",
                                 "builtin-tls", "plain-shell", "file-service", "command-queue", "bridge", "probe", "probe-tftp", "probe-ftp", "probe-dns"),
                        help="transport to listen for (overrides config)")
    parser.add_argument("--file-service", action="store_true",
                        help="receive target-initiated file uploads and store them under local/sessions")
    parser.add_argument("--version", action="store_true",
                        help="print griTTYkit version and exit")
    parser.add_argument("--help-console", action="store_true",
                        help="print interactive operator console command reference")
    parser.add_argument("--no-console", dest="no_console", action="store_true",
                        help="preserve direct listener CLI behavior when running interactively with no service action")
    parser.add_argument("--status", action="store_true",
                        help="show managed service state, actual listeners, sessions, uploads, and stale warnings")
    parser.add_argument("--json-status", action="store_true",
                        help="print --status information as JSON")
    parser.add_argument("--api-status", action="store_true",
                        help="alias for --json-status for future frontend/API consumers")
    parser.add_argument("--event-limit", type=int, default=12,
                        help="number of recent structured events to include in --status/--json-status output")
    parser.add_argument("--stop", action="store_true",
                        help="stop known managed listeners from server-state PID records")
    parser.add_argument("--stop-service",
                        help="stop one named managed service from server-state PID records")
    parser.add_argument("--daemon", action="store_true",
                        help="run a foreground operator daemon that owns selected listener child processes")
    parser.add_argument("--daemon-service", action="append", default=[],
                        choices=DAEMON_SERVICE_CHOICES,
                        help="service for --daemon to own; may be repeated; default uses *_enable=yes config")
    parser.add_argument("--systemd-user-action",
                        choices=("print", "install", "start", "stop", "restart", "status"),
                        help="render/install/control the operator daemon as a systemd user service")
    parser.add_argument("--systemd-user-unit-name", default="grit-operator.service",
                        help="systemd user service unit name for --systemd-user-action")
    parser.add_argument("--systemd-user-unit-dir",
                        help="systemd user unit directory, default ~/.config/systemd/user")
    parser.add_argument("--systemd-user-dry-run", action="store_true",
                        help="print planned systemd user-service changes/commands without running systemctl")
    parser.add_argument("--serve-file",
                        help="stage a local file for explicit target fetch")
    parser.add_argument("--as", dest="serve_as",
                        help="target request name for --serve-file, for example /tmp/myfile")
    parser.add_argument("--serve-dir",
                        help="stage direct child files from a local directory for explicit target fetch")
    parser.add_argument("--stage-release-artifact",
                        help="stage an artifact from the current or configured release bundle for explicit target fetch")
    parser.add_argument("--release-dir",
                        help="release bundle directory to inspect for status or --stage-release-artifact")
    parser.add_argument("--list-staged", action="store_true",
                        help="list operator-staged target fetch files and commands")
    parser.add_argument("--unstage",
                        help="remove a staged target fetch request name")
    parser.add_argument("--state-file",
                        help="operator workbench state JSON path")
    parser.add_argument("--staged-file",
                        help="operator staged-files JSON path")
    parser.add_argument("--command-queue-file",
                        help="operator command queue JSON path")
    parser.add_argument("--command-copy-file",
                        help="operator last copied/generated command text path")
    parser.add_argument("--targets-file",
                        help="operator target ledger JSON path")
    parser.add_argument("--bridge-profiles-file",
                        help="operator bridge profiles JSON path")
    parser.add_argument("--target-id",
                        help="filter target-aware status/API/workbench records to this target id")
    parser.add_argument("--set-target-label",
                        help="set or override a friendly label for target id in targets.json")
    parser.add_argument("--target-label",
                        help="friendly label to use with --set-target-label")
    parser.add_argument("--target-alias", action="append",
                        help="alias to attach with --set-target-label; may be repeated")
    parser.add_argument("--target-notes",
                        help="operator notes to store with --set-target-label")
    parser.add_argument("--copy-target-command", type=int,
                        help="copy/export generated target command N to clipboard when available and to the command copy file")
    parser.add_argument("--view-path",
                        help="open a local operator path in the configured pager when viewable")
    parser.add_argument("--start-workbench-job",
                        help="start a background-capable operator workflow action by id")
    parser.add_argument("--cancel-workbench-job",
                        help="cancel a managed workbench background job by id when ownership evidence matches")
    parser.add_argument("--run-workbench-action",
                        help="run a foreground operator workflow action by id or visible number")
    parser.add_argument("--workbench-action-dry-run", action="store_true",
                        help="preview a foreground operator workflow action without changing host state where supported")
    parser.add_argument("--confirm-workbench-action", action="store_true",
                        help="confirm execution of a foreground operator workflow action that requires confirmation")
    parser.add_argument("--run-service-workflow-action",
                        help="run a service lifecycle workflow action by id or visible number")
    parser.add_argument("--service-workflow-dry-run", action="store_true",
                        help="preview a service lifecycle workflow action without starting/stopping services")
    parser.add_argument("--confirm-service-workflow-action", action="store_true",
                        help="confirm execution of a service lifecycle workflow action that requires confirmation")
    parser.add_argument("--run-operator-daemon-workflow-action",
                        help="run an operator daemon workflow action by id, systemd action, or visible number")
    parser.add_argument("--operator-daemon-workflow-dry-run", action="store_true",
                        help="preview an operator daemon workflow action without starting/stopping services")
    parser.add_argument("--confirm-operator-daemon-workflow-action", action="store_true",
                        help="confirm execution of an operator daemon workflow action that requires confirmation")
    parser.add_argument("--run-command-queue-workflow-action",
                        help="run a command queue workflow action by id or visible number")
    parser.add_argument("--command-queue-workflow-command",
                        help="command text for the queue-command command queue workflow action")
    parser.add_argument("--command-queue-workflow-dry-run", action="store_true",
                        help="preview a command queue workflow action without changing queue or listener state")
    parser.add_argument("--confirm-command-queue-workflow-action", action="store_true",
                        help="confirm execution of a command queue workflow action that requires confirmation")
    parser.add_argument("--run-probe-workflow-action",
                        help="run a probe workflow action by id or visible number")
    parser.add_argument("--probe-workflow-dry-run", action="store_true",
                        help="preview a probe workflow action without starting/stopping the listener")
    parser.add_argument("--confirm-probe-workflow-action", action="store_true",
                        help="confirm execution of a probe workflow action that requires confirmation")
    parser.add_argument("--run-bridge-profile-workflow-action",
                        help="run a bridge profile workflow action by id, profile name, or visible number")
    parser.add_argument("--bridge-profile-workflow-dry-run", action="store_true",
                        help="preview a bridge profile workflow action without starting/stopping/deleting profiles")
    parser.add_argument("--confirm-bridge-profile-workflow-action", action="store_true",
                        help="confirm execution of a bridge profile workflow action that requires confirmation")
    parser.add_argument("--run-file-service-workflow-action",
                        help="run a file-service workflow action by id or visible number")
    parser.add_argument("--file-service-workflow-local-file",
                        help="local file path for the stage-file file-service workflow action")
    parser.add_argument("--file-service-workflow-request-name",
                        help="request name for the stage-file file-service workflow action")
    parser.add_argument("--file-service-workflow-target-path",
                        help="target path for the show-upload-command file-service workflow action")
    parser.add_argument("--file-service-workflow-dry-run", action="store_true",
                        help="preview a file-service workflow action without changing staged files or listener state")
    parser.add_argument("--confirm-file-service-workflow-action", action="store_true",
                        help="confirm execution of a file-service workflow action that requires confirmation")
    parser.add_argument("--run-staged-file-workflow-action",
                        help="run a staged-file workflow action by id, request name, or visible number")
    parser.add_argument("--staged-file-workflow-dry-run", action="store_true",
                        help="preview a staged-file workflow action without queueing or unstaging")
    parser.add_argument("--confirm-staged-file-workflow-action", action="store_true",
                        help="confirm execution of a staged-file workflow action that requires confirmation")
    parser.add_argument("--run-release-artifact-workflow-action",
                        help="run a release/artifact workflow action by id, selector, or visible number")
    parser.add_argument("--release-artifact-workflow-dry-run", action="store_true",
                        help="preview a release/artifact workflow action without staging or running self-tests")
    parser.add_argument("--job-command", help=argparse.SUPPRESS)
    parser.add_argument("--run-target-workflow-action",
                        help="run a target workflow action by id or visible number")
    parser.add_argument("--target-workflow-command",
                        help="command text for the queue-command target workflow action")
    parser.add_argument("--target-workflow-local-file",
                        help="local file path for the stage-file-fetch target workflow action")
    parser.add_argument("--target-workflow-request-name",
                        help="target request name for the stage-file-fetch target workflow action")
    parser.add_argument("--list-build-config", action="store_true",
                        help="list guided griTTYkit build configuration fields")
    parser.add_argument("--set-build-config", action="append", default=[],
                        help="set a guided griTTYkit build config value as KEY=VALUE")
    parser.add_argument("--queue-command",
                        help="record an explicit operator command queue entry; the poll listener may deliver metadata but will not execute it")
    parser.add_argument("--queue-timeout", type=int,
                        help="timeout metadata for --queue-command, in seconds")
    parser.add_argument("--queue-max-output", type=int,
                        help="max output metadata for --queue-command, in bytes")
    parser.add_argument("--queue-expire-sec", type=int,
                        help="expire queued work after this many seconds; 0 or omitted means no expiration")
    parser.add_argument("--list-command-queue", action="store_true",
                        help="list explicit operator command queue entries")
    parser.add_argument("--json-command-queue", action="store_true",
                        help="print command queue entries as JSON")
    parser.add_argument("--record-command-result",
                        help="record structured JSON result metadata for a queued command id")
    parser.add_argument("--result-json",
                        help="JSON object to attach with --record-command-result")
    parser.add_argument("--clear-command-queue", action="store_true",
                        help="clear explicit operator command queue entries")
    parser.add_argument("--listen-host", help="listener bind address")
    parser.add_argument("--ssh-port", type=int, help="SSH reverse-forward listener port")
    parser.add_argument("--shell-port", type=int,
                        help="TLS/plain shell listener port (socat-port alias also accepted)")
    parser.add_argument("--socat-port", type=int,
                        help=argparse.SUPPRESS)  # compat alias for --shell-port
    parser.add_argument("--forward-port", type=int,
                        help="remote forward port exposed on the operator workstation")
    parser.add_argument("--file-port", type=int,
                        help="receive-only file service listener port")
    parser.add_argument("--command-queue-port", type=int,
                        help="command queue poll listener port")
    parser.add_argument("--bridge-port", type=int,
                        help="TCP bridge listener port")
    parser.add_argument("--bridge-dest-host",
                        help="TCP bridge destination host")
    parser.add_argument("--bridge-dest-port", type=int,
                        help="TCP bridge destination port")
    parser.add_argument("--bridge-profile",
                        help="named bridge profile to use for bridge listener/status context")
    parser.add_argument("--save-bridge-profile",
                        help="create or update a named bridge profile from current bridge flags")
    parser.add_argument("--bridge-profile-purpose",
                        help="purpose text stored with --save-bridge-profile")
    parser.add_argument("--bridge-profile-notes",
                        help="operator notes stored with --save-bridge-profile")
    parser.add_argument("--bridge-hop", action="append", default=[],
                        help="explicit bridge profile hop FROM=TO; may be repeated for multi-hop chains")
    parser.add_argument("--inspect-bridge-profile",
                        help="inspect one named bridge profile")
    parser.add_argument("--delete-bridge-profile",
                        help="delete one named bridge profile")
    parser.add_argument("--list-bridge-profiles", action="store_true",
                        help="list named bridge profiles")
    parser.add_argument("--json-bridge-profiles", action="store_true",
                        help="print named bridge profiles as JSON")
    parser.add_argument("--probe-port", type=int,
                        help="probe HTTP listener port")
    parser.add_argument("--probe-tftp-port", type=int,
                        help="probe TFTP UDP listener port")
    parser.add_argument("--probe-ftp-port", type=int,
                        help="probe FTP listener port")
    parser.add_argument("--probe-dns-port", type=int,
                        help="probe DNS UDP listener port")
    parser.add_argument("--probe-dns-name",
                        help="probe DNS TXT query name, default probe.grit")
    parser.add_argument("--probe-name",
                        help="probe script filename, default probe.sh")
    parser.add_argument("--file-service-tls", choices=("yes", "no"),
                        help="use TLS for file-service uploads (default yes)")
    parser.add_argument("--timeout", type=float, default=0,
                        help="seconds to wait for a connection; 0 waits forever")
    parser.add_argument("--no-stdin", action="store_true",
                        help="do not relay local stdin to the remote shell")
    parser.add_argument("--log-only", action="store_true",
                        help="alias for --no-stdin; receive stdout/session log only")
    parser.add_argument("--one-shot", action="store_true",
                        help="exit after one shell session instead of waiting for reconnects")
    parser.add_argument("--script",
                        help="file containing shell input to send after tls/plain shell connect")
    parser.add_argument("--expect",
                        help="literal text that must appear in captured shell output")
    parser.add_argument("--session-timeout", type=float, default=30,
                        help="seconds to allow a scripted shell session; 0 disables the limit")
    parser.add_argument("--managed-by", help=argparse.SUPPRESS)
    parser.add_argument("--process-log", help=argparse.SUPPRESS)
    return parser


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
