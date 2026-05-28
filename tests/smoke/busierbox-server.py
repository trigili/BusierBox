#!/usr/bin/env python3
import json
import os
import pty
import select
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def recv_all(sock):
    out = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return out
        out += chunk


def connect_with_retry(port, payload, tls_context=None):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as raw:
                if tls_context:
                    with tls_context.wrap_socket(raw, server_hostname="busierbox") as conn:
                        conn.sendall(payload)
                        return recv_all(conn)
                raw.sendall(payload)
                return recv_all(raw)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"server did not open port {port}: {last}")


def main():
    server = ROOT / "scripts" / "busierbox-server"

    help_out = run("scripts/busierbox-server", "--help")
    if help_out.returncode != 0:
        print(help_out.stderr, file=sys.stderr)
        return 1
    forbidden = ("--artifact", "--send", "--token", "send_file", "stager")
    combined = help_out.stdout + help_out.stderr
    for word in forbidden:
        if word in combined:
            print(f"old server protocol surfaced in help: {word}", file=sys.stderr)
            return 1

    # help must describe tls-shell as accepting both builtin+tls and socat+tls
    if "tls-shell" not in combined:
        print("busierbox-server help missing tls-shell transport description", file=sys.stderr)
        return 1
    if "file-service" not in combined or "--file-service" not in combined:
        print("busierbox-server help missing receive-only file service", file=sys.stderr)
        return 1
    for word in ("--tui", "--serve-file", "--serve-dir", "--stage-release-artifact", "--release-dir", "--list-staged", "--status", "--stop", "--json-status", "--api-status", "--event-limit",
                 "--queue-command", "--list-command-queue", "--clear-command-queue", "--copy-target-command", "--command-copy-file",
                 "--record-command-result", "--result-json", "--start-workbench-job", "--cancel-workbench-job",
                 "--build-config", "--list-build-config", "--set-build-config"):
        if word not in combined:
            print(f"busierbox-server help missing operator workbench flag: {word}", file=sys.stderr)
            return 1

    # Paramiko key comparison must use get_name/get_base64, not object equality
    src = (ROOT / "scripts" / "busierbox-server").read_text()
    release_docs = (ROOT / "docs" / "release-bundles.md").read_text()
    for word in ("invalid_command_queue_policy",
                 "command_queue_policy_valid",
                 "command_queue_policy_error_count"):
        if word not in release_docs:
            print(f"release bundle status docs missing command queue policy contract: {word}", file=sys.stderr)
            return 1
    if "get_name()" not in src or "get_base64()" not in src:
        print("busierbox-server: Paramiko key comparison missing get_name()/get_base64()", file=sys.stderr)
        return 1
    # Should not use bare == or 'is' for key objects
    # (keys_equal helper function should exist)
    if "keys_equal" not in src:
        print("busierbox-server: keys_equal helper not found", file=sys.stderr)
        return 1

    # New config field names: shell_listen_port, encryption (not socat_listen_port)
    if "shell_listen_port" not in src:
        print("busierbox-server: shell_listen_port not found (expected rename from socat_listen_port)", file=sys.stderr)
        return 1
    if "sys.stdin.isatty()" not in src or "--no-stdin" not in src or "--log-only" not in src:
        print("busierbox-server: stdin EOF/log-only handling not found", file=sys.stderr)
        return 1
    for word in ("open_path_in_pager", "pager_command", 'ord("v")', "v opens", "copy_generated_command", "clipboard_command",
                 "event_id:", "details_json:", "v opens operator event log in pager", "record_workbench_refresh",
                 "workbench_refreshed", 'ord("r")', 'ord("R")'):
        if word not in src:
            print(f"busierbox-server: workbench pager inspection missing: {word}", file=sys.stderr)
            return 1
    for word in ("stage_release_nav_item", "stage_release_selection", "by_device:", "by_tuple_path:", "enter/s stages recommended artifact when available"):
        if word not in src:
            print(f"busierbox-server: release device/tuple staging missing: {word}", file=sys.stderr)
            return 1
    for word in ("tty.setraw", "tcsetattr", "SSLWantReadError", "SSLWantWriteError",
                 "bytearray", "--one-shot", "listener remains open", 'reason = "active"',
                 "TLSVersion.TLSv1_2"):
        if word not in src:
            print(f"busierbox-server: robust interactive relay feature missing: {word}", file=sys.stderr)
            return 1
    for reason in ("stdin_eof", "remote_eof", "socket_error", "tls_error", "keyboard_interrupt", "timeout"):
        if reason not in src:
            print(f"busierbox-server: relay exit reason missing: {reason}", file=sys.stderr)
            return 1
    for word in (
        "Receive-only file service",
        "local/sessions",
        "metadata_path",
        "x-busierbox-source-path",
        "does not send artifacts",
        "file_service_port",
    ):
        if word not in src:
            print(f"busierbox-server: file service feature missing: {word}", file=sys.stderr)
            return 1
    for word in ("reverse_forward_active", "requested_port", "forward_host",
                 "reverse_forward_listener", "reverse-forward listener bind failed"):
        if word not in src:
            print(f"busierbox-server: reverse forward event missing: {word}", file=sys.stderr)
            return 1
    if 'name="busierbox-reverse-forward"' not in src or "join(timeout=2.0)" not in src:
        print("busierbox-server: reverse-forward listener thread is not explicitly owned/joined", file=sys.stderr)
        return 1
    if ("busierbox-reverse-forward-pipe-" not in src or
            "register_socket(local)" not in src or
            "register_transport(chan)" not in src or
            "register_thread(threading.Thread(" not in src or
            "daemon=True" in src):
        print("busierbox-server: reverse-forward relay resources are not explicitly owned", file=sys.stderr)
        return 1
    for word in ("class ServiceManager", "SERVICE_MANAGER = ServiceManager()", "register_transport",
                 "SERVICE_MANAGER.register_socket", "SERVICE_MANAGER.shutdown()", "register_thread",
                 "start_child_process", "register_child_process", "class EventLog", "class Service",
                 "class Session", "class SessionManager", "SESSION_MANAGER = SessionManager()",
                 "SESSION_MANAGER.start_record", "SESSION_MANAGER.finish_record"):
        if word not in src:
            print(f"busierbox-server: service/session manager primitive missing: {word}", file=sys.stderr)
            return 1
    if "OWNED_TRANSPORTS.append(transport)" in src:
        print("busierbox-server: transport ownership bypasses ServiceManager", file=sys.stderr)
        return 1
    if "proc = subprocess.Popen(cmd" in src:
        print("busierbox-server: workbench child process bypasses ServiceManager", file=sys.stderr)
        return 1
    stop_helper = src[src.find("def stop_recorded_service"):src.find("def run_line_tui")]
    if ("managed_server_evidence(pid, cfg=cfg, rec=rec)" not in stop_helper or
            "service_stop_skipped" not in stop_helper or
            "unmanaged-pid" not in stop_helper or
            "workbench-stop" not in stop_helper):
        print("busierbox-server: workbench stop path lacks managed-PID safety guard", file=sys.stderr)
        return 1
    if ("cmdline_option_matches_path" not in src or
            "ownership_evidence" not in src or
            "unmanaged_recorded_pid" not in src):
        print("busierbox-server: PID ownership evidence reporting missing", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        cert_path = Path(tmp) / "shell-server.crt"
        key_path = Path(tmp) / "shell-server.key"
        port1 = free_port()
        port2 = free_port()

        # Test: missing cert/key → server auto-generates them, then runs.
        # Use a high ephemeral port with a short timeout so the server exits
        # cleanly after confirming it started (rather than binding to port 1).
        cfg = Path(tmp) / "server-config.json"
        queue_operator_dir = Path(tmp) / "operator-session-queue"
        cfg.write_text(json.dumps({
            "transport": "tls-shell",
            "listen_host": "127.0.0.1",
            "shell_listen_port": port1,
            "session_root": str(Path(tmp) / "sessions"),
            "operator_session_dir": str(queue_operator_dir),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
        }), encoding="utf-8")
        result = run("scripts/busierbox-server", "--config", str(cfg),
                     "--transport", "tls-shell", "--timeout", "0.05")
        combined = result.stdout + result.stderr
        # The server should have auto-generated the cert and started
        if not cert_path.is_file() or not key_path.is_file():
            print("TLS cert/key were not auto-generated:", file=sys.stderr)
            print(combined, file=sys.stderr)
            return 1
        # Log should mention the generation
        if "Generating" not in combined and "Generated" not in combined and "generating" not in combined:
            print("Server did not report TLS cert generation:", file=sys.stderr)
            print(combined, file=sys.stderr)
            return 1

        command_copy_file = queue_operator_dir / "last-command.txt"
        copied = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-copy-file", str(command_copy_file),
            "--copy-target-command", "1",
        )
        if copied.returncode != 0 or "copied target command 1" not in copied.stdout:
            print("generated target command was not copied/exported", file=sys.stderr)
            print(copied.stdout, file=sys.stderr)
            print(copied.stderr, file=sys.stderr)
            return 1
        copied_text = command_copy_file.read_text(encoding="utf-8")
        if "busierbox put /etc/config/network" not in copied_text:
            print("generated target command copy file has wrong content", file=sys.stderr)
            return 1
        copied_status = json.loads(run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--json-status",
        ).stdout)
        copied_record = copied_status.get("command_copy") or {}
        if (copied_record.get("path") != str(command_copy_file) or
                copied_record.get("has_command") is not True or
                "busierbox put /etc/config/network" not in copied_record.get("command", "") or
                (copied_status.get("target_commands_by_ordinal") or {}).get("1", {}).get("copy_command") != "scripts/busierbox-server --copy-target-command 1" or
                (copied_status.get("target_commands_by_copy_supported") or {}).get("True", [{}])[0].get("ordinal") != 1 or
                copied_status.get("command_copy_records_by_has_command", {}).get("True", [{}])[0].get("path") != str(command_copy_file) or
                copied_status.get("summary", {}).get("command_copy_has_command_count") != 1 or
                copied_status.get("summary", {}).get("target_command_copy_supported_count") != copied_status.get("summary", {}).get("target_command_count")):
            print("json status missing last copied command record", file=sys.stderr)
            print(json.dumps(copied_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        guided_build_config = Path(tmp) / "guided-busierbox.conf"
        guided_build_config.write_text(
            'BB_TARGET_PRESET="native"\n'
            'BB_PAYLOAD_PRESET="survey-core"\n'
            'BB_STATIC_POLICY="static-preferred"\n'
            'BB_NORESIDUE_LEVEL="best-effort"\n'
            'BB_RSHELL_SESSION_POLICY="single"\n'
            'BB_COMMAND_QUEUE_ENABLE="no"\n'
            'BB_COMMAND_QUEUE_POLL_INTERVAL_SEC="5"\n',
            encoding="utf-8",
        )
        listed_build_config = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--list-build-config",
        )
        if (listed_build_config.returncode != 0 or
                "BB_TARGET_PRESET" not in listed_build_config.stdout or
                "BB_NORESIDUE_LEVEL" not in listed_build_config.stdout or
                "BB_COMMAND_QUEUE_POLL_INTERVAL_SEC" not in listed_build_config.stdout or
                "safety: boundary=command-queue control_like=yes explicit_choice=yes" not in listed_build_config.stdout or
                "--set-build-config" not in listed_build_config.stdout):
            print("guided build config listing missing expected fields", file=sys.stderr)
            print(listed_build_config.stdout, file=sys.stderr)
            print(listed_build_config.stderr, file=sys.stderr)
            return 1
        set_build_config = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--set-build-config", "BB_NORESIDUE_LEVEL=aggressive",
            "--set-build-config", "BB_RSHELL_SESSION_POLICY=reconnect",
            "--set-build-config", "BB_COMMAND_QUEUE_POLL_INTERVAL_SEC=10",
            "--set-build-config", "BB_COMMAND_QUEUE_POLL_BACKOFF=linear",
        )
        if (set_build_config.returncode != 0 or
                'BB_NORESIDUE_LEVEL="aggressive"' not in set_build_config.stdout or
                'BB_RSHELL_SESSION_POLICY="reconnect"' not in set_build_config.stdout or
                'BB_COMMAND_QUEUE_POLL_INTERVAL_SEC="10"' not in set_build_config.stdout or
                'BB_COMMAND_QUEUE_POLL_BACKOFF="linear"' not in set_build_config.stdout):
            print("guided build config update failed", file=sys.stderr)
            print(set_build_config.stdout, file=sys.stderr)
            print(set_build_config.stderr, file=sys.stderr)
            return 1
        guided_text = guided_build_config.read_text(encoding="utf-8")
        if ('BB_NORESIDUE_LEVEL="aggressive"' not in guided_text or
                'BB_RSHELL_SESSION_POLICY="reconnect"' not in guided_text or
                'BB_COMMAND_QUEUE_POLL_INTERVAL_SEC="10"' not in guided_text or
                'BB_COMMAND_QUEUE_POLL_BACKOFF="linear"' not in guided_text):
            print("guided build config file was not updated", file=sys.stderr)
            print(guided_text, file=sys.stderr)
            return 1
        guided_status = json.loads(run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--json-status",
        ).stdout)
        guided_fields = guided_status.get("workbench_config_fields") or []
        guided_by_key = guided_status.get("workbench_config_fields_by_key") or {}
        guided_by_category = guided_status.get("workbench_config_fields_by_category") or {}
        guided_fixed = guided_status.get("workbench_config_fields_by_fixed_options") or {}
        guided_writes_config = guided_status.get("workbench_config_fields_by_writes_config") or {}
        guided_target_execution = guided_status.get("workbench_config_fields_by_target_execution") or {}
        guided_source_format = guided_status.get("workbench_config_fields_by_source_format") or {}
        guided_safety = guided_status.get("workbench_config_fields_by_safety_boundary") or {}
        guided_control_like = guided_status.get("workbench_config_fields_by_control_like") or {}
        guided_command_queue = guided_status.get("workbench_config_fields_by_command_queue_related") or {}
        guided_reverse_access = guided_status.get("workbench_config_fields_by_reverse_access_related") or {}
        guided_explicit_choice = guided_status.get("workbench_config_fields_by_requires_explicit_operator_choice") or {}
        if (len(guided_fields) < 12 or
                guided_status.get("summary", {}).get("workbench_config_field_count") != len(guided_fields) or
                guided_by_key.get("BB_NORESIDUE_LEVEL", {}).get("value") != "aggressive" or
                guided_by_key.get("BB_RSHELL_SESSION_POLICY", {}).get("value") != "reconnect" or
                guided_by_key.get("BB_RSHELL_SESSION_POLICY", {}).get("safety_boundary") != "reverse-access" or
                guided_by_key.get("BB_COMMAND_QUEUE_ENABLE", {}).get("control_like") is not True or
                guided_by_key.get("BB_COMMAND_QUEUE_ENABLE", {}).get("requires_explicit_operator_choice") is not True or
                guided_by_key.get("BB_COMMAND_QUEUE_POLL_INTERVAL_SEC", {}).get("value") != "10" or
                guided_by_key.get("BB_COMMAND_QUEUE_POLL_INTERVAL_SEC", {}).get("fixed_options") is not False or
                guided_by_key.get("BB_COMMAND_QUEUE_POLL_BACKOFF", {}).get("options") != ["none", "linear", "exponential"] or
                guided_by_key.get("BB_RSHELL_TRANSPORT", {}).get("options") != ["ssh", "socat", "builtin", "none"] or
                guided_by_key.get("BB_RSHELL_SESSION_POLICY", {}).get("fixed_options") is not True or
                guided_by_key.get("BB_RSHELL_SESSION_POLICY", {}).get("option_count") != 3 or
                guided_status.get("summary", {}).get("workbench_config_field_fixed_option_count", 0) < 17 or
                guided_status.get("summary", {}).get("workbench_config_field_control_like_count", 0) < 16 or
                guided_status.get("summary", {}).get("workbench_config_field_safety_boundary_counts", {}).get("command-queue", 0) < 13 or
                not guided_fixed.get("True") or
                len(guided_writes_config.get("True", [])) != len(guided_fields) or
                guided_target_execution.get("True", []) != [] or
                len(guided_target_execution.get("False", [])) != len(guided_fields) or
                len(guided_source_format.get("shell-assignment", [])) != len(guided_fields) or
                not guided_safety.get("reverse-access") or
                not guided_control_like.get("True") or
                not guided_command_queue.get("True") or
                not guided_reverse_access.get("True") or
                not guided_explicit_choice.get("True") or
                not guided_by_category.get("target") or
                not guided_by_category.get("command-queue") or
                guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("primary_key") != "key" or
                "workbench_config_fields_by_fixed_options" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_target_execution" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_safety_boundary" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", [])):
            print("server json status missing guided build config field records", file=sys.stderr)
            print(json.dumps(guided_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        bad_build_config = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--set-build-config", "BB_RSHELL_SESSION_POLICY=resume",
        )
        if bad_build_config.returncode == 0 or "unsupported value for BB_RSHELL_SESSION_POLICY" not in (bad_build_config.stdout + bad_build_config.stderr):
            print("guided build config accepted invalid fixed-option value", file=sys.stderr)
            print(bad_build_config.stdout, file=sys.stderr)
            print(bad_build_config.stderr, file=sys.stderr)
            return 1
        guided_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(event.get("event") == "workbench_config_updated" and event.get("details", {}).get("key") == "BB_NORESIDUE_LEVEL" for event in guided_events):
            print("guided build config update event missing", file=sys.stderr)
            return 1

        workbench_job_dir = Path(tmp) / "operator-session-workbench-job"
        workbench_job_cfg = Path(tmp) / "server-config-workbench-job.json"
        workbench_job_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(workbench_job_dir),
            "session_root": str(Path(tmp) / "sessions-workbench-job"),
        }), encoding="utf-8")
        started_job = run(
            "scripts/busierbox-server",
            "--config", str(workbench_job_cfg),
            "--start-workbench-job", "package-artifact",
            "--job-command", "printf 'job ready\\n'; sleep 30",
        )
        if started_job.returncode != 0 or "started workbench job" not in started_job.stdout:
            print("workbench background job did not start", file=sys.stderr)
            print(started_job.stdout, file=sys.stderr)
            print(started_job.stderr, file=sys.stderr)
            return 1
        job_id = ""
        for token in started_job.stdout.replace(":", " ").split():
            if token.startswith("job-"):
                job_id = token
                break
        if not job_id:
            print("workbench background job id missing", file=sys.stderr)
            print(started_job.stdout, file=sys.stderr)
            return 1
        job_status = None
        for _ in range(20):
            job_status_doc = run(
                "scripts/busierbox-server",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            job_status = json.loads(job_status_doc.stdout)
            job = (job_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
            if job.get("cancel_supported") is True:
                break
            time.sleep(0.1)
        job = (job_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
        if (job.get("action_id") != "package-artifact" or
                job.get("effective_state") != "running" or
                job.get("cancel_supported") is not True or
                job.get("started_at_known") is not True or
                job.get("finished_at_known") is not False or
                job.get("duration_known") is not False or
                job.get("elapsed_known") is not True or
                "environ:job-id" not in (job.get("ownership_evidence") or []) or
                "environ:action-id" not in (job.get("ownership_evidence") or []) or
                "job ready" not in "\n".join(job.get("last_output_tail") or []) or
                job_status.get("summary", {}).get("workbench_job_running_count") != 1):
            print("workbench background job status missing live managed job", file=sys.stderr)
            print(json.dumps(job_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        cancelled_job = run(
            "scripts/busierbox-server",
            "--config", str(workbench_job_cfg),
            "--cancel-workbench-job", job_id,
        )
        if cancelled_job.returncode != 0 or "cancel requested" not in cancelled_job.stdout:
            print("workbench background job did not cancel", file=sys.stderr)
            print(cancelled_job.stdout, file=sys.stderr)
            print(cancelled_job.stderr, file=sys.stderr)
            return 1
        for _ in range(20):
            cancelled_status_doc = run(
                "scripts/busierbox-server",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            cancelled_status = json.loads(cancelled_status_doc.stdout)
            cancelled = (cancelled_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
            if cancelled.get("effective_state") != "running":
                break
            time.sleep(0.1)
        if (cancelled.get("state") != "cancelling" or
                cancelled.get("cancel_supported") is not False or
                cancelled_status.get("summary", {}).get("workbench_job_cancel_supported_count") != 0):
            print("workbench background job cancellation status missing", file=sys.stderr)
            print(json.dumps(cancelled_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        job_events = [
            json.loads(line)
            for line in (workbench_job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (not any(event.get("event") == "workbench_job_started" and event.get("details", {}).get("job_id") == job_id for event in job_events) or
                not any(event.get("event") == "workbench_job_cancel_requested" and event.get("details", {}).get("job_id") == job_id for event in job_events)):
            print("workbench background job events missing", file=sys.stderr)
            return 1

        quick_job = run(
            "scripts/busierbox-server",
            "--config", str(workbench_job_cfg),
            "--start-workbench-job", "bringup-recommend",
            "--job-command", "printf 'quick job done\\n'; exit 7",
        )
        if quick_job.returncode != 0 or "started workbench job" not in quick_job.stdout:
            print("quick workbench background job did not start", file=sys.stderr)
            print(quick_job.stdout, file=sys.stderr)
            print(quick_job.stderr, file=sys.stderr)
            return 1
        quick_job_id = ""
        for token in quick_job.stdout.replace(":", " ").split():
            if token.startswith("job-"):
                quick_job_id = token
                break
        if not quick_job_id:
            print("quick workbench background job id missing", file=sys.stderr)
            print(quick_job.stdout, file=sys.stderr)
            return 1
        quick_status = None
        for _ in range(30):
            quick_status_doc = run(
                "scripts/busierbox-server",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            quick_status = json.loads(quick_status_doc.stdout)
            quick = (quick_status.get("workbench_jobs_by_id") or {}).get(quick_job_id) or {}
            if quick.get("exit_status_known") is True:
                break
            time.sleep(0.1)
        quick = (quick_status.get("workbench_jobs_by_id") or {}).get(quick_job_id) or {}
        if (quick.get("effective_state") != "exited" or
                quick.get("exit_status") != 7 or
                quick.get("outcome") != "failed" or
                quick.get("finished_at", "") == "" or
                quick.get("completed_event_at", "") == "" or
                quick.get("started_at_known") is not True or
                quick.get("finished_at_known") is not True or
                quick.get("duration_known") is not True or
                quick.get("elapsed_known") is not True or
                quick.get("last_output_tail", [])[-1:] != ["quick job done"] or
                quick_status.get("summary", {}).get("workbench_job_exit_status_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_started_at_known_count", 0) < 2 or
                quick_status.get("summary", {}).get("workbench_job_finished_at_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_duration_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_elapsed_known_count", 0) < 2 or
                quick_status.get("summary", {}).get("workbench_job_outcome_counts", {}).get("failed", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_exit_status_counts", {}).get("7", 0) < 1 or
                (quick_status.get("workbench_jobs_by_duration_known") or {}).get("True", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_finished_at_known") or {}).get("True", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_outcome") or {}).get("failed", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_exit_status") or {}).get("7", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("event_log_stats") or {}).get("by_event", {}).get("workbench_job_completed", 0) != 1):
            print("completed workbench background job missing exit metadata", file=sys.stderr)
            print(json.dumps(quick_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        quick_text = run(
            "scripts/busierbox-server",
            "--config", str(workbench_job_cfg),
            "--status",
        )
        if ("exit_status=7 outcome=failed" not in quick_text.stdout or
                "exit_status_known=" not in quick_text.stdout or
                "duration_known=" not in quick_text.stdout or
                "elapsed_known=" not in quick_text.stdout or
                "duration_sec=" not in quick_text.stdout or
                "managed=" not in quick_text.stdout or
                "background=" not in quick_text.stdout or
                "long_running=" not in quick_text.stdout or
                "cancel: disabled; process is not alive" not in quick_text.stdout or
                "outcomes:" not in quick_text.stdout):
            print("text status missing completed workbench job exit metadata", file=sys.stderr)
            print(quick_text.stdout, file=sys.stderr)
            return 1
        quick_events = [
            json.loads(line)
            for line in (workbench_job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        completion_events = [
            event for event in quick_events
            if event.get("event") == "workbench_job_completed" and event.get("details", {}).get("job_id") == quick_job_id
        ]
        if (len(completion_events) != 1 or
                completion_events[0].get("details", {}).get("exit_status") != 7 or
                completion_events[0].get("details", {}).get("outcome") != "failed"):
            print("completed workbench background job event missing or duplicated", file=sys.stderr)
            print(json.dumps(quick_events, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        forged_dir = Path(tmp) / "operator-session-forged-job"
        forged_cfg = Path(tmp) / "server-config-forged-job.json"
        forged_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(forged_dir),
            "session_root": str(Path(tmp) / "sessions-forged-job"),
        }), encoding="utf-8")
        forged_dir.mkdir(parents=True, exist_ok=True)
        (forged_dir / "workbench-jobs.json").write_text(json.dumps({
            "schema": 1,
            "jobs": [{
                "id": "job-forged",
                "action_id": "package-artifact",
                "state": "running",
                "pid": os.getpid(),
                "managed_by": "busierbox-server-workbench",
                "started_at": "2026-01-01T00:00:00Z",
            }],
        }), encoding="utf-8")
        forged_status = json.loads(run(
            "scripts/busierbox-server",
            "--config", str(forged_cfg),
            "--json-status",
        ).stdout)
        forged_job = (forged_status.get("workbench_jobs_by_id") or {}).get("job-forged") or {}
        if forged_job.get("cancel_supported") is not False or forged_job.get("pid_managed") is not False:
            print("forged workbench job ledger was treated as cancellable", file=sys.stderr)
            print(json.dumps(forged_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        forged_text = run(
            "scripts/busierbox-server",
            "--config", str(forged_cfg),
            "--status",
        )
        if ("job job-forged" not in forged_text.stdout or
                "managed=no cancel_supported=no" not in forged_text.stdout or
                "ownership: ledger:managed-by-workbench" not in forged_text.stdout or
                "cancel: disabled; ownership unverified" not in forged_text.stdout):
            print("text status missing forged workbench job ownership warning", file=sys.stderr)
            print(forged_text.stdout, file=sys.stderr)
            return 1
        forged_cancel = run(
            "scripts/busierbox-server",
            "--config", str(forged_cfg),
            "--cancel-workbench-job", "job-forged",
        )
        if forged_cancel.returncode == 0 or "not cancellable" not in (forged_cancel.stdout + forged_cancel.stderr):
            print("forged workbench job cancellation was not rejected", file=sys.stderr)
            print(forged_cancel.stdout, file=sys.stderr)
            print(forged_cancel.stderr, file=sys.stderr)
            return 1

        isolated_operator_dir = Path(tmp) / "isolated-operator-session"
        isolated_cfg = Path(tmp) / "server-config-isolated-operator-dir.json"
        isolated_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(isolated_operator_dir),
            "session_root": str(Path(tmp) / "isolated-sessions"),
        }), encoding="utf-8")
        isolated_status = run(
            "scripts/busierbox-server",
            "--config", str(isolated_cfg),
            "--json-status",
        )
        isolated_doc = json.loads(isolated_status.stdout)
        isolated_paths = isolated_doc.get("paths") or {}
        expected_isolated = {
            "state_file": isolated_operator_dir / "server-state.json",
            "staged_files": isolated_operator_dir / "staged-files.json",
            "command_queue_file": isolated_operator_dir / "command-queue.json",
            "command_copy_file": isolated_operator_dir / "last-command.txt",
            "event_log": isolated_operator_dir / "events.jsonl",
        }
        if any(isolated_paths.get(key) != str(path) for key, path in expected_isolated.items()):
            print("operator_session_dir did not derive isolated operator paths", file=sys.stderr)
            print(isolated_status.stdout, file=sys.stderr)
            return 1
        isolated_workbench = run(
            "scripts/busierbox-server",
            "--config", str(isolated_cfg),
            "--tui",
        )
        if (str(expected_isolated["staged_files"]) not in isolated_workbench.stdout or
                str(expected_isolated["command_queue_file"]) not in isolated_workbench.stdout or
                str(expected_isolated["command_copy_file"]) not in isolated_workbench.stdout):
            print("workbench did not show isolated operator paths", file=sys.stderr)
            print(isolated_workbench.stdout, file=sys.stderr)
            return 1

        mismatched_copy_path = Path(tmp) / "command-copy-is-directory"
        mismatched_copy_path.mkdir()
        path_mismatch_cfg = Path(tmp) / "server-config-path-mismatch.json"
        path_mismatch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(Path(tmp) / "operator-session-path-mismatch"),
            "session_root": str(Path(tmp) / "path-mismatch-sessions"),
            "command_copy_file": str(mismatched_copy_path),
        }), encoding="utf-8")
        path_mismatch_status = run(
            "scripts/busierbox-server",
            "--config", str(path_mismatch_cfg),
            "--json-status",
        )
        path_mismatch_doc = json.loads(path_mismatch_status.stdout)
        path_mismatch_rec = (path_mismatch_doc.get("path_status") or {}).get("command_copy_file") or {}
        path_mismatch_browser_rec = (
            path_mismatch_doc.get("browser_paths_by_path", {}).get(str(mismatched_copy_path)) or [{}]
        )[0]
        path_mismatch_warnings = [
            item for item in path_mismatch_doc.get("warnings", [])
            if item.get("type") == "operator_path_kind_mismatch"
        ]
        if (path_mismatch_rec.get("expected_kind") != "file" or
                path_mismatch_rec.get("expected_kind_mismatch") is not True or
                path_mismatch_rec.get("is_dir") is not True or
                path_mismatch_rec.get("warning_count") != 1 or
                "operator_path_kind_mismatch" not in path_mismatch_rec.get("warning_types", []) or
                path_mismatch_browser_rec.get("warning_count") != 1 or
                "operator_path_kind_mismatch" not in path_mismatch_browser_rec.get("warning_types", []) or
                path_mismatch_doc.get("summary", {}).get("path_kind_mismatch_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_kind_mismatch_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_kind_mismatch_counts", {}).get("command-copy") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("command-copy") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_type_counts", {}).get("operator_path_kind_mismatch") != 1 or
                path_mismatch_doc.get("browser_path_summary", {}).get("warning_count") != 1 or
                path_mismatch_doc.get("browser_path_summary", {}).get("warning_by_kind", {}).get("command-copy") != 1 or
                not path_mismatch_warnings or
                path_mismatch_warnings[-1].get("path_name") != "command_copy_file" or
                path_mismatch_warnings[-1].get("path") != str(mismatched_copy_path) or
                path_mismatch_doc.get("summary", {}).get("warning_type_counts", {}).get("operator_path_kind_mismatch") != 1 or
                path_mismatch_doc.get("summary", {}).get("warning_path_counts", {}).get(str(mismatched_copy_path)) != 1 or
                path_mismatch_doc.get("summary", {}).get("warning_type_path_counts", {}).get(f"operator_path_kind_mismatch:{mismatched_copy_path}") != 1 or
                path_mismatch_doc.get("warnings_by_path", {}).get(str(mismatched_copy_path), [{}])[-1].get("type") != "operator_path_kind_mismatch" or
                path_mismatch_doc.get("warnings_by_type_path", {}).get(f"operator_path_kind_mismatch:{mismatched_copy_path}", [{}])[-1].get("path") != str(mismatched_copy_path)):
            print("server json status missing operator path kind mismatch warning", file=sys.stderr)
            print(path_mismatch_status.stdout, file=sys.stderr)
            return 1
        path_mismatch_text = run(
            "scripts/busierbox-server",
            "--config", str(path_mismatch_cfg),
            "--status",
        )
        if ("operator path kind mismatch:" not in path_mismatch_text.stdout or
                f"{mismatched_copy_path} expected=file actual=dir" not in path_mismatch_text.stdout):
            print("text --status missing operator path kind mismatch warning", file=sys.stderr)
            print(path_mismatch_text.stdout, file=sys.stderr)
            return 1

        invalid_state_dir = Path(tmp) / "operator-session-invalid-state"
        invalid_state_dir.mkdir()
        invalid_state_file = invalid_state_dir / "server-state.json"
        invalid_staged_file = invalid_state_dir / "staged-files.json"
        invalid_queue_file = invalid_state_dir / "command-queue.json"
        invalid_state_file.write_text("{not-json\n", encoding="utf-8")
        invalid_staged_file.write_text("[]\n", encoding="utf-8")
        invalid_queue_file.write_text('{"schema":1,"commands":{}}\n', encoding="utf-8")
        invalid_state_cfg = Path(tmp) / "server-config-invalid-state.json"
        invalid_state_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(invalid_state_dir),
            "server_state": str(invalid_state_file),
            "staged_files": str(invalid_staged_file),
            "command_queue_file": str(invalid_queue_file),
            "session_root": str(Path(tmp) / "invalid-state-sessions"),
        }), encoding="utf-8")
        invalid_state_status = run(
            "scripts/busierbox-server",
            "--config", str(invalid_state_cfg),
            "--json-status",
        )
        invalid_state_doc = json.loads(invalid_state_status.stdout)
        invalid_state_path_status = invalid_state_doc.get("path_status") or {}
        invalid_state_browser_by_path = invalid_state_doc.get("browser_paths_by_path") or {}
        invalid_warning_types = invalid_state_doc.get("summary", {}).get("warning_type_counts", {})
        invalid_warning_paths = invalid_state_doc.get("summary", {}).get("warning_path_counts", {})
        invalid_warning_type_paths = invalid_state_doc.get("summary", {}).get("warning_type_path_counts", {})
        invalid_warnings_by_type = invalid_state_doc.get("warnings_by_type") or {}
        invalid_warnings_by_path = invalid_state_doc.get("warnings_by_path") or {}
        invalid_warnings_by_type_path = invalid_state_doc.get("warnings_by_type_path") or {}
        invalid_path_api = (invalid_state_doc.get("api_collections") or {}).get("path_status_records") or {}
        invalid_browser_api = (invalid_state_doc.get("api_collections") or {}).get("browser_paths") or {}
        if (invalid_state_doc.get("summary", {}).get("server_state_valid") is not False or
                invalid_state_doc.get("summary", {}).get("staged_files_valid") is not False or
                invalid_state_doc.get("summary", {}).get("command_queue_file_valid") is not False or
                invalid_warning_types.get("invalid_server_state") != 1 or
                invalid_warning_types.get("invalid_staged_files_state") != 1 or
                invalid_warning_types.get("invalid_command_queue_state") != 1 or
                invalid_warning_paths.get(str(invalid_state_file)) != 1 or
                invalid_warning_paths.get(str(invalid_staged_file)) != 1 or
                invalid_warning_paths.get(str(invalid_queue_file)) != 1 or
                invalid_warning_type_paths.get(f"invalid_server_state:{invalid_state_file}") != 1 or
                invalid_warning_type_paths.get(f"invalid_staged_files_state:{invalid_staged_file}") != 1 or
                invalid_warning_type_paths.get(f"invalid_command_queue_state:{invalid_queue_file}") != 1 or
                invalid_state_path_status.get("state_file", {}).get("warning_count") != 1 or
                invalid_state_path_status.get("staged_files", {}).get("warning_count") != 1 or
                invalid_state_path_status.get("command_queue_file", {}).get("warning_count") != 1 or
                "invalid_server_state" not in invalid_state_path_status.get("state_file", {}).get("warning_types", []) or
                "invalid_staged_files_state" not in invalid_state_path_status.get("staged_files", {}).get("warning_types", []) or
                "invalid_command_queue_state" not in invalid_state_path_status.get("command_queue_file", {}).get("warning_types", []) or
                invalid_state_doc.get("path_status_by_has_warnings", {}).get("yes", [{}])[0].get("name") != "state_file" or
                invalid_state_doc.get("path_status_by_warning_type", {}).get("invalid_server_state", [{}])[0].get("name") != "state_file" or
                invalid_state_doc.get("summary", {}).get("path_warning_count") != 3 or
                invalid_state_doc.get("summary", {}).get("path_warning_type_counts", {}).get("invalid_server_state") != 1 or
                invalid_state_browser_by_path.get(str(invalid_state_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_browser_by_path.get(str(invalid_staged_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_browser_by_path.get(str(invalid_queue_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_doc.get("browser_paths_by_has_warnings", {}).get("yes", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_state_doc.get("browser_paths_by_warning_type", {}).get("invalid_server_state", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_count") != 3 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("server-state") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("staged-ledger") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("command-queue-ledger") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_type_counts", {}).get("invalid_server_state") != 1 or
                invalid_state_doc.get("browser_path_summary", {}).get("warning_count") != 3 or
                invalid_warnings_by_type.get("invalid_server_state", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_warnings_by_type.get("invalid_staged_files_state", [{}])[0].get("path") != str(invalid_staged_file) or
                invalid_warnings_by_type.get("invalid_command_queue_state", [{}])[0].get("path") != str(invalid_queue_file) or
                invalid_warnings_by_path.get(str(invalid_state_file), [{}])[0].get("type") != "invalid_server_state" or
                invalid_warnings_by_path.get(str(invalid_staged_file), [{}])[0].get("type") != "invalid_staged_files_state" or
                invalid_warnings_by_path.get(str(invalid_queue_file), [{}])[0].get("type") != "invalid_command_queue_state" or
                invalid_warnings_by_type_path.get(f"invalid_server_state:{invalid_state_file}", [{}])[0].get("path") != str(invalid_state_file) or
                "path_status_by_has_warnings" not in (invalid_path_api.get("indexes") or []) or
                "path_status_by_warning_type" not in (invalid_path_api.get("indexes") or []) or
                "browser_paths_by_has_warnings" not in (invalid_browser_api.get("indexes") or []) or
                "browser_paths_by_warning_type" not in (invalid_browser_api.get("indexes") or [])):
            print("server json status missing invalid operator state warnings", file=sys.stderr)
            print(invalid_state_status.stdout, file=sys.stderr)
            return 1
        invalid_state_text = run(
            "scripts/busierbox-server",
            "--config", str(invalid_state_cfg),
            "--status",
        )
        if ("server-state ledger is invalid" not in invalid_state_text.stdout or
                "staged-files ledger is invalid" not in invalid_state_text.stdout or
                "command queue ledger is invalid" not in invalid_state_text.stdout):
            print("text --status missing invalid operator state warnings", file=sys.stderr)
            print(invalid_state_text.stdout, file=sys.stderr)
            return 1

        queue_file = queue_operator_dir / "command-queue.json"
        queued = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "busierbox reality-test --json",
            "--queue-timeout", "9",
            "--queue-max-output", "1234",
        )
        if queued.returncode != 0 or "execution_supported=no" not in queued.stdout:
            print("operator command queue entry was not recorded safely", file=sys.stderr)
            print(queued.stdout, file=sys.stderr)
            print(queued.stderr, file=sys.stderr)
            return 1
        queue_doc = json.loads(queue_file.read_text(encoding="utf-8"))
        if (len(queue_doc.get("commands", [])) != 1 or
                queue_doc["commands"][0].get("command") != "busierbox reality-test --json" or
                queue_doc["commands"][0].get("execution_supported") is not False or
                queue_doc["commands"][0].get("delivery_supported") is not False):
            print("operator command queue JSON missing non-exec safety fields", file=sys.stderr)
            return 1
        bad_queue_timeout = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "busierbox survey",
            "--queue-timeout", "0",
        )
        if bad_queue_timeout.returncode == 0 or "timeout must be a positive integer" not in bad_queue_timeout.stderr:
            print("operator command queue accepted invalid timeout", file=sys.stderr)
            print(bad_queue_timeout.stdout, file=sys.stderr)
            print(bad_queue_timeout.stderr, file=sys.stderr)
            return 1
        bad_queue_output = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "busierbox survey",
            "--queue-max-output", "0",
        )
        if bad_queue_output.returncode == 0 or "max output must be a positive integer" not in bad_queue_output.stderr:
            print("operator command queue accepted invalid max output", file=sys.stderr)
            print(bad_queue_output.stdout, file=sys.stderr)
            print(bad_queue_output.stderr, file=sys.stderr)
            return 1
        queue_doc_after_bad = json.loads(queue_file.read_text(encoding="utf-8"))
        if len(queue_doc_after_bad.get("commands", [])) != 1:
            print("invalid command queue entries were persisted", file=sys.stderr)
            return 1
        unique_queue_file = Path(tmp) / "operator-session" / "unique-command-queue.json"
        unique_queue = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.machinery, importlib.util, json, pathlib, sys; "
                    "p=pathlib.Path(sys.argv[1]); "
                    "loader=importlib.machinery.SourceFileLoader('srv', str(p)); "
                    "spec=importlib.util.spec_from_loader('srv', loader); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "cfg=m.load_config(sys.argv[2]); cfg['command_queue_file']=sys.argv[3]; "
                    "a=m.queue_command(cfg, 'busierbox survey'); "
                    "b=m.queue_command(cfg, 'busierbox survey'); "
                    "print(json.dumps([a['id'], b['id']]))"
                ),
                str(server),
                str(cfg),
                str(unique_queue_file),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if unique_queue.returncode != 0:
            print("same-process command queue uniqueness smoke failed", file=sys.stderr)
            print(unique_queue.stdout, file=sys.stderr)
            print(unique_queue.stderr, file=sys.stderr)
            return 1
        unique_ids = json.loads(unique_queue.stdout)
        if len(unique_ids) != 2 or unique_ids[0] == unique_ids[1]:
            print("same-process command queue entries received duplicate ids", file=sys.stderr)
            print(unique_queue.stdout, file=sys.stderr)
            return 1
        queue_list = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-command-queue",
        )
        queue_status = json.loads(queue_list.stdout)
        if queue_status["command_queue"]["queued_count"] != 1:
            print("json command queue listing missing queued entry", file=sys.stderr)
            return 1
        queue_summary = queue_status["command_queue"]
        queued_id = queue_summary["commands"][0]["id"]
        queued_policy = queue_summary["commands"][0].get("queue_policy_snapshot") or {}
        if (queue_summary.get("commands_by_id", {}).get(queued_id, {}).get("command") != "busierbox reality-test --json" or
                len(queue_summary.get("commands_by_status", {}).get("queued", [])) != 1 or
                queue_summary["commands_by_status"]["queued"][0].get("id") != queued_id or
                queue_summary.get("commands_by_timeout_sec", {}).get("9", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_max_output_bytes", {}).get("1234", [{}])[0].get("id") != queued_id or
                queue_summary.get("timeout_sec_counts", {}).get("9") != 1 or
                queue_summary.get("max_output_bytes_counts", {}).get("1234") != 1 or
                queue_summary.get("commands_by_queue_policy_enabled", {}).get("false", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_valid", {}).get("true", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_execution_mode", {}).get("metadata-only", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_allowed_commands", {}).get("none", [{}])[0].get("id") != queued_id or
                queue_summary.get("queue_policy_enabled_counts", {}).get("false") != 1 or
                queue_summary.get("queue_policy_valid_counts", {}).get("true") != 1 or
                queue_summary.get("queue_policy_execution_mode_counts", {}).get("metadata-only") != 1 or
                queue_summary.get("queue_policy_allowed_commands_counts", {}).get("none") != 1 or
                queue_summary.get("latest_created_at") != queue_summary["commands"][0].get("created_at") or
                queue_summary.get("latest_result_received_at") != ""):
            print("json command queue listing missing command lookup indexes", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        if (queued_policy.get("enabled") is not False or
                queued_policy.get("valid") is not True or
                queued_policy.get("allowed_commands") != "none" or
                queued_policy.get("execution_mode") != "metadata-only" or
                queued_policy.get("execution_supported") is not False or
                queued_policy.get("executes_commands") is not False or
                queued_policy.get("delivery_supported") is not False or
                queued_policy.get("result_upload_supported") is not True or
                queued_policy.get("active_control_channel") is not False or
                queued_policy.get("arbitrary_execution_allowed") is not False or
                queued_policy.get("operator_queue_records_only") is not True):
            print("queued command missing policy snapshot", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        if (queue_summary.get("enabled") != "no" or
                queue_summary.get("default_enabled") is not False or
                queue_summary.get("allowed_commands") != "none" or
                queue_summary.get("execution_mode") != "metadata-only" or
                queue_summary.get("metadata_only_default") is not True or
                queue_summary.get("allow_arbitrary") != "no" or
                queue_summary.get("policy_valid") is not True or
                queue_summary.get("policy_errors") != [] or
                queue_summary.get("arbitrary_policy_requested") is not False or
                queue_summary.get("arbitrary_execution_allowed") is not False or
                queue_summary.get("poll_interval_sec") != "5" or
                queue_summary.get("poll_jitter_pct") != "0" or
                queue_summary.get("poll_backoff") != "none" or
                queue_summary.get("poll_max_interval_sec") != "300" or
                queue_summary.get("max_polls") != "0" or
                queue_summary.get("poll_transport_supported") is not True or
                queue_summary.get("live_polling_supported") is not True or
                queue_summary.get("delivery_supported") is not False or
                queue_summary.get("result_upload_supported") is not True or
                queue_summary.get("executes_commands") is not False or
                queue_summary.get("operator_queue_records_only") is not True or
                queue_summary.get("active_control_channel") is not False):
            print("json command queue listing missing explicit safety policy", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        queue_policy_summary = queue_summary.get("policy_summary") or {}
        if (queue_policy_summary.get("safe_disabled_default") is not True or
                queue_policy_summary.get("operator_queue_records_only") is not True or
                queue_policy_summary.get("execution_mode") != "metadata-only" or
                queue_policy_summary.get("metadata_only_default") is not True or
                queue_policy_summary.get("execution_supported") is not False or
                queue_policy_summary.get("result_upload_supported") is not True or
                queue_policy_summary.get("poll_transport_supported") is not True or
                queue_policy_summary.get("live_polling_supported") is not True or
                queue_policy_summary.get("poll_interval_sec") != "5" or
                queue_policy_summary.get("poll_jitter_pct") != "0" or
                queue_policy_summary.get("poll_backoff") != "none" or
                queue_policy_summary.get("poll_max_interval_sec") != "300" or
                queue_policy_summary.get("max_polls") != "0" or
                queue_policy_summary.get("active_control_channel") is not False or
                queue_policy_summary.get("error_count") != 0):
            print("json command queue listing missing compact policy summary", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        queue_modes = queue_summary.get("mode_semantics") or {}
        queue_mode_summary = queue_summary.get("mode_summary") or {}
        if (queue_modes.get("status", {}).get("lifecycle") != "inspect" or
                queue_modes.get("poll", {}).get("lifecycle") != "single-poll" or
                queue_modes.get("once", {}).get("lifecycle") != "single-cycle" or
                queue_modes.get("daemon", {}).get("lifecycle") != "long-running" or
                queue_modes.get("stop", {}).get("lifecycle") != "stop" or
                queue_modes.get("stop", {}).get("requires_operator_host") is not False or
                queue_modes.get("stop", {}).get("would_poll_if_configured") is not False or
                queue_modes.get("daemon", {}).get("dry_run_default") is not True or
                queue_modes.get("daemon", {}).get("dry_run_only") is not False or
                queue_modes.get("daemon", {}).get("live_supported") is not True or
                queue_modes.get("daemon", {}).get("live_would_contact_operator") is not True or
                queue_modes.get("daemon", {}).get("execution_supported") is not False or
                queue_modes.get("daemon", {}).get("active_control_channel") is not False or
                queue_mode_summary.get("mode_count") != 5 or
                queue_mode_summary.get("polling_mode_count") != 3 or
                queue_mode_summary.get("live_supported_mode_count") != 3 or
                queue_mode_summary.get("result_upload_supported_mode_count") != 5 or
                queue_mode_summary.get("execution_supported_mode_count") != 0):
            print("json command queue listing missing mode semantics", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        invalid_queue_cfg = Path(tmp) / "server-config-invalid-command-queue.json"
        invalid_queue_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "command_queue_file": str(queue_file),
            "command_queue_enable": "no",
            "command_queue_allowed_commands": "busierbox-only",
            "command_queue_allow_arbitrary": "yes",
        }), encoding="utf-8")
        invalid_queue_list = run(
            "scripts/busierbox-server",
            "--config", str(invalid_queue_cfg),
            "--json-command-queue",
        )
        if invalid_queue_list.returncode != 0:
            print("invalid command queue policy listing failed", file=sys.stderr)
            print(invalid_queue_list.stderr, file=sys.stderr)
            return 1
        invalid_queue_summary = json.loads(invalid_queue_list.stdout)["command_queue"]
        invalid_queue_policy_summary = invalid_queue_summary.get("policy_summary") or {}
        if (invalid_queue_summary.get("policy_valid") is not False or
                "disabled command queue must keep allowed commands policy none" not in invalid_queue_summary.get("policy_errors", []) or
                "disabled command queue must not allow arbitrary execution" not in invalid_queue_summary.get("policy_errors", []) or
                invalid_queue_summary.get("configured_for_polling") is not False or
                invalid_queue_summary.get("arbitrary_policy_requested") is not False or
                invalid_queue_summary.get("arbitrary_execution_allowed") is not False or
                invalid_queue_summary.get("active_control_channel") is not False or
                invalid_queue_summary.get("executes_commands") is not False or
                invalid_queue_policy_summary.get("valid") is not False or
                invalid_queue_policy_summary.get("safe_disabled_default") is not False or
                invalid_queue_policy_summary.get("error_count") != len(invalid_queue_summary.get("policy_errors", []))):
            print("invalid command queue policy was not reported safely", file=sys.stderr)
            print(invalid_queue_list.stdout, file=sys.stderr)
            return 1
        invalid_queue_text = run(
            "scripts/busierbox-server",
            "--config", str(invalid_queue_cfg),
            "--list-command-queue",
        )
        if (invalid_queue_text.returncode != 0 or
                "policy_valid=no" not in invalid_queue_text.stdout or
                "arbitrary_execution_allowed=no" not in invalid_queue_text.stdout or
                "modes: total=5 would_poll_if_configured=3 operator_host_required=3 delivery_supported=0 result_upload_supported=5 execution_supported=0 active_control_channel=0" not in invalid_queue_text.stdout or
                "mode daemon: lifecycle=long-running requires_operator_host=yes would_poll_if_configured=yes execution_supported=no active_control_channel=no" not in invalid_queue_text.stdout or
                "mode stop: lifecycle=stop requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in invalid_queue_text.stdout or
                "policy_error=disabled command queue must keep allowed commands policy none" not in invalid_queue_text.stdout):
            print("invalid command queue text listing missing policy errors", file=sys.stderr)
            print(invalid_queue_text.stdout, file=sys.stderr)
            print(invalid_queue_text.stderr, file=sys.stderr)
            return 1
        command_id = queue_status["command_queue"]["commands"][0]["id"]
        mismatched_result_json = Path(tmp) / "command-result-mismatch.json"
        mismatched_result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": "cq-wrong",
            "status": "completed",
            "exit_code": 0,
        }) + "\n", encoding="utf-8")
        mismatched_result = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--record-command-result", command_id,
            "--result-json", str(mismatched_result_json),
        )
        if mismatched_result.returncode == 0 or "command result id mismatch" not in mismatched_result.stderr:
            print("operator command queue accepted mismatched result id", file=sys.stderr)
            print(mismatched_result.stdout, file=sys.stderr)
            print(mismatched_result.stderr, file=sys.stderr)
            return 1
        queue_after_mismatch = json.loads(queue_file.read_text(encoding="utf-8"))
        if queue_after_mismatch["commands"][0].get("status") != "queued":
            print("mismatched command result changed queue state", file=sys.stderr)
            return 1
        result_json = Path(tmp) / "command-result.json"
        result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": command_id,
            "status": "completed",
            "exit_code": 0,
            "stdout_bytes": 12,
            "stderr_bytes": 0,
        }) + "\n", encoding="utf-8")
        recorded_result = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--record-command-result", command_id,
            "--result-json", str(result_json),
        )
        if recorded_result.returncode != 0 or "recorded result" not in recorded_result.stdout:
            print("operator command queue result was not recorded", file=sys.stderr)
            print(recorded_result.stdout, file=sys.stderr)
            print(recorded_result.stderr, file=sys.stderr)
            return 1
        queue_after_result = json.loads(queue_file.read_text(encoding="utf-8"))
        command_after_result = queue_after_result["commands"][0]
        if (command_after_result.get("status") != "result-received" or
                command_after_result.get("result", {}).get("exit_code") != 0 or
                command_after_result.get("result_command_id") != command_id or
                not command_after_result.get("result_received_at") or
                command_after_result.get("result_output_bytes") != 12 or
                command_after_result.get("result_output_limit_bytes") != 1234 or
                command_after_result.get("result_output_exceeded_limit") is not False):
            print("operator command queue result metadata missing", file=sys.stderr)
            return 1
        event_log = queue_operator_dir / "events.jsonl"
        result_events = [
            json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()
            if "command_result_received" in line
        ]
        if (not result_events or
                result_events[-1].get("details", {}).get("command_id") != command_id or
                result_events[-1].get("details", {}).get("output_bytes") != 12 or
                result_events[-1].get("details", {}).get("output_limit_bytes") != 1234 or
                result_events[-1].get("details", {}).get("output_exceeded_limit") is not False):
            print("operator command queue result event missing command id", file=sys.stderr)
            return 1

        result_port = free_port()
        http_queue_dir = Path(tmp) / "operator-session-command-result-http"
        http_queue_file = http_queue_dir / "command-queue.json"
        http_result_cfg = Path(tmp) / "server-config-command-result-http.json"
        http_result_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(http_queue_dir),
            "command_queue_file": str(http_queue_file),
            "command_queue_enable": "yes",
            "command_queue_tls": "no",
            "command_queue_port": str(result_port),
            "command_queue_require_token": "no",
            "command_queue_allowed_commands": "busierbox-only",
            "command_queue_allow_arbitrary": "no",
        }), encoding="utf-8")
        http_queued = run(
            "scripts/busierbox-server",
            "--config", str(http_result_cfg),
            "--queue-command", "busierbox survey --json",
            "--queue-timeout", "3",
            "--queue-max-output", "10",
        )
        if http_queued.returncode != 0:
            print("http result queue command setup failed", file=sys.stderr)
            print(http_queued.stderr, file=sys.stderr)
            return 1
        http_command_id = json.loads(http_queue_file.read_text(encoding="utf-8"))["commands"][0]["id"]
        http_server = subprocess.Popen(
            ["scripts/busierbox-server", "--config", str(http_result_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        http_result = json.dumps({
            "schema": 1,
            "command_id": http_command_id,
            "status": "completed",
            "exit_code": 7,
            "stdout_bytes": 9,
            "stderr_bytes": 2,
        }).encode("utf-8")
        request = (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(http_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + http_result
        )
        response = connect_with_retry(result_port, request)
        http_stdout, http_stderr = http_server.communicate(timeout=15)
        if http_server.returncode != 0 or b"HTTP/1.1 200 OK" not in response or b'"status": "result-received"' not in response:
            print("command queue HTTP result upload failed", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(http_stdout, file=sys.stderr)
            print(http_stderr, file=sys.stderr)
            return 1
        http_queue = json.loads(http_queue_file.read_text(encoding="utf-8"))
        http_command = http_queue["commands"][0]
        if (http_command.get("status") != "result-received" or
                http_command.get("result", {}).get("exit_code") != 7 or
                http_command.get("result_output_bytes") != 11 or
                http_command.get("result_output_limit_bytes") != 10 or
                http_command.get("result_output_exceeded_limit") is not True or
                not str(http_command.get("result_source_path", "")).startswith("http:")):
            print("command queue HTTP result metadata missing", file=sys.stderr)
            print(json.dumps(http_command, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        http_events = [
            json.loads(line)
            for line in (http_queue_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (not any(event.get("event") == "command_result_received" and event.get("details", {}).get("command_id") == http_command_id for event in http_events) or
                not any(event.get("event") == "command_queue_result_upload" and event.get("details", {}).get("result_output_exceeded_limit") is True for event in http_events)):
            print("command queue HTTP result events missing", file=sys.stderr)
            return 1

        workbench_jobs_file = queue_operator_dir / "workbench-jobs.json"
        workbench_job_log = queue_operator_dir / "package-job.log"
        workbench_job_log.write_text(
            "\n".join([f"line {idx}" for idx in range(1, 25)] + ["package complete"]) + "\n",
            encoding="utf-8",
        )
        workbench_jobs_file.write_text(json.dumps({
            "schema": 1,
            "jobs": [
                {
                    "id": "job-smoke",
                    "action_id": "package-artifact",
                    "command": "make package",
                    "state": "running",
                    "pid": 999999,
                    "managed_by": "workbench-smoke",
                    "started_at": "2026-05-28T00:00:00Z",
                    "log_path": str(workbench_job_log),
                }
            ],
        }) + "\n", encoding="utf-8")

        queue_status_doc = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-status",
        )
        queue_status_json = json.loads(queue_status_doc.stdout)
        if (queue_status_json["command_queue"]["result_count"] != 1 or
                queue_status_json["command_queue"].get("result_output_exceeded_count") != 0 or
                queue_status_json["command_queue"].get("result_status_counts", {}).get("completed") != 1 or
                queue_status_json["command_queue"].get("result_exit_code_counts", {}).get("0") != 1 or
                queue_status_json["command_queue"].get("result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_status_counts", {}).get("completed") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_exit_code_counts", {}).get("0") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json["command_queue"].get("latest_created_at") != command_after_result.get("created_at") or
                queue_status_json["command_queue"].get("latest_result_received_at") != command_after_result.get("result_received_at")):
            print("server json status missing command queue summary", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        status_queue = queue_status_json["command_queue"]
        if (status_queue.get("enabled") != "no" or
                status_queue.get("policy_valid") is not True or
                status_queue.get("policy_errors") != [] or
                status_queue.get("configured_for_polling") is not False or
                status_queue.get("arbitrary_policy_requested") is not False or
                status_queue.get("arbitrary_execution_allowed") is not False or
                status_queue.get("active_control_channel") is not False or
                status_queue.get("executes_commands") is not False):
            print("server json status missing command queue safety policy", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (status_queue.get("commands_by_id", {}).get(command_id, {}).get("status") != "result-received" or
                len(status_queue.get("commands_by_status", {}).get("result-received", [])) != 1 or
                status_queue.get("commands_by_result_status", {}).get("completed", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_exit_code", {}).get("0", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_output_exceeded", {}).get("no", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_output_size_bucket", {}).get("small", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_timeout_sec", {}).get("9", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_max_output_bytes", {}).get("1234", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_id", {}).get(command_id, {}).get("result_output_size_bucket") != "small" or
                queue_status_json.get("summary", {}).get("command_queue_timeout_sec_counts", {}).get("9") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_max_output_bytes_counts", {}).get("1234") != 1 or
                "commands_by_timeout_sec" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_max_output_bytes" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_result_output_size_bucket" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                status_queue.get("status_counts", {}).get("result-received") != 1):
            print("server json status missing command queue lookup indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_queue_status_doc = run(
            "scripts/busierbox-server",
            "--config", str(invalid_queue_cfg),
            "--json-status",
        )
        invalid_queue_status = json.loads(invalid_queue_status_doc.stdout)
        invalid_status_queue = invalid_queue_status["command_queue"]
        invalid_policy_warnings = [
            item for item in invalid_queue_status.get("warnings", [])
            if item.get("type") == "invalid_command_queue_policy"
        ]
        if (invalid_status_queue.get("policy_valid") is not False or
                invalid_status_queue.get("configured_for_polling") is not False or
                invalid_status_queue.get("arbitrary_policy_requested") is not False or
                invalid_status_queue.get("arbitrary_execution_allowed") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_policy_valid") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_policy_error_count") != len(invalid_status_queue.get("policy_errors", [])) or
                invalid_queue_status.get("summary", {}).get("command_queue_configured_for_polling") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_active_control_channel") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_arbitrary_execution_allowed") is not False or
                not invalid_policy_warnings or
                "disabled command queue must keep allowed commands policy none" not in invalid_policy_warnings[-1].get("policy_errors", [])):
            print("server json status marked invalid command queue policy usable", file=sys.stderr)
            print(invalid_queue_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_queue_status_text = run(
            "scripts/busierbox-server",
            "--config", str(invalid_queue_cfg),
            "--status",
        )
        if ("command queue policy is invalid; target polling is not configured" not in invalid_queue_status_text.stdout or
                "disabled command queue must keep allowed commands policy none" not in invalid_queue_status_text.stdout):
            print("server text status missing invalid command queue policy warning", file=sys.stderr)
            print(invalid_queue_status_text.stdout, file=sys.stderr)
            return 1
        invalid_rshell_cfg = Path(tmp) / "server-config-invalid-rshell-policy.json"
        invalid_rshell_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "rshell_session_policy": "bogus",
        }), encoding="utf-8")
        invalid_rshell_status_doc = run(
            "scripts/busierbox-server",
            "--config", str(invalid_rshell_cfg),
            "--json-status",
        )
        invalid_rshell_status = json.loads(invalid_rshell_status_doc.stdout)
        invalid_rshell_warnings = [
            item for item in invalid_rshell_status.get("warnings", [])
            if item.get("type") == "invalid_rshell_session_policy"
        ]
        invalid_rshell_record = (invalid_rshell_status.get("target_commands_by_service") or {}).get("rshell", [{}])[0]
        invalid_rshell_metadata = invalid_rshell_record.get("metadata") or {}
        if (invalid_rshell_metadata.get("session_policy") != "bogus" or
                invalid_rshell_metadata.get("session_policy_valid") is not False or
                "unsupported rshell session policy" not in invalid_rshell_metadata.get("session_policy_errors", []) or
                "unsupported rshell session policy" not in (invalid_rshell_metadata.get("session_policy_summary") or {}).get("errors", []) or
                not invalid_rshell_warnings or
                invalid_rshell_warnings[-1].get("session_policy") != "bogus" or
                "unsupported rshell session policy" not in invalid_rshell_warnings[-1].get("session_policy_errors", []) or
                invalid_rshell_status.get("summary", {}).get("warning_type_counts", {}).get("invalid_rshell_session_policy") != 1 or
                invalid_rshell_status.get("summary", {}).get("target_command_session_policy_valid_counts", {}).get("False") != 1 or
                invalid_rshell_status.get("summary", {}).get("target_command_session_policy_error_count") != 1 or
                invalid_rshell_status.get("warnings_by_type", {}).get("invalid_rshell_session_policy", [{}])[-1].get("session_policy") != "bogus"):
            print("server json status missing invalid rshell session policy warning", file=sys.stderr)
            print(invalid_rshell_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_rshell_status_text = run(
            "scripts/busierbox-server",
            "--config", str(invalid_rshell_cfg),
            "--status",
        )
        if ("rshell session policy is invalid: bogus" not in invalid_rshell_status_text.stdout or
                "unsupported rshell session policy" not in invalid_rshell_status_text.stdout):
            print("server text status missing invalid rshell session policy warning", file=sys.stderr)
            print(invalid_rshell_status_text.stdout, file=sys.stderr)
            return 1
        exceeded_queue_file = Path(tmp) / "operator-session" / "exceeded-command-queue.json"
        exceeded_queued = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--queue-command", "busierbox survey",
            "--queue-max-output", "10",
        )
        if exceeded_queued.returncode != 0:
            print("operator command queue exceeded-limit fixture failed to queue", file=sys.stderr)
            print(exceeded_queued.stdout, file=sys.stderr)
            print(exceeded_queued.stderr, file=sys.stderr)
            return 1
        exceeded_id = json.loads(exceeded_queue_file.read_text(encoding="utf-8"))["commands"][0]["id"]
        exceeded_result_json = Path(tmp) / "command-result-exceeded.json"
        exceeded_result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": exceeded_id,
            "status": "completed",
            "exit_code": 0,
            "stdout_bytes": 8,
            "stderr_bytes": 7,
        }) + "\n", encoding="utf-8")
        exceeded_recorded = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--record-command-result", exceeded_id,
            "--result-json", str(exceeded_result_json),
        )
        if exceeded_recorded.returncode != 0:
            print("operator command queue exceeded-limit result failed to record", file=sys.stderr)
            print(exceeded_recorded.stdout, file=sys.stderr)
            print(exceeded_recorded.stderr, file=sys.stderr)
            return 1
        exceeded_status = json.loads(run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--json-command-queue",
        ).stdout)["command_queue"]
        exceeded_rec = exceeded_status["commands"][0]
        if (exceeded_status.get("result_output_exceeded_count") != 1 or
                exceeded_status.get("result_status_counts", {}).get("completed") != 1 or
                exceeded_status.get("result_exit_code_counts", {}).get("0") != 1 or
                exceeded_status.get("result_output_size_bucket_counts", {}).get("small") != 1 or
                exceeded_status.get("commands_by_result_output_size_bucket", {}).get("small", [{}])[0].get("id") != exceeded_rec.get("id") or
                exceeded_rec.get("result_output_bytes") != 15 or
                exceeded_rec.get("result_output_size_bucket") != "small" or
                exceeded_rec.get("result_output_limit_bytes") != 10 or
                exceeded_rec.get("result_output_exceeded_limit") is not True):
            print("operator command queue did not flag result output over limit", file=sys.stderr)
            print(json.dumps(exceeded_status, indent=2), file=sys.stderr)
            return 1

        arbitrary_queue_cfg = Path(tmp) / "server-config-arbitrary-command-queue.json"
        arbitrary_queue_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "command_queue_file": str(queue_file),
            "command_queue_enable": "yes",
            "command_queue_require_token": "no",
            "command_queue_allowed_commands": "custom",
            "command_queue_allow_arbitrary": "yes",
        }), encoding="utf-8")
        arbitrary_queue_doc = run(
            "scripts/busierbox-server",
            "--config", str(arbitrary_queue_cfg),
            "--json-command-queue",
        )
        arbitrary_queue = json.loads(arbitrary_queue_doc.stdout)["command_queue"]
        arbitrary_queue_summary = arbitrary_queue.get("policy_summary") or {}
        if (arbitrary_queue.get("policy_valid") is not True or
                arbitrary_queue.get("arbitrary_policy_requested") is not True or
                arbitrary_queue.get("arbitrary_execution_allowed") is not False or
                arbitrary_queue.get("execution_supported") is not False or
                arbitrary_queue.get("executes_commands") is not False or
                arbitrary_queue_summary.get("configured_for_polling") is not True or
                arbitrary_queue_summary.get("arbitrary_policy_requested") is not True or
                arbitrary_queue_summary.get("arbitrary_execution_allowed") is not False):
            print("server command queue treated arbitrary policy request as execution permission", file=sys.stderr)
            print(arbitrary_queue_doc.stdout, file=sys.stderr)
            return 1
        if "summary" not in queue_status_json or "warnings" not in queue_status_json:
            print("server json status missing top-level summary/warnings", file=sys.stderr)
            return 1
        paths = queue_status_json.get("paths") or {}
        if (not queue_status_json.get("generated_at") or
                paths.get("state_file") != queue_status_json.get("state_file") or
                paths.get("staged_files") != queue_status_json.get("staged_files") or
                paths.get("command_queue_file") != str(queue_file) or
                paths.get("workbench_jobs_file") != str(workbench_jobs_file) or
                not paths.get("event_log") or
                not paths.get("operator_session_dir") or
                paths.get("tls_cert") != queue_status_json.get("tls_cert") or
                paths.get("tls_key") != queue_status_json.get("tls_key") or
                paths.get("tls_cert") != str(cert_path) or
                paths.get("tls_key") != str(key_path)):
            print("server json status missing stable generated_at/paths API fields", file=sys.stderr)
            return 1
        path_status = queue_status_json.get("path_status") or {}
        path_status_records = queue_status_json.get("path_status_records") or []
        path_status_by_name = queue_status_json.get("path_status_by_name") or {}
        path_status_by_path = queue_status_json.get("path_status_by_path") or {}
        path_status_by_kind = queue_status_json.get("path_status_by_expected_kind") or {}
        path_status_by_exists = queue_status_json.get("path_status_by_exists") or {}
        path_status_by_parent_exists = queue_status_json.get("path_status_by_parent_exists") or {}
        path_status_by_writable = queue_status_json.get("path_status_by_writable") or {}
        path_status_by_kind_mismatch = queue_status_json.get("path_status_by_expected_kind_mismatch") or {}
        state_path_status = path_status.get("state_file") or {}
        staged_path_status = path_status.get("staged_files") or {}
        command_queue_path_status = path_status.get("command_queue_file") or {}
        session_path_status = path_status.get("session_root") or {}
        server_state = queue_status_json.get("server_state") or {}
        staged_files_state = queue_status_json.get("staged_files_state") or {}
        command_queue_state = queue_status_json.get("command_queue_state") or {}
        if (set(paths) - set(path_status) or
                state_path_status.get("path") != queue_status_json.get("state_file") or
                state_path_status.get("expected_kind") != "file" or
                state_path_status.get("expected_kind_matches") is not True or
                state_path_status.get("expected_kind_mismatch") is not False or
                state_path_status.get("parent_exists") is not True or
                state_path_status.get("writable") is not True or
                session_path_status.get("expected_kind") != "dir" or
                session_path_status.get("expected_kind_matches") is not True or
                session_path_status.get("expected_kind_mismatch") is not False or
                queue_status_json["summary"].get("path_status_count") != len(paths) or
                queue_status_json["summary"].get("path_parent_missing_count") != 0 or
                queue_status_json["summary"].get("path_kind_mismatch_count") != 0):
            print("server json status missing operator path health records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (len(path_status_records) != len(paths) or
                path_status_by_name.get("state_file", {}).get("path") != queue_status_json.get("state_file") or
                path_status_by_path.get(str(queue_file), [{}])[0].get("name") != "command_queue_file" or
                not path_status_by_kind.get("dir") or
                len(path_status_by_kind.get("file", [])) < 1 or
                len(path_status_by_exists.get("yes", [])) < 1 or
                path_status_by_parent_exists.get("no") != [] or
                len(path_status_by_writable.get("yes", [])) < 1 or
                path_status_by_kind_mismatch.get("yes") != []):
            print("server json status missing normalized operator path records/indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        browser_paths = queue_status_json.get("browser_paths") or []
        browser_summary = queue_status_json.get("browser_path_summary") or {}
        browser_by_kind = queue_status_json.get("browser_paths_by_kind") or {}
        browser_by_path = queue_status_json.get("browser_paths_by_path") or {}
        browser_by_kind_source = queue_status_json.get("browser_paths_by_kind_source_id") or {}
        browser_by_exists = queue_status_json.get("browser_paths_by_exists") or {}
        browser_by_writable = queue_status_json.get("browser_paths_by_writable") or {}
        browser_by_kind_mismatch = queue_status_json.get("browser_paths_by_expected_kind_mismatch") or {}
        if (browser_summary.get("total_count") != len(browser_paths) or
                queue_status_json["summary"].get("browser_path_count") != len(browser_paths) or
                queue_status_json["summary"].get("browser_path_kind_counts", {}).get("server-state") != 1 or
                queue_status_json["summary"].get("browser_path_exists_kind_counts", {}).get("command-queue-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_exists_kind_counts", {}).get("workbench-jobs-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_missing_kind_counts", {}).get("staged-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_kind_mismatch_count") != 0 or
                queue_status_json["summary"].get("browser_path_kind_mismatch_counts") != {} or
                not browser_by_kind.get("operator-dir") or
                not browser_by_kind.get("server-state") or
                not browser_by_kind.get("command-queue-ledger") or
                browser_by_kind["operator-dir"][0].get("expected_kind_matches") is not True or
                browser_by_kind["server-state"][0].get("expected_kind_mismatch") is not False or
                not browser_by_exists.get("yes") or
                not browser_by_writable.get("yes") or
                browser_by_kind_mismatch.get("yes") != [] or
                browser_by_kind_mismatch.get("no", [{}])[0].get("kind") not in ("operator-dir", "server-state") or
                browser_by_path.get(str(queue_file), [{}])[0].get("kind") != "command-queue-ledger" or
                browser_by_kind_source.get("command-queue-ledger:command_queue_file", [{}])[0].get("path") != str(queue_file) or
                browser_summary.get("exists_count", 0) < 1):
            print("server json status missing normalized browser path records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        api_collections = queue_status_json.get("api_collections") or {}
        api = queue_status_json.get("api") or {}
        api_resources = queue_status_json.get("api_resources") or []
        api_resources_by_name = queue_status_json.get("api_resources_by_name") or {}
        api_resources_by_records_key = queue_status_json.get("api_resources_by_records_key") or {}
        api_resources_by_summary_key = queue_status_json.get("api_resources_by_summary_key") or {}
        api_resources_by_primary_key = queue_status_json.get("api_resources_by_primary_key") or {}
        api_resources_by_warning_indexes = queue_status_json.get("api_resources_by_has_warning_indexes") or {}
        if (api.get("schema") != 1 or
                api.get("status_command") != "scripts/busierbox-server --api-status" or
                api.get("json_status_command") != "scripts/busierbox-server --json-status" or
                api.get("event_limit") != 12 or
                api.get("resource_count") != len(api_resources) or
                api.get("resources_key") != "api_resources" or
                api.get("collections_key") != "api_collections"):
            print("server json status missing future frontend API catalog metadata", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        for collection_name, expected_count, expected_index in (
                ("services", len(queue_status_json.get("services") or []), "services_by_has_error"),
                ("ports", len(queue_status_json.get("ports") or []), "ports_by_number"),
                ("path_status_records", len(path_status_records), "path_status_by_name"),
                ("browser_paths", len(browser_paths), "browser_paths_by_expected_kind_mismatch"),
                ("warnings", len(queue_status_json.get("warnings") or []), "warnings_by_type"),
                ("staged_records", len(queue_status_json.get("staged_records") or []), "staged_by_fetch_command"),
                ("command_copy_records", len(queue_status_json.get("command_copy_records") or []), "command_copy_records_by_has_command"),
                ("command_queue_commands", len((queue_status_json.get("command_queue") or {}).get("commands") or []), "commands_by_queue_policy_execution_mode"),
                ("command_queue_modes", len(queue_status_json.get("command_queue_mode_records") or []), "command_queue_modes_by_result_upload_supported"),
                ("workbench_actions", len(queue_status_json.get("workbench_actions") or []), "workbench_actions_by_id"),
                ("workbench_config_fields", len(queue_status_json.get("workbench_config_fields") or []), "workbench_config_fields_by_key"),
                ("workbench_jobs", len(queue_status_json.get("workbench_jobs") or []), "workbench_jobs_by_id"),
                ("sessions", len(queue_status_json.get("sessions") or []), "sessions_by_has_uploads"),
                ("events", len(queue_status_json.get("events") or []), "events_by_id"),
        ):
            collection = api_collections.get(collection_name) or {}
            if (collection.get("count") != expected_count or
                    collection.get("name") != collection_name or
                    expected_index not in (collection.get("indexes") or []) or
                    not collection.get("summary_key") or
                    collection.get("count_summary_key") != collection.get("summary_key") or
                    (collection_name in ("services", "ports", "path_status_records", "browser_paths") and
                     collection.get("has_warning_indexes") is not True)):
                print(f"server json status missing api collection metadata for {collection_name}", file=sys.stderr)
                print(queue_status_doc.stdout, file=sys.stderr)
                return 1
        if (len(api_resources) != len(api_collections) or
                api_resources_by_name.get("services", {}).get("records_key") != "services" or
                api_resources_by_name.get("services", {}).get("collection_key") != "api_collections.services" or
                api_resources_by_name.get("services", {}).get("count") != len(queue_status_json.get("services") or []) or
                api_resources_by_name.get("services", {}).get("summary_key") != "service_count" or
                api_resources_by_name.get("services", {}).get("has_warning_indexes") is not True or
                "services_by_warning_type" not in (api_resources_by_name.get("services", {}).get("warning_indexes") or []) or
                api_resources_by_name.get("command_queue_commands", {}).get("has_warning_indexes") is not False or
                len(api_resources_by_warning_indexes.get("True", [])) < 4 or
                not any(rec.get("name") == "browser_paths" for rec in api_resources_by_warning_indexes.get("True", [])) or
                "services_by_name" not in (api_resources_by_name.get("services", {}).get("indexes") or []) or
                api_resources_by_name.get("command_queue_commands", {}).get("records_key") != "command_queue.commands" or
                api_resources_by_records_key.get("command_queue.commands", [{}])[0].get("name") != "command_queue_commands" or
                api_resources_by_name.get("workbench_actions", {}).get("records_key") != "workbench_actions" or
                api_resources_by_summary_key.get("workbench_action_count", [{}])[0].get("name") != "workbench_actions" or
                api_resources_by_name.get("workbench_config_fields", {}).get("records_key") != "workbench_config_fields" or
                api_resources_by_summary_key.get("workbench_config_field_count", [{}])[0].get("name") != "workbench_config_fields" or
                api_resources_by_name.get("workbench_jobs", {}).get("records_key") != "workbench_jobs" or
                api_resources_by_summary_key.get("workbench_job_count", [{}])[0].get("name") != "workbench_jobs" or
                api_resources_by_summary_key.get("event_tail_count", [{}])[0].get("name") != "events" or
                not any(rec.get("name") == "services" for rec in api_resources_by_primary_key.get("name", []))):
            print("server json status missing API resource catalog lookup maps", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        workbench_actions = queue_status_json.get("workbench_actions") or []
        workbench_config_fields = queue_status_json.get("workbench_config_fields") or []
        config_fields_by_key = queue_status_json.get("workbench_config_fields_by_key") or {}
        config_fields_by_category = queue_status_json.get("workbench_config_fields_by_category") or {}
        config_fields_by_target_execution = queue_status_json.get("workbench_config_fields_by_target_execution") or {}
        config_fields_by_safety = queue_status_json.get("workbench_config_fields_by_safety_boundary") or {}
        config_fields_by_control_like = queue_status_json.get("workbench_config_fields_by_control_like") or {}
        actions_by_id = queue_status_json.get("workbench_actions_by_id") or {}
        actions_by_category = queue_status_json.get("workbench_actions_by_category") or {}
        actions_by_script = queue_status_json.get("workbench_actions_by_script") or {}
        actions_by_background = queue_status_json.get("workbench_actions_by_background_supported") or {}
        actions_by_confirmation = queue_status_json.get("workbench_actions_by_requires_confirmation") or {}
        actions_by_execution_default = queue_status_json.get("workbench_actions_by_execution_default") or {}
        actions_by_target_execution = queue_status_json.get("workbench_actions_by_target_execution") or {}
        actions_by_event = queue_status_json.get("workbench_actions_by_event") or {}
        actions_by_config_path = queue_status_json.get("workbench_actions_by_config_path") or {}
        workbench_summary = queue_status_json.get("summary") or {}
        if (len(workbench_config_fields) < 12 or
                workbench_summary.get("workbench_config_field_count") != len(workbench_config_fields) or
                workbench_summary.get("workbench_config_field_fixed_option_count", 0) < 10 or
                not config_fields_by_key.get("BB_TARGET_PRESET") or
                not config_fields_by_key.get("BB_STATIC_POLICY") or
                config_fields_by_key.get("BB_STATIC_POLICY", {}).get("options") != ["static-preferred", "static-only", "dynamic-ok"] or
                not config_fields_by_key.get("BB_COMMAND_QUEUE_ENABLE") or
                config_fields_by_key.get("BB_COMMAND_QUEUE_ENABLE", {}).get("fixed_options") is not True or
                config_fields_by_key.get("BB_COMMAND_QUEUE_ENABLE", {}).get("safety_boundary") != "command-queue" or
                not config_fields_by_key.get("BB_COMMAND_QUEUE_POLL_INTERVAL_SEC") or
                config_fields_by_key.get("BB_COMMAND_QUEUE_POLL_BACKOFF", {}).get("options") != ["none", "linear", "exponential"] or
                config_fields_by_key.get("BB_RSHELL_TRANSPORT", {}).get("safety_boundary") != "reverse-access" or
                not config_fields_by_category.get("runtime") or
                not config_fields_by_category.get("rshell") or
                config_fields_by_target_execution.get("True", []) != [] or
                len(config_fields_by_target_execution.get("False", [])) != len(workbench_config_fields) or
                not config_fields_by_safety.get("command-queue") or
                not config_fields_by_control_like.get("True") or
                workbench_summary.get("workbench_config_field_command_queue_related_count", 0) < 13):
            print("server json status missing guided build config descriptors", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (len(workbench_actions) < 6 or
                workbench_summary.get("workbench_action_count") != len(workbench_actions) or
                workbench_summary.get("workbench_action_target_execution_count") != 0 or
                workbench_summary.get("workbench_action_background_supported_count", 0) < 2 or
                workbench_summary.get("workbench_action_requires_confirmation_count", 0) < 4 or
                workbench_summary.get("workbench_action_execution_default_counts", {}).get("show-command") != len(workbench_actions) or
                workbench_summary.get("workbench_action_event_counts", {}).get("workbench_job_requested", 0) < 3 or
                workbench_summary.get("workbench_action_config_path_counts", {}).get(str(cfg), 0) < 5 or
                actions_by_id.get("package-artifact", {}).get("command") != "make package" or
                actions_by_id.get("configure-trailer", {}).get("script") != "scripts/artifact-config" or
                not actions_by_category.get("configuration") or
                not actions_by_script.get("scripts/busierbox-bringup") or
                not actions_by_background.get("True") or
                not actions_by_confirmation.get("True") or
                actions_by_execution_default.get("show-command", [{}])[0].get("execution_default") != "show-command" or
                actions_by_target_execution.get("True", []) != [] or
                len(actions_by_target_execution.get("False", [])) != len(workbench_actions) or
                not actions_by_event.get("workbench_job_requested") or
                not any(item.get("id") == "package-artifact" for item in actions_by_config_path.get(str(cfg), [])) or
                "workbench_actions_by_requires_confirmation" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_execution_default" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_target_execution" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_event" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_config_path" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", [])):
            print("server json status missing operator workflow action descriptors", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        workbench_jobs = queue_status_json.get("workbench_jobs") or []
        jobs_by_id = queue_status_json.get("workbench_jobs_by_id") or {}
        jobs_by_action = queue_status_json.get("workbench_jobs_by_action") or {}
        jobs_by_state = queue_status_json.get("workbench_jobs_by_effective_state") or {}
        jobs_by_pid_managed = queue_status_json.get("workbench_jobs_by_pid_managed") or {}
        jobs_by_log_exists = queue_status_json.get("workbench_jobs_by_log_exists") or {}
        jobs_by_exit_status_known = queue_status_json.get("workbench_jobs_by_exit_status_known") or {}
        jobs_by_started_at_known = queue_status_json.get("workbench_jobs_by_started_at_known") or {}
        jobs_by_finished_at_known = queue_status_json.get("workbench_jobs_by_finished_at_known") or {}
        jobs_by_duration_known = queue_status_json.get("workbench_jobs_by_duration_known") or {}
        jobs_by_elapsed_known = queue_status_json.get("workbench_jobs_by_elapsed_known") or {}
        jobs_by_background_supported = queue_status_json.get("workbench_jobs_by_background_supported") or {}
        jobs_by_long_running = queue_status_json.get("workbench_jobs_by_long_running") or {}
        jobs_api = (queue_status_json.get("api_collections") or {}).get("workbench_jobs") or {}
        job = jobs_by_id.get("job-smoke") or {}
        if (len(workbench_jobs) != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_running_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_pid_managed_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_log_exists_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_log_total_size") != workbench_job_log.stat().st_size or
                queue_status_json.get("summary", {}).get("workbench_job_last_output_tail_truncated_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_started_at_known_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_finished_at_known_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_duration_known_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_elapsed_known_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_background_supported_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_long_running_count") != 1 or
                job.get("effective_state") != "exited" or
                job.get("pid_alive") is not False or
                job.get("pid_managed") is not False or
                job.get("cancel_supported") is not False or
                job.get("log_exists") is not True or
                job.get("exit_status_known") is not False or
                job.get("started_at_known") is not True or
                job.get("finished_at_known") is not False or
                job.get("duration_known") is not False or
                job.get("elapsed_known") is not True or
                job.get("background_supported") is not True or
                job.get("long_running") is not True or
                job.get("last_output_tail", [])[-1:] != ["package complete"] or
                job.get("last_output_tail_count") != 20 or
                job.get("last_output_tail_truncated") is not True or
                job.get("last_output_tail_line_limit") != 20 or
                job.get("last_output_tail_byte_limit") != 8192 or
                job.get("log_line_count") != 25 or
                job.get("log_size") != workbench_job_log.stat().st_size or
                not jobs_by_action.get("package-artifact") or
                not jobs_by_state.get("exited") or
                jobs_by_pid_managed.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_log_exists.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_exit_status_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_started_at_known.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_finished_at_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_duration_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_elapsed_known.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_background_supported.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_long_running.get("True", [{}])[0].get("id") != "job-smoke" or
                (queue_status_json.get("workbench_jobs_by_last_output_tail_truncated") or {}).get("True", [{}])[0].get("id") != "job-smoke" or
                "workbench_jobs_by_pid_managed" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_log_exists" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_exit_status_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_started_at_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_finished_at_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_duration_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_elapsed_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_background_supported" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_long_running" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_last_output_tail_truncated" not in (jobs_api.get("indexes") or [])):
            print("server json status missing workbench background job records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (staged_files_state.get("path") != queue_status_json.get("staged_files") or
                staged_files_state.get("exists") != staged_path_status.get("exists") or
                queue_status_json["summary"].get("staged_files_exists") != bool(staged_files_state.get("exists")) or
                queue_status_json["summary"].get("staged_files_valid") != bool(staged_files_state.get("valid")) or
                not isinstance(staged_files_state.get("request_names"), list)):
            print("server json status missing reusable staged-files state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (command_queue_state.get("path") != queue_status_json.get("command_queue_file") or
                command_queue_state.get("exists") != command_queue_path_status.get("exists") or
                command_queue_state.get("valid") is not True or
                command_queue_state.get("command_count") != 1 or
                command_queue_state.get("status_counts", {}).get("result-received") != 1 or
                queue_status_json["summary"].get("command_queue_file_exists") is not True or
                queue_status_json["summary"].get("command_queue_file_valid") is not True or
                queue_status_json["summary"].get("command_queue_file_command_count") != 1):
            print("server json status missing reusable command queue state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (server_state.get("path") != queue_status_json.get("state_file") or
                server_state.get("exists") != state_path_status.get("exists") or
                queue_status_json["summary"].get("server_state_exists") != bool(server_state.get("exists")) or
                queue_status_json["summary"].get("server_state_valid") != bool(server_state.get("valid")) or
                not isinstance(server_state.get("services"), dict) or
                not isinstance(server_state.get("sessions"), list)):
            print("server json status missing reusable server-state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (queue_status_json["summary"].get("service_count") != 5 or
                queue_status_json["summary"].get("service_actual_counts", {}).get("stopped") != 5 or
                queue_status_json["summary"].get("service_configured_counts", {}).get("unknown", 0) < 3):
            print("server json status service summary is wrong", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        services_by_name = queue_status_json.get("services_by_name") or {}
        if set(services_by_name) != {"ssh", "tls-shell", "plain-shell", "file-service", "command-queue"}:
            print("server json status missing stable services_by_name map", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        services_by_actual = queue_status_json.get("services_by_actual") or {}
        services_by_configured = queue_status_json.get("services_by_configured") or {}
        services_by_port = queue_status_json.get("services_by_port") or {}
        ports = queue_status_json.get("ports") or []
        ports_by_number = queue_status_json.get("ports_by_number") or {}
        ports_by_service = queue_status_json.get("ports_by_service") or {}
        ports_by_actual = queue_status_json.get("ports_by_actual") or {}
        file_service_port = str(services_by_name.get("file-service", {}).get("port", ""))
        if (len(services_by_actual.get("stopped", [])) != 5 or
                len(services_by_configured.get("unknown", [])) < 3 or
                not any(row.get("name") == "file-service" for row in services_by_port.get(file_service_port, []))):
            print("server json status missing grouped service lookup maps", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (queue_status_json["summary"].get("port_count") != 5 or
                queue_status_json["summary"].get("port_actual_counts", {}).get("stopped") != 5 or
                len(ports) != 5 or
                not any(row.get("service") == "file-service" for row in ports_by_number.get(file_service_port, [])) or
                ports_by_service.get("file-service", [{}])[0].get("port") != int(file_service_port) or
                len(ports_by_actual.get("stopped", [])) != 5):
            print("server json status missing explicit port API records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        service_rows = {row.get("name"): row for row in queue_status_json.get("services") or []}
        for name, row in service_rows.items():
            mapped = services_by_name.get(name) or {}
            for key in ("port", "tls", "configured", "actual", "pid", "pid_alive", "pid_managed", "listener_pids", "stale", "error", "warning_count", "warning_types"):
                if mapped.get(key) != row.get(key):
                    print(f"server json status services_by_name drift for {name}:{key}", file=sys.stderr)
                    print(queue_status_doc.stdout, file=sys.stderr)
                    return 1
        command_queue_doc = queue_status_json.get("command_queue") or {}
        command_queue_modes = command_queue_doc.get("mode_semantics") or {}
        command_queue_mode_records = queue_status_json.get("command_queue_mode_records") or []
        command_queue_modes_by_mode = queue_status_json.get("command_queue_modes_by_mode") or {}
        command_queue_modes_by_lifecycle = queue_status_json.get("command_queue_modes_by_lifecycle") or {}
        command_queue_modes_by_polling = queue_status_json.get("command_queue_modes_by_would_poll_if_configured") or {}
        command_queue_modes_by_live = queue_status_json.get("command_queue_modes_by_live_supported") or {}
        command_queue_modes_by_delivery = queue_status_json.get("command_queue_modes_by_delivery_supported") or {}
        command_queue_modes_by_result_upload = queue_status_json.get("command_queue_modes_by_result_upload_supported") or {}
        command_queue_modes_by_execution = queue_status_json.get("command_queue_modes_by_execution_supported") or {}
        command_queue_modes_by_control = queue_status_json.get("command_queue_modes_by_active_control_channel") or {}
        command_queue_modes_by_operator_exec = queue_status_json.get("command_queue_modes_by_operator_supplied_command_execution") or {}
        command_queue_mode_summary = command_queue_doc.get("mode_summary") or {}
        if (queue_status_json["summary"].get("command_queue_total_count") != 1 or
                queue_status_json["summary"].get("command_queue_result_count") != 1 or
                queue_status_json["summary"].get("command_queue_result_output_exceeded_count") != 0 or
                queue_status_json["summary"].get("command_queue_result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json["summary"].get("command_queue_status_counts", {}).get("result-received") != 1 or
                queue_status_json["summary"].get("command_queue_latest_created_at") != command_after_result.get("created_at") or
                queue_status_json["summary"].get("command_queue_latest_result_received_at") != command_after_result.get("result_received_at") or
                queue_status_json["summary"].get("command_queue_enabled") is not False or
                queue_status_json["summary"].get("command_queue_configured_for_polling") is not False or
                queue_status_json["summary"].get("command_queue_active_control_channel") is not False or
                queue_status_json["summary"].get("command_queue_token_required") is not True or
                queue_status_json["summary"].get("command_queue_token_configured") is not False or
                queue_status_json["summary"].get("command_queue_execution_mode") != "metadata-only" or
                queue_status_json["summary"].get("command_queue_metadata_only_default") is not True or
                queue_status_json["summary"].get("command_queue_execution_supported") is not False or
                queue_status_json["summary"].get("command_queue_delivery_supported") is not False or
                queue_status_json["summary"].get("command_queue_result_upload_supported") is not True or
                queue_status_json["summary"].get("command_queue_poll_transport_supported") is not True or
                queue_status_json["summary"].get("command_queue_live_polling_supported") is not True or
                queue_status_json["summary"].get("command_queue_poll_interval_sec") != "5" or
                queue_status_json["summary"].get("command_queue_poll_jitter_pct") != "0" or
                queue_status_json["summary"].get("command_queue_poll_backoff") != "none" or
                queue_status_json["summary"].get("command_queue_poll_max_interval_sec") != "300" or
                queue_status_json["summary"].get("command_queue_max_polls") != "0" or
                queue_status_json["summary"].get("command_queue_arbitrary_policy_requested") is not False or
                queue_status_json["summary"].get("command_queue_arbitrary_execution_allowed") is not False or
                queue_status_json["summary"].get("command_queue_safe_disabled_default") is not True or
                command_queue_modes.get("status", {}).get("lifecycle") != "inspect" or
                command_queue_modes.get("status", {}).get("would_poll_if_configured") is not False or
                command_queue_modes.get("poll", {}).get("lifecycle") != "single-poll" or
                command_queue_modes.get("once", {}).get("lifecycle") != "single-cycle" or
                command_queue_modes.get("daemon", {}).get("lifecycle") != "long-running" or
                command_queue_modes.get("stop", {}).get("lifecycle") != "stop" or
                command_queue_modes.get("stop", {}).get("requires_operator_host") is not False or
                command_queue_modes.get("stop", {}).get("would_poll_if_configured") is not False or
                command_queue_modes.get("daemon", {}).get("dry_run_default") is not True or
                command_queue_modes.get("daemon", {}).get("dry_run_only") is not False or
                command_queue_modes.get("daemon", {}).get("live_supported") is not True or
                command_queue_modes.get("daemon", {}).get("live_would_contact_operator") is not True or
                command_queue_modes.get("daemon", {}).get("execution_supported") is not False or
                command_queue_modes.get("daemon", {}).get("active_control_channel") is not False or
                len(command_queue_mode_records) != 5 or
                command_queue_modes_by_mode.get("daemon", {}).get("lifecycle") != "long-running" or
                len(command_queue_modes_by_lifecycle.get("long-running", [])) != 1 or
                len(command_queue_modes_by_polling.get("True", [])) != 3 or
                len(command_queue_modes_by_polling.get("False", [])) != 2 or
                len(command_queue_modes_by_live.get("True", [])) != 3 or
                len(command_queue_modes_by_delivery.get("False", [])) != 5 or
                len(command_queue_modes_by_result_upload.get("True", [])) != 5 or
                len(command_queue_modes_by_execution.get("False", [])) != 5 or
                len(command_queue_modes_by_control.get("False", [])) != 5 or
                len(command_queue_modes_by_operator_exec.get("False", [])) != 5 or
                command_queue_mode_summary.get("mode_count") != 5 or
                command_queue_mode_summary.get("polling_mode_count") != 3 or
                command_queue_mode_summary.get("operator_host_required_mode_count") != 3 or
                command_queue_mode_summary.get("live_supported_mode_count") != 3 or
                command_queue_mode_summary.get("delivery_supported_mode_count") != 0 or
                command_queue_mode_summary.get("result_upload_supported_mode_count") != 5 or
                command_queue_mode_summary.get("execution_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_mode_count") != 5 or
                queue_status_json["summary"].get("command_queue_polling_mode_count") != 3 or
                queue_status_json["summary"].get("command_queue_operator_host_required_mode_count") != 3 or
                queue_status_json["summary"].get("command_queue_live_supported_mode_count") != 3 or
                queue_status_json["summary"].get("command_queue_delivery_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_result_upload_supported_mode_count") != 5 or
                queue_status_json["summary"].get("command_queue_execution_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_active_control_channel_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_operator_supplied_command_execution_mode_count") != 0):
            print("server json status missing aggregate command queue counts", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        event_stats = queue_status_json.get("event_log_stats") or {}
        event_log_state = queue_status_json.get("event_log_state") or {}
        if (event_stats.get("total_count", 0) < 2 or
                event_stats.get("tail_count") != len(queue_status_json.get("events", [])) or
                queue_status_json["summary"].get("event_count") != event_stats.get("total_count") or
                queue_status_json["summary"].get("event_tail_count") != event_stats.get("tail_count") or
                event_stats.get("tail_truncated") is not False or
                event_stats.get("tail_omitted_count") != 0 or
                queue_status_json["summary"].get("event_tail_truncated") is not False or
                queue_status_json["summary"].get("event_tail_omitted_count") != 0 or
                not event_stats.get("first_event_at") or
                not event_stats.get("latest_event_at") or
                queue_status_json["summary"].get("first_event_at") != event_stats.get("first_event_at") or
                queue_status_json["summary"].get("latest_event_at") != event_stats.get("latest_event_at")):
            print("server json status missing event log total/tail stats", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (event_log_state.get("path") != queue_status_json.get("event_log") or
                event_log_state.get("exists") is not True or
                event_log_state.get("valid") is not True or
                event_log_state.get("event_count") != event_stats.get("total_count") or
                event_log_state.get("invalid_count") != event_stats.get("invalid_count") or
                event_log_state.get("tail_truncated") is not False or
                event_log_state.get("tail_omitted_count") != 0 or
                queue_status_json["summary"].get("event_log_exists") is not True or
                queue_status_json["summary"].get("event_log_valid") is not True or
                queue_status_json["summary"].get("event_log_size", 0) <= 0):
            print("server json status missing reusable event log state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (event_stats.get("by_service", {}).get("command-queue", 0) < 2 or
                event_stats.get("by_event", {}).get("command_queue_queued", 0) < 1 or
                event_stats.get("by_event", {}).get("command_result_received", 0) < 1 or
                event_stats.get("by_level", {}).get("info", 0) < 2 or
                event_stats.get("by_service_event", {}).get("command-queue:command_queue_queued", 0) < 1 or
                event_stats.get("by_service_event", {}).get("command-queue:command_result_received", 0) < 1 or
                event_stats.get("by_detail_command_id", {}).get(command_id, 0) < 1 or
                event_stats.get("by_event_detail_command_id", {}).get(f"command_result_received:{command_id}", 0) < 1 or
                event_stats.get("by_service_detail_command_id", {}).get(f"command-queue:{command_id}", 0) < 1):
            print("server json status missing event log aggregate counters", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        event_summary = queue_status_json.get("summary", {})
        if (event_summary.get("event_service_counts", {}).get("command-queue", 0) < 2 or
                event_summary.get("event_type_counts", {}).get("command_queue_queued", 0) < 1 or
                event_summary.get("event_type_counts", {}).get("command_result_received", 0) < 1 or
                event_summary.get("event_level_counts", {}).get("info", 0) < 2 or
                event_summary.get("event_service_event_counts", {}).get("command-queue:command_queue_queued", 0) < 1 or
                event_summary.get("event_service_event_counts", {}).get("command-queue:command_result_received", 0) < 1 or
                event_summary.get("event_service_level_counts", {}).get("command-queue:info", 0) < 2 or
                event_summary.get("event_type_level_counts", {}).get("command_queue_queued:info", 0) < 1 or
                event_summary.get("event_detail_command_id_counts", {}).get(command_id, 0) < 1 or
                event_summary.get("event_type_detail_command_id_counts", {}).get(f"command_result_received:{command_id}", 0) < 1 or
                event_summary.get("event_service_detail_command_id_counts", {}).get(f"command-queue:{command_id}", 0) < 1):
            print("server json status missing mirrored event aggregate summary counters", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        events_by_service = queue_status_json.get("events_by_service") or {}
        events_by_id = queue_status_json.get("events_by_id") or {}
        events_by_event = queue_status_json.get("events_by_event") or {}
        events_by_level = queue_status_json.get("events_by_level") or {}
        events_by_service_event = queue_status_json.get("events_by_service_event") or {}
        events_by_service_level = queue_status_json.get("events_by_service_level") or {}
        events_by_event_level = queue_status_json.get("events_by_event_level") or {}
        events_by_remote_event = queue_status_json.get("events_by_remote_event") or {}
        events_by_remote_level = queue_status_json.get("events_by_remote_level") or {}
        events_by_detail_command_id = queue_status_json.get("events_by_detail_command_id") or {}
        events_by_event_detail_command_id = queue_status_json.get("events_by_event_detail_command_id") or {}
        events_by_service_detail_command_id = queue_status_json.get("events_by_service_detail_command_id") or {}
        events_api = (queue_status_json.get("api_collections") or {}).get("events") or {}
        first_tail_event = (queue_status_json.get("events") or [{}])[0]
        first_tail_event_id = first_tail_event.get("id", "")
        if (not first_tail_event_id or
                events_by_id.get(first_tail_event_id, {}).get("event") != first_tail_event.get("event") or
                not events_by_service.get("command-queue") or
                not events_by_event.get("command_queue_queued") or
                not events_by_event.get("command_result_received") or
                not events_by_level.get("info") or
                not events_by_service_event.get("command-queue:command_queue_queued") or
                not events_by_service_event.get("command-queue:command_result_received") or
                not events_by_service_level.get("command-queue:info") or
                not events_by_event_level.get("command_queue_queued:info") or
                events_by_detail_command_id.get(command_id, [{}])[0].get("event") != "command_result_received" or
                not events_by_event_detail_command_id.get(f"command_result_received:{command_id}") or
                not events_by_service_detail_command_id.get(f"command-queue:{command_id}") or
                "events_by_service_level" not in (events_api.get("indexes") or []) or
                "events_by_event_level" not in (events_api.get("indexes") or []) or
                "events_by_remote_event" not in (events_api.get("indexes") or []) or
                "events_by_remote_level" not in (events_api.get("indexes") or []) or
                "events_by_detail_command_id" not in (events_api.get("indexes") or []) or
                "events_by_event_detail_command_id" not in (events_api.get("indexes") or []) or
                "events_by_service_detail_command_id" not in (events_api.get("indexes") or [])):
            print("server json status missing event tail lookup indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if events_by_remote_event or events_by_remote_level:
            print("command queue status unexpectedly had remote event indexes before remote traffic", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        truncated_event_dir = Path(tmp) / "truncated-events"
        truncated_event_dir.mkdir()
        truncated_event_log = truncated_event_dir / "events.jsonl"
        with truncated_event_log.open("w", encoding="utf-8") as fh:
            for idx in range(15):
                fh.write(json.dumps({
                    "schema": 1,
                    "id": f"evt-trunc-{idx}",
                    "ts": f"2026-05-26T12:00:{idx:02d}Z",
                    "service": "smoke",
                    "session": "",
                    "session_path": "",
                    "event": "truncated_tail_probe",
                    "level": "info",
                    "remote": "198.51.100.7:1234",
                    "details": {"idx": idx},
                }, sort_keys=True) + "\n")
        truncated_event_cfg = Path(tmp) / "server-config-truncated-events.json"
        truncated_event_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(truncated_event_dir),
            "session_root": str(Path(tmp) / "truncated-event-sessions"),
        }), encoding="utf-8")
        truncated_event_status = run(
            "scripts/busierbox-server",
            "--config", str(truncated_event_cfg),
            "--json-status",
        )
        truncated_event_doc = json.loads(truncated_event_status.stdout)
        truncated_stats = truncated_event_doc.get("event_log_stats") or {}
        truncated_state = truncated_event_doc.get("event_log_state") or {}
        if (truncated_stats.get("total_count") != 15 or
                truncated_stats.get("tail_count") != 12 or
                truncated_stats.get("tail_truncated") is not True or
                truncated_stats.get("tail_omitted_count") != 3 or
                truncated_stats.get("by_remote_event", {}).get("198.51.100.7:1234:truncated_tail_probe") != 15 or
                truncated_stats.get("by_remote_level", {}).get("198.51.100.7:1234:info") != 15 or
                truncated_state.get("tail_truncated") is not True or
                truncated_state.get("tail_omitted_count") != 3 or
                truncated_event_doc.get("summary", {}).get("event_tail_truncated") is not True or
                truncated_event_doc.get("summary", {}).get("event_tail_omitted_count") != 3 or
                truncated_event_doc.get("summary", {}).get("event_remote_event_counts", {}).get("198.51.100.7:1234:truncated_tail_probe") != 15 or
                truncated_event_doc.get("summary", {}).get("event_remote_level_counts", {}).get("198.51.100.7:1234:info") != 15 or
                truncated_event_doc.get("events_by_remote_event", {}).get("198.51.100.7:1234:truncated_tail_probe", [{}])[0].get("id") != "evt-trunc-3" or
                truncated_event_doc.get("events_by_remote_level", {}).get("198.51.100.7:1234:info", [{}])[0].get("id") != "evt-trunc-3" or
                (truncated_event_doc.get("events") or [{}])[0].get("id") != "evt-trunc-3"):
            print("server json status missing explicit truncated event tail metadata", file=sys.stderr)
            print(truncated_event_status.stdout, file=sys.stderr)
            return 1
        limited_event_status = run(
            "scripts/busierbox-server",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "5",
        )
        limited_event_doc = json.loads(limited_event_status.stdout)
        limited_stats = limited_event_doc.get("event_log_stats") or {}
        if (limited_stats.get("tail_limit") != 5 or
                limited_stats.get("tail_count") != 5 or
                limited_stats.get("tail_omitted_count") != 10 or
                limited_event_doc.get("summary", {}).get("event_tail_count") != 5 or
                (limited_event_doc.get("events") or [{}])[0].get("id") != "evt-trunc-10"):
            print("server json status did not honor --event-limit", file=sys.stderr)
            print(limited_event_status.stdout, file=sys.stderr)
            return 1
        zero_event_status = run(
            "scripts/busierbox-server",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "0",
        )
        zero_event_doc = json.loads(zero_event_status.stdout)
        zero_stats = zero_event_doc.get("event_log_stats") or {}
        if (zero_stats.get("tail_limit") != 0 or
                zero_stats.get("tail_count") != 0 or
                zero_stats.get("tail_omitted_count") != 15 or
                zero_event_doc.get("events") != []):
            print("server json status did not honor --event-limit 0", file=sys.stderr)
            print(zero_event_status.stdout, file=sys.stderr)
            return 1
        negative_event_limit = run(
            "scripts/busierbox-server",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "-1",
        )
        if negative_event_limit.returncode != 2 or "--event-limit must be >= 0" not in negative_event_limit.stderr:
            print("server json status did not reject a negative --event-limit", file=sys.stderr)
            print(negative_event_limit.stdout, file=sys.stderr)
            print(negative_event_limit.stderr, file=sys.stderr)
            return 1
        event_log_path = Path(paths["event_log"])
        previous_invalid = int(event_stats.get("invalid_count", 0))
        with event_log_path.open("a", encoding="utf-8") as fh:
            fh.write("not-json\n")
        invalid_event_status = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-status",
        )
        invalid_event_doc = json.loads(invalid_event_status.stdout)
        invalid_event_warnings = [
            item for item in invalid_event_doc.get("warnings", [])
            if item.get("type") == "invalid_event_log"
        ]
        expected_invalid = previous_invalid + 1
        if (invalid_event_doc.get("summary", {}).get("event_invalid_count") != expected_invalid or
                invalid_event_doc.get("summary", {}).get("event_log_valid") is not False or
                (invalid_event_doc.get("event_log_state") or {}).get("valid") is not False or
                (invalid_event_doc.get("event_log_state") or {}).get("invalid_count") != expected_invalid or
                not invalid_event_warnings or
                invalid_event_warnings[-1].get("path") != str(event_log_path) or
                invalid_event_warnings[-1].get("invalid_count") != expected_invalid):
            print("server json status missing invalid event log warning", file=sys.stderr)
            print(invalid_event_status.stdout, file=sys.stderr)
            return 1
        invalid_event_text = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--status",
        )
        if f"event log contains {expected_invalid} invalid JSONL record" not in invalid_event_text.stdout:
            print("text --status missing invalid event log warning", file=sys.stderr)
            print(invalid_event_text.stdout, file=sys.stderr)
            return 1
        api_status_doc = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--api-status",
        )
        if api_status_doc.returncode != 0 or json.loads(api_status_doc.stdout)["schema"] != 1:
            print("--api-status did not return status JSON", file=sys.stderr)
            print(api_status_doc.stdout, file=sys.stderr)
            print(api_status_doc.stderr, file=sys.stderr)
            return 1
        queue_status_text = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--status",
        )
        if ("Command queue:" not in queue_status_text.stdout or
                "Path health:" not in queue_status_text.stdout or
                "state_file: exists=" not in queue_status_text.stdout or
                "API resources: schema=1 resources=" not in queue_status_text.stdout or
                "collections_key=api_collections resources_key=api_resources" not in queue_status_text.stdout or
                "command_queue_commands: records=command_queue.commands" not in queue_status_text.stdout or
                "summary=command_queue_total_count" not in queue_status_text.stdout or
                "enabled=no default_enabled=no" not in queue_status_text.stdout or
                "require_token=yes token_configured=no token_source=manual" not in queue_status_text.stdout or
                "allowed_commands=none execution_mode=metadata-only allow_arbitrary=no active_control_channel=no" not in queue_status_text.stdout or
                "policy_valid=yes configured_for_polling=no arbitrary_policy_requested=no arbitrary_execution_allowed=no" not in queue_status_text.stdout or
                "busierbox reality-test --json" not in queue_status_text.stdout or
                "result-received" not in queue_status_text.stdout or
                "result_output=12 limit=1234 exceeded_limit=no" not in queue_status_text.stdout or
                "command_limits: timeouts=9=1 max_output=1234=1" not in queue_status_text.stdout or
                "result_size_buckets: small=1" not in queue_status_text.stdout or
                "latest_created=" not in queue_status_text.stdout or
                "latest_result=" not in queue_status_text.stdout or
                "modes: total=5 would_poll_if_configured=3 operator_host_required=3 delivery_supported=0 result_upload_supported=5 execution_supported=0 active_control_channel=0" not in queue_status_text.stdout or
                "mode status: lifecycle=inspect requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "mode daemon: lifecycle=long-running requires_operator_host=yes would_poll_if_configured=yes execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "mode stop: lifecycle=stop requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "command_result_received" not in queue_status_text.stdout or
                "Event log:" not in queue_status_text.stdout or
                "services: command-queue=" not in queue_status_text.stdout or
                "events: command_queue_queued=" not in queue_status_text.stdout or
                "levels: info=" not in queue_status_text.stdout or
                "detail_command_ids:" not in queue_status_text.stdout or
                f"{command_id}=1" not in queue_status_text.stdout or
                f"command_id={command_id}" not in queue_status_text.stdout or
                "first=" not in queue_status_text.stdout or
                "latest=" not in queue_status_text.stdout or
                "tls=yes" not in queue_status_text.stdout or
                "tls=no" not in queue_status_text.stdout):
            print("text --status missing command queue/event sections", file=sys.stderr)
            print(queue_status_text.stdout, file=sys.stderr)
            return 1
        cleared = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--clear-command-queue",
        )
        if cleared.returncode != 0 or "cleared 1 command queue entry" not in cleared.stdout:
            print("operator command queue clear failed", file=sys.stderr)
            return 1

        # Test: cert already present → server does not regenerate (no generation message)
        result_existing = run("scripts/busierbox-server", "--config", str(cfg),
                              "--transport", "tls-shell", "--timeout", "0.05")
        if "Generating" in result_existing.stderr or "generating" in result_existing.stderr:
            print("Server re-generated existing cert:", file=sys.stderr)
            return 1

        # Test: legacy socat_listen_port field accepted (compat)
        cfg2 = Path(tmp) / "server-config-legacy.json"
        cfg2.write_text(json.dumps({
            "transport": "tls-shell",
            "listen_host": "127.0.0.1",
            "socat_listen_port": port2,
            "session_root": str(Path(tmp) / "sessions"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
        }), encoding="utf-8")
        result2 = run("scripts/busierbox-server", "--config", str(cfg2),
                      "--transport", "tls-shell", "--timeout", "0.05")
        # Should start without error (cert already exists from above)
        if result2.returncode not in (0, None) and "Error" in result2.stderr:
            print("Legacy socat_listen_port field not accepted:", file=sys.stderr)
            print(result2.stdout, file=sys.stderr)
            print(result2.stderr, file=sys.stderr)
            return 1

        lifecycle_port = free_port()
        lifecycle_cfg = Path(tmp) / "server-config-lifecycle.json"
        lifecycle_state = Path(tmp) / "operator-session" / "lifecycle-state.json"
        lifecycle_staged = Path(tmp) / "operator-session" / "lifecycle-staged.json"
        lifecycle_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": lifecycle_port,
            "session_root": str(Path(tmp) / "sessions-lifecycle"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        lifecycle_proc = subprocess.Popen(
            [
                str(server), "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--managed-by", "workbench-smoke",
                "--process-log", str(Path(tmp) / "operator-session" / "file-service-workbench.log"),
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status_doc = None
        deadline = time.time() + 5
        while time.time() < deadline:
            status = run(
                "scripts/busierbox-server", "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            if status.returncode == 0:
                status_doc = json.loads(status.stdout)
                rows = {row["name"]: row for row in status_doc["services"]}
                if rows["file-service"]["actual"] == "listening" and rows["file-service"].get("pid"):
                    break
            time.sleep(0.05)
        else:
            print("lifecycle file-service did not reach listening state", file=sys.stderr)
            lifecycle_proc.terminate()
            try:
                lifecycle_proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                lifecycle_proc.kill()
                lifecycle_proc.communicate(timeout=2)
            return 1
        rows = {row["name"]: row for row in status_doc["services"]}
        if not rows["file-service"].get("pid"):
            print("status missing file-service pid", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_server_state = status_doc.get("server_state") or {}
        if (lifecycle_server_state.get("valid") is not True or
                lifecycle_server_state.get("service_count", 0) < 1 or
                lifecycle_server_state.get("services", {}).get("file-service", {}).get("status") != "listening" or
                status_doc.get("summary", {}).get("server_state_valid") is not True):
            print("status missing live reusable server-state record", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        state_doc = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        state_service = state_doc.get("services", {}).get("file-service", {})
        if (state_service.get("managed_by") != "workbench-smoke" or
                not state_service.get("process_log", "").endswith("file-service-workbench.log")):
            print("listening child state did not preserve workbench ownership metadata", file=sys.stderr)
            print(json.dumps(state_service, indent=2), file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        if not rows["file-service"].get("listener_pids") or not rows["file-service"].get("listener_processes"):
            print("status missing actual listener pid/process details", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        recorded_pid = str(rows["file-service"].get("pid"))
        listener_pid = str(rows["file-service"].get("listener_pids", [""])[0])
        if ((status_doc.get("services_by_pid") or {}).get(recorded_pid, [{}])[0].get("name") != "file-service" or
                (status_doc.get("services_by_listener_pid") or {}).get(listener_pid, [{}])[0].get("name") != "file-service"):
            print("status missing service PID lookup indexes", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_summary = status_doc.get("summary") or {}
        if (not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_bind_address") or {}).get("127.0.0.1", [])) or
                not any(row.get("name") == "tls-shell" for row in (status_doc.get("services_by_tls") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_tls") or {}).get("no", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_stale") or {}).get("no", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_pid_alive") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_pid_managed") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_listener_bind_mismatch") or {}).get("no", [])) or
                len((status_doc.get("services_by_has_error") or {}).get("no", [])) != 5 or
                lifecycle_summary.get("service_bind_address_counts", {}).get("127.0.0.1") != 5 or
                lifecycle_summary.get("service_tls_counts", {}).get("yes") != 2 or
                lifecycle_summary.get("service_tls_counts", {}).get("no") != 3 or
                lifecycle_summary.get("service_pid_alive_counts", {}).get("yes") != 1 or
                lifecycle_summary.get("service_pid_managed_counts", {}).get("yes") != 1):
            print("status missing service lifecycle/filter indexes", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        endpoints = rows["file-service"].get("listener_endpoints") or []
        if not any(endpoint.get("address") == "127.0.0.1" and endpoint.get("port") == lifecycle_port for endpoint in endpoints):
            print("status missing actual listener endpoint address/port", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_ports_by_number = status_doc.get("ports_by_number") or {}
        lifecycle_port_rows = lifecycle_ports_by_number.get(str(lifecycle_port)) or []
        if (not lifecycle_port_rows or
                lifecycle_port_rows[0].get("service") != "file-service" or
                lifecycle_port_rows[0].get("actual") != "listening" or
                lifecycle_port_rows[0].get("listener_endpoints") != endpoints):
            print("status missing explicit listening port record", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        if not any(endpoint.get("pids") for endpoint in endpoints):
            print("status listener endpoints missing owning PIDs", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        if rows["file-service"].get("tls") is not False or rows["tls-shell"].get("tls") is not True:
            print("status missing normalized service TLS flags", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_status_text = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if f"listener=127.0.0.1:{lifecycle_port}" not in lifecycle_status_text.stdout:
            print("text status missing actual listener endpoint", file=sys.stderr)
            print(lifecycle_status_text.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_start = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.machinery, importlib.util, pathlib, sys; "
                    "p=pathlib.Path(sys.argv[1]); "
                    "loader=importlib.machinery.SourceFileLoader('srv', str(p)); "
                    "spec=importlib.util.spec_from_loader('srv', loader); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "cfg=m.load_config(sys.argv[2]); "
                    "cfg['_config_path']=sys.argv[2]; "
                    "cfg['server_state']=sys.argv[3]; "
                    "cfg['staged_files']=sys.argv[4]; "
                    "m.start_service_process(cfg, 'file-service')"
                ),
                str(server),
                str(lifecycle_cfg),
                str(lifecycle_state),
                str(lifecycle_staged),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if dup_start.returncode != 0 or "already listening" not in dup_start.stdout:
            print("workbench duplicate service start was not skipped cleanly", file=sys.stderr)
            print(dup_start.stdout, file=sys.stderr)
            print(dup_start.stderr, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_state = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        if dup_state.get("services", {}).get("file-service", {}).get("pid") != rows["file-service"].get("pid"):
            print("duplicate service start changed recorded listener pid", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_events = [json.loads(line) for line in (Path(tmp) / "operator-session" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "service_start_skipped" and event.get("details", {}).get("reason") == "already-listening" for event in dup_events):
            print("duplicate service start did not log service_start_skipped", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (stop.returncode != 0 or
                "stopped pid" not in stop.stdout or
                "port released" not in stop.stdout or
                "Stop summary: stopped=1 skipped=0 failed=0" not in stop.stdout):
            print("--stop did not stop managed listener", file=sys.stderr)
            print(stop.stdout, file=sys.stderr)
            print(stop.stderr, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        stdout_life, stderr_life = lifecycle_proc.communicate(timeout=5)
        if lifecycle_proc.returncode not in (0, -15):
            print("managed listener exited unexpectedly after --stop", file=sys.stderr)
            print(stdout_life, file=sys.stderr)
            print(stderr_life, file=sys.stderr)
            return 1
        lifecycle_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        lifecycle_events = [json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()]
        shutdown_events = [
            event for event in lifecycle_events
            if event.get("service") == "file-service" and event.get("event") == "shutdown"
        ]
        if not shutdown_events or shutdown_events[-1].get("details", {}).get("reason") != "SIGTERM":
            print("--stop did not leave a structured SIGTERM shutdown event", file=sys.stderr)
            return 1
        service_stop_events = [
            event for event in lifecycle_events
            if event.get("service") == "file-service" and event.get("event") == "service_stop"
        ]
        if not service_stop_events or service_stop_events[-1].get("details", {}).get("port_released") is not True:
            print("--stop did not record that the listener port was released", file=sys.stderr)
            return 1
        status_after = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        status_after_doc = json.loads(status_after.stdout)
        rows_after = {row["name"]: row for row in status_after_doc["services"]}
        if rows_after["file-service"]["actual"] == "listening":
            print("file-service port still listening after --stop", file=sys.stderr)
            return 1
        stopped_state = (status_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {})
        if stopped_state.get("pid") or stopped_state.get("managed_by") or not stopped_state.get("stopped_at"):
            print("--stop did not clear stopped service ownership fields", file=sys.stderr)
            print(status_after.stdout, file=sys.stderr)
            return 1
        if (not rows_after["file-service"].get("process_log", "").endswith("file-service-workbench.log") or
                not rows_after["file-service"].get("session_log")):
            print("stopped status lost service log context", file=sys.stderr)
            print(status_after.stdout, file=sys.stderr)
            return 1
        rebind = subprocess.Popen(
            [
                str(server), "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        missing_request = b"GET /fetch?name=missing HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        response_rebind = connect_with_retry(lifecycle_port, missing_request)
        stdout_rebind, stderr_rebind = rebind.communicate(timeout=5)
        if rebind.returncode != 0 or b"HTTP/1.1 404" not in response_rebind:
            print("file-service did not rebind cleanly after --stop", file=sys.stderr)
            print(stdout_rebind, file=sys.stderr)
            print(stderr_rebind, file=sys.stderr)
            return 1

        sigint_port = free_port()
        sigint_cfg = Path(tmp) / "server-config-foreground-sigint.json"
        sigint_state = Path(tmp) / "operator-session" / "foreground-sigint-state.json"
        sigint_staged = Path(tmp) / "operator-session" / "foreground-sigint-staged.json"
        sigint_sessions = Path(tmp) / "sessions-foreground-sigint"
        sigint_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": sigint_port,
            "session_root": str(sigint_sessions),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigint_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigint_status = run(
                "scripts/busierbox-server",
                "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--json-status",
            )
            if sigint_status.returncode == 0:
                sigint_status_doc = json.loads(sigint_status.stdout)
                sigint_rows = {row["name"]: row for row in sigint_status_doc.get("services", [])}
                if sigint_rows.get("file-service", {}).get("actual") == "listening":
                    break
            time.sleep(0.05)
        else:
            sigint_proc.terminate()
            print("foreground SIGINT test listener did not start", file=sys.stderr)
            return 1
        sigint_proc.send_signal(signal.SIGINT)
        sigint_stdout, sigint_stderr = sigint_proc.communicate(timeout=5)
        if sigint_proc.returncode != 0 or "Traceback" in (sigint_stderr or ""):
            print("foreground file-service SIGINT did not exit cleanly", file=sys.stderr)
            print(sigint_stdout, file=sys.stderr)
            print(sigint_stderr, file=sys.stderr)
            return 1
        sigint_state_doc = json.loads(sigint_state.read_text(encoding="utf-8"))
        sigint_service = sigint_state_doc.get("services", {}).get("file-service", {})
        if (sigint_service.get("status") != "stopped" or
                sigint_service.get("stopped_reason") != "SIGINT" or
                sigint_service.get("pid") or
                sigint_service.get("managed_by")):
            print("foreground SIGINT did not persist stopped service state", file=sys.stderr)
            print(json.dumps(sigint_state_doc, indent=2), file=sys.stderr)
            return 1
        sigint_session_paths = list(sigint_sessions.glob("*/session.json"))
        if len(sigint_session_paths) != 1:
            print("foreground SIGINT did not write one session record", file=sys.stderr)
            return 1
        sigint_session_doc = json.loads(sigint_session_paths[0].read_text(encoding="utf-8"))
        if (sigint_session_doc.get("state") != "stopped" or
                sigint_session_doc.get("exit_reason") != "SIGINT"):
            print("foreground SIGINT session did not record exit reason", file=sys.stderr)
            print(json.dumps(sigint_session_doc, indent=2), file=sys.stderr)
            return 1
        sigint_events = [
            json.loads(line)
            for line in (sigint_session_paths[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        sigint_stop_events = [
            event for event in sigint_events
            if event.get("event") == "service_stop"
        ]
        if (not sigint_stop_events or
                sigint_stop_events[-1].get("details", {}).get("reason") != "SIGINT" or
                sigint_stop_events[-1].get("details", {}).get("port") != sigint_port):
            print("foreground SIGINT service_stop event did not record reason and port", file=sys.stderr)
            return 1

        tui_owned_port = free_port()
        tui_owned_cfg = Path(tmp) / "server-config-tui-owned.json"
        tui_owned_state = Path(tmp) / "operator-session" / "tui-owned-state.json"
        tui_owned_staged = Path(tmp) / "operator-session" / "tui-owned-staged.json"
        tui_owned_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": tui_owned_port,
            "session_root": str(Path(tmp) / "sessions-tui-owned"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        tui_master, tui_slave = pty.openpty()
        try:
            tui_owned_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(tui_owned_cfg),
                    "--state-file", str(tui_owned_state),
                    "--staged-file", str(tui_owned_staged),
                    "--tui",
                ],
                cwd=ROOT,
                stdin=tui_slave,
                stdout=tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(tui_slave)
            tui_slave = -1
            time.sleep(0.3)
            os.write(tui_master, b"4\n")
            tui_status_doc = None
            deadline = time.time() + 5
            while time.time() < deadline:
                tui_status = run(
                    "scripts/busierbox-server", "--config", str(tui_owned_cfg),
                    "--state-file", str(tui_owned_state),
                    "--staged-file", str(tui_owned_staged),
                    "--json-status",
                )
                if tui_status.returncode == 0:
                    tui_status_doc = json.loads(tui_status.stdout)
                    tui_rows = {row["name"]: row for row in tui_status_doc["services"]}
                    if tui_rows["file-service"]["actual"] == "listening":
                        break
                time.sleep(0.05)
            else:
                print("line TUI did not start managed file-service", file=sys.stderr)
                tui_owned_proc.terminate()
                tui_owned_proc.communicate(timeout=2)
                return 1
            os.write(tui_master, b"q\n")
            _tui_owned_stdout, tui_owned_stderr = tui_owned_proc.communicate(timeout=5)
        finally:
            if tui_slave != -1:
                os.close(tui_slave)
            try:
                os.close(tui_master)
            except OSError:
                pass
        if tui_owned_proc.returncode != 0 or "Traceback" in (tui_owned_stderr or ""):
            print("line TUI did not quit cleanly after starting managed service", file=sys.stderr)
            print(tui_owned_stderr or "", file=sys.stderr)
            return 1
        tui_after = run(
            "scripts/busierbox-server", "--config", str(tui_owned_cfg),
            "--state-file", str(tui_owned_state),
            "--staged-file", str(tui_owned_staged),
            "--json-status",
        )
        tui_after_doc = json.loads(tui_after.stdout)
        tui_after_rows = {row["name"]: row for row in tui_after_doc["services"]}
        if (tui_after_rows["file-service"]["actual"] == "listening" or
                tui_after_doc.get("server_state", {}).get("services", {}).get("file-service", {}).get("status") != "stopped" or
                tui_after_doc.get("server_state", {}).get("services", {}).get("workbench", {}).get("status") != "stopped"):
            print("line TUI quit did not stop services it started", file=sys.stderr)
            print(tui_after.stdout, file=sys.stderr)
            return 1
        try:
            with socket.create_connection(("127.0.0.1", tui_owned_port), timeout=0.2):
                print("line TUI-owned file-service port still listening after quit", file=sys.stderr)
                return 1
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass
        tui_owned_events = [json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()]
        if not any(event.get("service") == "file-service" and event.get("event") == "service_stop" and event.get("details", {}).get("via") == "workbench-stop" for event in tui_owned_events):
            print("line TUI quit did not log workbench-owned service stop", file=sys.stderr)
            return 1

        tui_sigterm_operator_dir = Path(tmp) / "operator-session-tui-sigterm"
        tui_sigterm_cfg = Path(tmp) / "server-config-tui-sigterm.json"
        tui_sigterm_state = tui_sigterm_operator_dir / "server-state.json"
        tui_sigterm_staged = tui_sigterm_operator_dir / "staged-files.json"
        tui_sigterm_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": free_port(),
            "session_root": str(Path(tmp) / "sessions-tui-sigterm"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(tui_sigterm_operator_dir),
        }), encoding="utf-8")
        sigterm_master, sigterm_slave = pty.openpty()
        try:
            tui_sigterm_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(tui_sigterm_cfg),
                    "--state-file", str(tui_sigterm_state),
                    "--staged-file", str(tui_sigterm_staged),
                    "--tui",
                ],
                cwd=ROOT,
                stdin=sigterm_slave,
                stdout=sigterm_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(sigterm_slave)
            sigterm_slave = -1
            deadline = time.time() + 5
            while time.time() < deadline:
                sigterm_status = run(
                    "scripts/busierbox-server", "--config", str(tui_sigterm_cfg),
                    "--state-file", str(tui_sigterm_state),
                    "--staged-file", str(tui_sigterm_staged),
                    "--json-status",
                )
                if sigterm_status.returncode == 0:
                    sigterm_doc = json.loads(sigterm_status.stdout)
                    if (sigterm_doc.get("server_state", {}).get("services", {}).get("workbench") or {}).get("status") == "open":
                        break
                time.sleep(0.05)
            else:
                print("line TUI SIGTERM fixture did not reach open state", file=sys.stderr)
                tui_sigterm_proc.terminate()
                tui_sigterm_proc.communicate(timeout=2)
                return 1
            tui_sigterm_proc.terminate()
            _tui_sigterm_stdout, tui_sigterm_stderr = tui_sigterm_proc.communicate(timeout=5)
        finally:
            if sigterm_slave != -1:
                os.close(sigterm_slave)
            try:
                os.close(sigterm_master)
            except OSError:
                pass
        if tui_sigterm_proc.returncode not in (0, 130, 143, -signal.SIGTERM) or "Traceback" in (tui_sigterm_stderr or ""):
            print("line TUI did not exit cleanly on SIGTERM while waiting for input", file=sys.stderr)
            print(tui_sigterm_stderr or "", file=sys.stderr)
            return 1
        tui_sigterm_after = run(
            "scripts/busierbox-server", "--config", str(tui_sigterm_cfg),
            "--state-file", str(tui_sigterm_state),
            "--staged-file", str(tui_sigterm_staged),
            "--json-status",
        )
        tui_sigterm_doc = json.loads(tui_sigterm_after.stdout)
        tui_sigterm_workbench = tui_sigterm_doc.get("server_state", {}).get("services", {}).get("workbench") or {}
        if tui_sigterm_workbench.get("status") != "stopped" or tui_sigterm_workbench.get("stopped_reason") != "SIGTERM":
            print("line TUI SIGTERM did not mark workbench stopped with SIGTERM reason", file=sys.stderr)
            print(tui_sigterm_after.stdout, file=sys.stderr)
            return 1
        tui_sigterm_events = [
            json.loads(line) for line in (tui_sigterm_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(event.get("service") == "workbench" and event.get("event") == "shutdown" and event.get("details", {}).get("reason") == "SIGTERM" for event in tui_sigterm_events):
            print("line TUI SIGTERM did not write structured workbench shutdown event", file=sys.stderr)
            return 1

        bind_fail_port = free_port()
        bind_fail_cfg = Path(tmp) / "server-config-bind-fail.json"
        bind_fail_state = Path(tmp) / "operator-session" / "bind-fail-state.json"
        bind_fail_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": bind_fail_port,
            "session_root": str(Path(tmp) / "sessions-bind-fail"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_fail_port))
            blocker.listen(1)
            bind_fail = run(
                "scripts/busierbox-server", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "0.05",
            )
        combined_bind = bind_fail.stdout + bind_fail.stderr
        if bind_fail.returncode == 0 or "Traceback" in combined_bind or "unable to bind" not in combined_bind:
            print("bind failure was not reported cleanly", file=sys.stderr)
            print(combined_bind, file=sys.stderr)
            return 1
        state_after_bind = json.loads(bind_fail_state.read_text(encoding="utf-8"))
        if state_after_bind["services"]["file-service"].get("status") != "error":
            print("bind failure did not mark service error", file=sys.stderr)
            return 1
        if not state_after_bind["services"]["file-service"].get("owners"):
            print("bind failure did not record possible listener owners", file=sys.stderr)
            return 1
        bind_fail_status = run(
            "scripts/busierbox-server", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        bind_fail_doc = json.loads(bind_fail_status.stdout)
        bind_fail_warnings = [
            item for item in bind_fail_doc.get("warnings", [])
            if item.get("type") == "service_error" and item.get("service") == "file-service"
        ]
        bind_fail_service = (bind_fail_doc.get("services_by_name") or {}).get("file-service") or {}
        bind_fail_port_rows = (bind_fail_doc.get("ports_by_number") or {}).get(str(bind_fail_port)) or []
        bind_fail_port_row = next((row for row in bind_fail_port_rows if row.get("service") == "file-service"), {})
        bind_fail_services_api = (bind_fail_doc.get("api_collections") or {}).get("services") or {}
        bind_fail_ports_api = (bind_fail_doc.get("api_collections") or {}).get("ports") or {}
        if (not bind_fail_warnings or
                not bind_fail_warnings[-1].get("error") or
                bind_fail_warnings[-1].get("bind_address") != "127.0.0.1" or
                bind_fail_warnings[-1].get("port") != bind_fail_port or
                not bind_fail_warnings[-1].get("owners") or
                bind_fail_service.get("warning_count") != 1 or
                "service_error" not in bind_fail_service.get("warning_types", []) or
                bind_fail_port_row.get("warning_count") != 1 or
                "service_error" not in bind_fail_port_row.get("warning_types", []) or
                bind_fail_doc.get("services_by_has_warnings", {}).get("yes", [{}])[-1].get("name") != "file-service" or
                bind_fail_doc.get("services_by_warning_type", {}).get("service_error", [{}])[-1].get("name") != "file-service" or
                bind_fail_doc.get("ports_by_has_warnings", {}).get("yes", [{}])[-1].get("service") != "file-service" or
                bind_fail_doc.get("ports_by_warning_type", {}).get("service_error", [{}])[-1].get("service") != "file-service" or
                "services_by_has_warnings" not in (bind_fail_services_api.get("indexes") or []) or
                "services_by_warning_type" not in (bind_fail_services_api.get("indexes") or []) or
                "ports_by_has_warnings" not in (bind_fail_ports_api.get("indexes") or []) or
                "ports_by_warning_type" not in (bind_fail_ports_api.get("indexes") or [])):
            print("bind failure status warning missing bind/error/owner context", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        bind_warning_stats = bind_fail_doc.get("warning_stats") or {}
        bind_summary = bind_fail_doc.get("summary") or {}
        if (bind_warning_stats.get("total_count", 0) < 1 or
                bind_warning_stats.get("by_type", {}).get("service_error", 0) < 1 or
                bind_warning_stats.get("by_service", {}).get("file-service", 0) < 1 or
                bind_warning_stats.get("by_port", {}).get(str(bind_fail_port), 0) < 1 or
                bind_summary.get("warning_count", 0) < 1 or
                bind_summary.get("warning_type_counts", {}).get("service_error", 0) < 1 or
                bind_summary.get("warning_service_counts", {}).get("file-service", 0) < 1 or
                bind_summary.get("warning_port_counts", {}).get(str(bind_fail_port), 0) < 1 or
                bind_summary.get("service_warning_count", 0) < 1 or
                bind_summary.get("service_warning_type_counts", {}).get("service_error", 0) < 1 or
                bind_summary.get("port_warning_count", 0) < 1 or
                bind_summary.get("port_warning_type_counts", {}).get("service_error", 0) < 1):
            print("bind failure status missing warning aggregate stats", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        warnings_by_type = bind_fail_doc.get("warnings_by_type") or {}
        warnings_by_service = bind_fail_doc.get("warnings_by_service") or {}
        warnings_by_port = bind_fail_doc.get("warnings_by_port") or {}
        if (not warnings_by_type.get("service_error") or
                warnings_by_type["service_error"][-1].get("service") != "file-service" or
                not warnings_by_service.get("file-service") or
                warnings_by_service["file-service"][-1].get("type") != "service_error" or
                not warnings_by_port.get(str(bind_fail_port)) or
                warnings_by_port[str(bind_fail_port)][-1].get("type") != "service_error"):
            print("bind failure status missing warning lookup indexes", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        owner_pid = str((bind_fail_warnings[-1].get("owners") or [{}])[-1].get("pid") or "")
        warnings_by_owner_pid = bind_fail_doc.get("warnings_by_owner_pid") or {}
        if (not owner_pid or
                bind_warning_stats.get("by_owner_pid", {}).get(owner_pid, 0) < 1 or
                bind_summary.get("warning_owner_pid_counts", {}).get(owner_pid, 0) < 1 or
                not warnings_by_owner_pid.get(owner_pid) or
                warnings_by_owner_pid[owner_pid][-1].get("service") != "file-service"):
            print("bind failure status missing warning owner-pid index", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        service_port_key = f"file-service:{bind_fail_port}"
        type_service_port_key = f"service_error:{service_port_key}"
        if (bind_warning_stats.get("by_service_port", {}).get(service_port_key, 0) < 1 or
                bind_warning_stats.get("by_type_service_port", {}).get(type_service_port_key, 0) < 1 or
                bind_summary.get("warning_service_port_counts", {}).get(service_port_key, 0) < 1 or
                bind_summary.get("warning_type_service_port_counts", {}).get(type_service_port_key, 0) < 1 or
                bind_fail_doc.get("warnings_by_service_port", {}).get(service_port_key, [{}])[-1].get("type") != "service_error" or
                bind_fail_doc.get("warnings_by_type_service_port", {}).get(type_service_port_key, [{}])[-1].get("service") != "file-service"):
            print("bind failure status missing service:port warning indexes", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        bind_fail_text_status = run(
            "scripts/busierbox-server", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if (f"file-service bind=127.0.0.1 port={bind_fail_port}" not in bind_fail_text_status.stdout or
                "configured=error" not in bind_fail_text_status.stdout or
                "warnings=1:service_error" not in bind_fail_text_status.stdout or
                "Warning summary:" not in bind_fail_text_status.stdout or
                "service_error=1" not in bind_fail_text_status.stdout or
                "services=file-service=1" not in bind_fail_text_status.stdout or
                f"ports={bind_fail_port}=1" not in bind_fail_text_status.stdout):
            print("bind failure text status missing inline service warning badge", file=sys.stderr)
            print(bind_fail_text_status.stdout, file=sys.stderr)
            return 1
        bind_fail_workbench = run(
            "scripts/busierbox-server", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
            "--tui",
        )
        if ("Warnings:" not in bind_fail_workbench.stdout or
                "service_error file-service" not in bind_fail_workbench.stdout or
                "unable to bind" not in bind_fail_workbench.stdout or
                f"bind: 127.0.0.1:{bind_fail_port}" not in bind_fail_workbench.stdout or
                "owner_pid=" not in bind_fail_workbench.stdout or
                "suggested_action:" not in bind_fail_workbench.stdout or
                "Warning summary:" not in bind_fail_workbench.stdout or
                "service_error=1" not in bind_fail_workbench.stdout or
                "services=file-service=1" not in bind_fail_workbench.stdout or
                f"ports={bind_fail_port}=1" not in bind_fail_workbench.stdout or
                "bind_error=" not in bind_fail_workbench.stdout or
                "error=" not in bind_fail_workbench.stdout or
                "file-service:bind_error" not in bind_fail_workbench.stdout):
            print("workbench did not surface bind failure warnings", file=sys.stderr)
            print(bind_fail_workbench.stdout, file=sys.stderr)
            return 1
        bind_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        bind_events = [json.loads(line) for line in bind_events_path.read_text(encoding="utf-8").splitlines()]
        bind_error = [event for event in bind_events if event.get("event") == "bind_error"]
        if not bind_error:
            print("bind failure did not write structured bind_error event", file=sys.stderr)
            return 1
        if bind_error[-1].get("service") != "file-service" or bind_error[-1].get("level") != "error":
            print("bind_error event missing service/error level", file=sys.stderr)
            return 1
        if bind_error[-1].get("details", {}).get("port") != bind_fail_port:
            print("bind_error event missing failed port", file=sys.stderr)
            return 1

        unexpected_state = {
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "stopped",
                    "pid": "",
                    "listen_host": "127.0.0.1",
                    "file_service_port": bind_fail_port,
                    "updated_at": "unexpected-listener",
                }
            },
            "sessions": [],
        }
        bind_fail_state.write_text(json.dumps(unexpected_state, indent=2) + "\n", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_fail_port))
            blocker.listen(1)
            unexpected_status = run(
                "scripts/busierbox-server", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--status",
            )
            if "actual listener detected while configured state is not listening" not in unexpected_status.stdout:
                print("--status did not warn on unexpected actual listener", file=sys.stderr)
                print(unexpected_status.stdout, file=sys.stderr)
                return 1
            unexpected_json = run(
                "scripts/busierbox-server", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            unexpected_doc = json.loads(unexpected_json.stdout)
            unexpected_warnings = [
                item for item in unexpected_doc.get("warnings", [])
                if item.get("type") == "unexpected_listener" and item.get("service") == "file-service"
            ]
            if (not unexpected_warnings or
                    not unexpected_warnings[-1].get("listener_pids") or
                    unexpected_warnings[-1].get("configured") != "stopped" or
                    unexpected_warnings[-1].get("actual") != "listening"):
                print("--json-status did not expose structured unexpected listener warning", file=sys.stderr)
                print(unexpected_json.stdout, file=sys.stderr)
                return 1

        bind_mismatch_port = free_port()
        bind_mismatch_cfg = Path(tmp) / "server-config-bind-mismatch.json"
        bind_mismatch_state = Path(tmp) / "operator-session" / "bind-mismatch-state.json"
        bind_mismatch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.2",
            "file_service_port": bind_mismatch_port,
            "session_root": str(Path(tmp) / "sessions-bind-mismatch"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        bind_mismatch_state.write_text(json.dumps({
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "stopped",
                    "pid": "",
                    "listen_host": "127.0.0.2",
                    "file_service_port": bind_mismatch_port,
                    "updated_at": "bind-mismatch",
                }
            },
            "sessions": [],
        }, indent=2) + "\n", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_mismatch_port))
            blocker.listen(1)
            bind_mismatch_text = run(
                "scripts/busierbox-server", "--config", str(bind_mismatch_cfg),
                "--state-file", str(bind_mismatch_state),
                "--staged-file", str(lifecycle_staged),
                "--status",
            )
            if "listener found on configured port but not configured bind address" not in bind_mismatch_text.stdout:
                print("--status did not warn on listener bind-address mismatch", file=sys.stderr)
                print(bind_mismatch_text.stdout, file=sys.stderr)
                return 1
            bind_mismatch_json = run(
                "scripts/busierbox-server", "--config", str(bind_mismatch_cfg),
                "--state-file", str(bind_mismatch_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            bind_mismatch_doc = json.loads(bind_mismatch_json.stdout)
            bind_mismatch_service = (bind_mismatch_doc.get("services_by_name") or {}).get("file-service") or {}
            bind_mismatch_warnings = [
                item for item in bind_mismatch_doc.get("warnings", [])
                if item.get("type") == "listener_bind_mismatch" and item.get("service") == "file-service"
            ]
            if (bind_mismatch_service.get("actual") != "stopped" or
                    not bind_mismatch_service.get("listener_endpoints") or
                    bind_mismatch_service.get("matching_listener_endpoints") or
                    not bind_mismatch_warnings or
                    bind_mismatch_warnings[-1].get("bind_address") != "127.0.0.2" or
                    bind_mismatch_warnings[-1].get("actual") != "stopped"):
                print("--json-status did not expose listener bind-address mismatch", file=sys.stderr)
                print(bind_mismatch_json.stdout, file=sys.stderr)
                return 1

        state_after_bind["services"]["file-service"].update({"status": "listening", "pid": 999999, "updated_at": "stale"})
        lifecycle_state.write_text(json.dumps(state_after_bind, indent=2) + "\n", encoding="utf-8")
        stale = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if "stale-state" not in stale.stdout:
            print("--status did not warn on stale listening state", file=sys.stderr)
            print(stale.stdout, file=sys.stderr)
            return 1
        stale_json = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        stale_doc = json.loads(stale_json.stdout)
        stale_warnings = [
            item for item in stale_doc.get("warnings", [])
            if item.get("type") == "stale_state" and item.get("service") == "file-service"
        ]
        if (stale_doc.get("summary", {}).get("stale_count", 0) < 1 or
                not stale_warnings or
                stale_warnings[-1].get("pid") != 999999 or
                stale_warnings[-1].get("configured") != "listening" or
                stale_warnings[-1].get("actual") != "stopped"):
            print("--json-status did not expose structured stale-state warning", file=sys.stderr)
            return 1
        stale_stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (stale_stop.returncode != 0 or
                "stale pid 999999; marked stopped" not in stale_stop.stdout or
                "Stop summary: stopped=0 skipped=1 failed=0" not in stale_stop.stdout):
            print("--stop did not clean stale PID records", file=sys.stderr)
            print(stale_stop.stdout, file=sys.stderr)
            print(stale_stop.stderr, file=sys.stderr)
            return 1
        stale_clean_doc = json.loads(run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        ).stdout)
        stale_clean_state = stale_clean_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (stale_clean_state.get("status") != "stopped" or
                stale_clean_state.get("pid") or
                stale_clean_state.get("managed_by") or
                not stale_clean_state.get("stopped_at")):
            print("--stop stale PID cleanup left misleading ownership fields", file=sys.stderr)
            print(json.dumps(stale_clean_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        events_after_stale_stop = [
            json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()
        ]
        stale_cleanup_events = [
            event for event in events_after_stale_stop
            if event.get("service") == "file-service"
            and event.get("event") == "service_stop"
            and event.get("details", {}).get("reason") == "stale-pid"
        ]
        if not stale_cleanup_events:
            print("--stop did not log stale PID cleanup event", file=sys.stderr)
            return 1

        sigint_port = free_port()
        sigint_cfg = Path(tmp) / "server-config-sigint.json"
        sigint_state = Path(tmp) / "operator-session" / "sigint-state.json"
        sigint_staged = Path(tmp) / "operator-session" / "sigint-staged.json"
        sigint_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": sigint_port,
            "session_root": str(Path(tmp) / "sessions-sigint"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigint_proc = subprocess.Popen(
            [
                str(server), "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigint_status = run(
                "scripts/busierbox-server", "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--json-status",
            )
            if sigint_status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(sigint_status.stdout)["services"]}
                if rows["file-service"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("SIGINT lifecycle file-service did not reach listening state", file=sys.stderr)
            sigint_proc.terminate()
            sigint_proc.communicate(timeout=2)
            return 1
        sigint_proc.send_signal(signal.SIGINT)
        sigint_stdout, sigint_stderr = sigint_proc.communicate(timeout=5)
        sigint_combined = sigint_stdout + sigint_stderr
        if sigint_proc.returncode not in (0, 130) or "Traceback" in sigint_combined:
            print("SIGINT foreground listener did not exit cleanly", file=sys.stderr)
            print(sigint_combined, file=sys.stderr)
            return 1
        sigint_after = run(
            "scripts/busierbox-server", "--config", str(sigint_cfg),
            "--state-file", str(sigint_state),
            "--staged-file", str(sigint_staged),
            "--json-status",
        )
        sigint_after_doc = json.loads(sigint_after.stdout)
        sigint_rows = {row["name"]: row for row in sigint_after_doc["services"]}
        if sigint_rows["file-service"]["actual"] == "listening" or sigint_rows["file-service"]["configured"] != "stopped":
            print("SIGINT foreground listener did not stop and release its port", file=sys.stderr)
            print(sigint_after.stdout, file=sys.stderr)
            return 1
        sigint_state_rec = sigint_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (sigint_state_rec.get("stopped_reason") != "SIGINT" or
                sigint_rows["file-service"].get("stopped_reason") != "SIGINT" or
                not sigint_state_rec.get("stopped_at")):
            print("SIGINT foreground listener did not preserve stopped reason in status", file=sys.stderr)
            print(sigint_after.stdout, file=sys.stderr)
            return 1
        sigint_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        sigint_events = [json.loads(line) for line in sigint_events_path.read_text(encoding="utf-8").splitlines()]
        sigint_shutdowns = [
            event for event in sigint_events
            if event.get("service") == "file-service"
            and event.get("event") == "shutdown"
            and event.get("details", {}).get("reason") == "SIGINT"
        ]
        if not sigint_shutdowns:
            print("SIGINT foreground listener did not record structured shutdown event", file=sys.stderr)
            return 1

        sigterm_port = free_port()
        sigterm_cfg = Path(tmp) / "server-config-sigterm.json"
        sigterm_state = Path(tmp) / "operator-session" / "sigterm-state.json"
        sigterm_staged = Path(tmp) / "operator-session" / "sigterm-staged.json"
        sigterm_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": sigterm_port,
            "session_root": str(Path(tmp) / "sessions-sigterm"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigterm_proc = subprocess.Popen(
            [
                str(server), "--config", str(sigterm_cfg),
                "--state-file", str(sigterm_state),
                "--staged-file", str(sigterm_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigterm_status = run(
                "scripts/busierbox-server", "--config", str(sigterm_cfg),
                "--state-file", str(sigterm_state),
                "--staged-file", str(sigterm_staged),
                "--json-status",
            )
            if sigterm_status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(sigterm_status.stdout)["services"]}
                if rows["file-service"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("SIGTERM lifecycle file-service did not reach listening state", file=sys.stderr)
            sigterm_proc.terminate()
            sigterm_proc.communicate(timeout=2)
            return 1
        sigterm_proc.terminate()
        sigterm_stdout, sigterm_stderr = sigterm_proc.communicate(timeout=5)
        sigterm_combined = sigterm_stdout + sigterm_stderr
        if sigterm_proc.returncode not in (0, 143, -signal.SIGTERM) or "Traceback" in sigterm_combined:
            print("SIGTERM foreground listener did not exit cleanly", file=sys.stderr)
            print(sigterm_combined, file=sys.stderr)
            return 1
        sigterm_after = run(
            "scripts/busierbox-server", "--config", str(sigterm_cfg),
            "--state-file", str(sigterm_state),
            "--staged-file", str(sigterm_staged),
            "--json-status",
        )
        sigterm_after_doc = json.loads(sigterm_after.stdout)
        sigterm_rows = {row["name"]: row for row in sigterm_after_doc["services"]}
        sigterm_state_rec = sigterm_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (sigterm_rows["file-service"]["actual"] == "listening" or
                sigterm_rows["file-service"]["configured"] != "stopped" or
                sigterm_state_rec.get("stopped_reason") != "SIGTERM" or
                sigterm_rows["file-service"].get("stopped_reason") != "SIGTERM" or
                not sigterm_state_rec.get("stopped_at")):
            print("SIGTERM foreground listener did not stop and preserve stopped reason", file=sys.stderr)
            print(sigterm_after.stdout, file=sys.stderr)
            return 1
        sigterm_events = [json.loads(line) for line in sigint_events_path.read_text(encoding="utf-8").splitlines()]
        sigterm_shutdowns = [
            event for event in sigterm_events
            if event.get("service") == "file-service"
            and event.get("event") == "shutdown"
            and event.get("details", {}).get("reason") == "SIGTERM"
        ]
        if not sigterm_shutdowns:
            print("SIGTERM foreground listener did not record structured shutdown event", file=sys.stderr)
            return 1

        unmanaged_state = {
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "listening",
                    "pid": os.getpid(),
                    "listen_host": "127.0.0.1",
                    "file_service_port": lifecycle_port,
                    "updated_at": "unmanaged",
                }
            },
            "sessions": [],
        }
        lifecycle_state.write_text(json.dumps(unmanaged_state, indent=2) + "\n", encoding="utf-8")
        unmanaged_status = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        unmanaged_doc = json.loads(unmanaged_status.stdout)
        unmanaged_rows = {row["name"]: row for row in unmanaged_doc["services"]}
        unmanaged_warnings = [
            item for item in unmanaged_doc.get("warnings", [])
            if item.get("type") == "unmanaged_recorded_pid" and item.get("service") == "file-service"
        ]
        if (unmanaged_rows["file-service"].get("pid_managed") is not False or
                unmanaged_rows["file-service"].get("ownership_evidence") or
                not unmanaged_warnings or
                unmanaged_warnings[-1].get("pid") != os.getpid() or
                unmanaged_warnings[-1].get("pid_managed") is not False):
            print("--json-status did not expose unmanaged recorded PID warning", file=sys.stderr)
            return 1
        unmanaged_stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (unmanaged_stop.returncode != 0 or
                "skipped pid" not in unmanaged_stop.stdout or
                "Stop summary: stopped=0 skipped=1 failed=0" not in unmanaged_stop.stdout):
            print("--stop did not skip unmanaged live PID", file=sys.stderr)
            print(unmanaged_stop.stdout, file=sys.stderr)
            print(unmanaged_stop.stderr, file=sys.stderr)
            return 1
        unmanaged_after = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        if unmanaged_after["services"]["file-service"].get("status") != "listening":
            print("--stop changed unmanaged live PID state", file=sys.stderr)
            return 1
        unmanaged_events = [
            json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()
        ]
        unmanaged_skips = [
            event for event in unmanaged_events
            if event.get("service") == "file-service"
            and event.get("event") == "service_stop_skipped"
            and event.get("details", {}).get("reason") == "unmanaged-pid"
            and event.get("details", {}).get("via") == "server-stop"
        ]
        if not unmanaged_skips:
            print("--stop did not log unmanaged PID skip event", file=sys.stderr)
            return 1

        upload_port = free_port()
        upload_cfg = Path(tmp) / "server-config-upload.json"
        session_root = Path(tmp) / "sessions-upload"
        upload_operator_dir = Path(tmp) / "operator-session-upload"
        upload_cfg.write_text(json.dumps({
            "file_service_enable": "yes",
            "listen_host": "127.0.0.1",
            "file_service_port": upload_port,
            "session_root": str(session_root),
            "operator_session_dir": str(upload_operator_dir),
            "server_state": str(upload_operator_dir / "server-state.json"),
            "staged_files": str(upload_operator_dir / "staged-files.json"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "rshell_session_policy": "reconnect",
            "rshell_retry_count": "2",
            "rshell_retry_interval_sec": "3",
            "rshell_retry_jitter_pct": "10",
            "rshell_retry_backoff": "linear",
            "rshell_retry_max_interval_sec": "8",
        }), encoding="utf-8")
        proc = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--file-service",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        context = ssl._create_unverified_context()
        payload = b"busierbox evidence\n"
        request = (
            "PUT /upload/evidence.txt HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-BusierBox-Source-Path: /tmp/evidence.txt\r\n"
            "X-BusierBox-Upload-Kind: evidence\r\n"
            "X-BusierBox-UID: 0\r\n"
            "X-BusierBox-GID: 0\r\n"
            "X-BusierBox-Mode: 0644\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "\r\n"
        ).encode("ascii") + payload
        deadline = time.time() + 5
        response = b""
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", upload_port), timeout=0.5) as raw:
                    with context.wrap_socket(raw, server_hostname="busierbox") as tls:
                        tls.sendall(request)
                        while True:
                            chunk = tls.recv(65536)
                            if not chunk:
                                break
                            response += chunk
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(0.05)
        stdout, stderr = proc.communicate(timeout=5)
        if proc.returncode != 0:
            print("file service exited nonzero:", file=sys.stderr)
            print(stdout, file=sys.stderr)
            print(stderr, file=sys.stderr)
            return 1
        if b"HTTP/1.1 200 OK" not in response:
            print("file service did not return HTTP 200:", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        uploaded = list(session_root.glob("*/files/evidence.txt"))
        if len(uploaded) != 1 or uploaded[0].read_bytes() != payload:
            print("file service did not store uploaded payload", file=sys.stderr)
            return 1
        metadata_path = uploaded[0].with_name(uploaded[0].name + ".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_path") != "/tmp/evidence.txt" or metadata.get("upload_kind") != "evidence":
            print("file service metadata missing source path/upload kind", file=sys.stderr)
            return 1
        if metadata.get("size") != len(payload) or metadata.get("transfer_status") != "ok":
            print("file service metadata has wrong size/status", file=sys.stderr)
            return 1
        if len(metadata.get("sha256", "")) != 64:
            print("file service metadata missing sha256", file=sys.stderr)
            return 1
        session_json_paths = list(session_root.glob("*/session.json"))
        if len(session_json_paths) != 1:
            print("file service did not write session.json", file=sys.stderr)
            return 1
        session_doc = json.loads(session_json_paths[0].read_text(encoding="utf-8"))
        if (session_doc.get("service") != "file-service" or
                session_doc.get("state") != "stopped" or
                not session_doc.get("session_id") or
                not session_doc.get("uploads") or
                not isinstance(session_doc.get("duration_sec"), int)):
            print("file service session.json missing structured fields", file=sys.stderr)
            print(session_doc, file=sys.stderr)
            return 1
        session_doc["exit_reason"] = "clean shutdown"
        session_json_paths[0].write_text(json.dumps(session_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session_events = [json.loads(line) for line in (session_json_paths[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        event_names = {event.get("event") for event in session_events}
        for expected_event in ("service_start", "connection_open", "upload_start", "upload_complete", "connection_close", "service_stop"):
            if expected_event not in event_names:
                print(f"session events missing {expected_event}", file=sys.stderr)
                return 1
        if any(event.get("session") != session_doc.get("session_id") for event in session_events):
            print("session event records should carry the session id, not an empty/path value", file=sys.stderr)
            return 1
        if any(not event.get("id") or not event.get("session_path") for event in session_events):
            print("session event records should carry stable ids and session paths", file=sys.stderr)
            return 1
        if any(event.get("session_path") != str(session_json_paths[0].parent) for event in session_events):
            print("session event records should carry the exact session path", file=sys.stderr)
            return 1
        close_events = [event for event in session_events if event.get("event") == "connection_close"]
        if (not close_events or
                close_events[-1].get("details", {}).get("operation") != "upload" or
                close_events[-1].get("details", {}).get("status") != "ok" or
                close_events[-1].get("details", {}).get("http_status") != 200 or
                close_events[-1].get("details", {}).get("filename") != "evidence.txt"):
            print("file-service connection_close event missing request outcome details", file=sys.stderr)
            return 1
        global_events_path = upload_operator_dir / "events.jsonl"
        global_events = [json.loads(line) for line in global_events_path.read_text(encoding="utf-8").splitlines()]
        if "upload_complete" not in {event.get("event") for event in global_events}:
            print("global operator event log missing upload_complete", file=sys.stderr)
            return 1
        if any(not event.get("id") for event in global_events):
            print("global operator event log entries should carry stable ids", file=sys.stderr)
            return 1
        session_global_events = [
            event for event in global_events
            if event.get("session") == session_doc.get("session_id")
        ]
        if not session_global_events:
            print("global operator event log missing session-correlated events", file=sys.stderr)
            return 1
        upload_state = json.loads((upload_operator_dir / "server-state.json").read_text(encoding="utf-8"))
        if not any(item.get("session_id") == session_doc.get("session_id") for item in upload_state.get("sessions", [])):
            print("server-state sessions missing file-service session id", file=sys.stderr)
            return 1
        upload_status_json = run(
            "scripts/busierbox-server",
            "--config", str(upload_cfg),
            "--json-status",
        )
        upload_doc = json.loads(upload_status_json.stdout)
        upload_event_stats = upload_doc.get("event_log_stats") or {}
        upload_summary = upload_doc.get("summary") or {}
        session_close_key = f"{session_doc.get('session_id')}:connection_close"
        if (upload_event_stats.get("by_session_event", {}).get(session_close_key) != 1 or
                upload_summary.get("event_session_event_counts", {}).get(session_close_key) != 1 or
                upload_summary.get("event_service_event_counts", {}).get("file-service:upload_complete", 0) < 1):
            print("server json status missing full-log session/event aggregate counters", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_commands = upload_doc.get("target_commands") or []
        for expected_command in (
            "./busierbox survey push",
            "./busierbox reality-test push",
            "./busierbox manifest push",
            "./busierbox config-push",
            "./busierbox evidence push",
        ):
            if not any(expected_command in command for command in target_commands):
                print(f"server json status missing generated target command: {expected_command}", file=sys.stderr)
                print(upload_status_json.stdout, file=sys.stderr)
                return 1
        target_records = upload_doc.get("target_command_records") or []
        if not target_records or len(target_records) != len(target_commands):
            print("server json status missing structured target command records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if any(
            rec.get("side") != "target" or
            rec.get("requires_explicit_target_action") is not True or
            rec.get("executes_operator_supplied_commands") is not False
            for rec in target_records
        ):
            print("server target command records weakened the explicit-action safety boundary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_summary = upload_doc.get("target_command_summary") or {}
        if (target_summary.get("total_count") != len(target_records) or
                target_summary.get("target_count") != len(target_records) or
                target_summary.get("network_count") != len(target_records) or
                target_summary.get("explicit_target_action_count") != len(target_records) or
                target_summary.get("operator_supplied_command_execution_count") != 0 or
                target_summary.get("executes_operator_supplied_commands") is not False or
                target_summary.get("all_require_explicit_target_action") is not True or
                target_summary.get("by_side", {}).get("target") != len(target_records) or
                target_summary.get("by_purpose", {}).get("start the configured reverse shell transport from the target") != 1):
            print("server json status missing target command safety summary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_summary = upload_doc.get("summary", {})
        if (upload_summary.get("target_command_count") != len(target_records) or
                upload_summary.get("target_command_network_count") != len(target_records) or
                upload_summary.get("target_command_explicit_action_count") != len(target_records) or
                upload_summary.get("target_command_operator_supplied_execution_count") != 0 or
                upload_summary.get("target_command_copy_supported_count") != len(target_records) or
                upload_summary.get("target_command_executes_operator_supplied_commands") is not False or
                upload_summary.get("target_command_all_require_explicit_target_action") is not True or
                upload_summary.get("target_command_side_counts", {}).get("target") != len(target_records) or
                upload_summary.get("target_command_purpose_counts", {}).get("start the configured reverse shell transport from the target") != 1):
            print("server json status missing aggregate target command safety counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_commands_by_service = upload_doc.get("target_commands_by_service") or {}
        target_commands_by_side = upload_doc.get("target_commands_by_side") or {}
        target_commands_by_purpose = upload_doc.get("target_commands_by_purpose") or {}
        target_commands_by_service_purpose = upload_doc.get("target_commands_by_service_purpose") or {}
        target_commands_by_side_purpose = upload_doc.get("target_commands_by_side_purpose") or {}
        target_commands_by_network = upload_doc.get("target_commands_by_network") or {}
        target_commands_by_explicit_action = upload_doc.get("target_commands_by_requires_explicit_target_action") or {}
        target_commands_by_operator_supplied = upload_doc.get("target_commands_by_executes_operator_supplied_commands") or {}
        target_commands_by_ordinal = upload_doc.get("target_commands_by_ordinal") or {}
        target_commands_by_sha = upload_doc.get("target_commands_by_command_sha256") or {}
        target_commands_by_copy_supported = upload_doc.get("target_commands_by_copy_supported") or {}
        target_commands_by_session_policy = upload_doc.get("target_commands_by_session_policy") or {}
        target_commands_by_session_policy_valid = upload_doc.get("target_commands_by_session_policy_valid") or {}
        target_commands_by_retry_backoff = upload_doc.get("target_commands_by_retry_backoff") or {}
        target_commands_by_retry_interval = upload_doc.get("target_commands_by_retry_interval_sec") or {}
        target_commands_by_retry_post_disconnect = upload_doc.get("target_commands_by_retry_post_disconnect_count") or {}
        rshell_record = next((rec for rec in target_records if rec.get("service") == "rshell"), {})
        rshell_metadata = rshell_record.get("metadata") or {}
        rshell_semantics = rshell_metadata.get("session_semantics") or {}
        rshell_policy_summary = rshell_metadata.get("session_policy_summary") or {}
        rshell_retry = rshell_metadata.get("retry") or {}
        rshell_retry_timing = rshell_metadata.get("retry_timing") or {}
        rshell_purpose = "start the configured reverse shell transport from the target"
        if (len(target_commands_by_service.get("file-service") or []) < 6 or
                len(target_commands_by_side.get("target") or []) != len(target_records) or
                len(target_commands_by_purpose.get(rshell_purpose) or []) != 1 or
                len(target_commands_by_service_purpose.get(f"rshell:{rshell_purpose}") or []) != 1 or
                len(target_commands_by_side_purpose.get(f"target:{rshell_purpose}") or []) != 1 or
                len(target_commands_by_network.get("True") or []) != len(target_records) or
                len(target_commands_by_explicit_action.get("True") or []) != len(target_records) or
                target_commands_by_operator_supplied.get("True", []) != [] or
                len(target_commands_by_operator_supplied.get("False") or []) != len(target_records) or
                target_commands_by_ordinal.get("1", {}).get("copy_selector") != "1" or
                target_commands_by_ordinal.get("1", {}).get("command_sha256") not in target_commands_by_sha or
                len(target_commands_by_copy_supported.get("True") or []) != len(target_records) or
                "target_commands_by_executes_operator_supplied_commands" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_ordinal" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_command_sha256" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_copy_supported" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_retry_backoff" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                not rshell_record or
                target_commands_by_session_policy.get("reconnect", [{}])[0].get("service") != "rshell" or
                target_commands_by_session_policy_valid.get("True", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_backoff.get("linear", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_interval.get("3", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_post_disconnect.get("2", [{}])[0].get("service") != "rshell" or
                rshell_metadata.get("session_policy") != "reconnect" or
                rshell_metadata.get("session_policy_valid") is not True or
                rshell_metadata.get("session_policy_errors") != [] or
                rshell_semantics.get("reconnect_after_disconnect") is not True or
                rshell_semantics.get("fresh_session_on_reconnect") is not True or
                rshell_semantics.get("session_resume_supported") is not False or
                rshell_policy_summary.get("errors") != [] or
                rshell_policy_summary.get("retry_scope") != "pre-connect+post-disconnect" or
                rshell_policy_summary.get("pre_connect_retry_count") != "2" or
                rshell_policy_summary.get("post_disconnect_retry_count") != "2" or
                rshell_policy_summary.get("fresh_session_on_reconnect") is not True or
                rshell_policy_summary.get("session_resume_supported") is not False or
                rshell_retry.get("count") != "2" or
                rshell_retry.get("pre_connect_count") != "2" or
                rshell_retry.get("post_disconnect_count") != "2" or
                rshell_retry.get("interval_sec") != "3" or
                rshell_retry.get("jitter_pct") != "10" or
                rshell_retry.get("backoff") != "linear" or
                rshell_retry.get("max_interval_sec") != "8" or
                rshell_retry_timing.get("sample_delays_sec") != [3, 6, 8] or
                rshell_retry_timing.get("sample_delays_exclude_jitter") is not True or
                target_summary.get("by_service", {}).get("file-service", 0) < 6 or
                target_summary.get("by_service", {}).get("rshell") != 1 or
                target_summary.get("copy_supported_count") != len(target_records) or
                target_summary.get("by_session_policy", {}).get("reconnect") != 1 or
                target_summary.get("by_session_policy_valid", {}).get("True") != 1 or
                target_summary.get("session_policy_error_count") != 0 or
                target_summary.get("by_retry_backoff", {}).get("linear") != 1 or
                upload_summary.get("target_command_session_policy_counts", {}).get("reconnect") != 1 or
                upload_summary.get("target_command_session_policy_valid_counts", {}).get("True") != 1 or
                upload_summary.get("target_command_session_policy_error_count") != 0 or
                upload_summary.get("target_command_retry_backoff_counts", {}).get("linear") != 1):
            print("server json status missing generated command service/session-policy lookup", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("upload_count", 0) < 1 or
                upload_summary.get("upload_total_size") != len(payload) or
                upload_summary.get("upload_stored_exists_count") != 1 or
                upload_summary.get("upload_stored_missing_count") != 0 or
                upload_summary.get("upload_kind_counts", {}).get("evidence") != 1 or
                upload_summary.get("upload_status_counts", {}).get("ok") != 1 or
                upload_summary.get("session_count", 0) < 1 or
                upload_summary.get("session_service_counts", {}).get("file-service") != 1 or
                upload_summary.get("session_state_counts", {}).get("stopped") != 1 or
                upload_summary.get("session_exit_reason_counts", {}).get("clean shutdown") != 1 or
                upload_summary.get("event_count", 0) < 1):
            print("server json status missing aggregate upload/session/event counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_item = (upload_doc.get("uploads") or [{}])[0]
        if (upload_item.get("metadata_path") != str(metadata_path) or
                upload_item.get("stored_exists") is not True or
                upload_item.get("session_id") != session_json_paths[0].parent.name or
                upload_item.get("session_path") != str(session_json_paths[0].parent) or
                upload_item.get("metadata_exists") is not True or
                upload_item.get("event_log_exists") is not True or
                upload_item.get("event_log") != str(session_json_paths[0].parent / "events.jsonl") or
                upload_item.get("sha256_prefix") != metadata.get("sha256", "")[:12] or
                upload_item.get("upload_kind") != "evidence" or
                upload_item.get("status") != "ok"):
            print("server json status missing upload browser metadata", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        uploads_by_session = upload_doc.get("uploads_by_session") or {}
        session_uploads = uploads_by_session.get(session_json_paths[0].parent.name) or []
        if (len(session_uploads) != 1 or
                session_uploads[0].get("metadata_path") != str(metadata_path) or
                session_uploads[0].get("stored_exists") is not True):
            print("server json status missing uploads_by_session browser grouping", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        uploads_by_filename = upload_doc.get("uploads_by_filename") or {}
        uploads_by_kind = upload_doc.get("uploads_by_kind") or {}
        uploads_by_sha = upload_doc.get("uploads_by_sha256") or {}
        uploads_by_source = upload_doc.get("uploads_by_source_path") or {}
        uploads_by_stored = upload_doc.get("uploads_by_stored_path") or {}
        uploads_by_stored_exists = upload_doc.get("uploads_by_stored_exists") or {}
        uploads_by_metadata_exists = upload_doc.get("uploads_by_metadata_exists") or {}
        uploads_by_event_log_exists = upload_doc.get("uploads_by_event_log_exists") or {}
        uploads_by_remote = upload_doc.get("uploads_by_remote_addr") or {}
        uploads_by_status = upload_doc.get("uploads_by_status") or {}
        uploads_by_kind_status = upload_doc.get("uploads_by_kind_status") or {}
        uploads_by_filename_status = upload_doc.get("uploads_by_filename_status") or {}
        uploads_by_status_stored_exists = upload_doc.get("uploads_by_status_stored_exists") or {}
        uploads_by_status_remote = upload_doc.get("uploads_by_status_remote_addr") or {}
        upload_remote = upload_item.get("remote_addr", "")
        upload_filename_status_key = "evidence.txt:ok"
        upload_kind_status_key = "evidence:ok"
        upload_status_stored_exists_key = "ok:yes"
        upload_status_remote_key = f"ok:{upload_remote}"
        if (uploads_by_filename.get("evidence.txt", [{}])[0].get("metadata_path") != str(metadata_path) or
                uploads_by_kind.get("evidence", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_sha.get(metadata.get("sha256"), [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_source.get("/tmp/evidence.txt", [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_stored.get(str(uploaded[0]), {}).get("source_path") != "/tmp/evidence.txt" or
                uploads_by_stored_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_metadata_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_event_log_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_status.get("ok", [{}])[0].get("filename") != "evidence.txt" or
                not upload_remote or
                uploads_by_remote.get(upload_remote, [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_kind_status.get(upload_kind_status_key, [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_filename_status.get(upload_filename_status_key, [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_status_stored_exists.get(upload_status_stored_exists_key, [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_status_remote.get(upload_status_remote_key, [{}])[0].get("filename") != "evidence.txt"):
            print("server json status missing upload browser lookup maps", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("upload_remote_counts", {}).get(upload_remote) != 1 or
                upload_summary.get("upload_metadata_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("upload_event_log_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("upload_kind_status_counts", {}).get(upload_kind_status_key) != 1 or
                upload_summary.get("upload_filename_status_counts", {}).get(upload_filename_status_key) != 1 or
                upload_summary.get("upload_status_stored_exists_counts", {}).get(upload_status_stored_exists_key) != 1 or
                upload_summary.get("upload_status_remote_counts", {}).get(upload_status_remote_key) != 1 or
                upload_summary.get("session_remote_counts", {}).get(upload_remote) != 1):
            print("server json status missing upload/session remote summary counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_api = (upload_doc.get("api_collections") or {}).get("uploads") or {}
        if ("uploads_by_metadata_exists" not in (upload_api.get("indexes") or []) or
                "uploads_by_event_log_exists" not in (upload_api.get("indexes") or [])):
            print("server json status missing upload metadata/log availability API indexes", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("latest_upload_at") != upload_item.get("timestamp") or
                upload_summary.get("latest_session_updated_at") != upload_doc.get("sessions", [{}])[0].get("updated_at")):
            print("server json status missing upload/session recency summary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_browser_by_kind = upload_doc.get("browser_paths_by_kind") or {}
        upload_browser_by_path = upload_doc.get("browser_paths_by_path") or {}
        upload_browser_by_source = upload_doc.get("browser_paths_by_source_id") or {}
        upload_browser_by_kind_source = upload_doc.get("browser_paths_by_kind_source_id") or {}
        upload_session_id = session_json_paths[0].parent.name
        if (upload_doc.get("browser_path_summary", {}).get("by_kind", {}).get("upload-stored") != 1 or
                upload_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("upload-stored") != 1 or
                upload_summary.get("browser_path_kind_counts", {}).get("upload-metadata") != 1 or
                upload_summary.get("browser_path_exists_kind_counts", {}).get("upload-stored") != 1 or
                upload_summary.get("browser_path_missing_kind_counts", {}).get("staged-ledger") != 1 or
                upload_browser_by_kind.get("upload-stored", [{}])[0].get("path") != str(uploaded[0]) or
                upload_browser_by_path.get(str(metadata_path), [{}])[0].get("kind") != "upload-metadata" or
                not upload_browser_by_source.get(upload_session_id) or
                upload_browser_by_kind_source.get(f"upload-metadata:{upload_session_id}", [{}])[0].get("path") != str(metadata_path) or
                upload_browser_by_kind_source.get(f"session-dir:{upload_session_id}", [{}])[0].get("path") != str(session_json_paths[0].parent)):
            print("server json status missing upload/session browser path records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_session = (upload_doc.get("sessions") or [{}])[0]
        session_root_state = upload_doc.get("session_root_state") or {}
        if (upload_session.get("upload_count") != 1 or
                upload_session.get("event_count", 0) < 1 or
                upload_session.get("fetch_count") != 0 or
                upload_session.get("has_uploads") is not True or
                upload_session.get("has_fetches") is not False or
                upload_session.get("has_events") is not True or
                upload_session.get("metadata_exists") is not True or
                upload_session.get("event_log_exists") is not True or
                not isinstance(upload_session.get("duration_sec"), int) or
                upload_session.get("metadata_path") != str(session_json_paths[0]) or
                upload_session.get("event_log") != str(session_json_paths[0].parent / "events.jsonl")):
            print("server json status missing session browser counts and paths", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (session_root_state.get("path") != str(session_root) or
                session_root_state.get("exists") is not True or
                session_root_state.get("recent_session_count") != 1 or
                session_root_state.get("recent_session_ids") != [session_json_paths[0].parent.name] or
                session_root_state.get("service_counts", {}).get("file-service") != 1 or
                session_root_state.get("total_upload_count") != 1 or
                session_root_state.get("total_fetch_count") != 0 or
                session_root_state.get("total_event_count", 0) < 1 or
                session_root_state.get("duration_known_count") != 1 or
                session_root_state.get("total_duration_sec", -1) < 0 or
                session_root_state.get("max_duration_sec", -1) < 0 or
                session_root_state.get("sessions_with_uploads_count") != 1 or
                session_root_state.get("sessions_with_fetches_count") != 0 or
                session_root_state.get("sessions_with_events_count") != 1 or
                session_root_state.get("sessions_with_metadata_count") != 1 or
                session_root_state.get("sessions_with_event_logs_count") != 1 or
                upload_summary.get("session_root_exists") is not True or
                upload_summary.get("session_root_recent_count") != 1 or
                upload_summary.get("session_total_upload_count") != 1 or
                upload_summary.get("session_total_fetch_count") != 0 or
                upload_summary.get("session_total_event_count", 0) < 1 or
                upload_summary.get("session_duration_known_count") != 1 or
                upload_summary.get("session_total_duration_sec", -1) < 0 or
                upload_summary.get("session_average_duration_sec", -1) < 0 or
                upload_summary.get("session_max_duration_sec", -1) < 0 or
                upload_summary.get("sessions_with_uploads_count") != 1 or
                upload_summary.get("sessions_with_fetches_count") != 0 or
                upload_summary.get("sessions_with_events_count") != 1 or
                upload_summary.get("sessions_with_metadata_count") != 1 or
                upload_summary.get("sessions_with_event_logs_count") != 1):
            print("server json status missing session root browser state", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        sessions_by_id = upload_doc.get("sessions_by_id") or {}
        sessions_by_service = upload_doc.get("sessions_by_service") or {}
        sessions_by_state = upload_doc.get("sessions_by_state") or {}
        sessions_by_exit_reason = upload_doc.get("sessions_by_exit_reason") or {}
        sessions_by_remote = upload_doc.get("sessions_by_remote") or {}
        sessions_by_service_state = upload_doc.get("sessions_by_service_state") or {}
        sessions_by_service_exit_reason = upload_doc.get("sessions_by_service_exit_reason") or {}
        sessions_by_service_remote = upload_doc.get("sessions_by_service_remote") or {}
        sessions_by_has_uploads = upload_doc.get("sessions_by_has_uploads") or {}
        sessions_by_has_fetches = upload_doc.get("sessions_by_has_fetches") or {}
        sessions_by_has_events = upload_doc.get("sessions_by_has_events") or {}
        sessions_by_duration_known = upload_doc.get("sessions_by_duration_known") or {}
        sessions_by_metadata_exists = upload_doc.get("sessions_by_metadata_exists") or {}
        sessions_by_event_log_exists = upload_doc.get("sessions_by_event_log_exists") or {}
        events_by_session = upload_doc.get("events_by_session") or {}
        events_by_session_event = upload_doc.get("events_by_session_event") or {}
        upload_events_by_service_event = upload_doc.get("events_by_service_event") or {}
        upload_events_by_detail_status = upload_doc.get("events_by_detail_status") or {}
        upload_events_by_detail_operation = upload_doc.get("events_by_detail_operation") or {}
        upload_events_by_detail_http_status = upload_doc.get("events_by_detail_http_status") or {}
        upload_events_by_event_detail_status = upload_doc.get("events_by_event_detail_status") or {}
        upload_events_by_service_detail_status = upload_doc.get("events_by_service_detail_status") or {}
        upload_events_api = (upload_doc.get("api_collections") or {}).get("events") or {}
        uploaded_session_id = session_json_paths[0].parent.name
        session_service_state_key = "file-service:stopped"
        session_service_exit_key = "file-service:clean shutdown"
        session_service_remote_key = f"file-service:{upload_remote}"
        if (sessions_by_id.get(uploaded_session_id, {}).get("metadata_path") != str(session_json_paths[0]) or
                not sessions_by_service.get("file-service") or
                sessions_by_service["file-service"][0].get("session_id") != uploaded_session_id or
                not sessions_by_state.get("stopped") or
                sessions_by_state["stopped"][0].get("session_id") != uploaded_session_id or
                not sessions_by_exit_reason.get("clean shutdown") or
                sessions_by_exit_reason["clean shutdown"][0].get("session_id") != uploaded_session_id or
                not events_by_session.get(uploaded_session_id) or
                events_by_session[uploaded_session_id][-1].get("event") != "service_stop" or
                not events_by_session_event.get(f"{uploaded_session_id}:upload_complete") or
                not upload_events_by_service_event.get("file-service:upload_complete") or
                upload_events_by_detail_status.get("ok", [{}])[0].get("event") not in ("upload_complete", "connection_close") or
                upload_events_by_detail_operation.get("upload", [{}])[0].get("service") != "file-service" or
                upload_events_by_detail_http_status.get("200", [{}])[0].get("service") != "file-service" or
                not upload_events_by_event_detail_status.get("upload_complete:ok") or
                not upload_events_by_service_detail_status.get("file-service:ok") or
                "events_by_detail_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_operation" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_http_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_status" not in (upload_events_api.get("indexes") or []) or
                not upload_remote or
                sessions_by_remote.get(upload_remote, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_state.get(session_service_state_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_exit_reason.get(session_service_exit_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_remote.get(session_service_remote_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_uploads.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_fetches.get("no", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_events.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_duration_known.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_metadata_exists.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_event_log_exists.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                upload_summary.get("session_service_state_counts", {}).get(session_service_state_key) != 1 or
                upload_summary.get("session_service_exit_reason_counts", {}).get(session_service_exit_key) != 1 or
                upload_summary.get("session_service_remote_counts", {}).get(session_service_remote_key) != 1 or
                upload_summary.get("session_has_uploads_counts", {}).get("yes") != 1 or
                upload_summary.get("session_has_fetches_counts", {}).get("no") != 1 or
                upload_summary.get("session_has_events_counts", {}).get("yes") != 1 or
                upload_summary.get("session_duration_known_counts", {}).get("yes") != 1 or
                upload_summary.get("session_metadata_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("session_event_log_exists_counts", {}).get("yes") != 1 or
                "sessions_by_metadata_exists" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", []) or
                "sessions_by_event_log_exists" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", [])):
            print("server json status missing session/event lookup indexes", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_event_stats = upload_doc.get("event_log_stats") or {}
        if (upload_event_stats.get("total_count", 0) < len(global_events) or
                upload_event_stats.get("tail_count") != len(upload_doc.get("events", [])) or
                upload_doc.get("summary", {}).get("event_tail_count") != upload_event_stats.get("tail_count") or
                upload_event_stats.get("by_remote", {}).get(upload_remote, 0) < 1 or
                upload_event_stats.get("by_detail_status", {}).get("ok", 0) < 1 or
                upload_event_stats.get("by_detail_operation", {}).get("upload", 0) < 1 or
                upload_event_stats.get("by_detail_http_status", {}).get("200", 0) < 1 or
                upload_event_stats.get("by_event_detail_status", {}).get("upload_complete:ok", 0) < 1 or
                upload_event_stats.get("by_service_detail_status", {}).get("file-service:ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_remote_counts", {}).get(upload_remote, 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_status_counts", {}).get("ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_operation_counts", {}).get("upload", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_http_status_counts", {}).get("200", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_status_counts", {}).get("upload_complete:ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_status_counts", {}).get("file-service:ok", 0) < 1):
            print("server json status missing upload event log stats", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (not (upload_doc.get("events_by_level") or {}).get("info") or
                not (upload_doc.get("events_by_remote") or {}).get(upload_remote)):
            print("server json status missing upload event lookup index", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_status_text = run(
            "scripts/busierbox-server",
            "--config", str(upload_cfg),
            "--status",
        )
        if ("Event log:" not in upload_status_text.stdout or
                "file-service:upload_complete" not in upload_status_text.stdout or
                "services: file-service=" not in upload_status_text.stdout or
                "levels: info=" not in upload_status_text.stdout or
                "remotes:" not in upload_status_text.stdout or
                "detail_statuses: ok=" not in upload_status_text.stdout or
                "detail_operations: upload=" not in upload_status_text.stdout or
                "detail_http_statuses: 200=" not in upload_status_text.stdout or
                "operation=upload status=ok http=200 filename=evidence.txt" not in upload_status_text.stdout or
                "Command queue:" not in upload_status_text.stdout or
                "Generated target commands:" not in upload_status_text.stdout or
                "Target command summary:" not in upload_status_text.stdout or
                "operator_supplied_execution=0" not in upload_status_text.stdout or
                "executes_operator_supplied_commands=no" not in upload_status_text.stdout or
                "all_require_explicit_target_action=yes" not in upload_status_text.stdout or
                "rshell policy validity: True=1" not in upload_status_text.stdout or
                "rshell policy errors: 0" not in upload_status_text.stdout or
                "./busierbox reality-test push" not in upload_status_text.stdout or
                "Activity summary:" not in upload_status_text.stdout or
                "session durations:" not in upload_status_text.stdout or
                "uploads=1" not in upload_status_text.stdout or
                "stored_exists=True" not in upload_status_text.stdout or
                f"upload={upload_item.get('timestamp')}" not in upload_status_text.stdout or
                f"remote: {upload_remote} at {upload_item.get('timestamp')}" not in upload_status_text.stdout or
                "session:" not in upload_status_text.stdout or
                "duration_sec=" not in upload_status_text.stdout or
                "metadata:" not in upload_status_text.stdout or
                "event_log:" not in upload_status_text.stdout):
            print("text --status missing event log or command queue section", file=sys.stderr)
            print(upload_status_text.stdout, file=sys.stderr)
            return 1

        state_file = Path(tmp) / "operator-session" / "server-state.json"
        staged_file = Path(tmp) / "operator-session" / "staged-files.json"
        uploads_view = run(
            "scripts/busierbox-server",
            "--config", str(upload_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--tui",
        )
        if ("Received uploads" not in uploads_view.stdout or
                "evidence.txt" not in uploads_view.stdout or
                "metadata:" not in uploads_view.stdout or
                "Generated target commands" not in uploads_view.stdout or
                "Operator paths:" not in uploads_view.stdout or
                "Service summary:" not in uploads_view.stdout or
                "Workbench mode: noninteractive" not in uploads_view.stdout or
                "Activity summary:" not in uploads_view.stdout or
                "Path health:" not in uploads_view.stdout or
                "state_file: exists=" not in uploads_view.stdout or
                "event_log:" not in uploads_view.stdout or
                "tls_cert:" not in uploads_view.stdout or
                "Event log" not in uploads_view.stdout or
                "detail_statuses: ok=" not in uploads_view.stdout or
                "detail_operations: upload=" not in uploads_view.stdout or
                "detail_http_statuses: 200=" not in uploads_view.stdout or
                "uploads=1" not in uploads_view.stdout or
                "Target command summary:" not in uploads_view.stdout or
                "operator_supplied_execution=0" not in uploads_view.stdout or
                "executes_operator_supplied_commands=no" not in uploads_view.stdout or
                "all_require_explicit_target_action=yes" not in uploads_view.stdout or
                "rshell policy validity: True=1" not in uploads_view.stdout or
                "rshell policy errors: 0" not in uploads_view.stdout or
                f"upload={upload_item.get('timestamp')}" not in uploads_view.stdout or
                "stored_exists: True" not in uploads_view.stdout or
                "session:" not in uploads_view.stdout or
                "./busierbox put /etc/config/network" not in uploads_view.stdout or
                "./busierbox reality-test push" not in uploads_view.stdout or
                "./busierbox evidence push" not in uploads_view.stdout):
            print("workbench did not show received upload metadata", file=sys.stderr)
            print(uploads_view.stdout, file=sys.stderr)
            return 1
        uploads_view_state = json.loads(state_file.read_text(encoding="utf-8"))
        if uploads_view_state.get("services", {}).get("workbench", {}).get("workbench_mode") != "noninteractive":
            print("noninteractive workbench did not persist workbench mode", file=sys.stderr)
            print(json.dumps(uploads_view_state, indent=2), file=sys.stderr)
            return 1

        tui_sigint_state = Path(tmp) / "operator-session" / "tui-sigint-state.json"
        tui_master, tui_slave = pty.openpty()
        try:
            tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(tui_sigint_state),
                    "--staged-file", str(staged_file),
                    "--tui",
                ],
                cwd=ROOT,
                stdin=tui_slave,
                stdout=tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "xterm"},
            )
            os.close(tui_slave)
            tui_slave = -1
            time.sleep(0.5)
            tui_proc.send_signal(signal.SIGINT)
            _tui_stdout, tui_stderr = tui_proc.communicate(timeout=5)
        finally:
            if tui_slave != -1:
                os.close(tui_slave)
            try:
                os.close(tui_master)
            except OSError:
                pass
        if tui_proc.returncode not in (0, 130) or "Traceback" in (tui_stderr or ""):
            print("interactive TUI SIGINT did not exit cleanly", file=sys.stderr)
            print(tui_stderr or "", file=sys.stderr)
            return 1
        tui_sigint_doc = json.loads(tui_sigint_state.read_text(encoding="utf-8"))
        if tui_sigint_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("interactive TUI SIGINT did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(tui_sigint_doc, indent=2), file=sys.stderr)
            return 1
        if tui_sigint_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "curses":
            print("interactive TUI SIGINT did not preserve curses workbench mode", file=sys.stderr)
            print(json.dumps(tui_sigint_doc, indent=2), file=sys.stderr)
            return 1

        dumb_tui_state = Path(tmp) / "operator-session" / "tui-dumb-state.json"
        dumb_master, dumb_slave = pty.openpty()
        try:
            dumb_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(dumb_tui_state),
                    "--staged-file", str(staged_file),
                    "--tui",
                ],
                cwd=ROOT,
                stdin=dumb_slave,
                stdout=dumb_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(dumb_slave)
            dumb_slave = -1
            time.sleep(0.3)
            os.write(dumb_master, b"q\n")
            _dumb_stdout, dumb_stderr = dumb_proc.communicate(timeout=5)
        finally:
            if dumb_slave != -1:
                os.close(dumb_slave)
            try:
                os.close(dumb_master)
            except OSError:
                pass
        if dumb_proc.returncode != 0 or "Traceback" in (dumb_stderr or ""):
            print("TERM=dumb line-oriented TUI fallback did not exit cleanly", file=sys.stderr)
            print(dumb_stderr or "", file=sys.stderr)
            return 1
        if "using line menu" not in (dumb_stderr or ""):
            print("TERM=dumb TUI did not announce line-oriented fallback", file=sys.stderr)
            print(dumb_stderr or "", file=sys.stderr)
            return 1
        dumb_tui_doc = json.loads(dumb_tui_state.read_text(encoding="utf-8"))
        if dumb_tui_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("TERM=dumb line-oriented TUI fallback did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(dumb_tui_doc, indent=2), file=sys.stderr)
            return 1
        if dumb_tui_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "line":
            print("TERM=dumb line-oriented TUI fallback did not preserve line workbench mode", file=sys.stderr)
            print(json.dumps(dumb_tui_doc, indent=2), file=sys.stderr)
            return 1
        dumb_invalid_state = Path(tmp) / "operator-session" / "tui-dumb-invalid-state.json"
        dumb_invalid_staged = Path(tmp) / "operator-session" / "tui-dumb-invalid-staged.json"
        dumb_invalid_master, dumb_invalid_slave = pty.openpty()
        try:
            dumb_invalid_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(dumb_invalid_state),
                    "--staged-file", str(dumb_invalid_staged),
                    "--tui",
                ],
                cwd=ROOT,
                stdin=dumb_invalid_slave,
                stdout=dumb_invalid_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(dumb_invalid_slave)
            dumb_invalid_slave = -1
            time.sleep(0.3)
            os.write(dumb_invalid_master, b"6\n/no/such/file\n/tmp/missing\n8\n../bad\nq\n")
            deadline = time.time() + 5
            while dumb_invalid_proc.poll() is None and time.time() < deadline:
                ready, _, _ = select.select([dumb_invalid_master], [], [], 0.1)
                if ready:
                    try:
                        os.read(dumb_invalid_master, 65536)
                    except OSError:
                        break
            if dumb_invalid_proc.poll() is None:
                dumb_invalid_proc.kill()
            _dumb_invalid_stdout, dumb_invalid_stderr = dumb_invalid_proc.communicate(timeout=5)
        finally:
            if dumb_invalid_slave != -1:
                os.close(dumb_invalid_slave)
            try:
                os.close(dumb_invalid_master)
            except OSError:
                pass
        if dumb_invalid_proc.returncode != 0 or "Traceback" in (dumb_invalid_stderr or ""):
            print("TERM=dumb line-oriented TUI fallback did not handle invalid stage/unstage input cleanly", file=sys.stderr)
            print(dumb_invalid_stderr or "", file=sys.stderr)
            return 1
        dumb_invalid_doc = json.loads(dumb_invalid_state.read_text(encoding="utf-8"))
        if dumb_invalid_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("TERM=dumb invalid-input fallback did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(dumb_invalid_doc, indent=2), file=sys.stderr)
            return 1
        if dumb_invalid_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "line":
            print("TERM=dumb invalid-input fallback did not preserve line workbench mode", file=sys.stderr)
            print(json.dumps(dumb_invalid_doc, indent=2), file=sys.stderr)
            return 1

        staged_source = Path(tmp) / "operator-file.bin"
        staged_source.write_bytes(b"operator staged bytes\n")
        fetch_port = free_port()
        fetch_cfg = Path(tmp) / "server-config-fetch.json"
        fetch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": fetch_port,
            "session_root": str(Path(tmp) / "sessions-fetch"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
        }), encoding="utf-8")

        tui = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--tui",
        )
        if tui.returncode != 0 or "BusierBox Operator Workbench" not in tui.stdout:
            print("noninteractive TUI/workbench failed:", file=sys.stderr)
            print(tui.stdout, file=sys.stderr)
            print(tui.stderr, file=sys.stderr)
            return 1
        if ("Operator paths:" not in tui.stdout or
                str(state_file) not in tui.stdout or
                str(staged_file) not in tui.stdout or
                "Workbench mode: noninteractive" not in tui.stdout or
                "Workbench refresh: count=" not in tui.stdout or
                "API resources: schema=1 resources=" not in tui.stdout or
                "collections_key=api_collections resources_key=api_resources" not in tui.stdout or
                "session_root:" not in tui.stdout or
                "Operator workflow actions:" not in tui.stdout or
                "make package" not in tui.stdout or
                "scripts/busierbox-bringup --recommend-only --json" not in tui.stdout):
            print("noninteractive TUI/workbench missing operator path details", file=sys.stderr)
            print(tui.stdout, file=sys.stderr)
            return 1

        release_dir = Path(tmp) / "release"
        (release_dir / "bin").mkdir(parents=True)
        (release_dir / "scripts").mkdir()
        (release_dir / "manifests").mkdir()
        (release_dir / "LICENSES").mkdir()
        (release_dir / "bin" / "busierbox-test").write_text("artifact\n", encoding="utf-8")
        (release_dir / "LICENSE.busierbox").write_text("BusierBox license grant\n", encoding="utf-8")
        (release_dir / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 2, June 1991\n", encoding="utf-8")
        (release_dir / "NOTICE").write_text("BusierBox project license notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "busybox.txt").write_text("BusyBox notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "buildroot.txt").write_text("Buildroot notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "doom-ascii.txt").write_text("doom-ascii notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "miniz.txt").write_text("miniz notice\n", encoding="utf-8")
        (release_dir / "sources.lock.json").write_text('{"schema":2,"sources":[]}\n', encoding="utf-8")
        (release_dir / "manifests" / "sources.lock.json").write_text('{"schema":2,"sources":[]}\n', encoding="utf-8")
        (release_dir / "manifests" / "license-policy.json").write_text(json.dumps({
            "schema": 1,
            "project": {"name": "BusierBox", "license": "GPL-2.0-or-later"},
            "compatibility": {
                "combined_gplv2_compatible": True,
                "preferred_combined_terms_with_busybox": "GPL-2.0",
                "source_availability_required_for_distribution": True,
            },
            "components": [
                {"name": "BusierBox", "license": "GPL-2.0-or-later"},
                {"name": "BusyBox", "license": "GPL-2.0"},
                {"name": "Buildroot", "license": "GPL-2.0-or-later with package exceptions"},
                {"name": "doom-ascii", "license": "GPL-2.0-or-later"},
                {"name": "miniz", "license": "MIT OR Unlicense"},
            ],
        }) + "\n", encoding="utf-8")
        (release_dir / "release.json").write_text(json.dumps({
            "schema": 1,
            "release_name": "operator-smoke",
            "layout": {
                "devices": {
                    "lab-router": {
                        "tuple_path": "by-tuple/native/host/host/host",
                        "artifacts": ["by-tuple/native/host/host/host/bin/busierbox-test"],
                    }
                },
                "tuples": {
                    "by-tuple/native/host/host/host": {
                        "tuple": {"arch": "native", "libc": "host", "kernel_floor": "host"},
                        "artifacts": ["by-tuple/native/host/host/host/bin/busierbox-test"],
                    }
                },
            },
        }) + "\n", encoding="utf-8")
        (release_dir / "release-index.json").write_text(json.dumps({
            "schema": 1,
            "release_name": "operator-smoke",
            "devices": {
                "lab-router": {
                    "tuple_path": "by-tuple/native/host/host/host",
                    "artifacts": ["by-tuple/native/host/host/host/bin/busierbox-test"],
                }
            },
            "tuples": {
                "by-tuple/native/host/host/host": {
                    "tuple": {"arch": "native", "libc": "host", "kernel_floor": "host"},
                    "artifacts": ["by-tuple/native/host/host/host/bin/busierbox-test"],
                }
            },
            "artifacts": [
                {
                    "artifact": "bin/busierbox-test",
                    "tuple_artifact": "bin/busierbox-test",
                    "tuple_path": "by-tuple/native/host/host/host",
                    "payload_preset": "default",
                    "sha256": "abc123",
                    "tools": ["sh"],
                    "features": ["reverse-ssh", "default", "sh", "reverse-ssh"],
                    "tool_provider_status": {"gdbserver": {"schema": 1, "overall": "found", "search_paths": []}},
                    "doom_wads": [
                        {
                            "filename": "doom.wad",
                            "size": 9,
                            "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        }
                    ],
                    "command_queue": {
                        "enabled": "no",
                        "execution_supported": False,
                        "executes_commands": False,
                        "mode_summary": {"operator_supplied_command_execution_mode_count": 0},
                    },
                    "compatibility": {"label": "exact", "reasons": ["fixture"]},
                }
            ],
        }) + "\n", encoding="utf-8")
        release_view = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--tui",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if ("Release artifact browser" not in release_view.stdout or
                "Release summary:" not in release_view.stdout or
                "present=yes valid=yes release_json_valid=yes release_index_valid=yes" not in release_view.stdout or
                "artifacts=1 devices=1 tuples=1 total_size=9" not in release_view.stdout or
                f"release_dir: {release_dir}" not in release_view.stdout or
                "release_name: operator-smoke" not in release_view.stdout or
                "license: project=GPL-2.0-or-later gplv2_compatible=yes valid=yes notices=10 missing_notices=0" not in release_view.stdout or
                "busierbox-test" not in release_view.stdout or
                "compatibility=exact" not in release_view.stdout or
                "compatibility_reason: fixture" not in release_view.stdout or
                "provider_status_gdbserver: found" not in release_view.stdout or
                "doom_wad: doom.wad size=9" not in release_view.stdout or
                "Release recommendations" not in release_view.stdout or
                "by_device:lab-router -> bin/busierbox-test" not in release_view.stdout or
                "Release devices" not in release_view.stdout or
                "lab-router" not in release_view.stdout or
                "artifacts=1" not in release_view.stdout or
                "artifact_path:" not in release_view.stdout or
                "--stage-release-artifact" not in release_view.stdout):
            print("workbench did not show release artifact paths", file=sys.stderr)
            print(release_view.stdout, file=sys.stderr)
            return 1
        release_text_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if ("Release browser" not in release_text_status.stdout or
                "Release summary:" not in release_text_status.stdout or
                "present=yes valid=yes release_json_valid=yes release_index_valid=yes" not in release_text_status.stdout or
                "artifacts=1 devices=1 tuples=1 total_size=9" not in release_text_status.stdout or
                "recommendations:" not in release_text_status.stdout or
                "by_device:lab-router -> bin/busierbox-test" not in release_text_status.stdout):
            print("text --status missing release summary", file=sys.stderr)
            print(release_text_status.stdout, file=sys.stderr)
            return 1
        release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        release_doc = json.loads(release_status.stdout)
        rel = release_doc.get("release") or {}
        if (rel.get("release_name") != "operator-smoke" or
                not rel.get("artifacts") or
                rel.get("devices", [{}])[0].get("name") != "lab-router" or
                rel.get("devices", [{}])[0].get("artifact_count") != 1 or
                not rel.get("devices", [{}])[0].get("artifact_paths", [""])[0].endswith("bin/busierbox-test") or
                rel.get("tuples", [{}])[0].get("path") != "by-tuple/native/host/host/host"):
            print("json status missing release browser metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        if (rel.get("tuples", [{}])[0].get("artifact_count") != 1 or
                not rel.get("tuples", [{}])[0].get("artifact_paths", [""])[0].endswith("bin/busierbox-test")):
            print("json status missing release tuple artifact metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_artifact_map = rel.get("artifacts_by_release_path") or {}
        release_artifacts_by_name = rel.get("artifacts_by_name") or {}
        release_artifacts_by_sha = rel.get("artifacts_by_sha256") or {}
        release_artifacts_by_preset = rel.get("artifacts_by_payload_preset") or {}
        release_artifacts_by_compat = rel.get("artifacts_by_compatibility") or {}
        release_artifacts_by_source = rel.get("artifacts_by_source") or {}
        release_artifacts_by_tuple_path = rel.get("artifacts_by_tuple_path") or {}
        release_artifacts_by_tool = rel.get("artifacts_by_tool") or {}
        release_artifacts_by_feature = rel.get("artifacts_by_feature") or {}
        release_artifacts_by_tool_preset = rel.get("artifacts_by_tool_payload_preset") or {}
        release_artifacts_by_feature_preset = rel.get("artifacts_by_feature_payload_preset") or {}
        release_artifacts_by_tuple_preset = rel.get("artifacts_by_tuple_payload_preset") or {}
        release_artifacts_by_provider_tool = rel.get("artifacts_by_provider_tool") or {}
        release_artifacts_by_provider_status = rel.get("artifacts_by_provider_status") or {}
        release_artifacts_by_doom_wad_filename = rel.get("artifacts_by_doom_wad_filename") or {}
        release_artifacts_by_doom_wad_sha256 = rel.get("artifacts_by_doom_wad_sha256") or {}
        release_artifacts_by_command_queue_enabled = rel.get("artifacts_by_command_queue_enabled") or {}
        release_artifacts_by_command_queue_execution_supported = rel.get("artifacts_by_command_queue_execution_supported") or {}
        release_artifacts_by_command_queue_operator_supplied = rel.get("artifacts_by_command_queue_operator_supplied_command_execution") or {}
        release_device_map = rel.get("devices_by_name") or {}
        release_devices_by_tuple_path = rel.get("devices_by_tuple_path") or {}
        release_devices_by_artifact = rel.get("devices_by_artifact") or {}
        release_tuple_map = rel.get("tuples_by_path") or {}
        release_tuples_by_artifact = rel.get("tuples_by_artifact") or {}
        release_recommendations = rel.get("recommendations") or {}
        release_recommendation_records = rel.get("recommendation_records") or []
        release_recommendations_by_scope = rel.get("recommendations_by_scope") or {}
        release_recommendations_by_artifact = rel.get("recommendations_by_artifact") or {}
        release_recommendations_by_payload = rel.get("recommendations_by_payload_preset") or {}
        release_recommendations_by_compat = rel.get("recommendations_by_compatibility") or {}
        release_license = rel.get("release_license") or {}
        release_license_records = rel.get("release_license_records") or []
        release_licenses_by_project = rel.get("release_license_records_by_project_license") or {}
        release_licenses_by_gplv2 = rel.get("release_license_records_by_combined_gplv2_compatible") or {}
        release_licenses_by_component = rel.get("release_license_records_by_component") or {}
        release_licenses_by_component_license = rel.get("release_license_records_by_component_license") or {}
        release_licenses_by_notice = rel.get("release_license_records_by_notice_file") or {}
        release_artifact_size = len("artifact\n")
        release_layout_artifact = "by-tuple/native/host/host/host/bin/busierbox-test"
        doom_wad_sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        if (release_artifact_map.get("bin/busierbox-test", {}).get("name") != "busierbox-test" or
                release_artifacts_by_name.get("busierbox-test", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_artifacts_by_sha.get("abc123", [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_preset.get("default", [{}])[0].get("sha256") != "abc123" or
                release_artifacts_by_compat.get("exact", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_source.get("release-index", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_artifacts_by_tuple_path.get("by-tuple/native/host/host/host", [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_tool.get("sh", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_feature.get("reverse-ssh", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_artifacts_by_tool_preset.get("sh:default", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_artifacts_by_feature_preset.get("reverse-ssh:default", [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_tuple_preset.get("by-tuple/native/host/host/host:default", [{}])[0].get("sha256") != "abc123" or
                release_artifacts_by_provider_tool.get("gdbserver", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_provider_status.get("gdbserver:found", [{}])[0].get("name") != "busierbox-test" or
                release_artifact_map.get("bin/busierbox-test", {}).get("doom_wads", [{}])[0].get("filename") != "doom.wad" or
                release_artifacts_by_doom_wad_filename.get("doom.wad", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_artifacts_by_doom_wad_sha256.get(doom_wad_sha, [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_command_queue_enabled.get("false", [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_command_queue_execution_supported.get("false", [{}])[0].get("name") != "busierbox-test" or
                release_artifacts_by_command_queue_operator_supplied.get("false", [{}])[0].get("name") != "busierbox-test" or
                rel.get("artifact_stats", {}).get("total_size") != release_artifact_size or
                rel.get("artifact_stats", {}).get("by_compatibility", {}).get("exact") != 1 or
                rel.get("artifact_stats", {}).get("by_payload_preset", {}).get("default") != 1 or
                rel.get("artifact_stats", {}).get("by_source", {}).get("release-index") != 1 or
                rel.get("artifact_stats", {}).get("by_tool", {}).get("sh") != 1 or
                rel.get("artifact_stats", {}).get("by_feature", {}).get("reverse-ssh") != 1 or
                rel.get("artifact_stats", {}).get("by_provider_tool", {}).get("gdbserver") != 1 or
                rel.get("artifact_stats", {}).get("by_provider_status", {}).get("gdbserver:found") != 1 or
                rel.get("artifact_stats", {}).get("by_doom_wad_filename", {}).get("doom.wad") != 1 or
                rel.get("artifact_stats", {}).get("by_doom_wad_sha256", {}).get(doom_wad_sha) != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_enabled", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_execution_supported", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_operator_supplied_command_execution", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("doom_wad_count") != 1 or
                release_device_map.get("lab-router", {}).get("tuple_path") != "by-tuple/native/host/host/host" or
                release_devices_by_tuple_path.get("by-tuple/native/host/host/host", [{}])[0].get("name") != "lab-router" or
                release_devices_by_artifact.get(release_layout_artifact, [{}])[0].get("tuple_path") != "by-tuple/native/host/host/host" or
                release_tuple_map.get("by-tuple/native/host/host/host", {}).get("artifact_count") != 1 or
                release_tuples_by_artifact.get(release_layout_artifact, [{}])[0].get("path") != "by-tuple/native/host/host/host" or
                release_recommendations.get("by_device", {}).get("lab-router", {}).get("name") != "busierbox-test" or
                release_recommendations.get("by_tuple_path", {}).get("by-tuple/native/host/host/host", {}).get("sha256") != "abc123" or
                release_recommendations.get("by_tool", {}).get("sh", {}).get("payload_preset") != "default" or
                release_recommendations.get("by_payload_preset", {}).get("default", {}).get("name") != "busierbox-test" or
                release_recommendations.get("by_feature", {}).get("reverse-ssh", {}).get("name") != "busierbox-test" or
                not release_recommendation_records or
                release_recommendations_by_scope.get("by_device", [{}])[0].get("key") != "lab-router" or
                release_recommendations_by_artifact.get("bin/busierbox-test", [{}])[0].get("artifact_name") != "busierbox-test" or
                release_recommendations_by_payload.get("default", [{}])[0].get("artifact_name") != "busierbox-test" or
                release_recommendations_by_compat.get("exact", [{}])[0].get("payload_preset") != "default" or
                release_license.get("project_license") != "GPL-2.0-or-later" or
                release_license.get("combined_gplv2_compatible") is not True or
                release_license.get("missing_notice_count") != 0 or
                len(release_license_records) != 1 or
                release_licenses_by_project.get("GPL-2.0-or-later", [{}])[0].get("valid") is not True or
                release_licenses_by_gplv2.get("True", [{}])[0].get("project_license") != "GPL-2.0-or-later" or
                release_licenses_by_component.get("BusyBox", [{}])[0].get("combined_gplv2_compatible") is not True or
                release_licenses_by_component_license.get("BusyBox:GPL-2.0", [{}])[0].get("project_license") != "GPL-2.0-or-later" or
                release_licenses_by_notice.get("LICENSE.busierbox", [{}])[0].get("notice_count") != 10):
            print("json status missing release browser lookup maps", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_state = release_doc.get("release_state") or {}
        if (release_state.get("release_dir") != str(release_dir) or
                release_state.get("release_json") != str(release_dir / "release.json") or
                release_state.get("release_index") != str(release_dir / "release-index.json") or
                release_state.get("present") is not True or
                release_state.get("valid") is not True or
                release_state.get("release_json_valid") is not True or
                release_state.get("release_index_valid") is not True or
                release_state.get("bin_dir_exists") is not True or
                release_state.get("scripts_dir_exists") is not True or
                release_state.get("artifact_count") != 1 or
                release_state.get("device_count") != 1 or
                release_state.get("tuple_count") != 1 or
                release_state.get("release_name") != "operator-smoke" or
                release_state.get("release_license_valid") is not True or
                release_state.get("project_license") != "GPL-2.0-or-later" or
                release_state.get("combined_gplv2_compatible") is not True or
                release_state.get("license_notice_count") != 10 or
                release_state.get("license_missing_notice_count") != 0):
            print("json status missing explicit release state metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_browser_by_kind = release_doc.get("browser_paths_by_kind") or {}
        release_browser_by_path = release_doc.get("browser_paths_by_path") or {}
        release_browser_by_release_path = release_doc.get("browser_paths_by_release_path") or {}
        release_browser_by_kind_source = release_doc.get("browser_paths_by_kind_source_id") or {}
        if (release_doc.get("browser_path_summary", {}).get("by_kind", {}).get("release-artifact") != 1 or
                release_doc.get("browser_path_summary", {}).get("by_release_path", {}).get("bin/busierbox-test", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("by_kind", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("release-artifact") != 1 or
                release_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("kind_mismatch_count") != 0 or
                release_doc.get("summary", {}).get("browser_path_exists_kind_counts", {}).get("release-artifact") != 1 or
                release_doc.get("summary", {}).get("browser_path_release_path_counts", {}).get("bin/busierbox-test", 0) < 1 or
                release_doc.get("summary", {}).get("browser_path_exists_kind_counts", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("summary", {}).get("browser_path_kind_mismatch_count") != 0 or
                release_browser_by_kind.get("release-json", [{}])[0].get("path") != str(release_dir / "release.json") or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("release_path") != "bin/busierbox-test" or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("source_id") != "bin/busierbox-test" or
                release_browser_by_kind.get("release-recommendation-artifact", [{}])[0].get("source_id") != "by_device:lab-router" or
                release_browser_by_release_path.get("bin/busierbox-test", [{}])[0].get("path") != str(release_dir / "bin" / "busierbox-test") or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("expected_kind_matches") is not True or
                release_browser_by_path.get(str(release_dir / "bin" / "busierbox-test"), [{}])[0].get("kind") != "release-artifact" or
                release_browser_by_kind_source.get("release-artifact:bin/busierbox-test", [{}])[0].get("path") != str(release_dir / "bin" / "busierbox-test") or
                release_browser_by_kind_source.get("release-recommendation-artifact:by_device:lab-router", [{}])[0].get("path") != str(release_dir / "bin" / "busierbox-test")):
            print("json status missing release browser path records", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_summary = release_doc.get("summary") or {}
        if (release_summary.get("release_present") is not True or
                release_summary.get("release_valid") is not True or
                release_summary.get("release_json_valid") is not True or
                release_summary.get("release_index_valid") is not True or
                release_summary.get("release_artifact_count", 0) < 1 or
                release_summary.get("release_artifact_total_size") != release_artifact_size or
                release_summary.get("release_device_count") != 1 or
                release_summary.get("release_tuple_count") != 1 or
                release_summary.get("release_device_artifact_reference_count") != 1 or
                release_summary.get("release_tuple_artifact_reference_count") != 1 or
                release_summary.get("release_device_tuple_path_counts", {}).get("by-tuple/native/host/host/host") != 1 or
                release_summary.get("release_device_artifact_counts", {}).get(release_layout_artifact) != 1 or
                release_summary.get("release_tuple_artifact_counts", {}).get(release_layout_artifact) != 1 or
                release_summary.get("release_artifact_compatibility_counts", {}).get("exact") != 1 or
                release_summary.get("release_artifact_payload_preset_counts", {}).get("default") != 1 or
                release_summary.get("release_artifact_source_counts", {}).get("release-index") != 1 or
                release_summary.get("release_artifact_tuple_path_counts", {}).get("by-tuple/native/host/host/host") != 1 or
                release_summary.get("release_artifact_tool_counts", {}).get("sh") != 1 or
                release_summary.get("release_artifact_feature_counts", {}).get("reverse-ssh") != 1 or
                release_summary.get("release_artifact_tool_payload_preset_combo_count") != 1 or
                release_summary.get("release_artifact_feature_payload_preset_combo_count") != 3 or
                release_summary.get("release_artifact_tuple_payload_preset_combo_count") != 1 or
                release_summary.get("release_artifact_provider_tool_counts", {}).get("gdbserver") != 1 or
                release_summary.get("release_artifact_provider_status_counts", {}).get("gdbserver:found") != 1 or
                release_summary.get("release_artifact_doom_wad_filename_counts", {}).get("doom.wad") != 1 or
                release_summary.get("release_artifact_doom_wad_sha256_counts", {}).get(doom_wad_sha) != 1 or
                release_summary.get("release_artifact_command_queue_enabled_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_command_queue_execution_supported_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_command_queue_operator_supplied_command_execution_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_doom_wad_count") != 1 or
                release_summary.get("release_license_count") != 1 or
                release_summary.get("release_license_valid_count") != 1 or
                release_summary.get("release_license_notice_count") != 10 or
                release_summary.get("release_license_missing_notice_count") != 0 or
                release_summary.get("release_project_license_counts", {}).get("GPL-2.0-or-later") != 1 or
                release_summary.get("release_combined_gplv2_compatible_counts", {}).get("True") != 1 or
                release_summary.get("release_recommendation_count", 0) < 1 or
                release_summary.get("release_recommendation_scope_counts", {}).get("by_device") != 1 or
                release_summary.get("release_recommendation_payload_preset_counts", {}).get("default", 0) < 1 or
                release_summary.get("release_recommendation_compatibility_counts", {}).get("exact", 0) < 1):
            print("json status missing release aggregate counts", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_api = release_doc.get("api_collections") or {}
        if ("devices_by_tuple_path" not in (release_api.get("release_devices", {}).get("indexes") or []) or
                "devices_by_artifact" not in (release_api.get("release_devices", {}).get("indexes") or []) or
                "tuples_by_artifact" not in (release_api.get("release_tuples", {}).get("indexes") or []) or
                "release_license_records_by_component_license" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_notice_file" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "artifacts_by_command_queue_enabled" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_command_queue_execution_supported" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_command_queue_operator_supplied_command_execution" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "recommendations_by_payload_preset" not in (release_api.get("release_recommendations", {}).get("indexes") or []) or
                "recommendations_by_compatibility" not in (release_api.get("release_recommendations", {}).get("indexes") or [])):
            print("json status missing release device/tuple api collection indexes", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        invalid_release_dir = Path(tmp) / "invalid-release"
        (invalid_release_dir / "bin").mkdir(parents=True)
        (invalid_release_dir / "scripts").mkdir()
        (invalid_release_dir / "release.json").write_text("{not-json\n", encoding="utf-8")
        invalid_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=invalid_release_dir,
            text=True,
            capture_output=True,
        )
        invalid_release_doc = json.loads(invalid_release_status.stdout)
        invalid_release_state = invalid_release_doc.get("release_state") or {}
        invalid_release_warnings = [
            item for item in invalid_release_doc.get("warnings", [])
            if item.get("type") == "invalid_release_state"
        ]
        if (invalid_release_state.get("present") is not True or
                invalid_release_state.get("valid") is not False or
                invalid_release_state.get("release_json_valid") is not False or
                not invalid_release_state.get("errors") or
                invalid_release_doc.get("release") or
                invalid_release_doc.get("summary", {}).get("release_valid") is not False or
                invalid_release_doc.get("summary", {}).get("warning_type_counts", {}).get("invalid_release_state") != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir)) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir / "release.json")) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir / "release-index.json")) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_type_path_counts", {}).get(f"invalid_release_state:{invalid_release_dir}") != 1 or
                not invalid_release_warnings or
                invalid_release_warnings[-1].get("path") != str(invalid_release_dir) or
                not invalid_release_warnings[-1].get("errors") or
                invalid_release_doc.get("warnings_by_type", {}).get("invalid_release_state", [{}])[-1].get("path") != str(invalid_release_dir) or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir / "release.json"), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir / "release-index.json"), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_type_path", {}).get(f"invalid_release_state:{invalid_release_dir}", [{}])[-1].get("path") != str(invalid_release_dir)):
            print("json status did not expose invalid release bundle state", file=sys.stderr)
            print(invalid_release_status.stdout, file=sys.stderr)
            return 1
        invalid_release_text = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--status",
            ],
            cwd=invalid_release_dir,
            text=True,
            capture_output=True,
        )
        if ("release bundle state is invalid:" not in invalid_release_text.stdout or
                "release.json:" not in invalid_release_text.stdout):
            print("text status did not expose invalid release bundle warning", file=sys.stderr)
            print(invalid_release_text.stdout, file=sys.stderr)
            return 1
        staged_release = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "busierbox-test",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if staged_release.returncode != 0 or "busierbox fetch busierbox-test" not in staged_release.stdout:
            print("--stage-release-artifact did not stage release artifact", file=sys.stderr)
            print(staged_release.stdout, file=sys.stderr)
            print(staged_release.stderr, file=sys.stderr)
            return 1
        staged_release_recommendation = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "by_device:lab-router",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (staged_release_recommendation.returncode != 0 or
                "busierbox fetch busierbox-test" not in staged_release_recommendation.stdout):
            print("--stage-release-artifact did not stage release recommendation", file=sys.stderr)
            print(staged_release_recommendation.stdout, file=sys.stderr)
            print(staged_release_recommendation.stderr, file=sys.stderr)
            return 1
        staged_release_tuple_recommendation = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "by_tuple_path:by-tuple/native/host/host/host",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (staged_release_tuple_recommendation.returncode != 0 or
                "busierbox fetch busierbox-test" not in staged_release_tuple_recommendation.stdout):
            print("--stage-release-artifact did not stage tuple recommendation", file=sys.stderr)
            print(staged_release_tuple_recommendation.stdout, file=sys.stderr)
            print(staged_release_tuple_recommendation.stderr, file=sys.stderr)
            return 1
        line_release_staged_file = Path(tmp) / "operator-session" / "line-release-staged.json"
        line_release_state_file = Path(tmp) / "operator-session" / "line-release-state.json"
        line_master, line_slave = pty.openpty()
        try:
            line_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(fetch_cfg),
                    "--state-file", str(line_release_state_file),
                    "--staged-file", str(line_release_staged_file),
                    "--tui",
                ],
                cwd=release_dir,
                stdin=line_slave,
                stdout=line_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(line_slave)
            line_slave = -1
            time.sleep(0.3)
            os.write(line_master, b"10\nby_tuple_path:by-tuple/native/host/host/host\nq\n")
            line_stdout_chunks = []
            deadline = time.time() + 5
            while line_proc.poll() is None and time.time() < deadline:
                readable, _, _ = select.select([line_master], [], [], 0.1)
                if readable:
                    try:
                        line_stdout_chunks.append(os.read(line_master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
            if line_proc.poll() is None:
                line_proc.terminate()
                try:
                    line_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    line_proc.kill()
                    line_proc.wait(timeout=2)
            _line_stdout = "".join(line_stdout_chunks)
            line_stderr = line_proc.stderr.read()
        finally:
            if line_slave != -1:
                os.close(line_slave)
            try:
                os.close(line_master)
            except OSError:
                pass
        if line_proc.returncode != 0 or "Traceback" in (line_stderr or ""):
            print("line-oriented TUI did not stage release tuple recommendation", file=sys.stderr)
            print(line_stderr or "", file=sys.stderr)
            return 1
        line_staged = json.loads(line_release_staged_file.read_text(encoding="utf-8"))
        if ((line_staged.get("staged") or {}).get("busierbox-test", {}).get("tuple_path") !=
                "by-tuple/native/host/host/host"):
            print("line-oriented TUI staged release metadata incorrectly", file=sys.stderr)
            print(json.dumps(line_staged, indent=2), file=sys.stderr)
            return 1
        staged_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        staged_doc = json.loads(staged_status.stdout)
        release_staged = staged_doc.get("staged", {}).get("busierbox-test", {})
        release_staged_by_kind = staged_doc.get("staged_by_kind") or {}
        release_staged_summary = staged_doc.get("summary") or {}
        if (release_staged.get("stage_kind") != "release-artifact" or
                release_staged.get("release_path") != "bin/busierbox-test" or
                release_staged.get("tuple_path") != "by-tuple/native/host/host/host" or
                release_staged.get("payload_preset") != "default" or
                (release_staged.get("compatibility") or {}).get("label") != "exact" or
                release_staged_by_kind.get("release-artifact", [{}])[0].get("request_name") != "busierbox-test" or
                release_staged_summary.get("staged_kind_counts", {}).get("release-artifact") != 1):
            print("json status missing release artifact staged metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        fetch_records = [
            rec for rec in staged_doc.get("target_command_records") or []
            if rec.get("request_name") == "busierbox-test"
        ]
        if (not fetch_records or
                fetch_records[0].get("source_path") != str(release_dir / "bin" / "busierbox-test") or
                fetch_records[0].get("stage_kind") != "release-artifact" or
                fetch_records[0].get("release_path") != "bin/busierbox-test" or
                fetch_records[0].get("tuple_path") != "by-tuple/native/host/host/host" or
                fetch_records[0].get("payload_preset") != "default" or
                (fetch_records[0].get("compatibility") or {}).get("label") != "exact" or
                fetch_records[0].get("network") is not True or
                fetch_records[0].get("executes_operator_supplied_commands") is not False):
            print("json status missing structured staged fetch command metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        staged_commands_by_request = staged_doc.get("target_commands_by_request") or {}
        staged_commands_by_stage_kind = staged_doc.get("target_commands_by_stage_kind") or {}
        staged_commands_by_release_path = staged_doc.get("target_commands_by_release_path") or {}
        staged_commands_by_service_purpose = staged_doc.get("target_commands_by_service_purpose") or {}
        staged_commands_by_explicit_action = staged_doc.get("target_commands_by_requires_explicit_target_action") or {}
        staged_commands_by_operator_supplied = staged_doc.get("target_commands_by_executes_operator_supplied_commands") or {}
        if (staged_commands_by_request.get("busierbox-test", {}).get("source_path") != str(release_dir / "bin" / "busierbox-test") or
                staged_commands_by_request.get("busierbox-test", {}).get("release_path") != "bin/busierbox-test" or
                staged_commands_by_stage_kind.get("release-artifact", [{}])[0].get("request_name") != "busierbox-test" or
                staged_commands_by_release_path.get("bin/busierbox-test", [{}])[0].get("request_name") != "busierbox-test" or
                staged_doc.get("summary", {}).get("target_command_stage_kind_counts", {}).get("release-artifact") != 1 or
                staged_doc.get("summary", {}).get("target_command_release_path_counts", {}).get("bin/busierbox-test") != 1 or
                not any(item.get("request_name") == "busierbox-test" for item in staged_commands_by_explicit_action.get("True", [])) or
                staged_commands_by_operator_supplied.get("True", []) != [] or
                staged_commands_by_service_purpose.get("file-service:explicitly fetch an operator-staged file", [{}])[0].get("request_name") != "busierbox-test"):
            print("json status missing staged fetch command request lookup", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        staged_browser_by_kind_source = staged_doc.get("browser_paths_by_kind_source_id") or {}
        staged_browser_by_stage_kind = staged_doc.get("browser_paths_by_stage_kind") or {}
        staged_browser_by_release_path = staged_doc.get("browser_paths_by_release_path") or {}
        staged_source_browser = staged_browser_by_kind_source.get("staged-source:busierbox-test", [{}])[0]
        if (staged_source_browser.get("stage_kind") != "release-artifact" or
                staged_source_browser.get("release_path") != "bin/busierbox-test" or
                staged_source_browser.get("tuple_path") != "by-tuple/native/host/host/host" or
                (staged_source_browser.get("compatibility") or {}).get("label") != "exact" or
                staged_browser_by_stage_kind.get("release-artifact", [{}])[0].get("source_id") != "busierbox-test" or
                staged_browser_by_release_path.get("bin/busierbox-test", [{}])[0].get("source_id") != "busierbox-test" or
                staged_doc.get("summary", {}).get("browser_path_stage_kind_counts", {}).get("release-artifact") != 1 or
                staged_doc.get("summary", {}).get("browser_path_release_path_counts", {}).get("bin/busierbox-test", 0) < 1):
            print("json status missing staged browser release metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1

        bad_stage = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--transport", "file-service",
            "--serve-file", str(staged_source),
            "--as", "../bad",
            "--timeout", "0.01",
        )
        if bad_stage.returncode == 0 or "path traversal" not in (bad_stage.stdout + bad_stage.stderr):
            print("staged path traversal was not rejected", file=sys.stderr)
            return 1

        proc = subprocess.Popen(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--transport", "file-service",
                "--serve-file", str(staged_source),
                "--as", "/tmp/myfile",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        request = (
            "GET /fetch?name=%2Ftmp%2Fmyfile HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "\r\n"
        ).encode("ascii")
        response = connect_with_retry(fetch_port, request)
        stdout, stderr = proc.communicate(timeout=5)
        if proc.returncode != 0:
            print("staged fetch server exited nonzero:", file=sys.stderr)
            print(stdout, file=sys.stderr)
            print(stderr, file=sys.stderr)
            return 1
        if b"HTTP/1.1 200 OK" not in response or not response.endswith(b"operator staged bytes\n"):
            print("staged fetch did not return the staged file:", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        fetch_sessions = list((Path(tmp) / "sessions-fetch").glob("*/session.json"))
        if len(fetch_sessions) != 1:
            print("staged fetch did not write a session record", file=sys.stderr)
            return 1
        fetch_session_doc = json.loads(fetch_sessions[0].read_text(encoding="utf-8"))
        if (len(fetch_session_doc.get("fetches") or []) != 1 or
                fetch_session_doc["fetches"][0].get("operation") != "fetch" or
                fetch_session_doc["fetches"][0].get("status") != "served" or
                fetch_session_doc["fetches"][0].get("http_status") != 200 or
                fetch_session_doc.get("uploads")):
            print("staged fetch session was not classified as fetch-only", file=sys.stderr)
            print(json.dumps(fetch_session_doc, indent=2), file=sys.stderr)
            return 1
        fetch_events = [json.loads(line) for line in (fetch_sessions[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "fetch_complete" and event.get("details", {}).get("operation") == "fetch" for event in fetch_events):
            print("staged fetch did not write structured fetch_complete event", file=sys.stderr)
            return 1
        fetch_close_events = [event for event in fetch_events if event.get("event") == "connection_close"]
        if (not fetch_close_events or
                fetch_close_events[-1].get("details", {}).get("operation") != "fetch" or
                fetch_close_events[-1].get("details", {}).get("status") != "served" or
                fetch_close_events[-1].get("details", {}).get("http_status") != 200 or
                fetch_close_events[-1].get("details", {}).get("request_name") != "/tmp/myfile"):
            print("staged fetch connection_close event missing request outcome details", file=sys.stderr)
            return 1
        fetch_status = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--json-status",
        )
        fetch_status_doc = json.loads(fetch_status.stdout)
        fetch_items = fetch_status_doc.get("fetches") or []
        fetch_summary = fetch_status_doc.get("summary", {})
        if (fetch_summary.get("fetch_count") != 1 or
                fetch_summary.get("fetch_total_size") != staged_source.stat().st_size or
                fetch_summary.get("fetch_source_exists_count") != 1 or
                fetch_summary.get("fetch_source_missing_count") != 0 or
                fetch_summary.get("fetch_status_counts", {}).get("served") != 1 or
                fetch_summary.get("fetch_http_status_counts", {}).get("200") != 1 or
                len(fetch_items) != 1 or
                fetch_items[0].get("request_name") != "/tmp/myfile" or
                fetch_items[0].get("status") != "served" or
                fetch_items[0].get("http_status") != 200 or
                fetch_items[0].get("source_exists") is not True or
                fetch_items[0].get("metadata_exists") is not True or
                fetch_items[0].get("event_log_exists") is not True or
                fetch_items[0].get("session_id") != fetch_sessions[0].parent.name or
                fetch_items[0].get("event_log") != str(fetch_sessions[0].parent / "events.jsonl")):
            print("server json status missing recent fetch metadata", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetches_by_session = fetch_status_doc.get("fetches_by_session") or {}
        session_fetches = fetches_by_session.get(fetch_sessions[0].parent.name) or []
        if (len(session_fetches) != 1 or
                session_fetches[0].get("request_name") != "/tmp/myfile" or
                session_fetches[0].get("status") != "served"):
            print("server json status missing fetches_by_session browser grouping", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetches_by_request = fetch_status_doc.get("fetches_by_request") or {}
        fetches_by_sha = fetch_status_doc.get("fetches_by_sha256") or {}
        fetches_by_source = fetch_status_doc.get("fetches_by_source_path") or {}
        fetches_by_source_exists = fetch_status_doc.get("fetches_by_source_exists") or {}
        fetches_by_metadata_exists = fetch_status_doc.get("fetches_by_metadata_exists") or {}
        fetches_by_event_log_exists = fetch_status_doc.get("fetches_by_event_log_exists") or {}
        fetches_by_status = fetch_status_doc.get("fetches_by_status") or {}
        fetches_by_http_status = fetch_status_doc.get("fetches_by_http_status") or {}
        fetches_by_remote = fetch_status_doc.get("fetches_by_remote_addr") or {}
        fetches_by_request_status = fetch_status_doc.get("fetches_by_request_status") or {}
        fetches_by_status_source_exists = fetch_status_doc.get("fetches_by_status_source_exists") or {}
        fetches_by_status_remote = fetch_status_doc.get("fetches_by_status_remote_addr") or {}
        fetches_by_http_status_remote = fetch_status_doc.get("fetches_by_http_status_remote_addr") or {}
        fetch_sha = fetch_items[0].get("sha256", "")
        fetch_remote = fetch_items[0].get("remote_addr", "")
        fetch_request_status_key = "/tmp/myfile:served"
        fetch_status_source_exists_key = "served:yes"
        fetch_status_remote_key = f"served:{fetch_remote}"
        fetch_http_status_remote_key = f"200:{fetch_remote}"
        if (fetches_by_request.get("/tmp/myfile", [{}])[0].get("status") != "served" or
                not fetch_sha or
                fetches_by_sha.get(fetch_sha, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_source.get(str(staged_source), [{}])[0].get("http_status") != 200 or
                fetches_by_source_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_metadata_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_event_log_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_status.get("served", [{}])[0].get("source_path") != str(staged_source) or
                fetches_by_http_status.get("200", [{}])[0].get("request_name") != "/tmp/myfile" or
                not fetch_remote or
                fetches_by_remote.get(fetch_remote, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_request_status.get(fetch_request_status_key, [{}])[0].get("source_path") != str(staged_source) or
                fetches_by_status_source_exists.get(fetch_status_source_exists_key, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_status_remote.get(fetch_status_remote_key, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_http_status_remote.get(fetch_http_status_remote_key, [{}])[0].get("status") != "served"):
            print("server json status missing fetch browser lookup maps", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        if (fetch_summary.get("fetch_remote_counts", {}).get(fetch_remote) != 1 or
                fetch_summary.get("fetch_metadata_exists_counts", {}).get("yes") != 1 or
                fetch_summary.get("fetch_event_log_exists_counts", {}).get("yes") != 1 or
                fetch_summary.get("fetch_request_status_counts", {}).get(fetch_request_status_key) != 1 or
                fetch_summary.get("fetch_status_source_exists_counts", {}).get(fetch_status_source_exists_key) != 1 or
                fetch_summary.get("fetch_status_remote_counts", {}).get(fetch_status_remote_key) != 1 or
                fetch_summary.get("fetch_http_status_remote_counts", {}).get(fetch_http_status_remote_key) != 1):
            print("server json status missing fetch remote summary counts", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetch_api = (fetch_status_doc.get("api_collections") or {}).get("fetches") or {}
        if ("fetches_by_metadata_exists" not in (fetch_api.get("indexes") or []) or
                "fetches_by_event_log_exists" not in (fetch_api.get("indexes") or [])):
            print("server json status missing fetch metadata/log availability API indexes", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        if fetch_summary.get("latest_fetch_at") != fetch_items[0].get("timestamp"):
            print("server json status missing fetch recency summary", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetch_status_text = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--status",
        )
        if ("Recent fetches:" not in fetch_status_text.stdout or
                "Activity summary:" not in fetch_status_text.stdout or
                "fetches=1" not in fetch_status_text.stdout or
                "/tmp/myfile" not in fetch_status_text.stdout or
                "status=served http=200" not in fetch_status_text.stdout or
                f"fetch={fetch_items[0].get('timestamp')}" not in fetch_status_text.stdout or
                f"remote: {fetch_remote} at {fetch_items[0].get('timestamp')}" not in fetch_status_text.stdout):
            print("text --status missing recent fetch metadata", file=sys.stderr)
            print(fetch_status_text.stdout, file=sys.stderr)
            return 1
        fetch_view = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--tui",
        )
        if ("Recent fetches:" not in fetch_view.stdout or
                "Activity summary:" not in fetch_view.stdout or
                "fetches=1" not in fetch_view.stdout or
                "/tmp/myfile" not in fetch_view.stdout or
                "status=served http=200" not in fetch_view.stdout or
                f"fetch={fetch_items[0].get('timestamp')}" not in fetch_view.stdout or
                f"remote: {fetch_remote} at {fetch_items[0].get('timestamp')}" not in fetch_view.stdout or
                "event_log:" not in fetch_view.stdout):
            print("workbench fallback missing recent fetch metadata", file=sys.stderr)
            print(fetch_view.stdout, file=sys.stderr)
            return 1
        staged_doc = json.loads(staged_file.read_text(encoding="utf-8"))
        if "/tmp/myfile" not in staged_doc.get("staged", {}):
            print("staged-files JSON missing request name", file=sys.stderr)
            return 1
        listed = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--list-staged",
        )
        if listed.returncode != 0 or "busierbox fetch /tmp/myfile" not in listed.stdout:
            print("--list-staged did not show target fetch command", file=sys.stderr)
            print(listed.stdout, file=sys.stderr)
            return 1
        status_enriched = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--json-status",
        )
        status_doc = json.loads(status_enriched.stdout)
        staged_status = status_doc.get("staged", {}).get("/tmp/myfile", {})
        staged_records = status_doc.get("staged_records") or []
        staged_record = next((item for item in staged_records if item.get("request_name") == "/tmp/myfile"), {})
        staged_by_request = status_doc.get("staged_by_request") or {}
        staged_by_kind = status_doc.get("staged_by_kind") or {}
        staged_by_sha256 = status_doc.get("staged_by_sha256") or {}
        staged_by_source_path = status_doc.get("staged_by_source_path") or {}
        staged_by_fetch_command = status_doc.get("staged_by_fetch_command") or {}
        staged_by_fetch_command_force = status_doc.get("staged_by_fetch_command_force") or {}
        staged_by_source_exists = status_doc.get("staged_by_source_exists") or {}
        staged_by_kind_source_exists = status_doc.get("staged_by_kind_source_exists") or {}
        staged_files_state = status_doc.get("staged_files_state") or {}
        staged_sha = staged_record.get("sha256", "")
        staged_summary = status_doc.get("summary") or {}
        if (not staged_status or
                staged_status.get("request_name") != "/tmp/myfile" or
                staged_status.get("stage_kind") != "file" or
                "fetch /tmp/myfile" not in staged_status.get("fetch_command", "") or
                "--force" not in staged_status.get("fetch_command_force", "") or
                staged_status.get("source_exists") is not True or
                staged_summary.get("staged_count", 0) < 1 or
                staged_summary.get("staged_kind_counts", {}).get("file", 0) < 1 or
                staged_summary.get("staged_source_exists_count", 0) < 1 or
                staged_summary.get("staged_source_missing_count") != 0 or
                staged_summary.get("staged_fetch_command_count", 0) < 1 or
                staged_summary.get("staged_fetch_command_force_count", 0) < 1 or
                staged_summary.get("staged_source_exists_kind_counts", {}).get("file", 0) < 1 or
                staged_summary.get("staged_source_missing_kind_counts") != {} or
                staged_summary.get("staged_total_size", 0) < staged_source.stat().st_size or
                staged_summary.get("latest_staged_at") != staged_record.get("staged_at") or
                not staged_record or
                staged_record.get("name") != "/tmp/myfile" or
                staged_record.get("stage_kind") != "file" or
                staged_record.get("source_path") != str(staged_source) or
                staged_record.get("source_exists") is not True or
                "fetch /tmp/myfile" not in staged_record.get("fetch_command", "") or
                staged_by_request.get("/tmp/myfile", {}).get("source_path") != str(staged_source) or
                staged_by_kind.get("file", [{}])[0].get("request_name") != "/tmp/myfile" or
                staged_by_source_path.get(str(staged_source), {}).get("request_name") != "/tmp/myfile" or
                staged_by_fetch_command.get(staged_record.get("fetch_command", ""), {}).get("request_name") != "/tmp/myfile" or
                staged_by_fetch_command_force.get(staged_record.get("fetch_command_force", ""), {}).get("request_name") != "/tmp/myfile" or
                staged_by_source_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                staged_by_source_exists.get("no") != [] or
                staged_by_kind_source_exists.get("file:yes", [{}])[0].get("source_path") != str(staged_source) or
                not staged_sha or
                not any(item.get("request_name") == "/tmp/myfile" for item in staged_by_sha256.get(staged_sha, [])) or
                status_doc.get("target_commands_by_request", {}).get("/tmp/myfile", {}).get("request_name") != "/tmp/myfile" or
                not any("fetch /tmp/myfile" in cmd for cmd in status_doc.get("target_commands", [])) or
                "selected_local_ip" not in status_doc or
                not isinstance(status_doc.get("events"), list)):
            print("json status missing enriched workbench fields", file=sys.stderr)
            print(status_enriched.stdout, file=sys.stderr)
            return 1
        if (staged_files_state.get("valid") is not True or
                staged_files_state.get("staged_count", 0) < 1 or
                "/tmp/myfile" not in staged_files_state.get("request_names", []) or
                staged_summary.get("staged_files_valid") is not True or
                staged_summary.get("staged_files_state_count", 0) < 1):
            print("json status missing staged-files ledger state", file=sys.stderr)
            print(status_enriched.stdout, file=sys.stderr)
            return 1
        unstage = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--unstage", "/tmp/myfile",
            "--list-staged",
        )
        staged_after_unstage = json.loads(staged_file.read_text(encoding="utf-8"))
        if unstage.returncode != 0 or "/tmp/myfile" in staged_after_unstage.get("staged", {}):
            print("--unstage did not remove staged request", file=sys.stderr)
            print(unstage.stdout, file=sys.stderr)
            print(unstage.stderr, file=sys.stderr)
            return 1

        missing_fetch_port = free_port()
        missing_fetch_cfg = Path(tmp) / "server-config-missing-fetch.json"
        missing_fetch_root = Path(tmp) / "sessions-missing-fetch"
        missing_fetch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "file_service_port": missing_fetch_port,
            "session_root": str(missing_fetch_root),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "file_service_tls": "no",
        }), encoding="utf-8")
        missing_proc = subprocess.Popen(
            [
                str(server), "--config", str(missing_fetch_cfg),
                "--state-file", str(Path(tmp) / "missing-fetch-state.json"),
                "--staged-file", str(Path(tmp) / "missing-fetch-staged.json"),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        missing_response = connect_with_retry(
            missing_fetch_port,
            b"GET /fetch?name=not-staged HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
        )
        missing_stdout, missing_stderr = missing_proc.communicate(timeout=5)
        if missing_proc.returncode != 0 or b"HTTP/1.1 404" not in missing_response:
            print("missing staged fetch did not return HTTP 404 cleanly", file=sys.stderr)
            print(missing_stdout, file=sys.stderr)
            print(missing_stderr, file=sys.stderr)
            return 1
        missing_sessions = list(missing_fetch_root.glob("*/session.json"))
        if len(missing_sessions) != 1:
            print("missing staged fetch did not write a session record", file=sys.stderr)
            return 1
        missing_doc = json.loads(missing_sessions[0].read_text(encoding="utf-8"))
        if (len(missing_doc.get("fetches") or []) != 1 or
                missing_doc["fetches"][0].get("operation") != "fetch" or
                missing_doc["fetches"][0].get("status") != "missing" or
                missing_doc["fetches"][0].get("http_status") != 404 or
                missing_doc.get("uploads")):
            print("missing staged fetch was incorrectly classified", file=sys.stderr)
            print(json.dumps(missing_doc, indent=2), file=sys.stderr)
            return 1
        missing_events = [json.loads(line) for line in (missing_sessions[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "fetch_complete" and event.get("details", {}).get("status") == "missing" for event in missing_events):
            print("missing staged fetch did not write fetch_complete status", file=sys.stderr)
            return 1
        missing_close_events = [event for event in missing_events if event.get("event") == "connection_close"]
        if (not missing_close_events or
                missing_close_events[-1].get("details", {}).get("operation") != "fetch" or
                missing_close_events[-1].get("details", {}).get("status") != "missing" or
                missing_close_events[-1].get("details", {}).get("http_status") != 404 or
                missing_close_events[-1].get("details", {}).get("request_name") != "not-staged"):
            print("missing fetch connection_close event missing request outcome details", file=sys.stderr)
            return 1
        missing_fetch_status = run(
            "scripts/busierbox-server",
            "--config", str(missing_fetch_cfg),
            "--state-file", str(Path(tmp) / "missing-fetch-state.json"),
            "--staged-file", str(Path(tmp) / "missing-fetch-staged.json"),
            "--json-status",
        )
        missing_fetch_doc = json.loads(missing_fetch_status.stdout)
        missing_fetches = missing_fetch_doc.get("fetches") or []
        if (missing_fetch_doc.get("summary", {}).get("fetch_count") != 1 or
                missing_fetch_doc.get("summary", {}).get("fetch_source_exists_count") != 0 or
                missing_fetch_doc.get("summary", {}).get("fetch_source_missing_count") != 1 or
                len(missing_fetches) != 1 or
                missing_fetches[0].get("request_name") != "not-staged" or
                missing_fetches[0].get("status") != "missing" or
                missing_fetches[0].get("http_status") != 404 or
                missing_fetches[0].get("source_exists") is not False or
                (missing_fetch_doc.get("fetches_by_http_status") or {}).get("404", [{}])[0].get("request_name") != "not-staged"):
            print("server json status missing missing-fetch metadata", file=sys.stderr)
            print(missing_fetch_status.stdout, file=sys.stderr)
            return 1

        serve_dir = Path(tmp) / "operator-files"
        serve_dir.mkdir()
        (serve_dir / "tcpdump").write_text("fake tcpdump\n", encoding="utf-8")
        list_dir = run(
            "scripts/busierbox-server",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--transport", "file-service",
            "--serve-dir", str(serve_dir),
            "--list-staged",
            "--timeout", "0.01",
        )
        if list_dir.returncode != 0 or "busierbox fetch tcpdump" not in list_dir.stdout:
            print("--serve-dir did not stage direct child files", file=sys.stderr)
            print(list_dir.stdout, file=sys.stderr)
            print(list_dir.stderr, file=sys.stderr)
            return 1

        bb = ROOT / "dist" / "busierbox.core"
        if not bb.exists():
            bb = ROOT / "dist" / "busierbox-native-full"
        if bb.exists() and os.access(bb, os.X_OK):
            bb_run = Path(tmp) / "busierbox"
            try:
                bb_run.symlink_to(bb)
            except OSError:
                bb_run.write_bytes(bb.read_bytes())
                bb_run.chmod(0o755)
            existing = Path(tmp) / "existing.out"
            existing.write_text("existing\n", encoding="utf-8")
            overwrite = subprocess.run(
                [str(bb_run), "fetch", "/tmp/myfile", "--host", "127.0.0.1", "--port", str(fetch_port),
                 "--no-tls", "--output", str(existing)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if overwrite.returncode == 0 or "overwrite" not in (overwrite.stdout + overwrite.stderr):
                print("fetch applet did not protect existing output", file=sys.stderr)
                return 1
            traversal = subprocess.run(
                [str(bb_run), "fetch", "../bad", "--host", "127.0.0.1", "--port", str(fetch_port), "--no-tls"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if traversal.returncode == 0 or "path traversal" not in (traversal.stdout + traversal.stderr):
                print("fetch applet did not reject request traversal", file=sys.stderr)
                return 1

            fetch_port2 = free_port()
            fetch_cfg2 = Path(tmp) / "server-config-fetch2.json"
            fetch_cfg2.write_text(json.dumps({
                "listen_host": "127.0.0.1",
                "file_service_port": fetch_port2,
                "session_root": str(Path(tmp) / "sessions-fetch2"),
                "tls_cert": str(cert_path),
                "tls_key": str(key_path),
                "file_service_tls": "no",
            }), encoding="utf-8")
            fetched = Path(tmp) / "fetched.out"
            proc2 = subprocess.Popen(
                [
                    str(server), "--config", str(fetch_cfg2),
                    "--state-file", str(Path(tmp) / "state2.json"),
                    "--staged-file", str(Path(tmp) / "staged2.json"),
                    "--transport", "file-service",
                    "--serve-file", str(staged_source),
                    "--as", "/tmp/myfile",
                    "--file-service-tls", "no",
                    "--one-shot",
                    "--timeout", "5",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.time() + 5
            fetch = None
            while time.time() < deadline:
                fetch = subprocess.run(
                    [str(bb_run), "fetch", "/tmp/myfile", "--host", "127.0.0.1", "--port", str(fetch_port2),
                     "--no-tls", "--output", str(fetched)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                if fetch.returncode == 0:
                    break
                if "download failed" not in (fetch.stdout + fetch.stderr):
                    break
                time.sleep(0.1)
            stdout2, stderr2 = proc2.communicate(timeout=5)
            if not fetch or fetch.returncode != 0 or fetched.read_bytes() != b"operator staged bytes\n":
                print("fetch applet did not retrieve staged file", file=sys.stderr)
                print(fetch.stdout if fetch else "", file=sys.stderr)
                print(fetch.stderr if fetch else "", file=sys.stderr)
                print(stdout2, file=sys.stderr)
                print(stderr2, file=sys.stderr)
                return 1
        else:
            print("skip: built BusierBox artifact missing; fetch applet server smoke skipped")

    print("busierbox-server smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
