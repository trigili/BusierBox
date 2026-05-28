#!/bin/sh
set -eu

old=${1:-tests/fixtures/integration/old-summary.json}
new=${2:-tests/fixtures/integration/new-summary.json}

chmod +x scripts/integration-report scripts/integration-compare

scripts/integration-report "$new" >local/tmp.integration-report.out
grep -q '^status=partial$' local/tmp.integration-report.out
grep -q '^counts=pass:3 fail:1 skip:0$' local/tmp.integration-report.out
grep -q '^event_log=.*tests/fixtures/integration/new-events.jsonl$' local/tmp.integration-report.out
grep -q '^event_total=3 invalid=0 first=2026-05-26T12:00:00Z latest=2026-05-26T12:00:05Z$' local/tmp.integration-report.out
grep -q '^event_counts=.*service_start:1.*shutdown:1.*upload_complete:1' local/tmp.integration-report.out
grep -q '^event_levels=info:3$' local/tmp.integration-report.out
grep -q '^event_services=file-service:3$' local/tmp.integration-report.out
grep -q '^event_service_events=.*file-service:service_start:1.*file-service:shutdown:1.*file-service:upload_complete:1' local/tmp.integration-report.out
grep -q '^recent_events:$' local/tmp.integration-report.out
grep -q 'file-service:upload_complete' local/tmp.integration-report.out
grep -q '^release_self_test=.*tests/fixtures/integration/new-release-self-test.json$' local/tmp.integration-report.out
grep -q '^release_self_test_status=pass release=fixture-release artifacts=1 tuples=1 devices=1 command_queue_enabled=0 command_queue_token_required=1 command_queue_token_configured=0 command_queue_exec=0 command_queue_operator_exec=0$' local/tmp.integration-report.out
grep -q '^release_self_test_diagnostics=records=3 statuses=pass:3 categories=checksums:1,command_queue:1,compatibility:1$' local/tmp.integration-report.out
grep -q '^release_self_test_diagnostic name=command_queue_safety status=pass category=command_queue count=5$' local/tmp.integration-report.out
grep -q '^recovery_status=reports=1 valid=1 invalid=0 installations=1 evidence_uploads=1 dmesg=1 rshell=0 rshell_after_evidence=0 operator_commands=0 command_queue=0 hidden_channels=0$' local/tmp.integration-report.out
grep -q '^recovery_actions=dmesg-push:1$' local/tmp.integration-report.out
grep -q '^recovery_action_categories=evidence:1$' local/tmp.integration-report.out
grep -q '^  recovery_report case=recovery-fakeroot installed=true installations=1 evidence_uploads=1 dmesg=1 rshell=0$' local/tmp.integration-report.out
grep -q '^reality_tests=reports=1 valid=1 invalid=0 checks=5 pass=3 fail=0 skipped=2 operator_skipped=2$' local/tmp.integration-report.out
grep -q '^reality_test_statuses=pass:3,skipped:2$' local/tmp.integration-report.out
grep -q '^reality_test_types=capability:2,constraint:1,operator:2$' local/tmp.integration-report.out
grep -q '^reality_test_detected_constraints=tmp_noexec:1$' local/tmp.integration-report.out
grep -q '^reality_test_skipped_operator_checks:$' local/tmp.integration-report.out
grep -q '^  survey-core:upload_operator$' local/tmp.integration-report.out
grep -q '^failure_reasons:$' local/tmp.integration-report.out
grep -q 'builtin-core-shell: fail: listener timeout' local/tmp.integration-report.out
grep -q '^Case.*Build.*Transfer.*Run.*Validation.*Cleanup.*Status.*Duration.*Artifact Size.*SHA256.*Log' local/tmp.integration-report.out
grep -q 'survey-core.*pass.*pass.*pass.*pass.*pass.*pass.*13.250s.*120.*bbbbbbbbbbbb' local/tmp.integration-report.out
grep -q 'builtin-core-shell.*pass.*pass.*fail.*pending.*pass.*fail.*7.500s' local/tmp.integration-report.out
grep -q 'listener timeout' local/tmp.integration-report.out

scripts/integration-report "$new" --json | python3 -m json.tool >/dev/null
scripts/integration-report "$new" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d["operator_events"]; r=d["release_self_test"]; p=d["recovery_status"]; reality=d["reality_tests"]; assert e["total_count"] == 3; assert e["invalid_count"] == 0; assert e["first_event_at"] == "2026-05-26T12:00:00Z"; assert e["latest_event_at"] == "2026-05-26T12:00:05Z"; assert e["event_counts"]["upload_complete"] == 1; assert e["level_counts"]["info"] == 3; assert e["service_counts"]["file-service"] == 3; assert e["service_event_counts"]["file-service:upload_complete"] == 1; assert e["remote_counts"]["192.0.2.10:40100"] == 1; assert e["session_counts"]["20260526-file-service"] == 1; assert e["recent"][-1]["event"] == "shutdown"; assert r["valid"] is True; assert r["status"] == "pass"; assert r["release_name"] == "fixture-release"; assert r["command_queue_enabled_count"] == 0; assert r["command_queue_token_required_count"] == 1; assert r["command_queue_token_configured_count"] == 0; assert r["command_queue_execution_supported_count"] == 0; assert r["command_queue_operator_supplied_command_execution_count"] == 0; assert r["diagnostic_record_count"] == 3; assert r["diagnostic_status_counts"]["pass"] == 3; assert r["diagnostic_category_counts"]["command_queue"] == 1; assert r["diagnostic_records_by_name"]["command_queue_safety"]["status"] == "pass"; assert p["report_count"] == 1; assert p["valid_count"] == 1; assert p["totals"]["evidence_upload_count"] == 1; assert p["totals"]["dmesg_action_count"] == 1; assert p["totals"]["command_queue_enabled_count"] == 0; assert p["totals"]["hidden_control_channel_count"] == 0; assert p["action_counts"]["dmesg-push"] == 1; assert p["category_counts"]["evidence"] == 1; assert p["reports"][0]["installations"][0]["action"] == "dmesg-push"; assert reality["report_count"] == 1; assert reality["totals"]["check_count"] == 5; assert reality["status_counts"]["skipped"] == 2; assert reality["type_counts"]["operator"] == 2; assert reality["detected_constraints"]["tmp_noexec"] == 1; assert reality["skipped_operator_checks"][0]["name"] == "upload_operator"'

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
