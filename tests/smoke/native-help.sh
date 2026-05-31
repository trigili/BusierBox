#!/bin/sh
set -eu

bb=${1:-dist/grit-native-full}

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/native-help.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" list --plain | while read -r kind app; do
    [ "$kind" = native ] || continue
    out="$tmp/$app.out"
    err="$tmp/$app.err"
    if ! "$bb" "$app" --help >"$out" 2>"$err"; then
        printf '%s\n' "native-help: $app --help failed" >&2
        cat "$err" >&2
        exit 1
    fi
    if [ ! -s "$out" ] && [ ! -s "$err" ]; then
        printf '%s\n' "native-help: $app --help produced no output" >&2
        exit 1
    fi
done

if ! "$bb" fetch --help 2>&1 | grep -q -- '--target-id ID'; then
    printf '%s\n' "native-help: fetch help missing target identity options" >&2
    exit 1
fi
if ! "$bb" fetch --help 2>&1 | grep -q -- '--target-alias ALIAS'; then
    printf '%s\n' "native-help: fetch help missing target alias option" >&2
    exit 1
fi
if ! "$bb" put --help 2>&1 | grep -q -- '--target-id ID'; then
    printf '%s\n' "native-help: put help missing target identity options" >&2
    exit 1
fi
if ! "$bb" put --help 2>&1 | grep -q -- '--target-alias ALIAS'; then
    printf '%s\n' "native-help: put help missing target alias option" >&2
    exit 1
fi
if ! "$bb" config-push --help 2>&1 | grep -q -- '--target-id ID'; then
    printf '%s\n' "native-help: config-push help missing target identity options" >&2
    exit 1
fi
if ! "$bb" config-push --help 2>&1 | grep -q -- '--target-alias ALIAS'; then
    printf '%s\n' "native-help: config-push help missing target alias option" >&2
    exit 1
fi
if ! "$bb" persistence --help 2>&1 | grep -q -- '--target-id ID'; then
    printf '%s\n' "native-help: persistence help missing target identity options" >&2
    exit 1
fi
if ! "$bb" persistence --help 2>&1 | grep -q -- '--target-alias ALIAS'; then
    printf '%s\n' "native-help: persistence help missing target alias option" >&2
    exit 1
fi

printf '%s\n' "native-help ok"
