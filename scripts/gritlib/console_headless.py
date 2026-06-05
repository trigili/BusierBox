"""Headless console action wiring for grit-console."""

import gritlib.bridge_routes as bridge_routes
from gritlib.build_config import handle_build_config_args
import gritlib.console_actions as console_actions
from gritlib.event_log import append_event
import gritlib.workbench_jobs as workbench_jobs
from gritlib.workflow_actions import workbench_action_records
import gritlib.workflow_runners as workflow_runners


def handle_headless_action_args(cfg, args):
    bridge_profile_code = console_actions.handle_bridge_profile_args(
        cfg,
        args,
        save_bridge_profile_func=bridge_routes.save_bridge_profile,
        delete_bridge_profile_func=bridge_routes.delete_bridge_profile,
        print_bridge_profile_func=bridge_routes.print_bridge_profile,
        print_bridge_profiles_func=bridge_routes.print_bridge_profiles,
        bridge_profiles_path_func=bridge_routes.bridge_profiles_path,
    )
    if bridge_profile_code is not None:
        return bridge_profile_code
    workbench_job_code = console_actions.handle_workbench_job_args(
        cfg,
        args,
        workbench_action_records_func=workbench_action_records,
        start_workbench_job_headless_command_func=workbench_jobs.start_workbench_job_headless_command,
        start_workbench_job_record_func=workbench_jobs.start_workbench_job_record,
        cancel_workbench_job_headless_command_func=workbench_jobs.cancel_workbench_job_headless_command,
        cancel_workbench_job_record_func=workbench_jobs.cancel_workbench_job_record,
        run_workbench_action_record_func=workbench_jobs.run_workbench_action_record,
    )
    if workbench_job_code is not None:
        return workbench_job_code
    workflow_code = console_actions.handle_workflow_action_args(
        cfg,
        args,
        run_service_workflow_action_func=workflow_runners.run_service_workflow_action,
        run_operator_daemon_workflow_action_func=workflow_runners.run_operator_daemon_workflow_action,
        run_release_artifact_workflow_action_func=workflow_runners.run_release_artifact_workflow_action,
        run_command_queue_workflow_action_func=workflow_runners.run_command_queue_workflow_action,
        run_probe_workflow_action_func=workflow_runners.run_probe_workflow_action,
        run_bridge_profile_workflow_action_func=workflow_runners.run_bridge_profile_workflow_action,
        run_file_service_workflow_action_func=workflow_runners.run_file_service_workflow_action,
        run_staged_file_workflow_action_func=workflow_runners.run_staged_file_workflow_action,
        run_target_workflow_action_func=workflow_runners.run_target_workflow_action,
    )
    if workflow_code is not None:
        return workflow_code
    build_config_code = handle_build_config_args(cfg, args, append_event_fn=append_event)
    if build_config_code is not None:
        return build_config_code
    return console_actions.handle_console_utility_args(
        cfg, args, append_event_fn=append_event
    )
