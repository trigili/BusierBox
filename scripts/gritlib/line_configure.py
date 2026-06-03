"""Line-console config generation helpers."""

import subprocess
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


def run_config_from_survey(survey_path, write_config_path, extra_args):
    """Run config-from-survey script and return the subprocess result."""
    scripts_dir = Path(__file__).resolve().parents[1]
    script = scripts_dir / "lib" / "config-from-survey"
    if not script.is_file():
        script = Path("scripts/lib/config-from-survey")
    if not script.is_file():
        raise ValueError("config-from-survey script not found")
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
