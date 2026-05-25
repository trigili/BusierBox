#!/bin/sh
set -eu

full=${1:-dist/busierbox-native-full}

[ -x "$full" ] || {
    printf '%s\n' "artifact-tiers: missing full artifact: $full" >&2
    exit 1
}
"$full" config-info | grep -q '^artifact_tier=full$'
"$full" config-info | grep -q '^embedded_payload=yes$'
"$full" --help >/dev/null

if [ -e dist/busierbox-native.core ]; then
    printf '%s\n' "artifact-tiers: deployable-looking .core artifact leaked into dist/" >&2
    exit 1
fi
if [ -e dist/busierbox-native-stager ]; then
    printf '%s\n' "artifact-tiers: retired stager artifact leaked into dist/" >&2
    exit 1
fi

printf '%s\n' "artifact-tiers ok"
