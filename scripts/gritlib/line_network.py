"""Line-console network display helpers."""

import socket

from gritlib.operator_network import sorted_local_ips


def print_line_local_ips(snap):
    candidates = sorted_local_ips((snap or {}).get("local_ips") or [])
    print("Local IPs:")
    if candidates:
        for ip in candidates:
            print(f"  {ip}")
    else:
        try:
            addrs = set()
            for info in socket.getaddrinfo(socket.gethostname(), None):
                addr = info[4][0]
                if not addr.startswith("127.") and addr != "::1":
                    addrs.add(addr)
            for addr in sorted(addrs):
                print(f"  {addr}")
        except Exception:
            print("  (could not determine local IPs)")
    print("  use: set GRIT_OPERATOR_SERVER_HOST <IP>  to configure")
