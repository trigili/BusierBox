"""Command queue policy and mode helpers for grit-console."""

import json
import time
from pathlib import Path

from gritlib.record_utils import int_value, record_count_by_key, records_by_key
from gritlib.session_state import atomic_write_json, parse_utc_timestamp, read_json_file, utc_now


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


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
