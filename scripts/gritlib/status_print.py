"""Status document rendering helpers for grit-console."""

import json

from gritlib.command_queue import print_workbench_command_queue_summary
from gritlib.event_log import print_event_log_summary
from gritlib.file_transfers import (
    print_recent_fetches, print_recent_uploads, recent_upload_metadata,
    render_fetch_command,
)
from gritlib.operator_network import sorted_local_ips
from gritlib.session_state import utc_now
from gritlib.session_records import print_recent_sessions
from gritlib.status_indexes import (
    print_activity_summary, print_api_resource_summary,
    print_operator_state_records,
)
from gritlib.status_print_release import (
    print_release_browser, print_snapshot_release_browser,
)
from gritlib.target_activity import print_workbench_phone_home_attempts
import gritlib.status_print_workflows as status_print_workflows
from gritlib.target_records import (
    print_target_summary, target_filter_evidence_lines,
    target_filter_summary_text,
)
from gritlib.warnings import print_warning_summary, warning_badge_suffix


def _print_status_header(doc):
    print("griTTYkit server status")
    print(f"  state_file: {doc['state_file']}")
    print(f"  staged_files: {doc['staged_files']}")
    print(f"  command_queue_file: {doc['command_queue_file']}")
    print(f"  command_copy_file: {doc['command_copy_file']}")
    if (doc.get("command_copy") or {}).get("has_command"):
        print(f"  last_copied_command: {(doc.get('command_copy') or {}).get('command', '')}")
    print(f"  workbench_jobs_file: {doc['workbench_jobs_file']}")
    print(f"  targets_file: {doc['targets_file']}")
    if (doc.get("target_filter") or {}).get("active"):
        target_filter = doc.get("target_filter") or {}
        print(f"  {target_filter_summary_text(target_filter)}")
        for line in target_filter_evidence_lines(target_filter):
            print(f"    selected_target_{line}")
    print(f"  session_root: {doc['session_root']}")
    manager = doc.get("service_manager") or {}
    print(
        "  runtime_manager: "
        f"shutdown={'yes' if manager.get('shutdown_requested') else 'no'} "
        f"reason={manager.get('shutdown_reason') or '-'} "
        f"sockets={manager.get('open_socket_count', 0)}/{manager.get('socket_count', 0)} "
        f"transports={manager.get('active_transport_count', 0)}/{manager.get('transport_count', 0)} "
        f"threads={manager.get('alive_thread_count', 0)}/{manager.get('thread_count', 0)} "
        f"children={manager.get('running_child_process_count', 0)}/{manager.get('child_process_count', 0)} "
        f"resources={len(doc.get('service_manager_resources') or [])}"
    )


def _print_path_health(doc):
    print("Path health:")
    for name in sorted(doc.get("path_status") or {}):
        rec = doc["path_status"][name]
        exists = "yes" if rec.get("exists") else "no"
        parent_exists = "yes" if rec.get("parent_exists") else "no"
        writable = "yes" if rec.get("writable") else "no"
        print(f"  {name}: exists={exists} parent_exists={parent_exists} writable={writable} kind={rec.get('expected_kind', '')} path={rec.get('path', '')}")


def _print_service_rows(doc):
    print("Services:")
    for row in doc["services"]:
        stale = " stale-state" if row["stale"] else ""
        pid = f" pid={row['pid']}" if row["pid"] else ""
        tls = "yes" if row["tls"] else "no"
        bind_address = row.get("bind_address") or ""
        warnings = warning_badge_suffix(row)
        print(f"  {row['name']:12s} bind={bind_address} port={row['port']} tls={tls} configured={row['configured']} actual={row['actual']}{pid}{stale}{warnings}")
        if row["pid"] and row.get("pid_managed"):
            print(f"    ownership: {','.join(row.get('ownership_evidence') or [])}")
        elif row["pid"] and row.get("pid_alive"):
            print("    ownership: unverified; --stop will skip this PID")
        if row["listener_endpoints"]:
            for endpoint in row["listener_endpoints"]:
                pids = ",".join(str(pid) for pid in endpoint.get("pids", [])) or "unknown"
                print(f"    listener={endpoint.get('address', '')}:{endpoint.get('port', '')} family={endpoint.get('family', '')} pids={pids}")
        if row["listener_processes"]:
            for owner in row["listener_processes"]:
                print(f"    listener_pid={owner['pid']} process={owner.get('process_name', '')} exe={owner.get('exe', '')} cmdline={owner.get('cmdline', '')}")
        if row["owners"]:
            for owner in row["owners"]:
                print(f"    recorded_owner_pid={owner.get('pid', '')} process={owner.get('process_name', '')} exe={owner.get('exe', '')} cmdline={owner.get('cmdline', '')}")
        if row["error"]:
            print(f"    error: {row['error']}")
        if row.get("stopped_reason"):
            print(f"    stopped_reason: {row.get('stopped_reason', '')} at {row.get('stopped_at', '')}")
        if row["process_log"]:
            print(f"    process_log: {row['process_log']}")
        if row["session_log"]:
            print(f"    session_log: {row['session_log']}")


def _print_status_warnings(doc):
    warnings_printed = False

    def print_warnings_header_once():
        nonlocal warnings_printed
        if not warnings_printed:
            print("")
            print("Warnings:")
            warnings_printed = True

    if doc["summary"].get("path_kind_mismatch_count", 0):
        print_warnings_header_once()
        for rec in (doc.get("path_status") or {}).values():
            if rec.get("expected_kind_mismatch"):
                actual = "dir" if rec.get("is_dir") else ("file" if rec.get("is_file") else "other")
                print(f"  operator path kind mismatch: {rec.get('path', '')} expected={rec.get('expected_kind', '')} actual={actual}")
    if any(row["stale"] for row in doc["services"]):
        print_warnings_header_once()
        print("  stale state detected; run scripts/grit-console --stop to clean managed records")
    if any(row["actual"] == "listening" and row["configured"] not in ("listening", "starting") for row in doc["services"]):
        print_warnings_header_once()
        print("  actual listener detected while configured state is not listening; inspect listener PID ownership")
    if any(row.get("listener_bind_mismatch") for row in doc["services"]):
        print_warnings_header_once()
        print("  listener found on configured port but not configured bind address; inspect listener address/PID ownership")
    if any(row["pid"] and row.get("pid_alive") and not row.get("pid_managed") for row in doc["services"]):
        print_warnings_header_once()
        print("  recorded live PID without ownership evidence detected; --stop will skip it")
    if doc["summary"].get("event_invalid_count", 0):
        print_warnings_header_once()
        print(f"  event log contains {doc['summary'].get('event_invalid_count', 0)} invalid JSONL record(s); inspect {doc['event_log']}")
    invalid_state_warnings = [
        item for item in doc.get("warnings") or []
        if item.get("type") in ("invalid_server_state", "invalid_staged_files_state", "invalid_command_queue_state")
    ]
    if invalid_state_warnings:
        print_warnings_header_once()
        for warning in invalid_state_warnings:
            suffix = f": {warning.get('error', '')}" if warning.get("error") else ""
            print(f"  {warning.get('message', 'operator state file is invalid')}: {warning.get('path', '')}{suffix}")
    invalid_release_warnings = [
        item for item in doc.get("warnings") or []
        if item.get("type") == "invalid_release_state"
    ]
    if invalid_release_warnings:
        print_warnings_header_once()
        for warning in invalid_release_warnings:
            print(f"  release bundle state is invalid: {warning.get('path', '')}")
            for error in warning.get("errors") or []:
                print(f"    {error}")
    if not doc["command_queue"].get("policy_valid", True):
        print_warnings_header_once()
        print("  command queue policy is invalid; target polling is not configured")
        for error in doc["command_queue"].get("policy_errors") or []:
            print(f"    {error}")
    invalid_rshell_warnings = [
        item for item in doc.get("warnings") or []
        if item.get("type") == "invalid_rshell_session_policy"
    ]
    if invalid_rshell_warnings:
        print_warnings_header_once()
        for warning in invalid_rshell_warnings:
            print(f"  rshell session policy is invalid: {warning.get('session_policy', '')}")
            for error in warning.get("session_policy_errors") or []:
                print(f"    {error}")


def _print_snapshot_header(cfg, snap, include_api_summary):
    summary = snap.get("summary") or {}
    print("griTTYkit Operator Workbench")
    print(f"Current time: {utc_now()}")
    print(f"Selected local IP: {snap['selected_local_ip']}")
    workbench = snap.get("workbench") or {}
    if workbench.get("mode"):
        print(f"Workbench mode: {workbench.get('mode', '')}")
    if (snap.get("target_filter") or {}).get("active"):
        target_filter = snap.get("target_filter") or {}
        print(target_filter_summary_text(target_filter, prefix="Target filter:"))
        for line in target_filter_evidence_lines(target_filter):
            print(f"  selected_target_{line}")
    print(f"Workbench refresh: count={workbench.get('refresh_count', 0)} last={workbench.get('last_refresh_at', '') or '-'}")
    print(
        "Service summary: "
        f"listening={summary.get('listening_count', 0)} "
        f"configured_listening={summary.get('configured_listening_count', 0)} "
        f"errors={summary.get('error_count', 0)} "
        f"stale={summary.get('stale_count', 0)} "
        f"warnings={len(snap.get('warnings') or [])}"
    )
    print_activity_summary(summary)
    print_warning_summary(summary)
    if include_api_summary:
        print_api_resource_summary(snap)


def _print_snapshot_operator_paths(cfg, snap):
    print("Operator paths:")
    paths = snap.get("paths") or {}
    for label, key in (
        ("state_file", "state_file"),
        ("staged_files", "staged_files"),
        ("command_queue_file", "command_queue_file"),
        ("command_copy_file", "command_copy_file"),
        ("workbench_jobs_file", "workbench_jobs_file"),
        ("targets_file", "targets_file"),
        ("event_log", "event_log"),
        ("session_root", "session_root"),
    ):
        print(f"  {label}: {paths.get(key, snap.get(key, ''))}")
    print(f"  tls_cert: {cfg.get('tls_cert', '')}")
    print(f"  tls_key: {cfg.get('tls_key', '')}")


def _print_snapshot_path_health(snap):
    print("Path health:")
    path_status = snap.get("path_status") or {}
    for name in sorted(path_status):
        rec = path_status[name]
        exists = "yes" if rec.get("exists") else "no"
        parent_exists = "yes" if rec.get("parent_exists") else "no"
        writable = "yes" if rec.get("writable") else "no"
        print(f"  {name}: exists={exists} parent_exists={parent_exists} writable={writable} kind={rec.get('expected_kind', '')}")


def _print_snapshot_local_ip_candidates(snap):
    print("Local IP candidates:")
    candidates = sorted_local_ips(snap["local_ips"])
    if candidates:
        for ip in candidates:
            print(f"  {ip}")
    else:
        print("  OPERATOR_IP")


def _print_snapshot_services(snap):
    print("Services:")
    for row in snap["services"].values():
        item = row["status_row"]
        pid = f" pid={item['pid']}" if item["pid"] else ""
        tls = "yes" if item["tls"] else "no"
        print(f"  {item['name']:12s} bind={item.get('bind_address', '')} port={item['port']} tls={tls} desired={item['configured']} actual={item['actual']}{pid}")
        if item["error"]:
            print(f"    error: {item['error']}")
        if item["session_log"]:
            print(f"    log: {item['session_log']}")


def _print_snapshot_warnings(snap):
    print("Warnings:")
    warnings = snap.get("warnings") or []
    if warnings:
        for warning in warnings:
            service = warning.get("service", "")
            prefix = f"{warning.get('type', '')}"
            if service:
                prefix = f"{prefix} {service}"
            print(f"  {prefix}: {warning.get('message', '')}")
            if warning.get("bind_address") or warning.get("port"):
                print(f"    bind: {warning.get('bind_address', '')}:{warning.get('port', '')}")
            if warning.get("suggested_action"):
                print(f"    suggested_action: {warning.get('suggested_action', '')}")
            if warning.get("error"):
                print(f"    error: {warning.get('error', '')}")
            for owner in warning.get("owners") or []:
                print(f"    owner_pid={owner.get('pid', '')} process={owner.get('process_name', '')} exe={owner.get('exe', '')} cmdline={owner.get('cmdline', '')}")
            for pid in warning.get("listener_pids") or []:
                print(f"    listener_pid={pid}")
    else:
        print("  none")


def _print_snapshot_staged_files(cfg, snap):
    print("Staged files:")
    if snap["staged"]:
        for name in sorted(snap["staged"]):
            rec = snap["staged"][name]
            sha = str(rec.get("sha256", ""))[:12]
            print(f"  {name} kind={rec.get('stage_kind', 'file')} <- {rec.get('source_path', '')} size={rec.get('size', '')} sha256={sha} staged={rec.get('staged_at', '')}")
            if rec.get("release_path") or rec.get("tuple_path"):
                print(f"    release: {rec.get('release_path', '')} tuple={rec.get('tuple_path', '')} preset={rec.get('payload_preset', '')}")
            if rec.get("target_id"):
                print(f"    target: {rec.get('target_id', '')} label={rec.get('target_label', '')}")
            print(f"    {rec.get('fetch_command') or render_fetch_command(name, cfg)}")
    else:
        print("  none")


def print_status_document(doc, json_output=False):
    if json_output:
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    _print_status_header(doc)
    print("")
    print_activity_summary(doc.get("summary") or {})
    print_warning_summary(doc.get("summary") or {})
    print_api_resource_summary(doc)
    print("")
    _print_path_health(doc)
    print("")
    print_operator_state_records(doc)
    print("")
    print_target_summary(doc)
    print("")
    _print_service_rows(doc)
    _print_status_warnings(doc)
    print("")
    print_recent_sessions(doc["sessions"])
    print("")
    print_recent_uploads(doc["uploads"], include_stored_exists=True)
    print("")
    print_recent_fetches(doc["fetches"], include_source_exists=True)
    print("")
    status_print_workflows.print_generated_target_commands(doc)
    print("")
    status_print_workflows.print_operator_workflow_actions(doc)
    status_print_workflows.print_target_workflow_actions(doc)
    status_print_workflows.print_workbench_jobs(doc)
    print("")
    print_workbench_command_queue_summary(doc["command_queue"], include_polling=True)
    print("")
    print_workbench_phone_home_attempts(doc, limit=8, include_work_details=True)
    print("")
    print_event_log_summary(doc)
    print_release_browser(doc)
    return 0


def print_workbench_snapshot(cfg, snap, include_api_summary=True):
    _print_snapshot_header(cfg, snap, include_api_summary)
    print("")
    _print_snapshot_operator_paths(cfg, snap)
    print("")
    _print_snapshot_path_health(snap)
    print("")
    print_operator_state_records(snap)
    print("")
    print_target_summary(snap)
    print("")
    _print_snapshot_local_ip_candidates(snap)
    print("")
    _print_snapshot_services(snap)
    print("")
    _print_snapshot_warnings(snap)
    print("")
    _print_snapshot_staged_files(cfg, snap)
    print("")
    print_recent_uploads(recent_upload_metadata(cfg), title="Received uploads:")
    print("")
    print_recent_fetches(snap.get("fetches") or [])
    print("")
    print_recent_sessions(snap["sessions"], updated_on_header=True)
    print("")
    status_print_workflows.print_generated_target_commands(snap)
    print("")
    status_print_workflows.print_snapshot_workflow_actions(snap)
    status_print_workflows.print_snapshot_target_workflow_actions(snap)
    status_print_workflows.print_snapshot_workbench_jobs(snap)
    print("")
    print_workbench_command_queue_summary(snap["command_queue"])
    print("")
    print_workbench_phone_home_attempts(snap)
    print("")
    print_event_log_summary(snap)
    print_snapshot_release_browser(cfg, snap)
