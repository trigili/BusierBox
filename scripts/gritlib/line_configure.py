"""Line-console config generation helpers."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from gritlib.build_config import build_config_path
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.console_display import console_table
from gritlib.probe_results import (
    probe_effective_arch,
    probe_result_by_ordinal,
    probe_synthetic_survey,
)
from gritlib.session_state import read_json_file
from gritlib.shell_utils import shquote
from gritlib.file_transfers import render_fetch_command
from gritlib.session_state import atomic_write_json, utc_now
from gritlib.staged_files import (
    file_sha256,
    load_staged,
    prepare_staged_artifact_for_configure,
    staged_file_path,
    staged_record_for_configure,
)


def parse_line_configure_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd not in {"configure", "trailer"}:
        return {}
    return {"action": "configure", "args": list(args or [])}


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


def artifact_config_script(search_roots=None):
    helper = find_artifact_config(search_roots)
    if helper:
        return helper
    searched = ", ".join(str(path) for path in artifact_config_candidates(search_roots)[:6])
    raise ValueError(f"artifact-config helper not found (searched: {searched})")


def configure_line_artifact(cfg, args, append_event_fn=None):
    selector, action, obfuscation, kv = parse_line_configure_args(args)
    request_name, staged_rec = staged_record_for_configure(cfg, selector)
    if request_name:
        artifact = prepare_staged_artifact_for_configure(cfg, request_name, staged_rec)
    else:
        artifact = Path(selector).expanduser()
        if not artifact.is_file():
            raise ValueError(f"artifact or staged request not found: {selector}")
    helper = artifact_config_script()
    cmd = [str(helper), action, str(artifact)]
    if action == "set":
        cmd = [str(helper), "set", "--obfuscation", obfuscation, str(artifact)] + kv
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        raise ValueError(f"artifact-config exited {result.returncode}")
    if request_name:
        data = load_staged(cfg)
        staged = data.setdefault("staged", {})
        rec = dict(staged.get(request_name) or staged_rec)
        rec.update({
            "source_path": str(artifact),
            "configured_source_path": str(artifact),
            "configured": action != "clear",
            "configured_at": utc_now(),
            "configured_keys": sorted([item.split("=", 1)[0] for item in kv]) if action == "set" else rec.get("configured_keys", []),
            "size": artifact.stat().st_size,
            "sha256": file_sha256(artifact),
            "mtime": int(artifact.stat().st_mtime),
        })
        if action == "clear":
            rec["configured_keys"] = []
        staged[request_name] = rec
        atomic_write_json(staged_file_path(cfg), data)
    fetch_command = render_fetch_command(request_name, cfg) if request_name else ""
    print("Artifact trailer configured:" if action == "set" else f"Artifact trailer {action}:")
    print(f"  artifact: {artifact}")
    if request_name:
        print(f"  name: {request_name}")
        print(f"  target fetch: {fetch_command}")
    if kv:
        print("  keys: " + ", ".join(item.split("=", 1)[0] for item in kv))
    headless = " ".join(shquote(part) for part in cmd)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_artifact_trailer_configured", details={
            "selector": selector,
            "request_name": request_name,
            "artifact": str(artifact),
            "action": action,
            "keys": [item.split("=", 1)[0] for item in kv],
            "sha256": file_sha256(artifact) if artifact.is_file() else "",
            "fetch_command": fetch_command,
            "headless_command": headless,
        })
    return artifact


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


def finish_line_config_run(cfg, write_config_path, event_details, append_event_fn=None):
    if write_config_path:
        print(f"\nConfig written: {write_config_path}")
        print("  reload  — apply it now without restarting")
    else:
        build_cfg = str(build_config_path(cfg))
        print(f"\n  To write: {event_details.get('cmd_name', 'config')} --write-config {shquote(build_cfg)}")
        print(
            "  (build config — separate from server config "
            f"{str(cfg.get('_config_path') or DEFAULT_CONFIG)})"
        )
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_config_generated", details=event_details)


def run_line_probe_config(cfg, args, append_event_fn=None):
    survey_path, write_config_path, extra_args = parse_line_config_args(args, "probe config")
    tmp_survey_path = None
    selected_probe_ordinal = ""
    if not survey_path or str(survey_path).isdigit():
        selected_probe_ordinal = str(survey_path or "1")
        rec = probe_result_by_ordinal(cfg, selected_probe_ordinal)
        if not rec:
            raise ValueError(f"probe result not found: {selected_probe_ordinal} — run: probe results")
        uname_m, endian = probe_effective_arch(rec)
        bits = str(rec.get("word_bits") or "")
        kernel = str(rec.get("uname_r") or rec.get("kernel") or "")
        print(f"Using probe result {selected_probe_ordinal} ({rec.get('received_at', '')})")
        print(f"  arch={uname_m}  kernel={kernel}  bits={bits}  endian={endian}")
        print("  Note: libc, filesystem, and tool data will use estimated defaults.")
        print("")
        synthetic = probe_synthetic_survey(rec)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="grit-probe-",
            delete=False, encoding="utf-8",
        )
        tmp.write(json.dumps(synthetic, indent=2) + "\n")
        tmp.close()
        tmp_survey_path = tmp.name
        survey_path = tmp_survey_path
    else:
        if not Path(survey_path).is_file():
            raise ValueError(f"probe data file not found: {survey_path}")
    try:
        result = run_config_from_survey(survey_path, write_config_path, extra_args)
    finally:
        if tmp_survey_path:
            try:
                Path(tmp_survey_path).unlink()
            except OSError:
                pass
    finish_line_config_run(cfg, write_config_path, {
        "cmd_name": "probe config",
        "survey_path": survey_path,
        "write_config_path": write_config_path or "",
        "exit_code": result.returncode,
        "from_probe": True,
        "probe_ordinal": selected_probe_ordinal,
    }, append_event_fn=append_event_fn)


def run_line_survey_config(cfg, args, find_survey_uploads_fn, append_event_fn=None):
    survey_path, write_config_path, extra_args = parse_line_config_args(args, "survey config")
    if not survey_path:
        uploads = find_survey_uploads_fn()
        if not uploads:
            raise ValueError(
                "no full survey uploads found\n"
                "  on target: grit survey push --host OPERATOR_IP --port FILE_SERVICE_PORT\n"
                "  or use probe data: probe config"
            )
        survey_path = uploads[0].get("stored_path") or ""
        print(f"Using most recent survey upload: {survey_path}")
    if not Path(survey_path).is_file():
        raise ValueError(f"survey file not found: {survey_path}")
    result = run_config_from_survey(survey_path, write_config_path, extra_args)
    finish_line_config_run(cfg, write_config_path, {
        "cmd_name": "survey config",
        "survey_path": survey_path,
        "write_config_path": write_config_path or "",
        "exit_code": result.returncode,
    }, append_event_fn=append_event_fn)


def _preset_from_survey_candidates(search_roots=None):
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
        _add(root / "lib" / "preset-from-survey")
        _add(root / "scripts" / "lib" / "preset-from-survey")
        _add(root / "preset-from-survey")
    return candidates


def find_preset_from_survey(search_roots=None):
    for candidate in _preset_from_survey_candidates(search_roots):
        if candidate.is_file():
            return candidate
    return None


def find_survey_uploads(cfg, limit=20):
    root = Path(str(cfg.get("session_root", "local/sessions")))
    if not root.is_dir():
        return []
    metas = sorted(root.glob("*/files/*.metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for meta_path in metas:
        data = read_json_file(meta_path, {})
        if not isinstance(data, dict):
            continue
        if str(data.get("upload_kind") or "") != "survey":
            continue
        stored = str(data.get("stored_path") or "")
        if not stored or not Path(stored).is_file():
            continue
        data["_meta_path"] = str(meta_path)
        results.append(data)
        if len(results) >= limit:
            break
    return results


def _line_time_text(iso):
    text = str(iso or "")
    if len(text) >= 16 and "T" in text:
        date, rest = text.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return text or "-"


def print_line_survey_status(cfg, append_event_fn=None):
    uploads = find_survey_uploads(cfg)
    console_table(
        f"Survey uploads  ({len(uploads)} found)",
        uploads[:8],
        [
            ("File",    lambda r: r.get("filename") or "-"),
            ("Size",    lambda r: str(r.get("size") or "-")),
            ("Remote",  lambda r: str(r.get("remote_addr") or "-").split(":")[0]),
            ("At",      lambda r: _line_time_text(r.get("timestamp"))),
            ("Path",    lambda r: r.get("stored_path") or "-"),
        ],
    )
    print("")
    if uploads:
        print("  survey config [PATH]         — generate config from full survey")
        print("  survey preset [PATH] --name  — save a reusable target preset")
    else:
        print("  No full survey uploads yet.")
        print("  After deploying griTTYkit, run on the target:")
        print("    grit survey push --host OPERATOR_IP --port FILE_SERVICE_PORT")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_survey_status_viewed", details={
            "upload_count": len(uploads),
        })


def run_line_survey_preset(cfg, args, find_survey_uploads_fn, append_event_fn=None):
    survey_path = None
    preset_name = None
    write_local = False
    overwrite = False
    i = 0
    while i < len(args):
        a = str(args[i])
        if a in {"--name", "-n"} and i + 1 < len(args):
            preset_name = str(args[i + 1])
            i += 2
        elif a.startswith("--name="):
            preset_name = a.split("=", 1)[1]
            i += 1
        elif a in {"--write-local", "--write"}:
            write_local = True
            i += 1
        elif a == "--overwrite":
            overwrite = True
            i += 1
        elif not a.startswith("-"):
            survey_path = a
            i += 1
        else:
            raise ValueError(
                f"unknown option: {a}\n"
                "usage: survey preset [PATH] --name NAME [--write-local] [--overwrite]"
            )
    if not survey_path:
        uploads = find_survey_uploads_fn()
        if not uploads:
            raise ValueError(
                "no full survey uploads found\n"
                "  on target: grit survey push --host OPERATOR_IP --port FILE_SERVICE_PORT\n"
                "  or specify: survey preset PATH --name NAME"
            )
        survey_path = uploads[0].get("stored_path") or ""
        print(f"Using most recent survey upload: {survey_path}")
    if not Path(survey_path).is_file():
        raise ValueError(f"survey file not found: {survey_path}")
    if not preset_name:
        try:
            data = read_json_file(survey_path, {})
            arch = str(data.get("uname_m") or data.get("architecture") or "unknown")
            preset_name = f"target-{arch}"
        except Exception:
            preset_name = "target-unknown"
        print(f"Auto-generated preset name: {preset_name}  (override with --name NAME)")
    script = find_preset_from_survey()
    if not script:
        raise ValueError("preset-from-survey script not found")
    cmd = [str(script), "--survey", survey_path, "--name", preset_name, "--json"]
    if write_local:
        cmd.append("--write-local")
    if overwrite:
        cmd.append("--overwrite")
    headless = " ".join(shquote(str(a)) for a in cmd)
    print(f"Running: {headless}")
    print("")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        raise ValueError(f"preset-from-survey exited {result.returncode}")
    if not write_local:
        print(f"\n  To save: survey preset {shquote(survey_path)} --name {shquote(preset_name)} --write-local")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_survey_preset_generated", details={
            "survey_path": survey_path,
            "preset_name": preset_name,
            "write_local": write_local,
            "headless_command": headless,
            "exit_code": result.returncode,
        })
