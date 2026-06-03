"""systemd user unit helpers for grit-console."""

from pathlib import Path
import subprocess
import sys

from .event_log import append_event
from .service_status import configured_daemon_services
from .shell_utils import shquote


DEFAULT_CONFIG = Path("local/server-config.json")


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


def handle_systemd_user_action(cfg, action, services, unit_name, unit_dir=None, dry_run=False):
    unit_name = systemd_user_unit_name(unit_name)
    unit_dir_path = systemd_user_unit_dir(unit_dir)
    unit_path = unit_dir_path / unit_name
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    daemon_services = configured_daemon_services(cfg, services)
    headless = systemd_user_headless_command(config_path, action, daemon_services, unit_name, unit_dir=unit_dir, dry_run=dry_run)
    daemon_command = " ".join(shquote(str(part)) for part in systemd_user_daemon_command(config_path, daemon_services))
    if action == "print":
        print(render_systemd_user_unit(config_path, daemon_services, unit_name=unit_name), end="")
        append_event(cfg, "operator-daemon", "systemd_user_unit_printed", details={
            "unit_name": unit_name,
            "unit_path": str(unit_path),
            "headless_command": headless,
            "daemon_headless_command": daemon_command,
        })
        return 0
    if action == "install":
        unit_text = render_systemd_user_unit(config_path, daemon_services, unit_name=unit_name)
        if dry_run:
            print(f"would write {unit_path}")
            print(unit_text, end="")
            append_event(cfg, "operator-daemon", "systemd_user_unit_install_dry_run", details={
                "unit_name": unit_name,
                "unit_path": str(unit_path),
                "headless_command": headless,
                "daemon_headless_command": daemon_command,
            })
            return 0
        unit_dir_path.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(unit_text, encoding="utf-8")
        print(f"installed {unit_path}")
        print("run: systemctl --user daemon-reload")
        print(f"run: systemctl --user enable --now {unit_name}")
        append_event(cfg, "operator-daemon", "systemd_user_unit_installed", details={
            "unit_name": unit_name,
            "unit_path": str(unit_path),
            "headless_command": headless,
            "daemon_headless_command": daemon_command,
            "daemon_reload_command": "systemctl --user daemon-reload",
            "enable_now_command": "systemctl --user enable --now " + shquote(unit_name),
        })
        return 0
    if action in ("start", "stop", "restart", "status"):
        cmd = systemctl_user_command(action, unit_name)
        systemctl_command = " ".join(shquote(part) for part in cmd)
        if dry_run:
            print(systemctl_command)
            append_event(cfg, "operator-daemon", "systemd_user_action_dry_run", details={
                "action": action,
                "unit_name": unit_name,
                "headless_command": headless,
                "systemctl_command": systemctl_command,
            })
            return 0
        result = subprocess.run(cmd, text=True)
        append_event(cfg, "operator-daemon", "systemd_user_action_completed", details={
            "action": action,
            "unit_name": unit_name,
            "headless_command": headless,
            "systemctl_command": systemctl_command,
            "returncode": int(result.returncode),
        })
        return int(result.returncode)
    raise ValueError(f"unsupported systemd user action: {action}")
