"""Workbench job path and state helpers for grit-console."""

import json
import os
import time
from pathlib import Path

from gritlib.session_state import atomic_write_json, read_json_file


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


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
