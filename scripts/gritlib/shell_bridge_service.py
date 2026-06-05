"""SSH, shell, and bridge service listeners for grit-console."""

import json
import os
import select
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from subprocess import run

from gritlib.bridge_routes import (
    bridge_profile_record,
    bridge_profile_service_name,
    bridge_profiles_path,
    load_bridge_profiles,
)
from gritlib.crypto import generate_tls_cert
from gritlib.event_log import append_event
from gritlib.operator_io import restore_interactive_tty, set_interactive_tty_raw
from gritlib.operator_network import print_candidates
from gritlib.service_runtime import (
    SESSION_MANAGER,
    SHUTDOWN,
    bind_listen_socket,
    current_shutdown_reason,
    current_stop_reason,
    pipe,
    record_shutdown_event,
    register_socket,
    register_thread,
    register_transport,
    unregister_socket,
    unregister_transport,
)
from gritlib.session_state import (
    atomic_write_json,
    mark_service_error,
    mark_service_stopped,
    update_server_state,
    utc_now,
)
from gritlib.ssh_keys import ensure_host_key, keys_equal, load_public_key
from gritlib.target_activity import record_selected_target_activity
from gritlib.target_commands import rshell_session_policy_record
from gritlib.target_records import details_with_target, selected_target_context
from gritlib.tls_io import recv_ssl_nonblocking, send_ssl_nonblocking

try:
    import paramiko
    HAVE_PARAMIKO = True
except ImportError:
    HAVE_PARAMIKO = False

class ReverseSSHServer(paramiko.ServerInterface if HAVE_PARAMIKO else object):
    def __init__(self, cfg, session_dir, authorized_key, forward_host, forward_port):
        self.cfg = cfg
        self.session_dir = session_dir
        self.authorized_key = authorized_key
        self.forward_host = forward_host
        self.forward_port = forward_port
        self.forward_requests = []
        self.transport = None
        self.listener = None
        self._listener_sock = None
        self._listener_thread = None

    def set_transport(self, transport):
        self.transport = transport

    def close(self):
        try:
            if self._listener_sock:
                self._listener_sock.close()
        except OSError:
            pass
        try:
            if self.transport:
                self.transport.close()
        except Exception:
            pass
        try:
            if self._listener_thread and self._listener_thread.is_alive():
                self._listener_thread.join(timeout=2.0)
        except RuntimeError:
            pass

    def check_auth_publickey(self, username, key):
        if keys_equal(self.authorized_key, key):
            print(f"SSH auth OK for {username}")
            return paramiko.AUTH_SUCCESSFUL
        print(f"SSH auth rejected for {username} (key mismatch)")
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "publickey"

    def check_port_forward_request(self, address, port):
        requested = int(port)
        if requested != int(self.forward_port):
            print(f"reject remote forward {address}:{port}; expected port {self.forward_port}")
            return False
        self.forward_requests.append((address, requested))
        self.start_forward_listener()
        print(f"Reverse SSH forward active: {address}:{requested}")
        print(f"Connect with: ssh -p {requested} root@127.0.0.1")
        append_event(
            self.cfg,
            "ssh",
            "reverse_forward_active",
            session=str(self.session_dir),
            details=details_with_target(self.cfg, {
                "requested_address": address,
                "requested_port": requested,
                "forward_host": str(self.forward_host),
                "GRIT_OPERATOR_REMOTE_FORWARD_PORT": int(self.forward_port),
            }),
        )
        return requested

    def check_channel_direct_tcpip_request(self, chanid, origin, destination):
        return paramiko.OPEN_SUCCEEDED

    def start_forward_listener(self):
        if self.listener is not None:
            return

        def run():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((str(self.forward_host), int(self.forward_port)))
                sock.listen(20)
            except OSError as exc:
                print(f"reverse-forward listener bind failed on {self.forward_host}:{self.forward_port}: {exc}", file=sys.stderr)
                append_event(
                    self.cfg,
                    "ssh",
                    "bind_error",
                    "error",
                    session=str(self.session_dir),
                    details={
                        "component": "reverse_forward_listener",
                        "listen_host": str(self.forward_host),
                        "port": int(self.forward_port),
                        "error": str(exc),
                    },
                )
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                return
            register_socket(sock)
            self._listener_sock = sock
            self.listener = sock
            try:
                while not SHUTDOWN.is_set() and self.transport and self.transport.is_active():
                    try:
                        sock.settimeout(2.0)
                        try:
                            local, origin = sock.accept()
                        except socket.timeout:
                            continue
                    except OSError:
                        break
                    try:
                        chan = self.transport.open_forwarded_tcpip_channel(
                            (origin[0], origin[1]),
                            (str(self.forward_host), int(self.forward_port)),
                        )
                    except Exception as exc:
                        print(f"forward channel failed: {exc}", file=sys.stderr)
                        local.close()
                        continue
                    register_socket(local)
                    register_transport(chan)
                    for src, dst, suffix in (
                        (local, chan, "local-to-channel"),
                        (chan, local, "channel-to-local"),
                    ):
                        thread = register_thread(threading.Thread(
                            target=pipe,
                            args=(src, dst),
                            name=f"grit-reverse-forward-pipe-{suffix}",
                        ))
                        thread.start()
            finally:
                unregister_socket(sock)
                try:
                    sock.close()
                except OSError:
                    pass
                self._listener_sock = None
                self.listener = None

        self._listener_thread = register_thread(threading.Thread(target=run, name="grit-reverse-forward"))
        self._listener_thread.start()


class _KexGuess2CompatTransport(paramiko.Transport if HAVE_PARAMIKO else object):
    """Paramiko Transport that handles Dropbear's KEXGUESS2 optimistic packet.

    Dropbear advertises kexguess2@matt.ucc.asn.au and sets kex_follows=True in
    its KEXINIT, meaning it speculatively sends its preferred-algorithm kex init
    packet immediately.  If the agreed algorithm differs from the client's first
    choice, that speculative packet must be silently discarded per RFC 4253 §7.1.
    Paramiko ignores kex_follows=True entirely, so we intercept it here.
    """

    def _really_parse_kex_init(self, m, ignore_first_byte=False):
        parsed = super()._really_parse_kex_init(m, ignore_first_byte=ignore_first_byte)
        real_algos = [
            a for a in parsed.get("kex_algo_list", [])
            if not a.startswith("kexguess2") and not a.startswith("ext-info")
            and not a.startswith("kex-strict")
        ]
        self._kexguess2_follows = parsed.get("kex_follows", False)
        self._kexguess2_client_first = real_algos[0] if real_algos else None
        return parsed

    def _parse_kex_init(self, m):
        super()._parse_kex_init(m)
        if not (self._kexguess2_follows and self.server_mode):
            return
        agreed = getattr(self.kex_engine, "name", None)
        if agreed == self._kexguess2_client_first:
            return  # guess was correct; no discard needed
        _original = self.kex_engine.parse_next
        _skipped = [False]

        def _skip_once(ptype, msg):
            if not _skipped[0]:
                _skipped[0] = True
                self._expect_packet(ptype)
                return
            return _original(ptype, msg)

        self.kex_engine.parse_next = _skip_once


def serve_ssh(cfg, timeout):
    service = "ssh"
    if not HAVE_PARAMIKO:
        print("Paramiko is required for SSH reverse-forward mode.", file=sys.stderr)
        print("Install python3-paramiko or use --transport tls-shell.", file=sys.stderr)
        return 2
    host_key = ensure_host_key(cfg["operator_host_key"])
    authorized = load_public_key(cfg["authorized_dbclient_pubkey"])
    log_dir = SESSION_MANAGER.log_dir(cfg, "ssh")
    target_ctx = selected_target_context(cfg)
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=details_with_target(cfg, {
        "GRIT_RSHELL_TRANSPORT": "ssh",
        "port": int(cfg["ssh_listen_port"]),
    }, target_ctx))
    if target_ctx:
        SESSION_MANAGER.update_record(log_dir, **target_ctx)
        SESSION_MANAGER.upsert_state(cfg, log_dir, service, "starting", **target_ctx)
        record_selected_target_activity(cfg, service, "listener", session_id=SESSION_MANAGER.session_id(log_dir))
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    update_server_state(cfg, service, "starting", {"session_log": str(log_dir)})
    sock = None
    transport = None
    server = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, cfg["ssh_listen_port"], 20)
        bound = True
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", details_with_target(cfg, {"session_log": str(log_dir)}, target_ctx))
        append_event(cfg, service, "service_start", session=str(log_dir), details=details_with_target(cfg, {"port": int(cfg["ssh_listen_port"])}, target_ctx))
        print_candidates(cfg, cfg["ssh_listen_port"])
        print(f"Authorized target key: {cfg['authorized_dbclient_pubkey']}")
        print("Waiting for dbclient reverse-forward connection...")
        try:
            client, addr = sock.accept()
        except socket.timeout:
            print("timeout waiting for reverse SSH connection", file=sys.stderr)
            return 1
        except OSError:
            if SHUTDOWN.is_set():
                return 0
            raise
        print(f"Connection from {addr[0]}:{addr[1]}")
        remote = f"{addr[0]}:{addr[1]}"
        SESSION_MANAGER.update_record(log_dir, state="active", remote=remote, **target_ctx)
        SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote, **target_ctx)
        record_selected_target_activity(cfg, service, "session", remote=remote, session_id=SESSION_MANAGER.session_id(log_dir))
        append_event(cfg, service, "connection_open", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))

        transport = register_transport(_KexGuess2CompatTransport(client))
        transport.add_server_key(host_key)
        # Pin to the one kex algorithm both Paramiko and the Dropbear build support.
        # Dropbear's first preference is sntrup761 (PQ hybrid), which Paramiko
        # doesn't implement, so we must pin to avoid an impossible negotiation.
        _sec = transport.get_security_options()
        _sec.kex = ("diffie-hellman-group14-sha256",)
        server = ReverseSSHServer(cfg, log_dir, authorized, cfg["forward_host"], cfg["GRIT_OPERATOR_REMOTE_FORWARD_PORT"])
        server.set_transport(transport)
        transport.start_server(server=server)
        while not SHUTDOWN.is_set() and transport.is_active():
            time.sleep(0.5)
        append_event(cfg, service, "connection_close", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))
    finally:
        if server:
            server.close()
        if transport:
            unregister_transport(transport)
            transport.close()
        if sock:
            unregister_socket(sock)
            try:
                sock.close()
            except OSError:
                pass
        if bound:
            stop_reason = current_stop_reason("complete")
            record_shutdown_event(cfg, service, session=log_dir)
            mark_service_stopped(cfg, service, stop_reason)
            SESSION_MANAGER.finish_record(cfg, service, log_dir, exit_reason=stop_reason)
            append_event(cfg, service, "service_stop", session=str(log_dir),
                         details=details_with_target(cfg, {"port": int(cfg["ssh_listen_port"]), "reason": stop_reason}, target_ctx))
    return 0


def relay_stdio(conn, log_dir=None, use_stdin=True, script_bytes=None, expect=None,
                session_timeout=None):
    """Relay from conn to stdout/log and optionally from stdin to conn."""
    scripted = script_bytes is not None
    stdin_interactive = bool(use_stdin and not scripted and sys.stdin.isatty())
    reason = "active"
    log_fp = None
    tty_state = None
    outbound = bytearray(script_bytes or b"")
    captured = bytearray()
    deadline = time.monotonic() + session_timeout if session_timeout else None
    if log_dir is not None:
        log_fp = (Path(log_dir) / "session.log").open("ab", buffering=0)
    if stdin_interactive:
        print("Shell connected. Ctrl-C to close.")
        tty_state = set_interactive_tty_raw()
    elif scripted:
        print("Shell connected. running scripted shell input.")
    else:
        print("Shell connected. stdin is non-interactive; receiving remote output only.")
    conn.setblocking(False)
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                reason = "session_timeout"
                break
            readers = [conn]
            if stdin_interactive:
                readers.append(sys.stdin)
            writers = [conn] if outbound else []
            try:
                timeout = 1.0
                if deadline is not None:
                    timeout = max(0.0, min(timeout, deadline - time.monotonic()))
                readable, writable, _ = select.select(readers, writers, [], timeout)
            except KeyboardInterrupt:
                reason = "keyboard_interrupt"
                break
            except (OSError, ValueError):
                reason = "socket_error"
                break

            socket_read_ready = conn in readable
            while socket_read_ready or getattr(conn, "pending", lambda: 0)() > 0:
                socket_read_ready = False
                data, err = recv_ssl_nonblocking(conn)
                if err == "want":
                    break
                if err is not None:
                    reason = "tls_error" if isinstance(err, ssl.SSLError) else "socket_error"
                    break
                if not data:
                    reason = "remote_eof"
                    break
                if log_fp:
                    log_fp.write(data)
                captured.extend(data)
                os.write(sys.stdout.fileno(), data)
                if getattr(conn, "pending", lambda: 0)() <= 0:
                    break
            if reason in ("tls_error", "socket_error", "remote_eof"):
                break

            if stdin_interactive and sys.stdin in readable:
                try:
                    data = os.read(sys.stdin.fileno(), 65536)
                except OSError:
                    reason = "stdin_eof"
                    break
                if not data:
                    reason = "stdin_eof"
                    break
                outbound.extend(data)

            if outbound and conn in writable:
                sent, err = send_ssl_nonblocking(conn, bytes(outbound))
                if err == "want":
                    continue
                if err == "remote_eof":
                    reason = "remote_eof"
                    break
                if err is not None:
                    reason = "tls_error" if isinstance(err, ssl.SSLError) else "socket_error"
                    break
                if sent > 0:
                    del outbound[:sent]
    finally:
        restore_interactive_tty(tty_state)
        if log_fp:
            log_fp.close()
        if log_dir is not None and expect is not None:
            expect_path = Path(log_dir) / "expectation"
            text = captured.decode("utf-8", errors="replace")
            if expect in text:
                expect_path.write_text("matched\n", encoding="utf-8")
            else:
                expect_path.write_text(f"missing: {expect}\n", encoding="utf-8")
                if reason in ("remote_eof", "stdin_eof", "active"):
                    reason = "expectation_missing"
        print(f"relay exit reason: {reason}", file=sys.stderr)
        if log_dir is not None:
            (Path(log_dir) / "exit-reason").write_text(reason + "\n", encoding="utf-8")
    return reason
















def serve_tls_shell(cfg, timeout, use_stdin=True, max_sessions=0, script_bytes=None,
                    expect=None, session_timeout=None):
    """TLS shell listener — accepts both builtin+tls and socat+tls targets."""
    service = "tls-shell"
    cert = Path(str(cfg["tls_cert"]))
    key = Path(str(cfg["tls_key"]))
    if not cert.is_file() or not key.is_file():
        print(f"TLS cert/key not found, generating: {cert}", file=sys.stderr)
        if not generate_tls_cert(cert, key):
            print(f"TLS cert/key generation failed — see {cert.parent}/openssl-generate.log", file=sys.stderr)
            print(f"Manual: openssl req -x509 -newkey rsa:2048 -keyout {key} -out {cert} -days 3650 -nodes -subj /CN=grit", file=sys.stderr)
            return 2
        print(f"Generated TLS cert/key: {cert}", file=sys.stderr)
    port = int(cfg["GRIT_RSHELL_SOCAT_PORT"])
    log_dir = SESSION_MANAGER.log_dir(cfg, "tls-shell")
    policy = rshell_session_policy_record(cfg)
    target_ctx = selected_target_context(cfg)
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=details_with_target(cfg, {
        "port": port,
        "tls": True,
        "session_policy": policy.get("session_policy", ""),
    }, target_ctx))
    if target_ctx:
        SESSION_MANAGER.update_record(log_dir, **target_ctx)
        SESSION_MANAGER.upsert_state(cfg, log_dir, service, "starting", **target_ctx)
        record_selected_target_activity(cfg, service, "listener", session_id=SESSION_MANAGER.session_id(log_dir))
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if hasattr(ssl, "TLSVersion"):
        context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    print(f"TLS shell listener — accepts builtin+tls and socat+tls transports")
    sessions = 0
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir)})
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 1)
        bound = True
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", details_with_target(cfg, {"session_log": str(log_dir)}, target_ctx))
        append_event(cfg, service, "service_start", session=str(log_dir), details=details_with_target(cfg, {"port": port, "session_policy": policy.get("session_policy", "")}, target_ctx))
        print_candidates(cfg, port)
        while not SHUTDOWN.is_set():
            print("Waiting for TLS shell connection...")
            try:
                raw, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for TLS shell connection", file=sys.stderr)
                (Path(log_dir) / "exit-reason").write_text("timeout\n", encoding="utf-8")
                print("relay exit reason: timeout", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            print(f"TLS connection from {addr[0]}:{addr[1]}")
            remote = f"{addr[0]}:{addr[1]}"
            SESSION_MANAGER.update_record(log_dir, state="active", remote=remote, **target_ctx)
            SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote, **target_ctx)
            record_selected_target_activity(cfg, service, "session", remote=remote, session_id=SESSION_MANAGER.session_id(log_dir))
            append_event(cfg, service, "shell_connected", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))
            try:
                with context.wrap_socket(raw, server_side=True) as conn:
                    reason = relay_stdio(conn, log_dir, use_stdin=use_stdin,
                                          script_bytes=script_bytes, expect=expect,
                                          session_timeout=session_timeout)
                    if expect is not None and reason == "expectation_missing":
                        return 1
            except ssl.SSLError as exc:
                print(f"TLS session failed: {exc}", file=sys.stderr)
                (Path(log_dir) / "exit-reason").write_text("tls_error\n", encoding="utf-8")
                append_event(cfg, service, "shell_error", "error", session=str(log_dir), remote=remote, details=details_with_target(cfg, {"error": str(exc)}, target_ctx))
            finally:
                exit_reason = SESSION_MANAGER.exit_reason(log_dir)
                sessions += 1
                SESSION_MANAGER.update_record(log_dir, state="listening", exit_reason=exit_reason, **target_ctx)
                SESSION_MANAGER.upsert_state(cfg, log_dir, service, "listening", remote=remote, exit_reason=exit_reason, **target_ctx)
                append_event(cfg, service, "shell_disconnected", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))
            if max_sessions > 0 and sessions >= max_sessions:
                print(f"Shell session ended; session_policy={policy.get('session_policy', '')} stops after first successful session.")
                append_event(cfg, service, "shell_listener_policy_stop", session=str(log_dir), details=details_with_target(cfg, {
                    "session_policy": policy.get("session_policy", ""),
                    "sessions": sessions,
                    "reason": "max_sessions",
                }, target_ctx))
                break
            print("Shell session ended; listener remains open for target retry/reconnect.")
    finally:
        if sock:
            unregister_socket(sock)
            try:
                sock.close()
            except OSError:
                pass
        if bound:
            stop_reason = SESSION_MANAGER.exit_reason(log_dir) or current_stop_reason("complete")
            record_shutdown_event(cfg, service, session=log_dir)
            mark_service_stopped(cfg, service, stop_reason)
            SESSION_MANAGER.finish_record(cfg, service, log_dir, exit_reason=stop_reason)
            append_event(cfg, service, "service_stop", session=str(log_dir),
                         details=details_with_target(cfg, {"port": port, "reason": stop_reason}, target_ctx))
    return 0


def serve_plain_shell(cfg, timeout, use_stdin=True, max_sessions=0, script_bytes=None,
                      expect=None, session_timeout=None):
    """Plaintext shell listener — debug/insecure; socat+none or builtin+none."""
    service = "plain-shell"
    port = int(cfg["GRIT_RSHELL_SOCAT_PORT"])
    print("WARNING: plain-shell is INSECURE and for debug use only!", file=sys.stderr)
    log_dir = SESSION_MANAGER.log_dir(cfg, "plain-shell")
    policy = rshell_session_policy_record(cfg)
    target_ctx = selected_target_context(cfg)
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=details_with_target(cfg, {
        "port": port,
        "tls": False,
        "session_policy": policy.get("session_policy", ""),
    }, target_ctx))
    if target_ctx:
        SESSION_MANAGER.update_record(log_dir, **target_ctx)
        SESSION_MANAGER.upsert_state(cfg, log_dir, service, "starting", **target_ctx)
        record_selected_target_activity(cfg, service, "listener", session_id=SESSION_MANAGER.session_id(log_dir))
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    sessions = 0
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir)})
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 1)
        bound = True
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", details_with_target(cfg, {"session_log": str(log_dir)}, target_ctx))
        append_event(cfg, service, "service_start", session=str(log_dir), details=details_with_target(cfg, {"port": port, "session_policy": policy.get("session_policy", "")}, target_ctx))
        print_candidates(cfg, port)
        while not SHUTDOWN.is_set():
            print("Waiting for plaintext shell connection (INSECURE)...")
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for plain shell connection", file=sys.stderr)
                (Path(log_dir) / "exit-reason").write_text("timeout\n", encoding="utf-8")
                print("relay exit reason: timeout", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            print(f"Plain connection from {addr[0]}:{addr[1]}")
            remote = f"{addr[0]}:{addr[1]}"
            SESSION_MANAGER.update_record(log_dir, state="active", remote=remote, **target_ctx)
            SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote, **target_ctx)
            record_selected_target_activity(cfg, service, "session", remote=remote, session_id=SESSION_MANAGER.session_id(log_dir))
            append_event(cfg, service, "shell_connected", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))
            with conn:
                reason = relay_stdio(conn, log_dir, use_stdin=use_stdin,
                                      script_bytes=script_bytes, expect=expect,
                                      session_timeout=session_timeout)
                if expect is not None and reason == "expectation_missing":
                    return 1
            sessions += 1
            SESSION_MANAGER.update_record(log_dir, state="listening", exit_reason=reason, **target_ctx)
            SESSION_MANAGER.upsert_state(cfg, log_dir, service, "listening", remote=remote, exit_reason=reason, **target_ctx)
            append_event(cfg, service, "shell_disconnected", session=str(log_dir), remote=remote, details=details_with_target(cfg, {}, target_ctx))
            if max_sessions > 0 and sessions >= max_sessions:
                print(f"Shell session ended; session_policy={policy.get('session_policy', '')} stops after first successful session.")
                append_event(cfg, service, "shell_listener_policy_stop", session=str(log_dir), details=details_with_target(cfg, {
                    "session_policy": policy.get("session_policy", ""),
                    "sessions": sessions,
                    "reason": "max_sessions",
                }, target_ctx))
                break
            print("Shell session ended; listener remains open for target retry/reconnect.")
    finally:
        if sock:
            unregister_socket(sock)
            try:
                sock.close()
            except OSError:
                pass
        if bound:
            stop_reason = SESSION_MANAGER.exit_reason(log_dir) or current_stop_reason("complete")
            record_shutdown_event(cfg, service, session=log_dir)
            mark_service_stopped(cfg, service, stop_reason)
            SESSION_MANAGER.finish_record(cfg, service, log_dir, exit_reason=stop_reason)
            append_event(cfg, service, "service_stop", session=str(log_dir),
                         details=details_with_target(cfg, {"port": port, "reason": stop_reason}, target_ctx))
    return 0


def bridge_relay(client, upstream, log_dir, session_timeout=0):
    sockets = [client, upstream]
    names = {client: "client", upstream: "upstream"}
    peers = {client: upstream, upstream: client}
    bytes_from_client = 0
    bytes_from_upstream = 0
    started = time.monotonic()
    reason = "complete"
    for sock in sockets:
        sock.setblocking(False)
    try:
        while sockets and not SHUTDOWN.is_set():
            if session_timeout and time.monotonic() - started >= session_timeout:
                reason = "timeout"
                break
            readable, _, _ = select.select(sockets, [], [], 0.25)
            if not readable:
                continue
            for sock in readable:
                try:
                    data = sock.recv(65536)
                except BlockingIOError:
                    continue
                except OSError:
                    reason = f"{names.get(sock, 'socket')}_error"
                    sockets = []
                    break
                if not data:
                    reason = f"{names.get(sock, 'socket')}_eof"
                    sockets = []
                    break
                if sock is client:
                    bytes_from_client += len(data)
                else:
                    bytes_from_upstream += len(data)
                try:
                    peers[sock].sendall(data)
                except OSError:
                    reason = f"{names.get(peers[sock], 'peer')}_error"
                    sockets = []
                    break
        if SHUTDOWN.is_set():
            reason = current_shutdown_reason() or "shutdown"
    finally:
        (Path(log_dir) / "bridge-result.json").write_text(json.dumps({
            "schema": 1,
            "reason": reason,
            "bytes_from_client": bytes_from_client,
            "bytes_from_upstream": bytes_from_upstream,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return reason, bytes_from_client, bytes_from_upstream


def serve_bridge(cfg, timeout, max_sessions=0, session_timeout=0):
    port = int(cfg.get("bridge_listen_port", 22206))
    dest_host = str(cfg.get("bridge_dest_host", "127.0.0.1"))
    dest_port = int(cfg.get("bridge_dest_port", 0))
    profile_name = str(cfg.get("bridge_profile") or "")
    service = bridge_profile_service_name(profile_name)
    bridge_route_path = ""
    if profile_name:
        try:
            profile = (load_bridge_profiles(cfg).get("profiles") or {}).get(profile_name) or {}
            bridge_route_path = str(bridge_profile_record(cfg, profile_name, profile).get("route_path") or "")
        except Exception:
            bridge_route_path = ""
    if dest_port <= 0:
        print("bridge: --bridge-dest-port is required", file=sys.stderr)
        mark_service_error(cfg, service, ValueError("missing bridge destination port"), {
            "listen_host": str(cfg.get("listen_host", "")),
            "port": port,
            "bridge_dest_host": dest_host,
            "bridge_dest_port": dest_port,
        })
        return 2
    log_dir = SESSION_MANAGER.log_dir(cfg, service)
    bridge_details = {
        "port": port,
        "bridge_dest_host": dest_host,
        "bridge_dest_port": dest_port,
        "bridge_profile": profile_name,
        "bridge_route_path": bridge_route_path,
    }
    SESSION_MANAGER.start_record(cfg, service, log_dir, details=bridge_details)
    (log_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"TCP bridge listener. Relaying {cfg['listen_host']}:{port} -> {dest_host}:{dest_port}")
    update_server_state(cfg, service, "starting", {"session_log": str(log_dir), **bridge_details})
    sessions = 0
    sock = None
    bound = False
    try:
        sock = bind_listen_socket(cfg, service, port, 20)
        bound = True
        sock.settimeout(timeout)
        update_server_state(cfg, service, "listening", {"session_log": str(log_dir), **bridge_details})
        append_event(cfg, service, "service_start", session=str(log_dir), details=bridge_details)
        record_selected_target_activity(
            cfg, service, "bridge_listener",
            details={**bridge_details, "status": "listening"},
            session_id=SESSION_MANAGER.session_id(log_dir),
        )
        print_candidates(cfg, port)
        while not SHUTDOWN.is_set():
            print("Waiting for bridge client...")
            try:
                client, addr = sock.accept()
            except socket.timeout:
                print("timeout waiting for bridge client", file=sys.stderr)
                return 1 if sessions == 0 else 0
            except OSError:
                if SHUTDOWN.is_set():
                    return 0
                raise
            remote = f"{addr[0]}:{addr[1]}"
            upstream = None
            metadata = {
                "operation": "bridge",
                "status": "error",
                "remote_addr": remote,
                "bridge_dest_host": dest_host,
                "bridge_dest_port": dest_port,
                "bridge_profile": profile_name,
            }
            register_socket(client)
            try:
                upstream = socket.create_connection((dest_host, dest_port), timeout=10)
                register_socket(upstream)
                metadata["status"] = "connected"
                append_event(cfg, service, "bridge_connected", session=str(log_dir), remote=remote, details=metadata)
                SESSION_MANAGER.update_record(log_dir, state="active", remote=remote)
                SESSION_MANAGER.upsert_state(cfg, log_dir, service, "active", remote=remote)
                reason, from_client, from_upstream = bridge_relay(client, upstream, log_dir, session_timeout=session_timeout or 0)
                metadata.update({
                    "status": "closed",
                    "reason": reason,
                    "bytes_from_client": from_client,
                    "bytes_from_upstream": from_upstream,
                    "bridge_route_path": bridge_route_path,
                })
                append_event(cfg, service, "bridge_closed", session=str(log_dir), remote=remote, details=metadata)
                record_selected_target_activity(
                    cfg, service, "bridge_relay", remote=remote, details=metadata,
                    session_id=SESSION_MANAGER.session_id(log_dir),
                )
                if profile_name:
                    data = load_bridge_profiles(cfg)
                    profile = data.get("profiles", {}).get(profile_name)
                    if isinstance(profile, dict):
                        profile["last_successful_relay_at"] = utc_now()
                        profile["last_bytes_from_client"] = from_client
                        profile["last_bytes_from_upstream"] = from_upstream
                        profile["updated_at"] = utc_now()
                        data["profiles"][profile_name] = profile
                        atomic_write_json(bridge_profiles_path(cfg), data)
                print(f"bridge closed: reason={reason} client_bytes={from_client} upstream_bytes={from_upstream}")
            except OSError as exc:
                metadata.update({"status": "error", "reason": str(exc), "bridge_route_path": bridge_route_path})
                append_event(cfg, service, "bridge_error", "error", session=str(log_dir), remote=remote, details=metadata)
                record_selected_target_activity(
                    cfg, service, "bridge_error", remote=remote, details=metadata,
                    session_id=SESSION_MANAGER.session_id(log_dir),
                )
                if profile_name:
                    data = load_bridge_profiles(cfg)
                    profile = data.get("profiles", {}).get(profile_name)
                    if isinstance(profile, dict):
                        now = utc_now()
                        profile["last_failure_at"] = now
                        profile["last_failure_reason"] = str(exc)
                        profile["last_failure_remote_addr"] = remote
                        profile["last_failure_dest_host"] = dest_host
                        profile["last_failure_dest_port"] = dest_port
                        profile["updated_at"] = now
                        data["profiles"][profile_name] = profile
                        atomic_write_json(bridge_profiles_path(cfg), data)
                print(f"bridge failed: {exc}", file=sys.stderr)
            finally:
                for s in (client, upstream):
                    if s is None:
                        continue
                    unregister_socket(s)
                    try:
                        s.close()
                    except OSError:
                        pass
                SESSION_MANAGER.update_record(log_dir, state="listening", exit_reason=metadata.get("reason", metadata.get("status", "")))
                SESSION_MANAGER.upsert_state(cfg, log_dir, service, "listening", remote=remote, exit_reason=metadata.get("reason", metadata.get("status", "")))
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
            stop_reason = current_stop_reason("complete")
            update_server_state(cfg, service, "stopped", {
                "session_log": str(log_dir),
                "bridge_dest_host": dest_host,
                "bridge_dest_port": dest_port,
                "bridge_profile": profile_name,
                "pid": "",
                "managed_by": "",
                "stopped_at": utc_now(),
                "stopped_reason": stop_reason,
            })
            SESSION_MANAGER.update_record(log_dir, state="ended", exit_reason=stop_reason)
            SESSION_MANAGER.upsert_state(cfg, log_dir, service, "ended", exit_reason=stop_reason)
            record_shutdown_event(cfg, service, session=log_dir)
            append_event(cfg, service, "service_stop", session=str(log_dir), details={"port": port, "reason": stop_reason})
    return 0
