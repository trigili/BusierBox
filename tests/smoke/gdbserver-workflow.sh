#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/gdbserver-workflow.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

fake="$work/gdbserver"
cat >"$fake" <<'EOF'
#!/bin/sh
printf '%s\n' "fake gdbserver"
EOF
chmod 0755 "$fake"

scripts/tools/check-dropin-tool --tool gdbserver --path "$fake" --target native --arch native --libc host --metadata-out "$work/check-metadata.json" >"$work/check.out"
grep -q '^sha256=' "$work/check.out"
python3 -m json.tool "$work/check-metadata.json" >/dev/null
python3 - "$work/check-metadata.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("tool") != "gdbserver":
    raise SystemExit("metadata tool mismatch")
if len(data.get("sha256", "")) != 64:
    raise SystemExit("metadata sha256 missing")
if data.get("status") != "ok":
    raise SystemExit("metadata status mismatch")
PY
scripts/tools/install-dropin-gdbserver --source "$fake" --target native --dest-root "$work/tools" >"$work/install.out"
test -x "$work/tools/native/bin/gdbserver"
test -f "$work/tools/native/bin/metadata.json"
grep -q '^sha256=' "$work/install.out"
python3 -m json.tool "$work/tools/native/bin/metadata.json" >/dev/null
if scripts/tools/check-dropin-tool --tool gdbserver --path "$fake" --arch mipsel --libc musl --strict >"$work/strict-script.out" 2>"$work/strict-script.err"; then
    printf '%s\n' "gdbserver-workflow: strict check accepted script with unknown target arch" >&2
    exit 1
fi
grep -q 'unable to detect arch expected=mipsel' "$work/strict-script.out"
mockbin="$work/mockbin"
mkdir "$mockbin"
cat >"$mockbin/file" <<'EOF'
#!/bin/sh
printf '%s\n' "$1: ELF 32-bit MSB executable, MIPS"
EOF
chmod 0755 "$mockbin/file"
cat >"$mockbin/readelf" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod 0755 "$mockbin/readelf"
if PATH="$mockbin:$PATH" scripts/tools/check-dropin-tool --tool gdbserver --path "$fake" --arch mipsel --libc musl --strict >"$work/strict-endian.out" 2>"$work/strict-endian.err"; then
    printf '%s\n' "gdbserver-workflow: strict check accepted big-endian MIPS for mipsel" >&2
    exit 1
fi
grep -q '^expected_endian=little$' "$work/strict-endian.out"
grep -q 'endian mismatch expected=little detected=big' "$work/strict-endian.out"
if command -v ls >/dev/null 2>&1; then
    if scripts/tools/install-dropin-gdbserver --source "$(command -v ls)" --arch mipsel --libc musl --dest-root "$work/tools-strict" --strict >"$work/install-strict.out" 2>"$work/install-strict.err"; then
        printf '%s\n' "gdbserver-workflow: strict install accepted mismatched host binary" >&2
        exit 1
    fi
    grep -q 'arch mismatch expected=mipsel' "$work/install-strict.out"
    test ! -e "$work/tools-strict/mipsel-musl/bin/gdbserver"
    test ! -e "$work/tools-strict/mipsel-musl/bin/metadata.json"
fi
scripts/tools/dropin-tool-status --tool gdbserver --target native --arch native --libc host --dest-root "$work/tools" >"$work/status.out"
grep -q 'Overall: found' "$work/status.out"
grep -q 'metadata_sha256=' "$work/status.out"
grep -q '    sha256=' "$work/status.out"
grep -q 'detected_arch=' "$work/status.out"
scripts/tools/dropin-tool-status --tool gdbserver --target native --arch native --libc host --dest-root "$work/tools" --json >"$work/status.json"
python3 -m json.tool "$work/status.json" >/dev/null
python3 - "$work/status.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("schema") != 1:
    raise SystemExit("schema mismatch")
if data.get("tool") != "gdbserver":
    raise SystemExit("tool mismatch")
if data.get("overall") != "found":
    raise SystemExit("overall mismatch")
found = [p for p in data.get("search_paths", []) if p.get("executable")]
if len(found) != 1:
    raise SystemExit("expected exactly one executable path")
entry = found[0]
if entry.get("status") != "ok":
    raise SystemExit("entry status mismatch")
if entry.get("check", {}).get("sha256") != entry.get("metadata", {}).get("sha256"):
    raise SystemExit("metadata sha mismatch")
PY

scripts/tools/install-dropin-tool --tool gdb --source "$fake" --arch mipsel --libc musl --dest-root "$work/tools" >"$work/install-gdb.out"
test -x "$work/tools/mipsel-musl/bin/gdb"
scripts/tools/dropin-tool-status --tool gdb --target glinet-mt7621-openwrt-musl --arch mipsel --libc musl --dest-root "$work/tools" >"$work/gdb-status.out"
grep -q "$work/tools/mipsel-musl/bin/gdb \\[found\\]" "$work/gdb-status.out"
scripts/tools/dropin-tool-status --tool missing-tool --target native --arch native --libc host --dest-root "$work/tools" --json >"$work/missing-status.json"
python3 - "$work/missing-status.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("overall") != "missing":
    raise SystemExit("missing overall mismatch")
if any(path.get("executable") for path in data.get("search_paths", [])):
    raise SystemExit("missing tool reported executable path")
PY

cat >"$work/survey.json" <<'EOF'
{
  "arch": "mipsel",
  "endianness": "little",
  "uname": {"machine": "mipsel"},
  "recommendations": {
    "target_arch_guess": "mipsel",
    "endian_guess": "little"
  }
}
EOF
cat >"$work/manifest.json" <<'EOF'
{
  "target": {
    "name": "mipsel-linux-4.x-musl",
    "arch": "mipsel",
    "endian": "little",
    "libc": "musl"
  }
}
EOF
scripts/busierbox-gdb-workspace --survey "$work/survey.json" --manifest "$work/manifest.json" \
    --out "$work/ws" --host 127.0.0.1 --port 31337 --binary ./app >/dev/null
test -f "$work/ws/target.json"
test -f "$work/ws/connect.gdb"
grep -q 'set architecture mips' "$work/ws/connect.gdb"
grep -q 'set endian little' "$work/ws/connect.gdb"
grep -q 'target remote 127.0.0.1:31337' "$work/ws/connect.gdb"

cat >"$work/gdb.conf" <<EOF
BB_HEAVY_TOOLS="gdbserver"
BB_GDBSERVER_PROVIDER="local-dropin"
BB_TARGET_NAME="native"
BB_TARGET_ARCH="native"
BB_TARGET_LIBC="host"
BB_DOTFILES_ENABLE="no"
BB_USER_OVERLAY_ENABLE="no"
EOF
mkdir -p local/tools/native/bin
cp "$fake" local/tools/native/bin/gdbserver
chmod 0755 local/tools/native/bin/gdbserver
trap 'rm -rf "$work"; rm -f local/tools/native/bin/gdbserver local/tools/native/bin/metadata.json' EXIT HUP INT TERM
if [ -x runtime/payload/bin/busybox ]; then
    BUSIERBOX_CONFIG="$work/gdb.conf" scripts/build-payload >/dev/null
    test -x runtime/payload/bin/gdbserver
    grep -qx gdbserver runtime/payload/staged-tools.txt
    grep -qx gdbserver runtime/payload/built-tools.txt
else
    printf '%s\n' "skip: runtime/payload/bin/busybox missing; package-native first for gdbserver provider smoke"
fi

cat >"$work/bad-buildroot.conf" <<'EOF'
BB_HEAVY_TOOLS="gdbserver"
BB_GDBSERVER_PROVIDER="auto"
BB_TARGET_ARCH="mipsel"
BB_TARGET_LIBC="musl"
BB_STATIC_POLICY="static-preferred"
EOF
BUSIERBOX_CONFIG="$work/bad-buildroot.conf" scripts/gen-buildroot-defconfig glinet-mt7621-openwrt-musl >"$work/defconfig.out" 2>"$work/defconfig.err" || true
grep -q 'gdbserver pre-excluded' "$work/defconfig.err"
grep -q 'Buildroot GDB BFD fails' "$work/defconfig.err"

cat >"$work/local-dropin-defconfig.conf" <<'EOF'
BB_HEAVY_TOOLS="gdbserver"
BB_GDBSERVER_PROVIDER="local-dropin"
BB_TARGET_ARCH="mipsel"
BB_TARGET_LIBC="uclibc"
BB_STATIC_POLICY="static-preferred"
EOF
BUSIERBOX_CONFIG="$work/local-dropin-defconfig.conf" scripts/gen-buildroot-defconfig mipsel-linux-2.6-uclibc-legacy >/dev/null
grep -q '^# gdbserver: provider=local-dropin (not Buildroot), no BR2 symbol emitted$' buildroot/generated-configs/mipsel-linux-2.6-uclibc_defconfig
grep -q '^BR2_TOOLCHAIN_BUILDROOT_CXX=n$' buildroot/generated-configs/mipsel-linux-2.6-uclibc_defconfig
! grep -q '^BR2_PACKAGE_GDB' buildroot/generated-configs/mipsel-linux-2.6-uclibc_defconfig

printf '%s\n' "gdbserver-workflow ok"
