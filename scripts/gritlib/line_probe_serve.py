"""Line-console probe release staging helpers."""

from gritlib.console_display import console_table
from gritlib.probe_results import probe_effective_arch, probe_latest_result
from gritlib.release_contexts import discover_release_context
from gritlib.release_artifacts import (
    kernel_floor_from_release,
    normalized_probe_arch,
    release_artifact_matches_probe,
    release_record_matches_probe,
)


PROBE_PRESET_DESCRIPTIONS = {
    "builtin-core-shell": "small built-in shell/core; no extracted payload required",
    "survey-core": "minimal - probe, survey, config-info; smallest footprint",
    "default": "BusyBox + common debug tools; balanced size",
    "payload-bash": "default-style payload with bash when available",
    "socat-rescue": "no-residue socat-oriented rescue payload",
    "ssh-operator": "full suite - dropbear, tmux, gdbserver, strace, curl, zsh",
    "full-debug": "maximum toolset including RE tools",
}


def parse_line_probe_serve_args(args):
    start_file_service = False
    for arg in args:
        if arg in {"--start", "start"}:
            start_file_service = True
        else:
            raise ValueError(f"unknown option: {arg}\nusage: serve [start]")
    return start_file_service


def _dedupe_probe_matches(records):
    deduped = []
    seen = set()
    for item in records or []:
        key = (
            str(item.get("release_path") or item.get("path") or item.get("name") or ""),
            str(item.get("tuple_path") or ""),
            str(item.get("payload_preset") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def probe_release_matches(rel, probe_arch, probe_kernel_floor):
    recs = rel.get("artifacts") or []
    matches = [
        rec for rec in recs
        if release_artifact_matches_probe(rel, rec, probe_arch, probe_kernel_floor)
    ]
    if not matches:
        matches = [
            rec for rec in recs
            if rec.get("tuple_path") and rec.get("payload_preset")
            and release_record_matches_probe(rel, rec, probe_arch, "")
            and probe_arch
            and probe_arch in str(
                rec.get("name") or rec.get("release_path") or rec.get("path") or ""
            ).lower()
        ]
    return _dedupe_probe_matches(matches)


def _print_no_release_guidance(probe_arch, uname_m, probe_kernel_floor, endian, checked_releases):
    print("No release configured.")
    expected_floor = probe_kernel_floor or "KERNEL"
    expected_arch = probe_arch or uname_m or "ARCH"
    print(f"  Probe needs arch={expected_arch} kernel_floor={expected_floor} endian={endian or '-'}")
    print(f"  Expected tuple shape: by-tuple/{expected_arch}/LIBC/{expected_floor}/CPU")
    print(f"  Expected artifact stem: grit-{expected_arch}-linux-{expected_floor}-LIBC-PRESET")
    print("  Common payload presets: builtin-core-shell, survey-core, default, payload-bash, socat-rescue, ssh-operator, full-debug")
    print("")
    print("  Looked for a release bundle in:")
    for state in checked_releases[:8]:
        markers = state.get("detection_reason") or "not-a-release"
        print(f"    {state.get('release_dir', '')}  ({markers})")
    if len(checked_releases) > 8:
        print(f"    ... {len(checked_releases) - 8} more")
    print("")
    print("  Expected a release directory containing release.json, bin/, and scripts/.")
    print("  From a source checkout, build one with: make release-full")
    print("  From this console, point at an extracted release with:")
    print("    set release_dir /path/to/extracted-release")
    print("    serve start")


def _choose_probe_match(matches, probe_arch, uname_m, line_input_fn):
    console_table(
        f"Available for {probe_arch or uname_m}  ({len(matches)} found)",
        matches[:9],
        [
            ("Preset",    lambda r: r.get("payload_preset") or "-"),
            ("Tuple",     lambda r: r.get("tuple_path") or "-"),
            ("Artifact",  lambda r: r.get("name") or r.get("release_path") or r.get("path") or "-"),
            ("Compat",    lambda r: (r.get("compatibility") or {}).get("label") or "-"),
        ],
    )
    print("")
    if len(matches) == 1:
        return matches[0]
    print("  Which payload preset?")
    for i, rec in enumerate(matches[:9], 1):
        preset = rec.get("payload_preset") or "-"
        desc = PROBE_PRESET_DESCRIPTIONS.get(preset, "")
        tuple_path = rec.get("tuple_path") or "-"
        print(f"    {i}  {preset:<20}  {tuple_path:<42}  {desc}")
    print("")
    choice_line = line_input_fn("  Select preset (number or name, blank to cancel)> ")
    choice = (choice_line or "").strip()
    if not choice:
        print("  Cancelled.")
        return None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            return matches[idx]
    else:
        for rec in matches:
            if (rec.get("payload_preset") or "").lower() == choice.lower():
                return rec
    raise ValueError(f"no match for '{choice}' - enter a number or preset name")


def _probe_release_selector(chosen):
    tuple_path = str(chosen.get("tuple_path") or "")
    preset = str(chosen.get("payload_preset") or "")
    if tuple_path and preset:
        return f"by_tuple_payload_preset:{tuple_path}:{preset}", preset
    selector = str(chosen.get("tuple_artifact") or chosen.get("id") or chosen.get("artifact") or "")
    selector = str(chosen.get("release_path") or chosen.get("path") or chosen.get("name") or selector)
    return selector, preset or "?"


def _print_no_match_guidance(rel, probe_arch, uname_m, probe_kernel_floor, endian):
    tuple_candidates = []
    preset_candidates = []
    for tuple_rec in rel.get("tuples") or []:
        tuple_info = tuple_rec.get("tuple") if isinstance(tuple_rec.get("tuple"), dict) else {}
        if probe_arch and str(tuple_info.get("arch") or "") != probe_arch:
            continue
        if probe_kernel_floor and str(tuple_info.get("kernel_floor") or "") != probe_kernel_floor:
            continue
        if tuple_rec.get("path"):
            tuple_candidates.append(str(tuple_rec.get("path")))
    for artifact in rel.get("artifacts") or []:
        preset = str(artifact.get("payload_preset") or "")
        if preset and preset not in preset_candidates:
            preset_candidates.append(preset)
    print("  No matching release artifact found for this probe.")
    print(f"  Expected arch={probe_arch or uname_m} kernel_floor={probe_kernel_floor or '-'} endian={endian or '-'}")
    if tuple_candidates:
        print("  Candidate tuple paths in this release:")
        for path in tuple_candidates[:8]:
            print(f"    {path}")
    else:
        print("  No tuple path in this release matched the probe arch/kernel floor.")
    if preset_candidates:
        print("  Payload presets available in this release:")
        print("    " + ", ".join(sorted(preset_candidates)))
    expected_patterns = []
    for tuple_path in tuple_candidates[:4]:
        tuple_rec = (rel.get("tuples_by_path") or {}).get(tuple_path) or {}
        tuple_info = tuple_rec.get("tuple") if isinstance(tuple_rec.get("tuple"), dict) else {}
        arch = str(tuple_info.get("arch") or probe_arch or uname_m or "ARCH")
        libc = str(tuple_info.get("libc") or "LIBC")
        kernel_floor = str(tuple_info.get("kernel_floor") or probe_kernel_floor or "KERNEL")
        target_stem = "native" if arch == "native" else f"{arch}-linux-{kernel_floor}-{libc}"
        for preset in (sorted(preset_candidates) or ["PRESET"])[:4]:
            expected_patterns.append(f"grit-{target_stem}-{preset}-full")
    if not expected_patterns:
        floor = probe_kernel_floor or "KERNEL"
        expected_patterns.append(f"grit-{probe_arch or uname_m or 'ARCH'}-linux-{floor}-LIBC-PRESET-full")
    print("  Expected generic artifact names like:")
    for pattern in expected_patterns[:8]:
        print(f"    {pattern}")
    print("  Try: release")


def run_line_probe_serve(cfg, args, line_input_fn, stage_line_release_fn, append_event_fn=None):
    start_file_service = parse_line_probe_serve_args(args)
    rec = probe_latest_result(cfg)
    if not rec:
        raise ValueError("no probe results - run: probe start")
    uname_m, endian = probe_effective_arch(rec)
    kernel = str(rec.get("uname_r") or rec.get("kernel") or "")
    probe_arch = normalized_probe_arch(uname_m, endian)
    probe_kernel_floor = kernel_floor_from_release(kernel)
    print(f"Probe arch: {probe_arch or uname_m}  kernel: {kernel}  floor: {probe_kernel_floor or '-'}  endian: {endian}")
    print("")
    rel, checked_releases = discover_release_context(cfg)
    if not rel:
        _print_no_release_guidance(probe_arch, uname_m, probe_kernel_floor, endian, checked_releases)
        return None
    if rel.get("release_discovery_source") == "auto":
        cfg["release_dir"] = rel.get("release_dir", "")
        print(f"Using release: {rel.get('release_dir', '')}")
        print("")
    matches = probe_release_matches(rel, probe_arch, probe_kernel_floor)
    if matches:
        chosen = _choose_probe_match(matches, probe_arch, uname_m, line_input_fn)
        if not chosen:
            return None
        selector, preset = _probe_release_selector(chosen)
        print(f"  Staging {preset}: {selector}")
        try:
            stage_line_release_fn(selector, start_file_service=start_file_service)
        except Exception as exc:
            raise ValueError(f"staging failed: {exc}") from exc
    else:
        _print_no_match_guidance(rel, probe_arch, uname_m, probe_kernel_floor, endian)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_probe_serve_run", details={
            "probe_arch": probe_arch or uname_m,
            "probe_kernel": kernel,
            "probe_kernel_floor": probe_kernel_floor,
            "match_count": len(matches),
            "start_file_service": start_file_service,
            "release_dir": rel.get("release_dir", ""),
            "release_discovery_source": rel.get("release_discovery_source", ""),
        })
    return matches
