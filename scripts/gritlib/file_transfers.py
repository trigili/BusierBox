"""File-transfer record and index helpers for grit-console."""

import hashlib
import json
import time
import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import target_route_context
from gritlib.config_utils import yes
import gritlib.file_service_workflow_actions as file_service_workflow_actions
import gritlib.target_file_transfer_records as target_file_transfer_records_module
from gritlib.file_fetch_commands import (
    print_staged_fetch_target_options, render_fetch_command,
    render_staged_fetch_url, staged_fetch_output_name,
    staged_fetch_target_commands,
)
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import (
    latest_record_value, record_bool_counts, record_count_by_key, record_sum_by_key,
    records_by_bool, records_by_key,
)
from gritlib.session_state import read_json_file
from gritlib.shell_utils import shquote
from gritlib.target_records import (
    attach_target_identity, selected_target_context,
    target_identity_from_headers,
)


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


def print_recent_uploads(records, title="Recent uploads:", include_stored_exists=False):
    print(title)
    if records:
        for meta in records:
            sha = str(meta.get("sha256_prefix") or str(meta.get("sha256", ""))[:12])
            stored_exists = f" stored_exists={meta.get('stored_exists', False)}" if include_stored_exists else ""
            print(f"  {meta.get('filename', '')} kind={meta.get('upload_kind', 'file')} size={meta.get('size', '')} sha256={sha} status={meta.get('transfer_status', meta.get('status', ''))}{stored_exists}")
            print(f"    source: {meta.get('source_path', '')}")
            print(f"    remote: {meta.get('remote_addr', '')} at {meta.get('timestamp', '')}")
            if meta.get("target_id"):
                print(f"    target: {meta.get('target_id', '')} label={meta.get('target_label', '')} confidence={meta.get('target_identity_confidence', '')}")
            print(f"    stored: {meta.get('stored_path', '')}")
            print(f"    metadata: {meta.get('metadata_path', meta.get('_metadata_path', ''))}")
            print(f"    session: {meta.get('session_id', '')} {meta.get('session_path', '')}")
            if not include_stored_exists:
                print(f"    stored_exists: {meta.get('stored_exists', False)}")
    else:
        print("  none")


def print_recent_fetches(records, include_source_exists=False):
    print("Recent fetches:")
    if records:
        for meta in records:
            sha = str(meta.get("sha256_prefix") or str(meta.get("sha256", ""))[:12])
            source_exists = f" source_exists={meta.get('source_exists', False)}" if include_source_exists else ""
            print(f"  {meta.get('request_name', '')} size={meta.get('size', '')} sha256={sha} status={meta.get('status', '')} http={meta.get('http_status', '')}{source_exists}")
            print(f"    source: {meta.get('source_path', '')}")
            print(f"    remote: {meta.get('remote_addr', '')} at {meta.get('timestamp', '')}")
            if meta.get("target_id"):
                print(f"    target: {meta.get('target_id', '')} label={meta.get('target_label', '')} confidence={meta.get('target_identity_confidence', '')}")
            print(f"    session: {meta.get('session_id', '')} {meta.get('session_path', '')}")
            if meta.get("event_log"):
                print(f"    event_log: {meta.get('event_log', '')}")
    else:
        print("  none")


def render_file_service_command(parts, cfg, host=None):
    host = operator_advertised_host(cfg, host=host)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=host,
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    target_ctx = selected_target_context(cfg)
    cmd = [
        "./grit",
        *parts,
        "--host",
        str(route.get("host") or host),
        "--port",
        str(route.get("port") or cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204)),
    ]
    if not yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes")):
        cmd.append("--no-tls")
    if target_ctx.get("target_id"):
        cmd.extend(["--target-id", target_ctx.get("target_id", "")])
    if target_ctx.get("target_label"):
        cmd.extend(["--target-label", target_ctx.get("target_label", "")])
    for alias in target_ctx.get("target_aliases") or []:
        cmd.extend(["--target-alias", alias])
    return " ".join(shquote(part) for part in cmd)


def read_http_upload(conn, files_dir, addr):
    method, target, headers, body = _read_http_upload_request(conn)
    if method not in {"PUT", "POST"}:
        return _upload_rejection_metadata(
            headers,
            addr,
            method,
            target,
            "receive-only file service accepts only PUT or POST",
        ), 405
    if "content-length" not in headers:
        return _upload_rejection_metadata(
            headers,
            addr,
            method,
            target,
            "missing Content-Length",
        ), 411
    try:
        expected = int(headers["content-length"])
    except ValueError:
        return _upload_rejection_metadata(
            headers,
            addr,
            method,
            target,
            "invalid Content-Length",
        ), 400

    source_path = (
        headers.get("x-grit-source-path") or
        headers.get("x-grittykit-source-path") or
        urllib.parse.urlparse(target).path
    )
    upload_kind = (
        headers.get("x-grit-upload-kind") or
        headers.get("x-grittykit-upload-kind") or
        "file"
    )
    out_path = _unique_upload_path(files_dir, safe_upload_name(source_path))
    written, digest = _write_upload_payload(conn, out_path, body, expected)
    status = "ok" if written == expected else "truncated"
    metadata = _upload_success_metadata(
        headers,
        addr,
        method,
        source_path,
        upload_kind,
        out_path,
        written,
        expected,
        digest,
        status,
    )
    meta_path = files_dir / f"{out_path.name}.metadata.json"
    metadata["metadata_path"] = str(meta_path)
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata, 200 if status == "ok" else 400


def _read_http_upload_request(conn):
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
    return method, target, headers, body


def _upload_rejection_metadata(headers, addr, method, target, reason):
    return attach_target_identity({
        "operation": "upload",
        "status": "rejected",
        "reason": reason,
        "method": method,
        "source_path": target,
        "remote_addr": f"{addr[0]}:{addr[1]}",
    }, headers)


def _unique_upload_path(files_dir, out_name):
    out_path = files_dir / out_name
    if out_path.exists():
        stem = out_path.stem
        suffix = out_path.suffix
        out_path = files_dir / f"{stem}-{int(time.time())}{suffix}"
    return out_path


def _write_upload_payload(conn, out_path, body, expected):
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
    return written, h.hexdigest()


def _upload_success_metadata(
    headers,
    addr,
    method,
    source_path,
    upload_kind,
    out_path,
    written,
    expected,
    digest,
    status,
):
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
        "sha256": digest,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "remote_addr": f"{addr[0]}:{addr[1]}",
        "uid": headers.get("x-grit-uid", ""),
        "gid": headers.get("x-grit-gid", ""),
        "mode": headers.get("x-grit-mode", ""),
        "transfer_status": status,
    }
    metadata.update(target_identity_from_headers(headers))
    return metadata


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


def file_transfer_status_context(uploads=None, fetches=None):
    return {
        "upload_indexes": upload_record_indexes(uploads),
        "fetch_indexes": fetch_record_indexes(fetches),
    }


def _index_counts(index):
    return {key: len(value) for key, value in (index or {}).items()}


def upload_record_summary(records, target_attribution=None):
    records = records or []
    target_attribution = target_attribution or {}
    (
        _uploads_by_filename,
        _uploads_by_kind,
        _uploads_by_sha256,
        _uploads_by_target_id,
        _uploads_by_source_path,
        _uploads_by_stored_path,
        _uploads_by_stored_exists,
        uploads_by_metadata_exists,
        uploads_by_event_log_exists,
        _uploads_by_remote_addr,
        _uploads_by_status,
        uploads_by_kind_status,
        uploads_by_filename_status,
        uploads_by_status_stored_exists,
        uploads_by_status_remote_addr,
    ) = upload_record_indexes(records)
    stored_exists_count, stored_missing_count = record_bool_counts(records, "stored_exists")
    return {
        "upload_count": len(records),
        "upload_total_size": record_sum_by_key(records, "size"),
        "upload_stored_exists_count": stored_exists_count,
        "upload_stored_missing_count": stored_missing_count,
        "upload_metadata_exists_counts": _index_counts(uploads_by_metadata_exists),
        "upload_event_log_exists_counts": _index_counts(uploads_by_event_log_exists),
        "upload_kind_counts": record_count_by_key(records, "upload_kind"),
        "upload_status_counts": record_count_by_key(records, "status"),
        "upload_remote_counts": record_count_by_key(records, "remote_addr"),
        "upload_target_counts": record_count_by_key(records, "target_id"),
        "upload_with_target_count": target_attribution.get("upload_with_target_count", 0),
        "upload_without_target_count": target_attribution.get("upload_without_target_count", 0),
        "upload_kind_status_counts": _index_counts(uploads_by_kind_status),
        "upload_filename_status_counts": _index_counts(uploads_by_filename_status),
        "upload_status_stored_exists_counts": _index_counts(uploads_by_status_stored_exists),
        "upload_status_remote_counts": _index_counts(uploads_by_status_remote_addr),
        "latest_upload_at": latest_record_value(records, ("timestamp", "updated_at")),
    }


def fetch_record_summary(records, target_attribution=None):
    records = records or []
    target_attribution = target_attribution or {}
    (
        _fetches_by_request,
        _fetches_by_sha256,
        _fetches_by_target_id,
        _fetches_by_source_path,
        _fetches_by_source_exists,
        fetches_by_metadata_exists,
        fetches_by_event_log_exists,
        _fetches_by_status,
        _fetches_by_http_status,
        _fetches_by_remote_addr,
        fetches_by_request_status,
        fetches_by_status_source_exists,
        fetches_by_status_remote_addr,
        fetches_by_http_status_remote_addr,
    ) = fetch_record_indexes(records)
    source_exists_count, source_missing_count = record_bool_counts(records, "source_exists")
    return {
        "fetch_count": len(records),
        "fetch_total_size": record_sum_by_key(records, "size"),
        "fetch_source_exists_count": source_exists_count,
        "fetch_source_missing_count": source_missing_count,
        "fetch_metadata_exists_counts": _index_counts(fetches_by_metadata_exists),
        "fetch_event_log_exists_counts": _index_counts(fetches_by_event_log_exists),
        "fetch_status_counts": record_count_by_key(records, "status"),
        "fetch_http_status_counts": record_count_by_key(records, "http_status"),
        "fetch_remote_counts": record_count_by_key(records, "remote_addr"),
        "fetch_target_counts": record_count_by_key(records, "target_id"),
        "fetch_with_target_count": target_attribution.get("fetch_with_target_count", 0),
        "fetch_without_target_count": target_attribution.get("fetch_without_target_count", 0),
        "fetch_request_status_counts": _index_counts(fetches_by_request_status),
        "fetch_status_source_exists_counts": _index_counts(fetches_by_status_source_exists),
        "fetch_status_remote_counts": _index_counts(fetches_by_status_remote_addr),
        "fetch_http_status_remote_counts": _index_counts(fetches_by_http_status_remote_addr),
        "latest_fetch_at": latest_record_value(records, ("timestamp", "updated_at")),
    }


def target_file_transfer_records_from_sources(staged_records, uploads, fetches):
    return target_file_transfer_records_module.target_file_transfer_records_from_sources(
        staged_records, uploads, fetches
    )


def target_file_transfer_record_indexes(records):
    return target_file_transfer_records_module.target_file_transfer_record_indexes(records)


def target_file_transfer_status_context(staged_records=None, uploads=None, fetches=None):
    return target_file_transfer_records_module.target_file_transfer_status_context(
        staged_records, uploads, fetches
    )


def target_file_transfer_record_summary(records):
    return target_file_transfer_records_module.target_file_transfer_record_summary(records)


def file_service_workflow_action_record(
    action_id,
    category,
    label,
    command,
    workflow,
    run_command,
    target_filter_id,
    route,
    service_row,
    listen_port,
    fallback_bind_address,
    staged_count,
    upload_count,
    fetch_count,
    transfer_count,
    fleet_metrics,
    action_state,
    action_reason,
    available=True,
    requires_input=False,
    requires_confirmation=False,
    queues_offline_work=False,
    target_phone_home_required=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    return file_service_workflow_actions.file_service_workflow_action_record(
        action_id, category, label, command, workflow, run_command,
        target_filter_id, route, service_row, listen_port, fallback_bind_address,
        staged_count, upload_count, fetch_count, transfer_count, fleet_metrics,
        action_state, action_reason, available=available,
        requires_input=requires_input,
        requires_confirmation=requires_confirmation,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
        can_run_from_curses_enter=can_run_from_curses_enter,
        curses_enter_action=curses_enter_action,
    )


def file_service_workflow_action_records(
    cfg,
    service_row,
    staged_records=None,
    uploads=None,
    fetches=None,
    transfer_records=None,
    targets=None,
):
    return file_service_workflow_actions.file_service_workflow_action_records(
        cfg,
        service_row,
        staged_records=staged_records,
        uploads=uploads,
        fetches=fetches,
        transfer_records=transfer_records,
        targets=targets,
        render_file_service_command_func=render_file_service_command,
    )


def file_service_workflow_action_indexes(records):
    return file_service_workflow_actions.file_service_workflow_action_indexes(records)


def file_service_workflow_status_context(
    cfg,
    service_row,
    staged_records=None,
    uploads=None,
    fetches=None,
    transfer_records=None,
    targets=None,
):
    return file_service_workflow_actions.file_service_workflow_status_context(
        cfg,
        service_row,
        staged_records=staged_records,
        uploads=uploads,
        fetches=fetches,
        transfer_records=transfer_records,
        targets=targets,
        render_file_service_command_func=render_file_service_command,
    )


def file_service_workflow_action_summary(records):
    return file_service_workflow_actions.file_service_workflow_action_summary(records)


def file_service_workflow_status_summary(records):
    return file_service_workflow_actions.file_service_workflow_status_summary(records)
