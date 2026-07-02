"""Line REPL display callback adapters."""

from gritlib.line_options import print_line_options
from gritlib.line_workspace import print_current_line_info, print_current_line_next
from gritlib.operator_io import view_path_headless_command
from gritlib.workbench_jobs import cancel_workbench_job_headless_command


def build_line_display_callbacks(
    cfg,
    *,
    workbench_snapshot_func,
    selected_action_func,
    service_status_rows_func,
    service_record_func,
    route_record_func,
    session_record_func,
    job_record_func,
    probe_delivery_func,
    bridge_command_builder,
    display_name_func,
    build_fields_func,
    target_command_records_func,
):
    def print_info():
        return print_current_line_info(
            cfg,
            workbench_snapshot_func(cfg),
            selected_action=selected_action_func,
            service_record=lambda service: service_record_func(service_status_rows_func(cfg), service),
            route_record=route_record_func,
            session_record=session_record_func,
            job_record=job_record_func,
            probe_delivery_printer=lambda: probe_delivery_func(cfg),
            bridge_command_builder=bridge_command_builder,
            view_command_builder=lambda path: view_path_headless_command(cfg, path),
            cancel_job_command_builder=lambda job_id: cancel_workbench_job_headless_command(cfg, job_id),
        )

    def print_next():
        return print_current_line_next(
            cfg,
            workbench_snapshot_func(cfg),
            selected_action=selected_action_func,
            route_record=route_record_func,
            job_record=job_record_func,
        )

    def print_options():
        module = str(cfg.get("_line_console_module") or "root")
        return print_line_options(
            cfg,
            module=module,
            service_record_func=lambda service: service_record_func(service_status_rows_func(cfg), service),
            display_name_func=display_name_func,
            build_fields_func=lambda: build_fields_func(cfg),
            target_command_records_func=lambda: target_command_records_func(cfg),
            route_record_func=route_record_func,
            session_record_func=session_record_func,
            job_record_func=job_record_func,
            selected_action_func=selected_action_func,
        )

    return print_info, print_next, print_options
