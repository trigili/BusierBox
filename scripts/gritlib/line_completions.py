"""Line-console completion vocabulary helpers."""

import shlex
from pathlib import Path


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


def completion_provider(providers, name, default=None):
    value = (providers or {}).get(name)
    if value is None:
        return list(default or [])
    if callable(value):
        value = value()
    return list(value or [])


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
    def target_names():
        names = []
        unfiltered_cfg = dict(cfg)
        unfiltered_cfg.pop("_target_id_filter", None)
        unfiltered_cfg.pop("_target_label_filter", None)
        for rec in workbench_snapshot_func(unfiltered_cfg).get("targets") or []:
            for item in [rec.get("target_id"), rec.get("label"), *(rec.get("aliases") or [])]:
                value = str(item or "").strip()
                if value:
                    names.append(value)
        return names

    def session_names():
        names = []
        for rec in workbench_snapshot_func(cfg).get("sessions") or []:
            value = str(rec.get("session_id") or Path(str(rec.get("path", ""))).name)
            if value:
                names.append(value)
        return names

    def action_names():
        names = []
        for rec in line_action_records_func():
            rec_id = str(rec.get("id") or "")
            kind = str(rec.get("kind") or "")
            if rec_id:
                names.append(rec_id)
                if kind:
                    names.append(f"{kind}:{rec_id}")
        return names

    def release_selectors():
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

    def command_queue_ids():
        ids = []
        for idx, rec in enumerate((command_queue_summary_func(cfg).get("commands") or []), 1):
            ids.append(str(idx))
            command_id = str(rec.get("id") or "")
            if command_id:
                ids.append(command_id)
        return ids

    def daemon_action_ids():
        snap = workbench_snapshot_func(cfg)
        return [
            str(rec.get("id") or "") for rec in (snap.get("operator_daemon_workflow_actions") or [])
            if rec.get("id")
        ]

    def staged_names_snapshot():
        return [
            str(name or "")
            for name in sorted((workbench_snapshot_func(cfg).get("staged") or {}).keys())
            if str(name or "")
        ]

    def session_paths():
        path_values = []
        for rec in workbench_snapshot_func(cfg).get("sessions") or []:
            for key in ("path", "session_log", "event_log"):
                value = str(rec.get(key) or "").strip()
                if value:
                    path_values.append(value)
        return path_values

    def survey_upload_paths():
        return [
            rec.get("stored_path") or ""
            for rec in find_survey_uploads_func()
            if rec.get("stored_path")
        ]

    return {
        "target_names": target_names,
        "session_names": session_names,
        "job_names": lambda: [
            str(rec.get("id") or "") for rec in workbench_snapshot_func(cfg).get("workbench_jobs") or []
            if str(rec.get("id") or "")
        ],
        "route_names": lambda: [
            str(rec.get("name") or "") for rec in bridge_profile_records_func(cfg)
            if str(rec.get("name") or "")
        ],
        "action_names": action_names,
        "release_selectors": release_selectors,
        "command_queue_ids": command_queue_ids,
        "generated_command_ids": lambda: [
            str(idx) for idx, _rec in enumerate(generated_target_command_records_func(cfg), 1)
        ],
        "build_config_keys": lambda: [
            str(rec.get("key") or "") for rec in workbench_config_field_records_func(cfg)
            if str(rec.get("key") or "")
        ],
        "service_completion_names": lambda: service_completion_names_func(service_status_rows_func(cfg)),
        "service_names": lambda: service_names_func(service_status_rows_func(cfg)),
        "daemon_action_ids": daemon_action_ids,
        "staged_names_load": lambda: sorted((load_staged_func(cfg).get("staged") or {}).keys()),
        "staged_names_snapshot": staged_names_snapshot,
        "session_paths": session_paths,
        "survey_upload_paths": survey_upload_paths,
    }


def line_completion_candidates(prefix="", providers=None):
    text = str(prefix or "")
    stripped = text.strip()
    providers = providers or {}

    def values(name):
        return completion_provider(providers, name)

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
    current = "" if trailing_space else parts[-1]

    if len(parts) == 1 and not trailing_space:
        return prefixed(current, BASE_COMMANDS)

    def arg(n):
        if len(parts) > n:
            return "" if trailing_space else parts[n]
        if len(parts) == n and trailing_space:
            return ""
        return None

    def arg_pfx(n):
        value = arg(n)
        return value if value is not None else (parts[n] if len(parts) > n else "")

    def at_arg(n):
        return (len(parts) == n and trailing_space) or (len(parts) == n + 1 and not trailing_space)

    if cmd in {"help", "?"}:
        return [f"help {item}" for item in prefixed(arg_pfx(1), HELP_TOPICS)]

    if cmd == "show":
        pfx = "" if trailing_space else " ".join(parts[1:])
        return [f"show {item}" for item in prefixed(pfx, SHOW_RESOURCES)]

    if cmd == "events":
        return [f"events {item}" for item in prefixed(arg_pfx(1), [
            "-n", "--since", "service=", "event=", "level=", "target=",
        ])]

    if cmd in {"commands", "target-commands"}:
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), ["list", "show", "copy"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd == "copy" and at_arg(2):
            return [f"{cmd} copy {item}" for item in prefixed(arg_pfx(2), values("generated_command_ids"))]

    if cmd == "copy":
        return [f"copy {item}" for item in prefixed(arg_pfx(1), values("generated_command_ids"))]

    if cmd == "use":
        if at_arg(1):
            return [f"use {item}" for item in prefixed(arg_pfx(1), USE_KINDS)]
        kind = parts[1].lower() if len(parts) >= 2 else ""
        kind_pfx = arg_pfx(2)
        candidate_provider = {
            "agent": "target_names", "target": "target_names", "host": "target_names",
            "listener": "service_completion_names", "service": "service_completion_names",
            "route": "route_names",
            "session": "session_names",
            "job": "job_names",
            "module": "action_names", "action": "action_names",
        }.get(kind, "")
        return [f"use {kind} {item}" for item in prefixed(kind_pfx, values(candidate_provider))]

    if cmd in {"agent", "target", "host", "agents", "targets", "hosts",
               "useagent", "usetarget", "usehost"}:
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("target_names"))]

    if cmd in {"listener", "service", "listeners", "services",
               "uselistener", "useservice"}:
        service_values = (["-v"] if cmd in {"listeners", "services"} else []) + values("service_completion_names")
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), service_values)]

    if cmd in {"start", "stop"}:
        if len(parts) >= 2 and parts[1].lower() == "route":
            return [f"{cmd} route {item}" for item in prefixed(arg_pfx(2), values("route_names"))]
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("service_names") + values("route_names"))]

    if cmd in {"route", "useroute"}:
        route_names = values("route_names")
        if at_arg(1):
            return [f"route {item}" for item in prefixed(arg_pfx(1),
                ["add", "start", "stop", "delete", "rm", "print"] + route_names)]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"start", "stop", "delete", "rm", "remove"} and at_arg(2):
            return [f"route {subcmd} {item}" for item in prefixed(arg_pfx(2), route_names)]
        return []

    if cmd == "routes":
        return [f"routes {item}" for item in prefixed(arg_pfx(1), ["-v"] + values("route_names"))]

    if cmd == "sessions":
        if at_arg(1):
            return [f"sessions {item}" for item in prefixed(arg_pfx(1),
                ["-v", "-l", "clear", "prune"] + values("session_names"))]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"clear", "prune", "clean"}:
            return [f"sessions {subcmd} {item}" for item in prefixed(arg_pfx(2), ["--confirm", "--all"])]
        return []

    if cmd in {"session", "usesession", "interact"}:
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), ["agent"] + values("session_names"))]

    if cmd == "jobs":
        return [f"jobs {item}" for item in prefixed(arg_pfx(1), ["-i", "-k", "-v"] + values("job_names"))]

    if cmd == "job":
        return [f"job {item}" for item in prefixed(arg_pfx(1), values("job_names"))]

    if cmd == "daemon":
        return [f"daemon {item}" for item in prefixed(arg_pfx(1),
            ["start", "stop", "status", "install", "print",
             "systemd-start", "systemd-stop", "systemd-restart", "systemd-status",
             "--dry-run", "-v", "--verbose"] + values("daemon_action_ids"))]

    if cmd in {"modules", "module"}:
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1),
                ["service", "daemon", "target", "workbench"] + values("action_names"))]
        return []

    if cmd in {"files", "staged", "stagers", "loot", "downloads"}:
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1),
                ["-v", "upload", "fetch", "unstage", "clear"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"unstage", "rm"}:
            return [f"{cmd} {subcmd} {item}" for item in prefixed(arg_pfx(2), values("staged_names_load"))]
        if subcmd == "clear" and at_arg(2):
            return [f"{cmd} clear --confirm"]

    if cmd in {"usemodule", "useaction", "run", "execute", "exploit", "check"}:
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("action_names"))]

    if cmd == "queue":
        if at_arg(1):
            return [f"queue {item}" for item in prefixed(arg_pfx(1),
                ["list", "result", "results", "clear", "command", "--"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"result", "results"} and at_arg(2):
            return [f"queue {subcmd} {item}" for item in prefixed(arg_pfx(2), values("command_queue_ids"))]
        if subcmd == "clear" and at_arg(2):
            return [f"queue clear {item}" for item in prefixed(arg_pfx(2), ["--confirm"])]

    if cmd == "build":
        if at_arg(1):
            return [f"build {item}" for item in prefixed(arg_pfx(1), ["list", "set", "unset"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"set", "unset"} and at_arg(2):
            return [f"build {subcmd} {item}" for item in prefixed(arg_pfx(2), values("build_config_keys"))]

    if cmd in {"release", "releases"}:
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1),
                ["list", "stage", "recommendations", "artifacts"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd in {"stage", "use", "select"} and at_arg(2):
            return [f"{cmd} {subcmd} {item}" for item in prefixed(arg_pfx(2), values("release_selectors"))]

    if cmd == "stage-release":
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("release_selectors"))]

    if cmd in {"fetch", "deploy", "queue-fetch", "unstage", "rmfile", "rm-file"}:
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("staged_names_snapshot"))]

    if cmd in {"configure", "trailer"}:
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("staged_names_snapshot"))]
        return [f"{cmd} {parts[1]} {item}" for item in prefixed(arg_pfx(2), [
            "--show", "--clear", "--operator-host", "--operator-user", "--ssh-port",
            "--shell-port", "--remote-forward-port", "--target-bind-host",
            "--transport", "--encryption", "--run-mode", "--session-policy",
            "--shell-provider", "--zero-arg-mode", "--zero-arg-log-mode",
            "--runtime-mode", "--noresidue-level", "--retry-count",
            "--retry-interval", "--retry-backoff", "--retry-max-interval",
            "--command-queue-enable", "--command-queue-port",
            "--command-queue-execution", "--command-queue-poll-interval",
            "--command-queue-max-polls",
        ])] if len(parts) >= 2 else []

    if cmd in {"view", "cat", "less"}:
        return [f"{cmd} {item}" for item in prefixed(arg_pfx(1), values("session_paths"))]

    if cmd == "probe":
        if at_arg(1):
            return [f"{cmd} {item}" for item in prefixed(arg_pfx(1),
                ["start", "queue", "results", "config", "clear", "serve", "delivery", "paste", "script", "--start", "--queue"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd == "config" and at_arg(2):
            return [f"probe config {item}" for item in prefixed(arg_pfx(2),
                ["1", "2", "3", "--write-config", "--prefer-rshell", "--prefer-runtime",
                 "--target-preset", "--payload-preset"])]
        if subcmd == "clear" and at_arg(2):
            return [f"probe clear {item}" for item in prefixed(arg_pfx(2), ["--all", "1", "2", "3"])]
        if subcmd == "serve" and at_arg(2):
            return [f"probe serve {item}" for item in prefixed(arg_pfx(2), ["--start"])]

    if cmd == "survey":
        if at_arg(1):
            return [f"survey {item}" for item in prefixed(arg_pfx(1),
                ["results", "config", "preset"])]
        subcmd = parts[1].lower() if len(parts) >= 2 else ""
        if subcmd == "config" and at_arg(2):
            return [f"survey config {item}" for item in prefixed(arg_pfx(2),
                values("survey_upload_paths") + ["--write-config", "--prefer-rshell", "--prefer-runtime",
                                                  "--target-preset", "--payload-preset"])]
        if subcmd == "preset" and at_arg(2):
            return [f"survey preset {item}" for item in prefixed(arg_pfx(2),
                values("survey_upload_paths") + ["--name", "--write-local", "--overwrite"])]

    return prefixed(current, BASE_COMMANDS)


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
