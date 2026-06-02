#!/bin/sh
# Ensure retired stager/callback UX does not return to user-facing files.
set -eu

tmp=${TMPDIR:-/tmp}/grit-stale-ux.$$
trap 'rm -f "$tmp"' EXIT HUP INT TERM

rg -n \
    -e '--rshell' \
    -e 'wait-operator-tunnel' \
    -e 'scripts/grit-console --rshell' \
    -e 'scripts/grit-console --wait-operator-tunnel' \
    -e 'shell-again' \
    -e 'send_file' \
    -e 'framed callback' \
    -e 'stager callback' \
    scripts src docs presets targets tests \
    >"$tmp" || true

# Internal regression tests may mention forbidden strings as data.
if grep -v '^tests/smoke/grit-console.py:' "$tmp" |
    grep -v '^tests/smoke/stale-ux-text.sh:' |
    grep -q .; then
    printf '%s\n' "stale-ux-text: retired user-facing text found" >&2
    grep -v '^tests/smoke/grit-console.py:' "$tmp" |
        grep -v '^tests/smoke/stale-ux-text.sh:' >&2
    exit 1
fi

for doc in \
    docs/plan-mode.md \
    docs/cleanup-ledger.md \
    docs/gdbserver-workflow.md \
    docs/release-bundles.md \
    docs/heavy-tools-triage.md \
    docs/licensing.md
do
    grep -q "$doc" README.md || {
        printf '%s\n' "stale-ux-text: README missing workflow doc link $doc" >&2
        exit 1
    }
done

require_text() {
    file=$1
    pattern=$2
    grep -Eq "$pattern" "$file" || {
        printf '%s\n' "stale-ux-text: $file missing required wording: $pattern" >&2
        exit 1
    }
}

require_text README.md 'not a BusyBox replacement and is not a BusyBox fork'
require_text README.md 'payload/bin/busybox'
require_text README.md 'payload/bin/<tool>'
require_text README.md 'positive inventory by default'
require_text README.md 'release self-test'
if grep -q 'by_device:gl-mt1300' README.md docs/release-bundles.md; then
    printf '%s\n' "stale-ux-text: release docs still use stale gl-mt1300 selector" >&2
    exit 1
fi
if grep -q 'release selection number, recommendation id, artifact path, by_device:NAME, or by_tuple_path:PATH' scripts/grit-console; then
    printf '%s\n' "stale-ux-text: workbench release prompt omits payload preset selectors" >&2
    exit 1
fi
if grep -q 'not an artifact sender' scripts/grit-console; then
    printf '%s\n' "stale-ux-text: grit-console still describes itself as not serving artifacts" >&2
    exit 1
fi
require_text scripts/grit-console 'operator console and service supervisor'
require_text scripts/grit-console 'staged file delivery'
require_text docs/manifest.md 'positive inventory by default'
require_text docs/manifest.md 'payload/bin/busybox'
require_text docs/manifest.md 'payload/bin/<tool>'
require_text docs/artifact-runtime-overrides.md 'cannot change target tuple compatibility'
require_text docs/artifact-runtime-overrides.md 'remove, or replace payload contents'
require_text docs/release-bundles.md 'scripts/lib/release-self-test'
require_text docs/release-bundles.md 'source_tree_changed_during_build'
require_text docs/release-bundles.md 'source_tree_stability'
require_text docs/release-bundles.md 'scripts/lib/release-find --device glinet-mt1300'
require_text docs/release-bundles.md 'scripts/verify-checksums --configured'
require_text docs/release-bundles.md 'event_log_stats'
require_text docs/release-bundles.md 'total valid event count'
require_text docs/release-bundles.md 'unexpected_listener'
require_text docs/release-bundles.md 'invalid_event_log'
require_text docs/release-bundles.md 'PID ownership evidence'
require_text docs/release-bundles.md 'api_resources_by_records_key'
require_text docs/release-bundles.md 'offline artifact browser discover record keys'
require_text docs/cleanup-ledger.md 'not forensic no-trace execution'
require_text docs/recovery.md 'authorized lab reboot recovery'
require_text docs/recovery.md 'visible and'
require_text docs/recovery.md 'reversible'
require_text docs/recovery.md 'explicit apply requirements'
require_text docs/persistence.md 'actions_by_starts_rshell_after_evidence'
require_text docs/persistence.md 'actions_by_requires_explicit_apply'
require_text docs/persistence.md 'actions_by_requires_external_write'
require_text docs/gdbserver-workflow.md 'payload/bin/gdbserver'
require_text docs/gdbserver-workflow.md 'Static MIPS Caveat'
require_text docs/survey-and-bringup.md 'without changing target tuple compatibility or payload contents'
require_text docs/integration-glinet.md 'best-effort ephemeral runtime cleanup'

printf '%s\n' "stale-ux-text ok"
