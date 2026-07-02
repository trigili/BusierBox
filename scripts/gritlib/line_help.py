"""Line-console help rendering for grit-console."""

from gritlib.bridge_routes import ROUTE_HELP_LINES


def line_help_topic_for_module(module):
    module = str(module or "").strip().lower()
    if not module:
        return ""
    if module in {"listener/probe", "listener/probe-http", "probe", "probe-http", "http-probe"}:
        return "probe"
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
        "probe": "probe",
        "queue": "queue",
"mailbox": "queue", "check-ins": "queue", "checkins": "queue",
        "survey": "survey",
        "commands": "generated-commands",
        "target-commands": "generated-commands",
        "copy": "generated-commands",
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
        return f"unknown command: {cmd}; run ?, options, or next to recover in the {topic} menu"
    return f"unknown command: {cmd}; run ?, options, or next to recover"


def print_context_line_help(module="", target_selected=False, command_help_printer=None):
    topic = line_context_help_topic(module, target_selected=target_selected)
    if topic and command_help_printer:
        return command_help_printer(topic)
    return print_line_console_help()


def print_modules_context_help(module="", selected_action=None):
    module = str(module or "").strip()
    selected_action = selected_action if isinstance(selected_action, dict) else {}
    selected = module.startswith("action/")
    print("Help: modules — runnable console modules")
    print("")
    if selected:
        entries = [
            ("info", "show current module state and summary"),
            ("options", "show inputs and related details"),
            ("check", "preflight the current module without running it"),
            ("preview", "preview the current module run command"),
            ("run", "run the current module"),
        ]
        if selected_action.get("requires_confirmation"):
            entries.append(("run confirm", "run this confirmation-required module"))
        if selected_action.get("background_supported"):
            entries.extend([
                ("run job", "start the current module as a managed job"),
                ("background", "start the current module as a managed job"),
            ])
        entries.extend([
            ("modules", "return to the runnable module list"),
            ("back", "go up one breadcrumb level"),
        ])
        notes = [
            "These short commands act on the current module.",
            "Use `modules` to choose a different module.",
        ]
    else:
        entries = [
            ("modules", "show module categories and counts"),
            ("modules service", "browse service modules"),
            ("modules daemon", "browse daemon modules"),
            ("modules target", "browse target modules"),
            ("modules operator", "browse operator modules"),
            ("modules verbose service", "include command lines for service modules"),
            ("use module Inspect bridge status", "choose a module by name"),
            ("use module N", "choose a module by number"),
            ("use N", "select a numbered module from the last module list"),
            ("check Inspect bridge status", "preflight a named module without running it"),
            ("preview Inspect bridge status", "preview a named module run command"),
            ("run Inspect bridge status", "run a named module"),
            ("back", "go up one breadcrumb level"),
        ]
        notes = [
            "Select a module first to use short commands such as `info`, `options`, `check`, and `run`.",
            "open service modules: modules service",
            "choose first module: use 1",
            "run by name: run Inspect bridge status",
            "Select a module that can run in the background before using `run job`.",
            "Command lines are hidden in filtered lists; run `modules verbose service` when you need them.",
        ]
    col = max(len(cmd) for cmd, _ in entries) + 2
    for cmd, desc in entries:
        print(f"  {cmd:<{col}}{desc}")
    for note in notes:
        print(f"  {note}")


def print_daemon_context_help():
    entries = [
        ("daemon", "list operator daemon and systemd controls"),
        ("daemon verbose", "list daemon controls with command lines"),
        ("daemon status", "show daemon health and managed listener state"),
        ("daemon status preview", "preview the daemon status control"),
        ("daemon install confirm", "install the user systemd unit after confirmation"),
        ("daemon start confirm", "start configured listeners in the background after confirmation"),
        ("modules daemon", "browse daemon controls in the general module list"),
        ("use module Check operator daemon", "choose the daemon status control from the module list"),
        ("back", "go up one breadcrumb level"),
    ]
    print("Help: daemon — operator daemon and systemd controls")
    print("")
    col = max(len(cmd) for cmd, _ in entries) + 2
    for cmd, desc in entries:
        print(f"  {cmd:<{col}}{desc}")
    print("  Select a daemon control first to use short commands such as `check` and `run`.")
    print("  review daemon state: daemon status")
    print("  preview daemon state check: daemon status preview")
    print("  Add `preview` or `confirm` after a concrete daemon command, such as `daemon status preview`.")


def print_commands_context_help():
    entries = [
        ("commands", "list commands to paste or run on a target"),
        ("commands list", "show the target-command table again"),
        ("copy N", "copy target command row N for pasting and save a fallback file"),
        ("commands copy N", "copy target command row N from the commands menu"),
        ("files", "review staged files and commands to run on targets"),
        ("use listener probe", "open the probe menu"),
        ("listeners", "review listener start and stop commands"),
        ("survey", "review survey collection commands"),
        ("back", "go up one breadcrumb level"),
    ]
    print("Help: commands — target commands to run on devices")
    print("")
    col = max(len(cmd) for cmd, _ in entries) + 2
    for cmd, desc in entries:
        print(f"  {cmd:<{col}}{desc}")
    print("  Target commands are things you paste or run on a target, such as probe scripts, staged-file commands generated by deliver, survey retrieval, and reverse access.")
    print("  Direction guide: console `retrieve` sends target files to the operator; console `deliver` sends staged operator files to the target.")
    print("  Open `commands` first when you want numbered rows for `copy N`.")
    print("  After copying, the console prints the saved file path and clipboard status.")


def print_line_console_help():
    print("Console commands")
    print("")
    print("Usage:")
    print("  help listeners  show focused help, for example listener commands")
    print("  listeners ?     same as help listeners")
    print("  search listener find targets, listeners, modules, sessions, jobs, files, and queued work")
    print("  Core commands work anywhere: targets, profiles, listeners, files, routes, sessions, modules, jobs.")
    print("  Choose a target, listener, module, session, or job only when you want shorter commands there.")
    print("")
    groups = [
        (
            "Workspace",
            [
                ("workspace", "leave the current menu and show the main overview"),
                ("workflow", "probe, profile, serve, staged files"),
                ("targets", "target list, select, pending work, activity feed"),
                ("listeners", "listener list, start and stop, options"),
                ("profiles", "active target deployment profile"),
                ("sessions", "list, select, inspect, interact"),
            ],
        ),
        (
            "Target Work",
            [
                ("files", "stage, deliver, retrieve, release artifacts, view"),
                ("artifact", "stamp embedded runtime settings into staged files or artifacts"),
                ("survey", "full griTTYkit survey: config, presets"),
                ("queue", "command queue, target check-ins, results"),
            ],
        ),
        (
            "Operator Tools",
            [
                ("routes", "bridge profiles, multi-hop tunnels"),
                ("modules", "runnable modules, preview, run, background jobs"),
                ("daemon", "operator daemon and systemd controls"),
                ("jobs", "background jobs"),
                ("build", "build config, guided options"),
                ("events", "operator event log browser and filters"),
            ],
        ),
        (
            "Console",
            [
                ("console", "navigation, history, command files, completion"),
            ],
        ),
    ]
    for title, entries in groups:
        print(title)
        for topic, desc in entries:
            print(f"  {topic:<10} {desc}")
        print("")


LINE_COMMAND_HELP_ALIASES = {
    "agent": "targets", "agents": "targets", "target": "targets",
    "host": "targets", "hosts": "targets", "mailbox": "queue",
    "check-ins": "queue", "checkins": "queue",
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
    "probe": "probe", "probe-http": "probe", "http-probe": "probe",
    "listener probe": "probe", "listener/probe": "probe", "use listener probe": "probe",
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
    "refresh": "workspace", "reload": "workspace", "workflow": "workflow",
    "daemon": "daemon",
}


LINE_COMMAND_HELP_TOPICS = {
    "workspace": {
        "title": "workspace — main overview and navigation",
        "entries": [
            ("workspace", "leave the current menu and show the main overview"),
            ("status", "one-line overview summary"),
            ("info", "show the current selection"),
            ("next", "suggested next steps for where you are"),
            ("search listener", "search targets, listeners, modules, sessions, jobs, files, queue"),
            ("show targets", "show known targets"),
            ("show listeners", "show operator listeners"),
            ("show files", "show staged files and release artifacts"),
            ("show sessions", "show captured sessions"),
            ("show events", "show recent operator activity"),
            ("show modules", "browse runnable modules"),
            ("show modules service", "filter runnable service modules"),
            ("show modules verbose service", "include command lines for service modules"),
            ("modules service", "browse service modules; also modules daemon, modules target, modules operator"),
            ("refresh", "redraw the current console view"),
            ("reload", "reload config file without restarting"),
        ],
        "notes": [
            "`workspace` leaves the current menu or selection, returns to `grit[all]>`, and shows the main overview.",
            "It does not delete saved targets, profiles, sessions, staged files, or routes.",
            "`main`, `home`, and `root` also return to `grit[all]>` without printing the overview.",
            "Use `next` when you want suggested commands for where you are already working.",
        ],
    },
    "workflow": {
        "title": "workflow — probe, profile, serve, and staged files",
        "entries": [
            ("use listener probe", "open the probe menu"),
            ("listener probe start", "discover target details from any menu"),
            ("listener probe results", "review received probe data from any menu"),
            ("listener probe config", "update the active profile from any menu"),
            ("profiles", "inspect or switch the active target deployment profile"),
            ("listener serve", "after profile setup, stage a release artifact for the active profile"),
            ("listener serve start default", "after profile setup, stage a release artifact and start file-service"),
            ("deliver sample-file", "after staging, show commands to run on the target"),
            ("listener serve ssh start", "after profile setup, stage a reverse SSH payload and start file-service"),
            ("files", "review staged files and release artifacts plus commands to run on targets"),
        ],
        "notes": [
            "The probe discovers target details; the active profile carries those details into later release and listener commands.",
            "After `use listener probe`, the same probe actions are available as short commands: start, results, config.",
            "`listener serve` is available from anywhere after the active profile has target details.",
            "open probe menu: use listener probe",
            "discover target: listener probe start",
            "review probe data: listener probe results",
            "update active profile: listener probe config",
            "after profile setup: listener serve ssh start",
        ],
    },
    "show": {
        "title": "show — resource lists and current selection",
        "entries": [
            ("show targets", "list known targets"),
            ("show listeners", "list operator listeners"),
            ("show files", "list staged files and release artifacts"),
            ("show sessions", "list captured sessions"),
            ("show jobs", "list background jobs"),
            ("show routes", "list bridge routes"),
            ("show queue", "inspect queued commands"),
            ("show check-ins", "inspect target check-ins and pending work"),
            ("show events", "show recent operator activity"),
            ("show modules", "browse runnable modules"),
            ("show modules service", "filter runnable service modules"),
            ("show service modules", "browse service modules"),
            ("show daemon modules", "browse daemon modules"),
            ("show target modules", "browse target modules"),
            ("show operator modules", "browse operator modules"),
            ("show release", "review release artifacts and next steps"),
            ("show options", "show options for where you are and build config"),
            ("show context", "show the current selection"),
        ],
        "notes": [
            "Bare `show` lists supported resources; choose a resource to open it directly.",
            "Use `modules service`, `modules daemon`, `modules target`, or `modules operator` to browse module kinds.",
            "Use `complete show` to browse supported resources in terminals without tab completion.",
        ],
    },
    "targets": {
        "title": "targets — target list, pending work, and activity",
        "entries": [
            ("targets", "list known targets"),
            ("target lab-router", "inspect and select a target by label, id, or number"),
            ("use target ID", "select a target context by id"),
            ("use target lab-router", "select a target context by label"),
            ("use target 1", "select a target context by row number"),
            ("use N", "select a numbered result from search or list"),
            ("show events", "show the target activity feed"),
            ("check-ins", "show pending work for the current target"),
            ("interact", "show log paths and interaction commands for the current target or session"),
            ("interact SESSION", "show log paths and interaction commands for a session"),
            ("rename LABEL", "set a display label"),
            ("note TEXT", "add notes"),
            ("alias NAME", "set a short alias"),
            ("clear target", "deselect the current target context"),
        ],
        "notes": [
            "Target commands with an explicit target can be run from anywhere.",
            "After choosing a target, shortcuts such as `interact`, `check-ins`, `rename`, `note`, and `alias` use the current target.",
            "`target all`, `target clear`, or `clear target` returns to all targets.",
            "If you have not chosen a target, use `targets`, `target lab-router`, `use target ID`, or `use target 1` first.",
        ],
    },
    "listeners": {
        "title": "listeners — operator listeners",
        "sections": [
            (
                "Listener list and lifecycle",
                [
                    ("listeners verbose", "list listeners with detail"),
                    ("listener probe", "inspect and select the probe listener"),
                    ("listener ssh", "inspect and select the ssh listener"),
                    ("use listener probe", "choose the probe listener"),
                    ("start probe", "start the probe listener"),
                    ("start 1", "start listener row 1 from the listener list"),
                    ("start ssh", "start the ssh listener"),
                    ("start tls-shell", "start the tls-shell listener"),
                    ("start plain-shell", "start the plain-shell listener"),
                    ("start file-service", "start the file-service listener"),
                    ("stop probe", "stop the probe listener"),
                    ("stop 1", "stop listener row 1 from the listener list"),
                ],
            ),
            (
                "Probe listener",
                [
                    ("use listener probe", "open the probe menu"),
                    ("probe commands: ?", "show probe start, results, config, and paste commands"),
                ],
            ),
            (
                "Serve from active profile",
                [
                    ("listener serve", "after profile setup, stage a release artifact for the active profile"),
                    ("listener serve start default", "after profile setup, stage a release artifact and start file-service"),
                    ("listener serve ssh start", "after profile setup, stage reverse SSH payload and start file-service"),
                ],
            ),
            (
                "After selecting a listener",
                [
                    ("start", "start the current listener"),
                    ("options", "show current listener settings"),
                    ("info", "show current listener details"),
            ("show start", "show console and terminal shell command for starting the listener"),
            ("show stop", "show console and terminal shell command for stopping the listener"),
                    ("copy start", "copy the listener start command to clipboard"),
                    ("copy stop", "copy the listener stop command to clipboard"),
                ],
            ),
        ],
        "notes": [
            "From the listener list or root menu, use concrete commands such as `listener probe`, `start probe`, `start 1`, `stop probe`, or `stop 1`.",
            "After `listener probe` or `use listener probe`, use short controls such as `start`, `stop`, `options`, and `show start`.",
            "In the probe menu, `?` shows probe-specific start, results, config, and paste commands.",
        ],
    },
    "probe": {
        "title": "probe — target discovery listener",
        "sections": [
            (
                "Probe flow",
                [
                    ("start", "start the probe listener and show commands to run on the target"),
                    ("queue", "queue the probe command for the current target"),
                    ("commands", "print commands to run on the target"),
                    ("results", "show received probe results"),
                    ("config", "populate the active profile from the latest probe result"),
                    ("config 1", "populate the active profile from probe result row 1"),
                    ("config write-config ./grit-probe.conf", "export build config from probe data"),
                ],
            ),
            (
                "Manual command transfer",
                [
                    ("paste", "print serial or admin shell paste commands"),
                    ("paste copy", "copy serial or admin shell paste commands"),
                    ("paste base64", "print base64 serial or admin shell paste commands"),
                    ("paste base64 copy", "copy base64 serial or admin shell paste commands"),
                    ("script", "print probe.sh for manual copy and paste"),
                ],
            ),
            (
                "Probe result cleanup",
                [
                    ("clear", "preview clearing all probe results"),
                    ("clear 1", "preview clearing probe result row 1"),
                    ("clear all", "preview clearing all probe results"),
                    ("clear 1 confirm", "remove probe result row 1"),
                    ("clear all confirm", "remove all probe results"),
                ],
            ),
            (
                "Probe listener controls",
                [
                    ("start", "start the probe listener"),
                    ("stop", "stop the probe listener"),
                    ("options", "show probe listener settings"),
                    ("info", "show probe listener details"),
                    ("show start", "show console and terminal shell command for starting the listener"),
                    ("show stop", "show console and terminal shell command for stopping the listener"),
                    ("copy start", "copy the listener start command to clipboard"),
                    ("copy stop", "copy the listener stop command to clipboard"),
                ],
            ),
            (
                "After profile setup",
                [
                    ("listener serve", "after profile setup, stage a release artifact for the active profile"),
                    ("listener serve start default", "after profile setup, stage a release artifact and start file-service"),
                    ("listener serve ssh start", "after profile setup, stage reverse SSH payload and start file-service"),
                ],
            ),
        ],
        "notes": [
            "You are in the probe menu; the short commands above work here.",
            "Open this menu from anywhere with `use listener probe`.",
            "Here, use start, results, config, commands, paste, paste copy, or queue.",
            "`start` discovers target details; `config` writes those details to the active profile for later serve and release commands.",
            "open probe menu: use listener probe",
            "discover target: start",
            "review probe data: results",
            "update active profile: config",
            "after profile setup: listener serve ssh start",
        ],
    },
    "profiles": {
        "title": "profiles — active target deployment profile",
        "entries": [
            ("profiles", "list saved profiles and mark the active one"),
            ("profile", "show the active profile"),
            ("profile use lab-router", "set the active profile by name"),
            ("profile use N", "set the active profile by number"),
            ("profile create lab-router", "create a custom profile"),
            ("profile set operator-host 192.168.8.241", "edit the active profile"),
            ("profile clear", "stop using the active profile"),
            ("profile delete lab-router confirm", "delete a saved profile by name"),
            ("profile delete N confirm", "delete a saved profile by number"),
            ("profile from probe 1", "populate the active profile from probe result row 1"),
            ("use listener probe", "open the probe menu"),
            ("config", "in the probe menu, populate the active profile from the latest result"),
            ("config 1", "in the probe menu, populate the active profile from probe result row 1"),
            ("listener serve", "stage a release artifact using the active profile"),
            ("listener serve start default", "stage a release artifact and start file-service using the active profile"),
        ],
        "notes": [
            "Profiles are target deployment settings saved in your local operator workspace.",
            "Listener bind and operator-host settings are separate from target profiles; use `ip` to review or change them.",
            "The active profile is shared by release and listener workflows, so profile commands are available from anywhere.",
            "Custom profile fields include target name, target label, architecture, kernel baseline, release tuple, operator host, preferred payload, preferred transport, and notes.",
            "open probe menu: use listener probe",
            "update active profile: listener probe config",
            "after profile setup: listener serve ssh start",
        ],
    },
    "sessions": {
        "title": "sessions — captured shells and file transfers",
        "entries": [
            ("sessions", "list sessions"),
            ("sessions list", "list sessions"),
            ("sessions verbose", "list sessions with detail"),
            ("session sess-1", "inspect and select a session context by id"),
            ("session 1", "inspect and select a session context by row number"),
            ("use session sess-1", "select a session context by id"),
            ("use session 1", "select a session context by row number"),
            ("sessions interact 1", "show session inspection commands"),
            ("interact", "show log paths and interaction commands"),
            ("interact sess-1", "show log paths and interaction commands for a session"),
            ("view ./README.md", "view a local path in pager"),
            ("cat ./README.md", "print a local path"),
            ("sessions clear", "preview deletion of finished sessions with no saved activity"),
            ("sessions clear confirm", "delete finished sessions with no saved activity"),
            ("sessions clear all confirm", "delete every session record"),
            ("info", "show the current session context"),
            ("options", "show session paths and activity"),
            ("back", "go up one breadcrumb level"),
        ],
        "notes": [
            "command-queue sessions accumulate quickly — they're created per poll cycle.",
            "sessions clear removes ended/stopped sessions with no uploads, fetches, or artifacts.",
            "Inside a selected session prompt, short forms such as `info`, `options`, `interact`, and `back` act on that session.",
        ],
    },
    "files": {
        "title": "files — deliver to targets and retrieve from targets",
        "entries": [
            ("files", "list staged files and commands to run on targets"),
            ("stage ./grit sample-file", "stage a local file for deliver commands"),
            ("stage start ./grit sample-file", "stage a local file and start file-service"),
            ("deliver sample-file", "show commands to run on the target for a staged file"),
            ("deliver queue sample-file", "queue the staged-file command for the current target"),
            ("deliver start sample-file", "start file-service and show commands to run on the target"),
            ("release", "review release artifacts and next steps"),
            ("release stage by_device:gl-mt3000", "stage a release artifact by known device name"),
            ("release stage start by_device:gl-mt3000", "stage a release artifact and start file-service"),
            ("stamp sample-file operator-host 192.168.8.241", "stamp embedded runtime settings into a staged file or artifact"),
            ("stamp ./grit operator-host 192.168.8.241", "stamp embedded runtime settings into a local artifact path"),
            ("artifact stamp sample-file transport builtin", "stamp embedded runtime settings"),
            ("artifact stamp ./grit transport builtin", "stamp embedded runtime settings by path"),
            ("unstage NAME", "remove a staged file"),
            ("files clear", "preview removal of all staged files"),
            ("files clear confirm", "unstage every staged file"),
            ("view ./README.md", "view a local path in the configured pager"),
            ("cat ./README.md", "print a local path"),
            ("retrieve /etc/hosts", "generate a target-to-operator retrieval command"),
            ("retrieve queue /etc/hosts", "queue a target-to-operator retrieval command"),
            ("use listener probe", "open the probe menu"),
        ],
        "notes": [
            "`stage` and `deliver` are operator-to-target: the target requests a file staged by the operator.",
            "`retrieve` is target-to-operator: the target sends one of its files back to the operator.",
            "Use `stage start`, `deliver start`, or `release stage start` when the same command should start file-service.",
            "Probe discovery has its own context: use `use listener probe`, then `start`, `commands`, or `queue`.",
        ],
        "examples": [
            "stage ./grit grit  ->  deliver grit",
            "release stage by_device:gl-mt3000",
            "stage start ./grit grit",
            "stamp grit operator-host 192.168.8.241 zero-arg-mode rshell",
        ],
    },
    "artifact": {
        "title": "artifact — staged artifact inspection and runtime settings stamping",
        "entries": [
            ("artifact", "show staged artifacts and current release directory"),
            ("artifact info grit", "show embedded runtime settings for a staged artifact"),
            ("artifact info ./grit", "show embedded runtime settings for a local path"),
            ("stamp grit operator-host 192.168.8.241", "stamp embedded runtime settings into a staged file or artifact"),
            ("stamp ./grit operator-host 192.168.8.241", "stamp embedded runtime settings into a local artifact path"),
            ("stamp grit show", "show current stamped runtime settings"),
            ("stamp grit clear", "remove stamped runtime settings"),
            ("artifact stamp grit transport builtin", "stamp embedded runtime settings"),
            ("artifact stamp ./grit transport builtin", "stamp embedded runtime settings by path"),
            ("artifact show grit", "show stamped runtime settings"),
            ("artifact show ./grit", "show stamped runtime settings by path"),
            ("artifact clear grit", "clear stamped runtime settings"),
            ("artifact clear ./grit", "clear stamped runtime settings by path"),
        ],
        "notes": [
            "Artifact commands inspect or stamp local staged files; they do not run anything on the target.",
            "Use `files` or `deliver sample-file` when you want commands to run on the target for staged files.",
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
        "title": "release — target-matched artifact staging",
        "entries": [
            ("release", "review release artifacts and next steps"),
            ("release stage by_device:gl-mt3000", "stage a release artifact by known device name"),
            ("release stage start by_device:gl-mt3000", "stage a release artifact and start file-service"),
            ("release stage dist/releases/lab/bin/grit-target-full", "stage a specific local release artifact path"),
            ("release stage ssh start", "stage reverse SSH payload and start file-service using the active profile"),
            ("show release", "review release artifacts and next steps"),
            ("files", "show staged release artifacts after staging"),
            ("deliver grit", "show the command to run on the target"),
            ("deliver queue grit", "queue the staged-file command for the current target"),
        ],
        "notes": [
            "Release staging is operator-to-target: it selects a local release artifact and stages it for deliver commands.",
            "The active profile supplies default release tuple, device, and payload choices after probe `config` or `profile from probe N`.",
        ],
        "examples": [
            "release stage by_device:gl-mt3000",
            "release stage by_tuple_path:by-tuple/native/host/host/host",
            "release stage start grit-target-full",
        ],
    },
    "queue": {
        "title": "queue — commands, target check-ins, and results",
        "entries": [
            ("queue uname -a", "queue a shell command to run on the target; the current target scopes the command"),
            ("queue list", "review queued commands, target check-ins, and queue controls"),
            ("queue targets", "show target check-ins and pending work"),
            ("queue result ID", "inspect a queued command result by id"),
            ("queue result 1", "inspect the first queued command result"),
            ("queue clear", "preview clearing queued commands"),
            ("queue clear confirm", "delete every queued command"),
            ("check-ins", "show pending work for the current target"),
            ("retrieve queue /etc/hosts", "queue a target-to-operator retrieval command"),
            ("deliver queue sample-file", "queue the staged-file command for the current target"),
            ("listener probe queue", "queue the probe command for the current target"),
        ],
        "notes": [
            "Without a chosen target, `queue uname -a` would be available to any target that checks in.",
            "Queued shell commands run on the target when it checks in for queued work.",
            "Select a target first for target-scoped queue commands: `retrieve queue /etc/hosts`, `deliver queue sample-file`.",
            "To queue the probe for one target, run `targets`, `use target 1`, then `listener probe queue`.",
            "Queued work depends on the command-queue policy and target polling interval.",
        ],
    },
    "events": {
        "title": "events — operator event log browser",
        "entries": [
            ("events", "show the last 20 operator events"),
            ("events n 50", "show the last 50 matching events"),
            ("events service=file-service", "filter by service"),
            ("events event=opened", "filter by event name"),
            ("events level=warning", "filter by level"),
            ("events target=Console Router", "filter by target name or label"),
            ("events status=available", "filter by status"),
            ("events operation=probe", "filter by event operation"),
            ("events file=grit", "filter by file or request name"),
            ("events command=cq-123", "filter by queued command"),
            ("events job=job-123", "filter by background job"),
            ("events module=bridge", "advanced: filter by module id recorded in events"),
            ("events since 2h", "show events from the last 2 hours; also accepts 30m or 1d"),
            ("view event log", "open the full event log file"),
        ],
        "notes": [
            "Filters can be combined, for example `events service=console status=ready n 10`.",
            "Use `module=...` only for module ids shown in event details; use `modules` to browse runnable modules by name.",
            "Event summaries stay concise by default; open the full event log for command details.",
        ],
    },
    "search": {
        "title": "search — find and select console items",
        "entries": [
            ("search listener", "search targets, listeners, modules, sessions, jobs, files, routes, and queued work"),
            ("use 1", "select the first numbered result from the latest search or list"),
            ("complete listener", "show command completions when tab completion is unavailable"),
            ("history 50", "show recent commands if you meant to replay command history"),
        ],
        "notes": [
            "Search results are temporary. Run targets, listeners, files, or another search to replace the numbered result set.",
            "Use `resource ./commands.gritrc` for replayable command files; use `!1` or `repeat 1` for command history.",
            "find probe entries: search probe",
            "select first result: use 1",
            "search staged file names: search sample.txt",
        ],
    },
    "ip": {
        "title": "ip — choose operator network addresses",
        "entries": [
            ("ip", "list local IP candidates"),
            ("ip show", "list local IP candidates"),
            ("ips", "list local IP candidates"),
            ("ip host N", "set advertised operator address from the numbered IP list"),
            ("ip host IP", "set advertised operator address directly"),
            ("ip bind N", "set listener bind address from the numbered IP list"),
            ("ip bind IP", "set listener bind address directly"),
        ],
        "notes": [
            "`ip host` affects commands run on the target, such as probe scripts, staged-file commands generated by deliver, survey retrieval, and reverse access.",
            "`ip bind` affects where operator listeners accept connections.",
            "Use `ip` first when you want to pick from detected local interfaces instead of typing an address manually.",
            "list IPs: ip",
            "set advertised host: ip host 1",
            "bind listeners manually: ip bind 192.168.8.241",
        ],
    },
    "generated-commands": {
        "title": "commands — target commands to run on devices",
        "entries": [
            ("commands", "list commands to paste or run on a target"),
            ("commands list", "show the target-command table again"),
            ("copy N", "copy target command row N for pasting and save a fallback file"),
            ("commands copy N", "copy target command row N from the commands menu"),
            ("show start", "show console and terminal shell command for starting the current listener"),
            ("show stop", "show console and terminal shell command for stopping the current listener"),
            ("copy start", "copy the current listener start command"),
            ("copy stop", "copy the current listener stop command"),
        ],
        "notes": [
            "Target commands are things you paste or run on a target, such as probe scripts, staged-file commands generated by deliver, survey retrieval, and reverse access.",
            "Direction guide: console `retrieve` sends target files to the operator; console `deliver` sends staged operator files to the target.",
            "Open `commands` first when you want numbered rows for `copy N`.",
            "After copying, the console prints the saved file path and clipboard status.",
            "Listener `copy start` and `copy stop` only apply after selecting a listener context.",
        ],
        "examples": [
            "commands",
            "copy 1",
            "commands copy 2",
            "use listener probe",
            "copy start",
        ],
    },
    "start-stop": {
        "title": "start and stop — listener and route lifecycle",
        "entries": [
            ("start file-service", "start the file-service listener"),
            ("start ssh", "start the ssh listener"),
            ("start probe", "start the probe listener"),
            ("start N", "start a listener by number"),
            ("stop file-service", "stop the file-service listener"),
            ("stop probe", "stop the probe listener"),
            ("stop N", "stop a listener by number"),
            ("use listener probe", "open the probe menu before using short lifecycle commands"),
            ("start (listener menu)", "start the current listener"),
            ("stop (listener menu)", "stop the current listener"),
            ("route start web-hop", "start a bridge route by name"),
            ("route start N", "start a bridge route by number"),
            ("route stop web-hop", "stop a bridge route by name"),
            ("route stop N", "stop a bridge route by number"),
            ("start (route menu)", "start the current route"),
            ("stop (route menu)", "stop the current route"),
        ],
        "notes": [
            "At the root menu, use concrete listener names such as `start file-service`, `start probe`, `stop file-service`, or `stop probe`.",
            "Use `start N` or `stop N` after listing listeners when you prefer a number.",
            "After `use listener probe`, short `start` and `stop` act on that listener.",
            "Inside the route menu, short `start` and `stop` act on that route.",
            "root listener start: start file-service",
            "open listener menu: use listener probe",
            "current listener start: start",
            "route start by name: route start web-hop",
            "route stop by name: route stop web-hop",
        ],
    },
    "survey": {
        "title": "survey — full griTTYkit survey (requires griTTYkit deployed)",
        "entries": [
            ("survey",                                        "show received full survey results"),
            ("survey results",                                "list received full survey results"),
            ("survey config",                                 "generate config from most recent full survey"),
            ("survey config PATH",                            "generate config from a specific survey result"),
            ("survey config PATH write-config FILE",          "generate and save config"),
            ("survey preset PATH name NAME",                  "generate a reusable target preset (dry-run)"),
            ("survey preset PATH name NAME write-local",      "save preset under local/presets/targets/"),
        ],
        "notes": [
            "Full survey captures: libc, filesystem layout, writable paths, tools, network interfaces.",
            "Requires griTTYkit already deployed on the target.",
            "Run `commands`, copy the survey row with `copy N`, then run it on the target.",
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
            ("routes", "list bridge route profiles"),
            ("route ssh-home", "inspect a bridge route by name"),
            ("route 1", "inspect route row 1 from the route list"),
            ("use route ssh-home", "choose a route by name"),
            ("route add ssh-home 2222 127.0.0.1 22", "create a direct route profile"),
            ("route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222", "document the target-to-operator path"),
            ("route start ssh-home", "start a route by name"),
            ("route start 1", "start route row 1 from the route list"),
            ("route stop ssh-home", "stop a route by name"),
            ("route stop 1", "stop route row 1 from the route list"),
            ("route delete ssh-home", "preview route profile removal"),
            ("route delete ssh-home confirm", "remove a route profile"),
            ("start", "start the current route"),
            ("stop", "stop the current route"),
            ("info", "show current route details"),
            ("options", "show current route details"),
            ("routes verbose", "show route hop details and route start commands"),
        ],
        "notes": [
            "Short route commands omit the route name and only apply after `route ssh-home`, `route 1`, or `use route ssh-home`.",
            *ROUTE_HELP_LINES,
        ],
    },
    "daemon": {
        "title": "daemon — operator daemon and systemd controls",
        "entries": [
            ("daemon", "list operator daemon and systemd controls"),
            ("daemon verbose", "list daemon controls with command lines"),
            ("daemon status", "show daemon health and managed listener state"),
            ("daemon status preview", "preview the daemon status control"),
            ("daemon install confirm", "install the user systemd unit after confirmation"),
            ("daemon start confirm", "start configured listeners in the background after confirmation"),
            ("show daemon modules", "browse daemon controls"),
            ("use module Check operator daemon", "choose the daemon status control from the module list"),
            ("run", "run the current daemon control"),
            ("check", "preflight the current daemon control without running it"),
        ],
        "notes": [
            "Short commands apply after choosing a daemon control; concrete `daemon ...` commands work from anywhere.",
            "Add `preview` or `confirm` after a concrete daemon command, such as `daemon status preview`.",
        ],
    },
    "jobs": {
        "title": "jobs — background jobs",
        "entries": [
            ("jobs", "list managed background jobs"),
            ("job job-1", "inspect a background job by id"),
            ("job 1", "inspect a background job by row number"),
            ("jobs info job-1", "inspect a background job by id"),
            ("jobs info 1", "inspect a background job by row number"),
            ("jobs cancel job-1", "cancel a background job by id"),
            ("jobs cancel 1", "cancel a background job by row number"),
            ("use job job-1", "select a job context by id"),
            ("use job 1", "select a job context by row number"),
            ("run job", "start the current module as a background job"),
            ("info", "show the current job context"),
            ("options", "show current job details and shortcuts"),
            ("next", "show suggested job commands"),
            ("cancel", "cancel the current job when cancellation is supported"),
            ("back", "go up one breadcrumb level"),
        ],
        "notes": [
            "`run job` starts the current module as a background job; use job commands such as `jobs cancel job-1` to manage jobs.",
        ],
    },
    "build": {
        "title": "build — griTTYkit build configuration",
        "entries": [
            ("build", "show current guided build config"),
            ("build verbose", "show build config options and examples"),
            ("build set GRIT_RUNTIME_ROOT ./.grit", "set a build config field by key"),
            ("build set 16 ssh", "set a build config field by row number"),
            ("build unset GRIT_RUNTIME_ROOT", "clear a build config field by key"),
            ("build unset 16", "clear a build config field by row number"),
            ("set GRIT_RUNTIME_ROOT ./.grit", "set a guided build option here"),
            ("options", "show options for where you are and build config"),
            ("show options", "show options for where you are and build config"),
        ],
        "notes": [
            "`set` follows where you are when a target, listener, or module is selected; use `build set ...` for build config.",
            "Concrete build examples work from any menu: `build set GRIT_RUNTIME_ROOT ./.grit`, `build unset GRIT_RUNTIME_ROOT`.",
        ],
    },
    "modules": {
        "title": "modules — runnable console modules",
        "entries": [
            ("modules", "show module categories and counts"),
            ("modules service", "browse service modules"),
            ("modules daemon", "browse daemon modules"),
            ("modules target", "browse target modules"),
            ("modules operator", "browse operator modules"),
            ("modules verbose service", "include command lines for service modules"),
            ("use module Inspect bridge status", "choose a module by name"),
            ("use module N", "choose a module by number"),
            ("use N", "select a numbered module from the last module list"),
            ("info", "show current module state and summary"),
            ("options", "show inputs and related details"),
            ("show options", "show inputs and related details"),
            ("check Inspect bridge status", "preflight the current or named module without running it"),
            ("preview Inspect bridge status", "preview the current or named module run command"),
            ("run Inspect bridge status", "run the current or named module"),
            ("run job", "start the current module as a managed background job"),
            ("background", "start the current module as a managed background job"),
            ("back", "go up one breadcrumb level"),
        ],
        "notes": [
            "Command lines are hidden in filtered lists; run `modules verbose service` when you need them.",
            "Short `run`, `check`, `options`, and `info` act on the current module after `use module Inspect bridge status`.",
        ],
    },
    "console": {
        "title": "console — navigation and command files",
        "entries": [
            ("history 50", "show recent command history"),
            ("!!", "replay the previous command"),
            ("!1", "replay history entry 1"),
            ("repeat 1", "replay history entry 1"),
            ("resource ./commands.gritrc", "run console commands from a command file"),
            ("makerc ./last-session.gritrc", "save command history as a replayable command file"),
            ("complete listener", "show command completions"),
            ("search listener", "search targets, listeners, modules, sessions, jobs, files"),
            ("use 1", "select a numbered result from the last list or search"),
            ("main", "return to `grit[all]>` without printing the overview"),
            ("home", "return to `grit[all]>` without printing the overview"),
            ("root", "return to `grit[all]>` without printing the overview"),
            ("back", "go up one breadcrumb level"),
            ("quit", "quit from the root menu; use back or main first from submenus"),
            ("exit", "quit from the root menu; use back or main first from submenus"),
        ],
        "notes": [
            "`console` opens this help; use the listed commands without a `console` prefix.",
            "`back` follows the current breadcrumb; `main` returns directly to `grit[all]>`.",
            "Common commands: targets, listeners, routes, files, modules, complete listener.",
            "Named selection examples: use target lab-router, use listener probe, use route ssh-home, use module Inspect bridge status.",
            "Use `use 1` only after a list or search prints numbered rows.",
        ],
    },
    "aliases": {
        "title": "aliases — preferred forms and legacy aliases",
        "entries": [
            ("targets", "preferred; legacy alias accepted in command files: agents"),
            ("listeners", "preferred; legacy aliases accepted in command files: services, service"),
            ("routes", "preferred; legacy aliases accepted in command files: bridges, bridge"),
            ("queue", "preferred; legacy alias accepted in command files: mailbox"),
            ("check-ins", "preferred; legacy alias accepted in command files: mailbox"),
            ("stage LOCAL_PATH NAME", "preferred; legacy aliases accepted in command files: upload LOCAL_PATH NAME, serve-file LOCAL_PATH NAME"),
            ("deliver NAME", "preferred; legacy aliases accepted in command files: fetch NAME, deploy NAME"),
            ("retrieve PATH", "preferred; legacy alias accepted in command files: download PATH"),
            ("stamp NAME KEY=VALUE", "preferred; legacy aliases accepted in command files: trailer NAME KEY=VALUE, configure NAME KEY=VALUE"),
            ("release stage SELECTOR", "preferred; legacy alias accepted in command files: stage-release SELECTOR"),
            ("binary PATH NAME", "preferred; legacy alias accepted in command files: serve-binary PATH NAME"),
            ("binary start PATH NAME", "preferred; legacy alias accepted in command files: serve-binary start PATH NAME"),
            ("run Inspect bridge status", "preferred; legacy aliases accepted in command files: execute Inspect bridge status, exploit Inspect bridge status"),
            ("use target NAME", "preferred; legacy alias accepted in command files: useagent NAME"),
            ("use listener NAME", "preferred; legacy alias accepted in command files: uselistener NAME"),
            ("use route NAME", "preferred; legacy alias accepted in command files: useroute NAME"),
            ("use session ID", "preferred; legacy alias accepted in command files: usesession ID"),
            ("use module Inspect bridge status", "preferred; legacy alias accepted in command files: usemodule Inspect bridge status"),
        ],
        "notes": [
            "Legacy aliases stay accepted so older command files keep working.",
            "For interactive use, prefer the command shown in the left column.",
            "Use explicit selectors such as `use target lab-router`, `use listener probe`, `use route ssh-home`, `use session 1`, and `use module Inspect bridge status`.",
        ],
    },
}


def line_command_help_topic(topic):
    key = str(topic or "").strip().lower()
    if not key:
        return None
    canonical = LINE_COMMAND_HELP_ALIASES.get(key, key)
    entry = LINE_COMMAND_HELP_TOPICS.get(canonical)
    if entry:
        return entry
    head = key.split(None, 1)[0]
    if head and head != key:
        canonical = LINE_COMMAND_HELP_ALIASES.get(head, head)
        return LINE_COMMAND_HELP_TOPICS.get(canonical)
    return None


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
    sections = entry.get("sections")
    if sections:
        section_entries = [
            item
            for _, entries in sections
            for item in entries
        ]
        col = max(len(cmd) for cmd, _ in section_entries) + 2
        for idx, (section_title, section_items) in enumerate(sections):
            if idx:
                print("")
            print(f"{section_title}:")
            for cmd, desc in section_items:
                print(f"  {cmd:<{col}}{desc}")
    else:
        col = max(len(cmd) for cmd, _ in entry["entries"]) + 2
        for cmd, desc in entry["entries"]:
            print(f"  {cmd:<{col}}{desc}")
    if sections and entry.get("notes"):
        print("")
    for note in entry.get("notes") or []:
        print(f"  {note}")
    for i, ex in enumerate(entry.get("examples") or []):
        prefix = "  Example: " if i == 0 else "           "
        print(f"{prefix}{ex}")
