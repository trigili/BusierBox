"""File-service workflow action helpers for grit-console."""

from gritlib.bridge_routes import target_route_context
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.shell_utils import shquote
from gritlib.target_context import configured_target_filter
from gritlib.workflow_support import (
    optional_target_id_arg, optional_target_scoped_command,
    scoped_service_workflow_run_command, workflow_fleet_metrics,
)


def file_service_workflow_action_record(
    action_id,
    category,
    label,
    command,
    workflow,
    run_command,
    target_filter_id,
    route,
    service_row,
    listen_port,
    fallback_bind_address,
    staged_count,
    upload_count,
    fetch_count,
    transfer_count,
    fleet_metrics,
    action_state,
    action_reason,
    available=True,
    requires_input=False,
    requires_confirmation=False,
    queues_offline_work=False,
    target_phone_home_required=False,
    can_run_from_curses_enter=False,
    curses_enter_action="",
):
    route = route or {}
    service_row = service_row or {}
    return {
        "id": f"file-service:{action_id}",
        "action_id": action_id,
        "service": "file-service",
        "actual": str(service_row.get("actual") or "unknown"),
        "configured": str(service_row.get("configured") or ""),
        "category": category,
        "workflow": workflow,
        "label": label,
        "command": command,
        "headless_command": command,
        "run_command": run_command,
        "target_id_filter": target_filter_id,
        "target_filter_active": bool(target_filter_id),
        "route_kind": str(route.get("route_kind") or "direct"),
        "route_host": str(route.get("host") or ""),
        "route_port": route.get("port", ""),
        "bridge_profile": str(route.get("bridge_profile") or ""),
        "bridge_route_path": str(route.get("bridge_route_path") or ""),
        "requires_bridge": bool(route.get("requires_bridge", False)),
        "port": service_row.get("port", listen_port),
        "bind_address": str(service_row.get("bind_address") or fallback_bind_address or ""),
        "tls": bool(service_row.get("tls", False)),
        "pid": service_row.get("pid", ""),
        "pid_alive": bool(service_row.get("pid_alive", False)),
        "staged_count": staged_count,
        "upload_count": upload_count,
        "fetch_count": fetch_count,
        "target_file_transfer_record_count": transfer_count,
        **(fleet_metrics or {}),
        "available": bool(available),
        "requires_input": bool(requires_input),
        "requires_confirmation": bool(requires_confirmation),
        "requires_target_online": False,
        "queues_offline_work": bool(queues_offline_work),
        "target_phone_home_required": bool(target_phone_home_required),
        "operator_action_state": action_state,
        "operator_action_reason": action_reason,
        "can_run_from_curses_enter": bool(can_run_from_curses_enter),
        "curses_enter_action": curses_enter_action,
        "execution_default": "show-command",
        "target_execution": False,
        "tui_visible": True,
        "safety_boundary": "operator-side file workflow metadata; target submissions and staged delivery still require explicit target-side command or poll",
    }


def _file_service_workflow_context(
    cfg,
    service_row,
    staged_records=None,
    uploads=None,
    fetches=None,
    transfer_records=None,
    targets=None,
    render_file_service_command_func=None,
):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    base = "scripts/grit-console --config " + shquote(config_path)
    service_row = service_row if isinstance(service_row, dict) else {}
    target_filter_id = configured_target_filter(cfg)
    target_arg = optional_target_id_arg(target_filter_id)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=operator_advertised_host(cfg),
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    target_records = [rec for rec in (targets or []) if isinstance(rec, dict)]
    return {
        "base": base,
        "service_row": service_row,
        "target_filter_id": target_filter_id,
        "target_arg": target_arg,
        "route": route,
        "listen_port": cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
        "fallback_bind_address": cfg.get("listen_host", ""),
        "staged_count": len([rec for rec in staged_records or [] if isinstance(rec, dict)]),
        "upload_count": len([rec for rec in uploads or [] if isinstance(rec, dict)]),
        "fetch_count": len([rec for rec in fetches or [] if isinstance(rec, dict)]),
        "transfer_count": len([rec for rec in transfer_records or [] if isinstance(rec, dict)]),
        "fleet_metrics": workflow_fleet_metrics(target_records),
        "render_file_service_command_func": render_file_service_command_func,
    }


def _file_service_workflow_action(context, action_id, category, label, command, workflow,
                                  action_state, action_reason, available=True,
                                  requires_input=False, requires_confirmation=False,
                                  queues_offline_work=False,
                                  target_phone_home_required=False,
                                  can_run_from_curses_enter=False,
                                  curses_enter_action=""):
    return file_service_workflow_action_record(
        action_id,
        category,
        label,
        command,
        workflow,
        scoped_service_workflow_run_command(
            context["base"],
            context["target_arg"],
            "file-service",
            action_id,
        ),
        context["target_filter_id"],
        context["route"],
        context["service_row"],
        context["listen_port"],
        context["fallback_bind_address"],
        context["staged_count"],
        context["upload_count"],
        context["fetch_count"],
        context["transfer_count"],
        context["fleet_metrics"],
        action_state,
        action_reason,
        available=available,
        requires_input=requires_input,
        requires_confirmation=requires_confirmation,
        queues_offline_work=queues_offline_work,
        target_phone_home_required=target_phone_home_required,
        can_run_from_curses_enter=can_run_from_curses_enter,
        curses_enter_action=curses_enter_action,
    )


def _file_service_inspect_workflow_actions(context):
    base = context["base"]
    target_arg = context["target_arg"]
    return [
        _file_service_workflow_action(
            context,
            "inspect-file-workflows",
            "inspect",
            "Inspect file service, staged files, uploads, fetches, and target file records",
            optional_target_scoped_command(base, target_arg, " --status"),
            "file-service",
            "ready",
            "run-now",
        ),
        _file_service_workflow_action(
            context,
            "list-staged-files",
            "staged",
            "List staged files and commands to run on targets",
            optional_target_scoped_command(base, target_arg, " --list-staged"),
            "staged-files",
            "ready",
            "run-now",
            can_run_from_curses_enter=True,
            curses_enter_action="list-staged-files",
        ),
    ]


def _file_service_staged_upload_workflow_actions(cfg, context):
    base = context["base"]
    target_arg = context["target_arg"]
    stage_action = _file_service_workflow_action(
        context,
        "stage-file",
        "staged",
        "Stage a local file for deliver commands",
        optional_target_scoped_command(base, target_arg, " --serve-file LOCAL_PATH --as REQUEST_NAME --list-staged"),
        "staged-files",
        "needs-input",
        "input-required",
        requires_input=True,
    )
    stage_action["run_command"] = scoped_service_workflow_run_command(
        base,
        target_arg,
        "file-service",
        "stage-file",
        " --file-service-workflow-local-file LOCAL_PATH --file-service-workflow-request-name REQUEST_NAME",
    )
    upload_action = _file_service_workflow_action(
        context,
        "show-upload-command",
        "upload",
        "Show target upload command for a target path",
        optional_target_scoped_command(base, target_arg, " --status"),
        "target-upload",
        "needs-input",
        "input-required",
        requires_input=True,
    )
    render_command = context.get("render_file_service_command_func")
    upload_action["target_command_template"] = (
        render_command(["put", "TARGET_PATH"], cfg, host=context["route"].get("host"))
        if render_command else ""
    )
    upload_action["run_command"] = scoped_service_workflow_run_command(
        base,
        target_arg,
        "file-service",
        "show-upload-command",
        " --file-service-workflow-target-path TARGET_PATH",
    )
    return [stage_action, upload_action]


def _file_service_lifecycle_workflow_actions(cfg, context):
    # Local import preserves the service_status -> staged_files -> file_transfers
    # top-level boundary while keeping lifecycle command text service-owned.
    from gritlib.service_status import (
        service_lifecycle_action_states, service_start_headless_command,
        service_stop_headless_command,
    )

    base = context["base"]
    target_arg = context["target_arg"]
    lifecycle_states = service_lifecycle_action_states(context["service_row"])
    start_action = _file_service_workflow_action(
        context,
        "start-file-service",
        "service",
        "Start file service listener",
        service_start_headless_command(cfg, "file-service"),
        "service-lifecycle",
        lifecycle_states["start_state"],
        lifecycle_states["start_reason"],
        can_run_from_curses_enter=lifecycle_states["start_enter"],
        curses_enter_action="start-file-service" if lifecycle_states["start_enter"] else "stop-file-service",
    )
    stop_action = _file_service_workflow_action(
        context,
        "stop-file-service",
        "service",
        "Stop file service listener",
        service_stop_headless_command(cfg, "file-service"),
        "service-lifecycle",
        lifecycle_states["stop_state"],
        lifecycle_states["stop_reason"],
        requires_confirmation=True,
        can_run_from_curses_enter=lifecycle_states["stop_enter"],
        curses_enter_action="stop-file-service" if lifecycle_states["stop_enter"] else "start-file-service",
    )
    stop_action["run_command"] = scoped_service_workflow_run_command(
        base,
        target_arg,
        "file-service",
        "stop-file-service",
        " --confirm-file-service-workflow-action",
    )
    return [start_action, stop_action]


def file_service_workflow_action_records(
    cfg,
    service_row,
    staged_records=None,
    uploads=None,
    fetches=None,
    transfer_records=None,
    targets=None,
    render_file_service_command_func=None,
):
    context = _file_service_workflow_context(
        cfg,
        service_row,
        staged_records=staged_records,
        uploads=uploads,
        fetches=fetches,
        transfer_records=transfer_records,
        targets=targets,
        render_file_service_command_func=render_file_service_command_func,
    )
    records = []
    records.extend(_file_service_inspect_workflow_actions(context))
    records.extend(_file_service_staged_upload_workflow_actions(cfg, context))
    records.extend(_file_service_lifecycle_workflow_actions(cfg, context))
    records.sort(key=lambda rec: (rec.get("category", ""), rec.get("action_id", "")))
    return records


def file_service_workflow_action_indexes(records):
    return {
        "file_service_workflow_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "file_service_workflow_actions_by_action_id": records_by_key(records, "action_id"),
        "file_service_workflow_actions_by_service": records_by_key(records, "service"),
        "file_service_workflow_actions_by_category": records_by_key(records, "category"),
        "file_service_workflow_actions_by_workflow": records_by_key(records, "workflow"),
        "file_service_workflow_actions_by_actual": records_by_key(records, "actual"),
        "file_service_workflow_actions_by_configured": records_by_key(records, "configured"),
        "file_service_workflow_actions_by_target_filter_active": records_by_key(records, "target_filter_active"),
        "file_service_workflow_actions_by_route_kind": records_by_key(records, "route_kind"),
        "file_service_workflow_actions_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "file_service_workflow_actions_by_requires_bridge": records_by_key(records, "requires_bridge"),
        "file_service_workflow_actions_by_fleet_target_count": records_by_key(records, "fleet_target_count"),
        "file_service_workflow_actions_by_fleet_offline_target_count": records_by_key(records, "fleet_offline_target_count"),
        "file_service_workflow_actions_by_fleet_stale_target_count": records_by_key(records, "fleet_stale_target_count"),
        "file_service_workflow_actions_by_fleet_mailbox_pending_target_count": records_by_key(records, "fleet_mailbox_pending_target_count"),
        "file_service_workflow_actions_by_fleet_mailbox_pending_work_count": records_by_key(records, "fleet_mailbox_pending_work_count"),
        "file_service_workflow_actions_by_fleet_poll_overdue_target_count": records_by_key(records, "fleet_poll_overdue_target_count"),
        "file_service_workflow_actions_by_fleet_has_offline_targets": records_by_key(records, "fleet_has_offline_targets"),
        "file_service_workflow_actions_by_fleet_has_stale_targets": records_by_key(records, "fleet_has_stale_targets"),
        "file_service_workflow_actions_by_fleet_has_mailbox_pending_work": records_by_key(records, "fleet_has_mailbox_pending_work"),
        "file_service_workflow_actions_by_fleet_has_poll_overdue_targets": records_by_key(records, "fleet_has_poll_overdue_targets"),
        "file_service_workflow_actions_by_available": records_by_key(records, "available"),
        "file_service_workflow_actions_by_requires_input": records_by_key(records, "requires_input"),
        "file_service_workflow_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "file_service_workflow_actions_by_queues_offline_work": records_by_key(records, "queues_offline_work"),
        "file_service_workflow_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "file_service_workflow_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "file_service_workflow_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "file_service_workflow_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def file_service_workflow_status_context(
    cfg,
    service_row,
    staged_records=None,
    uploads=None,
    fetches=None,
    transfer_records=None,
    targets=None,
    render_file_service_command_func=None,
):
    actions = file_service_workflow_action_records(
        cfg,
        service_row,
        staged_records,
        uploads,
        fetches,
        transfer_records,
        targets,
        render_file_service_command_func=render_file_service_command_func,
    )
    return {
        "actions": actions,
        "index_maps": file_service_workflow_action_indexes(actions),
    }


def file_service_workflow_action_summary(records):
    return {
        "total_count": len(records or []),
        "available_count": len([rec for rec in records or [] if rec.get("available") is True]),
        "requires_input_count": len([rec for rec in records or [] if rec.get("requires_input") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "queues_offline_work_count": len([rec for rec in records or [] if rec.get("queues_offline_work") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "action_counts": record_count_by_key(records, "action_id"),
        "service_counts": record_count_by_key(records, "service"),
        "category_counts": record_count_by_key(records, "category"),
        "workflow_counts": record_count_by_key(records, "workflow"),
        "actual_counts": record_count_by_key(records, "actual"),
        "configured_counts": record_count_by_key(records, "configured"),
        "target_filter_active_counts": record_count_by_key(records, "target_filter_active"),
        "route_kind_counts": record_count_by_key(records, "route_kind"),
        "bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "requires_bridge_counts": record_count_by_key(records, "requires_bridge"),
        "fleet_target_count_counts": record_count_by_key(records, "fleet_target_count"),
        "fleet_offline_target_count_counts": record_count_by_key(records, "fleet_offline_target_count"),
        "fleet_stale_target_count_counts": record_count_by_key(records, "fleet_stale_target_count"),
        "fleet_mailbox_pending_target_count_counts": record_count_by_key(records, "fleet_mailbox_pending_target_count"),
        "fleet_mailbox_pending_work_count_counts": record_count_by_key(records, "fleet_mailbox_pending_work_count"),
        "fleet_poll_overdue_target_count_counts": record_count_by_key(records, "fleet_poll_overdue_target_count"),
        "fleet_has_offline_targets_counts": record_count_by_key(records, "fleet_has_offline_targets"),
        "fleet_has_stale_targets_counts": record_count_by_key(records, "fleet_has_stale_targets"),
        "fleet_has_mailbox_pending_work_counts": record_count_by_key(records, "fleet_has_mailbox_pending_work"),
        "fleet_has_poll_overdue_targets_counts": record_count_by_key(records, "fleet_has_poll_overdue_targets"),
        "available_counts": record_count_by_key(records, "available"),
        "requires_input_counts": record_count_by_key(records, "requires_input"),
        "requires_confirmation_counts": record_count_by_key(records, "requires_confirmation"),
        "queues_offline_work_counts": record_count_by_key(records, "queues_offline_work"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def _file_service_workflow_total_status_summary(summary):
    return {
        "file_service_workflow_action_count": summary.get("total_count", 0),
        "file_service_workflow_action_available_count": summary.get(
            "available_count", 0
        ),
        "file_service_workflow_action_requires_input_count": summary.get(
            "requires_input_count", 0
        ),
        "file_service_workflow_action_requires_confirmation_count": summary.get(
            "requires_confirmation_count", 0
        ),
        "file_service_workflow_action_queues_offline_work_count": summary.get(
            "queues_offline_work_count", 0
        ),
        "file_service_workflow_action_can_run_from_curses_enter_count": summary.get(
            "can_run_from_curses_enter_count", 0
        ),
    }


def _file_service_workflow_category_status_summary(summary):
    return {
        "file_service_workflow_action_action_counts": summary.get("action_counts") or {},
        "file_service_workflow_action_service_counts": summary.get("service_counts") or {},
        "file_service_workflow_action_category_counts": summary.get("category_counts") or {},
        "file_service_workflow_action_workflow_counts": summary.get("workflow_counts") or {},
        "file_service_workflow_action_actual_counts": summary.get("actual_counts") or {},
        "file_service_workflow_action_configured_counts": summary.get("configured_counts") or {},
        "file_service_workflow_action_target_filter_active_counts": summary.get(
            "target_filter_active_counts"
        ) or {},
        "file_service_workflow_action_route_kind_counts": summary.get(
            "route_kind_counts"
        ) or {},
        "file_service_workflow_action_bridge_profile_counts": summary.get(
            "bridge_profile_counts"
        ) or {},
        "file_service_workflow_action_requires_bridge_counts": summary.get(
            "requires_bridge_counts"
        ) or {},
    }


def _file_service_workflow_fleet_status_summary(summary):
    return {
        "file_service_workflow_action_fleet_target_count_counts": summary.get(
            "fleet_target_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_offline_target_count_counts": summary.get(
            "fleet_offline_target_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_stale_target_count_counts": summary.get(
            "fleet_stale_target_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_mailbox_pending_target_count_counts": summary.get(
            "fleet_mailbox_pending_target_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_mailbox_pending_work_count_counts": summary.get(
            "fleet_mailbox_pending_work_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_poll_overdue_target_count_counts": summary.get(
            "fleet_poll_overdue_target_count_counts"
        ) or {},
        "file_service_workflow_action_fleet_has_offline_targets_counts": summary.get(
            "fleet_has_offline_targets_counts"
        ) or {},
        "file_service_workflow_action_fleet_has_stale_targets_counts": summary.get(
            "fleet_has_stale_targets_counts"
        ) or {},
        "file_service_workflow_action_fleet_has_mailbox_pending_work_counts": summary.get(
            "fleet_has_mailbox_pending_work_counts"
        ) or {},
        "file_service_workflow_action_fleet_has_poll_overdue_targets_counts": summary.get(
            "fleet_has_poll_overdue_targets_counts"
        ) or {},
    }


def _file_service_workflow_operator_status_summary(summary):
    return {
        "file_service_workflow_action_available_counts": summary.get(
            "available_counts"
        ) or {},
        "file_service_workflow_action_requires_input_counts": summary.get(
            "requires_input_counts"
        ) or {},
        "file_service_workflow_action_requires_confirmation_counts": summary.get(
            "requires_confirmation_counts"
        ) or {},
        "file_service_workflow_action_queues_offline_work_counts": summary.get(
            "queues_offline_work_counts"
        ) or {},
        "file_service_workflow_action_operator_action_state_counts": summary.get(
            "operator_action_state_counts"
        ) or {},
        "file_service_workflow_action_operator_action_reason_counts": summary.get(
            "operator_action_reason_counts"
        ) or {},
        "file_service_workflow_action_can_run_from_curses_enter_counts": summary.get(
            "can_run_from_curses_enter_counts"
        ) or {},
        "file_service_workflow_action_curses_enter_action_counts": summary.get(
            "curses_enter_action_counts"
        ) or {},
    }


def file_service_workflow_status_summary(records):
    summary = file_service_workflow_action_summary(records)
    status = {}
    status.update(_file_service_workflow_total_status_summary(summary))
    status.update(_file_service_workflow_category_status_summary(summary))
    status.update(_file_service_workflow_fleet_status_summary(summary))
    status.update(_file_service_workflow_operator_status_summary(summary))
    return status
