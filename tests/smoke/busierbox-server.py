#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def main():
    help_out = run("scripts/busierbox-server", "--help")
    if help_out.returncode != 0:
        print(help_out.stderr, file=sys.stderr)
        return 1
    forbidden = ("--artifact", "--send", "--token", "send_file", "stager")
    combined = help_out.stdout + help_out.stderr
    for word in forbidden:
        if word in combined:
            print(f"old server protocol surfaced in help: {word}", file=sys.stderr)
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "server-config.json"
        cfg.write_text(json.dumps({
            "transport": "socat-tls",
            "listen_host": "127.0.0.1",
            "socat_listen_port": 1,
            "session_root": str(Path(tmp) / "sessions"),
            "tls_cert": str(Path(tmp) / "missing.crt"),
            "tls_key": str(Path(tmp) / "missing.key"),
        }), encoding="utf-8")
        result = run("scripts/busierbox-server", "--config", str(cfg),
                     "--transport", "socat-tls", "--timeout", "0.1")
        if result.returncode != 2 or "TLS cert/key missing" not in result.stderr:
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 1

    print("busierbox-server smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
