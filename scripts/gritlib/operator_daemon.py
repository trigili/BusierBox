"""Operator daemon loop for grit-console."""

import os
import subprocess
import time
from pathlib import Path

from gritlib.config_utils import DEFAULT_OPERATOR_SESSION_DIR
from gritlib.event_log import append_event
from gritlib.service_runtime import (
    SHUTDOWN,
    current_shutdown_reason,
    request_shutdown,
    start_child_process,
)
from gritlib.service_status import (
    configured_daemon_services,
    daemon_child_command,
    operator_daemon_headless_command,
)
from gritlib.session_state import mark_service_stopped, update_server_state
from gritlib.shell_utils import shquote

def run_operator_daemon(cfg, services, timeout=None):
    services = configured_daemon_services(cfg, services)
    if not services:
        raise ValueError("operator daemon has no services selected; set *_enable=yes or pass --daemon-service")
    headless = operator_daemon_headless_command(cfg, services, timeout=timeout)
    daemon_log_root = _prepare_operator_daemon(cfg, services, headless)
    children = _start_operator_daemon_children(cfg, services, headless, daemon_log_root)
    _mark_operator_daemon_listening(cfg, services, headless, children)
    _print_operator_daemon_started(children)
    deadline = None if timeout is None else time.time() + float(timeout)
    exit_code = 0
    try:
        exit_code = _run_operator_daemon_supervision_loop(cfg, children, deadline)
    finally:
        _stop_operator_daemon_children(cfg, services, headless, children, exit_code)
    return exit_code


def _prepare_operator_daemon(cfg, services, headless):
    daemon_log_root = Path(str(cfg.get("operator_session_dir", DEFAULT_OPERATOR_SESSION_DIR))) / "daemon-logs"
    daemon_log_root.mkdir(parents=True, exist_ok=True)
    update_server_state(cfg, "operator-daemon", "starting", {
        "daemon_services": services,
        "child_count": 0,
        "headless_command": headless,
    })
    append_event(cfg, "operator-daemon", "daemon_starting", details={"services": services, "headless_command": headless})
    return daemon_log_root


def _start_operator_daemon_children(cfg, services, headless, daemon_log_root):
    children = []
    for service in services:
        command = daemon_child_command(cfg, service)
        child_headless = " ".join(shquote(str(part)) for part in command)
        log_path = daemon_log_root / f"{service}.log"
        log_fh = log_path.open("ab")
        child_env = dict(os.environ)
        child_env["GRIT_OPERATOR_DAEMON"] = "1"
        proc = start_child_process(command + ["--process-log", str(log_path)], cwd=Path.cwd(), stdout=log_fh, stderr=subprocess.STDOUT, env=child_env)
        children.append({"service": service, "process": proc, "log_fh": log_fh, "log_path": str(log_path), "command": command, "headless_command": child_headless})
        append_event(cfg, "operator-daemon", "daemon_child_start", details={
            "service": service,
            "pid": proc.pid,
            "process_log": str(log_path),
            "command": command,
            "headless_command": child_headless,
            "daemon_headless_command": headless,
        })
    return children


def _mark_operator_daemon_listening(cfg, services, headless, children):
    update_server_state(cfg, "operator-daemon", "listening", {
        "daemon_services": services,
        "child_count": len(children),
        "child_pids": [item["process"].pid for item in children],
        "child_process_logs": {item["service"]: item["log_path"] for item in children},
        "headless_command": headless,
    })


def _print_operator_daemon_started(children):
    print("griTTYkit operator daemon")
    for item in children:
        print(f"  {item['service']}: pid={item['process'].pid} log={item['log_path']}")


def _run_operator_daemon_supervision_loop(cfg, children, deadline):
    exit_code = 0
    while not SHUTDOWN.is_set():
        failed = [item for item in children if item["process"].poll() not in (None, 0)]
        if failed:
            for item in failed:
                append_event(cfg, "operator-daemon", "daemon_child_exit", "error", details={
                    "service": item["service"],
                    "pid": item["process"].pid,
                    "returncode": item["process"].returncode,
                })
            exit_code = 1
            break
        if all(item["process"].poll() == 0 for item in children):
            break
        if deadline is not None and time.time() >= deadline:
            request_shutdown("daemon-timeout")
            break
        time.sleep(0.1)
    return exit_code


def _terminate_operator_daemon_children(children):
    for item in children:
        proc = item["process"]
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass


def _wait_operator_daemon_child(proc):
    if proc.poll() is None:
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait(timeout=3)


def _close_operator_daemon_child_log(item):
    try:
        item["log_fh"].close()
    except OSError:
        pass


def _stop_operator_daemon_children(cfg, services, headless, children, exit_code):
    request_shutdown(current_shutdown_reason() or "daemon-stop")
    _terminate_operator_daemon_children(children)
    for item in children:
        proc = item["process"]
        _wait_operator_daemon_child(proc)
        _close_operator_daemon_child_log(item)
        append_event(cfg, "operator-daemon", "daemon_child_stopped", details={
            "service": item["service"],
            "pid": proc.pid,
            "returncode": proc.returncode,
            "headless_command": item.get("headless_command", ""),
            "daemon_headless_command": headless,
        })
    mark_service_stopped(cfg, "operator-daemon", current_shutdown_reason() or "daemon-stop")
    append_event(cfg, "operator-daemon", "daemon_stopped", details={"services": services, "exit_code": exit_code, "headless_command": headless})
