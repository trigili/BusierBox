"""API collection schema builders for grit-console status documents."""

import gritlib.status_indexes as status_indexes


def _build_service_bridge_api_collections(
    *,
    services,
    service_workflow_actions,
    probe_workflow_actions,
    service_manager_resources,
    service_manager_state_records,
    bridge_profiles,
    bridge_profile_workflow_actions,
    bridge_hop_records,
):
    return {
        **_build_service_record_api_collections(
            services=services,
        ),
        **_build_service_workflow_api_collections(
            service_workflow_actions=service_workflow_actions,
            probe_workflow_actions=probe_workflow_actions,
        ),
        **_build_service_runtime_api_collections(
            service_manager_resources=service_manager_resources,
            service_manager_state_records=service_manager_state_records,
        ),
        **_build_bridge_api_collections(
            bridge_profiles=bridge_profiles,
            bridge_profile_workflow_actions=bridge_profile_workflow_actions,
            bridge_hop_records=bridge_hop_records,
        ),
    }

def _build_service_record_api_collections(*, services):
    return {
        "services": status_indexes.api_collection_record(
            "services", services, "name", (
                "services_by_name", "services_by_actual", "services_by_configured",
                "services_by_bind_address", "services_by_port", "services_by_pid",
                "services_by_listener_pid", "services_by_tls", "services_by_stale",
                "services_by_pid_alive", "services_by_pid_managed",
                "services_by_listener_bind_mismatch", "services_by_has_error",
                "services_by_session_log_exists", "services_by_process_log_exists",
                "services_by_stopped_reason", "services_by_has_warnings",
                "services_by_warning_type",
            ), "service_count",
        ),
    }

def _build_service_workflow_api_collections(*, service_workflow_actions, probe_workflow_actions):
    return {
        "service_workflow_actions": status_indexes.api_collection_record(
            "service_workflow_actions", service_workflow_actions, "id", (
                "service_workflow_actions_by_id",
                "service_workflow_actions_by_action_id",
                "service_workflow_actions_by_service",
                "service_workflow_actions_by_category",
                "service_workflow_actions_by_workflow",
                "service_workflow_actions_by_actual",
                "service_workflow_actions_by_configured",
                "service_workflow_actions_by_fleet_target_count",
                "service_workflow_actions_by_fleet_offline_target_count",
                "service_workflow_actions_by_fleet_stale_target_count",
                "service_workflow_actions_by_fleet_mailbox_pending_target_count",
                "service_workflow_actions_by_fleet_mailbox_pending_work_count",
                "service_workflow_actions_by_fleet_poll_overdue_target_count",
                "service_workflow_actions_by_fleet_has_offline_targets",
                "service_workflow_actions_by_fleet_has_stale_targets",
                "service_workflow_actions_by_fleet_has_mailbox_pending_work",
                "service_workflow_actions_by_fleet_has_poll_overdue_targets",
                "service_workflow_actions_by_available",
                "service_workflow_actions_by_requires_input",
                "service_workflow_actions_by_requires_confirmation",
                "service_workflow_actions_by_operator_action_state",
                "service_workflow_actions_by_operator_action_reason",
                "service_workflow_actions_by_can_run_from_curses_enter",
                "service_workflow_actions_by_curses_enter_action",
                "service_workflow_actions_by_has_error",
                "service_workflow_actions_by_has_warnings",
            ), "service_workflow_action_count",
        ),
        "probe_workflow_actions": status_indexes.api_collection_record(
            "probe_workflow_actions", probe_workflow_actions, "id", (
                "probe_workflow_actions_by_id",
                "probe_workflow_actions_by_action_id",
                "probe_workflow_actions_by_category",
                "probe_workflow_actions_by_workflow",
                "probe_workflow_actions_by_actual",
                "probe_workflow_actions_by_route_kind",
                "probe_workflow_actions_by_bridge_profile",
                "probe_workflow_actions_by_requires_bridge",
                "probe_workflow_actions_by_fleet_target_count",
                "probe_workflow_actions_by_fleet_offline_target_count",
                "probe_workflow_actions_by_fleet_stale_target_count",
                "probe_workflow_actions_by_fleet_mailbox_pending_target_count",
                "probe_workflow_actions_by_fleet_mailbox_pending_work_count",
                "probe_workflow_actions_by_fleet_poll_overdue_target_count",
                "probe_workflow_actions_by_fleet_has_offline_targets",
                "probe_workflow_actions_by_fleet_has_stale_targets",
                "probe_workflow_actions_by_fleet_has_mailbox_pending_work",
                "probe_workflow_actions_by_fleet_has_poll_overdue_targets",
                "probe_workflow_actions_by_available",
                "probe_workflow_actions_by_requires_confirmation",
                "probe_workflow_actions_by_target_phone_home_required",
                "probe_workflow_actions_by_operator_action_state",
                "probe_workflow_actions_by_operator_action_reason",
                "probe_workflow_actions_by_can_run_from_curses_enter",
                "probe_workflow_actions_by_curses_enter_action",
            ), "probe_workflow_action_count",
        ),
    }

def _build_service_runtime_api_collections(*, service_manager_resources, service_manager_state_records):
    return {
        "service_manager_resources": status_indexes.api_collection_record(
            "service_manager_resources", service_manager_resources, "id", (
                "service_manager_resources_by_id", "service_manager_resources_by_kind",
                "service_manager_resources_by_state", "service_manager_resources_by_active",
                "service_manager_resources_by_pid", "service_manager_resources_by_kind_state",
                "service_manager_resources_by_kind_active",
            ), "service_manager_resource_count",
        ),
        "service_manager_state_records": status_indexes.api_collection_record(
            "service_manager_state_records", service_manager_state_records, "id", (
                "service_manager_state_records_by_id",
                "service_manager_state_records_by_shutdown_requested",
                "service_manager_state_records_by_has_open_sockets",
                "service_manager_state_records_by_has_active_transports",
                "service_manager_state_records_by_has_alive_threads",
                "service_manager_state_records_by_has_running_children",
                "service_manager_state_records_by_has_resources",
            ), "service_manager_state_record_count",
        ),
    }

def _build_bridge_api_collections(
    *,
    bridge_profiles,
    bridge_profile_workflow_actions,
    bridge_hop_records,
):
    return {
        "bridge_profiles": status_indexes.api_collection_record(
            "bridge_profiles", bridge_profiles, "name", (
                "bridge_profiles_by_name", "bridge_profiles_by_target_id",
                "bridge_profiles_by_dest_host", "bridge_profiles_by_listen_port",
                "bridge_profiles_by_current_state", "bridge_profiles_by_active",
                "bridge_profiles_by_requires_target_online", "bridge_profiles_by_multi_hop",
                "bridge_profiles_by_hop_count", "bridge_profiles_by_route_path",
                "bridge_profiles_by_has_last_successful_relay",
                "bridge_profiles_by_has_last_failure",
            ), "bridge_profile_count",
        ),
        "bridge_profile_workflow_actions": status_indexes.api_collection_record(
            "bridge_profile_workflow_actions", bridge_profile_workflow_actions, "id", (
                "bridge_profile_workflow_actions_by_id",
                "bridge_profile_workflow_actions_by_action_id",
                "bridge_profile_workflow_actions_by_bridge_profile",
                "bridge_profile_workflow_actions_by_target_id",
                "bridge_profile_workflow_actions_by_category",
                "bridge_profile_workflow_actions_by_workflow",
                "bridge_profile_workflow_actions_by_current_state",
                "bridge_profile_workflow_actions_by_active",
                "bridge_profile_workflow_actions_by_requires_target_online",
                "bridge_profile_workflow_actions_by_multi_hop",
                "bridge_profile_workflow_actions_by_hop_count",
                "bridge_profile_workflow_actions_by_fleet_target_count",
                "bridge_profile_workflow_actions_by_fleet_offline_target_count",
                "bridge_profile_workflow_actions_by_fleet_stale_target_count",
                "bridge_profile_workflow_actions_by_fleet_mailbox_pending_target_count",
                "bridge_profile_workflow_actions_by_fleet_mailbox_pending_work_count",
                "bridge_profile_workflow_actions_by_fleet_poll_overdue_target_count",
                "bridge_profile_workflow_actions_by_fleet_has_offline_targets",
                "bridge_profile_workflow_actions_by_fleet_has_stale_targets",
                "bridge_profile_workflow_actions_by_fleet_has_mailbox_pending_work",
                "bridge_profile_workflow_actions_by_fleet_has_poll_overdue_targets",
                "bridge_profile_workflow_actions_by_has_last_successful_relay",
                "bridge_profile_workflow_actions_by_has_last_failure",
                "bridge_profile_workflow_actions_by_requires_confirmation",
                "bridge_profile_workflow_actions_by_operator_action_state",
                "bridge_profile_workflow_actions_by_operator_action_reason",
                "bridge_profile_workflow_actions_by_can_run_from_curses_enter",
                "bridge_profile_workflow_actions_by_curses_enter_action",
            ), "bridge_profile_workflow_action_count",
        ),
        "bridge_hop_records": status_indexes.api_collection_record(
            "bridge_hop_records", bridge_hop_records, "id", (
                "bridge_hops_by_id", "bridge_hops_by_profile",
                "bridge_hops_by_profile_name", "bridge_hops_by_ordinal",
                "bridge_hops_by_from", "bridge_hops_by_to",
                "bridge_hops_by_from_host", "bridge_hops_by_from_port",
                "bridge_hops_by_to_host", "bridge_hops_by_to_port",
                "bridge_hops_by_route_path", "bridge_hops_by_target_id",
                "bridge_hops_by_multi_hop", "bridge_hops_by_is_first_hop",
                "bridge_hops_by_is_last_hop", "bridge_hops_by_current_state",
                "bridge_hops_by_profile_active",
                "bridge_hops_by_profile_has_last_successful_relay",
                "bridge_hops_by_profile_has_last_failure",
            ), "bridge_hop_record_count",
        ),
    }

def _build_operator_health_api_collections(
    *,
    ports,
    path_status_records,
    server_state_records,
    operator_state_records_list,
    operator_network_records,
    operator_network_state_records,
    browser_paths,
    warnings,
):
    return {
        **_build_operator_path_port_api_collections(
            ports=ports,
            path_status_records=path_status_records,
        ),
        **_build_operator_state_api_collections(
            server_state_records=server_state_records,
            operator_state_records_list=operator_state_records_list,
        ),
        **_build_operator_network_path_api_collections(
            operator_network_records=operator_network_records,
            operator_network_state_records=operator_network_state_records,
            browser_paths=browser_paths,
        ),
        **_build_warning_api_collections(
            warnings=warnings,
        ),
    }

def _build_operator_path_port_api_collections(*, ports, path_status_records):
    return {
        "ports": status_indexes.api_collection_record(
            "ports", ports, "service", (
                "ports_by_number", "ports_by_service", "ports_by_actual",
                "ports_by_has_warnings", "ports_by_warning_type",
            ), "port_count",
        ),
        "path_status_records": status_indexes.api_collection_record(
            "path_status_records", path_status_records, "name", (
                "path_status_by_name", "path_status_by_path",
                "path_status_by_expected_kind", "path_status_by_exists",
                "path_status_by_parent_exists", "path_status_by_writable",
                "path_status_by_expected_kind_mismatch",
                "path_status_by_has_warnings", "path_status_by_warning_type",
            ), "path_status_count",
        ),
    }

def _build_operator_state_api_collections(*, server_state_records, operator_state_records_list):
    return {
        "server_state_records": status_indexes.api_collection_record(
            "server_state_records", server_state_records, "path", (
                "server_state_records_by_path",
                "server_state_records_by_exists",
                "server_state_records_by_valid",
                "server_state_records_by_has_services",
                "server_state_records_by_has_sessions",
                "server_state_records_by_schema",
            ), "server_state_record_count",
        ),
        "operator_state_records": status_indexes.api_collection_record(
            "operator_state_records", operator_state_records_list, "name", (
                "operator_state_records_by_name", "operator_state_records_by_kind",
                "operator_state_records_by_status", "operator_state_records_by_exists",
                "operator_state_records_by_valid", "operator_state_records_by_unhealthy",
                "operator_state_records_by_severity",
                "operator_state_records_by_remediation_class",
                "operator_state_records_by_requires_operator_action",
                "operator_state_records_by_path",
                "operator_state_records_by_kind_status",
            ), "operator_state_count",
        ),
    }

def _build_operator_network_path_api_collections(
    *,
    operator_network_records,
    operator_network_state_records,
    browser_paths,
):
    return {
        "operator_network_records": status_indexes.api_collection_record(
            "operator_network_records", operator_network_records, "id", (
                "operator_network_records_by_id",
                "operator_network_records_by_kind",
                "operator_network_records_by_ip",
                "operator_network_records_by_selected",
                "operator_network_records_by_placeholder",
                "operator_network_records_by_source",
                "operator_network_records_by_usable_for_generated_commands",
            ), "operator_network_record_count",
        ),
        "operator_network_state_records": status_indexes.api_collection_record(
            "operator_network_state_records", operator_network_state_records, "id", (
                "operator_network_state_records_by_id",
                "operator_network_state_records_by_selected_ip",
                "operator_network_state_records_by_selected_source",
                "operator_network_state_records_by_selected_placeholder",
                "operator_network_state_records_by_has_detected_ip",
                "operator_network_state_records_by_uses_placeholder",
                "operator_network_state_records_by_has_generated_command_ip",
                "operator_network_state_records_by_has_multiple_ips",
            ), "operator_network_state_record_count",
        ),
        "browser_paths": status_indexes.api_collection_record(
            "browser_paths", browser_paths, "id", (
                "browser_paths_by_kind", "browser_paths_by_path",
                "browser_paths_by_source_id", "browser_paths_by_stage_kind",
                "browser_paths_by_release_path", "browser_paths_by_kind_source_id",
                "browser_paths_by_exists", "browser_paths_by_readable",
                "browser_paths_by_writable", "browser_paths_by_expected_kind_mismatch",
                "browser_paths_by_has_warnings", "browser_paths_by_warning_type",
            ), "browser_path_count",
        ),
    }

def _build_warning_api_collections(*, warnings):
    return {
        "warnings": status_indexes.api_collection_record(
            "warnings", warnings, "type", (
                "warnings_by_type", "warnings_by_severity",
                "warnings_by_remediation_class", "warnings_by_type_severity",
                "warnings_by_service", "warnings_by_port",
                "warnings_by_pid", "warnings_by_listener_pid", "warnings_by_owner_pid",
                "warnings_by_path", "warnings_by_type_path",
                "warnings_by_service_port", "warnings_by_type_service_port",
            ), "warning_count",
        ),
    }

def _build_target_api_collections(
    *,
    target_command_records,
    target_workflow_actions,
    target_command_state_records,
    rshell_session_policy_records,
    targets,
    target_registry_state_records,
    target_filter_records,
    target_attribution_records,
):
    return {
        **_build_target_command_api_collections(
            target_command_records=target_command_records,
            target_workflow_actions=target_workflow_actions,
            target_command_state_records=target_command_state_records,
            rshell_session_policy_records=rshell_session_policy_records,
        ),
        **_build_target_identity_api_collections(
            targets=targets,
        ),
        **_build_target_registry_api_collections(
            target_registry_state_records=target_registry_state_records,
        ),
        **_build_target_filter_api_collections(
            target_filter_records=target_filter_records,
        ),
        **_build_target_attribution_api_collections(
            target_attribution_records=target_attribution_records,
        ),
    }

def _build_target_command_record_api_collections(*, target_command_records):
    return {
        "target_command_records": status_indexes.api_collection_record(
            "target_command_records", target_command_records, "command", (
                "target_commands_by_service", "target_commands_by_request",
                "target_commands_by_target_id",
                "target_commands_by_stage_kind", "target_commands_by_release_path",
                "target_commands_by_side", "target_commands_by_purpose",
                "target_commands_by_service_purpose", "target_commands_by_side_purpose",
                "target_commands_by_network", "target_commands_by_route_kind",
                "target_commands_by_bridge_profile", "target_commands_by_requires_bridge",
                "target_commands_by_requires_explicit_target_action",
                "target_commands_by_executes_operator_supplied_commands",
                "target_commands_by_ordinal", "target_commands_by_command_sha256",
                "target_commands_by_copy_supported",
                "target_commands_by_session_policy", "target_commands_by_session_policy_valid",
                "target_commands_by_retry_backoff", "target_commands_by_retry_interval_sec",
                "target_commands_by_retry_post_disconnect_count",
            ), "target_command_count",
        ),
    }

def _build_target_workflow_api_collections(*, target_workflow_actions):
    return {
        "target_workflow_actions": status_indexes.api_collection_record(
            "target_workflow_actions", target_workflow_actions, "id", (
                "target_workflow_actions_by_id",
                "target_workflow_actions_by_action_id",
                "target_workflow_actions_by_target_id",
                "target_workflow_actions_by_category",
                "target_workflow_actions_by_workflow",
                "target_workflow_actions_by_available",
                "target_workflow_actions_by_requires_input",
                "target_workflow_actions_by_offline_supported",
                "target_workflow_actions_by_requires_target_online",
                "target_workflow_actions_by_queues_offline_work",
                "target_workflow_actions_by_target_phone_home_required",
                "target_workflow_actions_by_bridge_profile",
                "target_workflow_actions_by_target_connectivity_state",
                "target_workflow_actions_by_target_offline_age_bucket",
                "target_workflow_actions_by_target_poll_overdue",
                "target_workflow_actions_by_target_mailbox_pending_work_count",
                "target_workflow_actions_by_target_latest_phone_home_status",
                "target_workflow_actions_by_target_latest_successful_phone_home_status",
                "target_workflow_actions_by_target_last_failed_phone_home_status",
                "target_workflow_actions_by_operator_action_state",
                "target_workflow_actions_by_operator_action_reason",
                "target_workflow_actions_by_can_run_from_curses_enter",
            ), "target_workflow_action_count",
        ),
    }

def _build_target_command_state_api_collections(*, target_command_state_records):
    return {
        "target_command_state_records": status_indexes.api_collection_record(
            "target_command_state_records", target_command_state_records, "id", (
                "target_command_state_records_by_id",
                "target_command_state_records_by_has_commands",
                "target_command_state_records_by_has_network_commands",
                "target_command_state_records_by_has_copy_supported_commands",
                "target_command_state_records_by_has_operator_supplied_command_execution",
                "target_command_state_records_by_all_require_explicit_target_action",
                "target_command_state_records_by_safe_explicit_target_action_boundary",
                "target_command_state_records_by_has_session_policy_errors",
            ), "target_command_state_record_count",
        ),
    }

def _build_rshell_session_policy_api_collections(*, rshell_session_policy_records):
    return {
        "rshell_session_policy_records": status_indexes.api_collection_record(
            "rshell_session_policy_records", rshell_session_policy_records, "id", (
                "rshell_session_policy_records_by_id",
                "rshell_session_policy_records_by_session_policy",
                "rshell_session_policy_records_by_session_policy_valid",
                "rshell_session_policy_records_by_retry_scope",
                "rshell_session_policy_records_by_retry_backoff",
                "rshell_session_policy_records_by_reconnects_after_disconnect",
                "rshell_session_policy_records_by_persistent_lifecycle",
            ), "rshell_session_policy_record_count",
        ),
    }

def _build_target_command_api_collections(
    *,
    target_command_records,
    target_workflow_actions,
    target_command_state_records,
    rshell_session_policy_records,
):
    return {
        **_build_target_command_record_api_collections(
            target_command_records=target_command_records,
        ),
        **_build_target_workflow_api_collections(
            target_workflow_actions=target_workflow_actions,
        ),
        **_build_target_command_state_api_collections(
            target_command_state_records=target_command_state_records,
        ),
        **_build_rshell_session_policy_api_collections(
            rshell_session_policy_records=rshell_session_policy_records,
        ),
    }

def _build_target_identity_api_collections(*, targets):
    return {
        "targets": status_indexes.api_collection_record(
            "targets", targets, "target_id", (
                "targets_by_id", "targets_by_label", "targets_by_alias",
                "targets_by_remote_addr", "targets_by_service",
                "targets_by_identity_confidence", "targets_by_identity_source",
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
            ), "target_count",
        ),
    }

def _build_target_registry_api_collections(*, target_registry_state_records):
    return {
        "target_registry_state_records": status_indexes.api_collection_record(
            "target_registry_state_records", target_registry_state_records, "id", (
                "target_registry_state_records_by_id",
                "target_registry_state_records_by_has_targets",
                "target_registry_state_records_by_has_unfiltered_targets",
                "target_registry_state_records_by_filter_active",
                "target_registry_state_records_by_filter_target_id",
                "target_registry_state_records_by_selected_target_found",
                "target_registry_state_records_by_selected_target_identity_confidence",
                "target_registry_state_records_by_selected_target_connectivity_state",
                "target_registry_state_records_by_selected_target_offline_age_bucket",
                "target_registry_state_records_by_selected_target_latest_phone_home_status",
                "target_registry_state_records_by_selected_target_latest_successful_phone_home_status",
                "target_registry_state_records_by_selected_target_last_failed_phone_home_status",
                "target_registry_state_records_by_selected_target_poll_overdue",
                "target_registry_state_records_by_selected_target_mailbox_pending_work_count",
                "target_registry_state_records_by_selected_target_latest_file_transfer_status",
                "target_registry_state_records_by_selected_target_latest_file_transfer_route_kind",
                "target_registry_state_records_by_selected_target_latest_survey_result_status",
                "target_registry_state_records_by_selected_target_latest_survey_result_route_kind",
                "target_registry_state_records_by_selected_target_latest_bridge_profile",
                "target_registry_state_records_by_selected_target_latest_bridge_status",
                "target_registry_state_records_by_selected_target_latest_capability_report_kind",
                "target_registry_state_records_by_selected_target_latest_compatibility_label",
                "target_registry_state_records_by_selected_target_latest_compatibility_release_name",
                "target_registry_state_records_by_has_latest_activity",
                "target_registry_state_records_by_has_next_expected_polls",
                "target_registry_state_records_by_has_poll_overdue",
                "target_registry_state_records_by_has_mailbox_pending_work",
                "target_registry_state_records_by_has_failed_phone_home",
                "target_registry_state_records_by_has_latest_file_transfer",
                "target_registry_state_records_by_has_latest_survey_result",
                "target_registry_state_records_by_has_latest_bridge_activity",
                "target_registry_state_records_by_has_identity_sources",
                "target_registry_state_records_by_has_capability_reports",
                "target_registry_state_records_by_has_compatibility_reports",
            ), "target_registry_state_record_count",
        ),
    }

def _build_target_filter_api_collections(*, target_filter_records):
    return {
        "target_filter_records": status_indexes.api_collection_record(
            "target_filter_records", target_filter_records, "id", (
                "target_filter_records_by_id",
                "target_filter_records_by_active",
                "target_filter_records_by_target_id",
                "target_filter_records_by_selected_target_found",
                "target_filter_records_by_selected_target_label",
                "target_filter_records_by_selected_target_identity_confidence",
                "target_filter_records_by_selected_target_connectivity_state",
                "target_filter_records_by_selected_target_offline_age_bucket",
                "target_filter_records_by_selected_target_latest_phone_home_status",
                "target_filter_records_by_selected_target_latest_successful_phone_home_status",
                "target_filter_records_by_selected_target_last_failed_phone_home_status",
                "target_filter_records_by_selected_target_poll_overdue",
                "target_filter_records_by_selected_target_mailbox_pending_work_count",
                "target_filter_records_by_selected_target_notes_present",
                "target_filter_records_by_selected_target_latest_activity_service",
                "target_filter_records_by_selected_target_latest_activity_operation",
                "target_filter_records_by_selected_target_latest_file_transfer_status",
                "target_filter_records_by_selected_target_latest_file_transfer_route_kind",
                "target_filter_records_by_selected_target_latest_survey_result_status",
                "target_filter_records_by_selected_target_latest_survey_result_route_kind",
                "target_filter_records_by_selected_target_latest_bridge_profile",
                "target_filter_records_by_selected_target_latest_bridge_status",
                "target_filter_records_by_selected_target_latest_capability_report_kind",
                "target_filter_records_by_selected_target_latest_compatibility_report_kind",
                "target_filter_records_by_selected_target_latest_compatibility_label",
                "target_filter_records_by_selected_target_latest_compatibility_release_name",
                "target_filter_records_by_selected_target_latest_compatibility_payload_preset",
                "target_filter_records_by_has_unfiltered_activity",
                "target_filter_records_by_has_filtered_activity",
                "target_filter_records_by_filter_reduced_activity",
                "target_filter_records_by_has_unfiltered_observed_activity",
                "target_filter_records_by_has_filtered_observed_activity",
                "target_filter_records_by_filter_reduced_observed_activity",
            ), "target_filter_record_count",
        ),
    }

def _build_target_attribution_api_collections(*, target_attribution_records):
    return {
        "target_attribution_records": status_indexes.api_collection_record(
            "target_attribution_records", target_attribution_records, "scope", (
                "target_attribution_records_by_scope",
                "target_attribution_records_by_has_targeted_activity",
                "target_attribution_records_by_has_legacy_activity",
                "target_attribution_records_by_legacy_single_target_activity_present",
                "target_attribution_records_by_all_activity_has_target_id",
                "target_attribution_records_by_no_activity",
            ), "target_attribution_record_count",
        ),
    }

def _build_staged_file_activity_api_collections(
    *,
    staged_records,
    staged_file_workflow_actions,
    file_service_workflow_actions,
    target_file_transfer_records,
    target_activity_records,
    staged_files_state_records,
):
    return {
        **_build_staged_record_api_collections(
            staged_records=staged_records,
        ),
        **_build_file_workflow_api_collections(
            staged_file_workflow_actions=staged_file_workflow_actions,
            file_service_workflow_actions=file_service_workflow_actions,
        ),
        **_build_target_file_activity_api_collections(
            target_file_transfer_records=target_file_transfer_records,
            target_activity_records=target_activity_records,
        ),
        **_build_staged_state_api_collections(
            staged_files_state_records=staged_files_state_records,
        ),
    }

def _build_staged_record_api_collections(*, staged_records):
    return {
        "staged_records": status_indexes.api_collection_record(
            "staged_records", staged_records, "request_name", (
                "staged_by_request", "staged_by_kind", "staged_by_sha256",
                "staged_by_target_id", "staged_by_source_path",
                "staged_by_fetch_command", "staged_by_fetch_command_force",
                "staged_by_source_exists", "staged_by_kind_source_exists",
            ), "staged_count",
        ),
    }

def _build_staged_file_workflow_api_collections(*, staged_file_workflow_actions):
    return {
        "staged_file_workflow_actions": status_indexes.api_collection_record(
            "staged_file_workflow_actions", staged_file_workflow_actions, "id", (
                "staged_file_workflow_actions_by_id",
                "staged_file_workflow_actions_by_action_id",
                "staged_file_workflow_actions_by_request_name",
                "staged_file_workflow_actions_by_stage_kind",
                "staged_file_workflow_actions_by_category",
                "staged_file_workflow_actions_by_workflow",
                "staged_file_workflow_actions_by_target_id",
                "staged_file_workflow_actions_by_target_connectivity_state",
                "staged_file_workflow_actions_by_target_offline_age_bucket",
                "staged_file_workflow_actions_by_target_poll_overdue",
                "staged_file_workflow_actions_by_target_mailbox_pending_work_count",
                "staged_file_workflow_actions_by_target_latest_phone_home_status",
                "staged_file_workflow_actions_by_target_latest_successful_phone_home_status",
                "staged_file_workflow_actions_by_target_last_failed_phone_home_status",
                "staged_file_workflow_actions_by_route_kind",
                "staged_file_workflow_actions_by_bridge_profile",
                "staged_file_workflow_actions_by_fleet_target_count",
                "staged_file_workflow_actions_by_fleet_offline_target_count",
                "staged_file_workflow_actions_by_fleet_stale_target_count",
                "staged_file_workflow_actions_by_fleet_mailbox_pending_target_count",
                "staged_file_workflow_actions_by_fleet_mailbox_pending_work_count",
                "staged_file_workflow_actions_by_fleet_poll_overdue_target_count",
                "staged_file_workflow_actions_by_fleet_has_offline_targets",
                "staged_file_workflow_actions_by_fleet_has_stale_targets",
                "staged_file_workflow_actions_by_fleet_has_mailbox_pending_work",
                "staged_file_workflow_actions_by_fleet_has_poll_overdue_targets",
                "staged_file_workflow_actions_by_source_exists",
                "staged_file_workflow_actions_by_available",
                "staged_file_workflow_actions_by_requires_target",
                "staged_file_workflow_actions_by_queues_offline_work",
                "staged_file_workflow_actions_by_requires_confirmation",
                "staged_file_workflow_actions_by_operator_action_state",
                "staged_file_workflow_actions_by_operator_action_reason",
                "staged_file_workflow_actions_by_can_run_from_curses_enter",
                "staged_file_workflow_actions_by_curses_enter_action",
            ), "staged_file_workflow_action_count",
        ),
    }

def _build_file_service_workflow_api_collections(*, file_service_workflow_actions):
    return {
        "file_service_workflow_actions": status_indexes.api_collection_record(
            "file_service_workflow_actions", file_service_workflow_actions, "id", (
                "file_service_workflow_actions_by_id",
                "file_service_workflow_actions_by_action_id",
                "file_service_workflow_actions_by_service",
                "file_service_workflow_actions_by_category",
                "file_service_workflow_actions_by_workflow",
                "file_service_workflow_actions_by_actual",
                "file_service_workflow_actions_by_configured",
                "file_service_workflow_actions_by_target_filter_active",
                "file_service_workflow_actions_by_route_kind",
                "file_service_workflow_actions_by_bridge_profile",
                "file_service_workflow_actions_by_requires_bridge",
                "file_service_workflow_actions_by_fleet_target_count",
                "file_service_workflow_actions_by_fleet_offline_target_count",
                "file_service_workflow_actions_by_fleet_stale_target_count",
                "file_service_workflow_actions_by_fleet_mailbox_pending_target_count",
                "file_service_workflow_actions_by_fleet_mailbox_pending_work_count",
                "file_service_workflow_actions_by_fleet_poll_overdue_target_count",
                "file_service_workflow_actions_by_fleet_has_offline_targets",
                "file_service_workflow_actions_by_fleet_has_stale_targets",
                "file_service_workflow_actions_by_fleet_has_mailbox_pending_work",
                "file_service_workflow_actions_by_fleet_has_poll_overdue_targets",
                "file_service_workflow_actions_by_available",
                "file_service_workflow_actions_by_requires_input",
                "file_service_workflow_actions_by_requires_confirmation",
                "file_service_workflow_actions_by_queues_offline_work",
                "file_service_workflow_actions_by_operator_action_state",
                "file_service_workflow_actions_by_operator_action_reason",
                "file_service_workflow_actions_by_can_run_from_curses_enter",
                "file_service_workflow_actions_by_curses_enter_action",
            ), "file_service_workflow_action_count",
        ),
    }

def _build_file_workflow_api_collections(*, staged_file_workflow_actions, file_service_workflow_actions):
    return {
        **_build_staged_file_workflow_api_collections(
            staged_file_workflow_actions=staged_file_workflow_actions,
        ),
        **_build_file_service_workflow_api_collections(
            file_service_workflow_actions=file_service_workflow_actions,
        ),
    }

def _build_target_file_activity_api_collections(*, target_file_transfer_records, target_activity_records):
    return {
        "target_file_transfer_records": status_indexes.api_collection_record(
            "target_file_transfer_records", target_file_transfer_records, "id", (
                "target_file_transfer_records_by_id",
                "target_file_transfer_records_by_target_id",
                "target_file_transfer_records_by_target_label",
                "target_file_transfer_records_by_operation",
                "target_file_transfer_records_by_source_collection",
                "target_file_transfer_records_by_status",
                "target_file_transfer_records_by_route_kind",
                "target_file_transfer_records_by_bridge_profile",
                "target_file_transfer_records_by_request_name",
                "target_file_transfer_records_by_filename",
                "target_file_transfer_records_by_sha256",
                "target_file_transfer_records_by_session_id",
            ), "target_file_transfer_record_count",
        ),
        "target_activity_records": status_indexes.api_collection_record(
            "target_activity_records", target_activity_records, "id", (
                "target_activity_records_by_id",
                "target_activity_records_by_target_id",
                "target_activity_records_by_target_label",
                "target_activity_records_by_category",
                "target_activity_records_by_source_collection",
                "target_activity_records_by_operation",
                "target_activity_records_by_status",
                "target_activity_records_by_route_kind",
                "target_activity_records_by_bridge_profile",
                "target_activity_records_by_session_id",
                "target_activity_records_by_command_id",
                "target_activity_records_by_request_name",
                "target_activity_records_by_filename",
                "target_activity_records_by_pending_work",
                "target_activity_records_by_waiting_for",
                "target_activity_records_by_target_connectivity_state",
                "target_activity_records_by_target_offline_age_bucket",
                "target_activity_records_by_target_poll_overdue",
                "target_activity_records_by_target_mailbox_pending_work_count",
            ), "target_activity_record_count",
        ),
    }

def _build_staged_state_api_collections(*, staged_files_state_records):
    return {
        "staged_files_state_records": status_indexes.api_collection_record(
            "staged_files_state_records", staged_files_state_records, "path", (
                "staged_files_state_records_by_path",
                "staged_files_state_records_by_exists",
                "staged_files_state_records_by_valid",
                "staged_files_state_records_by_has_staged",
                "staged_files_state_records_by_schema",
            ), "staged_files_state_record_count",
        ),
    }

def _build_command_mailbox_api_collections(
    *,
    command_copy_records,
    command_copy_state_records,
    command_queue_state_records,
    target_mailbox_records,
    target_phone_home_records,
):
    return {
        **_build_command_copy_api_collections(
            command_copy_records=command_copy_records,
            command_copy_state_records=command_copy_state_records,
        ),
        **_build_command_queue_state_api_collections(
            command_queue_state_records=command_queue_state_records,
        ),
        **_build_target_mailbox_phone_home_api_collections(
            target_mailbox_records=target_mailbox_records,
            target_phone_home_records=target_phone_home_records,
        ),
    }

def _build_command_copy_api_collections(*, command_copy_records, command_copy_state_records):
    return {
        "command_copy_records": status_indexes.api_collection_record(
            "command_copy_records", command_copy_records, "path", (
                "command_copy_records_by_path", "command_copy_records_by_exists",
                "command_copy_records_by_readable", "command_copy_records_by_has_command",
                "command_copy_records_by_command_sha256",
            ), "command_copy_exists_count",
        ),
        "command_copy_state_records": status_indexes.api_collection_record(
            "command_copy_state_records", command_copy_state_records, "id", (
                "command_copy_state_records_by_id",
                "command_copy_state_records_by_path",
                "command_copy_state_records_by_exists",
                "command_copy_state_records_by_readable",
                "command_copy_state_records_by_has_command",
                "command_copy_state_records_by_empty_or_missing",
                "command_copy_state_records_by_has_readable_command",
                "command_copy_state_records_by_command_sha256",
            ), "command_copy_state_record_count",
        ),
    }

def _build_command_queue_state_api_collections(*, command_queue_state_records):
    return {
        "command_queue_state_records": status_indexes.api_collection_record(
            "command_queue_state_records", command_queue_state_records, "path", (
                "command_queue_state_records_by_path",
                "command_queue_state_records_by_exists",
                "command_queue_state_records_by_valid",
                "command_queue_state_records_by_has_commands",
            ), "command_queue_state_record_count",
        ),
    }

def _build_target_mailbox_api_collections(*, target_mailbox_records):
    return {
        "target_mailbox_records": status_indexes.api_collection_record(
            "target_mailbox_records", target_mailbox_records, "command_id", (
                "target_mailbox_records_by_id",
                "target_mailbox_records_by_command_id",
                "target_mailbox_records_by_target_id",
                "target_mailbox_records_by_target_label",
                "target_mailbox_records_by_target_connectivity_state",
                "target_mailbox_records_by_target_last_seen_via",
                "target_mailbox_records_by_target_offline_age_bucket",
                "target_mailbox_records_by_has_target_next_expected_poll",
                "target_mailbox_records_by_target_poll_overdue",
                "target_mailbox_records_by_status",
                "target_mailbox_records_by_waiting_for",
                "target_mailbox_records_by_pending_reason",
                "target_mailbox_records_by_has_pending_reason",
                "target_mailbox_records_by_work_kind",
                "target_mailbox_records_by_workflow",
                "target_mailbox_records_by_request_name",
                "target_mailbox_records_by_bridge_profile",
                "target_mailbox_records_by_bridge_requires_target_online",
                "target_mailbox_records_by_route_kind",
                "target_mailbox_records_by_expired",
                "target_mailbox_records_by_age_bucket",
                "target_mailbox_records_by_pending_delivery_age_bucket",
                "target_mailbox_records_by_delivered_without_result_age_bucket",
                "target_mailbox_records_by_result_latency_bucket",
                "target_mailbox_records_by_pending_work",
                "target_mailbox_records_by_pending_delivery",
                "target_mailbox_records_by_delivered_without_result",
                "target_mailbox_records_by_has_result",
                "target_mailbox_records_by_result_status",
                "target_mailbox_records_by_result_exit_code",
                "target_mailbox_records_by_result_output_exceeded_limit",
                "target_mailbox_records_by_result_output_size_bucket",
                "target_mailbox_records_by_command_sha256",
            ), "target_mailbox_record_count",
        ),
    }

def _build_target_phone_home_api_collections(*, target_phone_home_records):
    return {
        "target_phone_home_records": status_indexes.api_collection_record(
            "target_phone_home_records", target_phone_home_records, "id", (
                "target_phone_home_records_by_id",
                "target_phone_home_records_by_event_id",
                "target_phone_home_records_by_kind",
                "target_phone_home_records_by_status",
                "target_phone_home_records_by_successful",
                "target_phone_home_records_by_failed",
                "target_phone_home_records_by_target_id",
                "target_phone_home_records_by_target_label",
                "target_phone_home_records_by_target_connectivity_state",
                "target_phone_home_records_by_target_last_seen_via",
                "target_phone_home_records_by_target_offline_age_bucket",
                "target_phone_home_records_by_target_poll_overdue",
                "target_phone_home_records_by_target_mailbox_pending_work_count",
                "target_phone_home_records_by_has_target_identity",
                "target_phone_home_records_by_anonymous",
                "target_phone_home_records_by_contact_path",
                "target_phone_home_records_by_remote_addr",
                "target_phone_home_records_by_http_status",
                "target_phone_home_records_by_reason",
                "target_phone_home_records_by_pending_reason",
                "target_phone_home_records_by_has_pending_reason",
                "target_phone_home_records_by_has_queued_remaining_count",
                "target_phone_home_records_by_pending_work_remaining",
                "target_phone_home_records_by_queued_remaining_count",
                "target_phone_home_records_by_command_id",
                "target_phone_home_records_by_work_kind",
                "target_phone_home_records_by_workflow",
                "target_phone_home_records_by_request_name",
                "target_phone_home_records_by_bridge_profile",
                "target_phone_home_records_by_bridge_requires_target_online",
                "target_phone_home_records_by_route_kind",
                "target_phone_home_records_by_poll_mode",
                "target_phone_home_records_by_poll_interval_sec",
            ), "target_phone_home_record_count",
        ),
    }

def _build_target_mailbox_phone_home_api_collections(*, target_mailbox_records, target_phone_home_records):
    return {
        **_build_target_mailbox_api_collections(
            target_mailbox_records=target_mailbox_records,
        ),
        **_build_target_phone_home_api_collections(
            target_phone_home_records=target_phone_home_records,
        ),
    }

def _build_release_api_collections(
    *,
    release,
    release_artifact_workflow_actions,
    release_state_records,
):
    return {
        **_build_release_artifact_api_collections(
            release=release,
        ),
        **_build_release_workflow_api_collections(
            release_artifact_workflow_actions=release_artifact_workflow_actions,
        ),
        **_build_release_license_device_api_collections(
            release=release,
        ),
        **_build_release_state_api_collections(
            release_state_records=release_state_records,
        ),
    }

def _build_release_artifact_api_collections(*, release):
    return {
        "release_artifacts": status_indexes.api_collection_record(
            "release_artifacts", release.get("artifacts") or [], "path", (
                "artifacts_by_release_path", "artifacts_by_name", "artifacts_by_sha256",
                "artifacts_by_payload_preset", "artifacts_by_tool", "artifacts_by_feature",
                "artifacts_by_compatibility", "artifacts_by_source", "artifacts_by_tuple_path",
                "artifacts_by_tuple_payload_preset",
                "artifacts_by_device_alias",
                "artifacts_by_tool_payload_preset", "artifacts_by_device_payload_preset",
                "artifacts_by_feature_payload_preset",
                "artifacts_by_provider_tool", "artifacts_by_provider_status",
                "artifacts_by_doom_wad_filename", "artifacts_by_doom_wad_sha256",
                "artifacts_by_command_queue_enabled", "artifacts_by_command_queue_execution_supported",
                "artifacts_by_command_queue_operator_supplied_command_execution",
            ), "release_artifact_count",
        ),
        "release_recommendations": status_indexes.api_collection_record(
            "release_recommendations", release.get("recommendation_records") or [], "id", (
                "recommendations_by_id", "recommendations_by_scope", "recommendations_by_artifact",
                "recommendations_by_payload_preset", "recommendations_by_compatibility",
            ), "release_recommendation_count",
        ),
    }

def _build_release_workflow_api_collections(*, release_artifact_workflow_actions):
    return {
        "release_artifact_workflow_actions": status_indexes.api_collection_record(
            "release_artifact_workflow_actions", release_artifact_workflow_actions, "id", (
                "release_artifact_workflow_actions_by_id",
                "release_artifact_workflow_actions_by_action_id",
                "release_artifact_workflow_actions_by_category",
                "release_artifact_workflow_actions_by_workflow",
                "release_artifact_workflow_actions_by_selector_kind",
                "release_artifact_workflow_actions_by_release_dir",
                "release_artifact_workflow_actions_by_release_name",
                "release_artifact_workflow_actions_by_release_present",
                "release_artifact_workflow_actions_by_release_valid",
                "release_artifact_workflow_actions_by_artifact_name",
                "release_artifact_workflow_actions_by_release_path",
                "release_artifact_workflow_actions_by_payload_preset",
                "release_artifact_workflow_actions_by_compatibility_label",
                "release_artifact_workflow_actions_by_recommendation_scope",
                "release_artifact_workflow_actions_by_writes_staged_files",
                "release_artifact_workflow_actions_by_available",
                "release_artifact_workflow_actions_by_requires_input",
                "release_artifact_workflow_actions_by_requires_confirmation",
                "release_artifact_workflow_actions_by_operator_action_state",
                "release_artifact_workflow_actions_by_operator_action_reason",
                "release_artifact_workflow_actions_by_can_run_from_curses_enter",
                "release_artifact_workflow_actions_by_curses_enter_action",
            ), "release_artifact_workflow_action_count",
        ),
    }

def _build_release_license_device_api_collections(*, release):
    return {
        "release_licenses": status_indexes.api_collection_record(
            "release_licenses", release.get("release_license_records") or [], "project_license", (
                "release_license_records_by_project_license",
                "release_license_records_by_combined_gplv2_compatible",
                "release_license_records_by_corresponding_source_required",
                "release_license_records_by_corresponding_source_status",
                "release_license_records_by_package_license_audit",
                "release_license_records_by_component",
                "release_license_records_by_component_license",
                "release_license_records_by_notice_file",
                "release_license_records_by_evidence_source",
                "release_license_records_by_evidence_source_license",
            ), "release_license_count",
        ),
        "release_devices": status_indexes.api_collection_record(
            "release_devices", release.get("devices") or [], "name", (
                "devices_by_name", "devices_by_tuple_path", "devices_by_artifact",
            ), "release_device_count",
        ),
        "release_tuples": status_indexes.api_collection_record(
            "release_tuples", release.get("tuples") or [], "path", (
                "tuples_by_path", "tuples_by_artifact",
            ), "release_tuple_count",
        ),
    }

def _build_release_state_api_collections(*, release_state_records):
    return {
        "release_state_records": status_indexes.api_collection_record(
            "release_state_records", release_state_records, "release_dir", (
                "release_state_records_by_release_dir",
                "release_state_records_by_present",
                "release_state_records_by_valid",
                "release_state_records_by_detection_source",
                "release_state_records_by_detection_reason",
                "release_state_records_by_explicit_release_dir",
                "release_state_records_by_marker_count",
            ), "release_state_record_count",
        ),
    }

def _build_command_queue_api_collections(
    *,
    command_queue,
    command_queue_workflow_actions,
    command_queue_policy_records,
):
    return {
        **_build_command_queue_command_api_collections(
            command_queue=command_queue,
        ),
        **_build_command_queue_workflow_api_collections(
            command_queue_workflow_actions=command_queue_workflow_actions,
        ),
        **_build_command_queue_policy_api_collections(
            command_queue=command_queue,
            command_queue_policy_records=command_queue_policy_records,
        ),
    }

def _build_command_queue_command_api_collections(*, command_queue):
    return {
        "command_queue_commands": status_indexes.api_collection_record(
            "command_queue_commands", command_queue.get("commands") or [], "id", (
                "commands_by_id", "commands_by_status", "commands_by_command_sha256",
                "commands_by_target_id", "commands_by_created_at",
                "commands_by_delivered_at", "commands_by_result_received_at",
                "commands_by_result_source_path", "commands_by_timeout_sec",
                "commands_by_max_output_bytes", "commands_by_expire_sec",
                "commands_by_expires_at", "commands_by_expired",
                "commands_by_execution_decision",
                "commands_by_result_status",
                "commands_by_result_exit_code", "commands_by_result_output_exceeded",
                "commands_by_result_output_size_bucket",
                "commands_by_queue_policy_enabled", "commands_by_queue_policy_valid",
                "commands_by_queue_policy_execution_mode", "commands_by_queue_policy_allowed_commands",
                "commands_by_delivery_policy_enabled", "commands_by_delivery_policy_valid",
                "commands_by_delivery_policy_execution_mode",
                "commands_by_delivery_policy_delivery_supported",
                "commands_by_delivery_policy_result_upload_supported",
                "commands_by_delivery_policy_active_control_channel",
            ), "command_queue_total_count",
        ),
    }

def _build_command_queue_workflow_api_collections(*, command_queue_workflow_actions):
    return {
        "command_queue_workflow_actions": status_indexes.api_collection_record(
            "command_queue_workflow_actions", command_queue_workflow_actions, "id", (
                "command_queue_workflow_actions_by_id",
                "command_queue_workflow_actions_by_action_id",
                "command_queue_workflow_actions_by_category",
                "command_queue_workflow_actions_by_workflow",
                "command_queue_workflow_actions_by_actual",
                "command_queue_workflow_actions_by_target_filter_active",
                "command_queue_workflow_actions_by_policy_valid",
                "command_queue_workflow_actions_by_configured_for_polling",
                "command_queue_workflow_actions_by_poll_transport_supported",
                "command_queue_workflow_actions_by_live_polling_supported",
                "command_queue_workflow_actions_by_result_upload_supported",
                "command_queue_workflow_actions_by_execution_supported",
                "command_queue_workflow_actions_by_delivery_supported",
                "command_queue_workflow_actions_by_operator_queue_records_only",
                "command_queue_workflow_actions_by_target_mailbox_pending_target_count",
                "command_queue_workflow_actions_by_target_mailbox_pending_work_count",
                "command_queue_workflow_actions_by_target_mailbox_pending_poll_overdue_count",
                "command_queue_workflow_actions_by_fleet_target_count",
                "command_queue_workflow_actions_by_fleet_offline_target_count",
                "command_queue_workflow_actions_by_fleet_stale_target_count",
                "command_queue_workflow_actions_by_fleet_mailbox_pending_target_count",
                "command_queue_workflow_actions_by_fleet_mailbox_pending_work_count",
                "command_queue_workflow_actions_by_fleet_poll_overdue_target_count",
                "command_queue_workflow_actions_by_fleet_has_offline_targets",
                "command_queue_workflow_actions_by_fleet_has_stale_targets",
                "command_queue_workflow_actions_by_fleet_has_mailbox_pending_work",
                "command_queue_workflow_actions_by_fleet_has_poll_overdue_targets",
                "command_queue_workflow_actions_by_requires_input",
                "command_queue_workflow_actions_by_requires_confirmation",
                "command_queue_workflow_actions_by_queues_offline_work",
                "command_queue_workflow_actions_by_target_phone_home_required",
                "command_queue_workflow_actions_by_operator_action_state",
                "command_queue_workflow_actions_by_operator_action_reason",
                "command_queue_workflow_actions_by_can_run_from_curses_enter",
                "command_queue_workflow_actions_by_curses_enter_action",
            ), "command_queue_workflow_action_count",
        ),
    }

def _build_command_queue_policy_api_collections(*, command_queue, command_queue_policy_records):
    return {
        "command_queue_policy_records": status_indexes.api_collection_record(
            "command_queue_policy_records", command_queue_policy_records, "id", (
                "command_queue_policy_records_by_id",
                "command_queue_policy_records_by_enabled",
                "command_queue_policy_records_by_valid",
                "command_queue_policy_records_by_configured_for_polling",
                "command_queue_policy_records_by_execution_mode",
                "command_queue_policy_records_by_allowed_commands",
                "command_queue_policy_records_by_token_required",
                "command_queue_policy_records_by_token_configured",
                "command_queue_policy_records_by_safe_disabled_default",
                "command_queue_policy_records_by_poll_transport_supported",
                "command_queue_policy_records_by_live_polling_supported",
                "command_queue_policy_records_by_active_control_channel",
                "command_queue_policy_records_by_arbitrary_execution_allowed",
            ), "command_queue_policy_record_count",
        ),
        "command_queue_modes": status_indexes.api_collection_record(
            "command_queue_modes", command_queue.get("mode_records") or [], "mode", (
                "command_queue_modes_by_mode", "command_queue_modes_by_lifecycle",
                "command_queue_modes_by_requires_operator_host",
                "command_queue_modes_by_would_poll_if_configured",
                "command_queue_modes_by_live_supported",
                "command_queue_modes_by_live_transport_supported",
                "command_queue_modes_by_delivery_supported",
                "command_queue_modes_by_result_upload_supported",
                "command_queue_modes_by_execution_supported",
                "command_queue_modes_by_active_control_channel",
                "command_queue_modes_by_operator_supplied_command_execution",
            ), "command_queue_mode_count",
        ),
    }

def _build_workbench_api_collections(
    *,
    operator_console_workflows,
    workbench_actions,
    operator_daemon_workflow_actions,
    workbench_config_fields,
    workbench_jobs,
):
    return {
        **_build_operator_console_workflow_api_collections(
            operator_console_workflows=operator_console_workflows,
        ),
        **_build_workbench_action_api_collections(
            workbench_actions=workbench_actions,
        ),
        **_build_operator_daemon_action_api_collections(
            operator_daemon_workflow_actions=operator_daemon_workflow_actions,
        ),
        **_build_workbench_config_api_collections(
            workbench_config_fields=workbench_config_fields,
        ),
        **_build_workbench_job_api_collections(
            workbench_jobs=workbench_jobs,
        ),
    }

def _build_operator_console_workflow_api_collections(*, operator_console_workflows):
    return {
        "operator_console_workflows": status_indexes.api_collection_record(
            "operator_console_workflows", operator_console_workflows, "id", (
                "operator_console_workflows_by_id",
                "operator_console_workflows_by_workflow",
                "operator_console_workflows_by_group",
                "operator_console_workflows_by_primary_collection",
                "operator_console_workflows_by_target_scoped",
                "operator_console_workflows_by_multi_target",
                "operator_console_workflows_by_offline_queue_supported",
                "operator_console_workflows_by_has_records",
                "operator_console_workflows_by_has_actions",
                "operator_console_workflows_by_has_enter_runnable_actions",
                "operator_console_workflows_by_has_pending_work",
                "operator_console_workflows_by_has_warnings",
                "operator_console_workflows_by_fleet_target_count",
                "operator_console_workflows_by_fleet_offline_target_count",
                "operator_console_workflows_by_fleet_stale_target_count",
                "operator_console_workflows_by_fleet_mailbox_pending_target_count",
                "operator_console_workflows_by_fleet_mailbox_pending_work_count",
                "operator_console_workflows_by_fleet_poll_overdue_target_count",
                "operator_console_workflows_by_fleet_has_offline_targets",
                "operator_console_workflows_by_fleet_has_stale_targets",
                "operator_console_workflows_by_fleet_has_mailbox_pending_work",
                "operator_console_workflows_by_fleet_has_poll_overdue_targets",
                "operator_console_workflows_by_operator_action_state",
                "operator_console_workflows_by_operator_action_reason",
                "operator_console_workflows_by_tui_shortcut",
                "operator_console_workflows_by_line_mode_action",
            ), "operator_console_workflow_count",
        ),
    }

def _build_workbench_action_api_collections(*, workbench_actions):
    return {
        "workbench_actions": status_indexes.api_collection_record(
            "workbench_actions", workbench_actions, "id", (
                "workbench_actions_by_id", "workbench_actions_by_category",
                "workbench_actions_by_script", "workbench_actions_by_background_supported",
                "workbench_actions_by_long_running", "workbench_actions_by_writes_config",
                "workbench_actions_by_runs_build", "workbench_actions_by_requires_confirmation",
                "workbench_actions_by_execution_default",
                "workbench_actions_by_target_execution",
                "workbench_actions_by_event", "workbench_actions_by_config_path",
                "workbench_actions_by_foreground_runnable",
                "workbench_actions_by_dry_run_supported",
                "workbench_actions_by_has_placeholder",
                "workbench_actions_by_has_run_command",
                "workbench_actions_by_has_dry_run_command",
                "workbench_actions_by_has_start_job_command",
                "workbench_actions_by_operator_action_state",
                "workbench_actions_by_operator_action_reason",
                "workbench_actions_by_can_run_from_curses_enter",
                "workbench_actions_by_curses_enter_action",
            ), "workbench_action_count",
        ),
    }

def _build_operator_daemon_action_api_collections(*, operator_daemon_workflow_actions):
    return {
        "operator_daemon_workflow_actions": status_indexes.api_collection_record(
            "operator_daemon_workflow_actions", operator_daemon_workflow_actions, "id", (
                "operator_daemon_workflow_actions_by_id",
                "operator_daemon_workflow_actions_by_action_id",
                "operator_daemon_workflow_actions_by_workbench_action_id",
                "operator_daemon_workflow_actions_by_category",
                "operator_daemon_workflow_actions_by_workflow",
                "operator_daemon_workflow_actions_by_daemon_status",
                "operator_daemon_workflow_actions_by_daemon_attached",
                "operator_daemon_workflow_actions_by_control_state_exists",
                "operator_daemon_workflow_actions_by_command_queue_file_exists",
                "operator_daemon_workflow_actions_by_command_queue_command_count",
                "operator_daemon_workflow_actions_by_command_queue_queued_count",
                "operator_daemon_workflow_actions_by_command_queue_result_received_count",
                "operator_daemon_workflow_actions_by_command_queue_target_count",
                "operator_daemon_workflow_actions_by_targets_file_exists",
                "operator_daemon_workflow_actions_by_target_count",
                "operator_daemon_workflow_actions_by_target_registry_record_count",
                "operator_daemon_workflow_actions_by_fleet_target_count",
                "operator_daemon_workflow_actions_by_fleet_offline_target_count",
                "operator_daemon_workflow_actions_by_fleet_stale_target_count",
                "operator_daemon_workflow_actions_by_fleet_mailbox_pending_target_count",
                "operator_daemon_workflow_actions_by_fleet_mailbox_pending_work_count",
                "operator_daemon_workflow_actions_by_fleet_poll_overdue_target_count",
                "operator_daemon_workflow_actions_by_fleet_has_offline_targets",
                "operator_daemon_workflow_actions_by_fleet_has_stale_targets",
                "operator_daemon_workflow_actions_by_fleet_has_mailbox_pending_work",
                "operator_daemon_workflow_actions_by_fleet_has_poll_overdue_targets",
                "operator_daemon_workflow_actions_by_staged_file_count",
                "operator_daemon_workflow_actions_by_workbench_job_count",
                "operator_daemon_workflow_actions_by_background_supported",
                "operator_daemon_workflow_actions_by_foreground_runnable",
                "operator_daemon_workflow_actions_by_dry_run_supported",
                "operator_daemon_workflow_actions_by_requires_confirmation",
                "operator_daemon_workflow_actions_by_writes_config",
                "operator_daemon_workflow_actions_by_systemd_user_action",
                "operator_daemon_workflow_actions_by_operator_action_state",
                "operator_daemon_workflow_actions_by_operator_action_reason",
                "operator_daemon_workflow_actions_by_can_run_from_curses_enter",
                "operator_daemon_workflow_actions_by_curses_enter_action",
            ), "operator_daemon_workflow_action_count",
        ),
    }

def _build_workbench_config_api_collections(*, workbench_config_fields):
    return {
        "workbench_config_fields": status_indexes.api_collection_record(
            "workbench_config_fields", workbench_config_fields, "key", (
                "workbench_config_fields_by_key", "workbench_config_fields_by_category",
                "workbench_config_fields_by_configured", "workbench_config_fields_by_fixed_options",
                "workbench_config_fields_by_writes_config", "workbench_config_fields_by_target_execution",
                "workbench_config_fields_by_source_format",
                "workbench_config_fields_by_has_set_command", "workbench_config_fields_by_set_command_kind",
                "workbench_config_fields_by_safety_boundary", "workbench_config_fields_by_control_like",
                "workbench_config_fields_by_reverse_access_related", "workbench_config_fields_by_command_queue_related",
                "workbench_config_fields_by_requires_explicit_operator_choice",
            ), "workbench_config_field_count",
        ),
    }

def _build_workbench_job_api_collections(*, workbench_jobs):
    return {
        "workbench_jobs": status_indexes.api_collection_record(
            "workbench_jobs", workbench_jobs, "id", (
                "workbench_jobs_by_id", "workbench_jobs_by_action",
                "workbench_jobs_by_state", "workbench_jobs_by_effective_state",
                "workbench_jobs_by_category", "workbench_jobs_by_script",
                "workbench_jobs_by_pid", "workbench_jobs_by_pid_managed",
                "workbench_jobs_by_cancel_supported", "workbench_jobs_by_log_exists",
                "workbench_jobs_by_exit_status_known",
                "workbench_jobs_by_started_at_known", "workbench_jobs_by_finished_at_known",
                "workbench_jobs_by_duration_known", "workbench_jobs_by_elapsed_known",
                "workbench_jobs_by_background_supported", "workbench_jobs_by_long_running",
                "workbench_jobs_by_outcome", "workbench_jobs_by_exit_status",
                "workbench_jobs_by_last_output_tail_truncated",
            ), "workbench_job_count",
        ),
    }

def _build_history_api_collections(
    *,
    workbench_jobs_state_records,
    uploads,
    fetches,
    session_root_state_records,
    sessions,
    events,
    event_log_state_records,
):
    return {
        **_build_workbench_job_history_api_collections(
            workbench_jobs_state_records=workbench_jobs_state_records,
        ),
        **_build_file_transfer_history_api_collections(
            uploads=uploads,
            fetches=fetches,
        ),
        **_build_session_history_api_collections(
            session_root_state_records=session_root_state_records,
            sessions=sessions,
        ),
        **_build_event_history_api_collections(
            events=events,
            event_log_state_records=event_log_state_records,
        ),
    }

def _build_workbench_job_history_api_collections(*, workbench_jobs_state_records):
    return {
        "workbench_jobs_state_records": status_indexes.api_collection_record(
            "workbench_jobs_state_records", workbench_jobs_state_records, "path", (
                "workbench_jobs_state_records_by_path",
                "workbench_jobs_state_records_by_exists",
                "workbench_jobs_state_records_by_valid",
                "workbench_jobs_state_records_by_has_jobs",
            ), "workbench_jobs_state_record_count",
        ),
    }

def _build_file_transfer_history_api_collections(*, uploads, fetches):
    return {
        "uploads": status_indexes.api_collection_record(
            "uploads", uploads, "metadata_path", (
                "uploads_by_session", "uploads_by_filename", "uploads_by_kind", "uploads_by_sha256",
                "uploads_by_target_id", "uploads_by_source_path", "uploads_by_stored_path", "uploads_by_remote_addr",
                "uploads_by_status", "uploads_by_kind_status", "uploads_by_filename_status",
                "uploads_by_stored_exists", "uploads_by_status_stored_exists",
                "uploads_by_status_remote_addr", "uploads_by_metadata_exists",
                "uploads_by_event_log_exists",
            ), "upload_count",
        ),
        "fetches": status_indexes.api_collection_record(
            "fetches", fetches, "metadata_path", (
                "fetches_by_session", "fetches_by_request", "fetches_by_sha256", "fetches_by_target_id",
                "fetches_by_source_path", "fetches_by_status", "fetches_by_http_status",
                "fetches_by_source_exists", "fetches_by_remote_addr", "fetches_by_request_status",
                "fetches_by_status_source_exists", "fetches_by_metadata_exists",
                "fetches_by_event_log_exists",
                "fetches_by_status_remote_addr", "fetches_by_http_status_remote_addr",
            ), "fetch_count",
        ),
    }

def _build_session_history_api_collections(*, session_root_state_records, sessions):
    return {
        "session_root_state_records": status_indexes.api_collection_record(
            "session_root_state_records", session_root_state_records, "path", (
                "session_root_state_records_by_path",
                "session_root_state_records_by_exists",
                "session_root_state_records_by_has_recent_sessions",
                "session_root_state_records_by_has_uploads",
                "session_root_state_records_by_has_fetches",
                "session_root_state_records_by_has_events",
            ), "session_root_state_record_count",
        ),
        "sessions": status_indexes.api_collection_record(
            "sessions", sessions, "session_id", (
                "sessions_by_id", "sessions_by_service", "sessions_by_state",
                "sessions_by_exit_reason", "sessions_by_remote",
                "sessions_by_service_state", "sessions_by_service_exit_reason",
                "sessions_by_service_remote", "sessions_by_target_id", "sessions_by_has_uploads",
                "sessions_by_has_fetches", "sessions_by_has_events",
                "sessions_by_has_artifacts", "sessions_by_has_session_log",
                "sessions_by_duration_known", "sessions_by_metadata_exists",
                "sessions_by_event_log_exists", "sessions_by_session_log_exists",
            ), "session_count",
        ),
    }

def _build_event_history_api_collections(*, events, event_log_state_records):
    return {
        "events": status_indexes.api_collection_record(
            "events", events, "id", (
                "events_by_id", "events_by_session", "events_by_service",
                "events_by_event", "events_by_level", "events_by_remote",
                "events_by_service_event", "events_by_session_event",
                "events_by_service_level", "events_by_event_level",
                "events_by_session_level", "events_by_remote_event",
                "events_by_remote_level",
                "events_by_detail_status", "events_by_detail_operation",
                "events_by_detail_http_status", "events_by_detail_reason",
                "events_by_detail_command_id", "events_by_event_detail_status",
                "events_by_service_detail_status", "events_by_event_detail_operation",
                "events_by_service_detail_operation", "events_by_event_detail_http_status",
                "events_by_service_detail_http_status", "events_by_detail_request_name",
                "events_by_event_detail_request_name", "events_by_service_detail_request_name",
                "events_by_detail_filename", "events_by_event_detail_filename",
                "events_by_service_detail_filename", "events_by_event_detail_reason",
                "events_by_service_detail_reason", "events_by_detail_sha256",
                "events_by_event_detail_sha256", "events_by_service_detail_sha256",
                "events_by_event_detail_command_id",
                "events_by_service_detail_command_id", "events_by_detail_command_sha256",
                "events_by_event_detail_command_sha256", "events_by_service_detail_command_sha256",
                "events_by_detail_job_id",
                "events_by_event_detail_job_id", "events_by_service_detail_job_id",
                "events_by_detail_action_id", "events_by_event_detail_action_id",
                "events_by_service_detail_action_id",
                "events_by_detail_key", "events_by_event_detail_key",
                "events_by_service_detail_key", "events_by_detail_config_path",
                "events_by_event_detail_config_path", "events_by_service_detail_config_path",
                "events_by_detail_target_id", "events_by_detail_target_label",
                "events_by_detail_expected_target_id",
                "events_by_detail_target_identity_source",
                "events_by_detail_target_identity_confidence",
                "events_by_detail_poll_mode", "events_by_detail_poll_interval_sec",
                "events_by_detail_poll_jitter_pct", "events_by_detail_poll_backoff",
                "events_by_detail_poll_max_interval_sec", "events_by_detail_max_polls",
                "events_by_event_detail_target_id", "events_by_service_detail_target_id",
                "events_by_event_detail_target_label", "events_by_service_detail_target_label",
                "events_by_event_detail_expected_target_id",
                "events_by_service_detail_expected_target_id",
                "events_by_event_detail_target_identity_source",
                "events_by_service_detail_target_identity_source",
                "events_by_event_detail_target_identity_confidence",
                "events_by_service_detail_target_identity_confidence",
            ), "event_tail_count",
        ),
        "event_log_state_records": status_indexes.api_collection_record(
            "event_log_state_records", event_log_state_records, "path", (
                "event_log_state_records_by_path",
                "event_log_state_records_by_exists",
                "event_log_state_records_by_valid",
                "event_log_state_records_by_tail_truncated",
                "event_log_state_records_by_has_invalid_records",
                "event_log_state_records_by_tail_has_records",
                "event_log_state_records_by_tail_has_omitted_records",
                "event_log_state_records_by_tail_empty_due_to_limit",
            ), "event_log_state_record_count",
        ),
    }

def _build_status_service_health_api_collections(
    *,
    services,
    service_workflow_actions,
    probe_workflow_actions,
    service_manager_resources,
    service_manager_state_records,
    bridge_profiles,
    bridge_profile_workflow_actions,
    bridge_hop_records,
    ports,
    path_status_records,
    server_state_records,
    operator_state_records_list,
    operator_network_records,
    operator_network_state_records,
    browser_paths,
    warnings,
):
    return {
        **_build_service_bridge_api_collections(
            services=services,
            service_workflow_actions=service_workflow_actions,
            probe_workflow_actions=probe_workflow_actions,
            service_manager_resources=service_manager_resources,
            service_manager_state_records=service_manager_state_records,
            bridge_profiles=bridge_profiles,
            bridge_profile_workflow_actions=bridge_profile_workflow_actions,
            bridge_hop_records=bridge_hop_records,
        ),
        **_build_operator_health_api_collections(
            ports=ports,
            path_status_records=path_status_records,
            server_state_records=server_state_records,
            operator_state_records_list=operator_state_records_list,
            operator_network_records=operator_network_records,
            operator_network_state_records=operator_network_state_records,
            browser_paths=browser_paths,
            warnings=warnings,
        ),
    }

def _build_status_target_activity_api_collections(
    *,
    target_command_records,
    target_workflow_actions,
    target_command_state_records,
    rshell_session_policy_records,
    targets,
    target_registry_state_records,
    target_filter_records,
    target_attribution_records,
    staged_records,
    staged_file_workflow_actions,
    file_service_workflow_actions,
    target_file_transfer_records,
    target_activity_records,
    staged_files_state_records,
    command_copy_records,
    command_copy_state_records,
    command_queue_state_records,
    target_mailbox_records,
    target_phone_home_records,
):
    return {
        **_build_target_api_collections(
            target_command_records=target_command_records,
            target_workflow_actions=target_workflow_actions,
            target_command_state_records=target_command_state_records,
            rshell_session_policy_records=rshell_session_policy_records,
            targets=targets,
            target_registry_state_records=target_registry_state_records,
            target_filter_records=target_filter_records,
            target_attribution_records=target_attribution_records,
        ),
        **_build_staged_file_activity_api_collections(
            staged_records=staged_records,
            staged_file_workflow_actions=staged_file_workflow_actions,
            file_service_workflow_actions=file_service_workflow_actions,
            target_file_transfer_records=target_file_transfer_records,
            target_activity_records=target_activity_records,
            staged_files_state_records=staged_files_state_records,
        ),
        **_build_command_mailbox_api_collections(
            command_copy_records=command_copy_records,
            command_copy_state_records=command_copy_state_records,
            command_queue_state_records=command_queue_state_records,
            target_mailbox_records=target_mailbox_records,
            target_phone_home_records=target_phone_home_records,
        ),
    }

def _build_status_history_workbench_api_collections(
    *,
    workbench_jobs_state_records,
    uploads,
    fetches,
    session_root_state_records,
    sessions,
    events,
    event_log_state_records,
    release,
    release_artifact_workflow_actions,
    release_state_records,
    command_queue,
    command_queue_workflow_actions,
    command_queue_policy_records,
    operator_console_workflows,
    workbench_actions,
    operator_daemon_workflow_actions,
    workbench_config_fields,
    workbench_jobs,
):
    return {
        **_build_history_api_collections(
            workbench_jobs_state_records=workbench_jobs_state_records,
            uploads=uploads,
            fetches=fetches,
            session_root_state_records=session_root_state_records,
            sessions=sessions,
            events=events,
            event_log_state_records=event_log_state_records,
        ),
        **_build_release_api_collections(
            release=release,
            release_artifact_workflow_actions=release_artifact_workflow_actions,
            release_state_records=release_state_records,
        ),
        **_build_command_queue_api_collections(
            command_queue=command_queue,
            command_queue_workflow_actions=command_queue_workflow_actions,
            command_queue_policy_records=command_queue_policy_records,
        ),
        **_build_workbench_api_collections(
            operator_console_workflows=operator_console_workflows,
            workbench_actions=workbench_actions,
            operator_daemon_workflow_actions=operator_daemon_workflow_actions,
            workbench_config_fields=workbench_config_fields,
            workbench_jobs=workbench_jobs,
        ),
    }

def _build_status_api_collections(**data):
    return {
        **_build_status_service_health_api_collections(
            services=data["services"],
            service_workflow_actions=data["service_workflow_actions"],
            probe_workflow_actions=data["probe_workflow_actions"],
            service_manager_resources=data["service_manager_resources"],
            service_manager_state_records=data["service_manager_state_records"],
            bridge_profiles=data["bridge_profiles"],
            bridge_profile_workflow_actions=data["bridge_profile_workflow_actions"],
            bridge_hop_records=data["bridge_hop_records"],
            ports=data["ports"],
            path_status_records=data["path_status_records"],
            server_state_records=data["server_state_records"],
            operator_state_records_list=data["operator_state_records_list"],
            operator_network_records=data["operator_network_records"],
            operator_network_state_records=data["operator_network_state_records"],
            browser_paths=data["browser_paths"],
            warnings=data["warnings"],
        ),
        **_build_status_target_activity_api_collections(
            target_command_records=data["target_command_records"],
            target_workflow_actions=data["target_workflow_actions"],
            target_command_state_records=data["target_command_state_records"],
            rshell_session_policy_records=data["rshell_session_policy_records"],
            targets=data["targets"],
            target_registry_state_records=data["target_registry_state_records"],
            target_filter_records=data["target_filter_records"],
            target_attribution_records=data["target_attribution_records"],
            staged_records=data["staged_records"],
            staged_file_workflow_actions=data["staged_file_workflow_actions"],
            file_service_workflow_actions=data["file_service_workflow_actions"],
            target_file_transfer_records=data["target_file_transfer_records"],
            target_activity_records=data["target_activity_records"],
            staged_files_state_records=data["staged_files_state_records"],
            command_copy_records=data["command_copy_records"],
            command_copy_state_records=data["command_copy_state_records"],
            command_queue_state_records=data["command_queue_state_records"],
            target_mailbox_records=data["target_mailbox_records"],
            target_phone_home_records=data["target_phone_home_records"],
        ),
        **_build_status_history_workbench_api_collections(
            workbench_jobs_state_records=data["workbench_jobs_state_records"],
            uploads=data["uploads"],
            fetches=data["fetches"],
            session_root_state_records=data["session_root_state_records"],
            sessions=data["sessions"],
            events=data["events"],
            event_log_state_records=data["event_log_state_records"],
            release=data["release"],
            release_artifact_workflow_actions=data[
                "release_artifact_workflow_actions"
            ],
            release_state_records=data["release_state_records"],
            command_queue=data["command_queue"],
            command_queue_workflow_actions=data["command_queue_workflow_actions"],
            command_queue_policy_records=data["command_queue_policy_records"],
            operator_console_workflows=data["operator_console_workflows"],
            workbench_actions=data["workbench_actions"],
            operator_daemon_workflow_actions=data[
                "operator_daemon_workflow_actions"
            ],
            workbench_config_fields=data["workbench_config_fields"],
            workbench_jobs=data["workbench_jobs"],
        ),
    }


def build_status_api_collections(**data):
    return _build_status_api_collections(**data)
