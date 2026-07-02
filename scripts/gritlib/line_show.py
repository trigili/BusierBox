"""Line-console show/module argument parsing helpers."""

import shlex


VERBOSE_FLAGS = {"-v", "--verbose", "verbose", "details"}
LINE_SHOW_USAGE = (
    "Show resources:\n"
    "  show targets\n"
    "  show listeners\n"
    "  show files\n"
    "  show sessions\n"
    "  show jobs\n"
    "  show routes\n"
    "  show queue\n"
    "  show check-ins\n"
    "  show events\n"
    "  show modules\n"
    "  show modules service\n"
    "  show service modules\n"
    "  show daemon modules\n"
    "  show target modules\n"
    "  show operator modules\n"
    "  show release\n"
    "  show options\n"
    "  show context"
)
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
    "queue": ("queue", "check-ins", "checkins", "mailbox", "commands"),
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
MODULE_KIND_ALIASES = {
    "service": "service",
    "services": "service",
    "listener": "service",
    "listeners": "service",
    "daemon": "daemon",
    "daemons": "daemon",
    "target": "target",
    "targets": "target",
    "agent": "target",
    "agents": "target",
    "operator": "workbench",
    "operators": "workbench",
    "workbench": "workbench",
    "workbenches": "workbench",
    "job": "workbench",
    "jobs": "workbench",
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
        kind_filter = MODULE_KIND_ALIASES.get(key, key)
        filter_text = " ".join(filtered_parts[2:]).strip()
    elif key in ("module", "modules", "action", "actions") and len(filtered_parts) >= 2:
        second = filtered_parts[1].lower()
        if second in MODULE_KIND_ALIASES:
            kind = "module-kind"
            kind_filter = MODULE_KIND_ALIASES[second]
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
        resource = " ".join(args).strip()
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


def build_line_show_resource_callback(
    cfg,
    *,
    set_context_func,
    snapshot_func,
    target_filter_func,
    print_actions_func,
    print_targets_func,
    print_services_func,
    print_files_func,
    print_jobs_func,
    print_daemon_func,
    print_categories_func,
    print_sessions_func,
    print_routes_func,
    print_queue_func,
    print_events_func,
    print_release_func,
    print_options_func,
    print_info_func,
):
    def show_collection(name, render_fn):
        set_context_func(cfg, name)
        return render_fn()

    def show_events(_parsed=None):
        set_context_func(cfg, "events")
        snap = snapshot_func(cfg)
        return print_events_func(snap, target_id=target_filter_func(cfg), limit=12)

    def show_resource(resource):
        return dispatch_line_show_resource(resource, {
            "module-kind": lambda p: print_actions_func(
                p["filter_text"], kind_filter=p["kind_filter"], verbose=p["verbose"]),
            "targets": lambda _p: show_collection("targets", print_targets_func),
            "listeners": lambda p: show_collection("listeners", lambda: print_services_func(verbose=p["verbose"])),
            "files": lambda _p: show_collection("files", print_files_func),
            "jobs": lambda _p: show_collection("jobs", print_jobs_func),
            "daemon": lambda _p: show_collection("daemon", lambda: print_daemon_func(snapshot_func(cfg))),
            "categories": lambda _p: show_collection("categories", print_categories_func),
            "modules": lambda p: show_collection(
                "modules",
                print_categories_func
                if not p["filter_text"] and not p["verbose"]
                else lambda: print_actions_func(p["filter_text"], verbose=p["verbose"]),
            ),
            "sessions": lambda _p: show_collection("sessions", print_sessions_func),
            "routes": lambda p: show_collection("routes", lambda: print_routes_func(verbose=p["verbose"])),
            "queue": lambda p: show_collection(
                "queue",
                lambda: print_queue_func(
                    detailed=p["verbose"],
                    mailbox_only=p["key"] in {"check-ins", "checkins", "mailbox"},
                ),
            ),
            "events": show_events,
            "release": lambda _p: show_collection("release", print_release_func),
            "options": lambda _p: print_options_func(),
            "context": lambda _p: print_info_func(),
        })

    return show_resource
