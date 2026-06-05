"""Shared service runtime state and shutdown helpers for grit-console."""

import atexit
import signal
import socket
import sys
import threading

from gritlib.event_log import append_event
from gritlib.process_status import pid_process_record, port_listener_pids
from gritlib.runtime import ServiceManager, relay_pipe
from gritlib.session_state import SessionManager, mark_service_error


class ServiceRuntimeState:
    """Resettable owner for process-wide service runtime state."""

    def __init__(self):
        self.shutdown_event = threading.Event()
        self.shutdown_reason = ""
        self.owned_sockets = []
        self.owned_transports = []
        self.recorded_shutdowns = set()

    def current_stop_reason(self, default="complete"):
        return self.shutdown_reason or default

    def current_shutdown_reason(self):
        return self.shutdown_reason

    def request_shutdown(self, reason="shutdown"):
        if reason and not self.shutdown_reason:
            self.shutdown_reason = reason

    def shutdown_recorded(self, service, session=None):
        key = (service, str(session or ""), self.shutdown_reason)
        if key in self.recorded_shutdowns:
            return True
        self.recorded_shutdowns.add(key)
        return False

    def reset(self, *, shutdown_reason="", shutdown_requested=False):
        self.shutdown_reason = str(shutdown_reason or "")
        self.recorded_shutdowns.clear()
        self.owned_sockets.clear()
        self.owned_transports.clear()
        if shutdown_requested:
            self.shutdown_event.set()
        else:
            self.shutdown_event.clear()


RUNTIME_STATE = ServiceRuntimeState()
SHUTDOWN = RUNTIME_STATE.shutdown_event
OWNED_SOCKETS = RUNTIME_STATE.owned_sockets
OWNED_TRANSPORTS = RUNTIME_STATE.owned_transports
RECORDED_SHUTDOWNS = RUNTIME_STATE.recorded_shutdowns


SERVICE_MANAGER = ServiceManager(
    SHUTDOWN,
    OWNED_SOCKETS,
    OWNED_TRANSPORTS,
    shutdown_reason=RUNTIME_STATE.current_shutdown_reason,
)
SESSION_MANAGER = SessionManager()


def pipe(src, dst):
    return relay_pipe(src, dst, SERVICE_MANAGER)


def current_stop_reason(default="complete"):
    return RUNTIME_STATE.current_stop_reason(default)


def current_shutdown_reason():
    return RUNTIME_STATE.current_shutdown_reason()


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
    RUNTIME_STATE.request_shutdown(reason)
    close_registered_resources()


def reset_service_runtime_state(*, shutdown_reason="", shutdown_requested=False, close_resources=False):
    """Reset process-wide runtime state for focused tests."""
    if close_resources:
        close_registered_resources()
    RUNTIME_STATE.reset(
        shutdown_reason=shutdown_reason,
        shutdown_requested=shutdown_requested,
    )
    with SERVICE_MANAGER._lock:
        SERVICE_MANAGER.service_threads.clear()
        SERVICE_MANAGER.child_processes.clear()


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
    if RUNTIME_STATE.shutdown_recorded(service, session=session):
        return
    append_event(cfg, service, "shutdown", session=str(session) if session else None, details={"reason": reason})
