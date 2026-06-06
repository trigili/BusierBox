"""Target file-transfer record, index, and summary helpers."""

from pathlib import Path

from gritlib.record_utils import latest_record_value, record_count_by_key, records_by_key


def _target_file_transfer_staged_record(rec, fallback_index):
    request_name = str(rec.get("request_name") or rec.get("name") or "")
    timestamp = str(rec.get("staged_at") or rec.get("created_at") or rec.get("updated_at") or "")
    source_path = str(rec.get("source_path") or "")
    sha256_value = str(rec.get("sha256") or "")
    return {
        "id": f"staged:{request_name}" if request_name else f"staged:{fallback_index}",
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
    }


def _target_file_transfer_upload_record(rec, fallback_index):
    metadata_path = str(rec.get("metadata_path") or rec.get("_metadata_path") or "")
    timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
    sha256_value = str(rec.get("sha256") or "")
    return {
        "id": f"upload:{metadata_path}" if metadata_path else f"upload:{fallback_index}",
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
    }


def _target_file_transfer_fetch_record(rec, fallback_index):
    metadata_path = str(rec.get("metadata_path") or "")
    request_name = str(rec.get("request_name") or "")
    timestamp = str(rec.get("timestamp") or rec.get("updated_at") or rec.get("created_at") or "")
    source_path = str(rec.get("source_path") or "")
    sha256_value = str(rec.get("sha256") or "")
    return {
        "id": f"fetch:{metadata_path}:{request_name}:{timestamp}" if metadata_path or request_name or timestamp else f"fetch:{fallback_index}",
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
    }


def _append_target_file_transfer_records(records, source_records, build_record):
    for rec in source_records or []:
        if not isinstance(rec, dict):
            continue
        records.append(build_record(rec, len(records)))


def target_file_transfer_records_from_sources(staged_records, uploads, fetches):
    records = []
    _append_target_file_transfer_records(
        records, staged_records, _target_file_transfer_staged_record
    )
    _append_target_file_transfer_records(
        records, uploads, _target_file_transfer_upload_record
    )
    _append_target_file_transfer_records(
        records, fetches, _target_file_transfer_fetch_record
    )
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


def target_file_transfer_status_context(staged_records=None, uploads=None, fetches=None):
    records = target_file_transfer_records_from_sources(staged_records, uploads, fetches)
    return {
        "records": records,
        "index_maps": target_file_transfer_record_indexes(records),
    }


def target_file_transfer_record_summary(records):
    records = records or []
    return {
        "target_file_transfer_record_count": len(records),
        "target_file_transfer_operation_counts": record_count_by_key(records, "operation"),
        "target_file_transfer_source_collection_counts": record_count_by_key(records, "source_collection"),
        "target_file_transfer_status_counts": record_count_by_key(records, "status"),
        "target_file_transfer_target_counts": record_count_by_key(records, "target_id"),
        "target_file_transfer_route_kind_counts": record_count_by_key(records, "route_kind"),
        "target_file_transfer_bridge_profile_counts": record_count_by_key(records, "bridge_profile"),
        "latest_target_file_transfer_at": latest_record_value(records, ("timestamp", "updated_at", "created_at")),
    }
