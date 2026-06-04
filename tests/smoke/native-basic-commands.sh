#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}

if [ ! -f "$artifact" ]; then
    printf '%s\n' "native basic smoke: missing artifact $artifact" >&2
    exit 1
fi

"$artifact" list >/dev/null
"$artifact" survey >/dev/null
"$artifact" envfix >/dev/null
"$artifact" extract >/dev/null
"$artifact" extract >/dev/null
"$artifact" sh -c 'echo ok' >/dev/null
"$artifact" cp --help >/dev/null 2>&1
"$artifact" dd --help >/dev/null 2>&1
"$artifact" nc --help >/dev/null 2>&1
"$artifact" config-info >/dev/null

printf '%s\n' "smoke: native basic commands ok"
