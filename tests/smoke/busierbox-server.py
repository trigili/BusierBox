#!/usr/bin/env python3
import json
import os
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
    for word in ("--tui", "--serve-file", "--serve-dir", "--stage-release-artifact", "--list-staged", "--status", "--stop", "--json-status", "--api-status",
                 "--queue-command", "--list-command-queue", "--clear-command-queue", "--copy-target-command", "--command-copy-file",
                 "--record-command-result", "--result-json"):
        if word not in combined:
            print(f"busierbox-server help missing operator workbench flag: {word}", file=sys.stderr)
            return 1

    # Paramiko key comparison must use get_name/get_base64, not object equality
    src = (ROOT / "scripts" / "busierbox-server").read_text()
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
    for word in ("open_path_in_pager", "pager_command", 'ord("v")', "v opens", "copy_generated_command", "clipboard_command"):
        if word not in src:
            print(f"busierbox-server: workbench pager inspection missing: {word}", file=sys.stderr)
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
    for word in ("reverse_forward_active", "requested_port", "forward_host"):
        if word not in src:
            print(f"busierbox-server: reverse forward event missing: {word}", file=sys.stderr)
            return 1
    if 'name="busierbox-reverse-forward"' not in src or "join(timeout=2.0)" not in src:
        print("busierbox-server: reverse-forward listener thread is not explicitly owned/joined", file=sys.stderr)
        return 1
    for word in ("class ServiceManager", "SERVICE_MANAGER = ServiceManager()", "register_transport",
                 "SERVICE_MANAGER.register_socket", "SERVICE_MANAGER.shutdown()", "register_thread",
                 "start_child_process", "register_child_process", "class EventLog", "class Service",
                 "class Session"):
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
        cfg.write_text(json.dumps({
            "transport": "tls-shell",
            "listen_host": "127.0.0.1",
            "shell_listen_port": port1,
            "session_root": str(Path(tmp) / "sessions"),
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

        command_copy_file = Path(tmp) / "operator-session" / "last-command.txt"
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

        queue_file = Path(tmp) / "operator-session" / "command-queue.json"
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
        if (queue_summary.get("enabled") != "no" or
                queue_summary.get("default_enabled") is not False or
                queue_summary.get("allowed_commands") != "none" or
                queue_summary.get("allow_arbitrary") != "no" or
                queue_summary.get("executes_commands") is not False or
                queue_summary.get("operator_queue_records_only") is not True or
                queue_summary.get("active_control_channel") is not False):
            print("json command queue listing missing explicit safety policy", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        command_id = queue_status["command_queue"]["commands"][0]["id"]
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
                not command_after_result.get("result_received_at")):
            print("operator command queue result metadata missing", file=sys.stderr)
            return 1
        queue_status_doc = run(
            "scripts/busierbox-server",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-status",
        )
        queue_status_json = json.loads(queue_status_doc.stdout)
        if queue_status_json["command_queue"]["result_count"] != 1:
            print("server json status missing command queue summary", file=sys.stderr)
            return 1
        status_queue = queue_status_json["command_queue"]
        if (status_queue.get("enabled") != "no" or
                status_queue.get("configured_for_polling") is not False or
                status_queue.get("arbitrary_execution_allowed") is not False or
                status_queue.get("active_control_channel") is not False or
                status_queue.get("executes_commands") is not False):
            print("server json status missing command queue safety policy", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if "summary" not in queue_status_json or "warnings" not in queue_status_json:
            print("server json status missing top-level summary/warnings", file=sys.stderr)
            return 1
        paths = queue_status_json.get("paths") or {}
        if (not queue_status_json.get("generated_at") or
                paths.get("state_file") != queue_status_json.get("state_file") or
                paths.get("staged_files") != queue_status_json.get("staged_files") or
                paths.get("command_queue_file") != str(queue_file) or
                not paths.get("event_log") or
                not paths.get("operator_session_dir") or
                paths.get("tls_cert") != queue_status_json.get("tls_cert") or
                paths.get("tls_key") != queue_status_json.get("tls_key") or
                paths.get("tls_cert") != str(cert_path) or
                paths.get("tls_key") != str(key_path)):
            print("server json status missing stable generated_at/paths API fields", file=sys.stderr)
            return 1
        if queue_status_json["summary"].get("service_count") != 4:
            print("server json status service summary is wrong", file=sys.stderr)
            return 1
        if (queue_status_json["summary"].get("command_queue_total_count") != 1 or
                queue_status_json["summary"].get("command_queue_result_count") != 1):
            print("server json status missing aggregate command queue counts", file=sys.stderr)
            return 1
        event_stats = queue_status_json.get("event_log_stats") or {}
        if (event_stats.get("total_count", 0) < 2 or
                event_stats.get("tail_count") != len(queue_status_json.get("events", [])) or
                queue_status_json["summary"].get("event_count") != event_stats.get("total_count") or
                queue_status_json["summary"].get("event_tail_count") != event_stats.get("tail_count")):
            print("server json status missing event log total/tail stats", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
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
                "enabled=no default_enabled=no" not in queue_status_text.stdout or
                "allowed_commands=none allow_arbitrary=no active_control_channel=no" not in queue_status_text.stdout or
                "busierbox reality-test --json" not in queue_status_text.stdout or
                "result-received" not in queue_status_text.stdout or
                "command_result_received" not in queue_status_text.stdout or
                "Event log:" not in queue_status_text.stdout or
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
        endpoints = rows["file-service"].get("listener_endpoints") or []
        if not any(endpoint.get("address") == "127.0.0.1" and endpoint.get("port") == lifecycle_port for endpoint in endpoints):
            print("status missing actual listener endpoint address/port", file=sys.stderr)
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
        stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if stop.returncode != 0 or "stopped pid" not in stop.stdout or "port released" not in stop.stdout:
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
        rows_after = {row["name"]: row for row in json.loads(status_after.stdout)["services"]}
        if rows_after["file-service"]["actual"] == "listening":
            print("file-service port still listening after --stop", file=sys.stderr)
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
        if stale_doc.get("summary", {}).get("stale_count", 0) < 1 or not stale_warnings:
            print("--json-status did not expose structured stale-state warning", file=sys.stderr)
            return 1
        stale_stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if stale_stop.returncode != 0 or "stale pid 999999; marked stopped" not in stale_stop.stdout:
            print("--stop did not clean stale PID records", file=sys.stderr)
            print(stale_stop.stdout, file=sys.stderr)
            print(stale_stop.stderr, file=sys.stderr)
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
        sigint_rows = {row["name"]: row for row in json.loads(sigint_after.stdout)["services"]}
        if sigint_rows["file-service"]["actual"] == "listening" or sigint_rows["file-service"]["configured"] != "stopped":
            print("SIGINT foreground listener did not stop and release its port", file=sys.stderr)
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
                not unmanaged_warnings):
            print("--json-status did not expose unmanaged recorded PID warning", file=sys.stderr)
            return 1
        unmanaged_stop = run(
            "scripts/busierbox-server", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if unmanaged_stop.returncode != 0 or "skipped pid" not in unmanaged_stop.stdout:
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
        if metadata.get("source_path") != "/tmp/evidence.txt":
            print("file service metadata missing source path", file=sys.stderr)
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
                not session_doc.get("uploads")):
            print("file service session.json missing structured fields", file=sys.stderr)
            print(session_doc, file=sys.stderr)
            return 1
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
        global_events_path = upload_operator_dir / "events.jsonl"
        global_events = [json.loads(line) for line in global_events_path.read_text(encoding="utf-8").splitlines()]
        if "upload_complete" not in {event.get("event") for event in global_events}:
            print("global operator event log missing upload_complete", file=sys.stderr)
            return 1
        if any(not event.get("id") for event in global_events):
            print("global operator event log entries should carry stable ids", file=sys.stderr)
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
        if (upload_doc.get("summary", {}).get("upload_count", 0) < 1 or
                upload_doc.get("summary", {}).get("session_count", 0) < 1 or
                upload_doc.get("summary", {}).get("event_count", 0) < 1):
            print("server json status missing aggregate upload/session/event counts", file=sys.stderr)
            return 1
        upload_item = (upload_doc.get("uploads") or [{}])[0]
        if (upload_item.get("metadata_path") != str(metadata_path) or
                upload_item.get("stored_exists") is not True or
                upload_item.get("session_id") != session_json_paths[0].parent.name or
                upload_item.get("session_path") != str(session_json_paths[0].parent) or
                upload_item.get("sha256_prefix") != metadata.get("sha256", "")[:12] or
                upload_item.get("status") != "ok"):
            print("server json status missing upload browser metadata", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_session = (upload_doc.get("sessions") or [{}])[0]
        if (upload_session.get("upload_count") != 1 or
                upload_session.get("event_count", 0) < 1 or
                upload_session.get("metadata_path") != str(session_json_paths[0]) or
                upload_session.get("event_log") != str(session_json_paths[0].parent / "events.jsonl")):
            print("server json status missing session browser counts and paths", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_event_stats = upload_doc.get("event_log_stats") or {}
        if (upload_event_stats.get("total_count", 0) < len(global_events) or
                upload_event_stats.get("tail_count") != len(upload_doc.get("events", [])) or
                upload_doc.get("summary", {}).get("event_tail_count") != upload_event_stats.get("tail_count")):
            print("server json status missing upload event log stats", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_status_text = run(
            "scripts/busierbox-server",
            "--config", str(upload_cfg),
            "--status",
        )
        if ("Event log:" not in upload_status_text.stdout or
                "file-service:upload_complete" not in upload_status_text.stdout or
                "Command queue:" not in upload_status_text.stdout or
                "uploads=1" not in upload_status_text.stdout or
                "stored_exists=True" not in upload_status_text.stdout or
                "session:" not in upload_status_text.stdout or
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
                "event_log:" not in uploads_view.stdout or
                "tls_cert:" not in uploads_view.stdout or
                "Event log" not in uploads_view.stdout or
                "uploads=1" not in uploads_view.stdout or
                "stored_exists: True" not in uploads_view.stdout or
                "session:" not in uploads_view.stdout or
                "./busierbox put /etc/config/network" not in uploads_view.stdout):
            print("workbench did not show received upload metadata", file=sys.stderr)
            print(uploads_view.stdout, file=sys.stderr)
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
                "session_root:" not in tui.stdout):
            print("noninteractive TUI/workbench missing operator path details", file=sys.stderr)
            print(tui.stdout, file=sys.stderr)
            return 1

        release_dir = Path(tmp) / "release"
        (release_dir / "bin").mkdir(parents=True)
        (release_dir / "scripts").mkdir()
        (release_dir / "bin" / "busierbox-test").write_text("artifact\n", encoding="utf-8")
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
                "busierbox-test" not in release_view.stdout or
                "compatibility=exact" not in release_view.stdout or
                "compatibility_reason: fixture" not in release_view.stdout or
                "Release devices" not in release_view.stdout or
                "lab-router" not in release_view.stdout or
                "artifacts=1" not in release_view.stdout or
                "artifact_path:" not in release_view.stdout or
                "--stage-release-artifact" not in release_view.stdout):
            print("workbench did not show release artifact paths", file=sys.stderr)
            print(release_view.stdout, file=sys.stderr)
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
        release_summary = release_doc.get("summary") or {}
        if (release_summary.get("release_artifact_count", 0) < 1 or
                release_summary.get("release_device_count") != 1 or
                release_summary.get("release_tuple_count") != 1):
            print("json status missing release aggregate counts", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
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
        if (not staged_status or
                staged_status.get("request_name") != "/tmp/myfile" or
                "fetch /tmp/myfile" not in staged_status.get("fetch_command", "") or
                "--force" not in staged_status.get("fetch_command_force", "") or
                staged_status.get("source_exists") is not True or
                not any("fetch /tmp/myfile" in cmd for cmd in status_doc.get("target_commands", [])) or
                "selected_local_ip" not in status_doc or
                not isinstance(status_doc.get("events"), list)):
            print("json status missing enriched workbench fields", file=sys.stderr)
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
