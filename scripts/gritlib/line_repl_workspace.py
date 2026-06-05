"""Line REPL workspace/status callback adapters."""

from gritlib.console_workbench import workbench_snapshot
import gritlib.config_utils as config_utils
import gritlib.line_context as line_context
from gritlib.line_network import print_line_local_ips
import gritlib.line_workspace as line_workspace


def build_default_line_workspace_callbacks(cfg):
    return build_line_workspace_callbacks(
        cfg,
        default_config=config_utils.DEFAULT_CONFIG,
        load_config_func=config_utils.load_config,
        defaults=config_utils.DEFAULTS,
        workbench_snapshot_func=workbench_snapshot,
        clear_module_context_func=line_context.clear_line_module_context,
        print_workspace_snapshot_func=line_workspace.print_line_workspace_snapshot,
        reload_config_func=line_workspace.reload_line_config_for_repl,
        clear_console_context_func=line_context.clear_line_console_context,
        local_ips_func=print_line_local_ips,
    )


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
