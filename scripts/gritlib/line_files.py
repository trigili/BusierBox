"""Line-console staged file rendering helpers."""

from pathlib import Path

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import print_staged_fetch_target_options, render_fetch_command
from gritlib.shell_utils import shquote
from gritlib.staged_files import stage_file


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
    print(f"  request_name={rec.get('request_name', '')}")
    print(f"  source_path={rec.get('source_path', '')}")
    print(f"  sha256={rec.get('sha256', '')}")
    print(f"  target fetch: {fetch_command}")
    fetch_options = print_staged_fetch_target_options(rec.get("request_name", ""), cfg)
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print(f"  file service: {'started' if started else 'not started'}")
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
