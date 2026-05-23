#!/bin/sh
# Intended to run inside a Buildroot/OpenWrt QEMU guest.
# The qemu-system harness places this script beside busierbox in the payload.
set -u

PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

mountpoint=/mnt/busierbox-test
mkdir -p "$mountpoint" /proc /sys /dev /tmp
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true

if ! mount -t 9p -o trans=virtio,version=9p2000.L busierbox_payload "$mountpoint" 2>/dev/null; then
    echo "smoke-init: unable to mount 9p payload busierbox_payload" >&2
    poweroff -f 2>/dev/null || halt -f 2>/dev/null || exit 1
fi

mkdir -p "$mountpoint/artifacts"
BUSIERBOX="$mountpoint/busierbox" ARTIFACT_DIR="$mountpoint/artifacts" sh "$mountpoint/busierbox-smoke.sh"
rc=$?
sync
echo "BUSIERBOX_SMOKE_RC=$rc"
poweroff -f 2>/dev/null || halt -f 2>/dev/null || exit "$rc"

