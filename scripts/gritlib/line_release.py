"""Line-console release view helpers."""

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import print_staged_fetch_target_options, render_fetch_command
from gritlib.line_files import parse_line_release_stage_args
from gritlib.release_artifacts import discover_release_context, stage_release_selection
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
