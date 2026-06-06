"""Command queue policy, mode, and status-summary helpers."""

from gritlib.record_utils import (
    record_count_by_nested_key,
    records_by_key,
    records_by_nested_key,
)


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


def command_queue_policy_context(cfg):
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
        "enabled": enabled,
        "allowed_commands": allowed_commands,
        "execution_mode": execution_mode,
        "allow_arbitrary": allow_arbitrary,
        "poll_interval_sec": poll_interval_sec,
        "poll_jitter_pct": poll_jitter_pct,
        "poll_backoff": poll_backoff,
        "poll_max_interval_sec": poll_max_interval_sec,
        "max_polls": max_polls,
        "tls": tls,
        "policy_errors": policy_errors,
        "policy_valid": policy_valid,
        "token_configured": token_configured,
        "poll_transport_supported": poll_transport_supported,
        "poll_transport_unsupported_reason": poll_transport_unsupported_reason,
        "arbitrary_policy_requested": arbitrary_policy_requested,
        "execution_supported": execution_supported,
        "arbitrary_execution_allowed": arbitrary_execution_allowed,
        "configured_for_polling": configured_for_polling,
        "mode_semantics": mode_semantics,
        "mode_records": mode_records,
        "mode_indexes": mode_indexes,
        "mode_summary": mode_summary,
        "policy_summary": policy_summary,
    }


def command_queue_policy_indexes(commands):
    return {
        "commands_by_queue_policy_enabled": records_by_nested_key(commands, "queue_policy_snapshot", "enabled"),
        "commands_by_queue_policy_valid": records_by_nested_key(commands, "queue_policy_snapshot", "valid"),
        "commands_by_queue_policy_execution_mode": records_by_nested_key(commands, "queue_policy_snapshot", "execution_mode"),
        "commands_by_queue_policy_allowed_commands": records_by_nested_key(commands, "queue_policy_snapshot", "allowed_commands"),
        "commands_by_delivery_policy_enabled": records_by_nested_key(commands, "delivery_policy_snapshot", "enabled"),
        "commands_by_delivery_policy_valid": records_by_nested_key(commands, "delivery_policy_snapshot", "valid"),
        "commands_by_delivery_policy_execution_mode": records_by_nested_key(commands, "delivery_policy_snapshot", "execution_mode"),
        "commands_by_delivery_policy_delivery_supported": records_by_nested_key(commands, "delivery_policy_snapshot", "delivery_supported"),
        "commands_by_delivery_policy_result_upload_supported": records_by_nested_key(commands, "delivery_policy_snapshot", "result_upload_supported"),
        "commands_by_delivery_policy_active_control_channel": records_by_nested_key(commands, "delivery_policy_snapshot", "active_control_channel"),
    }


def command_queue_policy_counts(commands):
    return {
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
    }


def command_queue_status_summary(command_queue, policy_records=None):
    command_queue = command_queue or {}
    policy_records = policy_records or []
    policy_summary = command_queue.get("policy_summary") or {}
    mode_summary = command_queue.get("mode_summary") or {}
    return {
        **_command_queue_status_count_summary(command_queue, policy_records),
        **_command_queue_policy_count_summary(command_queue),
        **_command_queue_latest_status_summary(command_queue),
        **_command_queue_policy_status_summary(command_queue, policy_summary),
        **_command_queue_poll_status_summary(policy_summary),
        **_command_queue_mode_status_summary(mode_summary),
    }


def _command_queue_status_count_summary(command_queue, policy_records=None):
    return {
        "command_queue_policy_record_count": len(policy_records),
        "command_queue_total_count": command_queue.get("total_count", 0),
        "command_queue_queued_count": command_queue.get("queued_count", 0),
        "command_queue_delivered_count": command_queue.get("delivered_count", 0),
        "command_queue_result_count": command_queue.get("result_count", 0),
        "command_queue_result_output_exceeded_count": command_queue.get(
            "result_output_exceeded_count", 0
        ),
        "command_queue_status_counts": command_queue.get("status_counts") or {},
        "command_queue_target_counts": command_queue.get("target_counts") or {},
        "command_queue_timeout_sec_counts": (
            command_queue.get("timeout_sec_counts") or {}
        ),
        "command_queue_max_output_bytes_counts": (
            command_queue.get("max_output_bytes_counts") or {}
        ),
        "command_queue_expire_sec_counts": command_queue.get("expire_sec_counts")
        or {},
        "command_queue_expired_counts": command_queue.get("expired_counts") or {},
        "command_queue_execution_decision_counts": (
            command_queue.get("execution_decision_counts") or {}
        ),
        "command_queue_result_status_counts": (
            command_queue.get("result_status_counts") or {}
        ),
        "command_queue_result_exit_code_counts": (
            command_queue.get("result_exit_code_counts") or {}
        ),
        "command_queue_result_output_size_bucket_counts": (
            command_queue.get("result_output_size_bucket_counts") or {}
        ),
    }


def _command_queue_policy_count_summary(command_queue):
    return {
        "command_queue_queue_policy_enabled_counts": (
            command_queue.get("queue_policy_enabled_counts") or {}
        ),
        "command_queue_queue_policy_valid_counts": (
            command_queue.get("queue_policy_valid_counts") or {}
        ),
        "command_queue_queue_policy_execution_mode_counts": (
            command_queue.get("queue_policy_execution_mode_counts") or {}
        ),
        "command_queue_queue_policy_allowed_commands_counts": (
            command_queue.get("queue_policy_allowed_commands_counts") or {}
        ),
        "command_queue_delivery_policy_enabled_counts": (
            command_queue.get("delivery_policy_enabled_counts") or {}
        ),
        "command_queue_delivery_policy_valid_counts": (
            command_queue.get("delivery_policy_valid_counts") or {}
        ),
        "command_queue_delivery_policy_execution_mode_counts": (
            command_queue.get("delivery_policy_execution_mode_counts") or {}
        ),
        "command_queue_delivery_policy_delivery_supported_counts": (
            command_queue.get("delivery_policy_delivery_supported_counts") or {}
        ),
        "command_queue_delivery_policy_result_upload_supported_counts": (
            command_queue.get("delivery_policy_result_upload_supported_counts") or {}
        ),
        "command_queue_delivery_policy_active_control_channel_counts": (
            command_queue.get("delivery_policy_active_control_channel_counts") or {}
        ),
    }


def _command_queue_latest_status_summary(command_queue):
    return {
        "command_queue_latest_created_at": command_queue.get("latest_created_at", ""),
        "command_queue_latest_result_received_at": command_queue.get(
            "latest_result_received_at", ""
        ),
    }


def _command_queue_policy_status_summary(command_queue, policy_summary):
    return {
        "command_queue_policy_valid": bool(command_queue.get("policy_valid", True)),
        "command_queue_policy_error_count": len(
            command_queue.get("policy_errors") or []
        ),
        "command_queue_enabled": bool(policy_summary.get("enabled", False)),
        "command_queue_configured_for_polling": bool(
            policy_summary.get("configured_for_polling", False)
        ),
        "command_queue_active_control_channel": bool(
            policy_summary.get("active_control_channel", False)
        ),
        "command_queue_token_required": bool(
            policy_summary.get("token_required", False)
        ),
        "command_queue_token_configured": bool(
            policy_summary.get("token_configured", False)
        ),
        "command_queue_execution_mode": policy_summary.get(
            "execution_mode", "metadata-only"
        ),
        "command_queue_metadata_only_default": bool(
            policy_summary.get("metadata_only_default", False)
        ),
        "command_queue_execution_supported": bool(
            policy_summary.get("execution_supported", False)
        ),
        "command_queue_delivery_supported": bool(
            policy_summary.get("delivery_supported", False)
        ),
        "command_queue_result_upload_supported": bool(
            policy_summary.get("result_upload_supported", False)
        ),
        "command_queue_poll_transport_supported": bool(
            policy_summary.get("poll_transport_supported", False)
        ),
        "command_queue_live_polling_supported": bool(
            policy_summary.get("live_polling_supported", False)
        ),
    }


def _command_queue_poll_status_summary(policy_summary):
    return {
        "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC": policy_summary.get(
            "poll_interval_sec", "5"
        ),
        "GRIT_COMMAND_QUEUE_POLL_JITTER_PCT": policy_summary.get(
            "poll_jitter_pct", "0"
        ),
        "GRIT_COMMAND_QUEUE_POLL_BACKOFF": policy_summary.get(
            "poll_backoff", "none"
        ),
        "GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC": policy_summary.get(
            "poll_max_interval_sec", "300"
        ),
        "GRIT_COMMAND_QUEUE_MAX_POLLS": policy_summary.get("max_polls", "0"),
        "command_queue_arbitrary_policy_requested": bool(
            policy_summary.get("arbitrary_policy_requested", False)
        ),
        "command_queue_arbitrary_execution_allowed": bool(
            policy_summary.get("arbitrary_execution_allowed", False)
        ),
        "command_queue_safe_disabled_default": bool(
            policy_summary.get("safe_disabled_default", False)
        ),
    }


def _command_queue_mode_status_summary(mode_summary):
    return {
        "command_queue_mode_count": mode_summary.get("mode_count", 0),
        "command_queue_polling_mode_count": mode_summary.get(
            "polling_mode_count", 0
        ),
        "command_queue_operator_host_required_mode_count": mode_summary.get(
            "operator_host_required_mode_count", 0
        ),
        "command_queue_live_supported_mode_count": mode_summary.get(
            "live_supported_mode_count", 0
        ),
        "command_queue_delivery_supported_mode_count": mode_summary.get(
            "delivery_supported_mode_count", 0
        ),
        "command_queue_result_upload_supported_mode_count": mode_summary.get(
            "result_upload_supported_mode_count", 0
        ),
        "command_queue_execution_supported_mode_count": mode_summary.get(
            "execution_supported_mode_count", 0
        ),
        "command_queue_active_control_channel_mode_count": mode_summary.get(
            "active_control_channel_mode_count", 0
        ),
        "command_queue_operator_supplied_command_execution_mode_count": (
            mode_summary.get("operator_supplied_command_execution_mode_count", 0)
        ),
    }


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
