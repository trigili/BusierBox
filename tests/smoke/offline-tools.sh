#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/offline-tools.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

chmod +x scripts/mirror-sources scripts/check-offline-readiness

scripts/mirror-sources --out "$tmp/mirror" --dry-run >"$tmp/mirror-plan.json"
python3 -m json.tool "$tmp/mirror-plan.json" >/dev/null
grep -q '"limitations"' "$tmp/mirror-plan.json"

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
    --out "$tmp/matrix-mirror" \
    --dry-run >"$tmp/matrix-mirror-plan.json"
python3 -m json.tool "$tmp/matrix-mirror-plan.json" >/dev/null
grep -q "matrix:$tmp/matrix.json" "$tmp/matrix-mirror-plan.json"
grep -q 'targets:all' "$tmp/matrix-mirror-plan.json"
grep -q 'payloads:all' "$tmp/matrix-mirror-plan.json"

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

if scripts/check-offline-readiness --mirror "$tmp/missing" --manifest "$tmp/sources.lock.json" >"$tmp/missing.out" 2>"$tmp/missing.err"; then
    printf '%s\n' "offline-tools: missing mirror unexpectedly passed" >&2
    exit 1
fi
grep -q 'missing sample.tar' "$tmp/missing.err"

BUSIERBOX_OFFLINE=1 BUSIERBOX_MIRROR_DIR="$tmp/missing" \
    scripts/buildroot-build-payload --prepare-only >"$tmp/buildroot-offline.out" 2>"$tmp/buildroot-offline.err" && {
        printf '%s\n' "offline-tools: buildroot offline preflight unexpectedly passed" >&2
        exit 1
    }
grep -q 'offline mode: missing Buildroot tarball' "$tmp/buildroot-offline.err"

printf '%s\n' "offline-tools ok"
