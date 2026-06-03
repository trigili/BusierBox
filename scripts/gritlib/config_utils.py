"""Small configuration value helpers for grit-console."""

from pathlib import Path


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


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
