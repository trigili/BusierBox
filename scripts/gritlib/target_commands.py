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
from gritlib.target_records import configured_target_filter


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


def generated_target_command_records(cfg, staged=None):
    staged = staged if staged is not None else load_staged(cfg).get("staged", {})
    host = operator_advertised_host(cfg)
    file_route = target_route_context(cfg, "file-service", direct_host=host, direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204))
    survey_route = probe_route_context(cfg, host=host, port=cfg.get("GRIT_PROBE_PORT", 22207))
    records = [
        attach_target_route_fields({
            "command": render_file_service_command(["put", "/etc/config/network"], cfg, host=host),
            "purpose": "explicitly upload a target file to the operator file service",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_file_service_command(["survey", "push"], cfg, host=host),
            "purpose": "explicitly upload passive target survey evidence",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_file_service_command(["reality-test", "push"], cfg, host=host),
            "purpose": "explicitly upload active target capability evidence",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_file_service_command(["manifest", "push"], cfg, host=host),
            "purpose": "explicitly upload runtime manifest metadata",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_file_service_command(["config-push"], cfg, host=host),
            "purpose": "explicitly upload effective runtime configuration",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_file_service_command(["evidence", "push"], cfg, host=host),
            "purpose": "explicitly upload an evidence bundle",
            "side": "target",
            "service": "file-service",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, file_route),
        attach_target_route_fields({
            "command": render_probe_command(cfg, host=host, port=cfg.get("GRIT_PROBE_PORT", 22207)),
            "purpose": "download and run the architecture-agnostic probe script",
            "side": "target",
            "service": "probe",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
        }, survey_route),
        {
            "command": "./grit rshell start",
            "purpose": "start the configured reverse shell transport from the target",
            "side": "target",
            "service": "rshell",
            "network": True,
            "requires_explicit_target_action": True,
            "executes_operator_supplied_commands": False,
            "metadata": rshell_session_policy_record(cfg),
        },
    ]
    for name in sorted(staged):
        rec = staged.get(name) if isinstance(staged, dict) else {}
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
        records.append(record)
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


def shell_listener_max_sessions(cfg, explicit_one_shot=False, scripted=False):
    if explicit_one_shot or scripted:
        return 1
    policy = rshell_session_policy_record(cfg)
    summary = policy.get("session_policy_summary") or {}
    if not policy.get("session_policy_valid", False):
        return 1
    return 0 if summary.get("reconnects_after_disconnect") else 1


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
