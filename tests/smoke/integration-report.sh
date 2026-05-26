#!/bin/sh
set -eu

old=${1:-tests/fixtures/integration/old-summary.json}
new=${2:-tests/fixtures/integration/new-summary.json}

chmod +x scripts/integration-report scripts/integration-compare

scripts/integration-report "$new" >local/tmp.integration-report.out
grep -q '^status=partial$' local/tmp.integration-report.out
grep -q '^counts=pass:2 fail:1 skip:0$' local/tmp.integration-report.out
grep -q '^event_log=.*tests/fixtures/integration/new-events.jsonl$' local/tmp.integration-report.out
grep -q '^event_counts=.*service_start:1.*shutdown:1.*upload_complete:1' local/tmp.integration-report.out
grep -q '^recent_events:$' local/tmp.integration-report.out
grep -q 'file-service:upload_complete' local/tmp.integration-report.out
grep -q '^failure_reasons:$' local/tmp.integration-report.out
grep -q 'builtin-core-shell: fail: listener timeout' local/tmp.integration-report.out
grep -q '^Case.*Build.*Transfer.*Run.*Validation.*Cleanup.*Status.*Duration.*Artifact Size.*SHA256.*Log' local/tmp.integration-report.out
grep -q 'survey-core.*pass.*pass.*pass.*pass.*pass.*pass.*13.250s.*120.*bbbbbbbbbbbb' local/tmp.integration-report.out
grep -q 'builtin-core-shell.*pass.*pass.*fail.*pending.*pass.*fail.*7.500s' local/tmp.integration-report.out
grep -q 'listener timeout' local/tmp.integration-report.out

scripts/integration-report "$new" --json | python3 -m json.tool >/dev/null
scripts/integration-report "$new" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d["operator_events"]; assert e["total_count"] == 3; assert e["event_counts"]["upload_complete"] == 1; assert e["recent"][-1]["event"] == "shutdown"'

scripts/integration-compare "$old" "$new" >local/tmp.integration-compare.out
grep -q '^old_status=pass$' local/tmp.integration-compare.out
grep -q '^new_status=partial$' local/tmp.integration-compare.out
grep -q 'builtin-core-shell.*skip.*fail.*regression.*listener timeout' local/tmp.integration-compare.out
grep -q 'survey-core.*artifact_changed.*20.*3.25.*artifact changed.*size changed.*duration changed' local/tmp.integration-compare.out
grep -q 'ssh-operator.*missing.*pass.*new_case' local/tmp.integration-compare.out

scripts/integration-compare "$old" "$new" --json | python3 -m json.tool >/dev/null
scripts/integration-compare "$old" "$new" --json | grep -q '"regressions"'
scripts/integration-compare "$old" "$new" --json | grep -q '"duration_delta_sec": 3.25'

rm -f local/tmp.integration-report.out local/tmp.integration-compare.out
printf '%s\n' "integration-report ok"
