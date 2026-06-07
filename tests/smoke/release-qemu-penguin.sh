#!/bin/sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)

grep -q 'GRIT_RELEASE_QEMU_PENGUIN_BUILD=1' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'GRIT_RELEASE_QEMU_PENGUIN_RUN=1' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'penguin-qemu-plan' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'release-find' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'ArchId.yaml' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'KernelVersionFinder.yaml' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'RELEASE_TARGETS=' "$ROOT/tests/integration/release-qemu-penguin"
grep -q 'RELEASE_PAYLOAD_PRESETS=' "$ROOT/tests/integration/release-qemu-penguin"
grep -q '^test-release-qemu-penguin:' "$ROOT/Makefile"

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "skip: python3 release-qemu-penguin smoke unavailable"
    exit 0
fi

ARTIFACT_ROOT="${TMPDIR:-/tmp}/grit-release-qemu-penguin-smoke" \
PENGUIN_LIMIT=3 \
"$ROOT/tests/integration/release-qemu-penguin" >"${TMPDIR:-/tmp}/grit-release-qemu-penguin-smoke.out"

grep -q 'release-qemu-penguin plan ok' "${TMPDIR:-/tmp}/grit-release-qemu-penguin-smoke.out"
grep -q 'PLAN full release build skipped' "${TMPDIR:-/tmp}/grit-release-qemu-penguin-smoke.out"

printf '%s\n' "release-qemu-penguin smoke ok"
