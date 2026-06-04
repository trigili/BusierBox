"""Shared service runtime state and shutdown helpers for grit-console."""

import atexit
import itertools
import signal
import socket
import sys
import threading

from gritlib.event_log import append_event
from gritlib.process_status import pid_process_record, port_listener_pids
from gritlib.runtime import ServiceManager, relay_pipe
from gritlib.session_state import SessionManager, mark_service_error


SHUTDOWN = threading.Event()
SHUTDOWN_REASON = ""
OWNED_SOCKETS = []
OWNED_TRANSPORTS = []
RECORDED_SHUTDOWNS = set()
EVENT_COUNTER = itertools.count(1)


SERVICE_MANAGER = ServiceManager(
    SHUTDOWN,
    OWNED_SOCKETS,
    OWNED_TRANSPORTS,
    shutdown_reason=lambda: SHUTDOWN_REASON,
)
SESSION_MANAGER = SessionManager()


def pipe(src, dst):
    return relay_pipe(src, dst, SERVICE_MANAGER)


def current_stop_reason(default="complete"):
    return SHUTDOWN_REASON or default


def current_shutdown_reason():
    return SHUTDOWN_REASON


def register_socket(sock):
    return SERVICE_MANAGER.register_socket(sock)


def unregister_socket(sock):
    SERVICE_MANAGER.unregister_socket(sock)


def register_transport(transport):
    return SERVICE_MANAGER.register_transport(transport)


def unregister_transport(transport):
    SERVICE_MANAGER.unregister_transport(transport)


def register_thread(thread):
    return SERVICE_MANAGER.register_thread(thread)


def start_child_process(cmd, **kwargs):
    return SERVICE_MANAGER.start_child_process(cmd, **kwargs)


def close_registered_resources():
    SERVICE_MANAGER.shutdown()


def request_shutdown(reason="shutdown"):
    global SHUTDOWN_REASON
    if reason and not SHUTDOWN_REASON:
        SHUTDOWN_REASON = reason
    close_registered_resources()


def _signal_shutdown(signum, _frame):
    try:
        signame = signal.Signals(signum).name
    except ValueError:
        signame = str(signum)
    request_shutdown(signame)


def install_shutdown_handlers():
    atexit.register(close_registered_resources)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_shutdown)
        except (OSError, ValueError):
            pass


def bind_listen_socket(cfg, service, port, backlog):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(cfg["listen_host"]), int(port)))
        sock.listen(backlog)
        register_socket(sock)
        return sock
    except OSError as exc:
        try:
            sock.close()
        except OSError:
            pass
        owners = [pid_process_record(pid) for pid in port_listener_pids(port)]
        mark_service_error(
            cfg,
            service,
            exc,
            {"listen_host": str(cfg["listen_host"]), "port": int(port), "owners": owners},
            event_name="bind_error",
        )
        print(f"{service}: unable to bind {cfg['listen_host']}:{port}: {exc}", file=sys.stderr)
        if owners:
            print("possible listener owners:", file=sys.stderr)
            for owner in owners:
                details = []
                if owner.get("process_name"):
                    details.append(f"process={owner.get('process_name')}")
                if owner.get("exe"):
                    details.append(f"exe={owner.get('exe')}")
                if owner.get("cmdline"):
                    details.append(f"cmdline={owner.get('cmdline')}")
                print(f"  pid={owner['pid']} {' '.join(details)}", file=sys.stderr)
        print("Run: scripts/grit-console --status", file=sys.stderr)
        print("Or stop managed listeners with: scripts/grit-console --stop", file=sys.stderr)
        raise


def record_shutdown_event(cfg, service, session=None):
    reason = current_shutdown_reason()
    if not reason:
        return
    key = (service, str(session or ""), reason)
    if key in RECORDED_SHUTDOWNS:
        return
    RECORDED_SHUTDOWNS.add(key)
    append_event(cfg, service, "shutdown", session=str(session) if session else None, details={"reason": reason})
