"""Foundation status context assembly for grit-console."""

from pathlib import Path

from gritlib.config_utils import DEFAULT_OPERATOR_SESSION_DIR
from gritlib.event_log import EventLog
import gritlib.file_transfers as file_transfers
from gritlib.operator_network import local_ips
from gritlib.service_runtime import SERVICE_MANAGER
import gritlib.service_status as service_status
import gritlib.staged_files as staged_files
import gritlib.status_indexes as status_indexes
import gritlib.target_activity as target_activity
import gritlib.target_phone_home as target_phone_home
import gritlib.target_records as target_records

TARGET_INDEX_KEYS = (
    "targets_by_id",
    "targets_by_label",
    "targets_by_alias",
    "targets_by_remote_addr",
    "targets_by_service",
    "targets_by_identity_confidence",
    "targets_by_identity_source",
    "targets_by_latest_activity_service",
    "targets_by_latest_activity_operation",
    "targets_by_connectivity_state",
    "targets_by_last_seen_via",
    "targets_by_offline_age_bucket",
    "targets_by_has_next_expected_poll",
    "targets_by_poll_overdue",
    "targets_by_mailbox_pending_work",
    "targets_by_latest_phone_home_status",
    "targets_by_has_last_failed_phone_home",
    "targets_by_last_failed_phone_home_reason",
    "targets_by_last_failed_phone_home_status",
    "targets_by_latest_file_transfer_operation",
    "targets_by_latest_file_transfer_status",
    "targets_by_latest_file_transfer_route_kind",
    "targets_by_latest_file_transfer_bridge_profile",
    "targets_by_latest_survey_result_kind",
    "targets_by_latest_survey_result_status",
    "targets_by_latest_survey_result_route_kind",
    "targets_by_latest_survey_result_bridge_profile",
    "targets_by_latest_bridge_profile",
    "targets_by_latest_bridge_status",
    "targets_by_has_latest_bridge_activity",
    "targets_by_has_notes",
    "targets_by_capability_report_kind",
    "targets_by_compatibility_report_kind",
    "targets_by_compatibility_label",
    "targets_by_compatibility_baseline_label",
    "targets_by_compatibility_release",
    "targets_by_compatibility_payload_preset",
    "targets_by_observed_capability",
    "targets_by_missing_capability",
    "targets_by_observed_constraint",
)

SERVICE_INDEX_KEYS = (
    "services_by_actual",
    "services_by_configured",
    "services_by_bind_address",
    "services_by_port",
    "services_by_pid",
    "services_by_listener_pid",
    "services_by_tls",
    "services_by_stale",
    "services_by_pid_alive",
    "services_by_pid_managed",
    "services_by_listener_bind_mismatch",
    "services_by_session_log_exists",
    "services_by_process_log_exists",
    "services_by_has_error",
    "services_by_stopped_reason",
)

PORT_INDEX_KEYS = (
    "ports_by_number",
    "ports_by_service",
    "ports_by_actual",
)


def _build_operator_network_status_context(cfg):
    ips = local_ips()
    operator_network = status_indexes.operator_network_status(ips)
    operator_dir = Path(str(cfg.get("operator_session_dir", DEFAULT_OPERATOR_SESSION_DIR)))
    event_log_path = operator_dir / "events.jsonl"
    return {
        "ips": ips,
        "operator_network": operator_network,
        "selected_local_ip": operator_network["selected_local_ip"],
        "operator_network_records": operator_network["operator_network_records"],
        "operator_network_index_maps": operator_network["operator_network_index_maps"],
        "operator_network_state_record": operator_network[
            "operator_network_state_record"
        ],
        "operator_network_state_records": operator_network[
            "operator_network_state_records"
        ],
        "operator_network_state_index_maps": operator_network[
            "operator_network_state_index_maps"
        ],
        "operator_dir": operator_dir,
        "event_log_path": event_log_path,
        "session_root": str(cfg.get("session_root", "local/sessions")),
        "summary": operator_network["summary"],
    }


def _build_service_status_context(cfg):
    service_context = service_status.service_status_context(
        cfg, SERVICE_MANAGER.snapshot()
    )
    return {
        "service_context": service_context,
        "services": service_context["services"],
        "service_manager": service_context["manager"],
        "service_manager_status_doc": service_context["manager_status"],
        "service_manager_resources": service_context["manager_resources"],
        "service_manager_resource_index_maps": service_context[
            "manager_resource_index_maps"
        ],
        "service_manager_state_record": service_context["manager_state_record"],
        "service_manager_state_records": service_context["manager_state_records"],
        "service_manager_state_index_maps": service_context["manager_state_index_maps"],
        "ports": service_context["ports"],
        "port_index_maps": dict(zip(PORT_INDEX_KEYS, service_context["port_indexes"])),
        "summary": service_context["summary"],
        "warnings": service_context["warnings"],
        "service_index_maps": dict(zip(
            SERVICE_INDEX_KEYS,
            service_context["service_indexes"],
        )),
        "services_by_name": service_context["services_by_name"],
    }


def _build_staged_file_status_context(cfg, target_filter_id):
    staged_context = staged_files.staged_status_context(
        cfg, target_filter_id=target_filter_id
    )
    (
        staged_by_request,
        staged_by_kind,
        staged_by_sha256,
        staged_by_target_id,
        staged_by_source_path,
        staged_by_fetch_command,
        staged_by_fetch_command_force,
        staged_by_source_exists,
        staged_by_kind_source_exists,
    ) = staged_context["indexes"]
    return {
        "staged_context": staged_context,
        "staged_raw": staged_context["raw"],
        "unfiltered_staged_raw": staged_context["unfiltered_raw"],
        "staged": staged_context["staged"],
        "staged_records": staged_context["records"],
        "unfiltered_staged_count": staged_context["unfiltered_count"],
        "staged_by_request": staged_by_request,
        "staged_by_kind": staged_by_kind,
        "staged_by_sha256": staged_by_sha256,
        "staged_by_target_id": staged_by_target_id,
        "staged_by_source_path": staged_by_source_path,
        "staged_by_fetch_command": staged_by_fetch_command,
        "staged_by_fetch_command_force": staged_by_fetch_command_force,
        "staged_by_source_exists": staged_by_source_exists,
        "staged_by_kind_source_exists": staged_by_kind_source_exists,
    }


def _build_event_source_status_context(cfg):
    all_event_records, all_event_invalid = EventLog(cfg).records()
    all_target_phone_home_records = (
        target_phone_home.target_phone_home_records_from_events(all_event_records)
    )
    return {
        "all_event_records": all_event_records,
        "all_event_invalid": all_event_invalid,
        "all_target_phone_home_records": all_target_phone_home_records,
    }


def _build_target_registry_context(
    cfg,
    *,
    target_filter_id,
    all_target_phone_home_records,
    unfiltered_staged_count,
):
    uploads = file_transfers.recent_upload_metadata(cfg)
    fetches = file_transfers.recent_fetch_metadata(cfg)
    targets = target_records.target_records(cfg)
    targets = target_phone_home.apply_target_phone_home_summary(
        targets,
        all_target_phone_home_records,
    )
    unfiltered_counts = {
        "targets": len(targets),
        "uploads": len(uploads),
        "fetches": len(fetches),
        "staged": unfiltered_staged_count,
        "target_phone_home_records": len(all_target_phone_home_records),
    }
    if target_filter_id:
        uploads = target_records.records_for_target(uploads, target_filter_id)
        fetches = target_records.records_for_target(fetches, target_filter_id)
        targets = target_records.records_for_target(targets, target_filter_id)
    target_index_maps = dict(
        zip(TARGET_INDEX_KEYS, target_records.target_record_indexes(targets))
    )
    target_summary = target_records.target_record_summary(targets)
    selected_target = (
        dict(target_index_maps["targets_by_id"].get(target_filter_id) or {})
        if target_filter_id else {}
    )
    target_registry_state = target_records.target_registry_state_status(
        target_summary,
        selected_target,
        target_filter_id,
        unfiltered_counts.get("targets", 0),
    )
    return {
        "uploads": uploads,
        "fetches": fetches,
        "targets": targets,
        "unfiltered_counts": unfiltered_counts,
        "target_index_maps": target_index_maps,
        "target_summary": target_summary,
        "selected_target": selected_target,
        "target_registry_state_record": target_registry_state["state_record"],
        "target_registry_state_records": target_registry_state["state_records"],
        "target_registry_state_index_maps": target_registry_state["state_index_maps"],
        "target_registry_summary": target_registry_state["summary"],
    }


def _status_foundation_staged_fields(staged_context):
    return {
        "staged_context": staged_context,
        "staged_raw": staged_context["staged_raw"],
        "unfiltered_staged_raw": staged_context["unfiltered_staged_raw"],
        "staged": staged_context["staged"],
        "staged_records": staged_context["staged_records"],
        "unfiltered_staged_count": staged_context["unfiltered_staged_count"],
        "staged_by_request": staged_context["staged_by_request"],
        "staged_by_kind": staged_context["staged_by_kind"],
        "staged_by_sha256": staged_context["staged_by_sha256"],
        "staged_by_target_id": staged_context["staged_by_target_id"],
        "staged_by_source_path": staged_context["staged_by_source_path"],
        "staged_by_fetch_command": staged_context["staged_by_fetch_command"],
        "staged_by_fetch_command_force": staged_context[
            "staged_by_fetch_command_force"
        ],
        "staged_by_source_exists": staged_context["staged_by_source_exists"],
        "staged_by_kind_source_exists": staged_context[
            "staged_by_kind_source_exists"
        ],
    }


def _status_foundation_operator_network_fields(operator_network_context):
    return {
        "operator_network_context": operator_network_context,
        "ips": operator_network_context["ips"],
        "operator_network": operator_network_context["operator_network"],
        "selected_local_ip": operator_network_context["selected_local_ip"],
        "operator_network_records": operator_network_context[
            "operator_network_records"
        ],
        "operator_network_index_maps": operator_network_context[
            "operator_network_index_maps"
        ],
        "operator_network_state_record": operator_network_context[
            "operator_network_state_record"
        ],
        "operator_network_state_records": operator_network_context[
            "operator_network_state_records"
        ],
        "operator_network_state_index_maps": operator_network_context[
            "operator_network_state_index_maps"
        ],
        "operator_dir": operator_network_context["operator_dir"],
        "event_log_path": operator_network_context["event_log_path"],
        "session_root": operator_network_context["session_root"],
    }


def _status_foundation_service_fields(service_context):
    return {
        "service_context": service_context,
        "services": service_context["services"],
        "service_manager": service_context["service_manager"],
        "service_manager_status_doc": service_context[
            "service_manager_status_doc"
        ],
        "service_manager_resources": service_context["service_manager_resources"],
        "service_manager_resource_index_maps": service_context[
            "service_manager_resource_index_maps"
        ],
        "service_manager_state_record": service_context[
            "service_manager_state_record"
        ],
        "service_manager_state_records": service_context[
            "service_manager_state_records"
        ],
        "service_manager_state_index_maps": service_context[
            "service_manager_state_index_maps"
        ],
        "ports": service_context["ports"],
        "port_index_maps": service_context["port_index_maps"],
    }


def _status_foundation_event_source_fields(event_source_context):
    return {
        "event_source_context": event_source_context,
        "all_event_records": event_source_context["all_event_records"],
        "all_target_phone_home_records": event_source_context[
            "all_target_phone_home_records"
        ],
    }


def _status_foundation_target_fields(target_context):
    target_index_maps = target_context["target_index_maps"]
    return {
        "target_context": target_context,
        "uploads": target_context["uploads"],
        "fetches": target_context["fetches"],
        "targets": target_context["targets"],
        "unfiltered_counts": target_context["unfiltered_counts"],
        "target_index_maps": target_index_maps,
        "targets_by_id": target_index_maps["targets_by_id"],
        "target_summary": target_context["target_summary"],
        "selected_target": target_context["selected_target"],
        "target_registry_state_record": target_context[
            "target_registry_state_record"
        ],
        "target_registry_state_records": target_context[
            "target_registry_state_records"
        ],
        "target_registry_state_index_maps": target_context[
            "target_registry_state_index_maps"
        ],
        "target_registry_summary": target_context["target_registry_summary"],
    }


def build_status_foundation_context(cfg, *, target_filter_id):
    staged_context = _build_staged_file_status_context(cfg, target_filter_id)
    operator_network_context = _build_operator_network_status_context(cfg)
    service_context = _build_service_status_context(cfg)
    event_source_context = _build_event_source_status_context(cfg)
    target_context = _build_target_registry_context(
        cfg,
        target_filter_id=target_filter_id,
        all_target_phone_home_records=event_source_context[
            "all_target_phone_home_records"
        ],
        unfiltered_staged_count=staged_context["unfiltered_staged_count"],
    )
    return {
        **_status_foundation_staged_fields(staged_context),
        **_status_foundation_operator_network_fields(operator_network_context),
        **_status_foundation_service_fields(service_context),
        **_status_foundation_event_source_fields(event_source_context),
        **_status_foundation_target_fields(target_context),
    }
