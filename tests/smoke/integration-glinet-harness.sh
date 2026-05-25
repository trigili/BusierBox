#!/bin/sh
# Local-only checks for the opt-in GL.iNet integration harness.
set -eu

script=${1:-scripts/integration-glinet}
server=${2:-scripts/busierbox-server}

[ -x "$script" ] || {
    printf '%s\n' "integration-glinet-harness: missing executable $script" >&2
    exit 1
}

cases=$("$script" --case list)
for case_name in survey-core default-extract-help builtin-core-shell zero-arg-builtin socat-rescue ssh-operator; do
    printf '%s\n' "$cases" | grep -qx "$case_name" || {
        printf '%s\n' "integration-glinet-harness: missing case $case_name" >&2
        exit 1
    }
done

"$script" --dry-run --all-safe --operator-host 127.0.0.1 >/dev/null
scripts/busierbox-bringup --host root@192.0.2.1 --dry-run >/dev/null

grep -q 'capture_busierbox_outputs' "$script"
grep -q 'manifest --json' "$script"
grep -q 'cleanup-ledger --json' "$script"
grep -q 'clean --dry-run' "$script"
grep -q 'rshell status --json' "$script"

python3 -m py_compile "$script" "$server"
"$server" --help | grep -q -- '--script'
"$server" --help | grep -q -- '--expect'
"$server" --help | grep -q -- '--session-timeout'

printf '%s\n' "integration-glinet-harness ok"
