"""Operator network discovery helpers for grit-console."""

import os
import socket
import threading
import time


LOCAL_IPS_SLOW_LOOKUP_SEC = float(os.environ.get("GRIT_LOCAL_IPS_SLOW_LOOKUP_SEC", "0.25"))
LOCAL_IPS_SLOW_CACHE_SEC = float(os.environ.get("GRIT_LOCAL_IPS_SLOW_CACHE_SEC", "60"))
LOCAL_IPS_CACHE = {
    "until": 0.0,
    "hostname_ips": [],
    "slow": False,
}
LOCAL_IPS_CACHE_LOCK = threading.Lock()


def _dedupe_local_ips(ips):
    out = []
    seen = set()
    for ip in ips:
        if ip and not ip.startswith("127.") and ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def _hostname_ipv4_addrs():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    return _dedupe_local_ips(ips)


def _cached_hostname_ips(now):
    with LOCAL_IPS_CACHE_LOCK:
        if LOCAL_IPS_CACHE["slow"] and now < LOCAL_IPS_CACHE["until"]:
            return list(LOCAL_IPS_CACHE["hostname_ips"])
    return None


def _store_hostname_ips(ips, slow=False):
    until = time.monotonic() + LOCAL_IPS_SLOW_CACHE_SEC if slow else 0.0
    with LOCAL_IPS_CACHE_LOCK:
        LOCAL_IPS_CACHE["hostname_ips"] = list(ips)
        LOCAL_IPS_CACHE["slow"] = bool(slow)
        LOCAL_IPS_CACHE["until"] = until


def local_ips():
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ips.append(sock.getsockname()[0])
    except OSError:
        pass

    now = time.monotonic()
    cached = _cached_hostname_ips(now)
    if cached is not None:
        return _dedupe_local_ips(ips + cached)

    result = []

    def lookup():
        result.extend(_hostname_ipv4_addrs())

    worker = threading.Thread(target=lookup)
    worker.daemon = True
    worker.start()
    worker.join(max(0.0, LOCAL_IPS_SLOW_LOOKUP_SEC))
    if worker.is_alive():
        _store_hostname_ips([], slow=True)
        return _dedupe_local_ips(ips)
    _store_hostname_ips(result, slow=False)
    return _dedupe_local_ips(ips + result)


def target_visible_host(host, cfg, fallback_host=None):
    text = str(host or "").strip()
    if text and text.lower() not in ("operator", "localhost", "0.0.0.0", "::"):
        return text
    fallback = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or fallback_host or cfg.get("listen_host") or "").strip()
    if fallback and fallback not in ("0.0.0.0", "::"):
        return fallback
    candidates = local_ips()
    return candidates[0] if candidates else "OPERATOR_IP"


def operator_advertised_host(cfg, host=None, fallback="OPERATOR_IP"):
    text = str(host or "").strip()
    if text:
        return text
    configured = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "").strip()
    if configured:
        return configured
    candidates = local_ips()
    return candidates[0] if candidates else fallback
