"""Line-console session rendering helpers."""

from pathlib import Path
import shutil

from gritlib.console_display import console_table
from gritlib.shell_utils import shquote
from gritlib.session_state import read_json_file


_FINISHED_SESSION_STATES = {"ended", "stopped", "complete", "done", "error", "failed"}


def line_session_state_text(rec):
    state = rec.get("state") or "-"
    exit_reason = rec.get("exit_reason") or ""
    if exit_reason and exit_reason != state:
        return f"{state}/{exit_reason}"
    return state


def line_session_transfer_text(rec):
    parts = []
    if rec.get("upload_count"):
        parts.append(f"up={rec['upload_count']}")
    if rec.get("fetch_count"):
        parts.append(f"fetch={rec['fetch_count']}")
    if rec.get("artifact_count"):
        parts.append(f"art={rec['artifact_count']}")
    return "  ".join(parts) or "-"


def line_session_time_text(iso):
    if iso and len(iso) >= 16 and "T" in iso:
        date, rest = iso.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return iso or "-"


def line_session_record_by_selector(sessions, selector):
    text = str(selector or "").strip()
    if not text:
        return {}
    sessions = list(sessions or [])
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
    for item in sessions:
        session_id = str(item.get("session_id") or Path(str(item.get("path", ""))).name)
        if text == session_id or text == str(item.get("path", "")):
            return item
    return {}


def line_session_clear_candidates(root, all_sessions=False):
    candidates = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        meta = read_json_file(path / "session.json", {})
        state = str(meta.get("state") or "").lower()
        exit_r = str(meta.get("exit_reason") or "").lower()
        uploads = len(meta.get("uploads") or [])
        fetches = len(meta.get("fetches") or [])
        artifacts = len(meta.get("artifacts") or [])
        has_data = uploads > 0 or fetches > 0 or artifacts > 0
        finished = state in _FINISHED_SESSION_STATES or exit_r in _FINISHED_SESSION_STATES
        if all_sessions or (finished and not has_data):
            candidates.append((path, state or exit_r or "unknown", has_data))
    return candidates


def clear_line_sessions(cfg, root, all_sessions=False, confirm=False, append_event_fn=None):
    root = Path(root)
    if not root.is_dir():
        print("No session directory found.")
        return
    candidates = line_session_clear_candidates(root, all_sessions=all_sessions)
    if not candidates:
        msg = "No sessions to clear." if all_sessions else "No finished empty sessions to clear."
        print(msg)
        print("  Hint: sessions with uploads/fetches/artifacts are kept unless you use --all.")
        return
    for path, state, has_data in candidates:
        flag = "  [has data]" if has_data else ""
        print(f"  {path.name}  ({state}){flag}")
    if not confirm:
        print(f"\n  {len(candidates)} session(s) would be removed. Run: sessions clear --confirm")
        if not all_sessions:
            print("  To also remove sessions with data: sessions clear --all --confirm")
        return
    removed = 0
    errors = 0
    for path, _state, _has_data in candidates:
        try:
            shutil.rmtree(path)
            removed += 1
        except OSError as exc:
            print(f"  error removing {path.name}: {exc}")
            errors += 1
    print(f"\n  Cleared {removed} session(s)." + (f"  {errors} error(s)." if errors else ""))
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_sessions_cleared", details={
            "removed": removed,
            "errors": errors,
            "all_sessions": all_sessions,
        })


def print_selected_line_session(rec):
    session_id = str(rec.get("session_id") or Path(str(rec.get("path", ""))).name)
    service = rec.get("service") or "-"
    state_str = line_session_state_text(rec)
    if state_str == "-":
        state_str = "?"
    print(f"  {session_id}  —  {service}  |  {state_str}")
    print("  info / interact / view / sessions -v / back")


def print_line_session_interaction(rec, headless):
    path = str(rec.get("path") or "")
    print(f"Session interaction: {rec.get('session_id') or Path(path).name}")
    print(f"  service: {rec.get('service', '') or '-'}")
    print(f"  state: {rec.get('state', '') or '-'}")
    print(f"  path: {path}")
    print(f"  view: view {shquote(path)}")
    print(f"  next: view {path}, sessions -l, sessions -v")
    if rec.get("session_log"):
        print(f"  session log: {rec.get('session_log', '')}")
        print(f"  tail: tail -n 40 {shquote(str(rec.get('session_log', '')))}")
    if rec.get("event_log"):
        print(f"  event log: {rec.get('event_log', '')}")
        print(f"  events: tail -n 40 {shquote(str(rec.get('event_log', '')))}")


def print_line_session_records(sessions, verbose=False, view_command=None, quote=None):
    all_sessions = list(sessions or [])
    shown = all_sessions[:12]
    total = len(all_sessions)
    view_command = view_command or (lambda _path: "")
    quote = quote or (lambda text: str(text))

    def _detail(rec):
        if not verbose:
            return []
        session_id = rec.get("session_id") or Path(str(rec.get("path", ""))).name
        path = str(rec.get("path") or "")
        details = [("id", session_id), ("path", path)]
        if rec.get("session_log"):
            details.append(("log", Path(rec["session_log"]).name))
        if rec.get("event_log"):
            count = rec.get("event_count", "")
            suffix = f"  ({count} events)" if count else ""
            details.append(("events", Path(rec["event_log"]).name + suffix))
        if rec.get("target_id"):
            label = rec.get("target_label") or ""
            details.append(("target", rec["target_id"] + (f"  ({label})" if label else "")))
        transfers = line_session_transfer_text(rec)
        if transfers != "-":
            details.append(("transfers", transfers))
        return details

    transfers_any = any(
        (rec.get("upload_count") or rec.get("fetch_count") or rec.get("artifact_count"))
        for rec in shown
    )
    cols = [
        ("Service", lambda r: r.get("service") or "-"),
        ("State", line_session_state_text),
        ("Updated", lambda r: line_session_time_text(r.get("updated_at"))),
    ]
    if transfers_any and not verbose:
        cols.append(("Transfers", line_session_transfer_text))

    footer = "use N to select  |  sessions -v for details  |  sessions ? for help"
    if total > 12:
        footer = f"showing 12 of {total}  —  " + footer
    console_table(
        f"Sessions  ({total} total)" if total else "Sessions  (none)",
        shown, cols, detail_fn=_detail, footer=footer,
    )

    return [
        {
            "kind": "session",
            "label": (
                f"{rec.get('session_id') or Path(str(rec.get('path', ''))).name}"
                f" service={rec.get('service') or '-'} state={line_session_state_text(rec)}"
            ),
            "rec": rec,
            "command": view_command(str(rec.get("path") or "")),
            "use_hint": f"use session {quote(str(rec.get('session_id') or Path(str(rec.get('path', ''))).name))}",
        }
        for rec in shown
    ]
