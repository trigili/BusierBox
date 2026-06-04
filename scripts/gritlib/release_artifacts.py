"""Release artifact workflow helpers for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import (
    format_counts, int_value, record_count_by_key, records_by_key,
    records_by_list_item, records_by_nested_key,
)
from gritlib.session_state import read_json_file
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
        "  artifact workflow actions: "
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
    actions = release_artifact_workflow_action_records(cfg, release)
    return {
        "release": release,
        "state_record": release_status["state_record"],
        "state_records": release_status["state_records"],
        "state_index_maps": release_status["state_index_maps"],
        "workflow_actions": actions,
        "workflow_action_index_maps": release_artifact_workflow_action_indexes(actions),
    }


def release_context(cfg=None):
    here = Path(str((cfg or {}).get("release_dir") or Path.cwd()))
    release_json = here / "release.json"
    if release_json.is_file() and (here / "bin").is_dir() and (here / "scripts").is_dir():
        try:
            release = json.loads(release_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(release, dict):
            return {}
        license_record = release_license_record(here)
        artifacts = []
        for root_name in ("bin", "dist"):
            root = here / root_name
            if root.is_dir():
                for path in sorted(root.iterdir()):
                    if path.is_file() and not path.name.endswith(".sha256"):
                        artifacts.append({
                            "name": path.name,
                            "path": str(path),
                            "request_name": path.name,
                            "size": path.stat().st_size,
                            "source": root_name,
                        })
        index = read_json_file(here / "release-index.json", {})
        if isinstance(index, dict):
            for row in index.get("artifacts") or []:
                artifact = row.get("artifact") or row.get("tuple_artifact")
                if not artifact:
                    continue
                tuple_artifact = row.get("tuple_artifact") or ""
                path = here / artifact
                rec = {
                    "name": Path(artifact).name,
                    "path": str(path),
                    "request_name": Path(artifact).name,
                    "size": path.stat().st_size if path.is_file() else row.get("size", 0),
                    "source": "release-index",
                    "release_path": artifact,
                    "tuple_artifact": tuple_artifact,
                    "tuple_artifact_path": str(here / tuple_artifact) if tuple_artifact else "",
                    "tuple_path": row.get("tuple_path", ""),
                    "payload_preset": row.get("payload_preset", ""),
                    "sha256": row.get("sha256", ""),
                    "tools": row.get("tools") or [],
                    "features": row.get("features") or [],
                    "compatibility": row.get("compatibility") or {},
                    "tool_provider_status": row.get("tool_provider_status") or {},
                    "doom_wads": row.get("doom_wads") or [],
                    "release_license": license_record,
                    "project_license": license_record.get("project_license", ""),
                    "combined_gplv2_compatible": bool(license_record.get("combined_gplv2_compatible")),
                }
                existing_paths = [item.get("path") for item in artifacts]
                if rec["path"] in existing_paths:
                    artifacts[existing_paths.index(rec["path"])].update(rec)
                else:
                    artifacts.append(rec)
        devices = []
        tuples = []
        layout = release.get("layout") if isinstance(release, dict) else {}
        if isinstance(index, dict):
            devices_source = index.get("devices") or (layout or {}).get("devices") or {}
            tuples_source = index.get("tuples") or (layout or {}).get("tuples") or {}
        else:
            devices_source = (layout or {}).get("devices") or {}
            tuples_source = (layout or {}).get("tuples") or {}
        def enrich_release_artifact_refs(names):
            refs = [str(item) for item in (names or []) if str(item)]
            return {
                "artifacts": refs,
                "artifact_count": len(refs),
                "artifact_names": [Path(item).name for item in refs],
                "artifact_paths": [str(here / item) for item in refs],
            }
        for name, rec in sorted((devices_source or {}).items()):
            if isinstance(rec, dict):
                row = {"name": name, "tuple_path": rec.get("tuple_path", "")}
                row.update(enrich_release_artifact_refs(rec.get("artifacts") or []))
                device_dir = here / "devices" / name
                if device_dir.exists():
                    row["path"] = str(device_dir)
                devices.append(row)
        for name, rec in sorted((tuples_source or {}).items()):
            if isinstance(rec, dict):
                row = {"path": name, "tuple": rec.get("tuple") or {}}
                row.update(enrich_release_artifact_refs(rec.get("artifacts") or []))
                tuple_dir = here / name
                if tuple_dir.exists():
                    row["filesystem_path"] = str(tuple_dir)
                tuples.append(row)
        artifacts_by_release_path = {}
        artifacts_by_name = {}
        artifacts_by_sha256 = {}
        artifacts_by_payload_preset = {}
        artifacts_by_compatibility = {}
        artifacts_by_source = {}
        artifacts_by_tuple_path = {}
        artifacts_by_tool = {}
        artifacts_by_device_alias = {}
        artifacts_by_feature = {}
        artifacts_by_tool_payload_preset = {}
        artifacts_by_device_payload_preset = {}
        artifacts_by_feature_payload_preset = {}
        artifacts_by_tuple_payload_preset = {}
        artifacts_by_provider_tool = {}
        artifacts_by_provider_status = {}
        artifacts_by_doom_wad_filename = {}
        artifacts_by_doom_wad_sha256 = {}
        artifacts_by_command_queue_enabled = {}
        artifacts_by_command_queue_execution_supported = {}
        artifacts_by_command_queue_operator_supplied_command_execution = {}
        artifact_compatibility_counts = {}
        artifact_payload_preset_counts = {}
        artifact_source_counts = {}
        artifact_tool_counts = {}
        artifact_device_alias_counts = {}
        artifact_feature_counts = {}
        artifact_provider_tool_counts = {}
        artifact_provider_status_counts = {}
        artifact_doom_wad_filename_counts = {}
        artifact_doom_wad_sha256_counts = {}
        artifact_command_queue_enabled_counts = {}
        artifact_command_queue_execution_supported_counts = {}
        artifact_command_queue_operator_supplied_command_execution_counts = {}
        artifact_doom_wad_count = 0
        artifact_total_size = 0
        for rec in artifacts:
            try:
                artifact_total_size += int(rec.get("size", 0) or 0)
            except (TypeError, ValueError):
                pass
            key = rec.get("release_path") or rec.get("path") or rec.get("name")
            if key:
                artifacts_by_release_path[str(key)] = rec
            name = str(rec.get("name") or "")
            sha256 = str(rec.get("sha256") or "")
            payload_preset = str(rec.get("payload_preset") or "")
            source = str(rec.get("source") or "")
            tuple_path = str(rec.get("tuple_path") or "")
            compatibility_label = str((rec.get("compatibility") or {}).get("label") or "")
            command_queue = rec.get("command_queue") if isinstance(rec.get("command_queue"), dict) else {}
            mode_summary = command_queue.get("mode_summary") if isinstance(command_queue.get("mode_summary"), dict) else {}
            command_queue_enabled = "true" if command_queue.get("enabled") == "yes" or command_queue.get("enabled") is True else "false"
            command_queue_execution_supported = "true" if command_queue.get("execution_supported") is True or command_queue.get("executes_commands") is True else "false"
            command_queue_operator_supplied = (
                "true" if int_value(mode_summary.get("operator_supplied_command_execution_mode_count")) > 0 else "false"
            )
            if name:
                artifacts_by_name.setdefault(name, []).append(rec)
            if sha256:
                artifacts_by_sha256.setdefault(sha256, []).append(rec)
            if payload_preset:
                artifacts_by_payload_preset.setdefault(payload_preset, []).append(rec)
                artifact_payload_preset_counts[payload_preset] = artifact_payload_preset_counts.get(payload_preset, 0) + 1
            if tuple_path:
                artifacts_by_tuple_path.setdefault(tuple_path, []).append(rec)
            if tuple_path and payload_preset:
                artifacts_by_tuple_payload_preset.setdefault(f"{tuple_path}:{payload_preset}", []).append(rec)
            for device in devices or []:
                if not isinstance(device, dict):
                    continue
                alias = str(device.get("name") or "")
                if not alias:
                    continue
                refs = {str(item) for item in (device.get("artifacts") or []) if str(item)}
                ref_names = {Path(item).name for item in refs}
                device_tuple_path = str(device.get("tuple_path") or "")
                release_path = str(rec.get("release_path") or "")
                if not (
                    release_path in refs or
                    name in ref_names or
                    (device_tuple_path and tuple_path == device_tuple_path)
                ):
                    continue
                rec.setdefault("device_aliases", [])
                if alias not in rec["device_aliases"]:
                    rec["device_aliases"].append(alias)
                    artifact_device_alias_counts[alias] = artifact_device_alias_counts.get(alias, 0) + 1
                artifacts_by_device_alias.setdefault(alias, []).append(rec)
                if payload_preset:
                    artifacts_by_device_payload_preset.setdefault(f"{alias}:{payload_preset}", []).append(rec)
            if source:
                artifacts_by_source.setdefault(source, []).append(rec)
                artifact_source_counts[source] = artifact_source_counts.get(source, 0) + 1
            if compatibility_label:
                artifacts_by_compatibility.setdefault(compatibility_label, []).append(rec)
                artifact_compatibility_counts[compatibility_label] = artifact_compatibility_counts.get(compatibility_label, 0) + 1
            artifacts_by_command_queue_enabled.setdefault(command_queue_enabled, []).append(rec)
            artifact_command_queue_enabled_counts[command_queue_enabled] = artifact_command_queue_enabled_counts.get(command_queue_enabled, 0) + 1
            artifacts_by_command_queue_execution_supported.setdefault(command_queue_execution_supported, []).append(rec)
            artifact_command_queue_execution_supported_counts[command_queue_execution_supported] = artifact_command_queue_execution_supported_counts.get(command_queue_execution_supported, 0) + 1
            artifacts_by_command_queue_operator_supplied_command_execution.setdefault(command_queue_operator_supplied, []).append(rec)
            artifact_command_queue_operator_supplied_command_execution_counts[command_queue_operator_supplied] = artifact_command_queue_operator_supplied_command_execution_counts.get(command_queue_operator_supplied, 0) + 1
            for tool in rec.get("tools") or []:
                tool_name = str(tool)
                if tool_name:
                    artifacts_by_tool.setdefault(tool_name, []).append(rec)
                    artifact_tool_counts[tool_name] = artifact_tool_counts.get(tool_name, 0) + 1
                    if payload_preset:
                        artifacts_by_tool_payload_preset.setdefault(f"{tool_name}:{payload_preset}", []).append(rec)
            seen_features = set()
            for feature in rec.get("features") or []:
                feature_name = str(feature)
                if feature_name and feature_name not in seen_features:
                    seen_features.add(feature_name)
                    artifacts_by_feature.setdefault(feature_name, []).append(rec)
                    artifact_feature_counts[feature_name] = artifact_feature_counts.get(feature_name, 0) + 1
                    if payload_preset:
                        artifacts_by_feature_payload_preset.setdefault(f"{feature_name}:{payload_preset}", []).append(rec)
            for provider_tool, provider_status in (rec.get("tool_provider_status") or {}).items():
                if not isinstance(provider_status, dict):
                    continue
                provider_tool = str(provider_tool)
                overall = str(provider_status.get("overall") or provider_status.get("status") or "unknown")
                if provider_tool:
                    artifacts_by_provider_tool.setdefault(provider_tool, []).append(rec)
                    artifact_provider_tool_counts[provider_tool] = artifact_provider_tool_counts.get(provider_tool, 0) + 1
                    status_key = f"{provider_tool}:{overall}"
                    artifacts_by_provider_status.setdefault(status_key, []).append(rec)
                    artifact_provider_status_counts[status_key] = artifact_provider_status_counts.get(status_key, 0) + 1
            for wad in rec.get("doom_wads") or []:
                if not isinstance(wad, dict):
                    continue
                filename = str(wad.get("filename") or "")
                wad_sha256 = str(wad.get("sha256") or "")
                if filename:
                    artifact_doom_wad_count += 1
                    artifacts_by_doom_wad_filename.setdefault(filename, []).append(rec)
                    artifact_doom_wad_filename_counts[filename] = artifact_doom_wad_filename_counts.get(filename, 0) + 1
                if wad_sha256:
                    artifacts_by_doom_wad_sha256.setdefault(wad_sha256, []).append(rec)
                    artifact_doom_wad_sha256_counts[wad_sha256] = artifact_doom_wad_sha256_counts.get(wad_sha256, 0) + 1
        artifact_indexes = {
            "artifacts": artifacts,
            "artifacts_by_tuple_path": artifacts_by_tuple_path,
            "artifacts_by_payload_preset": artifacts_by_payload_preset,
            "artifacts_by_tool": artifacts_by_tool,
            "artifacts_by_device_alias": artifacts_by_device_alias,
            "artifacts_by_feature": artifacts_by_feature,
            "artifacts_by_tool_payload_preset": artifacts_by_tool_payload_preset,
            "artifacts_by_device_payload_preset": artifacts_by_device_payload_preset,
            "artifacts_by_feature_payload_preset": artifacts_by_feature_payload_preset,
            "artifacts_by_tuple_payload_preset": artifacts_by_tuple_payload_preset,
        }
        recommendations = release_recommendations(devices, artifact_indexes)
        recommendation_records = release_recommendation_records(recommendations)
        license_records = [license_record] if license_record.get("exists") or license_record.get("valid") else []
        license_records_by_component = {}
        license_records_by_component_license = {}
        license_records_by_notice_file = {}
        license_records_by_evidence_source = {}
        license_records_by_evidence_source_license = {}
        license_records_by_corresponding_source_required = records_by_key(license_records, "corresponding_source_required")
        license_records_by_corresponding_source_status = records_by_key(license_records, "corresponding_source_status")
        license_records_by_package_license_audit = records_by_key(license_records, "corresponding_source_requires_package_license_audit")
        for component in license_record.get("component_names") or []:
            license_records_by_component.setdefault(component, []).append(license_record)
        for component, license_id in (license_record.get("component_licenses") or {}).items():
            if component and license_id:
                license_records_by_component_license.setdefault(f"{component}:{license_id}", []).append(license_record)
        for notice_file in license_record.get("notice_files") or []:
            license_records_by_notice_file.setdefault(str(notice_file), []).append(license_record)
        for source_name in license_record.get("license_evidence_source_names") or []:
            license_records_by_evidence_source.setdefault(str(source_name), []).append(license_record)
        for source_name, license_id in (license_record.get("license_evidence_source_licenses") or {}).items():
            if source_name and license_id:
                license_records_by_evidence_source_license.setdefault(f"{source_name}:{license_id}", []).append(license_record)
        return {
            "release_dir": str(here),
            "release_json": str(release_json),
            "release_index": str(here / "release-index.json") if (here / "release-index.json").is_file() else "",
            "release_name": release.get("release_name", "") if isinstance(release, dict) else "",
            "release_license": license_record,
            "release_license_records": license_records,
            "release_license_records_by_project_license": records_by_key(license_records, "project_license"),
            "release_license_records_by_combined_gplv2_compatible": records_by_key(license_records, "combined_gplv2_compatible"),
            "release_license_records_by_corresponding_source_required": license_records_by_corresponding_source_required,
            "release_license_records_by_corresponding_source_status": license_records_by_corresponding_source_status,
            "release_license_records_by_package_license_audit": license_records_by_package_license_audit,
            "release_license_records_by_component": license_records_by_component,
            "release_license_records_by_component_license": license_records_by_component_license,
            "release_license_records_by_notice_file": license_records_by_notice_file,
            "release_license_records_by_evidence_source": license_records_by_evidence_source,
            "release_license_records_by_evidence_source_license": license_records_by_evidence_source_license,
            "artifacts": artifacts,
            "artifacts_by_release_path": artifacts_by_release_path,
            "artifacts_by_name": artifacts_by_name,
            "artifacts_by_sha256": artifacts_by_sha256,
            "artifacts_by_payload_preset": artifacts_by_payload_preset,
            "artifacts_by_compatibility": artifacts_by_compatibility,
            "artifacts_by_source": artifacts_by_source,
            "artifacts_by_tuple_path": artifacts_by_tuple_path,
            "artifacts_by_tool": artifacts_by_tool,
            "artifacts_by_device_alias": artifacts_by_device_alias,
            "artifacts_by_feature": artifacts_by_feature,
            "artifacts_by_tool_payload_preset": artifacts_by_tool_payload_preset,
            "artifacts_by_device_payload_preset": artifacts_by_device_payload_preset,
            "artifacts_by_feature_payload_preset": artifacts_by_feature_payload_preset,
            "artifacts_by_tuple_payload_preset": artifacts_by_tuple_payload_preset,
            "artifacts_by_provider_tool": artifacts_by_provider_tool,
            "artifacts_by_provider_status": artifacts_by_provider_status,
            "artifacts_by_doom_wad_filename": artifacts_by_doom_wad_filename,
            "artifacts_by_doom_wad_sha256": artifacts_by_doom_wad_sha256,
            "artifacts_by_command_queue_enabled": artifacts_by_command_queue_enabled,
            "artifacts_by_command_queue_execution_supported": artifacts_by_command_queue_execution_supported,
            "artifacts_by_command_queue_operator_supplied_command_execution": artifacts_by_command_queue_operator_supplied_command_execution,
            "artifact_stats": {
                "total_size": artifact_total_size,
                "by_compatibility": artifact_compatibility_counts,
                "by_payload_preset": artifact_payload_preset_counts,
                "by_source": artifact_source_counts,
                "by_tool": artifact_tool_counts,
                "by_device_alias": artifact_device_alias_counts,
                "by_feature": artifact_feature_counts,
                "by_provider_tool": artifact_provider_tool_counts,
                "by_provider_status": artifact_provider_status_counts,
                "by_doom_wad_filename": artifact_doom_wad_filename_counts,
                "by_doom_wad_sha256": artifact_doom_wad_sha256_counts,
                "by_command_queue_enabled": artifact_command_queue_enabled_counts,
                "by_command_queue_execution_supported": artifact_command_queue_execution_supported_counts,
                "by_command_queue_operator_supplied_command_execution": artifact_command_queue_operator_supplied_command_execution_counts,
                "doom_wad_count": artifact_doom_wad_count,
            },
            "devices": devices,
            "devices_by_name": {rec.get("name", ""): rec for rec in devices if rec.get("name")},
            "devices_by_tuple_path": records_by_key(devices, "tuple_path"),
            "devices_by_artifact": records_by_list_item(devices, "artifacts"),
            "tuples": tuples,
            "tuples_by_path": {rec.get("path", ""): rec for rec in tuples if rec.get("path")},
            "tuples_by_artifact": records_by_list_item(tuples, "artifacts"),
            "recommendations": recommendations,
            "recommendation_records": recommendation_records,
            "recommendations_by_id": {rec.get("id", ""): rec for rec in recommendation_records if rec.get("id")},
            "recommendations_by_scope": records_by_key(recommendation_records, "scope"),
            "recommendations_by_artifact": records_by_key(recommendation_records, "artifact"),
            "recommendations_by_payload_preset": records_by_key(recommendation_records, "payload_preset"),
            "recommendations_by_compatibility": records_by_nested_key(recommendation_records, "compatibility", "label"),
        }
    return {}


def release_context_for_dir(path):
    return release_context({"release_dir": str(path)})


def release_discovery_candidates(cfg=None):
    cfg = cfg or {}
    candidates = []

    def add(path):
        try:
            p = Path(path).expanduser()
        except (TypeError, ValueError):
            return
        if not p:
            return
        candidates.append(p)

    if cfg.get("release_dir"):
        add(cfg.get("release_dir"))
    cwd = Path.cwd()
    source_root = Path(__file__).resolve().parents[2]
    add(cwd)
    for parent in cwd.parents:
        add(parent)
        if parent == source_root:
            break
    for base in (cwd / "dist" / "releases", source_root / "dist" / "releases"):
        if base.is_dir():
            for path in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
                if path.is_dir():
                    add(path)
    seen = set()
    out = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def discover_release_context(cfg=None):
    cfg = cfg or {}
    configured = release_context(cfg)
    if configured:
        configured = dict(configured)
        configured["release_discovery_source"] = "configured"
        return configured, []
    checked = []
    explicit = bool(cfg.get("release_dir"))
    for path in release_discovery_candidates(cfg):
        state = release_state_record({"release_dir": str(path)})
        checked.append(state)
        if explicit and str(path) == str(cfg.get("release_dir")):
            return {}, checked
        if explicit:
            continue
        if not state.get("valid"):
            continue
        rel = release_context_for_dir(path)
        if rel:
            rel = dict(rel)
            rel["release_discovery_source"] = "auto"
            return rel, checked
    return {}, checked


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
    release = release or {}
    artifacts_by_path = release.get("artifacts_by_release_path") or {}
    out = [{"kind": "index", "label": f"index {Path(release.get('release_index', '')).name if release.get('release_index') else '-'}", "path": release.get("release_index", "")}]
    for rec in release.get("recommendation_records") or []:
        artifact_key = rec.get("artifact") or ""
        artifact = artifacts_by_path.get(artifact_key) or {}
        path = artifact.get("path") or artifact_key
        label = f"rec {rec.get('scope', '')}:{rec.get('key', '')} -> {rec.get('artifact_name') or Path(artifact_key).name}"
        out.append({"kind": "recommendation", "label": label, "path": path, "record": rec, "artifact": artifact})
    for d in (release_devices or [])[:limit]:
        out.append({"kind": "device", "label": f"dev {d.get('name', '')} -> {d.get('tuple_path', '')} artifacts={d.get('artifact_count', len(d.get('artifacts') or []))}", "record": d})
    for t in (release_tuples or [])[:limit]:
        out.append({"kind": "tuple", "label": f"tuple {t.get('path', '')} artifacts={t.get('artifact_count', len(t.get('artifacts') or []))}", "record": t})
    return out


def stage_release_artifact(cfg, artifact_name):
    rel = release_context(cfg)
    if not rel:
        raise ValueError("not running inside a release bundle")
    requested = str(artifact_name or "")
    artifact_name = requested
    recommendation_tuple_path = ""
    recommendation_payload_preset = ""
    recommendation = (rel.get("recommendations_by_id") or {}).get(requested)
    if recommendation:
        artifact_name = recommendation.get("artifact") or recommendation.get("artifact_name") or artifact_name
        recommendation_tuple_path = str(recommendation.get("tuple_path") or "")
        recommendation_payload_preset = str(recommendation.get("payload_preset") or "")
    matches = []
    requested_path = Path(artifact_name).expanduser() if artifact_name else None
    requested_resolved = ""
    if requested_path:
        try:
            requested_resolved = str(requested_path.resolve())
        except OSError:
            requested_resolved = str(requested_path)
    for rec in rel.get("artifacts") or []:
        path = Path(str(rec.get("path", "")))
        path_resolved = ""
        try:
            path_resolved = str(path.resolve())
        except OSError:
            path_resolved = str(path)
        tuple_artifact_path = str(rec.get("tuple_artifact_path") or "")
        tuple_artifact_resolved = ""
        if tuple_artifact_path:
            try:
                tuple_artifact_resolved = str(Path(tuple_artifact_path).resolve())
            except OSError:
                tuple_artifact_resolved = tuple_artifact_path
        if artifact_name in {
                rec.get("name"),
                rec.get("release_path"),
                rec.get("tuple_artifact"),
                str(path),
                tuple_artifact_path,
        } or (
                requested_resolved and requested_resolved == path_resolved):
            matches.append(rec)
        elif requested_resolved and tuple_artifact_resolved and requested_resolved == tuple_artifact_resolved:
            matches.append(rec)
    if recommendation_tuple_path or recommendation_payload_preset:
        matches = [
            rec for rec in matches
            if (not recommendation_tuple_path or str(rec.get("tuple_path") or "") == recommendation_tuple_path)
            and (not recommendation_payload_preset or str(rec.get("payload_preset") or "") == recommendation_payload_preset)
        ]
    if not matches:
        raise ValueError(f"release artifact not found: {requested}")
    if len(matches) > 1:
        raise ValueError(f"release artifact is ambiguous: {requested}")
    rec = matches[0]
    request = rec.get("request_name") or Path(str(rec.get("path"))).name
    metadata = {
        "stage_kind": "release-artifact",
        "release_artifact_name": rec.get("name", ""),
        "release_artifact_path": rec.get("path", ""),
        "release_path": rec.get("release_path", ""),
        "tuple_path": rec.get("tuple_path", ""),
        "payload_preset": rec.get("payload_preset", ""),
        "compatibility": rec.get("compatibility") or {},
        "selected_by_recommendation": requested if recommendation else "",
    }
    return stage_file(cfg, rec["path"], request, metadata=metadata)


def stage_release_nav_item(cfg, rec):
    kind = rec.get("kind", "")
    record = rec.get("record") if isinstance(rec.get("record"), dict) else {}
    if kind == "recommendation":
        recommendation_id = record.get("id")
        if recommendation_id:
            return stage_release_artifact(cfg, recommendation_id)
        artifact = record.get("artifact") or rec.get("path")
        if artifact:
            return stage_release_artifact(cfg, artifact)
    if kind == "device":
        name = record.get("name", "")
        if name:
            try:
                return stage_release_artifact(cfg, f"by_device:{name}")
            except ValueError:
                pass
    if kind == "tuple":
        tuple_path = record.get("path", "")
        if tuple_path:
            try:
                return stage_release_artifact(cfg, f"by_tuple_path:{tuple_path}")
            except ValueError:
                pass
    artifact_paths = record.get("artifacts") or record.get("artifact_paths") or []
    for artifact in artifact_paths:
        if artifact:
            return stage_release_artifact(cfg, artifact)
    path = rec.get("path") or record.get("path") or record.get("filesystem_path") or ""
    if path:
        return stage_release_artifact(cfg, path)
    raise ValueError("no release artifact to stage")


def stage_release_selection(cfg, selector):
    selector = str(selector or "").strip()
    if not selector:
        raise ValueError("release selection is required")
    rel = release_context(cfg)
    if not rel:
        raise ValueError("not running inside a release bundle")
    if selector.isdigit():
        nav = release_nav_records(rel, rel.get("devices") or [], rel.get("tuples") or [], limit=12)
        idx = int(selector) - 1
        if idx < 0 or idx >= len(nav):
            raise ValueError(f"release selection number out of range: {selector}")
        return stage_release_nav_item(cfg, nav[idx])
    if selector.startswith(("by_device:", "by_tuple_path:")):
        return stage_release_artifact(cfg, selector)
    recommendations = rel.get("recommendations_by_id") or {}
    if selector in recommendations:
        return stage_release_artifact(cfg, selector)
    return stage_release_artifact(cfg, selector)


def _release_shquote(value):
    text = str(value)
    if all(ch.isalnum() or ch in "._-/:=" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


def release_artifact_workflow_action_records(cfg, release, default_config="local/server-config.json"):
    release = release or {}
    config_path = str(cfg.get("_config_path", default_config))
    base = "scripts/grit-console --config " + _release_shquote(config_path)
    release_dir = str(release.get("release_dir") or cfg.get("release_dir") or ".")
    release_present = bool(release)
    release_valid = bool(release.get("valid", release_present))
    records = [
        {
            "id": "release:inspect-release",
            "action_id": "inspect-release",
            "category": "release",
            "workflow": "release-inspection",
            "label": "Inspect release bundle",
            "release_dir": release_dir,
            "release_name": str(release.get("release_name") or ""),
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
            "release_name": str(release.get("release_name") or ""),
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
    for artifact in release.get("artifacts") or []:
        release_path = str(artifact.get("release_path") or artifact.get("name") or artifact.get("path") or "")
        compatibility = artifact.get("compatibility") if isinstance(artifact.get("compatibility"), dict) else {}
        artifact_name = str(artifact.get("name") or Path(str(artifact.get("path") or release_path)).name)
        action_id = "stage-artifact"
        selector = release_path or artifact_name
        records.append({
            "id": f"release-artifact:{release_path or artifact_name}:stage-artifact",
            "action_id": action_id,
            "category": "release-artifact",
            "workflow": "release-staging",
            "label": "Stage release artifact for target fetch",
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
            "label": "Stage recommended release artifact for target fetch",
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
