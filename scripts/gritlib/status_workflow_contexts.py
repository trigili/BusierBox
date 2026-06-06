"""Workflow-scoped status context builders for grit-console."""

import gritlib.command_queue_workflow_actions as command_queue_workflow_actions_module
from gritlib.probe_commands import probe_workflow_action_records
import gritlib.service_status as service_status
import gritlib.staged_file_workflow_actions as staged_file_workflow_actions_module
import gritlib.staged_files as staged_files
import gritlib.workflow_actions as workflow_actions


def build_workbench_workflow_status_context(cfg, targets, bridge_profiles):
    workbench_action_context = workflow_actions.workbench_action_status_context(cfg)
    workbench_actions = workbench_action_context["actions"]
    operator_daemon_workflow_context = (
        workflow_actions.operator_daemon_workflow_action_status_context(
            cfg,
            workbench_actions,
            targets,
        )
    )
    target_workflow_context = workflow_actions.target_workflow_action_status_context(
        cfg,
        targets,
        bridge_profiles,
    )
    workbench_job_context = workflow_actions.workbench_job_status_context(
        cfg, workbench_actions
    )
    operator_daemon_workflow_actions = operator_daemon_workflow_context["actions"]
    target_workflow_actions = target_workflow_context["actions"]
    workbench_jobs = workbench_job_context["jobs"]
    return {
        "workbench_action_context": workbench_action_context,
        "workbench_actions": workbench_actions,
        "workbench_action_index_maps": workbench_action_context["index_maps"],
        "operator_daemon_workflow_actions": operator_daemon_workflow_actions,
        "operator_daemon_workflow_action_index_maps": operator_daemon_workflow_context[
            "index_maps"
        ],
        "target_workflow_actions": target_workflow_actions,
        "target_workflow_action_index_maps": target_workflow_context["index_maps"],
        "workbench_job_context": workbench_job_context,
        "workbench_jobs": workbench_jobs,
        "workbench_job_index_maps": workbench_job_context["index_maps"],
        "summary": {
            **workflow_actions.target_workflow_action_status_summary(
                target_workflow_actions
            ),
            **workbench_action_context["summary"],
            **workflow_actions.operator_daemon_workflow_action_status_summary(
                operator_daemon_workflow_actions
            ),
            **workbench_job_context["summary"],
        },
    }


def build_staged_file_workflow_status_context(cfg, staged_records, targets):
    staged_file_workflow_actions = staged_file_workflow_actions_module.staged_file_workflow_action_records(
        cfg,
        staged_records,
        targets,
    )
    return {
        "staged_file_workflow_actions": staged_file_workflow_actions,
        "staged_file_workflow_action_index_maps": (
            staged_file_workflow_actions_module.staged_file_workflow_action_indexes(
                staged_file_workflow_actions
            )
        ),
        "summary": staged_files.staged_status_summary(
            staged_records,
            staged_file_workflow_actions,
        ),
    }


def build_command_queue_workflow_status_context(
    cfg,
    command_queue,
    target_mailbox_records,
    command_queue_service,
    targets,
):
    command_queue_workflow_actions = (
        command_queue_workflow_actions_module.command_queue_workflow_action_records(
            cfg,
            command_queue,
            target_mailbox_records,
            command_queue_service,
            targets,
        )
    )
    return {
        "command_queue_workflow_actions": command_queue_workflow_actions,
        "command_queue_workflow_action_index_maps": (
            command_queue_workflow_actions_module.command_queue_workflow_action_indexes(
                command_queue_workflow_actions
            )
        ),
        "summary": command_queue_workflow_actions_module.command_queue_workflow_action_status_summary(
            command_queue_workflow_actions
        ),
    }


def build_service_probe_workflow_status_context(
    cfg,
    services,
    services_by_name,
    targets,
):
    service_workflow_actions = service_status.service_workflow_action_records(
        cfg, services, targets
    )
    probe_workflow_actions = probe_workflow_action_records(
        cfg,
        services_by_name.get("probe") or {},
        targets,
    )
    return {
        "service_workflow_actions": service_workflow_actions,
        "service_workflow_action_index_maps": service_status.service_workflow_action_indexes(
            service_workflow_actions
        ),
        "probe_workflow_actions": probe_workflow_actions,
        "probe_workflow_action_index_maps": (
            workflow_actions.probe_workflow_action_indexes(
                probe_workflow_actions
            )
        ),
        "summary": {
            **service_status.service_workflow_action_status_summary(
                service_workflow_actions
            ),
            **workflow_actions.probe_workflow_action_status_summary(
                probe_workflow_actions
            ),
        },
    }


def build_operator_console_workflow_status_context(
    cfg,
    *,
    targets,
    target_workflow_actions,
    target_mailbox_records,
    bridge_profiles,
    bridge_profile_workflow_actions,
    staged_records,
    staged_file_workflow_actions,
    file_service_workflow_actions,
    probe_workflow_actions,
    command_queue_workflow_actions,
    service_workflow_actions,
    operator_daemon_workflow_actions,
    workbench_actions,
    workbench_config_fields,
    workbench_jobs,
    target_activity_records,
    release_artifact_workflow_actions,
    release,
    warnings,
):
    operator_console_workflows = workflow_actions.operator_console_workflow_records(
        cfg,
        targets=targets,
        target_workflow_actions=target_workflow_actions,
        target_mailbox_records=target_mailbox_records,
        bridge_profiles=bridge_profiles,
        bridge_profile_workflow_actions=bridge_profile_workflow_actions,
        staged_records=staged_records,
        staged_file_workflow_actions=staged_file_workflow_actions,
        file_service_workflow_actions=file_service_workflow_actions,
        probe_workflow_actions=probe_workflow_actions,
        command_queue_workflow_actions=command_queue_workflow_actions,
        service_workflow_actions=service_workflow_actions,
        operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        workbench_actions=workbench_actions,
        workbench_config_fields=workbench_config_fields,
        workbench_jobs=workbench_jobs,
        target_activity_records=target_activity_records,
        release_artifact_workflow_actions=release_artifact_workflow_actions,
        release=release,
        warnings=warnings,
    )
    operator_console_workflow_stats = (
        workflow_actions.operator_console_workflow_summary(
            operator_console_workflows
        )
    )
    return {
        "operator_console_workflows": operator_console_workflows,
        "operator_console_workflow_index_maps": (
            workflow_actions.operator_console_workflow_indexes(
                operator_console_workflows
            )
        ),
        "operator_console_workflow_stats": operator_console_workflow_stats,
        "summary": workflow_actions.operator_console_workflow_status_summary(
            operator_console_workflow_stats
        ),
    }
