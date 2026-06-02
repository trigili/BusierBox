#!/bin/sh
# Local-only checks for the opt-in GL.iNet integration harness.
set -eu

script=${1:-scripts/lib/integration-glinet}
server=${2:-scripts/grit-console}

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
scripts/grit-bringup --help 2>&1 | grep -q 'Guided target bring-up flow'
scripts/grit-bringup --help 2>&1 | grep -q -- '--reality-json PATH'
scripts/grit-bringup --help 2>&1 | grep -q -- '--max-compatibility LABEL'
scripts/grit-bringup --help 2>&1 | grep -q 'does not start scripts/grit-console'
scripts/grit-bringup --help 2>&1 | grep -q 'does not install persistence'
scripts/grit-bringup --help 2>&1 | grep -q 'integration-glinet is the regression harness'
scripts/grit-bringup --host root@192.0.2.1 --dry-run >/dev/null
scripts/grit-bringup --host root@192.0.2.1 --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json >/dev/null
bringup_out=$(scripts/grit-bringup --host root@192.0.2.1 --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --target-preset glinet-mt7621-openwrt-musl)
recommended_conf=$(printf '%s\n' "$bringup_out" | sed -n 's/^bringup: recommended config: //p')
grep -q '^GRIT_TARGET_PRESET=glinet-mt7621-openwrt-musl$' "$recommended_conf"
rm -f local/presets/targets/smoke-bringup.json
bringup_json=$(scripts/grit-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --write-target-preset smoke-bringup --stage-recommended-artifact --operator-host 198.51.100.9 --target-id bringup-alpha --target-label "Bringup Router" --target-alias lab-bringup --configure-trailer --json)
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); compat=d["recommendation_compatibility"]; assert compat["label"] == "exact"; assert "arch inferred mipsel" in compat["reasons"]; assert d["recommendation"]["compatibility"] == compat'
printf '%s\n' "$bringup_json" | python3 -c 'import json,os,sys; d=json.load(sys.stdin); run_id=os.path.basename(d["run_dir"]); assert run_id.count("-") >= 2; assert d["remote_dir"].endswith(run_id)'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); ctx=d["target_context"]; s=d["command_record_summary"]; rec=d["next_command_records_by_request"][d["staged_request_name"]]; assert ctx["target_id"] == "bringup-alpha"; assert ctx["target_label"] == "Bringup Router"; assert "lab-bringup" in ctx["target_aliases"]; assert "--target-id bringup-alpha" in d["staged_fetch_command"]; assert "--target-label" in d["staged_fetch_command"]; assert "--target-alias lab-bringup" in d["staged_fetch_command"]; assert rec["target_id"] == "bringup-alpha"; assert rec["target_label"] == "Bringup Router"; assert "lab-bringup" in rec["target_aliases"]; assert d["next_command_records_by_target_id"]["bringup-alpha"] == d["next_target_command_records"]; assert d["next_command_records_by_target_label"]["Bringup Router"] == d["next_target_command_records"]; assert d["next_command_records_by_target_alias"]["lab-bringup"] == d["next_target_command_records"]; assert s["target_id_counts"]["bringup-alpha"] == len(d["next_target_command_records"]); assert s["target_label_counts"]["Bringup Router"] == len(d["next_target_command_records"]); assert "next_command_records_by_target_id" in d["api_collections"]["next_command_records"]["indexes"]; assert "next_command_records_by_target_label" in d["api_collections"]["next_command_records"]["indexes"]; assert "next_command_records_by_target_alias" in d["api_collections"]["next_command_records"]["indexes"]'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["recommended_target_preset_summary"]; c=p["compatibility"]; e=p["evidence"]; assert p["valid"] is True; assert p["source"] == d["recommended_target_preset"]; assert p["name"] == "smoke-bringup"; assert p["arch"] == "mipsel"; assert p["libc"] == "musl"; assert p["kernel_floor"] == "4.x"; assert p["confidence"]["arch"] == "high"; assert c["label"] == "exact"; assert "arch inferred from survey evidence" in c["reasons"]; assert "payload/runtime compatibility is scored separately" in c["note"]; assert e["machine"] == "mipsel"; assert e["recommendations"]["libc_guess"] == "musl"; assert p["notes"]'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; by=d["next_command_records_by_side"]; svc=d["next_command_records_by_service"]; purpose=d["next_command_records_by_purpose"]; by_side_service=d["next_command_records_by_side_service"]; by_service_purpose=d["next_command_records_by_service_purpose"]; by_network=d["next_command_records_by_network"]; by_target_action=d["next_command_records_by_requires_explicit_target_action"]; by_operator_action=d["next_command_records_by_requires_explicit_operator_action"]; by_exec_cmd=d["next_command_records_by_executes_operator_supplied_commands"]; by_exec_target=d["next_command_records_by_executes_on_target"]; files=d["run_files"]; fs=d["run_file_summary"]; assert d["status"] == "pass"; assert d["recommended_target_preset"].endswith("smoke-bringup.json"); assert d["staged_fetch_command"]; assert "./grit reality-test --json" in d["next_target_commands"]; assert d["safety_boundary"]["network_autorun"] is False; assert d["safety_boundary"]["target_must_run_fetch"] is True; assert d["safety_boundary"]["hidden_control_channel"] is False; assert any(r["command"] == d["staged_fetch_command"] and r["side"] == "target" and r["service"] == "file-service" and r["network"] is True and r["requires_explicit_target_action"] is True and r["executes_operator_supplied_commands"] is False for r in d["next_target_command_records"]); assert all(r["executes_on_target"] is False for r in d["next_operator_command_records"]); assert s["operator_count"] == len(d["next_operator_command_records"]); assert s["target_count"] == len(d["next_target_command_records"]); assert len(d["next_command_records"]) == s["operator_count"] + s["target_count"]; assert by["operator"] == d["next_operator_command_records"]; assert by["target"] == d["next_target_command_records"]; assert len(svc["file-service"]) >= 2; assert svc["survey"][0]["command"] == "./grit survey --json"; assert svc["reality-test"][0]["command"] == "./grit reality-test --json"; assert purpose["explicitly fetch operator-staged artifact or config"][0]["command"] == d["staged_fetch_command"]; assert by_side_service["target:file-service"][-1]["command"] == d["staged_fetch_command"]; assert by_side_service["operator:file-service"][0]["starts_listener"] is True; assert by_service_purpose["file-service:explicitly fetch operator-staged artifact or config"][0]["command"] == d["staged_fetch_command"]; assert by_service_purpose["reality-test:run active local capability probes"][0]["command"] == "./grit reality-test --json"; assert by_network["true"][0]["command"] == d["staged_fetch_command"]; assert len(by_network["false"]) >= 2; assert len(by_target_action["true"]) == len(d["next_target_command_records"]); assert len(by_operator_action["true"]) == len(d["next_operator_command_records"]); assert len(by_exec_cmd["false"]) == len(d["next_target_command_records"]); assert len(by_exec_target["false"]) == len(d["next_operator_command_records"]); assert s["target_network_count"] == 1; assert s["target_executes_operator_supplied_commands_count"] == 0; assert s["operator_executes_on_target_count"] == 0; assert s["all_target_commands_require_explicit_action"] is True; assert s["all_operator_commands_require_explicit_action"] is True; assert s["any_operator_command_executes_on_target"] is False; assert s["any_target_command_executes_operator_supplied_commands"] is False; assert files["survey_json"]["exists"] is True; assert files["recommendation_json"]["readable"] is True; assert files["recommended_config"]["size"] > 0; assert files["recommended_target_preset"]["path"] == d["recommended_target_preset"]; assert files["recommended_target_preset"]["exists"] is True; assert fs["exists_count"] >= 4; assert fs["total_count"] == len(files); assert fs["total_size"] >= files["recommended_config"]["size"]; assert fs["expected_kind_mismatch_count"] == 0; assert fs["expected_kind_counts"]["file"] >= 1; assert fs["expected_kind_exists_counts"]["dir:yes"] == 1; assert d["run_files_by_writable"]["yes"]; assert d["run_files_by_expected_kind_mismatch"]["no"]'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; assert s["side_counts"]["operator"] == s["operator_count"]; assert s["side_counts"]["target"] == s["target_count"]; assert s["service_counts"]["file-service"] >= 2; assert s["service_counts"]["survey"] == 1; assert s["network_counts"]["true"] == 1; assert s["network_counts"]["false"] >= 2; assert s["requires_explicit_target_action_counts"]["true"] == len(d["next_target_command_records"]); assert s["requires_explicit_operator_action_counts"]["true"] == len(d["next_operator_command_records"]); assert s["executes_operator_supplied_commands_counts"]["false"] == len(d["next_target_command_records"]); assert s["executes_on_target_counts"]["false"] == len(d["next_operator_command_records"])'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; by_stage=d["next_command_records_by_stage_kind"]; by_source=d["next_command_records_by_source_path"]; assert rec["command"] == d["staged_fetch_command"]; assert rec["stage_kind"] == "config"; assert rec["source_path"] == d["recommended_config"]; assert rec["request_name"] == d["staged_request_name"]; assert rec["compatibility"]["label"] == ""; assert by_stage["config"][0]["command"] == d["staged_fetch_command"]; assert by_source[d["recommended_config"]][0]["request_name"] == d["staged_request_name"]; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); api=d["api_collections"]; meta=d["api"]; resources=d["api_resources"]; by_name=d["api_resources_by_name"]; by_records=d["api_resources_by_records_key"]; by_summary=d["api_resources_by_summary_key"]; files=d["run_file_records"]; assert meta["resource_count"] == len(resources); assert meta["resources_key"] == "api_resources"; assert meta["collections_key"] == "api_collections"; assert d["command_record_summary"]["total_count"] == len(d["next_command_records"]); assert api["next_command_records"]["count"] == len(d["next_command_records"]); assert api["next_command_records"]["primary_key"] == "command"; assert "next_command_records_by_request" in api["next_command_records"]["indexes"]; assert "next_command_records_by_network" in api["next_command_records"]["indexes"]; assert "next_command_records_by_executes_operator_supplied_commands" in api["next_command_records"]["indexes"]; assert "next_command_records_by_executes_on_target" in api["next_command_records"]["indexes"]; assert api["next_command_records"]["summary_key"] == "command_record_summary.total_count"; assert api["next_command_records"]["count_summary_key"] == "command_record_summary.total_count"; assert by_name["next_command_records"]["records_key"] == "next_command_records"; assert by_records["next_command_records"][0]["collection_key"] == "api_collections.next_command_records"; assert by_summary["command_record_summary.total_count"][0]["name"] == "next_command_records"; assert api["run_file_records"]["count"] == len(files); assert api["run_file_records"]["primary_key"] == "name"; assert "run_files_by_exists" in api["run_file_records"]["indexes"]; assert "run_files_by_name" in api["run_file_records"]["indexes"]; assert "run_files_by_path" in api["run_file_records"]["indexes"]; assert "run_files_by_writable" in api["run_file_records"]["indexes"]; assert "run_files_by_expected_kind_exists" in api["run_file_records"]["indexes"]; assert "run_files_by_expected_kind_mismatch" in api["run_file_records"]["indexes"]; assert api["run_file_records"]["summary_key"] == "run_file_summary.total_count"; assert api["run_file_records"]["count_summary_key"] == "run_file_summary.total_count"; assert by_name["run_file_records"]["records_key"] == "run_file_records"; assert len(files) == d["run_file_summary"]["total_count"]; assert d["run_files_by_name"]["recommended_config"]["path"] == d["recommended_config"]; assert d["run_files_by_path"][d["recommended_config"]]["name"] == "recommended_config"; assert d["run_files_by_expected_kind"]["dir"][0]["name"] == "run_dir"; assert d["run_files_by_exists"]["yes"]; assert d["run_files_by_expected_kind_exists"]["dir:yes"][0]["name"] == "run_dir"; assert d["run_files_by_expected_kind_mismatch"]["yes"] == []'
printf '%s\n' "$bringup_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); steps=d["bringup_flow_steps"]; by_key=d["bringup_flow_steps_by_key"]; summary=d["bringup_flow_summary"]; api=d["api_collections"]["bringup_flow_steps"]; by_name=d["api_resources_by_name"]; assert len(steps) == 10; assert [s["ordinal"] for s in steps] == list(range(1, 11)); assert summary["step_count"] == 10; assert summary["required_step_count"] == 4; assert summary["required_pending_count"] == 0; assert summary["status_counts"]["complete"] >= 5; assert by_key["transfer_survey_artifact"]["status"] == "complete"; assert by_key["run_survey"]["evidence_exists"] is True; assert by_key["run_reality_test"]["status"] == "skipped"; assert by_key["generate_recommended_config"]["status"] == "complete"; assert by_key["generate_target_preset"]["status"] == "complete"; assert by_key["stage_artifact_or_config"]["status"] == "complete"; assert by_key["print_next_commands"]["command"] == "summary.next_operator_commands and summary.next_target_commands"; assert by_key["run_integration_safe_checks"]["optional"] is True; assert d["bringup_flow_steps_by_status"]["complete"]; assert d["bringup_flow_steps_by_optional"]["yes"]; assert d["bringup_flow_steps_by_evidence_exists"]["yes"]; assert api["count"] == 10; assert api["primary_key"] == "key"; assert api["summary_key"] == "bringup_flow_summary.step_count"; assert "bringup_flow_steps_by_key" in api["indexes"]; assert "bringup_flow_steps_by_status" in api["indexes"]; assert "bringup_flow_steps_by_evidence_exists" in api["indexes"]; assert by_name["bringup_flow_steps"]["records_key"] == "bringup_flow_steps"'
test -f local/presets/targets/smoke-bringup.json
rm -f local/presets/targets/smoke-bringup.json
release_tmp=$(mktemp -d "${TMPDIR:-/tmp}/grit-bringup-release.XXXXXX")
mkdir -p "$release_tmp/scripts/lib" "$release_tmp/bin"
printf '%s\n' "fake artifact" >"$release_tmp/bin/grit-mipsel-full"
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
      "artifact": "bin/grit-mipsel-full",
      "tuple_artifact": "bin/grit-mipsel-full",
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
cat >"$release_tmp/scripts/lib/release-find" <<'PY'
#!/usr/bin/env python3
import json
import pathlib
import sys
root = pathlib.Path(__file__).resolve().parents[2]
if "--json" not in sys.argv or "--survey-json" not in sys.argv:
    raise SystemExit(2)
if "--reality-json" not in sys.argv:
    raise SystemExit("missing --reality-json")
if "--max-compatibility" not in sys.argv:
    raise SystemExit("missing --max-compatibility")
print(json.dumps({
    "selected": {
        "artifact_path": str(root / "bin" / "grit-mipsel-full"),
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
chmod +x "$release_tmp/scripts/lib/release-find"
cat >"$release_tmp/scripts/lib/release-self-test" <<'PY'
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
chmod +x "$release_tmp/scripts/lib/release-self-test"
cat >"$release_tmp/reality.json" <<'JSON'
{"schema":1,"checks":[
  {"name":"runtime_root_executable","type":"capability","status":"pass","ok":true,"available":true,"skipped":false,"detail":"ok"},
  {"name":"tmp_noexec","type":"constraint","status":"pass","ok":true,"detected":true,"skipped":false,"detail":"detected"}
],"checks_by_name":{"runtime_root_executable":[0],"tmp_noexec":[1]},"checks_by_status":{"pass":[0,1],"fail":[],"skipped":[]},"checks_by_type":{"capability":[0],"operator":[],"constraint":[1]},"checks_by_skipped":{"yes":[],"no":[0,1]},"checks_by_available":{"yes":[0],"no":[],"unknown":[1]},"checks_by_detected":{"yes":[1],"no":[],"unknown":[0]},"api_collections":{"checks":{"name":"checks","count":2,"count_summary_key":"summary.check_count","summary_key":"summary.check_count","indexes":["checks_by_name","checks_by_status","checks_by_type","checks_by_skipped","checks_by_available","checks_by_detected"]}},"summary":{"check_count":2,"pass":2,"fail":0,"skipped":0,"capability_pass":1,"capability_fail":0,"operator_pass":0,"operator_fail":0,"operator_skipped":0,"constraints":{"tmp_noexec":true,"rootfs_read_only":false,"procfs_partial":false}}}
JSON
release_json=$(scripts/grit-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --reality-json "$release_tmp/reality.json" --release-dir "$release_tmp" --max-compatibility likely --configure-trailer --stage-recommended-artifact --json)
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); files=d["run_files"]; reality=d["reality_summary"]; release_self=d["release_self_test_summary"]; providers=d["selected_tool_provider_status"]; wads=d["selected_doom_wads"]; summary=d["selected_artifact_summary"]; reverse=summary["reverse_access"]; queue=summary["command_queue"]; api=reality["api_collections"]["checks"]; assert d["compatibility"]["label"] == "likely"; assert d["max_compatibility"] == "likely"; assert d["release_selection_source"] == "bundle-helper"; assert "scripts/lib/release-find" in d["release_selection_command"]; assert "--reality-json" in d["release_selection_command"]; assert d["selected_artifact"].endswith("grit-mipsel-full"); assert d["release_self_test_json"]; assert release_self["valid"] is True; assert release_self["status"] == "pass"; assert release_self["release_name"] == "bringup-smoke"; assert release_self["command_queue_enabled_count"] == 0; assert release_self["command_queue_token_required_count"] == 1; assert release_self["command_queue_token_configured_count"] == 0; assert release_self["command_queue_execution_supported_count"] == 0; assert release_self["command_queue_operator_supplied_command_execution_count"] == 0; assert providers["gdbserver"]["overall"] == "found"; assert wads[0]["filename"] == "doom.wad"; assert wads[0]["size"] == 9; assert reverse["session_policy"] == "reconnect"; assert reverse["session_policy_summary"]["fresh_session_on_reconnect"] is True; assert reverse["session_policy_summary"]["session_resume_supported"] is False; assert queue["enabled"] == "no"; assert queue["daemon_stop_supported"] is True; assert queue["executes_commands"] is False; assert d["reality_json"]; assert reality["check_count"] == 2; assert reality["checks_by_name"]["tmp_noexec"] == [1]; assert reality["checks_by_type"]["constraint"] == [1]; assert reality["checks_by_status"]["pass"] == [0,1]; assert reality["checks_by_skipped"]["no"] == [0,1]; assert reality["checks_by_available"]["yes"] == [0]; assert reality["checks_by_detected"]["yes"] == [1]; assert reality["constraints"]["tmp_noexec"] is True; assert api["count"] == 2; assert api["count_summary_key"] == "summary.check_count"; assert api["summary_key"] == "summary.check_count"; assert "checks_by_available" in api["indexes"]; assert "checks_by_detected" in api["indexes"]; assert "artifact-config set" in d["generated_trailer_override_command"]; assert d["recommendation"]["config"]["GRIT_RUNTIME_MODE"] == "extract"; assert d["recommendation"]["facts"]["reality"]["tmp_noexec_detected"] is True; assert any("reality-test detected /tmp noexec" in w for w in d["recommendation"]["warnings"]); assert files["release_find_json"]["exists"] is True; assert files["release_self_test_json"]["exists"] is True; assert files["selected_artifact"]["path"] == d["selected_artifact"]; assert files["selected_artifact"]["exists"] is True; assert files["reality_json"]["exists"] is True'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); compat=d["recommendation_compatibility"]; assert compat["label"] == "likely"; assert "/tmp noexec constraint" in compat["reasons"]; assert "reality-test data applied" in compat["reasons"]; assert d["recommendation"]["compatibility"] == compat'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; assert rec["stage_kind"] == "release-artifact"; assert rec["source_path"] == d["selected_artifact"]; assert rec["selected_artifact"] == d["selected_artifact"]; assert rec["compatibility"]["label"] == "likely"; assert rec["compatibility"]["reasons"] == ["arch exact", "libc inferred musl"]; assert d["next_command_records_by_stage_kind"]["release-artifact"][0]["command"] == d["staged_fetch_command"]; assert d["next_command_records_by_source_path"][d["selected_artifact"]][0]["request_name"] == d["staged_request_name"]; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; assert s["stage_kind_counts"]["release-artifact"] == 1; assert s["compatibility_label_counts"]["likely"] == 1'
printf '%s\n' "$release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); api=d["api_collections"]; by_name=d["api_resources_by_name"]; by_summary=d["api_resources_by_summary_key"]; detail=d["selected_artifact_detail_summary"]; providers=d["selected_tool_provider_status_records"]; wads=d["selected_doom_wad_records"]; assert detail["tool_provider_status_count"] == len(providers) == 1; assert detail["tool_provider_overall_counts"]["found"] == 1; assert d["selected_tool_provider_status_by_tool"]["gdbserver"][0]["overall"] == "found"; assert d["selected_tool_provider_status_by_overall"]["found"][0]["tool"] == "gdbserver"; assert api["selected_tool_provider_status_records"]["count"] == 1; assert api["selected_tool_provider_status_records"]["primary_key"] == "tool"; assert api["selected_tool_provider_status_records"]["count_summary_key"] == "selected_artifact_detail_summary.tool_provider_status_count"; assert "selected_tool_provider_status_by_tool" in api["selected_tool_provider_status_records"]["indexes"]; assert by_name["selected_tool_provider_status_records"]["records_key"] == "selected_tool_provider_status_records"; assert by_summary["selected_artifact_detail_summary.tool_provider_status_count"][0]["name"] == "selected_tool_provider_status_records"; assert detail["doom_wad_count"] == len(wads) == 1; assert detail["doom_wad_filename_count"] == 1; assert d["selected_doom_wads_by_filename"]["doom.wad"][0]["size"] == 9; assert d["selected_doom_wads_by_sha256"][wads[0]["sha256"]][0]["filename"] == "doom.wad"; assert api["selected_doom_wad_records"]["primary_key"] == "filename"; assert api["selected_doom_wad_records"]["summary_key"] == "selected_artifact_detail_summary.doom_wad_count"; assert api["selected_doom_wad_records"]["count_summary_key"] == "selected_artifact_detail_summary.doom_wad_count"; assert by_name["selected_doom_wad_records"]["records_key"] == "selected_doom_wad_records"'
printf '%s\n' "$release_json" | python3 -c 'import json,sys,pathlib; d=json.load(sys.stdin); out=pathlib.Path(d["run_dir"]) / "staged-artifact.out"; text=out.read_text(encoding="utf-8"); assert "release-artifact" in text; assert "release=bin/grit-mipsel-full" in text; assert "compatibility=likely" in text'
rm -rf "$release_tmp"
release_repo_tmp=$(mktemp -d "${TMPDIR:-/tmp}/grit-bringup-release-repo.XXXXXX")
release_repo_bundle="$release_repo_tmp/releases/repo-one"
mkdir -p "$release_repo_bundle/bin"
printf '%s\n' "repo artifact" >"$release_repo_bundle/bin/grit-mipsel-survey-full"
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
      "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-survey-full"]
    }
  },
  "artifacts": [
    {
      "artifact": "bin/grit-mipsel-survey-full",
      "tuple_artifact": "bin/grit-mipsel-survey-full",
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
cat >"$release_repo_tmp/reality.json" <<'JSON'
{
  "schema": 1,
  "checks": [
    {"name": "runtime_root_executable", "type": "capability", "status": "pass", "ok": true, "available": true, "skipped": false, "detail": "ok"},
    {"name": "tmp_noexec", "type": "constraint", "status": "pass", "ok": true, "detected": true, "skipped": false, "detail": "detected"}
  ],
  "checks_by_name": {"runtime_root_executable": [0], "tmp_noexec": [1]},
  "summary": {"check_count": 2, "constraints": {"tmp_noexec": true, "rootfs_read_only": false, "procfs_partial": false}}
}
JSON
repo_release_json=$(scripts/grit-bringup --recommend-only --survey-json tests/fixtures/survey/glinet-mt7621.json --reality-json "$release_repo_tmp/reality.json" --release-dir "$release_repo_tmp/releases" --stage-recommended-artifact --json)
printf '%s\n' "$repo_release_json" | python3 -c 'import json,sys,pathlib; d=json.load(sys.stdin); files=d["run_files"]; summary=d["selected_artifact_summary"]; release_find=json.load(open(d["release_find_json"], encoding="utf-8")); assert d["release_selection_source"] == "release-repository"; assert "scripts/lib/find-artifact" in d["release_selection_command"]; assert "--survey-json" in d["release_selection_command"]; assert "--payload-preset" in d["release_selection_command"]; assert "--reality-json" in d["release_selection_command"]; assert d["selected_artifact"].endswith("grit-mipsel-survey-full"); assert d["compatibility"]["label"] == "likely"; assert d["compatibility"]["baseline_label"] == "exact"; assert "survey repo match" in d["compatibility"]["reasons"]; assert "/tmp noexec: avoid /tmp extraction" in d["compatibility"]["reasons"]; assert summary["command_queue"]["enabled"] == "no"; assert summary["reverse_access"]["transport"] == "ssh"; assert d["release_self_test_summary"]["release_name"] == "repo-one"; assert files["release_self_test_json"]["exists"] is True; assert files["release_find_json"]["exists"] is True; assert release_find["filters"]["reality_json"].endswith("reality-test.json"); assert release_find["reality"]["constraints"]["tmp_noexec"] is True; assert release_find["selected"]["compatibility"]["label"] == "exact"; assert release_find["selected"]["effective_compatibility"]["label"] == "likely"; assert release_find["filters_by_name"]["reality_json"]["source"] == "explicit"; assert pathlib.Path(d["run_dir"], "staged-artifact.out").read_text(encoding="utf-8").find("grit fetch grit-mipsel-survey-full") >= 0'
printf '%s\n' "$repo_release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); rec=d["next_command_records_by_request"][d["staged_request_name"]]; by_label=d["next_command_records_by_compatibility_label"]; by_baseline=d["next_command_records_by_compatibility_baseline_label"]; by_source=d["next_command_records_by_compatibility_source"]; assert rec["stage_kind"] == "release-artifact"; assert rec["source_path"] == d["selected_artifact"]; assert rec["compatibility"]["label"] == "likely"; assert rec["compatibility"]["baseline_label"] == "exact"; assert rec["compatibility"]["source"] == "release-index+reality"; assert "/tmp noexec: avoid /tmp extraction" in rec["compatibility"]["reasons"]; assert by_label["likely"][0]["request_name"] == d["staged_request_name"]; assert by_baseline["exact"][0]["request_name"] == d["staged_request_name"]; assert by_source["release-index+reality"][0]["request_name"] == d["staged_request_name"]; assert d["command_record_summary"]["target_staged_fetch_count"] == 1'
printf '%s\n' "$repo_release_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["command_record_summary"]; api=d["api_collections"]["next_command_records"]; assert s["stage_kind_counts"]["release-artifact"] == 1; assert s["compatibility_label_counts"]["likely"] == 1; assert s["compatibility_baseline_label_counts"]["exact"] == 1; assert s["compatibility_source_counts"]["release-index+reality"] == 1; assert "next_command_records_by_compatibility_label" in api["indexes"]; assert "next_command_records_by_compatibility_baseline_label" in api["indexes"]; assert "next_command_records_by_compatibility_source" in api["indexes"]'
rm -rf "$release_repo_tmp"
grep -q 'GRIT_CONFIG="$recommended" make package' scripts/grit-bringup
grep -q 'Bringup is a guided onboarding flow' README.md
grep -q 'docs/bringup.md' README.md
grep -q 'docs/payload-presets.md' README.md
test -f docs/bringup.md
test -f docs/payload-presets.md

grep -q 'capture_grit_outputs' "$script"
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
grep -q 'GRIT_OPERATOR_SERVER_HOST=198.51.100.88' "$script"
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
grep -q 'GRIT_RUNTIME_MODE="no-residue"' "$script"
grep -q 'kill -TERM' "$script"
grep -q '.grit-nores' "$script"
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
grep -q "plan recovery install --method cron-reboot --action command --json -- 'grit rshell start'" "$script"
grep -q 'reality-test --json' "$script"
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
grep -q 'reality-test-json.log' "$script"
grep -q 'clean-dry-run-json.log' "$script"
grep -q 'clean-external-dry-run-json.log' "$script"
grep -q 'clean-external-no-apply.log' "$script"
grep -q 'rshell-status-json.log' "$script"
grep -q 'recovery-status-json.log' "$script"
grep -q 'operator_ssh_port' tests/smoke/rshell-status-json.sh
grep -q 'remote_forward_port' tests/smoke/rshell-status-json.sh

python3 -m py_compile "$script" "$server"
"$server" --help-all | grep -q -- '--script'
"$server" --help-all | grep -q -- '--expect'
"$server" --help-all | grep -q -- '--session-timeout'

printf '%s\n' "integration-glinet-harness ok"
