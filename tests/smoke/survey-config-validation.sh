#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}

if [ ! -f "$artifact" ]; then
    printf '%s\n' "survey config validation smoke: missing artifact $artifact" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "skip: python3 survey config validation unavailable"
    exit 0
fi

tmp=${TMPDIR:-/tmp}
work=$(mktemp -d "$tmp/grit-survey-config.XXXXXX")
cleanup() {
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM

"$artifact" survey --json >"$work/survey.json"
python3 tests/smoke/validate-survey-json.py "$work/survey.json" >/dev/null
scripts/lib/config-from-survey "$work/survey.json" >/dev/null
