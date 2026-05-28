#!/usr/bin/env python3
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(port, proc):
    deadline = time.time() + 5
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server exited before accepting uploads")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not open upload port")


def main():
    bb = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dist/busierbox-native-full")
    with tempfile.TemporaryDirectory(prefix="busierbox-upload.") as td:
        tmp = pathlib.Path(td)
        session_root = tmp / "sessions"
        cfg = tmp / "server.json"
        port = free_port()
        cfg.write_text(
            json.dumps(
                {
                    "listen_host": "127.0.0.1",
                    "session_root": str(session_root),
                    "file_service_enable": "yes",
                    "file_service_port": port,
                    "file_service_tls": "no",
                }
            ),
            encoding="utf-8",
        )
        server = subprocess.Popen(
            [
                str(ROOT / "scripts/busierbox-server"),
                "--config",
                str(cfg),
                "--file-service",
                "--timeout",
                "5",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_port(port, server)
            sample = tmp / "target-evidence.txt"
            sample.write_text("operator upload smoke\n", encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "BB_OPERATOR_SERVER_HOST": "127.0.0.1",
                    "BB_OPERATOR_FILE_SERVICE_PORT": str(port),
                    "BB_OPERATOR_FILE_SERVICE_TLS": "no",
                }
            )
            help_checks = [
                ([str(bb), "config-push", "--help"], "usage: busierbox config-push"),
                ([str(bb), "evidence", "push", "--help"], "usage: busierbox evidence push"),
                ([str(bb), "survey", "push", "--help"], "usage: busierbox survey push"),
                ([str(bb), "manifest", "push", "--help"], "usage: busierbox manifest push"),
                ([str(bb), "reality-test", "push", "--help"], "usage: busierbox reality-test push"),
            ]
            for cmd, expected in help_checks:
                result = subprocess.run(
                    cmd,
                    cwd=ROOT,
                    env=env,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if expected not in result.stdout:
                    raise SystemExit(f"operator-upload: help output missing {expected!r}")
            commands = [
                [str(bb), "put", str(sample), "--quiet"],
                [str(bb), "config-push", "--quiet"],
                [str(bb), "evidence", "push", "--quiet"],
                [str(bb), "survey", "push", "--quiet"],
                [str(bb), "manifest", "push", "--quiet"],
                [str(bb), "reality-test", "push", "--quiet"],
            ]
            for cmd in commands:
                subprocess.run(
                    cmd,
                    cwd=ROOT,
                    env=env,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            deadline = time.time() + 5
            while time.time() < deadline:
                files = list(session_root.glob("*/files/*"))
                names = {p.name for p in files if not p.name.endswith(".metadata.json")}
                if {
                    "target-evidence.txt",
                    "busierbox-config.json",
                    "busierbox-evidence.json",
                    "busierbox-survey.json",
                    "busierbox-manifest.json",
                    "busierbox-reality-test.json",
                }.issubset(names):
                    break
                time.sleep(0.05)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server.kill()

        uploaded = list(session_root.glob("*/files/target-evidence.txt"))
        if len(uploaded) != 1:
            raise SystemExit("operator-upload: uploaded file not found")
        if uploaded[0].read_text(encoding="utf-8") != "operator upload smoke\n":
            raise SystemExit("operator-upload: uploaded content mismatch")
        meta = json.loads(uploaded[0].with_name("target-evidence.txt.metadata.json").read_text(encoding="utf-8"))
        assert meta["source_path"].endswith("target-evidence.txt")
        assert meta["upload_kind"] == "file"
        assert meta["size"] == len("operator upload smoke\n")
        assert meta["transfer_status"] == "ok"
        assert len(meta["sha256"]) == 64
        expected_kinds = {
            "busierbox-config.json": "config",
            "busierbox-evidence.json": "evidence",
            "busierbox-survey.json": "survey",
            "busierbox-manifest.json": "manifest",
            "busierbox-reality-test.json": "reality-test",
        }
        for expected, upload_kind in expected_kinds.items():
            matches = list(session_root.glob(f"*/files/{expected}"))
            if len(matches) != 1:
                raise SystemExit(f"operator-upload: {expected} not found")
            generated_meta = json.loads(matches[0].with_name(f"{expected}.metadata.json").read_text(encoding="utf-8"))
            if generated_meta.get("upload_kind") != upload_kind:
                raise SystemExit(f"operator-upload: {expected} metadata kind mismatch")
            doc = json.loads(matches[0].read_text(encoding="utf-8"))
            if expected == "busierbox-config.json":
                if doc.get("schema") != 1 or doc.get("kind") != "config" or "runtime" not in doc or "effective_config" not in doc:
                    raise SystemExit("operator-upload: config-push uploaded invalid report")
            elif expected == "busierbox-evidence.json":
                if doc.get("schema") != 1 or doc.get("kind") != "evidence" or "runtime" not in doc or "rshell" not in doc:
                    raise SystemExit("operator-upload: evidence push uploaded invalid report")
            elif expected == "busierbox-survey.json":
                if doc.get("schema") != 2 or "busierbox" not in doc or "recommendations" not in doc:
                    raise SystemExit("operator-upload: survey push uploaded invalid report")
            elif expected == "busierbox-manifest.json":
                if doc.get("schema") != 1 or "busierbox" not in doc or "payload" not in doc or "operator_services" not in doc:
                    raise SystemExit("operator-upload: manifest push uploaded invalid report")
            elif expected == "busierbox-reality-test.json":
                if doc.get("schema") != 1 or "checks" not in doc or "summary" not in doc:
                    raise SystemExit("operator-upload: reality-test push uploaded invalid report")
    print("operator-upload ok")


if __name__ == "__main__":
    main()
