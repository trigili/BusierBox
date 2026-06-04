"""Line-console option metadata and mutation helpers."""

import json
from pathlib import Path

from gritlib.build_config import (
    set_workbench_build_config, shell_double_quote,
    workbench_config_field_records,
)
from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULTS, DEFAULT_CONFIG
from gritlib.event_log import append_event
from gritlib.session_state import atomic_write_json
from gritlib.shell_utils import shquote
from gritlib.target_records import (
    load_targets, selected_target_record_for_update, set_target_label,
)


SERVICE_OPTIONS = {
    "ssh": [
        ("GRIT_OPERATOR_REMOTE_FORWARD_PORT", "forward_port", "port the target opens for reverse forward"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname the target connects to"),
        ("GRIT_OPERATOR_SERVER_SSH_PORT", "GRIT_OPERATOR_SERVER_SSH_PORT", "operator SSH port"),
        ("GRIT_OPERATOR_SERVER_USER", "GRIT_OPERATOR_SERVER_USER", "SSH user on the operator side"),
        ("GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "how to handle host key verification"),
    ],
    "tls-shell": [
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on (and target connects to)"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname for target-side command"),
        ("GRIT_RSHELL_ENCRYPTION", "encryption", "transport encryption: tls / none"),
        ("GRIT_RSHELL_ALLOW_PLAINTEXT", "GRIT_RSHELL_ALLOW_PLAINTEXT", "allow unencrypted fallback"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target (auto/ash/bash/zsh)"),
    ],
    "plain-shell": [
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname for target-side command"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target"),
    ],
    "file-service": [
        ("GRIT_OPERATOR_FILE_SERVICE_PORT", "GRIT_OPERATOR_FILE_SERVICE_PORT", "file service listen port"),
        ("GRIT_OPERATOR_FILE_SERVICE_TLS", "GRIT_OPERATOR_FILE_SERVICE_TLS", "TLS for file service connections"),
        ("GRIT_OPERATOR_FILE_SERVICE_ENABLE", "GRIT_OPERATOR_FILE_SERVICE_ENABLE", "enable file service in zero-arg mode"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in staged fetch commands"),
    ],
    "command-queue": [
        ("GRIT_COMMAND_QUEUE_PORT", "GRIT_COMMAND_QUEUE_PORT", "command queue listen port"),
        ("GRIT_COMMAND_QUEUE_TLS", "GRIT_COMMAND_QUEUE_TLS", "TLS for command queue connections"),
        ("GRIT_COMMAND_QUEUE_ENABLE", "GRIT_COMMAND_QUEUE_ENABLE", "enable command queue in zero-arg mode"),
        ("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "require auth token from targets"),
        ("GRIT_COMMAND_QUEUE_TOKEN", "GRIT_COMMAND_QUEUE_TOKEN", "shared token (if token required)"),
        ("GRIT_COMMAND_QUEUE_EXECUTION", "GRIT_COMMAND_QUEUE_EXECUTION", "command execution mode"),
    ],
    "bridge": [
        ("GRIT_OPERATOR_TARGET_BIND_HOST", "GRIT_OPERATOR_TARGET_BIND_HOST", "bind address for bridge listeners"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP for generated commands"),
    ],
    "probe": [
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP listen port"),
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in probe command"),
    ],
    "probe-tftp": [
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in TFTP command"),
    ],
    "probe-ftp": [
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in FTP command"),
    ],
    "probe-dns": [
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in DNS command"),
    ],
}


GRIT_TO_CFG_KEY = {
    grit: cfg_key
    for entries in SERVICE_OPTIONS.values()
    for grit, cfg_key, _desc in entries
}


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

    status = f"{service_record.get('actual', '?')}"
    if service_record.get("configured") and service_record.get("configured") != service_record.get("actual"):
        status += f" (want {service_record.get('configured')})"
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
    print("")

    relevant = SERVICE_OPTIONS.get(service, [])
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
            rows.append({"key": grit_name, "value": value, "desc": desc, "opts": opts})

        def _opts(row):
            if row["opts"]:
                return [("options", "  ".join(str(item) for item in row["opts"]))]
            return []

        cfg["_options_keys"] = [row["key"] for row in rows]
        console_table(
            "Relevant settings  (set KEY VALUE or set N VALUE to change  |  build to see all)",
            rows,
            [
                ("Key", "key"),
                ("Value", "value"),
                ("Description", "desc"),
            ],
            detail_fn=_opts,
        )
    else:
        cfg.pop("_options_keys", None)
        print("  No specific options for this service.  Run: build")

    service_actual = str((service_record or {}).get("actual") or "")
    if target_command_records and service_actual == "listening":
        print("")
        print("  Target command:")
        for rec in target_command_records[:2]:
            command = str(rec.get("command") or "")
            print(f"    {command}")

    print("")
    print("  set KEY VALUE  /  build  /  back")


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

    if module.startswith("route/"):
        route_name = module.split("/", 1)[1]
        rec = route_record
        print(f"  route.name={route_name}")
        if rec:
            print(f"  route.listen={rec.get('listen_host', '')}:{rec.get('listen_port', '')}")
            print(f"  route.destination={rec.get('dest_host', '')}:{rec.get('dest_port', '')}")
            print(f"  route.route_path={rec.get('route_path', '') or '-'}")
            print(f"  route.state={rec.get('current_state', '') or '-'}")
            print(f"  route.active={'yes' if rec.get('active') else 'no'}")
            print(f"  route.hop_count={rec.get('hop_count', 0)}")
            print(f"  route.multi_hop={'yes' if rec.get('multi_hop') else 'no'}")
            print(f"  route.target_id={rec.get('target_id', '') or '-'}")
            print(f"  route.last_success={rec.get('last_successful_relay_at', '') or '-'}")
            print(f"  route.last_failure={rec.get('last_failure_reason', '') or '-'}")
        print(f"  route.commands=route {route_name}, route start {route_name}, route stop {route_name}, route delete {route_name}")
        print("  route.next=options, start, stop, routes -v, back")

    if module.startswith("session/"):
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
        print("  next: info, interact, sessions -v, view PATH, back")

    if module.startswith("job/"):
        job_id = module.split("/", 1)[1]
        rec = job_record
        print(f"  job.id={job_id}")
        if rec:
            print(f"  job.action={rec.get('action_id', '') or '-'}")
            print(f"  job.state={rec.get('state', '') or '-'}")
            print(f"  job.effective_state={rec.get('effective_state', '') or '-'}")
            print(f"  job.pid={rec.get('pid', '') or '-'}")
            print(f"  job.pid_managed={'yes' if rec.get('pid_managed') else 'no'}")
            print(f"  job.cancel_supported={'yes' if rec.get('cancel_supported') else 'no'}")
            print(f"  job.log_path={rec.get('log_path', '') or '-'}")
            print(f"  job.log_exists={'yes' if rec.get('log_exists') else 'no'}")
            print(f"  job.elapsed_sec={rec.get('elapsed_sec', '') if rec.get('elapsed_sec') != '' else '-'}")
            print(f"  job.exit_status={rec.get('exit_status', '') if rec.get('exit_status') != '' else '-'}")
        print("  job.next=info, jobs, jobs -v, back")

    action = selected_action
    if action:
        print(f"  action.kind={action.get('kind', '')}")
        print(f"  action.id={action.get('id', '')}")
        print(f"  action.label={action.get('label', '') or '-'}")
        print(f"  action.category={action.get('category', '') or '-'}")
        print(f"  action.workflow={action.get('workflow', '') or '-'}")
        print(f"  action.state={action.get('operator_action_state', '') or '-'}")
        print(f"  action.reason={action.get('operator_action_reason', '') or '-'}")
        print(f"  action.requires_confirmation={'yes' if action.get('requires_confirmation') else 'no'}")
        print(f"  action.background_supported={'yes' if action.get('background_supported') else 'no'}")
        print("  action.commands=check, run, run --dry-run, run --confirm")
        if action.get("background_supported"):
            print("  action.background=run -j")
        print("  action.next=info, check, run, back")
    else:
        print("  action.id=none")

    fields = workbench_config_field_records(cfg)
    if fields:
        print(f"  Build options: {len(fields)} configured  (run: build to view/edit)")


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
        print(f"set target.label={updated.get('label', '') or '-'}")
    elif key in ("notes", "target.notes"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=rec.get("aliases") or [],
            notes=text,
        )
        print(f"set target.notes={str(updated.get('notes') or '') or '-'}")
    elif key in ("alias", "target.alias", "target.aliases"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=[text],
            notes=rec.get("notes", ""),
        )
        print(f"set target.aliases={','.join(str(item) for item in updated.get('aliases') or []) or '-'}")
    else:
        raise ValueError(f"unknown option: {name}")
    record_line_target_metadata_update(cfg, target_id, action="set-option", field=key)
    return updated


def set_line_option(cfg, name, value):
    key = str(name or "").strip()
    text = str(value or "")
    if not key:
        raise ValueError("usage: set KEY VALUE  or  set N VALUE  (N = row number from options)")

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
        raise ValueError("usage: rename LABEL")
    target_id, rec = selected_target_record_for_update(cfg)
    updated = set_target_label(
        cfg,
        target_id,
        text,
        aliases=rec.get("aliases") or [],
        notes=rec.get("notes", ""),
    )
    cfg["_target_label_filter"] = str(updated.get("label") or "")
    print(f"renamed target {target_id} label={updated.get('label', '') or '-'}")
    record_line_target_metadata_update(cfg, target_id, action="rename", field="target.label")
    return updated


def note_line_target(cfg, notes):
    text = str(notes or "").strip()
    target_id, rec = selected_target_record_for_update(cfg)
    if not text:
        print(f"target.notes={str(rec.get('notes') or '') or '-'}")
        return rec
    updated = set_target_label(
        cfg,
        target_id,
        rec.get("label", ""),
        aliases=rec.get("aliases") or [],
        notes=text,
    )
    print(f"noted target {target_id} notes={str(updated.get('notes') or '') or '-'}")
    record_line_target_metadata_update(cfg, target_id, action="note", field="target.notes")
    return updated


def alias_line_target(cfg, alias):
    text = str(alias or "").strip()
    if not text:
        raise ValueError("usage: alias NAME")
    target_id, rec = selected_target_record_for_update(cfg)
    updated = set_target_label(
        cfg,
        target_id,
        rec.get("label", ""),
        aliases=[text],
        notes=rec.get("notes", ""),
    )
    print(f"aliased target {target_id} aliases={','.join(str(item) for item in updated.get('aliases') or []) or '-'}")
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
        print(f"unset target.label for {target_id}")
    elif key in ("notes", "target.notes"):
        updated = set_target_label(
            cfg,
            target_id,
            rec.get("label", ""),
            aliases=rec.get("aliases") or [],
            notes="",
        )
        print(f"unset target.notes for {target_id}")
    else:
        raise ValueError(f"unknown unset option: {name}")
    print(f"target={target_id} label={updated.get('label', '') or '-'}")
    return updated
