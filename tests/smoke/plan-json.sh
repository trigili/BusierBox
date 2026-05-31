#!/bin/sh
set -eu

artifact=${1:-dist/grit-native-full}
if [ ! -x "$artifact" ] || ! "$artifact" list --plain 2>/dev/null | grep -q '^native plan$'; then
    GRIT_CONFIG=presets/payload/default.conf GRIT_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
fi

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/plan-json.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

cp "$artifact" "$work/grit"
chmod 0755 "$work/grit"
scripts/artifact-config set "$work/grit" \
    GRIT_RUNTIME_ROOT="$work/runtime" \
    GRIT_RUNTIME_MODE=no-residue \
    GRIT_NORESIDUE_LEVEL=aggressive \
    GRIT_OPERATOR_SERVER_HOST=192.0.2.77 \
    GRIT_RSHELL_TRANSPORT=builtin \
    GRIT_RSHELL_SESSION_POLICY=reconnect \
    GRIT_RSHELL_RETRY_COUNT=1 >/dev/null

"$work/grit" plan --json | python3 -m json.tool >/dev/null
"$work/grit" plan extract --json >"$work/extract.json"
"$work/grit" plan rshell --json >"$work/rshell.json"
"$work/grit" plan clean --json >"$work/clean.json"
GRIT_COMMAND_QUEUE_ENABLE=yes GRIT_COMMAND_QUEUE_REQUIRE_TOKEN=no GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS=grit-only "$work/grit" plan command-queue --json >"$work/command-queue.json"
"$work/grit" plan recovery install --method openwrt-procd --action rshell --json >"$work/recovery.json"
"$work/grit" plan recovery install --method rc-local --action evidence-push --root "$work/root" --name grit_recovery --json >"$work/recovery-evidence.json"
"$work/grit" plan recovery install --method rc-local --action evidence-then-rshell --root "$work/root" --name grit_recovery --json >"$work/recovery-evidence-rshell.json"
"$work/grit" plan recovery install --method rc-local --action dmesg-push --root "$work/root" --name grit_recovery --json >"$work/recovery-dmesg.json"
"$work/grit" plan recovery install --method cron-reboot --action command --json -- 'grit rshell start' >"$work/recovery-command.json"
"$work/grit" plan recovery install --method cron-reboot --action command --json -- grit rshell start >"$work/recovery-command-argv.json"
printf '%s\n' '#!/bin/sh' 'echo recovery-script' >"$work/recover.sh"
"$work/grit" plan recovery install --method rc-local --action script --file "$work/recover.sh" --root "$work/root" --name grit_recovery --json >"$work/recovery-script.json"

for json in "$work"/*.json; do
    python3 -m json.tool "$json" >/dev/null
done

python3 - "$work" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
extract = json.loads((root / "extract.json").read_text())
rshell = json.loads((root / "rshell.json").read_text())
clean = json.loads((root / "clean.json").read_text())
command_queue = json.loads((root / "command-queue.json").read_text())
recovery = json.loads((root / "recovery.json").read_text())
evidence = json.loads((root / "recovery-evidence.json").read_text())
evidence_rshell = json.loads((root / "recovery-evidence-rshell.json").read_text())
dmesg = json.loads((root / "recovery-dmesg.json").read_text())
command = json.loads((root / "recovery-command.json").read_text())
command_argv = json.loads((root / "recovery-command-argv.json").read_text())
script = json.loads((root / "recovery-script.json").read_text())

assert extract["command"] == "extract"
assert extract["runtime_root"].endswith("/runtime")
assert extract["runtime_mode"] == "no-residue"
assert extract["noresidue_level"] == "aggressive"
extract_policy = extract["noresidue_policy"]
assert extract_policy["active"] is True
assert extract_policy["level"] == "aggressive"
assert extract_policy["best_effort"] is True
assert extract_policy["aggressive_minimizes_runtime_residue"] is True
assert extract_policy["persistent_target_logs_default"] == "no"
assert extract_policy["stdout_stderr_log_suppression"] == "GRIT_ZERO_ARG_LOG_MODE=none"
assert extract_policy["in_memory_log_guarantee"] is False
assert extract_policy["forensic_no_trace"] is False
assert extract_policy["external_writes_require_explicit_apply"] is True
assert "griTTYkit-owned runtime roots" in extract_policy["cleanup_scope"]
assert "cannot guarantee absence of residue" in extract_policy["guarantee"]
assert extract["config"]["effective_config_source"] == "trailer"
assert extract["config"]["trailer_present"] is True
assert extract["config"]["trailer_valid"] is True
assert any(path.endswith("/runtime") for path in extract["would_create"])

assert rshell["command"] == "rshell"
assert rshell["transport"] == "builtin"
assert rshell["session_policy"] == "reconnect"
assert rshell["session_semantics"]["retry_until_first_connection"] is True
assert rshell["session_semantics"]["stop_after_first_success"] is False
assert rshell["session_semantics"]["reconnect_after_disconnect"] is True
assert rshell["session_semantics"]["persistent_lifecycle"] is False
assert rshell["session_semantics"]["fresh_session_on_reconnect"] is True
assert rshell["session_semantics"]["session_resume_supported"] is False
summary = rshell["session_policy_summary"]
assert summary["valid"] is True
assert summary["errors"] == []
assert summary["retry_scope"] == "pre-connect+post-disconnect"
assert summary["post_disconnect_retry_count"] == "1"
assert summary["stops_after_success"] is False
assert summary["reconnects_after_disconnect"] is True
assert summary["persistent_lifecycle"] is False
assert summary["fresh_session_on_reconnect"] is True
assert summary["session_resume_supported"] is False
assert rshell["retry"]["pre_connect_count"] == "1"
assert rshell["retry"]["post_disconnect_count"] == "1"
assert rshell["retry_timing"]["backoff"] == rshell["retry"]["backoff"]
assert rshell["retry_timing"]["interval_sec"] == rshell["retry"]["interval_sec"]
assert rshell["retry_timing"]["max_interval_sec"] == rshell["retry"]["max_interval_sec"]
assert rshell["retry_timing"]["jitter_pct"] == rshell["retry"]["jitter_pct"]
assert rshell["retry_timing"]["sample_delays_exclude_jitter"] is True
assert rshell["retry_timing"]["sample_delays_sec"] == [5, 5, 5]
assert rshell["operator_host"] == "192.0.2.77"
assert rshell["requires_external_writes"] is False
assert "192.0.2.77" in rshell["would_connect"][0]
assert rshell["no_residue_cleanup"] is True
rshell_policy = rshell["noresidue_policy"]
assert rshell_policy["active"] is True
assert rshell_policy["level"] == "aggressive"
assert rshell_policy["best_effort"] is True
assert rshell_policy["aggressive_minimizes_runtime_residue"] is True
assert rshell_policy["persistent_target_logs_default"] == "no"
assert rshell_policy["stdout_stderr_log_suppression"] == "GRIT_ZERO_ARG_LOG_MODE=none"
assert rshell_policy["in_memory_log_guarantee"] is False
assert rshell_policy["forensic_no_trace"] is False
assert rshell_policy["external_writes_require_explicit_apply"] is True

assert clean["command"] == "clean"
assert clean["runtime_root"].endswith("/runtime")
assert clean["runtime_mode"] == "no-residue"
assert clean["noresidue_level"] == "aggressive"
clean_policy = clean["noresidue_policy"]
assert clean_policy["active"] is True
assert clean_policy["level"] == "aggressive"
assert clean_policy["best_effort"] is True
assert clean_policy["aggressive_minimizes_runtime_residue"] is True
assert clean_policy["persistent_target_logs_default"] == "no"
assert clean_policy["stdout_stderr_log_suppression"] == "GRIT_ZERO_ARG_LOG_MODE=none"
assert clean_policy["in_memory_log_guarantee"] is False
assert clean_policy["forensic_no_trace"] is False
assert clean_policy["external_writes_require_explicit_apply"] is True
assert any(path.endswith("/runtime") for path in clean["would_remove"])

assert command_queue["command"] == "command-queue"
assert command_queue["enabled"] is True
assert command_queue["policy_valid"] is True
assert command_queue["configured_for_polling"] is True
assert command_queue["would_start"] == ["command-queue poll"]
assert command_queue["would_connect"] == ["192.0.2.77:22205"]
assert command_queue["execution_mode"] == "metadata-only"
assert command_queue["metadata_only_default"] is True
assert command_queue["execution_supported"] is False
assert command_queue["daemon_state_file"].endswith("/runtime/run/command-queue-daemon.state")
mode_records = command_queue["mode_records"]
mode_summary = command_queue["mode_summary"]
api_modes = command_queue["api_collections"]["mode_records"]
assert len(mode_records) == 5
assert mode_records[1]["mode"] == "poll"
assert mode_records[1]["planned"] is True
assert mode_records[1]["would_start"] is True
assert mode_records[1]["target_polling_supported"] is True
assert mode_records[1]["delivery_supported"] is False
assert mode_records[1]["result_upload_supported"] is True
assert mode_records[1]["operator_supplied_command_execution"] is False
assert command_queue["mode_records_by_mode"]["poll"] == [1]
assert command_queue["mode_records_by_lifecycle"]["single-poll"] == [1]
assert command_queue["mode_records_by_would_poll_if_configured"]["true"] == [1, 2, 3]
assert command_queue["mode_records_by_planned"]["true"] == [1]
assert command_queue["mode_records_by_target_polling_supported"]["true"] == [1, 2, 3]
assert command_queue["mode_records_by_delivery_supported"]["false"] == [0, 1, 2, 3, 4]
assert command_queue["mode_records_by_result_upload_supported"]["true"] == [0, 1, 2, 3, 4]
assert command_queue["mode_records_by_execution_supported"]["false"] == [0, 1, 2, 3, 4]
assert command_queue["mode_records_by_active_control_channel"]["false"] == [0, 1, 2, 3, 4]
assert command_queue["mode_records_by_operator_supplied_command_execution"]["false"] == [0, 1, 2, 3, 4]
assert mode_summary["mode_count"] == 5
assert mode_summary["planned_mode_count"] == 1
assert mode_summary["target_polling_supported_mode_count"] == 3
assert mode_summary["delivery_supported_mode_count"] == 0
assert mode_summary["result_upload_supported_mode_count"] == 5
assert mode_summary["execution_supported_mode_count"] == 0
assert api_modes["count"] == 5
assert api_modes["summary_key"] == "mode_summary.mode_count"
assert api_modes["count_summary_key"] == "mode_summary.mode_count"
assert api_modes["primary_key"] == "mode"
assert "mode_records_by_planned" in api_modes["indexes"]
assert "mode_records_by_target_polling_supported" in api_modes["indexes"]
assert "mode_records_by_delivery_supported" in api_modes["indexes"]
assert "mode_records_by_result_upload_supported" in api_modes["indexes"]
assert "mode_records_by_operator_supplied_command_execution" in api_modes["indexes"]

assert recovery["command"] == "recovery install"
assert recovery["method"] == "openwrt-procd"
assert recovery["action"] == "rshell"
assert recovery["action_category"] == "reverse-shell"
assert recovery["starts_rshell"] is True
assert recovery["uploads_evidence"] is False
assert recovery["executes_operator_supplied_command"] is False
assert recovery["action_semantics"]["category"] == "reverse-shell"
assert recovery["action_semantics"]["starts_rshell"] is True
assert recovery["action_semantics"]["command_queue_enabled"] is False
assert recovery["action_semantics"]["hidden_control_channel"] is False
assert recovery["action_semantics"]["self_reinstall"] is False
assert recovery["action_semantics"]["survives_factory_reset_claim"] is False
assert recovery["action_semantics"]["requires_explicit_apply"] is True
assert recovery["requires_external_writes"] is True
assert recovery["binary_path"].endswith("/usr/bin/grit_recovery")
assert recovery["generated_command"] == "/usr/bin/grit_recovery rshell start"
assert recovery["generated_command"].endswith("rshell start")

assert evidence["action"] == "evidence-push"
assert evidence["action_category"] == "evidence"
assert evidence["uploads_evidence"] is True
assert evidence["collects_dmesg"] is False
assert evidence["starts_rshell"] is False
assert evidence["starts_rshell_after_evidence"] is False
assert evidence["executes_operator_supplied_command"] is False
assert evidence["action_semantics"]["uploads_evidence"] is True
assert evidence["requires_external_writes"] is False
assert evidence["generated_command"] == "/usr/bin/grit_recovery evidence push --quiet"
assert evidence["would_connect"] == ["192.0.2.77"]

assert evidence_rshell["action"] == "evidence-then-rshell"
assert evidence_rshell["action_category"] == "evidence"
assert evidence_rshell["uploads_evidence"] is True
assert evidence_rshell["starts_rshell"] is True
assert evidence_rshell["starts_rshell_after_evidence"] is True
assert evidence_rshell["action_semantics"]["starts_rshell_after_evidence"] is True
assert "evidence push --quiet" in evidence_rshell["generated_command"]
assert evidence_rshell["generated_command"].endswith("rshell start")
assert evidence_rshell["would_connect"] == ["192.0.2.77"]

assert dmesg["action"] == "dmesg-push"
assert dmesg["action_category"] == "evidence"
assert dmesg["uploads_evidence"] is True
assert dmesg["collects_dmesg"] is True
assert dmesg["starts_rshell"] is False
assert dmesg["action_semantics"]["collects_dmesg"] is True
assert 'dmesg >"$grit_dmesg"' in dmesg["generated_command"]
assert "--dest grit_recovery-dmesg.txt" in dmesg["generated_command"]
assert 'rm -f "$grit_dmesg"' in dmesg["generated_command"]
assert dmesg["would_connect"] == ["192.0.2.77"]

assert command["action"] == "command"
assert command["action_category"] == "command"
assert command["executes_operator_supplied_command"] is True
assert command["action_semantics"]["executes_operator_supplied_command"] is True
assert command["command_queue_enabled"] is False
assert command["hidden_control_channel"] is False
assert command["binary_path"].endswith("/usr/bin/grit_recovery")
assert command["generated_command"] == "grit rshell start"
assert command_argv["action"] == "command"
assert command_argv["generated_command"] == "grit rshell start"

assert script["action"] == "script"
assert script["action_category"] == "script"
assert script["executes_operator_supplied_command"] is True
assert script["action_semantics"]["category"] == "script"
assert script["requires_external_writes"] is False
assert script["script_source_path"].endswith("/recover.sh")
assert script["script_dest_path"].endswith("/root/usr/bin/grit_recovery.recovery.sh")
assert script["generated_command"] == "/usr/bin/grit_recovery.recovery.sh"
assert any(path.endswith("/root/usr/bin/grit_recovery.recovery.sh") for path in script["would_create"])
PY

"$work/grit" plan extract >"$work/extract.txt"
grep -q '^Plan: extract$' "$work/extract.txt"
grep -q '^effective_config_source=trailer$' "$work/extract.txt"
grep -q '^runtime_mode=no-residue$' "$work/extract.txt"
grep -q '^noresidue_level=aggressive$' "$work/extract.txt"
grep -q '^noresidue_policy_active=yes$' "$work/extract.txt"
grep -q '^noresidue_policy_aggressive_minimizes_runtime_residue=yes$' "$work/extract.txt"
grep -q '^noresidue_policy_persistent_target_logs_default=no$' "$work/extract.txt"
grep -q '^noresidue_policy_stdout_stderr_log_suppression=GRIT_ZERO_ARG_LOG_MODE=none$' "$work/extract.txt"
grep -q '^noresidue_policy_in_memory_log_guarantee=no$' "$work/extract.txt"
grep -q '^noresidue_policy_forensic_no_trace=no$' "$work/extract.txt"
grep -q '^noresidue_policy_external_writes_require_explicit_apply=yes$' "$work/extract.txt"
"$work/grit" plan clean >"$work/clean.txt"
grep -q '^runtime_mode=no-residue$' "$work/clean.txt"
grep -q '^noresidue_level=aggressive$' "$work/clean.txt"
grep -q '^noresidue_policy_active=yes$' "$work/clean.txt"
grep -q '^noresidue_policy_aggressive_minimizes_runtime_residue=yes$' "$work/clean.txt"
grep -q '^noresidue_policy_persistent_target_logs_default=no$' "$work/clean.txt"
grep -q '^noresidue_policy_stdout_stderr_log_suppression=GRIT_ZERO_ARG_LOG_MODE=none$' "$work/clean.txt"
grep -q '^noresidue_policy_in_memory_log_guarantee=no$' "$work/clean.txt"
grep -q '^noresidue_policy_forensic_no_trace=no$' "$work/clean.txt"
grep -q '^noresidue_policy_external_writes_require_explicit_apply=yes$' "$work/clean.txt"
"$work/grit" plan rshell >"$work/rshell.txt"
grep -q '^retry_backoff=' "$work/rshell.txt"
grep -q '^retry_interval_sec=' "$work/rshell.txt"
grep -q '^retry_max_interval_sec=' "$work/rshell.txt"
grep -q '^retry_jitter_pct=' "$work/rshell.txt"
grep -q '^retry_delay_attempt_0_sec=' "$work/rshell.txt"
grep -q '^retry_delay_attempt_1_sec=' "$work/rshell.txt"
grep -q '^retry_delay_attempt_2_sec=' "$work/rshell.txt"
"$work/grit" plan recovery install --method rc-local --action script --file "$work/recover.sh" --root "$work/root" --name grit_recovery >"$work/recovery-script.txt"
grep -q "^script_source_path=$work/recover.sh$" "$work/recovery-script.txt"
grep -q "^script_dest_path=$work/root/usr/bin/grit_recovery.recovery.sh$" "$work/recovery-script.txt"
grep -q "  $work/root/usr/bin/grit_recovery.recovery.sh" "$work/recovery-script.txt"
"$work/grit" plan recovery install --method rc-local --action dmesg-push --root "$work/root" --name grit_recovery >"$work/recovery-dmesg.txt"
grep -q '^action=dmesg-push$' "$work/recovery-dmesg.txt"
grep -q '^action_category=evidence$' "$work/recovery-dmesg.txt"
grep -q '^uploads_evidence=yes$' "$work/recovery-dmesg.txt"
grep -q '^collects_dmesg=yes$' "$work/recovery-dmesg.txt"
grep -q '^starts_rshell=no$' "$work/recovery-dmesg.txt"
grep -q '^executes_operator_supplied_command=no$' "$work/recovery-dmesg.txt"
grep -q '^command_queue_enabled=no$' "$work/recovery-dmesg.txt"
grep -q '^hidden_control_channel=no$' "$work/recovery-dmesg.txt"
grep -q 'dmesg >"$grit_dmesg"' "$work/recovery-dmesg.txt"
grep -q -- '--dest grit_recovery-dmesg.txt' "$work/recovery-dmesg.txt"

GRIT_RSHELL_SESSION_POLICY=bogus "$work/grit" plan rshell --json >"$work/rshell-invalid-policy.json"
python3 -m json.tool "$work/rshell-invalid-policy.json" >/dev/null
python3 - "$work/rshell-invalid-policy.json" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
assert data["session_policy"] == "bogus"
assert data["session_policy_valid"] is False
assert "unsupported rshell session policy" in data["session_policy_errors"]
assert "unsupported rshell session policy" in data["session_policy_summary"]["errors"]
assert data["session_semantics"]["session_resume_supported"] is False
PY
GRIT_RSHELL_SESSION_POLICY=bogus "$work/grit" plan rshell >"$work/rshell-invalid-policy.txt"
grep -q '^session_policy_valid=no$' "$work/rshell-invalid-policy.txt"
grep -q '^session_policy_error=unsupported rshell session policy$' "$work/rshell-invalid-policy.txt"

printf '%s\n' "plan-json ok"
