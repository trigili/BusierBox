#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-local/tmp}/reality-test-$$
mkdir -p "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" reality-test --help >/dev/null
"$bb" reality-test push --help >/dev/null
"$bb" list --plain | grep -q '^native reality-test$'

BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" reality-test >"$tmp/reality.txt"
grep -q '^BusierBox reality-test$' "$tmp/reality.txt"
grep -q '^runtime_root=' "$tmp/reality.txt"
grep -q '^fork ' "$tmp/reality.txt"
grep -q '^spawn_sh ' "$tmp/reality.txt"
grep -q '^bind_localhost ' "$tmp/reality.txt"
grep -q '^summary pass=' "$tmp/reality.txt"

BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" reality-test --json >"$tmp/reality.json"
python3 -m json.tool "$tmp/reality.json" >/dev/null
python3 - "$tmp/reality.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
if doc.get("schema") != 1:
    raise SystemExit("reality-test: missing schema")
checks = doc.get("checks")
if not isinstance(checks, list):
    raise SystemExit("reality-test: checks must be a list")
by_name = {item.get("name"): item for item in checks}
required = [
    "runtime_root_writable",
    "temporary_file",
    "runtime_root_executable",
    "fork",
    "spawn_sh",
    "pty",
    "pipes",
    "read_proc",
    "read_sys",
    "bind_localhost",
    "connect_operator",
    "upload_operator",
    "fetch_operator",
    "extract_core_payload",
    "exec_payload_busybox",
    "exec_heavy_tool",
    "tmp_noexec",
    "rootfs_read_only",
    "ptrace",
    "dmesg_readable",
    "procfs_partial",
]
missing = [name for name in required if name not in by_name]
if missing:
    raise SystemExit(f"reality-test: missing checks: {missing}")
for item in checks:
    if item.get("status") not in {"pass", "fail", "skipped"}:
        raise SystemExit(f"reality-test: bad status {item!r}")
    if "ok" not in item or "detail" not in item or "skipped" not in item or "type" not in item:
        raise SystemExit(f"reality-test: incomplete check {item!r}")
    if item["type"] not in {"capability", "constraint", "operator"}:
        raise SystemExit(f"reality-test: bad check type {item!r}")
    if item["type"] == "constraint":
        if "detected" not in item:
            raise SystemExit(f"reality-test: constraint check missing detected field {item!r}")
    elif "available" not in item:
        raise SystemExit(f"reality-test: capability/operator check missing available field {item!r}")
if by_name["tmp_noexec"].get("type") != "constraint":
    raise SystemExit("reality-test: tmp_noexec should be a structured constraint")
if by_name["rootfs_read_only"].get("type") != "constraint":
    raise SystemExit("reality-test: rootfs_read_only should be a structured constraint")
if by_name["procfs_partial"].get("type") != "constraint":
    raise SystemExit("reality-test: procfs_partial should be a structured constraint")
if by_name["spawn_sh"].get("type") != "capability" or "available" not in by_name["spawn_sh"]:
    raise SystemExit("reality-test: spawn_sh should expose structured availability")
if by_name["upload_operator"].get("type") != "operator" or "available" not in by_name["upload_operator"]:
    raise SystemExit("reality-test: upload_operator should expose structured operator availability")
summary = doc.get("summary", {})
if summary.get("check_count") != len(checks):
    raise SystemExit("reality-test: summary check_count does not match checks")
if summary.get("pass", 0) + summary.get("fail", 0) + summary.get("skipped", 0) != len(checks):
    raise SystemExit("reality-test: summary counts do not match checks")
api = (doc.get("api_collections") or {}).get("checks") or {}
if api.get("count_summary_key") != "summary.check_count":
    raise SystemExit("reality-test: checks api collection missing summary key")
if set(api.get("indexes") or []) < {"checks_by_name", "checks_by_status", "checks_by_type"}:
    raise SystemExit("reality-test: checks api collection missing indexes")
if doc.get("checks_by_name", {}).get("spawn_sh") != [required.index("spawn_sh")]:
    raise SystemExit("reality-test: checks_by_name lookup is wrong")
status_indexes = doc.get("checks_by_status") or {}
type_indexes = doc.get("checks_by_type") or {}
for status in ("pass", "fail", "skipped"):
    expected = [idx for idx, item in enumerate(checks) if item["status"] == status]
    if status_indexes.get(status) != expected:
        raise SystemExit(f"reality-test: checks_by_status drift for {status}")
for check_type in ("capability", "operator", "constraint"):
    expected = [idx for idx, item in enumerate(checks) if item["type"] == check_type]
    if type_indexes.get(check_type) != expected:
        raise SystemExit(f"reality-test: checks_by_type drift for {check_type}")
if summary.get("operator_pass", 0) + summary.get("operator_fail", 0) + summary.get("operator_skipped", 0) != 3:
    raise SystemExit("reality-test: summary should count all operator checks")
if by_name["upload_operator"]["status"] != "skipped":
    raise SystemExit("reality-test: upload_operator should be skipped without explicit side-effect setup")
if by_name["fetch_operator"]["status"] != "skipped":
    raise SystemExit("reality-test: fetch_operator should be skipped without staged file")
if summary.get("capability_pass", 0) + summary.get("capability_fail", 0) <= 0:
    raise SystemExit("reality-test: summary should expose capability counts")
constraints = summary.get("constraints") or {}
for name in ("tmp_noexec", "rootfs_read_only", "procfs_partial"):
    if constraints.get(name) is not by_name[name].get("detected"):
        raise SystemExit(f"reality-test: summary constraint drift for {name}")
PY

port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
staged="$tmp/staged-fetch.txt"
printf '%s\n' "staged reality fetch" >"$staged"
staged_spaced="$tmp/staged reality fetch spaced.txt"
printf '%s\n' "staged reality fetch with spaces" >"$staged_spaced"
operator_dir="$tmp/operator-session"
sessions_dir="$tmp/sessions"
cfg="$tmp/server-config.json"
cat >"$cfg" <<EOF
{
  "listen_host": "127.0.0.1",
  "file_service_port": $port,
  "file_service_tls": "no",
  "operator_session_dir": "$operator_dir",
  "session_root": "$sessions_dir"
}
EOF
scripts/busierbox-server --config "$cfg" --transport file-service --file-service-tls no \
    --serve-file "$staged" --as reality-fetch.txt --timeout 10 >"$tmp/server.out" 2>"$tmp/server.err" &
server_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    scripts/busierbox-server --config "$cfg" --json-status >"$tmp/server-status.json"
    if grep -q "\"actual\": \"listening\"" "$tmp/server-status.json"; then
        break
    fi
    sleep 0.1
done
BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard-active" "$bb" reality-test --json \
    --operator-host 127.0.0.1 --file-port "$port" --no-tls \
    --check-upload --check-fetch reality-fetch.txt >"$tmp/reality-active.json"
kill "$server_pid" 2>/dev/null || true
wait "$server_pid" 2>/dev/null || true
python3 -m json.tool "$tmp/reality-active.json" >/dev/null
python3 - "$tmp/reality-active.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
by_name = {item.get("name"): item for item in doc.get("checks", [])}
summary = doc.get("summary", {})
if summary.get("operator_pass") != 2 or summary.get("operator_fail", 0) > 1:
    raise SystemExit(f"reality-test: active operator summary mismatch: {summary}")
for name in ("upload_operator", "fetch_operator"):
    item = by_name.get(name)
    if not item:
        raise SystemExit(f"reality-test: missing active check {name}")
    if item.get("status") == "skipped":
        raise SystemExit(f"reality-test: {name} unexpectedly skipped when explicitly enabled")
    if item.get("status") != "pass":
        raise SystemExit(f"reality-test: {name} did not pass against local operator service: {item}")
PY

scripts/busierbox-server --config "$cfg" --transport file-service --file-service-tls no \
    --serve-file "$staged_spaced" --as "dir/reality fetch spaced.txt" --timeout 10 >"$tmp/server-spaced.out" 2>"$tmp/server-spaced.err" &
server_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    scripts/busierbox-server --config "$cfg" --json-status >"$tmp/server-spaced-status.json"
    if grep -q "\"actual\": \"listening\"" "$tmp/server-spaced-status.json"; then
        break
    fi
    sleep 0.1
done
BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard-spaced-fetch" "$bb" reality-test --json \
    --operator-host 127.0.0.1 --file-port "$port" --no-tls \
    --check-fetch "dir/reality fetch spaced.txt" >"$tmp/reality-spaced-fetch.json"
kill "$server_pid" 2>/dev/null || true
wait "$server_pid" 2>/dev/null || true
python3 -m json.tool "$tmp/reality-spaced-fetch.json" >/dev/null
python3 - "$tmp/reality-spaced-fetch.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
by_name = {item.get("name"): item for item in doc.get("checks", [])}
item = by_name.get("fetch_operator")
if not item or item.get("status") != "pass":
    raise SystemExit(f"reality-test: URL-encoded fetch request did not pass: {item}")
if doc.get("summary", {}).get("operator_pass") != 1:
    raise SystemExit(f"reality-test: encoded fetch summary mismatch: {doc.get('summary')}")
PY

printf '%s\n' "reality-test ok"
