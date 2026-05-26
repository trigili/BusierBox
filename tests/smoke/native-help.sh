#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}

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

printf '%s\n' "native-help ok"
