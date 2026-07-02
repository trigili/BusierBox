"""Line-console release view helpers."""

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.file_transfers import print_staged_fetch_target_options, render_fetch_command
from gritlib.line_files import parse_line_release_stage_args
from gritlib.line_probe_guidance import print_probe_menu_steps
from gritlib.line_search import set_line_search_results
from gritlib.line_probe_serve import probe_release_matches
from gritlib.profiles import active_profile, profile_release_selector, profile_summary_line
from gritlib.release_artifacts import (
    kernel_floor_from_release,
    normalized_probe_arch,
    release_artifact_matches_profile,
)
from gritlib.release_contexts import discover_release_context, release_context
from gritlib.release_staging import release_nav_records, stage_release_selection
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
    raise ValueError(
        "usage:\n"
        "  release\n"
        "  release stage SELECTOR\n"
        "  release stage start SELECTOR\n"
        "  release stage ssh start"
    )


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


def _profile_match_fields(profile):
    uname_m = str(profile.get("uname_m") or profile.get("arch") or "")
    endian = str(profile.get("endian") or "")
    arch = str(profile.get("arch") or normalized_probe_arch(uname_m, endian))
    kernel = str(profile.get("uname_r") or "")
    kernel_floor = str(profile.get("kernel_floor") or kernel_floor_from_release(kernel))
    return arch, kernel_floor


def _profile_compatible_artifacts(rel, profile):
    if not profile:
        return []
    arch, kernel_floor = _profile_match_fields(profile)
    preset = str(profile.get("preferred_payload_preset") or "")
    matches = [
        rec for rec in probe_release_matches(rel, arch, kernel_floor)
        if release_artifact_matches_profile(rel, rec, profile)
    ]
    if preset:
        preset_matches = [rec for rec in matches if str(rec.get("payload_preset") or "") == preset]
        if preset_matches:
            matches = preset_matches + [
                rec for rec in matches
                if str(rec.get("payload_preset") or "") != preset
            ]
    return matches


def _selector_from_artifact(rec):
    tuple_path = str(rec.get("tuple_path") or "")
    preset = str(rec.get("payload_preset") or "")
    if tuple_path and preset:
        return f"by_tuple_payload_preset:{tuple_path}:{preset}"
    return str(rec.get("release_path") or rec.get("path") or rec.get("name") or "")


def _profile_default_stage_selector(cfg, profile, preset=""):
    selector = profile_release_selector(profile, preset)
    if selector:
        return selector
    rel = release_context(cfg)
    matches = _profile_compatible_artifacts(rel, profile)
    if preset:
        preset_matches = [rec for rec in matches if str(rec.get("payload_preset") or "") == preset]
        if preset_matches:
            matches = preset_matches
    if matches:
        return _selector_from_artifact(matches[0])
    return ""


def _print_release_summary(view):
    print(f"Release  {view['name']}  ({view['rdir']})")
    print(
        f"  compatible artifacts: {len(view['recommendations'])}  "
        f"release artifacts: {len(view['artifacts'])}  "
        f"known devices: {len(view['devices'])}  "
        f"target tuples: {len(view['tuples'])}"
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
        f"Matching artifacts  ({len(recommendations[:8])} shown)",
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


def _print_release_selectors(devices, tuples, recommendations, include_tuple=True):
    if devices:
        selectors = "  ".join(f"by_device:{rec.get('name')}" for rec in devices[:8] if rec.get("name"))
        print(f"  Device selectors:  {selectors}")
    if include_tuple and tuples:
        selectors = "  ".join(f"by_tuple_path:{rec.get('path')}" for rec in tuples[:6] if rec.get("path"))
        print(f"  Tuple selectors:   {selectors}")
    preset_selectors = [
        str(rec.get("id") or "")
        for rec in recommendations
        if str(rec.get("scope") or "") in (
            {"by_device_payload_preset", "by_tuple_payload_preset"}
            if include_tuple else {"by_device_payload_preset"}
        )
    ]
    if preset_selectors:
        print(f"  Preset selectors:  {'  '.join(preset_selectors[:6])}")


def release_selector_example_lines(rel=None, include_tuple=True):
    has_release_context = isinstance(rel, dict) and bool(rel)
    rel = rel if isinstance(rel, dict) else {}
    examples = []
    for rec in rel.get("recommendation_records") or []:
        selector = _release_recommendation_selector(rec)
        if not selector:
            continue
        if not include_tuple and "by_tuple" in selector:
            continue
        examples.append(f"release stage {selector}")
        break
    for rec in rel.get("devices") or []:
        name = str(rec.get("name") or "")
        if name:
            examples.append(f"release stage by_device:{name}")
            break
    if include_tuple:
        for rec in rel.get("tuples") or []:
            path = str(rec.get("path") or "")
            if path:
                examples.append(f"release stage by_tuple_path:{path}")
                break
    for rec in rel.get("artifacts") or []:
        selector = _release_artifact_selector(rec)
        if selector:
            examples.append(f"release stage {selector}")
            break
    if not examples and has_release_context:
        return []
    if not examples:
        examples = [
            "release stage by_device:gl-mt3000",
            "release stage dist/releases/lab/bin/grit-target-full",
        ]
        if include_tuple:
            examples.insert(1, "release stage by_tuple_path:by-tuple/mipsel/musl/4.x/mips32r2-24kc")
    unique = []
    for example in examples:
        if example not in unique:
            unique.append(example)
    return unique[:3]


def release_selector_example_label(example):
    text = str(example or "")
    if " by_device:" in text:
        return "stage by known device"
    if " by_tuple_path:" in text:
        return "stage by target tuple"
    return "stage by local path"


def print_release_selector_examples(rel=None, indent="  ", include_tuple=True):
    examples = release_selector_example_lines(rel, include_tuple=include_tuple)
    print(f"{indent}staging choices:")
    if not examples:
        print(f"{indent}  No stageable release artifacts found in this release.")
        return False
    for example in examples:
        print(f"{indent}  {release_selector_example_label(example)}: {example}")
    return True


def release_selector_examples_are_placeholders(examples):
    return any("DEVICE_NAME" in str(example) or "ARTIFACT_PATH" in str(example) for example in examples or [])


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
    profile = active_profile(cfg)
    profile_matches = _profile_compatible_artifacts(rel, profile)
    if profile:
        print(f"Active profile: {profile_summary_line(profile)}")
        if profile_matches:
            search_records += _print_release_artifacts(profile_matches)
        else:
            print("  no compatible artifact found for active profile")
        print("")
    else:
        print("No active profile yet; create a custom profile or populate one from probe results.")
        print("  To match release artifacts to a target:")
        print_probe_menu_steps("    ")
        print("    create manually: profile create lab-router")
    search_records += _print_release_recommendations(view["recommendations"])
    if not profile_matches:
        search_records += _print_release_artifacts(view["artifacts"])
    _print_release_selectors(
        view["devices"],
        view["tuples"],
        view["recommendations"],
        include_tuple=bool(profile),
    )
    print("")
    examples = release_selector_example_lines(rel, include_tuple=bool(profile))
    examples_are_placeholders = release_selector_examples_are_placeholders(examples)
    if examples and not examples_are_placeholders:
        if profile:
            print(f"  try: {examples[0]}")
            print(f"  stage and start service: {examples[0].replace('release stage ', 'release stage start ', 1)}")
        else:
            print(f"  stage by known device: {examples[0]}")
            print(f"  stage and start file-service: {examples[0].replace('release stage ', 'release stage start ', 1)}")
        if examples[1:]:
            print("  other staging choices:")
            for example in examples[1:]:
                print(f"    {example}")
        if not profile:
            print("  More target-matched staging choices appear after a profile has probe or device details.")
    elif not examples:
        print("  No stageable release artifacts found in this release.")
        print("  Build or unpack a release artifact, then rerun release.")
    elif profile:
        print("  release stage ssh start")
        print("  release stage by_device:gl-mt3000")
    else:
        print("Next:")
        print("  profiles")
        print("  use listener probe")
        print("  profile create lab-router")
        print("  staging help: release ?")
    if profile:
        print("  help: release ?")
    else:
        print("  help: release ?, profiles ?")
    set_line_search_results(cfg, search_records)
    _append_release_view_event(cfg, append_event_fn, rel, view)
    return rel


def print_release_context_help(cfg, staged_records=None):
    profile = active_profile(cfg)
    staged_records = list(staged_records or [])
    print("Release")
    print("  release                                    review release artifacts and next steps")
    print("  release stage by_device:gl-mt3000          stage a release artifact by known device name")
    print("  release stage start by_device:gl-mt3000    stage a release artifact and start file-service")
    print("  release stage dist/releases/lab/bin/grit-target-full")
    print("                                             stage a specific local release artifact path")
    print("  files                                      show staged release artifacts after staging")
    if profile:
        print("  release stage ssh start                    stage reverse SSH payload and start file-service using the active profile")
    else:
        print_probe_menu_steps()
    if staged_records:
        print("  deliver grit                  show the command to run on the target")
        print("  deliver queue grit            queue the staged-file command for the current target")
    else:
        print("")
        print("No staged release artifact yet.")
        rel = release_context(cfg)
        if profile:
            print("Use the staging choices below to stage a matching artifact.")
        else:
            print("Create or populate a profile first for target-matched staging.")
            rel_has_choices = bool(release_selector_example_lines(rel, include_tuple=False))
            if rel_has_choices:
                print("Known device or artifact path: use one of the staging choices below.")
        has_choices = print_release_selector_examples(rel, include_tuple=bool(profile))
        if not profile and has_choices:
            print("  More target-matched staging choices appear after a profile has probe or device details.")
    print("")
    print("Release staging is operator-to-target: it selects a local release artifact and stages it for deliver commands.")
    if profile:
        print("The active profile supplies default release tuple, device, and payload choices.")
    else:
        print("Probe menu `config` or `profile from probe 1` supplies default release tuple, device, and payload choices.")


def stage_line_release(
    cfg,
    selector,
    start_file_service=False,
    start_file_service_fn=None,
    append_event_fn=None,
):
    selector = str(selector or "").strip()
    profile = active_profile(cfg)
    if selector in {"ssh", "ssh-operator"}:
        selector = _profile_default_stage_selector(cfg, profile, "ssh-operator")
        if not selector:
            raise ValueError(
                "no active profile tuple\n"
                "  open probe menu: use listener probe\n"
                "  discover target: listener probe start\n"
                "  review probe data: listener probe results\n"
                "  update active profile: listener probe config\n"
                "  create manually: profile create lab-router\n"
                "  release stage SELECTOR"
            )
        print(f"Using active profile: {profile.get('name') or '-'}")
    if not selector:
        selector = _profile_default_stage_selector(cfg, profile)
        if not selector:
            raise ValueError(
                "usage:\n"
                "  release stage SELECTOR\n"
                "  release stage start SELECTOR\n"
                "  open probe menu: use listener probe\n"
                "  discover target: listener probe start\n"
                "  review probe data: listener probe results\n"
                "  update active profile: listener probe config\n"
                "  create manually: profile create lab-router"
            )
        print(f"Using active profile: {profile.get('name') or '-'}")
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
    print(f"  run on target: {fetch_command}")
    fetch_options = print_staged_fetch_target_options(
        rec.get("request_name", ""),
        cfg,
        output_name=rec.get("request_name", ""),
        executable=True,
        item_label="artifact",
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
