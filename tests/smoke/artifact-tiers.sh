#!/bin/sh
set -eu

full=${1:-dist/busierbox-native-full}
stager=${2:-dist/busierbox-native-stager}

[ -x "$full" ] || {
    printf '%s\n' "artifact-tiers: missing full artifact: $full" >&2
    exit 1
}
[ -x "$stager" ] || {
    printf '%s\n' "artifact-tiers: missing stager artifact: $stager" >&2
    exit 1
}

"$full" config-info | grep -q '^artifact_tier=full$'
"$full" config-info | grep -q '^embedded_payload=yes$'
"$stager" --help >/dev/null
if command -v python3 >/dev/null 2>&1; then
    "$stager" survey --json | python3 -m json.tool >/dev/null
fi

if [ -e dist/busierbox-native.core ]; then
    printf '%s\n' "artifact-tiers: deployable-looking .core artifact leaked into dist/" >&2
    exit 1
fi

printf '%s\n' "artifact-tiers ok"
