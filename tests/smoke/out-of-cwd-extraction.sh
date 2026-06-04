#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}

if [ ! -f "$artifact" ]; then
    printf '%s\n' "out-of-cwd extraction smoke: missing artifact $artifact" >&2
    exit 1
fi

tmp=${TMPDIR:-/tmp}
work=$(mktemp -d "$tmp/grit-out-of-cwd.XXXXXX")
cleanup() {
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM

printf '%s\n' "smoke: testing out-of-cwd embedded extraction (catches exe-wipe bugs)..."
cp "$artifact" "$work/grit"
chmod +x "$work/grit"

(
    cd "$work"
    ./grit extract >/dev/null
    ./grit sh -c 'echo dispatch-ok' >/dev/null
    ./grit cp --help >/dev/null 2>&1
    ./grit touch --help >/dev/null 2>&1
    ./grit ls --help >/dev/null 2>&1
    ./grit extract >/dev/null
)

printf '%s\n' "smoke: out-of-cwd ok"
