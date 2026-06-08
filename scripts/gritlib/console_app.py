"""Application entrypoint for grit-console."""

import sys
from pathlib import Path
from gritlib.config_utils import load_config
from gritlib.console_artifact import handle_artifact_command
from gritlib.console_args import (
    apply_console_arg_overrides, build_arg_parser, handle_early_console_args,
    has_explicit_console_action,
)
from gritlib.console_bringup import handle_bringup_command
from gritlib.console_headless import handle_headless_action_args
from gritlib.console_listeners import (
    prepare_listener_action, serve_console_listener_action,
)
import gritlib.console_runtime as console_runtime
from gritlib.console_help import print_concise_help, print_console_help_reference
from gritlib.console_runtime_controls import handle_runtime_control_args
from gritlib.line_repl_app import run_line_console
from gritlib.service_runtime import install_shutdown_handlers
from gritlib.version import grit_version


def _handle_console_subcommand(raw_argv):
    if raw_argv and raw_argv[0] == "artifact":
        return handle_artifact_command(
            raw_argv[1:],
            program=f"{Path(sys.argv[0]).name} artifact",
        )
    if raw_argv and raw_argv[0] == "bringup":
        return handle_bringup_command(raw_argv[1:])
    return None


def _load_console_invocation(raw_argv):
    parser = build_arg_parser()
    early_args = handle_early_console_args(
        raw_argv,
        parser,
        version_text=f"griTTYkit {grit_version()}",
        print_concise_help_func=print_concise_help,
        print_console_help_reference_func=print_console_help_reference,
    )
    if early_args.handled:
        return early_args.code, None, None
    args = parser.parse_args(early_args.argv)

    cfg = load_config(args.config)
    try:
        apply_console_arg_overrides(cfg, args)
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2, None, None
    return None, cfg, args


def main(argv=None):
    install_shutdown_handlers()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    subcommand_code = _handle_console_subcommand(raw_argv)
    if subcommand_code is not None:
        return subcommand_code
    invocation_code, cfg, args = _load_console_invocation(raw_argv)
    if invocation_code is not None:
        return invocation_code

    try:
        headless_code = handle_headless_action_args(cfg, args)
        if headless_code is not None:
            return headless_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    timeout = console_runtime.timeout_from_args(args)
    try:
        runtime_code = handle_runtime_control_args(cfg, args, timeout)
        if runtime_code is not None:
            return runtime_code
        staging_code, action, script_bytes, session_timeout = prepare_listener_action(
            cfg, args
        )
        if staging_code is not None:
            return staging_code
    except ValueError as exc:
        print(f"grit-console: {exc}", file=sys.stderr)
        return 2

    if not has_explicit_console_action(args) and not args.no_console:
        return run_line_console(cfg)

    return serve_console_listener_action(
        cfg,
        args,
        action,
        timeout=timeout,
        script_bytes=script_bytes,
        session_timeout=session_timeout,
    )
