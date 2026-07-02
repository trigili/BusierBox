"""Line-console option metadata and mutation helpers."""

import json
from pathlib import Path

from gritlib.build_config import (
    build_config_path,
    set_workbench_build_config, shell_double_quote,
    workbench_config_field_records,
)
from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULTS, DEFAULT_CONFIG
from gritlib.event_log import append_event
from gritlib.event_log import EventLog
from gritlib.bridge_routes import line_route_context_commands
from gritlib.line_network import line_local_ip_candidates
from gritlib.line_probe_guidance import print_probe_menu_steps
from gritlib.line_services import line_service_status_text
from gritlib.profiles import (
    PROFILE_KEY_HINTS,
    active_profile,
    profile_records,
    profile_release_selector,
)
from gritlib.release_contexts import release_context
from gritlib.line_search import line_search_display_kind, line_search_results
from gritlib.session_state import atomic_write_json
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged
from gritlib.target_record_updates import (
    selected_target_record_for_update, set_target_label,
)
from gritlib.target_records import load_targets


SERVICE_OPTIONS = {
    "ssh": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_OPERATOR_REMOTE_FORWARD_PORT", "forward_port", "port the target opens for reverse forward"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname the target connects to"),
        ("GRIT_OPERATOR_SERVER_SSH_PORT", "GRIT_OPERATOR_SERVER_SSH_PORT", "operator SSH port"),
        ("GRIT_OPERATOR_SERVER_USER", "GRIT_OPERATOR_SERVER_USER", "SSH user on the operator side"),
        ("GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "how to handle host key verification"),
    ],
    "tls-shell": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on (and target connects to)"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
        ("GRIT_RSHELL_ENCRYPTION", "encryption", "transport encryption: tls / none"),
        ("GRIT_RSHELL_ALLOW_PLAINTEXT", "GRIT_RSHELL_ALLOW_PLAINTEXT", "allow unencrypted fallback"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target (auto/ash/bash/zsh)"),
    ],
    "plain-shell": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target"),
    ],
    "file-service": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_OPERATOR_FILE_SERVICE_PORT", "GRIT_OPERATOR_FILE_SERVICE_PORT", "file service listen port"),
        ("GRIT_OPERATOR_FILE_SERVICE_TLS", "GRIT_OPERATOR_FILE_SERVICE_TLS", "TLS for file service connections"),
        ("GRIT_OPERATOR_FILE_SERVICE_ENABLE", "GRIT_OPERATOR_FILE_SERVICE_ENABLE", "enable file service in zero-arg mode"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
    ],
    "command-queue": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_COMMAND_QUEUE_PORT", "GRIT_COMMAND_QUEUE_PORT", "command queue listen port"),
        ("GRIT_COMMAND_QUEUE_TLS", "GRIT_COMMAND_QUEUE_TLS", "TLS for command queue connections"),
        ("GRIT_COMMAND_QUEUE_ENABLE", "GRIT_COMMAND_QUEUE_ENABLE", "enable command queue in zero-arg mode"),
        ("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "require auth token from targets"),
        ("GRIT_COMMAND_QUEUE_TOKEN", "GRIT_COMMAND_QUEUE_TOKEN", "shared token (if token required)"),
        ("GRIT_COMMAND_QUEUE_EXECUTION", "GRIT_COMMAND_QUEUE_EXECUTION", "command execution mode"),
    ],
    "bridge": [
        ("listen_host", "listen_host", "local address for operator listeners"),
        ("GRIT_OPERATOR_TARGET_BIND_HOST", "GRIT_OPERATOR_TARGET_BIND_HOST", "bind address for bridge listeners"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for generated commands"),
    ],
    "probe": [
        ("listen_host", "listen_host", "local address for probe listeners"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP listen port"),
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
    ],
    "probe-tftp": [
        ("listen_host", "listen_host", "local address for probe TFTP listener"),
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
    ],
    "probe-ftp": [
        ("listen_host", "listen_host", "local address for probe FTP listener"),
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
    ],
    "probe-dns": [
        ("listen_host", "listen_host", "local address for probe DNS listener"),
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP address or hostname for commands run on the target"),
    ],
}


GRIT_TO_CFG_KEY = {
    grit: cfg_key
    for entries in SERVICE_OPTIONS.values()
    for grit, cfg_key, _desc in entries
}

SERVICE_OPTION_LABELS = {
    "listen_host": "bind IP",
    "GRIT_OPERATOR_REMOTE_FORWARD_PORT": "remote forward port",
    "GRIT_OPERATOR_SERVER_HOST": "operator host",
    "GRIT_OPERATOR_SERVER_SSH_PORT": "operator SSH port",
    "GRIT_OPERATOR_SERVER_USER": "operator SSH user",
    "GRIT_OPERATOR_KNOWN_HOSTS_POLICY": "host key policy",
    "GRIT_RSHELL_SOCAT_PORT": "listener port",
    "GRIT_RSHELL_ENCRYPTION": "encryption",
    "GRIT_RSHELL_ALLOW_PLAINTEXT": "plaintext fallback",
    "GRIT_RSHELL_TRANSPORT": "transport",
    "GRIT_RSHELL_SHELL_PROVIDER": "shell provider",
    "GRIT_OPERATOR_FILE_SERVICE_PORT": "file service port",
    "GRIT_OPERATOR_FILE_SERVICE_TLS": "file service TLS",
    "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "file service auto-start",
    "GRIT_COMMAND_QUEUE_PORT": "command queue port",
    "GRIT_COMMAND_QUEUE_TLS": "command queue TLS",
    "GRIT_COMMAND_QUEUE_ENABLE": "command queue auto-start",
    "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "require queue token",
    "GRIT_COMMAND_QUEUE_TOKEN": "queue token",
    "GRIT_COMMAND_QUEUE_EXECUTION": "queue execution",
    "GRIT_OPERATOR_TARGET_BIND_HOST": "bridge bind IP",
    "GRIT_PROBE_PORT": "probe HTTP port",
    "GRIT_PROBE_TFTP_PORT": "probe TFTP port",
    "GRIT_PROBE_FTP_PORT": "probe FTP port",
    "GRIT_PROBE_DNS_PORT": "probe DNS port",
    "GRIT_PROBE_DNS_NAME": "probe DNS name",
}


def line_service_option_display_key(key):
    return SERVICE_OPTION_LABELS.get(key, key)


def line_service_option_display_value(key, value):
    text = str(value)
    if key == "GRIT_RSHELL_TRANSPORT" and text.strip().lower() == "none":
        return "artifact needed"
    if key == "GRIT_RSHELL_SHELL_PROVIDER" and text.strip().lower() in ("", "(not set)", "none"):
        return "auto"
    return text


def _line_service_option_example_value(row, cfg):
    key = str((row or {}).get("key") or "")
    value = str((row or {}).get("value") or "").strip()
    if key == "listen_host":
        return _line_ip_options_example(cfg)
    if key == "GRIT_RSHELL_TRANSPORT" and value == "artifact needed":
        return "ssh"
    if key == "GRIT_RSHELL_SHELL_PROVIDER" and value == "auto":
        return "auto"
    if value and value != "(not set)":
        return value
    examples = {
        "GRIT_OPERATOR_REMOTE_FORWARD_PORT": "2222",
        "GRIT_OPERATOR_SERVER_HOST": _line_ip_options_example(cfg),
        "GRIT_OPERATOR_SERVER_SSH_PORT": "22",
        "GRIT_OPERATOR_SERVER_USER": "root",
        "GRIT_OPERATOR_KNOWN_HOSTS_POLICY": "accept-new",
        "GRIT_RSHELL_SOCAT_PORT": "22203",
        "GRIT_RSHELL_ENCRYPTION": "tls",
        "GRIT_RSHELL_ALLOW_PLAINTEXT": "no",
        "GRIT_OPERATOR_FILE_SERVICE_PORT": "22206",
        "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_PORT": "22205",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_TOKEN": "changeme",
        "GRIT_COMMAND_QUEUE_EXECUTION": "metadata-only",
        "GRIT_OPERATOR_TARGET_BIND_HOST": _line_ip_options_example(cfg),
        "GRIT_PROBE_PORT": "22207",
        "GRIT_PROBE_TFTP_PORT": "22269",
        "GRIT_PROBE_FTP_PORT": "22221",
        "GRIT_PROBE_DNS_PORT": "22253",
        "GRIT_PROBE_DNS_NAME": "probe.grit",
    }
    return examples.get(key, "value")


def _line_service_option_example(rows, cfg):
    for idx, row in enumerate(rows or [], start=1):
        if str(row.get("key") or "") != "listen_host":
            return f"set {idx} {_line_service_option_example_value(row, cfg)}"
    if rows:
        return f"set 1 {_line_service_option_example_value(rows[0], cfg)}"
    return "set 1 value"


def print_line_service_options(
    cfg,
    service,
    service_record=None,
    display_name_func=None,
    build_fields=None,
    target_command_records=None,
):
    service = str(service or "").strip()
    service_record = service_record if isinstance(service_record, dict) else {}
    display_name_func = display_name_func or (lambda name: name)
    build_fields = build_fields if isinstance(build_fields, dict) else {}
    target_command_records = list(target_command_records or [])

    status = line_service_status_text(service_record) if service_record else "?"
    bind = ""
    tls = ""
    if service_record:
        host = service_record.get("bind_address") or ""
        port = service_record.get("port") or ""
        bind = f"  |  {host}:{port}" if host else (f"  |  :{port}" if port else "")
        tls = "  |  TLS: yes" if service_record.get("tls") else ""

    display_name = display_name_func(service)
    print(f"{display_name}  ─  {status}{bind}{tls if service_record else ''}")
    if display_name != service:
        print(f"transport: {service}")
    service_actual = str((service_record or {}).get("actual") or "")
    if service_actual == "starting":
        print(f"startup requested; open listeners or events service={service} to check readiness")
    print("")

    relevant = SERVICE_OPTIONS.get(service, [])
    rows = []
    if relevant:
        rows = []
        for grit_name, cfg_key, desc in relevant:
            if cfg_key == "build":
                field = build_fields.get(grit_name) or {}
                value = field.get("value") or field.get("compiled") or "(not set)"
                opts = field.get("options") or []
            else:
                raw = cfg.get(cfg_key)
                value = str(raw) if raw not in (None, "") else "(not set)"
                opts = []
            value = line_service_option_display_value(grit_name, value)
            rows.append({
                "key": grit_name,
                "setting": line_service_option_display_key(grit_name),
                "value": value,
                "desc": desc,
                "opts": opts,
            })

        def _opts(row):
            if row["opts"]:
                return [("options", "  ".join(str(item) for item in row["opts"]))]
            return []

        cfg["_options_keys"] = [row["key"] for row in rows]
        console_table(
            "Relevant settings",
            rows,
            [
                ("Setting", "setting"),
                ("Value", "value"),
                ("Description", "desc"),
            ],
            detail_fn=_opts,
        )
        set_example = _line_service_option_example(rows, cfg)
        print(f"  edit setting: {set_example}")
        print("  build")
        guided_setup_keys = {
            row["key"]
            for row in rows
            if (
                (row.get("key") == "GRIT_RSHELL_TRANSPORT" and row.get("value") == "artifact needed")
                or (row.get("key") == "GRIT_RSHELL_SHELL_PROVIDER" and row.get("value") == "auto")
            )
        }
        if guided_setup_keys:
            print("  note: reverse-shell artifact settings can come from the active profile, build config, or this menu")
        if "GRIT_RSHELL_TRANSPORT" in guided_setup_keys:
            print("  set transport: set 4 ssh; profile default: profile set transport ssh")
            print_probe_menu_steps()
            print("  before target command: after profile setup, listener serve ssh start stages the reverse SSH artifact")
        if "GRIT_RSHELL_SHELL_PROVIDER" in guided_setup_keys:
            print("  set shell provider: set 5 auto")
        has_bind_menu = any(row["key"] == "listen_host" for row in rows)
        if has_bind_menu:
            bind_example = _line_ip_options_example(cfg)
            print(f"  choose bind IP: ips, ip bind 1, ip bind {bind_example}")
    else:
        cfg.pop("_options_keys", None)
        print("  No specific options for this service.  Run: build")

    if target_command_records and service_actual == "listening":
        print("")
        print("  Target command:")
        for rec in target_command_records[:2]:
            command = str(rec.get("command") or "")
            print(f"    {command}")

    print("")
    if relevant and has_bind_menu:
        bind_example = _line_ip_options_example(cfg)
        print(f"  {_line_service_option_example(rows, cfg)}, ips, ip bind 1, ip bind {bind_example}, build, back")
    else:
        print(f"  {_line_service_option_example(rows, cfg)}, build, back")


def _print_line_route_context_options(module, route_record):
    route_name = module.split("/", 1)[1]
    rec = route_record
    print(f"Route: {route_name}")
    if rec:
        print(f"  listen: {rec.get('listen_host', '')}:{rec.get('listen_port', '')}")
        print(f"  destination: {rec.get('dest_host', '')}:{rec.get('dest_port', '')}")
        print(f"  path: {rec.get('route_path', '') or '-'}")
        print(f"  status: {rec.get('current_state', '') or '-'}")
        print(f"  active: {'yes' if rec.get('active') else 'no'}")
        print(f"  hops: {rec.get('hop_count', 0)}")
        print(f"  multi-hop: {'yes' if rec.get('multi_hop') else 'no'}")
        print(f"  target: {rec.get('target_id', '') or '-'}")
        print(f"  last success: {rec.get('last_successful_relay_at', '') or '-'}")
        print(f"  last failure: {rec.get('last_failure_reason', '') or '-'}")
    if rec and rec.get("active"):
        print(f"  commands: route {route_name}, route stop {route_name}")
    else:
        print(f"  commands: route {route_name}, route start {route_name}")
    print(f"  delete: route delete {route_name}, route delete {route_name} confirm")
    print("  next: " + ", ".join(line_route_context_commands(rec)))


def _print_line_session_context_options(module, session_record):
    session_id = module.split("/", 1)[1]
    rec = session_record
    print(f"Session: {session_id}")
    if rec:
        path = str(rec.get("path") or "")
        print(f"  service: {rec.get('service', '') or '-'}")
        print(f"  state: {rec.get('state', '') or '-'}")
        print(f"  exit reason: {rec.get('exit_reason', '') or '-'}")
        print(f"  updated: {rec.get('updated_at', '') or '-'}")
        print(f"  path: {path}")
        print(
            "  activity: "
            f"{rec.get('upload_count', 0)} uploads, "
            f"{rec.get('fetch_count', 0)} fetches, "
            f"{rec.get('event_count', 0)} events"
        )
        if rec.get("session_log"):
            print(f"  session log: {rec.get('session_log', '')}")
        if rec.get("event_log"):
            print(f"  event log: {rec.get('event_log', '')}")
    print("  next: info, interact, sessions verbose, view ./README.md, back")


def _print_line_job_context_options(module, job_record):
    job_id = module.split("/", 1)[1]
    rec = job_record
    print(f"Job: {job_id}")
    if rec:
        elapsed = rec.get("elapsed_sec", "")
        exit_status = rec.get("exit_status", "")
        print(f"  module: {rec.get('action_id', '') or '-'}")
        print(f"  state: {rec.get('effective_state', '') or rec.get('state', '') or '-'}")
        print(f"  pid: {rec.get('pid', '') or '-'}")
        print(f"  managed: {'yes' if rec.get('pid_managed') else 'no'}")
        print(f"  cancel supported: {'yes' if rec.get('cancel_supported') else 'no'}")
        print(f"  log: {rec.get('log_path', '') or '-'}")
        print(f"  log exists: {'yes' if rec.get('log_exists') else 'no'}")
        print(f"  elapsed: {elapsed if elapsed != '' else '-'} sec")
        print(f"  exit: {exit_status if exit_status != '' else '-'}")
    if rec.get("cancel_supported"):
        print("  cancel: cancel, jobs cancel " + job_id)
    print("  next: info, cancel, jobs, jobs verbose, back" if rec.get("cancel_supported") else "  next: info, jobs, jobs verbose, back")


def _print_line_action_context_options(action):
    action_kind = action.get("kind", "")
    action_id = action.get("id", "")
    action_name = f"{action_kind}:{action_id}" if action_kind else action_id
    label = action.get("label", "") or action_name or "-"
    readiness = action.get("operator_action_reason", "") or "-"
    if readiness == "run-now":
        readiness = "ready to run"
    workflow = str(action.get("workflow", "") or "-").replace("-", " ")
    print(f"Module: {label}")
    print(f"  select: use module {label}")
    print(f"  type: {action.get('category', '') or '-'}")
    print(f"  area: {workflow}")
    print(f"  status: {action.get('operator_action_state', '') or '-'}")
    print(f"  run check: {readiness}")
    print(f"  confirmation needed: {'yes' if action.get('requires_confirmation') else 'no'}")
    print(f"  can run in background: {'yes' if action.get('background_supported') else 'no'}")
    commands = ["check", "preview", "run"]
    if action.get("requires_confirmation"):
        commands.append("run confirm")
    print("  commands: " + ", ".join(commands))
    if action.get("background_supported"):
        print("  background command: run job")
    print("  next: info, check, run, back")


def _print_line_build_options_summary(cfg):
    fields = workbench_config_field_records(cfg)
    if fields:
        print(f"  Build options: {len(fields)} configured  (run: build to view/edit)")


def _print_line_build_options(cfg):
    fields = workbench_config_field_records(cfg)
    configured = [rec for rec in fields if rec.get("configured")]
    explicit = [rec for rec in fields if rec.get("requires_explicit_operator_choice")]
    cfg["_options_keys"] = [str(rec.get("key") or "") for rec in fields]
    rows = []
    for idx, rec in enumerate(fields, 1):
        value = shell_double_quote(str(rec.get("value") or ""))
        if len(value) > 30:
            value = value[:27] + "..."
        choices = "  ".join(str(item) for item in rec.get("options") or [])
        if not choices and rec.get("examples"):
            choices = "examples: " + "  ".join(str(item) for item in rec.get("examples")[:3])
        rows.append({
            "row": str(idx),
            "key": str(rec.get("key") or ""),
            "value": value,
            "choices": choices or "-",
            "purpose": str(rec.get("label") or ""),
        })
    print("Build:")
    print(f"  config: {build_config_path(cfg)}")
    print(f"  configured: {len(configured)}/{len(fields)}")
    print(f"  explicit choices: {len(explicit)}")
    console_table(
        "Guided build fields",
        rows,
        [
            ("Row", "row"),
            ("Key", "key"),
            ("Value", "value"),
            ("Choices", "choices"),
            ("Purpose", "purpose"),
        ],
        show_numbers=False,
    )
    print("  edit: set 16 ssh, build set GRIT_RUNTIME_ROOT ./.grit, build set 16 ssh, build unset 16")
    print("  details: build verbose")
    print("  help: build ?")


def _print_line_events_options(cfg):
    log = EventLog(cfg)
    stats = log.stats(limit=8)
    print("Events:")
    print(f"  log: {log.path}")
    print(
        "  records: "
        f"{stats.get('total_count', 0)} total, "
        f"{stats.get('invalid_count', 0)} invalid"
    )
    print(f"  first: {stats.get('first_event_at') or '-'}")
    print(f"  latest: {stats.get('latest_event_at') or '-'}")

    def _counts(values, limit=5):
        items = sorted((values or {}).items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:limit]
        return ", ".join(f"{key}={count}" for key, count in items if key) or "-"

    print(f"  services: {_counts(stats.get('by_service'))}")
    print(f"  levels: {_counts(stats.get('by_level'))}")
    print(f"  statuses: {_counts(stats.get('by_detail_status'))}")
    print("  browse: events, events n 50, events since 2h")
    print("  filters: events service=NAME level=LEVEL status=TEXT")
    print("  ids: events file=NAME command=ID job=ID module=ID")
    print(f"  raw log: view {log.path}")
    print("  help: events ?")


def _print_line_console_options(cfg):
    print("Console reference:")
    print("  scope: these commands work from any prompt; do not prefix them with console")
    print("  history: history, history 50")
    print("  replay: !!, !1, repeat 1")
    print("  command files: resource ./commands.gritrc, makerc ./last-session.gritrc")
    print("  completions: complete, complete listener")
    print("  search: search listener, use 1")
    print("  navigation: back")
    print("  return to root: main  (aliases: home/root)")
    print("  quit from root: quit  (alias: exit)")
    print("  help: console ?")


def _print_line_workflow_options():
    print("Workflow:")
    print_probe_menu_steps()
    print("  profile: profiles, profile")
    print("  after profile setup: listener serve, listener serve start default")
    print("  reverse SSH after profile setup: listener serve ssh start")
    print("  after staging: files, deliver sample-file")
    print("  help: workflow ?")


def _print_line_aliases_options():
    print("Aliases:")
    print("  preferred forms: targets, listeners, routes, files, modules")
    print("  legacy aliases: accepted for older command files; use aliases ? to inspect")
    print("  selection: use target lab-router, use listener probe, use route ssh-home, use module Inspect bridge status")
    print("  help: aliases ?")


def _print_line_list_context_options(module, cfg=None):
    module = str(module or "")
    records = {
        "targets": (
            "Targets",
            "list: targets",
            "select after targets list has rows: use target 1, use target lab-router",
            "activity: queue targets, show events",
            "help: targets ?",
        ),
        "listeners": (
            "Listeners",
            "list: listeners, listeners verbose",
            "select: listener 1, listener probe, use listener probe",
            "controls: start 1, start probe, stop 1, stop probe",
            "help: listeners ?",
        ),
        "routes": (
            "Routes",
            "list: routes, routes verbose",
            "select after routes list has rows: route 1, route ssh-home, use route ssh-home",
            "create: route add ssh-home 2222 127.0.0.1 22",
            "help: routes ?",
        ),
        "sessions": (
            "Sessions",
            "list: sessions, sessions verbose",
            "select after sessions list has rows: session 1, use session 1",
            "create sessions: start plain-shell, start ssh, start command-queue",
            "help: sessions ?",
        ),
        "jobs": (
            "Jobs",
            "list: jobs",
            "inspect after jobs list has rows: job 1, jobs info 1",
            "control after jobs list has rows: jobs cancel 1",
            "help: jobs ?",
        ),
        "modules": (
            "Modules",
            "overview: modules",
            "list: modules service, modules daemon, modules target, modules operator",
            "verbose: modules verbose service",
            "select: use 1, use module Inspect bridge status",
            "help: modules ?",
        ),
        "queue": (
            "Queue",
            "list: queue, queue list, queue targets",
            "add: queue uname -a",
            "preview cleanup: queue clear",
            "confirm cleanup: queue clear confirm",
            "help: queue ?",
        ),
    }.get(module)
    if module == "files":
        staged = {}
        if isinstance(cfg, dict) and (cfg.get("staged_files") or cfg.get("operator_session_dir")):
            staged = load_staged(cfg).get("staged") or {}
        if staged:
            records = (
                "Files",
                "list: files",
                "deliver staged file: deliver NAME, deliver start NAME, deliver queue NAME",
                "stage more: stage ./grit sample-file, release stage by_device:gl-mt3000",
                "help: files ?",
            )
        else:
            records = (
                "Files",
                "list: files",
                "stage: stage ./grit sample-file, stage start ./grit sample-file",
                "release staging: release, release stage by_device:gl-mt3000",
                "help: files ?",
            )
    if not records:
        return False
    print(records[0] + ":")
    for line in records[1:]:
        print(f"  {line}")
    return True


def _print_line_search_options(cfg):
    results = line_search_results(cfg)
    print("Search:")
    print(f"  active numbered results: {len(results)}")
    if results:
        first = results[0] if isinstance(results[0], dict) else {}
        kind = line_search_display_kind(first.get("kind") or "-")
        print(f"  first result: {kind} {first.get('label') or '-'}")
    print("  search: search listener")
    print("  select: use 1")
    print("  keep results: ?, options, next, complete listener")
    print("  replace results: targets, listeners, files, or search listener")
    print("  history replay:")
    print("    !1")
    print("    repeat 1")
    print("  help: search ?")


def _line_ip_options_example(cfg):
    local_ips = (cfg or {}).get("local_ips") or []
    candidates = line_local_ip_candidates({"local_ips": local_ips} if local_ips else {})
    return str(candidates[0]) if candidates else "192.168.8.241"


def _print_line_ip_options(cfg=None):
    example_ip = _line_ip_options_example(cfg)
    print("IP address selection")
    print("  list: ip")
    print(f"  advertised host for commands run on the target: ip host 1, ip host {example_ip}")
    print(f"  listener bind address: ip bind 1, ip bind {example_ip}")
    print("  help: ip ?")


def _print_selected_target_options(cfg):
    target_id = str((cfg or {}).get("_target_id_filter") or "")
    if not target_id:
        return False
    rec = (load_targets(cfg).get("targets") or {}).get(target_id, {})
    label = str(rec.get("label") or cfg.get("_target_label_filter") or "")
    aliases = ", ".join(str(item) for item in rec.get("aliases") or []) or "-"
    notes = str(rec.get("notes") or "")
    print(f"Target: {target_id}")
    print(f"  label: {label or '-'}")
    print(f"  aliases: {aliases}")
    print(f"  notes: {notes or '-'}")
    print(f"  state: {rec.get('connectivity_state') or '-'}")
    print(f"  pending work: {rec.get('mailbox_pending_work_count') or 0}")
    print("  commands: rename LABEL, note TEXT, alias NAME, clear target")
    print("  next: info, next, check-ins, queue uname -a, sessions, back")
    return True


def _print_line_survey_options():
    print("Survey:")
    print("  purpose: turn a received full target survey into build config or a target preset")
    print("  status: survey, survey results")
    print("  config: survey config, survey config PATH, survey config PATH write-config FILE")
    print("  preset: survey preset PATH name NAME, survey preset PATH name NAME write-local")
    print("  target-to-operator: deploy griTTYkit, then run grit survey retrieve on the target")
    print("  help: survey ?")


def _print_line_profiles_options(cfg):
    records = profile_records(cfg)
    active = active_profile(cfg)
    example = (active or {}).get("name") or ((records[0] or {}).get("name") if records else "lab-router")
    print("Profiles:")
    print(f"  saved: {len(records)}")
    print(f"  active: {active.get('name') or '-'}")
    if active:
        print(f"  target: {active.get('arch') or active.get('uname_m') or '-'} {active.get('uname_r') or ''}".rstrip())
        print(f"  operator_host: {active.get('operator_host') or '-'}")
        print(f"  payload: {active.get('preferred_payload_preset') or 'default'}")
        print(f"  transport: {active.get('preferred_transport') or 'ssh'}")
    if records:
        print(f"  commands: profiles, profile, profile use {example}, profile use 1, profile create lab-router")
    else:
        print("  commands: profiles, profile, profile create lab-router")
    print("  edit: profile set FIELD VALUE")
    print("  editable keys: " + ", ".join(PROFILE_KEY_HINTS))
    if records:
        print(f"  cleanup: profile delete {example}, then profile delete {example} confirm")
        print("  cleanup by number: profile delete 1, then profile delete 1 confirm")
    print("  from probe results:")
    print("    use listener probe")
    print("    config")
    print("    profile from probe 1")
    print("  deployment: listener serve start default, listener serve ssh start")


def _print_line_artifact_options(cfg):
    staged = load_staged(cfg).get("staged") or {}
    records = []
    for idx, (name, rec) in enumerate(sorted(staged.items()), 1):
        if not isinstance(rec, dict):
            continue
        records.append({
            "num": str(idx),
            "name": str(name),
            "kind": str(rec.get("stage_kind") or rec.get("payload_preset") or "file"),
            "configured": "yes" if rec.get("configured") else "no",
        })
    profile = active_profile(cfg)
    print("Artifacts:")
    print(f"  staged: {len(records)}")
    print(f"  release dir: {cfg.get('release_dir') or '(not set)'}")
    if profile:
        print(f"  active profile: {profile.get('name') or '-'}")
        print(f"  operator_host: {profile.get('operator_host') or '-'}")
        print(f"  transport: {profile.get('preferred_transport') or 'ssh'}")
    else:
        print("  active profile: none")
    if records:
        console_table(
            "Staged artifacts",
            records,
            [
                ("#", "num"),
                ("Name", "name"),
                ("Kind", "kind"),
                ("Configured", "configured"),
            ],
        )
    print("  inspect: artifact info grit, artifact info 1, artifact info ./grit")
    print("  stamp: artifact show grit, artifact stamp grit transport builtin, artifact clear grit")
    print("  deliver command: files, deliver grit")
    print("  help: artifact ?")


def _print_line_release_options(cfg):
    rel = release_context(cfg)
    profile = active_profile(cfg)
    print("Release:")
    print(f"  release dir: {cfg.get('release_dir') or '(not set)'}")
    if rel:
        print(f"  name: {rel.get('release_name') or '-'}")
        print(
            "  inventory: "
            f"{len(rel.get('recommendation_records') or [])} recommendations, "
            f"{len(rel.get('artifacts') or [])} artifacts, "
            f"{len(rel.get('devices') or [])} devices, "
            f"{len(rel.get('tuples') or [])} tuples"
        )
    else:
        print("  detected: no")
        print("  set release dir: set release_dir /path/to/extracted-release")
    if profile:
        selector = profile_release_selector(profile)
        print(f"  active profile: {profile.get('name') or '-'}")
        print(f"  target: {profile.get('arch') or profile.get('uname_m') or '-'} {profile.get('uname_r') or ''}".rstrip())
        print(f"  default selector: {selector or '(auto-match from profile)'}")
        print(f"  ssh preset: release stage ssh start")
    else:
        print("  active profile: none")
        print_probe_menu_steps()
        print("  serve: listener serve start, listener serve ssh start")
    print("  browse: release")
    print("  stage: release stage by_device:gl-mt3000, release stage start by_device:gl-mt3000")
    print("  path stage: release stage dist/releases/lab/bin/grit-target-full")
    print("  after staging: files, deliver grit")
    print("  help: release ?")


def print_line_context_options(
    cfg,
    module,
    route_record=None,
    session_record=None,
    job_record=None,
    selected_action=None,
):
    module = str(module or "root")
    route_record = route_record if isinstance(route_record, dict) else {}
    session_record = session_record if isinstance(session_record, dict) else {}
    job_record = job_record if isinstance(job_record, dict) else {}
    selected_action = selected_action if isinstance(selected_action, dict) else {}

    if _print_line_list_context_options(module, cfg):
        return

    if module.startswith("route/"):
        _print_line_route_context_options(module, route_record)
        return

    if module.startswith("session/"):
        _print_line_session_context_options(module, session_record)
        return

    if module.startswith("job/"):
        _print_line_job_context_options(module, job_record)
        return

    if module == "survey":
        _print_line_survey_options()
        return

    if module == "profiles":
        _print_line_profiles_options(cfg)
        return

    if module == "build":
        _print_line_build_options(cfg)
        return

    if module == "events":
        _print_line_events_options(cfg)
        return

    if module == "console":
        _print_line_console_options(cfg)
        return

    if module == "workflow":
        _print_line_workflow_options()
        return

    if module == "aliases":
        _print_line_aliases_options()
        return

    if module == "search":
        _print_line_search_options(cfg)
        return

    if module == "ip":
        _print_line_ip_options(cfg)
        return

    if module == "artifact":
        _print_line_artifact_options(cfg)
        return

    if module == "release":
        _print_line_release_options(cfg)
        return

    action = selected_action
    if action:
        _print_line_action_context_options(action)
        return
    elif _print_selected_target_options(cfg):
        return
    else:
        print("Current area: workspace")
        print("  choose: targets, listeners, routes, sessions, modules, jobs, or search listener")

    _print_line_build_options_summary(cfg)


def print_line_options(
    cfg,
    *,
    module="",
    service_record_func=None,
    display_name_func=None,
    build_fields_func=None,
    target_command_records_func=None,
    route_record_func=None,
    session_record_func=None,
    job_record_func=None,
    selected_action_func=None,
):
    module = str(module or "root")
    service = ""
    if module.startswith(("listener/", "service/")):
        service = module.split("/", 1)[1]
    elif module in SERVICE_OPTIONS:
        service = module
    if service:
        build_records = build_fields_func() if build_fields_func else workbench_config_field_records(cfg)
        target_records = target_command_records_func() if target_command_records_func else []
        print_line_service_options(
            cfg,
            service,
            service_record=service_record_func(service) if service_record_func else {},
            display_name_func=display_name_func,
            build_fields={r.get("key", ""): r for r in build_records},
            target_command_records=[
                rec for rec in target_records
                if str(rec.get("service") or "") == service
            ],
        )
        return
    print_line_context_options(
        cfg,
        module,
        route_record=route_record_func(module.split("/", 1)[1]) if module.startswith("route/") and route_record_func else {},
        session_record=session_record_func(module.split("/", 1)[1]) if module.startswith("session/") and session_record_func else {},
        job_record=job_record_func(module.split("/", 1)[1]) if module.startswith("job/") and job_record_func else {},
        selected_action=selected_action_func() if selected_action_func else {},
    )


def record_line_target_metadata_update(cfg, target_id, action="", field="", default_config=DEFAULT_CONFIG):
    rec = (load_targets(cfg).get("targets") or {}).get(target_id, {})
    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --set-target-label "
        + shquote(target_id)
        + " --target-label "
        + shquote(str(rec.get("label") or ""))
    )
    append_event(cfg, "workbench", "workbench_target_metadata_updated", details={
        "action": action,
        "field": field,
        "target_id": target_id,
        "target_label": rec.get("label", ""),
        "aliases": rec.get("aliases") or [],
        "notes": rec.get("notes", ""),
        "headless_command": headless,
    })
    return headless


def parse_line_option_assignment(args):
    args = list(args or [])
    if args and "=" in str(args[0]):
        key, value = str(args[0]).split("=", 1)
        if len(args) > 1:
            value = value + " " + " ".join(str(item) for item in args[1:])
    else:
        key = str(args[0]) if args else ""
        value = " ".join(str(item) for item in args[1:]).strip()
    return key, value


def parse_line_option_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd in {"set", "setg"}:
        key, value = parse_line_option_assignment(args)
        return {
            "action": "set",
            "scope": "global" if cmd == "setg" else "context",
            "key": key,
            "value": value,
        }
    if cmd in {"unset", "unsetg"}:
        return {
            "action": "unset",
            "scope": "global" if cmd == "unsetg" else "context",
            "key": args[0] if args else "",
        }
    return {}


def dispatch_line_option_command(
    option_cmd,
    *,
    set_global_func=None,
    set_context_func=None,
    unset_global_func=None,
    unset_context_func=None,
):
    try:
        action = (option_cmd or {}).get("action")
        scope = (option_cmd or {}).get("scope")
        if action == "set" and scope == "global" and set_global_func:
            return set_global_func(option_cmd.get("key", ""), option_cmd.get("value", ""))
        if action == "set" and set_context_func:
            return set_context_func(option_cmd.get("key", ""), option_cmd.get("value", ""))
        if action == "unset" and not option_cmd.get("key", ""):
            if scope == "global":
                print("usage:\n  unsetg KEY")
            else:
                print("usage:")
                print("  unset KEY")
                print("  back")
            return None
        if scope == "global" and unset_global_func:
            return unset_global_func(option_cmd.get("key", ""))
        if unset_context_func:
            return unset_context_func(option_cmd.get("key", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported option command")


def parse_line_target_metadata_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd == "rename":
        return {"action": "rename", "value": " ".join(args or []).strip()}
    if cmd in {"note", "notes"}:
        return {"action": "note", "value": " ".join(args or []).strip()}
    if cmd == "alias":
        return {"action": "alias", "value": " ".join(args or []).strip()}
    return {}


def dispatch_line_target_metadata_command(
    metadata_cmd,
    *,
    rename_func=None,
    note_func=None,
    alias_func=None,
):
    try:
        action = (metadata_cmd or {}).get("action")
        value = (metadata_cmd or {}).get("value", "")
        if action == "rename" and rename_func:
            return rename_func(value)
        if action == "note" and note_func:
            return note_func(value)
        if action == "alias" and alias_func:
            return alias_func(value)
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported target metadata command")


def set_line_target_option(cfg, name, value):
    key = str(name or "").strip()
    text = str(value or "")
    target_id, rec = selected_target_record_for_update(cfg)
    if key in ("label", "target.label"):
        updated = set_target_label(
            cfg,
            target_id,
            text,
            aliases=rec.get("aliases") or [],
            notes=rec.get("notes", ""),
        )
        cfg["_target_label_filter"] = str(updated.get("label") or "")
        print(f"label: {updated.get('label', '') or '-'}")
    elif key in ("notes", "target.notes"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=rec.get("aliases") or [],
            notes=text,
        )
        print(f"notes: {str(updated.get('notes') or '') or '-'}")
    elif key in ("alias", "target.alias", "target.aliases"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=[text],
            notes=rec.get("notes", ""),
        )
        print(f"aliases: {', '.join(str(item) for item in updated.get('aliases') or []) or '-'}")
    else:
        raise ValueError(f"unknown option: {name}")
    record_line_target_metadata_update(cfg, target_id, action="set-option", field=key)
    return updated


def set_line_option(cfg, name, value):
    key = str(name or "").strip()
    text = str(value or "")
    if not key:
        raise ValueError(
            "usage:\n"
            "  set KEY VALUE\n"
            "  set ROW VALUE\n"
            "  options"
        )

    if key.isdigit():
        keys = cfg.get("_options_keys") or []
        idx = int(key) - 1
        if 0 <= idx < len(keys):
            key = keys[idx]
        else:
            raise ValueError(f"no option at row {key} — run: options")

    if key in {"release_dir", "release-dir", "server.release_dir"}:
        cfg["release_dir"] = text
        config_path = Path(str(cfg.get("_config_path") or DEFAULT_CONFIG))
        try:
            existing = {}
            if config_path.is_file():
                try:
                    existing = json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            if not isinstance(existing, dict):
                existing = {}
            existing["release_dir"] = text
            config_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(config_path, existing)
            print(f"set release_dir={shell_double_quote(text)}  (saved to {config_path})")
        except OSError as exc:
            print(f"set release_dir={shell_double_quote(text)}  (warning: could not save: {exc})")
        return {}

    build_keys = {rec.get("key") for rec in workbench_config_field_records(cfg)}
    if key.startswith("build."):
        key = key.split(".", 1)[1]
    if key in build_keys:
        rec = set_workbench_build_config(cfg, f"{key}={text}")
        print(f"set {rec.get('key', key)}={shell_double_quote(rec.get('value', text))}")
        return rec

    cfg_key = GRIT_TO_CFG_KEY.get(key)
    if cfg_key == "build":
        if key in build_keys:
            rec = set_workbench_build_config(cfg, f"{key}={text}")
            print(f"set {rec.get('key', key)}={shell_double_quote(rec.get('value', text))}")
            return rec
        print(f"{key} is a build config key — run: build set {key} {text}")
        return {}

    if cfg_key is not None:
        default_val = DEFAULTS.get(cfg_key)
        try:
            typed_val = type(default_val)(text) if default_val is not None else text
        except (ValueError, TypeError):
            typed_val = text
        cfg[cfg_key] = typed_val
        config_path = Path(str(cfg.get("_config_path") or DEFAULT_CONFIG))
        try:
            existing = {}
            if config_path.is_file():
                try:
                    existing = json.loads(config_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            if not isinstance(existing, dict):
                existing = {}
            existing[cfg_key] = typed_val
            config_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(config_path, existing)
            print(f"set {key}={shell_double_quote(str(typed_val))}  (saved to {config_path})")
        except OSError as exc:
            print(f"set {key}={shell_double_quote(str(typed_val))}  (warning: could not save: {exc})")
        return {cfg_key: typed_val}

    return set_line_target_option(cfg, key, text)


def rename_line_target(cfg, label):
    text = str(label or "").strip()
    if not text:
        raise ValueError("usage:\n  rename LABEL")
    target_id, rec = selected_target_record_for_update(cfg)
    updated = set_target_label(
        cfg,
        target_id,
        text,
        aliases=rec.get("aliases") or [],
        notes=rec.get("notes", ""),
    )
    cfg["_target_label_filter"] = str(updated.get("label") or "")
    print(f"target renamed: {target_id}")
    print(f"  label: {updated.get('label', '') or '-'}")
    record_line_target_metadata_update(cfg, target_id, action="rename", field="target.label")
    return updated


def note_line_target(cfg, notes):
    text = str(notes or "").strip()
    target_id, rec = selected_target_record_for_update(cfg)
    if not text:
        print(f"notes: {str(rec.get('notes') or '') or '-'}")
        return rec
    updated = set_target_label(
        cfg,
        target_id,
        rec.get("label", ""),
        aliases=rec.get("aliases") or [],
        notes=text,
    )
    print(f"target note updated: {target_id}")
    print(f"  notes: {str(updated.get('notes') or '') or '-'}")
    record_line_target_metadata_update(cfg, target_id, action="note", field="target.notes")
    return updated


def alias_line_target(cfg, alias):
    text = str(alias or "").strip()
    if not text:
        raise ValueError("usage:\n  alias NAME")
    target_id, rec = selected_target_record_for_update(cfg)
    updated = set_target_label(
        cfg,
        target_id,
        rec.get("label", ""),
        aliases=[text],
        notes=rec.get("notes", ""),
    )
    print(f"target alias updated: {target_id}")
    print(f"  aliases: {', '.join(str(item) for item in updated.get('aliases') or []) or '-'}")
    record_line_target_metadata_update(cfg, target_id, action="alias", field="target.aliases")
    return updated


def unset_line_target_option(cfg, name, clear_module=None):
    key = str(name or "").strip()
    if key in ("module", "action"):
        if clear_module is not None:
            clear_module()
        return {}
    target_id, rec = selected_target_record_for_update(cfg)
    if key in ("label", "target.label"):
        updated = set_target_label(
            cfg,
            target_id,
            "",
            aliases=rec.get("aliases") or [],
            notes=rec.get("notes", ""),
        )
        cfg.pop("_target_label_filter", None)
        print(f"target label cleared: {target_id}")
    elif key in ("notes", "target.notes"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=rec.get("aliases") or [],
            notes="",
        )
        print(f"target notes cleared: {target_id}")
    else:
        raise ValueError(f"unknown unset option: {name}")
    print(f"  target {target_id} ({updated.get('label', '') or '-'})")
    return updated
