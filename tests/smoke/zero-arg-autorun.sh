#!/bin/sh
set -eu

bb=${1:-dist/grit-native-full}
[ -x "$bb" ] || {
    printf '%s\n' "zero-arg-autorun: missing artifact: $bb" >&2
    exit 1
}
bb_abs=$(cd "$(dirname "$bb")" && pwd)/$(basename "$bb")

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

if GRIT_ZERO_ARG_MODE=help "$bb" >"$tmp/default.out" 2>&1; then
    :
fi
grep -Eq 'usage: grit|native applets:' "$tmp/default.out"
if grep -q 'zero-arg mode=' "$tmp/default.out" || grep -q 'zero-arg exit=' "$tmp/default.out"; then
    printf '%s\n' "zero-arg-autorun: quiet default printed status lines" >&2
    cat "$tmp/default.out" >&2
    exit 1
fi

GRIT_ZERO_ARG_MODE=help GRIT_ZERO_ARG_LOG_MODE=none "$bb" >"$tmp/none.out" 2>"$tmp/none.err" || true
[ ! -s "$tmp/none.out" ]
[ ! -s "$tmp/none.err" ]

GRIT_ZERO_ARG_MODE=help GRIT_ZERO_ARG_LOG_MODE=status "$bb" >"$tmp/status.out" 2>"$tmp/status.err" || true
grep -q 'zero-arg mode=help' "$tmp/status.err"
grep -q 'zero-arg exit=' "$tmp/status.err"

GRIT_NO_AUTORUN=1 "$bb" >"$tmp/no-autorun.out" 2>&1
grep -Eq 'usage: grit|native applets:' "$tmp/no-autorun.out"

guard="$tmp/guard"
mkdir -p "$guard"

cat >"$guard/autorun.lock" <<EOF
mode=rshell
pid=$$
started_at=0
artifact_tier=test
EOF
GRIT_AUTORUN_GUARD_PATH="$guard" GRIT_ZERO_ARG_MODE=rshell "$bb" >"$tmp/reentry.out" 2>&1
grep -q 'griTTYkit autorun already active' "$tmp/reentry.out"

ledger_run="$tmp/ledger-run"
mkdir -p "$ledger_run"
(
    cd "$ledger_run"
    GRIT_AUTORUN_GUARD_PATH="$ledger_run/guard" GRIT_ZERO_ARG_MODE=rshell "$bb_abs" >"$tmp/ledger-rshell.out" 2>&1 || true
    test -f ./.grit/run/cleanup-ledger.jsonl
    grep -q '"detail":"autorun lock"' ./.grit/run/cleanup-ledger.jsonl
    grep -q '"detail":"autorun status"' ./.grit/run/cleanup-ledger.jsonl
    if command -v python3 >/dev/null 2>&1; then
        "$bb_abs" cleanup-ledger --json | python3 -m json.tool >/dev/null
    fi
)

"$bb" doctor >"$tmp/explicit-doctor.out" 2>&1
grep -q '^artifact_tier=' "$tmp/explicit-doctor.out"

"$bb" rshell --help >"$tmp/rshell-help.out" 2>&1
grep -q 'usage: grit rshell' "$tmp/rshell-help.out"

"$bb" rshell status >"$tmp/rshell-status.out" 2>&1
grep -q 'rshell_status=' "$tmp/rshell-status.out"

GRIT_AUTORUN_GUARD_PATH="$guard" "$bb" rshell start --transport invalid-transport >"$tmp/invalid-transport.out" 2>&1 && {
    cat "$tmp/invalid-transport.out" >&2
    exit 1
}
grep -q 'unsupported transport' "$tmp/invalid-transport.out"

GRIT_AUTORUN_GUARD_PATH="$guard" "$bb" rshell start --transport builtin >"$tmp/builtin.out" 2>&1 && {
    cat "$tmp/builtin.out" >&2
    exit 1
}
grep -Eq 'operator host|requires wolfSSL|disabled' "$tmp/builtin.out"

printf '%s\n' "zero-arg-autorun ok"
