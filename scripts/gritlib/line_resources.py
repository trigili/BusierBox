"""Line-console resource script and history helpers."""

import shlex
from pathlib import Path

from gritlib.event_log import append_event
from gritlib.shell_utils import shquote


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
    print(f"Resource loaded: {path} commands={len(commands)} skipped_nested={skipped_nested}")
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
    print(f"Resource script saved: {path} commands={len(commands)}")
    print(f"replay: resource {shquote(str(path))}")
    append_event(cfg, "workbench", "workbench_console_makerc_saved", details={
        "path": str(path),
        "command_count": len(commands),
    })
    return path


def record_line_history(line_history, command, readline_module=None, limit=100):
    text = str(command or "").strip()
    if not text:
        return
    line_history.append(text)
    if len(line_history) > limit:
        del line_history[:-limit]
    if readline_module is not None:
        try:
            n = readline_module.get_current_history_length()
            if n == 0 or readline_module.get_history_item(n) != text:
                readline_module.add_history(text)
        except Exception:
            pass


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
