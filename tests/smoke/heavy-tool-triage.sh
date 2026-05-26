#!/bin/sh
set -eu

menu=${1:-scripts/menuconfig}

python3 -m json.tool payloads/tool-compat.json >/dev/null

grep -q 'configure_busybox_applet_search()' "$menu"
grep -q 'Search applets by name/group/description' "$menu"
grep -q 'Dangerous storage / flash diagnostics' "$menu"
grep -q 'BB_DOOM_USER_PATH' "$menu"
grep -q 'BB_DOOM_WAD_PATH' "$menu"
grep -q 'BB_DOOM_USER_PATH' scripts/build-payload
grep -q 'BB_DOOM_WAD_PATH' scripts/build-payload
grep -q 'BB_DOOM_USER_PATH' configs/busierbox.conf.example
grep -q 'BB_DOOM_WAD_PATH' configs/busierbox.conf.example
grep -Fq 'require_static_payload_tool runtime/payload/bin/doom-ascii "doom-ascii"' scripts/buildroot-build-payload
grep -Fq 'must be statically linked for the BusierBox doom payload' scripts/buildroot-build-payload
grep -Fq 'requested doom but the static doom-ascii engine was not found' scripts/buildroot-build-payload
! grep -Fq 'stage_first_found_as doom prboom' scripts/buildroot-build-payload
! grep -Fq 'chocolate-doom' scripts/buildroot-build-payload

scripts/check-buildroot-tool-mappings --tools "nmap nmap-ncat openssl fd zoxide psmisc mtd-utils ubi-utils i2c-tools spi-tools mmc-utils e2fsprogs parted gdb gef-pwndbg radare2 rizin gcore tshark doom" >/dev/null
scripts/check-buildroot-tool-mappings --tools doom | grep -q 'BR2_PACKAGE_BUSIERBOX_DOOM_ASCII'

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/heavy-tool-triage.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

cat >"$work/doom" <<'EOF'
#!/bin/sh
printf '%s\n' "fake doom provider"
EOF
chmod 0755 "$work/doom"
printf '%s\n' "fake wad" >"$work/doom.wad"
cat >"$work/doom.conf" <<EOF
BB_HEAVY_TOOLS="doom"
BB_DOOM_WAD_PATH="$work/doom.wad"
BB_USER_OVERLAY_ENABLE="no"
BB_USER_OVERLAY_ROOT="./overlay"
BB_USER_OVERLAY_ALLOW_OVERRIDE="no"
BB_RUNTIME_MODE="extract"
BB_DOTFILES_ENABLE="no"
EOF
cat >"$work/doom-native.conf" <<EOF
BB_HEAVY_TOOLS="doom"
BB_DOOM_USER_PATH="$work/doom"
BB_DOOM_WAD_PATH="$work/doom.wad"
BB_USER_OVERLAY_ENABLE="no"
BB_USER_OVERLAY_ROOT="./overlay"
BB_USER_OVERLAY_ALLOW_OVERRIDE="no"
BB_RUNTIME_MODE="extract"
BB_DOTFILES_ENABLE="no"
EOF

BUSIERBOX_CONFIG="$work/doom.conf" scripts/gen-buildroot-defconfig mipsel-linux-2.6-uclibc-legacy >/dev/null
grep -q '^BR2_PACKAGE_BUSIERBOX_DOOM_ASCII=y$' buildroot/generated-configs/mipsel-linux-2.6-uclibc_defconfig
grep -q "^DOOM_WAD_PATH := $work/doom.wad$" payloads/generated-profiles/mipsel-linux-2.6-uclibc.mk

cat >"$work/nmap.conf" <<'EOF'
BB_HEAVY_TOOLS="nmap nmap-ncat"
BB_USER_OVERLAY_ENABLE="no"
BB_USER_OVERLAY_ROOT="./overlay"
BB_USER_OVERLAY_ALLOW_OVERRIDE="no"
BB_RUNTIME_MODE="extract"
BB_DOTFILES_ENABLE="no"
EOF
BUSIERBOX_CONFIG="$work/nmap.conf" scripts/gen-buildroot-defconfig glinet-mt7621-openwrt-musl >/dev/null
grep -q '^BR2_TOOLCHAIN_BUILDROOT_CXX=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
grep -q '^BR2_PACKAGE_NMAP=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
grep -q '^BR2_PACKAGE_NMAP_NCAT=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig

if [ -x runtime/payload/bin/busybox ] && runtime/payload/bin/busybox --list >/dev/null 2>&1; then
    BUSIERBOX_CONFIG="$work/doom-native.conf" scripts/build-payload >/dev/null
    test -x runtime/payload/bin/doom
    test -f runtime/payload/share/games/doom/doom.wad
    grep -qx doom runtime/payload/staged-tools.txt
    grep -qx doom runtime/payload/built-tools.txt
    grep -qx doom runtime/payload/user-provided-tools.txt
    python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("runtime/payload/manifest.json").read_text(encoding="utf-8"))
assert "doom" in m["requested_payload_tools"]
assert "doom" in m["built_payload_tools"]
assert "doom" in m["staged_payload_tools"]
assert "doom" in m["user_provided_tools"]
assert "doom" not in m["missing_payload_tools"]
PY
else
    printf '%s\n' "skip: host-runnable runtime/payload/bin/busybox missing; package-native first for doom provider smoke"
fi

printf '%s\n' "heavy-tool-triage ok"
