"""prompt_toolkit input adapter for the line console."""

import os
import sys


def _load_prompt_toolkit():
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
    except ImportError:
        return None, None, None
    return PromptSession, Completer, Completion


def build_line_prompt_completer(candidate_func, *, completer_base=None, completion_class=None):
    if completer_base is None or completion_class is None:
        _session_cls, completer_base, completion_class = _load_prompt_toolkit()
    if completer_base is None or completion_class is None:
        return None

    class LinePromptCompleter(completer_base):
        def get_completions(self, document, complete_event):
            del complete_event
            text = str(getattr(document, "text_before_cursor", "") or "")
            for candidate in candidate_func(text) or []:
                candidate = str(candidate or "")
                if candidate:
                    yield completion_class(candidate, start_position=-len(text))

    return LinePromptCompleter()


class PromptToolkitLineInput:
    def __init__(
        self,
        session,
        *,
        shutdown_event,
        request_shutdown_func,
        completer_base=None,
        completion_class=None,
    ):
        self._session = session
        self._shutdown_event = shutdown_event
        self._request_shutdown_func = request_shutdown_func
        self._completer_base = completer_base
        self._completion_class = completion_class
        self._completion_func = None

    def set_completion_func(self, completion_func):
        self._completion_func = completion_func

    def _completer(self):
        if self._completion_func is None:
            return None
        return build_line_prompt_completer(
            self._completion_func,
            completer_base=self._completer_base,
            completion_class=self._completion_class,
        )

    def __call__(self, prompt):
        if self._shutdown_event.is_set():
            return None
        try:
            line = self._session.prompt(prompt, completer=self._completer())
        except EOFError:
            self._request_shutdown_func("input_eof")
            return None
        except KeyboardInterrupt:
            self._request_shutdown_func("keyboard_interrupt")
            return None
        if self._shutdown_event.is_set():
            return None
        return line


class MissingPromptToolkitLineInput:
    def __init__(self, *, request_shutdown_func, stderr=None):
        self._request_shutdown_func = request_shutdown_func
        self._stderr = stderr

    def set_completion_func(self, completion_func):
        del completion_func

    def __call__(self, prompt):
        del prompt
        print(
            "grit-console: python-prompt-toolkit is required for the interactive REPL",
            file=self._stderr or sys.stderr,
        )
        self._request_shutdown_func("prompt_toolkit_missing")
        return None


class BasicLineInput:
    def __init__(self, *, shutdown_event, request_shutdown_func):
        self._shutdown_event = shutdown_event
        self._request_shutdown_func = request_shutdown_func

    def set_completion_func(self, completion_func):
        del completion_func

    def __call__(self, prompt):
        if self._shutdown_event.is_set():
            return None
        try:
            return input(prompt)
        except EOFError:
            self._request_shutdown_func("input_eof")
            return None
        except KeyboardInterrupt:
            self._request_shutdown_func("keyboard_interrupt")
            return None


def build_prompt_toolkit_input(
    *,
    shutdown_event,
    request_shutdown_func,
    session_factory=None,
    completer_base=None,
    completion_class=None,
):
    if os.environ.get("GRIT_LINE_INPUT") == "basic":
        return BasicLineInput(
            shutdown_event=shutdown_event,
            request_shutdown_func=request_shutdown_func,
        )
    if session_factory is None:
        session_factory, completer_base, completion_class = _load_prompt_toolkit()
    if session_factory is None:
        return MissingPromptToolkitLineInput(request_shutdown_func=request_shutdown_func)
    return PromptToolkitLineInput(
        session_factory(),
        shutdown_event=shutdown_event,
        request_shutdown_func=request_shutdown_func,
        completer_base=completer_base,
        completion_class=completion_class,
    )
