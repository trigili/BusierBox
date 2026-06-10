#!/usr/bin/env python3
"""Run review-oriented grit-console UX audits.

This harness is intentionally not a pass/fail UX oracle. It fails for
infrastructure problems such as crashes, hangs, or missing artifacts, and writes
reviewable reports for operator-flow quality.
"""

import argparse
import datetime as dt
import json
import os
import pty
import re
import select
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


SCENARIOS = [
    {
        "name": "probe-create-and-serve",
        "description": "Discover, configure, start, and inspect the probe listener.",
        "qemu": False,
        "commands": [
            "workspace",
            "next",
            "listeners",
            "?",
            "probe options",
            "listener probe start",
            "listener probe delivery",
            "listener probe paste",
            "stop probe",
            "q",
        ],
        "rubric_focus": ["Discoverability", "Context clarity", "Copy/paste quality"],
    },
    {
        "name": "binary-delivery",
        "description": "Stage a local griTTYkit-like artifact and inspect target delivery commands.",
        "qemu": False,
        "commands": [
            "files",
            "serve-binary start scripts/grit-console grit-console",
            "deliver grit-console",
            "artifact info grit-console",
            "stop file-service",
            "q",
        ],
        "rubric_focus": ["Discoverability", "Directionality", "Noise"],
    },
    {
        "name": "reverse-shell",
        "description": "Inspect and start a reverse shell listener, then review target command shape.",
        "qemu": False,
        "commands": [
            "listeners",
            "listener plain-shell",
            "options",
            "show start",
            "run",
            "options",
            "show stop",
            "stop plain-shell",
            "q",
        ],
        "rubric_focus": ["Consistency", "Context clarity", "Reversibility"],
    },
    {
        "name": "file-directionality",
        "description": "Exercise operator-to-target staging and target-to-operator retrieval wording.",
        "qemu": False,
        "commands": [
            "files",
            "stage start {sample_file} ux-sample",
            "deliver ux-sample",
            "retrieve /etc/hosts",
            "retrieve queue /etc/hosts",
            "stop file-service",
            "q",
        ],
        "rubric_focus": ["Directionality", "Error recovery", "Copy/paste quality"],
    },
]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def timestamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def line_number_for(text, needle):
    if not needle:
        return None
    offset = text.find(needle)
    if offset < 0:
        return None
    return text.count("\n", 0, offset) + 1


def prompt_count(text):
    return len(re.findall(r"grit\[[^\n]+>", text))


def write_config(path, artifact_dir):
    state = artifact_dir / "server-state.json"
    staged = artifact_dir / "staged-files.json"
    sessions = artifact_dir / "sessions"
    operator_session = artifact_dir / "operator-session"
    bridge_profiles = artifact_dir / "bridge-profiles.json"
    build_config = artifact_dir / "build-config.json"
    cfg = {
        "listen_host": "127.0.0.1",
        "GRIT_OPERATOR_SERVER_HOST": "127.0.0.1",
        "GRIT_SSH_PORT": free_port(),
        "GRIT_TLS_SHELL_PORT": free_port(),
        "GRIT_PLAIN_SHELL_PORT": free_port(),
        "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
        "GRIT_COMMAND_QUEUE_PORT": free_port(),
        "GRIT_BRIDGE_PORT": free_port(),
        "GRIT_PROBE_PORT": free_port(),
        "GRIT_PROBE_TFTP_PORT": free_port(),
        "GRIT_PROBE_FTP_PORT": free_port(),
        "GRIT_PROBE_DNS_PORT": free_port(),
        "server_state": str(state),
        "staged_files": str(staged),
        "session_root": str(sessions),
        "operator_session_dir": str(operator_session),
        "bridge_profiles_file": str(bridge_profiles),
        "build_config": str(build_config),
    }
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cfg


def run_console(commands, cfg_path, scenario_dir, timeout_sec):
    master, slave = pty.openpty()
    proc = None
    chunks = []
    stderr_text = ""
    try:
        proc = subprocess.Popen(
            [
                str(ROOT / "scripts" / "grit-console"),
                "--config", str(cfg_path),
            ],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERM": "dumb", "PAGER": "cat"},
        )
        os.close(slave)
        slave = -1
        time.sleep(0.25)
        script = "\n".join(commands) + "\nq\n"
        view = memoryview(script.encode("utf-8"))
        while view:
            written = os.write(master, view)
            view = view[written:]
        deadline = time.time() + timeout_sec
        while proc.poll() is None and time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunks.append(os.read(master, 65536).decode("utf-8", errors="replace"))
                except OSError:
                    break
        if proc.poll() is None:
            try:
                os.write(master, b"q\n")
            except OSError:
                pass
            stop_deadline = time.time() + 2
            while proc.poll() is None and time.time() < stop_deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunks.append(os.read(master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        stderr_text = proc.stderr.read() if proc.stderr else ""
        transcript = "".join(chunks)
        (scenario_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        (scenario_dir / "stderr.txt").write_text(stderr_text or "", encoding="utf-8")
        (scenario_dir / "commands.txt").write_text(
            "\n".join(commands) + "\n",
            encoding="utf-8",
        )
        return {
            "returncode": proc.returncode,
            "transcript": transcript,
            "stderr": stderr_text or "",
            "timed_out": proc.returncode is None,
        }
    finally:
        if slave != -1:
            os.close(slave)
        try:
            os.close(master)
        except OSError:
            pass


def scenario_observations(transcript, commands):
    observations = []
    patterns = [
        ("help used", "?", "Operator asked for contextual help."),
        ("backtracking", "back", "Operator used back/background navigation."),
        ("invalid selection", "not found", "Console reported a missing selection or resource."),
        ("stopped listener", "stopped", "Console exposed stopped listener state."),
        ("target command", "Target command:", "Console generated a target-side command."),
        ("delivery options", "Delivery options", "Console showed multiple target delivery options."),
        ("direction wording", "target-to-operator", "Console used explicit target-to-operator direction wording."),
        ("headless detail", "headless_command", "Console exposed generated headless command details."),
    ]
    for label, needle, message in patterns:
        line = line_number_for(transcript, needle)
        if line is not None:
            observations.append({
                "label": label,
                "line": line,
                "message": message,
                "needle": needle,
            })
    local_global_line = line_number_for(transcript, "Global forms")
    if local_global_line is not None:
        observations.append({
            "label": "local/global help",
            "line": local_global_line,
            "message": "Help explicitly separated global command forms from selected-context commands.",
            "needle": "Global forms",
        })
    return observations


def scenario_summary(scenario, scenario_dir, result, rendered_commands):
    transcript = result["transcript"]
    stderr_text = result["stderr"]
    hard_failures = []
    if result["returncode"] not in (0, None):
        hard_failures.append(f"console exited {result['returncode']}")
    if "Traceback" in transcript or "Traceback" in stderr_text:
        hard_failures.append("traceback present")
    if not transcript.strip():
        hard_failures.append("empty transcript")
    return {
        "name": scenario["name"],
        "description": scenario["description"],
        "environment": "local PTY",
        "qemu": bool(scenario.get("qemu")),
        "artifact": None,
        "target_tuple": None,
        "command_count": len(rendered_commands),
        "commands": rendered_commands,
        "transcript": str(scenario_dir / "transcript.txt"),
        "stderr": str(scenario_dir / "stderr.txt"),
        "prompt_count": prompt_count(transcript),
        "returncode": result["returncode"],
        "hard_failures": hard_failures,
        "rubric_focus": list(scenario.get("rubric_focus") or []),
        "observations": scenario_observations(transcript, rendered_commands),
    }


def write_report(path, artifact_dir, summaries):
    lines = [
        "# grit-console UX Audit",
        "",
        f"Artifact directory: `{artifact_dir}`",
        "",
        "This report is review-oriented. Infrastructure failures are listed as",
        "hard failures; UX observations are prompts for human review and follow-up",
        "regression tests.",
        "",
        "## Scenarios",
        "",
    ]
    for summary in summaries:
        lines.extend([
            f"### {summary['name']}",
            "",
            summary["description"],
            "",
            f"- Environment: {summary['environment']}",
            f"- QEMU target used: {'yes' if summary['qemu'] else 'no'}",
            f"- Target tuple: {summary['target_tuple'] or 'n/a'}",
            f"- Artifact: {summary['artifact'] or 'n/a'}",
            f"- Commands: {summary['command_count']}",
            f"- Transcript: `{summary['transcript']}`",
            f"- stderr: `{summary['stderr']}`",
            f"- Prompt count: {summary['prompt_count']}",
            f"- Hard failures: {', '.join(summary['hard_failures']) if summary['hard_failures'] else 'none'}",
            f"- Rubric focus: {', '.join(summary['rubric_focus'])}",
            "",
            "Command list:",
            "",
        ])
        lines.extend(f"1. `{command}`" for command in summary["commands"])
        lines.extend(["", "Review observations:", ""])
        if summary["observations"]:
            for obs in summary["observations"]:
                lines.append(
                    f"- Line {obs['line']}: {obs['message']} (`{obs['needle']}`)"
                )
        else:
            lines.append("- No heuristic observations recorded; inspect transcript manually.")
        lines.extend([
            "",
            "Reviewer prompts:",
            "",
            "- Discoverability: did the next action appear on-screen before the command was entered?",
            "- Consistency: did global and submenu-local command forms behave as expected?",
            "- Context clarity: did the prompt make the active context obvious?",
            "- Reversibility: was it clear how to stop services or back out?",
            "- Directionality: was operator-to-target vs target-to-operator wording clear?",
            "- Noise: did output avoid raw ids and implementation details by default?",
            "",
        ])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", default="tests/artifacts/ux-audit")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    artifact_dir = ROOT / args.artifact_root / timestamp()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sample_file = artifact_dir / "ux-sample.txt"
    sample_file.write_text("griTTYkit UX audit sample\n", encoding="utf-8")
    cfg_path = artifact_dir / "config.json"
    cfg = write_config(cfg_path, artifact_dir)

    summaries = []
    hard_failures = []
    for scenario in SCENARIOS:
        scenario_dir = artifact_dir / scenario["name"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        rendered_commands = [
            command.format(sample_file=sample_file)
            for command in scenario["commands"]
        ]
        result = run_console(rendered_commands, cfg_path, scenario_dir, args.timeout)
        summary = scenario_summary(scenario, scenario_dir, result, rendered_commands)
        (scenario_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summaries.append(summary)
        hard_failures.extend(
            f"{scenario['name']}: {failure}"
            for failure in summary["hard_failures"]
        )

    summary = {
        "schema": 1,
        "kind": "grit-console-ux-audit",
        "artifact_dir": str(artifact_dir),
        "config": str(cfg_path),
        "environment": "local PTY",
        "qemu_used": False,
        "listener_host": cfg.get("listen_host"),
        "scenario_count": len(summaries),
        "hard_failures": hard_failures,
        "scenarios": summaries,
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(artifact_dir / "UX_AUDIT.md", artifact_dir, summaries)
    print(f"summary={artifact_dir / 'summary.json'}")
    print(f"report={artifact_dir / 'UX_AUDIT.md'}")
    if hard_failures:
        print("ux-audit-console: infrastructure failures:", file=sys.stderr)
        for failure in hard_failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
