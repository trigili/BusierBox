"""Runtime ownership primitives for grit-console services and sessions."""

import socket
import subprocess
import threading

from gritlib.runtime_snapshot import runtime_snapshot_document


class Service:
    def __init__(self, name, port=None, tls=False, pid=None, state="configured"):
        self.name = name
        self.port = port
        self.tls = tls
        self.pid = pid
        self.state = state

    def as_dict(self):
        return {
            "name": self.name,
            "port": self.port,
            "tls": self.tls,
            "pid": self.pid,
            "state": self.state,
        }


class Session:
    def __init__(self, session_id, service, path, state="starting", remote=""):
        self.session_id = session_id
        self.service = service
        self.path = str(path)
        self.state = state
        self.remote = remote

    def as_dict(self):
        return {
            "session_id": self.session_id,
            "service": self.service,
            "path": self.path,
            "state": self.state,
            "remote": self.remote,
        }


class ServiceManager:
    """Runtime owner for sockets/transports so shutdown is one explicit path."""

    def __init__(self, shutdown_event=None, sockets=None, transports=None, shutdown_reason=None):
        self.shutdown_event = shutdown_event or threading.Event()
        self.sockets = sockets if sockets is not None else []
        self.transports = transports if transports is not None else []
        self.shutdown_reason = shutdown_reason or (lambda: "")
        self.service_threads = []
        self.child_processes = []
        self._lock = threading.Lock()

    def register_thread(self, thread):
        with self._lock:
            if thread not in self.service_threads:
                self.service_threads.append(thread)
        return thread

    def register_socket(self, sock):
        with self._lock:
            if sock not in self.sockets:
                self.sockets.append(sock)
        return sock

    def unregister_socket(self, sock):
        with self._lock:
            try:
                self.sockets.remove(sock)
            except ValueError:
                pass

    def register_transport(self, transport):
        with self._lock:
            if transport not in self.transports:
                self.transports.append(transport)
        return transport

    def unregister_transport(self, transport):
        with self._lock:
            try:
                self.transports.remove(transport)
            except ValueError:
                pass

    def register_child_process(self, proc):
        with self._lock:
            if proc not in self.child_processes:
                self.child_processes.append(proc)
        return proc

    def start_child_process(self, cmd, **kwargs):
        return self.register_child_process(subprocess.Popen(cmd, **kwargs))

    def unregister_child_process(self, proc):
        with self._lock:
            try:
                self.child_processes.remove(proc)
            except ValueError:
                pass

    def shutdown(self):
        self.shutdown_event.set()
        for transport in list(self.transports):
            try:
                transport.close()
            except Exception:
                pass
        for sock in list(self.sockets):
            try:
                sock.close()
            except OSError:
                pass
        for proc in list(self.child_processes):
            if proc.poll() is not None:
                self.unregister_child_process(proc)
                continue
            try:
                proc.terminate()
            except OSError:
                pass
        current = threading.current_thread()
        for thread in list(self.service_threads):
            if thread is current or not thread.is_alive():
                continue
            try:
                thread.join(timeout=2.0)
            except RuntimeError:
                pass

    def snapshot(self):
        with self._lock:
            sockets = list(self.sockets)
            transports = list(self.transports)
            threads = list(self.service_threads)
            children = list(self.child_processes)
        return runtime_snapshot_document(
            sockets,
            transports,
            threads,
            children,
            self.shutdown_event.is_set(),
            self.shutdown_reason(),
        )


def relay_pipe(src, dst, service_manager):
    """Relay data from src to dst and unregister both ends when done."""
    try:
        while True:
            try:
                data = src.recv(65536)
            except Exception:
                break
            if not data:
                break
            try:
                dst.sendall(data)
            except Exception:
                break
    finally:
        for obj in (src, dst):
            service_manager.unregister_socket(obj)
            service_manager.unregister_transport(obj)
            try:
                obj.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            try:
                obj.close()
            except Exception:
                pass
