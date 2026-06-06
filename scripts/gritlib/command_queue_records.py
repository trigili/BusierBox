"""Command queue persistence, mutation, and command-record indexes."""

import hashlib
import json
import os
import time
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import int_value, records_by_key
from gritlib.session_state import (
    atomic_write_json,
    parse_utc_timestamp,
    read_json_file,
    utc_from_epoch,
    utc_now,
)
import gritlib.command_queue_policy as command_queue_policy
from gritlib.target_context import (
    configured_target_filter,
    records_for_target,
    target_context_fields,
)


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")

COMMAND_QUEUE_WORK_METADATA_FIELDS = (
    "work_kind",
    "workflow",
    "request_name",
    "bridge_profile",
    "bridge_route_path",
    "bridge_requires_target_online",
    "route_kind",
)


def command_queue_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("command_queue_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "command-queue.json"
    ))


def command_queue_state_record(cfg):
    path = command_queue_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "command_count": 0,
        "command_ids": [],
        "status_counts": {},
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "command-queue JSON is not an object"
            return rec
        commands = data.get("commands")
        if not isinstance(commands, list):
            rec["error"] = "command-queue JSON commands field is not a list"
            return rec
        command_ids = []
        status_counts = {}
        for item in commands:
            if not isinstance(item, dict):
                continue
            command_id = str(item.get("id") or "")
            status = str(item.get("status") or "")
            if command_id:
                command_ids.append(command_id)
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "command_count": len(commands),
            "command_ids": command_ids,
            "status_counts": status_counts,
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def command_queue_state_status(cfg):
    state_record = command_queue_state_record(cfg)
    state_record["has_commands"] = int(state_record.get("command_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "command_queue_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "command_queue_state_records_by_exists": records_by_key(
            state_records, "exists"
        ),
        "command_queue_state_records_by_valid": records_by_key(state_records, "valid"),
        "command_queue_state_records_by_has_commands": records_by_key(
            state_records, "has_commands"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def load_command_queue(cfg):
    data = read_json_file(command_queue_path(cfg), {"schema": 1, "commands": []})
    if not isinstance(data, dict):
        data = {"schema": 1, "commands": []}
    if not isinstance(data.get("commands"), list):
        data["commands"] = []
    data.setdefault("schema", 1)
    return data


def save_command_queue(cfg, data):
    data.setdefault("schema", 1)
    if not isinstance(data.get("commands"), list):
        data["commands"] = []
    atomic_write_json(command_queue_path(cfg), data)


def command_queue_expired(rec, now_epoch=None):
    if not isinstance(rec, dict):
        return False
    if str(rec.get("status") or "") != "queued":
        return False
    expires_epoch = parse_utc_timestamp(str(rec.get("expires_at") or ""))
    if expires_epoch is None:
        return False
    if now_epoch is None:
        now_epoch = parse_utc_timestamp(utc_now()) or int(time.time())
    return int(now_epoch) >= int(expires_epoch)


def command_result_output_size_bucket(size):
    size = int_value(size)
    if size <= 0:
        return "zero"
    if size <= 1024:
        return "small"
    if size <= 65536:
        return "medium"
    return "large"


def command_queue_work_metadata(rec):
    if not isinstance(rec, dict):
        return {}
    return {
        key: rec.get(key)
        for key in COMMAND_QUEUE_WORK_METADATA_FIELDS
        if rec.get(key) not in (None, "")
    }


def mark_command_delivered(cfg, command_id, remote_addr="", target_identity=None):
    data = load_command_queue(cfg)
    for rec in data.get("commands", []):
        if isinstance(rec, dict) and rec.get("id") == command_id:
            if command_queue_expired(rec):
                raise ValueError(f"command queue id expired: {command_id}")
            policy = command_queue_policy.command_queue_delivery_policy_snapshot(cfg)
            target_identity = dict(target_identity or {})
            rec_target_id = str(rec.get("target_id") or "").strip()
            poll_target_id = str(target_identity.get("target_id") or "").strip()
            if rec_target_id and not poll_target_id:
                raise ValueError(f"command target id required: expected {rec_target_id}")
            if poll_target_id and rec_target_id and poll_target_id != rec_target_id:
                raise ValueError(f"command target mismatch: expected {rec_target_id}, got {poll_target_id}")
            if poll_target_id and not rec_target_id:
                rec.update(target_identity)
            rec["status"] = "delivered"
            rec["delivered_at"] = utc_now()
            rec["delivered_to"] = remote_addr
            rec["delivery_supported"] = True
            rec["result_upload_supported"] = True
            rec["execution_supported"] = bool(policy.get("execution_supported"))
            rec["executes_commands"] = bool(policy.get("executes_commands"))
            rec["execution_decision"] = "pending" if policy.get("execution_supported") else "rejected"
            rec["execution_decision_reason"] = "" if policy.get("execution_supported") else command_queue_policy.command_queue_execution_rejection_reason(cfg)
            rec["delivery_policy_snapshot"] = policy
            save_command_queue(cfg, data)
            append_event(
                cfg,
                "command-queue",
                "command_delivered",
                details={
                    "id": command_id,
                    "command_id": command_id,
                    "command_sha256": rec.get("command_sha256", ""),
                    "remote_addr": remote_addr,
                    "timeout_sec": rec.get("timeout_sec", 0),
                    "max_output_bytes": rec.get("max_output_bytes", 0),
                    "delivery_supported": True,
                    "result_upload_supported": True,
                    "execution_supported": rec["execution_supported"],
                    "executes_commands": rec["executes_commands"],
                    "execution_decision": rec["execution_decision"],
                    "target_id": rec.get("target_id", ""),
                    "target_label": rec.get("target_label", ""),
                    "target_identity_source": rec.get("target_identity_source", ""),
                    "target_identity_confidence": rec.get("target_identity_confidence", ""),
                    **command_queue_work_metadata(rec),
                    "policy_snapshot": policy,
                },
            )
            return rec
    return None


def queue_command(cfg, command, timeout_sec=None, max_output_bytes=None, expire_sec=None, metadata=None):
    text = str(command or "").strip()
    if not text:
        raise ValueError("command queue entry must not be empty")
    timeout_value = int(timeout_sec) if timeout_sec is not None else 30
    max_output_value = int(max_output_bytes) if max_output_bytes is not None else 65536
    if timeout_value <= 0:
        raise ValueError("command queue timeout must be a positive integer")
    if max_output_value <= 0:
        raise ValueError("command queue max output must be a positive integer")
    expire_value = int(expire_sec) if expire_sec is not None else 0
    if expire_value < 0:
        raise ValueError("command queue expiration must be zero or a positive integer")
    data = load_command_queue(cfg)
    now = utc_now()
    now_epoch = parse_utc_timestamp(now) or int(time.time())
    digest = hashlib.sha256(f"{now}\0{time.time_ns()}\0{text}\0{os.getpid()}".encode("utf-8")).hexdigest()[:16]
    queue_policy = command_queue_policy.command_queue_policy_snapshot(cfg)
    rec = {
        "id": f"cq-{digest}",
        "created_at": now,
        "status": "queued",
        "command": text,
        "command_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "timeout_sec": timeout_value,
        "max_output_bytes": max_output_value,
        "expire_sec": expire_value,
        "expires_at": utc_from_epoch(now_epoch + expire_value) if expire_value > 0 else "",
        "execution_supported": bool(queue_policy.get("execution_supported")),
        "executes_commands": False,
        "delivery_supported": False,
        "queue_policy_snapshot": queue_policy,
        "safety_boundary": "operator queue record only; execution requires explicit target poll and execute policy",
    }
    if configured_target_filter(cfg):
        rec.update(target_context_fields(cfg, configured_target_filter(cfg)))
    queue_metadata = metadata if isinstance(metadata, dict) else {}
    for key in COMMAND_QUEUE_WORK_METADATA_FIELDS:
        if key in queue_metadata and queue_metadata.get(key) not in (None, ""):
            rec[key] = queue_metadata.get(key)
    data["commands"].append(rec)
    save_command_queue(cfg, data)
    append_event(
        cfg,
        "command-queue",
        "command_queue_queued",
        details={
            "id": rec["id"],
            "command_id": rec["id"],
            "status": rec["status"],
            "command_sha256": rec["command_sha256"],
            "timeout_sec": rec["timeout_sec"],
            "max_output_bytes": rec["max_output_bytes"],
            "expire_sec": rec["expire_sec"],
            "expires_at": rec["expires_at"],
            "delivery_supported": rec["delivery_supported"],
            "execution_supported": rec["execution_supported"],
            "executes_commands": rec["executes_commands"],
            "target_id": rec.get("target_id", ""),
            "target_label": rec.get("target_label", ""),
            "work_kind": rec.get("work_kind", ""),
            "workflow": rec.get("workflow", ""),
            "request_name": rec.get("request_name", ""),
            "bridge_profile": rec.get("bridge_profile", ""),
            "bridge_route_path": rec.get("bridge_route_path", ""),
            "bridge_requires_target_online": rec.get("bridge_requires_target_online", ""),
            "policy_snapshot": rec["queue_policy_snapshot"],
        },
    )
    return rec


def clear_command_queue(cfg):
    data = load_command_queue(cfg)
    count = len(data.get("commands", []))
    data["commands"] = []
    save_command_queue(cfg, data)
    append_event(cfg, "command-queue", "command_queue_cleared", details={"count": count})
    return count


def record_command_result_payload(cfg, command_id, result, result_source_path="", target_identity=None):
    data = load_command_queue(cfg)
    if not isinstance(result, dict):
        raise ValueError("command result JSON must be an object")
    result_command_id = str(result.get("command_id", "")).strip()
    if result_command_id and result_command_id != str(command_id):
        raise ValueError(f"command result id mismatch: expected {command_id}, got {result_command_id}")
    commands = data.get("commands", [])
    for rec in commands:
        if isinstance(rec, dict) and rec.get("id") == command_id:
            if command_queue_expired(rec):
                raise ValueError(f"command queue id expired: {command_id}")
            target_identity = dict(target_identity or {})
            rec_target_id = str(rec.get("target_id") or "").strip()
            result_target_id = str(target_identity.get("target_id") or "").strip()
            if rec_target_id and not result_target_id:
                raise ValueError(f"command result target id required: expected {rec_target_id}")
            if result_target_id and rec_target_id and result_target_id != rec_target_id:
                raise ValueError(f"command result target mismatch: expected {rec_target_id}, got {result_target_id}")
            if result_target_id and not rec_target_id:
                rec.update(target_identity)
            stdout_bytes = int(result.get("stdout_bytes", 0) or 0)
            stderr_bytes = int(result.get("stderr_bytes", 0) or 0)
            output_bytes = int(result.get("output_bytes", stdout_bytes + stderr_bytes) or 0)
            max_output_bytes = int(rec.get("max_output_bytes", 0) or 0)
            output_exceeded = bool(result.get("output_exceeded_limit")) or bool(max_output_bytes and output_bytes > max_output_bytes)
            rec["status"] = "result-received"
            rec["result_received_at"] = utc_now()
            rec["result"] = result
            rec["result_command_id"] = str(command_id)
            rec["result_source_path"] = str(result_source_path)
            rec["execution_supported"] = bool(result.get("execution_supported", rec.get("execution_supported", False)))
            rec["executes_commands"] = bool(result.get("executes_commands", False))
            rec["execution_decision"] = str(result.get("execution_decision") or ("executed" if rec["executes_commands"] else "rejected"))
            rec["execution_decision_reason"] = str(result.get("reason") or "")
            rec["result_status"] = str(result.get("status") or "")
            rec["result_exit_code"] = result.get("exit_code", "")
            rec["result_stdout_bytes"] = stdout_bytes
            rec["result_stderr_bytes"] = stderr_bytes
            rec["result_output_bytes"] = output_bytes
            rec["result_output_limit_bytes"] = max_output_bytes
            rec["result_output_exceeded_limit"] = output_exceeded
            save_command_queue(cfg, data)
            append_event(
                cfg,
                "command-queue",
                "command_result_received",
                details={
                    "id": command_id,
                    "command_id": command_id,
                    "command_sha256": rec.get("command_sha256", ""),
                    "result_source_path": str(result_source_path),
                    "status": result.get("status", ""),
                    "exit_code": result.get("exit_code", ""),
                    "execution_supported": rec["execution_supported"],
                    "executes_commands": rec["executes_commands"],
                    "execution_decision": rec["execution_decision"],
                    "stdout_bytes": stdout_bytes,
                    "stderr_bytes": stderr_bytes,
                    "output_bytes": output_bytes,
                    "output_limit_bytes": max_output_bytes,
                    "output_exceeded_limit": output_exceeded,
                    "target_id": rec.get("target_id", ""),
                    "target_label": rec.get("target_label", ""),
                    "target_identity_source": rec.get("target_identity_source", ""),
                    "target_identity_confidence": rec.get("target_identity_confidence", ""),
                },
            )
            return rec
    raise ValueError(f"command queue id not found: {command_id}")


def command_queue_visible_commands(cfg):
    data = load_command_queue(cfg)
    commands = data.get("commands", [])
    target_filter_id = configured_target_filter(cfg)
    unfiltered_command_count = len([rec for rec in commands if isinstance(rec, dict)])
    if target_filter_id:
        commands = records_for_target(commands, target_filter_id)
    now_epoch = parse_utc_timestamp(utc_now()) or int(time.time())
    for rec in commands:
        if not isinstance(rec, dict):
            continue
        expired = command_queue_expired(rec, now_epoch=now_epoch)
        rec["expired"] = expired
        if expired:
            rec["effective_status"] = "expired"
            rec["status"] = "expired"
        else:
            rec["effective_status"] = str(rec.get("status") or "")
    return commands, target_filter_id, unfiltered_command_count


def _empty_command_queue_record_index_state():
    return {
        "commands_by_id": {},
        "commands_by_status": {},
        "commands_by_command_sha256": {},
        "commands_by_created_at": {},
        "commands_by_delivered_at": {},
        "commands_by_result_received_at": {},
        "commands_by_result_source_path": {},
        "commands_by_timeout_sec": {},
        "commands_by_expire_sec": {},
        "commands_by_expires_at": {},
        "commands_by_expired": {},
        "commands_by_max_output_bytes": {},
        "commands_by_execution_decision": {},
        "commands_by_result_status": {},
        "commands_by_result_exit_code": {},
        "commands_by_result_output_exceeded": {},
        "commands_by_result_output_size_bucket": {},
        "commands_by_target_id": {},
        "status_counts": {},
        "execution_decision_counts": {},
        "result_status_counts": {},
        "result_exit_code_counts": {},
        "result_output_size_bucket_counts": {},
        "latest_created_at": "",
        "latest_result_received_at": "",
    }


def _queue_index_append(indexes, key, rec):
    indexes.setdefault(key, []).append(rec)


def _queue_index_count(counts, key):
    counts[key] = counts.get(key, 0) + 1


def _command_queue_index_values(rec):
    command_text = str(rec.get("command") or "")
    command_sha256 = str(rec.get("command_sha256") or "")
    if command_text and not command_sha256:
        command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
        rec["command_sha256"] = command_sha256
    return {
        "command_id": str(rec.get("id") or ""),
        "status": str(rec.get("status") or ""),
        "command_sha256": command_sha256,
        "target_id": str(rec.get("target_id") or ""),
        "execution_decision": str(rec.get("execution_decision") or ""),
        "created_at": str(rec.get("created_at") or ""),
        "delivered_at": str(rec.get("delivered_at") or ""),
        "result_received_at": str(rec.get("result_received_at") or ""),
        "result_source_path": str(rec.get("result_source_path") or ""),
        "expires_at": str(rec.get("expires_at") or ""),
    }


def _apply_command_queue_base_indexes(state, rec, values):
    if values["command_id"]:
        state["commands_by_id"][values["command_id"]] = rec
    if values["status"]:
        _queue_index_append(state["commands_by_status"], values["status"], rec)
        _queue_index_count(state["status_counts"], values["status"])
    if values["command_sha256"]:
        _queue_index_append(
            state["commands_by_command_sha256"],
            values["command_sha256"],
            rec,
        )
    if values["target_id"]:
        _queue_index_append(state["commands_by_target_id"], values["target_id"], rec)


def _apply_command_queue_timing_indexes(state, rec, values):
    if values["created_at"]:
        _queue_index_append(state["commands_by_created_at"], values["created_at"], rec)
    if values["delivered_at"]:
        _queue_index_append(state["commands_by_delivered_at"], values["delivered_at"], rec)
    if values["result_received_at"]:
        _queue_index_append(
            state["commands_by_result_received_at"],
            values["result_received_at"],
            rec,
        )
    if values["result_source_path"]:
        _queue_index_append(
            state["commands_by_result_source_path"],
            values["result_source_path"],
            rec,
        )
    timeout_sec = rec.get("timeout_sec")
    if timeout_sec not in (None, ""):
        _queue_index_append(state["commands_by_timeout_sec"], str(timeout_sec), rec)
    max_output_bytes = rec.get("max_output_bytes")
    if max_output_bytes not in (None, ""):
        _queue_index_append(
            state["commands_by_max_output_bytes"],
            str(max_output_bytes),
            rec,
        )
    expire_sec = rec.get("expire_sec")
    if expire_sec not in (None, ""):
        _queue_index_append(state["commands_by_expire_sec"], str(expire_sec), rec)
    if values["expires_at"]:
        _queue_index_append(state["commands_by_expires_at"], values["expires_at"], rec)
    _queue_index_append(
        state["commands_by_expired"],
        "true" if rec.get("expired") is True else "false",
        rec,
    )
    if values["created_at"] > state["latest_created_at"]:
        state["latest_created_at"] = values["created_at"]
    if values["result_received_at"] > state["latest_result_received_at"]:
        state["latest_result_received_at"] = values["result_received_at"]


def _apply_command_queue_execution_indexes(state, rec, values):
    if values["execution_decision"]:
        _queue_index_append(
            state["commands_by_execution_decision"],
            values["execution_decision"],
            rec,
        )
        _queue_index_count(
            state["execution_decision_counts"],
            values["execution_decision"],
        )


def _apply_command_queue_result_indexes(state, rec, status):
    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    result_status = str(result.get("status") or "")
    result_exit_code = result.get("exit_code")
    if result_status:
        _queue_index_append(state["commands_by_result_status"], result_status, rec)
        _queue_index_count(state["result_status_counts"], result_status)
    if result_exit_code not in (None, ""):
        key = str(result_exit_code)
        _queue_index_append(state["commands_by_result_exit_code"], key, rec)
        _queue_index_count(state["result_exit_code_counts"], key)
    if status == "result-received":
        output_key = "yes" if rec.get("result_output_exceeded_limit") is True else "no"
        _queue_index_append(state["commands_by_result_output_exceeded"], output_key, rec)
        size_bucket = command_result_output_size_bucket(rec.get("result_output_bytes"))
        rec["result_output_size_bucket"] = size_bucket
        _queue_index_append(
            state["commands_by_result_output_size_bucket"],
            size_bucket,
            rec,
        )
        _queue_index_count(state["result_output_size_bucket_counts"], size_bucket)


def _command_queue_record_index_result(state):
    return {
        "commands_by_id": state["commands_by_id"],
        "commands_by_status": state["commands_by_status"],
        "commands_by_command_sha256": state["commands_by_command_sha256"],
        "commands_by_target_id": state["commands_by_target_id"],
        "commands_by_created_at": state["commands_by_created_at"],
        "commands_by_delivered_at": state["commands_by_delivered_at"],
        "commands_by_result_received_at": state["commands_by_result_received_at"],
        "commands_by_result_source_path": state["commands_by_result_source_path"],
        "commands_by_timeout_sec": state["commands_by_timeout_sec"],
        "commands_by_max_output_bytes": state["commands_by_max_output_bytes"],
        "commands_by_expire_sec": state["commands_by_expire_sec"],
        "commands_by_expires_at": state["commands_by_expires_at"],
        "commands_by_expired": state["commands_by_expired"],
        "commands_by_execution_decision": state["commands_by_execution_decision"],
        "commands_by_result_status": state["commands_by_result_status"],
        "commands_by_result_exit_code": state["commands_by_result_exit_code"],
        "commands_by_result_output_exceeded": state["commands_by_result_output_exceeded"],
        "commands_by_result_output_size_bucket": state["commands_by_result_output_size_bucket"],
        "status_counts": state["status_counts"],
        "execution_decision_counts": state["execution_decision_counts"],
        "result_status_counts": state["result_status_counts"],
        "result_exit_code_counts": state["result_exit_code_counts"],
        "result_output_size_bucket_counts": state["result_output_size_bucket_counts"],
        "latest_created_at": state["latest_created_at"],
        "latest_result_received_at": state["latest_result_received_at"],
    }


def command_queue_record_indexes(commands):
    state = _empty_command_queue_record_index_state()
    for rec in commands:
        if not isinstance(rec, dict):
            continue
        values = _command_queue_index_values(rec)
        _apply_command_queue_base_indexes(state, rec, values)
        _apply_command_queue_timing_indexes(state, rec, values)
        _apply_command_queue_execution_indexes(state, rec, values)
        _apply_command_queue_result_indexes(state, rec, values["status"])
    return _command_queue_record_index_result(state)
