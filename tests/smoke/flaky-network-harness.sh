#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

python3 tests/integration/flaky-network-harness.py --artifact-dir "$tmp/flaky-network" >/dev/null
test -s "$tmp/flaky-network/summary.json"
python3 -m json.tool "$tmp/flaky-network/summary.json" >/dev/null
printf '%s\n' "flaky-network-harness ok"
