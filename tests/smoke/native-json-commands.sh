#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}

if [ ! -f "$artifact" ]; then
    printf '%s\n' "native JSON smoke: missing artifact $artifact" >&2
    exit 1
fi

check_json() {
    label=$1
    shift
    "$@" | python3 -m json.tool >/dev/null
    printf '%s\n' "smoke: $label JSON ok"
}

check_json "survey" "$artifact" survey --json
check_json "survey shell-probe" "$artifact" survey --json --shell-probe
check_json "manifest" "$artifact" manifest --json
check_json "cleanup-ledger" "$artifact" cleanup-ledger --json
check_json "rshell status" "$artifact" rshell status --json
