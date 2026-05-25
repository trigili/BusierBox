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

for key in ["schema", "embedded_payload", "extracted_payload", "payload_manifest", "environment", "host", "artifact"]:
    if key not in data:
        raise SystemExit(f"missing doctor key: {key}")
if "present" not in data["embedded_payload"]:
    raise SystemExit("embedded payload presence missing")
if "runtime_mode" not in data["artifact"] or "runtime_root" not in data["artifact"]:
    raise SystemExit("artifact runtime metadata missing")
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
PY
)

printf '%s\n' "doctor-json ok"
