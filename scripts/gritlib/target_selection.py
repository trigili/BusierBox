"""Workbench target selection helpers for grit-console."""

from pathlib import Path

from gritlib.event_log import append_event
from gritlib.session_state import update_server_state, utc_now
from gritlib.shell_utils import shquote
from gritlib.target_context import configured_target_filter
from gritlib.target_store import load_targets


DEFAULT_SERVER_CONFIG = Path("local/server-config.json")


def scoped_target_cfg(cfg, target_id, target_label=""):
    scoped = dict(cfg)
    scoped["_target_id_filter"] = str(target_id or "").strip()
    if target_label:
        scoped["_target_label_filter"] = str(target_label or "")
    return scoped


def set_workbench_target_filter(cfg, selector, targets=None, default_config=DEFAULT_SERVER_CONFIG):
    text = str(selector or "").strip()
    now = utc_now()
    config_path = str(cfg.get("_config_path", default_config))
    if text.lower() in ("", "all", "clear", "*"):
        cfg.pop("_target_id_filter", None)
        cfg.pop("_target_label_filter", None)
        update_server_state(cfg, "workbench", "open", {
            "selected_target_id": "",
            "selected_target_label": "",
            "selected_target_at": now,
        })
        headless = "scripts/grit-console --config " + shquote(config_path) + " --status"
        append_event(cfg, "workbench", "workbench_target_filter_cleared", details={
            "selected_at": now,
            "headless_command": headless,
        })
        return {"target_id": "", "target_label": "", "selected": False, "headless_command": headless}

    records = []
    if targets is not None:
        records = [rec for rec in targets or [] if isinstance(rec, dict)]
    else:
        for target_id, rec in sorted((load_targets(cfg).get("targets") or {}).items()):
            if isinstance(rec, dict):
                item = dict(rec)
                item.setdefault("target_id", target_id)
                records.append(item)
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"target number out of range: {text}")
        selected = records[idx]
    else:
        lower = text.lower()
        selected = {}
        for rec in records:
            target_id = str(rec.get("target_id") or "")
            label = str(rec.get("label") or rec.get("target_label") or "")
            aliases = [str(item) for item in rec.get("aliases") or []]
            if text == target_id or lower == label.lower() or lower in [alias.lower() for alias in aliases]:
                selected = rec
                break
        if not selected:
            raise ValueError(f"target not found: {text}; run: targets, then target NAME, use target ID, use target LABEL, or use target N")
    target_id = str(selected.get("target_id") or "").strip()
    if not target_id:
        raise ValueError(f"target not found: {text}; run: targets, then target NAME, use target ID, use target LABEL, or use target N")
    target_label = str(selected.get("label") or selected.get("target_label") or "")
    cfg["_target_id_filter"] = target_id
    if target_label:
        cfg["_target_label_filter"] = target_label
    else:
        cfg.pop("_target_label_filter", None)
    update_server_state(cfg, "workbench", "open", {
        "selected_target_id": target_id,
        "selected_target_label": target_label,
        "selected_target_at": now,
    })
    headless = (
        "scripts/grit-console --config "
        + shquote(config_path)
        + " --target-id "
        + shquote(target_id)
        + " --status"
    )
    append_event(cfg, "workbench", "workbench_target_selected", details={
        "target_id": target_id,
        "target_label": target_label,
        "selected_at": now,
        "headless_command": headless,
    })
    return {
        "target_id": target_id,
        "target_label": target_label,
        "selected": True,
        "headless_command": headless,
    }


def select_workbench_target_record(selector, targets, *, current_target_id=""):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("target selector is required")
    records = [rec for rec in targets or [] if isinstance(rec, dict)]
    current = str(current_target_id or "").strip()
    if text.lower() == "current":
        if not current:
            raise ValueError("no current target filter is selected")
        for rec in records:
            if str(rec.get("target_id") or "") == current:
                return {"scope": "target", "target": rec}
        raise ValueError(f"target not found: {current}")
    if text.lower() in ("all", "*"):
        return {"scope": "all", "target": {}}
    if text.isdigit():
        idx = int(text) - 1
        if idx < 0 or idx >= len(records):
            raise ValueError(f"target number out of range: {text}")
        return {"scope": "target", "target": records[idx]}
    lower = text.lower()
    for rec in records:
        target_id = str(rec.get("target_id") or "")
        label = str(rec.get("label") or rec.get("target_label") or "")
        aliases = [str(item) for item in rec.get("aliases") or []]
        if text == target_id or lower == label.lower() or lower in [alias.lower() for alias in aliases]:
            return {"scope": "target", "target": rec}
    raise ValueError(f"target not found: {text}")


def print_workbench_target_selector(targets, *, current_target_id="", empty_message="no known targets"):
    records = [rec for rec in targets or [] if isinstance(rec, dict)]
    current = str(current_target_id or "").strip()
    if not records:
        print(empty_message)
        return
    for idx, rec in enumerate(records, 1):
        marker = "*" if str(rec.get("target_id") or "") == current else " "
        print(
            f"{idx}:{marker} {rec.get('target_id', '')} "
            f"label={rec.get('label', '') or '-'} "
            f"state={rec.get('connectivity_state', '') or '-'} "
            f"mailbox_pending={rec.get('mailbox_pending_work_count', 0)} "
            f"poll_overdue={'yes' if rec.get('poll_overdue') else 'no'} "
            f"last_seen={rec.get('last_seen', '') or rec.get('last_seen_at', '') or '-'}"
        )


def dispatch_legacy_target_filter_number(choice, cfg, *, input_func=None, snapshot_func=None):
    if str(choice or "").strip() != "16":
        return False
    unfiltered_cfg = dict(cfg)
    unfiltered_cfg.pop("_target_id_filter", None)
    unfiltered_cfg.pop("_target_label_filter", None)
    snap = snapshot_func(unfiltered_cfg) if snapshot_func else {}
    targets = snap.get("targets") or []
    current = configured_target_filter(cfg)
    print_workbench_target_selector(
        targets,
        current_target_id=current,
        empty_message="no known targets; use all/clear to remove any current filter",
    )
    selected_line = input_func("target number/id/label, or all to clear> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        try:
            rec = set_workbench_target_filter(cfg, selected, targets=targets)
            if rec.get("selected"):
                print(f"selected target {rec.get('target_id', '')} label={rec.get('target_label', '') or '-'}")
            else:
                print("target filter cleared")
        except ValueError as exc:
            print(exc)
    return True
