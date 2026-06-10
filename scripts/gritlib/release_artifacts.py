"""Release artifact workflow helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, record_count_by_nested_key,
    records_by_key,
)
from gritlib.session_state import read_json_file
import gritlib.release_contexts as release_contexts_module
import gritlib.release_artifact_workflow_actions as release_artifact_workflow_actions_module
import gritlib.release_staging as release_staging
from gritlib.staged_files import stage_file


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


def print_release_summary(doc):
    doc = doc or {}
    release_state = doc.get("release_state") or {}
    summary = doc.get("summary") or {}
    release = doc.get("release") or {}
    print("Release summary:")
    print(
        f"  present={'yes' if release_state.get('present') else 'no'} "
        f"valid={'yes' if release_state.get('valid') else 'no'} "
        f"release_json_valid={'yes' if release_state.get('release_json_valid') else 'no'} "
        f"release_index_valid={'yes' if release_state.get('release_index_valid') else 'no'}"
    )
    print(
        f"  detection_source={release_state.get('detection_source', '') or '-'} "
        f"detection_reason={release_state.get('detection_reason', '') or '-'} "
        f"explicit_release_dir={'yes' if release_state.get('explicit_release_dir') else 'no'} "
        f"markers={release_state.get('release_marker_count', 0)}"
    )
    print(
        f"  artifacts={summary.get('release_artifact_count', len(release.get('artifacts') or []))} "
        f"devices={summary.get('release_device_count', len(release.get('devices') or []))} "
        f"tuples={summary.get('release_tuple_count', len(release.get('tuples') or []))} "
        f"total_size={summary.get('release_artifact_total_size', (release.get('artifact_stats') or {}).get('total_size', 0))}"
    )
    print(
        "  release artifact modules: "
        f"total={summary.get('release_artifact_workflow_action_count', 0)} "
        f"available={summary.get('release_artifact_workflow_action_available_count', 0)} "
        f"stage={summary.get('release_artifact_workflow_action_writes_staged_files_count', 0)} "
        f"enter_runnable={summary.get('release_artifact_workflow_action_can_run_from_curses_enter_count', 0)} "
        f"selectors={format_counts(summary.get('release_artifact_workflow_action_selector_kind_counts') or {})}"
    )
    if release_state.get("release_dir") or release.get("release_dir"):
        print(f"  release_dir: {release_state.get('release_dir') or release.get('release_dir', '')}")
    if release_state.get("release_name") or release.get("release_name"):
        print(f"  release_name: {release_state.get('release_name') or release.get('release_name', '')}")
    release_license = release.get("release_license") or {}
    if release_license:
        print(
            f"  license: project={release_license.get('project_license', '') or '-'} "
            f"gplv2_compatible={'yes' if release_license.get('combined_gplv2_compatible') else 'no'} "
            f"valid={'yes' if release_license.get('valid') else 'no'} "
            f"notices={release_license.get('notice_count', 0)} "
            f"missing_notices={release_license.get('missing_notice_count', 0)}"
        )
        print(
            "  corresponding_source: "
            f"required={'yes' if release_license.get('corresponding_source_required') else 'no'} "
            f"status={release_license.get('corresponding_source_status', '') or '-'} "
            f"release_inputs={release_license.get('corresponding_source_release_input_count', 0)} "
            f"reconstruction_inputs={release_license.get('corresponding_source_reconstruction_input_count', 0)} "
            f"package_license_audit={'yes' if release_license.get('corresponding_source_requires_package_license_audit') else 'no'}"
        )
        print(
            "  license_evidence: "
            f"verified_at={release_license.get('license_evidence_verified_at', '') or '-'} "
            f"sources={release_license.get('license_evidence_source_count', 0)}"
        )
    for error in release_state.get("errors") or []:
        print(f"  error: {error}")


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


def _release_license_notice_state(release_dir):
    notice_files = [
        rel for rel in RELEASE_LICENSE_NOTICE_FILES if (release_dir / rel).is_file()
    ]
    missing_notice_files = [
        rel for rel in RELEASE_LICENSE_NOTICE_FILES if rel not in notice_files
    ]
    return notice_files, missing_notice_files


def _release_license_base_record(release_dir, policy_rel, policy_path):
    notice_files, missing_notice_files = _release_license_notice_state(release_dir)
    return {
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


def _release_license_policy_sections(policy):
    project = policy.get("project") if isinstance(policy.get("project"), dict) else {}
    compatibility = policy.get("compatibility") if isinstance(policy.get("compatibility"), dict) else {}
    license_evidence = policy.get("license_evidence") if isinstance(policy.get("license_evidence"), dict) else {}
    artifact_distribution = policy.get("artifact_distribution") if isinstance(policy.get("artifact_distribution"), dict) else {}
    corresponding_source = artifact_distribution.get("corresponding_source_strategy") if isinstance(artifact_distribution.get("corresponding_source_strategy"), dict) else {}
    return project, compatibility, license_evidence, corresponding_source


def _release_license_policy_items(policy, license_evidence, corresponding_source):
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
    return (
        components,
        evidence_sources,
        corresponding_source_release_inputs,
        corresponding_source_reconstruction_inputs,
    )


def _release_license_policy_fields(policy):
    project, compatibility, license_evidence, corresponding_source = (
        _release_license_policy_sections(policy)
    )
    (
        components,
        evidence_sources,
        corresponding_source_release_inputs,
        corresponding_source_reconstruction_inputs,
    ) = _release_license_policy_items(policy, license_evidence, corresponding_source)
    return {
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
    }


def release_license_record(release_dir):
    release_dir = Path(release_dir)
    policy_rel = "manifests/license-policy.json"
    policy_path = release_dir / policy_rel
    rec = _release_license_base_record(release_dir, policy_rel, policy_path)
    if not policy_path.is_file():
        return rec
    policy = read_json_file(policy_path, {})
    if not isinstance(policy, dict):
        return rec
    rec.update(_release_license_policy_fields(policy))
    return rec

def _release_state_paths(cfg):
    cfg = cfg or {}
    explicit_release_dir = bool(cfg.get("release_dir"))
    here = Path(str(cfg.get("release_dir") or Path.cwd()))
    return {
        "explicit_release_dir": explicit_release_dir,
        "here": here,
        "release_json": here / "release.json",
        "release_index": here / "release-index.json",
        "bin_dir": here / "bin",
        "scripts_dir": here / "scripts",
    }


def _release_state_base_record(paths):
    here = paths["here"]
    release_json = paths["release_json"]
    release_index = paths["release_index"]
    return {
        "release_dir": str(here),
        "release_json": str(release_json),
        "release_index": str(release_index),
        "detection_source": "explicit" if paths["explicit_release_dir"] else "auto",
        "detection_reason": "",
        "explicit_release_dir": paths["explicit_release_dir"],
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


def _apply_release_marker_state(rec, paths):
    rec["release_json_exists"] = paths["release_json"].is_file()
    rec["release_index_exists"] = paths["release_index"].is_file()
    rec["bin_dir_exists"] = paths["bin_dir"].is_dir()
    rec["scripts_dir_exists"] = paths["scripts_dir"].is_dir()
    release_markers = []
    if rec["release_json_exists"]:
        release_markers.append("release.json")
    if rec["release_index_exists"]:
        release_markers.append("release-index.json")
    if rec["bin_dir_exists"] and rec["scripts_dir_exists"]:
        release_markers.append("bin+scripts")
    rec["release_marker_count"] = len(release_markers)
    rec["present"] = bool(paths["explicit_release_dir"] or release_markers)
    if paths["explicit_release_dir"]:
        rec["detection_reason"] = "explicit-release-dir"
    elif release_markers:
        rec["detection_reason"] = ",".join(release_markers)
    else:
        rec["detection_reason"] = "no-release-markers"


def _read_release_state_json_docs(rec, paths):
    release_doc = {}
    index_doc = {}
    if not rec["release_json_exists"]:
        rec["errors"].append("release.json is missing")
    else:
        try:
            release_doc = json.loads(paths["release_json"].read_text(encoding="utf-8"))
            if isinstance(release_doc, dict):
                rec["release_json_valid"] = True
                rec["release_name"] = str(release_doc.get("release_name", ""))
            else:
                rec["errors"].append("release.json is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            rec["errors"].append(f"release.json: {exc}")
    if rec["release_index_exists"]:
        try:
            index_doc = json.loads(paths["release_index"].read_text(encoding="utf-8"))
            if isinstance(index_doc, dict):
                rec["release_index_valid"] = True
            else:
                rec["errors"].append("release-index.json is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            rec["errors"].append(f"release-index.json: {exc}")
    return release_doc, index_doc


def _apply_release_directory_errors(rec):
    if not rec["bin_dir_exists"]:
        rec["errors"].append("bin directory is missing")
    if not rec["scripts_dir_exists"]:
        rec["errors"].append("scripts directory is missing")


def _apply_release_context_state(rec, release):
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


def _apply_release_doc_counts(rec, release_doc, index_doc):
    if rec["release_index_valid"]:
        rec["artifact_count"] = len(index_doc.get("artifacts") or [])
        rec["device_count"] = len(index_doc.get("devices") or [])
        rec["tuple_count"] = len(index_doc.get("tuples") or [])
    elif rec["release_json_valid"]:
        layout = release_doc.get("layout") or {}
        if isinstance(layout, dict):
            rec["device_count"] = len(layout.get("devices") or {})
            rec["tuple_count"] = len(layout.get("tuples") or {})


def _apply_release_state_validity(rec):
    rec["valid"] = bool(
        rec["release_json_valid"] and
        rec["bin_dir_exists"] and
        rec["scripts_dir_exists"] and
        (not rec["release_index_exists"] or rec["release_index_valid"])
    )


def release_state_record(cfg=None, release=None):
    paths = _release_state_paths(cfg)
    rec = _release_state_base_record(paths)
    release = release or {}
    _apply_release_marker_state(rec, paths)
    if not rec["present"]:
        return rec
    release_doc, index_doc = _read_release_state_json_docs(rec, paths)
    _apply_release_directory_errors(rec)
    if release:
        _apply_release_context_state(rec, release)
    else:
        _apply_release_doc_counts(rec, release_doc, index_doc)
    _apply_release_state_validity(rec)
    return rec

def release_state_status(cfg=None, release=None):
    state_record = release_state_record(cfg, release)
    state_records = [state_record]
    state_index_maps = {
        "release_state_records_by_release_dir": records_by_key(
            state_records, "release_dir"
        ),
        "release_state_records_by_present": records_by_key(state_records, "present"),
        "release_state_records_by_valid": records_by_key(state_records, "valid"),
        "release_state_records_by_detection_source": records_by_key(
            state_records, "detection_source"
        ),
        "release_state_records_by_detection_reason": records_by_key(
            state_records, "detection_reason"
        ),
        "release_state_records_by_explicit_release_dir": records_by_key(
            state_records, "explicit_release_dir"
        ),
        "release_state_records_by_marker_count": records_by_key(
            state_records, "release_marker_count"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def release_status_context(cfg=None, release=None):
    cfg = cfg or {}
    release = release if release is not None else release_context(cfg)
    release_status = release_state_status(cfg, release)
    actions = release_artifact_workflow_actions_module.release_artifact_workflow_action_records(
        cfg, release
    )
    return {
        "release": release,
        "state_record": release_status["state_record"],
        "state_records": release_status["state_records"],
        "state_index_maps": release_status["state_index_maps"],
        "workflow_actions": actions,
        "workflow_action_index_maps": release_artifact_workflow_actions_module.release_artifact_workflow_action_indexes(
            actions
        ),
        "summary": release_status_summary(
            release,
            release_status["state_record"],
            release_status["state_records"],
        ),
    }


def _sum_record_key(records, key):
    total = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        total += int_value(rec.get(key, 0))
    return total


def _release_state_summary(release_state, release_state_records):
    return {
        "release_present": bool(release_state.get("present", False)),
        "release_valid": bool(release_state.get("valid", False)),
        "release_json_valid": bool(release_state.get("release_json_valid", False)),
        "release_index_valid": bool(release_state.get("release_index_valid", False)),
        "release_detection_source": release_state.get("detection_source", ""),
        "release_detection_reason": release_state.get("detection_reason", ""),
        "release_explicit_release_dir": bool(
            release_state.get("explicit_release_dir", False)
        ),
        "release_marker_count": release_state.get("release_marker_count", 0),
        "release_state_record_count": len(release_state_records),
    }


def _release_artifact_inventory_summary(release, artifact_stats, devices, tuples, artifacts):
    return {
        "release_artifact_count": len(artifacts),
        "release_artifact_total_size": artifact_stats.get("total_size", 0),
        "release_device_count": len(devices),
        "release_tuple_count": len(tuples),
        "release_device_artifact_reference_count": _sum_record_key(
            devices, "artifact_count"
        ),
        "release_tuple_artifact_reference_count": _sum_record_key(
            tuples, "artifact_count"
        ),
        "release_device_tuple_path_counts": record_count_by_key(devices, "tuple_path"),
        "release_device_artifact_counts": {
            key: len(value)
            for key, value in (release.get("devices_by_artifact") or {}).items()
        },
        "release_tuple_artifact_counts": {
            key: len(value)
            for key, value in (release.get("tuples_by_artifact") or {}).items()
        },
        "release_artifact_compatibility_counts": (
            artifact_stats.get("by_compatibility") or {}
        ),
        "release_artifact_payload_preset_counts": (
            artifact_stats.get("by_payload_preset") or {}
        ),
        "release_artifact_source_counts": artifact_stats.get("by_source") or {},
        "release_artifact_tuple_path_counts": record_count_by_key(
            artifacts, "tuple_path"
        ),
        "release_artifact_tool_counts": artifact_stats.get("by_tool") or {},
        "release_artifact_device_alias_counts": (
            artifact_stats.get("by_device_alias") or {}
        ),
        "release_artifact_feature_counts": artifact_stats.get("by_feature") or {},
        "release_artifact_tool_payload_preset_combo_count": len(
            release.get("artifacts_by_tool_payload_preset") or {}
        ),
        "release_artifact_device_payload_preset_combo_count": len(
            release.get("artifacts_by_device_payload_preset") or {}
        ),
        "release_artifact_feature_payload_preset_combo_count": len(
            release.get("artifacts_by_feature_payload_preset") or {}
        ),
        "release_artifact_tuple_payload_preset_combo_count": len(
            release.get("artifacts_by_tuple_payload_preset") or {}
        ),
    }


def _release_artifact_provider_summary(artifact_stats):
    return {
        "release_artifact_provider_tool_counts": (
            artifact_stats.get("by_provider_tool") or {}
        ),
        "release_artifact_provider_status_counts": (
            artifact_stats.get("by_provider_status") or {}
        ),
        "release_artifact_doom_wad_filename_counts": (
            artifact_stats.get("by_doom_wad_filename") or {}
        ),
        "release_artifact_doom_wad_sha256_counts": (
            artifact_stats.get("by_doom_wad_sha256") or {}
        ),
        "release_artifact_command_queue_enabled_counts": (
            artifact_stats.get("by_command_queue_enabled") or {}
        ),
        "release_artifact_command_queue_execution_supported_counts": (
            artifact_stats.get("by_command_queue_execution_supported") or {}
        ),
        "release_artifact_command_queue_operator_supplied_command_execution_counts": (
            artifact_stats.get("by_command_queue_operator_supplied_command_execution")
            or {}
        ),
        "release_artifact_doom_wad_count": artifact_stats.get("doom_wad_count", 0),
    }


def _release_license_summary(release_license, license_records):
    return {
        "release_license_count": len(license_records),
        "release_license_valid_count": sum(
            1 for rec in license_records if isinstance(rec, dict) and rec.get("valid")
        ),
        "release_license_notice_count": release_license.get("notice_count", 0),
        "release_license_missing_notice_count": release_license.get(
            "missing_notice_count", 0
        ),
        "release_license_evidence_source_count": release_license.get(
            "license_evidence_source_count", 0
        ),
        "release_license_evidence_verified_at": release_license.get(
            "license_evidence_verified_at", ""
        ),
        "release_project_license_counts": record_count_by_key(
            license_records, "project_license"
        ),
        "release_combined_gplv2_compatible_counts": record_count_by_key(
            license_records, "combined_gplv2_compatible"
        ),
        "release_corresponding_source_required_counts": record_count_by_key(
            license_records, "corresponding_source_required"
        ),
        "release_corresponding_source_status_counts": record_count_by_key(
            license_records, "corresponding_source_status"
        ),
        "release_package_license_audit_counts": record_count_by_key(
            license_records, "corresponding_source_requires_package_license_audit"
        ),
    }


def _release_recommendation_summary(recommendations):
    return {
        "release_recommendation_count": len(recommendations),
        "release_recommendation_scope_counts": record_count_by_key(
            recommendations, "scope"
        ),
        "release_recommendation_payload_preset_counts": record_count_by_key(
            recommendations, "payload_preset"
        ),
        "release_recommendation_compatibility_counts": record_count_by_nested_key(
            recommendations, "compatibility", "label"
        ),
    }


def release_status_summary(release=None, release_state=None, release_state_records=None):
    release = release or {}
    release_state = release_state or {}
    release_state_records = release_state_records or []
    artifact_stats = release.get("artifact_stats") or {}
    release_license = release.get("release_license") or {}
    license_records = release.get("release_license_records") or []
    devices = release.get("devices") or []
    tuples = release.get("tuples") or []
    artifacts = release.get("artifacts") or []
    recommendations = release.get("recommendation_records") or []
    return {
        **_release_state_summary(release_state, release_state_records),
        **_release_artifact_inventory_summary(
            release,
            artifact_stats,
            devices,
            tuples,
            artifacts,
        ),
        **_release_artifact_provider_summary(artifact_stats),
        **_release_license_summary(release_license, license_records),
        **_release_recommendation_summary(recommendations),
    }


def release_context(cfg=None):
    return release_contexts_module.release_context(
        cfg,
        release_license_record_func=release_license_record,
        release_recommendations_func=release_recommendations,
        release_recommendation_records_func=release_recommendation_records,
    )


def release_context_for_dir(path):
    return release_context({"release_dir": str(path)})


def release_discovery_candidates(cfg=None):
    return release_contexts_module.release_discovery_candidates(cfg)


def discover_release_context(cfg=None):
    return release_contexts_module.discover_release_context(
        cfg,
        release_context_func=release_context,
        release_context_for_dir_func=release_context_for_dir,
        release_discovery_candidates_func=release_discovery_candidates,
        release_state_record_func=release_state_record,
    )


def artifact_compatibility_lines(artifact):
    compatibility = artifact.get("compatibility") or {}
    label = compatibility.get("label") or ""
    lines = []
    if label:
        lines.append(f"compatibility: {label}")
    for reason in compatibility.get("reasons") or []:
        lines.append(f"compatibility_reason: {reason}")
    if compatibility.get("note"):
        lines.append(f"compatibility_note: {compatibility.get('note')}")
    return lines


def artifact_provider_status_lines(artifact):
    lines = []
    for tool, status in sorted((artifact.get("tool_provider_status") or {}).items()):
        if not isinstance(status, dict):
            continue
        overall = status.get("overall") or status.get("status") or "unknown"
        lines.append(f"provider_status_{tool}: {overall}")
    return lines


def artifact_doom_wad_lines(artifact):
    lines = []
    for wad in artifact.get("doom_wads") or []:
        if not isinstance(wad, dict):
            continue
        filename = wad.get("filename")
        if not filename:
            continue
        lines.append(f"doom_wad: {filename} size={wad.get('size', '')} sha256={wad.get('sha256', '')}")
    return lines


def release_recommendation_lines(release, limit=10):
    lines = []
    records = release.get("recommendation_records") or []
    for rec in records[:limit]:
        artifact = rec.get("artifact") or rec.get("artifact_name") or ""
        compat = (rec.get("compatibility") or {}).get("label") or ""
        suffix = f" compatibility={compat}" if compat else ""
        preset = rec.get("payload_preset") or ""
        preset_text = f" preset={preset}" if preset else ""
        lines.append(f"{rec.get('scope', '')}:{rec.get('key', '')} -> {artifact}{preset_text}{suffix}")
    if records and len(records) > limit:
        lines.append(f"... {len(records) - limit} more recommendation(s)")
    return lines


def release_nav_records(release, release_devices, release_tuples, limit=5):
    return release_staging.release_nav_records(
        release,
        release_devices,
        release_tuples,
        limit=limit,
    )


def stage_release_artifact(cfg, artifact_name):
    return release_staging.stage_release_artifact(
        cfg,
        artifact_name,
        release_context_func=release_context,
        stage_file_func=stage_file,
    )


def stage_release_nav_item(cfg, rec):
    return release_staging.stage_release_nav_item(
        cfg,
        rec,
        stage_release_artifact_func=stage_release_artifact,
    )


def stage_release_selection(cfg, selector):
    return release_staging.stage_release_selection(
        cfg,
        selector,
        release_context_func=release_context,
        release_nav_records_func=release_nav_records,
        stage_release_artifact_func=stage_release_artifact,
    )


def release_artifact_workflow_action_records(cfg, release, default_config="local/server-config.json"):
    return release_artifact_workflow_actions_module.release_artifact_workflow_action_records(
        cfg, release, default_config
    )


def release_artifact_workflow_action_indexes(records):
    return release_artifact_workflow_actions_module.release_artifact_workflow_action_indexes(records)


def release_artifact_workflow_action_summary(records):
    return release_artifact_workflow_actions_module.release_artifact_workflow_action_summary(records)


def release_artifact_workflow_action_status_summary(records):
    return release_artifact_workflow_actions_module.release_artifact_workflow_action_status_summary(records)
