"""Line-console binary staging workflow helpers."""

import hashlib
from pathlib import Path

from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import (
    print_staged_fetch_target_options,
    render_fetch_command,
)
from gritlib.release_contexts import release_context
from gritlib.release_staging import release_nav_records, stage_release_selection
from gritlib.shell_utils import shquote
from gritlib.staged_files import stage_file


def parse_line_binary_args(args):
    selector = ""
    request_name = ""
    start_file_service = False
    no_start = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--start", "--start-service", "start", "start-service"}:
            start_file_service = True
        elif lower in {"--no-start", "--no-start-service", "no-start", "no-start-service"}:
            no_start = True
        else:
            values.append(item)
    if start_file_service and no_start:
        raise ValueError("usage: serve-binary [start|no-start] [PATH] [NAME]")
    if values:
        selector = values[0]
    if len(values) >= 3 and values[1].lower() == "as":
        request_name = values[2]
    elif len(values) >= 2:
        request_name = values[1]
    return selector, request_name, start_file_service, no_start


def parse_line_binary_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() not in {"serve-binary", "binary"}:
            return {}
    selector, request_name, start_service, no_start = parse_line_binary_args(args)
    return {
        "action": "stage_binary",
        "selector": selector,
        "request_name": request_name,
        "start_service": start_service,
        "no_start": no_start,
    }


def dispatch_line_binary_command(
    binary_cmd,
    *,
    stage_binary_func=None,
    set_context_func=None,
):
    try:
        if stage_binary_func:
            result = stage_binary_func(
                binary_cmd.get("selector", ""),
                binary_cmd.get("request_name", ""),
                prompt_for_missing=not binary_cmd.get("selector"),
                prompt_start=(
                    not binary_cmd.get("selector")
                    and not bool(binary_cmd.get("no_start"))
                ),
                start_file_service=bool(binary_cmd.get("start_service")),
            )
            if set_context_func:
                set_context_func()
            return result
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported binary command")


def _print_file_service_note(started):
    print(f"  file service {'started' if started else 'not started'}")


def _print_line_binary_release_choices(rel, prompt_for_missing):
    if not rel or not prompt_for_missing:
        return
    nav = release_nav_records(rel, rel.get("devices") or [], rel.get("tuples") or [], limit=6)
    print("Release binary choices:")
    for idx, item in enumerate(nav, 1):
        print(f"  {idx}: {item.get('label', '')}")


def _line_binary_selector(selector, prompt_for_missing, line_input_fn):
    default_path = "dist/grit-native-full"
    if not selector and prompt_for_missing:
        selector_line = line_input_fn(f"binary path or release selector [{default_path}]> ") if line_input_fn else None
        return selector_line.strip() if selector_line is not None and selector_line.strip() else default_path
    return selector or default_path


def _line_binary_request_name(request_name, prompt_for_missing, line_input_fn):
    if not request_name and prompt_for_missing:
        name_line = line_input_fn("target request name [grit]> ") if line_input_fn else None
        return name_line.strip() if name_line is not None and name_line.strip() else "grit"
    return request_name or "grit"


def _line_binary_file_headless(cfg, source_path, request_name):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --serve-file "
        + shquote(str(source_path))
        + " --as "
        + shquote(request_name)
        + " --list-staged"
    )


def _line_binary_release_headless(cfg, selector):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --stage-release-artifact "
        + shquote(selector)
        + " --list-staged"
    )


def _stage_line_binary_record(cfg, selector, request_name, rel):
    source_path = Path(selector).expanduser()
    if source_path.is_file():
        headless = _line_binary_file_headless(cfg, source_path, request_name)
        rec = stage_file(cfg, str(source_path), request_name, metadata={"stage_kind": "operator-binary"})
        return rec, headless
    if not rel:
        raise ValueError(f"binary path does not exist and no release bundle is available: {selector}")
    headless = _line_binary_release_headless(cfg, selector)
    rec = stage_release_selection(cfg, selector)
    return rec, headless


def _line_binary_run_hint(rec):
    run_name = "./" + Path(rec["request_name"]).name
    return "chmod +x " + shquote(run_name) + " && " + shquote(run_name) + " --help"


def _print_line_binary_staged(rec, fetch_command, run_hint):
    print("griTTYkit binary staged for target delivery:")
    print(f"  name: {rec.get('request_name', '')}")
    print(f"  source: {rec.get('source_path', '')}")
    print(f"  sha256: {str(rec.get('sha256', ''))[:16]}...")
    print(f"  target command: {fetch_command}")
    print(f"  run hint: {run_hint}")


def _maybe_start_line_binary_file_service(
    start_file_service,
    prompt_start,
    line_input_fn,
    start_file_service_fn,
):
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        return True
    if not prompt_start:
        return False
    start_line = line_input_fn("start file-service now? [y/N]> ") if line_input_fn else None
    started = start_line is not None and start_line.strip().lower() in ("y", "yes")
    if started and start_file_service_fn:
        start_file_service_fn()
    return started


def _append_line_binary_event(
    cfg,
    append_event_fn,
    *,
    headless,
    rec,
    fetch_command,
    run_hint,
    fetch_options,
    started,
):
    if not append_event_fn:
        return
    append_event_fn(cfg, "workbench", "workbench_binary_served", details={
        "headless_command": headless,
        "request_name": rec.get("request_name", ""),
        "source_path": rec.get("source_path", ""),
        "sha256": rec.get("sha256", ""),
        "fetch_command": fetch_command,
        "target_run_hint": run_hint,
        "fetch_options": fetch_options,
        "started_file_service": started,
        "stage_kind": rec.get("stage_kind", ""),
        "release_artifact_name": rec.get("release_artifact_name", ""),
        "release_path": rec.get("release_path", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
    })


def stage_line_binary(
    cfg,
    selector="",
    request_name="",
    prompt_for_missing=True,
    prompt_start=True,
    start_file_service=False,
    show_headless=False,
    line_input_fn=None,
    start_file_service_fn=None,
    append_event_fn=None,
):
    rel = release_context(cfg)
    _print_line_binary_release_choices(rel, prompt_for_missing)
    selector = _line_binary_selector(selector, prompt_for_missing, line_input_fn)
    request_name = _line_binary_request_name(request_name, prompt_for_missing, line_input_fn)
    rec, headless = _stage_line_binary_record(cfg, selector, request_name, rel)
    fetch_command = render_fetch_command(rec["request_name"], cfg)
    run_hint = _line_binary_run_hint(rec)
    _print_line_binary_staged(rec, fetch_command, run_hint)
    fetch_options = print_staged_fetch_target_options(
        rec.get("request_name", ""),
        cfg,
        output_name=rec.get("request_name", ""),
        executable=True,
    )
    if show_headless:
        print(f"headless_command: {headless}")
    started = _maybe_start_line_binary_file_service(
        start_file_service,
        prompt_start,
        line_input_fn,
        start_file_service_fn,
    )
    _print_file_service_note(started)
    _append_line_binary_event(
        cfg,
        append_event_fn,
        headless=headless,
        rec=rec,
        fetch_command=fetch_command,
        run_hint=run_hint,
        fetch_options=fetch_options,
        started=started,
    )
    return rec
