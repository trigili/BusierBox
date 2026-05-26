#!/bin/sh
set -eu

old=${1:-tests/fixtures/integration/old-summary.json}
new=${2:-tests/fixtures/integration/new-summary.json}

chmod +x scripts/integration-report scripts/integration-compare

scripts/integration-report "$new" >local/tmp.integration-report.out
grep -q '^status=partial$' local/tmp.integration-report.out
grep -q '^counts=pass:2 fail:1 skip:0$' local/tmp.integration-report.out
grep -q '^failure_reasons:$' local/tmp.integration-report.out
grep -q 'builtin-core-shell: fail: listener timeout' local/tmp.integration-report.out
grep -q 'survey-core' local/tmp.integration-report.out
grep -q 'listener timeout' local/tmp.integration-report.out

scripts/integration-report "$new" --json | python3 -m json.tool >/dev/null

scripts/integration-compare "$old" "$new" >local/tmp.integration-compare.out
grep -q '^old_status=pass$' local/tmp.integration-compare.out
grep -q '^new_status=partial$' local/tmp.integration-compare.out
grep -q 'builtin-core-shell.*skip.*fail.*status changed' local/tmp.integration-compare.out
grep -q 'survey-core.*artifact changed' local/tmp.integration-compare.out
grep -q 'ssh-operator.*missing.*pass' local/tmp.integration-compare.out

scripts/integration-compare "$old" "$new" --json | python3 -m json.tool >/dev/null

rm -f local/tmp.integration-report.out local/tmp.integration-compare.out
printf '%s\n' "integration-report ok"
