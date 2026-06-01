#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/offline-tools.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

chmod +x scripts/lib/mirror-sources scripts/lib/check-offline-readiness scripts/lib/mirror-report

scripts/lib/mirror-sources --out "$tmp/mirror" --dry-run >"$tmp/mirror-plan.json"
python3 -m json.tool "$tmp/mirror-plan.json" >/dev/null
grep -q '"limitations"' "$tmp/mirror-plan.json"
python3 - "$tmp/mirror-plan.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("schema") != 2:
    raise SystemExit("offline-tools: mirror dry-run schema must be 2")
if "mirror_layout" not in data:
    raise SystemExit("offline-tools: mirror layout missing")
PY

cat >"$tmp/matrix.json" <<'EOF'
{
  "targets": ["native"],
  "payloads": ["survey-core"],
  "formats": ["tgz"]
}
EOF
scripts/lib/mirror-sources \
    --matrix "$tmp/matrix.json" \
    --targets all \
    --payload-presets all \
    --source-only \
    --out "$tmp/matrix-mirror" \
    --dry-run >"$tmp/matrix-mirror-plan.json"
python3 -m json.tool "$tmp/matrix-mirror-plan.json" >/dev/null
grep -q "$tmp/matrix.json" "$tmp/matrix-mirror-plan.json"
grep -q '"targets": "all"' "$tmp/matrix-mirror-plan.json"
grep -q '"payload_presets": "all"' "$tmp/matrix-mirror-plan.json"
grep -q '"source_plans"' "$tmp/matrix-mirror-plan.json"
grep -q 'skipped-native' "$tmp/matrix-mirror-plan.json"

printf '%s' sample >"$tmp/sample.tar"
sha=$(sha256sum "$tmp/sample.tar" | awk '{print $1}')
cat >"$tmp/sources.lock.json" <<EOF
{
  "schema": 2,
  "sources": [
    {
      "name": "sample",
      "version": "1",
      "filename": "sample.tar",
      "sha256": "$sha",
      "urls": ["https://example.invalid/sample.tar"],
      "license": "test",
      "homepage": "https://example.invalid/"
    }
  ]
}
EOF
mkdir -p "$tmp/ready/sources" "$tmp/ready/buildroot-dl"
cp "$tmp/sample.tar" "$tmp/ready/sources/sample.tar"
cp "$tmp/sample.tar" "$tmp/ready/buildroot-dl/sample.tar"
scripts/lib/check-offline-readiness --mirror "$tmp/ready" --manifest "$tmp/sources.lock.json" >"$tmp/readiness.out"
grep -q 'offline-readiness ok' "$tmp/readiness.out"

scripts/lib/check-offline-readiness \
    --mirror "$tmp/ready" \
    --manifest "$tmp/sources.lock.json" \
    --matrix "$tmp/matrix.json" >"$tmp/readiness-matrix.out"
grep -q 'offline-readiness ok' "$tmp/readiness-matrix.out"

cat >"$tmp/payload-presets-matrix.json" <<'EOF'
{
  "targets": ["native"],
  "payload_presets": ["survey-core", "ssh-operator"],
  "formats": ["tgz"]
}
EOF
scripts/lib/mirror-sources \
    --matrix "$tmp/payload-presets-matrix.json" \
    --source-only \
    --all-supported-tools \
    --out "$tmp/payload-presets-mirror" \
    --dry-run >"$tmp/payload-presets-mirror-plan.json"
python3 - "$tmp/payload-presets-mirror-plan.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
coverage = data.get("source_coverage") or {}
if coverage.get("all_supported_tools") is not True:
    raise SystemExit("source mirror did not record all-supported-tools coverage")
for tool in ("doom", "nmap", "jq", "mtd-utils"):
    if tool not in (coverage.get("tools") or []):
        raise SystemExit(f"source coverage missing {tool}")
jobs = [
    item.get("job", {})
    for item in data.get("source_plans", [])
]
payloads = {job.get("payload") for job in jobs}
if {"survey-core", "ssh-operator"} - payloads:
    raise SystemExit(f"payload_presets matrix did not expand: {payloads!r}")
PY

make source-mirror DRY_RUN=1 SOURCE_MIRROR_DIR="$tmp/make-source-mirror" >"$tmp/make-source-mirror.out"
grep -q '"source_coverage"' "$tmp/make-source-mirror.out"
grep -q '"all_supported_tools": true' "$tmp/make-source-mirror.out"
python3 - "$tmp/make-source-mirror.out" <<'PY'
import json
import re
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
jobs = [item.get("job", {}) for item in data.get("source_plans", [])]
targets = {job.get("target") for job in jobs}
payloads = {job.get("payload") for job in jobs}
device_specific = {
    target for target in targets
    if target and re.search(r"glinet|tplink|asus|dlink|linksys|netgear", target)
}
expected_payloads = {
    "builtin-core-shell",
    "default",
    "full-debug",
    "payload-bash",
    "socat-rescue",
    "ssh-operator",
    "survey-core",
}
if len(jobs) != 112:
    raise SystemExit(f"release-full source mirror should plan 112 jobs, got {len(jobs)}")
if len(targets) != 16:
    raise SystemExit(f"release-full source mirror should plan 16 generic targets, got {len(targets)}")
if payloads != expected_payloads:
    raise SystemExit(f"release-full source mirror payload drift: {sorted(payloads)}")
if device_specific:
    raise SystemExit(f"release-full source mirror should not build device-specific targets: {sorted(device_specific)}")
PY
make source-release DRY_RUN=1 SOURCE_MIRROR_DIR="$tmp/make-source-release" SOURCE_RELEASE_DIR="$tmp/releases" SOURCE_RELEASE_NAME=smoke-source >"$tmp/make-source-release.out"
grep -q 'would create' "$tmp/make-source-release.out"

scripts/lib/check-offline-readiness \
    --mirror "$tmp/ready" \
    --manifest "$tmp/sources.lock.json" \
    --targets native \
    --payload-presets survey-core,ssh-operator >"$tmp/readiness-payload-presets.out"
grep -q 'offline-readiness ok' "$tmp/readiness-payload-presets.out"

if scripts/lib/check-offline-readiness \
    --mirror "$tmp/ready" \
    --manifest "$tmp/sources.lock.json" \
    --matrix "$tmp/matrix.json" \
    --strict >"$tmp/readiness-strict.out" 2>"$tmp/readiness-strict.err"; then
    printf '%s\n' "offline-tools: strict readiness unexpectedly passed without mirror-manifest" >&2
    exit 1
fi
grep -q 'missing-mirror-manifest' "$tmp/readiness-strict.err"

mkdir -p "$tmp/report/grit-sources"
cp "$tmp/sample.tar" "$tmp/report/grit-sources/sample.tar"
cat >"$tmp/report/mirror-manifest.json" <<EOF
{
  "schema": 2,
  "strict_ready": true,
  "jobs": [{"name": "native-survey-core-tgz"}],
  "files": [
    {
      "path": "grit-sources/sample.tar",
      "sha256": "$sha",
      "size": 6,
      "source_category": "grit-lockfile"
    }
  ],
  "failures": []
}
EOF
scripts/lib/mirror-report "$tmp/report" >"$tmp/report.out"
grep -q '^strict_ready=yes$' "$tmp/report.out"
grep -q '^matrix_jobs=1$' "$tmp/report.out"
grep -q '^missing_or_failed=0$' "$tmp/report.out"

if scripts/lib/check-offline-readiness --mirror "$tmp/missing" --manifest "$tmp/sources.lock.json" >"$tmp/missing.out" 2>"$tmp/missing.err"; then
    printf '%s\n' "offline-tools: missing mirror unexpectedly passed" >&2
    exit 1
fi
grep -q 'missing-lockfile-source: sample.tar' "$tmp/missing.err"

GRIT_OFFLINE=1 GRIT_MIRROR_DIR="$tmp/missing" \
    scripts/lib/buildroot-build-payload --prepare-only >"$tmp/buildroot-offline.out" 2>"$tmp/buildroot-offline.err" && {
        printf '%s\n' "offline-tools: buildroot offline preflight unexpectedly passed" >&2
        exit 1
    }
grep -q 'offline mode: missing Buildroot tarball' "$tmp/buildroot-offline.err"

printf '%s\n' "offline-tools ok"
