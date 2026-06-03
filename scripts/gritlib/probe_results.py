"""Probe result persistence helpers for grit-console."""

from pathlib import Path

from gritlib.session_state import atomic_write_json, read_json_file


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def probe_results_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "probe-results.json"


def append_probe_result(cfg, result):
    path = probe_results_path(cfg)
    data = read_json_file(path, {"schema": 1, "results": []})
    if not isinstance(data.get("results"), list):
        data["results"] = []
    data["results"].append(result)
    atomic_write_json(path, data)
    return path
