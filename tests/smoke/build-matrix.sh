#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/build-matrix.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

scripts/build-matrix --list-targets >"$tmp/targets"
grep -qx native "$tmp/targets"

scripts/build-matrix --list-payloads >"$tmp/payloads"
grep -qx default "$tmp/payloads"
grep -qx survey-core "$tmp/payloads"

scripts/build-matrix \
    --targets native \
    --payloads survey-core,default \
    --formats tgz \
    --dry-run \
    --run-dir "$tmp/run" >"$tmp/dry-run.out"

grep -q 'dry-run' "$tmp/dry-run.out"
test -f "$tmp/run/summary.json"
python3 - "$tmp/run/summary.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if not data.get("dry_run"):
    raise SystemExit("matrix summary did not record dry_run")
jobs = data.get("jobs") or []
if len(jobs) != 2:
    raise SystemExit(f"expected 2 dry-run jobs, got {len(jobs)}")
for job in jobs:
    if job.get("status") != "dry-run":
        raise SystemExit(f"unexpected job status: {job}")
    if "BUSIERBOX_CONFIG=" not in job.get("command", ""):
        raise SystemExit("dry-run command missing BUSIERBOX_CONFIG")
PY

grep -q '^BB_PAYLOAD_PRESET=survey-core$' "$tmp/run/configs/native-survey-core-tgz.conf"
grep -q '^BB_TARGET_PRESET=native$' "$tmp/run/configs/native-default-tgz.conf"

cat >"$tmp/matrix.json" <<'EOF'
{
  "targets": ["native"],
  "payloads": ["survey-core"],
  "formats": ["tgz"],
  "variants": {
    "operator": {
      "payload_preset": "ssh-operator",
      "BB_ZERO_ARG_MODE": "help"
    }
  }
}
EOF
scripts/build-matrix --matrix "$tmp/matrix.json" --dry-run --run-dir "$tmp/matrix-run" >/dev/null
python3 - "$tmp/matrix-run/summary.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
payloads = sorted(job["payload"] for job in data["jobs"])
if payloads != ["ssh-operator", "survey-core"]:
    raise SystemExit(f"unexpected payload expansion: {payloads}")
PY
grep -q '^BB_ZERO_ARG_MODE=help$' "$tmp/matrix-run/configs/native-ssh-operator-tgz.conf"

printf '%s\n' "build-matrix ok"
