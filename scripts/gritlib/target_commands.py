"""Target command index and summary helpers for grit-console."""

from gritlib.record_utils import records_by_key


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
