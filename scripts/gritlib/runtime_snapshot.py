"""Snapshot helpers for grit-console runtime-owned resources."""


def socket_snapshot_records(sockets):
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
    return socket_records


def thread_snapshot_records(threads):
    thread_records = []
    for thread in threads:
        thread_records.append({
            "name": getattr(thread, "name", ""),
            "ident": getattr(thread, "ident", None),
            "alive": bool(thread.is_alive()),
            "daemon": bool(getattr(thread, "daemon", False)),
        })
    return thread_records


def child_process_snapshot_records(children):
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
    return child_records


def transport_snapshot_records(transports):
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
    return transport_records


def runtime_snapshot_document(sockets, transports, threads, children, shutdown_requested, shutdown_reason):
    socket_records = socket_snapshot_records(sockets)
    transport_records = transport_snapshot_records(transports)
    thread_records = thread_snapshot_records(threads)
    child_records = child_process_snapshot_records(children)
    return {
        "schema": 1,
        "shutdown_requested": bool(shutdown_requested),
        "shutdown_reason": shutdown_reason or "",
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
