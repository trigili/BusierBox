"""Operator network discovery helpers for grit-console."""

import ipaddress
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


def sorted_local_ips(ips):
    def _key(ip):
        text = str(ip or "")
        try:
            parsed = ipaddress.ip_address(text)
            return (parsed.version, int(parsed), text)
        except ValueError:
            return (9, text, text)

    return sorted(_dedupe_local_ips(ips), key=_key)


def first_sorted_local_ip(ips=None):
    candidates = sorted_local_ips(local_ips() if ips is None else ips)
    return candidates[0] if candidates else ""


def local_ip_choice_candidates(ips=None):
    return sorted_local_ips(local_ips() if ips is None else ips)


def choose_operator_host_for_target(
    cfg,
    *,
    input_func=None,
    interactive=False,
    candidates_func=local_ip_choice_candidates,
):
    if str((cfg or {}).get("GRIT_OPERATOR_SERVER_HOST") or "").strip():
        return str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "")
    if not interactive:
        return ""
    candidates = list(candidates_func() or [])
    if len(candidates) > 1:
        print("Multiple local IPs — which should the target use to POST results back?")
        print("")
        for i, ip in enumerate(candidates, 1):
            print(f"  {i}  {ip}")
        print("  o  Other (enter manually)")
        print("")
        if input_func:
            choice_line = input_func(f"  Select (1-{len(candidates)}, o, or enter for {candidates[0]})> ")
        else:
            choice_line = ""
        choice = (choice_line or "").strip()
        if not choice:
            cfg["GRIT_OPERATOR_SERVER_HOST"] = candidates[0]
        elif choice.lower() == "o":
            other = (input_func("  IP address> ") if input_func else "") or ""
            other = other.strip()
            if other:
                cfg["GRIT_OPERATOR_SERVER_HOST"] = other
        elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
            cfg["GRIT_OPERATOR_SERVER_HOST"] = candidates[int(choice) - 1]
        print(f"  Using: {cfg.get('GRIT_OPERATOR_SERVER_HOST', candidates[0])}")
        print("")
    elif len(candidates) == 1:
        cfg["GRIT_OPERATOR_SERVER_HOST"] = candidates[0]
    return str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "")


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
    return first_sorted_local_ip() or "OPERATOR_IP"


def operator_advertised_host(cfg, host=None, fallback="OPERATOR_IP"):
    text = str(host or "").strip()
    if text:
        return text
    configured = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "").strip()
    if configured:
        return configured
    return first_sorted_local_ip() or fallback


def print_candidates(cfg, port, advertised_host=None, advertised_port=None):
    bind_host = str(cfg.get("listen_host") or "0.0.0.0")
    advertised = operator_advertised_host(cfg, host=advertised_host)
    target_port = int(advertised_port or port)
    print(f"Listening on {bind_host}:{port}")
    print(f"Advertised target endpoint: {advertised}:{target_port}")
    candidates = []
    configured = str(cfg.get("GRIT_OPERATOR_SERVER_HOST") or "").strip()
    if configured:
        candidates.append(configured)
    for ip in sorted_local_ips(local_ips()):
        if ip not in candidates:
            candidates.append(ip)
    if candidates:
        print("Candidate target connect-back hosts:")
        for ip in candidates:
            marker = "  *" if ip == advertised else "   "
            print(f"{marker} {ip}:{target_port}")
    else:
        print("Candidate target connect-back hosts: unable to infer local IPs")
