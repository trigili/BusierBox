#!/usr/bin/env python3
"""Run review-oriented grit-console UX audits.

This harness is intentionally not a pass/fail UX oracle. It fails for
infrastructure problems such as crashes, hangs, or missing artifacts, and writes
reviewable reports for operator-flow quality.
"""

import argparse
import datetime as dt
import json
import os
import pty
import re
import select
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

STALE_REPORT_PHRASES = (
    "confirm: delete confirm",
    "cleanup: queue clear, queue clear confirm",
    "check: listeners or events service=file-service",
    "global and submenu-local",
    "Global probe commands work anywhere",
    "review target command shape",
    "Run from this machine (SSH executes the target command)",
    "run files options to review file-service TLS",
    "run files options to change TLS",
    "run `?` there",
    "Run `use listener probe` anywhere",
    "Run `modules` to choose a different module",
    "Type `modules` to choose a different module.",
    "Run `commands` first when you want numbered rows",
    "Run `build` first to see row numbers",
    "run the listed commands without a `console` prefix",
    "type the listed commands without a `console` prefix",
    "Type `use listener probe` anywhere to return to this probe menu.",
    "No active profile yet; type profiles ? for profile setup.",
    "or type ? for help",
    "Console commands do not use -- flags; type ? to browse word commands such as confirm.",
    "REPL commands do not use dash flags; type ? to browse command forms.",
    "command form: queue <shell command to run on the target>",
    "Command form: queue <shell command to run on the target>",
    "advanced tuple selectors are hidden until a profile supplies target facts.",
    "target facts",
    "Selector examples below are syntax references for when you already know the selector.",
    "Use the selector examples below only when you already know the device name or artifact path.",
    "Known device or artifact path: use one of the selector examples below.",
    "selector example: release stage",
    "stage and start example: release stage start",
    "more selector examples:",
    "More selector examples appear after a profile has probe or device details.",
    "Run a list command or another search to replace the numbered result set",
    "Open a list view or run another search to replace the numbered result set",
    "replace results: open a list view or search again",
    "replace results: run another search or list command",
    "rshell        target-to-operator  operator listener",
    "rshell        target-to-operator  configured in artifact",
    "stamp an artifact or run listener serve ssh start, then rerun commands",
    "Back in this probe menu, run: results",
    "set transport: profile set transport ssh\n",
    "after staging: files, deliver NAME",
    "No staged artifacts yet; run release, then choose one of the selector examples below.",
    "survey ? for help",
    "or run profile from probe N",
    "copy N, commands copy N, back, commands ?",
    "copy N, commands copy N, back, help: commands ?",
    "copy command: copy N, commands copy N",
    "create: route add NAME LISTEN_PORT DEST_HOST DEST_PORT",
    "route add NAME LISTEN_PORT DEST_HOST DEST_PORT         create a direct route profile",
    "route add NAME LISTEN_PORT DEST_HOST DEST_PORT target:PORT=operator:PORT",
    "route start NAME                                       start a route by name",
    "route stop NAME                                        stop a route by name",
    "route start NAME       start a bridge route by name",
    "route stop NAME        stop a bridge route by name",
    "Inside `grit/.../route/NAME>`",
    "route delete NAME confirm                              remove a route profile",
    "stage: stage LOCAL_PATH NAME, stage start LOCAL_PATH NAME",
    "stage LOCAL_PATH NAME          stage a local file for target-side download",
    "stage start LOCAL_PATH NAME    stage a local file and start file-service",
    "deliver: deliver NAME, deliver start NAME, deliver queue NAME",
    "Example: stage start LOCAL_PATH sample-file",
    "Example: stage start ./grit sample-file",
    "next: stage ./grit sample-file, release, help: files ?",
    "deliver NAME, stage start LOCAL_PATH NAME, unstage NAME, files ?",
    "try: stage start LOCAL_PATH sample-file, files ?",
    "try: stage start LOCAL_PATH sample-file, help: files ?",
    "use N, route NAME, route N, route start NAME, route start N, routes ?",
    "Example: route add ssh-home 2222 127.0.0.1 22",
    "next: route add ssh-home 2222 127.0.0.1 22, routes verbose, help: routes ?",
    "try: route add ssh-home 2222 127.0.0.1 22, routes ?",
    "try: daemon status, daemon status preview, daemon verbose, help: daemon ?",
    "try: daemon status, daemon status preview, daemon verbose, daemon ?",
    "confirm selected action: daemon install confirm",
    "requires confirmation: daemon install confirm",
    "Example: daemon status",
    "Example preview: daemon status preview",
    "Put `preview` or `confirm` after a concrete command, for example `daemon status preview`.",
    "Example: build set 16 ssh",
    "Example: build unset 16",
    "Example: ip\n           ip host 1\n           ip bind 192.168.8.241",
    "Example: start file-service\n           use listener probe\n           start\n           route start web-hop\n           route stop web-hop",
    "queue result N, queue clear confirm, queue ?",
    "listener N, listener NAME, start N, stop N, listeners ?",
    "listener N, listener NAME, start N, stop N, help: listeners ?",
    "select: listener NAME, listener N, use listener NAME",
    "controls: start NAME, start N, stop NAME, stop N",
    "At the root menu, use `start NAME`, `start N`, `stop NAME`, or `stop N` for listeners.",
    "use N, sessions verbose, sessions ?",
    "use N, job ID, jobs cancel ID, jobs ?",
    "start with: targets, listeners, routes, sessions, modules, jobs, or ?",
    "suggest next actions for where you are",
    "suggested next actions for where you are",
    "workflow — probe, profile, serve, and target download",
    "workflow   probe, profile, serve, target download",
    "workflow ?       see the full probe, profile, serve, and target-download flow",
    "workflow — probe, profile, serve, and target-side download",
    "workflow   probe, profile, serve, target-side download",
    "workflow ?       see the full probe, profile, serve, and target-side download flow",
    "help first-run",
    "help TOPIC      show focused help",
    "TOPIC ?         same as help TOPIC",
    "stage a local file for target download",
    "queue target download",
    "staged-file target downloads",
    "so the target can download it",
    "run after download:",
    "complete --",
    "Completions for build set:\n  build set GRIT_TARGET_PRESET\n",
    "help: help ",
    "first result: service",
    "release ? for help",
    "build ? for help",
    "Run configured listeners in the background",
    "then ?                       show probe start, results, config, and paste commands",
    "listener probe         open the probe menu before using short lifecycle commands",
    "open probe discovery commands",
    "Direction guide: `put` and `push` send target data to the operator; `fetch` pulls staged files from the operator.",
    "Direction guide: console `retrieve` rows send target files to the operator (`put`/`push` on target); console `deliver` rows pull staged operator files to the target (`fetch` on target).",
    "then in probe menu: start, results, config",
    "from probe results: use listener probe",
    "discovery: use listener probe",
    "use listener probe  (populate profile from target details)",
    "deliver: deliver grit, deliver start grit, deliver queue grit",
    "select after sessions list: session ID, session N, use session ID, use session N",
    "open session: interact, sessions interact 1, view ./session.log",
    "select: job 1, jobs info 1",
    "control: jobs cancel 1",
    "use listener probe; in probe menu: start",
    "target discovery: use listener probe",
    "discover targets: use listener probe",
    "discover a target: use listener probe",
    "No queued commands yet; try a command to run on the target.",
    "more selector examples:\n  help: release ?\n",
    "sessions ?, listeners, files",
    "use N, use module NAME, modules service, modules daemon, modules target, modules operator, modules ?",
    "use listener probe; in probe menu: start, results, config; targets ?",
    "queue result N, queue COMMAND, queue ?",
    "queue result N, queue COMMAND, help: queue ?",
    "queue result N       inspect a queued command result by number",
    "queue result N, queue uname -a, help: queue ?",
    "queue clear confirm  remove all queued commands",
    "listener command-queue start, queue ?",
    "try: queue uname -a",
    "syntax: queue <shell command to run on the target>",
    "Example: queue uname -a",
    "try: queue uname -a, queue list, queue ?",
    "try: queue uname -a, queue list, help: queue ?",
    "queue --",
    "open: modules  |  select: use N  |  start: run job  |  help: jobs ?",
    "modules, use N, then run job, jobs ?",
    "modules, use N, run job, help: jobs ?",
    "Example: modules service, use 1, then run.",
    "Example by name: use module Inspect bridge status.",
    "background modules: modules, use module Inspect bridge status, use module N, run job",
    "help: sessions ?  |  start access: listeners  |  files",
    "open: interact, sessions interact ID, view PATH",
    "open selected session after selection: interact, sessions interact 1, view ./session.log",
    "select after sessions list: session ID, session N, use session ID, use session N",
    "open selected session: interact, sessions interact ID, view PATH",
    "view PATH                   view a local session path in pager",
    "cat PATH                    print a local session path",
    "next: info, interact, sessions verbose, view PATH, back",
    "raw log: options, then view PATH",
    "events event=NAME            filter by event name",
    "events target=TARGET_NAME    filter by target name or label",
        "events operation=TEXT        filter by event operation",
        "events operation=fetch       filter by event operation",
    "events job=JOB               filter by background job",
    "select: job ID, job N, jobs info ID",
    "control: jobs cancel ID, jobs cancel N",
    "requires confirmation: use daemon MODULE confirm",
    "requires confirmation: daemon MODULE confirm",
    "Narrow it: complete listener, complete files, complete run, or type ?.",
    "Narrow it: complete run SERVICE_OR_MODULE, modules, or show modules FILTER.",
    "Common commands: targets, listeners, routes, files, run MODULE.",
    "events module=MODULE",
    "Use `module=MODULE` when you want events for a specific console module.",
    "modules FILTER",
    "modules verbose FILTER",
    "check MODULE",
    "preview MODULE",
    "run MODULE",
    "Selection examples: use target lab-router, use listener probe, use route ssh-home, use session 1, use module Inspect bridge status.",
    "Selection examples: use target lab-router, use listener probe, use route ssh-home, use session 1, use module bridge:inspect-status.",
    "Selection examples: use target NAME, use listener NAME, use route NAME, use session ID, use module NAME.",
    "commands: history LIMIT, resource FILE, makerc FILE, complete PREFIX",
    "commands: history LIMIT, resource FILE, makerc FILE, complete listener",
    "history LIMIT    show recent command history",
    "resource FILE    run console commands from a command file",
    "makerc FILE      save command history as a replayable command file",
    "complete PREFIX  show command completions",
    "search TERM      search targets, listeners, modules, sessions, jobs, files",
    "search TERM                   search targets, listeners, modules, sessions, jobs, files, queue",
    "search TERM  find targets, listeners, sessions, files, modules, jobs",
    "commands: workspace, targets, listeners, routes, sessions, modules, search TERM",
    "choose: targets, listeners, routes, sessions, modules, jobs, or search TERM",
    "search: search TERM, use N",
    "safe inspection: ?, options, next, complete PREFIX",
    "safe inspection: ?, options, next, complete listener",
    "inspect safely: ?, options, next, complete PREFIX",
    "inspect safely: ?, options, next, complete listener",
    "add: queue COMMAND",
    "queue COMMAND        queue a shell command to run on any target that checks in",
    "queue COMMAND        queue a shell command to run on the current target",
    "profile create NAME  (create profile manually)",
    "profile create NAME                create a custom profile",
    "profile use NAME                   set the active profile by name",
    "profile set FIELD VALUE            edit the active profile",
    "profile delete NAME confirm        delete a saved profile by name",
    "artifact info PATH  (inspect a local file directly)",
    "artifact info PATH             show embedded runtime settings for a local path",
    "stamp PATH KEY=VALUE           stamp embedded runtime settings into a local artifact path",
    "artifact stamp PATH KEY=VALUE  stamp embedded runtime settings by path",
    "artifact show PATH             show stamped runtime settings by path",
    "artifact clear PATH            clear stamped runtime settings by path",
    "You can also inspect a local file directly with artifact info PATH.",
    "artifact info NAME             show embedded runtime settings for a staged artifact",
    "artifact info N                show embedded runtime settings by row number",
    "stamp NAME KEY=VALUE           stamp embedded runtime settings into a staged file or artifact",
    "artifact stamp NAME KEY=VALUE  stamp embedded runtime settings",
    "artifact show NAME             show stamped runtime settings",
    "artifact clear NAME            clear stamped runtime settings",
    "Use `files` or `deliver NAME` when you want commands to run on the target for staged files.",
    "artifact and release: artifact, artifact info NAME, release, release stage by_device",
    "commands: artifact, artifact info NAME, artifact info N, artifact info PATH, artifact show NAME",
    "target-side download: files, deliver NAME",
    "stamp grit-console operator-host HOST transport ssh",
    "artifact stamp grit-console operator-host HOST transport ssh",
    "choose HOST: run ip, then use ip host N or ip host IP",
    "\nreplay: resource ",
    "before target command: listener serve ssh start stages the reverse SSH artifact",
    "note: these values can come from the active profile, build config, or a setting here",
    "transport       not configured",
    "shell provider  not configured",
    "\n  none\n  No saved profiles match;",
    "\n  none\n  Console commands do not use -- flags;",
    "Help: daemon — systemd and init daemon modules",
    "daemon COMMAND",
    "use module COMMAND",
    "Daemon modules  (",
    "daemon MODULE",
    "Select a daemon module first to use short commands",
    "Put `preview` or `confirm` after the command",
    "Put `preview` or `confirm` after the module name",
    "note: `deliver` is the REPL command; `grit fetch` is the target-side pull command",
    "try: release stage by_device:DEVICE_NAME",
    "try: release stage by_device:gl-mt3000",
    "stage and start service: release stage start by_device:gl-mt3000",
    "stage by known device: release stage by_device:gl-mt3000",
    "stage and start file-service: release stage start by_device:gl-mt3000",
    "binary PATH NAME\n  binary start PATH NAME\n  binary no-start PATH NAME",
    "deliver NAME\n  deliver queue NAME\n  deliver start NAME",
    "unstage NAME\n  Run one of these commands.",
    "stamp NAME operator-host 192.168.8.241\n  stamp NAME transport builtin",
    "Example: use listener probe\n           start\n           results\n           config\n           listener serve ssh start",
    "Example: search probe\n           use 1\n           search sample.txt",
    "release stage by_device:DEVICE_NAME  (device name selector)",
    "release stage by_device:DEVICE_NAME        stage a release artifact by known device name",
    "release stage start by_device:DEVICE_NAME  stage a release artifact and start file-service",
    "release stage ARTIFACT_PATH                stage a specific local release artifact path",
    "device name selector: release stage by_device:DEVICE_NAME",
    "artifact path selector: release stage ARTIFACT_PATH",
    "path stage: release stage ARTIFACT_PATH",
    "commands: release, release stage by_device:DEVICE_NAME, release stage start by_device:DEVICE_NAME",
        "workspace  leave menu and print root dashboard",
        "leave the current menu and print the root dashboard",
        "leaves the current prompt and prints the root operator dashboard",
        "returned to root workspace",
        "already at root workspace",
        "returned to workspace",
    "No staged release artifact yet; choose one of the selector examples below.",
    "No staged artifacts yet; open release, then choose one of the selector examples below.",
)


SCENARIOS = [
    {
        "name": "probe-create-and-serve",
        "description": "Discover, configure, start, and inspect the probe listener.",
        "qemu": False,
        "commands": [
            "workspace",
            "next",
            "listeners",
            "?",
            "probe options",
            "use listener probe",
            "?",
            "start",
            "commands",
            "paste",
            "paste copy",
            "stop probe",
            "q",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Copy/paste quality"],
    },
    {
        "name": "local-artifact-delivery",
        "description": "Stage a local griTTYkit-like file and inspect commands to run on the target.",
        "qemu": False,
        "commands": [
            "files",
            "?",
            "stage start scripts/grit-console grit-console",
            "files",
            "?",
            "deliver grit-console",
            "artifact info grit-console",
            "stop file-service",
            "q",
        ],
        "required_markers": [
            "Files  (none staged)",
            "stage ./grit sample-file, release, help: files ?",
            "File staged for deliver commands:",
            "next: deliver grit-console",
            "Files  (1 staged)",
            "deliver grit-console, stage start ./grit sample-file, unstage grit-console, help: files ?",
            "deliver grit-console",
            "deliver queue grit-console",
            "deliver start grit-console",
            "stamp grit-console operator-host 192.168.8.241",
            "artifact stamp grit-console transport builtin",
            "unstage grit-console",
            "run options to review file-service TLS",
            "file service start requested by this command",
        ],
        "rubric_focus": ["Discoverability", "Directionality", "Noise"],
    },
    {
        "name": "profile-management",
        "description": "Create, edit, select, inspect, and delete an active deployment profile.",
        "qemu": False,
        "commands": [
            "profiles",
            "?",
            "profile create lab-router",
            "profile",
            "profile set operator-host 192.168.8.241",
            "profiles",
            "?",
            "options",
            "next",
            "profile use 1",
            "profile delete lab-router",
            "profile delete lab-router confirm",
            "profiles",
            "q",
        ],
        "required_markers": [
            "Profiles  (1 saved)",
            "profile use 1",
            "profile use lab-router",
            "profile delete lab-router confirm",
            "profile delete 1 confirm",
            "commands: profiles, profile, profile use lab-router, profile use 1, profile create lab-router, profile set operator-host 192.168.8.241",
            "cleanup: profile delete lab-router, then profile delete lab-router confirm",
            "cleanup by number: profile delete 1, then profile delete 1 confirm",
            "after target details: listener serve start default",
            "reverse SSH after target details: listener serve ssh start",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Reversibility"],
    },
    {
        "name": "ip-address-selection",
        "description": "Review local IP discovery, numbered address selection, and manual host/bind overrides.",
        "qemu": False,
        "commands": [
            "ip",
            "?",
            "options",
            "ip host 1",
            "ip bind 1",
            "listeners",
            "ip host 192.168.8.241",
            "ip bind 192.168.8.241",
            "listeners",
            "q",
        ],
        "required_markers": [
            "Local IPs:",
            "ip host N   advertise this IP in commands run on the target",
            "ip bind N   bind operator listeners to this IP",
            "If the address you need is missing, use ip host IP or ip bind IP directly.",
            "bind listeners manually: ip bind 192.168.8.241",
            "set GRIT_OPERATOR_SERVER_HOST=\"192.168.8.241\"",
            "set listen_host=\"192.168.8.241\"",
            "192.168.8.241:",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Error recovery"],
    },
    {
        "name": "target-selection",
        "description": "Review a populated target list, selected-target prompt, target help, options, next, and interaction guidance.",
        "qemu": False,
        "commands": [
            "targets",
            "?",
            "use target 1",
            "?",
            "options",
            "next",
            "interact",
            "clear target",
            "targets",
            "q",
        ],
        "required_markers": [
            "Targets  (1 total)",
            "lab-router",
            "use target N, target ID, target LABEL, * = current, help: targets ?",
            "lab-router  (router-1)",
            "target lab-router inspect and select a target by label, id, or number",
            "use target 1",
            "show log paths and interaction commands for the current target or session",
            "After choosing a target, shortcuts such as `interact`, `check-ins`, `rename`, `note`, and `alias` use the current target.",
            "current target:",
            "in this prompt: interact, queue uname -a, check-ins, show events, rename, note, alias",
            "delivery: stage start ./grit sample-file, listener serve start default, listener serve ssh start",
            "target filter cleared  —  showing all targets",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Consistency"],
    },
    {
        "name": "command-queue",
        "description": "Review empty queue guidance, target-scoped queueing, result inspection, and clear confirmation.",
        "qemu": False,
        "commands": [
            "queue",
            "?",
            "use target 1",
            "queue uname -a",
            "queue",
            "?",
            "options",
            "next",
            "queue result 1",
            "queue clear",
            "queue clear confirm",
            "queue",
            "q",
        ],
        "required_markers": [
            "No queued commands yet.",
            "Add command: queue uname -a",
            "Everything after `queue` is sent as the target shell command.",
            "Select a target first for target-scoped queue commands:",
            "grit[lab-router]> queue uname -a",
            "queued: cq-",
            "command: uname -a",
            "target: router-1 (lab-router)",
            "Next:",
            "queue result cq-",
            "queue list",
            "Queued commands  (1 total)",
            "queue result 1, queue clear confirm, help: queue ?",
            "queue list, queue uname -a, help: queue ?",
            "queue result 1       inspect the first queued command result",
            "queue uname -a       queue a shell command to run on the current target",
            "retrieve queue /etc/hosts  queue a target-to-operator retrieval command",
            "deliver queue sample-file  queue the staged-file command for the current target",
            "The current target scopes queued retrieve, deliver, and probe commands.",
            "Command result:",
            "summary: queued; waiting for target poll; result none",
            "1 queued command record(s) would be cleared",
            "Run: queue clear confirm",
            "cleared 1 queued command record(s)",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Reversibility"],
    },
    {
        "name": "session-selection",
        "description": "Review a populated session list, selected-session prompt, session help, options, and interaction guidance.",
        "qemu": False,
        "commands": [
            "sessions",
            "?",
            "use session 1",
            "info",
            "options",
            "next",
            "interact",
            "sessions clear",
            "back",
            "sessions",
            "q",
        ],
        "required_markers": [
            "Sessions  (1 total)",
            "sess-1",
            "use N, sessions verbose, help: sessions ?",
            "session sess-1",
            "use session sess-1",
            "use session 1",
            "sessions interact 1",
            "current session: sess-1",
            "in this prompt: info, options, interact, back",
            "also available: sessions verbose, sessions interact sess-1",
            "also available: sessions list, sessions verbose, sessions interact sess-1",
            "sessions clear confirm      delete finished sessions with no saved activity",
            "sessions clear all confirm  delete every session record",
            "Session interaction: sess-1",
            "view command: view",
            "session log:",
            "tail: tail -n 40",
            "No finished empty sessions to clear.",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Consistency"],
    },
    {
        "name": "job-selection",
        "description": "Review a populated job list, selected-job prompt, job help, options, and next guidance.",
        "qemu": False,
        "commands": [
            "jobs",
            "?",
            "use job 1",
            "info",
            "options",
            "next",
            "jobs info 1",
            "back",
            "jobs",
            "q",
        ],
        "required_markers": [
            "Jobs  (1 total)",
            "job-1",
            "use 1, job job-1, jobs info 1, help: jobs ?",
            "job job-1",
            "jobs info job-1",
            "use job job-1",
            "use job 1",
            "current job: job-1",
            "state: exited  |  module: package-artifact",
            "in this prompt: info, options, back",
            "also available: jobs, jobs info job-1",
            "Job: job-1",
            "cancel supported: no",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Consistency"],
    },
    {
        "name": "reverse-shell",
        "description": "Inspect and start a reverse shell listener, then review listener command forms.",
        "qemu": False,
        "commands": [
            "listeners",
            "next",
            "listener plain-shell",
            "next",
            "options",
            "show start",
            "start",
            "commands",
            "copy 8",
            "back",
            "options",
            "show stop",
            "stop plain-shell",
            "q",
        ],
        "required_markers": [
            "showing: listeners list",
            "commands: listeners, listener probe, listener 1, start probe, start 1, stop probe, stop 1",
            "current listener: plain-shell",
            "in this prompt: options, start, stop, show start, show stop, copy start, copy stop, back",
            "also available: listener plain-shell, start plain-shell, stop plain-shell, listeners verbose",
            "copy command: copy 8",
            "clipboard: yes",
            "restart: start plain-shell",
        ],
        "rubric_focus": ["Consistency", "Context clarity", "Reversibility"],
    },
    {
        "name": "file-directionality",
        "description": "Exercise operator-to-target staging and target-to-operator retrieval wording.",
        "qemu": False,
        "commands": [
            "files",
            "stage start {sample_file} ux-sample",
            "deliver ux-sample",
            "retrieve /etc/hosts",
            "retrieve queue /etc/hosts",
            "stop file-service",
            "q",
        ],
        "rubric_focus": ["Directionality", "Error recovery", "Copy/paste quality"],
    },
    {
        "name": "route-management",
        "description": "Create, select, inspect, and remove a bridge route profile.",
        "qemu": False,
        "commands": [
            "routes",
            "?",
            "route add ux-route {route_listen_port} 127.0.0.1 {route_dest_port}",
            "routes",
            "?",
            "use route 1",
            "?",
            "options",
            "delete",
            "delete confirm",
            "routes",
            "q",
        ],
        "required_markers": [
            "Routes  (1 total)",
            "use 1, route ux-route, route start ux-route, help: routes ?",
            "route ux-route",
            "route 1",
            "use route ux-route",
            "route start ux-route",
            "route delete ux-route",
            "current route ux-route",
            "confirm here: delete confirm",
            "from root menu: route delete ux-route confirm",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Reversibility"],
    },
    {
        "name": "console-command-tools",
        "description": "Exercise console help, history, completion, resource files, and makerc output.",
        "qemu": False,
        "commands": [
            "console",
            "?",
            "options",
            "complete resource",
            "history 5",
            "resource {resource_file}",
            "history 8",
            "makerc {makerc_file}",
            "q",
        ],
        "required_markers": [
            "Help: console — navigation and command files",
            "command files: resource ./commands.gritrc, makerc ./last-session.gritrc",
            "Completions for resource:",
            "resource ./commands.gritrc",
            "history",
            "resource ",
            "makerc ",
            "replay later: resource ",
        ],
        "rubric_focus": ["Discoverability", "Consistency", "Error recovery"],
    },
    {
        "name": "help-surface-sweep",
        "description": "Review top-level and submenu help surfaces for discoverability and context clarity.",
        "qemu": False,
        "commands": [
            "?",
            "workspace ?",
            "help start",
            "wat",
            "workflow",
            "options",
            "next",
            "?",
            "use listener probe",
            "wat",
            "?",
            "main",
            "targets",
            "?",
            "options",
            "profiles",
            "?",
            "next",
            "files",
            "?",
            "options",
            "queue",
            "?",
            "options",
            "release",
            "?",
            "artifact",
            "?",
            "sessions",
            "?",
            "options",
            "routes",
            "?",
            "options",
            "events",
            "?",
            "modules",
            "?",
            "options",
            "modules service",
            "use 1",
            "?",
            "options",
            "back",
            "jobs",
            "?",
            "daemon",
            "?",
            "survey",
            "?",
            "commands",
            "next",
            "?",
            "build",
            "build verbose",
            "?",
            "console",
            "?",
            "next",
            "options",
            "aliases",
            "?",
            "options",
            "back",
            "show ?",
            "main",
            "ip",
            "?",
            "options",
            "main",
            "search listener",
            "?",
            "options",
            "next",
            "q",
        ],
        "required_markers": [
            "Modules  (",
            "show module categories and counts",
            "overview: modules",
            "open service modules: modules service",
            "choose first module: use 1",
            "Command lines are hidden in filtered lists; run `modules verbose service` when you need them.",
            "listener probe start          discover target details from any menu",
            "discover target: listener probe start",
            "review probe data: listener probe results",
            "update active profile: listener probe config",
            "No stageable release artifacts found in this release.",
            "Build or unpack a release artifact, then rerun release.",
            "Help: aliases — preferred forms and legacy aliases",
            "preferred; legacy aliases accepted in command files: upload LOCAL_PATH NAME, serve-file LOCAL_PATH NAME",
            "For interactive use, prefer the command shown in the left column.",
            "Aliases:",
            "legacy aliases: accepted for older command files; use aliases ? to inspect",
            "Help: show — resource lists and current selection",
            "show listeners",
            "show events",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Consistency"],
    },
    {
        "name": "completion-surface",
        "description": "Review explicit completion output for root commands, subcommands, confirmations, and no-match recovery.",
        "qemu": False,
        "commands": [
            "complete",
            "complete complete",
            "complete start",
            "complete files",
            "complete modules",
            "complete check",
            "complete check bridge",
            "complete run",
            "complete retrieve",
            "complete build set",
            "complete listener serve",
            "complete listener serve ssh",
            "complete listener probe",
            "complete listener probe paste",
            "complete listener probe paste base64",
            "complete interact",
            "complete artifact",
            "complete binary",
            "complete deliver",
            "complete unstage",
            "complete stamp",
            "complete build set",
            "complete ip bind",
            "complete sessions clear",
            "complete sessions clear all",
            "complete queue clear",
            "complete profile delete",
            "q",
        ],
        "rubric_focus": ["Discoverability", "Consistency", "Error recovery"],
        "required_markers": [
            "run Inspect bridge status",
            "complete listener",
            "stage ./grit sample-file",
            "deliver sample-file",
            "files clear",
            "modules service",
            "modules operator",
            "check Inspect bridge status",
            "retrieve /etc/hosts",
            "retrieve queue /etc/hosts",
            "deliver queue sample-file",
            "binary start scripts/grit-console grit-console",
            "listener serve start default",
            "unstage sample-file",
            "stamp sample-file operator-host 192.168.8.241",
            "artifact info ./grit",
            "artifact stamp ./grit transport builtin",
            "interact target 1",
            "Preset names stage that payload; add start to also start file-service.",
            "ssh stages the reverse SSH preset; add start to also start file-service.",
            "build set GRIT_TARGET_PRESET mipsel-linux-4.x-musl",
            "Use a listed number, or type an address directly, for example ip bind 192.168.8.241.",
        ],
        "stale_markers": [
            "files stage",
            "files deliver",
            "files unstage",
            "artifact info\n",
            "artifact stamp\n",
            "artifact show\n",
            "artifact clear\n",
        ],
    },
]


def free_port(protocol="tcp"):
    sock_type = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, sock_type) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def timestamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def line_number_for(text, needle):
    if not needle:
        return None
    offset = text.find(needle)
    if offset < 0:
        return None
    return text.count("\n", 0, offset) + 1


def line_number_for_console_text(text, needle):
    """Return a line for console text, ignoring pasted heredoc/script bodies."""
    if not needle:
        return None
    heredoc_end = None
    heredoc_re = re.compile(r"<<-?\s*['\"]?(?P<end>[A-Za-z0-9_.-]+)['\"]?")
    for lineno, raw_line in enumerate(str(text or "").splitlines(), 1):
        line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw_line)
        stripped = line.strip()
        if heredoc_end:
            if stripped == heredoc_end:
                heredoc_end = None
            continue
        match = heredoc_re.search(line)
        if match:
            heredoc_end = match.group("end")
            continue
        if needle in line:
            return lineno
    return None


def line_number_for_entered_command(text, command):
    wanted = str(command or "").strip()
    if not wanted:
        return None
    prompt_re = re.compile(r"^grit\[[^\n]*>\s*(?P<cmd>.*)$")
    echoed_line = None
    for lineno, raw_line in enumerate(str(text or "").splitlines(), 1):
        line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw_line).strip()
        if line == wanted and echoed_line is None:
            echoed_line = lineno
        match = prompt_re.match(line)
        if match and match.group("cmd").strip() == wanted:
            return lineno
    if echoed_line is not None:
        return echoed_line
    return line_number_for(text, wanted)


def transcript_block_after(text, marker):
    value = str(text or "")
    marker_text = str(marker or "")
    start = value.find(marker_text)
    if start < 0:
        return ""
    next_prompt = value.find("\ngrit[", start + len(marker_text))
    if next_prompt < 0:
        return value[start:]
    return value[start:next_prompt]


def prompt_count(text):
    return len(re.findall(r"grit\[[^\n]+>", text))


def write_config(path, artifact_dir):
    state = artifact_dir / "server-state.json"
    staged = artifact_dir / "staged-files.json"
    sessions = artifact_dir / "sessions"
    operator_session = artifact_dir / "operator-session"
    bridge_profiles = artifact_dir / "bridge-profiles.json"
    build_config = artifact_dir / "build-config.json"
    cfg = {
        "listen_host": "127.0.0.1",
        "GRIT_OPERATOR_SERVER_HOST": "127.0.0.1",
        "GRIT_SSH_PORT": free_port(),
        "GRIT_TLS_SHELL_PORT": free_port(),
        "GRIT_PLAIN_SHELL_PORT": free_port(),
        "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
        "GRIT_COMMAND_QUEUE_PORT": free_port(),
        "GRIT_BRIDGE_PORT": free_port(),
        "GRIT_PROBE_PORT": free_port(),
        "GRIT_PROBE_TFTP_PORT": free_port("udp"),
        "GRIT_PROBE_FTP_PORT": free_port(),
        "GRIT_PROBE_DNS_PORT": free_port("udp"),
        "server_state": str(state),
        "staged_files": str(staged),
        "session_root": str(sessions),
        "operator_session_dir": str(operator_session),
        "bridge_profiles_file": str(bridge_profiles),
        "build_config": str(build_config),
    }
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cfg


def seed_target_selection_fixture(cfg_path, scenario_dir):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    operator_session = Path(str(cfg.get("operator_session_dir") or scenario_dir / "operator-session"))
    operator_session.mkdir(parents=True, exist_ok=True)
    target_doc = {
        "schema": 1,
        "targets": {
            "router-1": {
                "target_id": "router-1",
                "target_label": "lab-router",
                "label": "lab-router",
                "aliases": ["glinet"],
                "last_seen_at": "2026-06-28T16:00:00Z",
                "latest_activity_at": "2026-06-28T16:00:00Z",
                "latest_activity_service": "command-queue",
                "latest_activity_operation": "command_queue_poll",
                "latest_command_queue_poll_interval_sec": 60,
            },
        },
    }
    (operator_session / "targets.json").write_text(
        json.dumps(target_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def seed_session_selection_fixture(cfg_path, scenario_dir):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    session_root = Path(str(cfg.get("session_root") or scenario_dir / "sessions"))
    session_dir = session_root / "sess-1"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.log").write_text(
        "connected from 192.0.2.55\n$ uname -a\nLinux lab-router 5.10.176\n",
        encoding="utf-8",
    )
    (session_dir / "events.jsonl").write_text(
        json.dumps({
            "time": "2026-06-28T16:01:00Z",
            "event": "shell_connected",
            "service": "plain-shell",
        }) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session.json").write_text(
        json.dumps({
            "session_id": "sess-1",
            "service": "plain-shell",
            "state": "active",
            "remote": "192.0.2.55:49152",
            "started_at": "2026-06-28T16:00:00Z",
            "updated_at": "2026-06-28T16:01:00Z",
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def seed_job_selection_fixture(cfg_path, scenario_dir):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    jobs_path = Path(str(cfg.get("workbench_jobs_file") or scenario_dir / "operator-session" / "workbench-jobs.json"))
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = scenario_dir / "job-1.log"
    log_path.write_text("building package\nfinished successfully\n", encoding="utf-8")
    jobs_path.write_text(
        json.dumps({
            "schema": 1,
            "jobs": [{
                "id": "job-1",
                "action_id": "package-artifact",
                "state": "exited",
                "pid": "",
                "log_path": str(log_path),
                "started_at": "2026-06-28T16:00:00Z",
                "finished_at": "2026-06-28T16:02:00Z",
                "exit_status": 0,
            }],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


SCENARIO_SETUP = {
    "command-queue": seed_target_selection_fixture,
    "job-selection": seed_job_selection_fixture,
    "session-selection": seed_session_selection_fixture,
    "target-selection": seed_target_selection_fixture,
}


def run_console(commands, cfg_path, scenario_dir, timeout_sec):
    master, slave = pty.openpty()
    proc = None
    chunks = []
    stderr_text = ""
    try:
        proc = subprocess.Popen(
            [
                str(ROOT / "scripts" / "grit-console"),
                "--config", str(cfg_path),
            ],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERM": "dumb", "PAGER": "cat"},
        )
        os.close(slave)
        slave = -1
        time.sleep(0.25)
        script = "\n".join(commands) + "\nq\n"
        view = memoryview(script.encode("utf-8"))
        while view:
            written = os.write(master, view)
            view = view[written:]
        deadline = time.time() + timeout_sec
        while proc.poll() is None and time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunks.append(os.read(master, 65536).decode("utf-8", errors="replace"))
                except OSError:
                    break
        if proc.poll() is None:
            try:
                os.write(master, b"q\n")
            except OSError:
                pass
            stop_deadline = time.time() + 2
            while proc.poll() is None and time.time() < stop_deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunks.append(os.read(master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        stderr_text = proc.stderr.read() if proc.stderr else ""
        transcript = "".join(chunks)
        (scenario_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        (scenario_dir / "stderr.txt").write_text(stderr_text or "", encoding="utf-8")
        (scenario_dir / "commands.txt").write_text(
            "\n".join(commands) + "\n",
            encoding="utf-8",
        )
        return {
            "returncode": proc.returncode,
            "transcript": transcript,
            "stderr": stderr_text or "",
            "timed_out": proc.returncode is None,
        }
    finally:
        if slave != -1:
            os.close(slave)
        try:
            os.close(master)
        except OSError:
            pass


def scenario_observations(transcript, commands):
    observations = []
    stripped_commands = [
        str(command).strip()
        for command in commands
        if str(command).strip()
    ]
    entered_verbs = {
        command.split()[0].lower()
        for command in stripped_commands
    }
    help_command = next(
        (
            command
            for command in stripped_commands
            if command == "?" or command.endswith(" ?") or command.lower().startswith("help ")
        ),
        "",
    )
    if help_command:
        line = line_number_for_entered_command(transcript, help_command)
        observations.append({
            "label": "help used",
            "line": line if line is not None else 1,
            "message": "Operator asked for contextual help.",
            "needle": help_command,
        })
    patterns = [
        ("invalid selection", "not found", "Console reported a missing selection or resource."),
        ("target command", "Target command:", "Console generated a target-side command."),
        ("download options", "download options", "Console showed multiple target-side download options."),
        ("direction wording", "target-to-operator", "Console used explicit target-to-operator direction wording."),
        ("headless detail", "headless_command", "Console exposed generated headless command details."),
    ]
    for label, needle, message in patterns:
        line = line_number_for_console_text(transcript, needle)
        if line is not None:
            observations.append({
                "label": label,
                "line": line,
                "message": message,
                "needle": needle,
            })
    if entered_verbs.intersection({"back", "background"}):
        command_needle = next(
            command for command in commands
            if str(command).strip().split()[0].lower() in {"back", "background"}
        )
        line = line_number_for_entered_command(transcript, command_needle)
        observations.append({
            "label": "backtracking",
            "line": line if line is not None else 1,
            "message": "Operator used back/background navigation.",
            "needle": command_needle,
        })
    transcript_lower = transcript.lower()
    for stale_needle in (
        "global form:",
        "global forms:",
        "global command forms",
        "the global command `use listener probe` works from anywhere",
        "You can run `use listener probe` from anywhere.",
        "Select the probe listener with `use listener probe`; then the short commands above work in that prompt.",
        "In the probe menu, use start, results, config, commands, paste, or queue.",
        "manual form:",
        "manual: profile create NAME",
        "create manually: profile create NAME",
        "commands: profiles, profile, profile create NAME",
        "target -> operator",
        "operator -> target",
        "copy: copy ",
        "direct: use ",
        "use: use 1",
        "copy:  scp <(curl",
        "copy target command row N to the configured copy file and clipboard when available",
        "copy target command row N to the configured command-copy file and clipboard when available",
        "copy target command row N to the command-copy file and clipboard when available",
        "Copy the survey command row with `copy N`.",
        "After copying, the console prints the copy file path and clipboard status.",
        "After copying, the console prints the command-copy file path and clipboard status.",
        "No saved profiles match; run profiles to review them or profile create NAME to add one.",
        "No active profile yet; run profiles ? for profile setup.",
        "Use `start` when you want the file-service listener started by the same command.",
        "release stage by_tuple_path:by-tuple/mipsel/musl/4.x/mips32r2-24kc",
        "target/device",
        "IP/hostname",
        "profile/build",
        "autorun/recovery",
        "Delivery options (pick what the target has):",
        "Probe-specific commands are shown in `help listener probe`",
        "staged binaries and files",
        "staged binaries or artifacts",
        "staged binary or artifact",
        "Generated commands  (",
        "one-line workbench status",
        "show staged operator files and binaries",
        "redraw full workbench",
        "redraw the dashboard",
        "redraw the screen",
        "matching griTTYkit binary",
        "matching binary from the active profile",
        "matching binary from active profile",
        "review matching release artifacts",
        "matches  0 artifacts  0 devices  0 tuples",
        "release stage by_device:target-name",
        "binary build config",
        "binary build configuration",
        "using the commands family",
        "compatibility/API flag",
        "list target commands explicitly",
        "probe round trip",
        "modules    runnable modules, dry-run, run, background jobs",
        "modules                 browse runnable service, daemon, target, and operator modules",
        "modules service, modules verbose service, use n",
        "command lines are hidden in the default list; run `modules verbose service` when you need them.",
        "dry-run a named module",
        "dry-run the current module",
        "filter by target id or label",
        "filter by event status",
        "filter by queued command id",
        "filter by background job id",
        "filter by module name or id",
        "internal module id",
        "internal module ids",
        "run bridge:start-service",
        "run bridge:stop-service",
        "run command-queue:start-service",
        "run command-queue:stop-service",
        "run probe:start-service",
        "run probe:stop-service",
        "queue controls: ready 3 controls  needs input 1 control",
        "Queue command            needs input",
        "run a confirmation-required daemon module",
        "run a confirmed daemon module",
        "state guide: set configured; default automatic; choose requires a value; fixed locked",
        "state guide: set means configured; default is automatic; choose needs input; fixed is locked",
        "state guide: set is configured; default uses automatic value; choose needs a value; fixed is locked",
        "choose pick a value",
        "affects built artifacts or payload contents",
        "affects target runtime behavior after explicit artifact use",
        "affects explicit reverse-access behavior",
        "affects explicit opt-in command queue behavior",
        "\n  service process id:",
        "\n  process id:",
        "\n  service log:",
        "\n  log file:",
        "\n  stopped service process id:",
        "\n  stopped process id:",
        "serial/admin shell",
        "serial/admin-shell",
        "admin-shell",
        "profile not set",
        "\n  prompt: grit[",
        "\n  Event log: view /",
        "Event log: view operator-session/events.jsonl",
        "view operator-session/events.jsonl",
        "\n  sources: files, listener probe, listeners, survey",
        "\n  here:",
        "\n  from anywhere:",
        "artifact submenu form:",
        "artifact submenu form for",
        "reference form:",
        "placeholders in the reference form",
        "returned to main workspace",
        "already at main workspace",
        "probe workflow",
        "probe and discovery:",
        "use listener probe  open probe setup",
        "listener probe         inspect and select the probe listener before using short lifecycle commands",
        "Start here:\n    listener probe start",
        "listener serve      use the active profile to stage a release artifact",
        "target download: listener serve",
        "No results yet — run: listener probe start",
        "paste: listener probe paste",
        "after it runs, use: listener probe results",
        "listener probe results  — after running any of the above",
        "results  — after running any of the above",
        "After it runs, use:",
        "probe upload failed",
        "probe result upload failed",
        "policy: valid",
        "events event=upload                       filter by event name",
        "events operation=staged-fetch             filter by event operation",
        "polling disabled",
        "polling off until the check-in listener starts",
        "when it polls the command queue",
        "events service=workbench",
        "workbench_opened",
        "workbench_console_next_shown",
        "service=workbench status=ready",
        "Confirm?",
        "not running  yes",
        "Service       Transport                Command",
        "target-to-operator  direct",
        "target discovery    direct",
        "the full forms still work from anywhere",
        "Full listener commands written",
        "Current listener controls:",
        "Current listener controls omit",
        "example: listener probe start",
        "start it with: listener probe start",
        "confirmation: not required",
        "background: not supported",
        "policy details: execution metadata-only",
        "filter by detail status",
        "filter by detail operation",
        "filter by staged/request name",
        "events request_name=grit",
        "events module_id=module",
        "use `module_id=module`",
        "events command_id=cq-123",
        "events job_id=job",
        "command_id=id",
        "job_id=id",
        "Event summaries hide automation commands by default",
        "Generated commands stay in verbose module lists and event details by default.",
        "include automation commands",
        "list daemon modules with automation commands",
        "next: workspace, targets, listeners, routes, sessions, modules",
        "next: workspace, targets, listeners, routes, sessions, show categories",
        "commands: workspace, targets, listeners, routes, sessions, show categories",
        "workspace  overview, status, info, search, next",
        "show categories               summarize",
        "Core commands work anywhere: targets, profiles, listeners, files, routes, sessions, jobs.",
        "use module NUMBER       choose a module by number",
        "use N, use module NAME, use module N, modules verbose, modules ?",
        "modules service/daemon/target/operator",
        "legacy compatibility alias; prefer",
        "Accepted aliases remain for scripts",
        "Preferred forms: targets, listeners, routes, files, run MODULE",
        "Current forms: targets, listeners, routes, files, run MODULE",
        "aliases    legacy command names and preferred forms",
        "show tab-style completions for dumb terminals",
        "old muscle memory",
        "canonical forms",
        "aliases    old names and current forms",
        "Help: aliases — old names and current REPL forms",
        "Help: aliases — old names and current forms",
        "preferred; script alias",
        "preferred; script aliases",
        "script aliases:",
        "script aliases remain accepted",
        "showing: compatibility aliases",
        "next: ? help",
        "create manually: profile create NAME\n  help: workflow ?",
        "Old names still work in scripts; interactive help uses the current command names.",
        "workflow: use listener probe, start, results, config",
        "workflow sequence: use listener probe, start, results, config",
        "workflow sequence: use listener probe, then start, results, config, listener serve",
        "workflow: use listener probe, then start, results, config",
        "start/results/config",
        "start               after selecting probe, discover a target",
        "config              after selecting probe, populate a profile from results",
        "start               in probe context, discover a target\n  config",
        "From another prompt, run `use listener probe` first; then use start, results, config, delivery, paste, or queue.",
        "In the probe menu, use start, results, config, delivery, paste, or queue.",
        "in probe menu     run start, results, and config",
        "in probe menu                run start, results, and config",
        "events target=target-name",
        "stage start path/to/local-file sample-file",
        "release stage path/to/release-artifact",
        "listener serve               stage a release artifact for the active profile",
        "listener serve start PRESET  stage a release artifact and start file-service for the active profile",
        "listener serve ssh start     stage a reverse SSH payload and start file-service",
        "after config: listener serve, listener serve start PRESET",
        "after config: listener serve start PRESET, listener serve ssh start",
        "after config: listener serve, listener serve start default",
        "after config: listener serve start default, listener serve ssh start",
        "reverse SSH after config: listener serve ssh start",
        "serve: listener serve, listener serve start PRESET",
        "serve: listener serve start PRESET, listener serve ssh start",
        "reverse SSH: listener serve ssh start",
        "target-side download: files, deliver NAME",
        "target-side download: files, deliver grit",
        "Profiles and listener serve remain available from anywhere.",
        "No targets yet; select probe first, then run start, results, and config.",
        "No targets yet. Use listener probe, then run start, results, and config.",
        "No targets yet. Use listener probe, then start, results, and config.",
        "No targets yet; use listener probe, then start, results, and config.",
        "No targets yet; run use listener probe, then start, results, and config.",
        "No targets yet.\n  open probe menu: use listener probe\n  discover target: start",
        "No profiles yet.\n\nNext:\n  open probe menu: use listener probe\n  discover target: start",
        "No target check-ins yet.\n  start check-in listener: listener command-queue start\n  open probe menu: use listener probe\n  discover target: start",
        "To match release artifacts to a target:\n    open probe menu: use listener probe\n    discover target: start",
        "profiles ?  (profile setup)\n    open probe menu: use listener probe\n    discover target: start",
        "No sessions yet.\n  shell access: listener plain-shell start or listener ssh start\n  open probe menu: use listener probe\n  discover target: start",
        "set transport: set 4 ssh; profile default: profile set transport ssh\n  open probe menu: use listener probe\n  discover target: start",
        "config                             after selecting probe, populate from the latest result",
        "config N                           after selecting probe, populate from a numbered result",
        "profile from probe N",
        "from probe results: use listener probe; then run config",
        "No targets yet. Use listener probe to discover a target, then run config.",
        "use listener probe, queue targets, targets ?",
        "Select a target first for retrieve queue PATH and deliver queue NAME.",
        "Select a target first for `retrieve queue PATH` and `deliver queue NAME`.",
        "Queueing the probe command also needs a selected target.\nSelect probe first: use listener probe\nThen queue it: queue",
        "Queueing the probe command also needs a selected target.\nSelect probe first: `use listener probe`.\nThen queue it: `queue`.",
        "queue it: queue",
        "select target: use target N",
        "To queue the probe for one target, select a target, run `use listener probe`, then run `queue`.",
        "To queue the probe for one target, run `targets`, `use target 1`, `use listener probe`, then `queue`.",
        "this queues the probe command for the selected target",
        "open probe menu: use listener probe\n  in probe menu: queue",
        "Select a target first to use retrieve queue PATH, deliver queue NAME, or use listener probe, then queue.",
        "Select a target first to use `retrieve queue PATH`, `deliver queue NAME`, or `use listener probe` then `queue`.",
        "target-side download: retrieve queue TARGET_PATH, stage start LOCAL_PATH NAME, deliver queue NAME",
        "Queueing the probe command also needs a selected target: use listener probe, then queue.",
        "Queueing the probe command also needs a selected target: `use listener probe`, then `queue`.",
        "select probe: use listener probe",
        "select a target, select probe, then run `queue`",
        "use listener probe, then queue",
        "active profile: profiles, profile, or use listener probe then config",
        "create one manually or fill it from probe results",
        "create one manually or populate one from probe results",
        "empty/manual profile",
        "Manual profile fields include",
        "Next:\n  use listener probe\n  config\n  profile create NAME",
        "Next:\n  use listener probe\n  start\n  results\n  config",
        "Next:\n  use listener probe\n  then start\n  then results\n  then config",
        "then: start, results, config",
        "then: start, results",
        "then: config",
        "then: queue",
        "from probe results: use listener probe, then config",
        "from probe results: use listener probe, then start, results, config",
        "discovery: use listener probe, then start, results, config",
        "probe flow: use listener probe, then start, results, config",
        "target discovery: use listener probe, then start",
        "Queue actions",
        "queue actions:",
        "review queued commands, target check-ins, and queue actions",
        "To match release artifacts to a target:\n    use listener probe\n    then start\n    then results\n    then config",
        "To match release artifacts to a target:\n    use listener probe\n    start\n    results\n    config",
        "To match release artifacts to a target:\n    use listener probe\n    config",
        "config                        after selecting probe, populate the active profile",
        "start               after selecting probe, serve probe.sh and print target-side commands",
        "start                        after selecting probe, serve probe.sh and print target-side commands",
        "start               after `use listener probe`, serve probe.sh and print target-side commands",
        "start                        after `use listener probe`, serve probe.sh and print target-side commands",
        "start                        after `use listener probe`, start probe listener and show target-side commands",
        "start                        start the probe listener and show target-side probe commands",
        "run                          start the probe listener",
        "config                       after `use listener probe`, populate the active profile from the latest result",
        "Probe-specific commands are shown after `use listener probe`",
        "start               after `use listener probe`, start probe listener and show target-side commands",
        "results             after a target runs probe.sh, review probe results",
        "config              populate the active profile from probe results",
        "config                       after selecting probe, populate the active profile from the latest result",
        "help workflow       see the full probe, profile, serve, and target-download flow",
        "help workflow       see the full probe, profile, serve, and deliver flow",
        "help workflow       see probe, profile, serve, and deliver",
        "workflow   probe, profile, serve, deliver",
        "delivery: files, deliver NAME",
        "delivery: listener serve",
        "old name; use",
        "old file command; use",
        "old artifact command; use",
        "old release command; use",
        "old binary command; use",
        "old run command; use",
        "old selection command; use",
        "targets  (none)\n  (none)\n\n  use target n",
        "targets  (none)\n  (none)",
        "files  (none staged)\n  (none)",
        "routes  (none)\n  (none)",
        "target check-ins  (none)\n  (none)",
        "Start the check-in listener or run probe delivery",
        "queue retrieve, deliver, or probe delivery",
        "probe-command delivery",
        "queue shortcuts",
        "Queue shortcuts",
        "command queue shortcut",
        "Server listener settings remain in local/server-config.json.",
        "probe, deliver, retrieve, and reverse-access commands",
        "commands    — list target-side reverse-access commands",
        "target-side commands such as probe, deliver, retrieve, and reverse access",
        "target-side commands such as probe scripts, staged-file delivery, survey retrieval, and reverse access",
        "set GRIT_OPERATOR_SERVER_HOST IP",
        "set listen_host IP                manually set the listener bind address",
        "set GRIT_OPERATOR_SERVER_HOST from the numbered IP list",
        "state: set=configured  default=auto default  choose=needs choice",
        "states: set configured, default uses automatic value, choose needs a value, fixed locked",
        "  1  1    grit_target_preset",
        "  1  3    grit_payload_preset",
        "jobs  (none)\n  (none)\n\n  use n, job id",
        "jobs  (none)\n  (none)",
        "survey results  (0 received)\n  (none)",
        "Next: type `commands`, then copy the full-survey retrieval row to the target.",
        "Next: open `commands`, then copy the full-survey retrieval row to the target.",
        "Next: run `commands`, then copy the full-survey retrieval row to the target.",
        "Copy the row whose command starts with: ./grit survey retrieve",
        "The commands list fills in the current operator host and file-service port.",
        "modules, use module name, run job, jobs ?",
        "modules, then use n, run job, jobs ?",
        "job n           inspect a background job by number",
        "info            show the current job context",
        "options         show current job details and shortcuts",
        "next            show suggested job commands",
        "session id                  inspect and select a session context",
        "sessions clear confirm      remove finished empty sessions",
        "sessions clear all confirm  remove all sessions",
        "target name       inspect and select a target by label, id, or number",
        "use target n      select a target context by number",
        "route name                                             inspect and select a route context",
        "select a module context by name",
        "select a module context by number",
        "select a daemon module context",
        "select a module prompt by name",
        "select a module prompt by number",
        "select a daemon module prompt",
        "select a listener prompt",
        "select a route prompt",
        "inspect and select a route prompt",
        "select a route context",
        "show the current route context",
        "show inputs and related context",
        "Profiles are target/deployment context",
        "Use listener, target, profile, or module prompts when setting those contexts.",
        "build set KEY VALUE",
        "build set ROW VALUE",
        "build unset KEY",
        "build unset ROW",
        "set KEY VALUE        set a build config field from this build prompt",
        "set ROW VALUE        set a build config field by row from this build prompt",
        "Use listener, target, profile, or module prompts when setting those areas.",
        "leave context first",
        "opens this help context",
        "show current context and build options",
        "follows the current context",
        "show the current prompt context",
        "show — resource lists and current context",
        "Console context:",
        "Current context: workspace",
        "outside-console shell command",
        "context-sensitive suggested commands",
        "suggest next steps for the current prompt",
        "show help for the current prompt",
        "prompt workflow",
        "prompt profiles",
        "returned to modules context",
        "returned to listeners context",
        "returned to routes context",
        "short commands above work in that context",
        "run: delete confirm",
        "also: route delete",
        "run: route delete",
        "run targets, then use target N or use target NAME; if no targets are listed, use listener probe, then start, results, config",
        "if no targets are listed: use listener probe, then start, results, config",
        "set transport: profile set transport ssh, or use listener probe, then start, results, config",
        "discover a target: use listener probe, then start, results, config",
        "No target check-ins yet. Run listener command-queue start, or use listener probe, then delivery.",
        "No target check-ins yet.\n  check-ins: listener command-queue start",
        "target check-ins: listener command-queue start",
        "route start name/n                                     start a route",
        "profile use n                      set the active profile by number",
        "profile set key value              edit the active profile",
        "profile set preferred_payload_preset ssh-operator",
        "requires confirmation: no",
        "confirm before run: no\n  background job: no\n  commands: check, run, run dry-run, run confirm",
        "commands: check, run, run dry-run",
        "workflow type: service lifecycle",
        "state: ready\n  readiness: ready to run",
        "run hint:",
        "recent events: filter events by service",
        "process: pid",
        "stopped process: pid",
        "full command: route delete",
        "run confirm  run a confirmation-required module",
        "profile clear                      clear the active profile selection",
        "Artifact workspace",
        "open probe context",
        "open probe discovery context",
        "open probe listener context",
        "show current listener context",
        "show probe listener context",
        "redraw dashboard without leaving the current context",
        "redraw dashboard and keep your current prompt",
        "reprints the root operator dashboard and keeps your current prompt",
        "refreshes this view and keeps your current prompt",
        "refreshes this view without changing context",
        "stage and serve a local file",
        "stage and serve a release artifact",
        "listener serve start preset        stage and serve a release artifact using the active profile",
        "release stage ssh start       stage reverse ssh payload using the active profile",
        "deliver name                  show the command to run on the target",
        "deliver queue name            queue delivery for the current target",
        "staged: none\n  next:\n    artifact info n",
        "staged: none\n  next:\n    release",
        "artifact info name             inspect embedded runtime config details for a staged artifact",
        "artifact info n                inspect embedded runtime config details by row number",
        "stamp name key=value           stamp embedded runtime config into a staged binary or artifact",
        "artifact clear name            clear stamped runtime config",
        "embedded runtime config:",
        "embedded runtime config details",
        "deliver name                   show commands to run on the target for a staged file",
        "unstage name                   remove a staged file",
        "files clear confirm            remove all staged files",
        "retrieve target_path           generate a target-to-operator retrieval command",
        "retrieve queue target_path     queue a target-to-operator retrieval command",
        "queue command        queue a target-side shell command; the current target scopes delivery",
        "select a target first to pin delivery",
        "queue result n       inspect a queued command result by number",
        "queue clear confirm  remove all queued commands",
        "run job         start the current background-capable module as a job",
        "Next: modules operator, use module Build/package selected artifact, run job.",
        "choose module: use module Build/package selected artifact",
        "use module Build/package selected artifact",
        "No background jobs yet. Open `modules operator`, choose `Build/package selected artifact`, then type `run job` from that module menu.",
        "No jobs yet; open `modules operator`, choose `Build/package selected artifact`, then type `run job` from that module menu.",
        "No background jobs yet. Run `modules`, choose a module that supports background jobs, then run `run job` from that module menu.",
        "No jobs yet; run `modules`, choose a module that supports background jobs, then run `run job` from that module menu.",
        "No background jobs yet. Run `modules`, choose a module that can run in the background, then run `run job` from that module prompt.",
        "No jobs yet; run `modules`, choose a background-capable module, then run `run job` from that module prompt.",
        "No background jobs yet. Select a background-capable module, then run it as a job.",
        "No background jobs yet. Select a module that can run in the background, then run it as a job.",
        "Select a background-capable module before using `run job`.",
        "modules         browse background-capable modules",
        "use module NAME select a background-capable module",
        "current module is not background-capable",
        "no current background-capable module",
        "retrieve queue path  queue a target-to-operator retrieval command",
        "deliver queue name   queue delivery for the current target",
        "survey config                             generate config from most recent full survey",
        "survey preset path name name              generate a reusable target preset",
        "set key value        set a target, listener, module, or guided build option",
        "run                    run the current daemon module",
        "check                  dry-run the current daemon module",
        "daemon status dry-run",
        "run MODULE dry-run",
        "check                  preview the current daemon module without running it",
        "repl: run",
        "show repl and shell command",
        "show start       show repl and shell command for starting the current listener",
        "copy start       copy the current listener start command",
        "operator/server running grit-console",
        "unscoped record",
        "workspace, overview",
        "status, summary",
        "mailbox targets      show target mailbox records",
        "show queued targets and mailbox discovery",
        "target list, select, mailbox, activity feed",
        "command queue, mailbox, results",
        "options, next, sessions, queue, mailbox, back",
        "mailbox           show pending work for the current target",
        "commands: queue COMMAND, retrieve queue TARGET_PATH, mailbox, stage start LOCAL NAME, deliver queue NAME",
        "mailbox pending ",
        "Mailbox  (",
        "Target mailbox  (",
        "Show mailbox",
        "Start mailbox listener",
        "Stop mailbox listener",
        "Run `commands` if you want a copyable retrieval command",
        "start the selected listener",
        "show selected listener settings",
        "show selected listener context",
        "select probe listener context",
        "These short commands act on the selected module.",
        "Help: search — find and select console resources",
        "routes, and queue records",
        "service  command-queue:inspect-status",
        "service  command-queue:start-service",
        "service  command-queue:stop-service",
        "GRIT_RSHELL_TRANSPORT       none",
        "GRIT_RSHELL_SHELL_PROVIDER  (not set)",
        "set shell provider: set GRIT_RSHELL_SHELL_PROVIDER auto",
        "ip, ip show, ips",
        "target-commands     list commands to paste or run on a target",
        "commands list, commands show",
        "options, show options",
        "run job, background",
        "!!, !N, repeat N",
        "main, home, root",
        "back, background",
        "clear current module context",
        "quit, exit",
        "Legacy show aliases remain accepted for scripts",
        "Legacy file aliases remain accepted for scripts",
        "Legacy trailer aliases remain accepted for scripts",
        "Legacy `trailer` and `configure` aliases remain accepted for scripts",
        "Legacy `stage-release` remains accepted for scripts",
        "Old show names still work in scripts",
        "Old file command names still work in scripts",
        "Old artifact-stamping names still work in scripts",
        "Old `trailer` and `configure` names still work in scripts",
        "trailer  (2 fields)",
        "runtime trailer defaults",
        "trailer override categories",
        "Old `stage-release` still works in scripts",
        "Old command names still work in scripts; interactive help uses the current command names.",
        "start / stop",
        "run, check",
        "options, show options",
        "commands, copy N",
        "profile, profiles",
        "release, release stage SELECTOR",
        "release stage start SELECTOR",
        "routes, route print",
        "jobs, jobs info ID, job ID",
        "jobs cancel ID, kill, cancel",
        "sessions, sessions list",
        "  target command:",
        "target-side retrieval command",
        "target-side retrieval commands",
        "target delivery commands",
        "policy details:",
        "target pickup",
        "result upload yes",
        "enable command queue polling for target pickup",
        "generated target-side commands",
        "target-side commands generated from current console state",
        "Generated target-side commands",
        "raw generated probe.sh script",
        "open the raw JSONL event log",
        "raw JSONL view",
        "Summaries hide generated commands by default",
        "live under the operator session",
        "delivery no  result upload",
        "delivery: queue record only",
        "Delivery from active profile:",
        "print target commands",
        "show target probe commands",
        "serve                     stage a matching binary from the active profile",
        "serve start PRESET        stage and serve a matching binary from the active profile",
        "serve ssh start           stage reverse SSH payload from the active profile",
        "release stage ssh start       stage reverse ssh payload using the active profile",
        "profile flow: listener probe config",
        "profile defaults: profiles, profile, listener probe config",
        "profile defaults: profiles, profile, use listener probe then config",
        "For target-matched artifacts:",
        "file service started by this command",
        "file service is starting\n  check: listeners or events service=file-service",
        "file service is starting; run listeners or events service=file-service to check readiness",
        "file service is starting; run listeners to check readiness",
        "startup requested; run listeners or events service=",
        "Route model: the target connects to LPORT on the operator",
        "Route model: the target connects to LISTEN_PORT on the operator",
        "DEST_HOST:DEST_PORT is the endpoint reachable from the machine running grit-console.",
        "Hop examples use labels such as target:PORT, jump:PORT, and operator:PORT.",
        "HOP syntax:",
        "multi-hop: route add NAME LPORT DEST_HOST DEST_PORT FROM=TO",
        "route add NAME LISTEN_PORT DEST_HOST DEST_PORT FROM=TO",
        "Optional hop notation: FROM=TO",
        "hop: FROM=TO",
        "wait for command-queue polling",
        "no profiles yet.\n\nnext:\n  profile use n",
        "profiles context\n  commands: profiles, profile, profile use name, profile use n",
        "profiles context",
        "commands context",
        "survey context",
        "events context",
        "console context",
        "search context",
        "listeners list context",
        "routes list context",
        "sessions list context",
        "jobs list context",
        "modules list context",
        "files context",
        "artifact context",
        "release context",
        "build context",
        "Next:\n  profile use N\n  listener probe config",
        "Next:\n  listener probe config",
        "listener probe serve is deprecated.\nUse:\n  listener probe config",
        "\"listener probe config\"",
        "listener probe config         populate",
        "listener probe config N       populate",
        "listener probe config write-config FILE",
        "config write-config FILE",
        "listener probe config                  ",
        "listener probe config N                ",
        "after `listener probe config`",
        "listener probe clear                  ",
        "listener probe clear N                ",
        "listener probe clear all              ",
        "listener probe clear N confirm        ",
        "listener probe clear all confirm      ",
        "Run: listener probe clear",
        "or use probe data: listener probe config",
        "Bare `show` prints usage",
        "profile: none - run listener probe config",
        "full commands:",
        "current module: none",
        "execution supported: no",
        "run targets, then use target NAME or use target N",
        "\n  run targets\n  select: use target N or use target NAME",
        "then use target N or use target NAME",
        "select target: use target N or use target NAME",
        "select: use target NAME, use target N",
        "target NAME       inspect and select a target by label, id, or number",
        "`target NAME`",
        "select: route NAME, route N, use route NAME",
        "select: use 1, use module bridge:inspect-status",
        "  select: use module bridge:inspect-status",
        "select: use module Inspect bridge status, use module N",
        "if no targets are listed, use listener probe, start, results, config",
        "probe path: use listener probe; run start, results, config",
        "then run start, results, config",
        "retrieve /etc/hosts\r\nselect a target before retrieve queue; run targets",
        "select a target before retrieve (target-to-operator);",
        "select a target before retrieve queue (target-to-operator);",
        "Select a target first for retrieve (target-to-operator).",
        "Select a target first for retrieve queue (target-to-operator).",
        "Select a target first for retrieve; the target sends the file back to the operator.\n  list targets: targets\n  select from list: use target 1\n  if you know the label: use target lab-router\n  open probe menu: use listener probe\n  discover target: listener probe start",
        "Select a target first for retrieve queue; the target sends the file back to the operator.\n  list targets: targets\n  select from list: use target 1\n  if you know the label: use target lab-router\n  open probe menu: use listener probe\n  discover target: listener probe start",
        "select a target before deliver queue (operator-to-target);",
        "select a target before probe queue (target-side probe command);",
        "deliver shows target-side delivery commands; select a target before deliver queue NAME",
        "deliver shows commands to run on the target; select a target first to queue the target-side download with deliver queue NAME",
        "files        show staged files and delivery commands",
        "Select a target first to use retrieve or queued file delivery.",
    "retrieve TARGET_PATH, retrieve queue TARGET_PATH",
    "retrieve TARGET_PATH        show a target-to-operator retrieval command",
    "retrieve queue TARGET_PATH  queue target-to-operator retrieval",
        "deliver queue NAME          queue target-side download after staging a file",
        "deliver queue NAME after staging a file",
        "run on the target; the target pulls this staged file from the operator",
        "direction: run this on the target to pull the staged file from the operator",
        "direction: run this on the target to pull the staged binary from the operator",
        "direction: run this on the target to pull the staged artifact from the operator",
        "choose one; each command pulls this staged file from the operator",
        "choose one; each command pulls this staged binary from the operator",
        "choose one; each command pulls this staged artifact from the operator",
        "wait until file-service is listening before running target pull commands",
        "run after pull:",
        "note: `deliver` is the REPL command; `grit fetch` is the target-side pull command",
        "Direction guide: `put` and `push` send target data to the operator; `fetch` pulls staged files from the operator.",
        "Direction guide: console `retrieve` rows send target files to the operator (`put`/`push` on target); console `deliver` rows pull staged operator files to the target (`fetch` on target).",
        "reverse-access listeners",
        "inspect-artifact: embedded payload trailer missing",
        "inspect-artifact exited",
        "file-service: no recorded pid",
        "plain-shell: no recorded pid",
        "probe: no recorded pid",
        "file service already starting",
        "file service start recorded; run listeners if delivery fails",
        "startup recorded; run listeners or events service=",
        "startup recorded; listener is not confirmed ready yet",
        "script command:",
        "script forms",
        "navigation, history, scripts, completion",
        "console — navigation, command files, and aliases",
        "quit from root; leave the current prompt first",
        "use target/listener/route/session/module",
        "inspect/select",
        "artifact/release:",
        "replayable script files",
        "resource script",
        "script file path",
        "run console commands from a file",
    "automation files: resource FILE, makerc FILE",
        "Completions for resource:\n  resource FILE\n",
        "Completions for makerc:\n  makerc FILE\n",
        "start command:\n  scripts/grit-console",
        "stop command:\n  scripts/grit-console",
        "from the probe menu",
        "from the probe menu, serve probe.sh",
        "stopped (configured starting)",
        "stopped (configured listening)",
        "file service not started by this command",
        "unknown command: wat; run ? to show listeners help",
        "unknown command: wat; run ? to show probe help",
        "unknown command: wat; run ? to show help topics",
        "unknown command: wat; type ? to show probe help",
        "unknown command: wat; type ? to show help topics",
        "unknown command: wat; type ?, options, or next to recover",
        "unknown command: wat; type ?, options, or next to recover from probe context",
        "Probe commands appear in the probe menu after `use listener probe`; type `?` there.",
        "grit[all]> help listener probe\nHelp: listeners",
        "shortcuts after selecting a listener",
        "full commands work from anywhere",
        "workflow   probe-to-payload path",
        "probe-to-payload flow",
        "* = selected",
        "selected route ",
        "selected target ",
        "operator daemon workflow module:",
        "run selected listeners in the background",
        "no selected background-capable",
        "no selected module",
        "selected module runner is unavailable",
        "unknown workbench job:",
        "background-capable workbench module",
        "workbench module is not background-capable",
        "action_id=...",
        "current workbench state",
        "Open the workbench scoped to this target",
        "build/workbench option",
        "global workbench options",
        "guided build/workbench options",
        "target fetch commands",
        "target fetch command",
        "target-side command:",
        "target command that fetches",
        "stage a local file for target retrieval",
        "files — staging and serving files to targets",
        "explicit target fetch",
        "target fetch files",
        "stage release artifact for target fetch",
        "Target fetch options:",
        "deliver prints commands the target runs to fetch it",
        "list or copy generated target commands",
        "\n  stage local name, binary start path name, files ?",
        "\n  deliver name, stage local name, unstage name, files ?",
        "runnable operator workflows",
        "runnable operator workflow modules",
        "runnable workflow modules",
        "include generated run commands",
        "daemon modules with generated run commands",
        "deliver shows target-side commands",
        "review target command shape",
        "generated start commands",
        "run targets, then target NAME, use target ID, use target LABEL, or use target N",
        "use target NAME, use target N, or target NAME",
        "run targets, then use N, use target NAME, or target NAME",
        "sessions  (none)\n  (none)",
        "sessions  (none)\n  (none)\n\n  use n, sessions verbose, sessions ?",
        "No sessions yet. Start a shell listener, run `use listener probe`, then `start`, or start command-queue check-ins.",
        "No sessions yet; start a shell listener, run `use listener probe`, then `start`, or start command-queue check-ins.",
        "No sessions yet. Start a listener, use listener probe, then start, or run listener command-queue start.",
        "No sessions yet; start a listener, use listener probe, then start, or run listener command-queue start.",
        "target discovery: use listener probe\n  then: start\n  target check-ins:",
        "transport       not selected",
        "shell provider  not selected",
        "use listener probe then start",
        "use listener probe then queue",
        "use listener probe then delivery",
        "help probe                   show probe start, results, config, and paste commands",
        "No background jobs yet. Select a module, then run it as a job.",
        "Select a module first to use short commands such as `info`, `options`, `check`, `run`, and `run job`.",
        "After deploying griTTYkit, run on the target:",
        "After deploying griTTYkit, run this on the target:",
        "grit survey retrieve --host OPERATOR_IP --port FILE_SERVICE_PORT",
        "Replace OPERATOR_IP and FILE_SERVICE_PORT with the file service values.",
        "Next: type `commands`, then copy the full-survey retrieval row to the target.",
        "Next: run commands, then copy the full-survey retrieval row to the target.",
        "Copy the row whose command starts with: ./grit survey retrieve",
        "The commands list fills in the current operator host and file-service port.",
        "OPERATOR_IP and FILE_SERVICE_PORT are placeholders; run `commands` for a filled-in command.",
        "Run `commands` for a copyable retrieval command with the current operator host and port.",
        "Start a listener, run probe",
        "start a listener, run probe",
        "routes  (none)\n  (none)\n\n  use n, route name",
        "using generated default",
        "affects generated artifacts or payload contents",
        "manifest and runtime config metadata",
        "build internal griTTYkit core",
        "review recommendations and artifact details",
        "list detected release artifact recommendations",
        "show release recommendations and artifact metadata",
        "0 recommendations  0 artifacts",
        "Recommendations  (",
        "show workbench modules",
        "serve-binary start scripts/grit-console",
        "serve-binary start LOCAL NAME",
        "binary start LOCAL NAME",
        "next: stamp NAME KEY=VALUE",
        "next: stamp grit-console KEY=VALUE",
        "also works: artifact stamp grit-console KEY=VALUE",
        "from anywhere: artifact stamp NAME KEY=VALUE",
        "from anywhere: artifact stamp",
    "No queued commands yet; try: queue COMMAND",
    "No queued commands yet; try the example below.",
    "Syntax: queue COMMAND",
    "syntax: queue COMMAND  (shell command to run on the target)",
    "Form: queue followed by a shell command",
    "form: queue followed by a shell command",
    "Without a chosen target, `queue COMMAND` is available to any target that checks in.",
    "No bridge routes yet. Use the example below to create one.",
    "No routes yet; use the example below to create one.",
        "next: profiles\n  next: use listener probe\n  next: profile create NAME",
        "search: search TERM\n  select: use N\n  safe inspection: ?, options, next, complete listener",
        "select: use N\n  safe inspection: ?, options, next, complete listener",
        "commands: search listener, use N",
        "commands: search TERM, use N\n  inspect safely: ?, options, next, complete listener",
    "replace results: targets, listeners, files, or search TERM",
    "current module is stale; commands: show modules, search TERM, back",
        "profile set payload ssh-operator",
        "ssh-operator payload",
        "old module command; use",
        "print the start command",
        "-O ./ux-sample.txt",
        "-o ./ux-sample.txt",
        "Current listeners: probe-http, probe-tftp, probe-ftp, probe-dns",
        "operator IP used in commands to run on the target",
        "operator IP used in probe command",
        "operator IP used in TFTP command",
        "operator IP used in FTP command",
        "operator IP used in DNS command",
        "Receive-only file service. Accepts target-initiated PUT/POST uploads.",
        "Waiting for file upload/fetch",
        "timeout waiting for file upload/fetch",
        "target upload/fetch still requires",
        "operator choice recommended",
        "operator workflow modules",
        "options, info, run, stop, show start, show stop, copy start, copy stop, back",
        "options, info, run, show start, copy start, back",
        "console command: run",
        "options, info, start, stop, show start, show stop",
        "set KEY VALUE, set N VALUE, build, back",
        "set KEY VALUE, set N VALUE, ips, ip bind N, ip bind IP, build, back",
        "set N VALUE",
        "choose bind IP: ips, ip bind N, ip bind IP",
        "set ROW VALUE, set KEY VALUE, ips, ip bind N, ip bind IP, build, back",
        "bind IP list: ips, ip bind N, ip bind IP",
        "advertised host for commands run on the target: ip host N, ip host IP",
        "listener bind address: ip bind N, ip bind IP",
        "use:\n    ip host n\n    ip host ip\n    ip bind n\n    ip bind ip",
        "daemon/systemd modules",
        "daemon/systemd module",
        "background workflow jobs",
        "select a workflow module",
        "daemon/systemd workflows",
        "           listener probe\n           copy start",
        "clear target and module context",
        "clear current target/module context",
        "show current target/module/listener/build options",
        "show target/module/listener/build options",
        "  flow: service-lifecycle",
        "  reason: run-now",
        "  workflow: operator-daemon",
        "background ready",
        "operator-daemon       background ready",
        "ready for background",
        "run service:",
        "Use a completion as typed, or add a space and run complete again for subcommands.",
        "confirm required",
        "systemd-user-service  confirm required",
        "selected-context commands",
        "selected-listener command:",
        "selected-listener commands:",
        "selected-target command:",
        "selected-target commands:",
        "selected-route command:",
        "selected-route commands:",
        "selected-session command:",
        "selected-session commands:",
        "selected-session form:",
        "selected-module command:",
        "selected-module commands:",
        "selected-job command:",
        "selected-job commands:",
        "context command:",
        "selected-target",
        "selected-listener",
        "selected-route",
        "selected-session",
        "selected-module",
        "selected-job",
        "current workflow: none",
        "grit[all]/module/bridge:inspect-status>",
        "`workspace` clears the current prompt context, returns to `grit[all]>`, and prints the dashboard.",
        "`workspace` clears the current target or submenu and shows the root operator dashboard.",
        "Root prompt dashboard. `workspace` returns to grit[all]> and prints this view.",
        "Start here:\n    use listener probe  open the probe menu\n    discover target: listener probe start",
        "Workflow:\n  open probe menu: use listener probe\n  discover target: start",
        "showing: workflow guide\n  open probe menu: use listener probe\n  discover target: start",
        "Help: workflow — probe, profile, serve, and staged files\n\n  use listener probe            open the probe menu\n  start                         in the probe menu, discover target details\n  results                       in the probe menu, review received probe data\n  config                        in the probe menu, update the active profile\n  profiles                      inspect or switch the active target deployment profile\n  listener serve                after profile setup, stage a release artifact for the active profile\n  listener serve start default  after profile setup, stage a release artifact and start file-service\n  deliver sample-file           after staging, show commands to run on the target\n  listener serve ssh start      after profile setup, stage a reverse SSH payload and start file-service\n  files                         review staged files and release artifacts plus commands to run on targets\n  The probe discovers target details; the active profile carries those details into later release and listener commands.\n  Probe commands appear in the probe menu after `use listener probe`; run `?` there.\n  `listener serve` is available from anywhere after the active profile has target details.\n  open probe menu: use listener probe\n  discover target: listener probe start",
        "target scope: all targets\n  commands: workspace, targets, listeners, routes, sessions, modules, search listener\n  open probe menu: use listener probe\n  discover target: listener probe start",
        "target scope: all targets\n  commands: workspace, targets, listeners, routes, sessions, modules, search listener\n  open probe menu: use listener probe\n  discover target: start",
        "go to the root prompt and print the dashboard",
        "without printing the dashboard",
        "selected workflow: none",
        "selected target: all",
        "selected module:",
        "selected listener:",
        "selected job:",
        "service:bridge:inspect-status  —  ready  |  inspect bridge status",
        "ready: ready to run",
        "readiness: run-now",
        "category: inspect",
        "workflow: service-lifecycle",
        "workflow: service lifecycle",
        "Workflow              Status            Attached  Confirm",
        "Area                  Status            Attached  Confirm",
        "Status       Confirm",
        "Managed  Confirm",
        "ready for background  no       daemon start confirm",
        "ready for background  no       needed",
        "ready as job  no       daemon start confirm",
        "ready as job  no       needed",
        "confirm required      no       needed",
        "Process ID",
        "id: service:bridge:inspect-status",
        "module: service:bridge:inspect-status",
        "run operator-daemon-start",
        "run operator-daemon-status",
        "run systemd-user-install",
        "run configure-binary",
        "run resolve-target",
        "run package-artifact",
        "label: inspect bridge status",
        " tls  pid",
        "  pid ",
        "manual profile keys include target_id",
        "requires file-service tls=no",
        "  state: configured\n  active:",
    ):
        local_global_line = line_number_for(transcript_lower, stale_needle)
        if local_global_line is not None:
            observations.append({
                "label": "stale help taxonomy",
                "line": local_global_line,
                "message": "Help still uses stale or internal wording instead of plain command guidance.",
                "needle": stale_needle,
            })
            break
    return observations


def scenario_summary(scenario, scenario_dir, cfg_path, result, rendered_commands):
    transcript = result["transcript"]
    stderr_text = result["stderr"]
    hard_failures = []
    if result["returncode"] not in (0, None):
        hard_failures.append(f"console exited {result['returncode']}")
    if "Traceback" in transcript or "Traceback" in stderr_text:
        hard_failures.append("traceback present")
    if not transcript.strip():
        hard_failures.append("empty transcript")
    if "listener is active, but the saved service state is not marked listening" in transcript:
        hard_failures.append("unrelated active listener warning in transcript")
    for marker in scenario.get("required_markers") or []:
        if str(marker) not in transcript:
            hard_failures.append(f"missing required marker: {marker}")
    if scenario["name"] == "completion-surface":
        root_completion_block = transcript_block_after(transcript, "Completions for root:")
        root_completion_lines = {
            line.strip()
            for line in root_completion_block.splitlines()
            if line.strip()
        }
        for command in ("files", "modules", "quit"):
            if command not in root_completion_lines:
                hard_failures.append(f"root completion hid primary command: {command}")
        for alias in ("home", "root", "exit", "background", "interact", "set", "unset"):
            if alias in root_completion_lines:
                hard_failures.append(f"root completion advertised alias: {alias}")
        for command in ("start", "stop"):
            if command in root_completion_lines:
                hard_failures.append(f"root completion advertised bare lifecycle command: {command}")
        complete_completion_block = transcript_block_after(transcript, "Completions for complete:")
        complete_completion_lines = {
            line.strip()
            for line in complete_completion_block.splitlines()
            if line.strip()
        }
        for command in ("complete listener", "complete build set"):
            if command not in complete_completion_lines:
                hard_failures.append(f"complete completion omitted example: {command}")
        listener_serve_completion_block = transcript_block_after(transcript, "Completions for listener serve:")
        listener_serve_completion_lines = {
            line.strip()
            for line in listener_serve_completion_block.splitlines()
            if line.strip()
        }
        if "listener serve start default" not in listener_serve_completion_lines:
            hard_failures.append("listener serve completion omitted explicit default start form")
        if "listener serve start" in listener_serve_completion_lines:
            hard_failures.append("listener serve completion advertised ambiguous bare start form")
        interact_completion_block = transcript_block_after(transcript, "Completions for interact:")
        interact_completion_lines = {
            line.strip()
            for line in interact_completion_block.splitlines()
            if line.strip()
        }
        if "interact target 1" not in interact_completion_lines:
            hard_failures.append("interact completion did not advertise a concrete target example")
        if "interact agent" in interact_completion_lines:
            hard_failures.append("interact completion advertised old agent wording")
        modules_completion_block = transcript_block_after(transcript, "Completions for modules:")
        modules_completion_lines = {
            line.strip()
            for line in modules_completion_block.splitlines()
            if line.strip()
        }
        for command in ("modules service", "modules daemon", "modules target", "modules operator"):
            if command not in modules_completion_lines:
                hard_failures.append(f"modules completion omitted category: {command}")
        if any(":" in line for line in modules_completion_lines if line.startswith("modules ")):
            hard_failures.append("modules completion exposed module ids before narrowing")
        check_completion_block = transcript_block_after(transcript, "Completions for check:")
        check_completion_lines = {
            line.strip()
            for line in check_completion_block.splitlines()
            if line.strip()
        }
        if "check Inspect bridge status" not in check_completion_lines:
            hard_failures.append("check completion omitted friendly module name")
        if any(":" in line for line in check_completion_lines if line.startswith("check ")):
            hard_failures.append("check completion exposed module ids before narrowing")
        narrowed_check_block = transcript_block_after(transcript, "Completions for check bridge:")
        narrowed_check_lines = {
            line.strip()
            for line in narrowed_check_block.splitlines()
            if line.strip()
        }
        if "check Inspect bridge status" not in narrowed_check_lines:
            hard_failures.append("narrowed check completion omitted friendly bridge module")
        if any(":" in line for line in narrowed_check_lines if line.startswith("check ")):
            hard_failures.append("narrowed check completion exposed module ids")
        run_completion_block = transcript_block_after(transcript, "Completions for run:")
        run_completion_lines = {
            line.strip()
            for line in run_completion_block.splitlines()
            if line.strip()
        }
        if "run Inspect bridge status" not in run_completion_lines:
            hard_failures.append("run completion omitted friendly module name")
        if any(":" in line for line in run_completion_lines if line.startswith("run ")):
            hard_failures.append("run completion exposed module ids before narrowing")
        retrieve_completion_block = transcript_block_after(transcript, "Completions for retrieve:")
        retrieve_completion_lines = {
            line.strip()
            for line in retrieve_completion_block.splitlines()
            if line.strip()
        }
        for command in ("retrieve /etc/hosts", "retrieve queue /etc/hosts"):
            if command not in retrieve_completion_lines:
                hard_failures.append(f"retrieve completion omitted example: {command}")
    return {
        "name": scenario["name"],
        "description": scenario["description"],
        "environment": "local PTY",
        "qemu": bool(scenario.get("qemu")),
        "artifact": None,
        "target_tuple": None,
        "command_count": len(rendered_commands),
        "commands": rendered_commands,
        "config": str(cfg_path),
        "transcript": str(scenario_dir / "transcript.txt"),
        "stderr": str(scenario_dir / "stderr.txt"),
        "prompt_count": prompt_count(transcript),
        "returncode": result["returncode"],
        "hard_failures": hard_failures,
        "rubric_focus": list(scenario.get("rubric_focus") or []),
        "observations": scenario_observations(transcript, rendered_commands),
    }


def write_report(path, artifact_dir, summaries):
    lines = [
        "# grit-console UX Audit",
        "",
        f"Artifact directory: `{artifact_dir}`",
        "",
        "This report is review-oriented. Infrastructure failures are listed as",
        "hard failures; UX observations are prompts for human review and follow-up",
        "regression tests.",
        "",
        "## Scenarios",
        "",
    ]
    for summary in summaries:
        lines.extend([
            f"### {summary['name']}",
            "",
            summary["description"],
            "",
            f"- Environment: {summary['environment']}",
            f"- QEMU target used: {'yes' if summary['qemu'] else 'no'}",
            f"- Target tuple: {summary['target_tuple'] or 'n/a'}",
            f"- Artifact: {summary['artifact'] or 'n/a'}",
            f"- Config: `{summary['config']}`",
            f"- Commands: {summary['command_count']}",
            f"- Transcript: `{summary['transcript']}`",
            f"- stderr: `{summary['stderr']}`",
            f"- Prompt count: {summary['prompt_count']}",
            f"- Hard failures: {', '.join(summary['hard_failures']) if summary['hard_failures'] else 'none'}",
            f"- Rubric focus: {', '.join(summary['rubric_focus'])}",
            "",
            "Command list:",
            "",
        ])
        lines.extend(f"1. `{command}`" for command in summary["commands"])
        lines.extend(["", "Review observations:", ""])
        if summary["observations"]:
            for obs in summary["observations"]:
                lines.append(
                    f"- Line {obs['line']}: {obs['message']} (`{obs['needle']}`)"
                )
        else:
            lines.append("- No heuristic observations recorded; inspect transcript manually.")
        lines.extend([
            "",
            "Reviewer prompts:",
            "",
            "- Discoverability: did the next action appear on-screen before the command was entered?",
            "- Consistency: did root commands and selected-context shortcuts behave as expected?",
            "- Context clarity: did the prompt make the active context obvious?",
            "- Reversibility: was it clear how to stop services or back out?",
            "- Directionality: was operator-to-target vs target-to-operator wording clear?",
            "- Noise: did output avoid raw ids and implementation details by default?",
            "",
        ])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", default="tests/artifacts/ux-audit")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    artifact_dir = ROOT / args.artifact_root / timestamp()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sample_file = artifact_dir / "ux-sample.txt"
    sample_file.write_text("griTTYkit UX audit sample\n", encoding="utf-8")
    resource_file = artifact_dir / "console-resource.gritrc"
    resource_file.write_text("status\nnext\n", encoding="utf-8")

    summaries = []
    hard_failures = []
    for scenario in SCENARIOS:
        description = str(scenario.get("description") or "").lower()
        for phrase in STALE_REPORT_PHRASES:
            if phrase in description:
                hard_failures.append(
                    f"{scenario['name']}: stale report wording: {phrase}"
                )
    for scenario in SCENARIOS:
        scenario_dir = artifact_dir / scenario["name"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = scenario_dir / "config.json"
        write_config(cfg_path, scenario_dir)
        setup_func = SCENARIO_SETUP.get(scenario["name"])
        if setup_func:
            setup_func(cfg_path, scenario_dir)
        render_values = {
            "sample_file": sample_file,
            "resource_file": resource_file,
            "makerc_file": artifact_dir / "console-history.gritrc",
            "route_listen_port": free_port(),
            "route_dest_port": free_port(),
        }
        rendered_commands = [
            command.format(**render_values)
            for command in scenario["commands"]
        ]
        result = run_console(rendered_commands, cfg_path, scenario_dir, args.timeout)
        summary = scenario_summary(scenario, scenario_dir, cfg_path, result, rendered_commands)
        (scenario_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summaries.append(summary)
        hard_failures.extend(
            f"{scenario['name']}: {failure}"
            for failure in summary["hard_failures"]
        )

    summary = {
        "schema": 1,
        "kind": "grit-console-ux-audit",
        "artifact_dir": str(artifact_dir),
        "config": "per-scenario config.json",
        "environment": "local PTY",
        "qemu_used": False,
        "listener_host": "127.0.0.1",
        "scenario_count": len(summaries),
        "hard_failures": hard_failures,
        "scenarios": summaries,
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(artifact_dir / "UX_AUDIT.md", artifact_dir, summaries)
    print(f"summary={artifact_dir / 'summary.json'}")
    print(f"report={artifact_dir / 'UX_AUDIT.md'}")
    if hard_failures:
        print("ux-audit-console: infrastructure failures:", file=sys.stderr)
        for failure in hard_failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
