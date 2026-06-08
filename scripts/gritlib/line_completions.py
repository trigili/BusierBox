"""Line-console completion vocabulary helpers."""

import shlex
from pathlib import Path

from gritlib.target_store import load_targets
from gritlib.workbench_jobs import load_workbench_jobs


BASE_COMMANDS = [
    "help", "complete", "search", "resource", "makerc", "history", "workspace", "status",
    "events",
    "show", "info", "options", "next", "commands", "target-commands", "copy", "set", "setg", "unset", "unsetg",
    "agents", "agent", "targets", "target", "listeners", "listener",
    "routes", "route", "sessions", "session", "jobs", "job", "use",
    "useagent", "uselistener", "useroute", "usesession", "usemodule",
    "main", "home", "root", "back", "background", "start", "stop",
    "check", "run", "execute", "exploit", "interact", "queue",
    "retrieve", "stage", "deliver", "stamp", "artifact",
    "survey", "daemon", "build", "release", "releases", "stage-release",
    "serve-binary", "trailer", "downloads", "unstage",
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
    "modules", "options", "next", "workspace", "aliases", "listeners",
    "routes", "set", "setg", "run", "jobs", "queue", "events", "retrieve", "survey", "build",
    "release", "stage", "deliver", "stamp", "artifact", "files", "view",
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
        pfx = "" if ctx.trailing_space else " ".join(ctx.parts[1:])
        return [f"show {item}" for item in prefixed(pfx, SHOW_RESOURCES)]

    if cmd == "events":
        return [f"events {item}" for item in prefixed(ctx.arg_pfx(1), [
            "n", "since", "service=", "event=", "level=", "target=",
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
        }.get(kind, "")
        return [f"use {kind} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values(candidate_provider))]

    return None


def _line_completion_context_candidates(cmd, ctx):
    if cmd in {"agent", "target", "host", "agents", "targets", "hosts",
               "useagent", "usetarget", "usehost"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("target_names"))]

    if cmd in {"listener", "service", "listeners", "services",
               "uselistener", "useservice"}:
        if cmd in {"listener", "service"} and len(ctx.parts) >= 2 and ctx.parts[1].lower() in {"probe", "probe-http"}:
            if ctx.at_arg(2):
                return [f"{cmd} {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2),
                    ["start", "queue", "results", "config", "clear", "serve", "delivery", "paste", "script"])]
            subcmd = ctx.parts[2].lower() if len(ctx.parts) >= 3 else ""
            if subcmd == "config" and ctx.at_arg(3):
                return [f"{cmd} {ctx.parts[1]} config {item}" for item in prefixed(ctx.arg_pfx(3),
                    ["1", "2", "3", "write-config", "prefer-rshell", "prefer-runtime",
                     "target-preset", "payload-preset"])]
            if subcmd == "clear" and ctx.at_arg(3):
                return [f"{cmd} {ctx.parts[1]} clear {item}" for item in prefixed(ctx.arg_pfx(3), ["all", "1", "2", "3"])]
            if subcmd == "serve" and ctx.at_arg(3):
                return [f"{cmd} {ctx.parts[1]} serve {item}" for item in prefixed(ctx.arg_pfx(3), ["start"])]
            return None
        service_values = (["-v"] if cmd in {"listeners", "services"} else []) + ctx.values("service_completion_names")
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), service_values)]

    if cmd in {"start", "stop"}:
        if len(ctx.parts) >= 2 and ctx.parts[1].lower() == "route":
            return [f"{cmd} route {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("route_names"))]
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("service_names") + ctx.values("route_names"))]

    if cmd in {"route", "useroute"}:
        route_names = ctx.values("route_names")
        if ctx.at_arg(1):
            return [f"route {item}" for item in prefixed(ctx.arg_pfx(1),
                ["add", "start", "stop", "delete", "rm", "print"] + route_names)]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"start", "stop", "delete", "rm", "remove"} and ctx.at_arg(2):
            return [f"route {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), route_names)]
        return []

    if cmd == "routes":
        return [f"routes {item}" for item in prefixed(ctx.arg_pfx(1), ["-v"] + ctx.values("route_names"))]

    if cmd == "sessions":
        if ctx.at_arg(1):
            return [f"sessions {item}" for item in prefixed(ctx.arg_pfx(1),
                ["-v", "-l", "clear", "prune"] + ctx.values("session_names"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"clear", "prune", "clean"}:
            return [f"sessions {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ["confirm", "all"])]
        return []

    if cmd in {"session", "usesession", "interact"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ["agent"] + ctx.values("session_names"))]

    if cmd == "jobs":
        return [f"jobs {item}" for item in prefixed(ctx.arg_pfx(1), ["-i", "-k", "-v"] + ctx.values("job_names"))]

    if cmd == "job":
        return [f"job {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("job_names"))]

    if cmd == "daemon":
        return [f"daemon {item}" for item in prefixed(ctx.arg_pfx(1),
            ["start", "stop", "status", "install", "print",
             "systemd-start", "systemd-stop", "systemd-restart", "systemd-status",
             "dry-run", "v", "verbose"] + ctx.values("daemon_action_ids"))]

    if cmd in {"modules", "module"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["service", "daemon", "target", "workbench"] + ctx.values("action_names"))]
        return []

    return None


def _line_completion_file_work_candidates(cmd, ctx):
    if cmd in {"files", "staged", "stagers", "loot", "downloads"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["v", "stage", "deliver", "unstage", "clear"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"unstage", "rm"}:
            return [f"{cmd} {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("staged_names_load"))]
        if subcmd == "clear" and ctx.at_arg(2):
            return [f"{cmd} clear confirm"]
        return None

    if cmd in {"usemodule", "useaction", "run", "execute", "exploit", "check"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("action_names"))]

    if cmd in {"deliver", "fetch", "deploy", "queue-fetch", "queue-deliver", "unstage", "rmfile", "rm-file"}:
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_snapshot"))]

    if cmd in {"stamp", "trailer", "configure"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("staged_names_load"))]
            return [f"{cmd} {ctx.parts[1]} {item}" for item in prefixed(ctx.arg_pfx(2), [
            "show", "clear", "operator-host", "operator-user", "ssh-port",
            "shell-port", "remote-forward-port", "target-bind-host",
            "transport", "encryption", "run-mode", "session-policy",
            "shell-provider", "zero-arg-mode", "zero-arg-log-mode",
            "runtime-mode", "noresidue-level", "retry-count",
            "retry-interval", "retry-backoff", "retry-max-interval",
            "command-queue-enable", "command-queue-port",
            "command-queue-execution", "command-queue-poll-interval",
            "command-queue-max-polls",
        ])] if len(ctx.parts) >= 2 else []

    if cmd == "artifact":
        if ctx.at_arg(1):
            return [f"artifact {item}" for item in prefixed(ctx.arg_pfx(1), [
                "stamp", "show", "clear", "trailer",
            ] + ctx.values("staged_names_load"))]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"stamp", "trailer", "configure"}:
            if ctx.at_arg(2):
                return [f"artifact {subcmd} {item}" for item in prefixed(
                    ctx.arg_pfx(2), ctx.values("staged_names_load")
                )]
            if len(ctx.parts) >= 3:
                return [f"artifact {subcmd} {ctx.parts[2]} {item}" for item in prefixed(ctx.arg_pfx(3), [
                    "show", "clear", "operator-host", "operator-user", "ssh-port",
                    "shell-port", "remote-forward-port", "target-bind-host",
                    "transport", "encryption", "run-mode", "session-policy",
                    "shell-provider", "zero-arg-mode", "zero-arg-log-mode",
                    "runtime-mode", "noresidue-level", "retry-count",
                    "retry-interval", "retry-backoff", "retry-max-interval",
                    "command-queue-enable", "command-queue-port",
                    "command-queue-execution", "command-queue-poll-interval",
                    "command-queue-max-polls",
                ])]
        if subcmd in {"show", "clear"} and ctx.at_arg(2):
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
        if subcmd in {"set", "unset"} and ctx.at_arg(2):
            return [f"build {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("build_config_keys"))]
        return None

    if cmd in {"release", "releases"}:
        if ctx.at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1),
                ["list", "stage", "recommendations", "artifacts"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd in {"stage", "use", "select"} and ctx.at_arg(2):
            return [f"{cmd} {subcmd} {item}" for item in prefixed(ctx.arg_pfx(2), ctx.values("release_selectors"))]
        return None

    if cmd == "stage-release":
        return [f"{cmd} {item}" for item in prefixed(ctx.arg_pfx(1), ctx.values("release_selectors"))]

    return None


def _line_completion_probe_survey_candidates(cmd, ctx):
    if cmd == "survey":
        if ctx.at_arg(1):
            return [f"survey {item}" for item in prefixed(ctx.arg_pfx(1),
                ["results", "config", "preset"])]
        subcmd = ctx.parts[1].lower() if len(ctx.parts) >= 2 else ""
        if subcmd == "config" and ctx.at_arg(2):
            return [f"survey config {item}" for item in prefixed(ctx.arg_pfx(2),
                ctx.values("survey_upload_paths") + ["write-config", "prefer-rshell", "prefer-runtime",
                                                      "target-preset", "payload-preset"])]
        if subcmd == "preset" and ctx.at_arg(2):
            return [f"survey preset {item}" for item in prefixed(ctx.arg_pfx(2),
                ctx.values("survey_upload_paths") + ["name", "write-local", "overwrite"])]
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
    print(f"Completions for {prefix or '<root>'}:")
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
