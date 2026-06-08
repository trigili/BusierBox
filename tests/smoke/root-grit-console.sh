#!/bin/sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
console="$ROOT/grit"

test -x "$console"

python3 "$console" --version | grep -Eq '^griTTYkit [0-9]+\.[0-9]+'
python3 "$console" artifact inspect --help 2>&1 | grep -q 'usage: grit artifact inspect ARTIFACT'
bringup_help=$(python3 "$console" bringup --help 2>&1)
printf '%s\n' "$bringup_help" | grep -Eq 'usage: .*/?grit bringup'
printf '%s\n' "$bringup_help" | grep -q 'Guided target bring-up flow'
if printf '%s\n' "$bringup_help" | grep -q 'scripts/grit-bringup'; then
    printf '%s\n' "root grit bringup help leaked scripts/grit-bringup" >&2
    exit 1
fi

printf '%s\n' "root-grit ok"
