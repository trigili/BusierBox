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
test -s "$tmp/flaky-network/offline-workflow-drain-tui.json"
test -s "$tmp/flaky-network/mailbox-lifecycle.json"
test -s "$tmp/flaky-network/restart-persistence.json"
test -s "$tmp/flaky-network/bad-token-phone-home.json"
test -s "$tmp/flaky-network/duplicate-poll.json"
test -s "$tmp/flaky-network/malformed-result-upload.json"
test -s "$tmp/flaky-network/dropped-result-upload.json"
test -s "$tmp/flaky-network/systemd-user-service.json"
test -s "$tmp/flaky-network/tui-offline-queue.json"
test -s "$tmp/flaky-network/tui-offline-queue-drain.json"
test -s "$tmp/flaky-network/target-mismatch-phone-home.json"
test -s "$tmp/flaky-network/command-result.json"
test -s "$tmp/flaky-network/phone-home-attempts.json"
test -s "$tmp/flaky-network/multi-target-isolation.json"
test -s "$tmp/flaky-network/transfer.log"
test -s "$tmp/flaky-network/bridge-events.jsonl"
test -s "$tmp/flaky-network/bridge-interruption.json"
test -s "$tmp/flaky-network/return-offline.json"
test -s "$tmp/flaky-network/topology.json"
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
workflow_drain_tui = json.loads((artifact_dir / "offline-workflow-drain-tui.json").read_text(encoding="utf-8"))
lifecycle = json.loads((artifact_dir / "mailbox-lifecycle.json").read_text(encoding="utf-8"))
restart = json.loads((artifact_dir / "restart-persistence.json").read_text(encoding="utf-8"))
bad_token = json.loads((artifact_dir / "bad-token-phone-home.json").read_text(encoding="utf-8"))
duplicate = json.loads((artifact_dir / "duplicate-poll.json").read_text(encoding="utf-8"))
malformed_result = json.loads((artifact_dir / "malformed-result-upload.json").read_text(encoding="utf-8"))
dropped_result = json.loads((artifact_dir / "dropped-result-upload.json").read_text(encoding="utf-8"))
systemd = json.loads((artifact_dir / "systemd-user-service.json").read_text(encoding="utf-8"))
tui_queue = json.loads((artifact_dir / "tui-offline-queue.json").read_text(encoding="utf-8"))
tui_queue_drain = json.loads((artifact_dir / "tui-offline-queue-drain.json").read_text(encoding="utf-8"))
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
topology = json.loads((artifact_dir / "topology.json").read_text(encoding="utf-8"))

assert mailbox["kind"] == "target-mailbox-artifact"
assert mailbox["summary"]["target_mailbox_pending_work_count"] == 2
assert len(mailbox["target_mailbox_records"]) == 2
assert workflow["kind"] == "offline-workflow-mailbox-artifact"
assert workflow["target"]["target_id"] == "target-workflow"
assert workflow["target"]["mailbox_pending_work_count"] == 2
assert workflow["summary"]["target_mailbox_waiting_for_counts"]["target-poll"] == 2
assert any((rec.get("details") or {}).get("action_id") == "queue-probe" for rec in workflow["target_workflow_action_events"])
assert any((rec.get("details") or {}).get("action_id") == "queue-staged-fetch" for rec in workflow["staged_file_workflow_action_events"])
assert any((rec.get("details") or {}).get("queues_offline_work") is True for rec in workflow["staged_file_workflow_action_events"])
workflow_commands = "\n".join(rec.get("command") or "" for rec in workflow["target_mailbox_records"])
assert "wget -O-" in workflow_commands and "probe.sh" in workflow_commands
assert "grit fetch workflow-payload.txt" in workflow_commands
assert workflow_tui["kind"] == "offline-workflow-tui-artifact"
assert workflow_tui["returncode"] == 0
assert workflow_tui["summary"]["target_mailbox_pending_work_count"] == 2
assert workflow_tui["summary"]["target_mailbox_waiting_for_counts"]["target-poll"] == 2
assert "Mailbox  (2 records)" in workflow_tui["stdout"]
assert "target-workflow" in workflow_tui["stdout"]
assert "mailbox pending 2" in workflow_tui["stdout"]
assert "target-poll" in workflow_tui["stdout"]
assert "selected agent: target-workflow (Workflow Target)" in workflow_tui["stdout"]
assert "Queue controls" in workflow_tui["stdout"]
assert any(rec["event"] == "workbench_command_queue_inspected" for rec in workflow_tui["workbench_events"])
assert workflow_drain["kind"] == "offline-workflow-drain-artifact"
assert workflow_drain["target"]["target_id"] == "target-workflow"
assert workflow_drain["target"]["mailbox_delivered_command_count"] == 2
assert workflow_drain["target"]["mailbox_pending_work_count"] == 0
assert workflow_drain["target"]["last_seen"]
assert workflow_drain["target"]["last_seen_via"] == "command-queue:command_queue_poll"
assert workflow_drain["target"]["next_expected_poll"]
assert workflow_drain["target"]["poll_overdue"] is False
assert workflow_drain["target"]["latest_phone_home_status"] == "delivered"
assert workflow_drain["target"]["latest_successful_phone_home_status"] == "delivered"
assert workflow_drain["target"]["latest_command_queue_poll_interval_sec"] == "3600"
assert len(set(workflow_drain["delivered_command_ids"])) == 2
assert workflow_drain["http_statuses"] == ["HTTP/1.1 200 OK", "HTTP/1.1 200 OK"]
drained_commands = "\n".join(rec.get("command") or "" for rec in workflow_drain["target_mailbox_records"])
assert "wget -O-" in drained_commands and "probe.sh" in drained_commands
assert "grit fetch workflow-payload.txt" in drained_commands
assert all(rec["status"] == "delivered" for rec in workflow_drain["target_mailbox_records"])
assert workflow_drain["summary"]["target_phone_home_status_counts"]["delivered"] >= 2
assert len(workflow_drain["phone_home_records"]) >= 2
assert all(rec["kind"] == "poll" for rec in workflow_drain["phone_home_records"])
assert all(rec["successful"] is True for rec in workflow_drain["phone_home_records"])
assert any(rec["pending_work_remaining"] is True for rec in workflow_drain["phone_home_records"])
assert any(rec["pending_work_remaining"] is False for rec in workflow_drain["phone_home_records"])
assert workflow_drain_tui["kind"] == "offline-workflow-drain-tui-artifact"
assert workflow_drain_tui["returncode"] == 0
assert workflow_drain_tui["target"]["target_id"] == "target-workflow"
assert workflow_drain_tui["target"]["mailbox_pending_work_count"] == 0
assert workflow_drain_tui["target"]["mailbox_delivered_command_count"] == 2
assert workflow_drain_tui["target"]["last_seen_via"] == "command-queue:command_queue_poll"
assert workflow_drain_tui["target"]["latest_phone_home_status"] == "delivered"
assert all(rec["status"] == "delivered" for rec in workflow_drain_tui["target_mailbox_records"])
assert "Mailbox  (2 records)" in workflow_drain_tui["stdout"]
assert "target-workflow" in workflow_drain_tui["stdout"]
assert "delivered" in workflow_drain_tui["stdout"]
assert "mailbox pending 0" in workflow_drain_tui["stdout"]
assert "path=command-queue:" in workflow_drain_tui["stdout"]
assert "poll current" in workflow_drain_tui["stdout"]
assert "phone_home=" in workflow_drain_tui["stdout"]
assert any(rec["event"] == "workbench_command_queue_inspected" for rec in workflow_drain_tui["workbench_events"])
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
assert systemd["unit_name"] == "grit-flaky.service"
systemd_by_action = {rec["action"]: rec for rec in systemd["commands"]}
assert "Description=griTTYkit Operator Daemon" in systemd_by_action["print"]["stdout"]
assert "--daemon --daemon-service file-service --daemon-service command-queue" in systemd_by_action["print"]["stdout"]
assert "would write" in systemd_by_action["install"]["stdout"]
for action in ("start", "stop", "restart", "status"):
    assert systemd_by_action[action]["stdout"].strip() == f"systemctl --user {action} grit-flaky.service"
assert any(rec["event"] == "systemd_user_unit_printed" for rec in systemd["events"])
assert any(rec["event"] == "systemd_user_unit_install_dry_run" for rec in systemd["events"])
for action in ("start", "stop", "restart", "status"):
    assert any(rec["event"] == "systemd_user_action_dry_run" and (rec["details"] or {}).get("action") == action for rec in systemd["events"])
assert all((rec["details"] or {}).get("headless_command") for rec in systemd["events"])
assert tui_queue["kind"] == "tui-offline-queue-artifact"
assert tui_queue["returncode"] == 0
assert "target workflow action: target-tui:queue-command" in tui_queue["stdout"]
assert "target workflow action: target-tui:queue-probe" in tui_queue["stdout"]
assert "target workflow action: target-tui:stage-file-fetch" in tui_queue["stdout"]
assert "target workflow action: target-tui:queue-staged-fetch" in tui_queue["stdout"]
assert "target workflow action: target-tui:queue-bridge-start:tui-bridge" in tui_queue["stdout"]
assert "command to queue>" in tui_queue["stdout"]
assert "queued " in tui_queue["stdout"]
assert "staged tui-payload.txt" in tui_queue["stdout"]
assert "grit survey --json" in tui_queue["stdout"]
assert "probe.sh" in tui_queue["stdout"]
assert "grit fetch tui-payload.txt" in tui_queue["stdout"]
assert "bridge profile: tui-bridge" in tui_queue["stdout"]
assert "bridge_profile=tui-bridge" not in tui_queue["stdout"]
assert "grit rshell start" in tui_queue["stdout"]
assert tui_queue["target"]["target_id"] == "target-tui"
assert tui_queue["target"]["mailbox_pending_work_count"] == 4
assert tui_queue["after"]["target_mailbox_waiting_for_counts"]["target-poll"] == 4
assert len(tui_queue["target_mailbox_records"]) == 4
assert all(rec["status"] == "queued" for rec in tui_queue["target_mailbox_records"])
assert all(rec["pending_work"] is True for rec in tui_queue["target_mailbox_records"])
assert all(rec["waiting_for"] == "target-poll" for rec in tui_queue["target_mailbox_records"])
tui_queued_commands = "\n".join(rec.get("command") or "" for rec in tui_queue["target_mailbox_records"])
assert "grit survey --json" in tui_queued_commands
assert "probe.sh" in tui_queued_commands
assert "grit fetch tui-payload.txt" in tui_queued_commands
assert "grit rshell start" in tui_queued_commands
survey_mailbox = next(rec for rec in tui_queue["target_mailbox_records"] if "probe.sh" in rec["command"])
fetch_mailbox = next(rec for rec in tui_queue["target_mailbox_records"] if "grit fetch tui-payload.txt" in rec["command"])
bridge_mailbox = next(rec for rec in tui_queue["target_mailbox_records"] if rec["command"] == "grit rshell start")
assert survey_mailbox["work_kind"] == "probe"
assert survey_mailbox["workflow"] == "probe"
assert survey_mailbox["request_name"] == "probe.sh"
assert fetch_mailbox["work_kind"] == "staged-fetch"
assert fetch_mailbox["workflow"] == "file-service"
assert fetch_mailbox["request_name"] == "tui-payload.txt"
assert bridge_mailbox["work_kind"] == "bridge-start"
assert bridge_mailbox["workflow"] == "bridge"
assert bridge_mailbox["bridge_profile"] == "tui-bridge"
assert bridge_mailbox["bridge_route_path"]
assert bridge_mailbox["route_kind"] == "bridge"
assert tui_queue["after"]["target_mailbox_work_kind_counts"]["probe"] == 1
assert tui_queue["after"]["target_mailbox_work_kind_counts"]["staged-fetch"] == 1
assert tui_queue["after"]["target_mailbox_work_kind_counts"]["bridge-start"] == 1
assert tui_queue["after"]["target_mailbox_request_name_counts"]["probe.sh"] == 1
assert tui_queue["after"]["target_mailbox_request_name_counts"]["tui-payload.txt"] == 1
assert tui_queue["after"]["target_mailbox_bridge_profile_counts"]["tui-bridge"] == 1
assert any((rec.get("details") or {}).get("action_id") == "queue-command" for rec in tui_queue["target_workflow_events"])
assert any((rec.get("details") or {}).get("action_id") == "queue-probe" for rec in tui_queue["target_workflow_events"])
assert any((rec.get("details") or {}).get("action_id") == "stage-file-fetch" for rec in tui_queue["target_workflow_events"])
assert any((rec.get("details") or {}).get("action_id") == "queue-staged-fetch" for rec in tui_queue["target_workflow_events"])
assert any((rec.get("details") or {}).get("action_id") == "queue-bridge-start:tui-bridge" and (rec.get("details") or {}).get("bridge_profile") == "tui-bridge" for rec in tui_queue["target_workflow_events"])
assert tui_queue_drain["kind"] == "tui-offline-queue-drain-artifact"
assert tui_queue_drain["http_statuses"] == ["HTTP/1.1 200 OK", "HTTP/1.1 200 OK", "HTTP/1.1 200 OK", "HTTP/1.1 200 OK"]
assert tui_queue_drain["mailbox_record"]["status"] == "delivered"
assert tui_queue_drain["mailbox_record"]["pending_work"] is False
assert len(tui_queue_drain["command_ids"]) == 4
assert len(tui_queue_drain["target_mailbox_records"]) == 4
assert all(rec["status"] == "delivered" for rec in tui_queue_drain["target_mailbox_records"])
assert all(rec["pending_work"] is False for rec in tui_queue_drain["target_mailbox_records"])
drained_bridge_mailbox = next(rec for rec in tui_queue_drain["target_mailbox_records"] if rec["command"] == "grit rshell start")
drained_survey_mailbox = next(rec for rec in tui_queue_drain["target_mailbox_records"] if "probe.sh" in rec["command"])
drained_fetch_mailbox = next(rec for rec in tui_queue_drain["target_mailbox_records"] if "grit fetch tui-payload.txt" in rec["command"])
assert drained_bridge_mailbox["work_kind"] == "bridge-start"
assert drained_bridge_mailbox["bridge_profile"] == "tui-bridge"
assert drained_survey_mailbox["work_kind"] == "probe"
assert drained_fetch_mailbox["work_kind"] == "staged-fetch"
delivered_phone_home = [rec for rec in tui_queue_drain["phone_home_records"] if rec["status"] == "delivered"]
phone_home_by_work_kind = {rec.get("work_kind"): rec for rec in delivered_phone_home if rec.get("work_kind")}
assert phone_home_by_work_kind["probe"]["request_name"] == "probe.sh"
assert phone_home_by_work_kind["staged-fetch"]["request_name"] == "tui-payload.txt"
assert phone_home_by_work_kind["bridge-start"]["bridge_profile"] == "tui-bridge"
assert phone_home_by_work_kind["bridge-start"]["route_kind"] == "bridge"
assert tui_queue_drain["summary"]["target_phone_home_work_kind_counts"]["probe"] == 1
assert tui_queue_drain["summary"]["target_phone_home_work_kind_counts"]["staged-fetch"] == 1
assert tui_queue_drain["summary"]["target_phone_home_work_kind_counts"]["bridge-start"] == 1
assert tui_queue_drain["summary"]["target_phone_home_bridge_profile_counts"]["tui-bridge"] == 1
assert tui_queue_drain["target"]["mailbox_pending_work_count"] == 0
assert tui_queue_drain["target"]["last_seen_via"] == "command-queue:command_queue_poll"
assert tui_queue_drain["target"]["latest_phone_home_status"] == "delivered"
assert any(rec["status"] == "delivered" and rec["target_id"] == "target-tui" for rec in tui_queue_drain["phone_home_records"])
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
assert topology["kind"] == "flaky-network-topology-artifact"
assert topology["operator"]["services"]["command_queue"]["port"]
assert topology["operator"]["services"]["probe"]["port"]
assert topology["operator"]["services"]["file_service"]["port"]
assert topology["operator"]["services"]["bridge"]["port"]
topology_targets = {rec["target_id"]: rec for rec in topology["targets"]}
assert "target-alpha" in topology_targets
assert "target-bravo" in topology_targets
link_states = {rec["name"]: rec for rec in topology["link_states"]}
for state in ("offline-queue", "short-alpha-window", "duplicate-poll", "dropped-result-upload", "partial-transfer", "bridge-interruption", "return-offline"):
    assert state in link_states, state
assert link_states["short-alpha-window"]["state"] == "online-target-alpha-only"
assert link_states["return-offline"]["state"] == "offline-after-short-window"
assert any("--daemon --daemon-service command-queue" in command for command in topology["operator_commands"])
assert topology["qemu_lab_followup"]["status"] == "planned"
assert "summary.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "topology.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "plan.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "phase-contracts.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "validation-report.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "artifact-manifest.json" in topology["qemu_lab_followup"]["required_artifacts"]
assert "summary.json" in topology["qemu_lab_followup"]["support_artifacts"]
assert "validation-report.json" in topology["qemu_lab_followup"]["support_artifacts"]
assert "validate-phase-artifacts.py" in topology["qemu_lab_followup"]["support_artifacts"]
assert "host-network-setup.sh" in topology["qemu_lab_followup"]["support_artifacts"]
assert "qemu-commands.sh" in topology["qemu_lab_followup"]["support_artifacts"]
assert "offline-workflow-drain" in topology["qemu_lab_followup"]["phase_contracts"]
assert "multi-target-isolation" in topology["qemu_lab_followup"]["phase_contracts"]
manifest_names = {item["name"] for item in manifest["artifacts"]}
for name in (
    "target-mailbox.json",
    "offline-workflow-mailbox.json",
    "offline-workflow-tui.json",
    "offline-workflow-drain.json",
    "offline-workflow-drain-tui.json",
    "mailbox-lifecycle.json",
    "restart-persistence.json",
    "bad-token-phone-home.json",
    "duplicate-poll.json",
    "malformed-result-upload.json",
    "dropped-result-upload.json",
    "systemd-user-service.json",
    "tui-offline-queue.json",
    "tui-offline-queue-drain.json",
    "target-mismatch-phone-home.json",
    "command-result.json",
    "phone-home-attempts.json",
    "multi-target-isolation.json",
    "transfer.log",
    "bridge-events.jsonl",
    "bridge-interruption.json",
    "return-offline.json",
    "topology.json",
    "summary.json",
):
    assert name in manifest_names, name
PY
printf '%s\n' "flaky-network-harness ok"
