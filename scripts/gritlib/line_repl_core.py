"""Line REPL core command callback adapters."""

from gritlib.event_log import append_event
import gritlib.line_build as line_build
import gritlib.line_context as line_context
from gritlib.line_core_commands import dispatch_line_core_command
import gritlib.line_help as line_help
from gritlib.line_profiles import run_profile_command
from gritlib.line_repl_options import build_unset_line_option_callback
from gritlib.line_probe_serve import run_line_probe_serve
from gritlib.line_profile_serve import run_line_profile_serve
from gritlib.line_workspace import line_repl_status_bar
from gritlib.profiles import active_profile


def build_default_line_core_callbacks(
    cfg,
    *,
    line_probe_callbacks,
    line_file_callbacks,
    line_display_show_callbacks,
    line_option_callbacks,
    line_workspace_callbacks,
    line_survey_callbacks,
):
    return build_line_core_callbacks(
        cfg,
        clear_module_func=line_context.clear_line_module_context,
        probe_callbacks=line_probe_callbacks,
        file_callbacks=line_file_callbacks,
        display_callbacks=line_display_show_callbacks,
        option_callbacks=line_option_callbacks,
        workspace_callbacks=line_workspace_callbacks,
        survey_callbacks=line_survey_callbacks,
        set_context_func=line_context.set_line_collection_context,
        build_run_func=line_build.run_line_build_command,
        help_func=line_help.print_line_command_help,
        append_event_fn=append_event,
    )


def build_line_core_callbacks(
    cfg,
    *,
    clear_module_func,
    probe_callbacks=None,
    file_callbacks=None,
    display_callbacks=None,
    option_callbacks=None,
    workspace_callbacks=None,
    survey_callbacks=None,
    **dispatch_kwargs,
):
    if workspace_callbacks is not None:
        dispatch_kwargs.setdefault("default_config", workspace_callbacks["default_config"])
        dispatch_kwargs.setdefault("load_config_func", workspace_callbacks["load_config"])
        dispatch_kwargs.setdefault("defaults", workspace_callbacks["defaults"])
        dispatch_kwargs.setdefault("workbench_snapshot_func", workspace_callbacks["workbench_snapshot"])
        dispatch_kwargs.setdefault("clear_module_context_func", workspace_callbacks["clear_module_context"])
        dispatch_kwargs.setdefault("print_workspace_snapshot_func", workspace_callbacks["print_workspace_snapshot"])
        dispatch_kwargs.setdefault("reload_config_func", workspace_callbacks["reload_config"])
        dispatch_kwargs.setdefault("clear_console_context_func", workspace_callbacks["clear_console_context"])
        dispatch_kwargs.setdefault("local_ips_func", workspace_callbacks["local_ips"])
    if option_callbacks is not None:
        unset_line_option = option_callbacks["unset_line_option"]
        dispatch_kwargs.setdefault("set_global_option_func", option_callbacks["set_global_option"])
        dispatch_kwargs.setdefault("set_context_option_func", option_callbacks["set_context_option"])
        dispatch_kwargs.setdefault("unset_global_option_func", option_callbacks["unset_global_option"])
        dispatch_kwargs.setdefault("rename_target_func", option_callbacks["rename_target"])
        dispatch_kwargs.setdefault("note_target_func", option_callbacks["note_target"])
        dispatch_kwargs.setdefault("alias_target_func", option_callbacks["alias_target"])
    else:
        unset_line_option = build_unset_line_option_callback(
            cfg,
            clear_module_func=clear_module_func,
        )
    if survey_callbacks is not None:
        dispatch_kwargs.setdefault("survey_results_func", survey_callbacks["survey_results"])
        dispatch_kwargs.setdefault("find_survey_uploads_func", survey_callbacks["find_survey_uploads"])
        dispatch_kwargs.setdefault("survey_config_func", survey_callbacks["survey_config"])
        dispatch_kwargs.setdefault("survey_preset_func", survey_callbacks["survey_preset"])
    if probe_callbacks is not None:
        dispatch_kwargs.setdefault("probe_start_func", probe_callbacks["probe_line_start"])
        if probe_callbacks.get("probe_results") is not None:
            dispatch_kwargs.setdefault("probe_results_func", probe_callbacks["probe_results"])
        if probe_callbacks.get("probe_config") is not None:
            dispatch_kwargs.setdefault("probe_config_func", probe_callbacks["probe_config"])
        if probe_callbacks.get("probe_clear") is not None:
            dispatch_kwargs.setdefault("probe_clear_func", probe_callbacks["probe_clear"])
        if probe_callbacks.get("probe_serve_input") is not None:
            dispatch_kwargs.setdefault("probe_serve_input_func", probe_callbacks["probe_serve_input"])
        if probe_callbacks.get("probe_delivery") is not None:
            dispatch_kwargs.setdefault("probe_delivery_func", probe_callbacks["probe_delivery"])
        if probe_callbacks.get("probe_paste") is not None:
            dispatch_kwargs.setdefault("probe_paste_func", probe_callbacks["probe_paste"])
        if probe_callbacks.get("probe_script") is not None:
            dispatch_kwargs.setdefault("probe_script_func", probe_callbacks["probe_script"])
    if file_callbacks is not None:
        dispatch_kwargs.setdefault("probe_serve_stage_release_func", file_callbacks["stage_release"])
    if display_callbacks is not None:
        dispatch_kwargs.setdefault("info_func", display_callbacks["print_line_info"])
        dispatch_kwargs.setdefault("next_func", display_callbacks["print_line_next"])
        dispatch_kwargs.setdefault("options_func", display_callbacks["print_line_options"])
    dispatch_line_core = build_line_core_dispatch_callback(
        cfg,
        unset_context_option_func=unset_line_option,
        **dispatch_kwargs,
    )
    return {
        "dispatch_line_core": dispatch_line_core,
        "unset_line_option": unset_line_option,
    }


def _core_survey_uploads(ctx, limit=20):
    return ctx["find_survey_uploads_func"](ctx["cfg"], limit=limit)


def _core_workspace_snapshot(ctx):
    snap = dict(ctx["workbench_snapshot_func"](ctx["cfg"]))
    profile = active_profile(ctx["cfg"])
    if profile:
        snap["active_profile"] = profile
    return snap


def _core_show_root_workspace(ctx):
    cfg = ctx["cfg"]
    ctx["clear_console_context_func"](cfg, quiet=True)
    ctx["print_workspace_snapshot_func"](_core_workspace_snapshot(ctx))


def _core_workspace_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "status_func": lambda: ctx["print_func"](line_repl_status_bar(_core_workspace_snapshot(ctx))),
        "workspace_snapshot_func": lambda: _core_workspace_snapshot(ctx),
        "ips_func": lambda: ctx["local_ips_func"](_core_workspace_snapshot(ctx)),
        "workspace_func": lambda: _core_show_root_workspace(ctx),
        "reload_func": lambda: ctx["reload_config_func"](
            cfg,
            default_config=ctx["default_config"],
            load_config_fn=ctx["load_config_func"],
            defaults=ctx["defaults"],
            append_event_fn=ctx["append_event_fn"],
        ),
        "root_func": lambda quiet=False: ctx["clear_console_context_func"](cfg, quiet=quiet),
        "info_func": ctx["info_func"],
        "next_func": ctx["next_func"],
        "options_func": ctx["options_func"],
        "set_context_func": lambda module: ctx["set_context_func"](cfg, module),
        "build_run_func": lambda build_args: ctx["build_run_func"](cfg, build_args),
        "profile_func": lambda profile_cmd: ctx["profile_func"](
            cfg,
            profile_cmd,
            append_event_fn=ctx["append_event_fn"],
        ),
    }


def _core_option_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "set_global_option_func": lambda key, value: ctx["set_global_option_func"](cfg, key, value),
        "set_context_option_func": lambda key, value: ctx["set_context_option_func"](cfg, key, value),
        "unset_global_option_func": lambda key: ctx["unset_global_option_func"](cfg, key),
        "unset_context_option_func": ctx["unset_context_option_func"],
        "rename_target_func": lambda value: ctx["rename_target_func"](cfg, value),
        "note_target_func": lambda value: ctx["note_target_func"](cfg, value),
        "alias_target_func": lambda value: ctx["alias_target_func"](cfg, value),
    }


def _core_probe_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "probe_results_func": lambda: ctx["probe_results_func"](cfg, append_event_fn=ctx["append_event_fn"]),
        "probe_config_func": lambda probe_args: ctx["probe_config_func"](
            cfg,
            probe_args,
            append_event_fn=ctx["append_event_fn"],
        ),
        "probe_clear_func": lambda probe_args: ctx["probe_clear_func"](
            cfg,
            probe_args,
            append_event_fn=ctx["append_event_fn"],
        ),
        "probe_serve_func": lambda probe_args: run_line_probe_serve(
            cfg,
            probe_args,
            ctx["probe_serve_input_func"],
            ctx["probe_serve_stage_release_func"],
            append_event_fn=ctx["append_event_fn"],
        ),
        "probe_delivery_func": lambda: ctx["probe_delivery_func"](cfg),
        "probe_paste_func": lambda base64_mode=False, copy=False: ctx["probe_paste_func"](
            cfg,
            paste=True,
            base64_mode=base64_mode,
            copy=copy,
        ),
        "probe_script_func": lambda: ctx["probe_script_func"](cfg, paste=False),
        "profile_serve_func": lambda serve_args: ctx["profile_serve_func"](
            cfg,
            serve_args,
            stage_line_release_fn=ctx["probe_serve_stage_release_func"],
            append_event_fn=ctx["append_event_fn"],
        ),
    }


def _core_help_survey_dispatch_kwargs(ctx):
    cfg = ctx["cfg"]
    return {
        "help_func": ctx["help_func"],
        "probe_start_func": ctx["probe_start_func"],
        "survey_results_func": lambda: ctx["survey_results_func"](cfg, append_event_fn=ctx["append_event_fn"]),
        "survey_config_func": lambda survey_args: ctx["survey_config_func"](
            cfg,
            survey_args,
            lambda limit=20: _core_survey_uploads(ctx, limit=limit),
            append_event_fn=ctx["append_event_fn"],
        ),
        "survey_preset_func": lambda survey_args: ctx["survey_preset_func"](
            cfg,
            survey_args,
            lambda limit=20: _core_survey_uploads(ctx, limit=limit),
            append_event_fn=ctx["append_event_fn"],
        ),
    }


def _core_dispatch_kwargs(ctx):
    kwargs = {}
    kwargs.update(_core_workspace_dispatch_kwargs(ctx))
    kwargs.update(_core_option_dispatch_kwargs(ctx))
    kwargs.update(_core_probe_dispatch_kwargs(ctx))
    kwargs.update(_core_help_survey_dispatch_kwargs(ctx))
    return kwargs


def build_line_core_dispatch_callback(
    cfg,
    *,
    default_config,
    load_config_func,
    defaults,
    workbench_snapshot_func,
    clear_module_context_func,
    print_workspace_snapshot_func,
    reload_config_func,
    clear_console_context_func,
    info_func,
    next_func,
    options_func,
    set_context_func,
    build_run_func,
    set_global_option_func,
    set_context_option_func,
    unset_global_option_func,
    unset_context_option_func,
    rename_target_func,
    note_target_func,
    alias_target_func,
    local_ips_func,
    probe_results_func,
    probe_config_func,
    probe_clear_func,
    probe_serve_input_func,
    probe_serve_stage_release_func,
    probe_delivery_func,
    probe_paste_func,
    probe_script_func,
    help_func,
    probe_start_func,
    survey_results_func,
    find_survey_uploads_func,
    survey_config_func,
    survey_preset_func,
    append_event_fn,
    profile_func=run_profile_command,
    profile_serve_func=run_line_profile_serve,
    print_func=print,
):
    ctx = locals()

    def dispatch_core(command, args):
        return dispatch_line_core_command(
            command,
            args,
            **_core_dispatch_kwargs(ctx),
        )

    return dispatch_core
