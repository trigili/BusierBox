"""Probe protocol service listeners for grit-console."""

import base64
import json
import socket
import sys
import urllib.parse

from gritlib.bridge_routes import attach_target_route_fields
from gritlib.dns import dns_parse_qname, dns_txt_answer_packet
from gritlib.event_log import append_event
from gritlib.file_transfers import (
    read_http_body,
    read_http_headers,
    send_http_response,
    send_json_response,
)
from gritlib.ftp import ftp_pasv_reply_host, ftp_recv_line, ftp_send_line
from gritlib.operator_network import local_ips, operator_advertised_host, print_candidates
from gritlib.probe_commands import (
    probe_route_context,
    probe_script_fn,
    render_probe_command,
    render_probe_dns_command,
    render_probe_ftp_command,
    render_probe_tftp_command,
)
from gritlib.probe_results import append_probe_result
from gritlib.service_runtime import (
    SESSION_MANAGER,
    SHUTDOWN,
    bind_listen_socket,
    current_shutdown_reason,
    current_stop_reason,
    record_shutdown_event,
    register_socket,
    unregister_socket,
)
from gritlib.session_state import (
    mark_service_error,
    mark_service_stopped,
    update_server_state,
    utc_now,
)
from gritlib.target_records import (
    attach_target_identity,
    record_target_activity,
)
from gritlib.tftp import parse_tftp_rrq, send_tftp_file, tftp_error_packet

def handle_probe_http(cfg, conn, method, target, headers, body, addr, script_text, route=None):
    parsed = urllib.parse.urlparse(target)
    remote = f"{addr[0]}:{addr[1]}"
    route_doc = dict(route or probe_route_context(cfg))
    script_name = "/" + (str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh")
    if method in {"GET", "HEAD"} and parsed.path in {script_name, "/survey.sh", "/probe/probe.sh"}:
        payload = script_text.encode("utf-8")
        send_http_response(conn, 200, b"" if method == "HEAD" else payload, "text/x-shellscript", headers={
            "X-griTTYkit-Survey-Bootstrap": "yes",
        })
        return attach_target_identity(attach_target_route_fields({
            "operation": "probe_script_fn",
            "status": "served",
            "http_status": 200,
            "method": method,
            "remote_addr": remote,
            "script_name": script_name,
            "size": len(payload),
        }, route_doc), headers)
    if method in {"GET", "POST"} and parsed.path in {"/probe/result", "/probe/result/"}:
        if method == "GET":
            form = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        else:
            payload_body = read_http_body(conn, headers, body)
            form = urllib.parse.parse_qs(payload_body.decode("utf-8", errors="replace"), keep_blank_values=True)
        result = {
            "schema": 1,
            "operation": "probe_result",
            "status": "received",
            "method": method,
            "remote_addr": remote,
            "received_at": utc_now(),
        }
        for key in ("script", "uname_s", "uname_m", "uname_r", "word_bits", "endian"):
            result[key] = str((form.get(key) or [""])[0])
        result["architecture"] = result.get("uname_m", "")
        result["kernel"] = result.get("uname_r", "")
        path = append_probe_result(cfg, result)
        result["results_path"] = str(path)
        send_json_response(conn, 200, result)
        return attach_target_identity(attach_target_route_fields(result, route_doc), headers)
    payload = {"schema": 1, "status": "rejected", "reason": "unknown probe endpoint"}
    send_json_response(conn, 404, payload)
    return attach_target_identity(attach_target_route_fields({
        "operation": "probe",
        "status": "rejected",
        "http_status": 404,
        "method": method,
        "remote_addr": remote,
        "reason": payload["reason"],
    }, route_doc), headers)


def _probe_http_host(cfg):
    host = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "").strip()
    if not host or host in ("0.0.0.0", "::"):
        candidates = local_ips()
        host = candidates[0] if candidates else "OPERATOR_IP"
    return host


def _probe_script_name(cfg):
    return str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"


def _probe_http_session_details(port, script_name, route, route_host, route_port, target_command):
    return {
        "port": port,
        "script_name": script_name,
        "url": f"http://{route_host}:{route_port}/{script_name}",
        "target_command": target_command,
        "target_route": dict(route),
        "route_kind": route.get("route_kind", "direct"),
        "route_host": route_host,
        "route_port": route_port,
        "bridge_profile": route.get("bridge_profile", ""),
        "bridge_route_path": route.get("bridge_route_path", ""),
        "requires_bridge": bool(route.get("requires_bridge")),
    }


def _start_probe_http_record(cfg, service, log_dir, script_name, script_text, session_details):
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=session_details)
    (log_dir / script_name).write_text(script_text, encoding="utf-8")
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Probe listener. Binding on http://{cfg.get('listen_host', '0.0.0.0')}:{session_details['port']}/{script_name}")
    print(f"Probe target URL: {session_details['url']}")
    if session_details.get("route_kind") == "bridge":
        print(f"Probe route: bridge profile {session_details.get('bridge_profile', '')} {session_details.get('bridge_route_path', '')}")
    print(f"Target command: {session_details['target_command']}")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), **session_details})


def _mark_probe_http_listening(cfg, service, log_dir, port, route_host, route_port, session_details):
    update_server_state(cfg, service, "listening", {"session_log": str(log_dir), **session_details})
    append_event(cfg, service, "service_start", session=str(log_dir), details=session_details)
    print_candidates(cfg, port, advertised_host=route_host, advertised_port=route_port)


def _record_probe_http_request(cfg, service, log_dir, addr, metadata):
    remote = f"{addr[0]}:{addr[1]}"
    target_rec = record_target_activity(cfg, metadata, service, session_id=log_dir.name)
    if metadata.get("target_id"):
        SESSION_MANAGER.update_record(
            log_dir,
            target_id=metadata.get("target_id", ""),
            target_label=target_rec.get("label", metadata.get("target_label", "")),
        )
        SESSION_MANAGER.upsert_state(
            cfg,
            log_dir,
            service,
            "active",
            remote=remote,
            target_id=metadata.get("target_id", ""),
            target_label=target_rec.get("label", metadata.get("target_label", "")),
        )
    event = "probe_result" if metadata.get("operation") == "probe_result" else "probe_request"
    append_event(cfg, service, event, session=str(log_dir), remote=remote, details=metadata)
    print(f"probe {metadata.get('status')}: {metadata.get('operation', '')}")


def _handle_probe_http_connection(cfg, service, log_dir, conn, addr, script_text, route):
    metadata = {}
    try:
        with conn:
            method, target, _version, headers, body = read_http_headers(conn)
            metadata = handle_probe_http(
                cfg, conn, method, target, headers, body, addr, script_text, route=route
            )
            _record_probe_http_request(cfg, service, log_dir, addr, metadata)
    except Exception as exc:
        metadata = {"operation": "probe", "status": "error", "reason": str(exc)}
        try:
            send_json_response(conn, 500, {"schema": 1, "status": "error", "reason": str(exc)})
        except Exception:
            pass
        append_event(cfg, service, "probe_error", "error", session=str(log_dir), details=metadata)
        print(f"probe failed: {exc}", file=sys.stderr)
    return metadata


def _stop_probe_http_listener(cfg, service, log_dir, port, script_name, route_host, route_port):
    stop_reason = current_stop_reason("complete")
    update_server_state(cfg, service, "stopped", {
        "session_log": str(log_dir),
        "script_name": script_name,
        "url": f"http://{route_host}:{route_port}/{script_name}",
        "pid": "",
        "managed_by": "",
        "stopped_at": utc_now(),
        "stopped_reason": stop_reason,
    })
    SESSION_MANAGER.update_record(log_dir, state="ended", exit_reason=stop_reason)
    SESSION_MANAGER.upsert_state(cfg, log_dir, service, "ended", exit_reason=stop_reason)
    record_shutdown_event(cfg, service, session=log_dir)
    append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "reason": stop_reason})


def serve_probe(cfg, timeout, max_sessions=0):
    service = "probe"
    port = int(cfg.get("GRIT_PROBE_PORT", 22207))
    host = _probe_http_host(cfg)
    script_name = _probe_script_name(cfg)
    route = probe_route_context(cfg, host=host, port=port)
    route_host = str(route.get("host") or host)
    route_port = int(route.get("port") or port)
    target_command = render_probe_command(cfg, host=host, port=port)
    script_text = probe_script_fn(cfg, route_host, route_port)
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    session_details = _probe_http_session_details(
        port, script_name, route, route_host, route_port, target_command
    )
    _start_probe_http_record(
        cfg, service, log_dir, script_name, script_text, session_details
    )
    sessions = 0
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 20)
        bound = True
        sock.settimeout(timeout)
        _mark_probe_http_listening(
            cfg, service, log_dir, port, route_host, route_port, session_details
        )
        while not SHUTDOWN.is_set():
            print("Waiting for probe request...")
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for probe request", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            _handle_probe_http_connection(
                cfg, service, log_dir, conn, addr, script_text, route
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
            _stop_probe_http_listener(
                cfg, service, log_dir, port, script_name, route_host, route_port
            )
    return 0


def serve_probe_tftp(cfg, timeout, max_sessions=0):
    service = "probe-tftp"
    port = int(cfg.get("GRIT_PROBE_TFTP_PORT", 22208))
    host = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "").strip()
    if not host or host in ("0.0.0.0", "::"):
        candidates = local_ips()
        host = candidates[0] if candidates else "OPERATOR_IP"
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    script_text = probe_script_fn(cfg, host, int(cfg.get("GRIT_PROBE_PORT", 22207)))
    payload = script_text.encode("utf-8")
    target_command = render_probe_tftp_command(cfg, host=host, port=port)
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    session_details = {
        "port": port,
        "protocol": "udp",
        "script_name": script_name,
        "target_command": target_command,
        "http_result_port": int(cfg.get("GRIT_PROBE_PORT", 22207)),
    }
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=session_details)
    (log_dir / script_name).write_text(script_text, encoding="utf-8")
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Probe TFTP listener. Binding on udp://{cfg.get('listen_host', '0.0.0.0')}:{port}")
    print(f"Probe TFTP target URL: tftp://{host}:{port}/{script_name}")
    print(f"Target command: {target_command}")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), **session_details})
    sessions = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(cfg["listen_host"]), port))
        register_socket(sock)
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", {"session_log": str(log_dir), **session_details})
        append_event(cfg, service, "service_start", session=str(log_dir), details=session_details)
        while not SHUTDOWN.is_set():
            try:
                packet, addr = sock.recvfrom(516)
            except socket.timeout:
                print("timeout waiting for TFTP probe request", file=sys.stderr)
                return 1 if sessions == 0 else 0
            filename, mode = parse_tftp_rrq(packet)
            remote = f"{addr[0]}:{addr[1]}"
            if filename != script_name:
                sock.sendto(tftp_error_packet(1, "file not found"), addr)
                append_event(cfg, service, "probe_tftp_rejected", "warning", remote=remote, session=str(log_dir), details={
                    "filename": filename,
                    "mode": mode,
                    "reason": "file-not-found",
                })
                continue
            try:
                blocks = send_tftp_file(sock, addr, payload)
            except TimeoutError as exc:
                append_event(cfg, service, "probe_tftp_error", "error", remote=remote, session=str(log_dir), details={
                    "filename": filename,
                    "mode": mode,
                    "error": str(exc),
                })
                continue
            sessions += 1
            metadata = {
                "operation": "probe_tftp_script",
                "status": "served",
                "remote_addr": remote,
                "script_name": script_name,
                "mode": mode,
                "size": len(payload),
                "blocks": blocks,
            }
            SESSION_MANAGER.append_list_item(log_dir, "artifacts", metadata)
            append_event(cfg, service, "probe_tftp_served", remote=remote, session=str(log_dir), details=metadata)
            if max_sessions and sessions >= max_sessions:
                return 0
    except OSError as exc:
        mark_service_error(cfg, service, exc, {"listen_host": str(cfg["listen_host"]), "port": port, "protocol": "udp"}, event_name="bind_error")
        print(f"{service}: unable to bind UDP {cfg['listen_host']}:{port}: {exc}", file=sys.stderr)
        raise
    finally:
        try:
            unregister_socket(sock)
            sock.close()
        except OSError:
            pass
        stop_reason = current_shutdown_reason() or "server-exit"
        if stop_reason != "bind_error":
            mark_service_stopped(cfg, service, stop_reason)
            SESSION_MANAGER.finish_record(cfg, service, log_dir, state="ended", exit_reason=stop_reason)
            record_shutdown_event(cfg, service, session=log_dir)
            append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "protocol": "udp", "reason": stop_reason})
    return 0


def handle_probe_ftp_session(cfg, conn, addr, script_name, payload, log_dir, host):
    remote = f"{addr[0]}:{addr[1]}"
    data_sock = None
    retrievals = 0
    ftp_send_line(conn, "220 griTTYkit probe FTP ready")
    try:
        while not SHUTDOWN.is_set():
            line = ftp_recv_line(conn)
            if not line:
                break
            command, _, arg = line.partition(" ")
            command = command.upper()
            arg = arg.strip()
            if command == "USER":
                ftp_send_line(conn, "331 password not required")
            elif command == "PASS":
                ftp_send_line(conn, "230 logged in")
            elif command == "SYST":
                ftp_send_line(conn, "215 UNIX Type: L8")
            elif command == "PWD":
                ftp_send_line(conn, '257 "/"')
            elif command == "TYPE":
                ftp_send_line(conn, "200 type set")
            elif command in {"CWD", "NOOP"}:
                ftp_send_line(conn, "200 ok")
            elif command == "SIZE":
                name = arg.lstrip("/")
                if name == script_name:
                    ftp_send_line(conn, f"213 {len(payload)}")
                else:
                    ftp_send_line(conn, "550 file not found")
            elif command == "PASV":
                if data_sock:
                    try:
                        unregister_socket(data_sock)
                        data_sock.close()
                    except OSError:
                        pass
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                data_sock.bind((str(cfg.get("listen_host", "0.0.0.0")), 0))
                data_sock.listen(1)
                register_socket(data_sock)
                pasv_host = ftp_pasv_reply_host(host, local_ips()).replace(".", ",")
                data_port = data_sock.getsockname()[1]
                ftp_send_line(conn, f"227 Entering Passive Mode ({pasv_host},{data_port // 256},{data_port % 256})")
            elif command == "EPSV":
                if data_sock:
                    try:
                        unregister_socket(data_sock)
                        data_sock.close()
                    except OSError:
                        pass
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                data_sock.bind((str(cfg.get("listen_host", "0.0.0.0")), 0))
                data_sock.listen(1)
                register_socket(data_sock)
                data_port = data_sock.getsockname()[1]
                ftp_send_line(conn, f"229 Entering Extended Passive Mode (|||{data_port}|)")
            elif command == "RETR":
                name = arg.lstrip("/")
                if name != script_name:
                    ftp_send_line(conn, "550 file not found")
                    append_event(cfg, "probe-ftp", "probe_ftp_rejected", "warning", remote=remote, session=str(log_dir), details={
                        "filename": name,
                        "reason": "file-not-found",
                    })
                    continue
                if not data_sock:
                    ftp_send_line(conn, "425 use PASV first")
                    continue
                ftp_send_line(conn, "150 opening data connection")
                data_sock.settimeout(5.0)
                data_conn, data_addr = data_sock.accept()
                with data_conn:
                    data_conn.sendall(payload)
                unregister_socket(data_sock)
                data_sock.close()
                data_sock = None
                retrievals += 1
                metadata = {
                    "operation": "probe_ftp_script",
                    "status": "served",
                    "remote_addr": remote,
                    "data_remote_addr": f"{data_addr[0]}:{data_addr[1]}",
                    "script_name": script_name,
                    "size": len(payload),
                }
                SESSION_MANAGER.append_list_item(log_dir, "artifacts", metadata)
                append_event(cfg, "probe-ftp", "probe_ftp_served", remote=remote, session=str(log_dir), details=metadata)
                ftp_send_line(conn, "226 transfer complete")
            elif command == "QUIT":
                ftp_send_line(conn, "221 bye")
                break
            else:
                ftp_send_line(conn, "502 command not implemented")
    finally:
        if data_sock:
            try:
                unregister_socket(data_sock)
                data_sock.close()
            except OSError:
                pass
    return retrievals


def serve_probe_ftp(cfg, timeout, max_sessions=0):
    service = "probe-ftp"
    port = int(cfg.get("GRIT_PROBE_FTP_PORT", 22209))
    host = operator_advertised_host(cfg)
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    script_text = probe_script_fn(cfg, host, int(cfg.get("GRIT_PROBE_PORT", 22207)))
    payload = script_text.encode("utf-8")
    target_command = render_probe_ftp_command(cfg, host=host, port=port)
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    session_details = {
        "port": port,
        "protocol": "tcp",
        "script_name": script_name,
        "url": f"ftp://{host}:{port}/{script_name}",
        "target_command": target_command,
        "http_result_port": int(cfg.get("GRIT_PROBE_PORT", 22207)),
    }
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=session_details)
    (log_dir / script_name).write_text(script_text, encoding="utf-8")
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Probe FTP listener. Binding on ftp://{cfg.get('listen_host', '0.0.0.0')}:{port}/{script_name}")
    print(f"Probe FTP target URL: ftp://{host}:{port}/{script_name}")
    print(f"Target command: {target_command}")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), **session_details})
    sessions = 0
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 20)
        bound = True
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", {"session_log": str(log_dir), **session_details})
        append_event(cfg, service, "service_start", session=str(log_dir), details=session_details)
        print_candidates(cfg, port, advertised_host=host, advertised_port=port)
        while not SHUTDOWN.is_set():
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for FTP probe request", file=sys.stderr)
                return 1 if sessions == 0 else 0
            with conn:
                sessions += handle_probe_ftp_session(cfg, conn, addr, script_name, payload, log_dir, host)
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
            stop_reason = current_stop_reason("complete")
            update_server_state(cfg, service, "stopped", {
                "session_log": str(log_dir),
                "script_name": script_name,
                "url": f"ftp://{host}:{port}/{script_name}",
                "pid": "",
                "managed_by": "",
                "stopped_at": utc_now(),
                "stopped_reason": stop_reason,
            })
            SESSION_MANAGER.finish_record(cfg, service, log_dir, state="ended", exit_reason=stop_reason)
            record_shutdown_event(cfg, service, session=log_dir)
            append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "protocol": "tcp", "reason": stop_reason})
    return 0


def serve_probe_dns(cfg, timeout, max_sessions=0):
    service = "probe-dns"
    port = int(cfg.get("GRIT_PROBE_DNS_PORT", 22210))
    host = operator_advertised_host(cfg)
    dns_name = str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit")).strip().strip(".") or "probe.grit"
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    script_text = probe_script_fn(cfg, host, int(cfg.get("GRIT_PROBE_PORT", 22207)))
    encoded = base64.b64encode(script_text.encode("utf-8")).decode("ascii")
    txt_chunks = [encoded[i:i + 240] for i in range(0, len(encoded), 240)]
    target_command = render_probe_dns_command(cfg, host=host, port=port)
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    session_details = {
        "port": port,
        "protocol": "udp",
        "dns_name": dns_name,
        "script_name": script_name,
        "txt_chunk_count": len(txt_chunks),
        "target_command": target_command,
        "http_result_port": int(cfg.get("GRIT_PROBE_PORT", 22207)),
    }
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=session_details)
    (log_dir / script_name).write_text(script_text, encoding="utf-8")
    (log_dir / f"{dns_name}.txt").write_text("\n".join(txt_chunks) + "\n", encoding="utf-8")
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"Probe DNS listener. Binding on dns://{cfg.get('listen_host', '0.0.0.0')}:{port}/{dns_name}")
    print(f"Probe DNS TXT name: {dns_name}")
    print(f"Target command: {target_command}")
    if port != 53:
        print("DNS note: nslookup usually needs this service exposed on port 53; custom ports use the generated dig command.")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), **session_details})
    sessions = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(cfg["listen_host"]), port))
        register_socket(sock)
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", {"session_log": str(log_dir), **session_details})
        append_event(cfg, service, "service_start", session=str(log_dir), details=session_details)
        while not SHUTDOWN.is_set():
            try:
                packet, addr = sock.recvfrom(4096)
            except socket.timeout:
                print("timeout waiting for DNS probe request", file=sys.stderr)
                return 1 if sessions == 0 else 0
            qname, qend = dns_parse_qname(packet)
            qtype = int.from_bytes(packet[qend:qend + 2], "big") if qend + 2 <= len(packet) else 0
            remote = f"{addr[0]}:{addr[1]}"
            chunks = txt_chunks if qname.rstrip(".").lower() == dns_name.lower() else []
            response = dns_txt_answer_packet(packet, chunks)
            if response:
                sock.sendto(response, addr)
            sessions += 1
            metadata = {
                "operation": "probe_dns_txt",
                "status": "served" if chunks else "not-found",
                "remote_addr": remote,
                "dns_name": qname,
                "query_type": qtype,
                "txt_chunk_count": len(chunks),
                "size": len(encoded) if chunks else 0,
            }
            SESSION_MANAGER.append_list_item(log_dir, "artifacts", metadata)
            append_event(cfg, service, "probe_dns_query", remote=remote, session=str(log_dir), details=metadata)
            if max_sessions and sessions >= max_sessions:
                return 0
    except OSError as exc:
        mark_service_error(cfg, service, exc, {"listen_host": str(cfg["listen_host"]), "port": port, "protocol": "udp"}, event_name="bind_error")
        print(f"{service}: unable to bind UDP {cfg['listen_host']}:{port}: {exc}", file=sys.stderr)
        raise
    finally:
        try:
            unregister_socket(sock)
            sock.close()
        except OSError:
            pass
        stop_reason = current_shutdown_reason() or "server-exit"
        if stop_reason != "bind_error":
            mark_service_stopped(cfg, service, stop_reason)
            SESSION_MANAGER.finish_record(cfg, service, log_dir, state="ended", exit_reason=stop_reason)
            record_shutdown_event(cfg, service, session=log_dir)
            append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "protocol": "udp", "reason": stop_reason})
    return 0
