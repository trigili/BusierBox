"""Release browser rendering for status and workbench snapshots."""

from gritlib.release_artifacts import (
    artifact_compatibility_lines,
    artifact_doom_wad_lines,
    artifact_provider_status_lines,
    print_release_summary,
    release_context,
    release_recommendation_lines,
)
from gritlib.shell_utils import shquote


def print_release_browser(doc):
    if doc["release"]:
        print("")
        print("Release browser:")
        print_release_summary(doc)
        for artifact in doc["release"].get("artifacts", [])[:12]:
            compat = (artifact.get("compatibility") or {}).get("label") or ""
            suffix = f" compatibility={compat}" if compat else ""
            print(f"  artifact {artifact.get('name', '')} tuple={artifact.get('tuple_path', '')} preset={artifact.get('payload_preset', '')}{suffix}")
            for line in artifact_compatibility_lines(artifact):
                print(f"    {line}")
        recommendation_lines = release_recommendation_lines(doc["release"])
        if recommendation_lines:
            print("  recommendations:")
            for line in recommendation_lines:
                print(f"    {line}")
        for device in doc["release"].get("devices", [])[:8]:
            print(f"  device {device.get('name', '')} -> {device.get('tuple_path', '')} artifacts={device.get('artifact_count', len(device.get('artifacts') or []))}")
            for path in (device.get("artifact_paths") or [])[:3]:
                print(f"    artifact_path: {path}")
        for item in doc["release"].get("tuples", [])[:8]:
            print(f"  tuple {item.get('path', '')} artifacts={item.get('artifact_count', len(item.get('artifacts') or []))}")
            for path in (item.get("artifact_paths") or [])[:3]:
                print(f"    artifact_path: {path}")


def print_snapshot_release_browser(cfg, snap):
    rel = release_context(cfg)
    if rel:
        print("")
        print("Release artifact browser:")
        print_release_summary(snap)
        if rel.get("artifacts"):
            for artifact in rel["artifacts"][:12]:
                sha = str(artifact.get("sha256", ""))[:12]
                compat = (artifact.get("compatibility") or {}).get("label") or ""
                suffix = f" compatibility={compat}" if compat else ""
                print(f"  artifact {artifact.get('name', '')} size={artifact.get('size', '')} sha256={sha} tuple={artifact.get('tuple_path', '')} preset={artifact.get('payload_preset', '')}{suffix}")
                for line in artifact_compatibility_lines(artifact):
                    print(f"    {line}")
                for line in artifact_provider_status_lines(artifact):
                    print(f"    {line}")
                for line in artifact_doom_wad_lines(artifact):
                    print(f"    {line}")
                print(f"    stage: scripts/grit-console --stage-release-artifact {shquote(artifact.get('release_path') or artifact.get('name', ''))}")
        else:
            print("  artifacts: none")
        print("Release recommendations:")
        recommendation_lines = release_recommendation_lines(rel)
        if recommendation_lines:
            for line in recommendation_lines:
                print(f"  {line}")
        else:
            print("  none")
        print("Release devices:")
        for device in rel.get("devices", [])[:12] or [{"name": "none", "tuple_path": ""}]:
            print(f"  {device.get('name', '')} -> {device.get('tuple_path', '')} artifacts={device.get('artifact_count', len(device.get('artifacts') or []))}")
            for path in (device.get("artifact_paths") or [])[:3]:
                print(f"    artifact_path: {path}")
        print("Release tuples:")
        for item in rel.get("tuples", [])[:12] or [{"path": "none"}]:
            print(f"  {item.get('path', '')} artifacts={item.get('artifact_count', len(item.get('artifacts') or []))}")
            for path in (item.get("artifact_paths") or [])[:3]:
                print(f"    artifact_path: {path}")
