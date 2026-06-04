"""Line REPL option callback adapters."""

from gritlib.line_options import unset_line_target_option


def build_unset_line_option_callback(
    cfg,
    *,
    clear_module_func,
    unset_target_option_func=unset_line_target_option,
):
    def unset_line_option(name):
        return unset_target_option_func(
            cfg,
            name,
            clear_module=lambda quiet=False: clear_module_func(cfg, quiet=quiet),
        )

    return unset_line_option


def build_line_option_callbacks(
    cfg,
    *,
    clear_module_func,
    set_global_option_func,
    set_context_option_func,
    unset_global_option_func,
    rename_target_func,
    note_target_func,
    alias_target_func,
    unset_target_option_func=unset_line_target_option,
):
    unset_line_option = build_unset_line_option_callback(
        cfg,
        clear_module_func=clear_module_func,
        unset_target_option_func=unset_target_option_func,
    )
    return {
        "set_global_option": set_global_option_func,
        "set_context_option": set_context_option_func,
        "unset_global_option": unset_global_option_func,
        "unset_line_option": unset_line_option,
        "rename_target": rename_target_func,
        "note_target": note_target_func,
        "alias_target": alias_target_func,
    }
