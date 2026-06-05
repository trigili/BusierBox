"""Target command index, summary, and display helpers for grit-console."""

import hashlib

from gritlib.bridge_routes import attach_target_route_fields, target_route_context
from gritlib.command_copy import copy_text_for_operator
from gritlib.file_transfers import render_fetch_command, render_file_service_command
from gritlib.operator_network import operator_advertised_host
from gritlib.probe_commands import probe_route_context, render_probe_command
from gritlib.record_utils import format_counts, int_value, records_by_key
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged
from gritlib.target_records import configured_target_filter, target_context_fields


def print_target_command_summary(doc):
    doc = doc or {}
    summary = doc.get("summary") or {}
    records = doc.get("target_command_records") or []
    total = summary.get("target_command_count", len(records))
    print(
        "Target command summary: "
        f"total={total} "
        f"network={summary.get('target_command_network_count', 0)} "
        f"explicit_target_action={summary.get('target_command_explicit_action_count', 0)} "
        f"operator_supplied_execution={summary.get('target_command_operator_supplied_execution_count', 0)} "
        f"copy_supported={summary.get('target_command_copy_supported_count', 0)} "
        f"executes_operator_supplied_commands={'yes' if summary.get('target_command_executes_operator_supplied_commands') else 'no'} "
        f"all_require_explicit_target_action={'yes' if summary.get('target_command_all_require_explicit_target_action') else 'no'}"
    )
    print(f"  sides: {format_counts(summary.get('target_command_side_counts') or {})}")
    if summary.get("target_command_route_kind_counts"):
        print(f"  routes: {format_counts(summary.get('target_command_route_kind_counts') or {})}")
    if summary.get("target_command_bridge_profile_counts"):
        print(f"  bridge profiles: {format_counts(summary.get('target_command_bridge_profile_counts') or {})}")
    if summary.get("target_command_session_policy_counts"):
        print(f"  rshell policies: {format_counts(summary.get('target_command_session_policy_counts') or {})}")
    if summary.get("target_command_session_policy_valid_counts"):
        print(f"  rshell policy validity: {format_counts(summary.get('target_command_session_policy_valid_counts') or {})}")
        print(f"  rshell policy errors: {summary.get('target_command_session_policy_error_count', 0)}")
    if summary.get("target_command_retry_backoff_counts"):
        print(f"  rshell retry backoff: {format_counts(summary.get('target_command_retry_backoff_counts') or {})}")


def generated_target_commands(cfg, staged=None):
    return [rec["command"] for rec in generated_target_command_records(cfg, staged)]


def copy_generated_command(cfg, index, default_config="local/operator-session/config.json"):
    try:
        pos = int(index) - 1
    except (TypeError, ValueError):
        raise ValueError("target command index must be a positive integer")
    records = generated_target_command_records(cfg)
    if pos < 0 or pos >= len(records):
        raise ValueError(f"target command index out of range: {index}")
    rec = records[pos]
    command = str(rec.get("command") or "")
    headless_parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
    ]
    if configured_target_filter(cfg):
        headless_parts.extend(["--target-id", configured_target_filter(cfg)])
    headless_parts.extend(["--copy-target-command", str(index)])
    return copy_text_for_operator(cfg, command, label=f"target_command_{index}", details={
        "headless_command": " ".join(shquote(part) for part in headless_parts),
        "ordinal": pos + 1,
        "command_sha256": str(rec.get("command_sha256") or ""),
        "service": str(rec.get("service") or ""),
        "route_kind": str(rec.get("route_kind") or ""),
    })


def _target_command_route_contexts(cfg, host):
    return (
        target_route_context(
            cfg,
            "file-service",
            direct_host=host,
            direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
        ),
        probe_route_context(cfg, host=host, port=cfg.get("GRIT_PROBE_PORT", 22207)),
    )


def _file_service_target_command_record(cfg, host, file_route, args, purpose):
    return attach_target_route_fields({
        "command": render_file_service_command(args, cfg, host=host),
        "purpose": purpose,
        "side": "target",
        "service": "file-service",
        "network": True,
        "requires_explicit_target_action": True,
        "executes_operator_supplied_commands": False,
    }, file_route)


def _base_file_service_target_command_records(cfg, host, file_route):
    return [
        _file_service_target_command_record(
            cfg, host, file_route, ["put", "/etc/config/network"],
            "explicitly upload a target file to the operator file service",
        ),
        _file_service_target_command_record(
            cfg, host, file_route, ["survey", "push"],
            "explicitly upload passive target survey evidence",
        ),
        _file_service_target_command_record(
            cfg, host, file_route, ["reality-test", "push"],
            "explicitly upload active target capability evidence",
        ),
        _file_service_target_command_record(
            cfg, host, file_route, ["manifest", "push"],
            "explicitly upload runtime manifest metadata",
        ),
        _file_service_target_command_record(
            cfg, host, file_route, ["config-push"],
            "explicitly upload effective runtime configuration",
        ),
        _file_service_target_command_record(
            cfg, host, file_route, ["evidence", "push"],
            "explicitly upload an evidence bundle",
        ),
    ]


def _probe_target_command_record(cfg, host, survey_route):
    return attach_target_route_fields({
        "command": render_probe_command(cfg, host=host, port=cfg.get("GRIT_PROBE_PORT", 22207)),
        "purpose": "download and run the architecture-agnostic probe script",
        "side": "target",
        "service": "probe",
        "network": True,
        "requires_explicit_target_action": True,
        "executes_operator_supplied_commands": False,
    }, survey_route)


def _rshell_target_command_record(cfg):
    return {
        "command": "./grit rshell start",
        "purpose": "start the configured reverse shell transport from the target",
        "side": "target",
        "service": "rshell",
        "network": True,
        "requires_explicit_target_action": True,
        "executes_operator_supplied_commands": False,
        "metadata": rshell_session_policy_record(cfg),
    }


def _base_target_command_records(cfg, host, file_route, survey_route):
    return [
        *_base_file_service_target_command_records(cfg, host, file_route),
        _probe_target_command_record(cfg, host, survey_route),
        _rshell_target_command_record(cfg),
    ]


def _staged_target_command_record(cfg, host, file_route, name, rec):
    record = attach_target_route_fields({
        "command": render_fetch_command(name, cfg, host=host),
        "purpose": "explicitly fetch an operator-staged file",
        "side": "target",
        "service": "file-service",
        "network": True,
        "requires_explicit_target_action": True,
        "executes_operator_supplied_commands": False,
        "request_name": name,
        "source_path": str((rec or {}).get("source_path", "")) if isinstance(rec, dict) else "",
        "source_sha256": str((rec or {}).get("sha256", "")) if isinstance(rec, dict) else "",
        "source_size": (rec or {}).get("size", "") if isinstance(rec, dict) else "",
        "stage_kind": str((rec or {}).get("stage_kind") or "file") if isinstance(rec, dict) else "file",
    }, file_route)
    if isinstance(rec, dict):
        for key in (
            "target_id", "target_label", "target_identity_source",
            "target_identity_confidence", "release_path", "tuple_path",
            "payload_preset", "selected_by_recommendation", "compatibility",
        ):
            value = rec.get(key)
            if value not in (None, ""):
                record[key] = value
    return record


def _staged_target_command_records(cfg, host, file_route, staged):
    records = []
    for name in sorted(staged):
        rec = staged.get(name) if isinstance(staged, dict) else {}
        records.append(_staged_target_command_record(cfg, host, file_route, name, rec))
    return records


def _attach_target_command_copy_fields(cfg, records):
    for idx, record in enumerate(records, 1):
        command = str(record.get("command") or "")
        record["ordinal"] = idx
        record["copy_supported"] = bool(command)
        record["copy_selector"] = str(idx)
        copy_cmd = ["scripts/grit-console"]
        if configured_target_filter(cfg):
            copy_cmd.extend(["--target-id", configured_target_filter(cfg)])
        copy_cmd.extend(["--copy-target-command", str(idx)])
        record["copy_command"] = " ".join(shquote(part) for part in copy_cmd)
        record["command_sha256"] = hashlib.sha256(command.encode("utf-8")).hexdigest() if command else ""


def generated_target_command_records(cfg, staged=None):
    staged = staged if staged is not None else load_staged(cfg).get("staged", {})
    host = operator_advertised_host(cfg)
    file_route, survey_route = _target_command_route_contexts(cfg, host)
    records = _base_target_command_records(cfg, host, file_route, survey_route)
    records.extend(_staged_target_command_records(cfg, host, file_route, staged))
    _attach_target_command_copy_fields(cfg, records)
    return records


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


def rshell_session_policy_status(cfg):
    policy = rshell_session_policy_record(cfg)
    policy_summary = policy.get("session_policy_summary") or {}
    retry = policy.get("retry") or {}
    policy_record = {
        "id": "rshell",
        "session_policy": policy.get("session_policy", ""),
        "session_policy_valid": bool(policy.get("session_policy_valid", False)),
        "session_policy_errors": policy.get("session_policy_errors") or [],
        "retry_scope": policy_summary.get("retry_scope", ""),
        "pre_connect_retry_count": policy_summary.get("pre_connect_retry_count", ""),
        "post_disconnect_retry_count": policy_summary.get(
            "post_disconnect_retry_count", ""
        ),
        "retry_backoff": retry.get("backoff", ""),
        "retry_interval_sec": retry.get("interval_sec", ""),
        "retry_jitter_pct": retry.get("jitter_pct", ""),
        "retry_max_interval_sec": retry.get("max_interval_sec", ""),
        "stops_after_success": bool(policy_summary.get("stops_after_success", False)),
        "reconnects_after_disconnect": bool(
            policy_summary.get("reconnects_after_disconnect", False)
        ),
        "persistent_lifecycle": bool(
            policy_summary.get("persistent_lifecycle", False)
        ),
        "fresh_session_on_reconnect": bool(
            policy_summary.get("fresh_session_on_reconnect", False)
        ),
        "session_resume_supported": bool(
            policy_summary.get("session_resume_supported", False)
        ),
        "session_semantics": policy.get("session_semantics") or {},
        "session_policy_summary": policy_summary,
        "retry": retry,
        "retry_timing": policy.get("retry_timing") or {},
    }
    policy_records = [policy_record]
    policy_index_maps = {
        "rshell_session_policy_records_by_id": {
            rec.get("id", ""): rec for rec in policy_records if rec.get("id")
        },
        "rshell_session_policy_records_by_session_policy": records_by_key(
            policy_records, "session_policy"
        ),
        "rshell_session_policy_records_by_session_policy_valid": records_by_key(
            policy_records, "session_policy_valid"
        ),
        "rshell_session_policy_records_by_retry_scope": records_by_key(
            policy_records, "retry_scope"
        ),
        "rshell_session_policy_records_by_retry_backoff": records_by_key(
            policy_records, "retry_backoff"
        ),
        "rshell_session_policy_records_by_reconnects_after_disconnect": records_by_key(
            policy_records, "reconnects_after_disconnect"
        ),
        "rshell_session_policy_records_by_persistent_lifecycle": records_by_key(
            policy_records, "persistent_lifecycle"
        ),
    }
    return {
        "policy": policy,
        "policy_record": policy_record,
        "policy_records": policy_records,
        "policy_index_maps": policy_index_maps,
    }


def shell_listener_max_sessions(cfg, explicit_one_shot=False, scripted=False):
    if explicit_one_shot or scripted:
        return 1
    policy = rshell_session_policy_record(cfg)
    summary = policy.get("session_policy_summary") or {}
    if not policy.get("session_policy_valid", False):
        return 1
    return 0 if summary.get("reconnects_after_disconnect") else 1


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


def target_command_status_context(
    cfg,
    staged_raw=None,
    unfiltered_staged_raw=None,
    target_filter_id=None,
):
    unfiltered_target_command_records = generated_target_command_records(
        cfg,
        unfiltered_staged_raw,
    )
    target_command_records = generated_target_command_records(cfg, staged_raw)
    if target_filter_id:
        target_fields = target_context_fields(cfg, target_filter_id) or {}
        for rec in target_command_records:
            if isinstance(rec, dict):
                rec["target_id_filter"] = target_filter_id
                rec.setdefault("target_id", target_filter_id)
                rec.setdefault("target_label", target_fields.get("target_label", ""))
    target_command_summary = target_command_record_summary(target_command_records)
    target_command_state = target_command_state_status(target_command_summary)
    return {
        "records": target_command_records,
        "unfiltered_records": unfiltered_target_command_records,
        "unfiltered_count": len([
            rec for rec in unfiltered_target_command_records if isinstance(rec, dict)
        ]),
        "indexes": target_command_record_indexes(target_command_records),
        "summary": target_command_summary,
        "state_record": target_command_state["state_record"],
        "state_records": target_command_state["state_records"],
        "state_index_maps": target_command_state["state_index_maps"],
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


def target_command_route_text(rec):
    route_kind = str(rec.get("route_kind") or "direct")
    host = str(rec.get("route_host") or "")
    port = rec.get("route_port", "")
    endpoint = f"{host}:{port}" if host and port not in (None, "") else ""
    if route_kind == "bridge":
        profile = str(rec.get("bridge_profile") or "-")
        path = str(rec.get("bridge_route_path") or "")
        suffix = f" path={path}" if path else ""
        return f"route=bridge bridge_profile={profile}{suffix}"
    if endpoint:
        return f"route=direct endpoint={endpoint}"
    return f"route={route_kind}"


def target_command_display_line(rec, prefix=""):
    command = str(rec.get("command") or "")
    service = str(rec.get("service") or "")
    ordinal = rec.get("ordinal", "")
    route = target_command_route_text(rec)
    ordinal_text = f"{ordinal}: " if ordinal not in (None, "") else ""
    service_text = f" service={service}" if service else ""
    return f"{prefix}{ordinal_text}{route}{service_text} command={command}"
