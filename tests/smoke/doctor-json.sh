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

for key in ["schema", "embedded_payload", "extracted_payload", "payload_manifest", "manifest_summary", "rshell_readiness", "environment", "host", "artifact"]:
    if key not in data:
        raise SystemExit(f"missing doctor key: {key}")
if "present" not in data["embedded_payload"]:
    raise SystemExit("embedded payload presence missing")
if "runtime_mode" not in data["artifact"] or "runtime_root" not in data["artifact"]:
    raise SystemExit("artifact runtime metadata missing")
for key in ["target_preset", "payload_preset", "runtime_mode", "zero_arg_mode"]:
    if key not in data["manifest_summary"]:
        raise SystemExit(f"doctor manifest summary missing {key}")
for key in ["enabled", "transport", "operator_host_set", "server_listener", "connect_hint", "warnings"]:
    if key not in data["rshell_readiness"]:
        raise SystemExit(f"doctor rshell readiness missing {key}")
if not isinstance(data["rshell_readiness"]["warnings"], list):
    raise SystemExit("doctor rshell warnings must be a list")
PY

(
    cd "$tmp"
    "$OLDPWD/$bb" extract >/dev/null
    "$OLDPWD/$bb" doctor --json >doctor-after.json
    python3 -m json.tool doctor-after.json >/dev/null
    python3 - doctor-after.json <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if not data["extracted_payload"]["present"]:
    raise SystemExit("doctor did not report extracted payload")
if not data["extracted_payload"].get("busybox_present"):
    raise SystemExit("doctor did not report payload busybox")
if not data["payload_manifest"].get("found"):
    raise SystemExit("doctor did not report payload manifest")
if not data["manifest_summary"].get("payload_manifest_found"):
    raise SystemExit("doctor manifest summary did not report payload manifest")
PY
)

printf '%s\n' "doctor-json ok"
