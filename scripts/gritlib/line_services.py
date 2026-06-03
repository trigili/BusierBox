"""Line-console service display and selector helpers."""


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


def line_service_bind_text(rec):
    host = rec.get("bind_address") or ""
    port = rec.get("port") or "-"
    proto = str(rec.get("protocol") or "tcp").upper()
    bind = f"{host}:{port}" if host else str(port)
    return f"{bind}/{proto}" if proto != "TCP" else bind


def line_service_status_text(rec):
    actual = rec.get("actual") or "-"
    configured = rec.get("configured") or "-"
    if actual == configured:
        return actual
    return f"{actual} (want {configured})"


def print_line_service_records(rows, verbose=False, start_command=None, stop_command=None, quote=None):
    rows = list(rows or [])
    start_command = start_command or (lambda _name: "")
    stop_command = stop_command or (lambda _name: "")
    quote = quote or (lambda text: str(text))

    def _detail(rec):
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

    cols = [
        ("Service", "name"),
        ("Status", line_service_status_text),
        ("Bind", line_service_bind_text),
        ("TLS", lambda r: "yes" if r.get("tls") else "no"),
        ("PID", lambda r: str(r.get("pid") or "-")),
    ]

    by_name = {str(row.get("name") or ""): row for row in rows}
    num_w = len(str(len(rows)))
    widths = [max(len(header), max((len(cell) for row in rows for cell in [
        [
            line_service_display_name(str(row.get("name") or "")),
            line_service_status_text(row),
            line_service_bind_text(row),
            "yes" if row.get("tls") else "no",
            str(row.get("pid") or "-"),
        ][idx]
    ]), default=0)) for idx, (header, _key) in enumerate(cols)]

    def _row_line(num, rec):
        cells = [
            line_service_display_name(str(rec.get("name") or "")),
            line_service_status_text(rec),
            line_service_bind_text(rec),
            "yes" if rec.get("tls") else "no",
            str(rec.get("pid") or "-"),
        ]
        return (f"  {num:{num_w}}  " + "  ".join(f"{cell:{widths[idx]}}" for idx, cell in enumerate(cells))).rstrip()

    header = "  " + " " * num_w + "  " + "  ".join(f"{head:{widths[idx]}}" for idx, (head, _key) in enumerate(cols))
    sep = "  " + "─" * num_w + "  " + "  ".join("─" * width for width in widths)

    if not rows:
        print("Listeners  (none)")
    else:
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
            for rec in cat_rows:
                print(_row_line(num, rec))
                if verbose:
                    indent = " " * (2 + num_w + 2)
                    for label, value in (_detail(rec) or []):
                        if value:
                            print(f"{indent}{label}: {value}")
                num += 1
            printed_any = True
        extras = [row for row in rows if str(row.get("name") or "") not in cat_all]
        if extras:
            if printed_any:
                print("")
            print("  Other")
            for rec in extras:
                print(_row_line(num, rec))
                num += 1
    print("")
    print("  use N or listener NAME to select  |  start/stop N or NAME  |  listeners ? for help")
    return [
        {
            "kind": "service",
            "label": (
                f"{line_service_display_name(str(rec.get('name') or ''))} "
                f"status={line_service_status_text(rec)} bind={line_service_bind_text(rec)}"
            ),
            "rec": rec,
            "command": start_command(str(rec.get("name") or "")),
            "use_hint": f"use listener {quote(line_service_display_name(str(rec.get('name') or '')))}",
        }
        for rec in rows
    ]
