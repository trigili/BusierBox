"""Probe result persistence helpers for grit-console."""

from pathlib import Path

from gritlib.session_state import atomic_write_json, read_json_file


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")


def probe_results_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "probe-results.json"


def append_probe_result(cfg, result):
    path = probe_results_path(cfg)
    data = read_json_file(path, {"schema": 1, "results": []})
    if not isinstance(data.get("results"), list):
        data["results"] = []
    data["results"].append(result)
    atomic_write_json(path, data)
    return path


def probe_all_results(cfg):
    path = probe_results_path(cfg)
    if not path.is_file():
        return []
    data = read_json_file(path, {})
    return list(reversed(data.get("results") or []))


def probe_latest_result(cfg):
    results = probe_all_results(cfg)
    return results[0] if results else {}


def probe_result_by_ordinal(cfg, selector):
    text = str(selector or "").strip()
    if not text:
        return probe_latest_result(cfg)
    if not text.isdigit() or int(text) <= 0:
        return {}
    results = probe_all_results(cfg)
    idx = int(text) - 1
    if idx < 0 or idx >= len(results):
        return {}
    return results[idx]


def probe_effective_arch(rec):
    """Return (uname_m, endian) corrected so they're mutually consistent."""
    uname_m = str(rec.get("uname_m") or rec.get("architecture") or "")
    endian = str(rec.get("endian") or "")
    if uname_m == "mips" and endian == "little":
        uname_m = "mipsel"
    elif uname_m == "mipsel" and endian == "big":
        uname_m = "mips"
    return uname_m, endian


def probe_synthetic_survey(rec):
    """Build a minimal survey JSON dict from a probe result."""
    uname_m, endian = probe_effective_arch(rec)
    kernel = str(rec.get("uname_r") or rec.get("kernel") or "")
    return {
        "schema": 1,
        "arch": uname_m,
        "kernel": kernel,
        "endianness": endian,
        "uname_s": str(rec.get("uname_s") or "Linux"),
        "uname_m": uname_m,
        "uname_r": kernel,
        "uname": {
            "sysname": str(rec.get("uname_s") or "Linux"),
            "machine": uname_m,
            "release": kernel,
        },
        "word_bits": str(rec.get("word_bits") or ""),
        "endian": endian,
        "os": "linux",
        "recommendations": {},
        "_source": "probe",
        "_probe_received_at": str(rec.get("received_at") or ""),
        "_probe_remote": str(rec.get("remote_addr") or ""),
        "_note": (
            "Synthesized from probe only. "
            "Deploy griTTYkit and run 'grit survey push' for libc, "
            "filesystem, and tool capability data."
        ),
    }
