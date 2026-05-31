#!/bin/sh
set -eu

bb=${1:-dist/grit-native-full}
tmp=${TMPDIR:-/tmp}/grit-survey-shell-$$
mkdir "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" survey --shell-script >"$tmp/survey.sh"
chmod +x "$tmp/survey.sh"
GRIT_SURVEY_PROBE_DIR="$tmp/probe" /bin/sh "$tmp/survey.sh" >"$tmp/shell-survey.json"
python3 -m json.tool "$tmp/shell-survey.json" >/dev/null

python3 - "$tmp/shell-survey.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

required = ["uname", "shell", "os_markers", "libc_hints", "filesystem", "permissions", "tools"]
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit("missing shell survey keys: " + ", ".join(missing))

if data.get("engine") != "shell":
    raise SystemExit("shell survey engine missing")
if "nodename" not in data["uname"] or "version" not in data["uname"]:
    raise SystemExit("expanded uname fields missing")
if "symlink_target" not in data["shell"]:
    raise SystemExit("shell symlink target missing")
if "dirs" not in data["filesystem"]:
    raise SystemExit("filesystem dirs missing")
for tool in ["busybox", "tar", "df", "free", "cat", "ls", "readlink", "getconf", "opkg"]:
    if tool not in data["tools"]:
        raise SystemExit("tool probe missing: " + tool)
PY

"$bb" survey --json --shell-probe >"$tmp/native-shell-probe.json"
python3 -m json.tool "$tmp/native-shell-probe.json" >/dev/null
python3 - "$tmp/native-shell-probe.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

probe = data.get("shell_probe", {})
if not probe.get("safe_for_openwrt") or not probe.get("writes_only_probe_dir"):
    raise SystemExit("shell probe provenance flags missing")
fields = set(probe.get("collected_fields", []))
for name in ["uname", "filesystem", "tools", "network_hints"]:
    if name not in fields:
        raise SystemExit("shell probe field missing: " + name)

recs = data.get("recommendations", {})
for name in [
    "target_arch_guess",
    "endian_guess",
    "kernel_floor_guess",
    "libc_guess",
    "payload_preset_recommendation",
    "runtime_mode_recommendation",
    "runtime_root_recommendation",
    "external_writes_recommendation",
    "rshell_transport_recommendation",
    "warnings",
]:
    if name not in recs:
        raise SystemExit("recommendation missing: " + name)
PY

printf '%s\n' "survey-shell ok"
