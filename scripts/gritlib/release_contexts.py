"""Release context and artifact index construction for grit-console."""

import json
from pathlib import Path

from gritlib.record_utils import (
    int_value, records_by_key, records_by_list_item, records_by_nested_key,
)
from gritlib.session_state import read_json_file


def _release_artifacts_module():
    return __import__("gritlib.release_artifacts", fromlist=[
        "release_license_record",
        "release_recommendations",
        "release_recommendation_records",
        "release_state_record",
    ])


def _default_release_license_record(here):
    return _release_artifacts_module().release_license_record(here)


def _default_release_recommendations(devices, artifact_indexes):
    return _release_artifacts_module().release_recommendations(devices, artifact_indexes)


def _default_release_recommendation_records(recommendations):
    return _release_artifacts_module().release_recommendation_records(recommendations)


def _default_release_state_record(cfg):
    return _release_artifacts_module().release_state_record(cfg)


def _load_release_context_document(here):
    release_json = here / "release.json"
    if not (release_json.is_file() and (here / "bin").is_dir() and (here / "scripts").is_dir()):
        return None
    try:
        release = json.loads(release_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return release if isinstance(release, dict) else None


def _release_context_artifacts(here, index, license_record):
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
    return artifacts


def _release_artifact_refs(here, names):
    refs = [str(item) for item in (names or []) if str(item)]
    return {
        "artifacts": refs,
        "artifact_count": len(refs),
        "artifact_names": [Path(item).name for item in refs],
        "artifact_paths": [str(here / item) for item in refs],
    }


def _release_context_devices_tuples(here, release, index):
    devices = []
    tuples = []
    layout = release.get("layout") if isinstance(release, dict) else {}
    if isinstance(index, dict):
        devices_source = index.get("devices") or (layout or {}).get("devices") or {}
        tuples_source = index.get("tuples") or (layout or {}).get("tuples") or {}
    else:
        devices_source = (layout or {}).get("devices") or {}
        tuples_source = (layout or {}).get("tuples") or {}
    for name, rec in sorted((devices_source or {}).items()):
        if isinstance(rec, dict):
            row = {"name": name, "tuple_path": rec.get("tuple_path", "")}
            row.update(_release_artifact_refs(here, rec.get("artifacts") or []))
            device_dir = here / "devices" / name
            if device_dir.exists():
                row["path"] = str(device_dir)
            devices.append(row)
    for name, rec in sorted((tuples_source or {}).items()):
        if isinstance(rec, dict):
            row = {"path": name, "tuple": rec.get("tuple") or {}}
            row.update(_release_artifact_refs(here, rec.get("artifacts") or []))
            tuple_dir = here / name
            if tuple_dir.exists():
                row["filesystem_path"] = str(tuple_dir)
            tuples.append(row)
    return devices, tuples


def _empty_release_artifact_index_state():
    return {
        "artifacts_by_release_path": {},
        "artifacts_by_name": {},
        "artifacts_by_sha256": {},
        "artifacts_by_payload_preset": {},
        "artifacts_by_compatibility": {},
        "artifacts_by_source": {},
        "artifacts_by_tuple_path": {},
        "artifacts_by_tool": {},
        "artifacts_by_device_alias": {},
        "artifacts_by_feature": {},
        "artifacts_by_tool_payload_preset": {},
        "artifacts_by_device_payload_preset": {},
        "artifacts_by_feature_payload_preset": {},
        "artifacts_by_tuple_payload_preset": {},
        "artifacts_by_provider_tool": {},
        "artifacts_by_provider_status": {},
        "artifacts_by_doom_wad_filename": {},
        "artifacts_by_doom_wad_sha256": {},
        "artifacts_by_command_queue_enabled": {},
        "artifacts_by_command_queue_execution_supported": {},
        "artifacts_by_command_queue_operator_supplied_command_execution": {},
        "artifact_compatibility_counts": {},
        "artifact_payload_preset_counts": {},
        "artifact_source_counts": {},
        "artifact_tool_counts": {},
        "artifact_device_alias_counts": {},
        "artifact_feature_counts": {},
        "artifact_provider_tool_counts": {},
        "artifact_provider_status_counts": {},
        "artifact_doom_wad_filename_counts": {},
        "artifact_doom_wad_sha256_counts": {},
        "artifact_command_queue_enabled_counts": {},
        "artifact_command_queue_execution_supported_counts": {},
        "artifact_command_queue_operator_supplied_command_execution_counts": {},
        "artifact_doom_wad_count": 0,
        "artifact_total_size": 0,
    }


def _release_artifact_index_values(rec):
    command_queue = rec.get("command_queue") if isinstance(rec.get("command_queue"), dict) else {}
    mode_summary = command_queue.get("mode_summary") if isinstance(command_queue.get("mode_summary"), dict) else {}
    return {
        "key": rec.get("release_path") or rec.get("path") or rec.get("name"),
        "name": str(rec.get("name") or ""),
        "sha256": str(rec.get("sha256") or ""),
        "payload_preset": str(rec.get("payload_preset") or ""),
        "source": str(rec.get("source") or ""),
        "tuple_path": str(rec.get("tuple_path") or ""),
        "compatibility_label": str((rec.get("compatibility") or {}).get("label") or ""),
        "command_queue_enabled": "true" if command_queue.get("enabled") == "yes" or command_queue.get("enabled") is True else "false",
        "command_queue_execution_supported": "true" if command_queue.get("execution_supported") is True or command_queue.get("executes_commands") is True else "false",
        "command_queue_operator_supplied": (
            "true" if int_value(mode_summary.get("operator_supplied_command_execution_mode_count")) > 0 else "false"
        ),
    }


def _increment_count(counts, key):
    counts[key] = counts.get(key, 0) + 1


def _append_index(indexes, key, rec):
    indexes.setdefault(key, []).append(rec)


def _apply_release_artifact_base_indexes(state, rec, values):
    if values["key"]:
        state["artifacts_by_release_path"][str(values["key"])] = rec
    if values["name"]:
        _append_index(state["artifacts_by_name"], values["name"], rec)
    if values["sha256"]:
        _append_index(state["artifacts_by_sha256"], values["sha256"], rec)
    if values["payload_preset"]:
        _append_index(state["artifacts_by_payload_preset"], values["payload_preset"], rec)
        _increment_count(state["artifact_payload_preset_counts"], values["payload_preset"])
    if values["tuple_path"]:
        _append_index(state["artifacts_by_tuple_path"], values["tuple_path"], rec)
    if values["tuple_path"] and values["payload_preset"]:
        _append_index(
            state["artifacts_by_tuple_payload_preset"],
            f"{values['tuple_path']}:{values['payload_preset']}",
            rec,
        )
    if values["source"]:
        _append_index(state["artifacts_by_source"], values["source"], rec)
        _increment_count(state["artifact_source_counts"], values["source"])
    if values["compatibility_label"]:
        _append_index(state["artifacts_by_compatibility"], values["compatibility_label"], rec)
        _increment_count(state["artifact_compatibility_counts"], values["compatibility_label"])


def _apply_release_artifact_device_indexes(state, rec, values, devices):
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
            values["name"] in ref_names or
            (device_tuple_path and values["tuple_path"] == device_tuple_path)
        ):
            continue
        rec.setdefault("device_aliases", [])
        if alias not in rec["device_aliases"]:
            rec["device_aliases"].append(alias)
            _increment_count(state["artifact_device_alias_counts"], alias)
        _append_index(state["artifacts_by_device_alias"], alias, rec)
        if values["payload_preset"]:
            _append_index(
                state["artifacts_by_device_payload_preset"],
                f"{alias}:{values['payload_preset']}",
                rec,
            )


def _apply_release_artifact_command_queue_indexes(state, rec, values):
    _append_index(state["artifacts_by_command_queue_enabled"], values["command_queue_enabled"], rec)
    _increment_count(state["artifact_command_queue_enabled_counts"], values["command_queue_enabled"])
    _append_index(
        state["artifacts_by_command_queue_execution_supported"],
        values["command_queue_execution_supported"],
        rec,
    )
    _increment_count(
        state["artifact_command_queue_execution_supported_counts"],
        values["command_queue_execution_supported"],
    )
    _append_index(
        state["artifacts_by_command_queue_operator_supplied_command_execution"],
        values["command_queue_operator_supplied"],
        rec,
    )
    _increment_count(
        state["artifact_command_queue_operator_supplied_command_execution_counts"],
        values["command_queue_operator_supplied"],
    )


def _apply_release_artifact_tool_indexes(state, rec, payload_preset):
    for tool in rec.get("tools") or []:
        tool_name = str(tool)
        if tool_name:
            _append_index(state["artifacts_by_tool"], tool_name, rec)
            _increment_count(state["artifact_tool_counts"], tool_name)
            if payload_preset:
                _append_index(
                    state["artifacts_by_tool_payload_preset"],
                    f"{tool_name}:{payload_preset}",
                    rec,
                )


def _apply_release_artifact_feature_indexes(state, rec, payload_preset):
    seen_features = set()
    for feature in rec.get("features") or []:
        feature_name = str(feature)
        if feature_name and feature_name not in seen_features:
            seen_features.add(feature_name)
            _append_index(state["artifacts_by_feature"], feature_name, rec)
            _increment_count(state["artifact_feature_counts"], feature_name)
            if payload_preset:
                _append_index(
                    state["artifacts_by_feature_payload_preset"],
                    f"{feature_name}:{payload_preset}",
                    rec,
                )


def _apply_release_artifact_provider_indexes(state, rec):
    for provider_tool, provider_status in (rec.get("tool_provider_status") or {}).items():
        if not isinstance(provider_status, dict):
            continue
        provider_tool = str(provider_tool)
        overall = str(provider_status.get("overall") or provider_status.get("status") or "unknown")
        if provider_tool:
            _append_index(state["artifacts_by_provider_tool"], provider_tool, rec)
            _increment_count(state["artifact_provider_tool_counts"], provider_tool)
            status_key = f"{provider_tool}:{overall}"
            _append_index(state["artifacts_by_provider_status"], status_key, rec)
            _increment_count(state["artifact_provider_status_counts"], status_key)


def _apply_release_artifact_doom_indexes(state, rec):
    for wad in rec.get("doom_wads") or []:
        if not isinstance(wad, dict):
            continue
        filename = str(wad.get("filename") or "")
        wad_sha256 = str(wad.get("sha256") or "")
        if filename:
            state["artifact_doom_wad_count"] += 1
            _append_index(state["artifacts_by_doom_wad_filename"], filename, rec)
            _increment_count(state["artifact_doom_wad_filename_counts"], filename)
        if wad_sha256:
            _append_index(state["artifacts_by_doom_wad_sha256"], wad_sha256, rec)
            _increment_count(state["artifact_doom_wad_sha256_counts"], wad_sha256)


def _release_artifact_index_result(state):
    return {
        "artifacts_by_release_path": state["artifacts_by_release_path"],
        "artifacts_by_name": state["artifacts_by_name"],
        "artifacts_by_sha256": state["artifacts_by_sha256"],
        "artifacts_by_payload_preset": state["artifacts_by_payload_preset"],
        "artifacts_by_compatibility": state["artifacts_by_compatibility"],
        "artifacts_by_source": state["artifacts_by_source"],
        "artifacts_by_tuple_path": state["artifacts_by_tuple_path"],
        "artifacts_by_tool": state["artifacts_by_tool"],
        "artifacts_by_device_alias": state["artifacts_by_device_alias"],
        "artifacts_by_feature": state["artifacts_by_feature"],
        "artifacts_by_tool_payload_preset": state["artifacts_by_tool_payload_preset"],
        "artifacts_by_device_payload_preset": state["artifacts_by_device_payload_preset"],
        "artifacts_by_feature_payload_preset": state["artifacts_by_feature_payload_preset"],
        "artifacts_by_tuple_payload_preset": state["artifacts_by_tuple_payload_preset"],
        "artifacts_by_provider_tool": state["artifacts_by_provider_tool"],
        "artifacts_by_provider_status": state["artifacts_by_provider_status"],
        "artifacts_by_doom_wad_filename": state["artifacts_by_doom_wad_filename"],
        "artifacts_by_doom_wad_sha256": state["artifacts_by_doom_wad_sha256"],
        "artifacts_by_command_queue_enabled": state["artifacts_by_command_queue_enabled"],
        "artifacts_by_command_queue_execution_supported": state["artifacts_by_command_queue_execution_supported"],
        "artifacts_by_command_queue_operator_supplied_command_execution": state["artifacts_by_command_queue_operator_supplied_command_execution"],
        "artifact_stats": {
            "total_size": state["artifact_total_size"],
            "by_compatibility": state["artifact_compatibility_counts"],
            "by_payload_preset": state["artifact_payload_preset_counts"],
            "by_source": state["artifact_source_counts"],
            "by_tool": state["artifact_tool_counts"],
            "by_device_alias": state["artifact_device_alias_counts"],
            "by_feature": state["artifact_feature_counts"],
            "by_provider_tool": state["artifact_provider_tool_counts"],
            "by_provider_status": state["artifact_provider_status_counts"],
            "by_doom_wad_filename": state["artifact_doom_wad_filename_counts"],
            "by_doom_wad_sha256": state["artifact_doom_wad_sha256_counts"],
            "by_command_queue_enabled": state["artifact_command_queue_enabled_counts"],
            "by_command_queue_execution_supported": state["artifact_command_queue_execution_supported_counts"],
            "by_command_queue_operator_supplied_command_execution": state["artifact_command_queue_operator_supplied_command_execution_counts"],
            "doom_wad_count": state["artifact_doom_wad_count"],
        },
    }


def _release_artifact_index_state(artifacts, devices):
    state = _empty_release_artifact_index_state()
    for rec in artifacts:
        try:
            state["artifact_total_size"] += int(rec.get("size", 0) or 0)
        except (TypeError, ValueError):
            pass
        values = _release_artifact_index_values(rec)
        _apply_release_artifact_base_indexes(state, rec, values)
        _apply_release_artifact_device_indexes(state, rec, values, devices)
        _apply_release_artifact_command_queue_indexes(state, rec, values)
        _apply_release_artifact_tool_indexes(state, rec, values["payload_preset"])
        _apply_release_artifact_feature_indexes(state, rec, values["payload_preset"])
        _apply_release_artifact_provider_indexes(state, rec)
        _apply_release_artifact_doom_indexes(state, rec)
    return _release_artifact_index_result(state)


def _release_recommendation_artifact_indexes(artifacts, artifact_state):
    return {
        "artifacts": artifacts,
        "artifacts_by_tuple_path": artifact_state["artifacts_by_tuple_path"],
        "artifacts_by_payload_preset": artifact_state["artifacts_by_payload_preset"],
        "artifacts_by_tool": artifact_state["artifacts_by_tool"],
        "artifacts_by_device_alias": artifact_state["artifacts_by_device_alias"],
        "artifacts_by_feature": artifact_state["artifacts_by_feature"],
        "artifacts_by_tool_payload_preset": artifact_state["artifacts_by_tool_payload_preset"],
        "artifacts_by_device_payload_preset": artifact_state["artifacts_by_device_payload_preset"],
        "artifacts_by_feature_payload_preset": artifact_state["artifacts_by_feature_payload_preset"],
        "artifacts_by_tuple_payload_preset": artifact_state["artifacts_by_tuple_payload_preset"],
    }


def _release_license_index_state(license_record):
    license_records = [license_record] if license_record.get("exists") or license_record.get("valid") else []
    license_records_by_component = {}
    license_records_by_component_license = {}
    license_records_by_notice_file = {}
    license_records_by_evidence_source = {}
    license_records_by_evidence_source_license = {}
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
        "release_license_records": license_records,
        "release_license_records_by_project_license": records_by_key(license_records, "project_license"),
        "release_license_records_by_combined_gplv2_compatible": records_by_key(license_records, "combined_gplv2_compatible"),
        "release_license_records_by_corresponding_source_required": records_by_key(license_records, "corresponding_source_required"),
        "release_license_records_by_corresponding_source_status": records_by_key(license_records, "corresponding_source_status"),
        "release_license_records_by_package_license_audit": records_by_key(license_records, "corresponding_source_requires_package_license_audit"),
        "release_license_records_by_component": license_records_by_component,
        "release_license_records_by_component_license": license_records_by_component_license,
        "release_license_records_by_notice_file": license_records_by_notice_file,
        "release_license_records_by_evidence_source": license_records_by_evidence_source,
        "release_license_records_by_evidence_source_license": license_records_by_evidence_source_license,
    }


def release_context(
    cfg=None,
    *,
    release_license_record_func=None,
    release_recommendations_func=None,
    release_recommendation_records_func=None,
):
    release_license_record_func = release_license_record_func or _default_release_license_record
    release_recommendations_func = release_recommendations_func or _default_release_recommendations
    release_recommendation_records_func = (
        release_recommendation_records_func or _default_release_recommendation_records
    )
    here = Path(str((cfg or {}).get("release_dir") or Path.cwd()))
    release_json = here / "release.json"
    release = _load_release_context_document(here)
    if release is not None:
        license_record = release_license_record_func(here)
        index = read_json_file(here / "release-index.json", {})
        artifacts = _release_context_artifacts(here, index, license_record)
        devices, tuples = _release_context_devices_tuples(here, release, index)
        artifact_state = _release_artifact_index_state(artifacts, devices)
        artifact_indexes = _release_recommendation_artifact_indexes(artifacts, artifact_state)
        recommendations = release_recommendations_func(devices, artifact_indexes)
        recommendation_records = release_recommendation_records_func(recommendations)
        license_state = _release_license_index_state(license_record)
        return {
            "release_dir": str(here),
            "release_json": str(release_json),
            "release_index": str(here / "release-index.json") if (here / "release-index.json").is_file() else "",
            "release_name": release.get("release_name", "") if isinstance(release, dict) else "",
            "release_license": license_record,
            "release_license_records": license_state["release_license_records"],
            "release_license_records_by_project_license": license_state["release_license_records_by_project_license"],
            "release_license_records_by_combined_gplv2_compatible": license_state["release_license_records_by_combined_gplv2_compatible"],
            "release_license_records_by_corresponding_source_required": license_state["release_license_records_by_corresponding_source_required"],
            "release_license_records_by_corresponding_source_status": license_state["release_license_records_by_corresponding_source_status"],
            "release_license_records_by_package_license_audit": license_state["release_license_records_by_package_license_audit"],
            "release_license_records_by_component": license_state["release_license_records_by_component"],
            "release_license_records_by_component_license": license_state["release_license_records_by_component_license"],
            "release_license_records_by_notice_file": license_state["release_license_records_by_notice_file"],
            "release_license_records_by_evidence_source": license_state["release_license_records_by_evidence_source"],
            "release_license_records_by_evidence_source_license": license_state["release_license_records_by_evidence_source_license"],
            "artifacts": artifacts,
            "artifacts_by_release_path": artifact_state["artifacts_by_release_path"],
            "artifacts_by_name": artifact_state["artifacts_by_name"],
            "artifacts_by_sha256": artifact_state["artifacts_by_sha256"],
            "artifacts_by_payload_preset": artifact_state["artifacts_by_payload_preset"],
            "artifacts_by_compatibility": artifact_state["artifacts_by_compatibility"],
            "artifacts_by_source": artifact_state["artifacts_by_source"],
            "artifacts_by_tuple_path": artifact_state["artifacts_by_tuple_path"],
            "artifacts_by_tool": artifact_state["artifacts_by_tool"],
            "artifacts_by_device_alias": artifact_state["artifacts_by_device_alias"],
            "artifacts_by_feature": artifact_state["artifacts_by_feature"],
            "artifacts_by_tool_payload_preset": artifact_state["artifacts_by_tool_payload_preset"],
            "artifacts_by_device_payload_preset": artifact_state["artifacts_by_device_payload_preset"],
            "artifacts_by_feature_payload_preset": artifact_state["artifacts_by_feature_payload_preset"],
            "artifacts_by_tuple_payload_preset": artifact_state["artifacts_by_tuple_payload_preset"],
            "artifacts_by_provider_tool": artifact_state["artifacts_by_provider_tool"],
            "artifacts_by_provider_status": artifact_state["artifacts_by_provider_status"],
            "artifacts_by_doom_wad_filename": artifact_state["artifacts_by_doom_wad_filename"],
            "artifacts_by_doom_wad_sha256": artifact_state["artifacts_by_doom_wad_sha256"],
            "artifacts_by_command_queue_enabled": artifact_state["artifacts_by_command_queue_enabled"],
            "artifacts_by_command_queue_execution_supported": artifact_state["artifacts_by_command_queue_execution_supported"],
            "artifacts_by_command_queue_operator_supplied_command_execution": artifact_state["artifacts_by_command_queue_operator_supplied_command_execution"],
            "artifact_stats": artifact_state["artifact_stats"],
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


def release_context_for_dir(path, **kwargs):
    return release_context({"release_dir": str(path)}, **kwargs)


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


def discover_release_context(
    cfg=None,
    *,
    release_context_func=None,
    release_context_for_dir_func=None,
    release_discovery_candidates_func=None,
    release_state_record_func=None,
):
    cfg = cfg or {}
    release_context_func = release_context_func or release_context
    release_context_for_dir_func = release_context_for_dir_func or release_context_for_dir
    release_discovery_candidates_func = (
        release_discovery_candidates_func or release_discovery_candidates
    )
    release_state_record_func = release_state_record_func or _default_release_state_record
    configured = release_context_func(cfg)
    if configured:
        configured = dict(configured)
        configured["release_discovery_source"] = "configured"
        return configured, []
    checked = []
    explicit = bool(cfg.get("release_dir"))
    for path in release_discovery_candidates_func(cfg):
        state = release_state_record_func({"release_dir": str(path)})
        checked.append(state)
        if explicit and str(path) == str(cfg.get("release_dir")):
            return {}, checked
        if explicit:
            continue
        if not state.get("valid"):
            continue
        rel = release_context_for_dir_func(path)
        if rel:
            rel = dict(rel)
            rel["release_discovery_source"] = "auto"
            return rel, checked
    return {}, checked
