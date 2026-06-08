"""Bringup subcommand dispatch for grit-console."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRINGUP = ROOT / "scripts" / "lib" / "bringup"


def handle_bringup_command(argv):
    env = os.environ.copy()
    env.setdefault("GRIT_BRINGUP_PROGRAM", f"{sys.argv[0]} bringup")
    return subprocess.run([str(BRINGUP), *list(argv or [])], env=env).returncode
