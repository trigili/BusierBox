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

BUSIERBOX_ZERO_ARG_MODE=help BUSIERBOX_ZERO_ARG_LOG_MODE=none "$bb" >"$tmp/none.out" 2>"$tmp/none.err" || true
[ ! -s "$tmp/none.out" ]
[ ! -s "$tmp/none.err" ]

BUSIERBOX_ZERO_ARG_MODE=help BUSIERBOX_ZERO_ARG_LOG_MODE=status "$bb" >"$tmp/status.out" 2>"$tmp/status.err" || true
grep -q 'zero-arg mode=help' "$tmp/status.err"
grep -q 'zero-arg exit=' "$tmp/status.err"

BUSIERBOX_NO_AUTORUN=1 "$bb" >"$tmp/no-autorun.out" 2>&1
grep -Eq 'usage: busierbox|native applets:' "$tmp/no-autorun.out"

guard="$tmp/guard"
mkdir -p "$guard"

cat >"$guard/autorun.lock" <<EOF
mode=rshell
pid=$$
started_at=0
artifact_tier=test
EOF
BUSIERBOX_AUTORUN_GUARD_PATH="$guard" BUSIERBOX_ZERO_ARG_MODE=rshell "$bb" >"$tmp/reentry.out" 2>&1
grep -q 'BusierBox autorun already active' "$tmp/reentry.out"

"$bb" doctor >"$tmp/explicit-doctor.out" 2>&1
grep -q '^artifact_tier=' "$tmp/explicit-doctor.out"

"$bb" rshell --help >"$tmp/rshell-help.out" 2>&1
grep -q 'usage: busierbox rshell' "$tmp/rshell-help.out"

"$bb" rshell status >"$tmp/rshell-status.out" 2>&1
grep -q 'rshell_status=' "$tmp/rshell-status.out"

BUSIERBOX_AUTORUN_GUARD_PATH="$guard" "$bb" rshell start --transport invalid-transport >"$tmp/invalid-transport.out" 2>&1 && {
    cat "$tmp/invalid-transport.out" >&2
    exit 1
}
grep -q 'unsupported transport' "$tmp/invalid-transport.out"

BUSIERBOX_AUTORUN_GUARD_PATH="$guard" "$bb" rshell start --transport builtin >"$tmp/builtin.out" 2>&1 && {
    cat "$tmp/builtin.out" >&2
    exit 1
}
grep -Eq 'operator host|requires wolfSSL|disabled' "$tmp/builtin.out"

printf '%s\n' "zero-arg-autorun ok"
