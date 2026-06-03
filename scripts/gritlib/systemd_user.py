"""systemd user unit helpers for grit-console."""

from pathlib import Path
import sys

from .shell_utils import shquote


def systemd_unit_quote(value):
    text = str(value)
    if text and all(ch not in text for ch in " \t\n\"\\"):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def systemd_user_unit_name(name):
    value = str(name or "grit-operator.service").strip()
    if not value:
        value = "grit-operator.service"
    if "/" in value or value.startswith(".") or not value.endswith(".service"):
        raise ValueError("systemd user unit name must be a simple .service filename")
    return value


def systemd_user_unit_dir(path=None):
    return Path(str(path or Path.home() / ".config" / "systemd" / "user")).expanduser()


def systemd_user_daemon_command(config_path, services, executable=None, script_path=None):
    command = [str(executable or sys.executable), str(Path(script_path or sys.argv[0]).resolve())]
    command.extend(["--config", str(Path(str(config_path)).expanduser().resolve(strict=False))])
    command.append("--daemon")
    for service in services:
        command.extend(["--daemon-service", service])
    return command


def systemd_user_headless_command(config_path, action, services, unit_name, unit_dir=None, dry_run=False):
    parts = ["scripts/grit-console", "--config", str(config_path)]
    for service in services:
        parts.extend(["--daemon-service", service])
    parts.extend(["--systemd-user-action", action, "--systemd-user-unit-name", unit_name])
    if unit_dir:
        parts.extend(["--systemd-user-unit-dir", str(unit_dir)])
    if dry_run:
        parts.append("--systemd-user-dry-run")
    return " ".join(shquote(str(part)) for part in parts)


def render_systemd_user_unit(config_path, services, unit_name="grit-operator.service", working_dir=None):
    unit_name = systemd_user_unit_name(unit_name)
    command = systemd_user_daemon_command(config_path, services)
    exec_start = " ".join(systemd_unit_quote(part) for part in command)
    if working_dir is None:
        working_dir = Path.cwd().resolve()
    return "\n".join([
        "[Unit]",
        "Description=griTTYkit Operator Daemon",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={systemd_unit_quote(working_dir)}",
        "Environment=PYTHONUNBUFFERED=1",
        f"ExecStart={exec_start}",
        "Restart=on-failure",
        "RestartSec=2",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])


def systemctl_user_command(action, unit_name):
    if action == "status":
        return ["systemctl", "--user", "status", unit_name]
    return ["systemctl", "--user", action, unit_name]
