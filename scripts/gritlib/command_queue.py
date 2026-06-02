"""Command queue policy and mode helpers for grit-console."""

from gritlib.record_utils import int_value, record_count_by_key, records_by_key

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

