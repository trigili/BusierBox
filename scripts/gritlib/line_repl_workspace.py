"""Line REPL workspace/status callback adapters."""


def build_line_workspace_callbacks(
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
    local_ips_func,
):
    return {
        "default_config": default_config,
        "load_config": load_config_func,
        "defaults": defaults,
        "workbench_snapshot": workbench_snapshot_func,
        "clear_module_context": clear_module_context_func,
        "print_workspace_snapshot": print_workspace_snapshot_func,
        "reload_config": reload_config_func,
        "clear_console_context": clear_console_context_func,
        "local_ips": local_ips_func,
    }
