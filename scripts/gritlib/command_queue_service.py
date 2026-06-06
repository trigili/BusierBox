"""Command queue listener service for grit-console."""

import json
import socket
import sys
import urllib.parse

from gritlib.command_queue import (
    append_command_queue_poll_events,
    append_command_queue_result_events,
    command_queue_summary,
)
from gritlib.command_queue_policy import (
    command_queue_execution_rejection_reason,
    command_queue_token_valid,
)
from gritlib.command_queue_records import (
    command_queue_path,
    command_queue_work_metadata,
    mark_command_delivered,
    record_command_result_payload,
)
from gritlib.config_utils import yes
from gritlib.event_log import append_event
from gritlib.file_transfers import (
    read_http_body,
    read_http_headers,
    send_http_response,
    send_json_response,
)
from gritlib.operator_network import print_candidates
from gritlib.service_runtime import (
    SESSION_MANAGER,
    SHUTDOWN,
    bind_listen_socket,
    current_stop_reason,
    record_shutdown_event,
    unregister_socket,
)
from gritlib.session_state import update_server_state, utc_now
from gritlib.target_records import (
    details_with_target,
    target_identity_from_headers,
)
from gritlib.target_record_updates import record_target_activity


def handle_command_queue_result(cfg, conn, method, target, headers, body, addr):
    remote = f"{addr[0]}:{addr[1]}"
    target_identity = target_identity_from_headers(headers)
    command_id = ""
    if method not in {"PUT", "POST"}:
        payload = {"schema": 1, "status": "rejected", "reason": "command queue result accepts only PUT or POST"}
        send_json_response(conn, 405, payload)
        return details_with_target(cfg, {"operation": "command_queue_result", "status": "rejected", "http_status": 405, "method": method, "remote_addr": remote}, target_identity)
    parsed = urllib.parse.urlparse(target)
    if parsed.path not in {"/command-queue/result", "/command-queue/result/"}:
        payload = {"schema": 1, "status": "rejected", "reason": "unknown command queue result endpoint"}
        send_json_response(conn, 404, payload)
        return details_with_target(cfg, {"operation": "command_queue_result", "status": "rejected", "http_status": 404, "method": method, "remote_addr": remote, "reason": "unknown endpoint"}, target_identity)
    if not command_queue_token_valid(cfg, headers):
        payload = {"schema": 1, "status": "rejected", "reason": "missing or invalid command queue token"}
        send_json_response(conn, 403, payload)
        return details_with_target(cfg, {"operation": "command_queue_result", "status": "rejected", "http_status": 403, "method": method, "remote_addr": remote, "reason": "invalid token"}, target_identity)
    try:
        payload_body = read_http_body(conn, headers, body)
        result = json.loads(payload_body.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("command result JSON must be an object")
        command_id = str(result.get("command_id", "") or "").strip()
        if not command_id:
            raise ValueError("command result JSON must include command_id")
        rec = record_command_result_payload(cfg, command_id, result, f"http:{remote}{parsed.path}", target_identity=target_identity)
    except json.JSONDecodeError as exc:
        payload = {"schema": 1, "status": "rejected", "reason": f"invalid command result JSON: {exc}"}
        send_json_response(conn, 400, payload)
        return details_with_target(cfg, {"operation": "command_queue_result", "status": "rejected", "http_status": 400, "method": method, "remote_addr": remote, "reason": payload["reason"]}, target_identity)
    except ValueError as exc:
        payload = {"schema": 1, "status": "rejected", "reason": str(exc)}
        send_json_response(conn, 400, payload)
        details = {"operation": "command_queue_result", "status": "rejected", "http_status": 400, "method": method, "remote_addr": remote, "reason": str(exc)}
        if command_id:
            details["command_id"] = command_id
        return details_with_target(cfg, details, target_identity)
    response = {
        "schema": 1,
        "status": "result-received",
        "id": rec.get("id", command_id),
        "command_id": command_id,
        "command_sha256": rec.get("command_sha256", ""),
        "result_status": (rec.get("result") or {}).get("status", ""),
        "result_exit_code": (rec.get("result") or {}).get("exit_code", ""),
        "result_output_bytes": rec.get("result_output_bytes", 0),
        "result_output_limit_bytes": rec.get("result_output_limit_bytes", 0),
        "result_output_exceeded_limit": bool(rec.get("result_output_exceeded_limit")),
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "execution_supported": bool(rec.get("execution_supported", False)),
        "executes_commands": bool(rec.get("executes_commands", False)),
        "execution_decision": rec.get("execution_decision", ""),
        "result_upload_supported": True,
    }
    send_json_response(conn, 200, response)
    return details_with_target(cfg, {
        "operation": "command_queue_result",
        "status": "result-received",
        "http_status": 200,
        "method": method,
        "remote_addr": remote,
        "command_id": command_id,
        "command_sha256": rec.get("command_sha256", ""),
        "result_status": response["result_status"],
        "result_exit_code": response["result_exit_code"],
        "result_output_bytes": response["result_output_bytes"],
        "result_output_limit_bytes": response["result_output_limit_bytes"],
        "result_output_exceeded_limit": response["result_output_exceeded_limit"],
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "execution_supported": response["execution_supported"],
        "executes_commands": response["executes_commands"],
        "execution_decision": response["execution_decision"],
        "result_upload_supported": True,
    }, target_identity)

def handle_command_queue_http(cfg, conn, method, target, headers, body, addr):
    parsed = urllib.parse.urlparse(target)
    if parsed.path in {"/command-queue/result", "/command-queue/result/"}:
        return handle_command_queue_result(cfg, conn, method, target, headers, body, addr)
    return handle_command_queue_poll(cfg, conn, method, target, headers, addr)


def _command_queue_poll_context(headers):
    return {
        "poll_mode": str(headers.get("x-grit-command-queue-mode") or headers.get("x-grittykit-command-queue-mode") or ""),
        "poll_interval_sec": str(headers.get("x-grit-command-queue-poll-interval-sec") or headers.get("x-grittykit-command-queue-poll-interval-sec") or ""),
        "poll_jitter_pct": str(headers.get("x-grit-command-queue-poll-jitter-pct") or headers.get("x-grittykit-command-queue-poll-jitter-pct") or ""),
        "poll_backoff": str(headers.get("x-grit-command-queue-poll-backoff") or headers.get("x-grittykit-command-queue-poll-backoff") or ""),
        "poll_max_interval_sec": str(headers.get("x-grit-command-queue-poll-max-interval-sec") or headers.get("x-grittykit-command-queue-poll-max-interval-sec") or ""),
        "max_polls": str(headers.get("x-grit-command-queue-max-polls") or headers.get("x-grittykit-command-queue-max-polls") or ""),
    }


def _reject_command_queue_poll(
    cfg,
    conn,
    *,
    http_status,
    reason,
    method,
    remote,
    poll_context,
    target_identity,
    detail_reason=None,
):
    payload = {"schema": 1, "status": "rejected", "reason": reason}
    send_json_response(conn, http_status, payload)
    details = {
        "operation": "command_queue_poll",
        "status": "rejected",
        "http_status": http_status,
        "method": method,
        "remote_addr": remote,
        **poll_context,
    }
    if detail_reason:
        details["reason"] = detail_reason
    return details_with_target(cfg, details, target_identity)


def _command_queue_execution_context(cfg, queue):
    execution_supported = bool(queue.get("execution_supported"))
    execution_decision = "pending" if execution_supported else "rejected"
    execution_decision_reason = (
        "" if execution_supported else command_queue_execution_rejection_reason(cfg)
    )
    return execution_supported, execution_decision, execution_decision_reason


def _queued_commands_for_target(queue, target_id):
    return [
        rec for rec in queue.get("commands", [])
        if isinstance(rec, dict) and rec.get("status") == "queued" and rec.get("id")
        and (str(rec.get("target_id") or "") in ("", target_id) if target_id else not str(rec.get("target_id") or ""))
    ]


def _delivered_command_payload(
    cfg,
    command,
    target_identity,
    execution_supported,
    execution_decision,
    execution_decision_reason,
):
    payload = {
        "schema": 1,
        "status": "delivered",
        "id": command.get("id"),
        "command_id": command.get("id"),
        "command_sha256": command.get("command_sha256", ""),
        "command": command.get("command", ""),
        "timeout_sec": command.get("timeout_sec", 0),
        "max_output_bytes": command.get("max_output_bytes", 0),
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "delivery_supported": True,
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "result_upload_supported": True,
        "execution_decision": execution_decision,
        "execution_decision_reason": execution_decision_reason,
    }
    payload.update({key: value for key, value in target_identity.items() if value not in (None, "")})
    return payload


def _delivered_command_response_headers(command, target_id, execution_supported):
    response_headers = {
        "X-griTTYkit-Command-Queue-Status": "delivered",
        "X-griTTYkit-Command-Id": str(command.get("id")),
        "X-griTTYkit-Command-Sha256": str(command.get("command_sha256", "")),
        "X-griTTYkit-Delivery-Supported": "yes",
        "X-griTTYkit-Result-Upload-Supported": "yes",
        "X-griTTYkit-Execution-Supported": "yes" if execution_supported else "no",
        "X-griTTYkit-Executes-Commands": "yes" if execution_supported else "no",
    }
    if target_id:
        response_headers["X-griTTYkit-Target-Id"] = target_id
    return response_headers


def _delivered_command_poll_details(
    cfg,
    method,
    remote,
    command,
    queued_count,
    delivered,
    execution_supported,
    execution_decision,
    execution_decision_reason,
    poll_context,
):
    return {
        "operation": "command_queue_poll",
        "status": "delivered",
        "http_status": 200,
        "method": method,
        "remote_addr": remote,
        "command_id": command.get("id"),
        "command_sha256": command.get("command_sha256", ""),
        "queued_count_before": queued_count,
        "delivered_count": 1 if delivered else 0,
        **command_queue_work_metadata(command),
        "delivery_supported": True,
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "result_upload_supported": True,
        "execution_decision": execution_decision,
        "execution_decision_reason": execution_decision_reason,
        **poll_context,
    }


def _handle_delivered_command_poll(
    cfg,
    conn,
    *,
    method,
    remote,
    target_identity,
    target_id,
    command,
    queued_count,
    execution_supported,
    execution_decision,
    execution_decision_reason,
    poll_context,
):
    delivered = mark_command_delivered(
        cfg, command.get("id"), remote, target_identity=target_identity
    )
    payload = _delivered_command_payload(
        cfg, command, target_identity, execution_supported,
        execution_decision, execution_decision_reason,
    )
    body = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
    if method == "HEAD":
        body = b""
    send_http_response(
        conn,
        200,
        body,
        "application/json",
        headers=_delivered_command_response_headers(
            command, target_id, execution_supported
        ),
    )
    return details_with_target(
        cfg,
        _delivered_command_poll_details(
            cfg,
            method,
            remote,
            command,
            queued_count,
            delivered,
            execution_supported,
            execution_decision,
            execution_decision_reason,
            poll_context,
        ),
        target_identity,
    )


def _no_command_poll_payload(cfg, queued_count, execution_supported):
    return {
        "schema": 1,
        "status": "no-command",
        "queued_count": queued_count,
        "delivery_supported": False,
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "result_upload_supported": True,
        "message": "no queued command available; target poll recorded only",
    }


def _no_command_response_headers(queued_count, execution_supported):
    return {
        "X-griTTYkit-Command-Queue-Status": "no-command",
        "X-griTTYkit-Queued-Count": str(queued_count),
        "X-griTTYkit-Delivery-Supported": "no",
        "X-griTTYkit-Result-Upload-Supported": "yes",
        "X-griTTYkit-Execution-Supported": "yes" if execution_supported else "no",
        "X-griTTYkit-Executes-Commands": "yes" if execution_supported else "no",
    }


def _no_command_poll_details(
    cfg,
    *,
    method,
    remote,
    queued_count,
    execution_supported,
    poll_context,
):
    return {
        "operation": "command_queue_poll",
        "status": "no-command",
        "http_status": 204,
        "method": method,
        "remote_addr": remote,
        "queued_count": queued_count,
        "delivery_supported": False,
        "execution_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "result_upload_supported": True,
        **poll_context,
    }


def _handle_no_command_poll(
    cfg,
    conn,
    *,
    method,
    remote,
    queued_count,
    execution_supported,
    poll_context,
    target_identity,
):
    _no_command_poll_payload(cfg, queued_count, execution_supported)
    send_http_response(
        conn,
        204,
        b"",
        "application/json",
        headers=_no_command_response_headers(queued_count, execution_supported),
    )
    return details_with_target(
        cfg,
        _no_command_poll_details(
            cfg,
            method=method,
            remote=remote,
            queued_count=queued_count,
            execution_supported=execution_supported,
            poll_context=poll_context,
        ),
        target_identity,
    )


def handle_command_queue_poll(cfg, conn, method, target, headers, addr):
    remote = f"{addr[0]}:{addr[1]}"
    target_identity = target_identity_from_headers(headers)
    poll_context = _command_queue_poll_context(headers)
    if method not in {"GET", "HEAD"}:
        return _reject_command_queue_poll(
            cfg,
            conn,
            http_status=405,
            reason="command queue poll accepts only GET or HEAD",
            method=method,
            remote=remote,
            poll_context=poll_context,
            target_identity=target_identity,
        )
    parsed = urllib.parse.urlparse(target)
    if parsed.path not in {"/command-queue/poll", "/command-queue/poll/"}:
        return _reject_command_queue_poll(
            cfg,
            conn,
            http_status=404,
            reason="unknown command queue endpoint",
            method=method,
            remote=remote,
            poll_context=poll_context,
            target_identity=target_identity,
            detail_reason="unknown endpoint",
        )
    if not command_queue_token_valid(cfg, headers):
        return _reject_command_queue_poll(
            cfg,
            conn,
            http_status=403,
            reason="missing or invalid command queue token",
            method=method,
            remote=remote,
            poll_context=poll_context,
            target_identity=target_identity,
            detail_reason="invalid token",
        )
    queue = command_queue_summary(cfg)
    queued_count = int(queue.get("queued_count", 0) or 0)
    execution_supported, execution_decision, execution_decision_reason = (
        _command_queue_execution_context(cfg, queue)
    )
    target_id = str(target_identity.get("target_id") or "")
    queued = _queued_commands_for_target(queue, target_id)
    if queued:
        return _handle_delivered_command_poll(
            cfg,
            conn,
            method=method,
            remote=remote,
            target_identity=target_identity,
            target_id=target_id,
            command=queued[0],
            queued_count=queued_count,
            execution_supported=execution_supported,
            execution_decision=execution_decision,
            execution_decision_reason=execution_decision_reason,
            poll_context=poll_context,
        )
    return _handle_no_command_poll(
        cfg,
        conn,
        method=method,
        remote=remote,
        queued_count=queued_count,
        execution_supported=execution_supported,
        poll_context=poll_context,
        target_identity=target_identity,
    )

def _reject_command_queue_tls_listener(cfg, service, port):
    print("command-queue listener currently supports plain HTTP polling only; set command_queue_tls=no", file=sys.stderr)
    update_server_state(cfg, service, "error", {"port": port, "error": "plain HTTP polling requires command_queue_tls=no"})
    append_event(cfg, service, "bind_error", "error", details={"port": port, "error": "plain HTTP polling requires command_queue_tls=no"})


def _start_command_queue_listener_record(cfg, service, log_dir, port):
    SESSION_MANAGER.start_record(cfg, service, log_dir, details={"port": port, "tls": False})
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("Command queue poll listener. Delivers queued commands; target execution depends on explicit command queue policy.")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), "command_queue_file": str(command_queue_path(cfg))})


def _mark_command_queue_listening(cfg, service, log_dir, port):
    update_server_state(cfg, service, "listening", {"session_log": str(log_dir), "command_queue_file": str(command_queue_path(cfg))})
    append_event(cfg, service, "service_start", session=str(log_dir), details={"port": port, "tls": False})
    print_candidates(cfg, port)


def _record_command_queue_target_activity(cfg, service, log_dir, remote, metadata):
    target_rec = record_target_activity(cfg, metadata, service, session_id=log_dir.name)
    if not metadata.get("target_id"):
        return
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


def _record_command_queue_request_events(cfg, service, log_dir, remote, metadata):
    if metadata.get("operation") == "command_queue_result":
        append_command_queue_result_events(cfg, SESSION_MANAGER, service, log_dir, remote, metadata)
        print(f"command-queue result {metadata.get('status')}: id={metadata.get('command_id', '')}")
        return
    append_command_queue_poll_events(cfg, SESSION_MANAGER, service, log_dir, remote, metadata)
    queued_display = metadata.get("queued_count", metadata.get("queued_count_before", 0))
    print(f"command-queue poll {metadata.get('status')}: queued={queued_display}")


def _handle_command_queue_connection(cfg, service, log_dir, conn, addr):
    remote = f"{addr[0]}:{addr[1]}"
    metadata = {}
    try:
        with conn:
            append_event(cfg, service, "connection_open", session=str(log_dir), remote=remote)
            SESSION_MANAGER.update_record(log_dir, state="active", remote=remote)
            SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote)
            method, target, _version, headers, body = read_http_headers(conn)
            metadata = handle_command_queue_http(cfg, conn, method, target, headers, body, addr)
            _record_command_queue_target_activity(cfg, service, log_dir, remote, metadata)
            _record_command_queue_request_events(cfg, service, log_dir, remote, metadata)
    except Exception as exc:
        metadata = {"operation": "command_queue_poll", "status": "error", "reason": str(exc)}
        try:
            send_json_response(conn, 500, {"schema": 1, "status": "error", "reason": str(exc)})
        except Exception:
            pass
        print(f"command-queue poll failed: {exc}", file=sys.stderr)
        append_command_queue_poll_events(cfg, SESSION_MANAGER, service, log_dir, remote, metadata)
        append_event(cfg, service, "request_error", "error", session=str(log_dir), details={"error": str(exc)})
    finally:
        append_event(cfg, service, "connection_close", session=str(log_dir), remote=remote, details=metadata)


def _stop_command_queue_listener(cfg, service, log_dir, port):
    stop_reason = current_stop_reason("complete")
    update_server_state(cfg, service, "stopped", {
        "session_log": str(log_dir),
        "command_queue_file": str(command_queue_path(cfg)),
        "pid": "",
        "managed_by": "",
        "stopped_at": utc_now(),
        "stopped_reason": stop_reason,
    })
    SESSION_MANAGER.update_record(log_dir, state="ended", exit_reason=stop_reason)
    SESSION_MANAGER.upsert_state(cfg, log_dir, service, "ended", exit_reason=stop_reason)
    record_shutdown_event(cfg, service, session=log_dir)
    append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "reason": stop_reason})


def serve_command_queue(cfg, timeout, max_sessions=0):
    service = "command-queue"
    port = int(cfg.get("GRIT_COMMAND_QUEUE_PORT", "22205"))
    if yes(cfg.get("GRIT_COMMAND_QUEUE_TLS", "yes")):
        _reject_command_queue_tls_listener(cfg, service, port)
        return 2
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    _start_command_queue_listener_record(cfg, service, log_dir, port)
    sessions = 0
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 20)
        bound = True
        sock.settimeout(timeout)
        _mark_command_queue_listening(cfg, service, log_dir, port)
        while not SHUTDOWN.is_set():
            print("Waiting for command queue poll...")
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for command queue poll", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            _handle_command_queue_connection(cfg, service, log_dir, conn, addr)
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
            _stop_command_queue_listener(cfg, service, log_dir, port)
    return 0
