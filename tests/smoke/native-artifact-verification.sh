#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}

if [ ! -f "$artifact" ]; then
    printf '%s\n' "native artifact verification smoke: missing artifact $artifact" >&2
    exit 1
fi

scripts/lib/inspect-artifact "$artifact" >/dev/null
scripts/lib/verify-artifact "$artifact"

printf '%s\n' "smoke: native artifact verification ok"
