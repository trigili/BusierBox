#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

presets='
tplink-archer-a7-v5-openwrt-uclibc
tplink-archer-ax1800-v56-openwrt-musl
asus-rt-n16-uclibc
dlink-dir-615-revc-uclibc
dlink-dir-300-a1-uclibc
linksys-wrt54g-v5-ddwrt-uclibc
netgear-wndr3700-v1-uclibc
'

for preset in $presets; do
    resolved=$(scripts/lib/resolve-target "$preset")
    eval "$resolved"
    [ "${TARGET_STATUS:-}" = supported ] || {
        printf '%s\n' "preset $preset did not resolve as supported" >&2
        exit 1
    }
    scripts/lib/gen-buildroot-defconfig "$preset" >/dev/null
    [ -f "${TARGET_PROFILE_FILE:-}" ] || {
        printf '%s\n' "missing generated profile for $preset" >&2
        exit 1
    }
    [ -f "${TARGET_BUILDROOT_DEFCONFIG:-}" ] || {
        printf '%s\n' "missing generated defconfig for $preset" >&2
        exit 1
    }
done

scripts/lib/rehost-router-examples --help >/dev/null
scripts/lib/rehost-router-examples --list >"$tmp/list"
grep -q 'archer-a7-us-v5-211022' "$tmp/list"
grep -q 'archer-ax1800-usw-v56-250814' "$tmp/list"
grep -q 'asus-rt-n16-30043807378' "$tmp/list"
grep -q 'dir-615-revc-300' "$tmp/list"
grep -q 'dir-300-a1-fw105b09' "$tmp/list"
grep -q 'linksys-gv5flash' "$tmp/list"
grep -q 'netgear-wndr3700-v1-10431-na' "$tmp/list"
grep -q 'linksys-wrt54g-v5v6-1028.*no-linux-rootfs' "$tmp/list"
grep -q 'openwrt-18061-ixp4xx-zimage.*kernel-only' "$tmp/list"

printf '%s\n' "rehosted-router-presets ok"
