"""TLS socket I/O helpers for grit-console."""

import ssl


def recv_ssl_nonblocking(conn):
    try:
        return conn.recv(65536), None
    except ssl.SSLWantReadError:
        return None, "want"
    except ssl.SSLWantWriteError:
        return None, "want"
    except ssl.SSLZeroReturnError:
        return b"", None
    except ssl.SSLError as exc:
        return None, exc
    except OSError as exc:
        return None, exc


def send_ssl_nonblocking(conn, data):
    try:
        return conn.send(data), None
    except ssl.SSLWantReadError:
        return 0, "want"
    except ssl.SSLWantWriteError:
        return 0, "want"
    except ssl.SSLZeroReturnError:
        return 0, "remote_eof"
    except ssl.SSLError as exc:
        return 0, exc
    except OSError as exc:
        return 0, exc
