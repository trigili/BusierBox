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
for case_name in survey-core trailer-runtime-override recovery-fakeroot no-residue-cleanup default-extract-help builtin-core-shell zero-arg-builtin socat-rescue ssh-operator; do
    printf '%s\n' "$cases" | grep -qx "$case_name" || {
        printf '%s\n' "integration-glinet-harness: missing case $case_name" >&2
        exit 1
    }
done

"$script" --dry-run --all-safe --operator-host 127.0.0.1 >/dev/null
scripts/busierbox-bringup --help 2>&1 | grep -q 'Guided target bring-up flow'
scripts/busierbox-bringup --help 2>&1 | grep -q -- '--reality-json PATH'
scripts/busierbox-bringup --help 2>&1 | grep -q -- '--max-compatibility LABEL'
scripts/busierbox-bringup --help 2>&1 | grep -q 'does not start scripts/busierbox-server'
scripts/busierbox-bringup --help 2>&1 | grep -q 'does not install persistence'
scripts/busierbox-bringup --help 2>&1 | grep -q 'integration-glinet is the regression harness'
scripts/busierbox-bringup --host root@192.0.2.1 --dry-run >/dev/null
scripts/busierbox-bringup --host root@192.0.2.1 --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json >/dev/null
bringup_out=$(scripts/busierbox-bringup --host root@192.0.2.1 --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --target-preset glinet-mt7621-openwrt-musl)
recommended_conf=$(printf '%s\n' "$bringup_out" | sed -n 's/^bringup: recommended config: //p')
grep -q '^BB_TARGET_PRESET=glinet-mt7621-openwrt-musl$' "$recommended_conf"
rm -f local/presets/targets/smoke-bringup.json
bringup_json=$(scripts/busierbox-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --write-target-preset smoke-bringup --stage-recommended-artifact --operator-host 198.51.100.9 --configure-trailer --json)
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; by=d["next_command_records_by_side"]; svc=d["next_command_records_by_service"]; purpose=d["next_command_records_by_purpose"]; assert d["status"] == "pass"; assert d["recommended_target_preset"].endswith("smoke-bringup.json"); assert d["staged_fetch_command"]; assert "./busierbox reality-test --json" in d["next_target_commands"]; assert d["safety_boundary"]["network_autorun"] is False; assert d["safety_boundary"]["target_must_run_fetch"] is True; assert d["safety_boundary"]["hidden_control_channel"] is False; assert any(r["command"] == d["staged_fetch_command"] and r["side"] == "target" and r["service"] == "file-service" and r["network"] is True and r["requires_explicit_target_action"] is True and r["executes_operator_supplied_commands"] is False for r in d["next_target_command_records"]); assert all(r["executes_on_target"] is False for r in d["next_operator_command_records"]); assert s["operator_count"] == len(d["next_operator_command_records"]); assert s["target_count"] == len(d["next_target_command_records"]); assert len(d["next_command_records"]) == s["operator_count"] + s["target_count"]; assert by["operator"] == d["next_operator_command_records"]; assert by["target"] == d["next_target_command_records"]; assert len(svc["file-service"]) >= 2; assert svc["survey"][0]["command"] == "./busierbox survey --json"; assert svc["reality-test"][0]["command"] == "./busierbox reality-test --json"; assert purpose["explicitly fetch operator-staged artifact or config"][0]["command"] == d["staged_fetch_command"]; assert s["target_network_count"] == 1; assert s["target_executes_operator_supplied_commands_count"] == 0; assert s["operator_executes_on_target_count"] == 0'
test -f local/presets/targets/smoke-bringup.json
rm -f local/presets/targets/smoke-bringup.json
release_tmp=$(mktemp -d "${TMPDIR:-/tmp}/busierbox-bringup-release.XXXXXX")
mkdir -p "$release_tmp/scripts" "$release_tmp/bin"
printf '%s\n' "fake artifact" >"$release_tmp/bin/busierbox-mipsel-full"
cat >"$release_tmp/scripts/release-find" <<'PY'
#!/usr/bin/env python3
import json
import pathlib
import sys
root = pathlib.Path(__file__).resolve().parents[1]
if "--json" not in sys.argv or "--survey-json" not in sys.argv:
    raise SystemExit(2)
if "--reality-json" not in sys.argv:
    raise SystemExit("missing --reality-json")
if "--max-compatibility" not in sys.argv:
    raise SystemExit("missing --max-compatibility")
print(json.dumps({
    "selected": {"artifact_path": str(root / "bin" / "busierbox-mipsel-full")},
    "compatibility": {"label": "likely", "reasons": ["arch exact", "libc inferred musl"]},
}))
PY
chmod +x "$release_tmp/scripts/release-find"
cat >"$release_tmp/reality.json" <<'JSON'
{"schema":1,"checks":[
  {"name":"runtime_root_executable","type":"capability","status":"pass","ok":true,"available":true,"skipped":false,"detail":"ok"},
  {"name":"tmp_noexec","type":"constraint","status":"pass","ok":true,"detected":true,"skipped":false,"detail":"detected"}
]}
JSON
release_json=$(scripts/busierbox-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --reality-json "$release_tmp/reality.json" --release-dir "$release_tmp" --max-compatibility likely --configure-trailer --json)
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["compatibility"]["label"] == "likely"; assert d["max_compatibility"] == "likely"; assert d["selected_artifact"].endswith("busierbox-mipsel-full"); assert d["reality_json"]; assert "artifact-config set" in d["generated_trailer_override_command"]; assert d["recommendation"]["config"]["BB_RUNTIME_MODE"] == "extract"; assert d["recommendation"]["facts"]["reality"]["tmp_noexec_detected"] is True; assert any("reality-test detected /tmp noexec" in w for w in d["recommendation"]["warnings"])'
rm -rf "$release_tmp"
grep -q 'BUSIERBOX_CONFIG="$recommended" make package' scripts/busierbox-bringup
grep -q 'Bringup is a guided onboarding flow' README.md
grep -q 'docs/bringup.md' README.md
grep -q 'docs/payload-presets.md' README.md
test -f docs/bringup.md
test -f docs/payload-presets.md

grep -q 'capture_busierbox_outputs' "$script"
grep -q 'validate_captured_json' "$script"
grep -q 'summarize_cases' "$script"
grep -q 'write_operator_server_config' "$script"
grep -q 'aggregate_operator_events' "$script"
grep -q 'operator-server-config.json' "$script"
grep -q 'operator-events.jsonl' "$script"
grep -q '"operator_event_log"' "$script"
grep -q '"event_log"' "$script"
grep -q '"event_count"' "$script"
grep -q 'apply_case_artifact_overrides' "$script"
grep -q 'artifact-config.log' "$script"
grep -q 'BB_OPERATOR_SERVER_HOST=198.51.100.88' "$script"
grep -q 'case_trailer_runtime_override' "$script"
grep -q 'case_recovery_fakeroot' "$script"
grep -q 'recovery install --method rc-local --action command --dry-run' "$script"
grep -q 'recovery uninstall --method rc-local --apply' "$script"
grep -q 'recovery-fakeroot-status.json' "$script"
grep -q 'case_no_residue_cleanup' "$script"
grep -q 'BB_RUNTIME_MODE="no-residue"' "$script"
grep -q 'kill -TERM' "$script"
grep -q '.busierbox-nores' "$script"
grep -q '"failure_reasons"' "$script"
grep -q '"counts"' "$script"
grep -q 'json.loads(text)' "$script"
grep -q 'manifest --json' "$script"
grep -q 'runtime-config --json' "$script"
grep -q 'cleanup-ledger --json' "$script"
grep -q 'plan --json' "$script"
grep -q 'plan extract --json' "$script"
grep -q 'plan rshell --json' "$script"
grep -q 'plan clean --json' "$script"
grep -q 'plan recovery install --method openwrt-procd --action rshell --json' "$script"
grep -q "plan recovery install --method cron-reboot --action command --json -- 'busierbox rshell start'" "$script"
grep -q 'clean --dry-run' "$script"
grep -q 'clean --dry-run --json' "$script"
grep -q 'clean --dry-run --external --json' "$script"
grep -q 'clean --external' "$script"
grep -q 'rshell status --json' "$script"
grep -q 'recovery status --json' "$script"
grep -q 'runtime-config-json.log' "$script"
grep -q 'plan-json.log' "$script"
grep -q 'plan-extract-json.log' "$script"
grep -q 'plan-rshell-json.log' "$script"
grep -q 'plan-clean-json.log' "$script"
grep -q 'plan-recovery-rshell-json.log' "$script"
grep -q 'plan-recovery-command-json.log' "$script"
grep -q 'clean-dry-run-json.log' "$script"
grep -q 'clean-external-dry-run-json.log' "$script"
grep -q 'clean-external-no-apply.log' "$script"
grep -q 'rshell-status-json.log' "$script"
grep -q 'recovery-status-json.log' "$script"
grep -q 'operator_ssh_port' tests/smoke/rshell-status-json.sh
grep -q 'remote_forward_port' tests/smoke/rshell-status-json.sh

python3 -m py_compile "$script" "$server"
"$server" --help | grep -q -- '--script'
"$server" --help | grep -q -- '--expect'
"$server" --help | grep -q -- '--session-timeout'

printf '%s\n' "integration-glinet-harness ok"
