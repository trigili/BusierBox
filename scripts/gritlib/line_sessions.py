"""Line-console session rendering helpers."""

from pathlib import Path
import shutil

from gritlib.console_display import console_table
from gritlib.line_context import clear_line_module_context, set_line_collection_context
from gritlib.line_probe_guidance import probe_menu_step_text, print_probe_menu_steps
from gritlib.line_search import set_line_search_results
from gritlib.shell_utils import shquote
from gritlib.session_state import read_json_file


_FINISHED_SESSION_STATES = {"ended", "stopped", "complete", "done", "error", "failed"}

_EMPTY_SESSIONS_MESSAGE = (
    "No sessions yet.\n"
    "  shell access: start plain-shell or start ssh\n"
    f"{probe_menu_step_text()}\n"
    "  start check-in listener: start command-queue"
)


LINE_SESSION_COMMANDS = (
    {
        "action": "clear",
        "commands": ("sessions", "session"),
        "subcommands": ("clear", "prune", "clean"),
    },
    {
        "action": "help",
        "commands": ("sessions", "session"),
        "subcommands": ("-h", "--help", "help"),
    },
    {
        "action": "list",
        "commands": ("sessions", "session"),
        "subcommands": ("-l", "--list", "list"),
    },
    {
        "action": "list",
        "commands": ("sessions", "session"),
        "subcommands": ("-v", "--verbose", "verbose", "details"),
        "verbose": True,
    },
    {
        "action": "interact",
        "commands": ("sessions", "session"),
        "subcommands": ("-i", "--interact", "interact"),
    },
    {
        "action": "select",
        "commands": ("session",),
        "subcommands": (),
        "positional": True,
    },
    {
        "action": "interact",
        "commands": ("sessions",),
        "subcommands": (),
        "positional": True,
    },
    {
        "action": "list",
        "commands": ("sessions", "session"),
        "subcommands": (),
    },
)


def line_session_command_records():
    return [
        {
            "family": "session",
            "action": rec["action"],
            "commands": list(rec["commands"]),
            "primary": rec["commands"][0],
            "aliases": list(rec["commands"][1:]),
            "subcommands": list(rec["subcommands"]),
            "verbose": bool(rec.get("verbose")),
            "positional": bool(rec.get("positional")),
        }
        for rec in LINE_SESSION_COMMANDS
    ]


def parse_line_sessions_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    records = [rec for rec in line_session_command_records() if cmd in rec["commands"]]
    if not records:
        return {}
    first = str(args[0]).lower() if args else ""
    for rec in records:
        if first not in rec["subcommands"]:
            continue
        if rec["action"] == "clear":
            flags = {str(item).lower() for item in args[1:]}
            return {
                "action": "clear",
                "all_sessions": bool(flags & {"--all", "all"}),
                "confirm": bool(flags & {"--confirm", "confirm", "yes"}),
                "command": cmd,
                "subcommand": first,
            }
        if rec["action"] == "interact":
            if len(args) < 2:
                continue
            return {
                "action": "interact",
                "selector": " ".join(args[1:]).strip(),
                "command": cmd,
                "subcommand": first,
            }
        return {
            "action": rec["action"],
            "verbose": bool(rec.get("verbose")),
            "command": cmd,
            "subcommand": first,
        }
    if args and first not in {"-l", "--list", "list"}:
        for rec in records:
            if rec.get("positional"):
                return {
                    "action": rec["action"],
                    "selector": " ".join(args).strip(),
                    "command": cmd,
                }
    for rec in records:
        if rec["action"] == "list" and not rec["subcommands"]:
            return {
                "action": "list",
                "verbose": False,
                "command": cmd,
            }
    return {}


def dispatch_line_sessions_command(
    session_cmd,
    *,
    clear_func=None,
    help_func=None,
    interact_func=None,
    select_func=None,
    list_func=None,
):
    action = (session_cmd or {}).get("action")
    try:
        if action == "clear" and clear_func:
            return clear_func(
                all_sessions=bool(session_cmd.get("all_sessions")),
                confirm=bool(session_cmd.get("confirm")),
            )
        if action == "help" and help_func:
            return help_func("sessions")
        if action == "interact" and interact_func:
            return interact_func(session_cmd.get("selector", ""))
        if action == "select" and select_func:
            return select_func(session_cmd.get("selector", ""))
        if action == "list" and list_func:
            return list_func(verbose=bool(session_cmd.get("verbose")))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported sessions command")


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


def require_line_session_record(sessions, selector):
    text = str(selector or "").strip()
    selected = line_session_record_by_selector(sessions, text)
    if not selected and text.isdigit():
        raise ValueError(f"session number out of range: {text}; run sessions or sessions verbose")
    if not selected:
        raise ValueError(f"session not found: {text}; run: sessions or sessions verbose")
    return selected


def current_line_session_record(snapshot_func, selector):
    snapshot = snapshot_func() if snapshot_func else {}
    return line_session_record_by_selector(
        (snapshot or {}).get("sessions") or [],
        selector,
    )


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
        print("  Hint: sessions with uploads/fetches/artifacts are kept unless you use all.")
        return
    for path, state, has_data in candidates:
        flag = "  [has data]" if has_data else ""
        print(f"  {path.name}  ({state}){flag}")
    if not confirm:
        confirm_command = "sessions clear all confirm" if all_sessions else "sessions clear confirm"
        print(f"\n  {len(candidates)} session(s) would be removed. Run: {confirm_command}")
        if not all_sessions:
            print("  To also delete sessions with saved activity: sessions clear all confirm")
        return
    removed = 0
    errors = 0
    removed_names = set()
    for path, _state, _has_data in candidates:
        try:
            shutil.rmtree(path)
            removed_names.add(path.name)
            removed += 1
        except OSError as exc:
            print(f"  error removing {path.name}: {exc}")
            errors += 1
    module = str((cfg or {}).get("_line_console_module") or "")
    if module.startswith("session/") and module.split("/", 1)[1] in removed_names:
        clear_line_module_context(cfg)
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
    print(f"  current session: {session_id}")
    print(f"  service: {service}  |  state: {state_str}")
    print("  in this prompt: info, options, interact, back")
    print(f"  also available: sessions verbose, sessions interact {shquote(session_id)}")


def print_line_session_interaction(rec, headless):
    path = str(rec.get("path") or "")
    print(f"Session interaction: {rec.get('session_id') or Path(path).name}")
    print(f"  service: {rec.get('service', '') or '-'}")
    print(f"  state: {rec.get('state', '') or '-'}")
    print(f"  path: {path}")
    print(f"  view command: view {shquote(path)}")
    print(f"  next: view {path}, sessions list, sessions verbose")
    if rec.get("session_log"):
        print(f"  session log: {rec.get('session_log', '')}")
        print(f"  tail: tail -n 40 {shquote(str(rec.get('session_log', '')))}")
    if rec.get("event_log"):
        print(f"  event log: {rec.get('event_log', '')}")
        print(f"  events: tail -n 40 {shquote(str(rec.get('event_log', '')))}")


def _line_session_detail_rows(rec, verbose):
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


def _line_session_columns(shown, verbose):
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
    return cols


def _line_session_footer(total):
    if not total:
        return "listeners, files, help: sessions ?"
    footer = "use N, sessions verbose, help: sessions ?"
    if total > 12:
        footer = f"showing 12 of {total}  —  " + footer
    return footer


def _line_session_search_record(rec, view_command, quote):
    session_name = str(rec.get("session_id") or Path(str(rec.get("path", ""))).name)
    return {
        "kind": "session",
        "label": (
            f"{session_name}"
            f" service={rec.get('service') or '-'} state={line_session_state_text(rec)}"
        ),
        "rec": rec,
        "command": view_command(str(rec.get("path") or "")),
        "use_hint": f"use session {quote(session_name)}",
    }


def print_line_session_records(sessions, verbose=False, view_command=None, quote=None):
    all_sessions = list(sessions or [])
    shown = all_sessions[:12]
    total = len(all_sessions)
    view_command = view_command or (lambda _path: "")
    quote = quote or (lambda text: str(text))

    console_table(
        f"Sessions  ({total} total)" if total else "Sessions  (none)",
        shown,
        _line_session_columns(shown, verbose),
        detail_fn=lambda rec: _line_session_detail_rows(rec, verbose),
        footer=_line_session_footer(total),
        empty_message=_EMPTY_SESSIONS_MESSAGE,
    )

    return [
        _line_session_search_record(rec, view_command, quote)
        for rec in shown
    ]


def print_sessions_context_help(sessions=None):
    sessions = list(sessions or [])
    example_session = sessions[0] if sessions else {}
    example_id = str(
        example_session.get("session_id")
        or Path(str(example_session.get("path", ""))).name
        or "sess-1"
    )
    print("Help: sessions — captured shells and file transfers")
    print("")
    print("  sessions                    list sessions")
    print("  sessions list               list sessions")
    print("  sessions verbose            list sessions with detail")
    if sessions:
        print(f"  session {shquote(example_id):<19} inspect and select a session context")
        print(f"  use session {shquote(example_id):<15} select a session context by id")
        print("  use session 1               select a session context by row number")
        print("  sessions interact 1         show session inspection commands")
        print("  interact                    show log paths and interaction commands")
        print(f"  interact {shquote(example_id):<18} show log paths and interaction commands for a session")
    print("  view ./README.md            view a local path in pager")
    print("  cat ./README.md             print a local path")
    if sessions:
        print("  sessions clear              preview deletion of finished sessions with no saved activity")
        print("  sessions clear confirm      delete finished sessions with no saved activity")
        print("  sessions clear all confirm  delete every session record")
        print("  info                        show the current session context")
        print("  options                     show session paths and activity")
    print("  back                        go up one breadcrumb level")
    if sessions:
        print("  command-queue sessions accumulate quickly — they're created per poll cycle.")
        print("  sessions clear removes ended/stopped sessions with no uploads, fetches, or artifacts.")
        print("  Inside a selected session prompt, short forms such as `info`, `options`, `interact`, and `back` act on that session.")
    else:
        print("  No sessions yet.")
        print("  shell access: start plain-shell or start ssh")
        print_probe_menu_steps()
        print("  start check-in listener: start command-queue")


def print_current_line_sessions(
    cfg,
    snapshot_func,
    verbose=False,
    view_command=None,
    quote=None,
    append_event_fn=None,
):
    snapshot = snapshot_func() if snapshot_func else {}
    all_sessions = snapshot.get("sessions") or []
    search_records = print_line_session_records(
        all_sessions,
        verbose=verbose,
        view_command=view_command,
        quote=quote,
    )
    set_line_search_results(cfg, search_records)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_sessions_listed", details={
            "session_count": len(all_sessions),
            "shown_count": len(search_records),
            "verbose": bool(verbose),
        })
    return search_records


def select_current_line_session(cfg, snapshot_func, selector, append_event_fn=None):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage:\n  use session SESSION")
    snapshot = snapshot_func() if snapshot_func else {}
    selected = require_line_session_record((snapshot or {}).get("sessions") or [], text)
    session_id = str(selected.get("session_id") or Path(str(selected.get("path", ""))).name)
    path = str(selected.get("path") or "")
    set_line_collection_context(cfg, f"session/{session_id}")
    print_selected_line_session(selected)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_session_selected", details={
            "session_id": session_id,
            "session_path": path,
            "service": selected.get("service", ""),
            "state": selected.get("state", ""),
        })
    return selected


def interact_current_line_session(
    cfg,
    snapshot_func,
    selector,
    *,
    view_command_builder=None,
    append_event_fn=None,
):
    text = str(selector or "").strip()
    if not text:
        module = str((cfg or {}).get("_line_console_module") or "")
        if module.startswith("session/"):
            text = module.split("/", 1)[1]
    if not text:
        raise ValueError("usage:\n  interact SESSION")
    snapshot = snapshot_func() if snapshot_func else {}
    selected = require_line_session_record((snapshot or {}).get("sessions") or [], text)
    path = str(selected.get("path") or "")
    view_command_builder = view_command_builder or (lambda _path: "")
    headless = view_command_builder(path)
    print_line_session_interaction(selected, headless)
    if append_event_fn:
        append_event_fn(cfg, "workbench", "workbench_session_interaction_viewed", details={
            "session_id": selected.get("session_id") or Path(path).name,
            "session_path": path,
            "headless_command": headless,
        })
    return selected
