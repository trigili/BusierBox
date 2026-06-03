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
