#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/release-bundles.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

scripts/make-release --name smoke --targets native --payload-presets default --dry-run >"$work/dry-run.out"
grep -q 'would build target=native payload=default format=tgz' "$work/dry-run.out"

scripts/make-release --name matrix-smoke --matrix release/matrices/iot-lab.json --dry-run >"$work/matrix-dry-run.out"
python3 - "$work/matrix-dry-run.out" release/matrices/iot-lab.json <<'PY'
import json
import sys

dry_run = open(sys.argv[1], "r", encoding="utf-8").read()
matrix = json.load(open(sys.argv[2], "r", encoding="utf-8"))
for target in matrix["targets"]:
    for payload in matrix["payload_presets"]:
        expected = f"would build target={target} payload={payload} format=tgz"
        if expected not in dry_run:
            raise SystemExit(f"missing dry-run job: {expected}")
PY

cat >"$work/bad-target.json" <<'JSON'
{
  "name": "bad-target",
  "targets": ["no-such-target"],
  "payload_presets": ["default"]
}
JSON
if scripts/make-release --name bad --matrix "$work/bad-target.json" --dry-run >"$work/bad-target.out" 2>"$work/bad-target.err"; then
    printf '%s\n' "expected bad target matrix to fail" >&2
    exit 1
fi
grep -q 'unresolved target no-such-target' "$work/bad-target.err"

cat >"$work/bad-payload.json" <<'JSON'
{
  "name": "bad-payload",
  "targets": ["native"],
  "payload_presets": ["no-such-payload"]
}
JSON
if scripts/make-release --name bad --matrix "$work/bad-payload.json" --dry-run >"$work/bad-payload.out" 2>"$work/bad-payload.err"; then
    printf '%s\n' "expected bad payload matrix to fail" >&2
    exit 1
fi
grep -q 'missing payload preset no-such-payload' "$work/bad-payload.err"

if [ ! -x dist/busierbox-native-full ]; then
    BUSIERBOX_CONFIG=presets/payload/default.conf BB_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
fi

scripts/make-release \
    --name smoke \
    --targets native \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/release" >"$work/release.out"

test -x "$work/release/bin/busierbox-native-default-full"
test -x "$work/release/scripts/artifact-config"
test -x "$work/release/scripts/configure-artifact"
test -x "$work/release/scripts/configure-all"
test -x "$work/release/scripts/verify-checksums"
test -f "$work/release/SHA256SUMS.original"
test -f "$work/release/release.json"
test -f "$work/release.tar.gz"

python3 -m json.tool "$work/release/release.json" >/dev/null
grep -q '"release_name": "smoke"' "$work/release/release.json"
grep -q '"build_status": "copied"' "$work/release/release.json"
python3 - "$work/release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
host = data.get("build_host", {})
for key in ("system", "machine", "python_version"):
    if not host.get(key):
        raise SystemExit(f"missing build_host.{key}")
lock = data.get("source_lock", {})
if not lock.get("present"):
    raise SystemExit("source_lock metadata missing")
if lock.get("path") != "manifests/sources.lock.json":
    raise SystemExit("source_lock path mismatch")
if len(lock.get("sha256", "")) != 64:
    raise SystemExit("source_lock sha256 missing")
sources = {item.get("name"): item for item in lock.get("sources", [])}
for name in ("buildroot", "miniz", "doom-ascii"):
    if name not in sources:
        raise SystemExit(f"missing source lock entry: {name}")
    if not sources[name].get("version") or not sources[name].get("sha256"):
        raise SystemExit(f"incomplete source lock entry: {name}")
PY

(
    cd "$work/release"
    scripts/verify-checksums --original >/dev/null
)

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --operator-host 192.0.2.55 \
    --transport builtin \
    --shell-port 22203 >/dev/null

"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/show.out"
grep -q '^trailer_present=yes$' "$work/show.out"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/show.out"
test -x "$work/release/bin/busierbox-native-default-full"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --show >"$work/wrapper-show.out"
grep -q '^trailer_present=yes$' "$work/wrapper-show.out"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --export "$work/export.env"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/export.env"
test -f "$work/release/SHA256SUMS.configured"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

"$work/release/scripts/configure-all" --clear >/dev/null
"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/clear.out"
grep -q '^trailer_present=no$' "$work/clear.out"

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --import "$work/export.env" \
    --obfuscation xor >"$work/import-xor.out"
grep -q 'not encryption' "$work/import-xor.out"
"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/xor-show.out"
grep -q '^trailer_present=yes$' "$work/xor-show.out"
grep -q '^encoding=xor$' "$work/xor-show.out"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/xor-show.out"
test -x "$work/release/bin/busierbox-native-default-full"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

printf '%s\n' "release-bundles ok"
