"""Bringup subcommand dispatch for grit-console."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRINGUP = ROOT / "scripts" / "grit-bringup"


def handle_bringup_command(argv):
    return subprocess.run([str(BRINGUP), *list(argv or [])]).returncode
