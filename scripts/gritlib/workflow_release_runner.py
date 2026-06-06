"""Release artifact workflow action runner for grit-console."""

import subprocess

from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command
from gritlib.release_staging import stage_release_selection
from gritlib.workflow_actions import select_workflow_action


def _print_workflow_action_header(label, rec_id, command="", headless_command="", show_headless=False, show_command=True):
    print(f"{label} workflow action: {rec_id}")
    if show_headless and headless_command:
        print(f"headless_command={headless_command}")
    if show_command and command:
        print(f"command={command}")


def _release_artifact_workflow_context(rec):
    return {
        "rec_id": str(rec.get("id") or ""),
        "action_id": str(rec.get("action_id") or ""),
        "selector": str(rec.get("selector") or ""),
        "command": str(rec.get("command") or rec.get("headless_command") or ""),
        "run_command": str(rec.get("run_command") or ""),
    }


def _release_artifact_headless_command(context):
    return context["run_command"] or context["command"]


def _append_release_artifact_workflow_selected_event(cfg, rec, context, dry_run=False):
    append_event(cfg, "workbench", "release_artifact_workflow_action_selected", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "workflow": rec.get("workflow", ""),
        "category": rec.get("category", ""),
        "selector": context["selector"],
        "selector_kind": rec.get("selector_kind", ""),
        "release_dir": rec.get("release_dir", ""),
        "release_name": rec.get("release_name", ""),
        "release_path": rec.get("release_path", ""),
        "artifact_name": rec.get("artifact_name", ""),
        "recommendation_id": rec.get("recommendation_id", ""),
        "operator_action_state": rec.get("operator_action_state", ""),
        "operator_action_reason": rec.get("operator_action_reason", ""),
        "dry_run": bool(dry_run),
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
    })


def _run_release_artifact_workflow_dry_run(cfg, context):
    print("dry_run=yes")
    append_event(cfg, "workbench", "release_artifact_workflow_action_dry_run", details={
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "selector": context["selector"],
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
    })
    return 0


def _append_release_artifact_workflow_completed_event(cfg, rec, context, rc, extra_details=None):
    details = {
        "id": context["rec_id"],
        "action_id": context["action_id"],
        "selector": context["selector"],
    }
    details.update(extra_details or {})
    details.update({
        "headless_command": _release_artifact_headless_command(context),
        "command": context["command"],
        "returncode": rc,
    })
    append_event(cfg, "workbench", "release_artifact_workflow_action_completed", details=details)


def _run_release_artifact_self_test(cfg, rec, context):
    release_dir = str(rec.get("release_dir") or cfg.get("release_dir") or ".")
    cmd = ["scripts/lib/release-self-test", "--release-dir", release_dir, "--json"]
    result = subprocess.run(cmd, text=True)
    rc = int(result.returncode)
    _append_release_artifact_workflow_completed_event(cfg, rec, context, rc)
    return rc


def _run_release_artifact_stage_selection(cfg, rec, context):
    selector_value = context["selector"]
    if not selector_value:
        raise ValueError(f"release artifact workflow action is missing selector: {context['rec_id']}")
    staged = stage_release_selection(cfg, selector_value)
    print(f"staged {staged['request_name']} <- {staged['source_path']}")
    print(f"release_path={staged.get('release_path', '')} tuple_path={staged.get('tuple_path', '')} payload_preset={staged.get('payload_preset', '')}")
    print(render_fetch_command(staged["request_name"], cfg))
    _append_release_artifact_workflow_completed_event(cfg, rec, context, 0, {
        "selector_kind": rec.get("selector_kind", ""),
        "release_dir": rec.get("release_dir", ""),
        "release_name": rec.get("release_name", ""),
        "release_path": staged.get("release_path", ""),
        "artifact_name": staged.get("release_artifact_name", ""),
        "recommendation_id": rec.get("recommendation_id", ""),
        "request_name": staged.get("request_name", ""),
        "source_path": staged.get("source_path", ""),
        "sha256": staged.get("sha256", ""),
    })
    return 0


def _run_release_artifact_workflow_side_effect(cfg, rec, context, print_status_func):
    action_id = context["action_id"]
    if action_id == "inspect-release":
        return print_status_func(cfg, json_output=False)
    if action_id == "self-test-release":
        return _run_release_artifact_self_test(cfg, rec, context)
    if action_id in ("stage-artifact", "stage-recommendation"):
        return _run_release_artifact_stage_selection(cfg, rec, context)
    raise ValueError(f"unsupported release artifact workflow action: {action_id}")


def run_release_artifact_workflow_action(cfg, selector, dry_run=False, print_status_func=None):
    if print_status_func is None:
        raise ValueError("release artifact workflow runner requires print_status_func")
    snap = workbench_snapshot(cfg)
    rec = select_workflow_action(
        snap.get("release_artifact_workflow_actions") or [],
        selector,
        "release artifact",
        extra_keys=("selector", "release_path", "recommendation_id"),
    )
    context = _release_artifact_workflow_context(rec)
    _print_workflow_action_header(
        "release artifact",
        context["rec_id"],
        command=context["command"],
        headless_command=_release_artifact_headless_command(context),
    )
    _append_release_artifact_workflow_selected_event(cfg, rec, context, dry_run=dry_run)
    if dry_run:
        return _run_release_artifact_workflow_dry_run(cfg, context)
    return _run_release_artifact_workflow_side_effect(
        cfg,
        rec,
        context,
        print_status_func=print_status_func,
    )
