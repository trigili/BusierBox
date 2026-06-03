"""Status index and health summary helpers for grit-console."""

import os
from pathlib import Path

from gritlib.command_copy import command_copy_path
from gritlib.command_queue import command_queue_path
from gritlib.event_log import EventLog
from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, records_by_bool,
    records_by_composite, records_by_key,
)
from gritlib.session_state import state_file_path
from gritlib.staged_files import staged_file_path
from gritlib.workbench_jobs import workbench_jobs_path


def operator_state_indexes(records):
    return {
        "operator_state_records_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "operator_state_records_by_kind": records_by_key(records, "kind"),
        "operator_state_records_by_status": records_by_key(records, "status"),
        "operator_state_records_by_exists": records_by_key(records, "exists"),
        "operator_state_records_by_valid": records_by_key(records, "valid"),
        "operator_state_records_by_unhealthy": records_by_key(records, "unhealthy"),
        "operator_state_records_by_severity": records_by_key(records, "severity"),
        "operator_state_records_by_remediation_class": records_by_key(records, "remediation_class"),
        "operator_state_records_by_requires_operator_action": records_by_key(records, "requires_operator_action"),
        "operator_state_records_by_path": {rec.get("path", ""): rec for rec in records or [] if rec.get("path")},
        "operator_state_records_by_kind_status": records_by_composite(records, ("kind", "status")),
    }


def print_activity_summary(summary):
    summary = summary or {}
    print(
        "Activity summary: "
        f"staged={summary.get('staged_count', 0)} "
        f"uploads={summary.get('upload_count', 0)} "
        f"fetches={summary.get('fetch_count', 0)} "
        f"targets={summary.get('target_count', 0)} "
        f"sessions={summary.get('session_count', 0)} "
        f"events={summary.get('event_count', 0)}"
    )
    print(
        "  session durations: "
        f"known={summary.get('session_duration_known_count', 0)} "
        f"total_sec={summary.get('session_total_duration_sec', 0)} "
        f"avg_sec={summary.get('session_average_duration_sec', 0)} "
        f"max_sec={summary.get('session_max_duration_sec', 0)}"
    )
    print(
        "  session logs: "
        f"with_logs={summary.get('sessions_with_session_logs_count', 0)} "
        f"exists={format_counts(summary.get('session_log_exists_counts') or {})} "
        f"bytes={summary.get('session_total_log_size', 0)} "
        f"lines={summary.get('session_total_log_line_count', 0)}"
    )
    print(
        "  latest: "
        f"staged={summary.get('latest_staged_at') or '-'} "
        f"upload={summary.get('latest_upload_at') or '-'} "
        f"fetch={summary.get('latest_fetch_at') or '-'} "
        f"target={summary.get('latest_target_seen_at') or '-'} "
        f"session={summary.get('latest_session_updated_at') or '-'}"
    )
    print(
        "  targets: "
        f"latest={summary.get('latest_target_id') or '-'} "
        f"confidence={format_counts(summary.get('target_identity_confidence_counts') or {})} "
        f"services={format_counts(summary.get('target_service_counts') or {})}"
    )
    print(
        "  target attribution: "
        f"with={summary.get('target_attribution_with_target_count', 0)} "
        f"without={summary.get('target_attribution_without_target_count', 0)} "
        f"uploads_without={summary.get('upload_without_target_count', 0)} "
        f"fetches_without={summary.get('fetch_without_target_count', 0)} "
        f"sessions_without={summary.get('session_without_target_count', 0)} "
        f"legacy_single_target={'yes' if summary.get('target_legacy_single_target_activity_present') else 'no'}"
    )
    print(
        "  service lifecycle: "
        f"actual={format_counts(summary.get('service_actual_counts') or {})} "
        f"configured={format_counts(summary.get('service_configured_counts') or {})} "
        f"stale={format_counts(summary.get('service_stale_counts') or {})} "
        f"errors={format_counts(summary.get('service_has_error_counts') or {})} "
        f"session_logs={format_counts(summary.get('service_session_log_exists_counts') or {})} "
        f"process_logs={format_counts(summary.get('service_process_log_exists_counts') or {})} "
        f"stopped_reasons={format_counts(summary.get('service_stopped_reason_counts') or {})}"
    )


def print_api_resource_summary(doc, limit=8):
    api = doc.get("api") or {}
    resources = doc.get("api_resources") or []
    warning_indexed = [
        rec for rec in resources
        if isinstance(rec, dict) and rec.get("has_warning_indexes")
    ]
    print(
        "API resources: "
        f"schema={api.get('schema', '')} "
        f"resources={api.get('resource_count', len(resources))} "
        f"collections_key={api.get('collections_key', '')} "
        f"resources_key={api.get('resources_key', '')} "
        f"warning_indexed={len(warning_indexed)}"
    )
    for rec in resources[:limit]:
        print(
            f"  {rec.get('name', '')}: "
            f"records={rec.get('records_key', '')} "
            f"count={rec.get('count', 0)} "
            f"primary={rec.get('primary_key', '') or '-'} "
            f"summary={rec.get('summary_key', '') or '-'} "
            f"indexes={len(rec.get('indexes') or [])}"
        )
    if len(resources) > limit:
        print(f"  ... {len(resources) - limit} more resource(s)")


def print_operator_state_records(doc):
    print("Operator state:")
    operator_state_records = sorted(doc.get("operator_state_records") or [], key=lambda rec: rec.get("name", ""))
    if operator_state_records:
        for rec in operator_state_records:
            exists = "yes" if rec.get("exists") else "no"
            valid = "yes" if rec.get("valid") else "no"
            line = (
                f"  {rec.get('name', '')}: status={rec.get('status', '')} "
                f"kind={rec.get('kind', '')} exists={exists} valid={valid} "
                f"records={rec.get('record_count', 0)} path={rec.get('path', '')}"
            )
            if rec.get("error"):
                line = f"{line} error={rec.get('error', '')}"
            print(line)
    else:
        print("  none")


def operator_state_record(name, kind, path, exists, valid, record_count=0, error="", extra=None):
    if exists and not valid:
        status = "invalid"
    elif not exists:
        status = "missing"
    elif error:
        status = "error"
    else:
        status = "ok"
    requires_operator_action = status in ("invalid", "error")
    severity = "error" if requires_operator_action else ("warning" if status == "missing" else "info")
    remediation_class = "repair_operator_state" if requires_operator_action else ("initialize_operator_state" if status == "missing" else "none")
    suggested_action = ""
    if status == "invalid":
        suggested_action = "inspect, repair, archive, or remove the invalid operator state file"
    elif status == "error":
        suggested_action = "inspect operator state file permissions and filesystem errors"
    elif status == "missing":
        suggested_action = "state will be created when the related operator workflow is used"
    rec = {
        "name": name,
        "kind": kind,
        "path": str(path),
        "exists": bool(exists),
        "valid": bool(valid),
        "status": status,
        "unhealthy": status in ("missing", "invalid", "error"),
        "severity": severity,
        "remediation_class": remediation_class,
        "requires_operator_action": requires_operator_action,
        "suggested_action": suggested_action,
        "record_count": int(record_count or 0),
        "error": str(error or ""),
    }
    if extra:
        rec.update(extra)
    return rec


def operator_state_records(cfg, server_state, staged_files_state, command_queue_state,
                           command_copy, workbench_jobs_state, event_log_state,
                           session_root_state):
    return [
        operator_state_record(
            "server_state", "json-state", server_state.get("path", state_file_path(cfg)),
            server_state.get("exists", False), server_state.get("valid", False),
            server_state.get("service_count", 0), server_state.get("error", ""),
            {"schema": server_state.get("schema"), "session_count": server_state.get("session_count", 0)},
        ),
        operator_state_record(
            "staged_files", "json-state", staged_files_state.get("path", staged_file_path(cfg)),
            staged_files_state.get("exists", False), staged_files_state.get("valid", False),
            staged_files_state.get("staged_count", 0), staged_files_state.get("error", ""),
            {"schema": staged_files_state.get("schema")},
        ),
        operator_state_record(
            "command_queue", "json-state", command_queue_state.get("path", command_queue_path(cfg)),
            command_queue_state.get("exists", False), command_queue_state.get("valid", False),
            command_queue_state.get("command_count", 0), command_queue_state.get("error", ""),
            {"schema": command_queue_state.get("schema")},
        ),
        operator_state_record(
            "command_copy", "text-state", command_copy.get("path", command_copy_path(cfg)),
            command_copy.get("exists", False), command_copy.get("readable", False),
            1 if command_copy.get("has_command") else 0, command_copy.get("error", ""),
            {"readable": command_copy.get("readable", False), "has_command": command_copy.get("has_command", False)},
        ),
        operator_state_record(
            "workbench_jobs", "json-state", workbench_jobs_state.get("path", workbench_jobs_path(cfg)),
            workbench_jobs_state.get("exists", False), workbench_jobs_state.get("valid", False),
            workbench_jobs_state.get("job_count", 0), workbench_jobs_state.get("error", ""),
            {"schema": workbench_jobs_state.get("schema")},
        ),
        operator_state_record(
            "event_log", "jsonl-log", event_log_state.get("path", EventLog(cfg).path),
            event_log_state.get("exists", False), event_log_state.get("valid", False),
            event_log_state.get("event_count", 0), event_log_state.get("error", ""),
            {"invalid_count": event_log_state.get("invalid_count", 0), "tail_count": event_log_state.get("tail_count", 0)},
        ),
        operator_state_record(
            "session_root", "directory", session_root_state.get("path", cfg.get("session_root", "local/sessions")),
            session_root_state.get("exists", False), session_root_state.get("exists", False),
            session_root_state.get("recent_session_count", 0), session_root_state.get("error", ""),
            {"recent_session_ids": session_root_state.get("recent_session_ids") or []},
        ),
    ]


def operator_state_health_counts(records):
    counts = record_count_by_key(records, "status")
    unhealthy = sum(int(counts.get(key, 0) or 0) for key in ("missing", "invalid", "error"))
    return {
        "ok": int(counts.get("ok", 0) or 0),
        "missing": int(counts.get("missing", 0) or 0),
        "invalid": int(counts.get("invalid", 0) or 0),
        "error": int(counts.get("error", 0) or 0),
        "unhealthy": unhealthy,
        "status_counts": counts,
        "severity_counts": record_count_by_key(records, "severity"),
        "remediation_class_counts": record_count_by_key(records, "remediation_class"),
        "requires_operator_action_counts": record_count_by_key(records, "requires_operator_action"),
    }


def status_path_records(paths):
    records = {}
    dir_keys = {"operator_session_dir", "session_root"}
    for name, raw_path in (paths or {}).items():
        path_text = str(raw_path or "")
        rec = {
            "name": name,
            "path": path_text,
            "expected_kind": "dir" if name in dir_keys else "file",
            "expected_kind_matches": False,
            "expected_kind_mismatch": False,
            "exists": False,
            "is_file": False,
            "is_dir": False,
            "parent": "",
            "parent_exists": False,
            "readable": False,
            "writable": False,
        }
        if not path_text:
            records[name] = rec
            continue
        path = Path(path_text)
        parent = path.parent
        rec["parent"] = str(parent)
        try:
            rec["exists"] = path.exists()
            rec["is_file"] = path.is_file()
            rec["is_dir"] = path.is_dir()
            rec["parent_exists"] = parent.exists()
            rec["readable"] = bool(rec["exists"] and os.access(path, os.R_OK))
            if rec["exists"]:
                rec["writable"] = os.access(path, os.W_OK)
            else:
                rec["writable"] = bool(rec["parent_exists"] and os.access(parent, os.W_OK))
            if rec["exists"]:
                if rec["expected_kind"] == "dir":
                    rec["expected_kind_matches"] = bool(rec["is_dir"])
                elif rec["expected_kind"] == "file":
                    rec["expected_kind_matches"] = bool(rec["is_file"])
                else:
                    rec["expected_kind_matches"] = True
                rec["expected_kind_mismatch"] = not rec["expected_kind_matches"]
        except OSError as exc:
            rec["error"] = str(exc)
        records[name] = rec
    return records


def status_path_summary(records):
    missing = 0
    parent_missing = 0
    not_writable = 0
    kind_mismatch = 0
    for rec in (records or {}).values():
        if not rec.get("exists"):
            missing += 1
        if not rec.get("parent_exists"):
            parent_missing += 1
        if not rec.get("writable"):
            not_writable += 1
        if rec.get("expected_kind_mismatch"):
            kind_mismatch += 1
    return {
        "path_status_count": len(records or {}),
        "path_missing_count": missing,
        "path_parent_missing_count": parent_missing,
        "path_not_writable_count": not_writable,
        "path_kind_mismatch_count": kind_mismatch,
    }


def status_path_record_list(records):
    return list((records or {}).values())


def status_path_record_indexes(records):
    return {
        "path_status_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "path_status_by_path": records_by_key(records, "path"),
        "path_status_by_expected_kind": records_by_key(records, "expected_kind"),
        "path_status_by_exists": records_by_bool(records, "exists"),
        "path_status_by_parent_exists": records_by_bool(records, "parent_exists"),
        "path_status_by_writable": records_by_bool(records, "writable"),
        "path_status_by_expected_kind_mismatch": records_by_bool(records, "expected_kind_mismatch"),
    }


def browser_path_status(path_text, expected_kind="file"):
    rec = {
        "path": str(path_text or ""),
        "expected_kind": expected_kind,
        "expected_kind_matches": False,
        "expected_kind_mismatch": False,
        "exists": False,
        "is_file": False,
        "is_dir": False,
        "parent": "",
        "parent_exists": False,
        "readable": False,
        "writable": False,
        "error": "",
    }
    if not rec["path"]:
        return rec
    path = Path(rec["path"])
    parent = path.parent
    rec["parent"] = str(parent)
    try:
        rec["exists"] = path.exists()
        rec["is_file"] = path.is_file()
        rec["is_dir"] = path.is_dir()
        rec["parent_exists"] = parent.exists()
        rec["readable"] = bool(rec["exists"] and os.access(path, os.R_OK))
        if rec["exists"]:
            rec["writable"] = os.access(path, os.W_OK)
        else:
            rec["writable"] = bool(rec["parent_exists"] and os.access(parent, os.W_OK))
        if rec["exists"]:
            if rec["expected_kind"] == "dir":
                rec["expected_kind_matches"] = bool(rec["is_dir"])
            elif rec["expected_kind"] == "file":
                rec["expected_kind_matches"] = bool(rec["is_file"])
            else:
                rec["expected_kind_matches"] = True
            rec["expected_kind_mismatch"] = not rec["expected_kind_matches"]
    except OSError as exc:
        rec["error"] = str(exc)
    return rec


def add_browser_path(records, kind, label, path_text, expected_kind="file", source_id="", description="", metadata=None):
    path_text = str(path_text or "")
    if not path_text:
        return
    rec = {
        "id": f"{kind}:{len(records) + 1}",
        "kind": kind,
        "label": str(label or kind),
        "path": path_text,
        "source_id": str(source_id or ""),
        "description": str(description or ""),
    }
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if value not in (None, ""):
                rec[key] = value
    rec.update(browser_path_status(path_text, expected_kind=expected_kind))
    records.append(rec)


def operator_browser_path_records(cfg, paths, staged_records, uploads, fetches, sessions, release):
    records = []
    path_kinds = {
        "operator_session_dir": "operator-dir",
        "state_file": "server-state",
        "staged_files": "staged-ledger",
        "command_queue_file": "command-queue-ledger",
        "command_copy_file": "command-copy",
        "workbench_jobs_file": "workbench-jobs-ledger",
        "event_log": "operator-event-log",
        "session_root": "session-root",
        "tls_cert": "tls-cert",
        "tls_key": "tls-key",
    }
    for name, path_text in (paths or {}).items():
        add_browser_path(
            records,
            path_kinds.get(name, "operator-path"),
            name,
            path_text,
            expected_kind="dir" if name in ("operator_session_dir", "session_root") else "file",
            source_id=name,
        )
    for rec in staged_records or []:
        request = rec.get("request_name") or rec.get("name") or ""
        metadata = {
            "stage_kind": rec.get("stage_kind") or "file",
            "release_path": rec.get("release_path"),
            "tuple_path": rec.get("tuple_path"),
            "payload_preset": rec.get("payload_preset"),
            "selected_by_recommendation": rec.get("selected_by_recommendation"),
            "compatibility": rec.get("compatibility"),
        }
        add_browser_path(
            records,
            "staged-source",
            request,
            rec.get("source_path", ""),
            source_id=request,
            description=str(rec.get("stage_kind") or "file"),
            metadata=metadata,
        )
    for rec in uploads or []:
        filename = rec.get("filename") or rec.get("stored_path") or "upload"
        add_browser_path(records, "upload-metadata", filename, rec.get("metadata_path") or rec.get("_metadata_path", ""), source_id=rec.get("session_id", ""))
        add_browser_path(records, "upload-stored", filename, rec.get("stored_path", ""), source_id=rec.get("session_id", ""))
        add_browser_path(records, "upload-session", filename, rec.get("session_path", ""), expected_kind="dir", source_id=rec.get("session_id", ""))
    for rec in fetches or []:
        request = rec.get("request_name") or rec.get("source_path") or "fetch"
        add_browser_path(records, "fetch-source", request, rec.get("source_path", ""), source_id=rec.get("session_id", ""))
        add_browser_path(records, "fetch-metadata", request, rec.get("metadata_path") or rec.get("_metadata_path", ""), source_id=rec.get("session_id", ""))
        add_browser_path(records, "fetch-session", request, rec.get("session_path", ""), expected_kind="dir", source_id=rec.get("session_id", ""))
    for rec in sessions or []:
        session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
        add_browser_path(records, "session-dir", session_id, rec.get("path", ""), expected_kind="dir", source_id=session_id)
        add_browser_path(records, "session-metadata", session_id, rec.get("metadata_path", ""), source_id=session_id)
        add_browser_path(records, "session-event-log", session_id, rec.get("event_log", ""), source_id=session_id)
    if release:
        add_browser_path(records, "release-dir", release.get("release_name", "release"), release.get("release_dir", ""), expected_kind="dir")
        add_browser_path(records, "release-json", release.get("release_name", "release"), release.get("release_json", ""))
        add_browser_path(records, "release-index", release.get("release_name", "release"), release.get("release_index", ""))
        for rec in release.get("artifacts") or []:
            add_browser_path(
                records,
                "release-artifact",
                rec.get("name", "artifact"),
                rec.get("path", ""),
                source_id=rec.get("release_path", ""),
                metadata={
                    "release_path": rec.get("release_path"),
                    "tuple_path": rec.get("tuple_path"),
                    "payload_preset": rec.get("payload_preset"),
                    "compatibility": rec.get("compatibility"),
                },
            )
        artifacts_by_path = release.get("artifacts_by_release_path") or {}
        for rec in release.get("recommendation_records") or []:
            artifact_key = rec.get("artifact") or ""
            artifact = artifacts_by_path.get(artifact_key) or {}
            add_browser_path(
                records,
                "release-recommendation-artifact",
                rec.get("id", "recommendation"),
                artifact.get("path") or artifact_key,
                source_id=rec.get("id", ""),
                description=f"{rec.get('scope', '')}:{rec.get('key', '')}",
                metadata={
                    "release_path": artifact.get("release_path") or artifact_key,
                    "tuple_path": artifact.get("tuple_path") or rec.get("tuple_path"),
                    "payload_preset": artifact.get("payload_preset") or rec.get("payload_preset"),
                    "compatibility": artifact.get("compatibility") or rec.get("compatibility"),
                },
            )
        for rec in release.get("devices") or []:
            add_browser_path(records, "release-device-dir", rec.get("name", "device"), rec.get("path", ""), expected_kind="dir", source_id=rec.get("name", ""))
        for rec in release.get("tuples") or []:
            add_browser_path(records, "release-tuple-dir", rec.get("path", "tuple"), rec.get("filesystem_path", ""), expected_kind="dir", source_id=rec.get("path", ""))
    return records


def browser_path_indexes(records):
    by_kind = {}
    by_path = {}
    by_source_id = {}
    by_stage_kind = {}
    by_release_path = {}
    by_kind_source_id = {}
    by_exists = records_by_bool(records, "exists")
    by_readable = records_by_bool(records, "readable")
    by_writable = records_by_bool(records, "writable")
    by_expected_kind_mismatch = records_by_bool(records, "expected_kind_mismatch")
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        path = str(rec.get("path") or "")
        source_id = str(rec.get("source_id") or "")
        stage_kind = str(rec.get("stage_kind") or "")
        release_path = str(rec.get("release_path") or "")
        if kind:
            by_kind.setdefault(kind, []).append(rec)
        if path:
            by_path.setdefault(path, []).append(rec)
        if source_id:
            by_source_id.setdefault(source_id, []).append(rec)
        if stage_kind:
            by_stage_kind.setdefault(stage_kind, []).append(rec)
        if release_path:
            by_release_path.setdefault(release_path, []).append(rec)
        if kind and source_id:
            by_kind_source_id.setdefault(f"{kind}:{source_id}", []).append(rec)
    return (
        by_kind, by_path, by_source_id, by_stage_kind, by_release_path,
        by_kind_source_id, by_exists, by_readable, by_writable,
        by_expected_kind_mismatch,
    )


def browser_path_summary(records):
    exists_by_kind = {}
    missing_by_kind = {}
    readable_by_kind = {}
    writable_by_kind = {}
    kind_mismatch_by_kind = {}
    warning_by_kind = {}
    warning_by_type = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        if not kind:
            continue
        if rec.get("exists") is True:
            exists_by_kind[kind] = exists_by_kind.get(kind, 0) + 1
        else:
            missing_by_kind[kind] = missing_by_kind.get(kind, 0) + 1
        if rec.get("readable") is True:
            readable_by_kind[kind] = readable_by_kind.get(kind, 0) + 1
        if rec.get("writable") is True:
            writable_by_kind[kind] = writable_by_kind.get(kind, 0) + 1
        if rec.get("expected_kind_mismatch") is True:
            kind_mismatch_by_kind[kind] = kind_mismatch_by_kind.get(kind, 0) + 1
        warning_count = int(rec.get("warning_count") or 0)
        if warning_count:
            warning_by_kind[kind] = warning_by_kind.get(kind, 0) + warning_count
            for warning_type in rec.get("warning_types") or []:
                warning_type = str(warning_type or "")
                if warning_type:
                    warning_by_type[warning_type] = warning_by_type.get(warning_type, 0) + 1
    return {
        "total_count": len(records or []),
        "exists_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("exists") is True),
        "missing_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("exists") is not True),
        "readable_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("readable") is True),
        "writable_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("writable") is True),
        "kind_mismatch_count": sum(1 for rec in records or [] if isinstance(rec, dict) and rec.get("expected_kind_mismatch") is True),
        "warning_count": sum(int(rec.get("warning_count") or 0) for rec in records or [] if isinstance(rec, dict)),
        "by_kind": record_count_by_key(records, "kind"),
        "by_stage_kind": record_count_by_key(records, "stage_kind"),
        "by_release_path": record_count_by_key(records, "release_path"),
        "exists_by_kind": exists_by_kind,
        "missing_by_kind": missing_by_kind,
        "readable_by_kind": readable_by_kind,
        "writable_by_kind": writable_by_kind,
        "kind_mismatch_by_kind": kind_mismatch_by_kind,
        "warning_by_kind": warning_by_kind,
        "warning_by_type": warning_by_type,
    }


def api_collection_record(name, records, primary_key="", indexes=None, summary_key=""):
    index_names = sorted(indexes or [])
    warning_indexes = [
        item for item in index_names
        if item.endswith("_by_has_warnings") or item.endswith("_by_warning_type")
    ]
    return {
        "name": name,
        "count": len(records or []),
        "primary_key": primary_key,
        "count_summary_key": summary_key,
        "summary_key": summary_key,
        "indexes": index_names,
        "has_warning_indexes": bool(warning_indexes),
        "warning_indexes": warning_indexes,
    }


def api_resource_records(api_collections):
    record_locations = {
        "command_queue_commands": "command_queue.commands",
        "command_queue_modes": "command_queue_mode_records",
    }
    records = []
    for name in sorted(api_collections or {}):
        collection = api_collections.get(name) or {}
        records.append({
            "name": name,
            "records_key": record_locations.get(name, name),
            "collection_key": f"api_collections.{name}",
            "count": collection.get("count", 0),
            "primary_key": collection.get("primary_key", ""),
            "summary_key": collection.get("summary_key", ""),
            "count_summary_key": collection.get("count_summary_key", ""),
            "indexes": collection.get("indexes") or [],
            "has_warning_indexes": bool(collection.get("has_warning_indexes", False)),
            "warning_indexes": collection.get("warning_indexes") or [],
        })
    return records


def api_resource_record_indexes(records):
    return {
        "api_resources_by_name": {rec.get("name", ""): rec for rec in records or [] if rec.get("name")},
        "api_resources_by_records_key": records_by_key(records, "records_key"),
        "api_resources_by_summary_key": records_by_key(records, "summary_key"),
        "api_resources_by_primary_key": records_by_key(records, "primary_key"),
        "api_resources_by_has_warning_indexes": records_by_key(records, "has_warning_indexes"),
    }


def warning_health_indexes(records):
    by_has_warnings = {"yes": [], "no": []}
    by_warning_type = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        warning_count = int_value(rec.get("warning_count"))
        by_has_warnings["yes" if warning_count > 0 else "no"].append(rec)
        for warning_type in rec.get("warning_types") or []:
            warning_type = str(warning_type or "")
            if warning_type:
                by_warning_type.setdefault(warning_type, []).append(rec)
    return by_has_warnings, by_warning_type


def operator_network_status(ips):
    selected_local_ip = (ips or ["OPERATOR_IP"])[0]
    operator_network_records = [
        {
            "id": f"local-ip-{idx}",
            "kind": "local-ip",
            "ip": ip,
            "ordinal": idx,
            "selected": ip == selected_local_ip,
            "placeholder": ip == "OPERATOR_IP",
            "source": "detected" if ip != "OPERATOR_IP" else "placeholder",
            "usable_for_generated_commands": ip != "OPERATOR_IP",
        }
        for idx, ip in enumerate(ips or ["OPERATOR_IP"])
    ]
    operator_network_index_maps = {
        "operator_network_records_by_id": {rec["id"]: rec for rec in operator_network_records},
        "operator_network_records_by_kind": records_by_key(operator_network_records, "kind"),
        "operator_network_records_by_ip": records_by_key(operator_network_records, "ip"),
        "operator_network_records_by_selected": records_by_key(operator_network_records, "selected"),
        "operator_network_records_by_placeholder": records_by_key(operator_network_records, "placeholder"),
        "operator_network_records_by_source": records_by_key(operator_network_records, "source"),
        "operator_network_records_by_usable_for_generated_commands": records_by_key(
            operator_network_records, "usable_for_generated_commands"
        ),
    }
    selected_operator_network_record = next(
        (rec for rec in operator_network_records if rec.get("selected")),
        operator_network_records[0] if operator_network_records else {},
    )
    operator_network_state_record = {
        "id": "operator-network",
        "selected_ip": selected_local_ip,
        "selected_source": selected_operator_network_record.get("source", ""),
        "selected_placeholder": bool(selected_operator_network_record.get("placeholder", False)),
        "selected_usable_for_generated_commands": bool(
            selected_operator_network_record.get("usable_for_generated_commands", False)
        ),
        "record_count": len(operator_network_records),
        "detected_ip_count": len([rec for rec in operator_network_records if rec.get("source") == "detected"]),
        "placeholder_count": len([rec for rec in operator_network_records if rec.get("placeholder")]),
        "usable_for_generated_commands_count": len([
            rec for rec in operator_network_records
            if rec.get("usable_for_generated_commands")
        ]),
    }
    operator_network_state_record.update({
        "has_detected_ip": operator_network_state_record.get("detected_ip_count", 0) > 0,
        "uses_placeholder": bool(operator_network_state_record.get("selected_placeholder", False)),
        "has_generated_command_ip": bool(operator_network_state_record.get("selected_usable_for_generated_commands", False)),
        "has_multiple_ips": operator_network_state_record.get("record_count", 0) > 1,
    })
    operator_network_state_records = [operator_network_state_record]
    operator_network_state_index_maps = {
        "operator_network_state_records_by_id": {
            rec.get("id", ""): rec for rec in operator_network_state_records if rec.get("id")
        },
        "operator_network_state_records_by_selected_ip": records_by_key(operator_network_state_records, "selected_ip"),
        "operator_network_state_records_by_selected_source": records_by_key(operator_network_state_records, "selected_source"),
        "operator_network_state_records_by_selected_placeholder": records_by_key(
            operator_network_state_records, "selected_placeholder"
        ),
        "operator_network_state_records_by_has_detected_ip": records_by_key(operator_network_state_records, "has_detected_ip"),
        "operator_network_state_records_by_uses_placeholder": records_by_key(operator_network_state_records, "uses_placeholder"),
        "operator_network_state_records_by_has_generated_command_ip": records_by_key(
            operator_network_state_records, "has_generated_command_ip"
        ),
        "operator_network_state_records_by_has_multiple_ips": records_by_key(
            operator_network_state_records, "has_multiple_ips"
        ),
    }
    return {
        "selected_local_ip": selected_local_ip,
        "operator_network_records": operator_network_records,
        "operator_network_index_maps": operator_network_index_maps,
        "operator_network_state_record": operator_network_state_record,
        "operator_network_state_records": operator_network_state_records,
        "operator_network_state_index_maps": operator_network_state_index_maps,
    }
