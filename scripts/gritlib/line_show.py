"""Line-console show/module argument parsing helpers."""

import shlex


VERBOSE_FLAGS = {"-v", "--verbose", "verbose", "details"}
LINE_SHOW_USAGE = "usage: show targets|services|files|queue|mailbox|jobs|sessions|activity|modules|options"
SHOW_RESOURCE_ALIASES = {
    "targets": ("target", "targets", "agent", "agents", "host", "hosts"),
    "listeners": ("service", "services", "listener", "listeners"),
    "files": ("file", "files", "staged", "stager", "stagers", "loot", "download", "downloads"),
    "jobs": ("job", "jobs"),
    "daemon": ("daemon", "daemons"),
    "categories": ("category", "categories", "module-category", "module-categories"),
    "modules": ("action", "actions", "module", "modules"),
    "sessions": ("session", "sessions"),
    "routes": ("route", "routes"),
    "queue": ("queue", "mailbox", "commands"),
    "events": ("activity", "events"),
    "release": ("release", "releases", "artifact", "artifacts"),
    "options": ("options", "option"),
    "context": ("context", "info"),
}
SHOW_RESOURCE_KIND_BY_ALIAS = {
    alias: kind
    for kind, aliases in SHOW_RESOURCE_ALIASES.items()
    for alias in aliases
}


def split_line_verbose_args(args):
    parts = list(args or [])
    verbose = any(str(part).lower() in VERBOSE_FLAGS for part in parts)
    filtered_parts = [
        part for part in parts
        if str(part).lower() not in VERBOSE_FLAGS
    ]
    return verbose, filtered_parts


def parse_line_show_resource(resource):
    parts = shlex.split(str(resource or "").strip()) if str(resource or "").strip() else []
    verbose, filtered_parts = split_line_verbose_args(parts)
    key = (filtered_parts[0] if filtered_parts else "").lower()
    kind = SHOW_RESOURCE_KIND_BY_ALIAS.get(key, "")
    kind_filter = ""
    filter_text = " ".join(filtered_parts[1:]).strip()
    if len(filtered_parts) >= 2 and filtered_parts[1].lower() in ("module", "modules"):
        kind = "module-kind"
        kind_filter = key
        filter_text = " ".join(filtered_parts[2:]).strip()
    return {
        "key": key,
        "filtered_key": key,
        "filtered_parts": filtered_parts,
        "kind": kind,
        "kind_filter": kind_filter,
        "filter_text": filter_text,
        "verbose": verbose,
    }


def parse_line_show_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd == "show":
        resource = " ".join(args).strip() if args else "options"
    elif cmd in {"categories", "category", "module-categories"}:
        resource = "categories"
    elif cmd in {"modules", "module"}:
        resource = " ".join(["modules", *args]).strip()
    else:
        return {}
    return {"action": "show", "resource": resource}


def dispatch_line_show_command(show_cmd, *, show_func=None):
    try:
        if show_func:
            return show_func((show_cmd or {}).get("resource", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported show command")


def dispatch_line_show_resource(resource, handlers):
    parsed = parse_line_show_resource(resource)
    kind = parsed["kind"]
    handler = (handlers or {}).get(kind)
    if not handler:
        raise ValueError(LINE_SHOW_USAGE)
    return handler(parsed)
