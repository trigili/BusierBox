"""Line-console action/module rendering helpers."""

from gritlib.console_display import console_table


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
