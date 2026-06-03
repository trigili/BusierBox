"""File-transfer record and index helpers for grit-console."""

import hashlib
import json
import time
import urllib.parse
from pathlib import Path

from gritlib.record_utils import record_count_by_key, records_by_bool, records_by_key
from gritlib.session_state import read_json_file
from gritlib.target_records import attach_target_identity, target_identity_from_headers


def safe_upload_name(source_path):
    parsed = urllib.parse.urlparse(source_path or "")
    raw = urllib.parse.unquote(parsed.path or source_path or "upload.bin")
    name = Path(raw).name
    return name or "upload.bin"


def recent_upload_metadata(cfg, limit=8):
    root = Path(str(cfg.get("session_root", "local/sessions")))
    if not root.is_dir():
        return []
    metas = sorted(root.glob("*/files/*.metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for path in metas[:limit]:
        data = read_json_file(path, {})
        if isinstance(data, dict):
            stored_path = data.get("stored_path", "")
            data["metadata_path"] = str(path)
            data["_metadata_path"] = str(path)
            data["metadata_exists"] = path.is_file()
            data["session_path"] = str(path.parent.parent)
            data["session_id"] = path.parent.parent.name
            event_log = path.parent.parent / "events.jsonl"
            data["event_log"] = str(event_log) if event_log.is_file() else ""
            data["event_log_exists"] = event_log.is_file()
            data["stored_exists"] = Path(str(stored_path)).is_file() if stored_path else False
            data["sha256_prefix"] = str(data.get("sha256", ""))[:12]
            data["status"] = data.get("transfer_status", data.get("status", ""))
            data["upload_kind"] = str(data.get("upload_kind") or "file")
            out.append(data)
    return out


def recent_fetch_metadata(cfg, limit=8):
    root = Path(str(cfg.get("session_root", "local/sessions")))
    if not root.is_dir():
        return []
    rows = []
    for session_json in root.glob("*/session.json"):
        session_doc = read_json_file(session_json, {})
        if not isinstance(session_doc, dict):
            continue
        session_path = session_json.parent
        session_id_value = session_doc.get("session_id") or session_path.name
        for item in session_doc.get("fetches") or []:
            if not isinstance(item, dict):
                continue
            rec = dict(item)
            rec["session_id"] = session_id_value
            rec["session_path"] = str(session_path)
            rec["metadata_path"] = str(session_json)
            rec["metadata_exists"] = session_json.is_file()
            rec["event_log"] = str(session_path / "events.jsonl")
            rec["event_log_exists"] = (session_path / "events.jsonl").is_file()
            rec["sha256_prefix"] = str(rec.get("sha256", ""))[:12]
            rec["source_exists"] = Path(str(rec.get("source_path", ""))).is_file() if rec.get("source_path") else False
            rows.append(rec)
    rows.sort(key=lambda item: item.get("timestamp") or item.get("updated_at") or "", reverse=True)
    return rows[:limit]


def read_http_upload(conn, files_dir, addr):
    deadline = time.monotonic() + 30
    raw = bytearray()
    while b"\r\n\r\n" not in raw:
        if time.monotonic() >= deadline:
            raise RuntimeError("timeout reading upload headers")
        chunk = conn.recv(65536)
        if not chunk:
            raise RuntimeError("connection closed before upload headers")
        raw.extend(chunk)
    header_raw, body = bytes(raw).split(b"\r\n\r\n", 1)
    header_text = header_raw.decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    request = lines[0].split()
    if len(request) < 3:
        raise RuntimeError("malformed HTTP request")
    method, target, _version = request[:3]
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    if method not in {"PUT", "POST"}:
        return attach_target_identity({
            "operation": "upload",
            "status": "rejected",
            "reason": "receive-only file service accepts only PUT or POST",
            "method": method,
            "source_path": target,
            "remote_addr": f"{addr[0]}:{addr[1]}",
        }, headers), 405
    if "content-length" not in headers:
        return attach_target_identity({
            "operation": "upload",
            "status": "rejected",
            "reason": "missing Content-Length",
            "method": method,
            "source_path": target,
            "remote_addr": f"{addr[0]}:{addr[1]}",
        }, headers), 411
    try:
        expected = int(headers["content-length"])
    except ValueError:
        return attach_target_identity({
            "operation": "upload",
            "status": "rejected",
            "reason": "invalid Content-Length",
            "method": method,
            "source_path": target,
            "remote_addr": f"{addr[0]}:{addr[1]}",
        }, headers), 400
    source_path = headers.get("x-grit-source-path") or headers.get("x-grittykit-source-path") or urllib.parse.urlparse(target).path
    upload_kind = headers.get("x-grit-upload-kind") or headers.get("x-grittykit-upload-kind") or "file"
    out_name = safe_upload_name(source_path)
    out_path = files_dir / out_name
    if out_path.exists():
        stem = out_path.stem
        suffix = out_path.suffix
        out_path = files_dir / f"{stem}-{int(time.time())}{suffix}"
    h = hashlib.sha256()
    written = 0
    with out_path.open("wb") as fh:
        if body:
            piece = body[:expected]
            fh.write(piece)
            h.update(piece)
            written += len(piece)
        while written < expected:
            chunk = conn.recv(min(65536, expected - written))
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            written += len(chunk)
    status = "ok" if written == expected else "truncated"
    metadata = {
        "schema": 1,
        "operation": "upload",
        "status": status,
        "method": method,
        "upload_kind": upload_kind,
        "source_path": urllib.parse.unquote(source_path),
        "stored_path": str(out_path),
        "filename": out_path.name,
        "size": written,
        "expected_size": expected,
        "sha256": h.hexdigest(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "remote_addr": f"{addr[0]}:{addr[1]}",
        "uid": headers.get("x-grit-uid", ""),
        "gid": headers.get("x-grit-gid", ""),
        "mode": headers.get("x-grit-mode", ""),
        "transfer_status": status,
    }
    metadata.update(target_identity_from_headers(headers))
    meta_path = files_dir / f"{out_path.name}.metadata.json"
    metadata["metadata_path"] = str(meta_path)
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata, 200 if status == "ok" else 400


def read_http_headers(conn):
    deadline = time.monotonic() + 30
    raw = bytearray()
    while b"\r\n\r\n" not in raw:
        if time.monotonic() >= deadline:
            raise RuntimeError("timeout reading HTTP headers")
        chunk = conn.recv(65536)
        if not chunk:
            raise RuntimeError("connection closed before HTTP headers")
        raw.extend(chunk)
    header_raw, body = bytes(raw).split(b"\r\n\r\n", 1)
    header_text = header_raw.decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    request = lines[0].split()
    if len(request) < 3:
        raise RuntimeError("malformed HTTP request")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return request[0], request[1], request[2], headers, body


def read_http_body(conn, headers, initial_body):
    if "content-length" not in headers:
        raise ValueError("missing Content-Length")
    try:
        expected = int(headers["content-length"])
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if expected < 0:
        raise ValueError("invalid Content-Length")
    body = bytearray(initial_body[:expected])
    while len(body) < expected:
        chunk = conn.recv(min(65536, expected - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    if len(body) != expected:
        raise ValueError("truncated request body")
    return bytes(body)


def send_http_response(conn, status_code, body=b"", content_type="application/octet-stream", headers=None):
    reason = {
        204: "No Content",
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        411: "Length Required",
        500: "Internal Server Error",
    }.get(status_code, "OK")
    header_lines = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    for key, value in (headers or {}).items():
        header_lines.append(f"{key}: {value}")
    conn.sendall(("\r\n".join(header_lines) + "\r\n\r\n").encode("ascii") + body)


def stream_fetch_response(conn, src, status_code=200, content_type="application/octet-stream", headers=None, head_only=False):
    src = Path(src)
    reason = {200: "OK"}.get(status_code, "OK")
    header_lines = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {src.stat().st_size}",
        "Connection: close",
    ]
    for key, value in (headers or {}).items():
        header_lines.append(f"{key}: {value}")
    conn.sendall(("\r\n".join(header_lines) + "\r\n\r\n").encode("ascii"))
    if head_only:
        return
    with src.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            conn.sendall(chunk)


def send_json_response(conn, status_code, payload):
    reason = {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        405: "Method Not Allowed",
        411: "Length Required",
        500: "Internal Server Error",
    }.get(status_code, "OK")
    body = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
    headers = (
        f"HTTP/1.1 {status_code} {reason}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    conn.sendall(headers + body)


def upload_record_indexes(records):
    by_filename = {}
    by_kind = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_stored_path = {}
    by_stored_exists = records_by_bool(records, "stored_exists")
    by_metadata_exists = records_by_bool(records, "metadata_exists")
    by_event_log_exists = records_by_bool(records, "event_log_exists")
    by_remote_addr = {}
    by_status = {}
    by_kind_status = {}
    by_filename_status = {}
    by_status_stored_exists = {}
    by_status_remote_addr = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        filename = str(rec.get("filename") or "")
        kind = str(rec.get("upload_kind") or "file")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        stored_path = str(rec.get("stored_path") or "")
        remote_addr = str(rec.get("remote_addr") or "")
        status = str(rec.get("status") or "")
        if filename:
            by_filename.setdefault(filename, []).append(rec)
        if kind:
            by_kind.setdefault(kind, []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path.setdefault(source_path, []).append(rec)
        if stored_path:
            by_stored_path[stored_path] = rec
        if remote_addr:
            by_remote_addr.setdefault(remote_addr, []).append(rec)
        if status:
            by_status.setdefault(status, []).append(rec)
        if kind and status:
            by_kind_status.setdefault(f"{kind}:{status}", []).append(rec)
        if filename and status:
            by_filename_status.setdefault(f"{filename}:{status}", []).append(rec)
        if status:
            stored_exists = "yes" if rec.get("stored_exists") is True else "no"
            by_status_stored_exists.setdefault(f"{status}:{stored_exists}", []).append(rec)
        if status and remote_addr:
            by_status_remote_addr.setdefault(f"{status}:{remote_addr}", []).append(rec)
    return (
        by_filename,
        by_kind,
        by_sha256,
        by_target_id,
        by_source_path,
        by_stored_path,
        by_stored_exists,
        by_metadata_exists,
        by_event_log_exists,
        by_remote_addr,
        by_status,
        by_kind_status,
        by_filename_status,
        by_status_stored_exists,
        by_status_remote_addr,
    )


def fetch_record_indexes(records):
    by_request = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_source_exists = records_by_bool(records, "source_exists")
    by_metadata_exists = records_by_bool(records, "metadata_exists")
    by_event_log_exists = records_by_bool(records, "event_log_exists")
    by_status = {}
    by_http_status = {}
    by_remote_addr = {}
    by_request_status = {}
    by_status_source_exists = {}
    by_status_remote_addr = {}
    by_http_status_remote_addr = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or "")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        status = str(rec.get("status") or "")
        http_status = rec.get("http_status")
        remote_addr = str(rec.get("remote_addr") or "")
        if request_name:
            by_request.setdefault(request_name, []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path.setdefault(source_path, []).append(rec)
        if status:
            by_status.setdefault(status, []).append(rec)
        if http_status not in (None, ""):
            by_http_status.setdefault(str(http_status), []).append(rec)
        if remote_addr:
            by_remote_addr.setdefault(remote_addr, []).append(rec)
        if request_name and status:
            by_request_status.setdefault(f"{request_name}:{status}", []).append(rec)
        if status:
            source_exists = "yes" if rec.get("source_exists") is True else "no"
            by_status_source_exists.setdefault(f"{status}:{source_exists}", []).append(rec)
        if status and remote_addr:
            by_status_remote_addr.setdefault(f"{status}:{remote_addr}", []).append(rec)
        if http_status not in (None, "") and remote_addr:
            by_http_status_remote_addr.setdefault(f"{http_status}:{remote_addr}", []).append(rec)
    return (
        by_request,
        by_sha256,
        by_target_id,
        by_source_path,
        by_source_exists,
        by_metadata_exists,
        by_event_log_exists,
        by_status,
        by_http_status,
        by_remote_addr,
        by_request_status,
        by_status_source_exists,
        by_status_remote_addr,
        by_http_status_remote_addr,
    )


def target_file_transfer_records_from_sources(staged_records, uploads, fetches):
    records = []
    for rec in staged_records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or rec.get("name") or "")
        timestamp = str(rec.get("staged_at") or rec.get("created_at") or rec.get("updated_at") or "")
        source_path = str(rec.get("source_path") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"staged:{request_name}" if request_name else f"staged:{len(records)}",
            "operation": "staged-fetch",
            "source_collection": "staged_records",
            "status": "available" if rec.get("source_exists") is True else "source-missing",
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or rec.get("staged_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": request_name,
            "name": str(rec.get("name") or request_name),
            "filename": Path(source_path or request_name).name if (source_path or request_name) else "",
            "stage_kind": str(rec.get("stage_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": source_path,
            "stored_path": "",
            "metadata_path": "",
            "session_id": "",
            "session_path": "",
            "remote_addr": "",
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": rec.get("source_exists") is True,
            "stored_exists": False,
            "fetch_command": str(rec.get("fetch_command") or ""),
            "fetch_command_force": str(rec.get("fetch_command_force") or ""),
        })
    for rec in uploads or []:
        if not isinstance(rec, dict):
            continue
        metadata_path = str(rec.get("metadata_path") or rec.get("_metadata_path") or "")
        timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"upload:{metadata_path}" if metadata_path else f"upload:{len(records)}",
            "operation": "upload",
            "source_collection": "uploads",
            "status": str(rec.get("status") or rec.get("transfer_status") or ""),
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": str(rec.get("request_name") or ""),
            "name": str(rec.get("filename") or ""),
            "filename": str(rec.get("filename") or ""),
            "stage_kind": str(rec.get("upload_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": str(rec.get("source_path") or ""),
            "stored_path": str(rec.get("stored_path") or ""),
            "metadata_path": metadata_path,
            "session_id": str(rec.get("session_id") or ""),
            "session_path": str(rec.get("session_path") or ""),
            "remote_addr": str(rec.get("remote_addr") or ""),
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": False,
            "stored_exists": rec.get("stored_exists") is True,
            "fetch_command": "",
            "fetch_command_force": "",
        })
    for rec in fetches or []:
        if not isinstance(rec, dict):
            continue
        metadata_path = str(rec.get("metadata_path") or "")
        request_name = str(rec.get("request_name") or "")
        timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
        source_path = str(rec.get("source_path") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"fetch:{metadata_path}:{request_name}:{timestamp}" if metadata_path or request_name or timestamp else f"fetch:{len(records)}",
            "operation": "fetch",
            "source_collection": "fetches",
            "status": str(rec.get("status") or ""),
            "http_status": rec.get("http_status", ""),
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": request_name,
            "name": request_name,
            "filename": Path(source_path or request_name).name if (source_path or request_name) else "",
            "stage_kind": str(rec.get("stage_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": source_path,
            "stored_path": "",
            "metadata_path": metadata_path,
            "session_id": str(rec.get("session_id") or ""),
            "session_path": str(rec.get("session_path") or ""),
            "remote_addr": str(rec.get("remote_addr") or ""),
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": rec.get("source_exists") is True,
            "stored_exists": False,
            "fetch_command": "",
            "fetch_command_force": "",
        })
    records.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("id") or "")), reverse=True)
    return records


def target_file_transfer_record_indexes(records):
    return {
        "target_file_transfer_records_by_id": {rec.get("id", ""): rec for rec in records or [] if isinstance(rec, dict) and rec.get("id")},
        "target_file_transfer_records_by_target_id": records_by_key(records, "target_id"),
        "target_file_transfer_records_by_target_label": records_by_key(records, "target_label"),
        "target_file_transfer_records_by_operation": records_by_key(records, "operation"),
        "target_file_transfer_records_by_source_collection": records_by_key(records, "source_collection"),
        "target_file_transfer_records_by_status": records_by_key(records, "status"),
        "target_file_transfer_records_by_route_kind": records_by_key(records, "route_kind"),
        "target_file_transfer_records_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_file_transfer_records_by_request_name": records_by_key(records, "request_name"),
        "target_file_transfer_records_by_filename": records_by_key(records, "filename"),
        "target_file_transfer_records_by_sha256": records_by_key(records, "sha256"),
        "target_file_transfer_records_by_session_id": records_by_key(records, "session_id"),
    }


def file_service_workflow_action_indexes(records):
    return {
        "file_service_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "file_service_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "file_service_workflow_actions_by_service": records_by_key(records, "service"),
        "file_service_workflow_actions_by_category": records_by_key(records, "category"),
        "file_service_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "file_service_workflow_actions_by_actual": records_by_key(records, "actual"),
        "file_service_workflow_actions_by_configured": records_by_key(records, "configured"),
        "file_service_workflow_actions_by_target_filter_active": records_by_key(records, "target_filter_active"),
        "file_service_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "file_service_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "file_service_workflow_actions_by_requires_bridge": records_by_key(records, "requires_bridge"),
        "file_service_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "file_service_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "file_service_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "file_service_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "file_service_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "file_service_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "file_service_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "file_service_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "file_service_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "file_service_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "file_service_workflow_actions_by_available": records_by_key(records, "available"),
        "file_service_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "file_service_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "file_service_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "file_service_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "file_service_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "file_service_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "file_service_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def file_service_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "service_counts": record_count_by_key(records, "service"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "configured_counts": record_count_by_key(records, "configured"),
        "target_filter_active_counts": record_count_by_key(records, "target_filter_active"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "requires_bridge_counts": record_count_by_key(records, "requires_bridge"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "available_counts": record_count_by_key(records, "available"),
        "requires_input_counts": record_count_by_key(records, "requires_input"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "queues_offline_work_counts": record_count_by_key(records, "queues_offline_work"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }
