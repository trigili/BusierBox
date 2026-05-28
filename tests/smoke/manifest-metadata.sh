#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-local/tmp}/manifest-metadata

[ -x "$bb" ] || {
    printf '%s\n' "manifest-metadata: missing executable $bb" >&2
    exit 1
}

case "$bb" in
    /*) bb_abs=$bb ;;
    *) bb_abs=$(pwd)/$bb ;;
esac

python3 - "$bb" <<'PY'
import json
import subprocess
import sys

bb = sys.argv[1]
manifest = json.loads(subprocess.check_output([bb, "manifest", "--json"], text=True))
manifest_missing = json.loads(subprocess.check_output([bb, "manifest", "--json", "--include-missing"], text=True))
config = {}
for line in subprocess.check_output([bb, "config-info"], text=True).splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        config[k] = v

required = [
    ("busierbox", "payload_version"),
    ("busierbox", "artifact_tier"),
    ("busierbox", "build_timestamp"),
    ("busierbox", "git_commit"),
    ("target", "preset"),
    ("target", "name"),
    ("target", "arch"),
    ("target", "endian"),
    ("target", "cpu"),
    ("target", "abi"),
    ("target", "libc"),
    ("target", "kernel_floor"),
    ("target", "static_policy"),
    ("payload", "preset"),
    ("payload", "gdbserver_provider"),
    ("runtime", "mode"),
    ("runtime", "noresidue_level"),
    ("runtime", "noresidue_policy"),
    ("runtime", "root"),
    ("zero_arg", "mode"),
    ("rshell", "transport"),
    ("rshell", "session_policy"),
    ("rshell", "session_policy_valid"),
    ("rshell", "session_policy_errors"),
    ("rshell", "operator_host"),
    ("rshell", "operator_shell_port"),
    ("rshell", "operator_ssh_port"),
    ("rshell", "remote_forward_port"),
    ("rshell", "target_dropbear"),
    ("rshell", "authkeys_mode"),
    ("rshell", "retry"),
    ("operator_services", "command_queue"),
    ("dotfiles", "enabled"),
    ("dotfiles", "bash"),
    ("overlay", "enabled"),
    ("licensing", "project_license"),
    ("licensing", "combined_gplv2_compatible"),
    ("licensing", "not_busybox_fork"),
    ("licensing", "third_party"),
]
for section, field in required:
    if section not in manifest or field not in manifest[section]:
        raise SystemExit(f"manifest-metadata: missing {section}.{field}")

for section in ("compiled_config", "effective_config", "trailer_override"):
    if section not in manifest:
        raise SystemExit(f"manifest-metadata: missing {section}")
if not isinstance(manifest["compiled_config"], dict):
    raise SystemExit("manifest-metadata: compiled_config must be an object")
if not isinstance(manifest["effective_config"], dict):
    raise SystemExit("manifest-metadata: effective_config must be an object")
if not isinstance(manifest["trailer_override"], dict):
    raise SystemExit("manifest-metadata: trailer_override must be an object")
licensing = manifest.get("licensing") or {}
if licensing.get("project_license") != "GPL-2.0-or-later":
    raise SystemExit("manifest-metadata: project license missing from manifest")
if licensing.get("supervisor_license") != "GPL-2.0-or-later":
    raise SystemExit("manifest-metadata: supervisor license missing from manifest")
if licensing.get("combined_gplv2_compatible") is not True:
    raise SystemExit("manifest-metadata: GPL compatibility flag missing")
if licensing.get("not_busybox_fork") is not True:
    raise SystemExit("manifest-metadata: BusyBox fork boundary missing")
third_party = {item.get("name"): item for item in licensing.get("third_party", [])}
for name, license_id in {
    "BusyBox": "GPL-2.0",
    "Buildroot": "GPL-2.0-or-later with package exceptions",
    "doom-ascii": "GPL-2.0-or-later",
    "miniz": "MIT OR Unlicense",
}.items():
    if third_party.get(name, {}).get("license") != license_id:
        raise SystemExit(f"manifest-metadata: third-party license missing for {name}")
native_features = manifest.get("native_features") or {}
if native_features.get("persistence") is not True or native_features.get("recovery_alias") is not True:
    raise SystemExit("manifest-metadata: recovery native feature flags missing")
noresidue = manifest["runtime"].get("noresidue_policy") or {}
if noresidue.get("level") != manifest["runtime"].get("noresidue_level"):
    raise SystemExit("manifest-metadata: no-residue policy level mismatch")
if config.get("noresidue_policy_level") != manifest["runtime"].get("noresidue_level"):
    raise SystemExit("manifest-metadata: config-info no-residue policy level mismatch")
if noresidue.get("best_effort") is not True:
    raise SystemExit("manifest-metadata: no-residue policy must report best-effort cleanup")
if config.get("noresidue_policy_best_effort") != "yes":
    raise SystemExit("manifest-metadata: config-info no-residue best-effort flag missing")
if noresidue.get("forensic_no_trace") is not False:
    raise SystemExit("manifest-metadata: no-residue policy must reject forensic no-trace claims")
if config.get("noresidue_policy_forensic_no_trace") != "no":
    raise SystemExit("manifest-metadata: config-info no-residue no-trace boundary missing")
if noresidue.get("external_writes_require_explicit_apply") is not True:
    raise SystemExit("manifest-metadata: no-residue policy must require explicit external apply")
if config.get("noresidue_policy_external_writes_require_explicit_apply") != "yes":
    raise SystemExit("manifest-metadata: config-info external write gate missing")
if "BusierBox-owned runtime roots" not in noresidue.get("cleanup_scope", ""):
    raise SystemExit("manifest-metadata: no-residue policy cleanup scope missing")
if "BusierBox-owned runtime roots" not in config.get("noresidue_policy_cleanup_scope", ""):
    raise SystemExit("manifest-metadata: config-info no-residue cleanup scope missing")
payload_tools = manifest.get("payload_tools") or {}
for key in ("requested_payload_tools", "missing_payload_tools", "missing_payload_tool_reasons"):
    if key in payload_tools:
        raise SystemExit(f"manifest-metadata: default manifest should not include {key}")
payload_tools_missing = manifest_missing.get("payload_tools") or {}
for key in ("requested_payload_tools", "missing_payload_tools"):
    if not isinstance(payload_tools_missing.get(key), list):
        raise SystemExit(f"manifest-metadata: include-missing manifest lacks list {key}")
if not isinstance(payload_tools_missing.get("missing_payload_tool_reasons"), dict):
    raise SystemExit("manifest-metadata: include-missing manifest lacks missing reasons object")

trailer = manifest["trailer_override"]
for key in ("present", "valid", "encoding", "override_count", "status"):
    if key not in trailer:
        raise SystemExit(f"manifest-metadata: missing trailer_override.{key}")
if trailer["present"] is not False:
    raise SystemExit("manifest-metadata: unexpected trailer in baseline artifact")
if trailer["valid"] is not False:
    raise SystemExit("manifest-metadata: absent trailer should not be valid")
if trailer["override_count"] != 0:
    raise SystemExit("manifest-metadata: absent trailer should have zero overrides")

for key in (
    "BB_RUNTIME_MODE",
    "BB_NORESIDUE_LEVEL",
    "BB_RUNTIME_ROOT",
    "BB_ZERO_ARG_MODE",
    "BB_RSHELL_TRANSPORT",
    "BB_RSHELL_SESSION_POLICY",
    "BB_OPERATOR_SERVER_HOST",
    "BB_OPERATOR_FILE_SERVICE_PORT",
    "BB_COMMAND_QUEUE_ENABLE",
    "BB_COMMAND_QUEUE_ALLOWED_COMMANDS",
    "BB_COMMAND_QUEUE_ALLOW_ARBITRARY",
    "BB_COMMAND_QUEUE_POLL_INTERVAL_SEC",
    "BB_COMMAND_QUEUE_POLL_JITTER_PCT",
    "BB_COMMAND_QUEUE_POLL_BACKOFF",
    "BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC",
    "BB_COMMAND_QUEUE_MAX_POLLS",
):
    if key not in manifest["compiled_config"]:
        raise SystemExit(f"manifest-metadata: compiled_config missing {key}")
    if key not in manifest["effective_config"]:
        raise SystemExit(f"manifest-metadata: effective_config missing {key}")
    if manifest["compiled_config"][key] != manifest["effective_config"][key]:
        raise SystemExit(f"manifest-metadata: baseline effective config differs for {key}")

checks = [
    (manifest["busierbox"]["artifact_tier"], config.get("artifact_tier"), "artifact_tier"),
    (manifest["busierbox"]["payload_version"], config.get("payload_version"), "payload_version"),
    (manifest["payload"]["gdbserver_provider"], config.get("gdbserver_provider"), "gdbserver_provider"),
    (manifest["runtime"]["mode"], config.get("runtime_mode"), "runtime_mode"),
    (manifest["runtime"]["noresidue_level"], config.get("noresidue_level"), "noresidue_level"),
    (manifest["runtime"]["root"], config.get("runtime_root"), "runtime_root"),
    (manifest["zero_arg"]["mode"], config.get("zero_arg_mode"), "zero_arg_mode"),
    (manifest["rshell"]["transport"], config.get("rshell_transport"), "rshell_transport"),
    (manifest["rshell"]["session_policy"], config.get("rshell_session_policy"), "rshell_session_policy"),
    (manifest["rshell"]["session_policy_valid"], True, "rshell_session_policy_valid"),
    (manifest["rshell"]["operator_shell_port"], config.get("rshell_socat_port"), "rshell_socat_port"),
    (manifest["rshell"]["remote_forward_port"], config.get("operator_reverse_ssh_catch_hint", "").split()[2] if config.get("operator_reverse_ssh_catch_hint") else None, "remote_forward_port"),
]
for got, want, name in checks:
    if got != want:
        raise SystemExit(f"manifest-metadata: {name} mismatch: manifest={got!r} config-info={want!r}")

file_service = manifest.get("operator_services", {}).get("file_service", {})
if file_service.get("port") != manifest["effective_config"]["BB_OPERATOR_FILE_SERVICE_PORT"]:
    raise SystemExit("manifest-metadata: file service port does not match effective config")
if file_service.get("tls") != manifest["effective_config"]["BB_OPERATOR_FILE_SERVICE_TLS"]:
    raise SystemExit("manifest-metadata: file service tls does not match effective config")
if file_service.get("target_initiated") is not True or file_service.get("receive_only") is not True:
    raise SystemExit("manifest-metadata: file service safety metadata missing")
command_queue = manifest.get("operator_services", {}).get("command_queue", {})
if command_queue.get("enabled") != manifest["effective_config"]["BB_COMMAND_QUEUE_ENABLE"]:
    raise SystemExit("manifest-metadata: command queue enable does not match effective config")
if command_queue.get("allowed_commands") != manifest["effective_config"]["BB_COMMAND_QUEUE_ALLOWED_COMMANDS"]:
    raise SystemExit("manifest-metadata: command queue policy does not match effective config")
if command_queue.get("poll_interval_sec") != manifest["effective_config"]["BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"]:
    raise SystemExit("manifest-metadata: command queue poll interval does not match effective config")
if command_queue.get("poll_jitter_pct") != manifest["effective_config"]["BB_COMMAND_QUEUE_POLL_JITTER_PCT"]:
    raise SystemExit("manifest-metadata: command queue poll jitter does not match effective config")
if command_queue.get("poll_backoff") != manifest["effective_config"]["BB_COMMAND_QUEUE_POLL_BACKOFF"]:
    raise SystemExit("manifest-metadata: command queue poll backoff does not match effective config")
if command_queue.get("poll_max_interval_sec") != manifest["effective_config"]["BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC"]:
    raise SystemExit("manifest-metadata: command queue poll max interval does not match effective config")
if command_queue.get("max_polls") != manifest["effective_config"]["BB_COMMAND_QUEUE_MAX_POLLS"]:
    raise SystemExit("manifest-metadata: command queue max polls does not match effective config")
expected_state = manifest["effective_config"]["BB_RUNTIME_ROOT"] + "/run/command-queue-daemon.state"
if command_queue.get("daemon_state_file") != expected_state:
    raise SystemExit("manifest-metadata: command queue daemon state file missing")
if (command_queue.get("daemon_state_file_supported") is not True or
        command_queue.get("daemon_status_supported") is not True or
        command_queue.get("daemon_stop_supported") is not True):
    raise SystemExit("manifest-metadata: command queue daemon lifecycle metadata missing")
if command_queue.get("policy_valid") is not True or command_queue.get("policy_errors") != []:
    raise SystemExit("manifest-metadata: command queue policy validity metadata missing")
if command_queue.get("arbitrary_policy_requested") is not False or command_queue.get("arbitrary_execution_allowed") is not False:
    raise SystemExit("manifest-metadata: command queue arbitrary policy boundary missing")
if (command_queue.get("poll_transport_supported") is not True or
        command_queue.get("live_polling_supported") is not True or
        command_queue.get("delivery_supported") is not False or
        command_queue.get("result_upload_supported") is not True):
    raise SystemExit("manifest-metadata: command queue live-poll safety metadata missing")
if command_queue.get("executes_commands") is not False or command_queue.get("default_enabled") is not False:
    raise SystemExit("manifest-metadata: command queue safety metadata missing")

retry = manifest["rshell"]["retry"]
for key in ["count", "interval_sec", "jitter_pct", "backoff", "max_interval_sec"]:
    if key not in retry:
        raise SystemExit(f"manifest-metadata: missing rshell.retry.{key}")

print("manifest-metadata ok")
PY

mkdir -p "$tmp"
"$bb_abs" manifest >"$tmp/manifest.txt"
grep -q '^project_license=GPL-2.0-or-later$' "$tmp/manifest.txt"
grep -q '^combined_gplv2_compatible=yes$' "$tmp/manifest.txt"
grep -q '^not_busybox_fork=yes$' "$tmp/manifest.txt"
grep -q '^third_party_component=BusyBox GPL-2.0 payload applets$' "$tmp/manifest.txt"
grep -q '^third_party_component=Buildroot GPL-2.0-or-later target build system$' "$tmp/manifest.txt"

BB_RSHELL_SESSION_POLICY=bogus "$bb_abs" manifest --json >"$tmp/manifest-invalid-policy.json"
python3 -m json.tool "$tmp/manifest-invalid-policy.json" >/dev/null
python3 - "$tmp/manifest-invalid-policy.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], "r", encoding="utf-8"))
rshell = manifest.get("rshell") or {}
if rshell.get("session_policy") != "bogus":
    raise SystemExit("manifest invalid policy did not preserve effective value")
if rshell.get("session_policy_valid") is not False:
    raise SystemExit("manifest invalid policy should report session_policy_valid=false")
if "unsupported rshell session policy" not in rshell.get("session_policy_errors", []):
    raise SystemExit("manifest invalid policy error missing")
PY

rm -rf "$tmp"
mkdir -p "$tmp"
(
    cd "$tmp"
    "$bb_abs" extract --force >/dev/null
    test -f ./.busierbox/manifest/artifact.json
    python3 -m json.tool ./.busierbox/manifest/artifact.json >/dev/null
)
rm -rf "$tmp"

printf '%s\n' "manifest artifact file ok"
