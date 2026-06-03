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


def print_line_build_config(cfg):
    fields = workbench_config_field_records(cfg)

    def _detail(rec):
        details = []
        if rec.get("label"):
            details.append(("note", rec["label"]))
        if rec.get("options"):
            details.append(("options", "  ".join(str(o) for o in rec["options"])))
        details.append(("set", f"build set {rec.get('key', '')} VALUE"))
        return details

    cols = [
        ("Key", "key"),
        ("Value", lambda r: shell_double_quote(str(r.get("value") or ""))),
        ("Category", lambda r: r.get("category") or "-"),
    ]
    console_table(
        f"Build config  ({build_config_path(cfg)})",
        fields,
        cols,
        detail_fn=_detail,
        footer="build set KEY VALUE  |  build unset KEY  |  build ? for help",
    )
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
    subcmd = str(args[0] if args else "").lower()
    if not subcmd or subcmd in {"list", "show", "options"}:
        print_line_build_config(cfg)
        return
    if subcmd == "set":
        set_line_build_config(cfg, args[1:])
        return
    if subcmd in {"unset", "clear"}:
        unset_line_build_config(cfg, args[1:])
        return
    raise ValueError("usage: build [list|set KEY VALUE|unset KEY]")
