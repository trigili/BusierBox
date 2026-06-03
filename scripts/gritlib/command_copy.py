"""Command copy file helpers for grit-console."""

import hashlib
import subprocess
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.operator_io import clipboard_command
from gritlib.record_utils import int_value, records_by_key


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def command_copy_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("command_copy_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "last-command.txt"
    ))


def command_copy_record(cfg):
    path = command_copy_path(cfg)
    rec = {
        "schema": 1,
        "path": str(path),
        "exists": path.is_file(),
        "readable": False,
        "size": 0,
        "line_count": 0,
        "command": "",
        "command_sha256": "",
        "has_command": False,
    }
    if not path.is_file():
        return rec
    try:
        data = path.read_bytes()
    except OSError as exc:
        rec["error"] = str(exc)
        return rec
    rec["readable"] = True
    rec["size"] = len(data)
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    command = lines[0] if lines else ""
    rec.update({
        "line_count": len(lines),
        "command": command,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else "",
        "has_command": bool(command),
    })
    return rec


def copy_text_for_operator(cfg, text, label="command", details=None):
    value = str(text or "")
    if not value:
        raise ValueError(f"{label} is empty")
    path = command_copy_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    copied = False
    helper = clipboard_command()
    if helper:
        try:
            subprocess.run(
                helper,
                input=value,
                text=True,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            copied = True
        except OSError:
            copied = False
    event_details = {"path": str(path), "clipboard": copied, "label": label}
    if isinstance(details, dict):
        event_details.update(details)
    append_event(cfg, "workbench", "target_command_copied", details=event_details)
    return {
        "path": str(path),
        "clipboard": copied,
        "text": value,
        **({} if not isinstance(details, dict) else details),
    }


def command_copy_indexes(records):
    return {
        "command_copy_records_by_path": {
            rec.get("path", ""): rec for rec in records or [] if rec.get("path")
        },
        "command_copy_records_by_exists": records_by_key(records, "exists"),
        "command_copy_records_by_readable": records_by_key(records, "readable"),
        "command_copy_records_by_has_command": records_by_key(records, "has_command"),
        "command_copy_records_by_command_sha256": records_by_key(records, "command_sha256"),
    }


def command_copy_state_status(command_copy):
    state_record = {
        "id": "command-copy",
        "path": command_copy.get("path", ""),
        "exists": bool(command_copy.get("exists", False)),
        "readable": bool(command_copy.get("readable", False)),
        "size": int_value(command_copy.get("size", 0)),
        "line_count": int_value(command_copy.get("line_count", 0)),
        "has_command": bool(command_copy.get("has_command", False)),
        "command_sha256": command_copy.get("command_sha256", ""),
    }
    state_record.update({
        "empty_or_missing": not state_record.get("has_command", False),
        "has_readable_command": (
            state_record.get("readable") is True and
            state_record.get("has_command") is True
        ),
    })
    if command_copy.get("error"):
        state_record["error"] = command_copy.get("error")
    state_records = [state_record]
    state_index_maps = {
        "command_copy_state_records_by_id": {
            rec.get("id", ""): rec for rec in state_records if rec.get("id")
        },
        "command_copy_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "command_copy_state_records_by_exists": records_by_key(state_records, "exists"),
        "command_copy_state_records_by_readable": records_by_key(state_records, "readable"),
        "command_copy_state_records_by_has_command": records_by_key(state_records, "has_command"),
        "command_copy_state_records_by_empty_or_missing": records_by_key(
            state_records, "empty_or_missing"
        ),
        "command_copy_state_records_by_has_readable_command": records_by_key(
            state_records, "has_readable_command"
        ),
        "command_copy_state_records_by_command_sha256": records_by_key(
            state_records, "command_sha256"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }
