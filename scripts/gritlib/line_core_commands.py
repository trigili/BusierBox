"""Grouped line-console workspace, options, probe, and survey dispatch."""

from gritlib.line_build import dispatch_line_build_command, parse_line_build_command
from gritlib.line_options import (
    dispatch_line_option_command,
    dispatch_line_target_metadata_command,
    parse_line_option_command,
    parse_line_target_metadata_command,
)
from gritlib.line_workspace import dispatch_line_workspace_command, parse_line_workspace_command
from gritlib.probe_commands import (
    dispatch_line_probe_command,
    dispatch_line_survey_command,
    parse_line_probe_command,
    parse_line_survey_command,
)


def dispatch_line_core_command(
    cmd,
    args,
    *,
    status_func=None,
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
):
    args = list(args or [])
    if workspace_cmd := parse_line_workspace_command(cmd, args):
        workspace_result = dispatch_line_workspace_command(
            workspace_cmd,
            status_func=status_func,
            ips_func=ips_func,
            workspace_func=workspace_func,
            reload_func=reload_func,
            root_func=root_func,
            info_func=info_func,
            next_func=next_func,
            options_func=options_func,
        )
        return "refresh" if workspace_result == "refresh" else "handled"
    if build_cmd := parse_line_build_command(cmd, args):
        dispatch_line_build_command(
            build_cmd,
            set_context_func=set_context_func,
            run_func=build_run_func,
        )
        return "handled"
    if option_cmd := parse_line_option_command(cmd, args):
        dispatch_line_option_command(
            option_cmd,
            set_global_func=set_global_option_func,
            set_context_func=set_context_option_func,
            unset_global_func=unset_global_option_func,
            unset_context_func=unset_context_option_func,
        )
        return "handled"
    if metadata_cmd := parse_line_target_metadata_command(cmd, args):
        dispatch_line_target_metadata_command(
            metadata_cmd,
            rename_func=rename_target_func,
            note_func=note_target_func,
            alias_func=alias_target_func,
        )
        return "handled"
    if probe_cmd := parse_line_probe_command(cmd, args):
        dispatch_line_probe_command(
            probe_cmd,
            set_context_func=set_context_func,
            results_func=probe_results_func,
            config_func=probe_config_func,
            clear_func=probe_clear_func,
            serve_func=probe_serve_func,
            delivery_func=probe_delivery_func,
            paste_func=probe_paste_func,
            script_func=probe_script_func,
            help_func=help_func,
            start_func=probe_start_func,
        )
        return "handled"
    if survey_cmd := parse_line_survey_command(cmd, args):
        dispatch_line_survey_command(
            survey_cmd,
            set_context_func=set_context_func,
            results_func=survey_results_func,
            config_func=survey_config_func,
            preset_func=survey_preset_func,
            help_func=help_func,
        )
        return "handled"
    return ""
