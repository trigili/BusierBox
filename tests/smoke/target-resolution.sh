#!/bin/sh
set -eu

tmp=${TMPDIR:-/tmp}/grit-target-test.$$
trap 'rm -f "$tmp" "$tmp.err"' EXIT HUP INT TERM

cat >"$tmp" <<'EOF'
GRIT_TARGET_ARCH="mipsel"
GRIT_TARGET_ENDIAN="little"
GRIT_TARGET_CPU="mips32r2-24kc"
GRIT_TARGET_ABI="default"
GRIT_TARGET_LIBC="musl"
GRIT_KERNEL_FLOOR="4.x"
GRIT_STATIC_POLICY="static-preferred"
GRIT_PAYLOAD_TIER="debug"
GRIT_TARGET_QEMU_USER="qemu-mipsel-static"
GRIT_PAYLOAD_FORMAT="tgz"
GRIT_BUSYBOX_GROUPS="shell fileops disk process network text system"
GRIT_HEAVY_TOOLS="tmux strace"
EOF

resolved=$(GRIT_CONFIG="$tmp" scripts/resolve-target --config)
printf '%s\n' "$resolved" | grep "TARGET_NAME=mipsel-linux-4.x-musl" >/dev/null
printf '%s\n' "$resolved" | grep "TARGET_STATUS=supported" >/dev/null

generated=$(scripts/gen-buildroot-defconfig --from-config "$tmp")
printf '%s\n' "$generated" | grep "BUILDROOT_DEFCONFIG=buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig" >/dev/null
test -f buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
test -f payloads/generated-profiles/mipsel-linux-4.x-musl.mk
grep '^BR2_mipsel=y' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig >/dev/null
grep '^BR2_TOOLCHAIN_BUILDROOT_MUSL=y' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig >/dev/null

cat >"$tmp" <<'EOF'
GRIT_TARGET_ARCH="powerpc"
GRIT_TARGET_ENDIAN="big"
GRIT_TARGET_CPU="generic"
GRIT_TARGET_ABI="default"
GRIT_TARGET_LIBC="glibc"
GRIT_KERNEL_FLOOR="4.x"
GRIT_STATIC_POLICY="static-preferred"
GRIT_PAYLOAD_TIER="core"
EOF

if GRIT_CONFIG="$tmp" scripts/resolve-target --config | grep "TARGET_STATUS=supported" >/dev/null; then
    printf '%s\n' "expected unsupported tuple to be rejected" >&2
    exit 1
fi

cat >"$tmp" <<'EOF'
GRIT_TARGET_PRESET="default"
GRIT_TARGET_ARCH=""
GRIT_TARGET_ENDIAN="auto"
GRIT_TARGET_CPU="generic"
GRIT_TARGET_ABI="default"
GRIT_TARGET_LIBC=""
GRIT_KERNEL_FLOOR=""
GRIT_STATIC_POLICY="static-preferred"
GRIT_PAYLOAD_TIER="core"
EOF

blank=$(GRIT_CONFIG="$tmp" scripts/resolve-target --config)
printf '%s\n' "$blank" | grep "TARGET_STATUS=blank" >/dev/null
printf '%s\n' "$blank" | grep "default is a blank target configuration" >/dev/null
if GRIT_CONFIG="$tmp" scripts/resolve-target --config | grep "TARGET_NAME=native" >/dev/null; then
    printf '%s\n' "default/blank config unexpectedly resolved to native" >&2
    exit 1
fi

if scripts/package-target default 2>"$tmp.err"; then
    printf '%s\n' "package-target default unexpectedly succeeded" >&2
    exit 1
fi
grep "default is a blank target configuration" "$tmp.err" >/dev/null

list=$(scripts/resolve-target --list)
first=$(printf '%s\n' "$list" | sed -n '1p' | cut -f1)
second=$(printf '%s\n' "$list" | sed -n '2p' | cut -f1)
[ "$first" = default ] || { printf '%s\n' "default preset is not first in --list" >&2; exit 1; }
[ "$second" = native ] || { printf '%s\n' "native preset is not second in --list" >&2; exit 1; }
printf '%s\n' "$list" | awk -F '\t' '$1 == "mipsel-linux-4.x-musl" && $2 == "supported" { found=1 } END { exit found ? 0 : 1 }'

tree=$(scripts/resolve-target --list-tree)
printf '%s\n' "$tree" | grep '^\[specific-targets/legacy-routers\]$' >/dev/null
printf '%s\n' "$tree" | grep '  asus-rt-n16-uclibc' >/dev/null
printf '%s\n' "$tree" | grep '  mipsel-linux-4.x-musl' >/dev/null
printf '%s\n' "$tree" | grep '^\[generic-archs/arm\]$' >/dev/null
printf '%s\n' "$tree" | grep '  armv7-linux-3.x-musl' >/dev/null

printf '%s\n' "target-resolution ok"
