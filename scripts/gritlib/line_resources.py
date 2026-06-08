"""Line-console resource script and history helpers."""

import shlex
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.shell_utils import shquote


def parse_line_resource_command(cmd, args):
    name = str(cmd or "").strip().lower()
    values = [str(arg) for arg in (args or [])]
    if name == "history":
        return {
            "action": "history",
            "limit": values[0] if values else "",
        }
    if name == "resource":
        return {
            "action": "load",
            "path": " ".join(values).strip(),
        }
    if name == "makerc":
        return {
            "action": "save",
            "path": " ".join(values).strip(),
        }
    return None


def dispatch_line_resource_command(
    resource_cmd,
    *,
    history_func=None,
    load_func=None,
    save_func=None,
):
    action = (resource_cmd or {}).get("action")
    try:
        if action == "history" and history_func:
            return history_func(resource_cmd.get("limit", ""))
        if action == "load" and load_func:
            return load_func(resource_cmd.get("path", ""))
        if action == "save" and save_func:
            return save_func(resource_cmd.get("path", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported resource command")


def load_line_resource(cfg, path_text):
    text = str(path_text or "").strip()
    if not text:
        raise ValueError("usage: resource FILE")
    path = Path(text).expanduser()
    if not path.is_file():
        raise ValueError(f"resource file not found: {text}")
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"could not read resource file: {exc}") from exc
    commands = []
    skipped_nested = 0
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            args = shlex.split(line)
        except ValueError as exc:
            raise ValueError(f"resource parse error: {exc}") from exc
        if args and args[0].lower() == "resource":
            skipped_nested += 1
            continue
        commands.append(line)
        if len(commands) > 200:
            raise ValueError("resource file has more than 200 commands")
    suffix = f"; skipped {skipped_nested} nested resource line(s)" if skipped_nested else ""
    print(f"Resource loaded: {path}")
    print(f"  commands: {len(commands)}{suffix}")
    append_event(cfg, "workbench", "workbench_console_resource_loaded", details={
        "path": str(path),
        "command_count": len(commands),
        "skipped_nested_count": skipped_nested,
    })
    return commands


def write_line_makerc(cfg, path_text, line_history):
    text = str(path_text or "").strip()
    if not text:
        raise ValueError("usage: makerc FILE")
    path = Path(text).expanduser()
    commands = list(line_history or [])
    if commands and commands[-1].strip().lower().startswith("makerc "):
        commands = commands[:-1]
    if not commands:
        raise ValueError("command history is empty")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# griTTYkit operator console resource script\n"
            + "\n".join(commands)
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ValueError(f"could not write resource script: {exc}") from exc
    print(f"Resource script saved: {path}")
    print(f"  commands: {len(commands)}")
    print(f"replay: resource {shquote(str(path))}")
    append_event(cfg, "workbench", "workbench_console_makerc_saved", details={
        "path": str(path),
        "command_count": len(commands),
    })
    return path


def record_line_history(line_history, command, limit=100):
    text = str(command or "").strip()
    if not text:
        return
    line_history.append(text)
    if len(line_history) > limit:
        del line_history[:-limit]


def line_history_command(line_history, selector):
    text = str(selector or "").strip()
    if text == "!!":
        if not line_history:
            raise ValueError("history is empty")
        return line_history[-1]
    if text.startswith("!"):
        text = text[1:]
    if not text.isdigit():
        raise ValueError("usage: !N or repeat N")
    idx = int(text) - 1
    if idx < 0 or idx >= len(line_history):
        raise ValueError(f"history number out of range: {text}")
    return line_history[idx]


def print_line_history(line_history, limit_text=""):
    limit = 20
    text = str(limit_text or "").strip()
    if text:
        if not text.isdigit() or int(text) <= 0:
            raise ValueError("usage: history [LIMIT]")
        limit = int(text)
    print("Command history:")
    if not line_history:
        print("  none")
        return
    start = max(0, len(line_history) - limit)
    for idx, command in enumerate(line_history[start:], start + 1):
        print(f"  {idx}: {command}")
