"""Runtime helpers for the line-oriented console REPL."""

import os
import select
import signal
import sys
import time


def configure_readline_history(readline_module, have_readline, limit=500):
    if have_readline and readline_module is not None:
        readline_module.set_history_length(limit)


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
