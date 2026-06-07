#!/bin/sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
console="$ROOT/grit-console"

test -x "$console"

python3 "$console" --version | grep -Eq '^griTTYkit [0-9]+\.[0-9]+'
python3 "$console" artifact inspect --help 2>&1 | grep -q 'usage: grit-console artifact inspect ARTIFACT'
python3 "$console" bringup --help 2>&1 | grep -q 'Guided target bring-up flow'

printf '%s\n' "root-grit-console ok"
