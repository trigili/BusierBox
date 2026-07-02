"""Grouped line-console workspace, options, probe, and survey dispatch."""

from gritlib.line_build import dispatch_line_build_command, parse_line_build_command
from gritlib.line_options import (
    dispatch_line_option_command,
    dispatch_line_target_metadata_command,
    parse_line_option_command,
    parse_line_target_metadata_command,
)
from gritlib.line_network import dispatch_line_ip_command, parse_line_ip_command
from gritlib.line_profile_serve import parse_line_listener_serve_command
from gritlib.line_profiles import dispatch_line_profile_command, parse_line_profile_command
from gritlib.line_workspace import dispatch_line_workspace_command, parse_line_workspace_command
from gritlib.probe_commands import (
    dispatch_line_probe_command,
    dispatch_line_survey_command,
    parse_line_listener_probe_command,
    parse_line_probe_command,
    parse_line_survey_command,
)


def _dispatch_line_workspace_family(
    cmd,
    args,
    callbacks,
):
    ip_cmd = parse_line_ip_command(cmd, args)
    if ip_cmd:
        if ip_cmd.get("action") == "show" and callbacks.get("set_context_func"):
            callbacks["set_context_func"]("ip")
        dispatch_line_ip_command(
            ip_cmd,
            snap_func=callbacks.get("workspace_snapshot_func"),
            set_option_func=callbacks.get("set_context_option_func"),
        )
        return "handled"
    workspace_cmd = parse_line_workspace_command(cmd, args)
    if not workspace_cmd:
        return ""
    workspace_result = dispatch_line_workspace_command(
        workspace_cmd,
        status_func=callbacks.get("status_func"),
        ips_func=callbacks.get("ips_func"),
        workspace_func=callbacks.get("workspace_func"),
        reload_func=callbacks.get("reload_func"),
        root_func=callbacks.get("root_func"),
        info_func=callbacks.get("info_func"),
        next_func=callbacks.get("next_func"),
        options_func=callbacks.get("options_func"),
    )
    return "refresh" if workspace_result == "refresh" else "handled"


def _dispatch_line_build_family(
    cmd,
    args,
    callbacks,
):
    build_cmd = parse_line_build_command(cmd, args)
    if not build_cmd:
        return ""
    dispatch_line_build_command(
        build_cmd,
        set_context_func=callbacks.get("set_context_func"),
        run_func=callbacks.get("build_run_func"),
    )
    return "handled"


def _dispatch_line_option_family(
    cmd,
    args,
    callbacks,
):
    option_cmd = parse_line_option_command(cmd, args)
    if not option_cmd:
        return ""
    dispatch_line_option_command(
        option_cmd,
        set_global_func=callbacks.get("set_global_option_func"),
        set_context_func=callbacks.get("set_context_option_func"),
        unset_global_func=callbacks.get("unset_global_option_func"),
        unset_context_func=callbacks.get("unset_context_option_func"),
    )
    return "handled"


def _dispatch_line_target_metadata_family(
    cmd,
    args,
    callbacks,
):
    metadata_cmd = parse_line_target_metadata_command(cmd, args)
    if not metadata_cmd:
        return ""
    dispatch_line_target_metadata_command(
        metadata_cmd,
        rename_func=callbacks.get("rename_target_func"),
        note_func=callbacks.get("note_target_func"),
        alias_func=callbacks.get("alias_target_func"),
    )
    return "handled"


def _dispatch_line_profile_family(cmd, args, callbacks):
    try:
        profile_cmd = parse_line_profile_command(cmd, args)
    except ValueError as exc:
        print(exc)
        return "handled"
    if not profile_cmd:
        return ""
    set_context_func = callbacks.get("set_context_func")
    if set_context_func:
        set_context_func("profiles")
    dispatch_line_profile_command(
        profile_cmd,
        profile_func=callbacks.get("profile_func"),
    )
    return "handled"


def _dispatch_line_profile_serve_family(cmd, args, callbacks):
    serve_cmd = parse_line_listener_serve_command(cmd, args)
    if not serve_cmd:
        return ""
    serve_func = callbacks.get("profile_serve_func")
    if serve_func:
        try:
            serve_func(args[1:] if args and str(args[0]).lower() == "serve" else args)
        except ValueError as exc:
            print(exc)
        return "handled"
    raise ValueError("profile serve support is unavailable")


def _dispatch_line_probe_family(
    cmd,
    args,
    callbacks,
):
    probe_cmd = parse_line_listener_probe_command(cmd, args)
    listener_scoped = bool(probe_cmd)
    if not probe_cmd:
        probe_cmd = parse_line_probe_command(cmd, args)
    if not probe_cmd:
        return ""
    set_context_func = callbacks.get("set_context_func")
    probe_context_func = (
        (lambda _module="": set_context_func("listener/probe"))
        if set_context_func else None
    )
    if listener_scoped and probe_context_func:
        probe_context_func()
    dispatch_line_probe_command(
        probe_cmd,
        set_context_func=probe_context_func,
        results_func=callbacks.get("probe_results_func"),
        config_func=callbacks.get("probe_config_func"),
        clear_func=callbacks.get("probe_clear_func"),
        serve_func=callbacks.get("probe_serve_func"),
        delivery_func=callbacks.get("probe_delivery_func"),
        paste_func=callbacks.get("probe_paste_func"),
        script_func=callbacks.get("probe_script_func"),
        help_func=callbacks.get("help_func"),
        options_func=callbacks.get("options_func"),
        start_func=callbacks.get("probe_start_func"),
    )
    return "handled"


def _dispatch_line_survey_family(
    cmd,
    args,
    callbacks,
):
    try:
        survey_cmd = parse_line_survey_command(cmd, args)
    except ValueError as exc:
        print(exc)
        return "handled"
    if not survey_cmd:
        return ""
    dispatch_line_survey_command(
        survey_cmd,
        set_context_func=callbacks.get("set_context_func"),
        results_func=callbacks.get("survey_results_func"),
        config_func=callbacks.get("survey_config_func"),
        preset_func=callbacks.get("survey_preset_func"),
        help_func=callbacks.get("help_func"),
    )
    return "handled"


def dispatch_line_core_command(
    cmd,
    args,
    *,
    status_func=None,
    workspace_snapshot_func=None,
    ips_func=None,
    workspace_func=None,
    reload_func=None,
    root_func=None,
    info_func=None,
    next_func=None,
    options_func=None,
    set_context_func=None,
    build_run_func=None,
    set_global_option_func=None,
    set_context_option_func=None,
    unset_global_option_func=None,
    unset_context_option_func=None,
    rename_target_func=None,
    note_target_func=None,
    alias_target_func=None,
    probe_results_func=None,
    probe_config_func=None,
    probe_clear_func=None,
    probe_serve_func=None,
    probe_delivery_func=None,
    probe_paste_func=None,
    probe_script_func=None,
    help_func=None,
    probe_start_func=None,
    survey_results_func=None,
    survey_config_func=None,
    survey_preset_func=None,
    profile_func=None,
    profile_serve_func=None,
):
    args = list(args or [])
    callbacks = locals()
    if workspace_result := _dispatch_line_workspace_family(cmd, args, callbacks):
        return workspace_result
    if _dispatch_line_build_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_option_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_target_metadata_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_profile_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_profile_serve_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_probe_family(cmd, args, callbacks):
        return "handled"
    if _dispatch_line_survey_family(cmd, args, callbacks):
        return "handled"
    return ""
