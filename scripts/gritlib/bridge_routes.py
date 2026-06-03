"""Bridge route profile parsing, persistence, and presentation helpers."""

import json
from pathlib import Path

from gritlib.operator_network import target_visible_host
from gritlib.record_utils import record_count_by_key
from gritlib.session_state import atomic_write_json, read_json_file, state_file_path
from gritlib.shell_utils import shquote


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def records_by_key(records, key):
    out = {}
    for rec in records or []:
        value = rec.get(key)
        out.setdefault(str(value), []).append(rec)
    return out


def bridge_profiles_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(cfg.get("bridge_profiles_file") or Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "bridge-profiles.json"))


def valid_profile_name(name):
    text = str(name or "").strip()
    return bool(text) and all(ch.isalnum() or ch in "._-" for ch in text)


def load_bridge_profiles(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    data = read_json_file(bridge_profiles_path(cfg, default_operator_session_dir), {"schema": 1, "profiles": {}})
    if not isinstance(data, dict):
        data = {"schema": 1, "profiles": {}}
    if not isinstance(data.get("profiles"), dict):
        data["profiles"] = {}
    data.setdefault("schema", 1)
    return data


def parse_bridge_hop(text):
    raw = str(text or "").strip()
    for sep in ("->", "=", ","):
        if sep in raw:
            left, right = raw.split(sep, 1)
            left = left.strip()
            right = right.strip()
            if not left or not right:
                raise ValueError("--bridge-hop requires non-empty FROM and TO endpoints")
            return {"from": left, "to": right}
    raise ValueError("--bridge-hop must use FROM=TO, FROM->TO, or FROM,TO")


def default_bridge_hops(cfg, dest_port):
    listen_port = int(cfg.get("bridge_listen_port") or cfg.get("listen_port") or 22206)
    dest_host = str(cfg.get("bridge_dest_host") or cfg.get("dest_host") or "127.0.0.1")
    return [{"from": f"operator:{listen_port}", "to": f"{dest_host}:{dest_port}"}]


def bridge_hops_from_args(cfg, dest_port, hop_args=None):
    if not hop_args:
        return default_bridge_hops(cfg, dest_port)
    return [parse_bridge_hop(item) for item in hop_args]


def bridge_route_path(rec):
    hops = rec.get("hops")
    if isinstance(hops, list) and hops:
        path = []
        for hop in hops:
            if not isinstance(hop, dict):
                continue
            src = str(hop.get("from") or "").strip()
            dst = str(hop.get("to") or "").strip()
            if not src or not dst:
                continue
            if not path:
                path.append(src)
            elif path[-1] != src:
                path.append(src)
            path.append(dst)
        if path:
            return " -> ".join(path)
    return f"operator:{rec.get('listen_port', '')} -> {rec.get('dest_host', '')}:{rec.get('dest_port', '')}"


def parse_endpoint_host_port(endpoint):
    text = str(endpoint or "").strip()
    if not text:
        return "", 0
    if text.startswith("[") and "]:" in text:
        host, port = text[1:].split("]:", 1)
    elif ":" in text:
        host, port = text.rsplit(":", 1)
    else:
        return text, 0
    try:
        return host.strip(), int(port)
    except (TypeError, ValueError):
        return host.strip(), 0


def bridge_profile_record(cfg, name, rec, service_state=None):
    out = dict(rec or {})
    out["name"] = str(name or out.get("name") or "")
    out["listen_host"] = str(out.get("listen_host") or cfg.get("listen_host") or "")
    out["listen_port"] = int(out.get("listen_port") or cfg.get("bridge_listen_port", 22206) or 0)
    out["dest_host"] = str(out.get("dest_host") or "")
    out["dest_port"] = int(out.get("dest_port") or 0)
    out["target_id"] = str(out.get("target_id") or "")
    out["target_label"] = str(out.get("target_label") or "")
    out["purpose"] = str(out.get("purpose") or "")
    out["notes"] = str(out.get("notes") or "")
    if not isinstance(out.get("hops"), list) or not out.get("hops"):
        out["hops"] = default_bridge_hops(out, int(out.get("dest_port") or 0))
    out["route_path"] = bridge_route_path(out)
    out["hop_count"] = len(out.get("hops") or []) if isinstance(out.get("hops"), list) else 1
    out["multi_hop"] = out["hop_count"] > 1
    out["start_command"] = f"scripts/grit-console --transport bridge --bridge-profile {shquote(out['name'])}"
    out["stop_command"] = "scripts/grit-console --stop --transport bridge"
    out["requires_target_online"] = bool(out.get("target_id"))
    state = service_state if isinstance(service_state, dict) else {}
    active_profile = str(state.get("bridge_profile") or "")
    out["current_state"] = str(state.get("status") or "configured") if active_profile == out["name"] else "configured"
    out["active"] = active_profile == out["name"] and out["current_state"] in ("starting", "listening")
    out["pid"] = state.get("pid", "") if active_profile == out["name"] else ""
    out["last_error"] = str(state.get("error") or "") if active_profile == out["name"] else ""
    state_failure = ""
    if active_profile == out["name"]:
        state_failure = str(state.get("error") or "")
        if not state_failure and out["current_state"] == "error":
            state_failure = str(state.get("stopped_reason") or "")
    out["last_failure_reason"] = str(out.get("last_failure_reason") or state_failure)
    out["last_failure_at"] = str(out.get("last_failure_at") or "")
    out["last_failure_remote_addr"] = str(out.get("last_failure_remote_addr") or "")
    out["last_successful_relay_at"] = str(out.get("last_successful_relay_at") or "")
    out["has_last_successful_relay"] = bool(out["last_successful_relay_at"])
    out["has_last_failure"] = bool(out["last_failure_at"] or out["last_failure_reason"])
    return out


def selected_bridge_profile_record(cfg):
    name = str(cfg.get("bridge_profile") or "").strip()
    if not name:
        return {}
    profiles = load_bridge_profiles(cfg).get("profiles") or {}
    rec = profiles.get(name)
    if not isinstance(rec, dict):
        return {}
    return bridge_profile_record(cfg, name, rec)


def target_route_context(cfg, service, direct_host=None, direct_port=None):
    direct_port = int(direct_port or 0)
    direct = {
        "route_kind": "direct",
        "service": str(service or ""),
        "host": target_visible_host(direct_host, cfg),
        "port": direct_port,
        "bridge_profile": "",
        "bridge_route_path": "",
        "bridge_hop_count": 0,
        "bridge_multi_hop": False,
        "requires_bridge": False,
    }
    profile = selected_bridge_profile_record(cfg)
    if not profile:
        return direct
    hops = profile.get("hops") if isinstance(profile.get("hops"), list) else []
    first = hops[0] if hops and isinstance(hops[0], dict) else {}
    endpoint_host, endpoint_port = parse_endpoint_host_port(first.get("from") or "")
    if not endpoint_port:
        endpoint_port = int(profile.get("listen_port") or direct_port or 0)
    direct.update({
        "route_kind": "bridge",
        "host": target_visible_host(endpoint_host, cfg, fallback_host=direct_host),
        "port": endpoint_port,
        "bridge_profile": str(profile.get("name") or ""),
        "bridge_route_path": str(profile.get("route_path") or ""),
        "bridge_hop_count": int(profile.get("hop_count") or 0),
        "bridge_multi_hop": bool(profile.get("multi_hop")),
        "requires_bridge": True,
    })
    return direct


def bridge_profile_records(cfg):
    profiles = load_bridge_profiles(cfg).get("profiles") or {}
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    bridge_state = ((state.get("services") or {}).get("bridge") or {}) if isinstance(state, dict) else {}
    return [
        bridge_profile_record(cfg, name, rec, service_state=bridge_state)
        for name, rec in sorted(profiles.items())
        if isinstance(rec, dict)
    ]


def bridge_profile_indexes(records):
    return {
        "bridge_profiles_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "bridge_profiles_by_target_id": records_by_key(records, "target_id"),
        "bridge_profiles_by_dest_host": records_by_key(records, "dest_host"),
        "bridge_profiles_by_listen_port": records_by_key(records, "listen_port"),
        "bridge_profiles_by_current_state": records_by_key(records, "current_state"),
        "bridge_profiles_by_active": records_by_key(records, "active"),
        "bridge_profiles_by_requires_target_online": records_by_key(records, "requires_target_online"),
        "bridge_profiles_by_multi_hop": records_by_key(records, "multi_hop"),
        "bridge_profiles_by_hop_count": records_by_key(records, "hop_count"),
        "bridge_profiles_by_route_path": records_by_key(records, "route_path"),
        "bridge_profiles_by_has_last_successful_relay": records_by_key(records, "has_last_successful_relay"),
        "bridge_profiles_by_has_last_failure": records_by_key(records, "has_last_failure"),
    }


def bridge_hop_records_from_profiles(profiles):
    records = []
    for profile in profiles or []:
        if not isinstance(profile, dict):
            continue
        profile_name = str(profile.get("name") or "")
        route_path = str(profile.get("route_path") or "")
        hops = profile.get("hops") if isinstance(profile.get("hops"), list) else []
        hop_count = len(hops)
        for idx, hop in enumerate(hops, 1):
            if not isinstance(hop, dict):
                continue
            from_endpoint = str(hop.get("from") or "").strip()
            to_endpoint = str(hop.get("to") or "").strip()
            from_host, from_port = parse_endpoint_host_port(from_endpoint)
            to_host, to_port = parse_endpoint_host_port(to_endpoint)
            records.append({
                "id": f"{profile_name}:{idx}",
                "profile": profile_name,
                "profile_name": profile_name,
                "ordinal": idx,
                "hop_index": idx,
                "hop_count": hop_count,
                "is_first_hop": idx == 1,
                "is_last_hop": idx == hop_count,
                "multi_hop": hop_count > 1,
                "from": from_endpoint,
                "to": to_endpoint,
                "from_host": from_host,
                "from_port": from_port,
                "to_host": to_host,
                "to_port": to_port,
                "route_path": route_path,
                "target_id": str(profile.get("target_id") or ""),
                "target_label": str(profile.get("target_label") or ""),
                "requires_target_online": bool(profile.get("requires_target_online")),
                "current_state": str(profile.get("current_state") or ""),
                "profile_active": bool(profile.get("active")),
                "profile_has_last_successful_relay": bool(profile.get("has_last_successful_relay")),
                "profile_has_last_failure": bool(profile.get("has_last_failure")),
            })
    return records


def bridge_hop_indexes(records):
    return {
        "bridge_hops_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "bridge_hops_by_profile": records_by_key(records, "profile"),
        "bridge_hops_by_profile_name": records_by_key(records, "profile_name"),
        "bridge_hops_by_ordinal": records_by_key(records, "ordinal"),
        "bridge_hops_by_from": records_by_key(records, "from"),
        "bridge_hops_by_to": records_by_key(records, "to"),
        "bridge_hops_by_from_host": records_by_key(records, "from_host"),
        "bridge_hops_by_from_port": records_by_key(records, "from_port"),
        "bridge_hops_by_to_host": records_by_key(records, "to_host"),
        "bridge_hops_by_to_port": records_by_key(records, "to_port"),
        "bridge_hops_by_route_path": records_by_key(records, "route_path"),
        "bridge_hops_by_target_id": records_by_key(records, "target_id"),
        "bridge_hops_by_multi_hop": records_by_key(records, "multi_hop"),
        "bridge_hops_by_is_first_hop": records_by_key(records, "is_first_hop"),
        "bridge_hops_by_is_last_hop": records_by_key(records, "is_last_hop"),
        "bridge_hops_by_current_state": records_by_key(records, "current_state"),
        "bridge_hops_by_profile_active": records_by_key(records, "profile_active"),
        "bridge_hops_by_profile_has_last_successful_relay": records_by_key(records, "profile_has_last_successful_relay"),
        "bridge_hops_by_profile_has_last_failure": records_by_key(records, "profile_has_last_failure"),
    }


def bridge_profile_workflow_action_indexes(records):
    return {
        "bridge_profile_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "bridge_profile_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "bridge_profile_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "bridge_profile_workflow_actions_by_target_id": records_by_key(records, "target_id"),
        "bridge_profile_workflow_actions_by_category": records_by_key(records, "category"),
        "bridge_profile_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "bridge_profile_workflow_actions_by_current_state": records_by_key(records, "current_state"),
        "bridge_profile_workflow_actions_by_active": records_by_key(records, "active"),
        "bridge_profile_workflow_actions_by_requires_target_online": records_by_key(records, "requires_target_online"),
        "bridge_profile_workflow_actions_by_multi_hop": records_by_key(records, "multi_hop"),
        "bridge_profile_workflow_actions_by_hop_count": records_by_key(records, "hop_count"),
        "bridge_profile_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "bridge_profile_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "bridge_profile_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "bridge_profile_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "bridge_profile_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "bridge_profile_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "bridge_profile_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "bridge_profile_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "bridge_profile_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "bridge_profile_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "bridge_profile_workflow_actions_by_has_last_successful_relay": records_by_key(records, "has_last_successful_relay"),
        "bridge_profile_workflow_actions_by_has_last_failure": records_by_key(records, "has_last_failure"),
        "bridge_profile_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "bridge_profile_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "bridge_profile_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "bridge_profile_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "bridge_profile_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def bridge_profile_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "target_counts": record_count_by_key(records, "target_id"),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "current_state_counts": record_count_by_key(records, "current_state"),
        "active_counts": record_count_by_key(records, "active"),
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
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "requires_target_online_count": len([rec for rec in records or [] if rec.get("requires_target_online") is True]),
        "multi_hop_count": len([rec for rec in records or [] if rec.get("multi_hop") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
        "has_last_successful_relay_counts": record_count_by_key(records, "has_last_successful_relay"),
        "has_last_failure_counts": record_count_by_key(records, "has_last_failure"),
    }


def save_bridge_profile(cfg, name, purpose="", notes="", hop_args=None, target=None):
    name = str(name or "").strip()
    if not valid_profile_name(name):
        raise ValueError("bridge profile name must contain only letters, numbers, dot, underscore, or dash")
    dest_port = int(cfg.get("bridge_dest_port", 0) or 0)
    if dest_port <= 0:
        raise ValueError("--save-bridge-profile requires --bridge-dest-port")
    target = target or {}
    now = str(cfg.get("_now") or "")
    rec = {
        "schema": 1,
        "name": name,
        "listen_host": str(cfg.get("listen_host", "")),
        "listen_port": int(cfg.get("bridge_listen_port", 22206)),
        "dest_host": str(cfg.get("bridge_dest_host", "127.0.0.1")),
        "dest_port": dest_port,
        "target_id": str(target.get("target_id") or cfg.get("_target_id_filter") or ""),
        "target_label": str(target.get("target_label") or cfg.get("_target_label_filter") or ""),
        "purpose": str(purpose or ""),
        "notes": str(notes or ""),
        "hops": bridge_hops_from_args(cfg, dest_port, hop_args=hop_args),
        "created_at": now,
        "updated_at": now,
    }
    data = load_bridge_profiles(cfg)
    existing = data.setdefault("profiles", {}).get(name)
    if isinstance(existing, dict) and existing.get("created_at"):
        rec["created_at"] = existing.get("created_at")
    data["profiles"][name] = rec
    atomic_write_json(bridge_profiles_path(cfg), data)
    return bridge_profile_record(cfg, name, rec)


def delete_bridge_profile(cfg, name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("bridge profile name is required")
    data = load_bridge_profiles(cfg)
    profiles = data.setdefault("profiles", {})
    rec = profiles.get(name)
    if not isinstance(rec, dict):
        raise ValueError(f"bridge profile not found: {name}")
    out = bridge_profile_record(cfg, name, rec)
    del profiles[name]
    atomic_write_json(bridge_profiles_path(cfg), data)
    return out


def apply_bridge_profile(cfg, name):
    name = str(name or "").strip()
    profiles = load_bridge_profiles(cfg).get("profiles") or {}
    rec = profiles.get(name)
    if not isinstance(rec, dict):
        raise ValueError(f"bridge profile not found: {name}")
    cfg["bridge_profile"] = name
    cfg["listen_host"] = str(rec.get("listen_host") or cfg.get("listen_host", "0.0.0.0"))
    cfg["bridge_listen_port"] = int(rec.get("listen_port") or cfg.get("bridge_listen_port", 22206))
    cfg["bridge_dest_host"] = str(rec.get("dest_host") or cfg.get("bridge_dest_host", "127.0.0.1"))
    cfg["bridge_dest_port"] = int(rec.get("dest_port") or cfg.get("bridge_dest_port", 0))
    if rec.get("target_id"):
        cfg["_target_id_filter"] = str(rec.get("target_id") or "")
        if rec.get("target_label"):
            cfg["_target_label_filter"] = str(rec.get("target_label") or "")
    return bridge_profile_record(cfg, name, rec)


def bridge_profile_payload(cfg, name):
    profiles = load_bridge_profiles(cfg).get("profiles") or {}
    rec = profiles.get(str(name or "").strip())
    if not isinstance(rec, dict):
        raise ValueError(f"bridge profile not found: {name}")
    return bridge_profile_record(cfg, name, rec)


def print_bridge_profile(cfg, name, json_output=False):
    out = bridge_profile_payload(cfg, name)
    if json_output:
        print(json.dumps({"schema": 1, "path": str(bridge_profiles_path(cfg)), "profile": out}, indent=2, sort_keys=True))
        return 0
    print(f"Bridge profile {out.get('name', '')}")
    print(f"  listen: {out.get('listen_host', '')}:{out.get('listen_port', '')}")
    print(f"  destination: {out.get('dest_host', '')}:{out.get('dest_port', '')}")
    print(f"  route_path: {out.get('route_path', '')}")
    print(f"  state: {out.get('current_state', '')} active={'yes' if out.get('active') else 'no'} pid={out.get('pid', '') or '-'}")
    print(f"  relay: last_success={out.get('last_successful_relay_at', '') or '-'} client_bytes={out.get('last_bytes_from_client', '') or 0} upstream_bytes={out.get('last_bytes_from_upstream', '') or 0}")
    print(f"  failure: last={out.get('last_failure_at', '') or '-'} reason={out.get('last_failure_reason', '') or '-'}")
    print(f"  target: {out.get('target_id', '') or '-'} label={out.get('target_label', '') or '-'}")
    print(f"  purpose: {out.get('purpose', '') or '-'}")
    print(f"  notes: {out.get('notes', '') or '-'}")
    print(f"  start_command: {out.get('start_command', '')}")
    print(f"  stop_command: {out.get('stop_command', '')}")
    for idx, hop in enumerate(out.get("hops") or [], 1):
        print(f"  hop {idx}: {hop.get('from', '')} -> {hop.get('to', '')}")
    return 0


def print_bridge_profiles(cfg, json_output=False):
    records = bridge_profile_records(cfg)
    hop_records = bridge_hop_records_from_profiles(records)
    if json_output:
        payload = {
            "schema": 1,
            "path": str(bridge_profiles_path(cfg)),
            "profiles": records,
            "bridge_hop_records": hop_records,
            **bridge_profile_indexes(records),
            **bridge_hop_indexes(hop_records),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if not records:
        print("No bridge profiles.")
        return 0
    for rec in records:
        print(
            f"{rec.get('name', '')}\t{rec.get('listen_host', '')}:{rec.get('listen_port', '')}"
            f"\t{rec.get('dest_host', '')}:{rec.get('dest_port', '')}"
            f"\tstate={rec.get('current_state', '')}"
            f"\ttarget={rec.get('target_id', '') or '-'}"
            f"\tlast_success={rec.get('last_successful_relay_at', '') or '-'}"
            f"\tlast_failure={rec.get('last_failure_reason', '') or '-'}"
        )
        print(f"  path: {rec.get('route_path', '')}")
        if rec.get("purpose") or rec.get("notes"):
            print(f"  purpose={rec.get('purpose', '') or '-'} notes={rec.get('notes', '') or '-'}")
    return 0
