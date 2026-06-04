"""Line-console release view helpers."""

from gritlib.console_display import console_table
from gritlib.release_artifacts import discover_release_context


def _release_compat_label(rec):
    return (rec.get("compatibility") or {}).get("label") or "-"


def _release_recommendation_selector(rec):
    return str(rec.get("id") or rec.get("artifact") or "")


def _release_artifact_selector(rec):
    return str(rec.get("release_path") or rec.get("name") or rec.get("path") or "")


def print_line_release(cfg, append_event_fn=None):
    rel, checked_releases = discover_release_context(cfg)
    if not rel:
        print("Release  (none detected)")
        print("")
        print("  Looked for a release bundle in:")
        for state in checked_releases[:8]:
            markers = state.get("detection_reason") or "not-a-release"
            print(f"    {state.get('release_dir', '')}  ({markers})")
        if len(checked_releases) > 8:
            print(f"    ... {len(checked_releases) - 8} more")
        print("")
        print("  Run make release-full, extract the tarball, or set a release root here:")
        print("    set release_dir /path/to/extracted-release")
        return None
    if rel.get("release_discovery_source") == "auto":
        cfg["release_dir"] = rel.get("release_dir", "")
    name = rel.get("release_name") or "-"
    rdir = rel.get("release_dir") or "-"
    recommendations = rel.get("recommendation_records") or []
    artifacts = rel.get("artifacts") or []
    devices = rel.get("devices") or []
    tuples = rel.get("tuples") or []

    print(f"Release  {name}  ({rdir})")
    print(
        f"  {len(recommendations)} recommendations  {len(artifacts)} artifacts  "
        f"{len(devices)} devices  {len(tuples)} tuples"
    )
    print("")

    search_records = []
    if recommendations:
        console_table(
            f"Recommendations  ({len(recommendations[:8])} shown)",
            recommendations[:8],
            [
                ("Selector",     _release_recommendation_selector),
                ("Scope:Key",    lambda r: f"{r.get('scope','')}:{r.get('key','')}"),
                ("Artifact",     lambda r: r.get("artifact") or r.get("artifact_name") or "-"),
                ("Preset",       lambda r: r.get("payload_preset") or "-"),
                ("Compat",       _release_compat_label),
            ],
        )
        search_records += [
            {
                "kind": "release-recommendation",
                "label": (
                    f"{rec.get('scope','')}:{rec.get('key','')} -> "
                    f"{rec.get('artifact') or rec.get('artifact_name') or ''}"
                ),
                "rec": rec,
                "command": f"release stage {_release_recommendation_selector(rec)}",
                "use_hint": f"release stage {_release_recommendation_selector(rec)}",
            }
            for rec in recommendations[:8]
        ]
    if artifacts:
        console_table(
            f"Artifacts  ({len(artifacts[:8])} shown)",
            artifacts[:8],
            [
                ("Name",   lambda r: r.get("name") or "-"),
                ("Tuple",  lambda r: r.get("tuple_path") or "-"),
                ("Preset", lambda r: r.get("payload_preset") or "-"),
                ("Compat", _release_compat_label),
            ],
        )
        search_records += [
            {
                "kind": "release-artifact",
                "label": rec.get("name") or _release_artifact_selector(rec),
                "rec": rec,
                "command": f"release stage {_release_artifact_selector(rec)}",
                "use_hint": f"release stage {_release_artifact_selector(rec)}",
            }
            for rec in artifacts[:8]
        ]
    if devices:
        selectors = "  ".join(f"by_device:{rec.get('name')}" for rec in devices[:8] if rec.get("name"))
        print(f"  Device selectors:  {selectors}")
    if tuples:
        selectors = "  ".join(f"by_tuple_path:{rec.get('path')}" for rec in tuples[:6] if rec.get("path"))
        print(f"  Tuple selectors:   {selectors}")
    preset_selectors = [
        str(rec.get("id") or "")
        for rec in recommendations
        if str(rec.get("scope") or "") in {"by_device_payload_preset", "by_tuple_payload_preset"}
    ]
    if preset_selectors:
        print(f"  Preset selectors:  {'  '.join(preset_selectors[:6])}")
    print("")
    print("  release stage SELECTOR  |  release ? for help")

    cfg["_line_console_search_results"] = search_records
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_release_console_viewed", details={
            "release_dir": rel.get("release_dir", ""),
            "release_name": name,
            "artifact_count": len(artifacts),
            "recommendation_count": len(recommendations),
            "device_count": len(devices),
            "tuple_count": len(tuples),
        })
    return rel
