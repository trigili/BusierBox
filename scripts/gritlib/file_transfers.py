"""File-transfer record and index helpers for grit-console."""

from pathlib import Path

from gritlib.record_utils import records_by_bool, records_by_key


def upload_record_indexes(records):
    by_filename = {}
    by_kind = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_stored_path = {}
    by_stored_exists = records_by_bool(records, "stored_exists")
    by_metadata_exists = records_by_bool(records, "metadata_exists")
    by_event_log_exists = records_by_bool(records, "event_log_exists")
    by_remote_addr = {}
    by_status = {}
    by_kind_status = {}
    by_filename_status = {}
    by_status_stored_exists = {}
    by_status_remote_addr = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        filename = str(rec.get("filename") or "")
        kind = str(rec.get("upload_kind") or "file")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        stored_path = str(rec.get("stored_path") or "")
        remote_addr = str(rec.get("remote_addr") or "")
        status = str(rec.get("status") or "")
        if filename:
            by_filename.setdefault(filename, []).append(rec)
        if kind:
            by_kind.setdefault(kind, []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path.setdefault(source_path, []).append(rec)
        if stored_path:
            by_stored_path[stored_path] = rec
        if remote_addr:
            by_remote_addr.setdefault(remote_addr, []).append(rec)
        if status:
            by_status.setdefault(status, []).append(rec)
        if kind and status:
            by_kind_status.setdefault(f"{kind}:{status}", []).append(rec)
        if filename and status:
            by_filename_status.setdefault(f"{filename}:{status}", []).append(rec)
        if status:
            stored_exists = "yes" if rec.get("stored_exists") is True else "no"
            by_status_stored_exists.setdefault(f"{status}:{stored_exists}", []).append(rec)
        if status and remote_addr:
            by_status_remote_addr.setdefault(f"{status}:{remote_addr}", []).append(rec)
    return (
        by_filename,
        by_kind,
        by_sha256,
        by_target_id,
        by_source_path,
        by_stored_path,
        by_stored_exists,
        by_metadata_exists,
        by_event_log_exists,
        by_remote_addr,
        by_status,
        by_kind_status,
        by_filename_status,
        by_status_stored_exists,
        by_status_remote_addr,
    )


def fetch_record_indexes(records):
    by_request = {}
    by_sha256 = {}
    by_target_id = {}
    by_source_path = {}
    by_source_exists = records_by_bool(records, "source_exists")
    by_metadata_exists = records_by_bool(records, "metadata_exists")
    by_event_log_exists = records_by_bool(records, "event_log_exists")
    by_status = {}
    by_http_status = {}
    by_remote_addr = {}
    by_request_status = {}
    by_status_source_exists = {}
    by_status_remote_addr = {}
    by_http_status_remote_addr = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or "")
        sha256 = str(rec.get("sha256") or "")
        target_id = str(rec.get("target_id") or "")
        source_path = str(rec.get("source_path") or "")
        status = str(rec.get("status") or "")
        http_status = rec.get("http_status")
        remote_addr = str(rec.get("remote_addr") or "")
        if request_name:
            by_request.setdefault(request_name, []).append(rec)
        if sha256:
            by_sha256.setdefault(sha256, []).append(rec)
        if target_id:
            by_target_id.setdefault(target_id, []).append(rec)
        if source_path:
            by_source_path.setdefault(source_path, []).append(rec)
        if status:
            by_status.setdefault(status, []).append(rec)
        if http_status not in (None, ""):
            by_http_status.setdefault(str(http_status), []).append(rec)
        if remote_addr:
            by_remote_addr.setdefault(remote_addr, []).append(rec)
        if request_name and status:
            by_request_status.setdefault(f"{request_name}:{status}", []).append(rec)
        if status:
            source_exists = "yes" if rec.get("source_exists") is True else "no"
            by_status_source_exists.setdefault(f"{status}:{source_exists}", []).append(rec)
        if status and remote_addr:
            by_status_remote_addr.setdefault(f"{status}:{remote_addr}", []).append(rec)
        if http_status not in (None, "") and remote_addr:
            by_http_status_remote_addr.setdefault(f"{http_status}:{remote_addr}", []).append(rec)
    return (
        by_request,
        by_sha256,
        by_target_id,
        by_source_path,
        by_source_exists,
        by_metadata_exists,
        by_event_log_exists,
        by_status,
        by_http_status,
        by_remote_addr,
        by_request_status,
        by_status_source_exists,
        by_status_remote_addr,
        by_http_status_remote_addr,
    )


def target_file_transfer_records_from_sources(staged_records, uploads, fetches):
    records = []
    for rec in staged_records or []:
        if not isinstance(rec, dict):
            continue
        request_name = str(rec.get("request_name") or rec.get("name") or "")
        timestamp = str(rec.get("staged_at") or rec.get("created_at") or rec.get("updated_at") or "")
        source_path = str(rec.get("source_path") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"staged:{request_name}" if request_name else f"staged:{len(records)}",
            "operation": "staged-fetch",
            "source_collection": "staged_records",
            "status": "available" if rec.get("source_exists") is True else "source-missing",
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or rec.get("staged_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": request_name,
            "name": str(rec.get("name") or request_name),
            "filename": Path(source_path or request_name).name if (source_path or request_name) else "",
            "stage_kind": str(rec.get("stage_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": source_path,
            "stored_path": "",
            "metadata_path": "",
            "session_id": "",
            "session_path": "",
            "remote_addr": "",
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": rec.get("source_exists") is True,
            "stored_exists": False,
            "fetch_command": str(rec.get("fetch_command") or ""),
            "fetch_command_force": str(rec.get("fetch_command_force") or ""),
        })
    for rec in uploads or []:
        if not isinstance(rec, dict):
            continue
        metadata_path = str(rec.get("metadata_path") or rec.get("_metadata_path") or "")
        timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"upload:{metadata_path}" if metadata_path else f"upload:{len(records)}",
            "operation": "upload",
            "source_collection": "uploads",
            "status": str(rec.get("status") or rec.get("transfer_status") or ""),
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": str(rec.get("request_name") or ""),
            "name": str(rec.get("filename") or ""),
            "filename": str(rec.get("filename") or ""),
            "stage_kind": str(rec.get("upload_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": str(rec.get("source_path") or ""),
            "stored_path": str(rec.get("stored_path") or ""),
            "metadata_path": metadata_path,
            "session_id": str(rec.get("session_id") or ""),
            "session_path": str(rec.get("session_path") or ""),
            "remote_addr": str(rec.get("remote_addr") or ""),
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": False,
            "stored_exists": rec.get("stored_exists") is True,
            "fetch_command": "",
            "fetch_command_force": "",
        })
    for rec in fetches or []:
        if not isinstance(rec, dict):
            continue
        metadata_path = str(rec.get("metadata_path") or "")
        request_name = str(rec.get("request_name") or "")
        timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
        source_path = str(rec.get("source_path") or "")
        sha256_value = str(rec.get("sha256") or "")
        records.append({
            "id": f"fetch:{metadata_path}:{request_name}:{timestamp}" if metadata_path or request_name or timestamp else f"fetch:{len(records)}",
            "operation": "fetch",
            "source_collection": "fetches",
            "status": str(rec.get("status") or ""),
            "http_status": rec.get("http_status", ""),
            "timestamp": timestamp,
            "created_at": str(rec.get("created_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
            "request_name": request_name,
            "name": request_name,
            "filename": Path(source_path or request_name).name if (source_path or request_name) else "",
            "stage_kind": str(rec.get("stage_kind") or "file"),
            "target_id": str(rec.get("target_id") or ""),
            "target_label": str(rec.get("target_label") or ""),
            "source_path": source_path,
            "stored_path": "",
            "metadata_path": metadata_path,
            "session_id": str(rec.get("session_id") or ""),
            "session_path": str(rec.get("session_path") or ""),
            "remote_addr": str(rec.get("remote_addr") or ""),
            "sha256": sha256_value,
            "sha256_prefix": sha256_value[:12],
            "size": rec.get("size", 0),
            "route_kind": str(rec.get("route_kind") or "direct"),
            "bridge_profile": str(rec.get("bridge_profile") or ""),
            "bridge_route_path": str(rec.get("bridge_route_path") or ""),
            "source_exists": rec.get("source_exists") is True,
            "stored_exists": False,
            "fetch_command": "",
            "fetch_command_force": "",
        })
    records.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("id") or "")), reverse=True)
    return records


def target_file_transfer_record_indexes(records):
    return {
        "target_file_transfer_records_by_id": {rec.get("id", ""): rec for rec in records or [] if isinstance(rec, dict) and rec.get("id")},
        "target_file_transfer_records_by_target_id": records_by_key(records, "target_id"),
        "target_file_transfer_records_by_target_label": records_by_key(records, "target_label"),
        "target_file_transfer_records_by_operation": records_by_key(records, "operation"),
        "target_file_transfer_records_by_source_collection": records_by_key(records, "source_collection"),
        "target_file_transfer_records_by_status": records_by_key(records, "status"),
        "target_file_transfer_records_by_route_kind": records_by_key(records, "route_kind"),
        "target_file_transfer_records_by_bridge_profile": records_by_key(records, "bridge_profile"),
        "target_file_transfer_records_by_request_name": records_by_key(records, "request_name"),
        "target_file_transfer_records_by_filename": records_by_key(records, "filename"),
        "target_file_transfer_records_by_sha256": records_by_key(records, "sha256"),
        "target_file_transfer_records_by_session_id": records_by_key(records, "session_id"),
    }
