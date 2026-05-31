#!/bin/sh
set -eu

tmp=${TMPDIR:-local/tmp}/grit-open-memstream-fallback.$$
trap 'chmod 700 "$tmp/nowrite" 2>/dev/null || true; rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/runtime-root" "$tmp/nowrite"
chmod 500 "$tmp/nowrite"

case "$tmp" in
    /*) tmp_abs=$tmp ;;
    *) tmp_abs=$(pwd)/$tmp ;;
esac

out="$tmp_abs/grit-no-open-memstream"
runtime_root="$tmp_abs/runtime-root"

CPPFLAGS="${CPPFLAGS:-} -DGRIT_NO_OPEN_MEMSTREAM=1" \
OUT="$out" \
GRIT_RUNTIME_ROOT="$runtime_root" \
scripts/lib/build-native >/dev/null

python3 - "$out" "$tmp_abs/nowrite" <<'PY'
import base64
import json
import os
import subprocess
import sys

bb = sys.argv[1]
cwd = sys.argv[2]

def run_json(*args):
    return json.loads(subprocess.check_output([bb, *args], cwd=cwd, text=True))

manifest = run_json("manifest", "--json")
if manifest.get("runtime", {}).get("root") != os.path.dirname(cwd) + "/runtime-root":
    raise SystemExit("open-memstream fallback manifest used unexpected runtime root")
if manifest.get("grit", {}).get("artifact_tier") != "core":
    raise SystemExit("open-memstream fallback manifest missing artifact tier")

config_export = run_json("config-export", "--json")
if config_export.get("manifest", {}).get("runtime", {}).get("root") != manifest["runtime"]["root"]:
    raise SystemExit("open-memstream fallback config export lost manifest")

support_token = subprocess.check_output([bb, "doctor", "--support-token"], cwd=cwd, text=True).strip()
decoded = json.loads(base64.b64decode(support_token))
if decoded.get("manifest", {}).get("runtime", {}).get("root") != manifest["runtime"]["root"]:
    raise SystemExit("open-memstream fallback support token lost manifest")
if decoded.get("manifest", {}).get("operator_services", {}).get("command_queue", {}).get("execution_supported") is not False:
    raise SystemExit("open-memstream fallback support token lost command queue safety metadata")

print("open-memstream-fallback ok")
PY
