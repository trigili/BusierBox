"""Command queue policy and mode helpers for grit-console."""

import hashlib
import json
import os
import time
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, records_by_key,
)
from gritlib.session_state import (
    atomic_write_json, parse_utc_timestamp, read_json_file, utc_from_epoch,
    utc_now,
)
import gritlib.command_queue_workflow_actions as command_queue_workflow_actions
import gritlib.command_queue_policy as command_queue_policy
from gritlib.target_context import (
    configured_target_filter, records_for_target, target_context_fields,
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


def _print_command_queue_json(summary):
    print(json.dumps({"schema": 1, "command_queue": summary}, indent=2, sort_keys=True))


def _print_command_queue_header(summary):
    print(f"Command queue: {summary['path']}")
    print(
        f"  state: {summary['enabled']}  port {summary['port']}  "
        f"tls {summary['tls']}  token required {summary['require_token']}"
    )


def _print_command_queue_policy(summary):
    policy_state = "valid" if summary["policy_valid"] else "invalid"
    if not summary.get("policy_valid") and not summary.get("policy_errors"):
        policy_state = "not configured"
    print(
        f"  policy: {policy_state}  "
        f"execution {summary['execution_mode']}  "
        f"delivery {command_queue_policy_yes_no(summary, 'delivery_supported')}  "
        f"result upload {command_queue_policy_yes_no(summary, 'result_upload_supported')}"
    )
    for error in summary["policy_errors"]:
        print(f"  policy error: {error}")


def _print_command_queue_counts(summary):
    print(
        f"  queued: {summary.get('queued_count', 0)}  "
        f"results {summary.get('result_count', 0)}  "
        f"total {summary.get('total_count', 0)}"
    )
    print(
        f"  latest: created {summary.get('latest_created_at', '') or '-'}  "
        f"result {summary.get('latest_result_received_at', '') or '-'}"
    )


def _print_command_record_limits(rec):
    print(
        f"  limits: timeout {rec.get('timeout_sec', '')}  "
        f"max output {rec.get('max_output_bytes', '')}  "
        f"expire {rec.get('expire_sec', '')}  "
        f"expires {rec.get('expires_at', '') or '-'}"
    )
    print(
        f"  execution: {'yes' if rec.get('execution_supported') else 'no'}  "
        f"expired {'yes' if rec.get('expired') else 'no'}"
    )


def _print_command_record_target(rec):
    if not rec.get("target_id"):
        return
    target_label = rec.get("target_label", "") or "-"
    print(f"  target: {rec.get('target_id', '')} label={target_label}")


def _print_command_record_policy_snapshot(rec):
    policy = rec.get("delivery_policy_snapshot") if isinstance(rec.get("delivery_policy_snapshot"), dict) else {}
    if not policy and rec.get("queue_policy_snapshot"):
        policy = rec.get("queue_policy_snapshot") if isinstance(rec.get("queue_policy_snapshot"), dict) else {}
    if not policy:
        return
    print(
        "  policy: "
        f"enabled {yes_no(policy.get('enabled'))}  "
        f"valid {yes_no(policy.get('valid'))}  "
        f"delivery {yes_no(policy.get('delivery_supported'))}  "
        f"result upload {yes_no(policy.get('result_upload_supported'))}  "
        f"active control {yes_no(policy.get('active_control_channel'))}"
    )


def _print_command_record_result(rec):
    if not rec.get("result_received_at"):
        return
    print(f"  result: {rec.get('result_received_at', '')} source {rec.get('result_source_path', '')}")
    print(
        f"  output: {rec.get('result_output_bytes', '')} bytes  "
        f"limit {rec.get('result_output_limit_bytes', '')}  "
        f"exceeded {'yes' if rec.get('result_output_exceeded_limit') else 'no'}"
    )


def _print_command_queue_record(rec):
    print(f"{rec.get('id', '')}\t{rec.get('status', '')}\tcreated {rec.get('created_at', '')}")
    print(f"  command: {rec.get('command', '')}")
    _print_command_record_limits(rec)
    _print_command_record_target(rec)
    _print_command_record_policy_snapshot(rec)
    _print_command_record_result(rec)


def _print_command_queue_records(commands):
    if not commands:
        print("  no queued commands")
        return
    for rec in commands:
        _print_command_queue_record(rec)


def print_command_queue(cfg, json_output=False):
    summary = command_queue_summary(cfg)
    if json_output:
        _print_command_queue_json(summary)
        return
    _print_command_queue_header(summary)
    _print_command_queue_policy(summary)
    _print_command_queue_counts(summary)
    _print_command_queue_records(summary["commands"])


def handle_command_queue_args(cfg, args):
    if args.clear_command_queue:
        count = clear_command_queue(cfg)
        print(f"cleared {count} command queue entr{'y' if count == 1 else 'ies'}")
        if not (args.queue_command or args.list_command_queue or args.json_command_queue):
            return 0
    if args.queue_command:
        rec = queue_command(
            cfg,
            args.queue_command,
            timeout_sec=args.queue_timeout,
            max_output_bytes=args.queue_max_output,
            expire_sec=args.queue_expire_sec,
        )
        print(f"queued {rec['id']}: {rec['command']}")
        if rec.get("target_id"):
            print(f"target={rec.get('target_id', '')} label={rec.get('target_label', '')}")
        print(f"execution_supported={'yes' if rec.get('execution_supported') else 'no'} delivery_supported=no")
        if not (args.list_command_queue or args.json_command_queue):
            return 0
    if args.record_command_result:
        if not args.result_json:
            raise ValueError("--record-command-result requires --result-json")
        rec = record_command_result(cfg, args.record_command_result, args.result_json)
        print(f"recorded result for {rec['id']}: status={rec.get('result', {}).get('status', '')}")
        if not (args.list_command_queue or args.json_command_queue):
            return 0
    if args.list_command_queue or args.json_command_queue:
        print_command_queue(cfg, json_output=args.json_command_queue)
        return 0
    return None


def print_workbench_command_queue_summary(queue, include_polling=False):
    print("Command queue:")
    print(f"  path: {queue.get('path', '')}")
    print(f"  enabled={queue.get('enabled', 'no')} default_enabled=no port={queue.get('port', '')} tls={queue.get('tls', '')} require_token={queue.get('require_token', '')} token_configured={'yes' if queue.get('token_configured') else 'no'} token_source={queue.get('token_source', '')}")
    print(f"  allowed_commands={queue.get('allowed_commands', '')} execution_mode={queue.get('execution_mode', 'metadata-only')} allow_arbitrary={queue.get('allow_arbitrary', '')} active_control_channel={command_queue_policy_yes_no(queue, 'active_control_channel')}")
    print(f"  policy_valid={'yes' if queue.get('policy_valid') else 'no'} configured_for_polling={command_queue_policy_yes_no(queue, 'configured_for_polling')} arbitrary_policy_requested={command_queue_policy_yes_no(queue, 'arbitrary_policy_requested')} arbitrary_execution_allowed={command_queue_policy_yes_no(queue, 'arbitrary_execution_allowed')}")
    print(f"  policy_flags: operator_queue_records_only={command_queue_policy_yes_no(queue, 'operator_queue_records_only')} metadata_only_default={command_queue_policy_yes_no(queue, 'metadata_only_default')} safe_disabled_default={command_queue_policy_yes_no(queue, 'safe_disabled_default')}")
    print(f"  transport_support: poll={command_queue_policy_yes_no(queue, 'poll_transport_supported')} live_polling={command_queue_policy_yes_no(queue, 'live_polling_supported')}")
    if include_polling:
        print(f"  polling: interval={queue.get('poll_interval_sec', '')} jitter_pct={queue.get('poll_jitter_pct', '')} backoff={queue.get('poll_backoff', '')} max_interval={queue.get('poll_max_interval_sec', '')} max_polls={queue.get('max_polls', '')}")
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


def _command_queue_visible_commands(cfg):
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


def _command_queue_record_indexes(commands):
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

def _command_queue_policy_context(cfg):
    return command_queue_policy.command_queue_policy_context(cfg)


def _command_queue_policy_indexes(commands):
    return command_queue_policy.command_queue_policy_indexes(commands)


def _command_queue_policy_counts(commands):
    return command_queue_policy.command_queue_policy_counts(commands)


def _command_queue_config_summary(cfg, policy_context):
    return {
        "path": str(command_queue_path(cfg)),
        "enabled": policy_context["enabled"],
        "default_enabled": False,
        "port": str(cfg.get("GRIT_COMMAND_QUEUE_PORT", "22205")),
        "tls": policy_context["tls"],
        "require_token": str(cfg.get("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "yes")),
        "token_source": str(cfg.get("GRIT_COMMAND_QUEUE_TOKEN_SOURCE", "manual")),
        "token_configured": policy_context["token_configured"],
        "allowed_commands": policy_context["allowed_commands"],
        "execution_mode": policy_context["execution_mode"],
        "metadata_only_default": policy_context["execution_mode"] == "metadata-only",
        "allow_arbitrary": policy_context["allow_arbitrary"],
        "poll_interval_sec": policy_context["poll_interval_sec"],
        "poll_jitter_pct": policy_context["poll_jitter_pct"],
        "poll_backoff": policy_context["poll_backoff"],
        "poll_max_interval_sec": policy_context["poll_max_interval_sec"],
        "max_polls": policy_context["max_polls"],
        "policy_valid": policy_context["policy_valid"],
        "policy_errors": policy_context["policy_errors"],
        "policy_summary": policy_context["policy_summary"],
        "poll_transport_supported": policy_context["poll_transport_supported"],
        "live_polling_supported": policy_context["poll_transport_supported"],
        "poll_transport_unsupported_reason": policy_context["poll_transport_unsupported_reason"],
        "mode_semantics": policy_context["mode_semantics"],
        "mode_records": policy_context["mode_records"],
        **policy_context["mode_indexes"],
        "mode_summary": policy_context["mode_summary"],
    }


def _command_queue_index_summary(commands, command_indexes, policy_indexes):
    return {
        "commands": commands,
        "commands_by_id": command_indexes["commands_by_id"],
        "commands_by_status": command_indexes["commands_by_status"],
        "commands_by_command_sha256": command_indexes["commands_by_command_sha256"],
        "commands_by_target_id": command_indexes["commands_by_target_id"],
        "commands_by_created_at": command_indexes["commands_by_created_at"],
        "commands_by_delivered_at": command_indexes["commands_by_delivered_at"],
        "commands_by_result_received_at": command_indexes["commands_by_result_received_at"],
        "commands_by_result_source_path": command_indexes["commands_by_result_source_path"],
        "commands_by_timeout_sec": command_indexes["commands_by_timeout_sec"],
        "commands_by_max_output_bytes": command_indexes["commands_by_max_output_bytes"],
        "commands_by_expire_sec": command_indexes["commands_by_expire_sec"],
        "commands_by_expires_at": command_indexes["commands_by_expires_at"],
        "commands_by_expired": command_indexes["commands_by_expired"],
        "commands_by_execution_decision": command_indexes["commands_by_execution_decision"],
        "commands_by_result_status": command_indexes["commands_by_result_status"],
        "commands_by_result_exit_code": command_indexes["commands_by_result_exit_code"],
        "commands_by_result_output_exceeded": command_indexes["commands_by_result_output_exceeded"],
        "commands_by_result_output_size_bucket": command_indexes["commands_by_result_output_size_bucket"],
        **policy_indexes,
    }


def _command_queue_count_summary(commands, command_indexes, policy_counts):
    return {
        "status_counts": command_indexes["status_counts"],
        "timeout_sec_counts": record_count_by_key(commands, "timeout_sec"),
        "max_output_bytes_counts": record_count_by_key(commands, "max_output_bytes"),
        "expire_sec_counts": record_count_by_key(commands, "expire_sec"),
        "expired_counts": record_count_by_key(commands, "expired"),
        "target_counts": record_count_by_key(commands, "target_id"),
        "execution_decision_counts": command_indexes["execution_decision_counts"],
        "result_status_counts": command_indexes["result_status_counts"],
        "result_exit_code_counts": command_indexes["result_exit_code_counts"],
        "result_output_size_bucket_counts": command_indexes["result_output_size_bucket_counts"],
        **policy_counts,
        "latest_created_at": command_indexes["latest_created_at"],
        "latest_result_received_at": command_indexes["latest_result_received_at"],
    }


def _command_queue_result_counts(commands):
    return {
        "result_count": len([
            rec for rec in commands
            if isinstance(rec, dict) and rec.get("status") == "result-received"
        ]),
        "result_output_exceeded_count": len([
            rec for rec in commands
            if isinstance(rec, dict) and rec.get("result_output_exceeded_limit") is True
        ]),
    }


def _command_queue_delivery_counts(commands):
    return {
        "queued_count": len([
            rec for rec in commands
            if isinstance(rec, dict) and rec.get("status") == "queued"
        ]),
        "delivered_count": len([
            rec for rec in commands
            if isinstance(rec, dict) and rec.get("status") == "delivered"
        ]),
        **_command_queue_result_counts(commands),
        "total_count": len(commands),
    }


def _command_queue_filter_summary(target_filter_id, unfiltered_command_count):
    return {
        "target_filter_active": bool(target_filter_id),
        "target_filter_id": target_filter_id,
        "unfiltered_total_count": unfiltered_command_count,
    }


def _command_queue_capability_summary(policy_context):
    return {
        "execution_supported": policy_context["execution_supported"],
        "delivery_supported": False,
        "result_upload_supported": True,
        "poll_transport_supported": policy_context["poll_transport_supported"],
        "live_polling_supported": policy_context["poll_transport_supported"],
        "poll_transport_unsupported_reason": policy_context["poll_transport_unsupported_reason"],
        "executes_commands": policy_context["execution_supported"],
        "operator_queue_records_only": True,
        "active_control_channel": False,
        "configured_for_polling": policy_context["configured_for_polling"],
        "arbitrary_policy_requested": policy_context["arbitrary_policy_requested"],
        "arbitrary_execution_allowed": policy_context["arbitrary_execution_allowed"],
        "safety_boundary": "explicit operator queue records only; execution requires explicit target poll and execute policy",
    }


def command_queue_summary(cfg):
    commands, target_filter_id, unfiltered_command_count = _command_queue_visible_commands(cfg)
    command_indexes = _command_queue_record_indexes(commands)
    policy_context = _command_queue_policy_context(cfg)
    policy_indexes = _command_queue_policy_indexes(commands)
    policy_counts = _command_queue_policy_counts(commands)
    summary = {}
    summary.update(_command_queue_config_summary(cfg, policy_context))
    summary.update(_command_queue_index_summary(commands, command_indexes, policy_indexes))
    summary.update(_command_queue_count_summary(commands, command_indexes, policy_counts))
    summary.update(_command_queue_delivery_counts(commands))
    summary.update(_command_queue_filter_summary(target_filter_id, unfiltered_command_count))
    summary.update(_command_queue_capability_summary(policy_context))
    return summary


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


def command_queue_status_summary(command_queue, policy_records=None):
    return command_queue_policy.command_queue_status_summary(command_queue, policy_records)


def yes_no(value):
    return command_queue_policy.yes_no(value)


def command_queue_policy_value(queue, key, default=False):
    return command_queue_policy.command_queue_policy_value(queue, key, default)


def command_queue_policy_yes_no(queue, key, default=False):
    return command_queue_policy.command_queue_policy_yes_no(queue, key, default)


def valid_yes_no(value):
    return command_queue_policy.valid_yes_no(value)


def valid_uint_string(value):
    return command_queue_policy.valid_uint_string(value)


def valid_header_token(value):
    return command_queue_policy.valid_header_token(value)


def command_queue_policy_errors(cfg):
    return command_queue_policy.command_queue_policy_errors(cfg)


def command_queue_execution_supported(cfg):
    return command_queue_policy.command_queue_execution_supported(cfg)


def command_queue_execution_rejection_reason(cfg):
    return command_queue_policy.command_queue_execution_rejection_reason(cfg)


def command_queue_token_valid(cfg, headers):
    return command_queue_policy.command_queue_token_valid(cfg, headers)


def command_queue_policy_snapshot(cfg):
    return command_queue_policy.command_queue_policy_snapshot(cfg)


def command_queue_delivery_policy_snapshot(cfg):
    return command_queue_policy.command_queue_delivery_policy_snapshot(cfg)


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


def append_command_queue_poll_events(cfg, session_manager, service, log_dir, remote, metadata):
    session_manager.append_list_item(log_dir, "command_queue_polls", metadata)
    append_event(cfg, service, "command_queue_poll", session=str(log_dir), remote=remote, details=metadata)
    poll_event = command_queue_poll_outcome_event(metadata.get("status"))
    if poll_event:
        level = "error" if poll_event == "command_queue_poll_error" else "info"
        append_event(cfg, service, poll_event, level, session=str(log_dir), remote=remote, details=metadata)


def append_command_queue_result_events(cfg, session_manager, service, log_dir, remote, metadata):
    session_manager.append_list_item(log_dir, "command_queue_results", metadata)
    append_event(cfg, service, "command_queue_result_upload", session=str(log_dir), remote=remote, details=metadata)
    result_event = command_queue_result_outcome_event(metadata.get("status"))
    if result_event:
        level = "error" if result_event == "command_queue_result_upload_error" else "info"
        append_event(cfg, service, result_event, level, session=str(log_dir), remote=remote, details=metadata)


def command_queue_mode_semantics(live_transport_supported=True, execution_supported=False):
    return command_queue_policy.command_queue_mode_semantics(
        live_transport_supported,
        execution_supported,
    )


def command_queue_mode_summary(mode_semantics):
    return command_queue_policy.command_queue_mode_summary(mode_semantics)


def command_queue_mode_records(mode_semantics):
    return command_queue_policy.command_queue_mode_records(mode_semantics)


def command_queue_mode_record_indexes(records):
    return command_queue_policy.command_queue_mode_record_indexes(records)


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
    return command_queue_policy.command_queue_policy_status(command_queue)


def command_queue_workflow_action_indexes(records):
    return command_queue_workflow_actions.command_queue_workflow_action_indexes(records)


def command_queue_workflow_action_record(
    action_id,
    category,
    label,
    command,
    workflow,
    run_command,
    target_filter_id,
    service_row,
    queue_path,
    queued_count,
    total_count,
    result_count,
    mailbox_records,
    pending_mailbox_records,
    pending_mailbox_target_ids,
    fleet_metrics,
    command_queue,
    action_state,
    action_reason,
    available=True,
    requires_input=False,
    requires_confirmation=False,
    queues_offline_work=False,
    target_phone_home_required=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    return command_queue_workflow_actions.command_queue_workflow_action_record(
        action_id, category, label, command, workflow, run_command,
        target_filter_id, service_row, queue_path, queued_count, total_count,
        result_count, mailbox_records, pending_mailbox_records,
        pending_mailbox_target_ids, fleet_metrics, command_queue, action_state,
        action_reason, available=available, requires_input=requires_input,
        requires_confirmation=requires_confirmation,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
        can_run_from_curses_enter=can_run_from_curses_enter,
        curses_enter_action=curses_enter_action,
    )


def command_queue_listener_action_states(service_row):
    return command_queue_workflow_actions.command_queue_listener_action_states(service_row)


def command_queue_workflow_action_records(
    cfg,
    command_queue,
    target_mailbox_records=None,
    service_row=None,
    targets=None,
):
    return command_queue_workflow_actions.command_queue_workflow_action_records(
        cfg,
        command_queue,
        target_mailbox_records=target_mailbox_records,
        service_row=service_row,
        targets=targets,
    )


def command_queue_workflow_action_summary(records):
    return command_queue_workflow_actions.command_queue_workflow_action_summary(records)


def command_queue_workflow_action_status_summary(records):
    return command_queue_workflow_actions.command_queue_workflow_action_status_summary(records)
