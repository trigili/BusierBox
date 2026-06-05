"""Target state file path and loading helpers."""

from pathlib import Path

from gritlib.config_utils import DEFAULT_OPERATOR_SESSION_DIR
from gritlib.session_state import read_json_file


def targets_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("targets_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "targets.json"
    ))


def load_targets(cfg):
    data = read_json_file(targets_path(cfg), {"schema": 1, "targets": {}})
    if not isinstance(data, dict):
        data = {"schema": 1, "targets": {}}
    if not isinstance(data.get("targets"), dict):
        data["targets"] = {}
    data.setdefault("schema", 1)
    return data
