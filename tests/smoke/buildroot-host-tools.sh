#!/bin/sh
set -eu

tmp=${TMPDIR:-/tmp}/grit-buildroot-host-tools.$$
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

host=$tmp/out/host
mkdir -p "$host/bin"

cat >"$host/bin/fakeroot" <<'EOF'
#!/bin/sh
FAKEROOT_PREFIX=/old/tree/buildroot/output/mips-linux-2.4-uclibc/host
FAKEROOT_BINDIR=/old/tree/buildroot/output/mips-linux-2.4-uclibc/host/bin
PATHS=/old/tree/buildroot/output/mips-linux-2.4-uclibc/host/lib:${FAKEROOT_PREFIX}/lib64/libfakeroot:${FAKEROOT_PREFIX}/lib32/libfakeroot
export FAKEROOT_PREFIX FAKEROOT_BINDIR PATHS
EOF
chmod 0755 "$host/bin/fakeroot"

scripts/lib/repair-buildroot-host-tools "$tmp/out" >"$tmp/repair.out"

expected=$tmp/out/host
grep "^FAKEROOT_PREFIX=$expected\$" "$host/bin/fakeroot" >/dev/null
grep "^FAKEROOT_BINDIR=$expected/bin\$" "$host/bin/fakeroot" >/dev/null
grep "^PATHS=$expected/lib:\${FAKEROOT_PREFIX}/lib64/libfakeroot:\${FAKEROOT_PREFIX}/lib32/libfakeroot\$" "$host/bin/fakeroot" >/dev/null
grep "updated host fakeroot paths" "$tmp/repair.out" >/dev/null

scripts/lib/repair-buildroot-host-tools "$tmp/out" >"$tmp/repair-again.out"
test ! -s "$tmp/repair-again.out"

printf '%s\n' "buildroot-host-tools ok"
