"""Command queue policy and mode helpers for grit-console."""

import hashlib
import json
import os
import time
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, record_count_by_nested_key,
    records_by_key, records_by_nested_key,
)
from gritlib.session_state import (
    atomic_write_json, parse_utc_timestamp, read_json_file, utc_from_epoch,
    utc_now,
)


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def print_command_queue_mode_lines(queue):
    mode_summary = queue.get("mode_summary") or {}
    print(
        "  modes: "
        f"total={mode_summary.get('mode_count', 0)} "
        f"would_poll_if_configured={mode_summary.get('polling_mode_count', 0)} "
        f"operator_host_required={mode_summary.get('operator_host_required_mode_count', 0)} "
        f"delivery_supported={mode_summary.get('delivery_supported_mode_count', 0)} "
        f"result_upload_supported={mode_summary.get('result_upload_supported_mode_count', 0)} "
        f"execution_supported={mode_summary.get('execution_supported_mode_count', 0)} "
        f"active_control_channel={mode_summary.get('active_control_channel_mode_count', 0)}"
    )
    for name in ("status", "poll", "once", "daemon", "stop"):
        rec = (queue.get("mode_semantics") or {}).get(name) or {}
        print(
            f"  mode {name}: "
            f"lifecycle={rec.get('lifecycle', '')} "
            f"requires_operator_host={'yes' if rec.get('requires_operator_host') else 'no'} "
            f"would_poll_if_configured={'yes' if rec.get('would_poll_if_configured') else 'no'} "
            f"execution_supported={'yes' if rec.get('execution_supported') else 'no'} "
            f"active_control_channel={'yes' if rec.get('active_control_channel') else 'no'}"
        )


def print_command_queue(cfg, json_output=False):
    summary = command_queue_summary(cfg)
    delivery_counts = (
        f"enabled={format_counts(summary.get('delivery_policy_enabled_counts') or {})} "
        f"valid={format_counts(summary.get('delivery_policy_valid_counts') or {})} "
        f"execution_mode={format_counts(summary.get('delivery_policy_execution_mode_counts') or {})} "
        f"delivery_supported={format_counts(summary.get('delivery_policy_delivery_supported_counts') or {})} "
        f"result_upload_supported={format_counts(summary.get('delivery_policy_result_upload_supported_counts') or {})} "
        f"active_control_channel={format_counts(summary.get('delivery_policy_active_control_channel_counts') or {})}"
    )
    if json_output:
        print(json.dumps({"schema": 1, "command_queue": summary}, indent=2, sort_keys=True))
        return
    if not summary["commands"]:
        print(f"Command queue: {summary['path']}")
        print(f"  enabled={summary['enabled']} default_enabled=no port={summary['port']} tls={summary['tls']} require_token={summary['require_token']}")
        print(f"  allowed_commands={summary['allowed_commands']} execution_mode={summary['execution_mode']} allow_arbitrary={summary['allow_arbitrary']} execution_supported={command_queue_policy_yes_no(summary, 'execution_supported')} delivery_supported={command_queue_policy_yes_no(summary, 'delivery_supported')} result_upload_supported={command_queue_policy_yes_no(summary, 'result_upload_supported')}")
        print(f"  arbitrary_policy_requested={command_queue_policy_yes_no(summary, 'arbitrary_policy_requested')} arbitrary_execution_allowed={command_queue_policy_yes_no(summary, 'arbitrary_execution_allowed')}")
        print(f"  policy_valid={'yes' if summary['policy_valid'] else 'no'}")
        for error in summary["policy_errors"]:
            print(f"  policy_error={error}")
        print(f"  command_limits: timeouts={format_counts(summary.get('timeout_sec_counts') or {})} max_output={format_counts(summary.get('max_output_bytes_counts') or {})} expire_sec={format_counts(summary.get('expire_sec_counts') or {})}")
        print(f"  targets: {format_counts(summary.get('target_counts') or {})}")
        print(f"  delivery_policy_counts: {delivery_counts}")
        print(f"  latest_created={summary.get('latest_created_at', '') or '-'} latest_result={summary.get('latest_result_received_at', '') or '-'}")
        print_command_queue_mode_lines(summary)
        print("  no queued commands")
        return
    print(f"Command queue: {summary['path']}")
    print(f"  enabled={summary['enabled']} default_enabled=no port={summary['port']} tls={summary['tls']} require_token={summary['require_token']}")
    print(f"  allowed_commands={summary['allowed_commands']} execution_mode={summary['execution_mode']} allow_arbitrary={summary['allow_arbitrary']} execution_supported={command_queue_policy_yes_no(summary, 'execution_supported')} delivery_supported={command_queue_policy_yes_no(summary, 'delivery_supported')} result_upload_supported={command_queue_policy_yes_no(summary, 'result_upload_supported')}")
    print(f"  arbitrary_policy_requested={command_queue_policy_yes_no(summary, 'arbitrary_policy_requested')} arbitrary_execution_allowed={command_queue_policy_yes_no(summary, 'arbitrary_execution_allowed')}")
    print(f"  policy_valid={'yes' if summary['policy_valid'] else 'no'}")
    for error in summary["policy_errors"]:
        print(f"  policy_error={error}")
    print(f"  command_limits: timeouts={format_counts(summary.get('timeout_sec_counts') or {})} max_output={format_counts(summary.get('max_output_bytes_counts') or {})} expire_sec={format_counts(summary.get('expire_sec_counts') or {})}")
    print(f"  targets: {format_counts(summary.get('target_counts') or {})}")
    print(f"  delivery_policy_counts: {delivery_counts}")
    print(f"  latest_created={summary.get('latest_created_at', '') or '-'} latest_result={summary.get('latest_result_received_at', '') or '-'}")
    print_command_queue_mode_lines(summary)
    for rec in summary["commands"]:
        print(f"{rec.get('id', '')}\t{rec.get('status', '')}\tcreated={rec.get('created_at', '')}")
        print(f"  command: {rec.get('command', '')}")
        print(f"  timeout={rec.get('timeout_sec', '')} max_output={rec.get('max_output_bytes', '')} expire_sec={rec.get('expire_sec', '')} expires_at={rec.get('expires_at', '') or '-'} expired={yes_no(rec.get('expired'))} execution_supported={yes_no(rec.get('execution_supported'))}")
        if rec.get("target_id"):
            print(f"  target: {rec.get('target_id', '')} label={rec.get('target_label', '')}")
        delivery_policy = rec.get("delivery_policy_snapshot") if isinstance(rec.get("delivery_policy_snapshot"), dict) else {}
        if delivery_policy:
            print(
                "  delivery_policy: "
                f"enabled={yes_no(delivery_policy.get('enabled'))} "
                f"valid={yes_no(delivery_policy.get('valid'))} "
                f"execution_mode={delivery_policy.get('execution_mode', '')} "
                f"delivery_supported={yes_no(delivery_policy.get('delivery_supported'))} "
                f"result_upload_supported={yes_no(delivery_policy.get('result_upload_supported'))} "
                f"active_control_channel={yes_no(delivery_policy.get('active_control_channel'))}"
            )
        elif rec.get("queue_policy_snapshot"):
            queue_policy = rec.get("queue_policy_snapshot") if isinstance(rec.get("queue_policy_snapshot"), dict) else {}
            print(
                "  queue_policy: "
                f"enabled={yes_no(queue_policy.get('enabled'))} "
                f"valid={yes_no(queue_policy.get('valid'))} "
                f"execution_mode={queue_policy.get('execution_mode', '')} "
                f"delivery_supported={yes_no(queue_policy.get('delivery_supported'))} "
                f"result_upload_supported={yes_no(queue_policy.get('result_upload_supported'))} "
                f"active_control_channel={yes_no(queue_policy.get('active_control_channel'))}"
            )
        if rec.get("result_received_at"):
            print(f"  result: {rec.get('result_received_at', '')} source={rec.get('result_source_path', '')}")
            print(f"  result_output={rec.get('result_output_bytes', '')} limit={rec.get('result_output_limit_bytes', '')} exceeded_limit={'yes' if rec.get('result_output_exceeded_limit') else 'no'}")


def print_workbench_command_queue_summary(queue):
    print("Command queue:")
    print(f"  path: {queue.get('path', '')}")
    print(f"  enabled={queue.get('enabled', 'no')} default_enabled=no port={queue.get('port', '')} tls={queue.get('tls', '')} require_token={queue.get('require_token', '')} token_configured={'yes' if queue.get('token_configured') else 'no'} token_source={queue.get('token_source', '')}")
    print(f"  allowed_commands={queue.get('allowed_commands', '')} execution_mode={queue.get('execution_mode', 'metadata-only')} allow_arbitrary={queue.get('allow_arbitrary', '')} active_control_channel={command_queue_policy_yes_no(queue, 'active_control_channel')}")
    print(f"  policy_valid={'yes' if queue.get('policy_valid') else 'no'} configured_for_polling={command_queue_policy_yes_no(queue, 'configured_for_polling')} arbitrary_policy_requested={command_queue_policy_yes_no(queue, 'arbitrary_policy_requested')} arbitrary_execution_allowed={command_queue_policy_yes_no(queue, 'arbitrary_execution_allowed')}")
    print(f"  policy_flags: operator_queue_records_only={command_queue_policy_yes_no(queue, 'operator_queue_records_only')} metadata_only_default={command_queue_policy_yes_no(queue, 'metadata_only_default')} safe_disabled_default={command_queue_policy_yes_no(queue, 'safe_disabled_default')}")
    print(f"  transport_support: poll={command_queue_policy_yes_no(queue, 'poll_transport_supported')} live_polling={command_queue_policy_yes_no(queue, 'live_polling_supported')}")
    for error in queue.get("policy_errors") or []:
        print(f"  policy_error={error}")
    print(f"  queued: {queue.get('queued_count', 0)} results={queue.get('result_count', 0)} output_exceeded={queue.get('result_output_exceeded_count', 0)} total={queue.get('total_count', 0)} execution_supported={command_queue_policy_yes_no(queue, 'execution_supported')} delivery_supported={command_queue_policy_yes_no(queue, 'delivery_supported')} result_upload_supported={command_queue_policy_yes_no(queue, 'result_upload_supported')}")
    print(f"  command_limits: timeouts={format_counts(queue.get('timeout_sec_counts') or {})} max_output={format_counts(queue.get('max_output_bytes_counts') or {})} expire_sec={format_counts(queue.get('expire_sec_counts') or {})}")
    print(f"  targets: {format_counts(queue.get('target_counts') or {})}")
    print(f"  result_size_buckets: {format_counts(queue.get('result_output_size_bucket_counts') or {})}")
    print(f"  latest_created={queue.get('latest_created_at', '') or '-'} latest_result={queue.get('latest_result_received_at', '') or '-'}")
    print_command_queue_mode_lines(queue)
    for rec in (queue.get("commands") or [])[:8]:
        print(f"  {rec.get('id', '')} {rec.get('status', '')} {rec.get('command', '')}")
        if rec.get("target_id"):
            print(f"    target: {rec.get('target_id', '')} label={rec.get('target_label', '')}")
        if rec.get("result_received_at"):
            print(f"    result: {rec.get('result_received_at', '')} source={rec.get('result_source_path', '')}")
            print(f"    result_output={rec.get('result_output_bytes', '')} limit={rec.get('result_output_limit_bytes', '')} exceeded_limit={'yes' if rec.get('result_output_exceeded_limit') else 'no'}")


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


def mark_command_delivered(cfg, command_id, remote_addr="", target_identity=None):
    data = load_command_queue(cfg)
    for rec in data.get("commands", []):
        if isinstance(rec, dict) and rec.get("id") == command_id:
            if command_queue_expired(rec):
                raise ValueError(f"command queue id expired: {command_id}")
            policy = command_queue_delivery_policy_snapshot(cfg)
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
            rec["execution_decision_reason"] = "" if policy.get("execution_supported") else command_queue_execution_rejection_reason(cfg)
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
    from gritlib.target_records import configured_target_filter, target_context_fields

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
    queue_policy = command_queue_policy_snapshot(cfg)
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


def record_command_result(cfg, command_id, result_path):
    path = Path(result_path).expanduser()
    if not path.is_file():
        raise ValueError(f"command result JSON does not exist: {path}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"command result JSON is invalid: {exc}") from exc
    return record_command_result_payload(cfg, command_id, result, str(path))


def command_queue_summary(cfg):
    from gritlib.target_records import configured_target_filter, records_for_target

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
    queued = [rec for rec in commands if isinstance(rec, dict) and rec.get("status") == "queued"]
    delivered = [rec for rec in commands if isinstance(rec, dict) and rec.get("status") == "delivered"]
    commands_by_id = {}
    commands_by_status = {}
    commands_by_command_sha256 = {}
    commands_by_created_at = {}
    commands_by_delivered_at = {}
    commands_by_result_received_at = {}
    commands_by_result_source_path = {}
    commands_by_timeout_sec = {}
    commands_by_expire_sec = {}
    commands_by_expires_at = {}
    commands_by_expired = {}
    commands_by_max_output_bytes = {}
    commands_by_execution_decision = {}
    commands_by_result_status = {}
    commands_by_result_exit_code = {}
    commands_by_result_output_exceeded = {}
    commands_by_result_output_size_bucket = {}
    commands_by_target_id = {}
    commands_by_queue_policy_enabled = {}
    commands_by_queue_policy_valid = {}
    commands_by_queue_policy_execution_mode = {}
    commands_by_queue_policy_allowed_commands = {}
    commands_by_delivery_policy_enabled = {}
    commands_by_delivery_policy_valid = {}
    commands_by_delivery_policy_execution_mode = {}
    commands_by_delivery_policy_delivery_supported = {}
    commands_by_delivery_policy_result_upload_supported = {}
    commands_by_delivery_policy_active_control_channel = {}
    status_counts = {}
    execution_decision_counts = {}
    result_status_counts = {}
    result_exit_code_counts = {}
    result_output_size_bucket_counts = {}
    latest_created_at = ""
    latest_result_received_at = ""
    for rec in commands:
        if not isinstance(rec, dict):
            continue
        command_id = str(rec.get("id") or "")
        status = str(rec.get("status") or "")
        command_text = str(rec.get("command") or "")
        command_sha256 = str(rec.get("command_sha256") or "")
        if command_text and not command_sha256:
            command_sha256 = hashlib.sha256(command_text.encode("utf-8")).hexdigest()
            rec["command_sha256"] = command_sha256
        execution_decision = str(rec.get("execution_decision") or "")
        created_at = str(rec.get("created_at") or "")
        delivered_at = str(rec.get("delivered_at") or "")
        result_received_at = str(rec.get("result_received_at") or "")
        result_source_path = str(rec.get("result_source_path") or "")
        expires_at = str(rec.get("expires_at") or "")
        if command_id:
            commands_by_id[command_id] = rec
        if status:
            commands_by_status.setdefault(status, []).append(rec)
            status_counts[status] = status_counts.get(status, 0) + 1
        if command_sha256:
            commands_by_command_sha256.setdefault(command_sha256, []).append(rec)
        target_id = str(rec.get("target_id") or "")
        if target_id:
            commands_by_target_id.setdefault(target_id, []).append(rec)
        if created_at:
            commands_by_created_at.setdefault(created_at, []).append(rec)
        if delivered_at:
            commands_by_delivered_at.setdefault(delivered_at, []).append(rec)
        if result_received_at:
            commands_by_result_received_at.setdefault(result_received_at, []).append(rec)
        if result_source_path:
            commands_by_result_source_path.setdefault(result_source_path, []).append(rec)
        timeout_sec = rec.get("timeout_sec")
        if timeout_sec not in (None, ""):
            key = str(timeout_sec)
            commands_by_timeout_sec.setdefault(key, []).append(rec)
        max_output_bytes = rec.get("max_output_bytes")
        if max_output_bytes not in (None, ""):
            key = str(max_output_bytes)
            commands_by_max_output_bytes.setdefault(key, []).append(rec)
        expire_sec = rec.get("expire_sec")
        if expire_sec not in (None, ""):
            key = str(expire_sec)
            commands_by_expire_sec.setdefault(key, []).append(rec)
        if expires_at:
            commands_by_expires_at.setdefault(expires_at, []).append(rec)
        commands_by_expired.setdefault("true" if rec.get("expired") is True else "false", []).append(rec)
        if execution_decision:
            commands_by_execution_decision.setdefault(execution_decision, []).append(rec)
            execution_decision_counts[execution_decision] = execution_decision_counts.get(execution_decision, 0) + 1
        if created_at > latest_created_at:
            latest_created_at = created_at
        if result_received_at > latest_result_received_at:
            latest_result_received_at = result_received_at
        result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
        result_status = str(result.get("status") or "")
        result_exit_code = result.get("exit_code")
        if result_status:
            commands_by_result_status.setdefault(result_status, []).append(rec)
            result_status_counts[result_status] = result_status_counts.get(result_status, 0) + 1
        if result_exit_code not in (None, ""):
            key = str(result_exit_code)
            commands_by_result_exit_code.setdefault(key, []).append(rec)
            result_exit_code_counts[key] = result_exit_code_counts.get(key, 0) + 1
        if status == "result-received":
            output_key = "yes" if rec.get("result_output_exceeded_limit") is True else "no"
            commands_by_result_output_exceeded.setdefault(output_key, []).append(rec)
            size_bucket = command_result_output_size_bucket(rec.get("result_output_bytes"))
            rec["result_output_size_bucket"] = size_bucket
            commands_by_result_output_size_bucket.setdefault(size_bucket, []).append(rec)
            result_output_size_bucket_counts[size_bucket] = result_output_size_bucket_counts.get(size_bucket, 0) + 1
    commands_by_queue_policy_enabled = records_by_nested_key(commands, "queue_policy_snapshot", "enabled")
    commands_by_queue_policy_valid = records_by_nested_key(commands, "queue_policy_snapshot", "valid")
    commands_by_queue_policy_execution_mode = records_by_nested_key(commands, "queue_policy_snapshot", "execution_mode")
    commands_by_queue_policy_allowed_commands = records_by_nested_key(commands, "queue_policy_snapshot", "allowed_commands")
    commands_by_delivery_policy_enabled = records_by_nested_key(commands, "delivery_policy_snapshot", "enabled")
    commands_by_delivery_policy_valid = records_by_nested_key(commands, "delivery_policy_snapshot", "valid")
    commands_by_delivery_policy_execution_mode = records_by_nested_key(commands, "delivery_policy_snapshot", "execution_mode")
    commands_by_delivery_policy_delivery_supported = records_by_nested_key(commands, "delivery_policy_snapshot", "delivery_supported")
    commands_by_delivery_policy_result_upload_supported = records_by_nested_key(commands, "delivery_policy_snapshot", "result_upload_supported")
    commands_by_delivery_policy_active_control_channel = records_by_nested_key(commands, "delivery_policy_snapshot", "active_control_channel")
    result_count = len([rec for rec in commands if isinstance(rec, dict) and rec.get("status") == "result-received"])
    result_exceeded_count = len([
        rec for rec in commands
        if isinstance(rec, dict) and rec.get("result_output_exceeded_limit") is True
    ])
    enabled = str(cfg.get("GRIT_COMMAND_QUEUE_ENABLE", "no"))
    allowed_commands = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "none"))
    execution_mode = str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only"))
    allow_arbitrary = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "no"))
    poll_interval_sec = str(cfg.get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC", "5"))
    poll_jitter_pct = str(cfg.get("GRIT_COMMAND_QUEUE_POLL_JITTER_PCT", "0"))
    poll_backoff = str(cfg.get("GRIT_COMMAND_QUEUE_POLL_BACKOFF", "none"))
    poll_max_interval_sec = str(cfg.get("GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC", "300"))
    max_polls = str(cfg.get("GRIT_COMMAND_QUEUE_MAX_POLLS", "0"))
    tls = str(cfg.get("GRIT_COMMAND_QUEUE_TLS", "yes"))
    poll_transport_supported = tls == "no"
    poll_transport_unsupported_reason = "" if poll_transport_supported else "live command queue polling requires GRIT_COMMAND_QUEUE_TLS=no in this build"
    policy_errors = command_queue_policy_errors(cfg)
    policy_valid = not policy_errors
    token_required = str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")) == "yes"
    token_configured = bool(str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN", "")))
    arbitrary_policy_requested = policy_valid and enabled == "yes" and allowed_commands == "custom" and allow_arbitrary == "yes"
    execution_supported = command_queue_execution_supported(cfg)
    arbitrary_execution_allowed = arbitrary_policy_requested and execution_supported
    configured_for_polling = policy_valid and enabled == "yes"
    mode_semantics = command_queue_mode_semantics(poll_transport_supported, execution_supported)
    mode_records = command_queue_mode_records(mode_semantics)
    mode_indexes = command_queue_mode_record_indexes(mode_records)
    mode_summary = command_queue_mode_summary(mode_semantics)
    policy_summary = {
        "enabled": enabled == "yes",
        "default_enabled": False,
        "valid": policy_valid,
        "error_count": len(policy_errors),
        "configured_for_polling": configured_for_polling,
        "operator_queue_records_only": True,
        "execution_mode": execution_mode,
        "metadata_only_default": execution_mode == "metadata-only",
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "delivery_supported": False,
        "result_upload_supported": True,
        "poll_transport_supported": poll_transport_supported,
        "live_polling_supported": poll_transport_supported,
        "poll_transport_unsupported_reason": poll_transport_unsupported_reason,
        "active_control_channel": False,
        "token_required": token_required,
        "token_configured": token_configured,
        "poll_interval_sec": poll_interval_sec,
        "poll_jitter_pct": poll_jitter_pct,
        "poll_backoff": poll_backoff,
        "poll_max_interval_sec": poll_max_interval_sec,
        "max_polls": max_polls,
        "arbitrary_policy_requested": arbitrary_policy_requested,
        "arbitrary_execution_allowed": arbitrary_execution_allowed,
        "safe_disabled_default": enabled == "no" and policy_valid and allowed_commands == "none" and execution_mode == "metadata-only" and allow_arbitrary == "no",
    }
    return {
        "path": str(command_queue_path(cfg)),
        "enabled": enabled,
        "default_enabled": False,
        "port": str(cfg.get("GRIT_COMMAND_QUEUE_PORT", "22205")),
        "tls": tls,
        "require_token": str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")),
        "token_source": str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN_SOURCE", "manual")),
        "token_configured": token_configured,
        "allowed_commands": allowed_commands,
        "execution_mode": execution_mode,
        "metadata_only_default": execution_mode == "metadata-only",
        "allow_arbitrary": allow_arbitrary,
        "poll_interval_sec": poll_interval_sec,
        "poll_jitter_pct": poll_jitter_pct,
        "poll_backoff": poll_backoff,
        "poll_max_interval_sec": poll_max_interval_sec,
        "max_polls": max_polls,
        "policy_valid": policy_valid,
        "policy_errors": policy_errors,
        "policy_summary": policy_summary,
        "poll_transport_supported": poll_transport_supported,
        "live_polling_supported": poll_transport_supported,
        "poll_transport_unsupported_reason": poll_transport_unsupported_reason,
        "mode_semantics": mode_semantics,
        "mode_records": mode_records,
        **mode_indexes,
        "mode_summary": mode_summary,
        "commands": commands,
        "commands_by_id": commands_by_id,
        "commands_by_status": commands_by_status,
        "commands_by_command_sha256": commands_by_command_sha256,
        "commands_by_target_id": commands_by_target_id,
        "commands_by_created_at": commands_by_created_at,
        "commands_by_delivered_at": commands_by_delivered_at,
        "commands_by_result_received_at": commands_by_result_received_at,
        "commands_by_result_source_path": commands_by_result_source_path,
        "commands_by_timeout_sec": commands_by_timeout_sec,
        "commands_by_max_output_bytes": commands_by_max_output_bytes,
        "commands_by_expire_sec": commands_by_expire_sec,
        "commands_by_expires_at": commands_by_expires_at,
        "commands_by_expired": commands_by_expired,
        "commands_by_execution_decision": commands_by_execution_decision,
        "commands_by_result_status": commands_by_result_status,
        "commands_by_result_exit_code": commands_by_result_exit_code,
        "commands_by_result_output_exceeded": commands_by_result_output_exceeded,
        "commands_by_result_output_size_bucket": commands_by_result_output_size_bucket,
        "commands_by_queue_policy_enabled": commands_by_queue_policy_enabled,
        "commands_by_queue_policy_valid": commands_by_queue_policy_valid,
        "commands_by_queue_policy_execution_mode": commands_by_queue_policy_execution_mode,
        "commands_by_queue_policy_allowed_commands": commands_by_queue_policy_allowed_commands,
        "commands_by_delivery_policy_enabled": commands_by_delivery_policy_enabled,
        "commands_by_delivery_policy_valid": commands_by_delivery_policy_valid,
        "commands_by_delivery_policy_execution_mode": commands_by_delivery_policy_execution_mode,
        "commands_by_delivery_policy_delivery_supported": commands_by_delivery_policy_delivery_supported,
        "commands_by_delivery_policy_result_upload_supported": commands_by_delivery_policy_result_upload_supported,
        "commands_by_delivery_policy_active_control_channel": commands_by_delivery_policy_active_control_channel,
        "status_counts": status_counts,
        "timeout_sec_counts": record_count_by_key(commands, "timeout_sec"),
        "max_output_bytes_counts": record_count_by_key(commands, "max_output_bytes"),
        "expire_sec_counts": record_count_by_key(commands, "expire_sec"),
        "expired_counts": record_count_by_key(commands, "expired"),
        "target_counts": record_count_by_key(commands, "target_id"),
        "execution_decision_counts": execution_decision_counts,
        "result_status_counts": result_status_counts,
        "result_exit_code_counts": result_exit_code_counts,
        "result_output_size_bucket_counts": result_output_size_bucket_counts,
        "queue_policy_enabled_counts": record_count_by_nested_key(commands, "queue_policy_snapshot", "enabled"),
        "queue_policy_valid_counts": record_count_by_nested_key(commands, "queue_policy_snapshot", "valid"),
        "queue_policy_execution_mode_counts": record_count_by_nested_key(commands, "queue_policy_snapshot", "execution_mode"),
        "queue_policy_allowed_commands_counts": record_count_by_nested_key(commands, "queue_policy_snapshot", "allowed_commands"),
        "delivery_policy_enabled_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "enabled"),
        "delivery_policy_valid_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "valid"),
        "delivery_policy_execution_mode_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "execution_mode"),
        "delivery_policy_delivery_supported_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "delivery_supported"),
        "delivery_policy_result_upload_supported_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "result_upload_supported"),
        "delivery_policy_active_control_channel_counts": record_count_by_nested_key(commands, "delivery_policy_snapshot", "active_control_channel"),
        "latest_created_at": latest_created_at,
        "latest_result_received_at": latest_result_received_at,
        "queued_count": len(queued),
        "delivered_count": len(delivered),
        "result_count": result_count,
        "result_output_exceeded_count": result_exceeded_count,
        "total_count": len(commands),
        "target_filter_active": bool(target_filter_id),
        "target_filter_id": target_filter_id,
        "unfiltered_total_count": unfiltered_command_count,
        "execution_supported": execution_supported,
        "delivery_supported": False,
        "result_upload_supported": True,
        "poll_transport_supported": poll_transport_supported,
        "live_polling_supported": poll_transport_supported,
        "poll_transport_unsupported_reason": poll_transport_unsupported_reason,
        "executes_commands": execution_supported,
        "operator_queue_records_only": True,
        "active_control_channel": False,
        "configured_for_polling": configured_for_polling,
        "arbitrary_policy_requested": arbitrary_policy_requested,
        "arbitrary_execution_allowed": arbitrary_execution_allowed,
        "safety_boundary": "explicit operator queue records only; execution requires explicit target poll and execute policy",
    }


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


def yes_no(value):
    return "yes" if value is True else "no"


def command_queue_policy_value(queue, key, default=False):
    if isinstance(queue, dict):
        policy = queue.get("policy_summary") if isinstance(queue.get("policy_summary"), dict) else {}
        if key in policy:
            return policy.get(key)
        if key in queue:
            return queue.get(key)
    return default


def command_queue_policy_yes_no(queue, key, default=False):
    return yes_no(command_queue_policy_value(queue, key, default))


def valid_yes_no(value):
    return str(value) in ("yes", "no")


def valid_uint_string(value):
    text = str(value)
    return bool(text) and text.isdigit()


def valid_header_token(value):
    text = str(value)
    return "\r" not in text and "\n" not in text


def command_queue_policy_errors(cfg):
    errors = []
    enabled = str(cfg.get("GRIT_COMMAND_QUEUE_ENABLE", "no"))
    allowed = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "none"))
    execution = str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only"))
    allow_arbitrary = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "no"))
    if not valid_yes_no(enabled):
        errors.append("invalid command queue enable value")
    if not valid_uint_string(cfg.get("GRIT_COMMAND_QUEUE_PORT", "22205")):
        errors.append("invalid command queue port")
    if not valid_uint_string(cfg.get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC", "5")):
        errors.append("invalid command queue poll interval")
    if not valid_uint_string(cfg.get("GRIT_COMMAND_QUEUE_POLL_JITTER_PCT", "0")):
        errors.append("invalid command queue poll jitter")
    if str(cfg.get("GRIT_COMMAND_QUEUE_POLL_BACKOFF", "none")) not in ("none", "linear", "exponential"):
        errors.append("invalid command queue poll backoff")
    if not valid_uint_string(cfg.get("GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC", "300")):
        errors.append("invalid command queue poll max interval")
    if not valid_uint_string(cfg.get("GRIT_COMMAND_QUEUE_MAX_POLLS", "0")):
        errors.append("invalid command queue max polls")
    if not valid_yes_no(cfg.get("GRIT_COMMAND_QUEUE_TLS", "yes")):
        errors.append("invalid command queue TLS value")
    if not valid_yes_no(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")):
        errors.append("invalid command queue token requirement")
    if str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN_SOURCE", "manual")) not in ("manual", "generated"):
        errors.append("invalid command queue token source")
    if not valid_header_token(cfg.get("GRIT_COMMAND_QUEUE_TOKEN", "")):
        errors.append("invalid command queue token value")
    if enabled == "yes" and str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")) == "yes" and not str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN", "")):
        errors.append("enabled command queue requires command_queue_token when token requirement is yes")
    if allowed not in ("none", "grit-only", "allowlist", "custom"):
        errors.append("invalid command queue allowed commands policy")
    if execution not in ("metadata-only", "execute"):
        errors.append("invalid command queue execution mode")
    if not valid_yes_no(allow_arbitrary):
        errors.append("invalid command queue arbitrary-execution flag")
    if enabled != "yes":
        if allowed != "none":
            errors.append("disabled command queue must keep allowed commands policy none")
        if execution != "metadata-only":
            errors.append("disabled command queue must keep execution mode metadata-only")
        if allow_arbitrary != "no":
            errors.append("disabled command queue must not allow arbitrary execution")
    if execution == "execute" and allowed == "none":
        errors.append("command queue execution mode execute requires a non-none allowed commands policy")
    if allow_arbitrary == "yes" and allowed != "custom":
        errors.append("arbitrary command queue execution requires allowed commands policy custom")
    return errors


def command_queue_execution_supported(cfg):
    if command_queue_policy_errors(cfg):
        return False
    enabled = str(cfg.get("GRIT_COMMAND_QUEUE_ENABLE", "no"))
    allowed = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "none"))
    execution = str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only"))
    allow_arbitrary = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "no"))
    if enabled != "yes" or execution != "execute":
        return False
    if allowed == "grit-only":
        return True
    if allowed == "custom" and allow_arbitrary == "yes":
        return True
    return False


def command_queue_execution_rejection_reason(cfg):
    if str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")) == "metadata-only":
        return "command queue execution mode is metadata-only"
    allowed = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "none"))
    allow_arbitrary = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "no"))
    if allowed == "none":
        return "command queue execution mode execute requires a non-none allowed commands policy"
    if allowed == "allowlist":
        return "command queue allowlist execution is not configured in this build"
    if allowed == "custom" and allow_arbitrary != "yes":
        return "custom command queue execution requires command_queue_allow_arbitrary=yes"
    if command_queue_policy_errors(cfg):
        return "command queue execution policy is invalid"
    return "command queue execution policy does not permit this command"


def command_queue_token_valid(cfg, headers):
    if str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")) != "yes":
        return True
    expected = str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN", ""))
    supplied = str(
        (headers or {}).get("x-grit-command-queue-token") or
        (headers or {}).get("x-grittykit-command-queue-token") or
        ""
    )
    return bool(expected) and supplied == expected


def command_queue_policy_snapshot(cfg):
    errors = command_queue_policy_errors(cfg)
    enabled = str(cfg.get("GRIT_COMMAND_QUEUE_ENABLE", "no"))
    allowed_commands = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS", "none"))
    execution_mode = str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only"))
    allow_arbitrary = str(cfg.get("GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY", "no"))
    token_required = str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")) == "yes"
    token_configured = bool(str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN", "")))
    execution_supported = command_queue_execution_supported(cfg)
    arbitrary_execution_allowed = execution_supported and allowed_commands == "custom" and allow_arbitrary == "yes"
    return {
        "enabled": enabled == "yes",
        "valid": not errors,
        "errors": errors,
        "allowed_commands": allowed_commands,
        "execution_mode": execution_mode,
        "metadata_only_default": execution_mode == "metadata-only",
        "allow_arbitrary": allow_arbitrary == "yes",
        "token_required": token_required,
        "token_configured": token_configured,
        "execution_supported": execution_supported,
        "executes_commands": execution_supported,
        "delivery_supported": False,
        "result_upload_supported": True,
        "active_control_channel": False,
        "arbitrary_execution_allowed": arbitrary_execution_allowed,
        "operator_queue_records_only": True,
        "safety_boundary": "explicit operator queue record; target execution requires an explicit target poll and execute policy",
    }


def command_queue_delivery_policy_snapshot(cfg):
    policy = command_queue_policy_snapshot(cfg)
    policy.update({
        "delivery_supported": True,
        "result_upload_supported": True,
        "delivery_mode": str(cfg.get("GRIT_COMMAND_QUEUE_EXECUTION", "metadata-only")),
        "active_control_channel": True,
        "operator_queue_records_only": False,
        "safety_boundary": "explicit opt-in delivery on target poll; target execution depends on target-side command queue policy",
    })
    return policy


COMMAND_QUEUE_WORK_METADATA_FIELDS = (
    "work_kind",
    "workflow",
    "request_name",
    "bridge_profile",
    "bridge_route_path",
    "bridge_requires_target_online",
    "route_kind",
)


def command_queue_work_metadata(rec):
    if not isinstance(rec, dict):
        return {}
    return {
        key: rec.get(key)
        for key in COMMAND_QUEUE_WORK_METADATA_FIELDS
        if rec.get(key) not in (None, "")
    }


def command_queue_poll_outcome_event(status):
    return {
        "delivered": "command_queue_poll_delivered",
        "no-command": "command_queue_poll_no_command",
        "rejected": "command_queue_poll_rejected",
        "error": "command_queue_poll_error",
    }.get(str(status or ""))


def command_queue_result_outcome_event(status):
    return {
        "result-received": "command_queue_result_upload_received",
        "rejected": "command_queue_result_upload_rejected",
        "error": "command_queue_result_upload_error",
    }.get(str(status or ""))


def command_queue_mode_semantics(live_transport_supported=True, execution_supported=False):
    modes = {
        "status": {
            "lifecycle": "inspect",
            "requires_operator_host": False,
            "would_poll_if_configured": False,
        },
        "poll": {
            "lifecycle": "single-poll",
            "requires_operator_host": True,
            "would_poll_if_configured": True,
        },
        "once": {
            "lifecycle": "single-cycle",
            "requires_operator_host": True,
            "would_poll_if_configured": True,
        },
        "daemon": {
            "lifecycle": "long-running",
            "requires_operator_host": True,
            "would_poll_if_configured": True,
        },
        "stop": {
            "lifecycle": "stop",
            "requires_operator_host": False,
            "would_poll_if_configured": False,
        },
    }
    for rec in modes.values():
        live_supported = bool(rec.get("would_poll_if_configured")) and bool(live_transport_supported)
        live_execution_supported = live_supported and bool(execution_supported)
        rec.update({
            "dry_run_default": True,
            "dry_run_only": False if live_supported else True,
            "live_supported": live_supported,
            "requires_explicit_target_action": True,
            "would_contact_operator": False,
            "live_would_contact_operator": live_supported,
            "live_transport_supported": bool(live_transport_supported),
            "live_transport_unsupported_reason": "" if live_transport_supported else "live command queue polling requires GRIT_COMMAND_QUEUE_TLS=no in this build",
            "delivery_supported": False,
            "result_upload_supported": True,
            "execution_supported": live_execution_supported,
            "executes_commands": live_execution_supported,
            "active_control_channel": False,
            "operator_supplied_command_execution": live_execution_supported,
        })
    return modes


def command_queue_mode_summary(mode_semantics):
    records = list(mode_semantics.values())
    return {
        "mode_count": len(records),
        "polling_mode_count": len([rec for rec in records if rec.get("would_poll_if_configured")]),
        "operator_host_required_mode_count": len([rec for rec in records if rec.get("requires_operator_host")]),
        "live_supported_mode_count": len([rec for rec in records if rec.get("live_supported")]),
        "delivery_supported_mode_count": len([rec for rec in records if rec.get("delivery_supported")]),
        "result_upload_supported_mode_count": len([rec for rec in records if rec.get("result_upload_supported")]),
        "execution_supported_mode_count": len([rec for rec in records if rec.get("execution_supported")]),
        "active_control_channel_mode_count": len([rec for rec in records if rec.get("active_control_channel")]),
        "operator_supplied_command_execution_mode_count": len([
            rec for rec in records if rec.get("operator_supplied_command_execution")
        ]),
    }


def command_queue_mode_records(mode_semantics):
    records = []
    for mode in sorted(mode_semantics or {}):
        rec = dict(mode_semantics.get(mode) or {})
        rec["mode"] = mode
        records.append(rec)
    return records


def command_queue_mode_record_indexes(records):
    return {
        "command_queue_modes_by_mode": {rec["mode"]: rec for rec in records if rec.get("mode")},
        "command_queue_modes_by_lifecycle": records_by_key(records, "lifecycle"),
        "command_queue_modes_by_requires_operator_host": records_by_key(records, "requires_operator_host"),
        "command_queue_modes_by_would_poll_if_configured": records_by_key(records, "would_poll_if_configured"),
        "command_queue_modes_by_live_supported": records_by_key(records, "live_supported"),
        "command_queue_modes_by_live_transport_supported": records_by_key(records, "live_transport_supported"),
        "command_queue_modes_by_delivery_supported": records_by_key(records, "delivery_supported"),
        "command_queue_modes_by_result_upload_supported": records_by_key(records, "result_upload_supported"),
        "command_queue_modes_by_execution_supported": records_by_key(records, "execution_supported"),
        "command_queue_modes_by_active_control_channel": records_by_key(records, "active_control_channel"),
        "command_queue_modes_by_operator_supplied_command_execution": records_by_key(
            records, "operator_supplied_command_execution"
        ),
    }


def command_result_output_size_bucket(size):
    size = int_value(size)
    if size <= 0:
        return "zero"
    if size <= 1024:
        return "small"
    if size <= 65536:
        return "medium"
    return "large"


def command_queue_policy_status(command_queue):
    policy_summary = command_queue.get("policy_summary") or {}
    policy_record = {
        "id": "command-queue",
        "enabled": bool(policy_summary.get("enabled", False)),
        "default_enabled": bool(policy_summary.get("default_enabled", False)),
        "valid": bool(policy_summary.get("valid", True)),
        "errors": command_queue.get("policy_errors") or [],
        "error_count": len(command_queue.get("policy_errors") or []),
        "configured_for_polling": bool(policy_summary.get("configured_for_polling", False)),
        "operator_queue_records_only": bool(policy_summary.get("operator_queue_records_only", False)),
        "allowed_commands": command_queue.get("allowed_commands", "none"),
        "execution_mode": policy_summary.get("execution_mode", "metadata-only"),
        "metadata_only_default": bool(policy_summary.get("metadata_only_default", False)),
        "execution_supported": bool(policy_summary.get("execution_supported", False)),
        "executes_commands": bool(policy_summary.get("executes_commands", False)),
        "delivery_supported": bool(policy_summary.get("delivery_supported", False)),
        "result_upload_supported": bool(policy_summary.get("result_upload_supported", False)),
        "poll_transport_supported": bool(policy_summary.get("poll_transport_supported", False)),
        "live_polling_supported": bool(policy_summary.get("live_polling_supported", False)),
        "poll_transport_unsupported_reason": policy_summary.get("poll_transport_unsupported_reason", ""),
        "active_control_channel": bool(policy_summary.get("active_control_channel", False)),
        "token_required": bool(policy_summary.get("token_required", False)),
        "token_configured": bool(policy_summary.get("token_configured", False)),
        "poll_interval_sec": policy_summary.get("poll_interval_sec", "5"),
        "poll_jitter_pct": policy_summary.get("poll_jitter_pct", "0"),
        "poll_backoff": policy_summary.get("poll_backoff", "none"),
        "poll_max_interval_sec": policy_summary.get("poll_max_interval_sec", "300"),
        "max_polls": policy_summary.get("max_polls", "0"),
        "arbitrary_policy_requested": bool(policy_summary.get("arbitrary_policy_requested", False)),
        "arbitrary_execution_allowed": bool(policy_summary.get("arbitrary_execution_allowed", False)),
        "safe_disabled_default": bool(policy_summary.get("safe_disabled_default", False)),
        "policy_summary": policy_summary,
    }
    policy_records = [policy_record]
    policy_index_maps = {
        "command_queue_policy_records_by_id": {
            rec.get("id", ""): rec for rec in policy_records if rec.get("id")
        },
        "command_queue_policy_records_by_enabled": records_by_key(policy_records, "enabled"),
        "command_queue_policy_records_by_valid": records_by_key(policy_records, "valid"),
        "command_queue_policy_records_by_configured_for_polling": records_by_key(
            policy_records, "configured_for_polling"
        ),
        "command_queue_policy_records_by_execution_mode": records_by_key(
            policy_records, "execution_mode"
        ),
        "command_queue_policy_records_by_allowed_commands": records_by_key(
            policy_records, "allowed_commands"
        ),
        "command_queue_policy_records_by_token_required": records_by_key(
            policy_records, "token_required"
        ),
        "command_queue_policy_records_by_token_configured": records_by_key(
            policy_records, "token_configured"
        ),
        "command_queue_policy_records_by_safe_disabled_default": records_by_key(
            policy_records, "safe_disabled_default"
        ),
        "command_queue_policy_records_by_poll_transport_supported": records_by_key(
            policy_records, "poll_transport_supported"
        ),
        "command_queue_policy_records_by_live_polling_supported": records_by_key(
            policy_records, "live_polling_supported"
        ),
        "command_queue_policy_records_by_active_control_channel": records_by_key(
            policy_records, "active_control_channel"
        ),
        "command_queue_policy_records_by_arbitrary_execution_allowed": records_by_key(
            policy_records, "arbitrary_execution_allowed"
        ),
    }
    return {
        "policy_record": policy_record,
        "policy_records": policy_records,
        "policy_index_maps": policy_index_maps,
    }


def command_queue_workflow_action_indexes(records):
    return {
        "command_queue_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "command_queue_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "command_queue_workflow_actions_by_category": records_by_key(records, "category"),
        "command_queue_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "command_queue_workflow_actions_by_actual": records_by_key(records, "actual"),
        "command_queue_workflow_actions_by_target_filter_active": records_by_key(records, "target_filter_active"),
        "command_queue_workflow_actions_by_policy_valid": records_by_key(records, "policy_valid"),
        "command_queue_workflow_actions_by_configured_for_polling": records_by_key(records, "configured_for_polling"),
        "command_queue_workflow_actions_by_poll_transport_supported": records_by_key(records, "poll_transport_supported"),
        "command_queue_workflow_actions_by_live_polling_supported": records_by_key(records, "live_polling_supported"),
        "command_queue_workflow_actions_by_result_upload_supported": records_by_key(records, "result_upload_supported"),
        "command_queue_workflow_actions_by_execution_supported": records_by_key(records, "execution_supported"),
        "command_queue_workflow_actions_by_delivery_supported": records_by_key(records, "delivery_supported"),
        "command_queue_workflow_actions_by_operator_queue_records_only": records_by_key(records, "operator_queue_records_only"),
        "command_queue_workflow_actions_by_target_mailbox_pending_target_count": records_by_key(records, "target_mailbox_pending_target_count"),
        "command_queue_workflow_actions_by_target_mailbox_pending_work_count": records_by_key(records, "target_mailbox_pending_work_count"),
        "command_queue_workflow_actions_by_target_mailbox_pending_poll_overdue_count": records_by_key(records, "target_mailbox_pending_poll_overdue_count"),
        "command_queue_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "command_queue_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "command_queue_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "command_queue_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "command_queue_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "command_queue_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "command_queue_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "command_queue_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "command_queue_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "command_queue_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "command_queue_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "command_queue_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "command_queue_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "command_queue_workflow_actions_by_target_phone_home_required": records_by_key(records, "target_phone_home_required"),
        "command_queue_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "command_queue_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "command_queue_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "command_queue_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def command_queue_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "target_phone_home_required_count": len([rec for rec in records or [] if rec.get("target_phone_home_required") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "target_filter_active_counts": record_count_by_key(records, "target_filter_active"),
        "policy_valid_counts": record_count_by_key(records, "policy_valid"),
        "configured_for_polling_counts": record_count_by_key(records, "configured_for_polling"),
        "poll_transport_supported_counts": record_count_by_key(records, "poll_transport_supported"),
        "live_polling_supported_counts": record_count_by_key(records, "live_polling_supported"),
        "result_upload_supported_counts": record_count_by_key(records, "result_upload_supported"),
        "execution_supported_counts": record_count_by_key(records, "execution_supported"),
        "delivery_supported_counts": record_count_by_key(records, "delivery_supported"),
        "operator_queue_records_only_counts": record_count_by_key(records, "operator_queue_records_only"),
        "target_mailbox_pending_target_count_counts": record_count_by_key(records, "target_mailbox_pending_target_count"),
        "target_mailbox_pending_work_count_counts": record_count_by_key(records, "target_mailbox_pending_work_count"),
        "target_mailbox_pending_poll_overdue_count_counts": record_count_by_key(records, "target_mailbox_pending_poll_overdue_count"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "requires_input_counts": record_count_by_key(records, "requires_input"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "queues_offline_work_counts": record_count_by_key(records, "queues_offline_work"),
        "target_phone_home_required_counts": record_count_by_key(records, "target_phone_home_required"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }
