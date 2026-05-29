#!/usr/bin/env python3
"""Deterministic intermittent-connectivity harness for operator workflows."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "scripts" / "busierbox-server"


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


def connect_with_retry(port, payload, read_response=True, close_after_send=False):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as conn:
                conn.sendall(payload)
                if close_after_send:
                    try:
                        conn.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                if not read_response:
                    return b""
                return recv_all(conn)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"server did not open port {port}: {last}")


def bridge_roundtrip(port, payload):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as conn:
                conn.sendall(payload)
                return conn.recv(65536)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"bridge did not open port {port}: {last}")


def http_body(response):
    if b"\r\n\r\n" not in response:
        return b""
    return response.split(b"\r\n\r\n", 1)[1]


def json_body(response):
    body = http_body(response)
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def status(cfg, artifact_dir, name, *extra):
    result = run(str(SERVER), "--config", str(cfg), "--json-status", *extra)
    if result.returncode != 0:
        raise RuntimeError(f"status failed for {name}: {result.stderr}")
    doc = json.loads(result.stdout)
    write_json(artifact_dir / f"{name}.json", doc)
    return doc


def start_one_shot(cfg, transport, timeout="10", extra=None):
    args = [str(SERVER), "--config", str(cfg), "--transport", transport, "--timeout", timeout, "--one-shot"]
    if extra:
        args.extend(extra)
    return subprocess.Popen(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_proc(proc, name):
    out, err = proc.communicate(timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} exited {proc.returncode}\nstdout:\n{out}\nstderr:\n{err}")
    return out, err


def start_echo_server(prefix=b"bridge:"):
    ready = threading.Event()
    done = threading.Event()
    result = {"port": 0, "error": ""}

    def serve():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                result["port"] = sock.getsockname()[1]
                ready.set()
                conn, _addr = sock.accept()
                with conn:
                    data = conn.recv(65536)
                    conn.sendall(prefix + data)
        except OSError as exc:
            result["error"] = str(exc)
        finally:
            done.set()

    thread = threading.Thread(target=serve, name="busierbox-flaky-echo")
    thread.start()
    if not ready.wait(5):
        raise RuntimeError("echo server did not start")
    return result, done, thread


def queue_command(cfg, target_id, label, command):
    label_result = run(
        str(SERVER), "--config", str(cfg),
        "--set-target-label", target_id,
        "--target-label", label,
    )
    if label_result.returncode != 0:
        raise RuntimeError(f"target label setup failed for {target_id}: {label_result.stderr}")
    result = run(
        str(SERVER), "--config", str(cfg),
        "--target-id", target_id,
        "--target-label", label,
        "--queue-command", command,
        "--queue-timeout", "7",
        "--queue-max-output", "1024",
    )
    if result.returncode != 0:
        raise RuntimeError(f"queue command failed for {target_id}: {result.stderr}")


def command_ids(queue_file):
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    return {rec.get("target_id"): rec.get("id") for rec in data.get("commands") or []}


def poll_request(target_id="", label="", interval="3600"):
    headers = [
        "GET /command-queue/poll HTTP/1.1",
        "Host: 127.0.0.1",
        "Connection: close",
    ]
    if target_id:
        headers.extend([
            f"X-BusierBox-Target-Id: {target_id}",
            f"X-BusierBox-Target-Label: {label}",
            "X-BusierBox-Command-Queue-Mode: daemon",
            f"X-BusierBox-Command-Queue-Poll-Interval-Sec: {interval}",
        ])
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def result_request(command_id, target_id, label):
    body = json.dumps({
        "schema": 1,
        "command_id": command_id,
        "status": "completed",
        "exit_code": 0,
        "stdout_bytes": 5,
        "stderr_bytes": 0,
    }).encode("utf-8")
    return (
        "POST /command-queue/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"X-BusierBox-Target-Id: {target_id}\r\n"
        f"X-BusierBox-Target-Label: {label}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def dropped_result_request(command_id, target_id, label):
    body = json.dumps({
        "schema": 1,
        "command_id": command_id,
        "status": "completed",
        "exit_code": 0,
    }).encode("utf-8")
    body = body[:max(len(body) // 2, 1)]
    expected = len(body) + 128
    return (
        "POST /command-queue/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"X-BusierBox-Target-Id: {target_id}\r\n"
        f"X-BusierBox-Target-Label: {label}\r\n"
        f"Content-Length: {expected}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def survey_get_request(target_id, label):
    return (
        "GET /survey.sh HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        f"X-BusierBox-Target-Id: {target_id}\r\n"
        f"X-BusierBox-Target-Label: {label}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")


def survey_post_request(target_id, label):
    body = b"schema=1&script=survey.sh&uname_s=Linux&uname_m=mipsel&uname_r=5.10&word_bits=32&endian=little"
    return (
        "POST /survey-bootstrap/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"X-BusierBox-Target-Id: {target_id}\r\n"
        f"X-BusierBox-Target-Label: {label}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def truncated_upload_request(target_id, label):
    body = b"partial-payload\n"
    expected = len(body) + 64
    return (
        "PUT /upload/evidence.txt HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "X-BusierBox-Source-Path: /tmp/evidence.txt\r\n"
        "X-BusierBox-Upload-Kind: evidence\r\n"
        f"X-BusierBox-Target-Id: {target_id}\r\n"
        f"X-BusierBox-Target-Label: {label}\r\n"
        f"Content-Length: {expected}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def save_response(artifact_dir, name, response):
    path = artifact_dir / f"{name}.http"
    path.write_bytes(response)
    return path


def assert_condition(condition, message, detail=None):
    if not condition:
        if detail is not None:
            raise AssertionError(f"{message}: {detail}")
        raise AssertionError(message)


def run_harness(artifact_dir):
    artifact_dir.mkdir(parents=True, exist_ok=True)
    queue_port = free_port()
    survey_port = free_port()
    file_port = free_port()
    bridge_port = free_port()
    operator_dir = artifact_dir / "operator-session"
    session_root = artifact_dir / "sessions"
    cfg = artifact_dir / "server-config.json"
    queue_file = operator_dir / "command-queue.json"
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(operator_dir),
        "session_root": str(session_root),
        "server_state": str(operator_dir / "server-state.json"),
        "targets_file": str(operator_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "command_queue_enable": "yes",
        "command_queue_tls": "no",
        "command_queue_port": str(queue_port),
        "command_queue_require_token": "no",
        "command_queue_allowed_commands": "busierbox-only",
        "command_queue_allow_arbitrary": "no",
        "survey_bootstrap_port": str(survey_port),
        "survey_bootstrap_name": "survey.sh",
        "file_service_enable": "yes",
        "file_service_tls": "no",
        "file_service_port": str(file_port),
        "bridge_listen_port": str(bridge_port),
        "bridge_dest_host": "127.0.0.1",
        "bridge_dest_port": "0",
        "bridge_profiles_file": str(operator_dir / "bridge-profiles.json"),
    })

    phases = []

    queue_command(cfg, "target-alpha", "Alpha Router", "busierbox survey --json")
    queue_command(cfg, "target-bravo", "Bravo Router", "busierbox survey --json")
    ids = command_ids(queue_file)
    alpha_id = ids["target-alpha"]
    bravo_id = ids["target-bravo"]
    offline = status(cfg, artifact_dir, "offline-status")
    assert_condition(offline["summary"]["target_mailbox_pending_work_count"] == 2, "offline mailbox count mismatch")
    phases.append({"name": "offline-queue", "status": "pass", "artifact": "offline-status.json"})

    proc = start_one_shot(cfg, "command-queue")
    anon_response = connect_with_retry(queue_port, poll_request())
    wait_proc(proc, "anonymous poll")
    save_response(artifact_dir, "anonymous-poll", anon_response)
    after_anon = status(cfg, artifact_dir, "after-anonymous-poll")
    assert_condition(b"HTTP/1.1 204 No Content" in anon_response, "anonymous poll should not drain target mailbox")
    assert_condition(after_anon["summary"]["target_mailbox_pending_work_count"] == 2, "anonymous poll changed mailbox")
    phases.append({"name": "anonymous-poll", "status": "pass", "artifact": "after-anonymous-poll.json"})

    proc = start_one_shot(cfg, "command-queue")
    alpha_response = connect_with_retry(queue_port, poll_request("target-alpha", "Alpha Router"))
    wait_proc(proc, "alpha poll")
    save_response(artifact_dir, "alpha-poll", alpha_response)
    alpha_body = json_body(alpha_response)
    assert_condition(b"HTTP/1.1 200 OK" in alpha_response, "target poll did not receive work")
    assert_condition(alpha_body.get("id") == alpha_id, "target poll delivered wrong command", alpha_body)
    after_alpha = status(cfg, artifact_dir, "after-alpha-poll")
    alpha = after_alpha["targets_by_id"]["target-alpha"]
    bravo = after_alpha["targets_by_id"]["target-bravo"]
    assert_condition(alpha["mailbox_delivered_command_count"] == 1, "alpha delivery was not recorded")
    assert_condition(bravo["mailbox_pending_work_count"] == 1, "bravo queued work should remain offline")
    phases.append({"name": "reconnect-delivery", "status": "pass", "artifact": "after-alpha-poll.json"})

    proc = start_one_shot(cfg, "command-queue")
    duplicate_response = connect_with_retry(queue_port, poll_request("target-alpha", "Alpha Router"))
    wait_proc(proc, "duplicate alpha poll")
    save_response(artifact_dir, "duplicate-alpha-poll", duplicate_response)
    after_duplicate = status(cfg, artifact_dir, "after-duplicate-alpha-poll")
    assert_condition(b"HTTP/1.1 204 No Content" in duplicate_response, "duplicate poll should not redeliver work")
    assert_condition(after_duplicate["targets_by_id"]["target-alpha"]["mailbox_pending_work_count"] == 0, "duplicate poll changed alpha mailbox")
    phases.append({"name": "duplicate-poll", "status": "pass", "artifact": "after-duplicate-alpha-poll.json"})

    proc = start_one_shot(cfg, "command-queue")
    dropped_result = connect_with_retry(
        queue_port,
        dropped_result_request(alpha_id, "target-alpha", "Alpha Router"),
        close_after_send=True,
    )
    wait_proc(proc, "dropped alpha result")
    save_response(artifact_dir, "dropped-alpha-result", dropped_result)
    after_dropped_result = status(cfg, artifact_dir, "after-dropped-alpha-result")
    alpha_command = after_dropped_result["target_mailbox_records_by_command_id"][alpha_id]
    assert_condition(b"HTTP/1.1 400 Bad Request" in dropped_result, "dropped result upload should return HTTP 400")
    assert_condition(alpha_command["status"] == "delivered", "dropped result mutated command status", alpha_command)
    assert_condition(alpha_command["delivered_without_result"] is True, "dropped result should leave command awaiting result", alpha_command)
    assert_condition(after_dropped_result["targets_by_id"]["target-alpha"]["mailbox_result_received_command_count"] == 0, "dropped result should not count as received")
    assert_condition(
        after_dropped_result["summary"]["event_type_detail_status_counts"].get("command_queue_result_upload:rejected") == 1,
        "dropped result rejection event missing",
        after_dropped_result["summary"]["event_type_detail_status_counts"],
    )
    phases.append({"name": "dropped-result-upload", "status": "pass", "artifact": "after-dropped-alpha-result.json"})

    proc = start_one_shot(cfg, "command-queue")
    result_response = connect_with_retry(queue_port, result_request(alpha_id, "target-alpha", "Alpha Router"))
    wait_proc(proc, "alpha result")
    save_response(artifact_dir, "alpha-result", result_response)
    after_result = status(cfg, artifact_dir, "after-alpha-result")
    assert_condition(b"HTTP/1.1 200 OK" in result_response, "target result upload failed")
    assert_condition(after_result["targets_by_id"]["target-alpha"]["mailbox_result_received_command_count"] == 1, "alpha result was not recorded")
    assert_condition(after_result["targets_by_id"]["target-bravo"]["mailbox_pending_work_count"] == 1, "bravo offline mailbox was not preserved")
    phases.append({"name": "result-upload", "status": "pass", "artifact": "after-alpha-result.json"})

    proc = start_one_shot(cfg, "survey-bootstrap")
    survey_get = connect_with_retry(survey_port, survey_get_request("target-alpha", "Alpha Router"))
    wait_proc(proc, "survey get")
    save_response(artifact_dir, "survey-get", survey_get)
    assert_condition(b"busierbox survey bootstrap" in survey_get, "survey script was not served")

    proc = start_one_shot(cfg, "survey-bootstrap")
    survey_post = connect_with_retry(survey_port, survey_post_request("target-alpha", "Alpha Router"))
    wait_proc(proc, "survey post")
    save_response(artifact_dir, "survey-post", survey_post)
    survey_status = status(cfg, artifact_dir, "after-survey-result")
    assert_condition(b"HTTP/1.1 200 OK" in survey_post, "survey result upload failed")
    assert_condition(survey_status["targets_by_id"]["target-alpha"]["latest_survey_result_status"] == "received", "survey target state missing")
    phases.append({"name": "survey-window", "status": "pass", "artifact": "after-survey-result.json"})

    proc = start_one_shot(cfg, "file-service")
    partial_response = connect_with_retry(file_port, truncated_upload_request("target-alpha", "Alpha Router"), close_after_send=True)
    wait_proc(proc, "partial file upload")
    save_response(artifact_dir, "partial-upload", partial_response)
    partial_status = status(cfg, artifact_dir, "after-partial-upload")
    assert_condition(b"HTTP/1.1 400 Bad Request" in partial_response, "partial upload should return HTTP 400")
    assert_condition(partial_status["targets_by_id"]["target-alpha"]["latest_file_transfer_status"] == "truncated", "partial transfer not tracked")
    phases.append({"name": "partial-transfer", "status": "pass", "artifact": "after-partial-upload.json"})

    echo, done, thread = start_echo_server()
    save = run(
        str(SERVER), "--config", str(cfg),
        "--target-id", "target-alpha",
        "--save-bridge-profile", "flaky-bridge",
        "--bridge-port", str(bridge_port),
        "--bridge-dest-host", "127.0.0.1",
        "--bridge-dest-port", str(echo["port"]),
        "--bridge-profile-purpose", "flaky-link-test",
        "--bridge-profile-notes", "deterministic harness one-shot bridge",
    )
    if save.returncode != 0:
        raise RuntimeError(f"bridge profile save failed: {save.stderr}")
    proc = start_one_shot(cfg, "bridge", extra=["--bridge-profile", "flaky-bridge", "--session-timeout", "3"])
    bridge_response = bridge_roundtrip(bridge_port, b"hello")
    wait_proc(proc, "bridge relay")
    if not done.wait(5):
        raise RuntimeError("echo server did not complete")
    thread.join(timeout=5)
    if echo.get("error"):
        raise RuntimeError(f"echo server failed: {echo['error']}")
    (artifact_dir / "bridge-response.bin").write_bytes(bridge_response)
    bridge_status = status(cfg, artifact_dir, "after-bridge-relay")
    assert_condition(bridge_response == b"bridge:hello", "bridge relay returned wrong payload", bridge_response)
    assert_condition(bridge_status["targets_by_id"]["target-alpha"]["latest_bridge_status"] == "closed", "bridge activity not tracked")
    phases.append({"name": "bridge-reconnect", "status": "pass", "artifact": "after-bridge-relay.json"})

    summary = {
        "schema": 1,
        "status": "pass",
        "artifact_dir": str(artifact_dir),
        "phases": phases,
        "qemu_lab_followup": {
            "status": "planned",
            "topology": "operator node plus one or more target nodes with controllable link interruption",
            "reuse_scenario": "offline queue, short phone-home window, duplicate poll, result upload, survey, partial transfer, bridge relay",
        },
    }
    write_json(artifact_dir / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", help="directory for status JSON, HTTP transcripts, and summary")
    parser.add_argument("--keep-artifacts", action="store_true", help="keep temporary artifacts when --artifact-dir is omitted")
    args = parser.parse_args()

    cleanup = False
    if args.artifact_dir:
        artifact_dir = Path(args.artifact_dir)
    else:
        artifact_dir = Path(tempfile.mkdtemp(prefix="busierbox-flaky-network-"))
        cleanup = not args.keep_artifacts

    try:
        summary = run_harness(artifact_dir)
    except Exception as exc:
        print(f"flaky-network-harness failed: {exc}", file=sys.stderr)
        print(f"artifacts: {artifact_dir}", file=sys.stderr)
        return 1
    finally:
        if cleanup:
            shutil.rmtree(artifact_dir, ignore_errors=True)

    print(f"flaky-network-harness {summary['status']}: artifacts={summary['artifact_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
