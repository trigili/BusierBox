#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-local/tmp}/reality-test-$$
mkdir -p "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" reality-test --help >/dev/null
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
    if "ok" not in item or "detail" not in item:
        raise SystemExit(f"reality-test: incomplete check {item!r}")
summary = doc.get("summary", {})
if summary.get("pass", 0) + summary.get("fail", 0) + summary.get("skipped", 0) != len(checks):
    raise SystemExit("reality-test: summary counts do not match checks")
if by_name["upload_operator"]["status"] != "skipped":
    raise SystemExit("reality-test: upload_operator should be skipped without explicit side-effect setup")
if by_name["fetch_operator"]["status"] != "skipped":
    raise SystemExit("reality-test: fetch_operator should be skipped without staged file")
PY

printf '%s\n' "reality-test ok"
