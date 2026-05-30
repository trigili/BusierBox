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
import os
import subprocess
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
assert summary["schema"] == 1
assert summary["kind"] == "qemu-flaky-network-lab"
assert summary["status"] == "planned"
assert summary["phase_count"] == 14
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
    "malformed-result-upload",
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
    "host-network-setup.sh",
    "qemu-commands.sh",
    "operator-commands.sh",
    "target-commands.sh",
    "artifact-manifest.json",
    "summary.json",
):
    assert (artifact_dir / name).is_file(), name
for name in (
    "host-network-setup.sh",
    "qemu-commands.sh",
    "operator-commands.sh",
    "target-commands.sh",
):
    path = artifact_dir / name
    assert os.access(path, os.X_OK), name
    subprocess.run(["sh", "-n", str(path)], check=True)
plan = json.loads((artifact_dir / "plan.json").read_text(encoding="utf-8"))
topology = json.loads((artifact_dir / "topology.json").read_text(encoding="utf-8"))
manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
assert plan["kind"] == "qemu-flaky-network-lab-plan"
assert topology["kind"] == "qemu-flaky-network-topology"
assert manifest["kind"] == "qemu-flaky-network-artifact-manifest"
assert plan["artifact_manifest"] == str(artifact_dir / "artifact-manifest.json")
assert summary["artifact_manifest"] == str(artifact_dir / "artifact-manifest.json")
manifest_by_name = {item["name"]: item for item in manifest["artifacts"]}
assert manifest_by_name["host-network-setup.sh"]["executable"] is True
assert manifest_by_name["host-network-setup.sh"]["mode"] == "0755"
assert len(manifest_by_name["topology.json"]["sha256"]) == 64
assert manifest_by_name["summary.json"]["size"] > 0
assert len(topology["target_nodes"]) >= 3
assert topology["environment_paths"]["kernel"]
assert topology["environment_paths"]["rootfs"]
assert topology["environment_paths"]["busierbox"]
assert topology["kernel_init_command_line"]
assert topology["service_ports"]["command_queue"] == 22205
assert topology["operator_node"]["host_forward_ports"]["survey_bootstrap"] == 22207
assert topology["host_network_setup"]["bridge"] == "bbx-qemu-br0"
assert topology["host_network_setup"]["target_taps"]["target-alpha"] == "bbx-alpha-tap0"
assert topology["host_network_setup"]["link_control_commands"]["target-alpha-link-down"]
assert topology["accelerated_timing"]["simulated_offline_seconds"] >= 3600
assert topology["accelerated_timing"]["short_window_seconds"] <= 120
assert topology["accelerated_timing"]["poll_interval_seconds"] > 0
assert all(node["kernel"] and node["rootfs"] and node["init_command_line"] for node in topology["target_nodes"])
assert plan["service_ports"]["file_service"] == 22204
assert plan["accelerated_timing"]["short_window_seconds"] == topology["accelerated_timing"]["short_window_seconds"]
assert "host-network-setup.sh" in plan["support_artifacts"]
assert "qemu-commands.sh" in plan["support_artifacts"]
assert plan["support_artifact_modes"]["host-network-setup.sh"] == "0755"
assert plan["support_artifact_modes"]["link-transitions.json"] == "0644"
assert "target-alpha" in plan["qemu_command_templates"]
assert any("bbx-alpha-tap0" in item for item in plan["qemu_command_templates"]["target-alpha"])
host_script = (artifact_dir / "host-network-setup.sh").read_text(encoding="utf-8")
qemu_script = (artifact_dir / "qemu-commands.sh").read_text(encoding="utf-8")
assert "ip link add bbx-qemu-br0 type bridge" in host_script
assert "target-alpha-link-down" in host_script
assert "bbx-alpha-tap0" in qemu_script
assert "target-workflow" in qemu_script
requirements = plan["requirements"]
assert requirements["kind"] == "qemu-flaky-network-lab-requirements"
assert requirements["qemu_binary"]
assert "qemu_binary_found" in requirements
assert "kvm_available" in requirements
assert "tap_available" in requirements
assert requirements["path_requirements"]["kernel_path"]["path"]
assert requirements["path_requirements"]["rootfs_path"]["path"]
assert requirements["path_requirements"]["busierbox_path"]["path"]
assert "offline-status.json" in plan["required_artifacts"]
assert "tui-offline-queue.json" in plan["required_artifacts"]
assert "tui-offline-queue-drain.json" in plan["required_artifacts"]
assert "offline-workflow-tui.json" in plan["required_artifacts"]
assert "offline-workflow-drain.json" in plan["required_artifacts"]
assert "offline-workflow-drain-tui.json" in plan["required_artifacts"]
assert "systemd-user-service.json" in plan["required_artifacts"]
assert "dropped-command-result.http" in plan["required_artifacts"]
assert "multi-target-isolation.json" in plan["required_artifacts"]
assert "target-mismatch-phone-home.json" in plan["required_artifacts"]
assert "malformed-result-upload.json" in plan["required_artifacts"]
assert "bridge-events.jsonl" in plan["required_artifacts"]
assert "bridge-interruption.json" in plan["required_artifacts"]
assert "return-offline.json" in plan["required_artifacts"]
assert any("systemd-dry-run" in item for item in plan["operator_commands"])
assert any("line-tui" in item for item in plan["operator_commands"])
PY

"$ROOT/tests/qemu-system/run-flaky-network-lab" --artifact-root "$tmp/qemu-flaky-run" --run >/dev/null
test -s "$tmp/qemu-flaky-run/summary.json"
test -s "$tmp/qemu-flaky-run"/openwrt-mipsel-minimal/artifact-manifest.json

python3 - "$tmp/qemu-flaky-run/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert summary["kind"] == "qemu-flaky-network-lab"
assert summary["mode"] == "run"
assert summary["status"] == "skip"
assert summary["missing_requirements"]
assert summary["artifact_manifest"].endswith("/artifact-manifest.json")
assert "host-network-setup.sh" in summary["support_artifacts"]
assert "qemu-commands.sh" in summary["support_artifacts"]
assert summary["support_artifact_modes"]["qemu-commands.sh"] == "0755"
assert summary["requirements"]["kind"] == "qemu-flaky-network-lab-requirements"
assert "environment disabled" in summary["reason"]
assert any(item.startswith("missing qemu binary") or item == "missing qemu_binary" or item == "KVM unavailable" or item == "tap/tun unavailable" or item.startswith("missing kernel_path") for item in summary["missing_requirements"])
PY

printf '%s\n' "qemu-flaky-network-lab ok"
