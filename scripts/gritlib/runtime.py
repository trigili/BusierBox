"""Runtime ownership primitives for grit-console services and sessions."""

import socket
import subprocess
import threading


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
        socket_records = []
        for sock in sockets:
            rec = {"fileno": -1, "closed": True, "local": "", "peer": ""}
            try:
                rec["fileno"] = int(sock.fileno())
                rec["closed"] = rec["fileno"] < 0
            except (OSError, AttributeError, TypeError, ValueError):
                pass
            if not rec["closed"]:
                try:
                    local = sock.getsockname()
                    rec["local"] = ":".join(str(part) for part in local[:2]) if isinstance(local, tuple) else str(local)
                except OSError:
                    pass
                try:
                    peer = sock.getpeername()
                    rec["peer"] = ":".join(str(part) for part in peer[:2]) if isinstance(peer, tuple) else str(peer)
                except OSError:
                    pass
            socket_records.append(rec)
        thread_records = []
        for thread in threads:
            thread_records.append({
                "name": getattr(thread, "name", ""),
                "ident": getattr(thread, "ident", None),
                "alive": bool(thread.is_alive()),
                "daemon": bool(getattr(thread, "daemon", False)),
            })
        child_records = []
        for proc in children:
            try:
                poll = proc.poll()
            except Exception:
                poll = None
            child_records.append({
                "pid": getattr(proc, "pid", None),
                "running": poll is None,
                "returncode": poll,
            })
        transport_records = []
        for transport in transports:
            active = ""
            try:
                active = bool(transport.is_active())
            except Exception:
                active = ""
            transport_records.append({
                "type": transport.__class__.__name__,
                "active": active,
            })
        return {
            "schema": 1,
            "shutdown_requested": bool(self.shutdown_event.is_set()),
            "shutdown_reason": self.shutdown_reason() or "",
            "socket_count": len(socket_records),
            "open_socket_count": sum(1 for rec in socket_records if not rec.get("closed")),
            "transport_count": len(transport_records),
            "active_transport_count": sum(1 for rec in transport_records if rec.get("active") is True),
            "thread_count": len(thread_records),
            "alive_thread_count": sum(1 for rec in thread_records if rec.get("alive")),
            "child_process_count": len(child_records),
            "running_child_process_count": sum(1 for rec in child_records if rec.get("running")),
            "sockets": socket_records,
            "transports": transport_records,
            "threads": thread_records,
            "child_processes": child_records,
        }


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
