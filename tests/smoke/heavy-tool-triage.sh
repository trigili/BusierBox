#!/bin/sh
set -eu

menu=${1:-scripts/menuconfig}

python3 -m json.tool payloads/tool-compat.json >/dev/null
python3 - payloads/tool-compat.json <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    tools = json.load(fh).get("tools") or {}

required = {
    "providers",
    "classification",
    "expected_payload_size",
    "static_constraints",
    "minimum_kernel_floor",
    "supported_arches",
    "unsupported_libcs",
}
missing = {}
for name, meta in sorted(tools.items()):
    absent = sorted(field for field in required if field not in meta)
    if absent:
        missing[name] = absent
if missing:
    for name, absent in missing.items():
        print(f"{name}: missing {', '.join(absent)}", file=sys.stderr)
    raise SystemExit("tool compatibility metadata is incomplete")
PY

grep -q 'configure_busybox_applet_search()' "$menu"
grep -q 'Search applets by name/group/description' "$menu"
grep -q 'Dangerous storage / flash diagnostics' "$menu"
grep -q 'GRIT_DOOM_WAD_PATH' "$menu"
grep -q 'GRIT_DOOM_WAD_PATH' scripts/lib/build-payload
grep -q 'GRIT_DOOM_WAD_PATH' configs/grit.conf.example
! grep -q 'GRIT_DOOM_USER_PATH' "$menu"
! grep -q 'GRIT_DOOM_USER_PATH' scripts/lib/build-payload
! grep -q 'GRIT_DOOM_USER_PATH' configs/grit.conf.example
grep -Fq 'require_static_payload_tool $PAYLOAD_ROOT/bin/doom-ascii "doom-ascii"' scripts/lib/buildroot-build-payload
grep -Fq 'must be statically linked for the griTTYkit doom payload' scripts/lib/buildroot-build-payload
grep -Fq 'requested doom but the static doom-ascii engine was not found' scripts/lib/buildroot-build-payload
! grep -Fq 'stage_first_found_as doom prboom' scripts/lib/buildroot-build-payload
! grep -Fq 'command -v prboom' scripts/lib/build-payload
! grep -Fq 'command -v chocolate-doom' scripts/lib/build-payload
! grep -Fq 'chocolate-doom' scripts/lib/buildroot-build-payload

scripts/lib/check-buildroot-tool-mappings --tools "nmap nmap-ncat openssl fd zoxide psmisc mtd-utils ubi-utils i2c-tools spi-tools mmc-utils e2fsprogs parted gdb gef-pwndbg radare2 rizin gcore tshark doom" >/dev/null
scripts/lib/check-buildroot-tool-mappings --tools doom | grep -q 'BR2_PACKAGE_GRIT_DOOM_ASCII'

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/heavy-tool-triage.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

printf '%s\n' "fake wad" >"$work/doom.wad"
cat >"$work/doom.conf" <<EOF
GRIT_HEAVY_TOOLS="doom"
GRIT_DOOM_WAD_PATH="$work/doom.wad"
GRIT_USER_OVERLAY_ENABLE="no"
GRIT_USER_OVERLAY_ROOT="./overlay"
GRIT_USER_OVERLAY_ALLOW_OVERRIDE="no"
GRIT_RUNTIME_MODE="extract"
GRIT_DOTFILES_ENABLE="no"
EOF

GRIT_CONFIG="$work/doom.conf" scripts/lib/gen-buildroot-defconfig mipsel-linux-2.6-uclibc-legacy >/dev/null
grep -q '^BR2_PACKAGE_GRIT_DOOM_ASCII=y$' buildroot/generated-configs/mipsel-linux-2.6-uclibc_defconfig
grep -q "^DOOM_WAD_PATH := $work/doom.wad$" payloads/generated-profiles/mipsel-linux-2.6-uclibc.mk

mkdir -p "$work/payload/share/games/doom"
printf '%s\n' "fake wad" >"$work/payload/share/games/doom/doom.wad"
printf '%s\n' "doom" >"$work/payload/staged-tools.txt"
printf '%s\n' "doom" >"$work/payload/built-tools.txt"
scripts/lib/write-payload-manifest \
    --target mipsel-linux-2.6-uclibc-legacy \
    --arch mipsel \
    --libc uclibc \
    --kernel-floor 2.6 \
    --busybox-version test \
    --static-status static \
    --payload-sha256 pending \
    --requested-tools doom \
    --payload-dir "$work/payload"
python3 - "$work/payload/manifest.json" "$work" <<'PY'
import hashlib
import json
import sys

manifest = json.load(open(sys.argv[1], "r", encoding="utf-8"))
work = sys.argv[2]
wads = manifest.get("doom_wads") or []
if len(wads) != 1:
    raise SystemExit("heavy-tool-triage: payload manifest did not record staged Doom WAD")
wad = wads[0]
if wad.get("filename") != "doom.wad":
    raise SystemExit("heavy-tool-triage: Doom WAD manifest should record basename only")
if work in json.dumps(wad, sort_keys=True):
    raise SystemExit("heavy-tool-triage: Doom WAD manifest leaked local build path")
expected = hashlib.sha256(b"fake wad\n").hexdigest()
if wad.get("sha256") != expected:
    raise SystemExit("heavy-tool-triage: Doom WAD manifest sha256 mismatch")
if wad.get("size") != len(b"fake wad\n"):
    raise SystemExit("heavy-tool-triage: Doom WAD manifest size mismatch")
PY

cat >"$work/nmap.conf" <<'EOF'
GRIT_HEAVY_TOOLS="nmap nmap-ncat"
GRIT_USER_OVERLAY_ENABLE="no"
GRIT_USER_OVERLAY_ROOT="./overlay"
GRIT_USER_OVERLAY_ALLOW_OVERRIDE="no"
GRIT_RUNTIME_MODE="extract"
GRIT_DOTFILES_ENABLE="no"
EOF
GRIT_CONFIG="$work/nmap.conf" scripts/lib/gen-buildroot-defconfig glinet-mt7621-openwrt-musl >/dev/null
grep -q '^BR2_TOOLCHAIN_BUILDROOT_CXX=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
grep -q '^BR2_PACKAGE_NMAP=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig
grep -q '^BR2_PACKAGE_NMAP_NCAT=y$' buildroot/generated-configs/mipsel-linux-4.x-musl_defconfig

if [ -x runtime/payload/bin/busybox ] && runtime/payload/bin/busybox --list >/dev/null 2>&1; then
    if GRIT_CONFIG="$work/doom.conf" scripts/lib/build-payload >"$work/native-doom.out" 2>"$work/native-doom.err"; then
        printf '%s\n' "heavy-tool-triage: native doom packaging unexpectedly succeeded" >&2
        exit 1
    fi
    grep -q 'native payloads do not stage Doom engines' "$work/native-doom.err"
else
    printf '%s\n' "skip: host-runnable runtime/payload/bin/busybox missing; package-native first for native doom rejection smoke"
fi

printf '%s\n' "heavy-tool-triage ok"
