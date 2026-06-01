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
    "validate-phase-artifacts.py",
    "host-network-setup.sh",
    "qemu-commands.sh",
    "operator-commands.sh",
    "target-commands.sh",
    "phase-contracts.json",
    "validation-report.json",
    "artifact-manifest.json",
    "summary.json",
):
    assert (artifact_dir / name).is_file(), name
for name in (
    "host-network-setup.sh",
    "qemu-commands.sh",
    "operator-commands.sh",
    "target-commands.sh",
    "validate-phase-artifacts.py",
):
    path = artifact_dir / name
    assert os.access(path, os.X_OK), name
    if name.endswith(".py"):
        subprocess.run([sys.executable, "-m", "py_compile", str(path)], check=True)
    else:
        subprocess.run(["sh", "-n", str(path)], check=True)
subprocess.run([str(artifact_dir / "validate-phase-artifacts.py"), "--artifact-dir", str(artifact_dir), "--contract-only"], check=True)
validator_sample = artifact_dir / "validator-sample"
validator_sample.mkdir()
(validator_sample / "phase-contracts.json").write_text(json.dumps({
    "schema": 1,
    "kind": "qemu-flaky-network-phase-contracts",
    "contract_count": 1,
    "contracts": [{
        "phase": "systemd-user-service",
        "link_state": "operator-only",
        "required_artifacts": ["systemd-user-service.json"],
        "target_scope": [],
        "assertions": ["systemd dry-run commands complete"],
        "evidence_checks": [
            {"artifact": "systemd-user-service.json", "path": "unit_name", "expect": "grit-flaky.service"},
            {"artifact": "systemd-user-service.json", "path": "commands[*].returncode", "expect_all": 0},
        ],
    }],
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(validator_sample / "systemd-user-service.json").write_text(json.dumps({
    "unit_name": "grit-flaky.service",
    "commands": [{"returncode": 0}, {"returncode": 0}],
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(validator_sample / "validation-report.json").write_text(json.dumps({
    "schema": 1,
    "kind": "qemu-flaky-network-phase-validation-report",
    "environment": "validator-sample",
    "mode": "synthetic",
    "contract_count": 1,
    "phase_count": 1,
    "evidence_check_count": 2,
    "missing_evidence_artifact_count": 0,
    "status_counts": {"ready": 1, "pending-evidence": 0},
    "status": "ready",
    "records": [{
        "phase": "systemd-user-service",
        "link_state": "operator-only",
        "target_scope": [],
        "required_artifacts": ["systemd-user-service.json"],
        "assertion_count": 1,
        "evidence_check_count": 2,
        "missing_evidence_artifacts": [],
        "missing_evidence_artifact_count": 0,
        "status": "ready",
    }],
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
subprocess.run([str(artifact_dir / "validate-phase-artifacts.py"), "--artifact-dir", str(validator_sample)], check=True)
bad_report_sample = artifact_dir / "bad-validation-report-sample"
bad_report_sample.mkdir()
for name in ("phase-contracts.json", "systemd-user-service.json", "validation-report.json"):
    (bad_report_sample / name).write_text((validator_sample / name).read_text(encoding="utf-8"), encoding="utf-8")
bad_report = json.loads((bad_report_sample / "validation-report.json").read_text(encoding="utf-8"))
bad_report["contract_count"] = 2
(bad_report_sample / "validation-report.json").write_text(json.dumps(bad_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
failed = subprocess.run([str(artifact_dir / "validate-phase-artifacts.py"), "--artifact-dir", str(bad_report_sample)],
                        text=True, capture_output=True)
assert failed.returncode != 0
assert "validation report contract count mismatch" in failed.stderr
plan = json.loads((artifact_dir / "plan.json").read_text(encoding="utf-8"))
topology = json.loads((artifact_dir / "topology.json").read_text(encoding="utf-8"))
contracts = json.loads((artifact_dir / "phase-contracts.json").read_text(encoding="utf-8"))
validation_report = json.loads((artifact_dir / "validation-report.json").read_text(encoding="utf-8"))
manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
assert plan["kind"] == "qemu-flaky-network-lab-plan"
assert topology["kind"] == "qemu-flaky-network-topology"
assert contracts["kind"] == "qemu-flaky-network-phase-contracts"
assert validation_report["kind"] == "qemu-flaky-network-phase-validation-report"
assert manifest["kind"] == "qemu-flaky-network-artifact-manifest"
assert plan["artifact_manifest"] == str(artifact_dir / "artifact-manifest.json")
assert plan["phase_contracts_path"] == str(artifact_dir / "phase-contracts.json")
assert plan["phase_validation_report"] == str(artifact_dir / "validation-report.json")
assert summary["phase_contracts"] == str(artifact_dir / "phase-contracts.json")
assert summary["phase_validation_report"] == str(artifact_dir / "validation-report.json")
assert summary["phase_validation_status"] == "pending-evidence"
assert summary["phase_validation_missing_evidence_artifact_count"] > 0
assert summary["phase_contract_count"] == summary["phase_count"]
assert summary["phase_runbook_summary"]["phase_count"] == summary["phase_count"]
assert summary["phase_runbook_summary"] == plan["phase_runbook_summary"]
assert summary["artifact_manifest"] == str(artifact_dir / "artifact-manifest.json")
manifest_by_name = {item["name"]: item for item in manifest["artifacts"]}
assert manifest_by_name["host-network-setup.sh"]["executable"] is True
assert manifest_by_name["host-network-setup.sh"]["mode"] == "0755"
assert len(manifest_by_name["topology.json"]["sha256"]) == 64
assert len(manifest_by_name["phase-contracts.json"]["sha256"]) == 64
assert len(manifest_by_name["validation-report.json"]["sha256"]) == 64
assert manifest_by_name["summary.json"]["size"] > 0
assert validation_report["status"] == "pending-evidence"
assert validation_report["phase_count"] == summary["phase_count"]
assert validation_report["status_counts"]["pending-evidence"] == summary["phase_count"]
report_by_phase = {item["phase"]: item for item in validation_report["records"]}
assert "offline-workflow-drain.json" in report_by_phase["offline-workflow-drain"]["missing_evidence_artifacts"]
assert report_by_phase["offline-workflow-drain"]["evidence_check_count"] >= 2
contracts_by_phase = {item["phase"]: item for item in contracts["contracts"]}
assert len(contracts_by_phase) == summary["phase_count"]
assert contracts_by_phase["offline-workflow-drain"]["timing"]["short_window_seconds"] == 90
assert "target-workflow" in contracts_by_phase["offline-workflow-drain"]["target_scope"]
assert any("queued probe bootstrap" in item for item in contracts_by_phase["offline-workflow-drain"]["assertions"])
drain_checks = contracts_by_phase["offline-workflow-drain"]["evidence_checks"]
assert any(item["artifact"] == "offline-workflow-drain.json" and item["path"] == "target.latest_phone_home_status" and item["expect"] == "delivered" for item in drain_checks)
assert any(item["artifact"] == "offline-workflow-drain-tui.json" and item["path"] == "target.mailbox_delivered_command_count" and item["expect"] == 2 for item in drain_checks)
assert "target-bravo" in contracts_by_phase["multi-target-isolation"]["target_scope"]
assert any("does not mutate target-bravo" in item for item in contracts_by_phase["multi-target-isolation"]["assertions"])
isolation_checks = contracts_by_phase["multi-target-isolation"]["evidence_checks"]
assert any(item["path"] == "summary.target_mailbox_status_counts.queued" and item["expect"] == 1 for item in isolation_checks)
assert any(item["path"] == "summary.target_mailbox_status_counts.result-received" and item["expect"] == 1 for item in isolation_checks)
assert any(item["artifact"] == "return-offline.json" and item["path"] == "targets_by_id.target-bravo.mailbox_pending_work_count" and item["expect"] == 1 for item in contracts_by_phase["return-offline"]["evidence_checks"])
assert len(topology["target_nodes"]) >= 3
assert topology["environment_paths"]["kernel"]
assert topology["environment_paths"]["rootfs"]
assert topology["environment_paths"]["grit"]
assert topology["kernel_init_command_line"]
assert topology["service_ports"]["command_queue"] == 22205
assert topology["operator_node"]["host_forward_ports"]["probe"] == 22207
assert topology["host_network_setup"]["bridge"] == "grit-qemu-br0"
assert topology["host_network_setup"]["target_taps"]["target-alpha"] == "grit-alpha-tap0"
assert topology["host_network_setup"]["link_control_commands"]["target-alpha-link-down"]
transition_by_phase = {item["phase"]: item for item in topology["link_transitions"]}
assert set(transition_by_phase) == set(summary["phase_names"])
assert transition_by_phase["duplicate-poll"]["target-alpha-link"] == "up"
assert transition_by_phase["result-upload"]["target-alpha-link"] == "up"
assert transition_by_phase["survey-window"]["target-alpha-link"] == "up"
assert transition_by_phase["return-offline"]["target-bravo-link"] == "down"
assert topology["accelerated_timing"]["simulated_offline_seconds"] >= 3600
assert topology["accelerated_timing"]["short_window_seconds"] <= 120
assert topology["accelerated_timing"]["poll_interval_seconds"] > 0
assert all(node["kernel"] and node["rootfs"] and node["init_command_line"] for node in topology["target_nodes"])
assert plan["service_ports"]["file_service"] == 22204
assert plan["accelerated_timing"]["short_window_seconds"] == topology["accelerated_timing"]["short_window_seconds"]
assert "host-network-setup.sh" in plan["support_artifacts"]
assert "qemu-commands.sh" in plan["support_artifacts"]
assert "validate-phase-artifacts.py" in plan["support_artifacts"]
assert "phase-contracts.json" in plan["support_artifacts"]
assert "validation-report.json" in plan["support_artifacts"]
assert "summary.json" in plan["support_artifacts"]
assert "artifact-manifest.json" in plan["support_artifacts"]
assert plan["support_artifact_modes"]["validate-phase-artifacts.py"] == "0755"
assert plan["support_artifact_modes"]["host-network-setup.sh"] == "0755"
assert plan["support_artifact_modes"]["summary.json"] == "0644"
assert plan["support_artifact_modes"]["artifact-manifest.json"] == "0644"
assert plan["support_artifact_modes"]["link-transitions.json"] == "0644"
assert plan["support_artifact_modes"]["phase-contracts.json"] == "0644"
assert plan["support_artifact_modes"]["validation-report.json"] == "0644"
assert "target-alpha" in plan["qemu_command_templates"]
assert any("grit-alpha-tap0" in item for item in plan["qemu_command_templates"]["target-alpha"])
host_script = (artifact_dir / "host-network-setup.sh").read_text(encoding="utf-8")
qemu_script = (artifact_dir / "qemu-commands.sh").read_text(encoding="utf-8")
operator_script = (artifact_dir / "operator-commands.sh").read_text(encoding="utf-8")
target_script = (artifact_dir / "target-commands.sh").read_text(encoding="utf-8")
assert "ip link add grit-qemu-br0 type bridge" in host_script
assert "target-alpha-link-down" in host_script
assert "grit-alpha-tap0" in qemu_script
assert "target-workflow" in qemu_script
assert "# phase: offline-queue" in operator_script
assert "# phase: bridge-interruption" in operator_script
assert "# phase: offline-workflow-drain" in target_script
assert "grit command-queue once --target-id target-alpha" in target_script
requirements = plan["requirements"]
assert requirements["kind"] == "qemu-flaky-network-lab-requirements"
assert requirements["qemu_binary"]
assert "qemu_binary_found" in requirements
assert "kvm_available" in requirements
assert "tap_available" in requirements
assert requirements["path_requirements"]["kernel_path"]["path"]
assert requirements["path_requirements"]["rootfs_path"]["path"]
assert requirements["path_requirements"]["grit_path"]["path"]
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
phases_by_name = {item["name"]: item for item in plan["phases"]}
runbooks = plan["phase_runbook_summary"]
assert runbooks["operator_command_phase_count"] >= 10
assert runbooks["target_command_phase_count"] >= 8
assert runbooks["unique_operator_command_count"] == len(plan["operator_commands"])
assert runbooks["unique_target_command_count"] == len(plan["target_commands"])
assert runbooks["phases_without_operator_commands"] == []
assert "offline-queue" in runbooks["phases_without_target_commands"]
assert "systemd-user-service" in runbooks["phases_without_target_commands"]
assert "offline-workflow-drain" in runbooks["phases_with_both_operator_and_target_commands"]
assert "bridge-interruption" in runbooks["phases_with_both_operator_and_target_commands"]
assert any("--queue-command 'grit survey --json'" in item for item in phases_by_name["offline-queue"]["operator_commands"])
assert any("--line-tui" in item for item in phases_by_name["offline-queue"]["operator_commands"])
assert any("systemd-user-dry-run" in item for item in phases_by_name["systemd-user-service"]["operator_commands"])
assert any("--transport probe" in item for item in phases_by_name["survey-window"]["operator_commands"])
assert any("--file-service" in item for item in phases_by_name["partial-transfer"]["operator_commands"])
assert any("--save-bridge-profile flaky-bad-bridge" in item for item in phases_by_name["bridge-interruption"]["operator_commands"])
assert any("command-queue once --target-id target-workflow" in item for item in phases_by_name["offline-workflow-drain"]["target_commands"])
assert any("grit upload /tmp/evidence.txt" in item for item in phases_by_name["partial-transfer"]["target_commands"])
assert any("systemd-user-dry-run" in item for item in plan["operator_commands"])
assert any("line-tui" in item for item in plan["operator_commands"])
assert any("grit command-queue result --target-id target-alpha" in item for item in plan["target_commands"])
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
assert summary["phase_contracts"].endswith("/phase-contracts.json")
assert summary["phase_validation_report"].endswith("/validation-report.json")
assert "host-network-setup.sh" in summary["support_artifacts"]
assert "qemu-commands.sh" in summary["support_artifacts"]
assert "validate-phase-artifacts.py" in summary["support_artifacts"]
assert summary["support_artifact_modes"]["qemu-commands.sh"] == "0755"
assert summary["requirements"]["kind"] == "qemu-flaky-network-lab-requirements"
assert "environment disabled" in summary["reason"]
assert any(item.startswith("missing qemu binary") or item == "missing qemu_binary" or item == "KVM unavailable" or item == "tap/tun unavailable" or item.startswith("missing kernel_path") for item in summary["missing_requirements"])
PY

printf '%s\n' "qemu-flaky-network-lab ok"
