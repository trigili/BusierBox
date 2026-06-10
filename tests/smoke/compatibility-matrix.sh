#!/bin/sh
set -eu

matrix_path=tests/matrix/compatibility-ci.json
tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/compatibility-matrix.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

scripts/lib/build-matrix \
    --matrix "$matrix_path" \
    --dry-run \
    --run-dir "$tmp/run" >"$tmp/dry-run.out"

test -f "$tmp/run/summary.json"
python3 - "$tmp/run/summary.json" "$matrix_path" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], "r", encoding="utf-8"))
matrix = json.load(open(sys.argv[2], "r", encoding="utf-8"))
jobs = summary.get("jobs") or []
expected_count = (
    len(matrix.get("targets") or [])
    * len(matrix.get("payload_presets") or [])
    * len(matrix.get("formats") or [])
)
if summary.get("dry_run") is not True:
    raise SystemExit("compatibility matrix smoke did not run in dry-run mode")
if summary.get("jobs_requested") != expected_count or len(jobs) != expected_count:
    raise SystemExit(
        f"compatibility matrix expected {expected_count} jobs, "
        f"got requested={summary.get('jobs_requested')} actual={len(jobs)}"
    )
targets = {job.get("target") for job in jobs}
payloads = {job.get("payload") for job in jobs}
required_targets = {
    "mips-linux-2.4-uclibc",
    "mipsel-linux-2.6-uclibc-legacy",
    "mipsel-linux-3.x-musl",
    "armv7-linux-3.x-musl",
    "aarch64-linux-4.x-musl",
    "x86_64-linux-current-musl",
}
required_payloads = {"survey-core", "default", "ssh-operator"}
if not required_targets.issubset(targets):
    raise SystemExit(f"compatibility matrix missing targets: {sorted(required_targets - targets)}")
if not required_payloads.issubset(payloads):
    raise SystemExit(f"compatibility matrix missing payloads: {sorted(required_payloads - payloads)}")
if not any("uclibc" in str(target) for target in targets):
    raise SystemExit("compatibility matrix lost uClibc coverage")
if not any("musl" in str(target) for target in targets):
    raise SystemExit("compatibility matrix lost musl coverage")
if not any(str(target).startswith("mips-linux") for target in targets):
    raise SystemExit("compatibility matrix lost big-endian MIPS coverage")
if not any(str(target).startswith("mipsel-linux") for target in targets):
    raise SystemExit("compatibility matrix lost little-endian MIPS coverage")
for job in jobs:
    if job.get("status") != "dry-run":
        raise SystemExit(f"unexpected compatibility job status: {job}")
    if "GRIT_CONFIG=" not in str(job.get("command") or ""):
        raise SystemExit(f"compatibility job missing GRIT_CONFIG command: {job}")
PY

grep -q '^GRIT_TARGET_PRESET=mipsel-linux-2.6-uclibc-legacy$' \
    "$tmp/run/configs/mipsel-linux-2.6-uclibc-legacy-survey-core-tgz.conf"
grep -q '^GRIT_PAYLOAD_PRESET=ssh-operator$' \
    "$tmp/run/configs/x86_64-linux-current-musl-ssh-operator-tgz.conf"

printf '%s\n' "compatibility-matrix ok"
