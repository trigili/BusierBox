"""Operator workstation I/O helpers for grit-console."""

import os
import shlex
import shutil
import subprocess
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
