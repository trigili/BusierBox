"""Workbench job path and state helpers for grit-console."""

import json
import os
import time
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.process_status import pid_alive, pid_environ_contains
from gritlib.session_state import (
    atomic_write_json, elapsed_seconds, read_json_file, utc_now,
)
from gritlib.shell_utils import shquote


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_CONFIG = "local/operator-session/config.json"


def workbench_jobs_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("workbench_jobs_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "workbench-jobs.json"
    ))


def workbench_jobs_state_record(cfg):
    path = workbench_jobs_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "job_count": 0,
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "workbench-jobs JSON is not an object"
            return rec
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            rec["error"] = "workbench-jobs JSON jobs field is not a list"
            return rec
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "job_count": len(jobs),
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def tail_text_file(path_text, line_limit=20, byte_limit=8192):
    path = Path(str(path_text or ""))
    if not path.is_file():
        return []
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if len(data) > byte_limit:
        data = data[-byte_limit:]
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-int(line_limit or 20):]


def workbench_job_log_tail_record(path_text, line_limit=20, byte_limit=8192):
    path = Path(str(path_text or ""))
    line_limit = int(line_limit or 20)
    byte_limit = int(byte_limit or 8192)
    rec = {
        "exists": False,
        "size": 0,
        "tail": [],
        "tail_count": 0,
        "tail_line_limit": line_limit,
        "tail_byte_limit": byte_limit,
        "tail_truncated": False,
        "line_count": 0,
    }
    if not path.is_file():
        return rec
    rec["exists"] = True
    try:
        data = path.read_bytes()
    except OSError:
        return rec
    rec["size"] = len(data)
    truncated_by_bytes = len(data) > byte_limit
    tail_data = data[-byte_limit:] if truncated_by_bytes else data
    text = tail_data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not truncated_by_bytes:
        rec["line_count"] = len(lines)
    tail = lines[-line_limit:]
    rec["tail"] = tail
    rec["tail_count"] = len(tail)
    rec["tail_truncated"] = truncated_by_bytes or len(lines) > line_limit
    return rec


def load_workbench_jobs(cfg):
    data = read_json_file(workbench_jobs_path(cfg), {"schema": 1, "jobs": []})
    if not isinstance(data, dict):
        data = {"schema": 1, "jobs": []}
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    data.setdefault("schema", 1)
    return data


def write_workbench_jobs(cfg, data):
    data.setdefault("schema", 1)
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    atomic_write_json(workbench_jobs_path(cfg), data)


def next_workbench_job_id(data):
    existing = {str(rec.get("id") or "") for rec in data.get("jobs") or [] if isinstance(rec, dict)}
    base = f"job-{int(time.time())}-{os.getpid()}"
    if base not in existing:
        return base
    for idx in range(2, 1000):
        candidate = f"{base}-{idx}"
        if candidate not in existing:
            return candidate
    raise ValueError("unable to allocate unique workbench job id")


def read_workbench_job_exit_status(path_text):
    path = Path(str(path_text or ""))
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text or not text.lstrip("-").isdigit():
        return None
    return int(text)


def workbench_job_ownership_evidence(pid, rec):
    if not pid:
        return []
    rec = rec if isinstance(rec, dict) else {}
    job_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    evidence = []
    if str(rec.get("managed_by") or "") == "grit-console-workbench":
        evidence.append("ledger:managed-by-workbench")
    if job_id and pid_environ_contains(pid, "GRIT_WORKBENCH_JOB_ID", job_id):
        evidence.append("environ:job-id")
    if action_id and pid_environ_contains(pid, "GRIT_WORKBENCH_ACTION_ID", action_id):
        evidence.append("environ:action-id")
    return evidence


def workbench_job_has_cancel_ownership(evidence):
    evidence = set(evidence or [])
    return "environ:job-id" in evidence and "environ:action-id" in evidence


def workbench_job_records(cfg, actions):
    data = load_workbench_jobs(cfg)
    actions_by_id = {rec.get("id", ""): rec for rec in (actions or []) if rec.get("id")}
    records = []
    for raw in data.get("jobs") or []:
        if not isinstance(raw, dict):
            continue
        rec = dict(raw)
        action = actions_by_id.get(str(rec.get("action_id") or "")) or {}
        pid = rec.get("pid")
        pid_is_alive = pid_alive(pid) if pid else False
        state = str(rec.get("state") or "unknown")
        effective_state = state
        if state in ("starting", "running") and pid and not pid_is_alive:
            effective_state = "exited"
        log_path = str(rec.get("log_path") or "")
        exit_status_path = str(rec.get("exit_status_path") or "")
        finished_at_path = str(rec.get("finished_at_path") or "")
        exit_status = rec.get("exit_status")
        if exit_status in (None, ""):
            exit_status = read_workbench_job_exit_status(exit_status_path)
        exit_status_known = isinstance(exit_status, int)
        finished_at = str(rec.get("finished_at") or "")
        if not finished_at and finished_at_path and Path(finished_at_path).is_file():
            try:
                finished_at = Path(finished_at_path).read_text(encoding="utf-8").strip()
            except OSError:
                finished_at = ""
        started_at = str(rec.get("started_at") or "")
        duration_sec = elapsed_seconds(started_at, finished_at) if finished_at else None
        elapsed_sec = elapsed_seconds(started_at, utc_now()) if started_at else None
        outcome = "unknown"
        if exit_status_known:
            outcome = "succeeded" if exit_status == 0 else "failed"
        log_tail = workbench_job_log_tail_record(log_path, rec.get("tail_limit", 20))
        output_tail = log_tail.get("tail") or []
        ownership_evidence = workbench_job_ownership_evidence(pid, rec)
        cancel_ownership = workbench_job_has_cancel_ownership(ownership_evidence)
        cancel_supported = bool(pid and pid_is_alive and cancel_ownership and action.get("background_supported") is True)
        rec.update({
            "action_id": str(rec.get("action_id") or ""),
            "action_label": action.get("label", ""),
            "category": rec.get("category") or action.get("category", ""),
            "script": rec.get("script") or action.get("script", ""),
            "command": str(rec.get("command") or action.get("command", "")),
            "state": state,
            "effective_state": effective_state,
            "pid_alive": pid_is_alive,
            "pid_managed": bool(cancel_ownership),
            "ownership_evidence": ownership_evidence,
            "cancel_supported": cancel_supported,
            "log_path": log_path,
            "exit_status_path": exit_status_path,
            "finished_at_path": finished_at_path,
            "exit_status": exit_status if exit_status_known else "",
            "exit_status_known": exit_status_known,
            "started_at": started_at,
            "started_at_known": bool(started_at),
            "finished_at": finished_at,
            "finished_at_known": bool(finished_at),
            "duration_sec": duration_sec if duration_sec is not None else "",
            "duration_known": duration_sec is not None,
            "elapsed_sec": elapsed_sec if elapsed_sec is not None else "",
            "elapsed_known": elapsed_sec is not None,
            "outcome": outcome,
            "log_exists": bool(log_tail.get("exists", False)),
            "log_size": int(log_tail.get("size", 0) or 0),
            "last_output_tail": output_tail,
            "last_output_tail_count": len(output_tail),
            "last_output_tail_truncated": bool(log_tail.get("tail_truncated", False)),
            "last_output_tail_line_limit": int(log_tail.get("tail_line_limit", 20) or 20),
            "last_output_tail_byte_limit": int(log_tail.get("tail_byte_limit", 8192) or 8192),
            "log_line_count": int(log_tail.get("line_count", 0) or 0),
            "background_supported": bool(action.get("background_supported", False)),
            "long_running": bool(action.get("long_running", False)),
        })
        records.append(rec)
    return records


def reconcile_workbench_job_completion_events(cfg):
    data = load_workbench_jobs(cfg)
    changed = False
    completion_events = []
    for rec in data.get("jobs") or []:
        if not isinstance(rec, dict) or rec.get("completed_event_at"):
            continue
        exit_status = rec.get("exit_status")
        if exit_status in (None, ""):
            exit_status = read_workbench_job_exit_status(rec.get("exit_status_path", ""))
        if not isinstance(exit_status, int):
            continue
        finished_at = str(rec.get("finished_at") or "")
        finished_at_path = str(rec.get("finished_at_path") or "")
        if not finished_at and finished_at_path and Path(finished_at_path).is_file():
            try:
                finished_at = Path(finished_at_path).read_text(encoding="utf-8").strip()
            except OSError:
                finished_at = ""
        if not finished_at:
            finished_at = utc_now()
        outcome = "succeeded" if exit_status == 0 else "failed"
        event_at = utc_now()
        rec.update({
            "state": "exited",
            "exit_status": exit_status,
            "finished_at": finished_at,
            "outcome": outcome,
            "completed_event_at": event_at,
        })
        changed = True
        completion_events.append({
            "job_id": rec.get("id", ""),
            "action_id": rec.get("action_id", ""),
            "exit_status": exit_status,
            "outcome": outcome,
            "finished_at": finished_at,
            "log_path": rec.get("log_path", ""),
        })
    if changed:
        write_workbench_jobs(cfg, data)
        for details in completion_events:
            append_event(cfg, "workbench", "workbench_job_completed", details=details)


def start_workbench_job_headless_command(
    cfg, action_id, command_override=None, default_config=DEFAULT_CONFIG
):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--start-workbench-job",
        str(action_id or ""),
    ]
    if command_override:
        parts.extend(["--job-command", str(command_override)])
    return " ".join(shquote(part) for part in parts)


def cancel_workbench_job_headless_command(cfg, job_id, default_config=DEFAULT_CONFIG):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --cancel-workbench-job "
        + shquote(str(job_id or ""))
    )
