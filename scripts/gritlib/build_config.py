"""Build configuration field metadata and file helpers for grit-console."""

import os
import shlex
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import record_count_by_key, records_by_key


def shquote(value):
    text = str(value)
    if all(ch.isalnum() or ch in "._-/:=" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


DEFAULT_SERVER_CONFIG = Path("local/server-config.json")

WORKBENCH_BUILD_CONFIG_FIELDS = [
    ("target", "GRIT_TARGET_PRESET", "target/device preset", "mipsel-linux-4.x-musl native"),
    ("target", "GRIT_TARGETS", "target build list", "mipsel-linux-4.x-musl armv7-linux-3.x-musl"),
    ("payload", "GRIT_PAYLOAD_PRESET", "payload set", "survey-core default ssh-operator"),
    ("payload", "GRIT_BUSYBOX_GROUPS", "BusyBox applet groups", "shell fileops disk process network text system"),
    ("payload", "GRIT_HEAVY_TOOLS", "heavy payload tools", "tmux strace gdbserver"),
    ("build", "GRIT_STATIC_POLICY", "static-first build policy", "static-preferred static-only dynamic-ok"),
    ("build", "GRIT_BUILD_INTERNAL_CORE", "build internal griTTYkit core", "no yes"),
    ("runtime", "GRIT_RUNTIME_MODE", "runtime mode", "extract embedded"),
    ("runtime", "GRIT_RUNTIME_ROOT", "runtime root", "./.grit"),
    ("runtime", "GRIT_NORESIDUE_LEVEL", "no-residue behavior", "best-effort aggressive"),
    ("runtime", "GRIT_RUNTIME_ALLOW_EXTERNAL_WRITES", "allow external writes", "no yes"),
    ("trailer", "GRIT_TRAILER_OVERRIDES_ENABLE", "runtime trailer defaults", "yes no"),
    ("trailer", "GRIT_TRAILER_OVERRIDE_CATEGORIES", "trailer override categories", "runtime operator launch retry"),
    ("recovery", "GRIT_AUTORUN_GUARD_ENABLE", "autorun/recovery guard", "yes no"),
    ("recovery", "GRIT_RECOVERY_BINARY_NAME", "recovery binary name", "grit_recovery"),
    ("rshell", "GRIT_RSHELL_TRANSPORT", "reverse shell transport", "ssh socat builtin none"),
    ("rshell", "GRIT_RSHELL_RUN_MODE", "reverse shell run mode", "auto foreground background"),
    ("rshell", "GRIT_RSHELL_SESSION_POLICY", "reverse shell session policy", "single reconnect persistent"),
    ("command-queue", "GRIT_COMMAND_QUEUE_ENABLE", "command queue enable", "no yes"),
    ("command-queue", "GRIT_COMMAND_QUEUE_PORT", "command queue port", "22205"),
    ("command-queue", "GRIT_COMMAND_QUEUE_TLS", "command queue TLS", "yes no"),
    ("command-queue", "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "command queue token requirement", "yes no"),
    ("command-queue", "GRIT_COMMAND_QUEUE_TOKEN_SOURCE", "command queue token source", "manual generated"),
    ("command-queue", "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "command queue policy", "none grit-only allowlist custom"),
    ("command-queue", "GRIT_COMMAND_QUEUE_EXECUTION", "command queue execution mode", "metadata-only execute"),
    ("command-queue", "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "allow arbitrary command queue commands", "no yes"),
    ("command-queue", "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC", "command queue poll interval seconds", "5 10 30"),
    ("command-queue", "GRIT_COMMAND_QUEUE_POLL_JITTER_PCT", "command queue poll jitter percent", "0 10 20"),
    ("command-queue", "GRIT_COMMAND_QUEUE_POLL_BACKOFF", "command queue poll backoff", "none linear exponential"),
    ("command-queue", "GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC", "command queue poll max interval seconds", "60 300 900"),
    ("command-queue", "GRIT_COMMAND_QUEUE_MAX_POLLS", "command queue daemon max polls", "0 1 3"),
]

WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS = {
    "GRIT_STATIC_POLICY": ("static-preferred", "static-only", "dynamic-ok"),
    "GRIT_BUILD_INTERNAL_CORE": ("no", "yes"),
    "GRIT_NORESIDUE_LEVEL": ("best-effort", "aggressive"),
    "GRIT_RUNTIME_ALLOW_EXTERNAL_WRITES": ("no", "yes"),
    "GRIT_TRAILER_OVERRIDES_ENABLE": ("yes", "no"),
    "GRIT_AUTORUN_GUARD_ENABLE": ("yes", "no"),
    "GRIT_RSHELL_TRANSPORT": ("ssh", "socat", "builtin", "none"),
    "GRIT_RSHELL_RUN_MODE": ("auto", "foreground", "background"),
    "GRIT_RSHELL_SESSION_POLICY": ("single", "reconnect", "persistent"),
    "GRIT_COMMAND_QUEUE_ENABLE": ("no", "yes"),
    "GRIT_COMMAND_QUEUE_TLS": ("yes", "no"),
    "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": ("yes", "no"),
    "GRIT_COMMAND_QUEUE_TOKEN_SOURCE": ("manual", "generated"),
    "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": ("none", "grit-only", "allowlist", "custom"),
    "GRIT_COMMAND_QUEUE_EXECUTION": ("metadata-only", "execute"),
    "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": ("no", "yes"),
    "GRIT_COMMAND_QUEUE_POLL_BACKOFF": ("none", "linear", "exponential"),
}




def workbench_config_safety_metadata(category, key):
    boundary = {
        "target": "build-artifact",
        "payload": "build-artifact",
        "build": "build-artifact",
        "runtime": "target-runtime",
        "trailer": "target-runtime",
        "recovery": "target-runtime",
        "rshell": "reverse-access",
        "command-queue": "command-queue",
    }.get(str(category or ""), "build-config")
    control_like = boundary in ("reverse-access", "command-queue")
    note = {
        "build-artifact": "affects generated artifacts or payload contents",
        "target-runtime": "affects target runtime behavior after explicit artifact use",
        "reverse-access": "affects explicit reverse-access behavior",
        "command-queue": "affects explicit opt-in command queue behavior",
        "build-config": "updates shared build configuration",
    }.get(boundary, "updates shared build configuration")
    return {
        "safety_boundary": boundary,
        "control_like": control_like,
        "reverse_access_related": boundary == "reverse-access",
        "command_queue_related": boundary == "command-queue",
        "requires_explicit_operator_choice": control_like or key in (
            "GRIT_NORESIDUE_LEVEL",
            "GRIT_RUNTIME_ALLOW_EXTERNAL_WRITES",
            "GRIT_TRAILER_OVERRIDES_ENABLE",
            "GRIT_AUTORUN_GUARD_ENABLE",
        ),
        "safety_note": note,
    }


def build_config_path(cfg):
    return Path(str(cfg.get("_build_config_path") or cfg.get("build_config") or "configs/grit.conf"))


def parse_build_config(path):
    path = Path(path)
    values = {}
    order = []
    lines = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raw_lines = []
    for line in raw_lines:
        lines.append(line)
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if not key.replace("_", "A").isalnum() or not (key[0].isalpha() or key[0] == "_"):
            continue
        try:
            parsed = shlex.split(value, comments=False, posix=True)
            values[key] = parsed[0] if parsed else ""
        except ValueError:
            values[key] = value.strip().strip('"')
        order.append(key)
    return {"path": str(path), "exists": path.is_file(), "values": values, "order": order, "lines": lines}


def shell_double_quote(value):
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'


def write_build_config_value(path, key, value):
    if not key.startswith("GRIT_") or not key.replace("_", "A").isalnum():
        raise ValueError(f"unsupported build config key: {key}")
    path = Path(path)
    parsed = parse_build_config(path)
    lines = list(parsed.get("lines") or [])
    replacement = f"{key}={shell_double_quote(value)}"
    replaced = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(key + "="):
            lines[idx] = replacement
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


def delete_build_config_value(path, key):
    if not key.startswith("GRIT_") or not key.replace("_", "A").isalnum():
        raise ValueError(f"unsupported build config key: {key}")
    path = Path(path)
    parsed = parse_build_config(path)
    lines = []
    removed = False
    for line in parsed.get("lines") or []:
        if line.strip().startswith(key + "="):
            removed = True
            continue
        lines.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(("\n".join(lines).rstrip() + "\n") if lines else "", encoding="utf-8")
    tmp.replace(path)
    return removed


def workbench_config_field_records(cfg):
    path = build_config_path(cfg)
    parsed = parse_build_config(path)
    values = parsed.get("values") or {}
    records = []
    for category, key, label, examples in WORKBENCH_BUILD_CONFIG_FIELDS:
        example_values = examples.split()
        fixed_options = list(WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS.get(key, ()))
        records.append({
            "key": key,
            "category": category,
            "label": label,
            "value": values.get(key, ""),
            "configured": key in values,
            "config_path": str(path),
            "writes_config": True,
            "target_execution": False,
            "source_format": "shell-assignment",
            "examples": example_values,
            "options": fixed_options,
            "fixed_options": bool(fixed_options),
            "option_count": len(fixed_options),
            "set_command": "scripts/grit-console --build-config "
                           + shquote(str(path)) + " --set-build-config "
                           + shquote(f"{key}=VALUE"),
            "has_set_command": True,
            "set_command_kind": "server-build-config-set",
            **workbench_config_safety_metadata(category, key),
        })
    return records


def set_workbench_build_config(cfg, assignment, default_config=DEFAULT_SERVER_CONFIG):
    if "=" not in str(assignment):
        raise ValueError("--set-build-config expects KEY=VALUE")
    key, value = str(assignment).split("=", 1)
    key = key.strip()
    if not any(rec[1] == key for rec in WORKBENCH_BUILD_CONFIG_FIELDS):
        raise ValueError(f"unsupported guided build config key: {key}")
    options = WORKBENCH_BUILD_CONFIG_FIXED_OPTIONS.get(key)
    if options and value not in options:
        raise ValueError(f"unsupported value for {key}: {value}; expected one of: {', '.join(options)}")
    path = build_config_path(cfg)
    old_value = parse_build_config(path).get("values", {}).get(key, "")
    write_build_config_value(path, key, value)
    command = "scripts/grit-console --build-config " + shquote(str(path)) + " --set-build-config " + shquote(f"{key}={value}")
    headless_command = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --build-config "
        + shquote(str(path))
        + " --set-build-config "
        + shquote(f"{key}={value}")
    )
    append_event(cfg, "workbench", "workbench_config_updated", details={
        "config_path": str(path),
        "key": key,
        "old_value": old_value,
        "new_value": value,
        "command": command,
        "headless_command": headless_command,
    })
    return {rec.get("key"): rec for rec in workbench_config_field_records(cfg)}.get(key, {"key": key, "value": value, "config_path": str(path)})


def handle_build_config_args(cfg, args, append_event_fn=append_event):
    if args.list_build_config:
        for rec in workbench_config_field_records(cfg):
            print(
                f"{rec.get('key', '')}={shell_double_quote(rec.get('value', ''))} "
                f"category={rec.get('category', '')} "
                f"configured={'yes' if rec.get('configured') else 'no'}"
            )
            print(
                "  safety: "
                f"boundary={rec.get('safety_boundary', '')} "
                f"control_like={'yes' if rec.get('control_like') else 'no'} "
                f"explicit_choice={'yes' if rec.get('requires_explicit_operator_choice') else 'no'}"
            )
            print(f"  label: {rec.get('label', '')}")
            print(f"  set: {rec.get('set_command', '')}")
        append_event_fn(cfg, "workbench", "workbench_config_viewed", details={
            "config_path": str(build_config_path(cfg)),
            "field_count": len(workbench_config_field_records(cfg)),
        })
        return 0
    if args.set_build_config:
        for assignment in args.set_build_config:
            rec = set_workbench_build_config(cfg, assignment)
            print(f"set {rec.get('key', '')}={shell_double_quote(rec.get('value', ''))} in {rec.get('config_path', '')}")
        return 0
    return None


def unset_workbench_build_config(cfg, key, default_config=DEFAULT_SERVER_CONFIG):
    key = str(key or "").strip()
    if key.startswith("build."):
        key = key.split(".", 1)[1]
    if not any(rec[1] == key for rec in WORKBENCH_BUILD_CONFIG_FIELDS):
        raise ValueError(f"unsupported guided build config key: {key}")
    path = build_config_path(cfg)
    old_value = parse_build_config(path).get("values", {}).get(key, "")
    removed = delete_build_config_value(path, key)
    headless_command = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --build-config "
        + shquote(str(path))
        + " --set-build-config "
        + shquote(f"{key}=")
    )
    append_event(cfg, "workbench", "workbench_config_unset", details={
        "config_path": str(path),
        "key": key,
        "old_value": old_value,
        "removed": bool(removed),
        "headless_command": headless_command,
    })
    return {rec.get("key"): rec for rec in workbench_config_field_records(cfg)}.get(key, {"key": key, "value": "", "config_path": str(path)})


def workbench_config_field_indexes(records):
    return {
        "workbench_config_fields_by_key": {rec.get("key", ""): rec for rec in records or [] if rec.get("key")},
        "workbench_config_fields_by_category": records_by_key(records, "category"),
        "workbench_config_fields_by_configured": records_by_key(records, "configured"),
        "workbench_config_fields_by_fixed_options": records_by_key(records, "fixed_options"),
        "workbench_config_fields_by_writes_config": records_by_key(records, "writes_config"),
        "workbench_config_fields_by_target_execution": records_by_key(records, "target_execution"),
        "workbench_config_fields_by_source_format": records_by_key(records, "source_format"),
        "workbench_config_fields_by_has_set_command": records_by_key(records, "has_set_command"),
        "workbench_config_fields_by_set_command_kind": records_by_key(records, "set_command_kind"),
        "workbench_config_fields_by_safety_boundary": records_by_key(records, "safety_boundary"),
        "workbench_config_fields_by_control_like": records_by_key(records, "control_like"),
        "workbench_config_fields_by_reverse_access_related": records_by_key(records, "reverse_access_related"),
        "workbench_config_fields_by_command_queue_related": records_by_key(records, "command_queue_related"),
        "workbench_config_fields_by_requires_explicit_operator_choice": records_by_key(records, "requires_explicit_operator_choice"),
    }


def workbench_config_field_summary(records):
    return {
        "total_count": len(records or []),
        "configured_count": len([rec for rec in records or [] if rec.get("configured") is True]),
        "fixed_option_count": len([rec for rec in records or [] if rec.get("fixed_options") is True]),
        "category_counts": record_count_by_key(records, "category"),
        "safety_boundary_counts": record_count_by_key(records, "safety_boundary"),
        "has_set_command_count": len([rec for rec in records or [] if rec.get("has_set_command") is True]),
        "set_command_kind_counts": record_count_by_key(records, "set_command_kind"),
        "control_like_count": len([rec for rec in records or [] if rec.get("control_like") is True]),
        "reverse_access_related_count": len([rec for rec in records or [] if rec.get("reverse_access_related") is True]),
        "command_queue_related_count": len([rec for rec in records or [] if rec.get("command_queue_related") is True]),
        "requires_explicit_operator_choice_count": len([rec for rec in records or [] if rec.get("requires_explicit_operator_choice") is True]),
    }


def workbench_config_status_context(cfg):
    fields = workbench_config_field_records(cfg)
    return {
        "fields": fields,
        "index_maps": workbench_config_field_indexes(fields),
        "stats": workbench_config_field_summary(fields),
    }
