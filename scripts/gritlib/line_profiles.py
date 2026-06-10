"""Line-console profile commands."""

from gritlib.console_display import console_table
from gritlib.probe_results import probe_result_by_ordinal
from gritlib.profiles import (
    active_profile,
    clear_active_profile,
    create_profile,
    delete_profile,
    load_profiles,
    profile_records,
    profile_summary_line,
    resolve_profile_name,
    set_active_profile,
    set_profile_value,
    upsert_profile_from_probe,
)


PROFILE_COMMAND_HELP = "\n".join([
    "usage:",
    "  profile",
    "  profiles",
    "  profile use NAME",
    "  profile use N",
    "  profile create NAME",
    "  profile set KEY VALUE",
    "  profile clear",
    "  profile delete NAME confirm",
    "  profile delete N confirm",
    "  profile from probe N",
    "  listener probe config",
    "  listener serve start",
])


def parse_line_profile_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd not in {"profile", "profiles"}:
        return {}
    args = list(args or [])
    if cmd == "profiles":
        if not args or str(args[0]).lower() in {"list", "show"}:
            return {"action": "list"}
        if str(args[0]).lower() in {"use", "select"}:
            return {"action": "use", "selector": " ".join(args[1:]).strip()}
        raise ValueError("usage:\n  profiles\n  profiles use NAME\n  profiles use N")
    subcmd = str(args[0]).strip().lower() if args else ""
    if not subcmd or subcmd in {"show", "current"}:
        return {"action": "show"}
    if subcmd in {"list", "ls"}:
        return {"action": "list"}
    if subcmd in {"use", "select"}:
        return {"action": "use", "selector": " ".join(args[1:]).strip()}
    if subcmd in {"create", "new"}:
        return {"action": "create", "name": " ".join(args[1:]).strip()}
    if subcmd == "set":
        if len(args) < 3:
            raise ValueError("usage:\n  profile set KEY VALUE")
        return {"action": "set", "key": str(args[1]), "value": " ".join(args[2:])}
    if subcmd == "clear":
        return {"action": "clear"}
    if subcmd in {"delete", "remove", "rm"}:
        selector = " ".join(args[1:]).strip()
        confirm = False
        if selector.endswith(" confirm"):
            selector = selector.rsplit(" ", 1)[0].strip()
            confirm = True
        return {"action": "delete", "selector": selector, "confirm": confirm}
    if subcmd == "from" and len(args) >= 2 and str(args[1]).lower() == "probe":
        ordinal = str(args[2]).strip() if len(args) >= 3 else "1"
        return {"action": "from_probe", "ordinal": ordinal}
    if subcmd in {"-h", "--help", "help", "?"}:
        return {"action": "help"}
    raise ValueError(PROFILE_COMMAND_HELP)


def dispatch_line_profile_command(profile_cmd, *, profile_func=None):
    try:
        if profile_func:
            return profile_func(profile_cmd)
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("profile command support is unavailable")


def _profile_row_name(rec):
    marker = "*" if rec.get("_active") else " "
    return f"{marker} {rec.get('name') or '-'}"


def print_profiles(cfg):
    records = profile_records(cfg)
    print(f"Profiles  ({len(records)} saved)")
    print("")
    if records:
        console_table(
            "",
            records,
            [
                ("Profile", _profile_row_name),
                ("Arch", lambda r: r.get("arch") or r.get("uname_m") or "-"),
                ("Kernel", lambda r: r.get("uname_r") or "-"),
                ("Endian", lambda r: r.get("endian") or "-"),
                ("Operator", lambda r: r.get("operator_host") or "-"),
            ],
        )
    else:
        print("  No profiles yet.")
    print("")
    print("Next:")
    print("  profile use N")
    print("  profile")
    print("  listener probe config")
    print("  listener serve start")
    print("  listener serve ssh start")
    return records


def print_active_profile(cfg):
    profile = active_profile(cfg)
    if not profile:
        print("Active profile: none")
        print("Next:")
        print("  listener probe config")
        print("  profile create NAME")
        print("  profile use N")
        return {}
    print(f"Active profile: {profile.get('name') or '-'}")
    fields = [
        ("target", profile_summary_line(profile).split(":", 1)[-1].strip()),
        ("tuple", profile.get("tuple_path") or "-"),
        ("operator_host", profile.get("operator_host") or "-"),
        ("preferred_payload_preset", profile.get("preferred_payload_preset") or "default"),
        ("preferred_transport", profile.get("preferred_transport") or "ssh"),
        ("source", profile.get("source") or "-"),
        ("updated", profile.get("updated_at") or "-"),
    ]
    for key, value in fields:
        print(f"  {key}: {value}")
    print("")
    print("Next:")
    print("  listener serve start")
    print("  listener serve ssh start")
    print("  stamp ARTIFACT")
    return profile


def _print_profile_updated(profile, created=False):
    action = "created" if created else "updated"
    print(f"Profile {action}: {profile.get('name') or '-'}")
    print(f"  {profile_summary_line(profile)}")
    if profile.get("tuple_path"):
        print(f"  tuple: {profile.get('tuple_path')}")
    print("")
    print("Next:")
    print("  profile")
    print("  listener serve start")
    print("  listener serve ssh start")


def run_profile_command(cfg, profile_cmd, append_event_fn=None):
    action = (profile_cmd or {}).get("action")
    if action == "list":
        return print_profiles(cfg)
    if action == "show":
        return print_active_profile(cfg)
    if action == "use":
        selector = profile_cmd.get("selector") or ""
        if not selector:
            raise ValueError("usage:\n  profile use NAME\n  profile use N")
        profile = set_active_profile(cfg, selector)
        print(f"Active profile: {profile.get('name')}")
        print("Next:")
        print("  listener serve start")
        print("  listener serve ssh start")
        return profile
    if action == "create":
        name = profile_cmd.get("name") or ""
        if not name:
            raise ValueError("usage:\n  profile create NAME")
        profile = create_profile(cfg, name)
        _print_profile_updated(profile, created=True)
        return profile
    if action == "set":
        profile = set_profile_value(cfg, profile_cmd.get("key"), profile_cmd.get("value"))
        print(f"Profile updated: {profile.get('name')}")
        print(f"  {profile_cmd.get('key')}: {profile_cmd.get('value')}")
        return profile
    if action == "clear":
        clear_active_profile(cfg)
        print("Active profile cleared.")
        print("Next:")
        print("  profile use N")
        print("  listener probe config")
        return None
    if action == "delete":
        selector = profile_cmd.get("selector") or ""
        if not selector:
            raise ValueError("usage:\n  profile delete NAME confirm\n  profile delete N confirm")
        name = resolve_profile_name(cfg, selector)
        if not name:
            raise ValueError(f"profile not found: {selector}")
        if not profile_cmd.get("confirm"):
            raise ValueError(f"delete profile {name}? run: profile delete {selector} confirm")
        delete_profile(cfg, selector)
        print(f"Profile deleted: {name}")
        return None
    if action == "from_probe":
        ordinal = profile_cmd.get("ordinal") or "1"
        rec = probe_result_by_ordinal(cfg, ordinal)
        if not rec:
            raise ValueError(f"probe result not found: {ordinal} - run: listener probe results")
        profile, created = upsert_profile_from_probe(cfg, rec, ordinal=ordinal)
        _print_profile_updated(profile, created=created)
        return profile
    if action == "help":
        print(PROFILE_COMMAND_HELP)
        print("  profile from probe N populates the active profile from probe results")
        return None
    raise ValueError("unsupported profile command")
