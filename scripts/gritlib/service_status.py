"""Service status, resource, and index helpers for grit-console."""

import os
from pathlib import Path
import sys
import time

from gritlib.command_copy import command_copy_path
from gritlib.command_queue import command_queue_path
from gritlib.config_utils import yes
from gritlib.process_status import (
    endpoint_matches_bind_address, listener_endpoints, managed_server_evidence,
    pid_alive, pid_process_record,
)
from gritlib.record_utils import (
    int_value, record_count_by_key, records_by_bool, records_by_composite,
    records_by_key,
)
from gritlib.session_state import read_json_file, state_file_path
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged, staged_file_path
from gritlib.target_records import targets_path


DEFAULT_CONFIG = Path("local/server-config.json")
DAEMON_SERVICE_CHOICES = (
    "ssh", "tls-shell", "plain-shell", "file-service", "command-queue",
    "bridge", "probe", "probe-tftp", "probe-ftp", "probe-dns",
)


def resolve_transport(cfg, args_transport=None):
    """Map --transport flag and config fields to a canonical service action."""
    if args_transport:
        transport = args_transport
        if transport == "ssh-reverse":
            transport = "ssh"
        elif transport in {"socat-tls", "builtin-tls"}:
            transport = "tls-shell"
        return transport

    if yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_ENABLE", "no")):
        return "file-service"
    transport = cfg.get("GRIT_RSHELL_TRANSPORT", "ssh")
    encryption = cfg.get("GRIT_RSHELL_ENCRYPTION", "tls")
    if transport == "ssh":
        return "ssh"
    if encryption == "tls":
        return "tls-shell"
    return "plain-shell"


def configured_daemon_services(cfg, explicit=None):
    services = []
    for service in explicit or []:
        if service not in DAEMON_SERVICE_CHOICES:
            raise ValueError(f"unsupported daemon service: {service}")
        services.append(service)
    if not services:
        if yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_ENABLE", "no")):
            services.append("file-service")
        if yes(cfg.get("GRIT_COMMAND_QUEUE_ENABLE", "no")):
            services.append("command-queue")
        if yes(cfg.get("bridge_enable", "no")):
            services.append("bridge")
        if yes(cfg.get("probe_enable", "no")):
            services.append("probe")
        if yes(cfg.get("probe_tftp_enable", "no")):
            services.append("probe-tftp")
        if yes(cfg.get("probe_ftp_enable", "no")):
            services.append("probe-ftp")
        if yes(cfg.get("probe_dns_enable", "no")):
            services.append("probe-dns")
        if yes(cfg.get("rshell_enable", "no")):
            services.append(resolve_transport(cfg))
    return list(dict.fromkeys(services))


def daemon_child_command(cfg, service, executable=None, script_path=None, default_config=DEFAULT_CONFIG):
    command = [str(executable or sys.executable), str(Path(script_path or sys.argv[0]).resolve())]
    command.extend(["--config", str(cfg.get("_config_path", default_config))])
    command.extend(["--state-file", str(state_file_path(cfg))])
    command.extend(["--staged-file", str(staged_file_path(cfg))])
    command.extend(["--command-queue-file", str(command_queue_path(cfg))])
    command.extend(["--command-copy-file", str(command_copy_path(cfg))])
    command.extend(["--targets-file", str(targets_path(cfg))])
    command.extend(["--listen-host", str(cfg.get("listen_host", "0.0.0.0"))])
    if service in ("tls-shell", "plain-shell"):
        command.extend(["--shell-port", str(cfg.get("GRIT_RSHELL_SOCAT_PORT", 22203))])
    if service == "ssh":
        command.extend(["--ssh-port", str(cfg.get("ssh_listen_port", 22202))])
        command.extend(["--forward-port", str(cfg.get("GRIT_OPERATOR_REMOTE_FORWARD_PORT", 2200))])
    if service == "file-service":
        command.extend(["--file-port", str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204))])
        command.extend(["--file-service-tls", str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes"))])
    if service == "command-queue":
        command.extend(["--command-queue-port", str(cfg.get("GRIT_COMMAND_QUEUE_PORT", 22205))])
    if service == "bridge":
        command.extend(["--bridge-port", str(cfg.get("bridge_listen_port", 22206))])
        command.extend(["--bridge-dest-host", str(cfg.get("bridge_dest_host", "127.0.0.1"))])
        command.extend(["--bridge-dest-port", str(cfg.get("bridge_dest_port", 0))])
    if service == "probe":
        command.extend(["--probe-port", str(cfg.get("GRIT_PROBE_PORT", 22207))])
        command.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-tftp":
        command.extend(["--probe-tftp-port", str(cfg.get("GRIT_PROBE_TFTP_PORT", 22208))])
        command.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-ftp":
        command.extend(["--probe-ftp-port", str(cfg.get("GRIT_PROBE_FTP_PORT", 22209))])
        command.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-dns":
        command.extend(["--probe-dns-port", str(cfg.get("GRIT_PROBE_DNS_PORT", 22210))])
        command.extend(["--probe-dns-name", str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit"))])
        command.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    command.extend(["--transport", service])
    command.extend(["--managed-by", "operator-daemon"])
    return command


def operator_daemon_headless_command(cfg, services, timeout=None, default_config=DEFAULT_CONFIG):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--daemon",
    ]
    for service in configured_daemon_services(cfg, services):
        parts.extend(["--daemon-service", service])
    if timeout is not None:
        parts.extend(["--timeout", str(timeout)])
    return " ".join(shquote(part) for part in parts)


def operator_stop_headless_command(cfg, default_config=DEFAULT_CONFIG):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --stop"
    )


def service_start_headless_command(cfg, service, argv_extra=None, default_config=DEFAULT_CONFIG):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--transport",
        str(service or ""),
        "--state-file",
        str(state_file_path(cfg)),
        "--staged-file",
        str(staged_file_path(cfg)),
    ]
    if service == "file-service":
        parts.extend(["--file-service-tls", str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes"))])
    if service == "probe":
        parts.extend(["--probe-port", str(cfg.get("GRIT_PROBE_PORT", 22207))])
        parts.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-tftp":
        parts.extend(["--probe-tftp-port", str(cfg.get("GRIT_PROBE_TFTP_PORT", 22208))])
        parts.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-ftp":
        parts.extend(["--probe-ftp-port", str(cfg.get("GRIT_PROBE_FTP_PORT", 22209))])
        parts.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-dns":
        parts.extend(["--probe-dns-port", str(cfg.get("GRIT_PROBE_DNS_PORT", 22210))])
        parts.extend(["--probe-dns-name", str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit"))])
        parts.extend(["--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if argv_extra:
        parts.extend(str(item) for item in argv_extra)
    return " ".join(shquote(part) for part in parts)


def service_stop_headless_command(cfg, service, default_config=DEFAULT_CONFIG):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --stop-service "
        + shquote(str(service or ""))
    )


def run_service_workflow_action_headless_command(
    cfg, action_id, dry_run=False, confirmed=False, default_config=DEFAULT_CONFIG
):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--run-service-workflow-action",
        str(action_id or ""),
    ]
    if dry_run:
        parts.append("--service-workflow-dry-run")
    if confirmed:
        parts.append("--confirm-service-workflow-action")
    return " ".join(shquote(str(part)) for part in parts)


def service_tls_enabled(cfg, service):
    if service == "tls-shell":
        return True
    if service == "file-service":
        return yes(str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes")))
    if service == "command-queue":
        return yes(str(cfg.get("GRIT_COMMAND_QUEUE_TLS", "yes")))
    return False


def service_port(cfg, service):
    if service == "ssh":
        return int(cfg.get("ssh_listen_port", 22202))
    if service in {"tls-shell", "plain-shell"}:
        return int(cfg.get("GRIT_RSHELL_SOCAT_PORT", 22203))
    if service == "file-service":
        return int(cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204))
    if service == "command-queue":
        return int(cfg.get("GRIT_COMMAND_QUEUE_PORT", 22205))
    if service == "bridge":
        return int(cfg.get("bridge_listen_port", 22206))
    if service == "probe":
        return int(cfg.get("GRIT_PROBE_PORT", 22207))
    if service == "probe-tftp":
        return int(cfg.get("GRIT_PROBE_TFTP_PORT", 22208))
    if service == "probe-ftp":
        return int(cfg.get("GRIT_PROBE_FTP_PORT", 22209))
    if service == "probe-dns":
        return int(cfg.get("GRIT_PROBE_DNS_PORT", 22210))
    return 0


def wait_service_port_released(cfg, service, pid=None, timeout=3.0):
    port = service_port(cfg, service)
    if not port:
        deadline = time.time() + max(timeout, 8.0)
        while time.time() < deadline:
            if not pid or not pid_alive(pid):
                return True
            time.sleep(0.05)
        return not pid or not pid_alive(pid)
    deadline = time.time() + timeout
    protocol = "udp" if service in {"probe-tftp", "probe-dns"} else "tcp"
    while time.time() < deadline:
        endpoints = listener_endpoints(port, protocol=protocol)
        if not endpoints:
            return True
        time.sleep(0.05)
    return not listener_endpoints(port, protocol=protocol)


def raw_service_snapshot(cfg):
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    services = {}
    for name in DAEMON_SERVICE_CHOICES:
        port = service_port(cfg, name)
        bind_address = str(cfg.get("listen_host", ""))
        protocol = "udp" if name in {"probe-tftp", "probe-dns"} else "tcp"
        endpoints = listener_endpoints(port, protocol=protocol)
        matching_endpoints = [
            endpoint for endpoint in endpoints
            if endpoint_matches_bind_address(bind_address, endpoint.get("address", ""))
        ]
        listener_pids = sorted({pid for endpoint in endpoints for pid in endpoint.get("pids", [])})
        matching_listener_pids = sorted({pid for endpoint in matching_endpoints for pid in endpoint.get("pids", [])})
        services[name] = {
            "port": port,
            "protocol": protocol,
            "bind_address": bind_address,
            "listening": bool(matching_endpoints),
            "listener_endpoints": endpoints,
            "matching_listener_endpoints": matching_endpoints,
            "listener_pids": listener_pids,
            "matching_listener_pids": matching_listener_pids,
            "state": (state.get("services") or {}).get(name, {}),
        }
    return {"state": state, "staged": load_staged(cfg).get("staged", {}), "services": services}


def service_status_rows(cfg):
    snap = raw_service_snapshot(cfg)
    rows = []
    for name, info in snap["services"].items():
        rec = dict(info["state"])
        pid = rec.get("pid")
        ownership_evidence = managed_server_evidence(pid, cfg=cfg, rec=rec) if pid else []
        actual = "listening" if info["listening"] else "stopped"
        stale = bool(rec.get("status") == "listening" and not info["listening"])
        session_log = str(rec.get("session_log", "") or "")
        process_log = str(rec.get("process_log", "") or "")
        row = {
            "name": name,
            "port": info["port"],
            "protocol": info.get("protocol", "tcp"),
            "bind_address": rec.get("listen_host") or info.get("bind_address") or str(cfg.get("listen_host", "")),
            "tls": service_tls_enabled(cfg, name),
            "actual": actual,
            "configured": rec.get("status", "unknown"),
            "pid": pid or "",
            "pid_alive": pid_alive(pid) if pid else False,
            "pid_managed": bool(ownership_evidence),
            "ownership_evidence": ownership_evidence,
            "listener_pids": info.get("listener_pids", []),
            "matching_listener_pids": info.get("matching_listener_pids", []),
            "listener_endpoints": info.get("listener_endpoints", []),
            "matching_listener_endpoints": info.get("matching_listener_endpoints", []),
            "listener_processes": [pid_process_record(listener_pid) for listener_pid in info.get("listener_pids", [])],
            "stale": stale,
            "error": rec.get("error", ""),
            "stopped_at": rec.get("stopped_at", ""),
            "stopped_reason": rec.get("stopped_reason", ""),
            "owners": rec.get("owners", []),
            "session_log": session_log,
            "session_log_exists": Path(session_log).exists() if session_log else False,
            "process_log": process_log,
            "process_log_exists": Path(process_log).exists() if process_log else False,
            "listener_bind_mismatch": bool(info.get("listener_endpoints")) and not bool(info.get("matching_listener_endpoints")),
        }
        for key in (
            "url", "target_command", "target_route", "route_kind", "route_host",
            "route_port", "bridge_profile", "bridge_route_path", "requires_bridge",
        ):
            if rec.get(key) not in (None, ""):
                row[key] = rec.get(key)
        rows.append(row)
    return rows


def service_manager_resource_records(snapshot):
    records = []
    for idx, rec in enumerate(snapshot.get("sockets") or []):
        records.append({
            "id": f"socket:{idx}",
            "kind": "socket",
            "state": "closed" if rec.get("closed") else "open",
            "active": not bool(rec.get("closed")),
            "fileno": rec.get("fileno", -1),
            "local": rec.get("local", ""),
            "peer": rec.get("peer", ""),
            "pid": os.getpid(),
        })
    for idx, rec in enumerate(snapshot.get("transports") or []):
        active = rec.get("active")
        records.append({
            "id": f"transport:{idx}",
            "kind": "transport",
            "state": "active" if active is True else ("inactive" if active is False else "unknown"),
            "active": active is True,
            "transport_type": rec.get("type", ""),
            "pid": os.getpid(),
        })
    for idx, rec in enumerate(snapshot.get("threads") or []):
        alive = bool(rec.get("alive"))
        records.append({
            "id": f"thread:{idx}",
            "kind": "thread",
            "state": "alive" if alive else "stopped",
            "active": alive,
            "thread_name": rec.get("name", ""),
            "thread_ident": rec.get("ident", ""),
            "daemon": bool(rec.get("daemon", False)),
            "pid": os.getpid(),
        })
    for idx, rec in enumerate(snapshot.get("child_processes") or []):
        running = bool(rec.get("running"))
        records.append({
            "id": f"child_process:{idx}",
            "kind": "child_process",
            "state": "running" if running else "exited",
            "active": running,
            "pid": rec.get("pid", ""),
            "returncode": rec.get("returncode", ""),
        })
    return records


def service_manager_resource_indexes(records):
    return {
        "service_manager_resources_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "service_manager_resources_by_kind": records_by_key(records, "kind"),
        "service_manager_resources_by_state": records_by_key(records, "state"),
        "service_manager_resources_by_active": records_by_key(records, "active"),
        "service_manager_resources_by_pid": records_by_key(records, "pid"),
        "service_manager_resources_by_kind_state": records_by_composite(records, ("kind", "state")),
        "service_manager_resources_by_kind_active": records_by_composite(records, ("kind", "active")),
    }


def service_manager_status(snapshot):
    resources = service_manager_resource_records(snapshot)
    state_record = {
        "id": "service-manager",
        "shutdown_requested": bool(snapshot.get("shutdown_requested", False)),
        "socket_count": int_value(snapshot.get("socket_count", 0)),
        "open_socket_count": int_value(snapshot.get("open_socket_count", 0)),
        "transport_count": int_value(snapshot.get("transport_count", 0)),
        "active_transport_count": int_value(snapshot.get("active_transport_count", 0)),
        "thread_count": int_value(snapshot.get("thread_count", 0)),
        "alive_thread_count": int_value(snapshot.get("alive_thread_count", 0)),
        "child_process_count": int_value(snapshot.get("child_process_count", 0)),
        "running_child_process_count": int_value(snapshot.get("running_child_process_count", 0)),
        "resource_count": len(resources),
    }
    state_record.update({
        "has_open_sockets": state_record.get("open_socket_count", 0) > 0,
        "has_active_transports": state_record.get("active_transport_count", 0) > 0,
        "has_alive_threads": state_record.get("alive_thread_count", 0) > 0,
        "has_running_children": state_record.get("running_child_process_count", 0) > 0,
        "has_resources": state_record.get("resource_count", 0) > 0,
    })
    state_records = [state_record]
    state_index_maps = {
        "service_manager_state_records_by_id": {
            rec.get("id", ""): rec for rec in state_records if rec.get("id")
        },
        "service_manager_state_records_by_shutdown_requested": records_by_key(
            state_records, "shutdown_requested"
        ),
        "service_manager_state_records_by_has_open_sockets": records_by_key(
            state_records, "has_open_sockets"
        ),
        "service_manager_state_records_by_has_active_transports": records_by_key(
            state_records, "has_active_transports"
        ),
        "service_manager_state_records_by_has_alive_threads": records_by_key(
            state_records, "has_alive_threads"
        ),
        "service_manager_state_records_by_has_running_children": records_by_key(
            state_records, "has_running_children"
        ),
        "service_manager_state_records_by_has_resources": records_by_key(
            state_records, "has_resources"
        ),
    }
    return {
        "resources": resources,
        "resource_index_maps": service_manager_resource_indexes(resources),
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def service_record_indexes(records):
    by_actual = {}
    by_configured = {}
    by_port = {}
    by_pid = {}
    by_listener_pid = {}
    by_bind_address = {}
    by_stopped_reason = {}
    by_tls = records_by_bool(records, "tls")
    by_stale = records_by_bool(records, "stale")
    by_pid_alive = records_by_bool(records, "pid_alive")
    by_pid_managed = records_by_bool(records, "pid_managed")
    by_listener_bind_mismatch = records_by_bool(records, "listener_bind_mismatch")
    by_session_log_exists = records_by_bool(records, "session_log_exists")
    by_process_log_exists = records_by_bool(records, "process_log_exists")
    by_has_error = {"yes": [], "no": []}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        actual = str(rec.get("actual") or "")
        configured = str(rec.get("configured") or "")
        bind_address = str(rec.get("bind_address") or "")
        port = rec.get("port")
        pid = str(rec.get("pid") or "")
        if actual:
            by_actual.setdefault(actual, []).append(rec)
        if configured:
            by_configured.setdefault(configured, []).append(rec)
        if bind_address:
            by_bind_address.setdefault(bind_address, []).append(rec)
        if port not in (None, ""):
            by_port.setdefault(str(port), []).append(rec)
        if pid:
            by_pid.setdefault(pid, []).append(rec)
        stopped_reason = str(rec.get("stopped_reason") or "")
        if stopped_reason:
            by_stopped_reason.setdefault(stopped_reason, []).append(rec)
        for listener_pid in rec.get("listener_pids") or []:
            if listener_pid not in (None, ""):
                by_listener_pid.setdefault(str(listener_pid), []).append(rec)
        by_has_error["yes" if rec.get("error") else "no"].append(rec)
    return (
        by_actual, by_configured, by_bind_address, by_port, by_pid,
        by_listener_pid, by_tls, by_stale, by_pid_alive, by_pid_managed,
        by_listener_bind_mismatch, by_session_log_exists,
        by_process_log_exists, by_has_error, by_stopped_reason,
    )


def status_summary_and_warnings(services):
    summary = {
        "service_count": len(services),
        "listening_count": 0,
        "configured_listening_count": 0,
        "error_count": 0,
        "stale_count": 0,
        "listener_pid_count": 0,
    }
    warnings = []

    def warning_context(row):
        return {
            "service": row.get("name", ""),
            "port": row.get("port", 0),
            "bind_address": row.get("bind_address", ""),
            "configured": row.get("configured", ""),
            "actual": row.get("actual", ""),
            "pid": row.get("pid", ""),
            "pid_alive": row.get("pid_alive", False),
            "pid_managed": row.get("pid_managed", False),
            "ownership_evidence": row.get("ownership_evidence") or [],
            "listener_pids": row.get("listener_pids") or [],
            "matching_listener_pids": row.get("matching_listener_pids") or [],
            "listener_endpoints": row.get("listener_endpoints") or [],
            "matching_listener_endpoints": row.get("matching_listener_endpoints") or [],
            "process_log": row.get("process_log", ""),
            "session_log": row.get("session_log", ""),
            "error": row.get("error", ""),
            "owners": row.get("owners") or [],
        }

    for row in services:
        if row.get("actual") == "listening":
            summary["listening_count"] += 1
            if row.get("configured") not in ("listening", "starting"):
                warnings.append({**warning_context(row),
                    "type": "unexpected_listener",
                    "message": "actual listener was found but configured state does not say the service is listening",
                    "suggested_action": "inspect the listener PID and run scripts/grit-console --stop if it is managed",
                })
        if row.get("listener_bind_mismatch"):
            warnings.append({**warning_context(row),
                "type": "listener_bind_mismatch",
                "message": "a listener was found on the configured port, but not on the configured bind address",
                "suggested_action": "inspect listener address/PID ownership before treating the service as active",
            })
        if row.get("configured") == "listening":
            summary["configured_listening_count"] += 1
        if row.get("configured") == "error" or row.get("error"):
            summary["error_count"] += 1
            message = row.get("error", "service is marked error")
            if row.get("owners"):
                message = f"unable to bind/listen: {message}"
            warnings.append({**warning_context(row),
                "type": "service_error",
                "message": message,
                "suggested_action": "scripts/grit-console --status or scripts/grit-console --stop",
            })
        if row.get("stale"):
            summary["stale_count"] += 1
            warnings.append({**warning_context(row),
                "type": "stale_state",
                "message": "configured state says listening, but no actual listener was found",
                "suggested_action": "scripts/grit-console --stop",
            })
        if row.get("pid") and row.get("pid_alive") and not row.get("pid_managed"):
            warnings.append({**warning_context(row),
                "type": "unmanaged_recorded_pid",
                "message": "recorded PID is alive but does not have matching griTTYkit ownership evidence",
                "suggested_action": "inspect the PID before editing server-state.json or stopping it manually",
            })
        summary["listener_pid_count"] += len(row.get("listener_pids") or [])
    return summary, warnings


def service_workflow_action_indexes(records):
    return {
        "service_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "service_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "service_workflow_actions_by_service": records_by_key(records, "service"),
        "service_workflow_actions_by_category": records_by_key(records, "category"),
        "service_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "service_workflow_actions_by_actual": records_by_key(records, "actual"),
        "service_workflow_actions_by_configured": records_by_key(records, "configured"),
        "service_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "service_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "service_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "service_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "service_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "service_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "service_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "service_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "service_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "service_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "service_workflow_actions_by_available": records_by_key(records, "available"),
        "service_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "service_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "service_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "service_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "service_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "service_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
        "service_workflow_actions_by_has_error": records_by_key(records, "has_error"),
        "service_workflow_actions_by_has_warnings": records_by_key(records, "has_warnings"),
    }


def service_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "service_counts": record_count_by_key(records, "service"),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "configured_counts": record_count_by_key(records, "configured"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
        "has_error_counts": record_count_by_key(records, "has_error"),
        "has_warnings_counts": record_count_by_key(records, "has_warnings"),
    }


def port_record_indexes(records):
    by_number = {}
    by_service = {}
    by_actual = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        port = rec.get("port")
        service = str(rec.get("service") or "")
        actual = str(rec.get("actual") or "")
        if port not in (None, ""):
            by_number.setdefault(str(port), []).append(rec)
        if service:
            by_service.setdefault(service, []).append(rec)
        if actual:
            by_actual.setdefault(actual, []).append(rec)
    return by_number, by_service, by_actual


def port_records_from_services(records):
    ports = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        port = rec.get("port")
        if port in (None, ""):
            continue
        ports.append({
            "service": rec.get("name", ""),
            "port": port,
            "protocol": rec.get("protocol", "tcp"),
            "bind_address": rec.get("bind_address", ""),
            "tls": rec.get("tls", False),
            "configured": rec.get("configured", ""),
            "actual": rec.get("actual", ""),
            "pid": rec.get("pid", ""),
            "pid_alive": rec.get("pid_alive", False),
            "pid_managed": rec.get("pid_managed", False),
            "listener_pids": rec.get("listener_pids") or [],
            "listener_endpoints": rec.get("listener_endpoints") or [],
            "stale": rec.get("stale", False),
            "error": rec.get("error", ""),
        })
    return ports
