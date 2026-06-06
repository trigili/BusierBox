"""Line-console service display and selector helpers."""

from gritlib.console_display import console_display_mode, console_table
from gritlib.event_log import append_event
from gritlib.line_context import set_line_collection_context
from gritlib.line_search import set_line_search_results


LINE_SERVICE_CATEGORIES = [
    ("Probe & discovery", ["probe", "probe-tftp", "probe-ftp", "probe-dns", "bridge"]),
    ("Initial access", ["ssh", "tls-shell", "plain-shell"]),
    ("Post-deployment", ["file-service", "command-queue"]),
]

LINE_SERVICE_DISPLAY_NAMES = {
    "probe": "probe-http",
}

LINE_SERVICE_ALIASES = {
    "probe-http": "probe",
    "http-probe": "probe",
    "ftp-probe": "probe-ftp",
    "dns-probe": "probe-dns",
}


LINE_LISTENER_COMMANDS = (
    {"action": "list", "commands": ("services", "listeners")},
    {"action": "select", "commands": ("listener",)},
)

LINE_SERVICE_CONTROL_COMMANDS = (
    {"action": "start", "commands": ("start",)},
    {"action": "stop", "commands": ("stop",)},
)


def line_listener_command_records():
    return [
        {
            "family": "listener",
            "action": rec["action"],
            "commands": list(rec["commands"]),
            "primary": rec["commands"][0],
            "aliases": list(rec["commands"][1:]),
        }
        for rec in LINE_LISTENER_COMMANDS
    ]


def line_service_control_command_records():
    return [
        {
            "family": "service-control",
            "action": rec["action"],
            "commands": list(rec["commands"]),
            "primary": rec["commands"][0],
            "aliases": list(rec["commands"][1:]),
        }
        for rec in LINE_SERVICE_CONTROL_COMMANDS
    ]


def parse_line_listener_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    for rec in line_listener_command_records():
        if cmd not in rec["commands"]:
            continue
        if rec["action"] == "list":
            return {
                "action": "list",
                "verbose": any(str(item).lower() in {"-v", "--verbose"} for item in args),
                "command": cmd,
            }
        if args and str(args[0]).lower() in {"-v", "--verbose"}:
            return {"action": "list", "verbose": True, "command": cmd}
        selector = " ".join(args).strip()
        return {
            "action": "select" if selector else "list",
            "selector": selector,
            "verbose": False,
            "command": cmd,
        }
    return {}


def dispatch_line_listener_command(
    listener_cmd,
    *,
    list_func=None,
    select_func=None,
):
    action = (listener_cmd or {}).get("action")
    try:
        if action == "list" and list_func:
            return list_func(verbose=bool(listener_cmd.get("verbose")))
        if action == "select" and select_func:
            return select_func(listener_cmd.get("selector", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported listener command")


def parse_line_service_control_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    for rec in line_service_control_command_records():
        if cmd in rec["commands"]:
            return {
                "action": rec["action"],
                "selector": " ".join(args or []).strip(),
                "command": cmd,
            }
    return {}


def dispatch_line_service_control_command(
    service_cmd,
    *,
    start_func=None,
    stop_func=None,
):
    action = (service_cmd or {}).get("action")
    try:
        if action == "start" and start_func:
            return start_func(service_cmd.get("selector", ""))
        if action == "stop" and stop_func:
            return stop_func(service_cmd.get("selector", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported service control command")


def dispatch_legacy_line_service_number(
    choice,
    *,
    input_func=None,
    start_func=None,
    stop_func=None,
    service_rows_func=None,
    service_record_func=None,
    sleep_func=None,
):
    text = str(choice or "").strip()
    if text in {"1", "2", "3", "4"}:
        service = {"1": "ssh", "2": "tls-shell", "3": "plain-shell", "4": "file-service"}[text]
        if start_func:
            start_func(service)
        service_rows_func = service_rows_func or (lambda: [])
        service_record_func = service_record_func or line_service_record
        for _ in range(10):
            if sleep_func:
                sleep_func(0.1)
            rec = service_record_func(service_rows_func(), service) or {}
            if str(rec.get("actual") or "") == "listening":
                break
        return True
    if text == "5":
        service = input_func("service> ") if input_func else None
        if service is not None and stop_func:
            stop_func(service.strip())
        return True
    return False


def line_service_display_name(name):
    text = str(name or "").strip()
    return LINE_SERVICE_DISPLAY_NAMES.get(text, text)


def ordered_line_service_records(rows):
    order = {name: i for i, name in enumerate(
        s for _, names in LINE_SERVICE_CATEGORIES for s in names
    )}
    return sorted(rows or [], key=lambda r: order.get(str(r.get("name") or ""), 99))


def resolve_line_service_selector(selector, rows):
    text = str(selector or "").strip()
    if not text:
        return ""
    text = LINE_SERVICE_ALIASES.get(text, text)
    records = ordered_line_service_records(rows)
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"service number out of range: {text}")
        return str(records[idx].get("name") or "")
    names = [str(rec.get("name") or "") for rec in records]
    if text in names:
        return text
    display_names = {
        line_service_display_name(str(rec.get("name") or "")): str(rec.get("name") or "")
        for rec in records
    }
    if text in display_names:
        return display_names[text]
    return ""


def line_service_names(rows):
    return [
        str(rec.get("name") or "")
        for rec in ordered_line_service_records(rows)
        if str(rec.get("name") or "")
    ]


def line_service_completion_names(rows):
    names = line_service_names(rows)
    displayed = [line_service_display_name(name) for name in names]
    return list(dict.fromkeys(displayed + names))


def line_service_record(rows, name):
    text = str(name or "").strip()
    for rec in rows or []:
        if str(rec.get("name") or "") == text:
            return rec
    return {}


def line_service_selector_from_context(cfg, service, route_start=None, route_stop=None, op="start"):
    service = str(service or "").strip()
    if service:
        return service
    module = str((cfg or {}).get("_line_console_module") or "")
    if module.startswith(("listener/", "service/")):
        return module.split("/", 1)[1]
    if module.startswith("route/"):
        route_name = module.split("/", 1)[1]
        if op == "stop" and route_stop:
            return route_stop(route_name)
        if route_start:
            return route_start(route_name)
    return ""


def start_line_service(
    cfg,
    service,
    *,
    service_rows_func=None,
    route_record_func=None,
    route_start_func=None,
    service_start_command_func=None,
    service_start_func=None,
    probe_delivery_func=None,
    sleep_func=None,
):
    service = line_service_selector_from_context(
        cfg, service, route_start=route_start_func, op="start",
    )
    if service is None:
        return None
    service = str(service or "").strip()
    if service.lower().startswith("route ") and route_start_func:
        return route_start_func(service.split(None, 1)[1])
    if not service:
        raise ValueError("usage: start SERVICE|ROUTE")
    service_rows_func = service_rows_func or (lambda: [])
    resolved_service = resolve_line_service_selector(service, service_rows_func())
    if resolved_service:
        service = resolved_service
    if service not in line_service_names(service_rows_func()):
        if route_record_func and route_record_func(service):
            if route_start_func:
                return route_start_func(service)
        raise ValueError(f"service or route not found: {service}")
    if not service_start_command_func or not service_start_func:
        raise ValueError("service start support is unavailable")
    headless = service_start_command_func(service)
    cfg["_service_start_command"] = headless
    service_start_func(cfg, service, headless_command=headless)
    print("  copy start  — copy the start command")
    if service in {"probe", "probe-tftp", "probe-ftp", "probe-dns"} and probe_delivery_func:
        for _ in range(10):
            if sleep_func:
                sleep_func(0.1)
            if str((line_service_record(service_rows_func(), service) or {}).get("actual") or "") == "listening":
                break
        probe_delivery_func()
    return service


def stop_line_service(
    cfg,
    service,
    *,
    service_rows_func=None,
    route_record_func=None,
    route_stop_func=None,
    service_stop_command_func=None,
    service_stop_func=None,
):
    service = line_service_selector_from_context(
        cfg, service, route_stop=route_stop_func, op="stop",
    )
    if service is None:
        return None
    service = str(service or "").strip()
    if service.lower().startswith("route ") and route_stop_func:
        return route_stop_func(service.split(None, 1)[1])
    if not service:
        raise ValueError("usage: stop SERVICE|ROUTE")
    service_rows_func = service_rows_func or (lambda: [])
    resolved_service = resolve_line_service_selector(service, service_rows_func())
    if resolved_service:
        service = resolved_service
    if service not in line_service_names(service_rows_func()):
        if route_record_func and route_record_func(service):
            if route_stop_func:
                return route_stop_func(service)
        raise ValueError(f"service or route not found: {service}")
    if not service_stop_command_func or not service_stop_func:
        raise ValueError("service stop support is unavailable")
    headless = service_stop_command_func(service)
    cfg["_service_stop_command"] = headless
    service_stop_func(cfg, service, headless_command=headless)
    return service


def line_service_bind_text(rec):
    host = rec.get("bind_address") or ""
    port = rec.get("port") or "-"
    proto = str(rec.get("protocol") or "tcp").upper()
    bind = f"{host}:{port}" if host else str(port)
    return f"{bind}/{proto}" if proto != "TCP" else bind


def line_service_status_text(rec):
    actual = rec.get("actual") or "-"
    configured = rec.get("configured") or "-"
    if actual == configured or configured in {"-", "unknown"}:
        return actual
    return f"{actual} (configured {configured})"


def _line_service_detail_rows(rec, verbose, start_command, stop_command):
    if not verbose:
        return []
    name = str(rec.get("name") or "")
    details = [
        ("start", start_command(name)),
        ("stop", stop_command(name)),
    ]
    if rec.get("error"):
        details.append(("error", rec["error"]))
    if rec.get("session_log"):
        details.append(("log", rec["session_log"]))
    return details


def _line_service_columns():
    return [
        ("Service", "name"),
        ("Status", line_service_status_text),
        ("Bind", line_service_bind_text),
        ("TLS", lambda r: "yes" if r.get("tls") else "no"),
        ("PID", lambda r: str(r.get("pid") or "-")),
    ]


def _line_service_compact_columns():
    return [
        ("Service", lambda r: line_service_display_name(str(r.get("name") or ""))),
        ("Status", line_service_status_text),
        ("Bind", line_service_bind_text),
        ("TLS", lambda r: "yes" if r.get("tls") else "no"),
    ]


def _line_service_cells(rec):
    return [
        line_service_display_name(str(rec.get("name") or "")),
        line_service_status_text(rec),
        line_service_bind_text(rec),
        "yes" if rec.get("tls") else "no",
        str(rec.get("pid") or "-"),
    ]


def _line_service_widths(rows, cols):
    return [
        max(
            len(header),
            max((len(_line_service_cells(row)[idx]) for row in rows), default=0),
        )
        for idx, (header, _key) in enumerate(cols)
    ]


def _line_service_row_line(num, rec, num_w, widths):
    cells = _line_service_cells(rec)
    return (f"  {num:{num_w}}  " + "  ".join(f"{cell:{widths[idx]}}" for idx, cell in enumerate(cells))).rstrip()


def _print_line_service_category_rows(rows, verbose, detail_fn, row_line_fn, num, num_w):
    for rec in rows:
        print(row_line_fn(num, rec))
        if verbose:
            indent = " " * (2 + num_w + 2)
            for label, value in (detail_fn(rec) or []):
                if value:
                    print(f"{indent}{label}: {value}")
        num += 1
    return num


def _print_line_service_table(rows, verbose, detail_fn):
    if console_display_mode() != "normal":
        console_table(
            f"Listeners  ({len(rows)} total)" if rows else "Listeners  (none)",
            rows,
            _line_service_compact_columns(),
            detail_fn=detail_fn if verbose else None,
        )
        return
    cols = _line_service_columns()
    by_name = {str(row.get("name") or ""): row for row in rows}
    num_w = len(str(len(rows)))
    widths = _line_service_widths(rows, cols)
    row_line_fn = lambda num, rec: _line_service_row_line(num, rec, num_w, widths)
    header = "  " + " " * num_w + "  " + "  ".join(f"{head:{widths[idx]}}" for idx, (head, _key) in enumerate(cols))
    sep = "  " + "─" * num_w + "  " + "  ".join("─" * width for width in widths)

    if not rows:
        print("Listeners  (none)")
        return

    print(f"Listeners  ({len(rows)} total)")
    print("")
    print(header)
    print(sep)
    num = 1
    cat_all = {name for _title, names in LINE_SERVICE_CATEGORIES for name in names}
    printed_any = False
    for cat_title, cat_names in LINE_SERVICE_CATEGORIES:
        cat_rows = [by_name[name] for name in cat_names if name in by_name]
        if not cat_rows:
            continue
        if printed_any:
            print("")
        print(f"  {cat_title}")
        num = _print_line_service_category_rows(cat_rows, verbose, detail_fn, row_line_fn, num, num_w)
        printed_any = True
    extras = [row for row in rows if str(row.get("name") or "") not in cat_all]
    if extras:
        if printed_any:
            print("")
        print("  Other")
        _print_line_service_category_rows(extras, False, detail_fn, row_line_fn, num, num_w)


def _line_service_search_records(rows, start_command, quote):
    return [
        {
            "kind": "service",
            "label": (
                f"{line_service_display_name(str(rec.get('name') or ''))} "
                f"status {line_service_status_text(rec)}  bind {line_service_bind_text(rec)}"
            ),
            "rec": rec,
            "command": start_command(str(rec.get("name") or "")),
            "use_hint": f"use listener {quote(line_service_display_name(str(rec.get('name') or '')))}",
        }
        for rec in rows
    ]


def print_line_service_records(rows, verbose=False, start_command=None, stop_command=None, quote=None):
    rows = list(rows or [])
    start_command = start_command or (lambda _name: "")
    stop_command = stop_command or (lambda _name: "")
    quote = quote or (lambda text: str(text))
    detail_fn = lambda rec: _line_service_detail_rows(rec, verbose, start_command, stop_command)
    _print_line_service_table(rows, verbose, detail_fn)
    print("")
    print("  use N or listener NAME to select  |  start/stop N or NAME  |  listeners ? for help")
    return _line_service_search_records(rows, start_command, quote)


def select_line_service(cfg, selector, rows, start_command=None, stop_command=None):
    text = str(selector or "").strip()
    service = resolve_line_service_selector(text, rows)
    if not service:
        raise ValueError(f"service not found: {text}")
    set_line_collection_context(cfg, f"listener/{service}")
    start_command = start_command or (lambda _name: "")
    stop_command = stop_command or (lambda _name: "")
    cfg["_service_start_command"] = start_command(service)
    cfg["_service_stop_command"] = stop_command(service)
    rec = line_service_record(rows, service)
    if rec:
        actual = rec.get("actual") or "?"
        port = rec.get("port") or "-"
        tls = "TLS: yes" if rec.get("tls") else "TLS: no"
        pid = rec.get("pid")
        pid_str = f"  |  pid {pid}" if pid else ""
        if console_display_mode() != "normal":
            print(f"  {line_service_display_name(service)}  —  {actual}  |  :{port}  |  {tls}")
        else:
            print(f"  {line_service_display_name(service)}  —  {actual}  |  :{port}  |  {tls}{pid_str}")
        if line_service_display_name(service) != service:
            print(f"  transport: {service}")
    else:
        print(f"  {line_service_display_name(service)}  —  (no status)")
    if console_display_mode() != "normal":
        print("  next: options | start | stop | back")
    else:
        print("  options / info / start / stop / copy start / back")
    return service


def print_line_services(
    cfg, rows, verbose=False, start_command=None, stop_command=None, quote=None
):
    rows = ordered_line_service_records(rows)
    search_records = print_line_service_records(
        rows,
        verbose=verbose,
        start_command=start_command,
        stop_command=stop_command,
        quote=quote,
    )
    set_line_search_results(cfg, search_records)
    append_event(cfg, "workbench", "workbench_listeners_listed", details={
        "listener_count": len(rows),
        "verbose": bool(verbose),
    })
    return rows
