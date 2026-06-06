"""Release navigation and artifact staging helpers."""

from pathlib import Path

from gritlib.staged_files import stage_file


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


def _default_release_context(cfg):
    release_artifacts = __import__(
        "gritlib.release_artifacts",
        fromlist=["release_context"],
    )
    return release_artifacts.release_context(cfg)


def _release_artifact_matches(rec, artifact_name, requested_resolved):
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
        return True
    return bool(requested_resolved and tuple_artifact_resolved and requested_resolved == tuple_artifact_resolved)


def _release_artifact_matches_recommendation(rec, tuple_path, payload_preset):
    return (
        (not tuple_path or str(rec.get("tuple_path") or "") == tuple_path)
        and (not payload_preset or str(rec.get("payload_preset") or "") == payload_preset)
    )


def _release_artifact_staging_metadata(rec, requested, recommendation):
    return {
        "stage_kind": "release-artifact",
        "release_artifact_name": rec.get("name", ""),
        "release_artifact_path": rec.get("path", ""),
        "release_path": rec.get("release_path", ""),
        "tuple_path": rec.get("tuple_path", ""),
        "payload_preset": rec.get("payload_preset", ""),
        "compatibility": rec.get("compatibility") or {},
        "selected_by_recommendation": requested if recommendation else "",
    }


def stage_release_artifact(
    cfg,
    artifact_name,
    *,
    release_context_func=None,
    stage_file_func=stage_file,
):
    release_context_func = release_context_func or _default_release_context
    rel = release_context_func(cfg)
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
    requested_path = Path(artifact_name).expanduser() if artifact_name else None
    requested_resolved = ""
    if requested_path:
        try:
            requested_resolved = str(requested_path.resolve())
        except OSError:
            requested_resolved = str(requested_path)
    matches = [
        rec for rec in rel.get("artifacts") or []
        if _release_artifact_matches(rec, artifact_name, requested_resolved)
    ]
    if recommendation_tuple_path or recommendation_payload_preset:
        matches = [
            rec for rec in matches
            if _release_artifact_matches_recommendation(
                rec,
                recommendation_tuple_path,
                recommendation_payload_preset,
            )
        ]
    if not matches:
        raise ValueError(f"release artifact not found: {requested}")
    if len(matches) > 1:
        raise ValueError(f"release artifact is ambiguous: {requested}")
    rec = matches[0]
    request = rec.get("request_name") or Path(str(rec.get("path"))).name
    metadata = _release_artifact_staging_metadata(rec, requested, recommendation)
    return stage_file_func(cfg, rec["path"], request, metadata=metadata)


def stage_release_nav_item(cfg, rec, *, stage_release_artifact_func=None):
    stage_release_artifact_func = stage_release_artifact_func or stage_release_artifact
    kind = rec.get("kind", "")
    record = rec.get("record") if isinstance(rec.get("record"), dict) else {}
    if kind == "recommendation":
        recommendation_id = record.get("id")
        if recommendation_id:
            return stage_release_artifact_func(cfg, recommendation_id)
        artifact = record.get("artifact") or rec.get("path")
        if artifact:
            return stage_release_artifact_func(cfg, artifact)
    if kind == "device":
        name = record.get("name", "")
        if name:
            try:
                return stage_release_artifact_func(cfg, f"by_device:{name}")
            except ValueError:
                pass
    if kind == "tuple":
        tuple_path = record.get("path", "")
        if tuple_path:
            try:
                return stage_release_artifact_func(cfg, f"by_tuple_path:{tuple_path}")
            except ValueError:
                pass
    artifact_paths = record.get("artifacts") or record.get("artifact_paths") or []
    for artifact in artifact_paths:
        if artifact:
            return stage_release_artifact_func(cfg, artifact)
    path = rec.get("path") or record.get("path") or record.get("filesystem_path") or ""
    if path:
        return stage_release_artifact_func(cfg, path)
    raise ValueError("no release artifact to stage")


def stage_release_selection(
    cfg,
    selector,
    *,
    release_context_func=None,
    release_nav_records_func=release_nav_records,
    stage_release_artifact_func=None,
):
    selector = str(selector or "").strip()
    if not selector:
        raise ValueError("release selection is required")
    release_context_func = release_context_func or _default_release_context
    if stage_release_artifact_func is None:
        stage_release_artifact_func = (
            lambda cfg_arg, artifact: stage_release_artifact(
                cfg_arg,
                artifact,
                release_context_func=release_context_func,
            )
        )
    rel = release_context_func(cfg)
    if not rel:
        raise ValueError("not running inside a release bundle")
    if selector.isdigit():
        nav = release_nav_records_func(rel, rel.get("devices") or [], rel.get("tuples") or [], limit=12)
        idx = int(selector) - 1
        if idx < 0 or idx >= len(nav):
            raise ValueError(f"release selection number out of range: {selector}")
        return stage_release_nav_item(cfg, nav[idx], stage_release_artifact_func=stage_release_artifact_func)
    if selector.startswith(("by_device:", "by_tuple_path:")):
        return stage_release_artifact_func(cfg, selector)
    recommendations = rel.get("recommendations_by_id") or {}
    if selector in recommendations:
        return stage_release_artifact_func(cfg, selector)
    return stage_release_artifact_func(cfg, selector)
