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


def dispatch_line_quit_choice(
    choice,
    *,
    module=None,
    target_selected=False,
    clear_context_func,
    mark_stopped_func,
):
    """Handle q/quit/exit and return REPL state updates."""
    if choice not in {"q", "quit", "exit"}:
        return {"handled": False}
    if str(module or "") or target_selected:
        clear_context_func(quiet=True)
        return {
            "handled": True,
            "compact_next_prompt": True,
        }
    mark_stopped_func()
    return {
        "handled": True,
        "exit_code": 0,
    }


def dispatch_line_parsed_command(
    cmd,
    console_args,
    *,
    module=None,
    target_selected=False,
    command_help_printer,
    context_help_printer,
    utility_dispatch_func,
    core_dispatch_func,
    navigation_dispatch_func,
    workflow_dispatch_func,
    unknown_message_func,
    print_func=print,
):
    """Dispatch a parsed line-console command through the standard handler order."""
    args = list(console_args or [])
    command_args = args[1:]
    if cmd in {"q", "quit", "exit"}:
        return {
            "handled": False,
            "choice": "q",
        }
    if dispatch_line_help_command(
        cmd,
        args,
        module=module,
        target_selected=target_selected,
        command_help_printer=command_help_printer,
        context_help_printer=context_help_printer,
    ):
        return {"handled": True}
    if utility_dispatch_func(cmd, command_args):
        return {"handled": True}
    core_result = core_dispatch_func(cmd, command_args)
    if core_result:
        result = {"handled": True}
        if core_result == "refresh":
            result.update({
                "choice": "r",
                "compact_next_prompt": False,
            })
        return result
    if navigation_dispatch_func(cmd, command_args):
        return {"handled": True}
    if workflow_dispatch_func(cmd, command_args):
        return {"handled": True}
    print_func(unknown_message_func(cmd, module, target_selected=target_selected))
    return {"handled": True}


def run_line_repl_loop(
    cfg,
    *,
    shutdown_event,
    shutdown_reason_func,
    line_history,
    pending_console_lines,
    workbench_snapshot_func,
    print_workbench_func,
    print_banner_func,
    version_func,
    prompt_func,
    input_func,
    history_command_func,
    record_history_func,
    clear_results_func,
    readline_module,
    module_func,
    target_selected_func,
    command_help_printer,
    context_help_printer,
    utility_dispatch_func,
    core_dispatch_func,
    navigation_dispatch_func,
    workflow_dispatch_func,
    unknown_message_func,
    clear_context_func,
    mark_stopped_func,
    legacy_dispatch_func,
):
    render_full = False
    compact_next_prompt = False
    while not shutdown_event.is_set():
        prompt_result = read_next_repl_line(
            cfg,
            compact_next_prompt=compact_next_prompt,
            render_full=render_full,
            pending_console_lines=pending_console_lines,
            workbench_snapshot_func=workbench_snapshot_func,
            print_workbench_func=print_workbench_func,
            print_banner_func=print_banner_func,
            version_func=version_func,
            prompt_func=prompt_func,
            input_func=input_func,
        )
        line = prompt_result["line"]
        compact_next_prompt = prompt_result["compact_next_prompt"]
        render_full = prompt_result["render_full"]
        if line is None:
            break
        prepared = prepare_repl_choice(
            line,
            line_history,
            history_command_func=history_command_func,
            record_history_func=record_history_func,
            clear_results_func=clear_results_func,
            readline_module=readline_module,
        )
        if prepared.get("compact_next_prompt"):
            compact_next_prompt = True
        if prepared.get("continue"):
            continue
        choice = prepared["choice"]
        console_args = prepared["console_args"]
        cmd = prepared["cmd"]
        if console_args:
            parsed_result = dispatch_line_parsed_command(
                cmd,
                console_args,
                module=module_func(cfg),
                target_selected=target_selected_func(cfg),
                command_help_printer=command_help_printer,
                context_help_printer=context_help_printer,
                utility_dispatch_func=utility_dispatch_func,
                core_dispatch_func=core_dispatch_func,
                navigation_dispatch_func=navigation_dispatch_func,
                workflow_dispatch_func=workflow_dispatch_func,
                unknown_message_func=unknown_message_func,
            )
            if "choice" in parsed_result:
                choice = parsed_result["choice"]
            if "compact_next_prompt" in parsed_result:
                compact_next_prompt = parsed_result["compact_next_prompt"]
            if parsed_result.get("handled"):
                continue
        quit_result = dispatch_line_quit_choice(
            choice,
            module=module_func(cfg),
            target_selected=target_selected_func(cfg),
            clear_context_func=clear_context_func,
            mark_stopped_func=mark_stopped_func,
        )
        if quit_result.get("handled"):
            if quit_result.get("compact_next_prompt"):
                compact_next_prompt = True
                continue
            return quit_result.get("exit_code", 0)
        legacy_result = legacy_dispatch_func(choice)
        if legacy_result.get("handled"):
            if legacy_result.get("render_full"):
                render_full = True
            if legacy_result.get("compact_next_prompt"):
                compact_next_prompt = True
            continue
    return 130 if shutdown_reason_func() in ("SIGINT", "SIGTERM", "keyboard_interrupt") else 0


def run_configured_line_repl_loop(
    cfg,
    *,
    clear_console_context_func,
    target_filter_func=None,
    **kwargs,
):
    """Run the standard config-backed line REPL loop."""
    target_callbacks = kwargs.pop("target_callbacks", None)
    utility_callbacks = kwargs.pop("utility_callbacks", None)
    search_callbacks = kwargs.pop("search_callbacks", None)
    core_callbacks = kwargs.pop("core_callbacks", None)
    navigation_callbacks = kwargs.pop("navigation_callbacks", None)
    workflow_callbacks = kwargs.pop("workflow_callbacks", None)
    legacy_callbacks = kwargs.pop("legacy_callbacks", None)
    workbench_mark_stopped_func = kwargs.pop("workbench_mark_stopped_func", None)

    if utility_callbacks is not None:
        kwargs.setdefault("line_history", utility_callbacks["line_history"])
        kwargs.setdefault("pending_console_lines", utility_callbacks["pending_console_lines"])
        kwargs.setdefault("utility_dispatch_func", utility_callbacks["dispatch_line_utility"])
    if search_callbacks is not None:
        kwargs.setdefault("clear_results_func", search_callbacks["clear_line_search_results"])
    if core_callbacks is not None:
        kwargs.setdefault("core_dispatch_func", core_callbacks["dispatch_line_core"])
    if navigation_callbacks is not None:
        kwargs.setdefault("navigation_dispatch_func", navigation_callbacks["dispatch_line_navigation"])
    if workflow_callbacks is not None:
        kwargs.setdefault("workflow_dispatch_func", workflow_callbacks["dispatch_line_workflow"])
    if legacy_callbacks is not None:
        kwargs.setdefault("legacy_dispatch_func", legacy_callbacks["dispatch_line_legacy"])
    if workbench_mark_stopped_func is not None:
        kwargs.setdefault(
            "mark_stopped_func",
            build_line_workbench_quit_stopped_callback(
                cfg,
                workbench_mark_stopped_func,
            ),
        )
    if target_filter_func is None and target_callbacks is not None:
        target_filter_callback = target_callbacks.get("target_filter")
        if target_filter_callback is not None:
            target_filter_func = lambda _cfg: target_filter_callback()
    if target_filter_func is None:
        target_filter_func = lambda _cfg: None

    def line_module(repl_cfg):
        return repl_cfg.get("_line_console_module")

    def target_selected(repl_cfg):
        return bool(target_filter_func(repl_cfg))

    def clear_context(quiet=False):
        return clear_console_context_func(cfg, quiet=quiet)

    return run_line_repl_loop(
        cfg,
        module_func=line_module,
        target_selected_func=target_selected,
        clear_context_func=clear_context,
        **kwargs,
    )


def run_line_console_lifecycle(
    cfg,
    *,
    stdin_isatty_func,
    stdout_isatty_func,
    state_file_path_func,
    update_server_state_func,
    append_event_func,
    print_workbench_func,
    run_repl_func,
    request_shutdown_func,
    stop_services_func,
    mark_stopped_func,
    shutdown_reason_func,
    stderr=None,
):
    """Run the line console with workbench state and cleanup handling."""
    state_file = str(state_file_path_func(cfg))
    update_server_state_func(
        cfg,
        "workbench",
        "open",
        {"state_file": state_file, "workbench_mode": "starting"},
    )
    if not stdin_isatty_func() or not stdout_isatty_func():
        update_server_state_func(
            cfg,
            "workbench",
            "open",
            {
                "state_file": state_file,
                "workbench_mode": "noninteractive",
            },
        )
        append_event_func(cfg, "workbench", "workbench_opened", details={"mode": "noninteractive"})
        print_workbench_func(cfg)
        return 0
    try:
        update_server_state_func(
            cfg,
            "workbench",
            "open",
            {
                "state_file": state_file,
                "workbench_mode": "line",
            },
        )
        append_event_func(cfg, "workbench", "workbench_opened", details={"mode": "line"})
        return run_repl_func(cfg)
    except KeyboardInterrupt:
        request_shutdown_func("keyboard_interrupt")
        print("grit-console: interrupted, shutting down workbench", file=stderr or sys.stderr)
        return 130
    finally:
        stop_services_func(cfg)
        reason = shutdown_reason_func() or "quit"
        mark_stopped_func(cfg, "workbench", reason)
        append_event_func(cfg, "workbench", "shutdown", details={"reason": reason})


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


def build_line_repl_input_callback(
    *,
    shutdown_event,
    request_shutdown_func,
    have_readline,
    read_line_func=read_line,
):
    def line_input(prompt):
        return read_line_func(
            prompt,
            shutdown_event=shutdown_event,
            request_shutdown_func=request_shutdown_func,
            have_readline=have_readline,
        )

    return line_input


def setup_line_repl_io(
    readline_module,
    have_readline,
    *,
    shutdown_event,
    request_shutdown_func,
    history_configurer=configure_readline_history,
    signal_installer=install_line_repl_signal_handlers,
    input_builder=build_line_repl_input_callback,
):
    """Configure REPL-local input state and return callbacks/cleanup state."""
    history_configurer(readline_module, have_readline)
    signal_handlers = signal_installer(request_shutdown_func)
    line_input = input_builder(
        shutdown_event=shutdown_event,
        request_shutdown_func=request_shutdown_func,
        have_readline=have_readline,
    )
    return {
        "line_input": line_input,
        "signal_handlers": signal_handlers,
    }


def line_repl_io_input(repl_io):
    return repl_io["line_input"]


def restore_line_repl_io(repl_io):
    restore_signal_handlers((repl_io or {}).get("signal_handlers"))


def build_line_workbench_quit_stopped_callback(cfg, mark_stopped_func):
    def mark_line_workbench_quit_stopped():
        mark_stopped_func(cfg, "workbench", "quit")

    return mark_line_workbench_quit_stopped


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
