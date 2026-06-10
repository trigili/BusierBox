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
        "release": "release",
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
        return f"unknown command: {cmd}; run ? to show {topic} help"
    return f"unknown command: {cmd}; run ? to show help topics"


def print_context_line_help(module="", target_selected=False, command_help_printer=None):
    topic = line_context_help_topic(module, target_selected=target_selected)
    if topic and command_help_printer:
        return command_help_printer(topic)
    return print_line_console_help()


def print_line_console_help():
    print("Console commands")
    print("")
    print("Usage:")
    print("  help TOPIC      show detailed help")
    print("  TOPIC ?         show detailed help")
    print("  search TERM     find targets, listeners, modules, sessions, jobs, files, and queue records")
    print("")
    groups = [
        (
            "Workspace",
            [
                ("workspace", "overview, status, info, search, next"),
                ("workflow", "first-run probe-to-payload path"),
                ("targets", "target list, select, mailbox, activity feed"),
                ("listeners", "listener list, start and stop, options"),
                ("profiles", "active target/deployment profile"),
                ("sessions", "list, select, inspect, interact"),
            ],
        ),
        (
            "Target Work",
            [
                ("files", "stage, deliver, retrieve, release, manual binary, view"),
                ("artifact", "stamp embedded runtime config into staged binaries or artifacts"),
                ("survey", "full griTTYkit survey: config, presets"),
                ("queue", "command queue, mailbox, results"),
            ],
        ),
        (
            "Control Plane",
            [
                ("routes", "bridge profiles, multi-hop tunnels"),
                ("modules", "runnable operator workflows, dry-run, run, background jobs"),
                ("daemon", "systemd and init daemon modules"),
                ("jobs", "background jobs"),
                ("build", "binary build config, guided options"),
                ("events", "operator event log browser and filters"),
            ],
        ),
        (
            "Console",
            [
                ("console", "enter console help context; commands inside remain unprefixed"),
            ],
        ),
    ]
    for title, entries in groups:
        print(title)
        for topic, desc in entries:
            print(f"  {topic:<10} {desc}")
        print("")
    print("Compatibility: help aliases")


LINE_COMMAND_HELP_ALIASES = {
    "agent": "targets", "agents": "targets", "target": "targets",
    "host": "targets", "hosts": "targets", "mailbox": "queue",
    "listener": "listeners", "services": "listeners", "service": "listeners",
    "session": "sessions", "interact": "sessions", "usesession": "sessions",
    "file": "files", "staged": "files", "stagers": "files", "loot": "files",
    "stage": "files", "deliver": "files", "retrieve": "files",
    "upload": "files", "fetch": "files", "deploy": "files",
    "queue-fetch": "files", "queue-deliver": "files",
    "download": "files", "downloads": "files",
    "release": "release", "releases": "release", "stage-release": "release",
    "serve-binary": "files", "binary": "files",
    "stamp": "artifact", "artifact": "artifact",
    "configure": "artifact", "trailer": "artifact",
    "view": "files", "cat": "files", "less": "files", "unstage": "files",
    "rmfile": "files", "rm-file": "files",
    "route": "routes", "bridge": "routes", "bridges": "routes", "useroute": "routes",
    "job": "jobs",
    "action": "modules", "actions": "modules",
    "module": "modules", "modules": "modules",
    "check": "modules", "run": "modules", "execute": "modules", "exploit": "modules",
    "background": "modules", "usemodule": "modules",
    "probe": "listeners", "probe-http": "listeners", "http-probe": "listeners",
    "survey": "survey", "queue": "queue",
    "profile": "profiles", "profiles": "profiles",
    "set": "build", "unset": "build", "build": "build", "setg": "build", "unsetg": "build", "options": "build",
    "history": "console", "resource": "console", "makerc": "console",
    "complete": "console", "completions": "console", "search": "search",
    "use": "console", "useagent": "targets", "uselistener": "listeners",
    "main": "console", "home": "console", "root": "console", "back": "console",
    "help": "console", "q": "console", "quit": "console", "exit": "console",
    "events": "events", "event": "events",
    "aliases": "aliases",
    "commands": "generated-commands", "target-commands": "generated-commands", "copy": "generated-commands",
    "start": "start-stop", "stop": "start-stop",
    "ip": "ip", "ips": "ip",
    "workspace": "workspace", "overview": "workspace", "status": "workspace",
    "next": "workspace", "info": "workspace", "show": "show",
    "refresh": "workspace", "reload": "workspace", "workflow": "workflow", "first-run": "workflow",
    "daemon": "daemon",
}


LINE_COMMAND_HELP_TOPICS = {
    "workspace": {
        "title": "workspace — operator dashboard and navigation",
        "entries": [
            ("workspace, overview", "compact dashboard: listeners, targets, sessions, routes, files"),
            ("status, summary", "one-line workbench status"),
            ("info", "show selected context (target, module, session, route, job)"),
            ("next", "context-sensitive suggested commands"),
            ("search TERM", "search targets, listeners, modules, sessions, jobs, files, queue"),
            ("show targets", "show known targets"),
            ("show listeners", "show reverse-access listeners"),
            ("show files", "show staged operator files and binaries"),
            ("show sessions", "show captured sessions"),
            ("show events", "show recent operator activity"),
            ("show modules", "browse runnable operator workflow modules"),
            ("show modules FILTER", "filter runnable operator workflow modules"),
            ("show modules verbose FILTER", "include generated run commands"),
            ("show categories", "summarize runnable module kinds"),
            ("refresh", "redraw full workbench (verbose)"),
            ("reload", "reload config file without restarting"),
        ],
    },
    "workflow": {
        "title": "workflow — first-run probe-to-payload path",
        "entries": [
            ("listener probe start", "serve probe.sh and print target-side probe commands"),
            ("listener probe results", "review probe results after the target runs probe.sh"),
            ("listener probe config", "populate the active profile from the latest probe result"),
            ("listener probe config N", "populate the active profile from a numbered probe result"),
            ("profiles", "inspect or switch the active target/deployment profile"),
            ("listener serve", "stage a matching griTTYkit binary from the active profile"),
            ("listener serve start PRESET", "stage and serve a matching griTTYkit binary from the active profile"),
            ("deliver NAME", "show the target-side command that fetches a staged file"),
            ("listener serve ssh start", "stage and serve an ssh-operator payload for reverse SSH workflows"),
            ("files", "review staged binaries/files and next delivery commands"),
        ],
        "notes": [
            "The probe discovers target facts; the active profile carries those facts into later release and listener commands.",
            "Use global forms such as `listener probe config` from any prompt; use short forms only after selecting a context.",
        ],
        "examples": [
            "listener probe start",
            "listener probe results",
            "listener probe config",
            "listener serve ssh start",
        ],
    },
    "show": {
        "title": "show — resource lists and current context",
            "entries": [
            ("show targets", "global form: list known targets"),
            ("show listeners", "global form: list reverse-access listeners"),
            ("show files", "global form: list staged operator files and binaries"),
            ("show sessions", "global form: list captured sessions"),
            ("show jobs", "global form: list background jobs"),
            ("show routes", "global form: list bridge routes"),
            ("show queue", "global form: inspect queued commands"),
            ("show mailbox", "global form: inspect mailbox work"),
            ("show events", "global form: show recent operator activity"),
            ("show modules", "global form: browse runnable workflow modules"),
            ("show modules FILTER", "global form: filter runnable workflow modules"),
            ("show service modules", "global form: browse service modules"),
            ("show daemon modules", "global form: browse daemon modules"),
            ("show target modules", "global form: browse target modules"),
            ("show workbench modules", "global form: browse workbench modules"),
            ("show categories", "global form: summarize module categories"),
            ("show release", "global form: inspect release artifacts and recommendations"),
            ("show options", "context command: show current target/module/listener/build options"),
            ("show context", "context command: show the current prompt context"),
        ],
        "notes": [
            "Bare `show` prints usage; choose a resource so the result is predictable.",
            "Use `complete show` to browse supported resources in terminals without tab completion.",
            "Legacy show aliases remain accepted for scripts; run `help aliases` to see preferred replacements.",
        ],
    },
    "targets": {
        "title": "targets — target list, mailbox, and activity",
        "entries": [
            ("targets", "global form: list known targets"),
            ("target NAME", "global form: inspect and select a target by label, id, or number"),
            ("use target ID", "global form: select a target context by id"),
            ("use target LABEL", "global form: select a target context by label"),
            ("use target N", "global form: select a target context by number"),
            ("use N", "global form: select a numbered result from search or list"),
            ("show events", "selected-target command: show the target activity feed"),
            ("mailbox", "selected-target command: show selected-target mailbox and pending work"),
            ("interact", "selected-target command: show log paths and interaction commands for the selected target/session"),
            ("interact SESSION", "global form: show log paths and interaction commands for a session"),
            ("rename LABEL", "selected-target command: set a display label"),
            ("note TEXT", "selected-target command: add notes"),
            ("alias NAME", "selected-target command: set a short alias"),
            ("clear target", "global form: deselect the current target context"),
        ],
        "notes": [
            "Global target forms work from any prompt; selected-target commands require `grit[TARGET]>`.",
            "`target all`, `target clear`, or `clear target` returns to all targets.",
            "If no target is selected, use `targets`, `target NAME`, `use target ID`, or `use target N` first.",
        ],
    },
    "listeners": {
        "title": "listeners — reverse-access listeners",
        "entries": [
            ("listeners verbose", "list listeners with detail"),
            ("listener NAME", "inspect and select a listener"),
            ("use listener NAME", "select a listener context"),
            ("start LISTENER", "global form: start a listener by name"),
            ("start ssh", "global form: start the ssh listener"),
            ("start tls-shell", "global form: start the tls-shell listener"),
            ("start plain-shell", "global form: start the plain-shell listener"),
            ("start file-service", "global form: start the file-service listener"),
            ("stop LISTENER", "stop a running listener"),
            ("listener probe start", "global form: start probe-http and show target delivery commands"),
            ("listener probe results", "global form: show received probe results"),
            ("listener probe config", "global form: populate the active profile from the latest probe result"),
            ("listener probe config N", "global form: populate the active profile from a numbered probe result"),
            ("listener probe config write-config FILE", "global form: export build config from probe data"),
            ("listener probe options", "global form: show probe listener settings"),
            ("listener serve", "global form: stage a matching binary from the active profile"),
            ("listener serve start PRESET", "global form: stage and serve a matching binary from the active profile"),
            ("listener serve ssh start", "global form: stage ssh-operator payload from the active profile"),
            ("listener probe paste", "global form: print serial/admin-shell paste commands"),
            ("listener probe paste base64", "global form: print base64 serial/admin-shell paste commands"),
            ("listener probe script", "global form: print the raw generated probe.sh script"),
            ("listener probe clear", "global form: preview clearing all probe results"),
            ("listener probe clear N", "global form: preview clearing a numbered probe result"),
            ("listener probe clear all", "global form: preview clearing all probe results"),
            ("listener probe clear N confirm", "global form: remove a numbered probe result"),
            ("listener probe clear all confirm", "global form: remove all probe results"),
            ("run", "selected-listener command: start the current listener"),
            ("options", "selected-listener command: show current listener settings"),
            ("info", "selected-listener command: show current listener context"),
            ("show start", "selected-listener command: print the start command"),
            ("show stop", "selected-listener command: print the stop command"),
            ("copy start", "selected-listener command: copy the start command to clipboard"),
            ("copy stop", "selected-listener command: copy the stop command to clipboard"),
        ],
        "notes": [
            "Global forms include the command family, such as `listener probe start`, and work from any prompt.",
            "Selected-listener commands omit `listener` and only apply after selecting a listener context.",
            "Inside `grit/.../listener/probe>`, `options`, `run`, `show start`, and `stop` act on probe-http.",
        ],
    },
    "profiles": {
        "title": "profiles — active target/deployment profile",
        "entries": [
            ("profiles", "global form: list saved profiles and mark the active one"),
            ("profile", "global form: show the active profile"),
            ("profile use NAME", "global form: set the active profile by name"),
            ("profile use N", "global form: set the active profile by number"),
            ("profile create NAME", "global form: create an empty/manual profile"),
            ("profile set KEY VALUE", "global form: edit the active profile"),
            ("profile clear", "global form: clear the active profile selection"),
            ("profile delete NAME confirm", "global form: delete a saved profile by name"),
            ("profile delete N confirm", "global form: delete a saved profile by number"),
            ("profile from probe N", "global form: populate the active profile from a numbered probe result"),
            ("listener probe config", "global form: populate the active profile from the latest probe result"),
            ("listener probe config N", "global form: populate the active profile from a numbered probe result"),
            ("listener serve", "global form: stage a release artifact using the active profile"),
            ("listener serve start PRESET", "global form: stage and serve a release artifact using the active profile"),
        ],
        "notes": [
            "Profiles are target/deployment context and live under the operator session.",
            "Server listener settings remain in local/server-config.json.",
            "Most profile commands are global because the active profile affects release and listener workflows.",
            "Manual profile keys include target_id, target_label, arch, kernel_floor, tuple_path, operator_host, preferred_payload_preset, preferred_transport, and notes.",
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
            ("sessions, sessions list", "global form: list sessions"),
            ("sessions verbose", "global form: list sessions with detail"),
            ("session ID", "global form: inspect and select a session context"),
            ("use session ID", "global form: select a session context"),
            ("sessions interact SESSION", "global form: show session inspection commands"),
            ("interact", "selected-session form: show log paths and interaction commands"),
            ("interact SESSION", "global form: show log paths and interaction commands for a session"),
            ("view PATH", "global form: view a local session path in pager"),
            ("cat PATH", "global form: print a local session path"),
            ("sessions clear", "global form: preview removal of finished empty sessions"),
            ("sessions clear confirm", "global form: remove finished empty sessions"),
            ("sessions clear all confirm", "global form: remove all sessions"),
            ("info", "selected-session command: show selected session context"),
            ("options", "selected-session command: show session paths and activity"),
            ("back", "selected-session command: go up one breadcrumb level"),
        ],
        "notes": [
            "command-queue sessions accumulate quickly — they're created per poll cycle.",
            "sessions clear removes ended/stopped sessions with no uploads, fetches, or artifacts.",
            "Inside `grit/.../session/ID>`, short forms such as `info`, `options`, `interact`, and `back` act on that session.",
        ],
    },
    "files": {
        "title": "files — staging and serving files to targets",
        "entries": [
            ("files", "global form: list staged files and target delivery commands"),
            ("stage LOCAL NAME", "global form: stage a local file for target delivery"),
            ("stage start LOCAL NAME", "global form: stage and serve a local file"),
            ("deliver NAME", "global form: show the target-side retrieval command"),
            ("deliver queue NAME", "global form: queue the target-side retrieval command"),
            ("deliver start NAME", "global form: start file-service and show the target-side retrieval command"),
            ("release", "global form: list detected release artifact recommendations"),
            ("release stage SELECTOR", "global form: stage a release artifact; active profile can supply the selector"),
            ("release stage start SELECTOR", "global form: stage and serve a release artifact"),
            ("serve-binary PATH NAME", "manual form: stage a local griTTYkit binary for target delivery"),
            ("serve-binary start PATH NAME", "manual form: stage and serve a local griTTYkit binary"),
            ("stamp NAME KEY=VALUE", "global form: stamp embedded runtime config into a staged binary or artifact"),
            ("stamp PATH KEY=VALUE", "global form: stamp embedded runtime config into a local artifact path"),
            ("artifact stamp NAME KEY=VALUE", "artifact submenu form for embedded runtime config"),
            ("artifact stamp PATH KEY=VALUE", "artifact submenu form for embedded runtime config by path"),
            ("unstage NAME", "global form: remove a staged file"),
            ("files clear", "global form: preview removal of all staged files"),
            ("files clear confirm", "global form: remove all staged files"),
            ("view PATH", "global form: view a local path in the configured pager"),
            ("cat PATH", "global form: print a local path"),
            ("retrieve TARGET_PATH", "global form: generate a target-to-operator retrieval command"),
            ("retrieve queue TARGET_PATH", "global form: queue a target-to-operator retrieval command"),
            ("listener probe start", "global form: start probe listener and show target commands"),
            ("listener probe queue", "global form: queue the probe command for the selected target"),
        ],
        "notes": [
            "`stage` and `deliver` are operator-to-target: the target fetches a file staged by the operator.",
            "`retrieve` is target-to-operator: the target sends one of its files back to the operator.",
            "Use `start` when you want the file-service listener started by the same command.",
            "Legacy file aliases remain accepted for scripts; prefer `stage`, `deliver`, and `retrieve` in the REPL.",
            "Legacy trailer aliases remain accepted for scripts; prefer `stamp` in the REPL.",
        ],
        "examples": [
            "stage ./grit grit  ->  deliver grit",
            "release stage by_device:gl-mt3000",
            "serve-binary start",
            "stamp grit operator-host 192.168.8.241 zero-arg-mode rshell",
        ],
    },
    "artifact": {
        "title": "artifact — staged artifact inspection and runtime config stamping",
        "entries": [
            ("artifact", "global form: show staged artifacts and current release directory"),
            ("artifact info NAME", "global form: inspect embedded manifest and runtime config metadata for a staged artifact"),
            ("artifact info PATH", "global form: inspect embedded manifest and runtime config metadata for a local path"),
            ("stamp NAME KEY=VALUE", "global form: stamp embedded runtime config into a staged binary or artifact"),
            ("stamp PATH KEY=VALUE", "global form: stamp embedded runtime config into a local artifact path"),
            ("stamp NAME show", "global form: show current stamped runtime config"),
            ("stamp NAME clear", "global form: remove stamped runtime config"),
            ("artifact stamp NAME KEY=VALUE", "artifact submenu form: stamp embedded runtime config"),
            ("artifact stamp PATH KEY=VALUE", "artifact submenu form: stamp embedded runtime config by path"),
            ("artifact show NAME", "artifact submenu form: show stamped runtime config"),
            ("artifact show PATH", "artifact submenu form: show stamped runtime config by path"),
            ("artifact clear NAME", "artifact submenu form: clear stamped runtime config"),
            ("artifact clear PATH", "artifact submenu form: clear stamped runtime config by path"),
        ],
        "notes": [
            "Artifact commands inspect or stamp local staged files; they do not run anything on the target.",
            "Use `files` or `deliver NAME` when you want target-side retrieval commands.",
            "Legacy `trailer` and `configure` aliases remain accepted for scripts; prefer `stamp` in the REPL.",
        ],
        "examples": [
            "artifact",
            "artifact info grit",
            "artifact stamp grit operator-host 192.168.8.241 zero-arg-mode rshell",
            "artifact show grit",
            "stamp grit clear",
        ],
    },
    "release": {
        "title": "release — bundle recommendations and artifact staging",
        "entries": [
            ("release", "global form: list detected release artifact recommendations"),
            ("release stage SELECTOR", "global form: stage a release artifact for target delivery"),
            ("release stage start SELECTOR", "global form: stage and serve a release artifact"),
            ("release stage ssh start", "global form: stage ssh-operator payload using the active profile"),
            ("show release", "global form: show release recommendations and artifact metadata"),
            ("files", "global form: show staged release artifacts after staging"),
            ("deliver NAME", "global form: show the target delivery command"),
            ("deliver queue NAME", "global form: queue the target delivery command"),
        ],
        "notes": [
            "Release staging is operator-to-target: it selects a local release artifact and stages it for target fetch.",
            "The active profile supplies default tuple/device/payload choices after `listener probe config`.",
            "Legacy `stage-release` remains accepted for scripts; prefer `release stage` in the REPL.",
        ],
        "examples": [
            "release stage by_device:gl-mt3000",
            "release stage by_tuple_path:by-tuple/native/host/host/host",
            "release stage start grit-target-full",
        ],
    },
    "queue": {
        "title": "queue — command queue and target mailbox",
        "entries": [
            ("queue COMMAND", "global form: queue a shell command; selected target scopes delivery"),
            ("queue list", "global form: review command queue, mailbox records, and queue shortcuts"),
            ("queue targets, mailbox targets", "global form: show only target mailbox records"),
            ("queue result ID", "global form: inspect a queued command result by id"),
            ("queue result N", "global form: inspect a queued command result by number"),
            ("queue clear", "global form: preview clearing queued commands"),
            ("queue clear confirm", "global form: remove all queued commands"),
            ("mailbox", "selected-target command: show selected-target mailbox records"),
            ("retrieve queue PATH", "selected-target command: queue a target-to-operator retrieval command"),
            ("deliver queue NAME", "selected-target command: queue the target delivery command"),
            ("listener probe queue", "selected-target command: queue the probe command"),
        ],
        "notes": [
            "Without a selected target, `queue COMMAND` creates an unscoped record for any polling target.",
            "Select a target first when you want queue delivery pinned to one target, or when queueing deliver/retrieve/probe commands.",
            "Delivery depends on the command-queue policy and target polling interval.",
        ],
    },
    "events": {
        "title": "events — operator event log browser",
        "entries": [
            ("events", "global form: show the last 20 operator events"),
            ("events n 50", "global form: show the last 50 matching events"),
            ("events service=file-service", "global form: filter by service"),
            ("events event=upload", "global form: filter by event name"),
            ("events level=warning", "global form: filter by level"),
            ("events target=my-router", "global form: filter by target id or label"),
            ("events status=available", "global form: filter by detail status"),
            ("events operation=staged-fetch", "global form: filter by detail operation"),
            ("events request_name=grit", "global form: filter by staged/request name"),
            ("events command_id=cq-123", "global form: filter by queued command id"),
            ("events job_id=JOB", "global form: filter by background job id"),
            ("events module_id=MODULE", "global form: filter by module id"),
            ("events since 2h", "global form: show events from the last N seconds/minutes/hours/days"),
            ("view local/operator-session/events.jsonl", "global form: open the raw JSONL event log"),
        ],
        "notes": [
            "Filters can be combined, for example `events service=workbench status=ready n 10`.",
            "`action_id=...` is still accepted as a compatibility alias for `module_id=...`.",
            "Summaries hide generated commands by default; use the raw JSONL view for full event details.",
        ],
    },
    "search": {
        "title": "search — find and select console resources",
        "entries": [
            ("search TERM", "global form: search targets, listeners, modules, sessions, jobs, files, routes, and queue records"),
            ("use N", "global form: select a numbered result from the latest search or list"),
            ("complete PREFIX", "global form: show command completions when tab completion is unavailable"),
            ("history LIMIT", "global form: show recent commands if you meant to replay command history"),
        ],
        "notes": [
            "Search results are temporary. Run a list command or another search to replace the numbered result set.",
            "Use `resource FILE` for replayable script files; use `!N` or `repeat N` for command history.",
        ],
        "examples": [
            "search probe",
            "use 1",
            "search sample.txt",
        ],
    },
    "ip": {
        "title": "ip — choose operator network addresses",
        "entries": [
            ("ip, ip show, ips", "global form: list local IP candidates"),
            ("ip host N", "global form: set GRIT_OPERATOR_SERVER_HOST from the numbered IP list"),
            ("ip host IP", "global form: set GRIT_OPERATOR_SERVER_HOST directly"),
            ("ip bind N", "global form: set listen_host from the numbered IP list"),
            ("ip bind IP", "global form: set listen_host directly"),
            ("set GRIT_OPERATOR_SERVER_HOST IP", "global form: manually set the advertised operator address"),
            ("set listen_host IP", "global form: manually set the listener bind address"),
        ],
        "notes": [
            "`ip host` affects target-side commands such as probe, deliver, retrieve, and reverse access.",
            "`ip bind` affects where operator listeners accept connections.",
            "Use `ip` first when you want to pick from detected local interfaces instead of typing an address manually.",
        ],
        "examples": [
            "ip",
            "ip host 1",
            "ip bind 192.168.8.241",
        ],
    },
    "generated-commands": {
        "title": "commands — generated target-side commands",
        "entries": [
            ("commands, target-commands", "global form: list target-side commands generated from current workbench state"),
            ("commands list, commands show", "global form: list generated commands explicitly"),
            ("copy N", "global form: copy generated command row N to the command-copy file and clipboard when available"),
            ("commands copy N", "global form: copy generated command row N using the commands family"),
            ("show start, show stop", "selected-listener command: print the current listener start and stop commands"),
            ("copy start, copy stop", "selected-listener command: copy the current listener start and stop commands"),
        ],
        "notes": [
            "Generated target-side commands are things you paste or run on the target, such as probe, deliver, retrieve, and reverse-access commands.",
            "Run `commands` first when you want numbered rows for `copy N`.",
            "Listener `copy start` and `copy stop` only apply after selecting a listener context.",
        ],
        "examples": [
            "commands",
            "copy 1",
            "commands copy 2",
            "listener probe",
            "copy start",
        ],
    },
    "start-stop": {
        "title": "start and stop — listener and route lifecycle",
        "entries": [
            ("start LISTENER", "global form: start a listener such as ssh, file-service, command-queue, or probe"),
            ("stop LISTENER", "global form: stop a listener"),
            ("listener NAME", "global form: inspect/select a listener before using short lifecycle commands"),
            ("run", "selected-listener command: start the selected listener"),
            ("stop", "selected-listener command: stop the selected listener"),
            ("route start NAME", "global form: start a bridge route by name"),
            ("route start N", "global form: start a bridge route by number"),
            ("route stop NAME", "global form: stop a bridge route by name"),
            ("route stop N", "global form: stop a bridge route by number"),
            ("start, stop", "selected-route command: start or stop the selected route"),
        ],
        "notes": [
            "At the root prompt, use `start LISTENER` or `stop LISTENER` for listeners.",
            "Inside `grit/.../listener/NAME>`, short `run` and `stop` act on that listener.",
            "Inside `grit/.../route/NAME>`, short `start` and `stop` act on that route.",
        ],
        "examples": [
            "start file-service",
            "listener probe",
            "run",
            "route start web-hop",
        ],
    },
    "survey": {
        "title": "survey — full griTTYkit survey (requires griTTYkit deployed)",
        "entries": [
            ("survey",                                        "global form: show full survey upload status"),
            ("survey results",                                "global form: list received full survey uploads"),
            ("survey config",                                 "global form: generate config from most recent full survey"),
            ("survey config PATH",                            "global form: generate config from a specific survey upload"),
            ("survey config PATH write-config FILE",          "global form: generate and save config"),
            ("survey preset PATH name NAME",                  "global form: generate a reusable target preset (dry-run)"),
            ("survey preset PATH name NAME write-local",      "global form: save preset under local/presets/targets/"),
        ],
        "notes": [
            "Full survey captures: libc, filesystem layout, writable paths, tools, network interfaces.",
            "Requires griTTYkit already deployed on the target.",
            "On target: grit survey retrieve --host OPERATOR_IP --port FILE_SERVICE_PORT",
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
            ("routes", "global form: list bridge route profiles"),
            ("route NAME", "global form: inspect a bridge route"),
            ("use route NAME", "global form: select a route context"),
            ("route add NAME LISTEN_PORT DEST_HOST DEST_PORT", "global form: create a direct route profile"),
            ("route add NAME LISTEN_PORT DEST_HOST DEST_PORT FROM=TO", "global form: create a route profile with a documented hop"),
            ("route start NAME", "global form: start a route by name"),
            ("route start N", "global form: start a route by number"),
            ("route stop NAME", "global form: stop a route by name"),
            ("route stop N", "global form: stop a route by number"),
            ("route delete NAME", "global form: preview route profile removal"),
            ("route delete NAME confirm", "global form: remove a route profile"),
            ("start / stop", "selected-route command: start or stop the current route"),
            ("info, options", "selected-route command: show selected route context"),
            ("routes verbose", "global form: show route hop details and generated start commands"),
        ],
        "notes": [
            "Selected-route commands omit the route name and only apply after `route NAME` or `use route NAME`.",
            *ROUTE_HELP_LINES,
        ],
    },
    "daemon": {
        "title": "daemon — systemd and init daemon modules",
        "entries": [
            ("daemon", "global form: list available daemon modules"),
            ("daemon verbose", "global form: list daemon modules with generated run commands"),
            ("daemon MODULE", "global form: run a daemon workflow module"),
            ("daemon MODULE dry-run", "global form: preview a daemon workflow module"),
            ("daemon MODULE confirm", "global form: run a confirmed daemon workflow module"),
            ("show daemon modules", "global form: browse daemon modules"),
            ("use module MODULE", "global form: select a daemon module context"),
            ("run, check", "selected-module command: run or dry-run the selected daemon module"),
        ],
        "notes": [
            "Selected-module commands apply after `use module MODULE`; global `daemon MODULE` works from any prompt.",
            "Use `daemon MODULE dry-run` to preview; `dry-run` and `confirm` are modifiers after a module, not standalone commands.",
        ],
    },
    "jobs": {
        "title": "jobs — background workflow jobs",
        "entries": [
            ("jobs", "global form: list managed background jobs"),
            ("job ID", "global form: inspect a background job by id"),
            ("job N", "global form: inspect a background job by number"),
            ("jobs info ID", "global form: inspect a background job by id"),
            ("jobs info N", "global form: inspect a background job by number"),
            ("jobs cancel ID", "global form: cancel a background job by id"),
            ("jobs cancel N", "global form: cancel a background job by number"),
            ("use job ID", "global form: select a job context by id"),
            ("use job N", "global form: select a job context by number"),
            ("run job", "selected-module command: start selected background-capable module as a job"),
            ("info, options, next", "selected-job command: show selected job context and suggested commands"),
            ("cancel", "selected-job command: cancel the selected job when cancellation is supported"),
            ("back", "selected-job command: go up one breadcrumb level"),
        ],
        "notes": [
            "`run job` starts the currently selected background-capable module; it is not a job-context command.",
        ],
    },
    "build": {
        "title": "build — griTTYkit binary build configuration",
        "entries": [
            ("build", "global form: show current guided build config"),
            ("build verbose", "global form: show build config options and examples"),
            ("build set KEY VALUE", "global form: set a build config field by key"),
            ("build set ROW VALUE", "global form: set a build config field by row number"),
            ("build unset KEY", "global form: clear a build config field by key"),
            ("build unset ROW", "global form: clear a build config field by row number"),
            ("set KEY VALUE", "context command: set a target, listener, module, or guided build option"),
            ("setg KEY VALUE", "global form: set a global build/workbench option"),
            ("unsetg KEY", "global form: unset a global option"),
            ("options, show options", "context command: show target/module/listener/build options"),
            ("commands, copy N", "context command: list or copy generated target-side commands"),
        ],
        "notes": [
            "`set KEY VALUE` follows the selected context when one is active; use `build set ...` for build config.",
            "`setg` and `unsetg` always edit global workbench options.",
        ],
    },
    "modules": {
        "title": "modules — runnable operator workflows",
        "entries": [
            ("show modules", "global form: browse runnable service, daemon, target, and workbench modules"),
            ("show modules FILTER", "global form: filter runnable service, daemon, target, and workbench modules"),
            ("show service modules", "global form: browse service modules"),
            ("show daemon modules", "global form: browse daemon modules"),
            ("show target modules", "global form: browse target modules"),
            ("show workbench modules", "global form: browse workbench modules"),
            ("modules verbose FILTER", "global form: include generated run commands"),
            ("use module NAME", "global form: select a module context by name"),
            ("use module NUMBER", "global form: select a module context by number"),
            ("use N", "global form: select a numbered module from the last module list"),
            ("info", "selected-module command: show selected module state and summary"),
            ("options, show options", "selected-module command: show inputs and related context"),
            ("check MODULE", "global or selected-module form: dry-run the selected or named module"),
            ("run MODULE", "global or selected-module form: run the selected or named module"),
            ("run MODULE dry-run", "global or selected-module form: preview the selected or named module"),
            ("run job, background", "selected-module command: start a background-capable module as a managed job"),
            ("back", "selected-module command: go up one breadcrumb level"),
        ],
        "notes": [
            "Generated commands stay in verbose module lists and event details by default.",
            "Short `run`, `check`, `options`, and `info` use the selected module while a selected-module prompt is active.",
        ],
    },
    "console": {
        "title": "console — navigation, scripting, and aliases",
        "entries": [
            ("history LIMIT", "global form: show recent command history"),
            ("!!, !N, repeat N", "global form: replay a history entry"),
            ("resource FILE", "global form: run console commands from a script file"),
            ("makerc FILE", "global form: save command history as a replayable script"),
            ("complete PREFIX", "global form: show tab-style completions for dumb terminals"),
            ("search TERM", "global form: search targets, listeners, modules, sessions, jobs, files"),
            ("use N", "global form: select a numbered result from the last list or search"),
            ("main, home, root", "global form: clear target and module context"),
            ("back", "context command: go up one breadcrumb level"),
            ("quit, exit", "global form: quit from root; leave context first"),
        ],
        "notes": [
            "`console` opens this help context; run the listed commands without a `console` prefix.",
            "`back` follows the current breadcrumb; `main` returns directly to the root workspace.",
            "Accepted aliases remain for scripts, but interactive help and completions prefer canonical forms.",
            "Preferred forms: targets, listeners, routes, files, run MODULE, use target/listener/route/session/module.",
        ],
    },
    "aliases": {
        "title": "aliases — legacy compatibility names and preferred REPL forms",
        "entries": [
            ("agents", "legacy compatibility alias; prefer targets"),
            ("services", "legacy compatibility alias; prefer listeners"),
            ("bridges", "legacy compatibility alias; prefer routes"),
            ("mailbox", "legacy compatibility alias; prefer queue"),
            ("upload LOCAL NAME", "legacy compatibility alias; prefer stage LOCAL NAME"),
            ("fetch NAME", "legacy compatibility alias; prefer deliver NAME"),
            ("deploy NAME", "legacy compatibility alias; prefer deliver NAME"),
            ("download PATH", "legacy compatibility alias; prefer retrieve PATH"),
            ("trailer NAME KEY=VALUE", "legacy compatibility alias; prefer stamp NAME KEY=VALUE"),
            ("configure NAME KEY=VALUE", "legacy compatibility alias; prefer stamp NAME KEY=VALUE"),
            ("stage-release SELECTOR", "legacy compatibility alias; prefer release stage SELECTOR"),
            ("execute MODULE", "legacy compatibility alias; prefer run MODULE"),
            ("exploit MODULE", "legacy compatibility alias; prefer run MODULE"),
            ("useagent NAME", "legacy compatibility alias; prefer use target NAME"),
            ("uselistener NAME", "legacy compatibility alias; prefer use listener NAME"),
            ("useroute NAME", "legacy compatibility alias; prefer use route NAME"),
            ("usesession ID", "legacy compatibility alias; prefer use session ID"),
            ("usemodule MODULE", "legacy compatibility alias; prefer use module MODULE"),
        ],
        "notes": [
            "Aliases remain accepted for scripts and old muscle memory.",
            "Interactive help and completions prefer canonical forms: targets, listeners, routes, files, stage, deliver, retrieve, stamp, release stage, run, and use ...",
            "Preferred selector forms: use target/listener/route/session/module.",
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
