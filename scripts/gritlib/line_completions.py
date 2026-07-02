"""Line-console completion vocabulary helpers."""

import shlex
from pathlib import Path

from gritlib.build_config import WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS
from gritlib.line_network import line_local_ip_candidates
from gritlib.probe_results import probe_all_results
from gritlib.target_store import load_targets
from gritlib.workbench_jobs import load_workbench_jobs
from gritlib.profiles import PROFILE_KEY_HINTS, profile_records


BASE_COMMANDS = [
    "help", "complete", "search", "resource", "makerc", "history", "workspace", "status",
    "events", "console",
    "show", "info", "options", "next", "commands", "copy",
    "files", "modules",
    "targets", "target", "listeners", "listener",
    "routes", "route", "sessions", "session", "jobs", "job", "use",
    "main", "back", "quit",
    "check", "run", "queue",
    "retrieve", "stage", "deliver", "stamp", "artifact",
    "profile", "profiles",
    "survey", "daemon", "build", "release",
    "binary", "unstage",
    "view", "cat", "less", "check-ins", "refresh",
    "ips", "ip", "reload",
]

SHOW_RESOURCES = [
    "targets", "listeners", "routes", "sessions",
    "jobs", "queue", "check-ins", "files", "events",
    "release", "modules", "categories", "service modules", "daemon modules",
    "target modules", "operator modules", "options",
]
MODULE_KIND_COMPLETIONS = ["service", "daemon", "target", "operator"]
MODULE_KIND_COMPLETION_ALIASES = {
    "service": "service",
    "daemon": "daemon",
    "target": "target",
    "operator": "workbench",
    "operators": "workbench",
    "workbench": "workbench",
    "workbenches": "workbench",
}

USE_KINDS = ["target", "listener", "route", "session", "job", "module", "profile"]

HELP_TOPICS = [
    "search", "complete", "commands", "copy", "resource", "makerc", "history",
    "use", "main", "show", "start", "stop",
    "modules", "options", "next", "workspace", "workflow", "aliases", "ip", "listeners",
    "probe", "listener probe",
    "routes", "set", "run", "jobs", "queue", "events", "retrieve", "survey", "build",
    "release", "stage", "deliver", "stamp", "artifact", "files", "view",
    "daemon", "interact", "sessions", "profile", "profiles", "console",
]

EXACT_COMPLETION_EXPANDERS = {
    "complete", "completions",
    "help", "show", "search", "events", "commands", "copy", "use",
    "target", "targets",
    "profile", "profiles", "ip", "listener", "listeners",
    "start", "stop", "route", "routes", "sessions", "session", "jobs", "job",
    "daemon", "modules", "module", "files",
    "run", "check", "interact", "stage", "deliver", "retrieve", "queue-deliver",
    "unstage", "stamp",
    "artifact", "view", "cat", "less", "queue", "build", "release", "binary",
    "survey",
    "console", "history", "resource", "makerc",
}

EXACT_COMPLETION_PHRASE_EXPANDERS = {
    "commands copy",
    "use target", "use listener",
    "use route", "use session", "use job", "use module", "use profile",
    "profile use", "profile delete", "profile set", "profile from", "profile from probe",
    "profiles use",
    "listener probe", "listener probe config", "listener probe paste", "listener probe paste base64",
    "listener probe clear", "listener probe clear all", "listener serve",
    "daemon start", "daemon stop", "daemon status", "daemon install", "daemon print",
    "daemon systemd-start", "daemon systemd-stop", "daemon systemd-restart",
    "daemon systemd-status",
    "route add", "route start", "route stop", "route delete", "route rm", "route remove",
    "sessions clear", "sessions clear all", "sessions prune", "sessions prune all",
    "sessions clean", "sessions clean all",
    "queue result", "queue results", "queue clear",
    "build set", "build unset",
    "ip host", "ip bind",
    "events n", "events since",
    "release stage", "release stage start", "release stage ssh",
    "release use", "release select",
    "survey config", "survey preset",
    "artifact stamp", "artifact trailer", "artifact configure",
    "artifact info", "artifact inspect", "artifact show", "artifact clear",
    "show modules",
    "show daemon modules", "show service modules", "show target modules", "show operator modules",
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


def _listener_context_completion_names(names):
    result = []
    for name in names or []:
        value = str(name or "").strip()
        if not value:
            continue
        if value == "probe-http":
            value = "probe"
        if value not in result:
            result.append(value)
    return result


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
        label = str(rec.get("label") or "").strip()
        if label:
            names.append(label)
        if rec_id:
            names.append(rec_id)
            if kind:
                names.append(f"{kind}:{rec_id}")
    return names


def _completion_runnable_action_names(line_action_records_func):
    names = []
    seen = set()
    for rec in line_action_records_func():
        label = str(rec.get("label") or "").strip()
        rec_id = str(rec.get("id") or "").strip()
        for value in (label, rec_id):
            if value and value not in seen:
                seen.add(value)
                names.append(value)
    return names


def _display_runnable_action_names(names):
    friendly = []
    for name in names or []:
        text = str(name or "").strip()
        if not text:
            continue
        if text.startswith(("operator-daemon-", "systemd-user-")):
            continue
        if ":" not in text and " " not in text:
            continue
        friendly.append(text)
    return friendly


def _display_default_run_action_names(names):
    friendly = []
    for name in _display_runnable_action_names(names):
        if name.endswith((":start-service", ":stop-service")):
            continue
        if name.lower().startswith(("start ", "stop ")):
            continue
        friendly.append(name)
    return friendly


def _action_completion_values(prefix, names):
    prefix = str(prefix or "").strip()
    values = _display_runnable_action_names(names)
    if not prefix:
        return values
    if ":" in prefix:
        return prefixed(prefix, values)
    label_matches = [
        name for name in values
        if " " in name and prefix.lower() in name.lower()
    ]
    return label_matches or prefixed(prefix, values)


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


def _completion_editable_build_keys(records):
    return [
        str(rec.get("key") or "")
        for rec in records or []
        if str(rec.get("key") or "") and not rec.get("fixed_options")
    ]


def _completion_build_set_examples(records, key_prefix=""):
    examples = []
    by_key = {
        str(rec.get("key") or ""): rec
        for rec in (records or [])
        if str(rec.get("key") or "")
    }
    for key in prefixed(key_prefix, by_key.keys()):
        rec = by_key[key]
        key = str(rec.get("key") or "").strip()
        if not key or rec.get("fixed_options"):
            continue
        values = [str(value) for value in (rec.get("options") or rec.get("examples") or []) if str(value)]
        value = values[0] if values else str(rec.get("value") or "").strip()
        if value:
            examples.append(f"build set {key} {value}")
    return examples


def _completion_local_ip_values(snap):
    candidates = line_local_ip_candidates(snap)
    values = []
    for idx, ip in enumerate(candidates, 1):
        values.append(str(idx))
        values.append(str(ip))
    return values


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
        "runnable_action_names": lambda: _completion_runnable_action_names(line_action_records_func),
        "release_selectors": lambda: _completion_release_selectors(cfg, release_context_func),
        "command_queue_ids": lambda: _completion_command_queue_ids(cfg, command_queue_summary_func),
        "generated_command_ids": lambda: [
            str(idx) for idx, _rec in enumerate(generated_target_command_records_func(cfg), 1)
        ],
        "build_config_keys": lambda: [
            str(rec.get("key") or "") for rec in workbench_config_field_records_func(cfg)
            if str(rec.get("key") or "")
        ],
        "build_config_fields": lambda: workbench_config_field_records_func(cfg),
        "editable_build_config_keys": lambda: _completion_editable_build_keys(
            workbench_config_field_records_func(cfg)
        ),
        "local_ip_values": lambda: _completion_local_ip_values(workbench_snapshot_func(cfg)),
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
        if resource in MODULE_KIND_COMPLETION_ALIASES and len(ctx.parts) >= 3 and ctx.parts[2].lower() in {"module", "modules"}:
            kind = resource
            internal_kind = MODULE_KIND_COMPLETION_ALIASES.get(kind, kind)
            if ctx.at_arg(3):
                return [f"show {kind} modules {item}" for item in prefixed(ctx.arg_pfx(3),
                    [name for name in ctx.values("action_names") if name.startswith(f"{internal_kind}:")])]
        if resource in {"module", "modules", "action", "actions"}:
            if ctx.at_arg(2):
                module_kind_prefix = ctx.arg_pfx(2).lower()
                if not module_kind_prefix:
                    return ["show modules service"]
                if module_kind_prefix in MODULE_KIND_COMPLETION_ALIASES:
                    internal_kind = MODULE_KIND_COMPLETION_ALIASES[module_kind_prefix]
                    return [f"show {module_kind_prefix} modules {item}" for item in prefixed(
                        "", [name for name in ctx.values("action_names") if name.startswith(f"{internal_kind}:")]
                    )]
                matching_kinds = prefixed(module_kind_prefix, MODULE_KIND_COMPLETIONS)
                if matching_kinds:
                    return [f"show {kind} modules" for kind in matching_kinds]
                return [f"show modules {item}" for item in prefixed(ctx.arg_pfx(2),
                    ctx.values("action_names"))]
            if len(ctx.parts) >= 3 and ctx.parts[2].lower() in MODULE_KIND_COMPLETION_ALIASES and ctx.at_arg(3):
                kind = ctx.parts[2].lower()
                internal_kind = MODULE_KIND_COMPLETION_ALIASES.get(kind, kind)
                return [f"show {kind} modules {item}" for item in prefixed(ctx.arg_pfx(3),
                    [name for name in ctx.values("action_names") if name.startswith(f"{internal_kind}:")])]
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
            "status=", "operation=", "file=", "command=", "job=", "module=",
        ])]

    if cmd == "console":
        return []

    if cmd in {"complete", "completions"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), [
            "listener", "files", "modules", "run", "build set", "ip bind",
        ])]

    if cmd == "search":
        return [f"search {item}" for item in prefixed(ctx.arg_pfx(1), [
            "TERM", "target", "probe", "listener", "route", "session",
            "job", "file", "queue",
        ])]

    if cmd == "history":
        return [f"history {item}" for item in prefixed(ctx.arg_pfx(1), ["10", "20", "50", "100"])]

    if cmd == "resource":
        return [f"resource {item}" for item in prefixed(ctx.arg_pfx(1), [
            "./commands.gritrc", "./last-session.gritrc",
        ])]

    if cmd == "makerc":
        return [f"makerc {item}" for item in prefixed(ctx.arg_pfx(1), [
            "./last-session.gritrc", "./commands.gritrc",
        ])]

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
    if cmd in {"target", "targets"}:
        values = ctx.values("target_names")
        if cmd == "target":
            values = values + ["all", "clear"]
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), values)]

    if cmd == "ip":
        if ctx.at_arg(1):
            return [f"ip {item}" for item in prefixed(ctx.arg_pfx(1), ["host", "bind", "show"])]
        action = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if action in {"host", "operator", "advertise", "use", "bind", "listen", "listener"} and ctx.at_arg(2):
            values = ctx.values("local_ip_values") or ["IP"]
            return [f"ip {ctx.parts[1]} {item}" for item in prefixed(
                ctx.arg_pfx(2),
                values,
            )]
        return []

    if cmd in {"listener", "listeners"}:
        if cmd == "listener" and len(ctx.parts) >= 2 and ctx.parts[1].lower() == "probe":
            if ctx.at_arg(2):
                if ctx.arg_pfx(2):
                    return []
                return [
                    "listener probe",
                    "use listener probe",
                    "listener probe start",
                    "listener probe results",
                    "listener probe config",
                    "listener probe paste",
                    "listener probe paste copy",
                    "listener probe paste base64",
                    "listener probe paste base64 copy",
                    "listener probe queue",
                ]
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
            if subcmd == "paste" and ctx.at_arg(3):
                return [f"{cmd} {ctx.parts[1]} paste {item}" for item in prefixed(ctx.arg_pfx(3), ["copy", "base64"])]
            if subcmd == "paste" and len(ctx.parts) >= 4 and ctx.parts[3].lower() == "base64" and ctx.at_arg(4):
                return [f"{cmd} {ctx.parts[1]} paste base64 {item}" for item in prefixed(ctx.arg_pfx(4), ["copy"])]
            return None
        if cmd == "listener" and len(ctx.parts) >= 2 and ctx.parts[1].lower() == "serve":
            if ctx.at_arg(2):
                return [f"listener serve {item}" for item in prefixed(
                    ctx.arg_pfx(2),
                    ["default", "start default", "ssh", "ssh start"],
                )]
            if len(ctx.parts) >= 3 and ctx.parts[2].lower() in {"ssh", "ssh-operator"} and ctx.at_arg(3):
                return [f"listener serve {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), ["start"])]
            return []
        if cmd == "listener" and ctx.trailing_space and len(ctx.parts) >= 2:
            return []
        service_values = (["verbose", "details"] if cmd == "listeners" else []) + (
            ["serve"] if cmd == "listener" else []
        ) + _listener_context_completion_names(ctx.values("service_completion_names"))
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), service_values)]

    if cmd in {"start", "stop"}:
        if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "route":
            return [f"{cmd} route {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("route_names"))]
        services = _listener_context_completion_names(
            ctx.values("service_completion_names") or ctx.values("service_names")
        )
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), services + ctx.values("route_names"))]

    if cmd == "route":
        route_names = ctx.values("route_names")
        if ctx.at_arg(1):
            return [f"route {item}" for item in prefixed(ctx.arg_pfx(1),
                ["add", "start", "stop", "delete", "rm", "print"] + route_names)]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"add", "new"} and ctx.at_arg(2):
            return [
                "route add ssh-home 2222 127.0.0.1 22",
                "route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222",
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
            return [f"sessions {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ["confirm", "all", "all confirm"])]
        return []

    if cmd == "session":
        return [f"session {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("session_names"))]

    if cmd == "interact":
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        target_selectors = ctx.values("target_names") or ["1"]
        if subcmd in {"target", "agent", "host"} and ctx.at_arg(2):
            return [
                f"interact target {item}"
                for item in prefixed(ctx.arg_pfx(2), target_selectors)
            ]
        return [
            f"interact {item}"
            for item in prefixed(
                ctx.arg_pfx(1),
                [f"target {item}" for item in target_selectors] + ctx.values("session_names"),
            )
        ]

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
            return [f"daemon {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2), ["preview", "confirm"])]
        return []

    if cmd in {"modules", "module"}:
        if ctx.at_arg(1):
            values = MODULE_KIND_COMPLETIONS
            if ctx.arg_pfx(1):
                values = values + ctx.values("action_names")
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), values)]
        return []

    return None


def _line_completion_file_work_candidates(cmd, ctx):
    if cmd == "files":
        if ctx.at_arg(1):
            return prefixed(ctx.arg_pfx(1), [
                "files verbose",
                "files details",
                "stage ./grit sample-file",
                "stage start ./grit sample-file",
                "deliver sample-file",
                "deliver start sample-file",
                "unstage sample-file",
                "files clear",
            ])
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"unstage", "rm"}:
            return [f"{cmd} {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("staged_names_load"))]
        if subcmd == "clear" and ctx.at_arg(2):
            return [f"{cmd} clear confirm"]
        return None

    if cmd in {"usemodule", "useaction"}:
        return [f"use module {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("action_names"))]
    if cmd in {"run", "check"}:
        prefix = ctx.arg_pfx(1)
        runnable_names = _action_completion_values(prefix, ctx.values("runnable_action_names"))
        if not prefix:
            label_names = [name for name in runnable_names if " " in name]
            runnable_names = label_names or runnable_names
        if cmd == "run" and not prefix:
            runnable_names = _display_default_run_action_names(runnable_names)
        if cmd == "check" and not runnable_names:
            runnable_names = ["Inspect bridge status", "Inspect probe status"]
        return [f"{cmd} {item}" for item in runnable_names]

    if cmd == "stage":
        return [f"{cmd} LOCAL_PATH NAME"]

    if cmd == "binary":
        return [f"binary {item}" for item in prefixed(ctx.arg_pfx(1), [
            "scripts/grit-console grit-console",
            "start scripts/grit-console grit-console",
            "no-start scripts/grit-console grit-console",
        ])]

    if cmd == "deliver":
        staged_names = ctx.values("staged_names_snapshot")
        if staged_names:
            return [f"deliver {item}" for item in prefixed(ctx.arg_pfx(1), staged_names)]
        return [f"deliver {item}" for item in prefixed(ctx.arg_pfx(1), [
            "sample-file", "queue sample-file", "start sample-file",
        ])]
    if cmd == "queue-deliver":
        return [f"deliver queue {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]
    if cmd == "retrieve":
        examples = ["/etc/hosts", "/etc/config/network", "queue", "queue /etc/hosts"]
        if ctx.at_arg(1):
            return [f"retrieve {item}" for item in prefixed(ctx.arg_pfx(1), examples)]
        if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "queue" and ctx.at_arg(2):
            return [
                f"retrieve queue {item}"
                for item in prefixed(ctx.arg_pfx(2), ["/etc/hosts", "/etc/config/network"])
            ]
        return []
    if cmd == "unstage":
        staged_names = ctx.values("staged_names_snapshot")
        if staged_names:
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), staged_names)]
        return [f"{cmd} sample-file"]

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
            staged_names = ctx.values("staged_names_load")
            if staged_names:
                return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), staged_names)]
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), [
                "sample-file operator-host 192.168.8.241",
                "sample-file transport builtin",
            ])]
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
            staged_names = ctx.values("staged_names_load")
            examples = []
            for name in staged_names[:3]:
                examples.extend([
                    f"artifact info {name}",
                    f"artifact stamp {name} transport builtin",
                    f"artifact show {name}",
                    f"artifact clear {name}",
                ])
            examples.extend([
                "artifact info ./grit",
                "artifact stamp ./grit transport builtin",
                "artifact show ./grit",
                "artifact clear ./grit",
            ])
            return prefixed(ctx.arg_pfx(1), examples)
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "stamp":
            if ctx.at_arg(2):
                values = ctx.values("staged_names_load") or ["./grit"]
                return [f"artifact {subcmd} {item}" for item in prefixed(
                    ctx.arg_pfx(2), values
                )]
            if len(ctx.parts) >= 3:
                return [
                    f"artifact {subcmd} {ctx.parts[2]} {item}"
                    for item in prefixed(ctx.arg_pfx(3), trailer_fields)
                ]
        if subcmd in {"trailer", "configure"}:
            if ctx.at_arg(2):
                values = ctx.values("staged_names_load") or ["./grit"]
                return [f"artifact stamp {item}" for item in prefixed(
                    ctx.arg_pfx(2), values
                )]
            if len(ctx.parts) >= 3:
                return [
                    f"artifact stamp {ctx.parts[2]} {item}"
                    for item in prefixed(ctx.arg_pfx(3), trailer_fields)
                ]
        if subcmd in {"info", "inspect", "show", "clear"} and ctx.at_arg(2):
            values = ctx.values("staged_names_load") or ["./grit"]
            return [f"artifact {subcmd} {item}" for item in prefixed(
                ctx.arg_pfx(2), values
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
            if subcmd == "set":
                return _completion_build_set_examples(
                    ctx.values("build_config_fields"),
                    key_prefix=ctx.arg_pfx(2),
                )
            provider_name = "editable_build_config_keys" if subcmd == "set" else "build_config_keys"
            return [f"build {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values(provider_name))]
        return None

    if cmd == "release":
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

    if trailing_space:
        return []
    return prefixed(ctx.current, BASE_COMMANDS)


def _completion_empty_hint(prefix):
    text = str(prefix or "").strip().lower()
    if text.startswith("-"):
        return "Console commands do not use -- flags; run ? to browse word commands such as confirm."
    if text in {"profile delete", "profiles delete", "profile use", "profiles use"}:
        return "No saved profiles match; run profiles to review them or profile create lab-router to add one."
    if text.startswith("use "):
        return "No numbered or named item matches; open a list such as targets, listeners, files, or modules first."
    return "Try a shorter prefix, or use ? to browse help topics."


def _completion_overflow_hint(prefix):
    text = str(prefix or "").strip()
    lower = text.lower()
    if not lower:
        return "Narrow it: complete files, complete modules, complete listener, or complete run."
    if lower in {"run", "check"}:
        return f"Narrow it: complete {lower} bridge, modules service, or show modules service."
    return f"Narrow it: complete {text} TEXT."


def _completion_context_hint(prefix):
    text = str(prefix or "").strip().lower()
    if text == "listener probe":
        return "Probe commands work from any prompt; after use listener probe, short forms such as start, results, and config work in that menu."
    if text == "listener serve":
        return "Preset names stage that payload; add start to also start file-service."
    if text == "listener serve ssh":
        return "ssh stages the reverse SSH preset; add start to also start file-service."
    if text == "ip host":
        return "Use a listed number, or type an address directly, for example ip host 192.168.8.241."
    if text == "ip bind":
        return "Use a listed number, or type an address directly, for example ip bind 192.168.8.241."
    return ""


def print_line_completions(prefix="", candidates=None, append_event_func=None):
    candidates = list(candidates or [])
    print(f"Completions for {prefix or 'root'}:")
    if not candidates:
        print("  (no completions)")
        print(f"  {_completion_empty_hint(prefix)}")
    else:
        for candidate in candidates[:40]:
            print(f"  {candidate}")
        if len(candidates) > 40:
            print(f"  ... {len(candidates) - 40} more")
            print(f"  {_completion_overflow_hint(prefix)}")
        context_hint = _completion_context_hint(prefix)
        if context_hint:
            print(f"  {context_hint}")
        print("  Run one of these commands. For deeper choices, add a space and run complete again.")
    if append_event_func:
        append_event_func("workbench", "workbench_console_completions_shown", details={
            "prefix": str(prefix or ""),
            "candidate_count": len(candidates),
        })
