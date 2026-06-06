"""Target capability and compatibility report summary helpers."""

import json
from pathlib import Path


def capability_report_summary(metadata):
    stored_path = str((metadata or {}).get("stored_path") or "").strip()
    if not stored_path:
        return {}
    path = Path(stored_path)
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, dict):
        return {}
    checks = [
        item for item in (report.get("checks") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    observed = {
        "schema": 1,
        "kind": str((metadata or {}).get("upload_kind") or ""),
        "path": stored_path,
        "metadata_path": str((metadata or {}).get("metadata_path") or ""),
        "sha256": str((metadata or {}).get("sha256") or ""),
        "check_count": len(checks),
        "pass_count": int(summary.get("pass", 0) or 0),
        "fail_count": int(summary.get("fail", 0) or 0),
        "skipped_count": int(summary.get("skipped", 0) or 0),
        "capability_pass_count": int(summary.get("capability_pass", 0) or 0),
        "capability_fail_count": int(summary.get("capability_fail", 0) or 0),
        "operator_pass_count": int(summary.get("operator_pass", 0) or 0),
        "operator_fail_count": int(summary.get("operator_fail", 0) or 0),
        "operator_skipped_count": int(summary.get("operator_skipped", 0) or 0),
        "available": [],
        "unavailable": [],
        "skipped": [],
        "constraints": summary.get("constraints") if isinstance(summary.get("constraints"), dict) else {},
    }
    for item in checks:
        name = str(item.get("name") or "")
        if not name:
            continue
        if item.get("skipped") is True:
            observed["skipped"].append(name)
        elif item.get("ok") is True or item.get("available") is True:
            observed["available"].append(name)
        elif item.get("ok") is False or item.get("available") is False:
            observed["unavailable"].append(name)
    return observed


def compatibility_report_summary(metadata):
    stored_path = str((metadata or {}).get("stored_path") or "").strip()
    if not stored_path:
        return {}
    path = Path(stored_path)
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, dict):
        return {}
    selected = report.get("selected") if isinstance(report.get("selected"), dict) else {}
    compatibility = report.get("effective_compatibility")
    if not isinstance(compatibility, dict):
        compatibility = selected.get("effective_compatibility")
    if not isinstance(compatibility, dict):
        compatibility = report.get("compatibility")
    if not isinstance(compatibility, dict):
        compatibility = selected.get("compatibility")
    if not isinstance(compatibility, dict):
        return {}
    label = str(compatibility.get("label") or "")
    if not label:
        return {}
    baseline = str(compatibility.get("baseline_label") or ((selected.get("compatibility") or {}).get("label") if isinstance(selected.get("compatibility"), dict) else "") or "")
    return {
        "schema": 1,
        "kind": str((metadata or {}).get("upload_kind") or ""),
        "path": stored_path,
        "metadata_path": str((metadata or {}).get("metadata_path") or ""),
        "sha256": str((metadata or {}).get("sha256") or ""),
        "label": label,
        "baseline_label": baseline,
        "source": str(compatibility.get("source") or report.get("command") or ""),
        "reason_count": len(compatibility.get("reasons") or []),
        "reasons": [str(item) for item in (compatibility.get("reasons") or [])],
        "release_name": str(selected.get("release_name") or report.get("release_name") or ""),
        "artifact": str(selected.get("artifact") or selected.get("artifact_path") or report.get("artifact") or ""),
        "tuple_path": str(selected.get("tuple_path") or report.get("tuple_path") or ""),
        "payload_preset": str(selected.get("payload_preset") or report.get("payload_preset") or ""),
    }
