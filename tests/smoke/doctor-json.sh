#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-/tmp}/busierbox-doctor-json-$$
mkdir "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" doctor --json >"$tmp/doctor-before.json"
python3 -m json.tool "$tmp/doctor-before.json" >/dev/null
python3 - "$tmp/doctor-before.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

for key in ["schema", "embedded_payload", "extracted_payload", "extraction_runtime", "payload_manifest", "payload_inventory", "payload_runtime_health", "manifest_summary", "rshell_readiness", "runtime_config", "cleanup_ledger", "noresidue_policy", "environment", "host", "artifact"]:
    if key not in data:
        raise SystemExit(f"missing doctor key: {key}")
if "present" not in data["embedded_payload"]:
    raise SystemExit("embedded payload presence missing")
if "runtime_mode" not in data["artifact"] or "runtime_root" not in data["artifact"]:
    raise SystemExit("artifact runtime metadata missing")
for key in ["runtime_root", "fallback_root", "fallback_enabled", "required_bytes", "writable_executable", "selected_root", "roots"]:
    if key not in data["extraction_runtime"]:
        raise SystemExit(f"doctor extraction runtime missing {key}")
if not isinstance(data["extraction_runtime"]["roots"], list) or len(data["extraction_runtime"]["roots"]) < 2:
    raise SystemExit("doctor extraction runtime roots missing")
for root in data["extraction_runtime"]["roots"]:
    for key in ["role", "configured", "exists", "writable", "executable", "noexec", "available_bytes", "free_space_ok", "selected"]:
        if key not in root:
            raise SystemExit(f"doctor extraction root missing {key}")
if "present" not in data["payload_runtime_health"]:
    raise SystemExit("doctor payload runtime health presence missing")
inventory = data["payload_inventory"]
for key in ["manifest_found", "built_payload_tools", "staged_payload_tools", "overlay_enabled", "overlay_root", "overlay_applied_paths", "overlay_files", "overlay_tools", "overlay_warnings", "user_provided_tools", "included_shared_libs", "applet_symlink_skips"]:
    if key not in inventory:
        raise SystemExit(f"doctor payload inventory missing {key}")
for key in ["built_payload_tools", "staged_payload_tools", "overlay_applied_paths", "overlay_files", "overlay_tools", "overlay_warnings", "user_provided_tools", "included_shared_libs", "applet_symlink_skips"]:
    if not isinstance(inventory[key], list):
        raise SystemExit(f"doctor payload inventory {key} must be a list")
for key in ["requested_payload_tools", "missing_payload_tools", "missing_payload_tool_reasons"]:
    if key in inventory:
        raise SystemExit(f"doctor default inventory should not include {key}")
for key in ["target_preset", "payload_preset", "runtime_mode", "zero_arg_mode"]:
    if key not in data["manifest_summary"]:
        raise SystemExit(f"doctor manifest summary missing {key}")
for key in ["enabled", "transport", "operator_host_set", "server_listener", "connect_hint", "warnings", "session_policy_valid", "session_policy_errors"]:
    if key not in data["rshell_readiness"]:
        raise SystemExit(f"doctor rshell readiness missing {key}")
if not isinstance(data["rshell_readiness"]["warnings"], list):
    raise SystemExit("doctor rshell warnings must be a list")
if data["rshell_readiness"]["session_policy_valid"] is not True:
    raise SystemExit("doctor default rshell session policy should be valid")
if data["rshell_readiness"]["session_policy_errors"] != []:
    raise SystemExit("doctor default rshell session policy errors should be empty")
rshell_semantics = data["rshell_readiness"].get("session_semantics") or {}
rshell_summary = data["rshell_readiness"].get("session_policy_summary") or {}
rshell_retry = data["rshell_readiness"].get("retry") or {}
if rshell_semantics.get("retry_until_first_connection") is not True:
    raise SystemExit("doctor rshell semantics missing retry-until-first-connection")
if rshell_semantics.get("session_resume_supported") is not False:
    raise SystemExit("doctor rshell semantics must not claim session resume")
if rshell_summary.get("valid") is not True or rshell_summary.get("errors") != []:
    raise SystemExit("doctor rshell policy summary should report valid default policy")
if rshell_summary.get("pre_connect_retry_count") != rshell_retry.get("pre_connect_count"):
    raise SystemExit("doctor rshell pre-connect retry summary mismatch")
if rshell_summary.get("post_disconnect_retry_count") != rshell_retry.get("post_disconnect_count"):
    raise SystemExit("doctor rshell post-disconnect retry summary mismatch")
if data["runtime_config"].get("effective_config_source") not in {"compiled", "trailer", "env", "cli"}:
    raise SystemExit("doctor runtime config source missing")
if "trailer_override" not in data["runtime_config"]:
    raise SystemExit("doctor runtime trailer state missing")
for key in ["environment_override_count", "cli_override_count"]:
    if key not in data["runtime_config"]:
        raise SystemExit(f"doctor runtime config missing {key}")
if "path" not in data["cleanup_ledger"] or "entry_count" not in data["cleanup_ledger"]:
    raise SystemExit("doctor cleanup ledger state missing")
noresidue = data["noresidue_policy"]
if noresidue.get("forensic_no_trace") is not False:
    raise SystemExit("doctor no-residue policy must reject forensic no-trace claims")
if noresidue.get("best_effort") is not True:
    raise SystemExit("doctor no-residue policy must report best-effort cleanup")
if noresidue.get("external_writes_require_explicit_apply") is not True:
    raise SystemExit("doctor no-residue policy must require explicit external apply")
if "BusierBox-owned runtime roots" not in noresidue.get("cleanup_scope", ""):
    raise SystemExit("doctor no-residue policy cleanup scope missing")
environment = data["environment"]
for key in ["path_has_duplicates", "home_set", "shell_set"]:
    if not isinstance(environment.get(key), bool):
        raise SystemExit(f"doctor environment {key} must be boolean")
if "payload_bin_path_count" in environment and not isinstance(environment["payload_bin_path_count"], int):
    raise SystemExit("doctor environment payload_bin_path_count must be integer")
host = data["host"]
if not isinstance(host.get("mem_available_kb"), int):
    raise SystemExit("doctor host memory must be integer")
if not isinstance(host.get("devpts_available"), bool):
    raise SystemExit("doctor devpts status must be boolean")
if not isinstance(host.get("default_route_present"), bool):
    raise SystemExit("doctor default route status must be boolean")
if host.get("ptrace_probe") not in {"basic-ok", "denied", "unavailable", "unknown"}:
    raise SystemExit(f"doctor ptrace status unexpected: {host.get('ptrace_probe')!r}")
PY

BB_RSHELL_SESSION_POLICY=bogus "$bb" doctor --json >"$tmp/doctor-invalid-policy.json"
python3 -m json.tool "$tmp/doctor-invalid-policy.json" >/dev/null
python3 - "$tmp/doctor-invalid-policy.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
rshell = data.get("rshell_readiness") or {}
if rshell.get("session_policy_valid") is not False:
    raise SystemExit("doctor invalid rshell session policy should be invalid")
if "unsupported rshell session policy" not in rshell.get("session_policy_errors", []):
    raise SystemExit("doctor invalid rshell session policy error missing")
if "unsupported rshell session policy" not in (rshell.get("session_policy_summary") or {}).get("errors", []):
    raise SystemExit("doctor invalid rshell session policy summary error missing")
if (rshell.get("session_semantics") or {}).get("session_resume_supported") is not False:
    raise SystemExit("doctor invalid rshell session semantics must not claim session resume")
if "unsupported rshell session policy" not in rshell.get("warnings", []):
    raise SystemExit("doctor invalid rshell session policy warning missing")
PY

(
    cd "$tmp"
    "$OLDPWD/$bb" extract >/dev/null
    "$OLDPWD/$bb" doctor --json >doctor-after.json
    "$OLDPWD/$bb" doctor --json --include-missing >doctor-after-missing.json
    python3 -m json.tool doctor-after.json >/dev/null
    python3 - doctor-after.json <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if not data["extracted_payload"]["present"]:
    raise SystemExit("doctor did not report extracted payload")
if "extraction_runtime" not in data:
    raise SystemExit("doctor did not report extraction runtime after extract")
if data["extraction_runtime"].get("required_bytes", 0) < 1:
    raise SystemExit("doctor extraction runtime required bytes missing")
if not data["extracted_payload"].get("busybox_present"):
    raise SystemExit("doctor did not report payload busybox")
if data["extracted_payload"].get("extraction_mode") != "full":
    raise SystemExit("doctor did not report full extraction mode")
if not data["payload_manifest"].get("found"):
    raise SystemExit("doctor did not report payload manifest")
inventory = data.get("payload_inventory", {})
if not inventory.get("manifest_found"):
    raise SystemExit("doctor payload inventory did not report manifest")
for key in ["built_payload_tools", "staged_payload_tools", "overlay_files", "overlay_tools", "overlay_warnings", "user_provided_tools", "included_shared_libs"]:
    if not isinstance(inventory.get(key), list):
        raise SystemExit(f"doctor payload inventory {key} missing or not a list")
for key in ["requested_payload_tools", "missing_payload_tools", "missing_payload_tool_reasons"]:
    if key in inventory:
        raise SystemExit(f"doctor default inventory should not include {key}")
health = data.get("payload_runtime_health", {})
if not health.get("present"):
    raise SystemExit("doctor did not report payload runtime health")
for key in ["dir", "busybox_executable", "applet_symlink_count", "terminfo_present", "tmux_terminfo_present", "zsh_present", "payload_bin_path_count"]:
    if key not in health:
        raise SystemExit(f"doctor payload runtime health missing {key}")
if not health.get("busybox_executable"):
    raise SystemExit("doctor payload runtime health did not report executable busybox")
if not data["manifest_summary"].get("payload_manifest_found"):
    raise SystemExit("doctor manifest summary did not report payload manifest")
if not data["cleanup_ledger"].get("present"):
    raise SystemExit("doctor did not report cleanup ledger presence after extract")
if data["cleanup_ledger"].get("entry_count", 0) < 1:
    raise SystemExit("doctor cleanup ledger entry count did not increase")
environment = data["environment"]
if "payload_bin_path_count" not in environment:
    raise SystemExit("doctor did not report payload PATH count after extract")
if not isinstance(environment["payload_bin_path_count"], int):
    raise SystemExit("doctor payload PATH count after extract must be integer")
PY
    python3 - doctor-after-missing.json <<'PY'
import json

data = json.load(open("doctor-after-missing.json", "r", encoding="utf-8"))
inventory = data.get("payload_inventory", {})
for key in ["requested_payload_tools", "missing_payload_tools"]:
    if not isinstance(inventory.get(key), list):
        raise SystemExit(f"doctor include-missing inventory {key} missing or not a list")
if not isinstance(inventory.get("missing_payload_tool_reasons"), dict):
    raise SystemExit("doctor include-missing reasons missing or not an object")
PY
)

printf '%s\n' "doctor-json ok"
