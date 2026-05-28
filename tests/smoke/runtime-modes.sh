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
    root=${3:-.bbx-runtime}
    allow_fallback=${4:-no}
    fallback_root=${5:-/tmp/.busierbox}
    noresidue_level=${6:-best-effort}
    core="$tmp/$mode.core"
    OUT="$core" ARTIFACT_TIER=full ADVERTISE_PAYLOAD_TOOLS=1 \
        BB_RUNTIME_MODE="$mode" \
        BB_NORESIDUE_LEVEL="$noresidue_level" \
        BB_RUNTIME_ROOT="$root" \
        BB_RUNTIME_ALLOW_FALLBACK_ROOT="$allow_fallback" \
        BB_RUNTIME_FALLBACK_ROOT="$fallback_root" \
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
    if ../busierbox-no-residue sh -c 'exit 7'; then
        printf '%s\n' "runtime-modes: no-residue failed command unexpectedly succeeded" >&2
        exit 1
    else
        rc=$?
        [ "$rc" -eq 7 ] || {
            printf '%s\n' "runtime-modes: expected no-residue command exit 7, got $rc" >&2
            exit 1
        }
    fi
    [ ! -e .bbx-runtime ]
    ../busierbox-no-residue sh -c 'while :; do sleep 1; done' >/dev/null 2>term.err &
    bb_pid=$!
    i=0
    while [ ! -e .bbx-runtime ]; do
        i=$((i + 1))
        if [ "$i" -gt 50 ]; then
            kill "$bb_pid" 2>/dev/null || true
            printf '%s\n' "runtime-modes: no-residue signal test did not create runtime root" >&2
            exit 1
        fi
        sleep 0.1
    done
    kill -TERM "$bb_pid"
    if wait "$bb_pid"; then
        printf '%s\n' "runtime-modes: SIGTERM no-residue command unexpectedly succeeded" >&2
        exit 1
    else
        rc=$?
        [ "$rc" -eq 143 ] || {
            printf '%s\n' "runtime-modes: expected SIGTERM no-residue exit 143, got $rc" >&2
            exit 1
        }
    fi
    [ ! -e .bbx-runtime ]
)

build_mode_artifact no-residue "$tmp/busierbox-no-residue-fallback" ".bbx-runtime-blocked" yes ".bbx-fallback"
run="$tmp/run-nores-fallback"
mkdir "$run"
(
    cd "$run"
    printf '%s\n' "not a directory" >.bbx-runtime-blocked
    ../busierbox-no-residue-fallback clean --dry-run >dry-run.out
    grep -q '.bbx-fallback (fallback root' dry-run.out
    ../busierbox-no-residue-fallback sh -c 'echo fallback-ok' >out
    grep -q '^fallback-ok$' out
    [ -f .bbx-runtime-blocked ]
    [ ! -e .bbx-fallback ]
)

build_mode_artifact no-residue "$tmp/busierbox-no-residue-aggressive" ".bbx-aggressive" no "/tmp/.busierbox" aggressive
run="$tmp/run-nores-aggressive"
mkdir "$run"
(
    cd "$run"
    ../busierbox-no-residue-aggressive config-info >config-info.out
    grep -q '^effective_noresidue_level=aggressive$' config-info.out
    grep -q '^noresidue_policy_active=yes$' config-info.out
    grep -q '^noresidue_policy_level=aggressive$' config-info.out
    grep -q '^noresidue_policy_aggressive_minimizes_runtime_residue=yes$' config-info.out
    grep -q '^noresidue_policy_forensic_no_trace=no$' config-info.out
    grep -q '^noresidue_policy_external_writes_require_explicit_apply=yes$' config-info.out
    ../busierbox-no-residue-aggressive doctor >doctor.out
    grep -q '^noresidue_active=yes$' doctor.out
    grep -q '^noresidue_level=aggressive$' doctor.out
    grep -q '^noresidue_aggressive_minimizes_runtime_residue=yes$' doctor.out
    grep -q '^noresidue_forensic_no_trace=no$' doctor.out
    grep -q '^noresidue_external_writes_require_explicit_apply=yes$' doctor.out
    ../busierbox-no-residue-aggressive doctor --json | python3 -m json.tool >doctor.json
    python3 - doctor.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
policy = doc["noresidue_policy"]
assert policy["active"] is True
assert policy["level"] == "aggressive"
assert policy["aggressive_minimizes_runtime_residue"] is True
assert policy["forensic_no_trace"] is False
assert policy["external_writes_require_explicit_apply"] is True
PY
    ../busierbox-no-residue-aggressive manifest --json | python3 -m json.tool >manifest.json
    grep -q '"noresidue_level": "aggressive"' manifest.json
    ../busierbox-no-residue-aggressive plan extract --json | python3 -m json.tool >plan.json
    grep -q '"noresidue_level": "aggressive"' plan.json
    ../busierbox-no-residue-aggressive sh -c 'echo aggressive-ok' >out
    grep -q '^aggressive-ok$' out
    [ ! -e .bbx-aggressive ]
    printf '%s\n' "not a directory" >.bbx-aggressive-blocked
    if BB_RUNTIME_ROOT=.bbx-aggressive-blocked BB_RUNTIME_ALLOW_FALLBACK_ROOT=yes BB_RUNTIME_FALLBACK_ROOT=.bbx-aggressive-fallback ../busierbox-no-residue-aggressive sh -c 'echo should-not-fallback' >fallback.out 2>fallback.err; then
        printf '%s\n' "runtime-modes: aggressive no-residue unexpectedly used fallback root" >&2
        exit 1
    fi
    grep -q 'payload unavailable' fallback.err
    [ -f .bbx-aggressive-blocked ]
    [ ! -e .bbx-aggressive-fallback ]
    BB_RUNTIME_ROOT=.bbx-aggressive-blocked BB_RUNTIME_ALLOW_FALLBACK_ROOT=yes BB_RUNTIME_FALLBACK_ROOT=.bbx-aggressive-fallback ../busierbox-no-residue-aggressive doctor --json | python3 -m json.tool >aggressive-fallback-doctor.json
    python3 - aggressive-fallback-doctor.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
runtime = doc["extraction_runtime"]
assert runtime["fallback_configured"] is True
assert runtime["fallback_enabled"] is False
assert runtime["fallback_disabled_by_aggressive_noresidue"] is True
assert runtime["selected_root"] is None
PY
    if BB_RUNTIME_ROOT=.bbx-aggressive-blocked ../busierbox-no-residue-aggressive config-push --host 127.0.0.1 --port 1 --tls no --quiet >config-push-blocked.out 2>config-push-blocked.err; then
        printf '%s\n' "runtime-modes: aggressive config-push unexpectedly created scratch outside runtime root" >&2
        exit 1
    fi
    grep -q 'unable to create temporary config JSON' config-push-blocked.err
    if ls .busierbox-config.* >/dev/null 2>&1; then
        printf '%s\n' "runtime-modes: aggressive config-push left cwd scratch" >&2
        exit 1
    fi
    ../busierbox-no-residue-aggressive reality-test --json | python3 -m json.tool >reality.json
    [ ! -e .bbx-aggressive ]
)

if OUT="$tmp/aggressive-fallback-invalid.core" ARTIFACT_TIER=full ADVERTISE_PAYLOAD_TOOLS=1 \
    BB_RUNTIME_MODE=no-residue \
    BB_NORESIDUE_LEVEL=aggressive \
    BB_RUNTIME_ALLOW_FALLBACK_ROOT=yes \
    BB_ZERO_ARG_MODE=help \
    scripts/build-native >"$tmp/aggressive-fallback-invalid.out" 2>"$tmp/aggressive-fallback-invalid.err"; then
    printf '%s\n' "runtime-modes: build-native accepted aggressive no-residue fallback root" >&2
    exit 1
fi
grep -q 'aggressive no-residue cannot use runtime fallback root' "$tmp/aggressive-fallback-invalid.err"

build_mode_artifact extract "$tmp/busierbox-extract-fallback-clean" ".bbx-runtime-blocked" yes ".bbx-fallback"
run="$tmp/run-clean-fallback"
mkdir "$run"
(
    cd "$run"
    printf '%s\n' "not a directory" >.bbx-runtime-blocked
    ../busierbox-extract-fallback-clean extract >/dev/null
    [ -d .bbx-fallback/payload ]
    ../busierbox-extract-fallback-clean clean --ledger >/dev/null
    [ -f .bbx-runtime-blocked ]
    [ ! -e .bbx-fallback ]
)

printf '%s\n' "runtime-modes ok"
