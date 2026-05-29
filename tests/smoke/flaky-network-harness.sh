#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

python3 tests/integration/flaky-network-harness.py --artifact-dir "$tmp/flaky-network" >/dev/null
test -s "$tmp/flaky-network/summary.json"
test -s "$tmp/flaky-network/target-mailbox.json"
test -s "$tmp/flaky-network/command-result.json"
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
result = json.loads((artifact_dir / "command-result.json").read_text(encoding="utf-8"))
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
assert result["kind"] == "command-result-artifact"
assert result["status"] == "result-received"
assert result["result_status"] == "completed"
assert result["target_last_seen_via"] == "command-queue:command_queue_result"
assert transfer["kind"] == "transfer-log-artifact"
assert transfer["latest_file_transfer_status"] == "truncated"
assert bridge_events
assert any((rec.get("details") or {}).get("bridge_profile") == "flaky-bridge" for rec in bridge_events)
manifest_names = {item["name"] for item in manifest["artifacts"]}
for name in (
    "target-mailbox.json",
    "command-result.json",
    "transfer.log",
    "bridge-events.jsonl",
    "summary.json",
):
    assert name in manifest_names, name
PY
printf '%s\n' "flaky-network-harness ok"
