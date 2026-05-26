#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/release-bundles.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

scripts/make-release --name smoke --targets native --payload-presets default --dry-run >"$work/dry-run.out"
grep -q 'would build target=native payload=default format=tgz' "$work/dry-run.out"

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
