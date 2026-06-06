"""Reverse SSH local forward listener helpers for grit-console."""

import socket
import sys
import threading

from gritlib.event_log import append_event
from gritlib.service_runtime import (
    SHUTDOWN,
    pipe,
    register_socket,
    register_thread,
    register_transport,
    unregister_socket,
)
from gritlib.target_records import details_with_target


class ReverseForwardListener:
    """Owns the local listener used to service an accepted reverse SSH forward."""

    def __init__(self, cfg, session_dir, forward_host, forward_port, transport_func):
        self.cfg = cfg
        self.session_dir = session_dir
        self.forward_host = forward_host
        self.forward_port = forward_port
        self.transport_func = transport_func
        self.listener = None
        self.listener_sock = None
        self.listener_thread = None

    def close(self):
        try:
            if self.listener_sock:
                self.listener_sock.close()
        except OSError:
            pass
        try:
            if self.listener_thread and self.listener_thread.is_alive():
                self.listener_thread.join(timeout=2.0)
        except RuntimeError:
            pass

    def active_details(self, requested_address, requested_port):
        return details_with_target(self.cfg, {
            "requested_address": requested_address,
            "requested_port": requested_port,
            "forward_host": str(self.forward_host),
            "GRIT_OPERATOR_REMOTE_FORWARD_PORT": int(self.forward_port),
        })

    def record_bind_error(self, sock, exc):
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

    def open_socket(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((str(self.forward_host), int(self.forward_port)))
            sock.listen(20)
        except OSError as exc:
            self.record_bind_error(sock, exc)
            return None
        register_socket(sock)
        self.listener_sock = sock
        self.listener = sock
        return sock

    def accept_connection(self, sock):
        try:
            sock.settimeout(2.0)
            try:
                return sock.accept()
            except socket.timeout:
                return None, None
        except OSError:
            return None, "closed"

    def open_channel(self, local, origin):
        transport = self.transport_func()
        try:
            return transport.open_forwarded_tcpip_channel(
                (origin[0], origin[1]),
                (str(self.forward_host), int(self.forward_port)),
            )
        except Exception as exc:
            print(f"forward channel failed: {exc}", file=sys.stderr)
            local.close()
            return None

    def start_pipe_threads(self, local, chan):
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

    def run(self):
        sock = self.open_socket()
        if sock is None:
            return
        try:
            transport = self.transport_func()
            while not SHUTDOWN.is_set() and transport and transport.is_active():
                local, origin = self.accept_connection(sock)
                if origin is None:
                    transport = self.transport_func()
                    continue
                if origin == "closed":
                    break
                chan = self.open_channel(local, origin)
                if chan is None:
                    transport = self.transport_func()
                    continue
                self.start_pipe_threads(local, chan)
                transport = self.transport_func()
        finally:
            unregister_socket(sock)
            try:
                sock.close()
            except OSError:
                pass
            self.listener_sock = None
            self.listener = None

    def start(self):
        if self.listener is not None:
            return
        self.listener_thread = register_thread(threading.Thread(target=self.run, name="grit-reverse-forward"))
        self.listener_thread.start()
