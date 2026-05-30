#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

python3 tests/integration/flaky-network-harness.py --artifact-dir "$tmp/flaky-network" >/dev/null
test -s "$tmp/flaky-network/summary.json"
test -s "$tmp/flaky-network/target-mailbox.json"
test -s "$tmp/flaky-network/offline-workflow-mailbox.json"
test -s "$tmp/flaky-network/offline-workflow-tui.json"
test -s "$tmp/flaky-network/offline-workflow-drain.json"
test -s "$tmp/flaky-network/mailbox-lifecycle.json"
test -s "$tmp/flaky-network/restart-persistence.json"
test -s "$tmp/flaky-network/bad-token-phone-home.json"
test -s "$tmp/flaky-network/duplicate-poll.json"
test -s "$tmp/flaky-network/malformed-result-upload.json"
test -s "$tmp/flaky-network/dropped-result-upload.json"
test -s "$tmp/flaky-network/systemd-user-service.json"
test -s "$tmp/flaky-network/target-mismatch-phone-home.json"
test -s "$tmp/flaky-network/command-result.json"
test -s "$tmp/flaky-network/phone-home-attempts.json"
test -s "$tmp/flaky-network/multi-target-isolation.json"
test -s "$tmp/flaky-network/transfer.log"
test -s "$tmp/flaky-network/bridge-events.jsonl"
test -s "$tmp/flaky-network/bridge-interruption.json"
test -s "$tmp/flaky-network/return-offline.json"
test -s "$tmp/flaky-network/artifact-manifest.json"
python3 -m json.tool "$tmp/flaky-network/summary.json" >/dev/null
python3 - "$tmp/flaky-network" <<'PY'
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
mailbox = json.loads((artifact_dir / "target-mailbox.json").read_text(encoding="utf-8"))
workflow = json.loads((artifact_dir / "offline-workflow-mailbox.json").read_text(encoding="utf-8"))
workflow_tui = json.loads((artifact_dir / "offline-workflow-tui.json").read_text(encoding="utf-8"))
workflow_drain = json.loads((artifact_dir / "offline-workflow-drain.json").read_text(encoding="utf-8"))
lifecycle = json.loads((artifact_dir / "mailbox-lifecycle.json").read_text(encoding="utf-8"))
restart = json.loads((artifact_dir / "restart-persistence.json").read_text(encoding="utf-8"))
bad_token = json.loads((artifact_dir / "bad-token-phone-home.json").read_text(encoding="utf-8"))
duplicate = json.loads((artifact_dir / "duplicate-poll.json").read_text(encoding="utf-8"))
malformed_result = json.loads((artifact_dir / "malformed-result-upload.json").read_text(encoding="utf-8"))
dropped_result = json.loads((artifact_dir / "dropped-result-upload.json").read_text(encoding="utf-8"))
systemd = json.loads((artifact_dir / "systemd-user-service.json").read_text(encoding="utf-8"))
mismatch = json.loads((artifact_dir / "target-mismatch-phone-home.json").read_text(encoding="utf-8"))
result = json.loads((artifact_dir / "command-result.json").read_text(encoding="utf-8"))
phone_home = json.loads((artifact_dir / "phone-home-attempts.json").read_text(encoding="utf-8"))
multi_target = json.loads((artifact_dir / "multi-target-isolation.json").read_text(encoding="utf-8"))
transfer = json.loads((artifact_dir / "transfer.log").read_text(encoding="utf-8"))
manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
bridge_events = [
    json.loads(line)
    for line in (artifact_dir / "bridge-events.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
bridge_interruption = json.loads((artifact_dir / "bridge-interruption.json").read_text(encoding="utf-8"))
return_offline = json.loads((artifact_dir / "return-offline.json").read_text(encoding="utf-8"))

assert mailbox["kind"] == "target-mailbox-artifact"
assert mailbox["summary"]["target_mailbox_pending_work_count"] == 2
assert len(mailbox["target_mailbox_records"]) == 2
assert workflow["kind"] == "offline-workflow-mailbox-artifact"
assert workflow["target"]["target_id"] == "target-workflow"
assert workflow["target"]["mailbox_pending_work_count"] == 2
assert workflow["summary"]["target_mailbox_waiting_for_counts"]["target-poll"] == 2
workflow_commands = "\n".join(rec.get("command") or "" for rec in workflow["target_mailbox_records"])
assert "wget -O-" in workflow_commands and "survey.sh" in workflow_commands
assert "busierbox fetch workflow-payload.txt" in workflow_commands
assert workflow_tui["kind"] == "offline-workflow-tui-artifact"
assert workflow_tui["returncode"] == 0
assert workflow_tui["summary"]["target_mailbox_pending_work_count"] == 2
assert workflow_tui["summary"]["target_mailbox_waiting_for_counts"]["target-poll"] == 2
assert "Target mailbox records:" in workflow_tui["stdout"]
assert "target=target-workflow" in workflow_tui["stdout"]
assert "waiting_for=target-poll" in workflow_tui["stdout"]
assert "pending=yes" in workflow_tui["stdout"]
assert "Target detail: target-workflow label=Workflow Target" in workflow_tui["stdout"]
assert "queue-survey-bootstrap" in workflow_tui["stdout"]
assert "queue-staged-fetch" in workflow_tui["stdout"]
assert any(rec["event"] == "workbench_command_queue_inspected" for rec in workflow_tui["workbench_events"])
assert any(rec["event"] == "workbench_target_inspected" for rec in workflow_tui["workbench_events"])
assert workflow_drain["kind"] == "offline-workflow-drain-artifact"
assert workflow_drain["target"]["target_id"] == "target-workflow"
assert workflow_drain["target"]["mailbox_delivered_command_count"] == 2
assert workflow_drain["target"]["mailbox_pending_work_count"] == 0
assert len(set(workflow_drain["delivered_command_ids"])) == 2
assert workflow_drain["http_statuses"] == ["HTTP/1.1 200 OK", "HTTP/1.1 200 OK"]
drained_commands = "\n".join(rec.get("command") or "" for rec in workflow_drain["target_mailbox_records"])
assert "wget -O-" in drained_commands and "survey.sh" in drained_commands
assert "busierbox fetch workflow-payload.txt" in drained_commands
assert all(rec["status"] == "delivered" for rec in workflow_drain["target_mailbox_records"])
assert workflow_drain["summary"]["target_phone_home_status_counts"]["delivered"] >= 2
assert lifecycle["kind"] == "mailbox-lifecycle-artifact"
assert lifecycle["failed_mailbox_record"]["result_status"] == "failed"
assert lifecycle["failed_mailbox_record"]["result_exit_code"] == 23
assert lifecycle["expired_mailbox_record"]["status"] == "expired"
assert lifecycle["expired_mailbox_record"]["expired"] is True
assert lifecycle["expired_mailbox_record"]["pending_work"] is False
assert lifecycle["summary"]["target_mailbox_result_status_counts"]["failed"] == 1
assert lifecycle["summary"]["target_mailbox_expired_counts"]["True"] == 1
assert restart["kind"] == "restart-persistence-artifact"
assert restart["before_start"]["target_mailbox_pending_work_count"] == 1
assert restart["second_mailbox_record"]["status"] == "delivered"
assert restart["after_restart"]["target_phone_home_status_counts"]["delivered"] >= 2
assert bad_token["kind"] == "bad-token-phone-home-artifact"
assert bad_token["mailbox_record"]["status"] == "queued"
assert bad_token["summary"]["target_phone_home_http_status_counts"]["403"] == 1
assert bad_token["phone_home_records"][0]["reason"] == "invalid token"
assert duplicate["kind"] == "duplicate-poll-artifact"
assert duplicate["http_status"] == "HTTP/1.1 204 No Content"
assert duplicate["mailbox_record"]["status"] == "delivered"
assert duplicate["mailbox_record"]["delivered_without_result"] is True
assert duplicate["target"]["mailbox_pending_work_count"] == 0
assert any(rec["status"] == "no-command" and rec["successful"] is True for rec in duplicate["phone_home_records"])
assert malformed_result["kind"] == "malformed-result-upload-artifact"
assert malformed_result["http_status"] == "HTTP/1.1 400 Bad Request"
assert malformed_result["mailbox_record"]["status"] == "delivered"
assert malformed_result["mailbox_record"]["delivered_without_result"] is True
assert malformed_result["target"]["mailbox_result_received_command_count"] == 0
assert any("invalid command result JSON" in rec["reason"] and rec["failed"] is True for rec in malformed_result["phone_home_records"])
assert malformed_result["result_upload_events"]
assert dropped_result["kind"] == "dropped-result-upload-artifact"
assert dropped_result["http_status"] == "HTTP/1.1 400 Bad Request"
assert dropped_result["mailbox_record"]["status"] == "delivered"
assert dropped_result["mailbox_record"]["delivered_without_result"] is True
assert dropped_result["target"]["mailbox_result_received_command_count"] == 0
assert any(rec["status"] == "rejected" and rec["failed"] is True and rec["http_status"] == "400" and rec["reason"] == "truncated request body" for rec in dropped_result["phone_home_records"])
assert dropped_result["result_upload_events"]
assert systemd["kind"] == "systemd-user-service-artifact"
assert systemd["unit_name"] == "busierbox-flaky.service"
systemd_by_action = {rec["action"]: rec for rec in systemd["commands"]}
assert "Description=BusierBox Operator Daemon" in systemd_by_action["print"]["stdout"]
assert "--daemon --daemon-service file-service --daemon-service command-queue" in systemd_by_action["print"]["stdout"]
assert "would write" in systemd_by_action["install"]["stdout"]
for action in ("start", "stop", "restart", "status"):
    assert systemd_by_action[action]["stdout"].strip() == f"systemctl --user {action} busierbox-flaky.service"
assert any(rec["event"] == "systemd_user_unit_printed" for rec in systemd["events"])
assert any(rec["event"] == "systemd_user_unit_install_dry_run" for rec in systemd["events"])
for action in ("start", "stop", "restart", "status"):
    assert any(rec["event"] == "systemd_user_action_dry_run" and (rec["details"] or {}).get("action") == action for rec in systemd["events"])
assert all((rec["details"] or {}).get("headless_command") for rec in systemd["events"])
assert mismatch["kind"] == "target-mismatch-phone-home-artifact"
assert mismatch["mailbox_record"]["status"] == "delivered"
assert mismatch["phone_home_records"][0]["failed"] is True
assert "command result target mismatch" in mismatch["phone_home_records"][0]["reason"]
assert result["kind"] == "command-result-artifact"
assert result["status"] == "result-received"
assert result["result_status"] == "completed"
assert result["target_last_seen_via"] == "command-queue:command_queue_result"
assert phone_home["kind"] == "phone-home-attempts-artifact"
assert phone_home["summary"]["target_phone_home_status_counts"]["result-received"] >= 1
assert phone_home["summary"]["target_phone_home_failed_counts"]["True"] >= 1
assert phone_home["summary"]["target_phone_home_anonymous_counts"]["True"] >= 1
assert any(rec["pending_reason"] == "queued work requires a target identity" for rec in phone_home["target_phone_home_records"])
assert multi_target["kind"] == "multi-target-isolation-artifact"
assert multi_target["alpha_target"]["target_id"] == "target-alpha"
assert multi_target["bravo_target"]["target_id"] == "target-bravo"
assert multi_target["alpha_mailbox_record"]["status"] == "result-received"
assert multi_target["alpha_mailbox_record"]["target_id"] == "target-alpha"
assert multi_target["bravo_mailbox_record"]["status"] == "queued"
assert multi_target["bravo_mailbox_record"]["target_id"] == "target-bravo"
assert multi_target["bravo_mailbox_record"]["waiting_for"] == "target-poll"
assert multi_target["bravo_mailbox_record"]["pending_work"] is True
assert multi_target["bravo_target"]["mailbox_pending_work_count"] == 1
assert multi_target["summary"]["target_mailbox_pending_work_count"] == 1
assert multi_target["summary"]["target_mailbox_status_counts"]["result-received"] == 1
assert multi_target["summary"]["target_mailbox_status_counts"]["queued"] == 1
assert len(multi_target["target_mailbox_records_by_target_id"]["target-alpha"]) == 1
assert len(multi_target["target_mailbox_records_by_target_id"]["target-bravo"]) == 1
assert any(rec["status"] == "result-received" and rec["target_id"] == "target-alpha" for rec in multi_target["phone_home_records"])
assert transfer["kind"] == "transfer-log-artifact"
assert transfer["latest_file_transfer_status"] == "truncated"
assert transfer["target"]["latest_file_transfer_status"] == "truncated"
assert transfer["upload_record"]["status"] == "truncated"
assert transfer["upload_record"]["stored_exists"] is True
assert transfer["summary"]["upload_status_counts"]["truncated"] == 1
assert transfer["summary"]["upload_kind_status_counts"]["evidence:truncated"] == 1
assert transfer["summary"]["upload_status_stored_exists_counts"]["truncated:yes"] == 1
assert "uploads_by_status" in transfer["api_indexes"]["uploads"]
assert "targets_by_latest_file_transfer_status" in transfer["api_indexes"]["targets"]
assert any(rec["event"] == "upload_complete" and (rec["details"] or {}).get("status") == "truncated" for rec in transfer["upload_events"])
assert "latest_file_transfer=upload status=truncated" in transfer["status_text"]
assert bridge_events
assert any((rec.get("details") or {}).get("bridge_profile") == "flaky-bridge" for rec in bridge_events)
assert any((rec.get("details") or {}).get("bridge_profile") == "flaky-bad-bridge" for rec in bridge_events)
assert bridge_interruption["kind"] == "bridge-interruption-artifact"
assert bridge_interruption["profile"]["name"] == "flaky-bad-bridge"
assert bridge_interruption["profile"]["has_last_failure"] is True
assert bridge_interruption["profile"]["last_failure_reason"]
assert bridge_interruption["target"]["latest_bridge_status"] == "error"
assert bridge_interruption["target"]["latest_bridge_profile"] == "flaky-bad-bridge"
assert bridge_interruption["target"]["latest_bridge_failure_reason"] == bridge_interruption["profile"]["last_failure_reason"]
assert bridge_interruption["summary"]["bridge_profile_has_last_failure_counts"]["True"] == 1
assert bridge_interruption["summary"]["target_latest_bridge_status_counts"]["error"] == 1
assert "bridge_profiles_by_has_last_failure" in bridge_interruption["api_indexes"]["bridge_profiles"]
assert "targets_by_latest_bridge_status" in bridge_interruption["api_indexes"]["targets"]
assert bridge_interruption["bridge_error_events"]
assert return_offline["kind"] == "return-offline-artifact"
assert return_offline["targets"]["target-alpha"]["connectivity_state"] == "offline"
assert return_offline["targets"]["target-bravo"]["connectivity_state"] == "offline"
assert return_offline["targets"]["target-bravo"]["mailbox_pending_work_count"] == 1
assert return_offline["summary"]["target_connectivity_state_counts"]["offline"] >= 2
assert return_offline["summary"]["target_mailbox_pending_work_count"] >= 1
assert any(rec["target_id"] == "target-bravo" and rec["pending_work"] is True and rec["target_connectivity_state"] == "offline" for rec in return_offline["mailbox_records"])
assert "state=offline" in return_offline["status_text"]
assert "targets_by_connectivity_state" in return_offline["api_indexes"]["targets"]
assert "target_mailbox_records_by_target_connectivity_state" in return_offline["api_indexes"]["target_mailbox_records"]
manifest_names = {item["name"] for item in manifest["artifacts"]}
for name in (
    "target-mailbox.json",
    "offline-workflow-mailbox.json",
    "offline-workflow-tui.json",
    "offline-workflow-drain.json",
    "mailbox-lifecycle.json",
    "restart-persistence.json",
    "bad-token-phone-home.json",
    "duplicate-poll.json",
    "malformed-result-upload.json",
    "dropped-result-upload.json",
    "systemd-user-service.json",
    "target-mismatch-phone-home.json",
    "command-result.json",
    "phone-home-attempts.json",
    "multi-target-isolation.json",
    "transfer.log",
    "bridge-events.jsonl",
    "bridge-interruption.json",
    "return-offline.json",
    "summary.json",
):
    assert name in manifest_names, name
PY
printf '%s\n' "flaky-network-harness ok"
