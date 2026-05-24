#!/bin/sh
set -eu

tmp=${TMPDIR:-/tmp}/busierbox-target-test.$$
trap 'rm -f "$tmp"' EXIT HUP INT TERM

cat >"$tmp" <<'EOF'
BB_TARGET_ARCH="mipsel"
BB_TARGET_ENDIAN="little"
BB_TARGET_CPU="mips32r2-24kc"
BB_TARGET_ABI="default"
BB_TARGET_LIBC="musl"
BB_KERNEL_FLOOR="4.x"
BB_STATIC_POLICY="static-preferred"
BB_PAYLOAD_TIER="debug"
BB_TARGET_QEMU_USER="qemu-mipsel-static"
BB_PAYLOAD_FORMAT="tgz"
BB_BUSYBOX_GROUPS="shell fileops disk process network text system"
BB_HEAVY_TOOLS="tmux strace"
EOF

resolved=$(BUSIERBOX_CONFIG="$tmp" scripts/resolve-target --config)
printf '%s\n' "$resolved" | grep "TARGET_NAME=mipsel-linux-4.x-musl" >/dev/null
printf '%s\n' "$resolved" | grep "TARGET_STATUS=supported" >/dev/null

generated=$(scripts/gen-buildroot-defconfig --from-config "$tmp")
printf '%s\n' "$generated" | grep "BUILDROOT_DEFCONFIG=buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig" >/dev/null
test -f buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
test -f payloads/generated-profiles/mipsel-linux-4.x-musl.mk
grep '^BR2_mipsel=y' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig >/dev/null
grep '^BR2_TOOLCHAIN_BUILDROOT_MUSL=y' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig >/dev/null

cat >"$tmp" <<'EOF'
BB_TARGET_ARCH="powerpc"
BB_TARGET_ENDIAN="big"
BB_TARGET_CPU="generic"
BB_TARGET_ABI="default"
BB_TARGET_LIBC="glibc"
BB_KERNEL_FLOOR="4.x"
BB_STATIC_POLICY="static-preferred"
BB_PAYLOAD_TIER="core"
EOF

if BUSIERBOX_CONFIG="$tmp" scripts/resolve-target --config | grep "TARGET_STATUS=supported" >/dev/null; then
    printf '%s\n' "expected unsupported tuple to be rejected" >&2
    exit 1
fi

printf '%s\n' "target-resolution ok"
