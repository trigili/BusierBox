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
from gritlib.profiles import (
    active_profile,
    profile_summary_line,
    upsert_profile_from_probe,
)
from gritlib.line_release import (
    print_release_selector_examples,
    release_selector_examples_are_placeholders,
    release_selector_example_label,
    release_selector_example_lines,
)
from gritlib.release_contexts import release_context
from gritlib.session_state import read_json_file
from gritlib.shell_utils import shquote
from gritlib.file_transfers import render_fetch_command
from gritlib.line_probe_guidance import print_probe_menu_steps
from gritlib.session_state import atomic_write_json, utc_now
from gritlib.staged_files import (
    file_sha256,
    load_staged,
    prepare_staged_artifact_for_configure,
    staged_file_path,
    staged_record_for_configure,
)


def _line_option_token(value):
    text = str(value or "")
    if text.startswith("-") or "=" in text:
        return text
    return "--" + text


def parse_line_configure_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd not in {"stamp", "trailer", "configure"}:
        return {}
    return {"action": "stamp", "args": list(args or [])}


def _artifact_usage(*commands):
    return "usage:\n" + "\n".join(f"  {command}" for command in commands)


def _artifact_action_usage(subcmd):
    return _artifact_usage(f"artifact {subcmd} NAME", f"artifact {subcmd} PATH")


def _stamp_usage():
    return _artifact_usage(
        "stamp NAME show",
        "stamp NAME clear",
        "stamp NAME KEY=VALUE",
        "stamp PATH show",
        "stamp PATH clear",
        "stamp PATH KEY=VALUE",
    )


def _artifact_info_usage():
    return _artifact_usage("artifact info NAME", "artifact info PATH", "artifact info N")


def parse_line_artifact_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd != "artifact":
        return {}
    args = list(args or [])
    subcmd = str(args[0]).strip().lower() if args else ""
    if not subcmd:
        return {"action": "list", "args": []}
    if subcmd in {"info", "inspect"}:
        return {"action": "info", "args": args[1:]}
    if subcmd in {"stamp", "trailer", "configure"}:
        return {"action": "stamp", "args": args[1:]}
    if subcmd in {"show", "clear"}:
        if len(args) < 2:
            raise ValueError(_artifact_action_usage(subcmd))
        return {"action": "stamp", "args": [args[1], subcmd, *args[2:]]}
    return {"action": "stamp", "args": args}


def dispatch_line_configure_command(
    configure_cmd,
    *,
    configure_func=None,
    artifact_list_func=None,
    artifact_info_func=None,
    set_context_func=None,
):
    try:
        action = configure_cmd.get("action")
        if action == "list" and artifact_list_func:
            if set_context_func:
                set_context_func()
            return artifact_list_func()
        if action == "info" and artifact_info_func:
            if set_context_func:
                set_context_func()
            return artifact_info_func(configure_cmd.get("args") or [])
        if configure_func:
            if set_context_func:
                set_context_func()
            result = configure_func(configure_cmd.get("args") or [])
            return result
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported stamp command")


def parse_line_config_args(args, cmd_name):
    survey_path = None
    write_config_path = None
    extra_args = []
    i = 0
    while i < len(args):
        arg = str(args[i])
        opt = _line_option_token(arg)
        if opt in {"--write-config", "-w"} and i + 1 < len(args):
            write_config_path = str(args[i + 1])
            i += 2
        elif opt.startswith("--write-config="):
            write_config_path = opt.split("=", 1)[1]
            i += 1
        elif opt in {
            "--prefer-rshell",
            "--prefer-runtime",
            "--target-preset",
            "--payload-preset",
            "--reality-json",
        } and i + 1 < len(args):
            extra_args.extend([opt, str(args[i + 1])])
            i += 2
        elif opt in {"--allow-network-autorun", "--allow-external-writes"}:
            extra_args.append(opt)
            i += 1
        elif not arg.startswith("-"):
            survey_path = arg
            i += 1
        else:
            raise ValueError(
                f"unknown option: {arg}\n"
                f"usage: {cmd_name}\n"
                f"   or: {cmd_name} PATH\n"
                f"   or: {cmd_name} PATH write-config FILE\n"
                f"   or: {cmd_name} PATH prefer-rshell auto\n"
                f"   or: {cmd_name} PATH prefer-runtime auto"
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
        raise ValueError(_stamp_usage())
    selector = str(args[0])
    rest = list(args[1:])
    if not rest:
        raise ValueError(_stamp_usage())
    action = "set"
    obfuscation = "none"
    kv = []
    i = 0
    while i < len(rest):
        item = str(rest[i])
        opt = _line_option_token(item)
        if opt in {"--show", "show"}:
            action = "show"
            i += 1
        elif opt in {"--clear", "clear"}:
            action = "clear"
            i += 1
        elif opt == "--obfuscation":
            if i + 1 >= len(rest):
                raise ValueError(
                    "stamp obfuscation requires a value:\n"
                    "  stamp NAME obfuscation none\n"
                    "  stamp NAME obfuscation xor"
                )
            obfuscation = str(rest[i + 1])
            i += 2
        elif opt.startswith("--obfuscation="):
            obfuscation = opt.split("=", 1)[1]
            i += 1
        elif opt in option_keys:
            if i + 1 >= len(rest):
                raise ValueError(f"stamp {item} requires a value")
            kv.append(f"{option_keys[opt]}={rest[i + 1]}")
            i += 2
        elif opt.startswith("--") and "=" in opt:
            opt_name, value = opt.split("=", 1)
            if opt_name not in option_keys:
                raise ValueError(f"unknown stamp option: {item}")
            kv.append(f"{option_keys[opt_name]}={value}")
            i += 1
        elif "=" in item:
            kv.append(item)
            i += 1
        else:
            raise ValueError(f"unknown stamp argument: {item}")
    if action == "set" and not kv:
        raise ValueError("stamp needs at least one KEY=VALUE or option")
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


def inspect_artifact_script(search_roots=None):
    candidates = []
    seen = set()

    def _add(path):
        path = Path(path)
        text = str(path)
        if text not in seen:
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
        _add(root / "lib" / "inspect-artifact")
        _add(root / "scripts" / "lib" / "inspect-artifact")
        _add(root / "inspect-artifact")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in candidates[:6])
    raise ValueError(f"inspect-artifact helper not found (searched: {searched})")


def _artifact_selector_path(cfg, selector):
    request_name, staged_rec = staged_record_for_configure(cfg, selector)
    if request_name:
        path = Path(str(staged_rec.get("configured_source_path") or staged_rec.get("source_path") or "")).expanduser()
        if not path.is_file():
            raise ValueError(f"staged source is missing: {path}")
        return request_name, path.resolve(), staged_rec
    path = Path(str(selector or "")).expanduser()
    if not path.is_file():
        raise ValueError(f"artifact or staged request not found: {selector}")
    return "", path.resolve(), {}


def print_line_artifacts(cfg):
    staged = load_staged(cfg).get("staged") or {}
    records = []
    for idx, (name, rec) in enumerate(sorted(staged.items()), 1):
        if not isinstance(rec, dict):
            continue
        records.append({
            "num": str(idx),
            "name": name,
            "kind": rec.get("stage_kind") or rec.get("payload_preset") or "file",
            "source": rec.get("configured_source_path") or rec.get("source_path") or "",
        })
    release_dir = str(cfg.get("release_dir") or "")
    print(f"Artifact files  ({len(records)} staged)")
    print(f"  release dir: {release_dir or '(not set)'}")
    if records:
        console_table(
            "Staged artifacts",
            records,
            [
                ("#", "num"),
                ("Name", "name"),
                ("Kind", "kind"),
                ("Source", "source"),
            ],
        )
    else:
        print("  staged: no artifacts yet")
    print("  next:")
    if records:
        first = records[0]
        name = first.get("name") or "grit"
        num = first.get("num") or "1"
        print(f"    artifact info {num}")
        print(f"    artifact info {name}")
        print(f"    artifact show {name}")
    else:
        print("    release")
        profile = active_profile(cfg)
        rel = release_context(cfg)
        examples = release_selector_example_lines(rel, include_tuple=bool(profile))
        examples_are_placeholders = release_selector_examples_are_placeholders(examples)
        if examples and not examples_are_placeholders:
            print(f"    {examples[0]}  ({release_selector_example_label(examples[0])})")
        elif rel:
            print("    No stageable release artifacts found in this release.")
        print("    release ?  (staging help)")
        if not profile:
            print("    profiles ?  (profile setup)")
            print_probe_menu_steps("    ")
            print("    profile create lab-router  (create profile manually)")
        if examples[1:] and not examples_are_placeholders:
            print("    other staging choices:")
            for example in examples[1:]:
                print(f"      {example}  ({release_selector_example_label(example)})")
        if not profile and examples and not examples_are_placeholders:
            print("    More target-matched staging choices appear after a profile has probe or device details.")
    print("    artifact info ./grit  (inspect a local file directly)")


def print_artifact_context_help(records=None, cfg=None):
    records = list(records or [])
    print("Artifact")
    print("  artifact                       show staged artifacts and current release directory")
    print("  artifact info ./grit           show embedded runtime settings for a local path")
    print("  stamp ./grit operator-host 192.168.8.241")
    print("                                 stamp embedded runtime settings into a local artifact path")
    print("  artifact stamp ./grit transport builtin")
    print("                                 stamp embedded runtime settings by path")
    print("  artifact show ./grit           show stamped runtime settings by path")
    print("  artifact clear ./grit          clear stamped runtime settings by path")
    if records:
        print("  artifact info grit             show embedded runtime settings for a staged artifact")
        print("  artifact info 1                show embedded runtime settings by row number")
        print("  stamp grit operator-host 192.168.8.241")
        print("                                 stamp embedded runtime settings into a staged file or artifact")
        print("  stamp grit show                show current stamped runtime settings")
        print("  stamp grit clear               remove stamped runtime settings")
        print("  artifact stamp grit transport builtin")
        print("                                 stamp embedded runtime settings")
        print("  artifact show grit             show stamped runtime settings")
        print("  artifact clear grit            clear stamped runtime settings")
    else:
        print("")
        print("No staged artifacts yet.")
        has_profile = bool(cfg and active_profile(cfg))
        if has_profile:
            print("Open release and use the staging choices below to stage an artifact.")
        else:
            print("Open release for profile-aware staging steps.")
            print("No active profile yet; run profiles ? for profile setup.")
            rel = release_context(cfg) if cfg else None
            has_release_choices = bool(release_selector_example_lines(rel, include_tuple=False))
            if has_release_choices:
                print("Known device or artifact path: use one of the staging choices below.")
        print("You can also inspect a local file directly with artifact info ./grit.")
        has_choices = print_release_selector_examples(rel, include_tuple=has_profile)
        if not has_profile and has_choices:
            print("  More target-matched staging choices appear after a profile has probe or device details.")
    print("")
    print("Artifact commands inspect or stamp local files; they do not run anything on the target.")
    print("Use `files` or `deliver sample-file` when you want commands to run on the target for staged files.")


def print_line_artifact_info(cfg, args):
    selector = " ".join(str(item) for item in (args or [])).strip()
    if not selector:
        raise ValueError(_artifact_info_usage())
    request_name, path, rec = _artifact_selector_path(cfg, selector)
    print("Artifact info:")
    if request_name:
        print(f"  staged name: {request_name}")
        if rec.get("release_artifact_name"):
            print(f"  release artifact: {rec.get('release_artifact_name')}")
        if rec.get("payload_preset"):
            print(f"  payload preset: {rec.get('payload_preset')}")
    print(f"  path: {path}")
    helper = inspect_artifact_script()
    result = subprocess.run([str(helper), str(path)], cwd=Path(__file__).resolve().parent.parent, text=True, capture_output=True)
    combined_output = (result.stdout or "") + (result.stderr or "")
    missing_config_markers = (
        "embedded payload trailer missing",
        "artifact too small",
    )
    if result.returncode != 0 and any(marker in combined_output.lower() for marker in missing_config_markers):
        print("  embedded runtime settings: not stamped yet")
        stamp_selector = shquote(request_name) if request_name else shquote(str(path))
        operator_host = shquote(str(
            cfg.get("GRIT_OPERATOR_SERVER_HOST")
            or cfg.get("listen_host")
            or "127.0.0.1"
        ))
        print("  common stamp examples:")
        print(f"    stamp {stamp_selector} operator-host {operator_host} transport ssh")
        print(f"    stamp {stamp_selector} zero-arg-mode rshell")
        print(f"    artifact stamp {stamp_selector} operator-host {operator_host} transport ssh")
        print(f"  choose operator host: ip, ip host 1, or ip host {operator_host}")
        return path
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        raise ValueError(f"artifact inspection failed (inspect-artifact exited {result.returncode})")
    return path


def configure_line_artifact(cfg, args, append_event_fn=None):
    if len(args or []) == 1:
        selector = str(args[0])
        profile = active_profile(cfg)
        request_name, staged_rec = staged_record_for_configure(cfg, selector)
        source = ""
        if request_name:
            source = str(staged_rec.get("configured_source_path") or staged_rec.get("source_path") or "")
        elif Path(selector).expanduser().is_file():
            source = str(Path(selector).expanduser())
        elif not profile:
            raise ValueError(f"artifact or staged request not found: {selector}")
        if not profile:
            print("Artifact stamp action needed:")
            print(f"  artifact: {selector}")
            if source:
                print(f"  source: {source}")
            print(f"  inspect current stamp: artifact show {selector}")
            print(f"  clear stamp: artifact clear {selector}")
            print(f"  stamp values: artifact stamp {selector} operator-host HOST zero-arg-mode rshell")
            print("  no active profile is set, so profile-based suggestions are unavailable.")
            return None
        print(f"Artifact configuration suggestions from profile: {profile.get('name') or '-'}")
        print(f"  artifact: {selector}")
        if source:
            print(f"  source: {source}")
        if profile.get("operator_host"):
            print(f"  stamp {selector} operator-host {profile.get('operator_host')} transport {profile.get('preferred_transport') or 'ssh'}")
        else:
            print(f"  stamp {selector} operator-host OPERATOR_HOST transport {profile.get('preferred_transport') or 'ssh'}")
        print("  This only prints suggestions; stamp writes require explicit key/value arguments.")
        return None
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
    if result.returncode != 0 and result.stdout:
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
    print("Artifact stamp applied:" if action == "set" else f"Artifact stamp {action}:")
    print(f"  artifact: {artifact}")
    if request_name:
        print(f"  name: {request_name}")
        print(f"  run on target: {fetch_command}")
        print("  direction: run this on the target to download the staged artifact from the operator")
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
        _add(root / "scripts" / "config-from-survey")
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
        display_cmd_name = event_details.get("display_cmd_name") or event_details.get("cmd_name", "config")
        print(f"\n  To write: {display_cmd_name} write-config {shquote(build_cfg)}")
        print(
            "  (build config — separate from server config "
            f"{str(cfg.get('_config_path') or DEFAULT_CONFIG)})"
        )
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_config_generated", details=event_details)


def run_line_probe_config(cfg, args, append_event_fn=None):
    survey_path, write_config_path, extra_args = parse_line_config_args(args, "listener probe config")
    tmp_survey_path = None
    selected_probe_ordinal = ""
    if not survey_path or str(survey_path).isdigit():
        selected_probe_ordinal = str(survey_path or "1")
        rec = probe_result_by_ordinal(cfg, selected_probe_ordinal)
        if not rec:
            raise ValueError(f"probe result not found: {selected_probe_ordinal} — run: listener probe results")
        uname_m, endian = probe_effective_arch(rec)
        bits = str(rec.get("word_bits") or "")
        kernel = str(rec.get("uname_r") or rec.get("kernel") or "")
        print(f"Using probe result {selected_probe_ordinal} ({rec.get('received_at', '')})")
        print(f"  arch={uname_m}  kernel={kernel}  bits={bits}  endian={endian}")
        if not write_config_path:
            before = active_profile(cfg)
            if before:
                print(f"  updating active profile: {before.get('name')}")
            else:
                print("  creating active profile from probe result")
            profile, created = upsert_profile_from_probe(cfg, rec, ordinal=selected_probe_ordinal)
            print("")
            print(f"Profile {'created' if created else 'updated'}: {profile.get('name')}")
            print(f"  {profile_summary_line(profile)}")
            print(f"  tuple: {profile.get('tuple_path') or '(will be selected from release metadata)'}")
            print("")
            print("Next:")
            print("  profile")
            print("  listener serve start")
            print("  listener serve ssh start")
            print("")
            print("  Export build config if needed:")
            print("    config write-config ./grit-probe.conf")
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_probe_profile_updated", details={
                    "profile": profile.get("name", ""),
                    "created": created,
                    "probe_ordinal": selected_probe_ordinal,
                })
            return profile
        print("  Note: exporting build config from estimated probe defaults.")
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
        "cmd_name": "listener probe config",
        "display_cmd_name": "config",
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
                "no full survey results found\n"
"  on target: grit survey retrieve --host OPERATOR_IP --port FILE_SERVICE_PORT\n"
                "  or use probe data:\n"
                "    use listener probe\n"
                "    config"
            )
        survey_path = uploads[0].get("stored_path") or ""
        print(f"Using most recent survey result: {survey_path}")
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
        f"Survey results  ({len(uploads)} received)",
        uploads[:8],
        [
            ("File",    lambda r: r.get("filename") or "-"),
            ("Size",    lambda r: str(r.get("size") or "-")),
            ("Remote",  lambda r: str(r.get("remote_addr") or "-").split(":")[0]),
            ("At",      lambda r: _line_time_text(r.get("timestamp"))),
            ("Path",    lambda r: r.get("stored_path") or "-"),
        ],
        empty_message="No full survey results received yet.",
    )
    print("")
    if uploads:
        print("  survey config                — generate config from latest full survey")
        print("  survey config PATH           — generate config from a specific full survey")
        print("  survey preset name NAME      — save a reusable target preset from the latest survey")
        print("  survey preset PATH name NAME — save a reusable target preset from a specific survey")
        print("  commands                     — list target-side survey retrieval commands")
    else:
        print("  1. Start the file receiver: start file-service.")
        print("  2. Run `commands` to show target commands with current listener addresses.")
        print("  3. Copy the survey row, usually `copy 2`.")
        print("  4. Run that command on the target, then return here with `survey`.")
    print("  help: survey ?")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_survey_status_viewed", details={
            "upload_count": len(uploads),
        })


def print_survey_context_help(cfg):
    uploads = find_survey_uploads(cfg)
    print("Help: survey — full griTTYkit survey")
    print("")
    print("  survey          show received full survey results")
    print("  survey results  list received full survey results")
    print("  commands        list target commands, including survey collection")
    if uploads:
        print("  survey config                             generate config from the latest survey result")
        print("  survey config PATH                        generate config from a specific survey result")
        print("  survey config PATH write-config FILE      generate and save config")
        print("  survey preset name NAME                   generate a target preset from the latest result")
        print("  survey preset PATH name NAME              generate a target preset from a specific result")
        print("  survey preset PATH name NAME write-local  save preset under local/presets/targets/")
        print("")
        print("Survey results are available; run `survey` to see numbered paths.")
    else:
        print("")
        print("No full survey results received yet.")
        print("1. Start the file receiver: start file-service.")
        print("2. Run `commands` to show target commands with current listener addresses.")
        print("3. Copy the survey row, usually `copy 2`.")
        print("4. Run that command on the target, then return here with `survey`.")
    print("Full survey captures libc, filesystem layout, writable paths, tools, and network interfaces.")


def run_line_survey_preset(cfg, args, find_survey_uploads_fn, append_event_fn=None):
    survey_path = None
    preset_name = None
    write_local = False
    overwrite = False
    i = 0
    while i < len(args):
        a = str(args[i])
        opt = _line_option_token(a)
        if opt in {"--name", "-n"} and i + 1 < len(args):
            preset_name = str(args[i + 1])
            i += 2
        elif opt.startswith("--name="):
            preset_name = opt.split("=", 1)[1]
            i += 1
        elif opt in {"--write-local", "--write"}:
            write_local = True
            i += 1
        elif opt == "--overwrite":
            overwrite = True
            i += 1
        elif not a.startswith("-"):
            survey_path = a
            i += 1
        else:
            raise ValueError(
                f"unknown option: {a}\n"
                "usage:\n"
                "  survey preset name NAME\n"
                "  survey preset PATH name NAME\n"
                "  survey preset PATH name NAME write-local\n"
                "  survey preset PATH name NAME write-local overwrite"
            )
    if not survey_path:
        uploads = find_survey_uploads_fn()
        if not uploads:
            raise ValueError(
                "no full survey results found\n"
"  on target: grit survey retrieve --host OPERATOR_IP --port FILE_SERVICE_PORT\n"
                "  or specify: survey preset PATH name NAME"
            )
        survey_path = uploads[0].get("stored_path") or ""
        print(f"Using most recent survey result: {survey_path}")
    if not Path(survey_path).is_file():
        raise ValueError(f"survey file not found: {survey_path}")
    if not preset_name:
        try:
            data = read_json_file(survey_path, {})
            arch = str(data.get("uname_m") or data.get("architecture") or "unknown")
            preset_name = f"target-{arch}"
        except Exception:
            preset_name = "target-unknown"
        print(f"Auto-generated preset name: {preset_name}  (override with name NAME)")
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
        print(f"\n  To save: survey preset {shquote(survey_path)} name {shquote(preset_name)} write-local")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_survey_preset_generated", details={
            "survey_path": survey_path,
            "preset_name": preset_name,
            "write_local": write_local,
            "headless_command": headless,
            "exit_code": result.returncode,
        })
