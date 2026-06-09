"""Line-console help rendering for grit-console."""

from gritlib.bridge_routes import ROUTE_HELP_LINES


def line_help_topic_for_module(module):
    module = str(module or "").strip().lower()
    if not module:
        return ""
    head = module.split("/", 1)[0]
    return {
        "agent": "targets",
        "agents": "targets",
        "target": "targets",
        "targets": "targets",
        "host": "targets",
        "hosts": "targets",
        "listener": "listeners",
        "listeners": "listeners",
        "service": "listeners",
        "services": "listeners",
        "session": "sessions",
        "sessions": "sessions",
        "file": "files",
        "files": "files",
        "staged": "files",
        "stagers": "files",
        "loot": "files",
        "stage": "files",
        "deliver": "files",
        "retrieve": "files",
        "stamp": "artifact",
        "artifact": "artifact",
        "artifacts": "artifact",
        "download": "files",
        "downloads": "files",
        "release": "files",
        "route": "routes",
        "routes": "routes",
        "bridge": "routes",
        "bridges": "routes",
        "job": "jobs",
        "jobs": "jobs",
        "action": "modules",
        "actions": "modules",
        "module": "modules",
        "modules": "modules",
        "category": "workspace",
        "categories": "workspace",
        "build": "build",
        "daemon": "daemon",
        "events": "events",
        "probe": "listeners",
        "queue": "queue",
        "mailbox": "queue",
        "survey": "survey",
        "profile": "profiles",
        "profiles": "profiles",
        "workspace": "workspace",
    }.get(head, head)


def line_context_help_topic(module="", target_selected=False):
    topic = line_help_topic_for_module(module)
    if topic:
        return topic
    if target_selected:
        return "targets"
    return ""


def line_unknown_command_message(cmd, module="", target_selected=False):
    topic = line_context_help_topic(module, target_selected=target_selected)
    if topic:
        return f"unknown command: {cmd}; type ? for {topic} help"
    return f"unknown command: {cmd}; type ? for help topics"


def print_context_line_help(module="", target_selected=False, command_help_printer=None):
    topic = line_context_help_topic(module, target_selected=target_selected)
    if topic and command_help_printer:
        return command_help_printer(topic)
    return print_line_console_help()


def print_line_console_help():
    print("Console commands")
    print("")
    print("Usage:")
    print("  help <topic>    show detailed help")
    print("  <topic> ?       show detailed help")
    print("  search TERM     find agents, listeners, modules, sessions, jobs, files, and queue records")
    print("")
    groups = [
        (
            "Workspace",
            [
                ("workspace", "overview, status, info, search, next"),
                ("targets", "agents, select, mailbox, activity feed"),
                ("listeners", "services, start/stop, options"),
                ("profiles", "active target/deployment profile"),
                ("sessions", "list, select, inspect, interact"),
            ],
        ),
        (
            "Target Work",
            [
                ("files", "stage, deliver, retrieve, release, serve-binary, view"),
                ("artifact", "stamp trailer config into staged binaries or artifacts"),
                ("survey", "full griTTYkit survey: config, presets"),
                ("queue", "command queue, mailbox, results"),
            ],
        ),
        (
            "Control Plane",
            [
                ("routes", "bridge profiles, multi-hop tunnels"),
                ("modules", "runnable operator workflows, dry-run/run, background jobs"),
                ("daemon", "systemd workflow actions"),
                ("jobs", "background jobs"),
                ("build", "binary build config, guided options"),
                ("events", "operator event log browser and filters"),
            ],
        ),
        (
            "Console",
            [
                ("console", "history, resource scripts, completions, aliases"),
            ],
        ),
    ]
    for title, entries in groups:
        print(title)
        for topic, desc in entries:
            print(f"  {topic:<10} {desc}")
        print("")
    print("Aliases: agents=targets  services=listeners  bridges=routes  mailbox=queue")


LINE_COMMAND_HELP_ALIASES = {
    "agent": "targets", "agents": "targets", "target": "targets",
    "host": "targets", "hosts": "targets", "mailbox": "queue",
    "listener": "listeners", "services": "listeners", "service": "listeners",
    "session": "sessions", "interact": "sessions",
    "file": "files", "staged": "files", "stagers": "files", "loot": "files",
    "stage": "files", "deliver": "files", "retrieve": "files",
    "upload": "files", "fetch": "files", "download": "files",
    "release": "release", "releases": "release", "stage-release": "release",
    "serve-binary": "files", "binary": "files",
    "stamp": "artifact", "artifact": "artifact",
    "configure": "artifact", "trailer": "artifact",
    "view": "files", "cat": "files", "unstage": "files",
    "route": "routes", "bridge": "routes", "bridges": "routes",
    "job": "jobs",
    "action": "modules", "actions": "modules",
    "module": "modules", "modules": "modules",
    "check": "modules", "run": "modules", "execute": "modules",
    "probe": "listeners", "probe-http": "listeners", "http-probe": "listeners",
    "survey": "survey", "queue": "queue",
    "profile": "profiles", "profiles": "profiles",
    "set": "build", "build": "build", "setg": "build", "options": "build",
    "history": "console", "resource": "console", "makerc": "console",
    "complete": "console", "completions": "console", "search": "console",
    "use": "console", "main": "console", "back": "console",
    "events": "events", "event": "events",
    "aliases": "console", "commands": "console",
    "workspace": "workspace", "overview": "workspace", "status": "workspace",
    "next": "workspace", "info": "workspace", "show": "workspace",
    "refresh": "workspace",
    "daemon": "daemon",
}


LINE_COMMAND_HELP_TOPICS = {
    "workspace": {
        "title": "workspace — operator dashboard and navigation",
        "entries": [
            ("workspace, overview", "compact dashboard: listeners, agents, sessions, routes, files"),
            ("status, summary", "one-line workbench status"),
            ("info", "show selected context (target, module, session, route, job)"),
            ("next", "context-sensitive suggested commands"),
            ("search TERM", "search targets, services, modules, sessions, jobs, files, queue"),
            ("show targets|services|files|sessions|activity|modules", "show a resource list"),
            ("show modules [FILTER]", "browse runnable operator workflow modules"),
            ("show modules -v [FILTER]", "include generated run commands"),
            ("show categories", "summarize runnable module kinds"),
            ("refresh", "redraw full workbench (verbose)"),
            ("reload", "reload config file without restarting"),
        ],
    },
    "targets": {
        "title": "targets — target agents, mailbox, and activity",
        "entries": [
            ("targets, agents", "list known target agents"),
            ("agent NAME", "inspect and select a target by label, id, or number"),
            ("use target ID|LABEL|N", "select a target context"),
            ("use N", "select a numbered result from search or list"),
            ("targets -v", "verbose agent listing with connection history"),
            ("show activity", "show the target activity feed"),
            ("mailbox", "show selected-target mailbox and pending work"),
            ("interact [SESSION]", "show session log paths and interaction commands"),
            ("rename LABEL", "set a display label for the selected agent"),
            ("note TEXT", "add notes to the selected agent"),
            ("alias NAME", "set a short alias for the selected agent"),
            ("clear target", "deselect the current target context"),
        ],
    },
    "listeners": {
        "title": "listeners — reverse-access listener services",
        "entries": [
            ("listeners, services [-v]", "list listener services and their state"),
            ("listener NAME", "inspect and select a listener"),
            ("use listener NAME", "select a listener context"),
            ("start ssh|tls-shell|plain-shell|file-service", "start a listener"),
            ("stop SERVICE", "stop a running listener"),
            ("listener probe start", "start probe-http and show target delivery commands"),
            ("listener probe results", "show received probe results"),
            ("listener probe config [N]", "populate the active profile from the most recent or numbered probe result"),
            ("listener probe config write-config FILE", "export build config from probe data"),
            ("listener serve [start] [PRESET]", "stage a matching binary from the release using the active profile"),
            ("listener serve ssh start", "stage ssh-operator payload using the active profile"),
            ("listener probe paste [base64]", "print serial/admin-shell paste commands"),
            ("listener probe script", "print the raw generated probe.sh script"),
            ("listener probe clear [N|all]", "remove stale probe results"),
            ("run", "start the selected listener service"),
            ("options", "show selected listener options and relevant settings"),
            ("info", "show selected listener context"),
            ("copy start", "copy the start command to clipboard"),
            ("copy stop", "copy the stop command to clipboard"),
        ],
    },
    "profiles": {
        "title": "profiles — active target/deployment profile",
        "entries": [
            ("profiles", "list saved profiles and mark the active one"),
            ("profile", "show the active profile"),
            ("profile use NAME|N", "set the active profile"),
            ("profile create NAME", "create an empty/manual profile"),
            ("profile set KEY VALUE", "edit the active profile"),
            ("profile clear", "clear the active profile selection"),
            ("profile delete NAME|N confirm", "delete a saved profile"),
            ("profile from probe [N]", "populate the active profile from a probe result"),
            ("listener probe config [N]", "populate the active profile from probe results"),
            ("listener serve [start] [PRESET]", "stage a release artifact using the active profile"),
        ],
        "notes": [
            "Profiles are target/deployment context and live under the operator session.",
            "Server listener settings remain in local/server-config.json.",
        ],
        "examples": [
            "listener probe config",
            "profile set preferred_payload_preset ssh-operator",
            "listener serve ssh start",
        ],
    },
    "sessions": {
        "title": "sessions — captured shells and file transfers",
        "entries": [
            ("sessions [-l|-v]", "list sessions"),
            ("session ID", "inspect a session"),
            ("use session ID", "select a session context"),
            ("sessions -i SESSION", "show session inspection commands"),
            ("interact [SESSION]", "show log paths and interaction commands"),
            ("view PATH, cat PATH", "view a local session path in pager"),
            ("sessions clear", "preview removal of finished empty sessions"),
            ("sessions clear confirm", "remove finished empty sessions"),
            ("sessions clear all confirm", "remove all sessions"),
            ("info", "show selected session context"),
            ("back", "go up one breadcrumb level"),
        ],
        "notes": [
            "command-queue sessions accumulate quickly — they're created per poll cycle.",
            "sessions clear removes ended/stopped sessions with no uploads, fetches, or artifacts.",
        ],
    },
    "files": {
        "title": "files — staging and serving files to targets",
        "entries": [
            ("files, staged, stagers, loot", "list staged files and target delivery commands"),
            ("downloads", "legacy alias: list files a target can retrieve"),
            ("stage [start] LOCAL [NAME]", "stage a local file for target delivery"),
            ("deliver [queue] [start] NAME", "show or queue the target-side retrieval command"),
            ("release", "list detected release artifact recommendations"),
            ("release stage [start] [SELECTOR]", "stage a release artifact; active profile supplies default selector"),
            ("serve-binary [start] [PATH] [NAME]", "stage a griTTYkit binary for target delivery"),
            ("stamp NAME|PATH KEY=VALUE...", "apply trailer overrides to a staged binary or artifact"),
            ("artifact stamp NAME|PATH KEY=VALUE...", "artifact submenu form for trailer stamping"),
            ("unstage NAME", "remove a staged file"),
            ("files clear", "preview removal of all staged files"),
            ("files clear confirm", "remove all staged files"),
            ("view PATH, cat PATH", "view a local path in the configured pager"),
            ("retrieve [queue] TARGET_PATH", "generate a target-to-operator retrieval command"),
            ("listener probe [start] [queue]", "show or queue the probe command"),
        ],
        "notes": [
            "Compatibility aliases: upload=stage, fetch=deliver, download/get=retrieve.",
            "Trailer aliases: trailer=stamp, configure=stamp.",
        ],
        "examples": [
            "stage ./grit grit  ->  deliver grit",
            "release stage by_device:gl-mt3000",
            "serve-binary start",
            "stamp grit operator-host 192.168.8.241 zero-arg-mode rshell",
        ],
    },
    "artifact": {
        "title": "artifact — trailer stamping for staged binaries and artifacts",
        "entries": [
            ("stamp NAME|PATH KEY=VALUE...", "apply trailer overrides to a staged binary or artifact"),
            ("stamp NAME show", "show current trailer configuration"),
            ("stamp NAME clear", "remove trailer configuration"),
            ("artifact stamp NAME|PATH KEY=VALUE...", "submenu form of stamp"),
            ("artifact show NAME|PATH", "submenu shortcut for stamp NAME show"),
            ("artifact clear NAME|PATH", "submenu shortcut for stamp NAME clear"),
            ("trailer NAME|PATH ...", "compatibility alias for stamp"),
            ("configure NAME|PATH ...", "compatibility alias for stamp"),
        ],
        "examples": [
            "artifact stamp grit operator-host 192.168.8.241 zero-arg-mode rshell",
            "artifact show grit",
            "stamp grit clear",
        ],
    },
    "release": {
        "title": "release — bundle recommendations and artifact staging",
        "entries": [
            ("release", "list detected release artifact recommendations"),
            ("release stage [start] [SELECTOR]", "stage a release artifact for target delivery"),
            ("release stage ssh start", "stage ssh-operator payload using the active profile"),
            ("stage-release [start] SELECTOR", "legacy alias for release stage"),
            ("show release", "show release recommendations and artifact metadata"),
            ("files", "show staged release artifacts after staging"),
            ("deliver [queue] NAME", "show or queue the target delivery command"),
        ],
        "examples": [
            "release stage by_device:gl-mt3000",
            "release stage by_tuple_path:by-tuple/native/host/host/host",
            "stage-release start grit-target-full",
        ],
    },
    "queue": {
        "title": "queue — command queue and target mailbox",
        "entries": [
            ("queue COMMAND", "queue a shell command for the selected target"),
            ("queue list", "review command queue, mailbox records, and queue actions"),
            ("queue targets, mailbox targets", "show only target mailbox records"),
            ("queue result ID|N", "inspect a queued command result"),
            ("queue clear confirm", "remove all queued commands"),
            ("mailbox", "show selected-target mailbox records"),
            ("retrieve [queue] PATH", "queue a target-to-operator retrieval command"),
            ("deliver [queue] NAME", "queue the target delivery command"),
            ("listener probe [queue]", "queue the probe command"),
        ],
        "notes": [
            "Delivery depends on the command-queue policy and target polling interval.",
        ],
    },
    "events": {
        "title": "events — operator event log browser",
        "entries": [
            ("events", "show the last 20 operator events"),
            ("events n 50", "show the last 50 matching events"),
            ("events service=file-service", "filter by service"),
            ("events event=upload", "filter by event name"),
            ("events level=warning", "filter by level"),
            ("events target=my-router", "filter by target id or label"),
            ("events since 2h", "show events from the last N seconds/minutes/hours/days"),
            ("view local/operator-session/events.jsonl", "open the raw JSONL event log"),
        ],
        "notes": [
            "Summaries hide generated commands by default; use the raw JSONL view for full event details.",
        ],
    },
    "survey": {
        "title": "survey — full griTTYkit survey (requires griTTYkit deployed)",
        "entries": [
            ("survey",                                        "show full survey upload status"),
            ("survey results",                                "list received full survey uploads"),
            ("survey config [PATH]",                          "generate config from most recent full survey"),
            ("survey config PATH write-config FILE",          "generate and save config"),
            ("survey preset [PATH] name NAME",                "generate a reusable target preset (dry-run)"),
            ("survey preset PATH name NAME write-local",      "save preset under local/presets/targets/"),
        ],
        "notes": [
            "Full survey captures: libc, filesystem layout, writable paths, tools, network interfaces.",
            "Requires griTTYkit already deployed on the target.",
            "On target: grit survey push --host OPERATOR_IP --port FILE_SERVICE_PORT",
        ],
        "examples": [
            "survey results",
            "survey config write-config config.json",
            "survey preset name gl-mt3000 write-local",
        ],
    },
    "routes": {
        "title": "routes — bridge profiles and multi-hop tunnels",
        "entries": [
            ("routes [-v]", "list bridge route profiles"),
            ("route NAME", "inspect a bridge route"),
            ("use route NAME", "select a route context"),
            ("route add NAME LISTEN_PORT DEST_HOST DEST_PORT [FROM=TO ...]", "create a route profile"),
            ("route start NAME|NUMBER / route stop NAME|NUMBER", "start or stop a route"),
            ("route delete NAME", "remove a route profile"),
            ("start NAME / stop NAME", "shorthand start/stop when in route context"),
            ("info, options", "show selected route context"),
            ("routes -v", "show route hop details and generated start commands"),
        ],
        "notes": [
            *ROUTE_HELP_LINES,
        ],
    },
    "daemon": {
        "title": "daemon — systemd/init workflow actions",
        "entries": [
            ("daemon", "list available daemon workflow actions"),
            ("daemon verbose", "list daemon workflow actions with headless commands"),
            ("daemon ACTION", "run a daemon workflow action"),
            ("daemon ACTION dry-run", "preview a daemon workflow action"),
            ("daemon ACTION confirm", "run a confirmed daemon workflow action"),
            ("show daemon modules", "browse daemon workflow modules"),
            ("use module MODULE", "select a daemon module context"),
            ("run, check", "run or dry-run the selected daemon module"),
        ],
    },
    "jobs": {
        "title": "jobs — background workflow jobs",
        "entries": [
            ("jobs", "list managed background jobs"),
            ("job ID|NUMBER", "inspect a background job"),
            ("jobs -i ID|NUMBER", "verbose job inspection"),
            ("jobs -k ID|NUMBER", "cancel a background job"),
            ("use job ID|NUMBER", "select a job context"),
            ("run job", "start selected action module as a background job"),
            ("info, next", "show selected job context and suggested commands"),
            ("back", "go up one breadcrumb level"),
        ],
    },
    "build": {
        "title": "build — griTTYkit binary build configuration",
        "entries": [
            ("build", "show current guided build config"),
            ("build -v", "show build config options and examples"),
            ("build set KEY|NUMBER VALUE", "set a build config field"),
            ("build unset KEY|NUMBER", "clear a build config field"),
            ("set KEY VALUE", "set a target or guided build option"),
            ("setg KEY VALUE", "set a global build/workbench option"),
            ("unsetg KEY", "unset a global option"),
            ("options, show options", "show target/module/build options"),
            ("commands, copy N", "list or copy generated target-side commands"),
        ],
    },
    "modules": {
        "title": "modules — runnable operator workflows",
        "entries": [
            ("show modules [FILTER]", "browse runnable service, daemon, target, and workbench modules"),
            ("show service|daemon|target|workbench modules", "browse modules by category"),
            ("modules -v [FILTER]", "include generated headless run commands"),
            ("use module NAME|NUMBER", "select a module context"),
            ("use N", "select a numbered module from the last module list"),
            ("info", "show selected module state and summary"),
            ("options, show options", "show selected module inputs and related context"),
            ("check [MODULE]", "dry-run the selected or named module"),
            ("run [MODULE] [dry-run|confirm]", "run or preview the selected or named module"),
            ("run job, background", "start a background-capable selected action as a managed job"),
            ("back", "go up one breadcrumb level"),
        ],
        "notes": [
            "Generated headless commands stay in verbose module lists and event details by default.",
        ],
    },
    "console": {
        "title": "console — navigation, scripting, and aliases",
        "entries": [
            ("history [LIMIT]", "show recent command history"),
            ("!!, !N, repeat N", "replay a history entry"),
            ("resource FILE", "run console commands from a script file"),
            ("makerc FILE", "save command history as a replayable script"),
            ("complete [PREFIX]", "tab-style completions for dumb terminals"),
            ("search TERM", "search targets, services, modules, sessions, jobs, files"),
            ("use N", "select a numbered result from the last list or search"),
            ("main, home, root", "clear target and module context"),
            ("back", "go up one breadcrumb level"),
            ("quit, exit", "quit from root; leave context first"),
        ],
        "notes": [
            "Aliases: agents=targets  listeners=services  routes=bridges",
            "         stagers/loot=staged files  execute/exploit=run",
            "         useagent/uselistener/useroute/usesession/usemodule",
        ],
    },
}


def line_command_help_topic(topic):
    key = str(topic or "").strip().lower()
    if not key:
        return None
    canonical = LINE_COMMAND_HELP_ALIASES.get(key, key)
    return LINE_COMMAND_HELP_TOPICS.get(canonical)


def print_line_command_help(topic):
    key = str(topic or "").strip().lower()
    if not key:
        print_line_console_help()
        return

    entry = line_command_help_topic(topic)
    if not entry:
        print(f"no help topic '{topic}'  —  try: help  or  ?")
        return
    print(f"Help: {entry['title']}")
    print("")
    col = max(len(cmd) for cmd, _ in entry["entries"]) + 2
    for cmd, desc in entry["entries"]:
        print(f"  {cmd:<{col}}{desc}")
    for note in entry.get("notes") or []:
        print(f"  {note}")
    for i, ex in enumerate(entry.get("examples") or []):
        prefix = "  Example: " if i == 0 else "           "
        print(f"{prefix}{ex}")
