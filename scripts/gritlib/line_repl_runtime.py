"""Runtime helpers for the line-oriented console REPL."""

import os
import signal
import shlex
import sys
import time

from gritlib.line_prompt_toolkit import build_prompt_toolkit_input


LINE_REPL_LEGACY_SINGLE_KEY_CHOICES = frozenset({"c", "d", "r", "v", "q"})

CONTEXTUAL_COMMAND_PREFIXES = {
    "build": {
        "list", "set", "unset",
    },
    "files": {
        "clear",
    },
    "artifact": {
        "stamp", "trailer", "configure", "show", "clear",
    },
    "jobs": {
        "cancel", "kill", "select", "-i", "-k", "-v",
    },
    "listener": set(),
    "probe": {
        "start", "queue", "results", "result", "config", "clear",
        "delivery", "deliver", "commands", "paste", "serial", "heredoc",
        "script", "raw", "show", "command", "start-service",
        "help",
    },
    "queue": {
        "list", "result", "results", "clear", "command",
    },
    "release": {
        "list", "stage", "recommendations", "artifacts", "use", "select",
    },
    "routes": {
        "add", "start", "stop", "delete", "rm", "remove", "print",
    },
    "route": {
        "add", "start", "stop", "delete", "rm", "remove", "print",
    },
    "sessions": {
        "clear", "prune", "clean", "verbose", "list",
    },
    "survey": {
        "results", "result", "config", "preset", "help",
    },
}

CONTEXTUAL_COMMAND_CANONICAL = {
    "routes": "route",
    "route": "route",
    "route/": "route",
    "listener/": "listener",
    "job": "jobs",
    "job/": "jobs",
    "session": "sessions",
    "session/": "sessions",
}


def resolve_replay_command(choice, line_history, history_command_func):
    """Return (resolved_choice, replayed) for line-console history replay commands."""
    text = str(choice or "")
    if text == "!!" or (text.startswith("!") and text[1:].isdigit()):
        return history_command_func(line_history, text), True
    if text.lower().startswith("repeat "):
        repeat_args = shlex.split(text)
        if len(repeat_args) != 2:
            raise ValueError("usage:\n  repeat N")
        return history_command_func(line_history, repeat_args[1]), True
    return choice, False


def should_parse_line_command(choice):
    text = str(choice or "").strip()
    return bool(text) and not text.isdigit() and text not in LINE_REPL_LEGACY_SINGLE_KEY_CHOICES


def parse_line_command_args(choice):
    return shlex.split(str(choice or ""))


def contextual_line_command(cmd, args, *, module=None):
    """Return command/args with submenu-implied command family applied."""
    command = str(cmd or "").strip().lower()
    command_args = list(args or [])
    module_text = str(module or "").strip().lower()
    if not command:
        return command, command_args
    if command == "clear" and command_args[:1] == ["target"]:
        return command, command_args
    if module_text in {"listener/probe", "listener/probe-http"} and command == "serve":
        return "listener", ["serve", *command_args]
    if module_text in {"listener/probe", "listener/probe-http"} and command == "probe":
        return "listener", ["probe", *command_args]
    if module_text in {"listener/probe", "listener/probe-http"} and command in CONTEXTUAL_COMMAND_PREFIXES.get("probe", set()):
        return "listener", ["probe", command, *command_args]
    context = CONTEXTUAL_COMMAND_CANONICAL.get(module_text, module_text.split("/", 1)[0])
    context = CONTEXTUAL_COMMAND_CANONICAL.get(f"{context}/", context)
    if command == context:
        return command, command_args
    if command not in CONTEXTUAL_COMMAND_PREFIXES.get(context, set()):
        return command, command_args
    return context, [command, *command_args]


def prepare_repl_choice(
    line,
    line_history,
    *,
    history_command_func,
    record_history_func,
    clear_results_func,
    shutdown_event=None,
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
    if choice.startswith("#"):
        return {
            "continue": True,
            "compact_next_prompt": True,
            "choice": choice,
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
    record_history_func(line_history, choice)
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
        (cmd == "use" and len(console_args) == 2 and console_args[1].isdigit())
        or cmd in {
            "?", "help", "options", "next", "complete", "completions",
            "history", "console",
        }
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
    if line_repl_has_context_scope(module=module, target_selected=target_selected):
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


def line_repl_has_context_scope(*, module=None, target_selected=False):
    return bool(str(module or "") or target_selected)


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
    if dispatch_line_help_command(
        cmd,
        args,
        module=module,
        target_selected=target_selected,
        command_help_printer=command_help_printer,
        context_help_printer=context_help_printer,
    ):
        return {"handled": True}
    if cmd in {"q", "quit", "exit"}:
        return {
            "handled": False,
            "choice": "q",
        }
    cmd, command_args = contextual_line_command(cmd, command_args, module=module)
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


def _line_repl_shutdown_exit_code(shutdown_reason_func):
    if shutdown_reason_func() in ("SIGINT", "SIGTERM", "keyboard_interrupt"):
        return 130
    if shutdown_reason_func() == "prompt_toolkit_missing":
        return 2
    return 0


def _read_prepared_repl_choice(
    cfg,
    *,
    compact_next_prompt,
    render_full,
    pending_console_lines,
    workbench_snapshot_func,
    print_workbench_func,
    print_banner_func,
    version_func,
    prompt_func,
    input_func,
    line_history,
    history_command_func,
    record_history_func,
    clear_results_func,
    shutdown_event=None,
):
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
        shutdown_event=shutdown_event,
    )
    line = prompt_result["line"]
    if line is None:
        return {
            "line": None,
            "compact_next_prompt": prompt_result["compact_next_prompt"],
            "render_full": prompt_result["render_full"],
        }
    prepared = prepare_repl_choice(
        line,
        line_history,
        history_command_func=history_command_func,
            record_history_func=record_history_func,
            clear_results_func=clear_results_func,
            shutdown_event=shutdown_event,
        )
    compact_next_prompt = prompt_result["compact_next_prompt"]
    if prepared.get("compact_next_prompt"):
        compact_next_prompt = True
    prepared.update({
        "line": line,
        "compact_next_prompt": compact_next_prompt,
        "render_full": prompt_result["render_full"],
    })
    return prepared


def _dispatch_prepared_line_command(
    cfg,
    prepared,
    *,
    module_func,
    target_selected_func,
    command_help_printer,
    context_help_printer,
    utility_dispatch_func,
    core_dispatch_func,
    navigation_dispatch_func,
    workflow_dispatch_func,
    unknown_message_func,
):
    if not prepared.get("console_args"):
        return {"handled": False, "choice": prepared["choice"]}
    parsed_result = dispatch_line_parsed_command(
        prepared["cmd"],
        prepared["console_args"],
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
    result = {"handled": parsed_result.get("handled"), "choice": prepared["choice"]}
    if "choice" in parsed_result:
        result["choice"] = parsed_result["choice"]
    if "compact_next_prompt" in parsed_result:
        result["compact_next_prompt"] = parsed_result["compact_next_prompt"]
    return result


def _dispatch_repl_quit_or_legacy(
    cfg,
    choice,
    *,
    module_func,
    target_selected_func,
    clear_context_func,
    mark_stopped_func,
    legacy_dispatch_func,
    shutdown_event=None,
):
    quit_result = dispatch_line_quit_choice(
        choice,
        module=module_func(cfg),
        target_selected=target_selected_func(cfg),
        clear_context_func=clear_context_func,
        mark_stopped_func=mark_stopped_func,
    )
    if quit_result.get("handled"):
        return quit_result
    return legacy_dispatch_func(choice)


def _apply_repl_dispatch_state(loop_state, dispatch_result):
    if dispatch_result.get("compact_next_prompt"):
        loop_state["compact_next_prompt"] = True
    if dispatch_result.get("render_full"):
        loop_state["render_full"] = True


def _line_repl_iteration_exit_result(dispatch_result):
    if "exit_code" in dispatch_result:
        return {"continue": False, "exit_code": dispatch_result.get("exit_code", 0)}
    return {"continue": dispatch_result.get("handled", False)}


def _apply_prepared_repl_state(loop_state, prepared):
    loop_state["compact_next_prompt"] = prepared["compact_next_prompt"]
    loop_state["render_full"] = prepared["render_full"]


def _run_line_repl_iteration(
    cfg,
    loop_state,
    *,
    pending_console_lines,
    workbench_snapshot_func,
    print_workbench_func,
    print_banner_func,
    version_func,
    prompt_func,
    input_func,
    line_history,
    history_command_func,
    record_history_func,
    clear_results_func,
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
    shutdown_event=None,
):
    prepared = _read_prepared_repl_choice(
        cfg,
        compact_next_prompt=loop_state["compact_next_prompt"],
        render_full=loop_state["render_full"],
        pending_console_lines=pending_console_lines,
        workbench_snapshot_func=workbench_snapshot_func,
        print_workbench_func=print_workbench_func,
        print_banner_func=print_banner_func,
        version_func=version_func,
        prompt_func=prompt_func,
        input_func=input_func,
        line_history=line_history,
        history_command_func=history_command_func,
        record_history_func=record_history_func,
        clear_results_func=clear_results_func,
        shutdown_event=shutdown_event,
    )
    _apply_prepared_repl_state(loop_state, prepared)
    if prepared["line"] is None or prepared.get("continue"):
        return {"continue": prepared["line"] is not None}
    parsed_result = _dispatch_prepared_line_command(
        cfg,
        prepared,
        module_func=module_func,
        target_selected_func=target_selected_func,
        command_help_printer=command_help_printer,
        context_help_printer=context_help_printer,
        utility_dispatch_func=utility_dispatch_func,
        core_dispatch_func=core_dispatch_func,
        navigation_dispatch_func=navigation_dispatch_func,
        workflow_dispatch_func=workflow_dispatch_func,
        unknown_message_func=unknown_message_func,
    )
    if "compact_next_prompt" in parsed_result:
        loop_state["compact_next_prompt"] = parsed_result["compact_next_prompt"]
    if parsed_result.get("handled"):
        return {"continue": True}
    dispatch_result = _dispatch_repl_quit_or_legacy(
        cfg,
        parsed_result["choice"],
        module_func=module_func,
        target_selected_func=target_selected_func,
        clear_context_func=clear_context_func,
        mark_stopped_func=mark_stopped_func,
        legacy_dispatch_func=legacy_dispatch_func,
    )
    _apply_repl_dispatch_state(loop_state, dispatch_result)
    return _line_repl_iteration_exit_result(dispatch_result)


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
    loop_state = {
        "render_full": False,
        "compact_next_prompt": False,
    }
    while not shutdown_event.is_set():
        iteration = _run_line_repl_iteration(
            cfg,
            loop_state,
            pending_console_lines=pending_console_lines,
            workbench_snapshot_func=workbench_snapshot_func,
            print_workbench_func=print_workbench_func,
            print_banner_func=print_banner_func,
            version_func=version_func,
            prompt_func=prompt_func,
            input_func=input_func,
            line_history=line_history,
            history_command_func=history_command_func,
            record_history_func=record_history_func,
            clear_results_func=clear_results_func,
            module_func=module_func,
            target_selected_func=target_selected_func,
            command_help_printer=command_help_printer,
            context_help_printer=context_help_printer,
            utility_dispatch_func=utility_dispatch_func,
            core_dispatch_func=core_dispatch_func,
            navigation_dispatch_func=navigation_dispatch_func,
            workflow_dispatch_func=workflow_dispatch_func,
            unknown_message_func=unknown_message_func,
            clear_context_func=clear_context_func,
            mark_stopped_func=mark_stopped_func,
            legacy_dispatch_func=legacy_dispatch_func,
            shutdown_event=shutdown_event,
        )
        if "exit_code" in iteration:
            return iteration["exit_code"]
        if not iteration.get("continue"):
            break
    return _line_repl_shutdown_exit_code(shutdown_reason_func)


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


def _replace_stdin_with_devnull(stdin=None, devnull_path=os.devnull, close_after=False):
    stream = stdin if stdin is not None else sys.stdin
    null_fd = None
    try:
        null_fd = os.open(devnull_path, os.O_RDONLY)
        os.dup2(null_fd, stream.fileno())
        if close_after:
            try:
                os.close(stream.fileno())
            except OSError:
                pass
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
        _replace_stdin_with_devnull(stdin=stdin, close_after=(reason == "SIGTERM"))
        if reason == "SIGTERM":
            raise KeyboardInterrupt

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


def setup_line_repl_io(
    *,
    shutdown_event,
    request_shutdown_func,
    signal_installer=install_line_repl_signal_handlers,
):
    """Configure prompt-toolkit input state and return callbacks/cleanup state."""
    signal_handlers = signal_installer(request_shutdown_func)
    line_input = build_prompt_toolkit_input(
        shutdown_event=shutdown_event,
        request_shutdown_func=request_shutdown_func,
    )
    return {
        "line_input": line_input,
        "signal_handlers": signal_handlers,
    }


def line_repl_io_input(repl_io):
    return repl_io["line_input"]


def set_line_repl_io_completion_func(repl_io, completion_func):
    line_input = (repl_io or {}).get("line_input")
    setter = getattr(line_input, "set_completion_func", None)
    if callable(setter):
        setter(completion_func)


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
    shutdown_event=None,
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
        if shutdown_event is not None and shutdown_event.is_set():
            line = None
        else:
            try:
                line = input_func(prompt)
            except (EOFError, OSError):
                if shutdown_event is not None and shutdown_event.is_set():
                    line = None
                else:
                    raise
    return {
        "line": line,
        "snapshot": snap,
        "compact_next_prompt": compact_next_prompt,
        "render_full": render_full,
    }
