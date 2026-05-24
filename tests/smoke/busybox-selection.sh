#!/bin/sh
set -eu

tmp=$(mktemp -d "${TMPDIR:-/tmp}/busierbox-busybox-selection.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

BUILDROOT_VERSION=${BUILDROOT_VERSION:-2026.02.2}
base="buildroot/buildroot-$BUILDROOT_VERSION/package/busybox/busybox.config"
[ -f "$base" ] || {
    printf '%s\n' "skip: Buildroot BusyBox base config not found at $base"
    exit 0
}

cfg=$(BB_BUSYBOX_GROUPS="shell" BB_BUSYBOX_APPLET_OVERRIDES="+nc" TARGET=selection-nc OUT_DIR="$tmp" scripts/gen-buildroot-busybox-config)
grep -q '^CONFIG_NC=y$' "$cfg"
grep -q '^# CONFIG_WGET is not set$' "$cfg"
grep -q '^# CONFIG_NUKE is not set$' "$cfg"

cfg=$(BB_BUSYBOX_GROUPS="shell dangerous" BB_BUSYBOX_APPLET_OVERRIDES="-nuke" TARGET=selection-danger OUT_DIR="$tmp" scripts/gen-buildroot-busybox-config)
grep -q '^# CONFIG_NUKE is not set$' "$cfg"
grep -q '^CONFIG_DEVMEM=y$' "$cfg"

cfg=$(BB_BUSYBOX_GROUPS="shell" BB_BUSYBOX_APPLET_OVERRIDES="+ascii" TARGET=selection-ascii OUT_DIR="$tmp" scripts/gen-buildroot-busybox-config)
grep -q '^CONFIG_ASCII=y$' "$cfg"

printf '%s\n' "busybox-selection ok"
