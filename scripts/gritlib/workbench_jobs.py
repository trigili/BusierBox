"""Workbench job path and state helpers for grit-console."""

import json
from pathlib import Path


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
