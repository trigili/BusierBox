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
