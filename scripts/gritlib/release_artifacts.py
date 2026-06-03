"""Release artifact workflow helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.session_state import read_json_file


RELEASE_LICENSE_NOTICE_FILES = (
    "LICENSE.grit",
    "LICENSE",
    "NOTICE",
    "LICENSES/busybox.txt",
    "LICENSES/buildroot.txt",
    "LICENSES/doom-ascii.txt",
    "LICENSES/miniz.txt",
    "docs/licensing.md",
    "manifests/license-policy.json",
    "sources.lock.json",
    "manifests/sources.lock.json",
)


def release_artifact_compatibility_rank(rec):
    label = str((rec.get("compatibility") or {}).get("label") or "exact")
    return {"exact": 0, "likely": 1, "heuristic": 2, "unsafe": 3, "incompatible": 4}.get(label, 5)


def release_artifact_recommendation_key(rec):
    metadata_rank = 0 if rec.get("tuple_path") and rec.get("payload_preset") else 1
    return (
        metadata_rank,
        release_artifact_compatibility_rank(rec),
        str(rec.get("payload_preset") or ""),
        str(rec.get("release_path") or rec.get("path") or rec.get("name") or ""),
    )


def best_release_artifact(records):
    records = [rec for rec in (records or []) if isinstance(rec, dict)]
    if not records:
        return None
    return sorted(records, key=release_artifact_recommendation_key)[0]


def release_recommendations(devices, artifact_indexes):
    artifacts = artifact_indexes.get("artifacts") or []
    by_device = {}
    for device in devices or []:
        if not isinstance(device, dict):
            continue
        name = str(device.get("name") or "")
        if not name:
            continue
        refs = {str(item) for item in (device.get("artifacts") or []) if str(item)}
        ref_names = {Path(item).name for item in refs}
        tuple_path = str(device.get("tuple_path") or "")
        selected = best_release_artifact(
            rec for rec in artifacts
            if (str(rec.get("release_path") or "") in refs or
                str(rec.get("name") or "") in ref_names or
                (tuple_path and str(rec.get("tuple_path") or "") == tuple_path))
        )
        if selected:
            by_device[name] = selected

    return {
        "schema": 1,
        "selection_policy": [
            "lowest compatibility risk label",
            "payload preset name",
            "artifact path",
        ],
        "by_device": by_device,
        "by_tuple_path": {
            key: best_release_artifact(artifact_indexes["artifacts_by_tuple_path"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_tuple_path") or {})
        },
        "by_tool": {
            key: best_release_artifact(artifact_indexes["artifacts_by_tool"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_tool") or {})
        },
        "by_payload_preset": {
            key: best_release_artifact(artifact_indexes["artifacts_by_payload_preset"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_payload_preset") or {})
        },
        "by_feature": {
            key: best_release_artifact(artifact_indexes["artifacts_by_feature"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_feature") or {})
        },
        "by_tool_payload_preset": {
            key: best_release_artifact(artifact_indexes["artifacts_by_tool_payload_preset"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_tool_payload_preset") or {})
        },
        "by_device_payload_preset": {
            key: best_release_artifact(artifact_indexes["artifacts_by_device_payload_preset"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_device_payload_preset") or {})
        },
        "by_feature_payload_preset": {
            key: best_release_artifact(artifact_indexes["artifacts_by_feature_payload_preset"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_feature_payload_preset") or {})
        },
        "by_tuple_payload_preset": {
            key: best_release_artifact(artifact_indexes["artifacts_by_tuple_payload_preset"][key])
            for key in sorted(artifact_indexes.get("artifacts_by_tuple_payload_preset") or {})
        },
    }


def release_recommendation_records(recommendations):
    records = []
    for scope in (
        "by_device", "by_tuple_path", "by_tool", "by_payload_preset", "by_feature",
        "by_tool_payload_preset", "by_device_payload_preset",
        "by_feature_payload_preset", "by_tuple_payload_preset",
    ):
        for key, artifact in sorted((recommendations.get(scope) or {}).items()):
            if not isinstance(artifact, dict):
                continue
            records.append({
                "scope": scope,
                "key": key,
                "id": f"{scope}:{key}",
                "artifact": artifact.get("release_path") or artifact.get("path") or artifact.get("name") or "",
                "artifact_name": artifact.get("name") or "",
                "tuple_path": artifact.get("tuple_path") or "",
                "payload_preset": artifact.get("payload_preset") or "",
                "compatibility": artifact.get("compatibility") or {},
                "sha256": artifact.get("sha256") or "",
            })
    return records


def kernel_floor_from_release(release):
    release = str(release or "").strip().lower()
    if not release:
        return ""
    major = release.split(".", 1)[0]
    if major.isdigit():
        major_int = int(major)
        if major_int < 3:
            parts = release.split(".", 2)
            if len(parts) >= 2 and parts[1].isdigit():
                return f"{major_int}.{int(parts[1])}"
        if major_int == 3:
            return "3.x"
        if major_int == 4:
            return "4.x"
        return "current"
    return release


def normalized_probe_arch(arch, endian=""):
    arch = str(arch or "").strip().lower()
    endian = str(endian or "").strip().lower()
    if arch in {"x86-64", "amd64"}:
        return "x86_64"
    if arch in {"arm64"}:
        return "aarch64"
    if arch.startswith("armv7") or arch in {"armhf", "armv7l"}:
        return "armv7"
    if arch in {"mips"} and endian == "little":
        return "mipsel"
    if arch in {"mipsel"} and endian == "big":
        return "mips"
    return arch


def release_tuple_for_record(release, record):
    tuple_path = str(record.get("tuple_path") or "")
    if not tuple_path and str(record.get("scope") or "") in {"by_tuple_path", "by_tuple_payload_preset"}:
        tuple_path = str(record.get("key") or "").split(":", 1)[0]
    if not tuple_path:
        artifact = str(record.get("artifact") or "")
        artifact_rec = (release.get("artifacts_by_release_path") or {}).get(artifact) or {}
        tuple_path = str(artifact_rec.get("tuple_path") or "")
    return (release.get("tuples_by_path") or {}).get(tuple_path) or {}


def release_record_matches_probe(release, record, probe_arch, probe_kernel_floor):
    tuple_rec = release_tuple_for_record(release, record)
    tuple_info = tuple_rec.get("tuple") if isinstance(tuple_rec.get("tuple"), dict) else {}
    tuple_arch = normalized_probe_arch(tuple_info.get("arch") or "")
    tuple_kernel = str(tuple_info.get("kernel_floor") or "").strip().lower()
    if probe_arch and tuple_arch and probe_arch != tuple_arch:
        return False
    if probe_kernel_floor and tuple_kernel and tuple_kernel not in {"host", "current"}:
        if tuple_kernel != probe_kernel_floor:
            return False
    return True


def release_artifact_matches_probe(release, artifact, probe_arch, probe_kernel_floor):
    tuple_path = str(artifact.get("tuple_path") or "")
    tuple_rec = (release.get("tuples_by_path") or {}).get(tuple_path) or {}
    tuple_info = tuple_rec.get("tuple") if isinstance(tuple_rec.get("tuple"), dict) else {}
    tuple_arch = normalized_probe_arch(tuple_info.get("arch") or "")
    tuple_kernel = str(tuple_info.get("kernel_floor") or "").strip().lower()
    if not tuple_path or not artifact.get("payload_preset"):
        return False
    if probe_arch and tuple_arch and probe_arch != tuple_arch:
        return False
    if not probe_kernel_floor or not tuple_kernel or tuple_kernel in {"host"}:
        return True
    probe_floor = str(probe_kernel_floor or "").strip().lower()
    if probe_floor == tuple_kernel:
        return True
    if probe_floor == "current":
        return tuple_kernel in {"current", "4.x"}
    if probe_floor.endswith(".x"):
        try:
            probe_major = int(probe_floor.split(".", 1)[0])
            tuple_major = int(tuple_kernel.split(".", 1)[0])
        except (TypeError, ValueError):
            return False
        if probe_major >= 4:
            return tuple_kernel in {"current", "4.x"}
        return probe_major == tuple_major
    return False


def release_license_record(release_dir):
    release_dir = Path(release_dir)
    policy_rel = "manifests/license-policy.json"
    policy_path = release_dir / policy_rel
    notice_files = [rel for rel in RELEASE_LICENSE_NOTICE_FILES if (release_dir / rel).is_file()]
    missing_notice_files = [rel for rel in RELEASE_LICENSE_NOTICE_FILES if rel not in notice_files]
    rec = {
        "schema": 1,
        "path": str(policy_path),
        "license_policy_path": policy_rel,
        "exists": policy_path.is_file(),
        "valid": False,
        "project_license": "",
        "combined_gplv2_compatible": False,
        "preferred_combined_terms_with_busybox": "",
        "source_availability_required_for_distribution": False,
        "corresponding_source_required": False,
        "corresponding_source_status": "",
        "corresponding_source_summary": "",
        "corresponding_source_release_input_count": 0,
        "corresponding_source_reconstruction_input_count": 0,
        "corresponding_source_requires_package_license_audit": False,
        "corresponding_source_release_inputs": [],
        "corresponding_source_reconstruction_inputs": [],
        "component_count": 0,
        "components": [],
        "component_names": [],
        "component_licenses": {},
        "license_evidence_verified_at": "",
        "license_evidence_source_count": 0,
        "license_evidence_sources": [],
        "license_evidence_source_names": [],
        "license_evidence_source_licenses": {},
        "license_evidence_source_urls": {},
        "notice_count": len(notice_files),
        "notice_files": notice_files,
        "required_notice_files": list(RELEASE_LICENSE_NOTICE_FILES),
        "missing_notice_files": missing_notice_files,
        "missing_notice_count": len(missing_notice_files),
    }
    if not policy_path.is_file():
        return rec
    policy = read_json_file(policy_path, {})
    if not isinstance(policy, dict):
        return rec
    project = policy.get("project") if isinstance(policy.get("project"), dict) else {}
    compatibility = policy.get("compatibility") if isinstance(policy.get("compatibility"), dict) else {}
    license_evidence = policy.get("license_evidence") if isinstance(policy.get("license_evidence"), dict) else {}
    artifact_distribution = policy.get("artifact_distribution") if isinstance(policy.get("artifact_distribution"), dict) else {}
    corresponding_source = artifact_distribution.get("corresponding_source_strategy") if isinstance(artifact_distribution.get("corresponding_source_strategy"), dict) else {}
    components = [
        item for item in (policy.get("components") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    evidence_sources = [
        item for item in (license_evidence.get("sources") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    corresponding_source_release_inputs = [
        str(item) for item in (corresponding_source.get("release_bundle_inputs") or [])
    ]
    corresponding_source_reconstruction_inputs = [
        str(item) for item in (corresponding_source.get("source_reconstruction_inputs") or [])
    ]
    rec.update({
        "valid": True,
        "project_license": project.get("license", ""),
        "combined_gplv2_compatible": compatibility.get("combined_gplv2_compatible") is True,
        "preferred_combined_terms_with_busybox": compatibility.get("preferred_combined_terms_with_busybox", ""),
        "source_availability_required_for_distribution": compatibility.get("source_availability_required_for_distribution") is True,
        "corresponding_source_required": corresponding_source.get("status") == "required_for_distribution",
        "corresponding_source_status": str(corresponding_source.get("status") or ""),
        "corresponding_source_summary": str(corresponding_source.get("summary") or ""),
        "corresponding_source_release_input_count": len(corresponding_source_release_inputs),
        "corresponding_source_reconstruction_input_count": len(corresponding_source_reconstruction_inputs),
        "corresponding_source_requires_package_license_audit": corresponding_source.get("requires_package_license_audit") is True,
        "corresponding_source_release_inputs": corresponding_source_release_inputs,
        "corresponding_source_reconstruction_inputs": corresponding_source_reconstruction_inputs,
        "component_count": len(components),
        "components": components,
        "component_names": [str(item.get("name")) for item in components],
        "component_licenses": {
            str(item.get("name")): str(item.get("license") or "")
            for item in components
        },
        "license_evidence_verified_at": str(license_evidence.get("verified_at") or ""),
        "license_evidence_source_count": len(evidence_sources),
        "license_evidence_sources": evidence_sources,
        "license_evidence_source_names": [str(item.get("name")) for item in evidence_sources],
        "license_evidence_source_licenses": {
            str(item.get("name")): str(item.get("license") or "")
            for item in evidence_sources
        },
        "license_evidence_source_urls": {
            str(item.get("name")): str(item.get("url") or "")
            for item in evidence_sources
        },
    })
    return rec


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
