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


def write_transfer_log_artifact(artifact_dir, doc, response):
    alpha = (doc.get("targets_by_id") or {}).get("target-alpha") or {}
    uploads = doc.get("uploads") or []
    write_json(artifact_dir / "transfer.log", {
        "schema": 1,
        "kind": "transfer-log-artifact",
        "http_status": http_status_line(response),
        "target_id": "target-alpha",
        "target_label": alpha.get("label", ""),
        "latest_file_transfer_status": alpha.get("latest_file_transfer_status", ""),
        "latest_file_transfer_operation": alpha.get("latest_file_transfer_operation", ""),
        "latest_file_transfer_at": alpha.get("latest_file_transfer_at", ""),
        "latest_file_transfer_id": alpha.get("latest_file_transfer_id", ""),
        "uploads": uploads,
    })


def write_bridge_events_artifact(artifact_dir, doc):
    records = [
        rec for rec in (doc.get("events") or [])
        if str(rec.get("service") or "") == "bridge" or str(rec.get("event") or "").startswith("bridge_")
    ]
    write_jsonl(artifact_dir / "bridge-events.jsonl", records)


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
    })

    run_target_workflow_action(cfg, "stage-file-fetch", extra=[
        "--target-workflow-local-file", str(source),
        "--target-workflow-request-name", "workflow-payload.txt",
    ])
    run_target_workflow_action(cfg, "queue-survey-bootstrap")
    run_target_workflow_action(cfg, "queue-staged-fetch", extra=[
        "--target-workflow-request-name", "workflow-payload.txt",
    ])
    doc = status(cfg, artifact_dir, "offline-workflow-status")
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
    mailbox_records = [
        rec for rec in (doc.get("target_mailbox_records") or [])
        if rec.get("target_id") == "target-workflow"
    ]
    mailbox_commands = "\n".join(rec.get("command") or "" for rec in mailbox_records)
    assert_condition(target["mailbox_pending_work_count"] == 2, "offline workflow mailbox count mismatch", target)
    assert_condition(doc["summary"]["target_mailbox_waiting_for_counts"].get("target-poll") == 2, "offline workflow waiting-for count mismatch")
    assert_condition(completed_by_action.get("stage-file-fetch", {}).get("result") == "staged-file-fetch", "stage-file-fetch event missing", completed_by_action)
    assert_condition(completed_by_action.get("queue-survey-bootstrap", {}).get("result") == "queued-survey-bootstrap", "queue-survey-bootstrap event missing", completed_by_action)
    assert_condition(completed_by_action.get("queue-staged-fetch", {}).get("result") == "queued-staged-fetch", "queue-staged-fetch event missing", completed_by_action)
    assert_condition("wget -O-" in mailbox_commands and "survey.sh" in mailbox_commands, "queued survey bootstrap command missing", mailbox_commands)
    assert_condition("busierbox fetch workflow-payload.txt" in mailbox_commands, "queued staged fetch command missing", mailbox_commands)
    write_offline_workflow_artifact(artifact_dir, doc)
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
        "command_queue_enable": "yes",
        "command_queue_tls": "no",
        "command_queue_port": str(queue_port),
        "command_queue_require_token": "no",
        "command_queue_allowed_commands": "busierbox-only",
        "command_queue_allow_arbitrary": "no",
    })

    queue_command(cfg, "target-failed", "Failed Router", "busierbox survey --json")
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
        "--queue-command", "busierbox survey --json",
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
        "command_queue_enable": "yes",
        "command_queue_tls": "no",
        "command_queue_port": str(queue_port),
        "command_queue_require_token": "no",
        "command_queue_allowed_commands": "busierbox-only",
        "command_queue_allow_arbitrary": "no",
    })

    queue_command(cfg, "target-restart-a", "Restart Router A", "busierbox survey --json")
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

    queue_command(cfg, "target-restart-b", "Restart Router B", "busierbox survey --json")
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

    phases.append(run_offline_workflow_queue_scenario(artifact_dir))
    phases.append(run_mailbox_lifecycle_scenario(artifact_dir))
    phases.append(run_restart_persistence_scenario(artifact_dir))

    queue_command(cfg, "target-alpha", "Alpha Router", "busierbox survey --json")
    queue_command(cfg, "target-bravo", "Bravo Router", "busierbox survey --json")
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
    rejected_results = [
        rec for rec in after_dropped_result.get("target_phone_home_records") or []
        if rec.get("kind") == "result" and rec.get("target_id") == "target-alpha" and rec.get("failed") is True
    ]
    assert_condition(rejected_results, "dropped result phone-home rejection was not recorded")
    assert_condition(rejected_results[0].get("reason"), "dropped result rejection reason missing", rejected_results[0])
    phases.append({"name": "dropped-result-upload", "status": "pass", "artifact": "after-dropped-alpha-result.json"})

    proc = start_one_shot(cfg, "command-queue")
    result_response = connect_with_retry(queue_port, result_request(alpha_id, "target-alpha", "Alpha Router"))
    wait_proc(proc, "alpha result")
    save_response(artifact_dir, "alpha-result", result_response)
    after_result = status(cfg, artifact_dir, "after-alpha-result")
    assert_condition(b"HTTP/1.1 200 OK" in result_response, "target result upload failed")
    assert_condition(after_result["targets_by_id"]["target-alpha"]["mailbox_result_received_command_count"] == 1, "alpha result was not recorded")
    assert_condition(after_result["targets_by_id"]["target-bravo"]["mailbox_pending_work_count"] == 1, "bravo offline mailbox was not preserved")
    assert_condition(after_result["summary"]["target_phone_home_record_count"] >= 5, "phone-home attempts missing from status summary")
    assert_condition(after_result["summary"]["target_phone_home_status_counts"].get("result-received", 0) >= 1, "result phone-home success missing")
    write_command_result_artifact(artifact_dir, after_result, alpha_id, result_response)
    write_phone_home_artifact(artifact_dir, after_result)
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
    write_transfer_log_artifact(artifact_dir, partial_status, partial_response)
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
