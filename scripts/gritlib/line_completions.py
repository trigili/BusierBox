"""Line-console completion vocabulary helpers."""

import shlex
from pathlib import Path

from gritlib.build_config import WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS
from gritlib.probe_results import probe_all_results
from gritlib.target_store import load_targets
from gritlib.workbench_jobs import load_workbench_jobs
from gritlib.profiles import PROFILE_KEY_HINTS, profile_records


BASE_COMMANDS = [
    "help", "complete", "search", "resource", "makerc", "history", "workspace", "status",
    "events", "console",
    "show", "info", "options", "next", "commands", "target-commands", "copy", "set", "setg", "unset", "unsetg",
    "targets", "target", "listeners", "listener",
    "routes", "route", "sessions", "session", "jobs", "job", "use",
    "main", "home", "root", "back", "background", "start", "stop",
    "check", "run", "interact", "queue",
    "retrieve", "stage", "deliver", "stamp", "artifact",
    "profile", "profiles",
    "survey", "daemon", "build", "release",
    "serve-binary", "unstage",
    "view", "cat", "less", "mailbox", "refresh",
    "quit", "exit", "ips", "ip", "reload",
]

SHOW_RESOURCES = [
    "targets", "listeners", "routes", "sessions",
    "jobs", "queue", "mailbox", "files", "events",
    "release", "modules", "categories", "service modules", "daemon modules",
    "target modules", "workbench modules", "options",
]
MODULE_KIND_COMPLETIONS = ["service", "daemon", "target", "workbench"]

USE_KINDS = ["target", "listener", "route", "session", "job", "module", "profile"]

HELP_TOPICS = [
    "search", "complete", "commands", "target-commands", "copy", "resource", "makerc", "history",
    "use", "main", "show", "start", "stop",
    "modules", "options", "next", "workspace", "aliases", "ip", "listeners",
    "routes", "set", "setg", "run", "jobs", "queue", "events", "retrieve", "survey", "build",
    "release", "stage", "deliver", "stamp", "artifact", "files", "view",
    "daemon", "interact", "sessions", "profile", "profiles", "console",
]

EXACT_COMPLETION_EXPANDERS = {
    "help", "show", "search", "events", "commands", "target-commands", "copy", "use",
    "agent", "target", "host", "agents", "targets", "hosts",
    "profile", "profiles", "ip", "listener", "service", "listeners", "services",
    "start", "stop", "route", "routes", "sessions", "session", "jobs", "job",
    "daemon", "modules", "module", "files", "staged", "stagers", "loot", "downloads",
    "run", "execute", "exploit", "check", "stage", "upload", "deliver", "fetch", "deploy", "queue-fetch",
    "queue-deliver", "unstage", "rmfile", "rm-file", "stamp", "trailer", "configure",
    "artifact", "view", "cat", "less", "queue", "build", "release", "releases",
    "stage-release", "survey",
    "console", "history", "resource", "makerc",
}

EXACT_COMPLETION_PHRASE_EXPANDERS = {
    "commands copy", "target-commands copy",
    "use agent", "use target", "use host", "use listener", "use service",
    "use route", "use session", "use job", "use module", "use profile",
    "profile use", "profile delete", "profile set", "profile from", "profile from probe",
    "profiles use",
    "listener probe", "listener probe-http", "listener probe config", "listener probe-http config",
    "listener probe clear", "listener probe-http clear", "listener probe clear all",
    "listener probe-http clear all", "listener serve",
    "daemon start", "daemon stop", "daemon status", "daemon install", "daemon print",
    "daemon systemd-start", "daemon systemd-stop", "daemon systemd-restart",
    "daemon systemd-status",
    "route add", "route start", "route stop", "route delete", "route rm", "route remove",
    "sessions clear", "sessions clear all", "sessions prune", "sessions prune all",
    "sessions clean", "sessions clean all",
    "queue result", "queue results", "queue clear",
    "build set", "build unset",
    "events n", "events since",
    "release stage", "release stage start", "release stage ssh",
    "release use", "release select", "releases stage", "releases stage start",
    "releases use", "releases select", "stage-release start",
    "survey config", "survey preset",
    "artifact stamp", "artifact trailer", "artifact configure",
    "artifact info", "artifact inspect", "artifact show", "artifact clear",
    "show modules",
    "show daemon modules", "show service modules", "show target modules", "show workbench modules",
}


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


def completion_provider(providers, name, default=None):
    value = (providers or {}).get(name)
    if value is None:
        return list(default or [])
    if callable(value):
        value = value()
    return list(value or [])


def _completion_target_names(cfg, workbench_snapshot_func):
    names = []
    del workbench_snapshot_func
    for rec in (load_targets(cfg).get("targets") or {}).values():
        if not isinstance(rec, dict):
            continue
        for item in [rec.get("target_id"), rec.get("label"), *(rec.get("aliases") or [])]:
            value = str(item or "").strip()
            if value:
                names.append(value)
    return names


def _completion_session_names(cfg, workbench_snapshot_func):
    del workbench_snapshot_func
    names = []
    root = Path(str(cfg.get("session_root", "local/sessions")))
    try:
        entries = sorted(
            (entry for entry in root.iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return names
    for entry in entries[:100]:
        value = entry.name.strip()
        if value:
            names.append(value)
    return names


def _completion_action_names(line_action_records_func):
    names = []
    for rec in line_action_records_func():
        rec_id = str(rec.get("id") or "")
        kind = str(rec.get("kind") or "")
        if rec_id:
            names.append(rec_id)
            if kind:
                names.append(f"{kind}:{rec_id}")
    return names


def _completion_release_selectors(cfg, release_context_func):
    rel = release_context_func(cfg)
    if not rel:
        return []
    selectors = []
    for rec in rel.get("artifacts") or []:
        selectors.extend([rec.get("release_path"), rec.get("name"), rec.get("path")])
    for rec in rel.get("recommendation_records") or []:
        selectors.extend([rec.get("id"), rec.get("artifact")])
    for rec in rel.get("devices") or []:
        name = str(rec.get("name") or "")
        if name:
            selectors.append(f"by_device:{name}")
    for rec in rel.get("tuples") or []:
        path = str(rec.get("path") or "")
        if path:
            selectors.append(f"by_tuple_path:{path}")
    return [str(item or "") for item in selectors if str(item or "")]


def _completion_command_queue_ids(cfg, command_queue_summary_func):
    ids = []
    for idx, rec in enumerate((command_queue_summary_func(cfg).get("commands") or []), 1):
        ids.append(str(idx))
        command_id = str(rec.get("id") or "")
        if command_id:
            ids.append(command_id)
    return ids


def _completion_daemon_action_ids(cfg, workbench_snapshot_func):
    del cfg, workbench_snapshot_func
    return []


def _completion_job_names(cfg):
    names = []
    try:
        jobs = load_workbench_jobs(cfg).get("jobs") or []
    except OSError:
        return names
    for rec in jobs:
        if not isinstance(rec, dict):
            continue
        value = str(rec.get("id") or "").strip()
        if value:
            names.append(value)
    return names


def _completion_profile_names(cfg):
    return [
        str(rec.get("name") or "")
        for rec in profile_records(cfg)
        if str(rec.get("name") or "")
    ]


def _completion_probe_result_ordinals(cfg):
    try:
        records = probe_all_results(cfg)
    except OSError:
        return []
    return [str(idx) for idx, _rec in enumerate(records or [], 1)]


def _completion_session_paths(cfg, workbench_snapshot_func):
    del workbench_snapshot_func
    path_values = []
    root = Path(str(cfg.get("session_root", "local/sessions")))
    try:
        entries = sorted(
            (entry for entry in root.iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return path_values
    for entry in entries[:20]:
        path_values.append(str(entry))
        for child in (entry / "session.log", entry / "events.jsonl"):
            if child.exists():
                path_values.append(str(child))
        files_dir = entry / "files"
        if files_dir.is_dir():
            try:
                for child in sorted(files_dir.iterdir())[:20]:
                    if child.is_file():
                        path_values.append(str(child))
            except OSError:
                pass
    return path_values


def _completion_survey_upload_paths(find_survey_uploads_func):
    return [
        rec.get("stored_path") or ""
        for rec in find_survey_uploads_func()
        if rec.get("stored_path")
    ]


def _completion_build_value_options(selector, keys):
    text = str(selector or "").strip()
    if text.isdigit():
        idx = int(text) - 1
        key_list = list(keys or [])
        text = key_list[idx] if 0 <= idx < len(key_list) else ""
    return list(WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS.get(text, ()))


def build_line_completion_providers(
    cfg,
    *,
    workbench_snapshot_func,
    line_action_records_func,
    bridge_profile_records_func,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func,
    workbench_config_field_records_func,
    service_status_rows_func,
    service_completion_names_func,
    service_names_func,
    load_staged_func,
    find_survey_uploads_func,
):
    return {
        "target_names": lambda: _completion_target_names(cfg, workbench_snapshot_func),
        "session_names": lambda: _completion_session_names(cfg, workbench_snapshot_func),
        "job_names": lambda: _completion_job_names(cfg),
        "profile_names": lambda: _completion_profile_names(cfg),
        "probe_result_ordinals": lambda: _completion_probe_result_ordinals(cfg),
        "route_names": lambda: [
            str(rec.get("name") or "") for rec in bridge_profile_records_func(cfg)
            if str(rec.get("name") or "")
        ],
        "action_names": lambda: _completion_action_names(line_action_records_func),
        "release_selectors": lambda: _completion_release_selectors(cfg, release_context_func),
        "command_queue_ids": lambda: _completion_command_queue_ids(cfg, command_queue_summary_func),
        "generated_command_ids": lambda: [
            str(idx) for idx, _rec in enumerate(generated_target_command_records_func(cfg), 1)
        ],
        "build_config_keys": lambda: [
            str(rec.get("key") or "") for rec in workbench_config_field_records_func(cfg)
            if str(rec.get("key") or "")
        ],
        "service_completion_names": lambda: service_completion_names_func(service_status_rows_func(cfg)),
        "service_names": lambda: service_names_func(service_status_rows_func(cfg)),
        "daemon_action_ids": lambda: _completion_daemon_action_ids(cfg, workbench_snapshot_func),
        "staged_names_load": lambda: sorted((load_staged_func(cfg).get("staged") or {}).keys()),
        "staged_names_snapshot": lambda: sorted((load_staged_func(cfg).get("staged") or {}).keys()),
        "session_paths": lambda: _completion_session_paths(cfg, workbench_snapshot_func),
        "survey_upload_paths": lambda: _completion_survey_upload_paths(find_survey_uploads_func),
    }


def build_line_completion_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    line_action_records_func,
    bridge_profile_records_func,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func,
    workbench_config_field_records_func,
    service_status_rows_func,
    service_completion_names_func,
    service_names_func,
    load_staged_func,
    find_survey_uploads_func,
    append_event_func=None,
):
    def providers():
        return build_line_completion_providers(
            cfg,
            workbench_snapshot_func=workbench_snapshot_func,
            line_action_records_func=line_action_records_func,
            bridge_profile_records_func=bridge_profile_records_func,
            release_context_func=release_context_func,
            command_queue_summary_func=command_queue_summary_func,
            generated_target_command_records_func=generated_target_command_records_func,
            workbench_config_field_records_func=workbench_config_field_records_func,
            service_status_rows_func=service_status_rows_func,
            service_completion_names_func=service_completion_names_func,
            service_names_func=service_names_func,
            load_staged_func=load_staged_func,
            find_survey_uploads_func=find_survey_uploads_func,
        )

    def candidates(prefix=""):
        return line_completion_candidates(prefix, providers=providers())

    def printer(prefix=""):
        return print_line_completions(
            prefix,
            candidates=candidates(prefix),
            append_event_func=append_event_func,
        )

    return candidates, printer


class LineCompletionContext:
    def __init__(self, text, parts, trailing_space, providers):
        self.text = text
        self.parts = parts
        self.trailing_space = trailing_space
        self.providers = providers or {}
        self.current = "" if trailing_space else (parts[-1] if parts else "")

    def values(self, name):
        return completion_provider(self.providers, name)

    def arg(self, n):
        if len(self.parts) > n:
            return "" if self.trailing_space else self.parts[n]
        if len(self.parts) == n and self.trailing_space:
            return ""
        return None

    def arg_pfx(self, n):
        value = self.arg(n)
        return value if value is not None else (self.parts[n] if len(self.parts) > n else "")

    def at_arg(self, n):
        return (
            len(self.parts) == n and self.trailing_space
        ) or (
            len(self.parts) == n + 1 and not self.trailing_space
        )


def _line_completion_command_candidates(cmd, ctx):
    if cmd in {"help", "?"}:
        return [f"help {item}" for item in prefixed(ctx.arg_pfx(1), HELP_TOPICS)]

    if cmd == "show":
        resource = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if resource in MODULE_KIND_COMPLETIONS and len(ctx.parts) >= 3 and ctx.parts[2].lower() in {"module", "modules"}:
            kind = resource
            if ctx.at_arg(3):
                return [f"show {kind} modules {item}" for item in prefixed(ctx.arg_pfx(3),
                    [name for name in ctx.values("action_names") if name.startswith(f"{kind}:")])]
        if resource in {"module", "modules", "action", "actions"}:
            if ctx.at_arg(2):
                module_kind_prefix = ctx.arg_pfx(2).lower()
                if not module_kind_prefix:
                    return ["show modules FILTER"]
                if module_kind_prefix in MODULE_KIND_COMPLETIONS:
                    return [f"show {module_kind_prefix} modules {item}" for item in prefixed(
                        "", [name for name in ctx.values("action_names") if name.startswith(f"{module_kind_prefix}:")]
                    )]
                matching_kinds = prefixed(module_kind_prefix, MODULE_KIND_COMPLETIONS)
                if matching_kinds:
                    return [f"show {kind} modules" for kind in matching_kinds]
                return [f"show modules {item}" for item in prefixed(ctx.arg_pfx(2),
                    ctx.values("action_names"))]
            if len(ctx.parts) >= 3 and ctx.parts[2].lower() in MODULE_KIND_COMPLETIONS and ctx.at_arg(3):
                kind = ctx.parts[2].lower()
                return [f"show {kind} modules {item}" for item in prefixed(ctx.arg_pfx(3),
                    [name for name in ctx.values("action_names") if name.startswith(f"{kind}:")])]
        pfx = "" if ctx.trailing_space else " ".join(ctx.parts[1:])
        return [f"show {item}" for item in prefixed(pfx, SHOW_RESOURCES)]

    if cmd == "events":
        if len(ctx.parts) >= 2:
            subcmd = ctx.parts[1].lower()
            if subcmd in {"n", "limit", "-n", "--limit"} and ctx.at_arg(2):
                return [f"events n {item}" for item in prefixed(
                    ctx.arg_pfx(2), ["10", "20", "50", "100"]
                )]
            if subcmd == "since" and ctx.at_arg(2):
                return [f"events since {item}" for item in prefixed(
                    ctx.arg_pfx(2), ["5m", "30m", "2h", "1d"]
                )]
        return [f"events {item}" for item in prefixed(ctx.arg_pfx(1), [
            "n", "since", "service=", "event=", "level=", "target=",
            "status=", "operation=", "request_name=", "command_id=", "job_id=", "module_id=",
        ])]

    if cmd == "console":
        return []

    if cmd == "search":
        return [f"search {item}" for item in prefixed(ctx.arg_pfx(1), [
            "TERM", "target", "probe", "listener", "route", "session",
            "job", "file", "queue",
        ])]

    if cmd == "history":
        return [f"history {item}" for item in prefixed(ctx.arg_pfx(1), ["10", "20", "50", "100"])]

    if cmd == "resource":
        return [f"resource {item}" for item in prefixed(ctx.arg_pfx(1), ["FILE"])]

    if cmd == "makerc":
        return [f"makerc {item}" for item in prefixed(ctx.arg_pfx(1), ["FILE"])]

    if cmd in {"commands", "target-commands"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ["list", "show", "copy"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "copy" and ctx.at_arg(2):
            return [f"{cmd} copy {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("generated_command_ids"))]
        return None

    if cmd == "copy":
        return [f"copy {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("generated_command_ids"))]

    if cmd == "use":
        if ctx.at_arg(1):
            return [f"use {item}" for item in prefixed(ctx.arg_pfx(1), USE_KINDS)]
        kind = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        candidate_provider = {
            "agent": "target_names", "target": "target_names", "host": "target_names",
            "listener": "service_completion_names", "service": "service_completion_names",
            "route": "route_names",
            "session": "session_names",
            "job": "job_names",
            "module": "action_names", "action": "action_names",
            "profile": "profile_names",
        }.get(kind, "")
        values = ctx.values(candidate_provider)
        if kind in {"agent", "target", "host"}:
            values = values + ["all", "clear"]
        return [f"use {kind} {item}" for item in prefixed(ctx.arg_pfx(2), values)]

    if cmd in {"profile", "profiles"}:
        if cmd == "profiles":
            if ctx.at_arg(1):
                return [f"profiles {item}" for item in prefixed(ctx.arg_pfx(1), ["list", "use"] + ctx.values("profile_names"))]
            if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "use":
                return [f"profiles use {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("profile_names"))]
            return []
        if ctx.at_arg(1):
            return [f"profile {item}" for item in prefixed(ctx.arg_pfx(1), [
                "list", "use", "create", "set", "clear", "delete", "from", "show",
            ] + ctx.values("profile_names"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if (
            subcmd == "delete"
            and len(ctx.parts) >= 3
            and not ctx.trailing_space
            and ctx.parts[2] in ctx.values("profile_names")
        ):
            return [f"profile delete {ctx.parts[2]} confirm"]
        if subcmd in {"use", "delete"} and ctx.at_arg(2):
            return [f"profile {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("profile_names"))]
        if subcmd == "delete" and ctx.at_arg(3):
            return [f"profile delete {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), ["confirm"])]
        if subcmd == "set" and ctx.at_arg(2):
            return [f"profile set {item}" for item in prefixed(ctx.arg_pfx(2), PROFILE_KEY_HINTS)]
        if subcmd == "from" and ctx.at_arg(2):
            return [f"profile from {item}" for item in prefixed(ctx.arg_pfx(2), ["probe"])]
        if subcmd == "from" and len(ctx.parts) >= 3 and ctx.parts[2].lower() == "probe" and ctx.at_arg(3):
            return [f"profile from probe {item}" for item in prefixed(ctx.arg_pfx(3), ["1", "2", "3"])]
        return []

    return None


def _line_completion_context_candidates(cmd, ctx):
    if cmd in {"agent", "target", "host", "agents", "targets", "hosts",
               "useagent", "usetarget", "usehost"}:
        values = ctx.values("target_names")
        if cmd in {"agent", "target", "host", "useagent", "usetarget", "usehost"}:
            values = values + ["all", "clear"]
        preferred_cmd = {
            "agent": "target",
            "agents": "targets",
            "host": "target",
            "hosts": "targets",
            "useagent": "use target",
            "usetarget": "use target",
            "usehost": "use target",
            "uselistener": "use listener",
            "useservice": "use listener",
        }.get(cmd, cmd)
        return [f"{preferred_cmd} {item}" for item in prefixed(ctx.arg_pfx(1), values)]

    if cmd == "ip":
        if ctx.at_arg(1):
            return [f"ip {item}" for item in prefixed(ctx.arg_pfx(1), ["host", "bind", "show"])]
        return []

    if cmd in {"listener", "service", "listeners", "services",
               "uselistener", "useservice"}:
        if cmd in {"listener", "service"} and len(ctx.parts) >= 2 and ctx.parts[1].lower() in {"probe", "probe-http"}:
            if ctx.at_arg(2):
                return [f"{cmd} {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2),
                    ["start", "queue", "results", "config", "clear", "delivery", "paste", "script", "options"])]
            subcmd = ctx.parts[2].lower() if len(ctx.parts) >= 3 else ""
            if subcmd == "config" and ctx.at_arg(3):
                return [f"{cmd} {ctx.parts[1]} config {item}" for item in prefixed(ctx.arg_pfx(3),
                    (ctx.values("probe_result_ordinals") or ["1", "2", "3"]) + [
                     "write-config", "prefer-rshell", "prefer-runtime",
                     "target-preset", "payload-preset"])]
            if subcmd == "clear" and ctx.at_arg(3):
                ordinals = ctx.values("probe_result_ordinals") or ["1", "2", "3"]
                return [f"{cmd} {ctx.parts[1]} clear {item}" for item in prefixed(ctx.arg_pfx(3), ["confirm", "all"] + ordinals)]
            if subcmd == "clear" and ctx.at_arg(4):
                return [f"{cmd} {ctx.parts[1]} clear {ctx.parts[3]} {item}" for item in prefixed(ctx.arg_pfx(4), ["confirm"])]
            return None
        if cmd == "listener" and len(ctx.parts) >= 2 and ctx.parts[1].lower() == "serve":
            if ctx.at_arg(2):
                return [f"listener serve {item}" for item in prefixed(ctx.arg_pfx(2), ["start", "ssh", "default", "ssh-operator"])]
            if len(ctx.parts) >= 3 and ctx.parts[2].lower() in {"ssh", "ssh-operator"} and ctx.at_arg(3):
                return [f"listener serve {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), ["start"])]
            return []
        service_values = (["verbose", "details"] if cmd in {"listeners", "services"} else []) + (
            ["serve"] if cmd == "listener" else []
        ) + ctx.values("service_completion_names")
        preferred_cmd = {
            "uselistener": "use listener",
            "useservice": "use listener",
        }.get(cmd, cmd)
        return [f"{preferred_cmd} {item}" for item in prefixed(ctx.arg_pfx(1), service_values)]

    if cmd in {"start", "stop"}:
        if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "route":
            return [f"{cmd} route {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("route_names"))]
        services = ctx.values("service_completion_names") or ctx.values("service_names")
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), services + ctx.values("route_names"))]

    if cmd in {"route", "useroute"}:
        route_names = ctx.values("route_names")
        if ctx.at_arg(1):
            preferred_cmd = "use route" if cmd == "useroute" else "route"
            return [f"{preferred_cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["add", "start", "stop", "delete", "rm", "print"] + route_names)]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"add", "new"} and ctx.at_arg(2):
            return [
                "route add NAME LISTEN_PORT DEST_HOST DEST_PORT",
                "route add NAME LISTEN_PORT DEST_HOST DEST_PORT FROM=TO",
            ]
        if subcmd in {"start", "stop", "delete", "rm", "remove"} and ctx.at_arg(2):
            return [f"route {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), route_names)]
        if subcmd in {"delete", "rm", "remove"} and ctx.at_arg(3):
            return [f"route {subcmd} {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), ["confirm"])]
        return []

    if cmd == "routes":
        return [f"routes {item}" for item in prefixed(ctx.arg_pfx(1), ["verbose", "details"] + ctx.values("route_names"))]

    if cmd == "sessions":
        if ctx.at_arg(1):
            return [f"sessions {item}" for item in prefixed(ctx.arg_pfx(1),
                ["verbose", "details", "list", "clear", "prune"] + ctx.values("session_names"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"clear", "prune", "clean"}:
            if ctx.at_arg(3) and len(ctx.parts) >= 3 and ctx.parts[2].lower() == "all":
                return [f"sessions {subcmd} all {item}" for item in prefixed(ctx.arg_pfx(3), ["confirm"])]
            return [f"sessions {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ["confirm", "all"])]
        return []

    if cmd in {"session", "usesession"}:
        preferred_cmd = "use session" if cmd == "usesession" else cmd
        return [f"{preferred_cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("session_names"))]

    if cmd == "interact":
        return [f"interact {item}" for item in prefixed(ctx.arg_pfx(1), ["agent"] + ctx.values("session_names"))]

    if cmd == "jobs":
        if ctx.at_arg(1):
            return [f"jobs {item}" for item in prefixed(ctx.arg_pfx(1),
                ["info", "cancel", "verbose", "details"] + ctx.values("job_names"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"info", "select", "use", "-i", "--info"} and ctx.at_arg(2):
            return [f"jobs info {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("job_names"))]
        if subcmd in {"cancel", "kill", "-k", "--kill", "--cancel"} and ctx.at_arg(2):
            return [f"jobs cancel {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("job_names"))]
        return []

    if cmd == "job":
        return [f"job {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("job_names"))]

    if cmd == "daemon":
        actions = [
            "start", "stop", "status", "install", "print",
            "systemd-start", "systemd-stop", "systemd-restart", "systemd-status",
        ] + ctx.values("daemon_action_ids")
        if ctx.at_arg(1):
            return [f"daemon {item}" for item in prefixed(ctx.arg_pfx(1), actions + ["verbose", "details"])]
        if ctx.at_arg(2):
            return [f"daemon {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2), ["dry-run", "confirm"])]
        return []

    if cmd in {"modules", "module"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                MODULE_KIND_COMPLETIONS + ctx.values("action_names"))]
        return []

    return None


def _line_completion_file_work_candidates(cmd, ctx):
    if cmd in {"files", "staged", "stagers", "loot", "downloads"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["verbose", "details", "stage", "deliver", "unstage", "clear"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"unstage", "rm"}:
            return [f"{cmd} {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("staged_names_load"))]
        if subcmd == "clear" and ctx.at_arg(2):
            return [f"{cmd} clear confirm"]
        return None

    if cmd in {"usemodule", "useaction"}:
        return [f"use module {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("action_names"))]
    if cmd in {"execute", "exploit"}:
        return [f"run {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("action_names"))]
    if cmd in {"run", "check"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("action_names"))]

    if cmd in {"stage", "serve-file"}:
        return [f"{cmd} LOCAL NAME"]
    if cmd == "upload":
        return ["stage LOCAL NAME"]

    if cmd == "deliver":
        return [f"deliver {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]
    if cmd in {"fetch", "deploy"}:
        return [f"deliver {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]
    if cmd in {"queue-fetch", "queue-deliver"}:
        return [f"deliver queue {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]
    if cmd in {"unstage", "rmfile", "rm-file"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]

    trailer_fields = [
        "show", "clear", "operator-host", "operator-user", "ssh-port",
        "shell-port", "remote-forward-port", "target-bind-host",
        "transport", "encryption", "run-mode", "session-policy",
        "shell-provider", "zero-arg-mode", "zero-arg-log-mode",
        "runtime-mode", "noresidue-level", "retry-count",
        "retry-interval", "retry-backoff", "retry-max-interval",
        "command-queue-enable", "command-queue-port",
        "command-queue-execution", "command-queue-poll-interval",
        "command-queue-max-polls",
    ]

    if cmd == "stamp":
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_load"))]
        if len(ctx.parts) >= 2:
            return [f"{cmd} {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2), trailer_fields)]
        return []
    if cmd in {"trailer", "configure"}:
        if ctx.at_arg(1):
            return [f"stamp {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_load"))]
        if len(ctx.parts) >= 2:
            return [f"stamp {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2), trailer_fields)]
        return []

    if cmd == "artifact":
        if ctx.at_arg(1):
            return [f"artifact {item}" for item in prefixed(ctx.arg_pfx(1), [
                "info", "inspect", "stamp", "show", "clear",
            ] + ctx.values("staged_names_load"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "stamp":
            if ctx.at_arg(2):
                return [f"artifact {subcmd} {item}" for item in prefixed(
                    ctx.arg_pfx(2), ctx.values("staged_names_load")
                )]
            if len(ctx.parts) >= 3:
                return [
                    f"artifact {subcmd} {ctx.parts[2]} {item}"
                    for item in prefixed(ctx.arg_pfx(3), trailer_fields)
                ]
        if subcmd in {"trailer", "configure"}:
            if ctx.at_arg(2):
                return [f"artifact stamp {item}" for item in prefixed(
                    ctx.arg_pfx(2), ctx.values("staged_names_load")
                )]
            if len(ctx.parts) >= 3:
                return [
                    f"artifact stamp {ctx.parts[2]} {item}"
                    for item in prefixed(ctx.arg_pfx(3), trailer_fields)
                ]
        if subcmd in {"info", "inspect", "show", "clear"} and ctx.at_arg(2):
            return [f"artifact {subcmd} {item}" for item in prefixed(
                ctx.arg_pfx(2), ctx.values("staged_names_load")
            )]
        return []

    if cmd in {"view", "cat", "less"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("session_paths"))]

    return None


def _line_completion_queue_release_candidates(cmd, ctx):
    if cmd == "queue":
        if ctx.at_arg(1):
            return [f"queue {item}" for item in prefixed(ctx.arg_pfx(1),
                ["list", "result", "results", "clear", "command"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"result", "results"} and ctx.at_arg(2):
            return [f"queue {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("command_queue_ids"))]
        if subcmd == "clear" and ctx.at_arg(2):
            return [f"queue clear {item}" for item in prefixed(ctx.arg_pfx(2), ["confirm"])]
        return None

    if cmd == "build":
        if ctx.at_arg(1):
            return [f"build {item}" for item in prefixed(ctx.arg_pfx(1), ["list", "set", "unset"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "set" and len(ctx.parts) >= 3:
            value_options = _completion_build_value_options(
                ctx.parts[2],
                ctx.values("build_config_keys"),
            )
            if value_options:
                return [
                    f"build set {ctx.parts[2]} {item}"
                    for item in prefixed(ctx.arg_pfx(3), value_options)
                ]
        if subcmd in {"set", "unset"} and ctx.at_arg(2):
            return [f"build {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("build_config_keys"))]
        return None

    if cmd in {"release", "releases"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["list", "stage", "recommendations", "artifacts"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"stage", "use", "select"} and ctx.at_arg(2):
            return [f"{cmd} {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ["start", "ssh"] + ctx.values("release_selectors"))]
        if subcmd in {"stage", "use", "select"} and len(ctx.parts) >= 3:
            modifier = ctx.parts[2].lower()
            if modifier == "start" and ctx.at_arg(3):
                return [
                    f"{cmd} {subcmd} start {item}"
                    for item in prefixed(ctx.arg_pfx(3), ["ssh"] + ctx.values("release_selectors"))
                ]
            if modifier in {"ssh", "ssh-operator"} and ctx.at_arg(3):
                return [f"{cmd} {subcmd} {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), ["start"])]
        return None

    if cmd == "stage-release":
        if ctx.at_arg(1):
            return [f"release stage {item}" for item in prefixed(ctx.arg_pfx(1), ["start"] + ctx.values("release_selectors"))]
        if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "start" and ctx.at_arg(2):
            return [
                f"release stage start {item}"
                for item in prefixed(ctx.arg_pfx(2), ctx.values("release_selectors"))
            ]
        return [f"release stage {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("release_selectors"))]

    return None


def _line_completion_probe_survey_candidates(cmd, ctx):
    if cmd == "survey":
        if ctx.at_arg(1):
            return [f"survey {item}" for item in prefixed(ctx.arg_pfx(1),
                ["results", "config", "preset"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "config" and ctx.at_arg(2):
            return [f"survey config {item}" for item in prefixed(ctx.arg_pfx(2),
                ctx.values("survey_upload_paths") + [
                    "PATH",
                    "write-config FILE",
                    "prefer-rshell auto",
                    "prefer-runtime auto",
                    "target-preset NAME",
                    "payload-preset NAME",
                ])]
        if subcmd == "preset" and ctx.at_arg(2):
            return [f"survey preset {item}" for item in prefixed(ctx.arg_pfx(2),
                ctx.values("survey_upload_paths") + ["PATH", "name NAME", "write-local", "overwrite"])]
        return None

    return None


def line_completion_candidates(prefix="", providers=None):
    text = str(prefix or "")
    stripped = text.strip()
    providers = providers or {}

    if not stripped:
        return BASE_COMMANDS
    try:
        parts = shlex.split(stripped)
    except ValueError:
        parts = stripped.split()
    trailing_space = bool(text and text[-1].isspace())
    if not parts:
        return BASE_COMMANDS
    lower_phrase = " ".join(part.lower() for part in parts)
    if not trailing_space and (
        (len(parts) == 1 and lower_phrase in EXACT_COMPLETION_EXPANDERS)
        or lower_phrase in EXACT_COMPLETION_PHRASE_EXPANDERS
    ):
        trailing_space = True
        text = f"{stripped} "
    cmd = parts[0].lower()
    ctx = LineCompletionContext(text, parts, trailing_space, providers)

    if len(parts) == 1 and not trailing_space:
        return prefixed(ctx.current, BASE_COMMANDS)

    for candidate_func in (
        _line_completion_command_candidates,
        _line_completion_context_candidates,
        _line_completion_file_work_candidates,
        _line_completion_queue_release_candidates,
        _line_completion_probe_survey_candidates,
    ):
        candidates = candidate_func(cmd, ctx)
        if candidates is not None:
            return candidates

    return prefixed(ctx.current, BASE_COMMANDS)


def print_line_completions(prefix="", candidates=None, append_event_func=None):
    candidates = list(candidates or [])
    print(f"Completions for {prefix or 'root'}:")
    if not candidates:
        print("  none")
    else:
        for candidate in candidates[:40]:
            print(f"  {candidate}")
        if len(candidates) > 40:
            print(f"  ... {len(candidates) - 40} more")
    if append_event_func:
        append_event_func("workbench", "workbench_console_completions_shown", details={
            "prefix": str(prefix or ""),
            "candidate_count": len(candidates),
        })
