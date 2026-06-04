"""Line REPL core command callback adapters."""

from gritlib.line_core_commands import dispatch_line_core_command
from gritlib.line_repl_options import build_unset_line_option_callback
from gritlib.line_probe_serve import run_line_probe_serve
from gritlib.line_workspace import line_repl_status_bar


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
    print_func=print,
):
    def survey_uploads(limit=20):
        return find_survey_uploads_func(cfg, limit=limit)

    def dispatch_core(command, args):
        return dispatch_line_core_command(
            command,
            args,
            status_func=lambda: print_func(line_repl_status_bar(workbench_snapshot_func(cfg))),
            ips_func=lambda: local_ips_func(workbench_snapshot_func(cfg)),
            workspace_func=lambda: (
                clear_module_context_func(cfg, quiet=True),
                print_workspace_snapshot_func(workbench_snapshot_func(cfg)),
            ),
            reload_func=lambda: reload_config_func(
                cfg,
                default_config=default_config,
                load_config_fn=load_config_func,
                defaults=defaults,
                append_event_fn=append_event_fn,
            ),
            root_func=lambda quiet=False: clear_console_context_func(cfg, quiet=quiet),
            info_func=info_func,
            next_func=next_func,
            options_func=options_func,
            set_context_func=lambda module: set_context_func(cfg, module),
            build_run_func=lambda build_args: build_run_func(cfg, build_args),
            set_global_option_func=lambda key, value: set_global_option_func(cfg, key, value),
            set_context_option_func=lambda key, value: set_context_option_func(cfg, key, value),
            unset_global_option_func=lambda key: unset_global_option_func(cfg, key),
            unset_context_option_func=unset_context_option_func,
            rename_target_func=lambda value: rename_target_func(cfg, value),
            note_target_func=lambda value: note_target_func(cfg, value),
            alias_target_func=lambda value: alias_target_func(cfg, value),
            probe_results_func=lambda: probe_results_func(cfg, append_event_fn=append_event_fn),
            probe_config_func=lambda probe_args: probe_config_func(
                cfg,
                probe_args,
                append_event_fn=append_event_fn,
            ),
            probe_clear_func=lambda probe_args: probe_clear_func(
                cfg,
                probe_args,
                append_event_fn=append_event_fn,
            ),
            probe_serve_func=lambda probe_args: run_line_probe_serve(
                cfg,
                probe_args,
                probe_serve_input_func,
                probe_serve_stage_release_func,
                append_event_fn=append_event_fn,
            ),
            probe_delivery_func=lambda: probe_delivery_func(cfg),
            probe_paste_func=lambda base64_mode=False: probe_paste_func(
                cfg,
                paste=True,
                base64_mode=base64_mode,
            ),
            probe_script_func=lambda: probe_script_func(cfg, paste=False),
            help_func=help_func,
            probe_start_func=probe_start_func,
            survey_results_func=lambda: survey_results_func(cfg, append_event_fn=append_event_fn),
            survey_config_func=lambda survey_args: survey_config_func(
                cfg,
                survey_args,
                survey_uploads,
                append_event_fn=append_event_fn,
            ),
            survey_preset_func=lambda survey_args: survey_preset_func(
                cfg,
                survey_args,
                survey_uploads,
                append_event_fn=append_event_fn,
            ),
        )

    return dispatch_core
