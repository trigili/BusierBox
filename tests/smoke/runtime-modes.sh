#!/bin/sh
set -eu

payload=${1:-dist/payload-native.tar.gz}
[ -f "$payload" ] || {
    printf '%s\n' "runtime-modes: missing payload archive: $payload" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

build_mode_artifact() {
    mode=$1
    out=$2
    core="$tmp/$mode.core"
    OUT="$core" ARTIFACT_TIER=full ADVERTISE_PAYLOAD_TOOLS=1 \
        BB_RUNTIME_MODE="$mode" \
        BB_RUNTIME_ROOT=".bbx-runtime" \
        BB_ZERO_ARG_MODE=help \
        scripts/build-native >/dev/null
    scripts/embed-payload "$core" "$payload" "$out" >/dev/null
}

build_mode_artifact core-only "$tmp/busierbox-core-only"
run="$tmp/run-core"
mkdir "$run"
(
    cd "$run"
    ../busierbox-core-only survey --json >/dev/null
    [ ! -e .bbx-runtime ]
    if ../busierbox-core-only sh -c 'echo no' >out 2>err; then
        printf '%s\n' "runtime-modes: core-only payload command unexpectedly succeeded" >&2
        exit 1
    fi
    grep -q 'payload unavailable' err
    [ ! -e .bbx-runtime ]
)

build_mode_artifact no-residue "$tmp/busierbox-no-residue"
run="$tmp/run-nores"
mkdir "$run"
(
    cd "$run"
    ../busierbox-no-residue sh -c 'echo ok' >out
    grep -q '^ok$' out
    [ ! -e .bbx-runtime ]
)

printf '%s\n' "runtime-modes ok"
