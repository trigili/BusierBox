"""Service start/stop lifecycle helpers for grit-console."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from gritlib.event_log import append_event
from gritlib.process_status import managed_server_evidence, pid_alive
from gritlib.service_status import (
    DEFAULT_CONFIG,
    operator_stop_headless_command,
    service_port,
    service_start_headless_command,
    service_status_rows,
    wait_service_port_released,
)
from gritlib.session_state import (
    mark_service_error,
    mark_service_stopped,
    read_json_file,
    state_file_path,
    update_server_state,
)
from gritlib.staged_files import staged_file_path


def stop_managed_services(cfg):
    headless = operator_stop_headless_command(cfg)
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    services = state.get("services") if isinstance(state, dict) else {}
    if not isinstance(services, dict):
        services = {}
    stopped = 0
    skipped = 0
    failed = 0
    for name, rec in sorted(services.items()):
        pid = rec.get("pid") if isinstance(rec, dict) else None
        if isinstance(rec, dict) and rec.get("status") == "stopped":
            print(f"{name}: already stopped")
            skipped += 1
            continue
        if not pid:
            mark_service_stopped(cfg, name, "server-stop:no-pid")
            append_event(
                cfg,
                name,
                "service_stop",
                details={"reason": "no-pid", "via": "server-stop", "headless_command": headless},
            )
            print(f"{name}: no pid recorded; marked stopped")
            skipped += 1
            continue
        if not pid_alive(pid):
            mark_service_stopped(cfg, name, "server-stop:stale-pid")
            append_event(
                cfg,
                name,
                "service_stop",
                details={"pid": pid, "reason": "stale-pid", "via": "server-stop", "headless_command": headless},
            )
            print(f"{name}: stale pid {pid}; marked stopped")
            skipped += 1
            continue
        ownership_evidence = managed_server_evidence(pid, cfg=cfg, rec=rec)
        if not ownership_evidence:
            print(f"{name}: skipped pid {pid}; not clearly a managed grit-console process")
            append_event(
                cfg,
                name,
                "service_stop_skipped",
                details={
                    "pid": pid,
                    "reason": "unmanaged-pid",
                    "via": "server-stop",
                    "headless_command": headless,
                },
            )
            skipped += 1
            continue
        try:
            append_event(
                cfg,
                name,
                "shutdown",
                details={
                    "pid": pid,
                    "reason": "SIGTERM",
                    "via": "server-stop",
                    "ownership_evidence": ownership_evidence,
                    "headless_command": headless,
                },
            )
            os.kill(int(pid), signal.SIGTERM)
            if wait_service_port_released(cfg, name, pid=pid):
                stopped += 1
                mark_service_stopped(cfg, name, "server-stop:SIGTERM")
                append_event(
                    cfg,
                    name,
                    "service_stop",
                    details={
                        "pid": pid,
                        "via": "server-stop",
                        "ownership_evidence": ownership_evidence,
                        "port_released": True,
                        "headless_command": headless,
                    },
                )
                print(f"{name}: stopped pid {pid}; port released")
            else:
                raise TimeoutError(f"listener port {service_port(cfg, name)} still appears bound after SIGTERM")
        except OSError as exc:
            mark_service_error(cfg, name, exc)
            print(f"{name}: failed to stop pid {pid}: {exc}", file=sys.stderr)
            failed += 1
        except TimeoutError as exc:
            mark_service_error(cfg, name, exc)
            append_event(
                cfg,
                name,
                "service_stop_failed",
                "error",
                details={
                    "pid": pid,
                    "reason": "port-still-bound",
                    "via": "server-stop",
                    "error": str(exc),
                    "headless_command": headless,
                },
            )
            print(f"{name}: failed to stop pid {pid}: {exc}", file=sys.stderr)
            failed += 1
    if stopped == 0 and skipped == 0 and failed == 0:
        print("No managed services recorded.")
    print(f"Stop summary: stopped={stopped} skipped={skipped} failed={failed}")
    return 1 if failed else 0


def start_service_process(
    cfg,
    service,
    argv_extra=None,
    headless_command="",
    *,
    start_child_process,
    script_path,
    default_config=DEFAULT_CONFIG,
):
    headless_command = headless_command or service_start_headless_command(cfg, service, argv_extra)
    current = {row["name"]: row for row in service_status_rows(cfg)}.get(service)
    if current and current.get("actual") == "listening":
        append_event(
            cfg,
            service,
            "service_start_skipped",
            details={
                "reason": "already-listening",
                "port": current.get("port", 0),
                "listener_pids": current.get("listener_pids") or [],
                "pid": current.get("pid", ""),
                "headless_command": headless_command,
            },
        )
        print(f"{service} already listening on port {current.get('port', '')}; not starting duplicate")
        print(f"  recent events: filter events by service {service}")
        return None
    cmd = [
        sys.executable,
        str(Path(script_path).resolve()),
        "--config",
        str(Path(str(cfg.get("_config_path", default_config)))),
        "--transport",
        service,
    ]
    cmd.extend(["--state-file", str(state_file_path(cfg)), "--staged-file", str(staged_file_path(cfg))])
    if service == "file-service":
        cmd.extend(["--file-service-tls", str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes"))])
    if service == "probe":
        cmd.extend(["--probe-port", str(cfg.get("GRIT_PROBE_PORT", 22207)), "--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-tftp":
        cmd.extend(["--probe-tftp-port", str(cfg.get("GRIT_PROBE_TFTP_PORT", 22208)), "--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-ftp":
        cmd.extend(["--probe-ftp-port", str(cfg.get("GRIT_PROBE_FTP_PORT", 22209)), "--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if service == "probe-dns":
        cmd.extend(["--probe-dns-port", str(cfg.get("GRIT_PROBE_DNS_PORT", 22210)), "--probe-dns-name", str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit")), "--probe-name", str(cfg.get("GRIT_PROBE_NAME", "probe.sh"))])
    if argv_extra:
        cmd.extend(argv_extra)
    log_root = Path(str(cfg.get("session_root", "local/sessions")))
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"operator-{service}-{int(time.time())}.log"
    cmd.extend(["--managed-by", str(os.getpid()), "--process-log", str(log_path)])
    with log_path.open("ab") as log:
        proc = start_child_process(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    update_server_state(cfg, service, "starting", {"pid": proc.pid, "managed_by": os.getpid(), "process_log": str(log_path)})
    append_event(
        cfg,
        service,
        "service_start_requested",
        details={
            "pid": proc.pid,
            "process_log": str(log_path),
            "managed_by": os.getpid(),
            "headless_command": headless_command,
        },
    )
    started = cfg.setdefault("_workbench_started_services", [])
    if service not in started:
        started.append(service)
    print(f"{service} started")
    print(f"  pid {proc.pid}  log {log_path}")
    print(f"  recent events: filter events by service {service}")
    return proc


def stop_workbench_started_services(cfg, *, stop_service):
    for service in reversed(cfg.get("_workbench_started_services") or []):
        stop_service(cfg, service)
    cfg["_workbench_started_services"] = []


def stop_recorded_service(cfg, service, via="workbench-stop", headless_command="", shutdown_reason=""):
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    rec = (state.get("services") or {}).get(service, {})
    pid = rec.get("pid")
    managed_by_current_workbench = str(rec.get("managed_by", "")) == str(os.getpid())
    details_base = {"via": via}
    if headless_command:
        details_base["headless_command"] = headless_command
    if not pid:
        print(f"{service}: no recorded pid")
        reason = shutdown_reason if shutdown_reason else "no-pid"
        stopped_reason = f"{via}:{reason}" if shutdown_reason else f"{via}:no-pid"
        details = {**details_base, "reason": reason}
        if shutdown_reason:
            details["port_released"] = wait_service_port_released(cfg, service, pid=pid, timeout=0.1)
        mark_service_stopped(cfg, service, stopped_reason)
        append_event(cfg, service, "service_stop", details=details)
        return
    if not pid_alive(pid):
        print(f"{service}: stale pid {pid}; marked stopped")
        reason = "stale-pid"
        stopped_reason = f"{via}:stale-pid"
        details = {**details_base, "pid": pid, "reason": reason}
        if shutdown_reason and managed_by_current_workbench:
            reason = shutdown_reason
            stopped_reason = f"{via}:{shutdown_reason}"
            details.update({"reason": reason, "port_released": wait_service_port_released(cfg, service, pid=pid, timeout=0.1)})
        mark_service_stopped(cfg, service, stopped_reason)
        append_event(cfg, service, "service_stop", details=details)
        return
    ownership_evidence = managed_server_evidence(pid, cfg=cfg, rec=rec)
    if not ownership_evidence:
        print(f"{service}: skipped pid {pid}; not clearly a managed grit-console process")
        append_event(cfg, service, "service_stop_skipped", details={**details_base, "pid": pid, "reason": "unmanaged-pid"})
        return
    try:
        append_event(cfg, service, "shutdown", details={**details_base, "pid": pid, "reason": "SIGTERM", "ownership_evidence": ownership_evidence})
        os.kill(int(pid), signal.SIGTERM)
        if wait_service_port_released(cfg, service, pid=pid):
            print(f"{service} stopped; port released")
            print(f"  pid {pid}")
            mark_service_stopped(cfg, service, f"{via}:SIGTERM")
            append_event(cfg, service, "service_stop", details={**details_base, "pid": pid, "ownership_evidence": ownership_evidence, "port_released": True})
        else:
            raise TimeoutError(f"listener port {service_port(cfg, service)} still appears bound after SIGTERM")
    except OSError as exc:
        mark_service_error(cfg, service, exc)
        print(f"{service}: unable to stop pid {pid}: {exc}", file=sys.stderr)
    except TimeoutError as exc:
        mark_service_error(cfg, service, exc)
        append_event(cfg, service, "service_stop_failed", "error", details={**details_base, "pid": pid, "reason": "port-still-bound", "error": str(exc)})
        print(f"{service}: unable to stop pid {pid}: {exc}", file=sys.stderr)
