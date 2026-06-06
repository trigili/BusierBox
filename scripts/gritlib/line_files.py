"""Line-console staged file rendering helpers."""

import hashlib
from pathlib import Path

from gritlib.console_display import console_display_mode, console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import (
    print_staged_fetch_target_options,
    render_fetch_command,
    render_file_service_command,
    staged_fetch_target_commands,
)
import gritlib.line_binary as line_binary_module
from gritlib.line_search import set_line_search_results
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged, stage_file, unstage_file


def print_file_service_note(started):
    print(f"  file service {'started' if started else 'not started'}")


def print_file_queue_note(queued):
    print(f"  queued: {queued.get('id', '')}")
    queued_target = queued.get("target_id", "")
    queued_label = queued.get("target_label", "")
    if queued_label:
        queued_target = f"{queued_target} ({queued_label})"
    if queued_target:
        print(f"  target: {queued_target}")


def parse_line_files_command(cmd, args=None, module=None):
    module = str(module or "").strip().lower()
    if args is None:
        args = cmd
    else:
        command = str(cmd or "").strip().lower()
        if module == "files" and command in {"clear", "purge"}:
            args = [command, *list(args or [])]
        elif command not in {"files", "staged", "stagers", "loot", "downloads"}:
            return {}
    args = list(args or [])
    subcmd = str(args[0]).lower() if args else ""
    rest = args[1:]
    if subcmd in {"upload", "stage", "serve-file"}:
        selector, request_name, start_service = parse_line_file_args(rest)
        return {
            "action": "upload",
            "selector": selector,
            "request_name": request_name,
            "start_service": start_service,
        }
    if subcmd in {"fetch", "deploy"}:
        request_name, queue_fetch, start_service = parse_line_fetch_args(rest)
        return {
            "action": "fetch",
            "request_name": request_name,
            "queue": queue_fetch,
            "start_service": start_service,
        }
    if subcmd in {"unstage", "rm", "remove"}:
        return {"action": "unstage", "selector": " ".join(rest).strip()}
    if subcmd in {"clear", "purge"}:
        flags = {str(item).lower() for item in rest}
        return {
            "action": "clear",
            "confirm": "--confirm" in flags,
            "prompt": "--confirm" not in flags,
        }
    if subcmd in {"-v", "--verbose"}:
        return {"action": "list", "verbose": True}
    return {"action": "list", "verbose": False}


def parse_line_file_transfer_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd in {"upload", "stage", "serve-file"}:
        selector, request_name, start_service = parse_line_file_args(args)
        return {
            "action": "upload",
            "selector": selector,
            "request_name": request_name,
            "start_service": start_service,
        }
    if cmd in {"fetch", "deploy", "queue-fetch"}:
        request_name, queue_fetch, start_service = parse_line_fetch_args(
            args,
            queue_default=cmd == "queue-fetch",
        )
        return {
            "action": "fetch",
            "request_name": request_name,
            "queue": queue_fetch,
            "start_service": start_service,
        }
    if cmd in {"unstage", "rmfile", "rm-file"}:
        return {"action": "unstage", "selector": " ".join(args).strip()}
    return {}


def dispatch_line_file_command(
    file_cmd,
    *,
    upload_func=None,
    fetch_func=None,
    unstage_func=None,
    clear_func=None,
    list_func=None,
    set_context_func=None,
):
    try:
        action = (file_cmd or {}).get("action")
        if action == "upload" and upload_func:
            result = upload_func(
                file_cmd["selector"],
                file_cmd["request_name"],
                start_file_service=file_cmd["start_service"],
            )
        elif action == "fetch" and fetch_func:
            result = fetch_func(
                file_cmd["request_name"],
                queue=file_cmd["queue"],
                start_file_service=file_cmd["start_service"],
            )
        elif action == "unstage" and unstage_func:
            result = unstage_func(file_cmd["selector"])
        elif action == "clear" and clear_func:
            result = clear_func(
                confirm=file_cmd["confirm"],
                prompt=bool(file_cmd.get("prompt")),
            )
        elif action == "list" and list_func:
            result = list_func(verbose=file_cmd["verbose"])
        else:
            raise ValueError("unsupported file command")
        if set_context_func:
            set_context_func()
        return result
    except ValueError as exc:
        print(exc)
        return None


def dispatch_legacy_line_file_number(
    choice,
    cfg,
    *,
    input_func=None,
    append_event_fn=None,
    print_staged_func=None,
    snapshot_func=None,
    view_path_func=None,
    stage_binary_func=None,
):
    text = str(choice or "").strip()
    if text == "6":
        return _dispatch_legacy_stage_file(cfg, input_func, append_event_fn)
    if text == "7":
        return _dispatch_legacy_view_staged_files(
            cfg,
            append_event_fn=append_event_fn,
            print_staged_func=print_staged_func,
            snapshot_func=snapshot_func,
        )
    if text in {"8", "d"}:
        return _dispatch_legacy_unstage_file(cfg, input_func, append_event_fn)
    if text in {"9", "v"}:
        return _dispatch_legacy_view_path(
            cfg,
            input_func=input_func,
            append_event_fn=append_event_fn,
            view_path_func=view_path_func,
        )
    if text == "22":
        return _dispatch_legacy_stage_binary(stage_binary_func)
    return False


def _legacy_file_headless_config(cfg):
    return "scripts/grit-console --config " + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))


def _dispatch_legacy_stage_file(cfg, input_func, append_event_fn):
    path_line = input_func("local file> ") if input_func else None
    name_line = input_func("target request name> ") if input_func else None
    path = path_line.strip() if path_line is not None else ""
    name = name_line.strip() if name_line is not None else ""
    try:
        headless = (
            _legacy_file_headless_config(cfg)
            + " --serve-file "
            + shquote(path)
            + " --as "
            + shquote(name)
            + " --list-staged"
        )
        rec = stage_file(cfg, path, name)
        print(f"staged {rec['request_name']}")
        print(render_fetch_command(rec["request_name"], cfg))
        if append_event_fn:
            append_event_fn(cfg, "workbench", "workbench_file_staged", details={
                "headless_command": headless,
                "request_name": rec.get("request_name", ""),
                "source_path": rec.get("source_path", ""),
                "stage_kind": rec.get("stage_kind", ""),
                "target_id": rec.get("target_id", ""),
                "target_label": rec.get("target_label", ""),
            })
    except ValueError as exc:
        print(exc)
    return True


def _print_legacy_file_service_actions(file_actions):
    if not file_actions:
        return
    print("File service workflow actions:")
    for rec in file_actions:
        print(
            f"  {rec.get('id', '')} "
            f"state={rec.get('operator_action_state', '') or '-'} "
            f"reason={rec.get('operator_action_reason', '') or '-'} "
            f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'} "
            f"fleet_targets={rec.get('fleet_target_count', 0)} "
            f"pending_work={rec.get('fleet_mailbox_pending_work_count', 0)} "
            f"offline_targets={rec.get('fleet_offline_target_count', 0)} "
            f"poll_overdue={rec.get('fleet_poll_overdue_target_count', 0)}"
        )
        if rec.get("target_command_template"):
            print(f"    target_command_template: {rec.get('target_command_template', '')}")


def _print_legacy_staged_file_actions(staged_actions):
    if not staged_actions:
        return
    print("Staged file workflow actions:")
    for rec in staged_actions:
        print(
            f"  {rec.get('id', '')} "
            f"state={rec.get('operator_action_state', '') or '-'} "
            f"reason={rec.get('operator_action_reason', '') or '-'} "
            f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'} "
            f"target_pending={rec.get('target_mailbox_pending_work_count', 0)} "
            f"fleet_pending={rec.get('fleet_mailbox_pending_work_count', 0)} "
            f"poll_overdue={'yes' if rec.get('target_poll_overdue') else 'no'}"
        )


def _dispatch_legacy_view_staged_files(
    cfg,
    *,
    append_event_fn=None,
    print_staged_func=None,
    snapshot_func=None,
):
    if print_staged_func:
        print_staged_func(cfg)
    snap = snapshot_func(cfg) if snapshot_func else {}
    file_actions = snap.get("file_service_workflow_actions") or []
    _print_legacy_file_service_actions(file_actions)
    staged_actions = snap.get("staged_file_workflow_actions") or []
    _print_legacy_staged_file_actions(staged_actions)
    headless = _legacy_file_headless_config(cfg) + " --list-staged"
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_staged_files_viewed", details={
            "headless_command": headless,
            "staged_count": len(snap.get("staged_records") or []),
            "file_service_workflow_action_count": len(file_actions),
            "staged_file_workflow_action_count": len(staged_actions),
        })
    return True


def _dispatch_legacy_unstage_file(cfg, input_func, append_event_fn):
    name_line = input_func("target request name> ") if input_func else None
    name = name_line.strip() if name_line is not None else ""
    if name:
        try:
            headless = (
                _legacy_file_headless_config(cfg)
                + " --unstage "
                + shquote(name)
                + " --list-staged"
            )
            existed = unstage_file(cfg, name)
            print("unstaged" if existed else "not staged")
            if append_event_fn:
                append_event_fn(cfg, "workbench", "workbench_file_unstaged", details={
                    "headless_command": headless,
                    "request_name": name,
                    "existed": existed,
                })
        except ValueError as exc:
            print(exc)
    return True


def _dispatch_legacy_view_path(
    cfg,
    *,
    input_func=None,
    append_event_fn=None,
    view_path_func=None,
):
    path_line = input_func("local path> ") if input_func else None
    path = path_line.strip() if path_line is not None else ""
    if path and view_path_func:
        view_path_func(cfg, path, append_event_fn=append_event_fn)
    return True


def _dispatch_legacy_stage_binary(stage_binary_func):
    try:
        if stage_binary_func:
            stage_binary_func()
    except ValueError as exc:
        print(exc)
    return True


def _confirm_line_files_clear(staged, input_func):
    count = len(staged or {})
    answer = str(
        input_func(f"\nRemove {count} staged file{'s' if count != 1 else ''}? [y/N] ")
        or ""
    ).strip().lower()
    return answer in {"y", "yes"}


def clear_line_files(
    cfg,
    confirm=False,
    prompt=False,
    target_filter_id="",
    input_func=input,
    append_event_fn=None,
):
    staged = load_staged(cfg).get("staged", {})
    target_filter_id = str(target_filter_id or "")
    if target_filter_id:
        staged = {
            name: rec for name, rec in staged.items()
            if str(rec.get("target_id") or "") == target_filter_id
        }
    if not staged:
        print("No staged files to clear.")
        return 0
    for name in sorted(staged):
        print(f"  {name}")
    if not confirm and prompt:
        if not _confirm_line_files_clear(staged, input_func):
            print("Cancelled.")
            return 0
    elif not confirm:
        print(f"\n  {len(staged)} file(s) would be unstaged.  Run: files clear")
        return 0
    removed = 0
    for name in list(staged):
        if unstage_file(cfg, name):
            removed += 1
    print(f"\n  Cleared {removed} staged file(s).")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_files_cleared", details={
            "removed": removed,
            "target_filter": target_filter_id or "all",
        })
    return removed


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


def parse_line_download_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() not in {"download", "get"}:
            return {}
    target_path, queue, start_service = parse_line_download_args(args)
    return {
        "action": "download",
        "target_path": target_path,
        "queue": queue,
        "start_service": start_service,
    }


def dispatch_line_download_command(
    download_cmd,
    *,
    download_func=None,
    set_context_func=None,
):
    try:
        if download_func:
            result = download_func(
                download_cmd.get("target_path", ""),
                queue=bool(download_cmd.get("queue")),
                start_file_service=bool(download_cmd.get("start_service")),
            )
            if set_context_func:
                set_context_func()
            return result
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported download command")


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


def parse_line_binary_command(cmd, args=None):
    return line_binary_module.parse_line_binary_command(cmd, args)


def dispatch_line_binary_command(
    binary_cmd,
    *,
    stage_binary_func=None,
    set_context_func=None,
):
    return line_binary_module.dispatch_line_binary_command(
        binary_cmd,
        stage_binary_func=stage_binary_func,
        set_context_func=set_context_func,
    )


def parse_line_binary_args(args):
    return line_binary_module.parse_line_binary_args(args)


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
    if console_display_mode() != "normal":
        print(f"  command: {command}")
    else:
        print(f"  target command: {command}")
    print_file_service_note(started)
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
        print_file_queue_note(queued)
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
                details.append(("fetch command", command))
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


def print_current_line_files(
    cfg,
    staged,
    target_filter_id="",
    verbose=False,
    fetch_command=None,
    quote=None,
    append_event_fn=None,
):
    records = line_file_records_from_staged(staged, target_filter_id)
    search_records = print_line_file_records(
        records,
        verbose=verbose,
        fetch_command=fetch_command,
        quote=quote,
    )
    set_line_search_results(cfg, search_records)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_files_listed", details={
            "staged_count": len(records),
            "verbose": bool(verbose),
        })
    return search_records


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
    print(f"  next: fetch {rec.get('request_name', '')}")
    if console_display_mode() != "normal":
        print(f"  queue: fetch --queue {rec.get('request_name', '')}")
    else:
        print("  fetch shows target-side commands; fetch --queue queues it for the selected agent")
    fetch_options = staged_fetch_target_commands(rec.get("request_name", ""), cfg)
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print_file_service_note(started)
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


def _line_staged_target_context(
    cfg,
    queue,
    rec,
    target_id_fn,
    target_context_fn,
    scoped_target_cfg_fn,
):
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
    return target_id, target_label, scoped


def _line_staged_fetch_headless(cfg, name, target_id):
    if target_id:
        return (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --target-id "
            + shquote(target_id)
            + " --run-target-workflow-action queue-staged-fetch --target-workflow-request-name "
            + shquote(name)
        )
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --run-staged-file-workflow-action "
        + shquote(f"{name}:show-fetch-command")
    )


def _start_line_file_service(start_file_service, start_file_service_fn):
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    return started


def _print_line_staged_fetch(name, rec, target_id, target_label, fetch_command, scoped, started):
    print("Staged fetch command:")
    print(f"  name: {name}")
    print(f"  source: {rec.get('source_path', '')}")
    if target_id:
        target_text = target_id
        if target_label:
            target_text += f" ({target_label})"
        print(f"  target: {target_text}")
    if console_display_mode() != "normal":
        print(f"  command: {fetch_command}")
    else:
        print(f"  target fetch: {fetch_command}")
    print_staged_fetch_target_options(name, scoped)
    print_file_service_note(started)


def _queue_line_staged_fetch(queue, queue_command_fn, scoped, fetch_command, name, rec):
    if not queue:
        return {}
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
    print_file_queue_note(queued)
    return queued


def _append_line_staged_fetch_event(
    cfg,
    append_event_fn,
    *,
    headless,
    name,
    rec,
    target_id,
    target_label,
    fetch_command,
    queue,
    queued,
    started,
):
    if not append_event_fn:
        return
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
    target_id, target_label, scoped = _line_staged_target_context(
        cfg,
        queue,
        rec,
        target_id_fn,
        target_context_fn,
        scoped_target_cfg_fn,
    )
    fetch_command = render_fetch_command(name, scoped)
    headless = _line_staged_fetch_headless(cfg, name, target_id)
    started = _start_line_file_service(start_file_service, start_file_service_fn)
    _print_line_staged_fetch(name, rec, target_id, target_label, fetch_command, scoped, started)
    queued = _queue_line_staged_fetch(queue, queue_command_fn, scoped, fetch_command, name, rec)
    _append_line_staged_fetch_event(
        cfg,
        append_event_fn,
        headless=headless,
        name=name,
        rec=rec,
        target_id=target_id,
        target_label=target_label,
        fetch_command=fetch_command,
        queue=queue,
        queued=queued,
        started=started,
    )
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
    return line_binary_module.stage_line_binary(
        cfg,
        selector=selector,
        request_name=request_name,
        prompt_for_missing=prompt_for_missing,
        prompt_start=prompt_start,
        start_file_service=start_file_service,
        show_headless=show_headless,
        line_input_fn=line_input_fn,
        start_file_service_fn=start_file_service_fn,
        append_event_fn=append_event_fn,
    )
