"""Process and listener inspection helpers for grit-console."""

import os
import socket
import sys
from pathlib import Path

from gritlib.session_state import state_file_path


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    try:
        fields = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8", errors="replace").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    except (OSError, ValueError, TypeError):
        pass
    return True


def pid_cmdline(pid):
    try:
        raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except (OSError, ValueError, TypeError):
        return ""


def pid_comm(pid):
    try:
        return Path(f"/proc/{int(pid)}/comm").read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError, TypeError):
        return ""


def pid_exe(pid):
    try:
        return os.readlink(f"/proc/{int(pid)}/exe")
    except (OSError, ValueError, TypeError):
        return ""


def pid_process_record(pid):
    return {
        "pid": int(pid),
        "process_name": pid_comm(pid),
        "exe": pid_exe(pid),
        "cmdline": pid_cmdline(pid),
    }


def pid_cmdline_args(pid):
    try:
        raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
        return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
    except (OSError, ValueError, TypeError):
        return []


def pid_environ_contains(pid, key, expected):
    try:
        raw = Path(f"/proc/{int(pid)}/environ").read_bytes()
    except (OSError, ValueError, TypeError):
        return False
    prefix = (str(key) + "=").encode("utf-8")
    expected_bytes = str(expected).encode("utf-8")
    for part in raw.split(b"\0"):
        if part.startswith(prefix) and part[len(prefix):] == expected_bytes:
            return True
    return False


def paths_equivalent(left, right):
    if not left or not right:
        return False
    if str(left) == str(right):
        return True
    try:
        return Path(str(left)).expanduser().resolve(strict=False) == Path(str(right)).expanduser().resolve(strict=False)
    except OSError:
        return False


def cmdline_option_matches_path(args, option, expected):
    if not expected:
        return False
    for idx, arg in enumerate(args):
        if arg == option and idx + 1 < len(args) and paths_equivalent(args[idx + 1], expected):
            return True
        prefix = option + "="
        if arg.startswith(prefix) and paths_equivalent(arg[len(prefix):], expected):
            return True
    return False


def cmdline_looks_like_grit_server(args):
    return any(Path(arg).name == "grit-console" or "grit-console" in arg for arg in args)


def managed_server_evidence(pid, cfg=None, rec=None):
    try:
        pid_text = str(int(pid))
    except (ValueError, TypeError):
        return []
    if pid_text == str(os.getpid()) and Path(sys.argv[0]).name == "grit-console":
        return ["current-process"]
    args = pid_cmdline_args(pid)
    if not cmdline_looks_like_grit_server(args):
        return []
    evidence = ["cmdline:grit-console"]
    cfg = cfg or {}
    rec = rec if isinstance(rec, dict) else {}
    state_candidates = [
        str(state_file_path(cfg)) if cfg else "",
        str(rec.get("state_file", "")),
        str(rec.get("server_state", "")),
    ]
    config_candidates = [
        str(cfg.get("_config_path", "")) if cfg else "",
        str(rec.get("config_path", "")),
    ]
    if any(cmdline_option_matches_path(args, "--state-file", candidate) for candidate in state_candidates):
        evidence.append("state-file")
    if any(cmdline_option_matches_path(args, "--config", candidate) for candidate in config_candidates):
        evidence.append("config")
    # A legacy direct listener may only have the config path on its command line.
    # Require at least one path-level match for another process.
    if len(evidence) == 1:
        return []
    return evidence


def pid_is_managed_server(pid, cfg=None, rec=None):
    return bool(managed_server_evidence(pid, cfg=cfg, rec=rec))


def proc_socket_address(hexaddr, family):
    try:
        raw = bytes.fromhex(hexaddr)
    except ValueError:
        return hexaddr
    try:
        if family in {"tcp", "udp"}:
            return socket.inet_ntop(socket.AF_INET, raw[::-1])
        if family in {"tcp6", "udp6"}:
            # Linux /proc/net/tcp6 stores each 32-bit word little-endian.
            chunks = [raw[pos:pos + 4][::-1] for pos in range(0, len(raw), 4)]
            return socket.inet_ntop(socket.AF_INET6, b"".join(chunks))
    except OSError:
        return hexaddr
    return hexaddr


def socket_inode_pids(inodes):
    wanted = {str(inode) for inode in inodes if inode}
    if not wanted:
        return {}
    found = {inode: [] for inode in wanted}
    proc = Path("/proc")
    for pid_dir in proc.iterdir() if proc.is_dir() else []:
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        try:
            for fd in fd_dir.iterdir():
                try:
                    target_link = os.readlink(fd)
                except OSError:
                    continue
                if target_link.startswith("socket:["):
                    inode = target_link[8:-1]
                    if inode in wanted:
                        found.setdefault(inode, []).append(int(pid_dir.name))
        except OSError:
            continue
    return {inode: sorted(set(pids)) for inode, pids in found.items()}


def listener_endpoints(port, protocol="tcp"):
    entries = []
    target = f"{int(port):04X}"
    if protocol == "udp":
        tables = (("/proc/net/udp", "udp"), ("/proc/net/udp6", "udp6"))
        listen_states = None
    else:
        tables = (("/proc/net/tcp", "tcp"), ("/proc/net/tcp6", "tcp6"))
        listen_states = {"0A"}
    for table, family in tables:
        path = Path(table)
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="ascii", errors="ignore").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            cols = line.split()
            if len(cols) > 9 and cols[1].rsplit(":", 1)[-1].upper() == target and (listen_states is None or cols[3] in listen_states):
                host_hex, port_hex = cols[1].rsplit(":", 1)
                entries.append({
                    "family": family,
                    "protocol": protocol,
                    "address": proc_socket_address(host_hex, family),
                    "port": int(port_hex, 16),
                    "inode": cols[9],
                })
    inode_pids = socket_inode_pids([entry["inode"] for entry in entries])
    for entry in entries:
        pids = inode_pids.get(entry["inode"], [])
        entry["pids"] = pids
        entry["processes"] = [pid_process_record(pid) for pid in pids]
    return entries


def port_listener_pids(port):
    pids = []
    for endpoint in listener_endpoints(port):
        pids.extend(endpoint.get("pids", []))
    return sorted(set(pids))


def address_values(host):
    if not host:
        return set()
    value = str(host)
    if value in ("0.0.0.0", "::"):
        return {value}
    values = {value}
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(value, None):
            if family in (socket.AF_INET, socket.AF_INET6) and sockaddr:
                values.add(str(sockaddr[0]))
    except OSError:
        pass
    return values


def endpoint_matches_bind_address(bind_address, endpoint_address):
    bind_values = address_values(bind_address)
    endpoint_values = address_values(endpoint_address)
    if not bind_values:
        return True
    if bind_values.intersection({"0.0.0.0", "::"}):
        return True
    if endpoint_values.intersection({"0.0.0.0", "::"}):
        return True
    return bool(bind_values & endpoint_values)


def matching_listener_endpoints(host, port, protocol="tcp"):
    return [
        endpoint for endpoint in listener_endpoints(port, protocol=protocol)
        if endpoint_matches_bind_address(host, endpoint.get("address", ""))
    ]


def port_listening(host, port, protocol="tcp"):
    return bool(matching_listener_endpoints(host, port, protocol=protocol))
