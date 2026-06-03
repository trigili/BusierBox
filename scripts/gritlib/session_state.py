"""Session metadata persistence for grit-console."""

import calendar
import json
import os
import threading
import time
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import records_by_key


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_CONFIG = "local/operator-session/config.json"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_utc_timestamp(text):
    try:
        return calendar.timegm(time.strptime(str(text or ""), "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def elapsed_seconds(started_at, ended_at):
    start = parse_utc_timestamp(started_at)
    end = parse_utc_timestamp(ended_at)
    if start is None or end is None or end < start:
        return None
    return int(end - start)


def utc_from_epoch(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(epoch)))


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json_file(path, fallback):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def state_file_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("server_state") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "server-state.json"
    ))


def server_state_record(cfg):
    path = state_file_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "services": {},
        "sessions": [],
        "service_count": 0,
        "session_count": 0,
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "server-state JSON is not an object"
            return rec
        services = data.get("services") if isinstance(data.get("services"), dict) else {}
        sessions = data.get("sessions") if isinstance(data.get("sessions"), list) else []
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "services": services,
            "sessions": sessions,
            "service_count": len(services),
            "session_count": len(sessions),
            "updated_at": data.get("updated_at", ""),
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def server_state_status(cfg):
    state_record = server_state_record(cfg)
    state_record["has_services"] = int(state_record.get("service_count") or 0) > 0
    state_record["has_sessions"] = int(state_record.get("session_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "server_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "server_state_records_by_exists": records_by_key(state_records, "exists"),
        "server_state_records_by_valid": records_by_key(state_records, "valid"),
        "server_state_records_by_has_services": records_by_key(
            state_records, "has_services"
        ),
        "server_state_records_by_has_sessions": records_by_key(
            state_records, "has_sessions"
        ),
        "server_state_records_by_schema": records_by_key(state_records, "schema"),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def update_server_state(cfg, action, status="configured", extra=None, default_config=DEFAULT_CONFIG):
    data = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}, "sessions": []})
    if not isinstance(data, dict):
        data = {"schema": 1, "services": {}, "sessions": []}
    data.setdefault("schema", 1)
    data.setdefault("services", {})
    data.setdefault("sessions", [])
    previous = data.get("services", {}).get(action, {})
    if not isinstance(previous, dict):
        previous = {}
    service = {
        "status": status,
        "listen_host": str(cfg.get("listen_host", "")),
        "ssh_port": int(cfg.get("ssh_listen_port", 0)),
        "shell_port": int(cfg.get("GRIT_RSHELL_SOCAT_PORT", 0)),
        "GRIT_OPERATOR_FILE_SERVICE_PORT": int(cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 0)),
        "GRIT_OPERATOR_FILE_SERVICE_TLS": str(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes")),
        "pid": os.getpid(),
        "config_path": str(cfg.get("_config_path", default_config)),
        "state_file": str(state_file_path(cfg)),
        "updated_at": utc_now(),
    }
    for key in (
        "managed_by", "process_log", "session_log", "staged_file", "workbench_mode",
        "url", "target_command", "target_route", "route_kind", "route_host",
        "route_port", "bridge_profile", "bridge_route_path", "requires_bridge",
        "selected_target_id", "selected_target_label", "selected_target_at",
    ):
        if previous.get(key):
            service[key] = previous[key]
    if cfg.get("_managed_by"):
        service["managed_by"] = str(cfg.get("_managed_by"))
    if cfg.get("_process_log"):
        service["process_log"] = str(cfg.get("_process_log"))
    if extra:
        service.update(extra)
    data["services"][action] = service
    atomic_write_json(state_file_path(cfg), data)
    return data


def mark_service_stopped(cfg, action, reason=""):
    extra = {"pid": "", "managed_by": "", "stopped_at": utc_now()}
    if reason:
        extra["stopped_reason"] = str(reason)
    return update_server_state(cfg, action, "stopped", extra)


def mark_service_error(cfg, action, reason, extra=None, event_name="service_error"):
    data = {"error": str(reason)}
    if extra:
        data.update(extra)
    append_event(cfg, action, event_name, "error", details=data)
    return update_server_state(cfg, action, "error", data)


def count_file_lines(path):
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _line in fh)
    except OSError:
        return 0


def utc_now_from_mtime(mtime):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(mtime)))


class SessionManager:
    """Structured session metadata owner for status, TUI, and future APIs."""

    def __init__(self):
        self._lock = threading.RLock()

    def root(self, cfg):
        return Path(str(cfg.get("session_root", "local/sessions")))

    def recent_paths(self, cfg, limit=8):
        root = self.root(cfg)
        if not root.is_dir():
            return []
        sessions = [p for p in root.iterdir() if p.is_dir()]
        sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return sessions[:limit]

    def log_dir(self, cfg, label):
        root = Path(str(cfg["session_root"]))
        root.mkdir(parents=True, exist_ok=True)
        prefix = time.strftime("%Y%m%d-%H%M%S") + "-" + label
        with self._lock:
            for idx in range(1000):
                name = prefix if idx == 0 else f"{prefix}-{idx + 1}"
                path = root / name
                try:
                    path.mkdir(parents=False, exist_ok=False)
                    return path
                except FileExistsError:
                    continue
            path = root / f"{prefix}-{time.monotonic_ns()}"
            path.mkdir(parents=False, exist_ok=False)
            return path

    def session_id(self, log_dir):
        return Path(log_dir).name

    def metadata_path(self, log_dir):
        return Path(log_dir) / "session.json"

    def recent_records(self, cfg, limit=8):
        out = []
        for path in self.recent_paths(cfg, limit):
            metadata_path = path / "session.json"
            events_path = path / "events.jsonl"
            session_log_path = path / "session.log"
            session_log_exists = session_log_path.is_file()
            meta = read_json_file(metadata_path, {})
            if isinstance(meta, dict) and meta:
                meta.setdefault("service", path.name.split("-", 2)[-1] if "-" in path.name else "unknown")
                meta.setdefault("path", str(path))
                meta.setdefault("exit_reason", "")
                meta.setdefault("updated_at", utc_now_from_mtime(path.stat().st_mtime))
                if "duration_sec" not in meta:
                    duration = elapsed_seconds(meta.get("started_at", ""), meta.get("ended_at", ""))
                    if duration is not None:
                        meta["duration_sec"] = duration
                meta["metadata_path"] = str(metadata_path)
                meta["metadata_exists"] = metadata_path.is_file()
                meta["event_log"] = str(events_path) if events_path.is_file() else ""
                meta["event_log_exists"] = events_path.is_file()
                meta["event_count"] = count_file_lines(events_path)
                meta["session_log"] = str(session_log_path) if session_log_exists else ""
                meta["session_log_exists"] = session_log_exists
                meta["session_log_size"] = session_log_path.stat().st_size if session_log_exists else 0
                meta["session_log_line_count"] = count_file_lines(session_log_path) if session_log_exists else 0
                meta["has_session_log"] = session_log_exists
                meta["upload_count"] = len(meta.get("uploads") or [])
                meta["fetch_count"] = len(meta.get("fetches") or [])
                meta["artifact_count"] = len(meta.get("artifacts") or [])
                meta["has_uploads"] = meta["upload_count"] > 0
                meta["has_fetches"] = meta["fetch_count"] > 0
                meta["has_events"] = meta["event_count"] > 0
                meta["has_artifacts"] = meta["artifact_count"] > 0
                out.append(meta)
                continue
            exit_reason = ""
            try:
                exit_reason = (path / "exit-reason").read_text(encoding="utf-8").strip()
            except OSError:
                pass
            service = path.name.split("-", 2)[-1] if "-" in path.name else "unknown"
            event_count = count_file_lines(events_path)
            upload_count = len(list(path.glob("files/*.metadata.json")))
            out.append({
                "service": service,
                "path": str(path),
                "metadata_path": str(metadata_path) if metadata_path.is_file() else "",
                "metadata_exists": metadata_path.is_file(),
                "event_log": str(events_path) if events_path.is_file() else "",
                "event_log_exists": events_path.is_file(),
                "event_count": event_count,
                "session_log": str(session_log_path) if session_log_exists else "",
                "session_log_exists": session_log_exists,
                "session_log_size": session_log_path.stat().st_size if session_log_exists else 0,
                "session_log_line_count": count_file_lines(session_log_path) if session_log_exists else 0,
                "has_session_log": session_log_exists,
                "upload_count": upload_count,
                "fetch_count": 0,
                "artifact_count": 0,
                "has_uploads": upload_count > 0,
                "has_fetches": False,
                "has_events": event_count > 0,
                "has_artifacts": False,
                "exit_reason": exit_reason,
                "updated_at": utc_now_from_mtime(path.stat().st_mtime),
                "duration_sec": "",
            })
        return out

    def write_record(self, log_dir, record):
        path = self.metadata_path(log_dir)
        with self._lock:
            current = read_json_file(path, {})
            if not isinstance(current, dict):
                current = {}
            current.update(record)
            current.setdefault("schema", 1)
            current.setdefault("session_id", self.session_id(log_dir))
            current.setdefault("path", str(log_dir))
            current.setdefault("artifacts", [])
            current.setdefault("uploads", [])
            current.setdefault("fetches", [])
            atomic_write_json(path, current)
            return current

    def upsert_state(self, cfg, log_dir, service, state, remote="", exit_reason="", **extra):
        with self._lock:
            data = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}, "sessions": []})
            if not isinstance(data, dict):
                data = {"schema": 1, "services": {}, "sessions": []}
            data.setdefault("schema", 1)
            data.setdefault("services", {})
            sessions = data.get("sessions")
            if not isinstance(sessions, list):
                sessions = []
            sid = self.session_id(log_dir)
            summary = {
                "session_id": sid,
                "service": service,
                "path": str(log_dir),
                "state": state,
                "remote": remote or "",
                "exit_reason": exit_reason or "",
                "updated_at": utc_now(),
            }
            for key, value in (extra or {}).items():
                if value not in (None, ""):
                    summary[key] = value
            replaced = False
            for idx, item in enumerate(sessions):
                if isinstance(item, dict) and item.get("session_id") == sid:
                    merged = dict(item)
                    merged.update(summary)
                    sessions[idx] = merged
                    replaced = True
                    break
            if not replaced:
                sessions.append(summary)
            data["sessions"] = sessions[-50:]
            atomic_write_json(state_file_path(cfg), data)

    def start_record(self, cfg, service, log_dir, remote="", state="starting", details=None):
        self.upsert_state(cfg, log_dir, service, state, remote=remote)
        return self.write_record(log_dir, {
            "schema": 1,
            "session_id": self.session_id(log_dir),
            "service": service,
            "path": str(log_dir),
            "state": state,
            "started_at": utc_now(),
            "ended_at": "",
            "remote": remote or "",
            "exit_reason": "",
            "details": details or {},
            "artifacts": [],
            "uploads": [],
            "fetches": [],
        })

    def update_record(self, log_dir, **fields):
        return self.write_record(log_dir, fields)

    def append_list_item(self, log_dir, key, item):
        path = self.metadata_path(log_dir)
        with self._lock:
            current = read_json_file(path, {})
            if not isinstance(current, dict):
                current = {}
            values = current.get(key)
            if not isinstance(values, list):
                values = []
            values.append(item)
            current[key] = values
        return self.write_record(log_dir, current)

    def finish_record(self, cfg, service, log_dir, state="stopped", exit_reason=""):
        current = self.write_record(log_dir, {})
        self.upsert_state(cfg, log_dir, service, state, remote=current.get("remote", ""), exit_reason=exit_reason)
        ended_at = utc_now()
        duration = elapsed_seconds(current.get("started_at", ""), ended_at)
        fields = {"state": state, "ended_at": ended_at, "exit_reason": exit_reason}
        if duration is not None:
            fields["duration_sec"] = duration
        return self.update_record(log_dir, **fields)

    def exit_reason(self, log_dir):
        path = Path(log_dir) / "exit-reason"
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
