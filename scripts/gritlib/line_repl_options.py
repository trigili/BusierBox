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
