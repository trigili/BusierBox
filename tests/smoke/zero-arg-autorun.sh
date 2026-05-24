#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
[ -x "$bb" ] || {
    printf '%s\n' "zero-arg-autorun: missing artifact: $bb" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

if BUSIERBOX_ZERO_ARG_MODE=help "$bb" >"$tmp/default.out" 2>&1; then
    :
fi
grep -Eq 'usage: busierbox|native applets:' "$tmp/default.out"

BUSIERBOX_NO_AUTORUN=1 "$bb" >"$tmp/no-autorun.out" 2>&1
grep -Eq 'usage: busierbox|native applets:' "$tmp/no-autorun.out"

BUSIERBOX_ZERO_ARG_MODE=doctor "$bb" >"$tmp/doctor.out" 2>&1
grep -q '^artifact_tier=' "$tmp/doctor.out"

guard="$tmp/guard"
BUSIERBOX_AUTORUN_GUARD_PATH="$guard" BUSIERBOX_ZERO_ARG_MODE=bootstrap "$bb" >"$tmp/bootstrap.out" 2>&1 || {
    cat "$tmp/bootstrap.out" >&2
    exit 1
}
[ -f "$guard/autorun.lock" ]

cat >"$guard/autorun.lock" <<EOF
mode=bootstrap
pid=$$
started_at=0
artifact_tier=test
EOF
BUSIERBOX_AUTORUN_GUARD_PATH="$guard" BUSIERBOX_ZERO_ARG_MODE=bootstrap "$bb" >"$tmp/reentry.out" 2>&1
grep -q 'BusierBox autorun already active' "$tmp/reentry.out"

"$bb" doctor >"$tmp/explicit-doctor.out" 2>&1
grep -q '^artifact_tier=' "$tmp/explicit-doctor.out"

printf '%s\n' "zero-arg-autorun ok"
