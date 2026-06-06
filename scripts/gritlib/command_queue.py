"""Command queue policy and mode helpers for grit-console."""

import json
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.record_utils import (
    format_counts, record_count_by_key,
)
import gritlib.command_queue_workflow_actions as command_queue_workflow_actions
import gritlib.command_queue_policy as command_queue_policy
import gritlib.command_queue_records as command_queue_records


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
    return command_queue_records.command_queue_path(cfg, default_operator_session_dir)


def command_queue_state_record(cfg):
    return command_queue_records.command_queue_state_record(cfg)


def command_queue_state_status(cfg):
    return command_queue_records.command_queue_state_status(cfg)


def load_command_queue(cfg):
    return command_queue_records.load_command_queue(cfg)


def save_command_queue(cfg, data):
    return command_queue_records.save_command_queue(cfg, data)


def mark_command_delivered(cfg, command_id, remote_addr="", target_identity=None):
    return command_queue_records.mark_command_delivered(
        cfg, command_id, remote_addr, target_identity=target_identity
    )


def queue_command(cfg, command, timeout_sec=None, max_output_bytes=None, expire_sec=None, metadata=None):
    return command_queue_records.queue_command(
        cfg,
        command,
        timeout_sec=timeout_sec,
        max_output_bytes=max_output_bytes,
        expire_sec=expire_sec,
        metadata=metadata,
    )


def clear_command_queue(cfg):
    return command_queue_records.clear_command_queue(cfg)


def record_command_result_payload(cfg, command_id, result, result_source_path="", target_identity=None):
    return command_queue_records.record_command_result_payload(
        cfg,
        command_id,
        result,
        result_source_path=result_source_path,
        target_identity=target_identity,
    )


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
    return command_queue_records.command_queue_visible_commands(cfg)


def _empty_command_queue_record_index_state():
    return command_queue_records._empty_command_queue_record_index_state()


def _queue_index_append(indexes, key, rec):
    return command_queue_records._queue_index_append(indexes, key, rec)


def _queue_index_count(counts, key):
    return command_queue_records._queue_index_count(counts, key)


def _command_queue_index_values(rec):
    return command_queue_records._command_queue_index_values(rec)


def _apply_command_queue_base_indexes(state, rec, values):
    return command_queue_records._apply_command_queue_base_indexes(state, rec, values)


def _apply_command_queue_timing_indexes(state, rec, values):
    return command_queue_records._apply_command_queue_timing_indexes(state, rec, values)


def _apply_command_queue_execution_indexes(state, rec, values):
    return command_queue_records._apply_command_queue_execution_indexes(state, rec, values)


def _apply_command_queue_result_indexes(state, rec, status):
    return command_queue_records._apply_command_queue_result_indexes(state, rec, status)


def _command_queue_record_index_result(state):
    return command_queue_records._command_queue_record_index_result(state)


def _command_queue_record_indexes(commands):
    return command_queue_records.command_queue_record_indexes(commands)

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
    return command_queue_records.command_queue_expired(rec, now_epoch=now_epoch)


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
    *command_queue_records.COMMAND_QUEUE_WORK_METADATA_FIELDS,
)


def command_queue_work_metadata(rec):
    return command_queue_records.command_queue_work_metadata(rec)


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
    return command_queue_records.command_result_output_size_bucket(size)


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
