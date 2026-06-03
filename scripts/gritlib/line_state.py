"""Line-console state display helpers."""


def line_action_state_text(rec):
    state = str((rec or {}).get("operator_action_state") or "")
    labels = {
        "ready": "ready",
        "needs-input": "needs input",
        "already-empty": "empty",
        "already-stopped": "stopped",
        "already-running": "running",
        "missing-target": "needs target",
        "not-supported": "unavailable",
        "disabled": "disabled",
    }
    return labels.get(state, state.replace("-", " ") or "-")
