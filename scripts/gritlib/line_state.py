"""Line-console state display helpers."""


def line_action_state_text(rec):
    state = str((rec or {}).get("operator_action_state") or "")
    labels = {
        "ready": "ready",
        "background-ready": "ready as job",
        "confirm-required": "needs confirmation",
        "needs-input": "needs input",
        "already-empty": "empty",
        "already-stopped": "stopped",
        "already-running": "running",
        "missing-target": "needs target",
        "not-supported": "unavailable",
        "disabled": "disabled",
    }
    return labels.get(state, state.replace("-", " ") or "-")


def line_action_task_text(rec):
    rec = rec or {}
    label = str(rec.get("label") or "").strip()
    if not label:
        return ""
    identifiers = {
        str(rec.get("id") or "").strip().lower(),
        str(rec.get("action_id") or "").strip().lower(),
    }
    if label.lower() in identifiers:
        return ""
    return label
