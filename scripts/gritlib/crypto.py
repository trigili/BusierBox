"""Certificate and key generation helpers for grit-console services."""

import subprocess
from pathlib import Path


def generate_tls_cert(cert: Path, key: Path) -> bool:
    """Generate a self-signed TLS cert/key pair. Returns True on success."""
    cert.parent.mkdir(parents=True, exist_ok=True)
    log = cert.parent / "openssl-generate.log"
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key), "-out", str(cert),
        "-days", "3650", "-nodes", "-subj", "/CN=grit",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        log.write_text(
            f"command: {' '.join(cmd)}\nreturncode: {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            encoding="utf-8",
        )
        if result.returncode == 0 and cert.is_file() and key.is_file():
            key.chmod(0o600)
            return True
    except FileNotFoundError:
        log.write_text("openssl not found in PATH\n", encoding="utf-8")
    return False
