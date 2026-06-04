"""Line-console staged file rendering helpers."""

import hashlib
from pathlib import Path

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import (
    print_staged_fetch_target_options,
    render_fetch_command,
    render_file_service_command,
)
from gritlib.release_artifacts import release_context, release_nav_records, stage_release_selection
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged, stage_file, unstage_file


def parse_line_download_args(args):
    queue = False
    start_file_service = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--queue", "-q"}:
            queue = True
        elif lower in {"--start", "--start-service"}:
            start_file_service = True
        else:
            values.append(item)
    target_path = " ".join(values).strip()
    return target_path, queue, start_file_service


def parse_line_release_stage_args(args):
    start_file_service = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--start", "--start-service"}:
            start_file_service = True
        else:
            values.append(item)
    selector = " ".join(values).strip()
    return selector, start_file_service


def parse_line_binary_args(args):
    selector = ""
    request_name = ""
    start_file_service = False
    no_start = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--start", "--start-service"}:
            start_file_service = True
        elif lower in {"--no-start", "--no-start-service"}:
            no_start = True
        else:
            values.append(item)
    if start_file_service and no_start:
        raise ValueError("usage: serve-binary [--start|--no-start] [PATH] [NAME]")
    if values:
        selector = values[0]
    if len(values) >= 3 and values[1].lower() == "as":
        request_name = values[2]
    elif len(values) >= 2:
        request_name = values[1]
    return selector, request_name, start_file_service, no_start


def parse_line_file_args(args):
    start_file_service = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--start", "--start-service"}:
            start_file_service = True
        else:
            values.append(item)
    selector = values[0] if values else ""
    request_name = ""
    if len(values) >= 3 and values[1].lower() == "as":
        request_name = values[2]
    elif len(values) >= 2:
        request_name = values[1]
    return selector, request_name, start_file_service


def parse_line_fetch_args(args, queue_default=False):
    queue = bool(queue_default)
    start_file_service = False
    values = []
    for item in args:
        lower = item.lower()
        if lower in {"--queue", "-q"}:
            queue = True
        elif lower in {"--start", "--start-service"}:
            start_file_service = True
        else:
            values.append(item)
    if len(values) > 1:
        raise ValueError("usage: fetch [--queue] [--start] NAME")
    return (values[0] if values else ""), queue, start_file_service


def download_line_target(
    cfg,
    target_path,
    queue=False,
    start_file_service=False,
    target_id_fn=None,
    target_context_fn=None,
    queue_command_fn=None,
    start_file_service_fn=None,
    append_event_fn=None,
):
    path = str(target_path or "").strip()
    if not path:
        raise ValueError("usage: download [--queue] [--start] TARGET_PATH")
    target_id = target_id_fn() if target_id_fn else ""
    if not target_id:
        raise ValueError("select an agent before download; use agent NAME or use target ID")
    command = render_file_service_command(["put", path], cfg)
    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --target-id "
        + shquote(target_id)
        + " --run-target-workflow-action "
        + shquote(f"{target_id}:show-upload-command")
        + " --target-workflow-command "
        + shquote(path)
    )
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print("Target download command:")
    print(f"  target: {target_id}")
    target_ctx = target_context_fn() if target_context_fn else {}
    label = str((target_ctx or {}).get("target_label") or "")
    if label:
        print(f"  label: {label}")
    print(f"  target path: {path}")
    print(f"  target command: {command}")
    print(f"  service: file-service {'started' if started else 'not started'}")
    queued = {}
    if queue:
        if not queue_command_fn:
            raise ValueError("queue support is unavailable")
        queued = queue_command_fn(cfg, command, metadata={
            "work_kind": "target-upload",
            "workflow": "file-service",
            "target_upload_path": path,
            "route_kind": "bridge" if cfg.get("bridge_profile") else "direct",
            "bridge_profile": str(cfg.get("bridge_profile") or ""),
        })
        print(f"queued {queued['id']}: {queued['command']}")
        queued_target = queued.get("target_id", "")
        queued_label = queued.get("target_label", "")
        if queued_label:
            queued_target = f"{queued_target} ({queued_label})"
        print(f"target: {queued_target}")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_target_download_command_shown", details={
            "headless_command": headless,
            "target_id": target_id,
            "target_label": label,
            "target_upload_path": path,
            "target_command": command,
            "target_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else "",
            "queued": bool(queue),
            "command_id": queued.get("id", "") if queued else "",
            "started_file_service": started,
        })
    return command


def line_file_size_text(rec):
    try:
        size = int(rec.get("size") or 0)
        if size == 0:
            return "-"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size // 1024} KB"
        return f"{size / (1024 * 1024):.1f} MB"
    except (TypeError, ValueError):
        return str(rec.get("size") or "-")


def line_file_target_text(rec):
    label = rec.get("target_label") or rec.get("target_id") or ""
    return label or "-"


def line_file_records_from_staged(staged, target_filter_id=""):
    staged = staged if isinstance(staged, dict) else {}
    target_filter_id = str(target_filter_id or "")
    if target_filter_id:
        staged = {
            name: rec for name, rec in staged.items()
            if isinstance(rec, dict) and str(rec.get("target_id") or "") == target_filter_id
        }
    return [{"_name": name, **rec} for name, rec in sorted(staged.items())]


def print_line_file_records(records, verbose=False, fetch_command=None, quote=None):
    records = list(records or [])
    fetch_command = fetch_command or (lambda _name: "")
    quote = quote or (lambda text: str(text))

    def _detail(rec):
        name = rec["_name"]
        details = [("next", f"fetch {quote(name)}")]
        if verbose:
            command = fetch_command(name)
            if command:
                details.append(("target command", command))
            if rec.get("source_path"):
                details.append(("source", rec["source_path"]))
            sha = str(rec.get("sha256") or "")
            if sha:
                details.append(("sha256", sha[:16] + "..."))
            if rec.get("release_path"):
                details.append(("release", rec["release_path"]))
            if rec.get("tuple_path"):
                details.append(("tuple", rec["tuple_path"]))
            compat = (rec.get("compatibility") or {}).get("label") or ""
            if compat:
                details.append(("compat", compat))
        return details

    has_targets = any(rec.get("target_id") for rec in records)
    cols = [
        ("Name", "_name"),
        ("Kind", lambda r: r.get("stage_kind") or "file"),
        ("Size", line_file_size_text),
    ]
    if has_targets:
        cols.append(("Target", line_file_target_text))

    console_table(
        f"Files  ({len(records)} staged)" if records else "Files  (none staged)",
        records, cols, detail_fn=_detail,
        footer="fetch NAME  |  upload LOCAL  |  unstage NAME  |  files ? for help",
    )
    return [
        {
            "kind": "staged-file",
            "label": f"{record['_name']} kind={record.get('stage_kind', 'file')}",
            "rec": record,
            "command": fetch_command(record["_name"]),
            "use_hint": f"fetch {quote(record['_name'])}",
        }
        for record in records
    ]


def stage_line_file(
    cfg,
    path_text="",
    request_name="",
    start_file_service=False,
    start_file_service_fn=None,
    append_event_fn=None,
):
    path = str(path_text or "").strip()
    if not path:
        raise ValueError("usage: upload [--start] LOCAL [NAME]")
    name = str(request_name or "").strip() or Path(path).name
    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --serve-file "
        + shquote(path)
        + " --as "
        + shquote(name)
        + " --list-staged"
    )
    rec = stage_file(cfg, path, name, metadata={"stage_kind": "operator-upload"})
    fetch_command = render_fetch_command(rec["request_name"], cfg)
    print("File staged for target fetch:")
    print(f"  name: {rec.get('request_name', '')}")
    print(f"  source: {rec.get('source_path', '')}")
    print(f"  sha256: {str(rec.get('sha256', ''))[:16]}...")
    print(f"  target fetch: {fetch_command}")
    fetch_options = print_staged_fetch_target_options(rec.get("request_name", ""), cfg)
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print(f"  service: file-service {'started' if started else 'not started'}")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_file_uploaded", details={
            "headless_command": headless,
            "request_name": rec.get("request_name", ""),
            "source_path": rec.get("source_path", ""),
            "sha256": rec.get("sha256", ""),
            "fetch_command": fetch_command,
            "fetch_options": fetch_options,
            "started_file_service": started,
            "stage_kind": rec.get("stage_kind", ""),
            "target_id": rec.get("target_id", ""),
            "target_label": rec.get("target_label", ""),
        })
    return rec


def staged_line_record(cfg, request_name):
    name = str(request_name or "").strip()
    if not name:
        return "", {}
    staged = load_staged(cfg).get("staged") or {}
    if name in staged and isinstance(staged.get(name), dict):
        return name, staged[name]
    if name.isdigit():
        names = sorted(str(item or "") for item in staged.keys() if str(item or ""))
        idx = int(name) - 1
        if 0 <= idx < len(names):
            selected = names[idx]
            rec = staged.get(selected) or {}
            return selected, rec if isinstance(rec, dict) else {}
    return name, {}


def unstage_line_file(cfg, request_name, append_event_fn=None):
    name = str(request_name or "").strip()
    if not name:
        raise ValueError("usage: unstage NAME")
    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --unstage "
        + shquote(name)
        + " --list-staged"
    )
    existed = unstage_file(cfg, name)
    print(f"unstaged {name}" if existed else f"not staged {name}")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_file_unstaged", details={
            "headless_command": headless,
            "request_name": name,
            "existed": existed,
        })
    return existed


def fetch_line_staged(
    cfg,
    request_name,
    queue=False,
    start_file_service=False,
    target_id_fn=None,
    target_context_fn=None,
    scoped_target_cfg_fn=None,
    queue_command_fn=None,
    start_file_service_fn=None,
    append_event_fn=None,
):
    name, rec = staged_line_record(cfg, request_name)
    if not name:
        raise ValueError("usage: fetch [--queue] [--start] NAME")
    if not rec:
        raise ValueError(f"staged request not found: {name}")
    target_id = target_id_fn() if target_id_fn else ""
    if queue and not target_id:
        raise ValueError("select an agent before fetch --queue; use agent NAME or use target ID")
    staged_target = str(rec.get("target_id") or "")
    if queue and staged_target and staged_target != target_id:
        raise ValueError(f"staged request target mismatch: expected {target_id}, got {staged_target}")
    target_ctx = target_context_fn() if target_context_fn else {}
    target_label = str((target_ctx or {}).get("target_label") or "")
    scoped = (
        scoped_target_cfg_fn(target_id, target_label=target_label)
        if target_id and scoped_target_cfg_fn else cfg
    )
    fetch_command = render_fetch_command(name, scoped)
    if target_id:
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --target-id "
            + shquote(target_id)
            + " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name "
            + shquote(name)
        )
    else:
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --run-staged-file-workflow-action "
            + shquote(f"{name}:show-fetch-command")
        )
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print("Staged fetch command:")
    print(f"  name: {name}")
    print(f"  source: {rec.get('source_path', '')}")
    if target_id:
        target_text = target_id
        if target_label:
            target_text += f" ({target_label})"
        print(f"  target: {target_text}")
    print(f"  target fetch: {fetch_command}")
    print_staged_fetch_target_options(name, scoped)
    print(f"  service: file-service {'started' if started else 'not started'}")
    queued = {}
    if queue:
        if not queue_command_fn:
            raise ValueError("queue support is unavailable")
        queued = queue_command_fn(scoped, fetch_command, metadata={
            "work_kind": "staged-fetch",
            "workflow": "file-service",
            "request_name": name,
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
        })
        print(f"queued {queued['id']}: {queued['command']}")
        queued_target = queued.get("target_id", "")
        queued_label = queued.get("target_label", "")
        if queued_label:
            queued_target = f"{queued_target} ({queued_label})"
        print(f"target: {queued_target}")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_staged_fetch_command_shown", details={
            "headless_command": headless,
            "request_name": name,
            "source_path": str(rec.get("source_path") or ""),
            "target_id": target_id,
            "target_label": target_label,
            "target_command": fetch_command,
            "target_command_sha256": hashlib.sha256(fetch_command.encode("utf-8")).hexdigest() if fetch_command else "",
            "queued": bool(queue),
            "command_id": queued.get("id", "") if queued else "",
            "started_file_service": started,
        })
    return fetch_command


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
    if rel and prompt_for_missing:
        nav = release_nav_records(rel, rel.get("devices") or [], rel.get("tuples") or [], limit=6)
        print("Release binary choices:")
        for idx, item in enumerate(nav, 1):
            print(f"  {idx}: {item.get('label', '')}")
    default_path = "dist/grit-native-full"
    if not selector and prompt_for_missing:
        selector_line = line_input_fn(f"binary path or release selector [{default_path}]> ") if line_input_fn else None
        selector = selector_line.strip() if selector_line is not None and selector_line.strip() else default_path
    selector = selector or default_path
    if not request_name and prompt_for_missing:
        name_line = line_input_fn("target request name [grit]> ") if line_input_fn else None
        request_name = name_line.strip() if name_line is not None and name_line.strip() else "grit"
    request_name = request_name or "grit"
    source_path = Path(selector).expanduser()
    if source_path.is_file():
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --serve-file "
            + shquote(str(source_path))
            + " --as "
            + shquote(request_name)
            + " --list-staged"
        )
        rec = stage_file(cfg, str(source_path), request_name, metadata={"stage_kind": "operator-binary"})
    else:
        if not rel:
            raise ValueError(f"binary path does not exist and no release bundle is available: {selector}")
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --stage-release-artifact "
            + shquote(selector)
            + " --list-staged"
        )
        rec = stage_release_selection(cfg, selector)
        request_name = rec.get("request_name", request_name)
    fetch_command = render_fetch_command(rec["request_name"], cfg)
    run_name = "./" + Path(rec["request_name"]).name
    run_hint = "chmod +x " + shquote(run_name) + " && " + shquote(run_name) + " --help"
    print("griTTYkit binary staged for target fetch:")
    print(f"  name: {rec.get('request_name', '')}")
    print(f"  source: {rec.get('source_path', '')}")
    print(f"  sha256: {str(rec.get('sha256', ''))[:16]}...")
    print(f"  target fetch: {fetch_command}")
    print(f"  run hint: {run_hint}")
    fetch_options = print_staged_fetch_target_options(
        rec.get("request_name", ""),
        cfg,
        output_name=rec.get("request_name", ""),
        executable=True,
    )
    if show_headless:
        print(f"headless_command: {headless}")
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    elif prompt_start:
        start_line = line_input_fn("start file-service now? [y/N]> ") if line_input_fn else None
        started = start_line is not None and start_line.strip().lower() in ("y", "yes")
        if started and start_file_service_fn:
            start_file_service_fn()
    print(f"  service: file-service {'started' if started else 'not started'}")
    if append_event_fn:
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
    return rec
