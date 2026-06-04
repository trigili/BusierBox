"""Runtime helpers for the line-oriented console REPL."""

import os
import select
import signal
import shlex
import sys
import time


LINE_REPL_LEGACY_SINGLE_KEY_CHOICES = frozenset({"c", "d", "r", "v", "q"})


def configure_readline_history(readline_module, have_readline, limit=500):
    if have_readline and readline_module is not None:
        readline_module.set_history_length(limit)


def install_readline_completer(readline_module, have_readline, candidate_func):
    if not have_readline or readline_module is None:
        return
    completion_cache = {"line": None, "candidates": []}

    def _rl_completer(_text, state):
        try:
            line = readline_module.get_line_buffer()
            if line != completion_cache["line"]:
                completion_cache["line"] = line
                completion_cache["candidates"] = list(candidate_func(line) or [])
            candidates = completion_cache["candidates"]
            if state < len(candidates):
                return candidates[state]
        except Exception:
            pass
        return None

    readline_module.set_completer(_rl_completer)
    readline_module.set_completer_delims("\t\n")
    readline_module.parse_and_bind("tab: complete")


def resolve_replay_command(choice, line_history, history_command_func):
    """Return (resolved_choice, replayed) for line-console history replay commands."""
    text = str(choice or "")
    if text == "!!" or (text.startswith("!") and text[1:].isdigit()):
        return history_command_func(line_history, text), True
    if text.lower().startswith("repeat "):
        repeat_args = shlex.split(text)
        if len(repeat_args) != 2:
            raise ValueError("usage: repeat N")
        return history_command_func(line_history, repeat_args[1]), True
    return choice, False


def should_parse_line_command(choice):
    text = str(choice or "").strip()
    return bool(text) and not text.isdigit() and text not in LINE_REPL_LEGACY_SINGLE_KEY_CHOICES


def parse_line_command_args(choice):
    return shlex.split(str(choice or ""))


def prepare_repl_choice(
    line,
    line_history,
    *,
    history_command_func,
    record_history_func,
    clear_results_func,
    readline_module=None,
):
    choice = str(line or "").strip()
    if not choice:
        return {
            "continue": True,
            "compact_next_prompt": True,
            "choice": "",
            "console_args": [],
            "cmd": "",
        }
    try:
        choice, replayed_history = resolve_replay_command(
            choice,
            line_history,
            history_command_func,
        )
        if replayed_history:
            print(f"replay: {choice}")
    except ValueError as exc:
        print(exc)
        return {
            "continue": True,
            "choice": "",
            "console_args": [],
            "cmd": "",
        }
    record_history_func(line_history, choice, readline_module=readline_module)
    if replayed_history and str(choice).isdigit():
        clear_results_func()
    if not should_parse_line_command(choice):
        return {
            "continue": False,
            "choice": choice,
            "console_args": [],
            "cmd": "",
        }
    try:
        console_args = parse_line_command_args(choice)
    except ValueError as exc:
        print(exc)
        return {
            "continue": True,
            "choice": choice,
            "console_args": [],
            "cmd": "",
        }
    cmd = console_args[0].lower() if console_args else ""
    preserve_line_results = (
        cmd == "use" and len(console_args) == 2 and console_args[1].isdigit()
    )
    if not preserve_line_results:
        clear_results_func()
    return {
        "continue": False,
        "choice": choice,
        "console_args": console_args,
        "cmd": cmd,
        "compact_next_prompt": True,
    }


def dispatch_line_help_command(
    cmd,
    console_args,
    *,
    module=None,
    target_selected=False,
    command_help_printer,
    context_help_printer,
):
    """Handle line-console help commands and return True when consumed."""
    args = list(console_args or [])
    if args and len(args) >= 2 and args[-1] == "?":
        command_help_printer(cmd)
        return True
    if cmd not in {"?", "help"}:
        return False
    if len(args) >= 2:
        command_help_printer(args[1])
    else:
        context_help_printer(
            module,
            target_selected=target_selected,
            command_help_printer=command_help_printer,
        )
    return True


def _replace_stdin_with_devnull(stdin=None, devnull_path=os.devnull):
    stream = stdin if stdin is not None else sys.stdin
    null_fd = None
    try:
        null_fd = os.open(devnull_path, os.O_RDONLY)
        os.dup2(null_fd, stream.fileno())
    except OSError:
        pass
    finally:
        if null_fd is not None:
            try:
                os.close(null_fd)
            except OSError:
                pass


def install_line_repl_signal_handlers(request_shutdown_func, *, stdin=None, shutdown_delay_sec=0.4):
    """Install REPL-local signal handlers and return previous handler state."""
    previous_handlers = [
        (signal.SIGTERM, signal.getsignal(signal.SIGTERM)),
        (signal.SIGINT, signal.getsignal(signal.SIGINT)),
    ]

    def _line_repl_shutdown(reason, _signum, _frame):
        request_shutdown_func(reason)
        if reason == "SIGTERM":
            time.sleep(shutdown_delay_sec)
        _replace_stdin_with_devnull(stdin=stdin)

    try:
        signal.signal(signal.SIGTERM, lambda s, f: _line_repl_shutdown("SIGTERM", s, f))
        signal.signal(signal.SIGINT, lambda s, f: _line_repl_shutdown("keyboard_interrupt", s, f))
    except (OSError, ValueError):
        return [(sig, None) for sig, _prev in previous_handlers]
    return previous_handlers


def restore_signal_handlers(previous_handlers):
    for sig, previous in previous_handlers or ():
        if previous is None:
            continue
        try:
            signal.signal(sig, previous)
        except (OSError, ValueError):
            pass


def read_line(prompt, *, shutdown_event, request_shutdown_func, have_readline,
              stdin=None, stdout=None, input_func=input, select_func=select.select):
    """Read one REPL line while honoring shutdown requests."""
    if shutdown_event.is_set():
        return None
    if have_readline:
        try:
            line = input_func(prompt)
        except EOFError:
            request_shutdown_func("input_eof")
            return None
        if shutdown_event.is_set():
            return None
        return line

    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    output_stream.write(prompt)
    output_stream.flush()
    while not shutdown_event.is_set():
        try:
            ready, _w, _x = select_func([input_stream], [], [], 0.5)
        except (OSError, ValueError):
            request_shutdown_func("input_error")
            return None
        if not ready:
            continue
        line = input_stream.readline()
        if line == "":
            request_shutdown_func("input_eof")
            return None
        return line.rstrip("\n")
    return None


def read_next_repl_line(
    cfg,
    *,
    compact_next_prompt=False,
    render_full=False,
    pending_console_lines=None,
    workbench_snapshot_func=None,
    print_workbench_func=None,
    print_banner_func=None,
    version_func=None,
    prompt_func=None,
    input_func=None,
):
    """Render the next prompt frame and return the entered line plus updated state."""
    pending_console_lines = pending_console_lines if pending_console_lines is not None else []
    workbench_snapshot_func = workbench_snapshot_func or (lambda _cfg: {})
    print_workbench_func = print_workbench_func or (lambda _cfg, include_api_summary=False: None)
    print_banner_func = print_banner_func or (lambda _snap, _version: None)
    version_func = version_func or (lambda: "")
    prompt_func = prompt_func or (lambda _cfg: "> ")
    input_func = input_func or input
    snap = None
    if compact_next_prompt:
        compact_next_prompt = False
    elif render_full:
        print("")
        print_workbench_func(cfg, include_api_summary=False)
        render_full = False
        snap = workbench_snapshot_func(cfg)
    else:
        print("")
        snap = workbench_snapshot_func(cfg)
        print_banner_func(snap, version_func())
    prompt = prompt_func(cfg)
    if pending_console_lines:
        line = pending_console_lines.pop(0)
        print(f"{prompt}{line}")
    else:
        line = input_func(prompt)
    return {
        "line": line,
        "snapshot": snap,
        "compact_next_prompt": compact_next_prompt,
        "render_full": render_full,
    }
