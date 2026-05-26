#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/offline-tools.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

chmod +x scripts/mirror-sources scripts/check-offline-readiness scripts/mirror-report

scripts/mirror-sources --out "$tmp/mirror" --dry-run >"$tmp/mirror-plan.json"
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
scripts/mirror-sources \
    --matrix "$tmp/matrix.json" \
    --targets all \
    --payloads all \
    --source-only \
    --out "$tmp/matrix-mirror" \
    --dry-run >"$tmp/matrix-mirror-plan.json"
python3 -m json.tool "$tmp/matrix-mirror-plan.json" >/dev/null
grep -q "$tmp/matrix.json" "$tmp/matrix-mirror-plan.json"
grep -q '"targets": "all"' "$tmp/matrix-mirror-plan.json"
grep -q '"payloads": "all"' "$tmp/matrix-mirror-plan.json"
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
scripts/check-offline-readiness --mirror "$tmp/ready" --manifest "$tmp/sources.lock.json" >"$tmp/readiness.out"
grep -q 'offline-readiness ok' "$tmp/readiness.out"

scripts/check-offline-readiness \
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
scripts/mirror-sources \
    --matrix "$tmp/payload-presets-matrix.json" \
    --source-only \
    --out "$tmp/payload-presets-mirror" \
    --dry-run >"$tmp/payload-presets-mirror-plan.json"
python3 - "$tmp/payload-presets-mirror-plan.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
jobs = [
    item.get("job", {})
    for item in data.get("source_plans", [])
]
payloads = {job.get("payload") for job in jobs}
if {"survey-core", "ssh-operator"} - payloads:
    raise SystemExit(f"payload_presets matrix did not expand: {payloads!r}")
PY
scripts/check-offline-readiness \
    --mirror "$tmp/ready" \
    --manifest "$tmp/sources.lock.json" \
    --matrix "$tmp/payload-presets-matrix.json" >"$tmp/readiness-payload-presets.out"
grep -q 'offline-readiness ok' "$tmp/readiness-payload-presets.out"

if scripts/check-offline-readiness \
    --mirror "$tmp/ready" \
    --manifest "$tmp/sources.lock.json" \
    --matrix "$tmp/matrix.json" \
    --strict >"$tmp/readiness-strict.out" 2>"$tmp/readiness-strict.err"; then
    printf '%s\n' "offline-tools: strict readiness unexpectedly passed without mirror-manifest" >&2
    exit 1
fi
grep -q 'missing-mirror-manifest' "$tmp/readiness-strict.err"

mkdir -p "$tmp/report/busierbox-sources"
cp "$tmp/sample.tar" "$tmp/report/busierbox-sources/sample.tar"
cat >"$tmp/report/mirror-manifest.json" <<EOF
{
  "schema": 2,
  "strict_ready": true,
  "jobs": [{"name": "native-survey-core-tgz"}],
  "files": [
    {
      "path": "busierbox-sources/sample.tar",
      "sha256": "$sha",
      "size": 6,
      "source_category": "busierbox-lockfile"
    }
  ],
  "failures": []
}
EOF
scripts/mirror-report "$tmp/report" >"$tmp/report.out"
grep -q '^strict_ready=yes$' "$tmp/report.out"
grep -q '^matrix_jobs=1$' "$tmp/report.out"
grep -q '^missing_or_failed=0$' "$tmp/report.out"

if scripts/check-offline-readiness --mirror "$tmp/missing" --manifest "$tmp/sources.lock.json" >"$tmp/missing.out" 2>"$tmp/missing.err"; then
    printf '%s\n' "offline-tools: missing mirror unexpectedly passed" >&2
    exit 1
fi
grep -q 'missing-lockfile-source: sample.tar' "$tmp/missing.err"

BUSIERBOX_OFFLINE=1 BUSIERBOX_MIRROR_DIR="$tmp/missing" \
    scripts/buildroot-build-payload --prepare-only >"$tmp/buildroot-offline.out" 2>"$tmp/buildroot-offline.err" && {
        printf '%s\n' "offline-tools: buildroot offline preflight unexpectedly passed" >&2
        exit 1
    }
grep -q 'offline mode: missing Buildroot tarball' "$tmp/buildroot-offline.err"

printf '%s\n' "offline-tools ok"
