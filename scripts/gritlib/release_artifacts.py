"""Release artifact workflow helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import record_count_by_key, records_by_key


def release_state_record(cfg=None, release=None):
    cfg = cfg or {}
    explicit_release_dir = bool(cfg.get("release_dir"))
    here = Path(str(cfg.get("release_dir") or Path.cwd()))
    release_json = here / "release.json"
    release_index = here / "release-index.json"
    bin_dir = here / "bin"
    scripts_dir = here / "scripts"
    rec = {
        "release_dir": str(here),
        "release_json": str(release_json),
        "release_index": str(release_index),
        "detection_source": "explicit" if explicit_release_dir else "auto",
        "detection_reason": "",
        "explicit_release_dir": explicit_release_dir,
        "release_marker_count": 0,
        "present": False,
        "valid": False,
        "release_json_exists": False,
        "release_json_valid": False,
        "release_index_exists": False,
        "release_index_valid": False,
        "bin_dir_exists": False,
        "scripts_dir_exists": False,
        "release_name": "",
        "artifact_count": 0,
        "device_count": 0,
        "tuple_count": 0,
        "errors": [],
    }
    release = release or {}
    rec["release_json_exists"] = release_json.is_file()
    rec["release_index_exists"] = release_index.is_file()
    rec["bin_dir_exists"] = bin_dir.is_dir()
    rec["scripts_dir_exists"] = scripts_dir.is_dir()
    release_markers = []
    if rec["release_json_exists"]:
        release_markers.append("release.json")
    if rec["release_index_exists"]:
        release_markers.append("release-index.json")
    if rec["bin_dir_exists"] and rec["scripts_dir_exists"]:
        release_markers.append("bin+scripts")
    rec["release_marker_count"] = len(release_markers)
    rec["present"] = bool(
        explicit_release_dir or
        release_markers
    )
    if explicit_release_dir:
        rec["detection_reason"] = "explicit-release-dir"
    elif release_markers:
        rec["detection_reason"] = ",".join(release_markers)
    else:
        rec["detection_reason"] = "no-release-markers"
    if not rec["present"]:
        return rec
    release_doc = {}
    index_doc = {}
    if not rec["release_json_exists"]:
        rec["errors"].append("release.json is missing")
    else:
        try:
            release_doc = json.loads(release_json.read_text(encoding="utf-8"))
            if isinstance(release_doc, dict):
                rec["release_json_valid"] = True
                rec["release_name"] = str(release_doc.get("release_name", ""))
            else:
                rec["errors"].append("release.json is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            rec["errors"].append(f"release.json: {exc}")
    if rec["release_index_exists"]:
        try:
            index_doc = json.loads(release_index.read_text(encoding="utf-8"))
            if isinstance(index_doc, dict):
                rec["release_index_valid"] = True
            else:
                rec["errors"].append("release-index.json is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            rec["errors"].append(f"release-index.json: {exc}")
    if not rec["bin_dir_exists"]:
        rec["errors"].append("bin directory is missing")
    if not rec["scripts_dir_exists"]:
        rec["errors"].append("scripts directory is missing")
    if release:
        rec["release_name"] = str(release.get("release_name") or rec["release_name"])
        rec["artifact_count"] = len(release.get("artifacts") or [])
        rec["device_count"] = len(release.get("devices") or [])
        rec["tuple_count"] = len(release.get("tuples") or [])
        if release.get("release_index"):
            rec["release_index"] = str(release.get("release_index"))
            rec["release_index_exists"] = True
        release_license = release.get("release_license") or {}
        rec["release_license_exists"] = bool(release_license.get("exists", False))
        rec["release_license_valid"] = bool(release_license.get("valid", False))
        rec["project_license"] = release_license.get("project_license", "")
        rec["combined_gplv2_compatible"] = bool(release_license.get("combined_gplv2_compatible", False))
        rec["license_notice_count"] = release_license.get("notice_count", 0)
        rec["license_missing_notice_count"] = release_license.get("missing_notice_count", 0)
    elif rec["release_index_valid"]:
        rec["artifact_count"] = len(index_doc.get("artifacts") or [])
        rec["device_count"] = len(index_doc.get("devices") or [])
        rec["tuple_count"] = len(index_doc.get("tuples") or [])
    elif rec["release_json_valid"]:
        layout = release_doc.get("layout") or {}
        if isinstance(layout, dict):
            rec["device_count"] = len(layout.get("devices") or {})
            rec["tuple_count"] = len(layout.get("tuples") or {})
    rec["valid"] = bool(
        rec["release_json_valid"] and
        rec["bin_dir_exists"] and
        rec["scripts_dir_exists"] and
        (not rec["release_index_exists"] or rec["release_index_valid"])
    )
    return rec


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
