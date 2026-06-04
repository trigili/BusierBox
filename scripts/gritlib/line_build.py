"""Line-console build configuration commands."""

from gritlib.build_config import (
    build_config_path,
    set_workbench_build_config,
    shell_double_quote,
    unset_workbench_build_config,
    workbench_config_field_records,
)
from gritlib.event_log import append_event


def _group_build_fields(fields):
    groups = []
    by_category = {}
    for idx, rec in enumerate(fields, 1):
        category = str(rec.get("category") or "build-config")
        if category not in by_category:
            by_category[category] = []
            groups.append((category, by_category[category]))
        by_category[category].append((idx, rec))
    return groups


def _build_field_state(rec):
    if rec.get("configured"):
        return "set"
    if rec.get("fixed_options"):
        return "fixed"
    if rec.get("requires_explicit_operator_choice"):
        return "choose"
    return "default"


def _build_field_value(rec, limit=34):
    value = shell_double_quote(str(rec.get("value") or ""))
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _build_field_options_text(rec):
    count = int(rec.get("option_count") or len(rec.get("options") or []) or 0)
    if count:
        return str(count)
    if rec.get("examples"):
        return "examples"
    return "-"


def print_line_build_config(cfg, verbose=False):
    fields = workbench_config_field_records(cfg)
    configured_count = len([rec for rec in fields if rec.get("configured")])
    num_w = len(str(len(fields))) if fields else 1
    key_w = max([len("Key")] + [len(str(rec.get("key") or "")) for rec in fields])
    state_w = max([len("State")] + [len(_build_field_state(rec)) for rec in fields])
    value_w = max([len("Value")] + [len(_build_field_value(rec)) for rec in fields])
    opts_w = max([len("Opts")] + [len(_build_field_options_text(rec)) for rec in fields])
    label_w = max([len("Purpose")] + [len(str(rec.get("label") or "")) for rec in fields])

    print(f"Build config  ({build_config_path(cfg)})")
    print(f"  configured: {configured_count}/{len(fields)}")
    print("  state: set=configured  default=using generated default  choose=operator choice recommended")
    print("")
    for category, records in _group_build_fields(fields):
        print(f"  {category} ({len(records)})")
        print("  " + " " * num_w + "  "
              + f"{'Key':{key_w}}  {'State':{state_w}}  {'Value':{value_w}}  {'Opts':{opts_w}}  {'Purpose':{label_w}}")
        print("  " + "-" * num_w + "  "
              + f"{'-' * key_w}  {'-' * state_w}  {'-' * value_w}  {'-' * opts_w}  {'-' * label_w}")
        for idx, rec in records:
            value = _build_field_value(rec)
            state = _build_field_state(rec)
            opts = _build_field_options_text(rec)
            label = str(rec.get("label") or "")
            print(f"  {idx:{num_w}}  {str(rec.get('key') or ''):{key_w}}  {state:{state_w}}  {value:{value_w}}  {opts:{opts_w}}  {label:{label_w}}".rstrip())
            if verbose:
                options = [str(o) for o in rec.get("options") or []]
                examples = [str(o) for o in rec.get("examples") or []]
                if options:
                    print("      options: " + "  ".join(options))
                elif examples:
                    print("      examples: " + "  ".join(examples))
                safety = str(rec.get("safety_note") or "")
                if safety:
                    print("      note: " + safety)
                print(f"      set: build set {rec.get('key', '')} VALUE")
        print("")
    hint = "build set KEY VALUE  |  build unset KEY  |  build -v for options  |  build ? for help"
    if verbose:
        hint = "build set KEY VALUE  |  build unset KEY  |  build ? for help"
    print(f"  {hint}")
    cfg["_line_console_search_results"] = [
        {
            "kind": "build-config",
            "label": str(rec.get("key") or ""),
            "rec": rec,
            "command": str(rec.get("set_command") or ""),
            "use_hint": f"build set {rec.get('key', '')} VALUE",
        }
        for rec in fields
    ]
    append_event(cfg, "workbench", "workbench_build_config_listed", details={
        "config_path": str(build_config_path(cfg)),
        "field_count": len(fields),
        "verbose": bool(verbose),
    })


def set_line_build_config(cfg, args):
    if not args:
        raise ValueError("usage: build set KEY VALUE")
    if "=" in args[0]:
        key, value = args[0].split("=", 1)
        if len(args) > 1:
            value = value + " " + " ".join(args[1:])
    else:
        key = args[0]
        value = " ".join(args[1:]).strip()
    if not key or value == "":
        raise ValueError("usage: build set KEY VALUE")
    rec = set_workbench_build_config(cfg, f"{key}={value}")
    print(f"set build.{rec.get('key', key)}={shell_double_quote(rec.get('value', value))}")
    print(f"config_path={rec.get('config_path', build_config_path(cfg))}")
    return rec


def unset_line_build_config(cfg, args):
    key = " ".join(args).strip()
    if not key:
        raise ValueError("usage: build unset KEY")
    rec = unset_workbench_build_config(cfg, key)
    print(f"unset build.{rec.get('key', key)}")
    print(f"config_path={rec.get('config_path', build_config_path(cfg))}")
    return rec


def set_line_global_build_option(cfg, name, value):
    key = str(name or "").strip()
    text = str(value or "")
    if key.startswith("build."):
        key = key.split(".", 1)[1]
    build_keys = {rec.get("key") for rec in workbench_config_field_records(cfg)}
    if key not in build_keys:
        raise ValueError(f"setg only supports guided build/workbench options: {name}")
    rec = set_workbench_build_config(cfg, f"{key}={text}")
    print(f"setg {rec.get('key', key)}={shell_double_quote(rec.get('value', text))}")
    return rec


def unset_line_global_build_option(cfg, name):
    key = str(name or "").strip()
    if not key:
        raise ValueError("usage: unsetg KEY")
    rec = unset_workbench_build_config(cfg, key)
    print(f"unsetg {rec.get('key', key)}")
    print(f"config_path={rec.get('config_path', build_config_path(cfg))}")
    return rec


def run_line_build_command(cfg, args):
    verbose = any(str(arg).lower() in {"-v", "--verbose", "verbose"} for arg in args)
    args = [arg for arg in args if str(arg).lower() not in {"-v", "--verbose", "verbose"}]
    subcmd = str(args[0] if args else "").lower()
    if not subcmd or subcmd in {"list", "show", "options"}:
        print_line_build_config(cfg, verbose=verbose)
        return
    if subcmd == "set":
        set_line_build_config(cfg, args[1:])
        return
    if subcmd in {"unset", "clear"}:
        unset_line_build_config(cfg, args[1:])
        return
    raise ValueError("usage: build [-v|list|set KEY VALUE|unset KEY]")
