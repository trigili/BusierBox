#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/build-matrix.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

scripts/lib/build-matrix --list-targets >"$tmp/targets"
grep -qx native "$tmp/targets"

scripts/lib/build-matrix --list-payloads >"$tmp/payloads"
grep -qx default "$tmp/payloads"
grep -qx survey-core "$tmp/payloads"

scripts/lib/build-matrix \
    --targets native \
    --payload-presets survey-core,default \
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
if data.get("matrix", {}).get("payload_presets") != "survey-core,default":
    raise SystemExit("matrix summary did not record payload_presets alias")
jobs = data.get("jobs") or []
if len(jobs) != 2:
    raise SystemExit(f"expected 2 dry-run jobs, got {len(jobs)}")
for job in jobs:
    if job.get("status") != "dry-run":
        raise SystemExit(f"unexpected job status: {job}")
    if "GRIT_CONFIG=" not in job.get("command", ""):
        raise SystemExit("dry-run command missing GRIT_CONFIG")
    if not job.get("resolved_target"):
        raise SystemExit("dry-run job missing resolved_target")
PY

grep -q '^GRIT_PAYLOAD_PRESET=survey-core$' "$tmp/run/configs/native-survey-core-tgz.conf"
grep -q '^GRIT_TARGET_PRESET=native$' "$tmp/run/configs/native-default-tgz.conf"

cat >"$tmp/matrix.json" <<'EOF'
{
  "targets": ["native"],
  "payloads": ["survey-core"],
  "formats": ["tgz"],
  "variants": {
    "operator": {
      "payload_preset": "ssh-operator",
      "GRIT_ZERO_ARG_MODE": "help"
    }
  }
}
EOF
scripts/lib/build-matrix --matrix "$tmp/matrix.json" --dry-run --run-dir "$tmp/matrix-run" >/dev/null
python3 - "$tmp/matrix-run/summary.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
payloads = sorted(job["payload"] for job in data["jobs"])
if payloads != ["ssh-operator", "survey-core"]:
    raise SystemExit(f"unexpected payload expansion: {payloads}")
PY
grep -q '^GRIT_ZERO_ARG_MODE=help$' "$tmp/matrix-run/configs/native-ssh-operator-tgz.conf"

scripts/lib/build-matrix \
    --matrix release/matrices/iot-lab.json \
    --dry-run \
    --run-dir "$tmp/iot-run" >"$tmp/iot-run.out"
python3 - "$tmp/iot-run/summary.json" release/matrices/iot-lab.json <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], "r", encoding="utf-8"))
matrix = json.load(open(sys.argv[2], "r", encoding="utf-8"))
expected = {
    (target, payload, fmt)
    for target in matrix["targets"]
    for payload in matrix["payload_presets"]
    for fmt in matrix["formats"]
}
actual = {
    (job["target"], job["payload"], job["format"])
    for job in summary.get("jobs", [])
}
missing = expected - actual
if missing:
    raise SystemExit(f"missing iot-lab jobs: {sorted(missing)!r}")
if len(actual) != len(expected):
    raise SystemExit(f"unexpected iot-lab job count: {len(actual)} != {len(expected)}")
PY

scripts/lib/build-matrix \
    --matrix "$tmp/matrix.json" \
    --offline \
    --mirror-dir "$tmp/source-mirror" \
    --dry-run \
    --run-dir "$tmp/offline-run" >"$tmp/offline-run.out"
python3 - "$tmp/offline-run/summary.json" "$tmp/source-mirror" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
mirror = sys.argv[2]
if not data.get("offline"):
    raise SystemExit("offline matrix summary missing offline=true")
if data.get("mirror_dir") != mirror:
    raise SystemExit("offline matrix summary did not record mirror_dir")
if data.get("buildroot_dl_dir") != f"{mirror}/buildroot-dl":
    raise SystemExit("offline matrix summary did not record buildroot_dl_dir")
for job in data.get("jobs") or []:
    if not job.get("resolved_target"):
        raise SystemExit("offline dry-run job missing resolved_target")
    cmd = job.get("command", "")
    for token in ["GRIT_OFFLINE=1", "GRIT_MIRROR_DIR=", "BUILDROOT_DL_DIR="]:
        if token not in cmd:
            raise SystemExit(f"offline dry-run command missing {token}: {cmd}")
PY

printf '%s\n' "build-matrix ok"
