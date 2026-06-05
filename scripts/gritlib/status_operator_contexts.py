"""Operator state and path status contexts for grit-console status documents."""

from gritlib.build_config import build_config_path
import gritlib.command_copy as command_copy_module
import gritlib.command_queue as command_queue_module
import gritlib.session_state as session_state_module
import gritlib.staged_files as staged_files
import gritlib.status_indexes as status_indexes
import gritlib.target_records as target_records
from gritlib.workbench_jobs import workbench_jobs_path, workbench_jobs_state_status


BROWSER_PATH_INDEX_KEYS = (
    "browser_paths_by_kind",
    "browser_paths_by_path",
    "browser_paths_by_source_id",
    "browser_paths_by_stage_kind",
    "browser_paths_by_release_path",
    "browser_paths_by_kind_source_id",
    "browser_paths_by_exists",
    "browser_paths_by_readable",
    "browser_paths_by_writable",
    "browser_paths_by_expected_kind_mismatch",
)

def _build_path_browser_status_context(
    cfg,
    paths,
    *,
    staged_records,
    uploads,
    fetches,
    sessions,
    release,
):
    path_context = status_indexes.path_status_context(
        cfg,
        paths,
        staged_records,
        uploads,
        fetches,
        sessions,
        release,
    )
    return {
        "path_context": path_context,
        "path_status": path_context["path_status"],
        "path_status_records": path_context["path_status_records"],
        "path_status_indexes": path_context["path_status_index_maps"],
        "browser_paths": path_context["browser_paths"],
        "browser_path_index_maps": dict(zip(
            BROWSER_PATH_INDEX_KEYS,
            path_context["browser_path_indexes"],
        )),
        "browser_summary": path_context["browser_summary"],
    }

def _build_operator_state_status_context(
    cfg,
    *,
    event_log_state,
    session_root_state,
):
    server_status = session_state_module.server_state_status(cfg)
    server_state = server_status["state_record"]
    server_state_records = server_status["state_records"]
    staged_files_status = staged_files.staged_files_state_status(cfg)
    staged_files_state = staged_files_status["state_record"]
    staged_files_state_records = staged_files_status["state_records"]
    command_queue_status = command_queue_module.command_queue_state_status(cfg)
    command_queue_state = command_queue_status["state_record"]
    command_queue_state_records = command_queue_status["state_records"]
    command_copy = command_copy_module.command_copy_record(cfg)
    command_copy_state = command_copy_module.command_copy_state_status(command_copy)
    workbench_jobs_status = workbench_jobs_state_status(cfg)
    workbench_jobs_state = workbench_jobs_status["state_record"]
    workbench_jobs_state_records = workbench_jobs_status["state_records"]
    operator_state_context = status_indexes.operator_state_status_context(
        cfg,
        server_state,
        staged_files_state,
        command_queue_state,
        command_copy,
        workbench_jobs_state,
        event_log_state,
        session_root_state,
    )
    operator_state_file_summary_doc = status_indexes.operator_state_file_summary(
        server_state,
        server_state_records,
        staged_files_state,
        staged_files_state_records,
        command_queue_state,
        command_queue_state_records,
        command_copy,
        command_copy_state["state_record"],
        command_copy_state["state_records"],
        workbench_jobs_state,
        workbench_jobs_state_records,
    )
    return {
        "server_state": server_state,
        "server_state_records": server_state_records,
        "server_state_index_maps": server_status["state_index_maps"],
        "staged_files_state": staged_files_state,
        "staged_files_state_records": staged_files_state_records,
        "staged_files_state_index_maps": staged_files_status["state_index_maps"],
        "command_queue_state": command_queue_state,
        "command_queue_state_records": command_queue_state_records,
        "command_queue_state_index_maps": command_queue_status["state_index_maps"],
        "command_copy": command_copy,
        "command_copy_records": [command_copy],
        "command_copy_record_indexes": command_copy_module.command_copy_indexes(
            [command_copy]
        ),
        "command_copy_state_record": command_copy_state["state_record"],
        "command_copy_state_records": command_copy_state["state_records"],
        "command_copy_state_index_maps": command_copy_state["state_index_maps"],
        "workbench_jobs_state": workbench_jobs_state,
        "workbench_jobs_state_records": workbench_jobs_state_records,
        "workbench_jobs_state_index_maps": workbench_jobs_status["state_index_maps"],
        "operator_state_records_list": operator_state_context["records"],
        "operator_state_index_maps": operator_state_context["index_maps"],
        "operator_state_summary": operator_state_context["summary"],
        "operator_state_file_summary_doc": operator_state_file_summary_doc,
    }

def _status_tail_paths(cfg, foundation_context):
    f = foundation_context
    return {
        "operator_session_dir": str(f["operator_dir"]),
        "state_file": str(session_state_module.state_file_path(cfg)),
        "staged_files": str(staged_files.staged_file_path(cfg)),
        "command_queue_file": str(command_queue_module.command_queue_path(cfg)),
        "command_copy_file": str(command_copy_module.command_copy_path(cfg)),
        "workbench_jobs_file": str(workbench_jobs_path(cfg)),
        "targets_file": str(target_records.targets_path(cfg)),
        "build_config": str(build_config_path(cfg)),
        "event_log": str(f["event_log_path"]),
        "session_root": f["session_root"],
        "tls_cert": str(cfg.get("tls_cert", "")),
        "tls_key": str(cfg.get("tls_key", "")),
    }


def build_path_browser_status_context(*args, **kwargs):
    return _build_path_browser_status_context(*args, **kwargs)


def build_operator_state_status_context(*args, **kwargs):
    return _build_operator_state_status_context(*args, **kwargs)


def status_tail_paths(*args, **kwargs):
    return _status_tail_paths(*args, **kwargs)
