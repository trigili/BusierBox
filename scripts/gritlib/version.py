"""Version helpers for griTTYkit scripts."""

import subprocess
from pathlib import Path


def grit_version(root=None):
    """Return version as MAJOR.MINOR.PATCH (patch = git commit count)."""
    repo_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    version_file = repo_root / "VERSION"
    base = "0.1"
    if version_file.is_file():
        base = version_file.read_text(encoding="utf-8").strip()
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_root), timeout=3,
        )
        if result.returncode == 0:
            return f"{base}.{result.stdout.strip()}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return base
