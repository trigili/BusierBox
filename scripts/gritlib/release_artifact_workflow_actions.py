"""Release artifact workflow action records for grit-console."""

from pathlib import Path

from gritlib.record_utils import record_count_by_key, records_by_key


def _release_shquote(value):
    text = str(value)
    if all(ch.isalnum() or ch in "._-/:=" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


def _release_artifact_workflow_context(cfg, release, default_config):
    config_path = str(cfg.get("_config_path", default_config))
    release_dir = str(release.get("release_dir") or cfg.get("release_dir") or ".")
    release_present = bool(release)
    release_valid = bool(release.get("valid", release_present))
    return {
        "base": "scripts/grit-console --config " + _release_shquote(config_path),
        "release_dir": release_dir,
        "release_name": str(release.get("release_name") or ""),
        "release_present": release_present,
        "release_valid": release_valid,
    }


def _release_artifact_release_workflow_actions(release, context):
    base = context["base"]
    release_dir = context["release_dir"]
    release_present = context["release_present"]
    release_valid = context["release_valid"]
    release_name = context["release_name"]
    return [
        {
            "id": "release:inspect-release",
            "action_id": "inspect-release",
            "category": "release",
            "workflow": "release-inspection",
            "label": "Inspect release bundle",
            "release_dir": release_dir,
            "release_name": release_name,
            "release_present": release_present,
            "release_valid": release_valid,
            "selector": "",
            "selector_kind": "release",
            "artifact_name": "",
            "release_path": "",
            "payload_preset": "",
            "compatibility_label": "",
            "command": base + " --status",
            "headless_command": base + " --status",
            "run_command": base + " --run-release-artifact-workflow-action release:inspect-release",
            "requires_input": False,
            "requires_confirmation": False,
            "writes_staged_files": False,
            "available": True,
            "operator_action_state": "ready",
            "operator_action_reason": "run-now",
            "can_run_from_curses_enter": False,
            "curses_enter_action": "use-action-11",
            "target_scoped": False,
            "tui_visible": True,
        },
        {
            "id": "release:self-test-release",
            "action_id": "self-test-release",
            "category": "release",
            "workflow": "release-validation",
            "label": "Run release self-test",
            "release_dir": release_dir,
            "release_name": release_name,
            "release_present": release_present,
            "release_valid": release_valid,
            "selector": "",
            "selector_kind": "release",
            "artifact_name": "",
            "release_path": "",
            "payload_preset": "",
            "compatibility_label": "",
            "command": "scripts/lib/release-self-test --release-dir " + _release_shquote(release_dir) + " --json",
            "headless_command": "scripts/lib/release-self-test --release-dir " + _release_shquote(release_dir) + " --json",
            "run_command": base + " --run-release-artifact-workflow-action release:self-test-release",
            "requires_input": False,
            "requires_confirmation": False,
            "writes_staged_files": False,
            "available": release_present,
            "operator_action_state": "ready" if release_present else "unavailable",
            "operator_action_reason": "run-now" if release_present else "release-not-present",
            "can_run_from_curses_enter": False,
            "curses_enter_action": "use-action-11",
            "target_scoped": False,
            "tui_visible": True,
        },
    ]


def _release_artifact_stage_workflow_actions(release, context):
    base = context["base"]
    release_dir = context["release_dir"]
    release_present = context["release_present"]
    release_valid = context["release_valid"]
    records = []
    for artifact in release.get("artifacts") or []:
        release_path = str(artifact.get("release_path") or artifact.get("name") or artifact.get("path") or "")
        compatibility = artifact.get("compatibility") if isinstance(artifact.get("compatibility"), dict) else {}
        artifact_name = str(artifact.get("name") or Path(str(artifact.get("path") or release_path)).name)
        selector = release_path or artifact_name
        records.append({
            "id": f"release-artifact:{release_path or artifact_name}:stage-artifact",
            "action_id": "stage-artifact",
            "category": "release-artifact",
            "workflow": "release-staging",
            "label": "Stage release artifact for deliver commands",
            "release_dir": release_dir,
            "release_name": str(release.get("release_name") or ""),
            "release_present": release_present,
            "release_valid": release_valid,
            "selector": selector,
            "selector_kind": "artifact",
            "artifact_name": artifact_name,
            "artifact_path": str(artifact.get("path") or ""),
            "release_path": release_path,
            "tuple_path": str(artifact.get("tuple_path") or ""),
            "payload_preset": str(artifact.get("payload_preset") or ""),
            "compatibility_label": str(compatibility.get("label") or artifact.get("compatibility_label") or ""),
            "sha256": str(artifact.get("sha256") or ""),
            "size": artifact.get("size", ""),
            "command": base + " --stage-release-artifact " + _release_shquote(selector),
            "headless_command": base + " --stage-release-artifact " + _release_shquote(selector),
            "run_command": base + " --run-release-artifact-workflow-action " + _release_shquote(f"release-artifact:{release_path or artifact_name}:stage-artifact"),
            "requires_input": False,
            "requires_confirmation": False,
            "writes_staged_files": True,
            "available": bool(selector),
            "operator_action_state": "ready" if selector else "unavailable",
            "operator_action_reason": "stage-for-fetch" if selector else "missing-selector",
            "can_run_from_curses_enter": True,
            "curses_enter_action": "stage-release-artifact",
            "target_scoped": False,
            "tui_visible": True,
        })
    return records


def _release_artifact_recommendation_workflow_actions(release, context):
    base = context["base"]
    release_dir = context["release_dir"]
    release_present = context["release_present"]
    release_valid = context["release_valid"]
    records = []
    for rec in release.get("recommendation_records") or []:
        rec_id = str(rec.get("id") or "")
        artifact_name = str(rec.get("artifact_name") or rec.get("artifact") or "")
        compatibility = rec.get("compatibility") if isinstance(rec.get("compatibility"), dict) else {}
        selector = rec_id or str(rec.get("artifact") or "")
        records.append({
            "id": f"release-recommendation:{rec_id or artifact_name}:stage-recommendation",
            "action_id": "stage-recommendation",
            "category": "release-recommendation",
            "workflow": "release-staging",
            "label": "Stage recommended release artifact for deliver commands",
            "release_dir": release_dir,
            "release_name": str(release.get("release_name") or ""),
            "release_present": release_present,
            "release_valid": release_valid,
            "selector": selector,
            "selector_kind": "recommendation",
            "recommendation_id": rec_id,
            "recommendation_scope": str(rec.get("scope") or ""),
            "recommendation_key": str(rec.get("key") or ""),
            "artifact_name": artifact_name,
            "release_path": str(rec.get("artifact") or ""),
            "payload_preset": str(rec.get("payload_preset") or ""),
            "compatibility_label": str(compatibility.get("label") or ""),
            "command": base + " --stage-release-artifact " + _release_shquote(selector),
            "headless_command": base + " --stage-release-artifact " + _release_shquote(selector),
            "run_command": base + " --run-release-artifact-workflow-action " + _release_shquote(f"release-recommendation:{rec_id or artifact_name}:stage-recommendation"),
            "requires_input": False,
            "requires_confirmation": False,
            "writes_staged_files": True,
            "available": bool(selector),
            "operator_action_state": "ready" if selector else "unavailable",
            "operator_action_reason": "stage-recommendation-for-fetch" if selector else "missing-selector",
            "can_run_from_curses_enter": True,
            "curses_enter_action": "stage-release-recommendation",
            "target_scoped": False,
            "tui_visible": True,
        })
    return records


def release_artifact_workflow_action_records(cfg, release, default_config="local/server-config.json"):
    release = release or {}
    context = _release_artifact_workflow_context(cfg, release, default_config)
    return (
        _release_artifact_release_workflow_actions(release, context)
        + _release_artifact_stage_workflow_actions(release, context)
        + _release_artifact_recommendation_workflow_actions(release, context)
    )


def release_artifact_workflow_action_indexes(records):
    return {
        "release_artifact_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "release_artifact_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "release_artifact_workflow_actions_by_category": records_by_key(records, "category"),
        "release_artifact_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "release_artifact_workflow_actions_by_selector_kind": records_by_key(records, "selector_kind"),
        "release_artifact_workflow_actions_by_release_dir": records_by_key(records, "release_dir"),
        "release_artifact_workflow_actions_by_release_name": records_by_key(records, "release_name"),
        "release_artifact_workflow_actions_by_release_present": records_by_key(records, "release_present"),
        "release_artifact_workflow_actions_by_release_valid": records_by_key(records, "release_valid"),
        "release_artifact_workflow_actions_by_artifact_name": records_by_key(records, "artifact_name"),
        "release_artifact_workflow_actions_by_release_path": records_by_key(records, "release_path"),
        "release_artifact_workflow_actions_by_payload_preset": records_by_key(records, "payload_preset"),
        "release_artifact_workflow_actions_by_compatibility_label": records_by_key(records, "compatibility_label"),
        "release_artifact_workflow_actions_by_recommendation_scope": records_by_key(records, "recommendation_scope"),
        "release_artifact_workflow_actions_by_writes_staged_files": records_by_key(records, "writes_staged_files"),
        "release_artifact_workflow_actions_by_available": records_by_key(records, "available"),
        "release_artifact_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "release_artifact_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "release_artifact_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "release_artifact_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "release_artifact_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "release_artifact_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def release_artifact_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "writes_staged_files_count": len([rec for rec in records or [] if rec.get("writes_staged_files") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "selector_kind_counts": record_count_by_key(records, "selector_kind"),
        "release_present_counts": record_count_by_key(records, "release_present"),
        "release_valid_counts": record_count_by_key(records, "release_valid"),
        "payload_preset_counts": record_count_by_key(records, "payload_preset"),
        "compatibility_label_counts": record_count_by_key(records, "compatibility_label"),
        "recommendation_scope_counts": record_count_by_key(records, "recommendation_scope"),
        "writes_staged_files_counts": record_count_by_key(records, "writes_staged_files"),
        "available_counts": record_count_by_key(records, "available"),
        "requires_input_counts": record_count_by_key(records, "requires_input"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def release_artifact_workflow_action_status_summary(records):
    summary = release_artifact_workflow_action_summary(records)
    return {
        "release_artifact_workflow_action_count": summary.get("total_count", 0),
        "release_artifact_workflow_action_available_count": summary.get("available_count", 0),
        "release_artifact_workflow_action_requires_input_count": summary.get("requires_input_count", 0),
        "release_artifact_workflow_action_requires_confirmation_count": summary.get("requires_confirmation_count", 0),
        "release_artifact_workflow_action_writes_staged_files_count": summary.get("writes_staged_files_count", 0),
        "release_artifact_workflow_action_can_run_from_curses_enter_count": summary.get("can_run_from_curses_enter_count", 0),
        "release_artifact_workflow_action_action_counts": summary.get("action_counts") or {},
        "release_artifact_workflow_action_category_counts": summary.get("category_counts") or {},
        "release_artifact_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "release_artifact_workflow_action_selector_kind_counts": summary.get("selector_kind_counts") or {},
        "release_artifact_workflow_action_release_present_counts": summary.get("release_present_counts") or {},
        "release_artifact_workflow_action_release_valid_counts": summary.get("release_valid_counts") or {},
        "release_artifact_workflow_action_payload_preset_counts": summary.get("payload_preset_counts") or {},
        "release_artifact_workflow_action_compatibility_label_counts": summary.get("compatibility_label_counts") or {},
        "release_artifact_workflow_action_recommendation_scope_counts": summary.get("recommendation_scope_counts") or {},
        "release_artifact_workflow_action_writes_staged_files_counts": summary.get("writes_staged_files_counts") or {},
        "release_artifact_workflow_action_available_counts": summary.get("available_counts") or {},
        "release_artifact_workflow_action_requires_input_counts": summary.get("requires_input_counts") or {},
        "release_artifact_workflow_action_requires_confirmation_counts": summary.get("requires_confirmation_counts") or {},
        "release_artifact_workflow_action_operator_action_state_counts": summary.get("operator_action_state_counts") or {},
        "release_artifact_workflow_action_operator_action_reason_counts": summary.get("operator_action_reason_counts") or {},
        "release_artifact_workflow_action_can_run_from_curses_enter_counts": summary.get("can_run_from_curses_enter_counts") or {},
        "release_artifact_workflow_action_curses_enter_action_counts": summary.get("curses_enter_action_counts") or {},
    }
