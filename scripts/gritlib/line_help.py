"""Line-console help rendering for grit-console."""

from gritlib.bridge_routes import ROUTE_HELP_LINES


def print_line_console_help():
    print("Console help topics:")
    print("")
    print("  workspace   overview, status, info, search, next")
    print("  targets     agents, select, mailbox, activity feed")
    print("  listeners   services, start/stop, options")
    print("  sessions    list, select, inspect, interact")
    print("  files       stage, fetch, download, release, serve-binary, view")
    print("  probe       shell probe (pre-deployment): run probe.sh, see results, gen config")
    print("  survey      full griTTYkit survey (post-deployment): config, presets")
    print("  queue       command queue, mailbox, results")
    print("  events      operator event log browser and filters")
    print("  routes      bridge profiles, multi-hop tunnels")
    print("  daemon      systemd workflow actions")
    print("  jobs        background jobs")
    print("  build       binary build config, guided options")
    print("  console     history, resource scripts, completions, aliases")
    print("")
    print("  help <topic>  or  <topic> ?   get detailed help on a topic")


def print_line_command_help(topic):
    key = str(topic or "").strip().lower()
    if not key:
        print_line_console_help()
        return

    # Aliases map alternate spellings to canonical topic keys
    _topic_aliases = {
        "agent": "targets", "agents": "targets", "target": "targets",
        "host": "targets", "hosts": "targets", "mailbox": "targets",
        "listener": "listeners", "services": "listeners", "service": "listeners",
        "session": "sessions", "interact": "sessions",
        "file": "files", "staged": "files", "stagers": "files", "loot": "files",
        "upload": "files", "fetch": "files", "download": "files",
        "release": "files", "serve-binary": "files", "binary": "files",
        "configure": "files", "trailer": "files",
        "view": "files", "cat": "files", "unstage": "files",
        "route": "routes", "bridge": "routes", "bridges": "routes",
        "job": "jobs", "run": "jobs",
        "probe": "probe", "survey": "survey", "queue": "queue",
        "set": "build", "build": "build", "setg": "build", "options": "build",
        "history": "console", "resource": "console", "makerc": "console",
        "complete": "console", "completions": "console", "search": "console",
        "use": "console", "main": "console", "back": "console",
        "events": "events", "event": "events",
        "aliases": "console", "commands": "console",
        "workspace": "workspace", "overview": "workspace", "status": "workspace",
        "next": "workspace", "info": "workspace", "show": "workspace",
        "modules": "workspace", "refresh": "workspace",
        "daemon": "daemon",
    }
    canonical = _topic_aliases.get(key, key)

    help_topics = {
        "workspace": {
            "title": "workspace — operator dashboard and navigation",
            "entries": [
                ("workspace, overview", "compact dashboard: listeners, agents, sessions, routes, files"),
                ("status, summary", "one-line workbench status"),
                ("info", "show selected context (target, module, session, route, job)"),
                ("next", "context-sensitive suggested commands"),
                ("search TERM", "search targets, services, actions, sessions, jobs, files, queue"),
                ("show targets|services|files|sessions|activity|modules", "show a resource list"),
                ("show modules [FILTER]", "browse runnable action/service modules"),
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
                ("run", "start the selected listener service"),
                ("options", "show selected listener options and relevant settings"),
                ("info", "show selected listener context"),
                ("copy start", "copy the start command to clipboard"),
                ("copy stop", "copy the stop command to clipboard"),
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
                ("sessions clear --confirm", "remove finished empty sessions"),
                ("sessions clear --all --confirm", "remove all sessions"),
                ("info", "show selected session context"),
                ("back", "deselect session context"),
            ],
            "notes": [
                "command-queue sessions accumulate quickly — they're created per poll cycle.",
                "sessions clear removes ended/stopped sessions with no uploads, fetches, or artifacts.",
            ],
        },
        "files": {
            "title": "files — staging and serving files to targets",
            "entries": [
                ("files, staged, stagers, loot", "list staged files and target fetch commands"),
                ("downloads", "list files a target can currently fetch"),
                ("upload [--start] LOCAL [NAME]", "stage a local file for target fetch"),
                ("fetch [--queue] [--start] NAME", "show or queue a target fetch command"),
                ("release", "list detected release artifact recommendations"),
                ("release stage [--start] SELECTOR", "stage a release artifact"),
                ("serve-binary [--start] [PATH] [NAME]", "stage a griTTYkit binary for target fetch"),
                ("configure NAME|PATH KEY=VALUE...", "apply trailer overrides to a staged binary or artifact"),
                ("configure NAME --operator-host HOST --transport builtin", "guided trailer override flags"),
                ("unstage NAME", "remove a staged file"),
                ("files clear", "preview removal of all staged files"),
                ("files clear --confirm", "remove all staged files"),
                ("view PATH, cat PATH", "view a local path in the configured pager"),
                ("download [--queue] TARGET_PATH", "generate an upload-back command for the target"),
                ("probe [--start] [--queue]", "show or queue the probe command"),
            ],
            "examples": [
                "upload ./grit grit  →  fetch grit",
                "release stage by_device:gl-mt3000",
                "serve-binary --start",
                "configure grit --operator-host 192.168.8.241 --zero-arg-mode rshell",
            ],
        },
        "queue": {
            "title": "queue — command queue and target mailbox",
            "entries": [
                ("queue COMMAND", "queue a shell command for the selected target"),
                ("queue list", "show the target mailbox"),
                ("queue result ID|N", "inspect a queued command result"),
                ("queue clear --confirm", "remove all queued commands"),
                ("mailbox", "show command queue and mailbox state"),
                ("download [--queue] PATH", "queue a target-to-operator upload command"),
                ("fetch [--queue] NAME", "queue a target fetch command"),
                ("probe [--queue]", "queue the probe command"),
            ],
            "notes": [
                "Delivery depends on the command-queue policy and target polling interval.",
            ],
        },
        "events": {
            "title": "events — operator event log browser",
            "entries": [
                ("events", "show the last 20 operator events"),
                ("events -n 50", "show the last 50 matching events"),
                ("events service=file-service", "filter by service"),
                ("events event=upload", "filter by event name"),
                ("events level=warning", "filter by level"),
                ("events target=my-router", "filter by target id or label"),
                ("events --since 2h", "show events from the last N seconds/minutes/hours/days"),
                ("view local/operator-session/events.jsonl", "open the raw JSONL event log"),
            ],
            "notes": [
                "Summary condenses common detail fields, including headless_command when present.",
            ],
        },
        "probe": {
            "title": "probe — lightweight shell probe (no griTTYkit required)",
            "entries": [
                ("probe --start",                           "start the probe.sh listener on port 22207"),
                ("probe",                                   "show the target-side command (warns if listener is down)"),
                ("probe --queue",                           "queue probe command for selected target's next phone-home"),
                ("probe delivery",                          "show wget, curl, and raw nc delivery commands"),
                ("probe paste",                             "print a serial/admin-shell heredoc that runs without writing a file"),
                ("probe paste --base64",                    "print a base64 paste wrapper for shells with fragile quoting"),
                ("probe script",                            "print the raw generated probe.sh script"),
                ("probe results",                           "show received probe results (arch, kernel, bits, endian)"),
                ("probe config [N]",                        "generate config from the most recent or numbered probe result"),
                ("probe config --write-config FILE",        "generate and save config"),
                ("probe clear [N|--all]",                   "remove stale probe results"),
                ("probe serve [--start]",                   "stage the matching binary from the release for this arch"),
            ],
            "notes": [
                "probe.sh captures: arch (uname_m), kernel, OS, word size, endian.",
                "No griTTYkit required — download with wget, curl, or raw nc over HTTP.",
                "probe paste bypasses the script download step for serial consoles and limited admin shells.",
                "probe paste --base64 avoids most shell quoting issues but requires a base64 decoder.",
                "probe config uses estimated defaults for libc/filesystem; use survey config for full data.",
            ],
            "examples": [
                "probe --start",
                "  (run the shown command on the target)",
                "probe results",
                "probe config --write-config config.json",
                "probe serve --start",
            ],
        },
        "survey": {
            "title": "survey — full griTTYkit survey (requires griTTYkit deployed)",
            "entries": [
                ("survey",                                        "show full survey upload status"),
                ("survey results",                                "list received full survey uploads"),
                ("survey config [PATH]",                          "generate config from most recent full survey"),
                ("survey config PATH --write-config FILE",        "generate and save config"),
                ("survey preset [PATH] --name NAME",              "generate a reusable target preset (dry-run)"),
                ("survey preset PATH --name NAME --write-local",  "save preset under local/presets/targets/"),
            ],
            "notes": [
                "Full survey captures: libc, filesystem layout, writable paths, tools, network interfaces.",
                "Requires griTTYkit already deployed on the target.",
                "On target: grit survey push --host OPERATOR_IP --port FILE_SERVICE_PORT",
            ],
            "examples": [
                "survey results",
                "survey config --write-config config.json",
                "survey preset --name gl-mt3000 --write-local",
            ],
        },
        "routes": {
            "title": "routes — bridge profiles and multi-hop tunnels",
            "entries": [
                ("routes [-v]", "list bridge route profiles"),
                ("route NAME", "inspect a bridge route"),
                ("use route NAME", "select a route context"),
                ("route add NAME LISTEN_PORT DEST_HOST DEST_PORT [FROM=TO ...]", "create a route profile"),
                ("route start NAME / route stop NAME", "start or stop a route"),
                ("route delete NAME", "remove a route profile"),
                ("start NAME / stop NAME", "shorthand start/stop when in route context"),
                ("info, options", "show selected route context and headless commands"),
            ],
            "notes": [
                *ROUTE_HELP_LINES,
            ],
        },
        "daemon": {
            "title": "daemon — systemd/init workflow actions",
            "entries": [
                ("daemon", "list available daemon workflow actions"),
                ("daemon -v", "list daemon workflow actions with headless commands"),
                ("daemon ACTION", "run a daemon workflow action"),
                ("daemon ACTION --dry-run", "preview a daemon workflow action"),
                ("daemon ACTION --confirm", "run a confirmed daemon workflow action"),
                ("show daemon modules", "browse daemon workflow modules"),
                ("use module MODULE", "select a daemon module context"),
                ("run, check", "run or dry-run the selected daemon module"),
            ],
        },
        "jobs": {
            "title": "jobs — background workflow jobs",
            "entries": [
                ("jobs", "list managed background jobs"),
                ("job ID", "inspect a background job"),
                ("jobs -i ID", "verbose job inspection"),
                ("jobs -k ID", "cancel a background job"),
                ("use job ID", "select a job context"),
                ("run -j, run --job", "start selected action module as a background job"),
                ("info, next", "show selected job context and suggested commands"),
                ("back", "deselect job context"),
            ],
        },
        "build": {
            "title": "build — griTTYkit binary build configuration",
            "entries": [
                ("build", "show current guided build config"),
                ("build -v", "show build config options and examples"),
                ("build set KEY VALUE", "set a build config field"),
                ("build unset KEY", "clear a build config field"),
                ("set KEY VALUE", "set a target or guided build option"),
                ("setg KEY VALUE", "set a global build/workbench option"),
                ("unsetg KEY", "unset a global option"),
                ("options, show options", "show target/module/build options"),
                ("commands, copy N", "list or copy generated target-side commands"),
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
                ("search TERM", "search targets, services, actions, sessions, jobs, files"),
                ("use N", "select a numbered result from the last list or search"),
                ("main, home, root", "clear target and module context"),
                ("back", "clear module context only"),
                ("quit, exit", "quit"),
            ],
            "notes": [
                "Aliases: agents=targets  listeners=services  routes=bridges",
                "         stagers/loot=staged files  execute/exploit=run",
                "         useagent/uselistener/useroute/usesession/usemodule",
            ],
        },
    }

    entry = help_topics.get(canonical)
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
