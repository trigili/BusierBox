"""Line REPL option callback adapters."""

from gritlib.build_config import workbench_config_field_records
from gritlib import line_build
from gritlib import line_context
from gritlib import line_options
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
    build_fields_func=None,
    unset_target_option_func=unset_line_target_option,
):
    unset_line_option = build_unset_line_option_callback(
        cfg,
        clear_module_func=clear_module_func,
        unset_target_option_func=unset_target_option_func,
    )

    def workbench_config_fields():
        return build_fields_func(cfg) if build_fields_func is not None else []

    return {
        "set_global_option": set_global_option_func,
        "set_context_option": set_context_option_func,
        "unset_global_option": unset_global_option_func,
        "unset_line_option": unset_line_option,
        "rename_target": rename_target_func,
        "note_target": note_target_func,
        "alias_target": alias_target_func,
        "workbench_config_fields": workbench_config_fields,
    }


def build_default_line_option_callbacks(cfg):
    return build_line_option_callbacks(
        cfg,
        clear_module_func=line_context.clear_line_module_context,
        set_global_option_func=line_build.set_line_global_build_option,
        set_context_option_func=line_options.set_line_option,
        unset_global_option_func=line_build.unset_line_global_build_option,
        rename_target_func=line_options.rename_line_target,
        note_target_func=line_options.note_line_target,
        alias_target_func=line_options.alias_line_target,
        build_fields_func=workbench_config_field_records,
    )
