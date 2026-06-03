"""Target command index and summary helpers for grit-console."""

from gritlib.record_utils import int_value, records_by_key


def rshell_cfg_value(cfg, lower_key, upper_key, default):
    value = cfg.get(lower_key)
    if value in (None, ""):
        value = cfg.get(upper_key)
    if value in (None, ""):
        value = default
    return str(value)


def parse_int_default(value, default):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


def rshell_retry_delay_without_jitter(attempt, interval_sec, backoff, max_interval_sec):
    base = max(parse_int_default(interval_sec, 5), 0)
    max_delay = max(parse_int_default(max_interval_sec, 300), base)
    delay = base
    attempt = max(parse_int_default(attempt, 0), 0)
    if backoff == "linear":
        delay = base * (attempt + 1)
    elif backoff == "exponential":
        delay = base
        for _idx in range(attempt):
            if delay >= max_delay:
                break
            if delay > max_delay // 2:
                delay = max_delay
                break
            delay *= 2
    return min(delay, max_delay)


def rshell_session_policy_record(cfg):
    policy = str(cfg.get("GRIT_RSHELL_SESSION_POLICY") or cfg.get("GRIT_RSHELL_SESSION_POLICY") or "single")
    retry_count = rshell_cfg_value(cfg, "GRIT_RSHELL_RETRY_COUNT", "GRIT_RSHELL_RETRY_COUNT", "1")
    retry_interval = rshell_cfg_value(cfg, "GRIT_RSHELL_RETRY_INTERVAL_SEC", "GRIT_RSHELL_RETRY_INTERVAL_SEC", "5")
    retry_jitter = rshell_cfg_value(cfg, "GRIT_RSHELL_RETRY_JITTER_PCT", "GRIT_RSHELL_RETRY_JITTER_PCT", "20")
    retry_backoff = rshell_cfg_value(cfg, "GRIT_RSHELL_RETRY_BACKOFF", "GRIT_RSHELL_RETRY_BACKOFF", "none")
    retry_max_interval = rshell_cfg_value(cfg, "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC", "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC", "300")
    valid = policy in ("single", "reconnect", "persistent")
    reconnects = policy in ("reconnect", "persistent")
    post_disconnect_count = "-1" if policy == "persistent" else ("0" if policy == "single" else retry_count)
    retry_timing = {
        "backoff": retry_backoff,
        "interval_sec": retry_interval,
        "max_interval_sec": retry_max_interval,
        "jitter_pct": retry_jitter,
        "sample_delays_sec": [
            rshell_retry_delay_without_jitter(0, retry_interval, retry_backoff, retry_max_interval),
            rshell_retry_delay_without_jitter(1, retry_interval, retry_backoff, retry_max_interval),
            rshell_retry_delay_without_jitter(2, retry_interval, retry_backoff, retry_max_interval),
        ],
        "sample_delays_exclude_jitter": True,
    }
    summary = {
        "valid": valid,
        "errors": [] if valid else ["unsupported rshell session policy"],
        "retry_scope": "pre-connect+post-disconnect" if reconnects else "pre-connect",
        "pre_connect_retry_count": retry_count,
        "post_disconnect_retry_count": post_disconnect_count,
        "stops_after_success": policy == "single",
        "reconnects_after_disconnect": reconnects,
        "persistent_lifecycle": policy == "persistent",
        "fresh_session_on_reconnect": reconnects,
        "session_resume_supported": False,
    }
    return {
        "session_policy": policy,
        "session_policy_valid": valid,
        "session_policy_errors": [] if valid else ["unsupported rshell session policy"],
        "session_semantics": {
            "retry_until_first_connection": valid,
            "stop_after_first_success": policy == "single",
            "reconnect_after_disconnect": reconnects,
            "persistent_lifecycle": policy == "persistent",
            "fresh_session_on_reconnect": reconnects,
            "session_resume_supported": False,
        },
        "session_policy_summary": summary,
        "retry": {
            "count": retry_count,
            "interval_sec": retry_interval,
            "jitter_pct": retry_jitter,
            "backoff": retry_backoff,
            "max_interval_sec": retry_max_interval,
            "pre_connect_count": retry_count,
            "post_disconnect_count": post_disconnect_count,
        },
        "retry_timing": retry_timing,
    }


def target_command_record_indexes(records):
    by_service = {}
    by_target_id = {}
    by_request_name = {}
    by_stage_kind = {}
    by_release_path = {}
    by_side = {}
    by_purpose = {}
    by_service_purpose = {}
    by_side_purpose = {}
    by_network = records_by_key(records, "network")
    by_route_kind = records_by_key(records, "route_kind")
    by_bridge_profile = records_by_key(records, "bridge_profile")
    by_requires_bridge = records_by_key(records, "requires_bridge")
    by_requires_explicit_target_action = records_by_key(records, "requires_explicit_target_action")
    by_executes_operator_supplied_commands = records_by_key(records, "executes_operator_supplied_commands")
    by_ordinal = {}
    by_command_sha256 = {}
    by_copy_supported = records_by_key(records, "copy_supported")
    by_session_policy = {}
    by_session_policy_valid = {}
    by_retry_backoff = {}
    by_retry_interval_sec = {}
    by_retry_post_disconnect_count = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        service = str(rec.get("service") or "")
        target_id = str(rec.get("target_id") or "")
        request_name = str(rec.get("request_name") or "")
        stage_kind = str(rec.get("stage_kind") or "")
        release_path = str(rec.get("release_path") or "")
        side = str(rec.get("side") or "")
        purpose = str(rec.get("purpose") or "")
        metadata = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        retry = metadata.get("retry") if isinstance(metadata.get("retry"), dict) else {}
        ordinal = rec.get("ordinal")
        command_sha256 = str(rec.get("command_sha256") or "")
        if service:
            by_service.setdefault(service, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if ordinal not in (None, ""):
            by_ordinal[str(ordinal)] = rec
        if command_sha256:
            by_command_sha256[command_sha256] = rec
        if request_name:
            by_request_name[request_name] = rec
        if stage_kind:
            by_stage_kind.setdefault(stage_kind, []).append(rec)
        if release_path:
            by_release_path.setdefault(release_path, []).append(rec)
        if side:
            by_side.setdefault(side, []).append(rec)
        if purpose:
            by_purpose.setdefault(purpose, []).append(rec)
        if service and purpose:
            by_service_purpose.setdefault(f"{service}:{purpose}", []).append(rec)
        if side and purpose:
            by_side_purpose.setdefault(f"{side}:{purpose}", []).append(rec)
        if metadata.get("session_policy") not in (None, ""):
            by_session_policy.setdefault(str(metadata.get("session_policy")), []).append(rec)
        if metadata.get("session_policy_valid") not in (None, ""):
            by_session_policy_valid.setdefault(str(metadata.get("session_policy_valid")), []).append(rec)
        if retry.get("backoff") not in (None, ""):
            by_retry_backoff.setdefault(str(retry.get("backoff")), []).append(rec)
        if retry.get("interval_sec") not in (None, ""):
            by_retry_interval_sec.setdefault(str(retry.get("interval_sec")), []).append(rec)
        if retry.get("post_disconnect_count") not in (None, ""):
            by_retry_post_disconnect_count.setdefault(str(retry.get("post_disconnect_count")), []).append(rec)
    return (
        by_service, by_target_id, by_request_name, by_stage_kind, by_release_path, by_side,
        by_purpose, by_service_purpose, by_side_purpose, by_network,
        by_route_kind, by_bridge_profile, by_requires_bridge,
        by_requires_explicit_target_action, by_executes_operator_supplied_commands,
        by_ordinal, by_command_sha256, by_copy_supported,
        by_session_policy, by_session_policy_valid, by_retry_backoff,
        by_retry_interval_sec, by_retry_post_disconnect_count,
    )


def target_command_record_summary(records):
    total = 0
    target_count = 0
    network_count = 0
    explicit_target_action_count = 0
    operator_supplied_command_execution_count = 0
    by_service = {}
    by_target_id = {}
    by_stage_kind = {}
    by_release_path = {}
    by_side = {}
    by_purpose = {}
    by_route_kind = {}
    by_bridge_profile = {}
    by_session_policy = {}
    by_session_policy_valid = {}
    by_retry_backoff = {}
    session_policy_error_count = 0
    copy_supported_count = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        total += 1
        service = str(rec.get("service") or "")
        target_id = str(rec.get("target_id") or "")
        stage_kind = str(rec.get("stage_kind") or "")
        release_path = str(rec.get("release_path") or "")
        side = str(rec.get("side") or "")
        purpose = str(rec.get("purpose") or "")
        route_kind = str(rec.get("route_kind") or "")
        bridge_profile = str(rec.get("bridge_profile") or "")
        metadata = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        retry = metadata.get("retry") if isinstance(metadata.get("retry"), dict) else {}
        if service:
            by_service[service] = by_service.get(service, 0) + 1
        if target_id:
            by_target_id[target_id] = by_target_id.get(target_id, 0) + 1
        if stage_kind:
            by_stage_kind[stage_kind] = by_stage_kind.get(stage_kind, 0) + 1
        if release_path:
            by_release_path[release_path] = by_release_path.get(release_path, 0) + 1
        if side:
            by_side[side] = by_side.get(side, 0) + 1
        if purpose:
            by_purpose[purpose] = by_purpose.get(purpose, 0) + 1
        if route_kind:
            by_route_kind[route_kind] = by_route_kind.get(route_kind, 0) + 1
        if bridge_profile:
            by_bridge_profile[bridge_profile] = by_bridge_profile.get(bridge_profile, 0) + 1
        if metadata.get("session_policy") not in (None, ""):
            key = str(metadata.get("session_policy"))
            by_session_policy[key] = by_session_policy.get(key, 0) + 1
        if metadata.get("session_policy_valid") not in (None, ""):
            key = str(metadata.get("session_policy_valid"))
            by_session_policy_valid[key] = by_session_policy_valid.get(key, 0) + 1
        session_policy_error_count += len(metadata.get("session_policy_errors") or [])
        if retry.get("backoff") not in (None, ""):
            key = str(retry.get("backoff"))
            by_retry_backoff[key] = by_retry_backoff.get(key, 0) + 1
        if rec.get("side") == "target":
            target_count += 1
        if rec.get("network") is True:
            network_count += 1
        if rec.get("requires_explicit_target_action") is True:
            explicit_target_action_count += 1
        if rec.get("executes_operator_supplied_commands") is True:
            operator_supplied_command_execution_count += 1
        if rec.get("copy_supported") is True:
            copy_supported_count += 1
    return {
        "total_count": total,
        "target_count": target_count,
        "network_count": network_count,
        "explicit_target_action_count": explicit_target_action_count,
        "operator_supplied_command_execution_count": operator_supplied_command_execution_count,
        "copy_supported_count": copy_supported_count,
        "executes_operator_supplied_commands": operator_supplied_command_execution_count > 0,
        "all_require_explicit_target_action": total > 0 and explicit_target_action_count == total,
        "by_service": by_service,
        "by_target_id": by_target_id,
        "by_stage_kind": by_stage_kind,
        "by_release_path": by_release_path,
        "by_side": by_side,
        "by_purpose": by_purpose,
        "by_route_kind": by_route_kind,
        "by_bridge_profile": by_bridge_profile,
        "by_session_policy": by_session_policy,
        "by_session_policy_valid": by_session_policy_valid,
        "session_policy_error_count": session_policy_error_count,
        "by_retry_backoff": by_retry_backoff,
    }


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
