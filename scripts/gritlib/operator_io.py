"""Operator workstation I/O helpers for grit-console."""

import os
import shlex
import shutil
import subprocess
import sys
import termios
import tty
from pathlib import Path

from .shell_utils import shquote


def pager_command():
    configured = os.environ.get("PAGER", "").strip()
    candidates = []
    if configured:
        try:
            candidates.append(shlex.split(configured))
        except ValueError:
            candidates.append([configured])
    candidates.extend((["less", "-R"], ["more"]))
    for cmd in candidates:
        if not cmd:
            continue
        exe = cmd[0]
        if "/" in exe:
            if os.access(exe, os.X_OK):
                return cmd
            continue
        if shutil.which(exe):
            return cmd
    return None


def viewable_path(path):
    candidate = Path(str(path or "")).expanduser()
    if candidate.is_dir():
        for name in ("session.json", "events.jsonl"):
            child = candidate / name
            if child.is_file():
                return child
        return None
    if candidate.is_file():
        return candidate
    return None


def open_path_in_pager(path):
    target = viewable_path(path)
    if not target:
        return f"no viewable local file: {path}"
    cmd = pager_command()
    if not cmd:
        return f"no pager found for: {target}"
    subprocess.run(cmd + [str(target)], check=False)
    return f"viewed {target}"


def set_interactive_tty_raw():
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    return old


def restore_interactive_tty(old):
    if old is None:
        return
    try:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
    except termios.error:
        pass


def clipboard_command():
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def view_path_headless_command(cfg, path, default_config=Path("local/server-config.json")):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --view-path "
        + shquote(str(path or ""))
    )


def parse_line_view_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    if cmd not in {"view", "cat", "less"}:
        return {}
    return {"action": "view", "path": " ".join(args or []).strip()}


def dispatch_line_view_command(view_cmd, *, view_func=None):
    try:
        if view_func:
            return view_func((view_cmd or {}).get("path", ""))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported view command")


def view_line_path(cfg, path_text, append_event_fn=None, via=""):
    path = str(path_text or "").strip()
    if not path:
        raise ValueError("usage:\n  view PATH")
    headless = view_path_headless_command(cfg, path)
    result = open_path_in_pager(path)
    print(result)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_path_viewed", details={
            "headless_command": headless,
            "path": path,
            "result": result,
            "via": via,
            "viewable": viewable_path(path) is not None,
        })
    return result
