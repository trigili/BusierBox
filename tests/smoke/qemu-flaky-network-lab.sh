#!/bin/sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$ROOT/tests/qemu-system/run-flaky-network-lab" --artifact-root "$tmp/qemu-flaky" --plan-only >/dev/null
test -s "$tmp/qemu-flaky/summary.json"
test -s "$tmp/qemu-flaky/summary.txt"

python3 - "$tmp/qemu-flaky/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
assert summary["schema"] == 1
assert summary["kind"] == "qemu-flaky-network-lab"
assert summary["status"] == "planned"
assert summary["phase_count"] == 13
for required in (
    "offline-queue",
    "offline-workflow-drain",
    "systemd-user-service",
    "short-phone-home-window",
    "duplicate-poll",
    "dropped-result-upload",
    "result-upload",
    "multi-target-isolation",
    "target-mismatch-phone-home",
    "survey-window",
    "partial-transfer",
    "bridge-interruption",
    "return-offline",
):
    assert required in summary["phase_names"], required
artifact_dir = Path(summary["artifact_dir"])
for name in (
    "plan.json",
    "topology.json",
    "link-transitions.json",
    "operator-commands.sh",
    "target-commands.sh",
    "summary.json",
):
    assert (artifact_dir / name).is_file(), name
plan = json.loads((artifact_dir / "plan.json").read_text(encoding="utf-8"))
topology = json.loads((artifact_dir / "topology.json").read_text(encoding="utf-8"))
assert plan["kind"] == "qemu-flaky-network-lab-plan"
assert topology["kind"] == "qemu-flaky-network-topology"
assert len(topology["target_nodes"]) >= 3
assert "offline-status.json" in plan["required_artifacts"]
assert "offline-workflow-tui.json" in plan["required_artifacts"]
assert "offline-workflow-drain.json" in plan["required_artifacts"]
assert "systemd-user-service.json" in plan["required_artifacts"]
assert "dropped-command-result.http" in plan["required_artifacts"]
assert "multi-target-isolation.json" in plan["required_artifacts"]
assert "target-mismatch-phone-home.json" in plan["required_artifacts"]
assert "bridge-events.jsonl" in plan["required_artifacts"]
assert "bridge-interruption.json" in plan["required_artifacts"]
assert any("systemd-dry-run" in item for item in plan["operator_commands"])
assert any("line-tui" in item for item in plan["operator_commands"])
PY

printf '%s\n' "qemu-flaky-network-lab ok"
