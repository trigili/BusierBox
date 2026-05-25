#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

scripts/config-from-survey --format shell tests/fixtures/survey/glinet-mt7621.json >"$tmp/glinet.conf"
grep -q '^BB_TARGET_PRESET=glinet-mt7621-openwrt-musl$' "$tmp/glinet.conf"
grep -q '^BB_TARGET_ARCH=mipsel$' "$tmp/glinet.conf"
grep -q '^BB_TARGET_LIBC=musl$' "$tmp/glinet.conf"
grep -q '^BB_RUNTIME_ALLOW_EXTERNAL_WRITES=no$' "$tmp/glinet.conf"
grep -q '^BB_ZERO_ARG_MODE=help$' "$tmp/glinet.conf"

scripts/config-from-survey --format json tests/fixtures/survey/generic-openwrt-mipsel.json >"$tmp/openwrt.json"
python3 -m json.tool "$tmp/openwrt.json" >/dev/null
grep -q '"BB_TARGET_ARCH": "mipsel"' "$tmp/openwrt.json"
grep -q '"BB_TARGET_LIBC": "musl"' "$tmp/openwrt.json"

scripts/config-from-survey --write-config "$tmp/low.conf" tests/fixtures/survey/unknown-low-disk.json
grep -q '^BB_RUNTIME_MODE=core-only$' "$tmp/low.conf"
grep -q '^BB_RUNTIME_ROOT=/tmp/.busierbox$' "$tmp/low.conf"
grep -q '^# WARNING:' "$tmp/low.conf"

printf '%s\n' "config-from-survey ok"
