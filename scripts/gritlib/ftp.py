"""Small FTP protocol helpers for grit-console probe serving."""

import socket


def ftp_send_line(conn, text):
    conn.sendall((text.rstrip("\r\n") + "\r\n").encode("utf-8", errors="replace"))


def ftp_recv_line(conn):
    data = bytearray()
    while len(data) < 8192:
        chunk = conn.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if data.endswith(b"\n"):
            break
    return data.decode("utf-8", errors="replace").strip()


def ftp_pasv_reply_host(host, fallback_hosts=None):
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        candidates = list(fallback_hosts or [])
        return candidates[0] if candidates else "127.0.0.1"
