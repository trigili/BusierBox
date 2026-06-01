#!/usr/bin/env python3
"""Deterministic intermittent-connectivity harness for operator workflows."""

import argparse
import json
import os
import pty
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "scripts" / "grit-server"


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


def bridge_send_once(port, payload):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as conn:
                conn.sendall(payload)
                try:
                    return conn.recv(65536)
                except OSError:
                    return b""
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


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


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


def start_operator_daemon(cfg, *services):
    args = [str(SERVER), "--config", str(cfg), "--daemon"]
    for service in services:
        args.extend(["--daemon-service", service])
    return subprocess.Popen(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_for_service(cfg, proc, service, expected="listening", timeout=20):
    deadline = time.time() + timeout
    latest = {}
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            raise RuntimeError(f"operator daemon exited early: stdout={stdout} stderr={stderr}")
        result = run(str(SERVER), "--config", str(cfg), "--json-status")
        if result.returncode == 0:
            latest = json.loads(result.stdout)
            service_rec = (latest.get("services_by_name") or {}).get(service) or {}
            if service_rec.get("actual") == expected:
                return latest
        time.sleep(0.1)
    raise RuntimeError(f"{service} did not reach {expected}: {json.dumps(latest, sort_keys=True)}")


def stop_operator_daemon(cfg, proc):
    stop = run(str(SERVER), "--config", str(cfg), "--stop")
    if stop.returncode != 0 or "failed=0" not in stop.stdout:
        raise RuntimeError(f"operator daemon stop failed: stdout={stop.stdout} stderr={stop.stderr}")
    stdout, stderr = proc.communicate(timeout=8)
    if proc.returncode not in (0, -15):
        raise RuntimeError(f"operator daemon exited unexpectedly: rc={proc.returncode} stdout={stdout} stderr={stderr}")


def wait_proc(proc, name):
    out, err = proc.communicate(timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} exited {proc.returncode}\nstdout:\n{out}\nstderr:\n{err}")
    return out, err


def run_line_tui(cfg, script, timeout=8):
    master, slave = pty.openpty()
    proc = None
    try:
        proc = subprocess.Popen(
            [str(SERVER), "--config", str(cfg), "--tui"],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERM": "dumb"},
        )
        os.close(slave)
        slave = -1
        time.sleep(0.5)
        os.write(master, script.encode("utf-8"))
        _stdout, stderr = proc.communicate(timeout=timeout)
        output = b""
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
        return {
            "returncode": proc.returncode,
            "stdout": output.decode("utf-8", errors="replace"),
            "stderr": stderr or "",
        }
    finally:
        if slave != -1:
            os.close(slave)
        try:
            os.close(master)
        except OSError:
            pass
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


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

    thread = threading.Thread(target=serve, name="grit-flaky-echo")
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


def run_target_workflow_action(cfg, action, target_id="target-workflow", label="Workflow Target", extra=None):
    label_result = run(
        str(SERVER), "--config", str(cfg),
        "--set-target-label", target_id,
        "--target-label", label,
    )
    if label_result.returncode != 0:
        raise RuntimeError(f"target label setup failed for {target_id}: {label_result.stderr}")
    args = [
        str(SERVER), "--config", str(cfg),
        "--run-target-workflow-action", f"{target_id}:{action}",
    ]
    if extra:
        args.extend(extra)
    result = run(*args)
    if result.returncode != 0:
        raise RuntimeError(f"target workflow action {action} failed: {result.stderr}")
    return result


def run_staged_file_workflow_action(cfg, selector, target_id="target-workflow", label="Workflow Target", extra=None):
    args = [
        str(SERVER), "--config", str(cfg),
        "--target-id", target_id,
        "--target-label", label,
        "--run-staged-file-workflow-action", selector,
    ]
    if extra:
        args.extend(extra)
    result = run(*args)
    if result.returncode != 0:
        raise RuntimeError(f"staged file workflow action {selector} failed: {result.stderr}")
    return result


def command_ids(queue_file):
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    return {rec.get("target_id"): rec.get("id") for rec in data.get("commands") or []}


def poll_request(target_id="", label="", interval="3600", token=""):
    headers = [
        "GET /command-queue/poll HTTP/1.1",
        "Host: 127.0.0.1",
        "Connection: close",
    ]
    if token:
        headers.append(f"X-grit-command-queue-token: {token}")
    if target_id:
        headers.extend([
            f"X-grit-target-id: {target_id}",
            f"X-grit-target-label: {label}",
            "X-grit-command-queue-mode: daemon",
            f"X-grit-command-queue-poll-interval-sec: {interval}",
        ])
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def result_request(command_id, target_id, label, status="completed", exit_code=0, stdout_bytes=5, stderr_bytes=0):
    body = json.dumps({
        "schema": 1,
        "command_id": command_id,
        "status": status,
        "exit_code": exit_code,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
    }).encode("utf-8")
    return (
        "POST /command-queue/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
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
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
        f"Content-Length: {expected}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def malformed_result_request(target_id, label):
    body = b'{"schema": 1, "command_id": '
    return (
        "POST /command-queue/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def survey_get_request(target_id, label):
    return (
        "GET /survey.sh HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")


def survey_post_request(target_id, label):
    body = b"schema=1&script=survey.sh&uname_s=Linux&uname_m=mipsel&uname_r=5.10&word_bits=32&endian=little"
    return (
        "POST /probe/result HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def truncated_upload_request(target_id, label):
    body = b"partial-payload\n"
    expected = len(body) + 64
    return (
        "PUT /upload/evidence.txt HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "X-grit-source-path: /tmp/evidence.txt\r\n"
        "X-grit-upload-kind: evidence\r\n"
        f"X-grit-target-id: {target_id}\r\n"
        f"X-grit-target-label: {label}\r\n"
        f"Content-Length: {expected}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


def save_response(artifact_dir, name, response):
    path = artifact_dir / f"{name}.http"
    path.write_bytes(response)
    return path


def http_status_line(response):
    line = response.split(b"\r\n", 1)[0] if response else b""
    return line.decode("ascii", errors="replace")


def write_target_mailbox_artifact(artifact_dir, doc):
    write_json(artifact_dir / "target-mailbox.json", {
        "schema": 1,
        "kind": "target-mailbox-artifact",
        "summary": {
            "target_mailbox_record_count": doc.get("summary", {}).get("target_mailbox_record_count", 0),
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_status_counts": doc.get("summary", {}).get("target_mailbox_status_counts", {}),
            "target_mailbox_target_connectivity_state_counts": doc.get("summary", {}).get("target_mailbox_target_connectivity_state_counts", {}),
        },
        "targets": doc.get("targets") or [],
        "target_mailbox_records": doc.get("target_mailbox_records") or [],
    })


def write_command_result_artifact(artifact_dir, doc, command_id, response):
    mailbox = (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {}
    write_json(artifact_dir / "command-result.json", {
        "schema": 1,
        "kind": "command-result-artifact",
        "http_status": http_status_line(response),
        "command_id": command_id,
        "target_id": mailbox.get("target_id", ""),
        "target_label": mailbox.get("target_label", ""),
        "status": mailbox.get("status", ""),
        "result_status": mailbox.get("result_status", ""),
        "result_exit_code": mailbox.get("result_exit_code", ""),
        "result_received_at": mailbox.get("result_received_at", ""),
        "target_last_seen": mailbox.get("target_last_seen", ""),
        "target_last_seen_via": mailbox.get("target_last_seen_via", ""),
        "mailbox_record": mailbox,
    })


def write_phone_home_artifact(artifact_dir, doc):
    write_json(artifact_dir / "phone-home-attempts.json", {
        "schema": 1,
        "kind": "phone-home-attempts-artifact",
        "summary": {
            "target_phone_home_record_count": doc.get("summary", {}).get("target_phone_home_record_count", 0),
            "target_phone_home_kind_counts": doc.get("summary", {}).get("target_phone_home_kind_counts", {}),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_failed_counts": doc.get("summary", {}).get("target_phone_home_failed_counts", {}),
            "target_phone_home_anonymous_counts": doc.get("summary", {}).get("target_phone_home_anonymous_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "target_phone_home_records": doc.get("target_phone_home_records") or [],
    })


def write_multi_target_isolation_artifact(artifact_dir, doc, alpha_id, bravo_id):
    by_command = doc.get("target_mailbox_records_by_command_id") or {}
    alpha = (doc.get("targets_by_id") or {}).get("target-alpha") or {}
    bravo = (doc.get("targets_by_id") or {}).get("target-bravo") or {}
    write_json(artifact_dir / "multi-target-isolation.json", {
        "schema": 1,
        "kind": "multi-target-isolation-artifact",
        "alpha_command_id": alpha_id,
        "bravo_command_id": bravo_id,
        "alpha_target": alpha,
        "bravo_target": bravo,
        "alpha_mailbox_record": by_command.get(alpha_id) or {},
        "bravo_mailbox_record": by_command.get(bravo_id) or {},
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_status_counts": doc.get("summary", {}).get("target_mailbox_status_counts", {}),
            "target_mailbox_waiting_for_counts": doc.get("summary", {}).get("target_mailbox_waiting_for_counts", {}),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
        },
        "target_mailbox_records_by_target_id": {
            "target-alpha": (doc.get("target_mailbox_records_by_target_id") or {}).get("target-alpha") or [],
            "target-bravo": (doc.get("target_mailbox_records_by_target_id") or {}).get("target-bravo") or [],
        },
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") in ("target-alpha", "target-bravo")
        ],
    })


def write_bad_token_phone_home_artifact(artifact_dir, doc, command_id):
    write_json(artifact_dir / "bad-token-phone-home.json", {
        "schema": 1,
        "kind": "bad-token-phone-home-artifact",
        "command_id": command_id,
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_failed_counts": doc.get("summary", {}).get("target_phone_home_failed_counts", {}),
            "target_phone_home_http_status_counts": doc.get("summary", {}).get("target_phone_home_http_status_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "mailbox_record": (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {},
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-bad-token"
        ],
    })


def write_duplicate_poll_artifact(artifact_dir, doc, command_id, response):
    write_json(artifact_dir / "duplicate-poll.json", {
        "schema": 1,
        "kind": "duplicate-poll-artifact",
        "command_id": command_id,
        "http_status": http_status_line(response),
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "target": (doc.get("targets_by_id") or {}).get("target-alpha") or {},
        "mailbox_record": (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {},
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-alpha" and rec.get("kind") == "poll"
        ],
    })


def write_dropped_result_upload_artifact(artifact_dir, doc, command_id, response):
    write_json(artifact_dir / "dropped-result-upload.json", {
        "schema": 1,
        "kind": "dropped-result-upload-artifact",
        "command_id": command_id,
        "http_status": http_status_line(response),
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_failed_counts": doc.get("summary", {}).get("target_phone_home_failed_counts", {}),
            "target_phone_home_http_status_counts": doc.get("summary", {}).get("target_phone_home_http_status_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "target": (doc.get("targets_by_id") or {}).get("target-alpha") or {},
        "mailbox_record": (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {},
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-alpha"
            and rec.get("kind") == "result"
            and rec.get("failed") is True
        ],
        "result_upload_events": [
            rec for rec in (doc.get("events") or [])
            if rec.get("event") == "command_queue_result_upload"
            and (rec.get("details") or {}).get("status") == "rejected"
            and str((rec.get("details") or {}).get("target_id") or "") == "target-alpha"
            and str((rec.get("details") or {}).get("reason") or "") == "truncated request body"
        ],
    })


def write_malformed_result_upload_artifact(artifact_dir, doc, command_id, response):
    write_json(artifact_dir / "malformed-result-upload.json", {
        "schema": 1,
        "kind": "malformed-result-upload-artifact",
        "command_id": command_id,
        "http_status": http_status_line(response),
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_failed_counts": doc.get("summary", {}).get("target_phone_home_failed_counts", {}),
            "target_phone_home_http_status_counts": doc.get("summary", {}).get("target_phone_home_http_status_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "target": (doc.get("targets_by_id") or {}).get("target-alpha") or {},
        "mailbox_record": (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {},
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-alpha"
            and rec.get("kind") == "result"
            and rec.get("failed") is True
            and "invalid command result JSON" in str(rec.get("reason") or "")
        ],
        "result_upload_events": [
            rec for rec in (doc.get("events") or [])
            if rec.get("event") == "command_queue_result_upload"
            and (rec.get("details") or {}).get("status") == "rejected"
            and "invalid command result JSON" in str((rec.get("details") or {}).get("reason") or "")
        ],
    })


def write_target_mismatch_phone_home_artifact(artifact_dir, doc, command_id):
    write_json(artifact_dir / "target-mismatch-phone-home.json", {
        "schema": 1,
        "kind": "target-mismatch-phone-home-artifact",
        "command_id": command_id,
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_failed_counts": doc.get("summary", {}).get("target_phone_home_failed_counts", {}),
            "target_phone_home_http_status_counts": doc.get("summary", {}).get("target_phone_home_http_status_counts", {}),
            "target_phone_home_pending_reason_counts": doc.get("summary", {}).get("target_phone_home_pending_reason_counts", {}),
        },
        "mailbox_record": (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {},
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("command_id") == command_id and rec.get("status") == "rejected"
        ],
    })


def write_transfer_log_artifact(artifact_dir, doc, response, status_text=""):
    alpha = (doc.get("targets_by_id") or {}).get("target-alpha") or {}
    uploads = doc.get("uploads") or []
    upload_record = ((doc.get("uploads_by_target_id") or {}).get("target-alpha") or [{}])[0]
    upload_events = [
        rec for rec in (doc.get("events") or [])
        if str(rec.get("service") or "") == "file-service"
        and (str(rec.get("event") or "").startswith("upload_") or rec.get("event") == "connection_close")
        and (rec.get("details") or {}).get("target_id") == "target-alpha"
    ]
    write_json(artifact_dir / "transfer.log", {
        "schema": 1,
        "kind": "transfer-log-artifact",
        "http_status": http_status_line(response),
        "target_id": "target-alpha",
        "target_label": alpha.get("label", ""),
        "target": alpha,
        "latest_file_transfer_status": alpha.get("latest_file_transfer_status", ""),
        "latest_file_transfer_operation": alpha.get("latest_file_transfer_operation", ""),
        "latest_file_transfer_at": alpha.get("latest_file_transfer_at", ""),
        "latest_file_transfer_id": alpha.get("latest_file_transfer_id", ""),
        "summary": {
            "upload_status_counts": (doc.get("summary") or {}).get("upload_status_counts") or {},
            "upload_kind_status_counts": (doc.get("summary") or {}).get("upload_kind_status_counts") or {},
            "upload_status_stored_exists_counts": (doc.get("summary") or {}).get("upload_status_stored_exists_counts") or {},
            "target_latest_file_transfer_status_counts": (doc.get("summary") or {}).get("target_latest_file_transfer_status_counts") or {},
        },
        "api_indexes": {
            "uploads": ((doc.get("api_collections") or {}).get("uploads") or {}).get("indexes") or [],
            "targets": ((doc.get("api_collections") or {}).get("targets") or {}).get("indexes") or [],
        },
        "upload_record": upload_record,
        "uploads": uploads,
        "upload_events": upload_events,
        "status_text": status_text,
    })


def write_bridge_events_artifact(artifact_dir, doc):
    records = [
        rec for rec in (doc.get("events") or [])
        if str(rec.get("service") or "") == "bridge" or str(rec.get("event") or "").startswith("bridge_")
    ]
    write_jsonl(artifact_dir / "bridge-events.jsonl", records)


def write_bridge_interruption_artifact(artifact_dir, doc, profile_name):
    profile = (doc.get("bridge_profiles_by_name") or {}).get(profile_name) or {}
    target = (doc.get("targets_by_id") or {}).get("target-alpha") or {}
    events = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") == "bridge_error"
        and (rec.get("details") or {}).get("bridge_profile") == profile_name
    ]
    write_json(artifact_dir / "bridge-interruption.json", {
        "schema": 1,
        "kind": "bridge-interruption-artifact",
        "profile": profile,
        "target": target,
        "summary": {
            "bridge_profile_has_last_failure_counts": (doc.get("summary") or {}).get("bridge_profile_has_last_failure_counts") or {},
            "target_latest_bridge_status_counts": (doc.get("summary") or {}).get("target_latest_bridge_status_counts") or {},
        },
        "api_indexes": {
            "bridge_profiles": ((doc.get("api_collections") or {}).get("bridge_profiles") or {}).get("indexes") or [],
            "targets": ((doc.get("api_collections") or {}).get("targets") or {}).get("indexes") or [],
        },
        "bridge_error_events": events,
    })


def write_return_offline_artifact(artifact_dir, doc, target_ids, status_text):
    write_json(artifact_dir / "return-offline.json", {
        "schema": 1,
        "kind": "return-offline-artifact",
        "target_ids": target_ids,
        "targets": {
            target_id: (doc.get("targets_by_id") or {}).get(target_id) or {}
            for target_id in target_ids
        },
        "mailbox_records": [
            rec for rec in (doc.get("target_mailbox_records") or [])
            if rec.get("target_id") in target_ids
        ],
        "summary": {
            "target_connectivity_state_counts": doc.get("summary", {}).get("target_connectivity_state_counts", {}),
            "target_poll_overdue_counts": doc.get("summary", {}).get("target_poll_overdue_counts", {}),
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_target_connectivity_state_counts": doc.get("summary", {}).get("target_mailbox_target_connectivity_state_counts", {}),
            "target_mailbox_target_poll_overdue_counts": doc.get("summary", {}).get("target_mailbox_target_poll_overdue_counts", {}),
        },
        "status_text": status_text,
        "api_indexes": {
            "targets": ((doc.get("api_collections") or {}).get("targets") or {}).get("indexes") or [],
            "target_mailbox_records": ((doc.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or [],
        },
    })


def write_offline_workflow_artifact(artifact_dir, doc):
    target = (doc.get("targets_by_id") or {}).get("target-workflow") or {}
    records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    actions = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("target_id") == "target-workflow"
    ]
    staged_actions = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") == "staged_file_workflow_action_completed"
        and (rec.get("details") or {}).get("target_id") == "target-workflow"
    ]
    write_json(artifact_dir / "offline-workflow-mailbox.json", {
        "schema": 1,
        "kind": "offline-workflow-mailbox-artifact",
        "target": target,
        "summary": {
            "target_mailbox_record_count": doc.get("summary", {}).get("target_mailbox_record_count", 0),
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_waiting_for_counts": doc.get("summary", {}).get("target_mailbox_waiting_for_counts", {}),
            "target_workflow_action_result_counts": doc.get("summary", {}).get("target_workflow_action_result_counts", {}),
        },
        "target_mailbox_records": records,
        "target_workflow_action_events": actions,
        "staged_file_workflow_action_events": staged_actions,
    })


def write_offline_workflow_tui_artifact(artifact_dir, doc, tui_result):
    events = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") in ("workbench_command_queue_inspected", "workbench_target_inspected")
    ]
    write_json(artifact_dir / "offline-workflow-tui.json", {
        "schema": 1,
        "kind": "offline-workflow-tui-artifact",
        "returncode": tui_result.get("returncode"),
        "stderr": tui_result.get("stderr", ""),
        "stdout": tui_result.get("stdout", ""),
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_waiting_for_counts": doc.get("summary", {}).get("target_mailbox_waiting_for_counts", {}),
        },
        "workbench_events": events,
    })


def write_offline_workflow_drain_tui_artifact(artifact_dir, doc, tui_result):
    target = (doc.get("targets_by_id") or {}).get("target-workflow") or {}
    records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    events = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") in ("workbench_command_queue_inspected", "workbench_target_inspected")
    ]
    write_json(artifact_dir / "offline-workflow-drain-tui.json", {
        "schema": 1,
        "kind": "offline-workflow-drain-tui-artifact",
        "returncode": tui_result.get("returncode"),
        "stderr": tui_result.get("stderr", ""),
        "stdout": tui_result.get("stdout", ""),
        "target": target,
        "target_mailbox_records": records,
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_work_kind_counts": doc.get("summary", {}).get("target_phone_home_work_kind_counts", {}),
            "target_phone_home_bridge_profile_counts": doc.get("summary", {}).get("target_phone_home_bridge_profile_counts", {}),
            "target_phone_home_route_kind_counts": doc.get("summary", {}).get("target_phone_home_route_kind_counts", {}),
        },
        "workbench_events": events,
    })


def write_offline_workflow_drain_artifact(artifact_dir, doc, delivered_ids, responses):
    records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    write_json(artifact_dir / "offline-workflow-drain.json", {
        "schema": 1,
        "kind": "offline-workflow-drain-artifact",
        "target": (doc.get("targets_by_id") or {}).get("target-workflow") or {},
        "delivered_command_ids": delivered_ids,
        "http_statuses": [http_status_line(response) for response in responses],
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_waiting_for_counts": doc.get("summary", {}).get("target_mailbox_waiting_for_counts", {}),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
        },
        "target_mailbox_records": records,
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-workflow"
        ],
    })


def write_mailbox_lifecycle_artifact(artifact_dir, doc, failed_id, expired_id):
    records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") in ("target-failed", "target-expired")
    ]
    by_command = doc.get("target_mailbox_records_by_command_id") or {}
    write_json(artifact_dir / "mailbox-lifecycle.json", {
        "schema": 1,
        "kind": "mailbox-lifecycle-artifact",
        "summary": {
            "target_mailbox_record_count": doc.get("summary", {}).get("target_mailbox_record_count", 0),
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_status_counts": doc.get("summary", {}).get("target_mailbox_status_counts", {}),
            "target_mailbox_result_status_counts": doc.get("summary", {}).get("target_mailbox_result_status_counts", {}),
            "target_mailbox_expired_counts": doc.get("summary", {}).get("target_mailbox_expired_counts", {}),
        },
        "failed_command_id": failed_id,
        "expired_command_id": expired_id,
        "failed_mailbox_record": by_command.get(failed_id) or {},
        "expired_mailbox_record": by_command.get(expired_id) or {},
        "target_mailbox_records": records,
    })


def write_restart_persistence_artifact(artifact_dir, before_start, after_stop_queue, after_restart, first_id, second_id):
    write_json(artifact_dir / "restart-persistence.json", {
        "schema": 1,
        "kind": "restart-persistence-artifact",
        "first_command_id": first_id,
        "second_command_id": second_id,
        "before_start": {
            "target_mailbox_pending_work_count": before_start.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "command_queue_status_counts": before_start.get("summary", {}).get("command_queue_status_counts", {}),
        },
        "after_stop_queue": {
            "target_mailbox_pending_work_count": after_stop_queue.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "command_queue_status_counts": after_stop_queue.get("summary", {}).get("command_queue_status_counts", {}),
        },
        "after_restart": {
            "target_mailbox_pending_work_count": after_restart.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": after_restart.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_record_count": after_restart.get("summary", {}).get("target_phone_home_record_count", 0),
        },
        "first_mailbox_record": (after_restart.get("target_mailbox_records_by_command_id") or {}).get(first_id) or {},
        "second_mailbox_record": (after_restart.get("target_mailbox_records_by_command_id") or {}).get(second_id) or {},
        "phone_home_records": after_restart.get("target_phone_home_records") or [],
    })


def write_systemd_user_service_artifact(artifact_dir, doc, unit_name, unit_dir, command_results):
    events = [
        rec for rec in (doc.get("events") or [])
        if str(rec.get("service") or "") == "operator-daemon"
        and str(rec.get("event") or "").startswith("systemd_user_")
    ]
    write_json(artifact_dir / "systemd-user-service.json", {
        "schema": 1,
        "kind": "systemd-user-service-artifact",
        "unit_name": unit_name,
        "unit_dir": str(unit_dir),
        "commands": command_results,
        "summary": {
            "event_type_counts": (doc.get("summary") or {}).get("event_type_counts") or {},
            "event_service_counts": (doc.get("summary") or {}).get("event_service_counts") or {},
        },
        "events": events,
    })


def write_tui_offline_queue_artifact(artifact_dir, before_doc, after_doc, tui_result):
    target = (after_doc.get("targets_by_id") or {}).get("target-tui") or {}
    records = [
        rec for rec in (after_doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-tui"
    ]
    events = [
        rec for rec in (after_doc.get("events") or [])
        if rec.get("event") in ("target_workflow_action_selected", "target_workflow_action_completed")
        and (rec.get("details") or {}).get("target_id") == "target-tui"
    ]
    write_json(artifact_dir / "tui-offline-queue.json", {
        "schema": 1,
        "kind": "tui-offline-queue-artifact",
        "returncode": tui_result.get("returncode"),
        "stderr": tui_result.get("stderr", ""),
        "stdout": tui_result.get("stdout", ""),
        "before": {
            "target_mailbox_pending_work_count": before_doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
        },
        "after": {
            "target_mailbox_pending_work_count": after_doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_mailbox_waiting_for_counts": after_doc.get("summary", {}).get("target_mailbox_waiting_for_counts", {}),
            "target_mailbox_work_kind_counts": after_doc.get("summary", {}).get("target_mailbox_work_kind_counts", {}),
            "target_mailbox_request_name_counts": after_doc.get("summary", {}).get("target_mailbox_request_name_counts", {}),
            "target_mailbox_bridge_profile_counts": after_doc.get("summary", {}).get("target_mailbox_bridge_profile_counts", {}),
        },
        "target": target,
        "target_mailbox_records": records,
        "target_workflow_events": events,
    })


def write_tui_offline_queue_drain_artifact(artifact_dir, doc, command_ids, responses):
    target = (doc.get("targets_by_id") or {}).get("target-tui") or {}
    by_command = doc.get("target_mailbox_records_by_command_id") or {}
    records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-tui"
    ]
    write_json(artifact_dir / "tui-offline-queue-drain.json", {
        "schema": 1,
        "kind": "tui-offline-queue-drain-artifact",
        "http_statuses": [http_status_line(response) for response in responses],
        "command_ids": command_ids,
        "target": target,
        "mailbox_record": by_command.get(command_ids[0]) if command_ids else {},
        "target_mailbox_records": records,
        "summary": {
            "target_mailbox_pending_work_count": doc.get("summary", {}).get("target_mailbox_pending_work_count", 0),
            "target_phone_home_status_counts": doc.get("summary", {}).get("target_phone_home_status_counts", {}),
            "target_phone_home_work_kind_counts": doc.get("summary", {}).get("target_phone_home_work_kind_counts", {}),
            "target_phone_home_bridge_profile_counts": doc.get("summary", {}).get("target_phone_home_bridge_profile_counts", {}),
            "target_phone_home_route_kind_counts": doc.get("summary", {}).get("target_phone_home_route_kind_counts", {}),
        },
        "phone_home_records": [
            rec for rec in (doc.get("target_phone_home_records") or [])
            if rec.get("target_id") == "target-tui"
        ],
    })


def write_artifact_manifest(artifact_dir, phases):
    records = []
    for path in sorted(artifact_dir.iterdir()):
        if not path.is_file():
            continue
        records.append({
            "name": path.name,
            "size": path.stat().st_size,
        })
    write_json(artifact_dir / "artifact-manifest.json", {
        "schema": 1,
        "kind": "flaky-network-artifact-manifest",
        "artifact_count": len(records),
        "artifacts": records,
        "phases": phases,
    })


def write_topology_artifact(artifact_dir, cfg, ports, phases):
    cfg_doc = json.loads(Path(cfg).read_text(encoding="utf-8"))
    target_records = status(cfg, artifact_dir, "topology-status").get("targets") or []
    write_json(artifact_dir / "topology.json", {
        "schema": 1,
        "kind": "flaky-network-topology-artifact",
        "operator": {
            "config": str(cfg),
            "operator_session_dir": str(cfg_doc.get("operator_session_dir", "")),
            "session_root": str(cfg_doc.get("session_root", "")),
            "listen_host": str(cfg_doc.get("listen_host", "")),
            "services": {
                "command_queue": {
                    "port": ports.get("command_queue"),
                    "tls": str(cfg_doc.get("GRIT_COMMAND_QUEUE_TLS", "")),
                    "queue_file": str(cfg_doc.get("command_queue_file", "")),
                },
                "survey_bootstrap": {
                    "port": ports.get("survey_bootstrap"),
                    "script_name": str(cfg_doc.get("GRIT_PROBE_NAME", "")),
                },
                "file_service": {
                    "port": ports.get("file_service"),
                    "tls": str(cfg_doc.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "")),
                },
                "bridge": {
                    "port": ports.get("bridge"),
                    "profiles_file": str(cfg_doc.get("bridge_profiles_file", "")),
                },
            },
        },
        "targets": [
            {
                "target_id": rec.get("target_id", ""),
                "label": rec.get("label", ""),
                "connectivity_state": rec.get("connectivity_state", ""),
                "last_seen": rec.get("last_seen", "") or rec.get("last_seen_at", ""),
                "last_seen_via": rec.get("last_seen_via", ""),
                "mailbox_pending_work_count": rec.get("mailbox_pending_work_count", 0),
            }
            for rec in target_records
        ],
        "link_states": [
            {"name": "offline-queue", "state": "offline", "evidence": "target-mailbox.json"},
            {"name": "anonymous-poll", "state": "online-without-target-identity", "evidence": "after-anonymous-poll.json"},
            {"name": "short-alpha-window", "state": "online-target-alpha-only", "evidence": "after-alpha-poll.json"},
            {"name": "duplicate-poll", "state": "online-no-pending-work", "evidence": "duplicate-poll.json"},
            {"name": "malformed-result-upload", "state": "online-rejected-result", "evidence": "malformed-result-upload.json"},
            {"name": "dropped-result-upload", "state": "interrupted-result-upload", "evidence": "dropped-result-upload.json"},
            {"name": "partial-transfer", "state": "interrupted-file-transfer", "evidence": "transfer.log"},
            {"name": "bridge-interruption", "state": "interrupted-bridge-path", "evidence": "bridge-interruption.json"},
            {"name": "return-offline", "state": "offline-after-short-window", "evidence": "return-offline.json"},
        ],
        "operator_commands": [
            "scripts/grit-server --config CONFIG --target-id TARGET --queue-command COMMAND",
            "scripts/grit-server --config CONFIG --transport command-queue --one-shot",
            "scripts/grit-server --config CONFIG --transport probe --one-shot",
            "scripts/grit-server --config CONFIG --transport file-service --one-shot",
            "scripts/grit-server --config CONFIG --transport bridge --bridge-profile PROFILE --one-shot",
            "scripts/grit-server --config CONFIG --daemon --daemon-service command-queue",
        ],
        "qemu_lab_followup": {
            "status": "planned",
            "operator_node": "run the same operator config and service ports inside the lab operator node",
            "target_nodes": "map target ids to separate target nodes and apply the same link_states sequence",
            "accelerated_windows": "replace hour-scale downtime with scripted offline/online transitions around the same mailbox assertions",
            "support_artifacts": [
                "summary.json",
                "artifact-manifest.json",
                "phase-contracts.json",
                "validation-report.json",
                "validate-phase-artifacts.py",
                "host-network-setup.sh",
                "qemu-commands.sh",
                "operator-commands.sh",
                "target-commands.sh",
                "link-transitions.json",
            ],
            "required_artifacts": [
                "summary.json",
                "topology.json",
                "plan.json",
                "phase-contracts.json",
                "validation-report.json",
                "artifact-manifest.json",
                "target-mailbox.json",
                "restart-persistence.json",
                "offline-workflow-mailbox.json",
                "offline-workflow-drain.json",
                "offline-workflow-drain-tui.json",
                "multi-target-isolation.json",
                "bridge-interruption.json",
                "return-offline.json",
            ],
            "phase_contracts": [
                "offline-queue",
                "offline-workflow-drain",
                "short-phone-home-window",
                "multi-target-isolation",
                "bridge-interruption",
                "return-offline",
            ],
        },
        "phase_names": [phase.get("name", "") for phase in phases],
    })


def run_offline_workflow_queue_scenario(artifact_dir):
    scenario_dir = artifact_dir / "offline-workflow-session"
    queue_port = free_port()
    survey_port = free_port()
    file_port = free_port()
    cfg = scenario_dir / "server-config.json"
    queue_file = scenario_dir / "command-queue.json"
    source = scenario_dir / "workflow-payload.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("payload for offline staged fetch\n", encoding="utf-8")
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        "GRIT_PROBE_PORT": str(survey_port),
        "GRIT_PROBE_NAME": "survey.sh",
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
        "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        "GRIT_OPERATOR_FILE_SERVICE_PORT": str(file_port),
    })

    run_target_workflow_action(cfg, "stage-file-fetch", extra=[
        "--target-workflow-local-file", str(source),
        "--target-workflow-request-name", "workflow-payload.txt",
    ])
    run_target_workflow_action(cfg, "queue-probe")
    staged_queue_result = run_staged_file_workflow_action(cfg, "workflow-payload.txt:queue-staged-fetch")
    doc = status(
        cfg, artifact_dir, "offline-workflow-status",
        "--target-id", "target-workflow",
        "--target-label", "Workflow Target",
    )
    target = doc["targets_by_id"]["target-workflow"]
    workflow_events = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("target_id") == "target-workflow"
    ]
    completed_by_action = {
        (rec.get("details") or {}).get("action_id"): (rec.get("details") or {})
        for rec in workflow_events
    }
    staged_workflow_events = [
        rec for rec in (doc.get("events") or [])
        if rec.get("event") == "staged_file_workflow_action_completed"
        and (rec.get("details") or {}).get("target_id") == "target-workflow"
    ]
    staged_completed_by_action = {
        (rec.get("details") or {}).get("action_id"): (rec.get("details") or {})
        for rec in staged_workflow_events
    }
    staged_file_action = (doc.get("staged_file_workflow_actions_by_id") or {}).get("workflow-payload.txt:queue-staged-fetch") or {}
    mailbox_records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    mailbox_commands = "\n".join(rec.get("command") or "" for rec in mailbox_records)
    assert_condition(target["mailbox_pending_work_count"] == 2, "offline workflow mailbox count mismatch", target)
    assert_condition(doc["summary"]["target_mailbox_waiting_for_counts"].get("target-poll") == 2, "offline workflow waiting-for count mismatch")
    assert_condition(completed_by_action.get("stage-file-fetch", {}).get("result") == "staged-file-fetch", "stage-file-fetch event missing", completed_by_action)
    assert_condition(completed_by_action.get("queue-probe", {}).get("result") == "queued-probe", "queue-probe event missing", completed_by_action)
    assert_condition(staged_completed_by_action.get("queue-staged-fetch", {}).get("result") == "queued-staged-fetch", "staged-file queue-staged-fetch event missing", staged_completed_by_action)
    assert_condition(staged_completed_by_action.get("queue-staged-fetch", {}).get("queues_offline_work") is True, "staged-file queue action should be offline queueable", staged_completed_by_action)
    assert_condition("--run-staged-file-workflow-action workflow-payload.txt:queue-staged-fetch" in staged_queue_result.stdout, "staged-file workflow runner did not expose run command", staged_queue_result.stdout)
    assert_condition(staged_file_action.get("run_command", "").find("--run-staged-file-workflow-action workflow-payload.txt:queue-staged-fetch") >= 0, "staged-file workflow action missing stable run command", staged_file_action)
    assert_condition(staged_file_action.get("target_id") == "target-workflow", "staged-file workflow action lost target context", staged_file_action)
    assert_condition("wget -O-" in mailbox_commands and "survey.sh" in mailbox_commands, "queued survey bootstrap command missing", mailbox_commands)
    assert_condition("grit fetch workflow-payload.txt" in mailbox_commands, "queued staged fetch command missing", mailbox_commands)
    write_offline_workflow_artifact(artifact_dir, doc)
    tui_result = run_line_tui(cfg, "20\n18\ntarget-workflow\nq\n")
    assert_condition(tui_result["returncode"] == 0, "offline workflow line TUI failed", tui_result)
    tui_text = tui_result["stdout"]
    assert_condition("headless_command: scripts/grit-server --config" in tui_text, "offline workflow TUI missing headless command", tui_text)
    assert_condition("queue COMMAND  |  queue list  |  queue ? for help" in tui_text, "offline workflow TUI missing command queue controls", tui_text)
    assert_condition("Mailbox  (2 records)" in tui_text, "offline workflow TUI missing mailbox section", tui_text)
    assert_condition("target-workflow" in tui_text, "offline workflow TUI missing target-scoped mailbox records", tui_text)
    assert_condition("waiting_for=target-poll" in tui_text and "pending=2" in tui_text, "offline workflow TUI missing pending mailbox state", tui_text)
    assert_condition("Target detail: target-workflow label=Workflow Target" in tui_text, "offline workflow TUI missing target detail", tui_text)
    assert_condition("mailbox queued=2" in tui_text and "pending=2" in tui_text, "offline workflow TUI missing target mailbox counts", tui_text)
    assert_condition("queue-probe" in tui_text and "queue-staged-fetch" in tui_text, "offline workflow TUI missing offline workflow actions", tui_text)
    tui_doc = status(cfg, artifact_dir, "offline-workflow-tui-status")
    tui_events = tui_doc.get("events_by_event") or {}
    assert_condition(tui_events.get("workbench_command_queue_inspected"), "offline workflow TUI command queue event missing")
    assert_condition(tui_events.get("workbench_target_inspected"), "offline workflow TUI target detail event missing")
    write_offline_workflow_tui_artifact(artifact_dir, tui_doc, tui_result)
    delivered_ids = []
    responses = []
    for idx in (1, 2):
        proc = start_one_shot(cfg, "command-queue")
        response = connect_with_retry(queue_port, poll_request("target-workflow", "Workflow Target"))
        wait_proc(proc, f"offline workflow drain poll {idx}")
        save_response(artifact_dir, f"offline-workflow-drain-poll-{idx}", response)
        body = json_body(response)
        assert_condition(b"HTTP/1.1 200 OK" in response, "offline workflow reconnect did not receive queued work", response)
        assert_condition(body.get("id"), "offline workflow drain response missing command id", body)
        delivered_ids.append(body.get("id"))
        responses.append(response)
    drain_doc = status(cfg, artifact_dir, "offline-workflow-drain-status")
    drain_target = drain_doc["targets_by_id"]["target-workflow"]
    drain_records = [
        rec for rec in (drain_doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    drain_commands = "\n".join(rec.get("command") or "" for rec in drain_records)
    assert_condition(len(set(delivered_ids)) == 2, "offline workflow drain delivered duplicate command ids", delivered_ids)
    assert_condition(drain_target["mailbox_delivered_command_count"] == 2, "offline workflow drain delivery count mismatch", drain_target)
    assert_condition(drain_target["mailbox_pending_work_count"] == 0, "offline workflow drain left queued work pending", drain_target)
    assert_condition(drain_target.get("last_seen"), "offline workflow drain did not update target last_seen", drain_target)
    assert_condition(drain_target.get("last_seen_via") == "command-queue:command_queue_poll", "offline workflow drain last_seen_via mismatch", drain_target)
    assert_condition(drain_target.get("next_expected_poll"), "offline workflow drain did not record next expected poll", drain_target)
    assert_condition(drain_target.get("poll_overdue") is False, "offline workflow drain should not be overdue immediately after reconnect", drain_target)
    assert_condition(drain_target.get("latest_phone_home_status") == "delivered", "offline workflow drain latest phone-home status mismatch", drain_target)
    assert_condition(drain_target.get("latest_successful_phone_home_status") == "delivered", "offline workflow drain successful phone-home status mismatch", drain_target)
    assert_condition(str(drain_target.get("latest_command_queue_poll_interval_sec") or "") == "3600", "offline workflow drain poll interval mismatch", drain_target)
    assert_condition(all(rec.get("status") == "delivered" for rec in drain_records), "offline workflow drain records not delivered", drain_records)
    assert_condition("wget -O-" in drain_commands and "survey.sh" in drain_commands, "drained survey bootstrap command missing", drain_commands)
    assert_condition("grit fetch workflow-payload.txt" in drain_commands, "drained staged fetch command missing", drain_commands)
    assert_condition(drain_doc["summary"]["target_phone_home_status_counts"].get("delivered", 0) >= 2, "offline workflow drain phone-home deliveries missing")
    drain_phone_home = [
        rec for rec in (drain_doc.get("target_phone_home_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    assert_condition(len(drain_phone_home) >= 2, "offline workflow drain phone-home records missing", drain_phone_home)
    assert_condition(all(rec.get("kind") == "poll" for rec in drain_phone_home), "offline workflow drain phone-home kind mismatch", drain_phone_home)
    assert_condition(all(rec.get("successful") is True for rec in drain_phone_home), "offline workflow drain phone-home success mismatch", drain_phone_home)
    assert_condition(any(rec.get("pending_work_remaining") is True for rec in drain_phone_home), "offline workflow drain should record remaining queued work after first poll", drain_phone_home)
    assert_condition(any(rec.get("pending_work_remaining") is False for rec in drain_phone_home), "offline workflow drain should record empty mailbox after final poll", drain_phone_home)
    write_offline_workflow_drain_artifact(artifact_dir, drain_doc, delivered_ids, responses)
    drain_tui_result = run_line_tui(cfg, "20\n18\ntarget-workflow\nq\n")
    assert_condition(drain_tui_result["returncode"] == 0, "offline workflow drain line TUI failed", drain_tui_result)
    drain_tui_text = drain_tui_result["stdout"]
    assert_condition("Mailbox  (2 records)" in drain_tui_text, "offline workflow drain TUI missing mailbox section", drain_tui_text)
    assert_condition("target-workflow" in drain_tui_text, "offline workflow drain TUI missing target-scoped mailbox records", drain_tui_text)
    assert_condition("status=delivered" in drain_tui_text and "pending=0" in drain_tui_text, "offline workflow drain TUI missing delivered mailbox state", drain_tui_text)
    assert_condition("last_seen=" in drain_tui_text and "via=command-queue:command_queue_poll" in drain_tui_text, "offline workflow drain TUI missing heartbeat context", drain_tui_text)
    assert_condition("next_expected_poll=" in drain_tui_text and "poll_overdue=no" in drain_tui_text, "offline workflow drain TUI missing next poll context", drain_tui_text)
    assert_condition("phone_home_latest=" in drain_tui_text and "status=delivered" in drain_tui_text, "offline workflow drain TUI missing phone-home status", drain_tui_text)
    assert_condition("Target detail: target-workflow label=Workflow Target" in drain_tui_text, "offline workflow drain TUI missing target detail", drain_tui_text)
    drain_tui_doc = status(cfg, artifact_dir, "offline-workflow-drain-tui-status")
    drain_tui_events = drain_tui_doc.get("events_by_event") or {}
    assert_condition(drain_tui_events.get("workbench_command_queue_inspected"), "offline workflow drain TUI command queue event missing")
    assert_condition(drain_tui_events.get("workbench_target_inspected"), "offline workflow drain TUI target detail event missing")
    write_offline_workflow_drain_tui_artifact(artifact_dir, drain_tui_doc, drain_tui_result)
    return {"name": "offline-workflow-queue", "status": "pass", "artifact": "offline-workflow-status.json"}


def run_mailbox_lifecycle_scenario(artifact_dir):
    scenario_dir = artifact_dir / "mailbox-lifecycle-session"
    queue_port = free_port()
    cfg = scenario_dir / "server-config.json"
    queue_file = scenario_dir / "command-queue.json"
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
    })

    queue_command(cfg, "target-failed", "Failed Router", "grit survey --json")
    label_result = run(
        str(SERVER), "--config", str(cfg),
        "--set-target-label", "target-expired",
        "--target-label", "Expired Router",
    )
    if label_result.returncode != 0:
        raise RuntimeError(f"target label setup failed for target-expired: {label_result.stderr}")
    expired_queue = run(
        str(SERVER), "--config", str(cfg),
        "--target-id", "target-expired",
        "--target-label", "Expired Router",
        "--queue-command", "grit survey --json",
        "--queue-expire-sec", "1",
    )
    if expired_queue.returncode != 0:
        raise RuntimeError(f"expired command queue failed: {expired_queue.stderr}")
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    failed_id = ""
    expired_id = ""
    for rec in data.get("commands") or []:
        if rec.get("target_id") == "target-failed":
            failed_id = rec.get("id")
        if rec.get("target_id") == "target-expired":
            expired_id = rec.get("id")
            rec["created_at"] = "2000-01-01T00:00:00Z"
            rec["expires_at"] = "2000-01-01T00:00:01Z"
    write_json(queue_file, data)
    assert_condition(failed_id and expired_id, "mailbox lifecycle command ids missing", data)

    proc = start_one_shot(cfg, "command-queue")
    failed_poll = connect_with_retry(queue_port, poll_request("target-failed", "Failed Router"))
    wait_proc(proc, "failed target poll")
    save_response(artifact_dir, "lifecycle-failed-poll", failed_poll)
    assert_condition(b"HTTP/1.1 200 OK" in failed_poll and failed_id.encode("ascii") in failed_poll, "failed target command was not delivered")

    proc = start_one_shot(cfg, "command-queue")
    expired_poll = connect_with_retry(queue_port, poll_request("target-expired", "Expired Router"))
    wait_proc(proc, "expired target poll")
    save_response(artifact_dir, "lifecycle-expired-poll", expired_poll)
    assert_condition(b"HTTP/1.1 204 No Content" in expired_poll and expired_id.encode("ascii") not in expired_poll, "expired command should not be delivered")

    proc = start_one_shot(cfg, "command-queue")
    failed_result = connect_with_retry(
        queue_port,
        result_request(failed_id, "target-failed", "Failed Router", status="failed", exit_code=23, stdout_bytes=0, stderr_bytes=11),
    )
    wait_proc(proc, "failed target result")
    save_response(artifact_dir, "lifecycle-failed-result", failed_result)
    assert_condition(b"HTTP/1.1 200 OK" in failed_result, "failed target result upload failed")

    doc = status(cfg, artifact_dir, "mailbox-lifecycle-status")
    failed = (doc.get("target_mailbox_records_by_command_id") or {}).get(failed_id) or {}
    expired = (doc.get("target_mailbox_records_by_command_id") or {}).get(expired_id) or {}
    assert_condition(failed.get("status") == "result-received", "failed mailbox status mismatch", failed)
    assert_condition(failed.get("result_status") == "failed", "failed mailbox result status mismatch", failed)
    assert_condition(failed.get("result_exit_code") == 23, "failed mailbox exit mismatch", failed)
    assert_condition(expired.get("status") == "expired", "expired mailbox status mismatch", expired)
    assert_condition(expired.get("expired") is True, "expired mailbox flag mismatch", expired)
    assert_condition(expired.get("pending_work") is False, "expired mailbox pending mismatch", expired)
    assert_condition(doc["summary"]["target_mailbox_result_status_counts"].get("failed") == 1, "failed mailbox summary missing")
    assert_condition(doc["summary"]["target_mailbox_expired_counts"].get("True") == 1, "expired mailbox summary missing")
    write_mailbox_lifecycle_artifact(artifact_dir, doc, failed_id, expired_id)
    return {"name": "mailbox-failed-expired", "status": "pass", "artifact": "mailbox-lifecycle-status.json"}


def run_restart_persistence_scenario(artifact_dir):
    scenario_dir = artifact_dir / "restart-persistence-session"
    queue_port = free_port()
    cfg = scenario_dir / "server-config.json"
    queue_file = scenario_dir / "command-queue.json"
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
    })

    queue_command(cfg, "target-restart-a", "Restart Router A", "grit survey --json")
    before_start = status(cfg, artifact_dir, "restart-before-start")
    first_id = command_ids(queue_file)["target-restart-a"]
    assert_condition(before_start["summary"]["target_mailbox_pending_work_count"] == 1, "restart scenario initial queue missing", before_start["summary"])

    daemon = start_operator_daemon(cfg, "command-queue")
    try:
        wait_for_service(cfg, daemon, "command-queue")
        first_poll = connect_with_retry(queue_port, poll_request("target-restart-a", "Restart Router A"))
        save_response(artifact_dir, "restart-first-poll", first_poll)
        assert_condition(b"HTTP/1.1 200 OK" in first_poll and first_id.encode("ascii") in first_poll, "first restart command did not deliver")
        stop_operator_daemon(cfg, daemon)
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            daemon.communicate(timeout=8)

    queue_command(cfg, "target-restart-b", "Restart Router B", "grit survey --json")
    after_stop_queue = status(cfg, artifact_dir, "restart-after-stop-queue")
    second_id = command_ids(queue_file)["target-restart-b"]
    second_before = (after_stop_queue.get("target_mailbox_records_by_command_id") or {}).get(second_id) or {}
    assert_condition(second_before.get("status") == "queued", "second command was not queued while daemon stopped", second_before)

    daemon = start_operator_daemon(cfg, "command-queue")
    try:
        wait_for_service(cfg, daemon, "command-queue")
        second_poll = connect_with_retry(queue_port, poll_request("target-restart-b", "Restart Router B"))
        save_response(artifact_dir, "restart-second-poll", second_poll)
        assert_condition(b"HTTP/1.1 200 OK" in second_poll and second_id.encode("ascii") in second_poll, "queued command did not survive daemon restart")
        after_restart = status(cfg, artifact_dir, "restart-after-reconnect")
        first_after = (after_restart.get("target_mailbox_records_by_command_id") or {}).get(first_id) or {}
        second_after = (after_restart.get("target_mailbox_records_by_command_id") or {}).get(second_id) or {}
        assert_condition(first_after.get("status") == "delivered", "first restart command delivery missing", first_after)
        assert_condition(second_after.get("status") == "delivered", "second restart command delivery missing", second_after)
        assert_condition(after_restart["summary"]["target_phone_home_status_counts"].get("delivered", 0) >= 2, "restart phone-home deliveries missing")
        write_restart_persistence_artifact(artifact_dir, before_start, after_stop_queue, after_restart, first_id, second_id)
        stop_operator_daemon(cfg, daemon)
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            daemon.communicate(timeout=8)
    return {"name": "restart-persistence", "status": "pass", "artifact": "restart-after-reconnect.json"}


def run_bad_token_phone_home_scenario(artifact_dir):
    scenario_dir = artifact_dir / "bad-token-phone-home-session"
    queue_port = free_port()
    cfg = scenario_dir / "server-config.json"
    queue_file = scenario_dir / "command-queue.json"
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "yes",
        "command_queue_token": "correct-token",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
    })

    queue_command(cfg, "target-bad-token", "Bad Token Router", "grit survey --json")
    command_id = command_ids(queue_file)["target-bad-token"]
    proc = start_one_shot(cfg, "command-queue")
    rejected = connect_with_retry(
        queue_port,
        poll_request("target-bad-token", "Bad Token Router", token="wrong-token"),
    )
    wait_proc(proc, "bad token poll")
    save_response(artifact_dir, "bad-token-poll", rejected)
    doc = status(cfg, artifact_dir, "bad-token-phone-home-status")
    mailbox = (doc.get("target_mailbox_records_by_command_id") or {}).get(command_id) or {}
    attempts = [
        rec for rec in (doc.get("target_phone_home_records") or [])
        if rec.get("target_id") == "target-bad-token"
    ]
    assert_condition(b"HTTP/1.1 403 Forbidden" in rejected, "bad token poll should return HTTP 403")
    assert_condition(mailbox.get("status") == "queued", "bad token poll should not drain queued work", mailbox)
    assert_condition(doc["summary"]["target_mailbox_pending_work_count"] == 1, "bad token poll should leave mailbox pending")
    assert_condition(attempts, "bad token phone-home attempt was not recorded")
    assert_condition(attempts[0].get("status") == "rejected", "bad token phone-home status mismatch", attempts[0])
    assert_condition(attempts[0].get("failed") is True, "bad token phone-home should be failed", attempts[0])
    assert_condition(attempts[0].get("http_status") == "403", "bad token HTTP status missing", attempts[0])
    assert_condition(attempts[0].get("reason") == "invalid token", "bad token reason missing", attempts[0])
    write_bad_token_phone_home_artifact(artifact_dir, doc, command_id)
    return {"name": "bad-token-phone-home", "status": "pass", "artifact": "bad-token-phone-home-status.json"}


def run_systemd_user_service_scenario(artifact_dir):
    scenario_dir = artifact_dir / "systemd-user-session"
    cfg = scenario_dir / "server-config.json"
    unit_dir = scenario_dir / "systemd-user"
    unit_name = "grit-flaky.service"
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(scenario_dir / "command-queue.json"),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
    })

    command_results = []
    for action in ("print", "install", "start", "stop", "restart", "status"):
        args = [
            str(SERVER), "--config", str(cfg),
            "--daemon-service", "file-service",
            "--daemon-service", "command-queue",
            "--systemd-user-action", action,
            "--systemd-user-unit-name", unit_name,
            "--systemd-user-unit-dir", str(unit_dir),
        ]
        if action != "print":
            args.append("--systemd-user-dry-run")
        result = run(*args)
        assert_condition(result.returncode == 0, f"systemd user {action} command failed", result.stderr)
        command_results.append({
            "action": action,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })

    by_action = {rec["action"]: rec for rec in command_results}
    assert_condition("Description=griTTYkit Operator Daemon" in by_action["print"]["stdout"], "systemd print missing unit description")
    assert_condition("--daemon --daemon-service file-service --daemon-service command-queue" in by_action["print"]["stdout"], "systemd print missing daemon command")
    assert_condition("would write" in by_action["install"]["stdout"], "systemd install dry-run missing write plan")
    assert_condition("systemctl --user start grit-flaky.service" == by_action["start"]["stdout"].strip(), "systemd start dry-run mismatch")
    assert_condition("systemctl --user stop grit-flaky.service" == by_action["stop"]["stdout"].strip(), "systemd stop dry-run mismatch")
    assert_condition("systemctl --user restart grit-flaky.service" == by_action["restart"]["stdout"].strip(), "systemd restart dry-run mismatch")
    assert_condition("systemctl --user status grit-flaky.service" == by_action["status"]["stdout"].strip(), "systemd status dry-run mismatch")

    doc = status(cfg, artifact_dir, "systemd-user-service-status", "--event-limit", "64")
    events = [
        rec for rec in (doc.get("events") or [])
        if str(rec.get("service") or "") == "operator-daemon"
        and str(rec.get("event") or "").startswith("systemd_user_")
    ]
    assert_condition(any(rec.get("event") == "systemd_user_unit_printed" for rec in events), "systemd print event missing", events)
    assert_condition(any(rec.get("event") == "systemd_user_unit_install_dry_run" for rec in events), "systemd install dry-run event missing", events)
    for action in ("start", "stop", "restart", "status"):
        assert_condition(any(
            rec.get("event") == "systemd_user_action_dry_run"
            and (rec.get("details") or {}).get("action") == action
            and (rec.get("details") or {}).get("systemctl_command") == f"systemctl --user {action} {unit_name}"
            for rec in events
        ), f"systemd {action} dry-run event missing", events)
    assert_condition(all((rec.get("details") or {}).get("headless_command") for rec in events), "systemd event headless command missing", events)
    write_systemd_user_service_artifact(artifact_dir, doc, unit_name, unit_dir, command_results)
    return {"name": "systemd-user-service", "status": "pass", "artifact": "systemd-user-service-status.json"}


def run_tui_offline_queue_scenario(artifact_dir):
    scenario_dir = artifact_dir / "tui-offline-queue-session"
    queue_port = free_port()
    survey_port = free_port()
    file_port = free_port()
    bridge_port = free_port()
    bridge_dest_port = free_port()
    cfg = scenario_dir / "server-config.json"
    queue_file = scenario_dir / "command-queue.json"
    source = scenario_dir / "tui-payload.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("payload queued from TUI while offline\n", encoding="utf-8")
    write_json(cfg, {
        "listen_host": "127.0.0.1",
        "operator_session_dir": str(scenario_dir),
        "session_root": str(scenario_dir / "sessions"),
        "server_state": str(scenario_dir / "server-state.json"),
        "targets_file": str(scenario_dir / "targets.json"),
        "command_queue_file": str(queue_file),
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        "GRIT_PROBE_PORT": str(survey_port),
        "GRIT_PROBE_NAME": "survey.sh",
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
        "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        "GRIT_OPERATOR_FILE_SERVICE_PORT": str(file_port),
        "bridge_listen_port": str(bridge_port),
        "bridge_dest_host": "127.0.0.1",
        "bridge_dest_port": str(bridge_dest_port),
        "bridge_profiles_file": str(scenario_dir / "bridge-profiles.json"),
    })
    label_result = run(
        str(SERVER), "--config", str(cfg),
        "--set-target-label", "target-tui",
        "--target-label", "TUI Target",
    )
    if label_result.returncode != 0:
        raise RuntimeError(f"TUI target label setup failed: {label_result.stderr}")
    bridge_profile_result = run(
        str(SERVER), "--config", str(cfg),
        "--target-id", "target-tui",
        "--save-bridge-profile", "tui-bridge",
        "--bridge-port", str(bridge_port),
        "--bridge-dest-host", "127.0.0.1",
        "--bridge-dest-port", str(bridge_dest_port),
        "--bridge-profile-purpose", "tui-offline-bridge-work",
        "--bridge-profile-notes", "queued from TUI while target is offline",
    )
    if bridge_profile_result.returncode != 0:
        raise RuntimeError(f"TUI bridge profile setup failed: {bridge_profile_result.stderr}")

    before_doc = status(cfg, artifact_dir, "tui-offline-queue-before")
    tui_results = [
        run_line_tui(cfg, "15\ntarget-tui:queue-command\ngrit survey --json\nq\n"),
        run_line_tui(cfg, "15\ntarget-tui:queue-probe\nq\n"),
        run_line_tui(cfg, f"15\ntarget-tui:stage-file-fetch\n{source}\ntui-payload.txt\nq\n"),
        run_line_tui(cfg, "15\ntarget-tui:queue-staged-fetch\ntui-payload.txt\nq\n"),
        run_line_tui(cfg, "15\ntarget-tui:queue-bridge-start:tui-bridge\nq\n"),
    ]
    tui_result = {
        "returncode": 0 if all(item.get("returncode") == 0 for item in tui_results) else 1,
        "stderr": "\n".join(item.get("stderr", "") for item in tui_results if item.get("stderr")),
        "stdout": "\n".join(item.get("stdout", "") for item in tui_results),
    }
    assert_condition(tui_result["returncode"] == 0, "TUI offline queue action failed", tui_result)
    tui_text = tui_result["stdout"]
    assert_condition("target workflow action: target-tui:queue-command" in tui_text, "TUI offline queue action was not selected", tui_text)
    assert_condition("target workflow action: target-tui:queue-probe" in tui_text, "TUI offline probe queue action was not selected", tui_text)
    assert_condition("target workflow action: target-tui:stage-file-fetch" in tui_text, "TUI offline stage-file action was not selected", tui_text)
    assert_condition("target workflow action: target-tui:queue-staged-fetch" in tui_text, "TUI offline staged-fetch queue action was not selected", tui_text)
    assert_condition("target workflow action: target-tui:queue-bridge-start:tui-bridge" in tui_text, "TUI offline bridge queue action was not selected", tui_text)
    assert_condition("command to queue>" in tui_text, "TUI offline queue action did not prompt for command", tui_text)
    assert_condition("staged tui-payload.txt" in tui_text, "TUI offline file stage action did not stage file", tui_text)
    assert_condition("queued " in tui_text and "grit survey --json" in tui_text, "TUI offline queue action did not queue command", tui_text)
    assert_condition("survey.sh" in tui_text, "TUI offline survey queue action did not queue survey command", tui_text)
    assert_condition("grit fetch tui-payload.txt" in tui_text, "TUI offline staged-fetch action did not queue fetch command", tui_text)
    assert_condition("bridge_profile=tui-bridge" in tui_text and "grit rshell start" in tui_text, "TUI offline bridge action did not queue bridge work", tui_text)

    after_doc = status(cfg, artifact_dir, "tui-offline-queue-after", "--event-limit", "128")
    records = [
        rec for rec in (after_doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-tui"
    ]
    assert_condition(len(records) == 4, "TUI offline queue should create four mailbox records", records)
    command_ids_to_drain = [rec.get("command_id") or rec.get("id") or "" for rec in records]
    assert_condition(all(command_ids_to_drain), "TUI offline queue command ids missing", records)
    queued_commands = "\n".join(rec.get("command") or "" for rec in records)
    survey_mailbox = next((rec for rec in records if "survey.sh" in str(rec.get("command") or "")), {})
    fetch_mailbox = next((rec for rec in records if "grit fetch tui-payload.txt" in str(rec.get("command") or "")), {})
    bridge_mailbox = next((rec for rec in records if rec.get("command") == "grit rshell start"), {})
    assert_condition("grit survey --json" in queued_commands, "TUI offline queue command missing", queued_commands)
    assert_condition("survey.sh" in queued_commands, "TUI offline queued survey command missing", queued_commands)
    assert_condition("grit fetch tui-payload.txt" in queued_commands, "TUI offline queued fetch command missing", queued_commands)
    assert_condition("grit rshell start" in queued_commands, "TUI offline queued bridge command missing", queued_commands)
    assert_condition(survey_mailbox.get("work_kind") == "probe", "TUI offline probe mailbox work kind missing", survey_mailbox)
    assert_condition(survey_mailbox.get("workflow") == "probe", "TUI offline probe mailbox workflow missing", survey_mailbox)
    assert_condition(survey_mailbox.get("request_name") == "survey.sh", "TUI offline survey mailbox request name missing", survey_mailbox)
    assert_condition(fetch_mailbox.get("work_kind") == "staged-fetch", "TUI offline fetch mailbox work kind missing", fetch_mailbox)
    assert_condition(fetch_mailbox.get("workflow") == "file-service", "TUI offline fetch mailbox workflow missing", fetch_mailbox)
    assert_condition(fetch_mailbox.get("request_name") == "tui-payload.txt", "TUI offline fetch mailbox request name missing", fetch_mailbox)
    assert_condition(bridge_mailbox.get("work_kind") == "bridge-start", "TUI offline bridge mailbox work kind missing", bridge_mailbox)
    assert_condition(bridge_mailbox.get("workflow") == "bridge", "TUI offline bridge mailbox workflow missing", bridge_mailbox)
    assert_condition(bridge_mailbox.get("bridge_profile") == "tui-bridge", "TUI offline bridge mailbox profile missing", bridge_mailbox)
    assert_condition(bridge_mailbox.get("bridge_route_path"), "TUI offline bridge mailbox route missing", bridge_mailbox)
    assert_condition(bridge_mailbox.get("route_kind") == "bridge", "TUI offline bridge mailbox route kind missing", bridge_mailbox)
    assert_condition(after_doc["summary"]["target_mailbox_bridge_profile_counts"].get("tui-bridge") == 1, "TUI offline bridge mailbox profile summary missing")
    assert_condition(after_doc["summary"]["target_mailbox_work_kind_counts"].get("probe") == 1, "TUI offline probe mailbox work-kind summary missing")
    assert_condition(after_doc["summary"]["target_mailbox_work_kind_counts"].get("staged-fetch") == 1, "TUI offline staged-fetch mailbox work-kind summary missing")
    assert_condition(after_doc["summary"]["target_mailbox_work_kind_counts"].get("bridge-start") == 1, "TUI offline bridge mailbox work-kind summary missing")
    assert_condition(after_doc["summary"]["target_mailbox_request_name_counts"].get("survey.sh") == 1, "TUI offline survey mailbox request-name summary missing")
    assert_condition(after_doc["summary"]["target_mailbox_request_name_counts"].get("tui-payload.txt") == 1, "TUI offline staged-fetch mailbox request-name summary missing")
    assert_condition(
        ((after_doc.get("target_mailbox_records_by_bridge_profile") or {}).get("tui-bridge") or [{}])[0].get("command_id") == bridge_mailbox.get("command_id"),
        "TUI offline bridge mailbox profile index missing",
    )
    assert_condition(
        "target_mailbox_records_by_bridge_profile" in (((after_doc.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []),
        "TUI offline bridge mailbox API index missing",
    )
    assert_condition(all(rec.get("status") == "queued" for rec in records), "TUI offline queue mailbox status mismatch", records)
    assert_condition(all(rec.get("pending_work") is True for rec in records), "TUI offline queue should remain pending while target is offline", records)
    assert_condition(all(rec.get("waiting_for") == "target-poll" for rec in records), "TUI offline queue waiting_for mismatch", records)
    assert_condition(after_doc["targets_by_id"]["target-tui"]["mailbox_pending_work_count"] == 4, "TUI target pending mailbox count mismatch")
    assert_condition(any(
        rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("action_id") == "queue-command"
        and (rec.get("details") or {}).get("queues_offline_work") is True
        for rec in (after_doc.get("events") or [])
    ), "TUI offline queue completion event missing")
    assert_condition(any(
        rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("action_id") == "queue-probe"
        and (rec.get("details") or {}).get("queues_offline_work") is True
        for rec in (after_doc.get("events") or [])
    ), "TUI offline survey queue completion event missing")
    assert_condition(any(
        rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("action_id") == "stage-file-fetch"
        for rec in (after_doc.get("events") or [])
    ), "TUI offline stage-file completion event missing")
    assert_condition(any(
        rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("action_id") == "queue-staged-fetch"
        and (rec.get("details") or {}).get("queues_offline_work") is True
        for rec in (after_doc.get("events") or [])
    ), "TUI offline staged-fetch queue completion event missing")
    assert_condition(any(
        rec.get("event") == "target_workflow_action_completed"
        and (rec.get("details") or {}).get("action_id") == "queue-bridge-start:tui-bridge"
        and (rec.get("details") or {}).get("bridge_profile") == "tui-bridge"
        and (rec.get("details") or {}).get("queues_offline_work") is True
        for rec in (after_doc.get("events") or [])
    ), "TUI offline bridge queue completion event missing")
    write_tui_offline_queue_artifact(artifact_dir, before_doc, after_doc, tui_result)

    responses = []
    delivered_ids = []
    for idx in range(1, 5):
        proc = start_one_shot(cfg, "command-queue")
        response = connect_with_retry(queue_port, poll_request("target-tui", "TUI Target"))
        wait_proc(proc, f"TUI offline queued target poll {idx}")
        save_response(artifact_dir, f"tui-offline-queue-poll-{idx}", response)
        body = json_body(response)
        assert_condition(b"HTTP/1.1 200 OK" in response, "TUI offline queued command was not delivered", response)
        assert_condition(body.get("id"), "TUI offline queued poll response missing command id", body)
        responses.append(response)
        delivered_ids.append(body.get("id"))
    assert_condition(set(delivered_ids) == set(command_ids_to_drain), "TUI offline queue drain delivered wrong command ids", delivered_ids)

    drain_doc = status(cfg, artifact_dir, "tui-offline-queue-drain-status")
    drained_records = [
        rec for rec in (drain_doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-tui"
    ]
    target = drain_doc["targets_by_id"]["target-tui"]
    drained_survey = next((rec for rec in drained_records if "survey.sh" in str(rec.get("command") or "")), {})
    drained_fetch = next((rec for rec in drained_records if "grit fetch tui-payload.txt" in str(rec.get("command") or "")), {})
    drained_bridge = next((rec for rec in drained_records if rec.get("command") == "grit rshell start"), {})
    assert_condition(len(drained_records) == 4, "TUI offline queue drain records missing", drained_records)
    assert_condition(all(rec.get("status") == "delivered" for rec in drained_records), "TUI offline queued work did not become delivered", drained_records)
    assert_condition(all(rec.get("pending_work") is False for rec in drained_records), "TUI offline queued work should no longer be pending", drained_records)
    assert_condition(drained_bridge.get("bridge_profile") == "tui-bridge", "TUI offline drained bridge mailbox profile missing", drained_bridge)
    assert_condition(drained_bridge.get("work_kind") == "bridge-start", "TUI offline drained bridge mailbox work kind missing", drained_bridge)
    assert_condition(drained_survey.get("work_kind") == "probe", "TUI offline drained probe mailbox work kind missing", drained_survey)
    assert_condition(drained_fetch.get("work_kind") == "staged-fetch", "TUI offline drained fetch mailbox work kind missing", drained_fetch)
    assert_condition(target.get("last_seen_via") == "command-queue:command_queue_poll", "TUI offline queue drain last_seen_via mismatch", target)
    assert_condition(target.get("mailbox_pending_work_count") == 0, "TUI offline queue drain left pending work", target)
    assert_condition(target.get("latest_phone_home_status") == "delivered", "TUI offline queue drain phone-home status mismatch", target)
    delivered_phone_home = [
        rec for rec in (drain_doc.get("target_phone_home_records") or [])
        if rec.get("target_id") == "target-tui" and rec.get("status") == "delivered"
    ]
    phone_home_by_work_kind = {
        rec.get("work_kind"): rec for rec in delivered_phone_home
        if rec.get("work_kind")
    }
    assert_condition(phone_home_by_work_kind.get("probe"), "TUI offline probe delivery phone-home work metadata missing", delivered_phone_home)
    assert_condition(phone_home_by_work_kind.get("staged-fetch"), "TUI offline fetch delivery phone-home work metadata missing", delivered_phone_home)
    assert_condition(phone_home_by_work_kind.get("bridge-start"), "TUI offline bridge delivery phone-home work metadata missing", delivered_phone_home)
    assert_condition(phone_home_by_work_kind["probe"].get("request_name") == "survey.sh", "TUI offline probe delivery request name missing", phone_home_by_work_kind["probe"])
    assert_condition(phone_home_by_work_kind["staged-fetch"].get("request_name") == "tui-payload.txt", "TUI offline fetch delivery request name missing", phone_home_by_work_kind["staged-fetch"])
    assert_condition(phone_home_by_work_kind["bridge-start"].get("bridge_profile") == "tui-bridge", "TUI offline bridge delivery phone-home profile missing", phone_home_by_work_kind["bridge-start"])
    assert_condition(phone_home_by_work_kind["bridge-start"].get("route_kind") == "bridge", "TUI offline bridge delivery route kind missing", phone_home_by_work_kind["bridge-start"])
    assert_condition(drain_doc["summary"]["target_phone_home_work_kind_counts"].get("probe") == 1, "TUI offline probe phone-home work-kind summary missing")
    assert_condition(drain_doc["summary"]["target_phone_home_work_kind_counts"].get("staged-fetch") == 1, "TUI offline fetch phone-home work-kind summary missing")
    assert_condition(drain_doc["summary"]["target_phone_home_work_kind_counts"].get("bridge-start") == 1, "TUI offline bridge phone-home work-kind summary missing")
    assert_condition(drain_doc["summary"]["target_phone_home_bridge_profile_counts"].get("tui-bridge") == 1, "TUI offline bridge phone-home profile summary missing")
    assert_condition("target_phone_home_records_by_work_kind" in (((drain_doc.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or []), "target phone-home work-kind index missing")
    assert_condition(((drain_doc.get("target_phone_home_records_by_bridge_profile") or {}).get("tui-bridge") or [{}])[0].get("command_id") == drained_bridge.get("command_id"), "target phone-home bridge-profile index missing")
    write_tui_offline_queue_drain_artifact(artifact_dir, drain_doc, command_ids_to_drain, responses)
    return {"name": "tui-offline-queue", "status": "pass", "artifact": "tui-offline-queue-after.json"}


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
        "GRIT_COMMAND_QUEUE_ENABLE": "yes",
        "GRIT_COMMAND_QUEUE_TLS": "no",
        "GRIT_COMMAND_QUEUE_PORT": str(queue_port),
        "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
        "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
        "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        "GRIT_PROBE_PORT": str(survey_port),
        "GRIT_PROBE_NAME": "survey.sh",
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
        "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        "GRIT_OPERATOR_FILE_SERVICE_PORT": str(file_port),
        "bridge_listen_port": str(bridge_port),
        "bridge_dest_host": "127.0.0.1",
        "bridge_dest_port": "0",
        "bridge_profiles_file": str(operator_dir / "bridge-profiles.json"),
    })

    phases = []

    phases.append(run_offline_workflow_queue_scenario(artifact_dir))
    phases.append(run_mailbox_lifecycle_scenario(artifact_dir))
    phases.append(run_restart_persistence_scenario(artifact_dir))
    phases.append(run_bad_token_phone_home_scenario(artifact_dir))
    phases.append(run_systemd_user_service_scenario(artifact_dir))
    phases.append(run_tui_offline_queue_scenario(artifact_dir))

    queue_command(cfg, "target-alpha", "Alpha Router", "grit survey --json")
    queue_command(cfg, "target-bravo", "Bravo Router", "grit survey --json")
    ids = command_ids(queue_file)
    alpha_id = ids["target-alpha"]
    bravo_id = ids["target-bravo"]
    offline = status(cfg, artifact_dir, "offline-status")
    assert_condition(offline["summary"]["target_mailbox_pending_work_count"] == 2, "offline mailbox count mismatch")
    write_target_mailbox_artifact(artifact_dir, offline)
    phases.append({"name": "offline-queue", "status": "pass", "artifact": "offline-status.json"})

    proc = start_one_shot(cfg, "command-queue")
    anon_response = connect_with_retry(queue_port, poll_request())
    wait_proc(proc, "anonymous poll")
    save_response(artifact_dir, "anonymous-poll", anon_response)
    after_anon = status(cfg, artifact_dir, "after-anonymous-poll")
    assert_condition(b"HTTP/1.1 204 No Content" in anon_response, "anonymous poll should not drain target mailbox")
    assert_condition(after_anon["summary"]["target_mailbox_pending_work_count"] == 2, "anonymous poll changed mailbox")
    anonymous_attempts = [
        rec for rec in after_anon.get("target_phone_home_records") or []
        if rec.get("kind") == "poll" and rec.get("anonymous") is True
    ]
    assert_condition(anonymous_attempts, "anonymous phone-home attempt was not recorded")
    assert_condition(
        anonymous_attempts[0].get("pending_reason") == "queued work requires a target identity",
        "anonymous phone-home pending reason missing",
        anonymous_attempts[0],
    )
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
    duplicate_record = (after_duplicate.get("target_mailbox_records_by_command_id") or {}).get(alpha_id) or {}
    duplicate_attempts = [
        rec for rec in after_duplicate.get("target_phone_home_records") or []
        if rec.get("target_id") == "target-alpha" and rec.get("kind") == "poll" and rec.get("status") == "no-command"
    ]
    assert_condition(duplicate_record.get("status") == "delivered", "duplicate poll mutated delivered command", duplicate_record)
    assert_condition(duplicate_record.get("delivered_without_result") is True, "duplicate poll should leave command waiting for result", duplicate_record)
    assert_condition(duplicate_attempts, "duplicate poll phone-home record missing", after_duplicate.get("target_phone_home_records"))
    assert_condition(duplicate_attempts[-1].get("successful") is True, "duplicate poll should be an auditable successful no-command poll", duplicate_attempts[-1])
    write_duplicate_poll_artifact(artifact_dir, after_duplicate, alpha_id, duplicate_response)
    phases.append({"name": "duplicate-poll", "status": "pass", "artifact": "after-duplicate-alpha-poll.json"})

    proc = start_one_shot(cfg, "command-queue")
    mismatched_result = connect_with_retry(
        queue_port,
        result_request(alpha_id, "target-bravo", "Bravo Router"),
    )
    wait_proc(proc, "mismatched alpha result")
    save_response(artifact_dir, "mismatched-alpha-result", mismatched_result)
    after_mismatch = status(cfg, artifact_dir, "after-mismatched-alpha-result")
    alpha_after_mismatch = after_mismatch["target_mailbox_records_by_command_id"][alpha_id]
    mismatch_attempts = [
        rec for rec in after_mismatch.get("target_phone_home_records") or []
        if rec.get("kind") == "result" and rec.get("command_id") == alpha_id and rec.get("failed") is True
    ]
    assert_condition(b"HTTP/1.1 400 Bad Request" in mismatched_result, "mismatched result upload should return HTTP 400")
    assert_condition(b"command result target mismatch" in mismatched_result, "mismatched result upload should explain target mismatch")
    assert_condition(alpha_after_mismatch["status"] == "delivered", "mismatched result mutated command status", alpha_after_mismatch)
    assert_condition(alpha_after_mismatch["delivered_without_result"] is True, "mismatched result should leave command awaiting result", alpha_after_mismatch)
    assert_condition(mismatch_attempts, "mismatched result phone-home rejection was not recorded")
    assert_condition("command result target mismatch" in mismatch_attempts[0].get("reason", ""), "mismatched result rejection reason missing", mismatch_attempts[0])
    write_target_mismatch_phone_home_artifact(artifact_dir, after_mismatch, alpha_id)
    phases.append({"name": "target-mismatch-result-upload", "status": "pass", "artifact": "after-mismatched-alpha-result.json"})

    proc = start_one_shot(cfg, "command-queue")
    malformed_result = connect_with_retry(
        queue_port,
        malformed_result_request("target-alpha", "Alpha Router"),
    )
    wait_proc(proc, "malformed alpha result")
    save_response(artifact_dir, "malformed-alpha-result", malformed_result)
    after_malformed = status(cfg, artifact_dir, "after-malformed-alpha-result")
    malformed_alpha = after_malformed["target_mailbox_records_by_command_id"][alpha_id]
    malformed_attempts = [
        rec for rec in after_malformed.get("target_phone_home_records") or []
        if rec.get("kind") == "result"
        and rec.get("target_id") == "target-alpha"
        and rec.get("failed") is True
        and "invalid command result JSON" in rec.get("reason", "")
    ]
    assert_condition(b"HTTP/1.1 400 Bad Request" in malformed_result, "malformed result upload should return HTTP 400")
    assert_condition(b"invalid command result JSON" in malformed_result, "malformed result upload should explain invalid JSON")
    assert_condition(malformed_alpha["status"] == "delivered", "malformed result mutated command status", malformed_alpha)
    assert_condition(malformed_alpha["delivered_without_result"] is True, "malformed result should leave command awaiting result", malformed_alpha)
    assert_condition(after_malformed["targets_by_id"]["target-alpha"]["mailbox_result_received_command_count"] == 0, "malformed result should not count as received")
    assert_condition(malformed_attempts, "malformed result phone-home rejection was not recorded")
    assert_condition(malformed_attempts[-1].get("http_status") == "400", "malformed result HTTP status missing", malformed_attempts[-1])
    write_malformed_result_upload_artifact(artifact_dir, after_malformed, alpha_id, malformed_result)
    phases.append({"name": "malformed-result-upload", "status": "pass", "artifact": "after-malformed-alpha-result.json"})

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
        after_dropped_result["summary"]["event_type_detail_status_counts"].get("command_queue_result_upload:rejected", 0) >= 2,
        "dropped result rejection event missing",
        after_dropped_result["summary"]["event_type_detail_status_counts"],
    )
    rejected_results = [
        rec for rec in after_dropped_result.get("target_phone_home_records") or []
        if rec.get("kind") == "result" and rec.get("target_id") == "target-alpha" and rec.get("failed") is True
    ]
    assert_condition(rejected_results, "dropped result phone-home rejection was not recorded")
    assert_condition(rejected_results[-1].get("reason"), "dropped result rejection reason missing", rejected_results[-1])
    assert_condition(rejected_results[-1].get("http_status") == "400", "dropped result HTTP status missing", rejected_results[-1])
    write_dropped_result_upload_artifact(artifact_dir, after_dropped_result, alpha_id, dropped_result)
    phases.append({"name": "dropped-result-upload", "status": "pass", "artifact": "after-dropped-alpha-result.json"})

    proc = start_one_shot(cfg, "command-queue")
    result_response = connect_with_retry(queue_port, result_request(alpha_id, "target-alpha", "Alpha Router"))
    wait_proc(proc, "alpha result")
    save_response(artifact_dir, "alpha-result", result_response)
    after_result = status(cfg, artifact_dir, "after-alpha-result")
    assert_condition(b"HTTP/1.1 200 OK" in result_response, "target result upload failed")
    assert_condition(after_result["targets_by_id"]["target-alpha"]["mailbox_result_received_command_count"] == 1, "alpha result was not recorded")
    assert_condition(after_result["targets_by_id"]["target-bravo"]["mailbox_pending_work_count"] == 1, "bravo offline mailbox was not preserved")
    alpha_record = (after_result.get("target_mailbox_records_by_command_id") or {}).get(alpha_id) or {}
    bravo_record = (after_result.get("target_mailbox_records_by_command_id") or {}).get(bravo_id) or {}
    assert_condition(alpha_record.get("target_id") == "target-alpha" and alpha_record.get("status") == "result-received", "alpha mailbox did not complete in isolation", alpha_record)
    assert_condition(bravo_record.get("target_id") == "target-bravo" and bravo_record.get("status") == "queued", "bravo mailbox leaked during alpha reconnect", bravo_record)
    assert_condition(bravo_record.get("waiting_for") == "target-poll" and bravo_record.get("pending_work") is True, "bravo mailbox pending reason missing after alpha reconnect", bravo_record)
    assert_condition(after_result["summary"]["target_phone_home_record_count"] >= 5, "phone-home attempts missing from status summary")
    assert_condition(after_result["summary"]["target_phone_home_status_counts"].get("result-received", 0) >= 1, "result phone-home success missing")
    write_command_result_artifact(artifact_dir, after_result, alpha_id, result_response)
    write_phone_home_artifact(artifact_dir, after_result)
    write_multi_target_isolation_artifact(artifact_dir, after_result, alpha_id, bravo_id)
    phases.append({"name": "result-upload", "status": "pass", "artifact": "after-alpha-result.json"})

    proc = start_one_shot(cfg, "probe")
    survey_get = connect_with_retry(survey_port, survey_get_request("target-alpha", "Alpha Router"))
    wait_proc(proc, "survey get")
    save_response(artifact_dir, "survey-get", survey_get)
    assert_condition(b"grit probe" in survey_get, "probe script was not served")

    proc = start_one_shot(cfg, "probe")
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
    partial_upload = ((partial_status.get("uploads_by_target_id") or {}).get("target-alpha") or [{}])[0]
    partial_text = run(str(SERVER), "--config", str(cfg), "--target-id", "target-alpha", "--status")
    assert_condition(partial_text.returncode == 0, "partial transfer status text failed", partial_text.stderr)
    assert_condition(
        "latest_file_transfer=upload status=truncated" in partial_text.stdout,
        "partial transfer missing from target status text",
        partial_text.stdout,
    )
    assert_condition(partial_upload.get("status") == "truncated", "partial upload record status missing", partial_upload)
    assert_condition(partial_upload.get("stored_exists") is True, "partial upload should retain forensic payload", partial_upload)
    assert_condition(partial_status["summary"]["upload_status_counts"].get("truncated") == 1, "partial upload status summary missing")
    assert_condition(partial_status["summary"]["upload_kind_status_counts"].get("evidence:truncated") == 1, "partial upload kind/status summary missing")
    assert_condition(partial_status["summary"]["upload_status_stored_exists_counts"].get("truncated:yes") == 1, "partial upload stored-exists summary missing")
    assert_condition(
        ((partial_status.get("targets_by_latest_file_transfer_status") or {}).get("truncated") or [{}])[0].get("target_id") == "target-alpha",
        "partial transfer target status index missing",
    )
    assert_condition(
        "uploads_by_status" in (((partial_status.get("api_collections") or {}).get("uploads") or {}).get("indexes") or []),
        "partial transfer uploads API index missing",
    )
    write_transfer_log_artifact(artifact_dir, partial_status, partial_response, partial_text.stdout)
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
    write_bridge_events_artifact(artifact_dir, bridge_status)
    phases.append({"name": "bridge-reconnect", "status": "pass", "artifact": "after-bridge-relay.json"})

    bad_bridge_dest_port = free_port()
    save_bad = run(
        str(SERVER), "--config", str(cfg),
        "--target-id", "target-alpha",
        "--save-bridge-profile", "flaky-bad-bridge",
        "--bridge-port", str(bridge_port),
        "--bridge-dest-host", "127.0.0.1",
        "--bridge-dest-port", str(bad_bridge_dest_port),
        "--bridge-profile-purpose", "flaky-link-interruption-test",
        "--bridge-profile-notes", "deterministic harness closed upstream",
    )
    if save_bad.returncode != 0:
        raise RuntimeError(f"bad bridge profile save failed: {save_bad.stderr}")
    proc = start_one_shot(cfg, "bridge", extra=["--bridge-profile", "flaky-bad-bridge", "--session-timeout", "3"])
    bridge_failure_response = bridge_send_once(bridge_port, b"hello")
    wait_proc(proc, "bridge interruption")
    (artifact_dir / "bridge-interruption-response.bin").write_bytes(bridge_failure_response)
    bridge_failure_status = status(cfg, artifact_dir, "after-bridge-interruption")
    bad_profile = (bridge_failure_status.get("bridge_profiles_by_name") or {}).get("flaky-bad-bridge") or {}
    failure_target = bridge_failure_status["targets_by_id"]["target-alpha"]
    failure_events = bridge_failure_status.get("events_by_event") or {}
    assert_condition(failure_target["latest_bridge_status"] == "error", "bridge interruption target status missing", failure_target)
    assert_condition(failure_target["latest_bridge_profile"] == "flaky-bad-bridge", "bridge interruption target profile missing", failure_target)
    assert_condition(failure_target.get("latest_bridge_failure_reason"), "bridge interruption failure reason missing", failure_target)
    assert_condition(bad_profile.get("has_last_failure") is True, "bridge profile failure flag missing", bad_profile)
    assert_condition(bad_profile.get("last_failure_reason") == failure_target.get("latest_bridge_failure_reason"), "bridge profile failure reason mismatch", bad_profile)
    assert_condition(bad_profile.get("last_failure_dest_port") == bad_bridge_dest_port, "bridge failure destination port missing", bad_profile)
    assert_condition(bridge_failure_status["summary"]["bridge_profile_has_last_failure_counts"].get("True") == 1, "bridge failure summary missing")
    assert_condition(bridge_failure_status["summary"]["target_latest_bridge_status_counts"].get("error") == 1, "bridge target error summary missing")
    assert_condition(((bridge_failure_status.get("bridge_profiles_by_has_last_failure") or {}).get("True") or [{}])[0].get("name") == "flaky-bad-bridge", "bridge failure profile index missing")
    assert_condition(((bridge_failure_status.get("targets_by_latest_bridge_status") or {}).get("error") or [{}])[0].get("target_id") == "target-alpha", "bridge failure target index missing")
    assert_condition(failure_events.get("bridge_error"), "bridge error event missing")
    write_bridge_interruption_artifact(artifact_dir, bridge_failure_status, "flaky-bad-bridge")
    write_bridge_events_artifact(artifact_dir, bridge_failure_status)
    phases.append({"name": "bridge-interruption", "status": "pass", "artifact": "after-bridge-interruption.json"})

    cfg_doc = json.loads(Path(cfg).read_text(encoding="utf-8"))
    targets_file = Path(str(cfg_doc["targets_file"]))
    targets_doc = json.loads(targets_file.read_text(encoding="utf-8"))
    old_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - (2 * 86400)))
    for target_id in ("target-alpha", "target-bravo"):
        rec = (targets_doc.get("targets") or {}).get(target_id)
        if not isinstance(rec, dict):
            continue
        rec["last_seen_at"] = old_seen
        rec["latest_activity_at"] = old_seen
    write_json(targets_file, targets_doc)
    return_offline_status = status(cfg, artifact_dir, "return-offline-status")
    return_offline_text = run(str(SERVER), "--config", str(cfg), "--status")
    assert_condition(return_offline_text.returncode == 0, "return-offline status text failed", return_offline_text.stderr)
    alpha_offline = return_offline_status["targets_by_id"]["target-alpha"]
    bravo_offline = return_offline_status["targets_by_id"]["target-bravo"]
    bravo_mailbox = (return_offline_status.get("target_mailbox_records_by_target_id") or {}).get("target-bravo") or []
    assert_condition(alpha_offline["connectivity_state"] == "offline", "alpha did not age back offline", alpha_offline)
    assert_condition(bravo_offline["connectivity_state"] == "offline", "bravo did not age back offline", bravo_offline)
    assert_condition(bravo_offline["mailbox_pending_work_count"] == 1, "bravo pending mailbox disappeared after return-offline", bravo_offline)
    assert_condition(bravo_mailbox and bravo_mailbox[0].get("pending_work") is True, "bravo pending mailbox record missing after return-offline", bravo_mailbox)
    assert_condition(bravo_mailbox[0].get("target_connectivity_state") == "offline", "bravo mailbox did not inherit offline state", bravo_mailbox[0])
    assert_condition(return_offline_status["summary"]["target_connectivity_state_counts"].get("offline", 0) >= 2, "return-offline summary missing offline targets")
    assert_condition("state=offline" in return_offline_text.stdout and "target-bravo" in return_offline_text.stdout, "return-offline status text missing offline target state", return_offline_text.stdout)
    write_return_offline_artifact(artifact_dir, return_offline_status, ["target-alpha", "target-bravo"], return_offline_text.stdout)
    phases.append({"name": "return-offline", "status": "pass", "artifact": "return-offline-status.json"})
    write_topology_artifact(artifact_dir, cfg, {
        "command_queue": queue_port,
        "survey_bootstrap": survey_port,
        "file_service": file_port,
        "bridge": bridge_port,
    }, phases)

    summary = {
        "schema": 1,
        "status": "pass",
        "artifact_dir": str(artifact_dir),
        "phases": phases,
        "qemu_lab_followup": {
            "status": "planned",
            "topology": "operator node plus one or more target nodes with controllable link interruption",
            "reuse_scenario": "offline workflow queue, offline command queue, short phone-home window, duplicate poll, result upload, survey, partial transfer, bridge relay",
        },
    }
    write_json(artifact_dir / "summary.json", summary)
    write_artifact_manifest(artifact_dir, phases)
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
        artifact_dir = Path(tempfile.mkdtemp(prefix="grit-flaky-network-"))
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
