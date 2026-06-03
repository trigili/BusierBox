"""Small configuration value helpers for grit-console."""

import json
import sys
from pathlib import Path


DEFAULT_CONFIG = Path("local/server-config.json")
DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_STATE_FILE = DEFAULT_OPERATOR_SESSION_DIR / "server-state.json"
DEFAULT_STAGED_FILE = DEFAULT_OPERATOR_SESSION_DIR / "staged-files.json"
DEFAULT_COMMAND_QUEUE_FILE = DEFAULT_OPERATOR_SESSION_DIR / "command-queue.json"
DEFAULT_COMMAND_COPY_FILE = DEFAULT_OPERATOR_SESSION_DIR / "last-command.txt"
DEFAULT_WORKBENCH_JOBS_FILE = DEFAULT_OPERATOR_SESSION_DIR / "workbench-jobs.json"
DEFAULT_TARGETS_FILE = DEFAULT_OPERATOR_SESSION_DIR / "targets.json"
DEFAULT_BRIDGE_PROFILES_FILE = DEFAULT_OPERATOR_SESSION_DIR / "bridge-profiles.json"
DEFAULTS = {
    "GRIT_RSHELL_TRANSPORT": "ssh",
    "GRIT_RSHELL_ENCRYPTION": "tls",
    "listen_host": "0.0.0.0",
    "ssh_listen_port": 22202,
    "GRIT_RSHELL_SOCAT_PORT": 22203,
    "forward_host": "127.0.0.1",
    "GRIT_OPERATOR_REMOTE_FORWARD_PORT": 2200,
    "authorized_dbclient_pubkey": "local/operator-session/id_dbclient.pub",
    "operator_host_key": "local/operator-session/operator_ssh_host_key",
    "tls_cert": "local/operator-session/shell-server.crt",
    "tls_key": "local/operator-session/shell-server.key",
    "tls_verify": "no",
    "session_root": "local/sessions",
    "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "no",
    "GRIT_OPERATOR_FILE_SERVICE_PORT": 22204,
    "GRIT_OPERATOR_FILE_SERVICE_TLS": "yes",
    "bridge_listen_port": 22206,
    "bridge_dest_host": "127.0.0.1",
    "bridge_dest_port": 0,
    "GRIT_PROBE_PORT": 22207,
    "GRIT_PROBE_TFTP_PORT": 22208,
    "GRIT_PROBE_FTP_PORT": 22209,
    "GRIT_PROBE_DNS_PORT": 22210,
    "GRIT_PROBE_DNS_NAME": "probe.grit",
    "GRIT_PROBE_NAME": "probe.sh",
    "operator_session_dir": str(DEFAULT_OPERATOR_SESSION_DIR),
    "server_state": str(DEFAULT_STATE_FILE),
    "staged_files": str(DEFAULT_STAGED_FILE),
    "command_queue_file": str(DEFAULT_COMMAND_QUEUE_FILE),
    "command_copy_file": str(DEFAULT_COMMAND_COPY_FILE),
    "workbench_jobs_file": str(DEFAULT_WORKBENCH_JOBS_FILE),
    "targets_file": str(DEFAULT_TARGETS_FILE),
    "bridge_profiles_file": str(DEFAULT_BRIDGE_PROFILES_FILE),
    "GRIT_COMMAND_QUEUE_ENABLE": "no",
    "GRIT_COMMAND_QUEUE_PORT": "22205",
    "GRIT_COMMAND_QUEUE_TLS": "yes",
    "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "yes",
    "GRIT_COMMAND_QUEUE_TOKEN_SOURCE": "manual",
    "GRIT_COMMAND_QUEUE_TOKEN": "",
    "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "none",
    "GRIT_COMMAND_QUEUE_EXECUTION": "metadata-only",
    "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
    "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC": "5",
    "GRIT_COMMAND_QUEUE_POLL_JITTER_PCT": "0",
    "GRIT_COMMAND_QUEUE_POLL_BACKOFF": "none",
    "GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC": "300",
    "GRIT_COMMAND_QUEUE_MAX_POLLS": "0",
    "GRIT_RSHELL_SESSION_POLICY": "single",
    "GRIT_RSHELL_RETRY_COUNT": "1",
    "GRIT_RSHELL_RETRY_INTERVAL_SEC": "5",
    "GRIT_RSHELL_RETRY_JITTER_PCT": "20",
    "GRIT_RSHELL_RETRY_BACKOFF": "none",
    "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC": "300",
}


def yes(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def apply_operator_session_path_defaults(
    cfg, explicit_keys, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR
):
    operator_dir = Path(str(cfg.get("operator_session_dir", default_operator_session_dir)))
    if str(operator_dir) == str(default_operator_session_dir):
        return cfg
    derived_paths = {
        "server_state": operator_dir / "server-state.json",
        "staged_files": operator_dir / "staged-files.json",
        "command_queue_file": operator_dir / "command-queue.json",
        "command_copy_file": operator_dir / "last-command.txt",
        "workbench_jobs_file": operator_dir / "workbench-jobs.json",
        "targets_file": operator_dir / "targets.json",
        "bridge_profiles_file": operator_dir / "bridge-profiles.json",
        "authorized_dbclient_pubkey": operator_dir / "id_dbclient.pub",
        "operator_host_key": operator_dir / "operator_ssh_host_key",
        "tls_cert": operator_dir / "shell-server.crt",
        "tls_key": operator_dir / "shell-server.key",
    }
    for key, value in derived_paths.items():
        if key not in explicit_keys:
            cfg[key] = str(value)
    return cfg


def load_config(path):
    cfg = dict(DEFAULTS)
    explicit_keys = set()
    p = Path(path)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for key, value in data.items():
                if value not in (None, ""):
                    cfg[key] = value
                    explicit_keys.add(key)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: unable to read {p}: {exc}", file=sys.stderr)
    apply_operator_session_path_defaults(cfg, explicit_keys)
    if "socat_listen_port" in cfg and "GRIT_RSHELL_SOCAT_PORT" not in cfg:
        cfg["GRIT_RSHELL_SOCAT_PORT"] = cfg["socat_listen_port"]
    if "tls_shell_listen_port" in cfg and "GRIT_RSHELL_SOCAT_PORT" not in cfg:
        cfg["GRIT_RSHELL_SOCAT_PORT"] = cfg["tls_shell_listen_port"]
    transport = cfg.get("GRIT_RSHELL_TRANSPORT", "ssh")
    if transport == "socat-tls":
        cfg["GRIT_RSHELL_TRANSPORT"] = "socat"
        cfg.setdefault("GRIT_RSHELL_ENCRYPTION", "tls")
    elif transport == "builtin-tls":
        cfg["GRIT_RSHELL_TRANSPORT"] = "builtin"
        cfg.setdefault("GRIT_RSHELL_ENCRYPTION", "tls")
    for key in (
        "ssh_listen_port",
        "GRIT_RSHELL_SOCAT_PORT",
        "GRIT_OPERATOR_REMOTE_FORWARD_PORT",
        "GRIT_OPERATOR_FILE_SERVICE_PORT",
        "bridge_listen_port",
        "bridge_dest_port",
        "GRIT_PROBE_PORT",
        "GRIT_PROBE_TFTP_PORT",
        "GRIT_PROBE_FTP_PORT",
        "GRIT_PROBE_DNS_PORT",
    ):
        cfg[key] = int(cfg[key])
    return cfg
