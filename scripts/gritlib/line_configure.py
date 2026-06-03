"""Line-console config generation helpers."""

import os
import subprocess
import sys
from pathlib import Path

from gritlib.shell_utils import shquote


def parse_line_config_args(args, cmd_name):
    survey_path = None
    write_config_path = None
    extra_args = []
    i = 0
    while i < len(args):
        arg = str(args[i])
        if arg in {"--write-config", "-w"} and i + 1 < len(args):
            write_config_path = str(args[i + 1])
            i += 2
        elif arg.startswith("--write-config="):
            write_config_path = arg.split("=", 1)[1]
            i += 1
        elif arg in {
            "--prefer-rshell",
            "--prefer-runtime",
            "--target-preset",
            "--payload-preset",
            "--reality-json",
        } and i + 1 < len(args):
            extra_args.extend([arg, str(args[i + 1])])
            i += 2
        elif arg in {"--allow-network-autorun", "--allow-external-writes"}:
            extra_args.append(arg)
            i += 1
        elif not arg.startswith("-"):
            survey_path = arg
            i += 1
        else:
            raise ValueError(
                f"unknown option: {arg}\n"
                f"usage: {cmd_name} [PATH] [--write-config FILE] "
                "[--prefer-rshell auto|ssh|...] [--prefer-runtime auto|...]"
            )
    return survey_path, write_config_path, extra_args


ARTIFACT_CONFIG_OPTION_KEYS = {
    "--operator-host": "GRIT_OPERATOR_SERVER_HOST",
    "--operator-user": "GRIT_OPERATOR_SERVER_USER",
    "--ssh-port": "GRIT_OPERATOR_SERVER_SSH_PORT",
    "--shell-port": "GRIT_RSHELL_SOCAT_PORT",
    "--remote-forward-port": "GRIT_OPERATOR_REMOTE_FORWARD_PORT",
    "--target-bind-host": "GRIT_OPERATOR_TARGET_BIND_HOST",
    "--transport": "GRIT_RSHELL_TRANSPORT",
    "--encryption": "GRIT_RSHELL_ENCRYPTION",
    "--run-mode": "GRIT_RSHELL_RUN_MODE",
    "--session-policy": "GRIT_RSHELL_SESSION_POLICY",
    "--shell-provider": "GRIT_RSHELL_SHELL_PROVIDER",
    "--zero-arg-mode": "GRIT_ZERO_ARG_MODE",
    "--zero-arg-log-mode": "GRIT_ZERO_ARG_LOG_MODE",
    "--zero-arg-command": "GRIT_ZERO_ARG_CUSTOM_COMMAND",
    "--runtime-mode": "GRIT_RUNTIME_MODE",
    "--noresidue-level": "GRIT_NORESIDUE_LEVEL",
    "--retry-count": "GRIT_RSHELL_RETRY_COUNT",
    "--retry-interval": "GRIT_RSHELL_RETRY_INTERVAL_SEC",
    "--retry-jitter": "GRIT_RSHELL_RETRY_JITTER_PCT",
    "--retry-backoff": "GRIT_RSHELL_RETRY_BACKOFF",
    "--retry-max-interval": "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC",
    "--command-queue-enable": "GRIT_COMMAND_QUEUE_ENABLE",
    "--command-queue-port": "GRIT_COMMAND_QUEUE_PORT",
    "--command-queue-execution": "GRIT_COMMAND_QUEUE_EXECUTION",
    "--command-queue-poll-interval": "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC",
    "--command-queue-poll-jitter": "GRIT_COMMAND_QUEUE_POLL_JITTER_PCT",
    "--command-queue-poll-backoff": "GRIT_COMMAND_QUEUE_POLL_BACKOFF",
    "--command-queue-poll-max-interval": "GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC",
    "--command-queue-max-polls": "GRIT_COMMAND_QUEUE_MAX_POLLS",
}


def parse_line_configure_args(args, option_keys=ARTIFACT_CONFIG_OPTION_KEYS):
    if not args:
        raise ValueError("usage: configure NAME|PATH [--show|--clear|KEY=VALUE|options...]")
    selector = str(args[0])
    rest = list(args[1:])
    if not rest:
        raise ValueError("usage: configure NAME|PATH [--show|--clear|KEY=VALUE|options...]")
    action = "set"
    obfuscation = "none"
    kv = []
    i = 0
    while i < len(rest):
        item = str(rest[i])
        if item in {"--show", "show"}:
            action = "show"
            i += 1
        elif item in {"--clear", "clear"}:
            action = "clear"
            i += 1
        elif item == "--obfuscation":
            if i + 1 >= len(rest):
                raise ValueError("configure --obfuscation requires none|xor")
            obfuscation = str(rest[i + 1])
            i += 2
        elif item.startswith("--obfuscation="):
            obfuscation = item.split("=", 1)[1]
            i += 1
        elif item in option_keys:
            if i + 1 >= len(rest):
                raise ValueError(f"configure {item} requires a value")
            kv.append(f"{option_keys[item]}={rest[i + 1]}")
            i += 2
        elif item.startswith("--") and "=" in item:
            opt, value = item.split("=", 1)
            if opt not in option_keys:
                raise ValueError(f"unknown configure option: {opt}")
            kv.append(f"{option_keys[opt]}={value}")
            i += 1
        elif "=" in item:
            kv.append(item)
            i += 1
        else:
            raise ValueError(f"unknown configure argument: {item}")
    if action == "set" and not kv:
        raise ValueError("configure needs at least one KEY=VALUE or option")
    return selector, action, obfuscation, kv


def artifact_config_candidates(search_roots=None):
    seen = set()
    candidates = []

    def _add(path):
        path = Path(path)
        text = str(path)
        if text in seen:
            return
        seen.add(text)
        candidates.append(path)

    module_dir = Path(__file__).resolve().parent
    argv_dir = Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd()
    roots = [
        *(Path(root) for root in (search_roots or [])),
        module_dir.parent,
        module_dir.parent.parent,
        argv_dir,
        argv_dir.parent,
        Path.cwd(),
    ]
    for root in roots:
        _add(root / "lib" / "artifact-config")
        _add(root / "scripts" / "lib" / "artifact-config")
        _add(root / "artifact-config")
    return candidates


def find_artifact_config(search_roots=None):
    for candidate in artifact_config_candidates(search_roots):
        if candidate.is_file():
            return candidate
    return None


def _config_from_survey_candidates(search_roots=None):
    seen = set()

    def _add(path):
        path = Path(path)
        text = str(path)
        if text in seen:
            return
        seen.add(text)
        candidates.append(path)

    candidates = []
    override = os.environ.get("GRIT_CONFIG_FROM_SURVEY")
    if override:
        _add(override)
    module_dir = Path(__file__).resolve().parent
    argv_dir = Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd()
    roots = [
        *(Path(root) for root in (search_roots or [])),
        module_dir.parent,
        module_dir.parent.parent,
        argv_dir,
        argv_dir.parent,
        Path.cwd(),
    ]
    for root in roots:
        _add(root / "lib" / "config-from-survey")
        _add(root / "scripts" / "lib" / "config-from-survey")
        _add(root / "config-from-survey")
    return candidates


def find_config_from_survey(search_roots=None):
    for candidate in _config_from_survey_candidates(search_roots):
        if candidate.is_file():
            return candidate
    return None


def run_config_from_survey(survey_path, write_config_path, extra_args, search_roots=None):
    """Run config-from-survey script and return the subprocess result."""
    script = find_config_from_survey(search_roots)
    if not script:
        searched = ", ".join(str(path) for path in _config_from_survey_candidates(search_roots)[:6])
        raise ValueError(f"config-from-survey script not found (searched: {searched})")
    cmd = [str(script), "--format", "shell"] + list(extra_args or [])
    if write_config_path:
        cmd.extend(["--write-config", write_config_path])
    cmd.append(survey_path)
    print(f"Running: {' '.join(shquote(str(arg)) for arg in cmd)}")
    print("")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        raise ValueError(f"config-from-survey exited {result.returncode}")
    return result
