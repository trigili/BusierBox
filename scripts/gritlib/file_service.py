"""File-service listener for grit-console."""

import json
import socket
import ssl
import sys
import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import attach_target_route_fields, target_route_context
from gritlib.config_utils import yes
from gritlib.crypto import generate_tls_cert
from gritlib.event_log import append_event
from gritlib.file_transfers import (
    read_http_headers,
    read_http_upload,
    send_http_response,
    send_json_response,
    stream_fetch_response,
)
from gritlib.operator_network import operator_advertised_host, print_candidates
from gritlib.service_runtime import (
    SESSION_MANAGER,
    SHUTDOWN,
    bind_listen_socket,
    current_stop_reason,
    record_shutdown_event,
    unregister_socket,
)
from gritlib.session_state import mark_service_stopped, update_server_state, utc_now
from gritlib.staged_files import load_staged, reject_traversal_request_name, staged_file_path
from gritlib.target_records import (
    attach_target_identity,
    record_target_activity,
    target_identity_from_headers,
)


def handle_staged_fetch(cfg, conn, method, target, headers, addr):
    request_headers = dict(headers or {})
    if method not in {"GET", "HEAD"}:
        payload = {"status": "rejected", "reason": "staged fetch accepts only GET or HEAD"}
        send_http_response(conn, 405, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        return attach_target_identity({"operation": "fetch", "status": "rejected", "http_status": 405, "method": method, "remote_addr": f"{addr[0]}:{addr[1]}"}, request_headers)
    parsed = urllib.parse.urlparse(target)
    if parsed.path not in {"/fetch", "/fetch/"}:
        payload = {"status": "rejected", "reason": "unknown fetch endpoint"}
        send_http_response(conn, 404, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        return attach_target_identity({"operation": "fetch", "status": "rejected", "http_status": 404, "reason": "unknown endpoint", "method": method, "remote_addr": f"{addr[0]}:{addr[1]}"}, request_headers)
    query = urllib.parse.parse_qs(parsed.query)
    name = query.get("name", [""])[0]
    try:
        name = reject_traversal_request_name(name)
    except ValueError as exc:
        payload = {"status": "rejected", "reason": str(exc)}
        send_http_response(conn, 400, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        return attach_target_identity({"operation": "fetch", "status": "rejected", "http_status": 400, "reason": str(exc), "method": method, "remote_addr": f"{addr[0]}:{addr[1]}"}, request_headers)
    staged = load_staged(cfg).get("staged", {})
    rec = staged.get(name)
    if not rec:
        payload = {"status": "missing", "reason": "no staged file for request", "request_name": name}
        send_http_response(conn, 404, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        return attach_target_identity({"operation": "fetch", "status": "missing", "http_status": 404, "method": method, "request_name": name, "remote_addr": f"{addr[0]}:{addr[1]}"}, request_headers)
    target_identity = target_identity_from_headers(request_headers)
    staged_target_id = str(rec.get("target_id") or "").strip()
    request_target_id = str(target_identity.get("target_id") or "").strip()
    if staged_target_id and request_target_id != staged_target_id:
        reason = "target id required" if not request_target_id else "target mismatch"
        payload = {
            "status": "rejected",
            "reason": reason,
            "request_name": name,
            "expected_target_id": staged_target_id,
            "target_id": request_target_id,
        }
        send_http_response(conn, 403, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        details = attach_target_identity({
            "operation": "fetch",
            "status": "rejected",
            "http_status": 403,
            "reason": reason,
            "method": method,
            "request_name": name,
            "expected_target_id": staged_target_id,
            "remote_addr": f"{addr[0]}:{addr[1]}",
        }, request_headers)
        details.setdefault("target_id", request_target_id)
        return details
    src = Path(rec.get("source_path", ""))
    if not src.is_file():
        payload = {"status": "missing", "reason": "staged source file is no longer present", "request_name": name}
        send_http_response(conn, 404, json.dumps(payload).encode("utf-8") + b"\n", "application/json")
        return attach_target_identity({"operation": "fetch", "status": "missing-source", "http_status": 404, "method": method, "request_name": name, "remote_addr": f"{addr[0]}:{addr[1]}"}, request_headers)
    response_headers = {
        "X-griTTYkit-Request-Name": urllib.parse.quote(name, safe="/._-"),
        "X-griTTYkit-Sha256": rec.get("sha256", ""),
        "X-griTTYkit-Source-Size": str(src.stat().st_size),
        "Content-Disposition": f"attachment; filename={urllib.parse.quote(Path(name).name or src.name)}",
    }
    stream_fetch_response(conn, src, 200, "application/octet-stream", headers=response_headers, head_only=(method == "HEAD"))
    route = rec.get("target_route") if isinstance(rec.get("target_route"), dict) else None
    if not route:
        route = target_route_context(cfg, "file-service", direct_host=operator_advertised_host(cfg), direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204))
    return attach_target_identity(attach_target_route_fields({
        "operation": "fetch",
        "status": "served",
        "http_status": 200,
        "method": method,
        "request_name": name,
        "source_path": str(src),
        "size": src.stat().st_size,
        "sha256": rec.get("sha256", ""),
        "timestamp": utc_now(),
        "remote_addr": f"{addr[0]}:{addr[1]}",
    }, route), request_headers)


def handle_file_service_http(cfg, conn, files_dir, addr):
    method, target, _version, headers, body = read_http_headers(conn)
    if method in {"GET", "HEAD"}:
        return handle_staged_fetch(cfg, conn, method, target, headers, addr), 200
    if method not in {"PUT", "POST"}:
        metadata = {
            "operation": "upload",
            "status": "rejected",
            "reason": "file service accepts only target-initiated PUT/POST uploads or GET staged fetches",
            "method": method,
            "source_path": target,
            "remote_addr": f"{addr[0]}:{addr[1]}",
        }
        metadata.update(target_identity_from_headers(headers))
        send_json_response(conn, 405, metadata)
        return metadata, 405
    # Reconstruct the header block for the existing upload reader to keep upload
    # behavior unchanged while sharing the initial parse path with GET.
    request_line = f"{method} {target} HTTP/1.1\r\n"
    header_lines = "".join(f"{key}: {value}\r\n" for key, value in headers.items())
    buffered = request_line.encode("iso-8859-1") + header_lines.encode("iso-8859-1") + b"\r\n" + body

    class BufferedConn:
        def __init__(self, base, first):
            self.base = base
            self.first = bytearray(first)

        def recv(self, n):
            if self.first:
                chunk = bytes(self.first[:n])
                del self.first[:n]
                return chunk
            return self.base.recv(n)

        def sendall(self, data):
            return self.base.sendall(data)

    metadata, status_code = read_http_upload(BufferedConn(conn, buffered), files_dir, addr)
    send_json_response(conn, status_code, metadata)
    return metadata, status_code


def _file_service_tls_context(cfg, use_tls):
    cert = Path(str(cfg["tls_cert"]))
    key = Path(str(cfg["tls_key"]))
    if not use_tls:
        return None, 0
    if not cert.is_file() or not key.is_file():
        print(f"TLS cert/key not found, generating: {cert}", file=sys.stderr)
        if not generate_tls_cert(cert, key):
            print(f"TLS cert/key generation failed — see {cert.parent}/openssl-generate.log", file=sys.stderr)
            return None, 2
        print(f"Generated TLS cert/key: {cert}", file=sys.stderr)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    return context, 0


def _start_file_service_record(cfg, service, log_dir, port, use_tls):
    SESSION_MANAGER.start_record(cfg, service, log_dir, details={"port": port, "tls": use_tls})
    files_dir = log_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("Receive-only file service. Accepts target-initiated PUT/POST uploads.")
    print("Also serves operator-staged files only when the target explicitly requests them with grit fetch.")
    print("This service does not execute commands or provide callback RPC.")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), "staged_file": str(staged_file_path(cfg))})
    return files_dir


def _mark_file_service_listening(cfg, service, log_dir, port, use_tls):
    update_server_state(cfg, service, "listening", {"session_log": str(log_dir), "staged_file": str(staged_file_path(cfg))})
    append_event(cfg, service, "service_start", session=str(log_dir), details={"port": port, "tls": use_tls})
    print_candidates(cfg, port)


def _attach_file_service_upload_route(cfg, metadata):
    if metadata.get("operation") != "upload" or "route_kind" in metadata:
        return metadata
    host = operator_advertised_host(cfg)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=host,
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    return attach_target_route_fields(metadata, route)


def _record_file_service_transfer(cfg, service, log_dir, remote, metadata):
    target_rec = record_target_activity(cfg, metadata, service, session_id=log_dir.name)
    if metadata.get("operation") == "fetch":
        print(f"file-service fetch {metadata.get('status')}: {metadata.get('request_name')} <- {metadata.get('source_path', metadata.get('reason', ''))}")
        SESSION_MANAGER.append_list_item(log_dir, "fetches", metadata)
        append_event(cfg, service, "fetch_start", session=str(log_dir), remote=remote, details={"request_name": metadata.get("request_name", ""), "method": metadata.get("method", ""), "target_id": metadata.get("target_id", ""), "target_label": metadata.get("target_label", "")})
        append_event(cfg, service, "fetch_complete", session=str(log_dir), remote=remote, details=metadata)
    else:
        print(f"file-service upload {metadata.get('status')}: {metadata.get('stored_path', metadata.get('reason', ''))}")
        SESSION_MANAGER.append_list_item(log_dir, "uploads", metadata)
        append_event(cfg, service, "upload_start", session=str(log_dir), remote=remote, details={"filename": metadata.get("filename", ""), "expected_size": metadata.get("expected_size", ""), "target_id": metadata.get("target_id", ""), "target_label": metadata.get("target_label", "")})
        append_event(cfg, service, "upload_complete", session=str(log_dir), remote=remote, details=metadata)
    if target_rec:
        SESSION_MANAGER.update_record(log_dir, target_id=metadata.get("target_id", ""), target_label=target_rec.get("label", ""))
        SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote, target_id=metadata.get("target_id", ""))


def _record_file_service_connection_close(cfg, service, log_dir, remote, metadata, status_code):
    append_event(
        cfg,
        service,
        "connection_close",
        session=str(log_dir),
        remote=remote,
        details={
            "operation": metadata.get("operation", ""),
            "status": metadata.get("status", ""),
            "http_status": metadata.get("http_status", status_code),
            "request_name": metadata.get("request_name", ""),
            "filename": metadata.get("filename", ""),
            "target_id": metadata.get("target_id", ""),
        },
    )


def _handle_file_service_connection(
    cfg,
    service,
    log_dir,
    raw,
    addr,
    tls_context,
    files_dir,
):
    remote = f"{addr[0]}:{addr[1]}"
    metadata = {}
    status_code = ""
    try:
        with raw:
            conn = tls_context.wrap_socket(raw, server_side=True) if tls_context else raw
            with conn:
                append_event(cfg, service, "connection_open", session=str(log_dir), remote=remote)
                SESSION_MANAGER.update_record(log_dir, state="active", remote=remote)
                SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote)
                metadata, status_code = handle_file_service_http(cfg, conn, files_dir, addr)
                metadata = _attach_file_service_upload_route(cfg, metadata)
                _record_file_service_transfer(cfg, service, log_dir, remote, metadata)
    except Exception as exc:
        metadata = {"operation": "unknown", "status": "error", "reason": str(exc)}
        status_code = 500
        try:
            send_json_response(raw, 500, {"status": "error", "reason": str(exc)})
        except Exception:
            pass
        print(f"file-service request failed: {exc}", file=sys.stderr)
        append_event(cfg, service, "request_error", "error", session=str(log_dir), details={"error": str(exc)})
    finally:
        _record_file_service_connection_close(
            cfg, service, log_dir, remote, metadata, status_code
        )


def _stop_file_service(cfg, service, log_dir, port):
    stop_reason = current_stop_reason("complete")
    record_shutdown_event(cfg, service, session=log_dir)
    mark_service_stopped(cfg, service, stop_reason)
    SESSION_MANAGER.finish_record(cfg, service, log_dir, exit_reason=stop_reason)
    append_event(cfg, service, "service_stop", session=str(log_dir),
                 details={"port": port, "reason": stop_reason})


def serve_file_service(cfg, timeout, max_sessions=0):
    service = "file-service"
    port = int(cfg["GRIT_OPERATOR_FILE_SERVICE_PORT"])
    use_tls = yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes"))
    tls_context, tls_status = _file_service_tls_context(cfg, use_tls)
    if tls_status:
        return tls_status
    log_dir = SESSION_MANAGER.log_dir(cfg, "file-service")
    files_dir = _start_file_service_record(cfg, service, log_dir, port, use_tls)
    sessions = 0
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 20)
        bound = True
        sock.settimeout(timeout)
        _mark_file_service_listening(cfg, service, log_dir, port, use_tls)
        while not SHUTDOWN.is_set():
            print("Waiting for file upload/fetch...")
            try:
                raw, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for file upload/fetch", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            _handle_file_service_connection(
                cfg, service, log_dir, raw, addr, tls_context, files_dir
            )
            sessions += 1
            if max_sessions > 0 and sessions >= max_sessions:
                break
    finally:
        if sock:
            unregister_socket(sock)
            try:
                sock.close()
            except OSError:
                pass
        if bound:
            _stop_file_service(cfg, service, log_dir, port)
    return 0
