#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

python3 tests/integration/flaky-network-harness.py --artifact-dir "$tmp/flaky-network" >/dev/null
test -s "$tmp/flaky-network/summary.json"
test -s "$tmp/flaky-network/target-mailbox.json"
test -s "$tmp/flaky-network/offline-workflow-mailbox.json"
test -s "$tmp/flaky-network/mailbox-lifecycle.json"
test -s "$tmp/flaky-network/restart-persistence.json"
test -s "$tmp/flaky-network/bad-token-phone-home.json"
test -s "$tmp/flaky-network/command-result.json"
test -s "$tmp/flaky-network/phone-home-attempts.json"
test -s "$tmp/flaky-network/transfer.log"
test -s "$tmp/flaky-network/bridge-events.jsonl"
test -s "$tmp/flaky-network/artifact-manifest.json"
python3 -m json.tool "$tmp/flaky-network/summary.json" >/dev/null
python3 - "$tmp/flaky-network" <<'PY'
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
mailbox = json.loads((artifact_dir / "target-mailbox.json").read_text(encoding="utf-8"))
workflow = json.loads((artifact_dir / "offline-workflow-mailbox.json").read_text(encoding="utf-8"))
lifecycle = json.loads((artifact_dir / "mailbox-lifecycle.json").read_text(encoding="utf-8"))
restart = json.loads((artifact_dir / "restart-persistence.json").read_text(encoding="utf-8"))
bad_token = json.loads((artifact_dir / "bad-token-phone-home.json").read_text(encoding="utf-8"))
result = json.loads((artifact_dir / "command-result.json").read_text(encoding="utf-8"))
phone_home = json.loads((artifact_dir / "phone-home-attempts.json").read_text(encoding="utf-8"))
transfer = json.loads((artifact_dir / "transfer.log").read_text(encoding="utf-8"))
manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
bridge_events = [
    json.loads(line)
    for line in (artifact_dir / "bridge-events.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]

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
assert result["kind"] == "command-result-artifact"
assert result["status"] == "result-received"
assert result["result_status"] == "completed"
assert result["target_last_seen_via"] == "command-queue:command_queue_result"
assert phone_home["kind"] == "phone-home-attempts-artifact"
assert phone_home["summary"]["target_phone_home_status_counts"]["result-received"] >= 1
assert phone_home["summary"]["target_phone_home_failed_counts"]["True"] >= 1
assert phone_home["summary"]["target_phone_home_anonymous_counts"]["True"] >= 1
assert any(rec["pending_reason"] == "queued work requires a target identity" for rec in phone_home["target_phone_home_records"])
assert transfer["kind"] == "transfer-log-artifact"
assert transfer["latest_file_transfer_status"] == "truncated"
assert bridge_events
assert any((rec.get("details") or {}).get("bridge_profile") == "flaky-bridge" for rec in bridge_events)
manifest_names = {item["name"] for item in manifest["artifacts"]}
for name in (
    "target-mailbox.json",
    "offline-workflow-mailbox.json",
    "mailbox-lifecycle.json",
    "restart-persistence.json",
    "bad-token-phone-home.json",
    "command-result.json",
    "phone-home-attempts.json",
    "transfer.log",
    "bridge-events.jsonl",
    "summary.json",
):
    assert name in manifest_names, name
PY
printf '%s\n' "flaky-network-harness ok"
