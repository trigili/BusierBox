"""Probe result persistence helpers for grit-console."""

from pathlib import Path

from gritlib.console_display import console_table
from gritlib.line_search import set_line_search_results
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


def clear_probe_results(cfg, selector=""):
    path = probe_results_path(cfg)
    data = read_json_file(path, {"schema": 1, "results": []})
    results = data.get("results") if isinstance(data.get("results"), list) else []
    text = str(selector or "").strip()
    if not results:
        return {
            "count": 0,
            "selector": text,
            "remaining_count": 0,
            "removed": {},
            "had_results": False,
        }
    if not text or text in {"--all", "all"}:
        count = len(results)
        removed = {}
        data["results"] = []
    elif text.isdigit() and int(text) > 0:
        ordinal = int(text)
        if ordinal > len(results):
            raise ValueError(f"probe result number out of range: {text}")
        original_idx = len(results) - ordinal
        removed = results.pop(original_idx)
        count = 1
        data["results"] = results
    else:
        raise ValueError(
            "usage:\n"
            "  listener probe clear\n"
            "  listener probe clear N\n"
            "  listener probe clear all"
        )
    atomic_write_json(path, data)
    return {
        "count": count,
        "selector": text or "--all",
        "remaining_count": len(data.get("results") or []),
        "removed": removed,
        "had_results": True,
    }


def preview_probe_results_clear(cfg, selector=""):
    results = probe_all_results(cfg)
    text = str(selector or "").strip()
    if not results:
        return {
            "count": 0,
            "selector": text,
            "had_results": False,
            "selected": [],
        }
    if not text or text in {"--all", "all"}:
        selected = results
        selector_text = text or "--all"
    elif text.isdigit() and int(text) > 0:
        ordinal = int(text)
        if ordinal > len(results):
            raise ValueError(f"probe result number out of range: {text}")
        selected = [results[ordinal - 1]]
        selector_text = text
    else:
        raise ValueError(
            "usage:\n"
            "  listener probe clear confirm\n"
            "  listener probe clear N confirm\n"
            "  listener probe clear all confirm"
        )
    return {
        "count": len(selected),
        "selector": selector_text,
        "had_results": True,
        "selected": selected,
    }


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
"Deploy griTTYkit and run 'grit survey retrieve' for libc, "
            "filesystem, and tool capability data."
        ),
    }


def probe_result_time_text(iso):
    if iso and len(iso) >= 16 and "T" in iso:
        date, rest = iso.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return iso or "-"


def print_probe_result_records(records):
    records = list(records or [])
    console_table(
        f"Probe results  ({len(records)} received)",
        records[:8],
        [
            ("Remote", lambda r: r.get("remote_addr") or "-"),
            ("Arch", lambda r: r.get("uname_m") or r.get("architecture") or "-"),
            ("Kernel", lambda r: r.get("uname_r") or r.get("kernel") or "-"),
            ("OS", lambda r: r.get("uname_s") or "-"),
            ("Bits", lambda r: str(r.get("word_bits") or "-")),
            ("Endian", lambda r: r.get("endian") or "-"),
            ("At", lambda r: probe_result_time_text(r.get("received_at"))),
        ],
    )
    print("")
    if records:
        print("  Next steps:")
        print("    listener probe config                  — populate active profile from most recent result")
        print("    listener probe config N                — populate active profile from a numbered result")
        print("    listener probe config write-config FILE — export build config")
        print("    listener probe clear                  — preview clearing all probe results")
        print("    listener probe clear N                — preview clearing a numbered result")
        print("    listener probe clear all              — preview clearing all probe results")
        print("    listener probe clear N confirm        — remove a numbered result")
        print("    listener probe clear all confirm      — remove all probe results")
        print("    after config: listener serve start     — stage a matching binary from active profile")
        print("    after config: listener serve ssh start — stage ssh-operator payload from active profile")
    else:
        print("  No results yet — run: listener probe start")


def line_probe_result_search_records(records):
    return [
        {
            "kind": "probe-result",
            "label": (
                f"{idx} arch={rec.get('uname_m') or rec.get('architecture') or '-'} "
                f"kernel={rec.get('uname_r') or rec.get('kernel') or '-'} "
                f"remote={rec.get('remote_addr') or '-'}"
            ),
            "rec": rec,
            "ordinal": idx,
            "use_hint": f"listener probe config {idx}",
        }
        for idx, rec in enumerate(records or [], 1)
    ]


def print_line_probe_results(cfg, append_event_fn=None):
    records = probe_all_results(cfg)
    print_probe_result_records(records)
    set_line_search_results(cfg, line_probe_result_search_records(records))
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_probe_results_viewed", details={
            "result_count": len(records),
        })
    return records


def clear_line_probe_results(cfg, args, append_event_fn=None):
    tokens = [str(arg or "").strip() for arg in (args or []) if str(arg or "").strip()]
    confirm = any(token.lower() in {"--confirm", "confirm", "yes"} for token in tokens)
    selectors = [token for token in tokens if token.lower() not in {"--confirm", "confirm", "yes"}]
    if len(selectors) > 1:
        raise ValueError(
            "usage:\n"
            "  listener probe clear confirm\n"
            "  listener probe clear N confirm\n"
            "  listener probe clear all confirm"
        )
    text = selectors[0] if selectors else ""
    if not confirm:
        details = preview_probe_results_clear(cfg, text)
        if not details.get("had_results"):
            print("no probe results to clear")
            return 0
        count = int(details.get("count") or 0)
        selector_text = "" if details.get("selector") in {"", "--all"} else f" {details.get('selector')}"
        selected = details.get("selected") if isinstance(details.get("selected"), list) else []
        for rec in selected[:10]:
            print(f"  {rec.get('received_at', '') or '-'}  {rec.get('remote_addr', '') or '-'}")
        if len(selected) > 10:
            print(f"  ... {len(selected) - 10} more")
        print(f"\n  {count} probe result(s) would be cleared. Run: listener probe clear{selector_text} confirm")
        return 0
    details = clear_probe_results(cfg, text)
    if not details.get("had_results"):
        print("no probe results to clear")
        return 0
    count = int(details.get("count") or 0)
    removed = details.get("removed") if isinstance(details.get("removed"), dict) else {}
    if removed:
        print(
            f"removed probe result {details.get('selector')}: "
            f"{removed.get('received_at', '') or '-'} {removed.get('remote_addr', '') or '-'}"
        )
    print(f"cleared {count} probe result(s)")
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_probe_results_cleared", details={
            "count": count,
            "selector": details.get("selector") or "--all",
            "remaining_count": details.get("remaining_count", 0),
        })
    return count
