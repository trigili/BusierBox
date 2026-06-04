"""Line-console build configuration commands."""

from gritlib.build_config import (
    build_config_path,
    set_workbench_build_config,
    shell_double_quote,
    unset_workbench_build_config,
    workbench_config_field_records,
)
from gritlib.console_display import console_table
from gritlib.event_log import append_event
from gritlib.line_search import set_line_search_results
from gritlib.shell_utils import shquote


DEFAULT_CONFIG = "local/operator-session/config.json"


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


def _build_field_name(rec):
    return str(rec.get("key") or "")


def _build_field_purpose(rec):
    return str(rec.get("label") or "")


def print_line_build_config(cfg, verbose=False):
    fields = workbench_config_field_records(cfg)
    configured_count = len([rec for rec in fields if rec.get("configured")])

    print(f"Build config  ({build_config_path(cfg)})")
    print(f"  configured: {configured_count}/{len(fields)}")
    print("  state: set=configured  default=using generated default  choose=operator choice recommended")
    print("")

    def _detail(rec):
        details = []
        if verbose:
            options = [str(o) for o in rec.get("options") or []]
            examples = [str(o) for o in rec.get("examples") or []]
            if options:
                details.append(("options", "  ".join(options)))
            elif examples:
                details.append(("examples", "  ".join(examples)))
            safety = str(rec.get("safety_note") or "")
            if safety:
                details.append(("note", safety))
            details.append(("set", f"build set {rec.get('key', '')} VALUE"))
        return details

    for category, records in _group_build_fields(fields):
        category_records = [rec for _idx, rec in records]
        console_table(
            f"{category}  ({len(category_records)} fields)",
            category_records,
            [
                ("Key", _build_field_name),
                ("State", _build_field_state),
                ("Value", _build_field_value),
                ("Choices", _build_field_options_text),
                ("Purpose", _build_field_purpose),
            ],
            detail_fn=_detail,
        )
        print("")
    hint = "build set KEY VALUE  |  build unset KEY  |  build -v for options  |  build ? for help"
    if verbose:
        hint = "build set KEY VALUE  |  build unset KEY  |  build ? for help"
    print(f"  {hint}")
    search_records = [
        {
            "kind": "build-config",
            "label": str(rec.get("key") or ""),
            "rec": rec,
            "command": str(rec.get("set_command") or ""),
            "use_hint": f"build set {rec.get('key', '')} VALUE",
        }
        for rec in fields
    ]
    set_line_search_results(cfg, search_records)
    append_event(cfg, "workbench", "workbench_build_config_listed", details={
        "config_path": str(build_config_path(cfg)),
        "field_count": len(fields),
        "verbose": bool(verbose),
    })


def dispatch_legacy_line_build_number(choice, cfg, *, input_func=None):
    if str(choice or "").strip() != "14":
        return False
    fields = workbench_config_field_records(cfg)
    num_w = len(str(len(fields))) if fields else 1
    key_w = max([len("Key")] + [len(str(rec.get("key") or "")) for rec in fields])
    value_w = max([len("Value")] + [
        len(shell_double_quote(str(rec.get("value", "")))) for rec in fields
    ])
    current_category = None
    for idx, rec in enumerate(fields, 1):
        category = str(rec.get("category") or "build-config")
        if category != current_category:
            current_category = category
            print(f"{category}:")
            print("  " + " " * num_w + "  "
                  + f"{'Key':{key_w}}  {'Value':{value_w}}  Purpose")
            print("  " + "-" * num_w + "  "
                  + f"{'-' * key_w}  {'-' * value_w}  -------")
        print(f"  {idx:{num_w}}  {str(rec.get('key') or ''):{key_w}}  "
              f"{shell_double_quote(str(rec.get('value', ''))):{value_w}}  "
              f"{rec.get('label', '')}".rstrip())
    selected_line = input_func("build config key or number> ") if input_func else None
    selected = selected_line.strip() if selected_line is not None else ""
    if selected:
        try:
            rec = fields[int(selected) - 1] if selected.isdigit() else {item.get("key"): item for item in fields}.get(selected, {})
            key = rec.get("key")
            if not key:
                raise ValueError(f"unknown build config field: {selected}")
            print(f"current {key}={shell_double_quote(rec.get('value', ''))}")
            if rec.get("options"):
                print("options: " + "  ".join(str(opt) for opt in rec.get("options") or []))
            else:
                print("example: build set " + key + " VALUE")
            value_line = input_func("new value> ") if input_func else None
            value = value_line if value_line is not None else ""
            _headless = (
                "scripts/grit-console --config "
                + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                + " --build-config "
                + shquote(str(build_config_path(cfg)))
                + " --set-build-config "
                + shquote(f"{key}={value}")
            )
            updated = set_workbench_build_config(cfg, f"{key}={value}")
            print(f"set {updated.get('key', key)}={shell_double_quote(updated.get('value', value))}")
        except (ValueError, IndexError) as exc:
            print(exc)
    return True


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
    print(f"build option set: {rec.get('key', key)}")
    print(f"  value: {shell_double_quote(rec.get('value', value))}")
    print(f"  config: {rec.get('config_path', build_config_path(cfg))}")
    return rec


def unset_line_build_config(cfg, args):
    key = " ".join(args).strip()
    if not key:
        raise ValueError("usage: build unset KEY")
    rec = unset_workbench_build_config(cfg, key)
    print(f"build option unset: {rec.get('key', key)}")
    print(f"  config: {rec.get('config_path', build_config_path(cfg))}")
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
    print(f"global build option set: {rec.get('key', key)}")
    print(f"  value: {shell_double_quote(rec.get('value', text))}")
    return rec


def unset_line_global_build_option(cfg, name):
    key = str(name or "").strip()
    if not key:
        raise ValueError("usage: unsetg KEY")
    rec = unset_workbench_build_config(cfg, key)
    print(f"global build option unset: {rec.get('key', key)}")
    print(f"  config: {rec.get('config_path', build_config_path(cfg))}")
    return rec


def parse_line_build_command(cmd, args=None):
    if args is None:
        args = cmd
    else:
        if str(cmd or "").strip().lower() != "build":
            return None
    args = list(args or [])
    return {
        "action": "build",
        "args": args,
        "set_context": (
            not args
            or (len(args) == 1 and str(args[0]).lower() in {"-v", "--verbose", "verbose"})
        ),
    }


def dispatch_line_build_command(
    build_cmd,
    *,
    set_context_func=None,
    run_func=None,
):
    try:
        if build_cmd.get("set_context") and set_context_func:
            set_context_func("build")
        if run_func:
            return run_func(build_cmd.get("args") or [])
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported build command")


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
