"""Line-console config generation helpers."""

import os
import subprocess
import sys
from pathlib import Path

from gritlib.shell_utils import shquote


def parse_line_config_args(args, cmd_name):
    survey_path = None
    write_config_path = None
    extra_args = []
    i = 0
    while i < len(args):
        arg = str(args[i])
        if arg in {"--write-config", "-w"} and i + 1 < len(args):
            write_config_path = str(args[i + 1])
            i += 2
        elif arg.startswith("--write-config="):
            write_config_path = arg.split("=", 1)[1]
            i += 1
        elif arg in {
            "--prefer-rshell",
            "--prefer-runtime",
            "--target-preset",
            "--payload-preset",
            "--reality-json",
        } and i + 1 < len(args):
            extra_args.extend([arg, str(args[i + 1])])
            i += 2
        elif arg in {"--allow-network-autorun", "--allow-external-writes"}:
            extra_args.append(arg)
            i += 1
        elif not arg.startswith("-"):
            survey_path = arg
            i += 1
        else:
            raise ValueError(
                f"unknown option: {arg}\n"
                f"usage: {cmd_name} [PATH] [--write-config FILE] "
                "[--prefer-rshell auto|ssh|...] [--prefer-runtime auto|...]"
            )
    return survey_path, write_config_path, extra_args


def _config_from_survey_candidates(search_roots=None):
    seen = set()

    def _add(path):
        path = Path(path)
        text = str(path)
        if text in seen:
            return
        seen.add(text)
        candidates.append(path)

    candidates = []
    override = os.environ.get("GRIT_CONFIG_FROM_SURVEY")
    if override:
        _add(override)
    module_dir = Path(__file__).resolve().parent
    argv_dir = Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd()
    roots = [
        *(Path(root) for root in (search_roots or [])),
        module_dir.parent,
        module_dir.parent.parent,
        argv_dir,
        argv_dir.parent,
        Path.cwd(),
    ]
    for root in roots:
        _add(root / "lib" / "config-from-survey")
        _add(root / "scripts" / "lib" / "config-from-survey")
        _add(root / "config-from-survey")
    return candidates


def find_config_from_survey(search_roots=None):
    for candidate in _config_from_survey_candidates(search_roots):
        if candidate.is_file():
            return candidate
    return None


def run_config_from_survey(survey_path, write_config_path, extra_args, search_roots=None):
    """Run config-from-survey script and return the subprocess result."""
    script = find_config_from_survey(search_roots)
    if not script:
        searched = ", ".join(str(path) for path in _config_from_survey_candidates(search_roots)[:6])
        raise ValueError(f"config-from-survey script not found (searched: {searched})")
    cmd = [str(script), "--format", "shell"] + list(extra_args or [])
    if write_config_path:
        cmd.extend(["--write-config", write_config_path])
    cmd.append(survey_path)
    print(f"Running: {' '.join(shquote(str(arg)) for arg in cmd)}")
    print("")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    if result.returncode != 0:
        raise ValueError(f"config-from-survey exited {result.returncode}")
    return result
