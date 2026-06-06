"""Target command status index and summary helpers for grit-console."""

from gritlib.record_utils import int_value, records_by_key


def _empty_target_command_record_index_state(records):
    return {
        "by_service": {},
        "by_target_id": {},
        "by_request_name": {},
        "by_stage_kind": {},
        "by_release_path": {},
        "by_side": {},
        "by_purpose": {},
        "by_service_purpose": {},
        "by_side_purpose": {},
        "by_network": records_by_key(records, "network"),
        "by_route_kind": records_by_key(records, "route_kind"),
        "by_bridge_profile": records_by_key(records, "bridge_profile"),
        "by_requires_bridge": records_by_key(records, "requires_bridge"),
        "by_requires_explicit_target_action": records_by_key(records, "requires_explicit_target_action"),
        "by_executes_operator_supplied_commands": records_by_key(records, "executes_operator_supplied_commands"),
        "by_ordinal": {},
        "by_command_sha256": {},
        "by_copy_supported": records_by_key(records, "copy_supported"),
        "by_session_policy": {},
        "by_session_policy_valid": {},
        "by_retry_backoff": {},
        "by_retry_interval_sec": {},
        "by_retry_post_disconnect_count": {},
    }


def _apply_target_command_base_indexes(state, rec, values):
    if values["service"]:
        state["by_service"].setdefault(values["service"], []).append(rec)
    if values["target_id"]:
        state["by_target_id"].setdefault(values["target_id"], []).append(rec)
    if values["ordinal"] not in (None, ""):
        state["by_ordinal"][str(values["ordinal"])] = rec
    if values["command_sha256"]:
        state["by_command_sha256"][values["command_sha256"]] = rec
    if values["request_name"]:
        state["by_request_name"][values["request_name"]] = rec
    if values["stage_kind"]:
        state["by_stage_kind"].setdefault(values["stage_kind"], []).append(rec)
    if values["release_path"]:
        state["by_release_path"].setdefault(values["release_path"], []).append(rec)


def _apply_target_command_purpose_indexes(state, rec, values):
    if values["side"]:
        state["by_side"].setdefault(values["side"], []).append(rec)
    if values["purpose"]:
        state["by_purpose"].setdefault(values["purpose"], []).append(rec)
    if values["service"] and values["purpose"]:
        state["by_service_purpose"].setdefault(
            f"{values['service']}:{values['purpose']}", []
        ).append(rec)
    if values["side"] and values["purpose"]:
        state["by_side_purpose"].setdefault(
            f"{values['side']}:{values['purpose']}", []
        ).append(rec)


def _apply_target_command_policy_indexes(state, rec, metadata, retry):
    if metadata.get("session_policy") not in (None, ""):
        state["by_session_policy"].setdefault(str(metadata.get("session_policy")), []).append(rec)
    if metadata.get("session_policy_valid") not in (None, ""):
        state["by_session_policy_valid"].setdefault(str(metadata.get("session_policy_valid")), []).append(rec)
    if retry.get("backoff") not in (None, ""):
        state["by_retry_backoff"].setdefault(str(retry.get("backoff")), []).append(rec)
    if retry.get("interval_sec") not in (None, ""):
        state["by_retry_interval_sec"].setdefault(str(retry.get("interval_sec")), []).append(rec)
    if retry.get("post_disconnect_count") not in (None, ""):
        state["by_retry_post_disconnect_count"].setdefault(str(retry.get("post_disconnect_count")), []).append(rec)


def _target_command_index_values(rec):
    metadata = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
    retry = metadata.get("retry") if isinstance(metadata.get("retry"), dict) else {}
    return {
        "service": str(rec.get("service") or ""),
        "target_id": str(rec.get("target_id") or ""),
        "request_name": str(rec.get("request_name") or ""),
        "stage_kind": str(rec.get("stage_kind") or ""),
        "release_path": str(rec.get("release_path") or ""),
        "side": str(rec.get("side") or ""),
        "purpose": str(rec.get("purpose") or ""),
        "ordinal": rec.get("ordinal"),
        "command_sha256": str(rec.get("command_sha256") or ""),
        "metadata": metadata,
        "retry": retry,
    }


def _target_command_record_index_result(state):
    return (
        state["by_service"], state["by_target_id"], state["by_request_name"],
        state["by_stage_kind"], state["by_release_path"], state["by_side"],
        state["by_purpose"], state["by_service_purpose"], state["by_side_purpose"],
        state["by_network"], state["by_route_kind"], state["by_bridge_profile"],
        state["by_requires_bridge"], state["by_requires_explicit_target_action"],
        state["by_executes_operator_supplied_commands"], state["by_ordinal"],
        state["by_command_sha256"], state["by_copy_supported"],
        state["by_session_policy"], state["by_session_policy_valid"],
        state["by_retry_backoff"], state["by_retry_interval_sec"],
        state["by_retry_post_disconnect_count"],
    )


def target_command_record_indexes(records):
    state = _empty_target_command_record_index_state(records)
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        values = _target_command_index_values(rec)
        _apply_target_command_base_indexes(state, rec, values)
        _apply_target_command_purpose_indexes(state, rec, values)
        _apply_target_command_policy_indexes(state, rec, values["metadata"], values["retry"])
    return _target_command_record_index_result(state)


def _empty_target_command_summary_state():
    return {
        "total": 0,
        "target_count": 0,
        "network_count": 0,
        "explicit_target_action_count": 0,
        "operator_supplied_command_execution_count": 0,
        "copy_supported_count": 0,
        "session_policy_error_count": 0,
        "by_service": {},
        "by_target_id": {},
        "by_stage_kind": {},
        "by_release_path": {},
        "by_side": {},
        "by_purpose": {},
        "by_route_kind": {},
        "by_bridge_profile": {},
        "by_session_policy": {},
        "by_session_policy_valid": {},
        "by_retry_backoff": {},
    }


def _increment_target_command_summary_counts(state, rec):
    state["total"] += 1
    if rec.get("side") == "target":
        state["target_count"] += 1
    if rec.get("network") is True:
        state["network_count"] += 1
    if rec.get("requires_explicit_target_action") is True:
        state["explicit_target_action_count"] += 1
    if rec.get("executes_operator_supplied_commands") is True:
        state["operator_supplied_command_execution_count"] += 1
    if rec.get("copy_supported") is True:
        state["copy_supported_count"] += 1


def _increment_target_command_summary_map(state, map_name, value):
    if value:
        state[map_name][value] = state[map_name].get(value, 0) + 1


def _apply_target_command_summary_record(state, rec):
    metadata = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
    retry = metadata.get("retry") if isinstance(metadata.get("retry"), dict) else {}
    _increment_target_command_summary_counts(state, rec)
    _increment_target_command_summary_map(state, "by_service", str(rec.get("service") or ""))
    _increment_target_command_summary_map(state, "by_target_id", str(rec.get("target_id") or ""))
    _increment_target_command_summary_map(state, "by_stage_kind", str(rec.get("stage_kind") or ""))
    _increment_target_command_summary_map(state, "by_release_path", str(rec.get("release_path") or ""))
    _increment_target_command_summary_map(state, "by_side", str(rec.get("side") or ""))
    _increment_target_command_summary_map(state, "by_purpose", str(rec.get("purpose") or ""))
    _increment_target_command_summary_map(state, "by_route_kind", str(rec.get("route_kind") or ""))
    _increment_target_command_summary_map(state, "by_bridge_profile", str(rec.get("bridge_profile") or ""))
    if metadata.get("session_policy") not in (None, ""):
        _increment_target_command_summary_map(
            state, "by_session_policy", str(metadata.get("session_policy"))
        )
    if metadata.get("session_policy_valid") not in (None, ""):
        _increment_target_command_summary_map(
            state, "by_session_policy_valid", str(metadata.get("session_policy_valid"))
        )
    state["session_policy_error_count"] += len(metadata.get("session_policy_errors") or [])
    if retry.get("backoff") not in (None, ""):
        _increment_target_command_summary_map(
            state, "by_retry_backoff", str(retry.get("backoff"))
        )


def _target_command_summary_result(state):
    return {
        "total_count": state["total"],
        "target_count": state["target_count"],
        "network_count": state["network_count"],
        "explicit_target_action_count": state["explicit_target_action_count"],
        "operator_supplied_command_execution_count": state["operator_supplied_command_execution_count"],
        "copy_supported_count": state["copy_supported_count"],
        "executes_operator_supplied_commands": state["operator_supplied_command_execution_count"] > 0,
        "all_require_explicit_target_action": state["total"] > 0 and state["explicit_target_action_count"] == state["total"],
        "by_service": state["by_service"],
        "by_target_id": state["by_target_id"],
        "by_stage_kind": state["by_stage_kind"],
        "by_release_path": state["by_release_path"],
        "by_side": state["by_side"],
        "by_purpose": state["by_purpose"],
        "by_route_kind": state["by_route_kind"],
        "by_bridge_profile": state["by_bridge_profile"],
        "by_session_policy": state["by_session_policy"],
        "by_session_policy_valid": state["by_session_policy_valid"],
        "session_policy_error_count": state["session_policy_error_count"],
        "by_retry_backoff": state["by_retry_backoff"],
    }


def target_command_record_summary(records):
    state = _empty_target_command_summary_state()
    for rec in records or []:
        if isinstance(rec, dict):
            _apply_target_command_summary_record(state, rec)
    return _target_command_summary_result(state)


def target_command_state_status(summary):
    state_record = {
        "id": "target-commands",
        "command_count": int_value(summary.get("total_count", 0)),
        "target_count": int_value(summary.get("target_count", 0)),
        "network_count": int_value(summary.get("network_count", 0)),
        "explicit_target_action_count": int_value(summary.get("explicit_target_action_count", 0)),
        "operator_supplied_command_execution_count": int_value(
            summary.get("operator_supplied_command_execution_count", 0)
        ),
        "copy_supported_count": int_value(summary.get("copy_supported_count", 0)),
        "session_policy_error_count": int_value(summary.get("session_policy_error_count", 0)),
        "executes_operator_supplied_commands": bool(
            summary.get("executes_operator_supplied_commands", False)
        ),
        "all_require_explicit_target_action": bool(
            summary.get("all_require_explicit_target_action", False)
        ),
    }
    state_record.update({
        "has_commands": state_record.get("command_count", 0) > 0,
        "has_network_commands": state_record.get("network_count", 0) > 0,
        "has_copy_supported_commands": state_record.get("copy_supported_count", 0) > 0,
        "has_operator_supplied_command_execution": (
            state_record.get("operator_supplied_command_execution_count", 0) > 0
        ),
        "has_session_policy_errors": state_record.get("session_policy_error_count", 0) > 0,
    })
    state_record["safe_explicit_target_action_boundary"] = (
        state_record.get("has_commands") is True and
        state_record.get("all_require_explicit_target_action") is True and
        state_record.get("has_operator_supplied_command_execution") is False
    )
    state_records = [state_record]
    state_index_maps = {
        "target_command_state_records_by_id": {
            rec.get("id", ""): rec for rec in state_records if rec.get("id")
        },
        "target_command_state_records_by_has_commands": records_by_key(
            state_records, "has_commands"
        ),
        "target_command_state_records_by_has_network_commands": records_by_key(
            state_records, "has_network_commands"
        ),
        "target_command_state_records_by_has_copy_supported_commands": records_by_key(
            state_records, "has_copy_supported_commands"
        ),
        "target_command_state_records_by_has_operator_supplied_command_execution": records_by_key(
            state_records, "has_operator_supplied_command_execution"
        ),
        "target_command_state_records_by_all_require_explicit_target_action": records_by_key(
            state_records, "all_require_explicit_target_action"
        ),
        "target_command_state_records_by_safe_explicit_target_action_boundary": records_by_key(
            state_records, "safe_explicit_target_action_boundary"
        ),
        "target_command_state_records_by_has_session_policy_errors": records_by_key(
            state_records, "has_session_policy_errors"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def target_command_status_summary(
    summary,
    state_record=None,
    state_records=None,
    rshell_policy_record=None,
    rshell_policy_records=None,
):
    summary = summary or {}
    state_record = state_record or {}
    rshell_policy_record = rshell_policy_record or {}
    return {
        "target_command_count": summary.get("total_count", 0),
        "target_command_network_count": summary.get("network_count", 0),
        "target_command_explicit_action_count": summary.get("explicit_target_action_count", 0),
        "target_command_operator_supplied_execution_count": summary.get(
            "operator_supplied_command_execution_count", 0
        ),
        "target_command_copy_supported_count": summary.get("copy_supported_count", 0),
        "target_command_state_record_count": len(state_records or []),
        "target_command_state_has_commands": bool(
            state_record.get("has_commands", False)
        ),
        "target_command_state_has_network_commands": bool(
            state_record.get("has_network_commands", False)
        ),
        "target_command_state_has_copy_supported_commands": bool(
            state_record.get("has_copy_supported_commands", False)
        ),
        "target_command_state_has_operator_supplied_command_execution": bool(
            state_record.get("has_operator_supplied_command_execution", False)
        ),
        "target_command_state_safe_explicit_target_action_boundary": bool(
            state_record.get("safe_explicit_target_action_boundary", False)
        ),
        "target_command_state_has_session_policy_errors": bool(
            state_record.get("has_session_policy_errors", False)
        ),
        "target_command_executes_operator_supplied_commands": bool(
            summary.get("executes_operator_supplied_commands", False)
        ),
        "target_command_all_require_explicit_target_action": bool(
            summary.get("all_require_explicit_target_action", False)
        ),
        "target_command_target_counts": summary.get("by_target_id") or {},
        "target_command_side_counts": summary.get("by_side") or {},
        "target_command_purpose_counts": summary.get("by_purpose") or {},
        "target_command_route_kind_counts": summary.get("by_route_kind") or {},
        "target_command_bridge_profile_counts": summary.get("by_bridge_profile") or {},
        "target_command_stage_kind_counts": summary.get("by_stage_kind") or {},
        "target_command_release_path_counts": summary.get("by_release_path") or {},
        "target_command_session_policy_counts": summary.get("by_session_policy") or {},
        "target_command_session_policy_valid_counts": summary.get(
            "by_session_policy_valid"
        ) or {},
        "target_command_session_policy_error_count": summary.get(
            "session_policy_error_count", 0
        ),
        "rshell_session_policy_record_count": len(rshell_policy_records or []),
        "GRIT_RSHELL_SESSION_POLICY": rshell_policy_record.get("session_policy", ""),
        "rshell_session_policy_valid": bool(
            rshell_policy_record.get("session_policy_valid", False)
        ),
        "rshell_session_policy_error_count": len(
            rshell_policy_record.get("session_policy_errors") or []
        ),
        "rshell_session_policy_retry_scope": rshell_policy_record.get("retry_scope", ""),
        "rshell_session_policy_reconnects_after_disconnect": bool(
            rshell_policy_record.get("reconnects_after_disconnect", False)
        ),
        "rshell_session_policy_persistent_lifecycle": bool(
            rshell_policy_record.get("persistent_lifecycle", False)
        ),
        "target_command_retry_backoff_counts": summary.get("by_retry_backoff") or {},
    }
