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
"$stager" config-info | grep -q '^artifact_tier=stager$'
"$stager" config-info | grep -q '^embedded_payload=no$'
"$stager" fetch-full --help >/dev/null

if "$stager" list --plain | awk '$1 == "busybox" || $1 == "tool" { found = 1 } END { exit found ? 0 : 1 }'; then
    printf '%s\n' "artifact-tiers: stager advertised payload tools" >&2
    exit 1
fi

if [ -e dist/busierbox-native.core ]; then
    printf '%s\n' "artifact-tiers: deployable-looking .core artifact leaked into dist/" >&2
    exit 1
fi

printf '%s\n' "artifact-tiers ok"
