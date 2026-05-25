#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-/tmp}/busierbox-rshell-status-$$
mkdir "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

mkdir -p "$tmp/guard"
cat >"$tmp/guard/rshell.status" <<'EOF'
state=running
transport=ssh
rshell_pid=1234
dropbear_pid=2345
dbclient_pid=3456
started_at=1710000000
last_exit_reason=none
EOF

BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json --transport ssh >"$tmp/status.json"
python3 -m json.tool "$tmp/status.json" >/dev/null
python3 - "$tmp/status.json" "$tmp/guard" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

for key in ["state", "transport", "encryption", "run_mode", "guard_path", "pids", "log_paths", "started_at", "last_exit_reason", "connect_hint", "server_hint"]:
    if key not in data:
        raise SystemExit(f"missing rshell status key: {key}")

if data["guard_path"] != sys.argv[2]:
    raise SystemExit("guard path mismatch")
if data["pids"].get("rshell") != "1234":
    raise SystemExit("rshell pid missing")
if data["pids"].get("dropbear") != "2345":
    raise SystemExit("dropbear pid missing")
if data["pids"].get("dbclient") != "3456":
    raise SystemExit("dbclient pid missing")
if data["started_at"] != "1710000000":
    raise SystemExit("started_at missing")
if data["last_exit_reason"] != "none":
    raise SystemExit("last_exit_reason missing")
if "ssh -p" not in data["connect_hint"]:
    raise SystemExit("connect hint missing")
PY

rm -f "$tmp/guard/rshell.status"
BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json >"$tmp/inactive.json"
python3 -m json.tool "$tmp/inactive.json" >/dev/null
python3 - "$tmp/inactive.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if data["state"] != "inactive":
    raise SystemExit("inactive state missing")
if data["pids"]["rshell"] is not None:
    raise SystemExit("inactive pid should be null")
PY

printf '%s\n' "rshell-status-json ok"
