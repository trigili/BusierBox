"""Profile-aware listener serve command."""

from gritlib.console_display import console_table
from gritlib.line_probe_serve import PROBE_PRESET_DESCRIPTIONS, probe_release_matches
from gritlib.profiles import active_profile, profile_release_selector, profile_summary_line
from gritlib.release_contexts import discover_release_context
from gritlib.release_artifacts import kernel_floor_from_release, normalized_probe_arch


def parse_line_listener_serve_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd != "listener" or not args or str(args[0]).lower() != "serve":
        return {}
    rest = [str(arg) for arg in args[1:]]
    start = False
    preset = ""
    for arg in rest:
        text = str(arg).strip()
        if text == "start":
            start = True
        elif text == "ssh":
            preset = "ssh-operator"
        elif text:
            preset = text
    return {"action": "serve", "start": start, "preset": preset}


def _profile_probe_match_fields(profile):
    uname_m = str(profile.get("uname_m") or profile.get("arch") or "")
    endian = str(profile.get("endian") or "")
    arch = str(profile.get("arch") or normalized_probe_arch(uname_m, endian))
    kernel = str(profile.get("uname_r") or "")
    kernel_floor = str(profile.get("kernel_floor") or kernel_floor_from_release(kernel))
    return uname_m, endian, arch, kernel, kernel_floor


def _choose_profile_release_match(rel, profile, preset=""):
    _uname_m, _endian, arch, _kernel, kernel_floor = _profile_probe_match_fields(profile)
    requested_preset = str(preset or profile.get("preferred_payload_preset") or "default")
    tuple_selector = profile_release_selector(profile, requested_preset)
    if tuple_selector:
        return tuple_selector, requested_preset, []
    matches = probe_release_matches(rel, arch, kernel_floor)
    if requested_preset:
        preset_matches = [
            rec for rec in matches
            if str(rec.get("payload_preset") or "") == requested_preset
        ]
        if preset_matches:
            matches = preset_matches
    if not matches:
        return "", requested_preset, []
    chosen = matches[0]
    tuple_path = str(chosen.get("tuple_path") or "")
    chosen_preset = str(chosen.get("payload_preset") or requested_preset or "")
    if tuple_path and chosen_preset:
        return f"by_tuple_payload_preset:{tuple_path}:{chosen_preset}", chosen_preset, matches
    selector = str(chosen.get("release_path") or chosen.get("path") or chosen.get("name") or "")
    return selector, chosen_preset, matches


def _print_profile_serve_no_release(profile, checked_releases):
    _uname_m, endian, arch, kernel, kernel_floor = _profile_probe_match_fields(profile)
    print("No release configured.")
    print(f"  profile: {profile_summary_line(profile)}")
    print(f"  needs arch={arch or '-'} kernel={kernel or '-'} floor={kernel_floor or '-'} endian={endian or '-'}")
    print("")
    print("  Looked for a release bundle in:")
    for state in checked_releases[:8]:
        markers = state.get("detection_reason") or "not-a-release"
        print(f"    {state.get('release_dir', '')}  ({markers})")
    print("")
    print("  Build or select a release:")
    print("    make release-full")
    print("    set release_dir /path/to/extracted-release")
    print("    listener serve start")


def _print_profile_serve_no_match(rel, profile, preset):
    _uname_m, endian, arch, kernel, kernel_floor = _profile_probe_match_fields(profile)
    print("No matching release artifact found for the active profile.")
    print(f"  profile: {profile.get('name') or '-'}")
    print(f"  arch={arch or '-'} kernel={kernel or '-'} floor={kernel_floor or '-'} endian={endian or '-'}")
    print(f"  requested preset={preset or '-'}")
    presets = sorted({
        str(artifact.get("payload_preset") or "")
        for artifact in rel.get("artifacts") or []
        if artifact.get("payload_preset")
    })
    if presets:
        print("  available presets: " + ", ".join(presets))
    print("")
    print("  Try: release")


def run_line_profile_serve(
    cfg,
    args,
    *,
    stage_line_release_fn=None,
    append_event_fn=None,
):
    serve_cmd = parse_line_listener_serve_command("listener", ["serve", *(args or [])])
    profile = active_profile(cfg)
    if not profile:
        raise ValueError("no active profile - run: listener probe config or profile use N")
    preset = str(serve_cmd.get("preset") or profile.get("preferred_payload_preset") or "default")
    rel, checked_releases = discover_release_context(cfg)
    if not rel:
        _print_profile_serve_no_release(profile, checked_releases)
        return None
    if rel.get("release_discovery_source") == "auto":
        cfg["release_dir"] = rel.get("release_dir", "")
    selector, selected_preset, matches = _choose_profile_release_match(rel, profile, preset)
    if not selector:
        _print_profile_serve_no_match(rel, profile, preset)
        return None
    print(f"Using profile: {profile.get('name') or '-'}")
    print(f"  target: {profile_summary_line(profile).split(':', 1)[-1].strip()}")
    print(f"  tuple: {profile.get('tuple_path') or '(matched from release)'}")
    print(f"  preset: {selected_preset or preset}")
    if matches:
        print("")
        console_table(
            f"Compatible artifacts  ({len(matches[:5])} shown)",
            matches[:5],
            [
                ("Preset", lambda r: r.get("payload_preset") or "-"),
                ("Tuple", lambda r: r.get("tuple_path") or "-"),
                ("Artifact", lambda r: r.get("name") or r.get("release_path") or r.get("path") or "-"),
                ("Why", lambda r: PROBE_PRESET_DESCRIPTIONS.get(r.get("payload_preset") or "", "")),
            ],
        )
    print("")
    if not stage_line_release_fn:
        raise ValueError("release staging support is unavailable")
    rec = stage_line_release_fn(selector, start_file_service=bool(serve_cmd.get("start")))
    if profile.get("operator_host"):
        print("")
        print("Next:")
        print(
            f"  configure {rec.get('request_name', 'ARTIFACT')} "
            f"operator-host {profile.get('operator_host')} "
            f"transport {profile.get('preferred_transport') or 'ssh'}"
        )
    print("  listener ssh start")
    if rec and append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_profile_serve_run", details={
            "profile": profile.get("name", ""),
            "selector": selector,
            "payload_preset": selected_preset or preset,
            "request_name": rec.get("request_name", ""),
            "start_file_service": bool(serve_cmd.get("start")),
        })
    return rec
