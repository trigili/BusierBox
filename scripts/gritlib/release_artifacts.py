"""Release artifact workflow helpers for grit-console."""

from gritlib.record_utils import record_count_by_key, records_by_key


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
