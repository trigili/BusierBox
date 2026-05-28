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
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); compat=d["recommendation_compatibility"]; assert compat["label"] == "exact"; assert "arch inferred mipsel" in compat["reasons"]; assert d["recommendation"]["compatibility"] == compat'
printf '%s\n' "$bringup_json" | python3 -c 'import json,os,sys; d=json.load(sys.stdin); run_id=os.path.basename(d["run_dir"]); assert run_id.count("-") >= 2; assert d["remote_dir"].endswith(run_id)'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["recommended_target_preset_summary"]; c=p["compatibility"]; e=p["evidence"]; assert p["valid"] is True; assert p["source"] == d["recommended_target_preset"]; assert p["name"] == "smoke-bringup"; assert p["arch"] == "mipsel"; assert p["libc"] == "musl"; assert p["kernel_floor"] == "4.x"; assert p["confidence"]["arch"] == "high"; assert c["label"] == "exact"; assert "arch inferred from survey evidence" in c["reasons"]; assert "payload/runtime compatibility is scored separately" in c["note"]; assert e["machine"] == "mipsel"; assert e["recommendations"]["libc_guess"] == "musl"; assert p["notes"]'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; by=d["next_command_records_by_side"]; svc=d["next_command_records_by_service"]; purpose=d["next_command_records_by_purpose"]; by_side_service=d["next_command_records_by_side_service"]; by_service_purpose=d["next_command_records_by_service_purpose"]; files=d["run_files"]; fs=d["run_file_summary"]; assert d["status"] == "pass"; assert d["recommended_target_preset"].endswith("smoke-bringup.json"); assert d["staged_fetch_command"]; assert "./busierbox reality-test --json" in d["next_target_commands"]; assert d["safety_boundary"]["network_autorun"] is False; assert d["safety_boundary"]["target_must_run_fetch"] is True; assert d["safety_boundary"]["hidden_control_channel"] is False; assert any(r["command"] == d["staged_fetch_command"] and r["side"] == "target" and r["service"] == "file-service" and r["network"] is True and r["requires_explicit_target_action"] is True and r["executes_operator_supplied_commands"] is False for r in d["next_target_command_records"]); assert all(r["executes_on_target"] is False for r in d["next_operator_command_records"]); assert s["operator_count"] == len(d["next_operator_command_records"]); assert s["target_count"] == len(d["next_target_command_records"]); assert len(d["next_command_records"]) == s["operator_count"] + s["target_count"]; assert by["operator"] == d["next_operator_command_records"]; assert by["target"] == d["next_target_command_records"]; assert len(svc["file-service"]) >= 2; assert svc["survey"][0]["command"] == "./busierbox survey --json"; assert svc["reality-test"][0]["command"] == "./busierbox reality-test --json"; assert purpose["explicitly fetch operator-staged artifact or config"][0]["command"] == d["staged_fetch_command"]; assert by_side_service["target:file-service"][-1]["command"] == d["staged_fetch_command"]; assert by_side_service["operator:file-service"][0]["starts_listener"] is True; assert by_service_purpose["file-service:explicitly fetch operator-staged artifact or config"][0]["command"] == d["staged_fetch_command"]; assert by_service_purpose["reality-test:run active local capability probes"][0]["command"] == "./busierbox reality-test --json"; assert s["target_network_count"] == 1; assert s["target_executes_operator_supplied_commands_count"] == 0; assert s["operator_executes_on_target_count"] == 0; assert s["all_target_commands_require_explicit_action"] is True; assert s["all_operator_commands_require_explicit_action"] is True; assert s["any_operator_command_executes_on_target"] is False; assert s["any_target_command_executes_operator_supplied_commands"] is False; assert files["survey_json"]["exists"] is True; assert files["recommendation_json"]["readable"] is True; assert files["recommended_config"]["size"] > 0; assert files["recommended_target_preset"]["path"] == d["recommended_target_preset"]; assert files["recommended_target_preset"]["exists"] is True; assert fs["exists_count"] >= 4; assert fs["total_count"] == len(files); assert fs["total_size"] >= files["recommended_config"]["size"]'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; by_stage=d["next_command_records_by_stage_kind"]; by_source=d["next_command_records_by_source_path"]; assert rec["command"] == d["staged_fetch_command"]; assert rec["stage_kind"] == "config"; assert rec["source_path"] == d["recommended_config"]; assert rec["request_name"] == d["staged_request_name"]; assert rec["compatibility"]["label"] == ""; assert by_stage["config"][0]["command"] == d["staged_fetch_command"]; assert by_source[d["recommended_config"]][0]["request_name"] == d["staged_request_name"]; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); api=d["api_collections"]; files=d["run_file_records"]; assert d["command_record_summary"]["total_count"] == len(d["next_command_records"]); assert api["next_command_records"]["count"] == len(d["next_command_records"]); assert api["next_command_records"]["primary_key"] == "command"; assert "next_command_records_by_request" in api["next_command_records"]["indexes"]; assert api["next_command_records"]["summary_key"] == "command_record_summary.total_count"; assert api["next_command_records"]["count_summary_key"] == "command_record_summary.total_count"; assert api["run_file_records"]["count"] == len(files); assert api["run_file_records"]["primary_key"] == "name"; assert "run_files_by_exists" in api["run_file_records"]["indexes"]; assert "run_files_by_name" in api["run_file_records"]["indexes"]; assert "run_files_by_path" in api["run_file_records"]["indexes"]; assert api["run_file_records"]["summary_key"] == "run_file_summary.total_count"; assert api["run_file_records"]["count_summary_key"] == "run_file_summary.total_count"; assert len(files) == d["run_file_summary"]["total_count"]; assert d["run_files_by_name"]["recommended_config"]["path"] == d["recommended_config"]; assert d["run_files_by_path"][d["recommended_config"]]["name"] == "recommended_config"; assert d["run_files_by_expected_kind"]["dir"][0]["name"] == "run_dir"; assert d["run_files_by_exists"]["yes"]'
test -f local/presets/targets/smoke-bringup.json
rm -f local/presets/targets/smoke-bringup.json
release_tmp=$(mktemp -d "${TMPDIR:-/tmp}/busierbox-bringup-release.XXXXXX")
mkdir -p "$release_tmp/scripts" "$release_tmp/bin"
printf '%s\n' "fake artifact" >"$release_tmp/bin/busierbox-mipsel-full"
cat >"$release_tmp/release.json" <<'JSON'
{
  "schema": 1,
  "release_name": "bringup-smoke",
  "layout": {
    "devices": {},
    "tuples": {}
  },
  "artifacts": []
}
JSON
cat >"$release_tmp/release-index.json" <<'JSON'
{
  "schema": 1,
  "release_name": "bringup-smoke",
  "devices": {},
  "tuples": {},
  "artifacts": [
    {
      "artifact": "bin/busierbox-mipsel-full",
      "tuple_artifact": "bin/busierbox-mipsel-full",
      "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
      "payload_preset": "default",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "size": 14,
      "tools": ["sh", "gdbserver"],
      "features": ["reverse-ssh"],
      "compatibility": {"schema": 1, "label": "likely", "reasons": ["arch exact", "libc inferred musl"]},
      "tool_provider_status": {"gdbserver": {"schema": 1, "overall": "found", "search_paths": []}},
      "doom_wads": [{"filename": "doom.wad", "size": 9, "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]
    }
  ]
}
JSON
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
    "selected": {
        "artifact_path": str(root / "bin" / "busierbox-mipsel-full"),
        "tool_provider_status": {
            "gdbserver": {
                "schema": 1,
                "overall": "found",
                "search_paths": []
            }
        },
        "doom_wads": [
            {
                "filename": "doom.wad",
                "size": 9,
                "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            }
        ],
        "tuple_summary": {
            "reverse_access": {
                "session_policy": "reconnect",
                "session_policy_valid": True,
                "session_policy_summary": {
                    "retry_scope": "pre-connect+post-disconnect",
                    "reconnect_after_disconnect": True,
                    "fresh_session_on_reconnect": True,
                    "session_resume_supported": False
                }
            },
            "command_queue": {
                "enabled": "no",
                "default_enabled": False,
                "daemon_stop_supported": True,
                "executes_commands": False
            }
        }
    },
    "compatibility": {"label": "likely", "reasons": ["arch exact", "libc inferred musl"]},
}))
PY
chmod +x "$release_tmp/scripts/release-find"
cat >"$release_tmp/scripts/release-self-test" <<'PY'
#!/usr/bin/env python3
import json
import sys
if "--json" not in sys.argv:
    print("release-self-test ok")
else:
    print(json.dumps({
        "schema": 1,
        "status": "pass",
        "release_name": "bringup-smoke",
        "checked_artifact_count": 1,
        "release_tuple_count": 1,
        "release_device_count": 0,
        "command_queue_enabled_count": 0,
        "command_queue_token_required_count": 1,
        "command_queue_token_configured_count": 0,
        "command_queue_execution_supported_count": 0,
        "command_queue_operator_supplied_command_execution_count": 0,
    }))
PY
chmod +x "$release_tmp/scripts/release-self-test"
cat >"$release_tmp/reality.json" <<'JSON'
{"schema":1,"checks":[
  {"name":"runtime_root_executable","type":"capability","status":"pass","ok":true,"available":true,"skipped":false,"detail":"ok"},
  {"name":"tmp_noexec","type":"constraint","status":"pass","ok":true,"detected":true,"skipped":false,"detail":"detected"}
],"checks_by_name":{"runtime_root_executable":[0],"tmp_noexec":[1]},"checks_by_status":{"pass":[0,1],"fail":[],"skipped":[]},"checks_by_type":{"capability":[0],"operator":[],"constraint":[1]},"api_collections":{"checks":{"name":"checks","count":2,"count_summary_key":"summary.check_count","summary_key":"summary.check_count","indexes":["checks_by_name","checks_by_status","checks_by_type"]}},"summary":{"check_count":2,"pass":2,"fail":0,"skipped":0,"capability_pass":1,"capability_fail":0,"operator_pass":0,"operator_fail":0,"operator_skipped":0,"constraints":{"tmp_noexec":true,"rootfs_read_only":false,"procfs_partial":false}}}
JSON
release_json=$(scripts/busierbox-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --reality-json "$release_tmp/reality.json" --release-dir "$release_tmp" --max-compatibility likely --configure-trailer --stage-recommended-artifact --json)
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); files=d["run_files"]; reality=d["reality_summary"]; release_self=d["release_self_test_summary"]; providers=d["selected_tool_provider_status"]; wads=d["selected_doom_wads"]; summary=d["selected_artifact_summary"]; reverse=summary["reverse_access"]; queue=summary["command_queue"]; api=reality["api_collections"]["checks"]; assert d["compatibility"]["label"] == "likely"; assert d["max_compatibility"] == "likely"; assert d["selected_artifact"].endswith("busierbox-mipsel-full"); assert d["release_self_test_json"]; assert release_self["valid"] is True; assert release_self["status"] == "pass"; assert release_self["release_name"] == "bringup-smoke"; assert release_self["command_queue_enabled_count"] == 0; assert release_self["command_queue_token_required_count"] == 1; assert release_self["command_queue_token_configured_count"] == 0; assert release_self["command_queue_execution_supported_count"] == 0; assert release_self["command_queue_operator_supplied_command_execution_count"] == 0; assert providers["gdbserver"]["overall"] == "found"; assert wads[0]["filename"] == "doom.wad"; assert wads[0]["size"] == 9; assert reverse["session_policy"] == "reconnect"; assert reverse["session_policy_summary"]["fresh_session_on_reconnect"] is True; assert reverse["session_policy_summary"]["session_resume_supported"] is False; assert queue["enabled"] == "no"; assert queue["daemon_stop_supported"] is True; assert queue["executes_commands"] is False; assert d["reality_json"]; assert reality["check_count"] == 2; assert reality["checks_by_name"]["tmp_noexec"] == [1]; assert reality["checks_by_type"]["constraint"] == [1]; assert reality["checks_by_status"]["pass"] == [0,1]; assert reality["constraints"]["tmp_noexec"] is True; assert api["count"] == 2; assert api["count_summary_key"] == "summary.check_count"; assert api["summary_key"] == "summary.check_count"; assert "artifact-config set" in d["generated_trailer_override_command"]; assert d["recommendation"]["config"]["BB_RUNTIME_MODE"] == "extract"; assert d["recommendation"]["facts"]["reality"]["tmp_noexec_detected"] is True; assert any("reality-test detected /tmp noexec" in w for w in d["recommendation"]["warnings"]); assert files["release_find_json"]["exists"] is True; assert files["release_self_test_json"]["exists"] is True; assert files["selected_artifact"]["path"] == d["selected_artifact"]; assert files["selected_artifact"]["exists"] is True; assert files["reality_json"]["exists"] is True'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); compat=d["recommendation_compatibility"]; assert compat["label"] == "likely"; assert "/tmp noexec constraint" in compat["reasons"]; assert "reality-test data applied" in compat["reasons"]; assert d["recommendation"]["compatibility"] == compat'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; assert rec["stage_kind"] == "release-artifact"; assert rec["source_path"] == d["selected_artifact"]; assert rec["selected_artifact"] == d["selected_artifact"]; assert rec["compatibility"]["label"] == "likely"; assert rec["compatibility"]["reasons"] == ["arch exact", "libc inferred musl"]; assert d["next_command_records_by_stage_kind"]["release-artifact"][0]["command"] == d["staged_fetch_command"]; assert d["next_command_records_by_source_path"][d["selected_artifact"]][0]["request_name"] == d["staged_request_name"]; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); api=d["api_collections"]; detail=d["selected_artifact_detail_summary"]; providers=d["selected_tool_provider_status_records"]; wads=d["selected_doom_wad_records"]; assert detail["tool_provider_status_count"] == len(providers) == 1; assert detail["tool_provider_overall_counts"]["found"] == 1; assert d["selected_tool_provider_status_by_tool"]["gdbserver"][0]["overall"] == "found"; assert d["selected_tool_provider_status_by_overall"]["found"][0]["tool"] == "gdbserver"; assert api["selected_tool_provider_status_records"]["count"] == 1; assert api["selected_tool_provider_status_records"]["primary_key"] == "tool"; assert api["selected_tool_provider_status_records"]["count_summary_key"] == "selected_artifact_detail_summary.tool_provider_status_count"; assert "selected_tool_provider_status_by_tool" in api["selected_tool_provider_status_records"]["indexes"]; assert detail["doom_wad_count"] == len(wads) == 1; assert detail["doom_wad_filename_count"] == 1; assert d["selected_doom_wads_by_filename"]["doom.wad"][0]["size"] == 9; assert d["selected_doom_wads_by_sha256"][wads[0]["sha256"]][0]["filename"] == "doom.wad"; assert api["selected_doom_wad_records"]["primary_key"] == "filename"; assert api["selected_doom_wad_records"]["summary_key"] == "selected_artifact_detail_summary.doom_wad_count"; assert api["selected_doom_wad_records"]["count_summary_key"] == "selected_artifact_detail_summary.doom_wad_count"'
printf '%s\n' "$release_json" | python3 -c 'import json,sys,pathlib; d=json.load(sys.stdin); out=pathlib.Path(d["run_dir"]) / "staged-artifact.out"; text=out.read_text(encoding="utf-8"); assert "release-artifact" in text; assert "release=bin/busierbox-mipsel-full" in text; assert "compatibility=likely" in text'
rm -rf "$release_tmp"
release_repo_tmp=$(mktemp -d "${TMPDIR:-/tmp}/busierbox-bringup-release-repo.XXXXXX")
release_repo_bundle="$release_repo_tmp/releases/repo-one"
mkdir -p "$release_repo_bundle/bin"
printf '%s\n' "repo artifact" >"$release_repo_bundle/bin/busierbox-mipsel-survey-full"
cat >"$release_repo_bundle/release.json" <<'JSON'
{
  "schema": 1,
  "release_name": "repo-one",
  "layout": {
    "devices": {},
    "tuples": {}
  },
  "artifacts": []
}
JSON
cat >"$release_repo_bundle/release-index.json" <<'JSON'
{
  "schema": 1,
  "release_name": "repo-one",
  "devices": {},
  "tuples": {
    "by-tuple/mipsel/musl/4.x/mips32r2-24kc": {
      "tuple": {
        "arch": "mipsel",
        "libc": "musl",
        "kernel_floor": "4.x",
        "cpu": "mips32r2-24kc",
        "abi": "default"
      },
      "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-mipsel-survey-full"]
    }
  },
  "artifacts": [
    {
      "artifact": "bin/busierbox-mipsel-survey-full",
      "tuple_artifact": "bin/busierbox-mipsel-survey-full",
      "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
      "tuple": {
        "arch": "mipsel",
        "libc": "musl",
        "kernel_floor": "4.x",
        "cpu": "mips32r2-24kc",
        "abi": "default"
      },
      "payload_preset": "survey-core",
      "runtime_mode": "extract",
      "reverse_access": {"transport": "ssh", "session_policy": "single"},
      "command_queue": {"enabled": "no", "executes_commands": false},
      "sha256": "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd",
      "size": 14,
      "tools": ["sh"],
      "compatibility": {"schema": 1, "label": "exact", "reasons": ["survey repo match"]}
    }
  ]
}
JSON
cat >"$release_repo_bundle/release-self-test.json" <<'JSON'
{
  "schema": 1,
  "status": "pass",
  "release_name": "repo-one",
  "checked_artifact_count": 1,
  "release_tuple_count": 1,
  "release_device_count": 0,
  "command_queue_enabled_count": 0,
  "command_queue_token_required_count": 1,
  "command_queue_token_configured_count": 0,
  "command_queue_execution_supported_count": 0,
  "command_queue_operator_supplied_command_execution_count": 0
}
JSON
repo_release_json=$(scripts/busierbox-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --release-dir "$release_repo_tmp/releases" --stage-recommended-artifact --json)
printf '%s\n' "$repo_release_json" | python3 -c 'import json,sys,pathlib; d=json.load(sys.stdin); files=d["run_files"]; summary=d["selected_artifact_summary"]; assert d["selected_artifact"].endswith("busierbox-mipsel-survey-full"); assert d["compatibility"]["label"] == "exact"; assert d["compatibility"]["reasons"] == ["survey repo match"]; assert summary["command_queue"]["enabled"] == "no"; assert summary["reverse_access"]["transport"] == "ssh"; assert d["release_self_test_summary"]["release_name"] == "repo-one"; assert files["release_self_test_json"]["exists"] is True; assert files["release_find_json"]["exists"] is True; assert pathlib.Path(d["run_dir"], "staged-artifact.out").read_text(encoding="utf-8").find("busierbox fetch busierbox-mipsel-survey-full") >= 0'
printf '%s\n' "$repo_release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; assert rec["stage_kind"] == "release-artifact"; assert rec["source_path"] == d["selected_artifact"]; assert rec["compatibility"]["label"] == "exact"; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
rm -rf "$release_repo_tmp"
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
grep -q 'recovery install --method rc-local --action evidence-push --dry-run' "$script"
grep -q 'recovery install --method rc-local --action evidence-then-rshell --apply' "$script"
grep -q 'recovery install --method rc-local --action dmesg-push --dry-run' "$script"
grep -q 'recovery uninstall --method rc-local --apply' "$script"
grep -q 'recovery-fakeroot-status.json' "$script"
grep -q 'recovery-evidence-status.json' "$script"
grep -q 'recovery-evidence-rshell-status.json' "$script"
grep -q 'recovery-dmesg-status.json' "$script"
grep -q 'executes_operator_supplied_command\\":false' "$script"
grep -q 'collects_dmesg\\":true' "$script"
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
