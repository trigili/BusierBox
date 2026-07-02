"""Line-console network display helpers."""

import socket

from gritlib.operator_network import local_ip_choice_candidates, sorted_local_ips


def line_local_ip_candidates(snap=None):
    candidates = sorted_local_ips((snap or {}).get("local_ips") or [])
    return candidates or local_ip_choice_candidates()


def line_ip_usage_text():
    return "usage:\n  ip host N\n  ip host IP\n  ip bind N\n  ip bind IP\n  ips"


def print_line_local_ips(snap):
    candidates = line_local_ip_candidates(snap)
    print("Local IPs:")
    if candidates:
        for idx, ip in enumerate(candidates, 1):
            print(f"  {idx}  {ip}")
    else:
        try:
            addrs = set()
            for info in socket.getaddrinfo(socket.gethostname(), None):
                addr = info[4][0]
                if not addr.startswith("127.") and addr != "::1":
                    addrs.add(addr)
            for idx, addr in enumerate(sorted(addrs), 1):
                print(f"  {idx}  {addr}")
        except Exception:
            print("  (could not determine local IPs)")
    print("  use:")
    print("    ip host N   advertise this IP in commands run on the target")
    print("    ip host IP  advertise a manually entered IP")
    print("    ip bind N   bind operator listeners to this IP")
    print("    ip bind IP  bind operator listeners to a manually entered IP")
    print("  If the address you need is missing, use ip host IP or ip bind IP directly.")


def parse_line_ip_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd != "ip":
        return {}
    action = str(args[0]).strip().lower() if args else "show"
    if action in {"show", "list", "ls", "ips"}:
        return {"action": "show"}
    if action in {"host", "operator", "advertise", "use"}:
        return {"action": "set-host", "selector": " ".join(args[1:]).strip()}
    if action in {"bind", "listen", "listener"}:
        return {"action": "set-bind", "selector": " ".join(args[1:]).strip()}
    return {"action": "usage"}


def _resolve_ip_selector(selector, candidates):
    selector = str(selector or "").strip()
    if not selector:
        raise ValueError(line_ip_usage_text())
    if selector.isdigit():
        idx = int(selector) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
        raise ValueError(f"no IP at row {selector} - run: ips")
    return selector


def dispatch_line_ip_command(
    ip_cmd,
    *,
    snap_func=None,
    print_ips_func=None,
    set_option_func=None,
):
    action = (ip_cmd or {}).get("action")
    snap = snap_func() if snap_func else {}
    candidates = line_local_ip_candidates(snap)
    if action == "show":
        if print_ips_func:
            return print_ips_func(snap)
        return print_line_local_ips(snap)
    if action in {"set-host", "set-bind"} and set_option_func:
        key = "GRIT_OPERATOR_SERVER_HOST" if action == "set-host" else "listen_host"
        value = _resolve_ip_selector(ip_cmd.get("selector", ""), candidates)
        return set_option_func(key, value)
    print(line_ip_usage_text())
    return None
