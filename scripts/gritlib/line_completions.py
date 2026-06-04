"""Line-console completion vocabulary helpers."""


BASE_COMMANDS = [
    "help", "complete", "search", "resource", "makerc", "history", "workspace", "status",
    "events",
    "show", "info", "options", "next", "commands", "target-commands", "copy", "set", "setg", "unset", "unsetg",
    "agents", "agent", "targets", "target", "listeners", "listener",
    "routes", "route", "sessions", "session", "jobs", "job", "use",
    "useagent", "uselistener", "useroute", "usesession", "usemodule",
    "main", "home", "root", "back", "background", "start", "stop",
    "check", "run", "execute", "exploit", "interact", "queue",
    "download", "get", "probe", "survey", "daemon", "build", "release", "releases", "stage-release", "upload",
    "fetch", "deploy", "queue-fetch", "serve-binary", "configure", "trailer", "downloads", "unstage",
    "rmfile", "view", "cat", "less", "mailbox", "refresh",
    "quit", "exit", "ips", "reload",
]

SHOW_RESOURCES = [
    "agents", "targets", "listeners", "services", "routes", "sessions",
    "jobs", "queue", "mailbox", "files", "stagers", "loot", "activity",
    "release", "releases", "modules", "categories", "service modules", "daemon modules",
    "target modules", "workbench modules", "options",
]

USE_KINDS = ["agent", "target", "listener", "service", "route", "session", "job", "module", "action"]

HELP_TOPICS = [
    "search", "complete", "commands", "resource", "makerc", "history", "use", "main", "show",
    "actions", "modules", "options", "next", "workspace", "aliases", "listeners",
    "routes", "set", "setg", "run", "jobs", "queue", "events", "download", "probe", "survey", "build",
    "release", "upload", "fetch", "files", "view",
    "daemon", "interact", "sessions",
]


def parse_line_completion_command(cmd, args):
    if str(cmd or "").strip().lower() not in {"complete", "completions"}:
        return None
    return {
        "action": "show",
        "prefix": " ".join(str(arg) for arg in (args or [])).strip(),
    }


def prefixed(prefix_text, values):
    seen = set()
    result = []
    lower = str(prefix_text or "").lower()
    for value in values:
        candidate = str(value or "").strip()
        if not candidate or candidate in seen:
            continue
        if not lower or candidate.lower().startswith(lower):
            seen.add(candidate)
            result.append(candidate)
    return result
