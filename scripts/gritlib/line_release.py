"""Line-console release view helpers."""

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import print_staged_fetch_target_options, render_fetch_command
from gritlib.line_files import parse_line_release_stage_args
from gritlib.line_search import set_line_search_results
from gritlib.release_artifacts import (
    discover_release_context, release_context, release_nav_records, stage_release_selection,
)
from gritlib.shell_utils import shquote


def parse_line_release_command(args):
    args = list(args or [])
    subcmd = str(args[0]).lower() if args else ""
    if not subcmd or subcmd in {"list", "show", "recommendations", "artifacts"}:
        return {"action": "list"}
    if subcmd in {"stage", "use", "select"}:
        selector, start_service = parse_line_release_stage_args(args[1:])
        return {
            "action": "stage",
            "selector": selector,
            "start_service": start_service,
        }
    if subcmd in {"-h", "--help", "help"}:
        return {"action": "help"}
    raise ValueError("usage: release [list|stage SELECTOR]")


def parse_line_release_alias_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd in {"release", "releases"}:
        return parse_line_release_command(args)
    if cmd == "stage-release":
        return parse_line_release_command(["stage", *args])
    return {}


def dispatch_line_release_command(
    release_cmd,
    *,
    list_func=None,
    stage_func=None,
    help_func=None,
):
    action = (release_cmd or {}).get("action")
    try:
        if action == "list" and list_func:
            return list_func()
        if action == "stage" and stage_func:
            return stage_func(
                release_cmd.get("selector", ""),
                start_file_service=bool(release_cmd.get("start_service")),
            )
        if action == "help" and help_func:
            return help_func("release")
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported release command")


def dispatch_legacy_line_release_number(
    choice,
    cfg,
    *,
    input_func=None,
    append_event_fn=None,
):
    if str(choice or "").strip() != "10":
        return False
    rel = release_context(cfg)
    if not rel:
        print("no release bundle detected")
        return True
    nav = release_nav_records(rel, rel.get("devices") or [], rel.get("tuples") or [], limit=12)
    for idx, rec in enumerate(nav, 1):
        print(f"{idx}: {rec.get('label', '')}")
    selector_line = input_func(
        "release selection number, recommendation id, artifact path, "
        "by_device:NAME, by_device_payload_preset:NAME:PRESET, "
        "by_tuple_path:PATH, or by_tuple_payload_preset:PATH:PRESET> "
    ) if input_func else None
    selector = selector_line.strip() if selector_line is not None else ""
    if not selector:
        return True
    try:
        headless = (
            "scripts/grit-console --config "
            + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --stage-release-artifact "
            + shquote(selector)
        )
        rec = stage_release_selection(cfg, selector)
        print(f"staged {rec['request_name']}")
        print(render_fetch_command(rec["request_name"], cfg))
        if append_event_fn:
            append_event_fn(cfg, "workbench", "workbench_release_artifact_staged", details={
                "selector": selector,
                "headless_command": headless,
                "request_name": rec.get("request_name", ""),
                "release_artifact_name": rec.get("release_artifact_name", ""),
                "release_path": rec.get("release_path", ""),
                "tuple_path": rec.get("tuple_path", ""),
                "payload_preset": rec.get("payload_preset", ""),
            })
    except ValueError as exc:
        print(exc)
    return True


def _release_compat_label(rec):
    return (rec.get("compatibility") or {}).get("label") or "-"


def _release_recommendation_selector(rec):
    return str(rec.get("id") or rec.get("artifact") or "")


def _release_artifact_selector(rec):
    return str(rec.get("release_path") or rec.get("name") or rec.get("path") or "")


def _print_missing_release(checked_releases):
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


def _release_view_context(rel):
    return {
        "name": rel.get("release_name") or "-",
        "rdir": rel.get("release_dir") or "-",
        "recommendations": rel.get("recommendation_records") or [],
        "artifacts": rel.get("artifacts") or [],
        "devices": rel.get("devices") or [],
        "tuples": rel.get("tuples") or [],
    }


def _print_release_summary(view):
    print(f"Release  {view['name']}  ({view['rdir']})")
    print(
        f"  {len(view['recommendations'])} recommendations  {len(view['artifacts'])} artifacts  "
        f"{len(view['devices'])} devices  {len(view['tuples'])} tuples"
    )
    print("")


def _release_recommendation_search_records(recommendations):
    return [
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


def _release_artifact_search_records(artifacts):
    return [
        {
            "kind": "release-artifact",
            "label": rec.get("name") or _release_artifact_selector(rec),
            "rec": rec,
            "command": f"release stage {_release_artifact_selector(rec)}",
            "use_hint": f"release stage {_release_artifact_selector(rec)}",
        }
        for rec in artifacts[:8]
    ]


def _print_release_recommendations(recommendations):
    if not recommendations:
        return []
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
    return _release_recommendation_search_records(recommendations)


def _print_release_artifacts(artifacts):
    if not artifacts:
        return []
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
    return _release_artifact_search_records(artifacts)


def _print_release_selectors(devices, tuples, recommendations):
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


def _append_release_view_event(cfg, append_event_fn, rel, view):
    if not append_event_fn:
        return
    append_event_fn(cfg, "workbench", "workbench_release_console_viewed", details={
        "release_dir": rel.get("release_dir", ""),
        "release_name": view["name"],
        "artifact_count": len(view["artifacts"]),
        "recommendation_count": len(view["recommendations"]),
        "device_count": len(view["devices"]),
        "tuple_count": len(view["tuples"]),
    })


def print_line_release(cfg, append_event_fn=None):
    rel, checked_releases = discover_release_context(cfg)
    if not rel:
        _print_missing_release(checked_releases)
        return None
    if rel.get("release_discovery_source") == "auto":
        cfg["release_dir"] = rel.get("release_dir", "")

    view = _release_view_context(rel)
    _print_release_summary(view)
    search_records = []
    search_records += _print_release_recommendations(view["recommendations"])
    search_records += _print_release_artifacts(view["artifacts"])
    _print_release_selectors(view["devices"], view["tuples"], view["recommendations"])
    print("")
    print("  release stage SELECTOR  |  release ? for help")
    set_line_search_results(cfg, search_records)
    _append_release_view_event(cfg, append_event_fn, rel, view)
    return rel


def stage_line_release(
    cfg,
    selector,
    start_file_service=False,
    start_file_service_fn=None,
    append_event_fn=None,
):
    selector = str(selector or "").strip()
    if not selector:
        raise ValueError("usage: release stage [--start] SELECTOR")
    headless = (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
        + " --stage-release-artifact "
        + shquote(selector)
        + " --list-staged"
    )
    rec = stage_release_selection(cfg, selector)
    fetch_command = render_fetch_command(rec["request_name"], cfg)
    started = False
    if start_file_service:
        if start_file_service_fn:
            start_file_service_fn()
        started = True
    print("Release artifact staged:")
    print(f"  selector={selector}")
    print(f"  request_name={rec.get('request_name', '')}")
    print(f"  source_path={rec.get('source_path', '')}")
    print(f"  release_path={rec.get('release_path', '')}")
    print(f"  tuple_path={rec.get('tuple_path', '')}")
    print(f"  payload_preset={rec.get('payload_preset', '')}")
    print(f"  target fetch: {fetch_command}")
    fetch_options = print_staged_fetch_target_options(
        rec.get("request_name", ""),
        cfg,
        output_name=rec.get("request_name", ""),
        executable=True,
    )
    print(f"  file service: {'started' if started else 'not started'}")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_release_artifact_staged", details={
            "selector": selector,
            "headless_command": headless,
            "request_name": rec.get("request_name", ""),
            "source_path": rec.get("source_path", ""),
            "release_artifact_name": rec.get("release_artifact_name", ""),
            "release_path": rec.get("release_path", ""),
            "tuple_path": rec.get("tuple_path", ""),
            "payload_preset": rec.get("payload_preset", ""),
            "fetch_command": fetch_command,
            "fetch_options": fetch_options,
            "started_file_service": started,
            "direct_console": True,
        })
    return rec
