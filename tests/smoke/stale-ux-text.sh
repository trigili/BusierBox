#!/bin/sh
# Ensure retired stager/callback UX does not return to user-facing files.
set -eu

tmp=${TMPDIR:-/tmp}/busierbox-stale-ux.$$
trap 'rm -f "$tmp"' EXIT HUP INT TERM

rg -n \
    -e '--rshell' \
    -e 'wait-operator-tunnel' \
    -e 'scripts/busierbox-server --rshell' \
    -e 'scripts/busierbox-server --wait-operator-tunnel' \
    -e 'shell-again' \
    -e 'send_file' \
    -e 'framed callback' \
    -e 'stager callback' \
    scripts src docs presets targets tests \
    >"$tmp" || true

# Internal regression tests may mention forbidden strings as data.
if grep -v '^tests/smoke/busierbox-server.py:' "$tmp" |
    grep -v '^tests/smoke/stale-ux-text.sh:' |
    grep -q .; then
    printf '%s\n' "stale-ux-text: retired user-facing text found" >&2
    grep -v '^tests/smoke/busierbox-server.py:' "$tmp" |
        grep -v '^tests/smoke/stale-ux-text.sh:' >&2
    exit 1
fi

for doc in \
    docs/plan-mode.md \
    docs/cleanup-ledger.md \
    docs/gdbserver-workflow.md \
    docs/release-bundles.md \
    docs/heavy-tools-triage.md
do
    grep -q "$doc" README.md || {
        printf '%s\n' "stale-ux-text: README missing workflow doc link $doc" >&2
        exit 1
    }
done

printf '%s\n' "stale-ux-text ok"
