"""Bridge route profile parsing, persistence, and presentation helpers."""

import json
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.console_display import console_table
from gritlib.operator_network import target_visible_host
from gritlib.record_utils import int_value, record_count_by_key, records_by_key
from gritlib.session_state import atomic_write_json, read_json_file, state_file_path, utc_now
from gritlib.shell_utils import shquote
from gritlib.target_records import selected_target_context


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_SERVER_CONFIG = Path("local/server-config.json")
ROUTE_HELP_LINES = [
    "Route model: the target connects to LPORT on the operator; the operator bridge forwards to DEST_HOST:DEST_PORT.",
    "DEST_HOST:DEST_PORT is the endpoint visible from the operator/server running grit-console.",
    "Use hops to document the path the target uses to reach the operator listener; hops do not change the TCP relay destination.",
    "HOP syntax: FROM=TO, FROM->TO, or FROM,TO; use endpoint labels such as target:PORT, jump:PORT, operator:PORT.",
    "Direct target-to-operator SSH: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222",
    "  Meaning: target connects to operator:2222; operator forwards that connection to 127.0.0.1:22.",
    "Multi-hop web admin: route add web-hop 8080 192.168.1.1 80 target:8080=jump:9001 jump:9001=operator:8080",
    "  Meaning: target reaches jump:9001, jump reaches operator:8080; operator forwards to 192.168.1.1:80.",
]


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


def attach_target_route_fields(record, route):
    rec = dict(record)
    route_doc = dict(route or {})
    rec["target_route"] = route_doc
    rec["route_kind"] = str(route_doc.get("route_kind") or "direct")
    rec["route_host"] = str(route_doc.get("host") or "")
    rec["route_port"] = int(route_doc.get("port") or 0)
    rec["bridge_profile"] = str(route_doc.get("bridge_profile") or "")
    rec["bridge_route_path"] = str(route_doc.get("bridge_route_path") or "")
    rec["bridge_hop_count"] = int(route_doc.get("bridge_hop_count") or 0)
    rec["bridge_multi_hop"] = bool(route_doc.get("bridge_multi_hop"))
    rec["requires_bridge"] = bool(route_doc.get("requires_bridge"))
    return rec


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


def bridge_route_listen_text(rec):
    host = rec.get("listen_host") or ""
    port = rec.get("listen_port") or "-"
    return f"{host}:{port}" if host else str(port)


def bridge_route_dest_text(rec):
    host = rec.get("dest_host") or "-"
    port = rec.get("dest_port") or ""
    return f"{host}:{port}" if port else host


def print_bridge_route_records(records, verbose=False, command_builder=None, quote=shquote):
    records = list(records or [])
    command_builder = command_builder or (lambda _action, _name: "")

    def _detail(rec):
        if not verbose:
            return []
        name = str(rec.get("name") or "")
        details = [("path", rec.get("route_path") or "")]
        hops = rec.get("hop_count", 0)
        if hops:
            details.append(("hops", f"{hops}" + ("  (multi-hop)" if rec.get("multi_hop") else "")))
        if rec.get("target_id"):
            details.append(("target", rec["target_id"]))
        if rec.get("last_successful_relay_at"):
            details.append(("last_success", rec["last_successful_relay_at"]))
        if rec.get("last_failure_reason"):
            details.append(("last_failure", rec["last_failure_reason"]))
        details.append(("start", command_builder("start", name)))
        return details

    cols = [
        ("Name", "name"),
        ("Listen", bridge_route_listen_text),
        ("Dest", bridge_route_dest_text),
        ("State", lambda r: r.get("current_state") or "-"),
        ("Active", lambda r: "yes" if r.get("active") else "no"),
    ]
    console_table(
        f"Routes  ({len(records)} total)" if records else "Routes  (none)",
        records, cols, detail_fn=_detail,
        footer="use N or route NAME to select  |  start/stop NAME  |  routes ? for help",
    )
    return bridge_route_search_records(records, command_builder=command_builder, quote=quote)


def bridge_route_search_records(records, command_builder=None, quote=shquote):
    records = list(records or [])
    command_builder = command_builder or (lambda _action, _name: "")
    return [
        {
            "kind": "route",
            "label": f"{rec.get('name','')} state={rec.get('current_state','') or '-'} path={rec.get('route_path','')}",
            "rec": rec,
            "command": command_builder("inspect", str(rec.get("name") or "")),
            "use_hint": f"use route {quote(str(rec.get('name', '')))}",
        }
        for rec in records
    ]


def bridge_profile_record_by_selector(records, selector):
    text = str(selector or "").strip()
    if not text:
        return {}
    rows = list(records or [])
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(rows):
            return rows[idx]
        return {}
    for rec in rows:
        if str(rec.get("name") or "") == text:
            return rec
    return {}


def line_route_record(records, selector):
    return bridge_profile_record_by_selector(records, selector)


def print_line_routes(
    cfg, records, verbose=False, command_builder=None, quote=shquote
):
    records = list(records or [])
    search_records = print_bridge_route_records(
        records,
        verbose=verbose,
        command_builder=command_builder,
        quote=quote,
    )
    cfg["_line_console_search_results"] = search_records
    append_event(cfg, "workbench", "workbench_routes_listed", details={
        "route_count": len(records),
        "verbose": bool(verbose),
    })
    return records


def select_line_route(cfg, selector, records):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage: route NAME|NUMBER")
    records = list(records or [])
    selected = bridge_profile_record_by_selector(records, text)
    if text.isdigit() and not selected:
        raise ValueError(f"route number out of range: {text}")
    if not selected:
        raise ValueError(f"route not found: {text}")
    name = str(selected.get("name") or "")
    cfg["_line_console_module"] = f"route/{name}"
    cfg.pop("_line_console_action_kind", None)
    cfg.pop("_line_console_action_id", None)
    print(f"selected route {name}")
    state = selected.get("current_state") or "stopped"
    listen = f"{selected.get('listen_host','') or '0.0.0.0'}:{selected.get('listen_port','?')}"
    dest = f"{selected.get('dest_host','?')}:{selected.get('dest_port','?')}"
    active = "active" if selected.get("active") else "inactive"
    print(f"  {name}  —  {state} ({active})  |  {listen} → {dest}")
    print("  options / info / start / stop / back")
    append_event(cfg, "workbench", "workbench_route_selected", details={
        "name": name,
        "route_path": selected.get("route_path", ""),
        "active": bool(selected.get("active")),
    })
    return selected


def add_line_route(cfg, args, headless_command_builder=None):
    values = list(args or [])
    if len(values) < 5:
        raise ValueError(
            "usage: route add NAME LISTEN_PORT DEST_HOST DEST_PORT [FROM=TO ...]\n"
            + "\n".join(f"  {line}" for line in ROUTE_HELP_LINES)
        )
    name = values[1]
    try:
        listen_port = int(values[2])
        dest_port = int(values[4])
    except (TypeError, ValueError) as exc:
        raise ValueError("route add requires numeric LISTEN_PORT and DEST_PORT") from exc
    if listen_port <= 0 or dest_port <= 0:
        raise ValueError("route add requires positive LISTEN_PORT and DEST_PORT")
    dest_host = values[3]
    hop_args = values[5:]
    save_cfg = dict(cfg)
    save_cfg["bridge_listen_port"] = listen_port
    save_cfg["bridge_dest_host"] = dest_host
    save_cfg["bridge_dest_port"] = dest_port
    extra = [
        "--save-bridge-profile", name,
        "--bridge-port", str(listen_port),
        "--bridge-dest-host", dest_host,
        "--bridge-dest-port", str(dest_port),
    ]
    for hop in hop_args:
        extra.extend(["--bridge-hop", hop])
    rec = save_bridge_profile(save_cfg, name, purpose="line-console", hop_args=hop_args)
    headless_command_builder = headless_command_builder or (
        lambda _action, _name="", extra=None: ""
    )
    headless = headless_command_builder("save", extra=extra)
    print(f"saved route: {rec.get('name', '')}")
    print(f"  path: {rec.get('route_path', '')}")
    print(f"  listen: {rec.get('listen_host', '')}:{rec.get('listen_port', '')}")
    print(f"  destination: {rec.get('dest_host', '')}:{rec.get('dest_port', '')}")
    print(f"  hops: {rec.get('hop_count', 0)}")
    print(f"  multi-hop: {'yes' if rec.get('multi_hop') else 'no'}")
    print(f"  next: route {rec.get('name', '')}, use route {rec.get('name', '')}, route start {rec.get('name', '')}, route delete {rec.get('name', '')}")
    append_event(cfg, "workbench", "workbench_bridge_profile_saved", details={
        "name": rec.get("name", ""),
        "route_path": rec.get("route_path", ""),
        "listen_port": rec.get("listen_port", ""),
        "dest_host": rec.get("dest_host", ""),
        "dest_port": rec.get("dest_port", ""),
        "hop_count": rec.get("hop_count", 0),
        "multi_hop": bool(rec.get("multi_hop")),
        "headless_command": headless,
    })
    return rec


def start_line_route(
    cfg, route_name, records, headless_command_builder=None, start_service=None
):
    name = str(route_name or "").strip()
    if not name:
        raise ValueError("usage: start ROUTE")
    rec = line_route_record(records, name)
    if not rec:
        raise ValueError(f"route not found: {name}")
    name = str(rec.get("name") or name)
    headless_command_builder = headless_command_builder or (
        lambda _action, _name="", extra=None: ""
    )
    headless = headless_command_builder("start", name)
    if start_service is None:
        raise ValueError("route start requires a service starter")
    start_service(
        cfg,
        "bridge",
        argv_extra=["--bridge-profile", name],
        headless_command=headless,
    )
    print(f"started route {name}")
    append_event(cfg, "workbench", "workbench_route_started", details={
        "name": name,
        "headless_command": headless,
    })


def stop_line_route(
    cfg, route_name, records, headless_command_builder=None, stop_service=None
):
    name = str(route_name or "").strip()
    if not name:
        module = str(cfg.get("_line_console_module") or "")
        if module.startswith("route/"):
            name = module.split("/", 1)[1]
    if not name:
        raise ValueError("usage: stop ROUTE")
    rec = line_route_record(records, name)
    if not rec:
        raise ValueError(f"route not found: {name}")
    name = str(rec.get("name") or name)
    headless_command_builder = headless_command_builder or (
        lambda _action, _name="", extra=None: ""
    )
    headless = headless_command_builder("stop", name)
    if stop_service is None:
        raise ValueError("route stop requires a service stopper")
    stop_service(cfg, "bridge", headless_command=headless)
    print(f"stopped route {name}")
    append_event(cfg, "workbench", "workbench_route_stopped", details={
        "name": name,
        "headless_command": headless,
    })


def delete_line_route(cfg, route_name, records, headless_command_builder=None):
    name = str(route_name or "").strip()
    if not name:
        module = str(cfg.get("_line_console_module") or "")
        if module.startswith("route/"):
            name = module.split("/", 1)[1]
    if not name:
        raise ValueError("usage: route delete ROUTE")
    rec = line_route_record(records, name)
    if not rec:
        raise ValueError(f"route not found: {name}")
    name = str(rec.get("name") or name)
    headless_command_builder = headless_command_builder or (
        lambda _action, _name="", extra=None: ""
    )
    headless = headless_command_builder("delete", name)
    rec = delete_bridge_profile(cfg, name)
    if str(cfg.get("_line_console_module") or "") == f"route/{name}":
        cfg.pop("_line_console_module", None)
    print(f"deleted route {name}: {rec.get('route_path', '')}")
    append_event(cfg, "workbench", "workbench_route_deleted", details={
        "name": name,
        "route_path": rec.get("route_path", ""),
        "headless_command": headless,
    })
    cfg["_line_console_search_results"] = bridge_route_search_records(
        bridge_profile_records(cfg),
        headless_command_builder,
    )
    return rec


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


def bridge_profile_record_summary(profiles=None, hop_records=None):
    profiles = profiles or []
    hop_records = hop_records or []
    return {
        "bridge_profile_count": len(profiles),
        "bridge_profile_active_count": len(
            [rec for rec in profiles if rec.get("active")]
        ),
        "bridge_profile_target_counts": record_count_by_key(profiles, "target_id"),
        "bridge_profile_current_state_counts": record_count_by_key(
            profiles, "current_state"
        ),
        "bridge_profile_requires_target_online_counts": record_count_by_key(
            profiles, "requires_target_online"
        ),
        "bridge_profile_multi_hop_counts": record_count_by_key(profiles, "multi_hop"),
        "bridge_profile_hop_count_counts": record_count_by_key(profiles, "hop_count"),
        "bridge_profile_has_last_successful_relay_counts": record_count_by_key(
            profiles, "has_last_successful_relay"
        ),
        "bridge_profile_has_last_failure_counts": record_count_by_key(
            profiles, "has_last_failure"
        ),
        "bridge_hop_record_count": len(hop_records),
        "bridge_hop_profile_counts": record_count_by_key(hop_records, "profile"),
        "bridge_hop_multi_hop_counts": record_count_by_key(hop_records, "multi_hop"),
        "bridge_hop_is_first_hop_counts": record_count_by_key(
            hop_records, "is_first_hop"
        ),
        "bridge_hop_is_last_hop_counts": record_count_by_key(
            hop_records, "is_last_hop"
        ),
        "bridge_hop_profile_active_counts": record_count_by_key(
            hop_records, "profile_active"
        ),
        "bridge_hop_profile_has_last_successful_relay_counts": record_count_by_key(
            hop_records, "profile_has_last_successful_relay"
        ),
        "bridge_hop_profile_has_last_failure_counts": record_count_by_key(
            hop_records, "profile_has_last_failure"
        ),
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


def bridge_profile_workflow_action_status_summary(records):
    summary = bridge_profile_workflow_action_summary(records)
    return {
        "bridge_profile_workflow_action_count": summary.get("total_count", 0),
        "bridge_profile_workflow_action_available_count": summary.get("available_count", 0),
        "bridge_profile_workflow_action_requires_input_count": summary.get("requires_input_count", 0),
        "bridge_profile_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "bridge_profile_workflow_action_requires_target_online_count": summary.get("requires_target_online_count", 0),
        "bridge_profile_workflow_action_multi_hop_count": summary.get("multi_hop_count", 0),
        "bridge_profile_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "bridge_profile_workflow_action_bridge_profile_counts": summary.get("bridge_profile_counts") or {},
        "bridge_profile_workflow_action_target_counts": summary.get("target_counts") or {},
        "bridge_profile_workflow_action_action_counts": summary.get("action_counts") or {},
        "bridge_profile_workflow_action_category_counts": summary.get("category_counts") or {},
        "bridge_profile_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "bridge_profile_workflow_action_current_state_counts": summary.get("current_state_counts") or {},
        "bridge_profile_workflow_action_active_counts": summary.get("active_counts") or {},
        "bridge_profile_workflow_action_fleet_target_count_counts": summary.get("fleet_target_count_counts") or {},
        "bridge_profile_workflow_action_fleet_offline_target_count_counts": summary.get("fleet_offline_target_count_counts") or {},
        "bridge_profile_workflow_action_fleet_stale_target_count_counts": summary.get("fleet_stale_target_count_counts") or {},
        "bridge_profile_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get("fleet_mailbox_pending_target_count_counts") or {},
        "bridge_profile_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get("fleet_mailbox_pending_work_count_counts") or {},
        "bridge_profile_workflow_action_fleet_poll_overdue_target_count_counts": summary.get("fleet_poll_overdue_target_count_counts") or {},
        "bridge_profile_workflow_action_fleet_has_offline_targets_counts": summary.get("fleet_has_offline_targets_counts") or {},
        "bridge_profile_workflow_action_fleet_has_stale_targets_counts": summary.get("fleet_has_stale_targets_counts") or {},
        "bridge_profile_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get("fleet_has_mailbox_pending_work_counts") or {},
        "bridge_profile_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get("fleet_has_poll_overdue_targets_counts") or {},
        "bridge_profile_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "bridge_profile_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "bridge_profile_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "bridge_profile_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
        "bridge_profile_workflow_action_has_last_successful_relay_counts": summary.get("has_last_successful_relay_counts") or {},
        "bridge_profile_workflow_action_has_last_failure_counts": summary.get("has_last_failure_counts") or {},
    }


def bridge_profile_workflow_fleet_metrics(target_records):
    target_records = [rec for rec in target_records or [] if isinstance(rec, dict)]
    fleet_mailbox_pending_work_count = sum(
        int_value(rec.get("mailbox_pending_work_count", 0))
        for rec in target_records
    )
    fleet_offline_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "offline"
    ])
    fleet_stale_target_count = len([
        rec for rec in target_records
        if str(rec.get("connectivity_state") or "") == "stale"
    ])
    fleet_mailbox_pending_target_count = len([
        rec for rec in target_records
        if int_value(rec.get("mailbox_pending_work_count", 0)) > 0
    ])
    fleet_poll_overdue_target_count = len([
        rec for rec in target_records
        if rec.get("poll_overdue") is True
    ])
    return {
        "fleet_target_count": len(target_records),
        "fleet_connectivity_state_counts": record_count_by_key(target_records, "connectivity_state"),
        "fleet_offline_target_count": fleet_offline_target_count,
        "fleet_stale_target_count": fleet_stale_target_count,
        "fleet_mailbox_pending_target_count": fleet_mailbox_pending_target_count,
        "fleet_mailbox_pending_work_count": fleet_mailbox_pending_work_count,
        "fleet_poll_overdue_target_count": fleet_poll_overdue_target_count,
        "fleet_has_offline_targets": fleet_offline_target_count > 0,
        "fleet_has_stale_targets": fleet_stale_target_count > 0,
        "fleet_has_mailbox_pending_work": fleet_mailbox_pending_work_count > 0,
        "fleet_has_poll_overdue_targets": fleet_poll_overdue_target_count > 0,
    }


def bridge_profile_workflow_action_records(cfg, bridge_profiles, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    config_path = str(cfg.get("_config_path", default_config))
    base = "scripts/grit-console --config " + shquote(config_path)
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    fleet_metrics = bridge_profile_workflow_fleet_metrics(target_records)
    records = []

    def workflow_command(name, action_id, dry_run=False, confirmed=False):
        command = (
            base
            + " --run-bridge-profile-workflow-action "
            + shquote(f"{name}:{action_id}")
        )
        if dry_run:
            command += " --bridge-profile-workflow-dry-run"
        if confirmed:
            command += " --confirm-bridge-profile-workflow-action"
        return command

    def command_for(action_id, name):
        if action_id == "inspect-profile":
            return base + " --inspect-bridge-profile " + shquote(name)
        if action_id == "start-profile":
            return base + " --transport bridge --bridge-profile " + shquote(name)
        if action_id == "stop-profile":
            return base + " --stop --transport bridge"
        if action_id == "delete-profile":
            return base + " --delete-bridge-profile " + shquote(name)
        return base

    def add(profile, action_id, category, label, action_state, action_reason,
            can_run_from_curses_enter=False, curses_enter_action="", requires_confirmation=False):
        name = str(profile.get("name") or "")
        if not name:
            return
        command = command_for(action_id, name)
        records.append({
            "id": f"{name}:{action_id}",
            "action_id": action_id,
            "bridge_profile": name,
            "target_id": str(profile.get("target_id") or ""),
            "target_label": str(profile.get("target_label") or ""),
            "category": category,
            "workflow": "bridge-profile-lifecycle",
            "label": label,
            "command": command,
            "headless_command": command,
            "run_command": workflow_command(name, action_id),
            "dry_run_command": workflow_command(name, action_id, dry_run=True),
            "route_path": str(profile.get("route_path") or ""),
            "listen_host": str(profile.get("listen_host") or ""),
            "listen_port": profile.get("listen_port", ""),
            "dest_host": str(profile.get("dest_host") or ""),
            "dest_port": profile.get("dest_port", ""),
            "current_state": str(profile.get("current_state") or ""),
            "active": bool(profile.get("active")),
            "requires_target_online": bool(profile.get("requires_target_online")),
            "multi_hop": bool(profile.get("multi_hop")),
            "hop_count": int_value(profile.get("hop_count", 0)),
            "has_last_successful_relay": bool(profile.get("has_last_successful_relay")),
            "has_last_failure": bool(profile.get("has_last_failure")),
            "last_failure_reason": str(profile.get("last_failure_reason") or ""),
            **fleet_metrics,
            "available": True,
            "requires_input": False,
            "requires_confirmation": bool(requires_confirmation),
            "operator_action_state": action_state,
            "operator_action_reason": action_reason,
            "can_run_from_curses_enter": bool(can_run_from_curses_enter),
            "curses_enter_action": curses_enter_action,
            "execution_default": "show-command",
            "target_execution": False,
            "tui_visible": True,
            "safety_boundary": "operator-side bridge profile lifecycle; starts/stops local bridge listener process only",
        })

    for profile in bridge_profiles or []:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name") or "")
        if not name:
            continue
        active = bool(profile.get("active"))
        if active:
            start_state = "already-running"
            start_reason = "already-active"
            start_enter = False
            stop_state = "ready"
            stop_reason = "stop-bridge-profile"
            stop_enter = True
        else:
            start_state = "ready"
            start_reason = "start-bridge-profile"
            start_enter = True
            stop_state = "not-running"
            stop_reason = "profile-not-active"
            stop_enter = False
        add(
            profile,
            "inspect-profile",
            "inspect",
            f"Inspect bridge profile {name}",
            "ready",
            "run-now",
        )
        add(
            profile,
            "start-profile",
            "bridge",
            f"Start bridge profile {name}",
            start_state,
            start_reason,
            can_run_from_curses_enter=start_enter,
            curses_enter_action="start-profile" if start_enter else "stop-profile",
        )
        add(
            profile,
            "stop-profile",
            "bridge",
            f"Stop active bridge profile {name}",
            stop_state,
            stop_reason,
            can_run_from_curses_enter=stop_enter,
            curses_enter_action="stop-profile" if stop_enter else "start-profile",
        )
        if records:
            records[-1]["run_command"] = workflow_command(name, "stop-profile", confirmed=True)
            records[-1]["dry_run_command"] = workflow_command(
                name,
                "stop-profile",
                dry_run=True,
                confirmed=True,
            )
        add(
            profile,
            "delete-profile",
            "configuration",
            f"Delete bridge profile {name}",
            "confirm-required",
            "confirmation-required",
            requires_confirmation=True,
        )
        if records:
            records[-1]["run_command"] = workflow_command(name, "delete-profile", confirmed=True)
            records[-1]["dry_run_command"] = workflow_command(
                name,
                "delete-profile",
                dry_run=True,
                confirmed=True,
            )
    records.sort(key=lambda rec: (rec.get("bridge_profile", ""), rec.get("category", ""), rec.get("action_id", "")))
    return records


def save_bridge_profile(cfg, name, purpose="", notes="", hop_args=None, target=None):
    name = str(name or "").strip()
    if not valid_profile_name(name):
        raise ValueError("bridge profile name must contain only letters, numbers, dot, underscore, or dash")
    dest_port = int(cfg.get("bridge_dest_port", 0) or 0)
    if dest_port <= 0:
        raise ValueError("--save-bridge-profile requires --bridge-dest-port")
    target = selected_target_context(cfg) if target is None else (target or {})
    now = str(cfg.get("_now") or utc_now())
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
    out = bridge_profile_record(cfg, name, rec)
    append_event(cfg, "bridge", "bridge_profile_saved", details=out)
    return out


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
    append_event(cfg, "bridge", "bridge_profile_deleted", details=out)
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
