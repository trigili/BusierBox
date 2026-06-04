"""Line-console search helpers."""

from pathlib import Path

from gritlib.line_state import line_action_state_text


def parse_line_search_command(cmd, args):
    if str(cmd or "").strip().lower() != "search":
        return None
    return {
        "action": "search",
        "query": " ".join(str(arg) for arg in (args or [])).strip(),
    }


def dispatch_line_search_command(search_cmd, *, search_func=None):
    try:
        if search_func:
            return search_func((search_cmd or {}).get("query", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported search command")


def dispatch_line_number_selection(
    choice,
    cfg,
    *,
    use_result_func=None,
    clear_results_func=None,
    require_active_results=False,
):
    text = str(choice or "").strip()
    if not text.isdigit():
        return False
    search_results = list((cfg or {}).get("_line_console_search_results") or [])
    if not search_results:
        if require_active_results:
            return False
        print("no numbered result is active; run a list command first, then use N")
        return True
    idx = int(text) - 1
    if idx < 0 or idx >= len(search_results):
        print(f"numbered result not found: {text}; run a list command first, then use N")
        return True
    try:
        if use_result_func:
            use_result_func(text)
        if clear_results_func:
            clear_results_func()
    except ValueError as exc:
        print(exc)
    return True


def clear_line_search_results(cfg):
    cfg["_line_console_search_results"] = []


def line_searchable_text(rec):
    parts = []
    if isinstance(rec, dict):
        for key, value in sorted(rec.items()):
            if isinstance(value, (str, int, float, bool)):
                parts.append(f"{key}={value}")
            elif isinstance(value, list):
                parts.append(f"{key}=" + ",".join(str(item) for item in value[:8]))
    return " ".join(parts).lower()


def print_line_search_results(
    query,
    snap=None,
    service_records=None,
    route_records=None,
    action_records=None,
    route_command_builder=None,
    job_cancel_command_builder=None,
    quote=None,
):
    term = str(query or "").strip().lower()
    if not term:
        raise ValueError("usage: search TERM")
    snap = snap or {}
    service_records = list(service_records or [])
    route_records = list(route_records or [])
    action_records = list(action_records or [])
    route_command_builder = route_command_builder or (lambda _action, _name: "")
    job_cancel_command_builder = job_cancel_command_builder or (lambda _job_id: "")
    quote = quote or (lambda text: str(text))
    matches = []

    def add(kind, label, rec, command=""):
        if len(matches) >= 30:
            return
        haystack = f"{kind} {label} {command} {line_searchable_text(rec)}".lower()
        if term in haystack:
            matches.append((kind, label, rec, command))

    for rec in snap.get("targets") or []:
        add("target", f"{rec.get('target_id', '')} label={rec.get('label', '') or '-'} state={rec.get('connectivity_state', '') or '-'}", rec)
    for rec in service_records:
        add("service", f"{rec.get('name', '')} actual={rec.get('actual', '') or '-'} port={rec.get('port', '') or '-'}", rec)
    for rec in route_records:
        route_name = str(rec.get("name") or "")
        add(
            "route",
            f"{route_name} state={rec.get('current_state', '') or '-'} path={rec.get('route_path', '')}",
            rec,
            route_command_builder("inspect", route_name),
        )
    for rec in action_records:
        add(
            "action",
            f"{rec.get('kind', '')}:{rec.get('id', '')} state={line_action_state_text(rec)}",
            rec,
            str(rec.get("headless_command") or rec.get("run_command") or rec.get("command") or ""),
        )
    for rec in snap.get("sessions") or []:
        session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
        add("session", f"{session_id} service={rec.get('service', '') or '-'} state={rec.get('state', '') or '-'}", rec)
    for rec in snap.get("workbench_jobs") or []:
        add(
            "job",
            f"{rec.get('id', '')} action: {rec.get('action_id', '') or '-'} state: {rec.get('effective_state', '') or rec.get('state', '') or '-'}",
            rec,
            job_cancel_command_builder(str(rec.get("id") or "")),
        )
    for name, rec in sorted((snap.get("staged") or {}).items()):
        item = dict(rec) if isinstance(rec, dict) else {}
        item["request_name"] = name
        add("file", f"{name} kind={item.get('stage_kind', 'file')} source={item.get('source_path', '')}", item)
    for rec in (snap.get("command_queue") or {}).get("commands") or []:
        add("queue", f"{rec.get('id', '')} status={rec.get('status', '') or '-'} command={rec.get('command', '')}", rec)

    print(f"Search results for {query}:")
    if not matches:
        print("  none")
    search_records = []
    for idx, (kind, label, rec, command) in enumerate(matches, 1):
        print(f"  {idx}: {kind} {label}")
        use_hint = ""
        stored_command = command
        if kind == "target":
            use_hint = f"use target {quote(str(rec.get('target_id', '')))}"
        elif kind == "service":
            use_hint = f"use service {quote(str(rec.get('name', '')))}"
        elif kind == "route":
            use_hint = f"use route {quote(str(rec.get('name', '')))}"
        elif kind == "action":
            use_hint = f"use action {quote(str(rec.get('id', '')))}"
        elif kind == "session":
            session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
            use_hint = f"use session {quote(str(session_id))}"
        elif kind == "job":
            use_hint = f"use job {quote(str(rec.get('id', '')))}"
        if use_hint:
            print(f"     use: use {idx}")
            print(f"     use command: {use_hint}")
        search_records.append({
            "kind": kind,
            "label": label,
            "rec": rec,
            "command": stored_command,
            "use_hint": use_hint,
        })
    return search_records


def use_line_search_result(
    selector,
    results,
    *,
    select_target,
    select_service,
    select_route,
    select_action,
    select_session,
    select_job,
    probe_result_config,
):
    text = str(selector or "").strip()
    if not text.isdigit():
        raise ValueError("usage: use N")
    results = list(results or [])
    if not results:
        raise ValueError("no numbered results active; run search, targets, listeners, sessions, files, jobs, routes, or probe results")
    idx = int(text) - 1
    if idx < 0 or idx >= len(results):
        raise ValueError(f"search result number out of range: {text}")
    item = results[idx] if isinstance(results[idx], dict) else {}
    kind = str(item.get("kind") or "")
    rec = item.get("rec") if isinstance(item.get("rec"), dict) else {}
    if kind == "target":
        return select_target(str(rec.get("target_id") or ""))
    if kind == "service":
        return select_service(str(rec.get("name") or ""))
    if kind == "route":
        return select_route(str(rec.get("name") or ""))
    if kind == "action":
        return select_action(str(rec.get("id") or ""))
    if kind == "session":
        session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
        return select_session(str(session_id))
    if kind == "job":
        return select_job(str(rec.get("id") or ""))
    if kind == "probe-result":
        return probe_result_config([str(item.get("ordinal") or text)])
    raise ValueError(f"search result {text} is not directly selectable")
