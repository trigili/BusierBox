"""Line-console action/module rendering helpers."""

from gritlib.console_display import console_table
from gritlib.event_log import append_event


def normalize_line_action_kind(kind):
    text = str(kind or "").strip().lower()
    aliases = {
        "services": "service",
        "listeners": "service",
        "listener": "service",
        "daemons": "daemon",
        "agents": "target",
        "targets": "target",
        "jobs": "workbench",
    }
    return aliases.get(text, text)


def line_action_records_from_snapshot(snap):
    snap = snap or {}
    records = []
    for kind, collection in (
        ("service", snap.get("service_workflow_actions") or []),
        ("daemon", snap.get("operator_daemon_workflow_actions") or []),
        ("target", snap.get("target_workflow_actions") or []),
        ("workbench", snap.get("workbench_actions") or []),
    ):
        for rec in collection:
            if not isinstance(rec, dict):
                continue
            item = dict(rec)
            item["kind"] = kind
            item["id"] = str(item.get("id") or item.get("action_id") or "")
            records.append(item)
    return records


def line_action_matches_term(rec, term):
    text = str(term or "").strip().lower()
    if not text:
        return True
    haystack = (
        f"{rec.get('kind', '')} {rec.get('category', '')} {rec.get('workflow', '')} "
        f"{rec.get('id', '')} {rec.get('action_id', '')} {rec.get('label', '')} "
        f"{rec.get('operator_action_state', '')} {rec.get('operator_action_reason', '')} "
        f"{rec.get('headless_command', rec.get('run_command', rec.get('command', '')))}"
    ).lower()
    return text in haystack


def filtered_line_action_records(actions, filter_text="", kind_filter=""):
    records = list(actions or [])
    term = str(filter_text or "").strip().lower()
    kind_text = normalize_line_action_kind(kind_filter)
    if kind_text:
        records = [rec for rec in records if str(rec.get("kind") or "").lower() == kind_text]
    if term:
        records = [rec for rec in records if line_action_matches_term(rec, term)]
    return records, kind_text


def select_line_action_record(actions, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage: use action ACTION")
    actions = list(actions or [])
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(actions):
            raise ValueError(f"action number out of range: {text}")
        return actions[idx]
    lower = text.lower()
    for rec in actions:
        rec_id = str(rec.get("id") or "")
        action_id = str(rec.get("action_id") or "")
        label = str(rec.get("label") or "")
        qualified = f"{rec.get('kind', '')}:{rec_id}"
        if text in (rec_id, action_id, qualified) or lower == label.lower():
            return rec
    raise ValueError(f"action not found: {text}")


def select_line_action(cfg, actions, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage: use action ACTION")
    selected = select_line_action_record(actions, text)
    action_id = str(selected.get("id") or "")
    cfg["_line_console_action_kind"] = str(selected.get("kind") or "")
    cfg["_line_console_action_id"] = action_id
    cfg["_line_console_module"] = f"action/{action_id}"
    kind = selected.get("kind") or ""
    state = selected.get("operator_action_state") or "-"
    label = selected.get("label") or action_id
    flags = []
    if selected.get("requires_confirmation"):
        flags.append("confirm required")
    if selected.get("background_supported"):
        flags.append("background ok")
    flag_str = f"  |  {', '.join(flags)}" if flags else ""
    print(f"  {kind}:{action_id}  —  {state}  |  {label}{flag_str}")
    print("  options / check / run / run --dry-run / back")
    return selected


def selected_line_action(cfg, actions):
    kind = str(cfg.get("_line_console_action_kind") or "")
    action_id = str(cfg.get("_line_console_action_id") or "")
    if not kind or not action_id:
        return {}
    for rec in actions or []:
        if str(rec.get("kind") or "") == kind and str(rec.get("id") or "") == action_id:
            return rec
    return {}


def split_line_run_args(values):
    flags = []
    selector_parts = []
    for item in list(values or []):
        if item in {"--dry-run", "--confirm", "confirm", "yes"}:
            flags.append(item)
        else:
            selector_parts.append(item)
    return " ".join(selector_parts).strip(), flags


def run_line_selected_action(
    cfg, rec, args=None, dry_run_default=False,
    service_runner=None, daemon_runner=None, workbench_runner=None,
    target_runner=None, workbench_actions=None, target_input_func=None
):
    if not rec:
        raise ValueError("no selected action module; use action ACTION first")
    values = list(args or [])
    dry_run = bool(dry_run_default)
    confirmed = False
    for item in values:
        if item == "--dry-run":
            dry_run = True
        elif item in ("--confirm", "confirm", "yes"):
            confirmed = True
    kind = str(rec.get("kind") or "")
    rec_id = str(rec.get("id") or "")
    if kind == "service":
        if service_runner is None:
            raise ValueError("service action runner is unavailable")
        rc = service_runner(cfg, rec_id, dry_run=dry_run, confirmed=confirmed)
        print(f"action_returncode={rc}")
        return rc
    if kind == "daemon":
        if daemon_runner is None:
            raise ValueError("daemon action runner is unavailable")
        rc = daemon_runner(
            cfg,
            rec_id,
            dry_run=dry_run,
            confirmed=confirmed,
            show_commands=False,
        )
        print(f"action_returncode={rc}")
        return rc
    if kind == "workbench":
        if workbench_runner is None:
            raise ValueError("workbench action runner is unavailable")
        rc = workbench_runner(
            cfg,
            workbench_actions or [],
            rec_id,
            dry_run=dry_run,
            confirmed=confirmed,
            show_commands=False,
        )
        print(f"action_returncode={rc}")
        return rc
    if kind == "target":
        if dry_run:
            print(f"target workflow action: {rec_id}")
            print("dry_run=yes")
            append_event(cfg, "workbench", "target_workflow_action_dry_run", details={
                "id": rec_id,
                "action_id": rec.get("action_id", ""),
                "target_id": rec.get("target_id", ""),
                "target_label": rec.get("target_label", ""),
                "headless_command": rec.get("headless_command", rec.get("command", "")),
            })
            print("action_returncode=0")
            return 0
        if target_runner is None:
            raise ValueError("target action runner is unavailable")
        rc = target_runner(
            cfg,
            rec_id,
            input_func=target_input_func,
            show_commands=False,
        )
        print(f"action_returncode={rc}")
        return rc
    raise ValueError(f"unsupported selected action kind: {kind}")


def print_line_action_records(actions, filter_text="", kind_filter="", quote=None):
    actions, kind_text = filtered_line_action_records(actions, filter_text=filter_text, kind_filter=kind_filter)
    quote = quote or (lambda text: str(text))
    shown = actions[:30]

    def _detail(rec):
        cmd = str(rec.get("headless_command") or rec.get("run_command") or rec.get("command") or "")
        if len(cmd) > 100:
            cmd = cmd[:97] + "…"
        return [("run", cmd)] if cmd else []

    title = "Modules"
    if kind_text:
        title += f"  ({kind_text})"
    if str(filter_text or "").strip():
        title += f"  filter={filter_text!r}"
    title += f"  ({len(shown)} of {len(actions)})" if len(actions) > 30 else f"  ({len(actions)} total)"

    cols = [
        ("Kind", "kind"),
        ("Module", "id"),
        ("State", lambda r: r.get("operator_action_state") or "-"),
        ("Confirm", lambda r: "yes" if r.get("requires_confirmation") else "no"),
    ]
    console_table(
        title, shown, cols, detail_fn=_detail,
        footer="use N  |  use module NAME  |  modules ? for help",
    )
    grouped = {}
    for rec in actions:
        grouped.setdefault(str(rec.get("kind") or "other"), []).append(rec)
    search_records = [
        {
            "kind": "action",
            "label": f"{rec.get('kind', '')}:{rec.get('id', '')}",
            "rec": rec,
            "command": str(rec.get("headless_command") or rec.get("run_command") or rec.get("command") or ""),
            "use_hint": f"use module {quote(str(rec.get('id', '')))}",
        }
        for rec in shown
    ]
    event_details = {
        "filter": str(filter_text or ""),
        "kind": kind_text,
        "match_count": len(actions),
        "shown_count": len(shown),
        "group_counts": {kind: len(items) for kind, items in grouped.items()},
    }
    return search_records, event_details


def print_line_module_category_records(actions):
    actions = list(actions or [])
    grouped = {}
    category_counts = {}
    workflow_counts = {}
    for rec in actions:
        kind = str(rec.get("kind") or "other")
        grouped.setdefault(kind, []).append(rec)
        category = str(rec.get("category") or "-")
        workflow = str(rec.get("workflow") or "-")
        category_counts[category] = category_counts.get(category, 0) + 1
        workflow_counts[workflow] = workflow_counts.get(workflow, 0) + 1
    total = len(actions)
    print(f"Modules  ({total} total)")
    if not actions:
        print("  (none)")
        return {
            "module_count": total,
            "kind_counts": {},
            "category_counts": category_counts,
            "workflow_counts": workflow_counts,
        }
    print("")
    col = max(len(kind) for kind in grouped) + 2
    for kind in sorted(grouped):
        items = grouped[kind]
        states = {}
        for rec in items:
            state = rec.get("operator_action_state") or "unknown"
            states[state] = states.get(state, 0) + 1
        state_summary = "  ".join(f"{state}={count}" for state, count in sorted(states.items()))
        print(f"  {kind:{col}}{len(items)} modules   {state_summary}")
    print("")
    print("  show service|daemon|target|workbench modules  |  modules FILTER  |  use N")
    return {
        "module_count": total,
        "kind_counts": {kind: len(items) for kind, items in grouped.items()},
        "category_counts": category_counts,
        "workflow_counts": workflow_counts,
    }


def print_line_module_categories(cfg, actions):
    event_details = print_line_module_category_records(actions)
    cfg["_line_console_search_results"] = []
    append_event(
        cfg,
        "workbench",
        "workbench_console_module_categories_listed",
        details=event_details,
    )
    return event_details


def print_line_actions(cfg, actions, filter_text="", kind_filter="", quote=None):
    search_records, event_details = print_line_action_records(
        actions,
        filter_text=filter_text,
        kind_filter=kind_filter,
        quote=quote,
    )
    cfg["_line_console_search_results"] = search_records
    append_event(
        cfg,
        "workbench",
        "workbench_console_modules_listed",
        details=event_details,
    )
    return search_records, event_details
