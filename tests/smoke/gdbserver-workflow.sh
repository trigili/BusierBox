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

scripts/tools/check-dropin-tool --tool gdbserver --path "$fake" --target native --arch native --libc host >/dev/null
scripts/tools/install-dropin-gdbserver --source "$fake" --target native --dest-root "$work/tools" >"$work/install.out"
test -x "$work/tools/native/bin/gdbserver"
test -f "$work/tools/native/bin/metadata.json"
python3 -m json.tool "$work/tools/native/bin/metadata.json" >/dev/null
scripts/tools/dropin-tool-status --tool gdbserver --target native --arch native --libc host --dest-root "$work/tools" >"$work/status.out"
grep -q 'Overall: found' "$work/status.out"
grep -q 'metadata_sha256=' "$work/status.out"
grep -q 'detected_arch=' "$work/status.out"

scripts/tools/install-dropin-tool --tool gdb --source "$fake" --arch mipsel --libc musl --dest-root "$work/tools" >"$work/install-gdb.out"
test -x "$work/tools/mipsel-musl/bin/gdb"
scripts/tools/dropin-tool-status --tool gdb --target glinet-mt7621-openwrt-musl --arch mipsel --libc musl --dest-root "$work/tools" >"$work/gdb-status.out"
grep -q "$work/tools/mipsel-musl/bin/gdb \\[found\\]" "$work/gdb-status.out"

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

printf '%s\n' "gdbserver-workflow ok"
