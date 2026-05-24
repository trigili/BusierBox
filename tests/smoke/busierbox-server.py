#!/usr/bin/env python3
"""Tests for scripts/busierbox-server UX, parsing, and session flow."""

import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = REPO / "scripts" / "busierbox-server"


def load_server_module():
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("busierbox_server", str(SERVER_SCRIPT))
    spec = importlib.util.spec_from_loader("busierbox_server", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


srv = load_server_module()

PROTOCOL = "busierbox-stager-v1"


# ── fake-stager helpers ────────────────────────────────────────────────────────

def pack_frame(obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    return struct.pack(">I", len(data)) + data


def send_obj(sock, obj):
    sock.sendall(pack_frame(obj))


def recv_obj(sock):
    raw = b""
    while len(raw) < 4:
        chunk = sock.recv(4 - len(raw))
        if not chunk:
            raise EOFError
        raw += chunk
    n = struct.unpack(">I", raw)[0]
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return json.loads(data.decode())


def make_hello(token="tok", auto_exec="doctor"):
    return {
        "type": "hello",
        "protocol": PROTOCOL,
        "token": token,
        "stager_version": "dev",
        "target": "mipsel-linux-4.x-musl",
        "auto_exec": auto_exec,
        "output_path": "/tmp/busierbox-full",
        "survey": {
            "uname_machine": "mips",
            "uname_release": "5.10.176",
            "uname_sysname": "Linux",
            "endianness": "little",
            "pointer_width": 32,
            "uid": 0,
            "euid": 0,
            "devpts_exists": True,
            "ptrace": "unknown",
            "dirs": [
                {"path": ".", "exists": True, "writable": True,
                 "executable": True, "free_bytes": 113_000_000},
            ],
            "interfaces": [],
            "recommendations": {
                "payload_mode_possible": True,
                "recommended_extract_dir": "/tmp",
                "likely_tuple": "mipsel-linux-4.x-musl",
            },
        },
    }


def find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── unit tests: parsing ────────────────────────────────────────────────────────

class TestParseDoctorKv(unittest.TestCase):
    def test_real_output(self):
        text = (
            "embedded_payload=yes\n"
            "embedded_format=tgz\n"
            "embedded_size=5793681\n"
            "embedded_hash_ok=yes\n"
            "extracted_payload=yes\n"
            "payload_identity_match=yes\n"
            "busybox_applets_count=78\n"
            "staged_tools=[curl,dbclient,dropbear,file,zsh]\n"
            "missing_tools=[htop,ripgrep]\n"
            "missing_tool_reasons={htop=no provider,ripgrep=no provider}\n"
            "overlay_enabled=yes\n"
            "overlay_tools=[]\n"
            "artifact_tier=full\n"
            "embedded_version=dev\n"
        )
        kv = srv.parse_doctor_kv(text)
        self.assertEqual(kv["embedded_payload"], "yes")
        self.assertEqual(kv["embedded_hash_ok"], "yes")
        self.assertEqual(kv["busybox_applets_count"], "78")
        self.assertEqual(kv["artifact_tier"], "full")

    def test_identity_mismatch(self):
        text = "payload_identity_match=no (stale or different binary)\n"
        kv = srv.parse_doctor_kv(text)
        self.assertEqual(kv["payload_identity_match"], "no (stale or different binary)")

    def test_empty(self):
        kv = srv.parse_doctor_kv("")
        self.assertEqual(kv, {})

    def test_no_kv_lines(self):
        kv = srv.parse_doctor_kv("dummy doctor ok\nsome output\n")
        self.assertEqual(kv, {})


class TestParseListField(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(srv.parse_list_field("[a,b,c]"), ["a", "b", "c"])

    def test_empty(self):
        self.assertEqual(srv.parse_list_field("[]"), [])

    def test_none(self):
        self.assertEqual(srv.parse_list_field(None), [])

    def test_spaces(self):
        self.assertEqual(srv.parse_list_field("[ curl , zsh ]"), ["curl", "zsh"])


class TestParseDictField(unittest.TestCase):
    def test_basic(self):
        d = srv.parse_dict_field("{htop=no provider,ripgrep=no provider}")
        self.assertEqual(d["htop"], "no provider")
        self.assertEqual(d["ripgrep"], "no provider")

    def test_empty(self):
        self.assertEqual(srv.parse_dict_field("{}"), {})

    def test_none(self):
        self.assertEqual(srv.parse_dict_field(None), {})


class TestLikelyTuple(unittest.TestCase):
    def test_mipsel(self):
        survey = {"uname_machine": "mips", "endianness": "little",
                  "recommendations": {}}
        self.assertEqual(srv.likely_tuple(survey), "mipsel-linux-4.x-musl")

    def test_mips_big(self):
        survey = {"uname_machine": "mips", "endianness": "big",
                  "recommendations": {}}
        self.assertEqual(srv.likely_tuple(survey), "mips-linux-4.x-musl")

    def test_aarch64(self):
        survey = {"uname_machine": "aarch64", "endianness": "little",
                  "recommendations": {}}
        self.assertEqual(srv.likely_tuple(survey), "aarch64-linux-4.x-musl")

    def test_explicit_recommendation(self):
        survey = {"uname_machine": "mips", "endianness": "little",
                  "recommendations": {"likely_tuple": "mipsel-linux-4.x-musl"}}
        self.assertEqual(srv.likely_tuple(survey), "mipsel-linux-4.x-musl")


class TestBuildRecommendedConfig(unittest.TestCase):
    def test_mipsel(self):
        hello = {"survey": {
            "uname_machine": "mips", "endianness": "little",
            "uname_release": "5.10.176",
            "recommendations": {"likely_tuple": "mipsel-linux-4.x-musl"},
        }}
        cfg = srv.build_recommended_config(hello)
        self.assertIn('BB_TARGET_ARCH="mipsel"', cfg)
        self.assertIn('BB_TARGET_ENDIAN="little"', cfg)
        self.assertIn('BB_TARGET_LIBC="musl"', cfg)
        self.assertIn('BB_KERNEL_FLOOR="4.x"', cfg)
        self.assertIn('BB_PAYLOAD_TIER="operator"', cfg)
        self.assertIn('BB_TARGET_PRESET="glinet-mt7621-openwrt-musl"', cfg)
        self.assertIn("Generated by scripts/busierbox-server", cfg)

    def test_aarch64(self):
        hello = {"survey": {
            "uname_machine": "aarch64", "endianness": "little",
            "uname_release": "5.15.0",
            "recommendations": {"likely_tuple": "aarch64-linux-4.x-musl"},
        }}
        cfg = srv.build_recommended_config(hello)
        self.assertIn('BB_TARGET_ARCH="aarch64"', cfg)


class TestPrintDoctorSummary(unittest.TestCase):
    def test_full_output_no_crash(self):
        kv = {
            "embedded_payload": "yes",
            "embedded_format": "tgz",
            "embedded_size": "5793681",
            "embedded_hash_ok": "yes",
            "extracted_payload": "yes",
            "payload_identity_match": "yes",
            "busybox_applets_count": "78",
            "staged_tools": "[curl,dbclient,dropbear,file,zsh]",
            "missing_tools": "[htop,ripgrep]",
            "missing_tool_reasons": "{htop=no provider,ripgrep=no provider}",
            "overlay_enabled": "yes",
            "overlay_tools": "[]",
            "artifact_tier": "full",
            "embedded_version": "dev",
        }
        staged = srv.print_doctor_summary(kv)
        self.assertIn("curl", staged)
        self.assertIn("dropbear", staged)

    def test_identity_mismatch_shown(self):
        kv = {
            "embedded_payload": "yes",
            "embedded_format": "tgz",
            "embedded_size": "1000",
            "embedded_hash_ok": "yes",
            "extracted_payload": "yes",
            "payload_identity_match": "no (stale)",
            "busybox_applets_count": "10",
            "staged_tools": "[]",
            "missing_tools": "[]",
            "missing_tool_reasons": "{}",
            "overlay_enabled": "no",
            "overlay_tools": "[]",
            "artifact_tier": "full",
            "embedded_version": "dev",
        }
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            srv.print_doctor_summary(kv)
        out = buf.getvalue()
        self.assertIn("no (stale)", out)

    def test_missing_tools_listed(self):
        kv = {
            "embedded_payload": "yes",
            "embedded_format": "tgz",
            "embedded_size": "1000",
            "embedded_hash_ok": "yes",
            "extracted_payload": "yes",
            "payload_identity_match": "yes",
            "busybox_applets_count": "10",
            "staged_tools": "[]",
            "missing_tools": "[htop,ltrace]",
            "missing_tool_reasons": "{htop=no provider,ltrace=no provider}",
            "overlay_enabled": "no",
            "overlay_tools": "[]",
            "artifact_tier": "full",
            "embedded_version": "dev",
        }
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            srv.print_doctor_summary(kv)
        out = buf.getvalue()
        self.assertIn("htop", out)
        self.assertIn("ltrace", out)
        self.assertIn("no provider", out)


# ── integration tests: server subprocess ─────────────────────────────────────

class TestServerArgValidation(unittest.TestCase):
    """Test argparse-level startup validation (no session needed)."""

    def _run(self, *extra_args):
        proc = subprocess.run(
            [sys.executable, str(SERVER_SCRIPT)] + list(extra_args),
            capture_output=True, text=True, timeout=5,
        )
        return proc

    def test_send_without_artifact_fails(self):
        proc = self._run("--send", "--listen", "127.0.0.1:1", "--once")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--artifact", proc.stderr)

    def test_missing_artifact_path_fails(self):
        proc = self._run("--artifact", "/nonexistent/path", "--once")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("artifact not found", proc.stderr)

    def test_survey_only_and_start_operator_session_conflict(self):
        proc = self._run("--survey-only", "--start-operator-session", "--once")
        self.assertNotEqual(proc.returncode, 0)


class TestServerSession(unittest.TestCase):
    """Integration tests that spin up the server and connect as a fake stager."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.orig_dir = os.getcwd()
        os.chdir(self.tmp)
        # Create a dummy artifact
        self.artifact = self.tmp / "dummy-full"
        self.artifact.write_text(
            "#!/bin/sh\n"
            "case \"${1:-}\" in\n"
            "  extract) echo 'extract ok'; exit 0 ;;\n"
            "  doctor) printf 'embedded_payload=yes\\nembedded_format=tgz\\n"
            "embedded_size=1000\\nembedded_hash_ok=yes\\n"
            "extracted_payload=yes\\npayload_identity_match=yes\\n"
            "busybox_applets_count=5\\n"
            "staged_tools=[dropbear,dbclient,curl]\\n"
            "missing_tools=[]\\nmissing_tool_reasons={}\\n"
            "overlay_enabled=no\\noverlay_tools=[]\\n"
            "artifact_tier=full\\nembedded_version=dev\\n'; exit 0 ;;\n"
            "  *) echo 'full artifact'; exit 0 ;;\n"
            "esac\n"
        )
        self.artifact.chmod(0o755)
        self.received = self.tmp / "received-full"

    def tearDown(self):
        os.chdir(self.orig_dir)
        self.tmpdir.cleanup()

    def _start_server(self, port, token, extra_args=()):
        cmd = [
            sys.executable, str(SERVER_SCRIPT),
            "--listen", f"127.0.0.1:{port}",
            "--token", token,
            "--artifact", str(self.artifact),
            "--remote-path", str(self.received),
            "--send", "--exec-doctor", "--yes", "--once", "--timeout", "10",
        ] + list(extra_args)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        return proc

    def _connect_as_stager(self, port, hello):
        deadline = time.time() + 5
        sock = None
        while time.time() < deadline:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)
        if sock is None:
            raise RuntimeError(f"could not connect to server on port {port}")
        return sock

    def _fake_stager_exchange(self, port, token, auto_exec="doctor",
                               extract_exit=0, doctor_stdout=None):
        """Connect as fake stager, exchange frames, return (server_log, frames)."""
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            hello = make_hello(token=token, auto_exec=auto_exec)
            send_obj(sock, hello)
            frames = []
            while True:
                msg = recv_obj(sock)
                frames.append(msg)
                mtype = msg.get("type")
                if mtype == "close":
                    break
                elif mtype == "send_file":
                    # Accept the file bytes
                    size = msg.get("size", 0)
                    received = b""
                    while len(received) < size:
                        chunk = sock.recv(size - len(received))
                        if not chunk:
                            break
                        received += chunk
                    # Write received bytes so sha256 check passes
                    path = str(self.received)
                    with open(path, "wb") as f:
                        f.write(received)
                    import hashlib
                    h = hashlib.sha256(received).hexdigest()
                    os.chmod(path, 0o755)
                    send_obj(sock, {
                        "type": "result", "action": "send_file",
                        "ok": True, "sha256_ok": True, "sha256": h,
                        "message": "wrote file",
                    })
                elif mtype == "exec":
                    argv = msg.get("argv", [])
                    subcmd = argv[1] if len(argv) > 1 else ""
                    if subcmd == "extract" or (len(argv) > 2 and argv[2] == "--force"):
                        send_obj(sock, {
                            "type": "result", "action": "exec",
                            "ok": extract_exit == 0,
                            "exit_code": extract_exit,
                            "stdout": "extract ok\n" if extract_exit == 0 else "extract failed\n",
                            "stderr": "",
                        })
                    elif subcmd == "doctor":
                        out = doctor_stdout or (
                            "embedded_payload=yes\nembedded_format=tgz\n"
                            "embedded_size=1000\nembedded_hash_ok=yes\n"
                            "extracted_payload=yes\npayload_identity_match=yes\n"
                            "busybox_applets_count=5\n"
                            "staged_tools=[dropbear,dbclient,curl]\n"
                            "missing_tools=[]\nmissing_tool_reasons={}\n"
                            "overlay_enabled=no\noverlay_tools=[]\n"
                            "artifact_tier=full\nembedded_version=dev\n"
                        )
                        send_obj(sock, {
                            "type": "result", "action": "exec",
                            "ok": True, "exit_code": 0,
                            "stdout": out, "stderr": "",
                        })
                    else:
                        send_obj(sock, {
                            "type": "result", "action": "exec",
                            "ok": True, "exit_code": 0,
                            "stdout": "ok\n", "stderr": "",
                        })
        return frames

    def test_survey_only_mode_no_artifact(self):
        """Server with no --artifact runs survey-only, no traceback."""
        port = find_free_port()
        cmd = [
            sys.executable, str(SERVER_SCRIPT),
            "--listen", f"127.0.0.1:{port}",
            "--token", "tok",
            "--yes", "--once", "--timeout", "10",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        time.sleep(0.3)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                send_obj(sock, make_hello(token="tok"))
                msg = recv_obj(sock)
                # Server should send close (survey-only)
                self.assertEqual(msg.get("type"), "close")
        finally:
            proc.wait(timeout=5)
        log = proc.stdout.read()
        self.assertIn("Token OK", log)
        self.assertIn("survey-only mode", log)
        self.assertNotIn("Traceback", log)
        self.assertNotIn("RuntimeError", log)

    def test_survey_saved(self):
        """survey.json and recommended.conf are written to session directory."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        sessions = sorted(
            (self.tmp / ".busierbox-server" / "sessions").glob("*"),
            key=lambda p: p.stat().st_mtime,
        )
        self.assertTrue(sessions, "no session directories created")
        sdir = sessions[-1]
        self.assertTrue((sdir / "survey.json").exists(), "survey.json missing")
        self.assertTrue((sdir / "recommended.conf").exists(), "recommended.conf missing")
        self.assertTrue((sdir / "hello.json").exists(), "hello.json missing")
        self.assertTrue((sdir / "summary.txt").exists(), "summary.txt missing")
        self.assertTrue((sdir / "session.jsonl").exists(), "session.jsonl missing")
        self.assertTrue((sdir / "artifact.json").exists(), "artifact.json missing")
        self.assertTrue((sdir / "doctor.txt").exists(), "doctor.txt missing")

        survey = json.loads((sdir / "survey.json").read_text())
        self.assertEqual(survey.get("uname_machine"), "mips")

        cfg = (sdir / "recommended.conf").read_text()
        self.assertIn("BB_TARGET_ARCH", cfg)

    def test_extract_force_before_doctor(self):
        """Server sends extract --force before doctor by default."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            frames = self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        exec_frames = [f for f in frames if f.get("type") == "exec"]
        # Should have at least two execs: extract and doctor
        self.assertGreaterEqual(len(exec_frames), 2)
        first_exec = exec_frames[0]
        self.assertIn("extract", first_exec.get("argv", []))

    def test_extract_failure_stops_doctor(self):
        """If extract --force fails, doctor is not run."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            frames = self._fake_stager_exchange(port, "tok", extract_exit=1)
        finally:
            proc.wait(timeout=10)
        exec_frames = [f for f in frames if f.get("type") == "exec"]
        argv_sets = [f.get("argv", []) for f in exec_frames]
        # doctor should not have been run
        doctor_ran = any("doctor" in argv for argv in argv_sets)
        self.assertFalse(doctor_ran, "doctor ran despite extract failure")

    def test_no_force_extract_flag(self):
        """--no-force-extract-before-doctor skips the extract step."""
        port = find_free_port()
        proc = self._start_server(port, "tok",
                                   extra_args=["--no-force-extract-before-doctor"])
        time.sleep(0.3)
        try:
            frames = self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        exec_frames = [f for f in frames if f.get("type") == "exec"]
        self.assertEqual(len(exec_frames), 1, "expected exactly one exec (doctor)")
        self.assertIn("doctor", exec_frames[0].get("argv", []))

    def test_wrong_token_rejected_cleanly(self):
        """Wrong token results in clean reject, no traceback."""
        port = find_free_port()
        proc = self._start_server(port, "correct-token")
        time.sleep(0.3)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                send_obj(sock, make_hello(token="wrong-token"))
                msg = recv_obj(sock)
                self.assertEqual(msg.get("type"), "close")
                self.assertIn("token", msg.get("error", ""))
        finally:
            proc.wait(timeout=10)
        log = proc.stdout.read()
        self.assertIn("rejected", log)
        self.assertNotIn("Traceback", log)

    def test_operator_session_unavailable_without_tools(self):
        """Operator session is reported unavailable if dropbear/dbclient not staged."""
        port = find_free_port()
        doctor_no_dropbear = (
            "embedded_payload=yes\nembedded_format=tgz\n"
            "embedded_size=1000\nembedded_hash_ok=yes\n"
            "extracted_payload=yes\npayload_identity_match=yes\n"
            "busybox_applets_count=5\n"
            "staged_tools=[curl,file]\n"
            "missing_tools=[dropbear,dbclient]\n"
            "missing_tool_reasons={dropbear=no provider,dbclient=no provider}\n"
            "overlay_enabled=no\noverlay_tools=[]\n"
            "artifact_tier=full\nembedded_version=dev\n"
        )
        cmd = [
            sys.executable, str(SERVER_SCRIPT),
            "--listen", f"127.0.0.1:{port}",
            "--token", "tok",
            "--artifact", str(self.artifact),
            "--remote-path", str(self.received),
            "--send", "--exec-doctor", "--yes",
            "--start-operator-session",
            "--operator-server-host", "127.0.0.1",
            "--once", "--timeout", "10",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        time.sleep(0.3)
        try:
            self._fake_stager_exchange(port, "tok", doctor_stdout=doctor_no_dropbear)
        finally:
            proc.wait(timeout=10)
        log = proc.stdout.read()
        self.assertIn("unavailable", log)
        self.assertNotIn("Traceback", log)

    def test_operator_session_command_sent_when_tools_present(self):
        """When dropbear+dbclient staged and --start-operator-session, exec is sent."""
        port = find_free_port()
        doctor_with_tools = (
            "embedded_payload=yes\nembedded_format=tgz\n"
            "embedded_size=1000\nembedded_hash_ok=yes\n"
            "extracted_payload=yes\npayload_identity_match=yes\n"
            "busybox_applets_count=5\n"
            "staged_tools=[dropbear,dbclient,curl]\n"
            "missing_tools=[]\nmissing_tool_reasons={}\n"
            "overlay_enabled=no\noverlay_tools=[]\n"
            "artifact_tier=full\nembedded_version=dev\n"
        )
        cmd = [
            sys.executable, str(SERVER_SCRIPT),
            "--listen", f"127.0.0.1:{port}",
            "--token", "tok",
            "--artifact", str(self.artifact),
            "--remote-path", str(self.received),
            "--send", "--exec-doctor", "--yes",
            "--start-operator-session",
            "--operator-server-host", "192.168.8.100",
            "--operator-server-user", "jared",
            "--operator-remote-forward-port", "2200",
            "--once", "--timeout", "10",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        time.sleep(0.3)
        try:
            frames = self._fake_stager_exchange(
                port, "tok", doctor_stdout=doctor_with_tools
            )
        finally:
            proc.wait(timeout=10)
        log = proc.stdout.read()
        exec_frames = [f for f in frames if f.get("type") == "exec"]
        # There should be an exec with /bin/sh for the operator session
        op_frames = [f for f in exec_frames
                     if f.get("argv") and "/bin/sh" in f["argv"]]
        self.assertTrue(op_frames, "operator session exec not sent")
        sh_cmd = op_frames[0]["argv"][2]
        self.assertIn("dropbear", sh_cmd)
        self.assertIn("dbclient", sh_cmd)
        self.assertIn("192.168.8.100", sh_cmd)
        self.assertIn("jared", sh_cmd)

    def test_session_log_printed(self):
        """Session log path is printed after session."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        log = proc.stdout.read()
        self.assertIn("Session log:", log)

    def test_doctor_pretty_output(self):
        """Doctor pretty output is printed for structured doctor output."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        log = proc.stdout.read()
        self.assertIn("Full artifact doctor:", log)
        self.assertIn("embedded payload:", log)
        self.assertNotIn("Traceback", log)

    def test_extract_txt_written(self):
        """extract.txt is written to session directory."""
        port = find_free_port()
        proc = self._start_server(port, "tok")
        time.sleep(0.3)
        try:
            self._fake_stager_exchange(port, "tok")
        finally:
            proc.wait(timeout=10)
        sessions = sorted(
            (self.tmp / ".busierbox-server" / "sessions").glob("*"),
            key=lambda p: p.stat().st_mtime,
        )
        sdir = sessions[-1]
        self.assertTrue((sdir / "extract.txt").exists(), "extract.txt missing")


# ── stager protocol extension: exec_background (unit) ─────────────────────────

class TestBuildOperatorSessionSh(unittest.TestCase):
    def _make_args(self):
        import argparse
        ns = argparse.Namespace(
            operator_target_dropbear_port=2222,
            operator_target_bind_host="127.0.0.1",
            operator_server_host="192.168.1.100",
            operator_server_ssh_port=22,
            operator_server_user="operator",
            operator_remote_forward_port=2200,
        )
        return ns

    def test_contains_dropbear(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        self.assertIn("dropbear", cmd)

    def test_contains_dbclient(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        self.assertIn("dbclient", cmd)

    def test_contains_server_host(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        self.assertIn("192.168.1.100", cmd)

    def test_contains_forward_port(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        self.assertIn("2200", cmd)

    def test_host_key_generation(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        self.assertIn("dropbearkey", cmd)

    def test_backgrounded(self):
        args = self._make_args()
        cmd = srv.build_operator_session_sh(args, "/tmp/busierbox-full")
        # Must background the processes
        self.assertIn("&", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
