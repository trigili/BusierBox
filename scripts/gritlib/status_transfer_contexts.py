"""Transfer and target-activity status contexts for grit-console status documents."""

import gritlib.file_service_workflow_actions as file_service_workflow_actions_module
import gritlib.file_transfers as file_transfers
import gritlib.target_file_transfer_records as target_file_transfer_records_module
import gritlib.target_activity_feed as target_activity_feed
import gritlib.target_records as target_records


UPLOAD_INDEX_KEYS = (
    "uploads_by_filename",
    "uploads_by_kind",
    "uploads_by_sha256",
    "uploads_by_target_id",
    "uploads_by_source_path",
    "uploads_by_stored_path",
    "uploads_by_stored_exists",
    "uploads_by_metadata_exists",
    "uploads_by_event_log_exists",
    "uploads_by_remote_addr",
    "uploads_by_status",
    "uploads_by_kind_status",
    "uploads_by_filename_status",
    "uploads_by_status_stored_exists",
    "uploads_by_status_remote_addr",
)

FETCH_INDEX_KEYS = (
    "fetches_by_request",
    "fetches_by_sha256",
    "fetches_by_target_id",
    "fetches_by_source_path",
    "fetches_by_source_exists",
    "fetches_by_metadata_exists",
    "fetches_by_event_log_exists",
    "fetches_by_status",
    "fetches_by_http_status",
    "fetches_by_remote_addr",
    "fetches_by_request_status",
    "fetches_by_status_source_exists",
    "fetches_by_status_remote_addr",
    "fetches_by_http_status_remote_addr",
)

def _build_target_activity_feed_status_context(
    targets,
    target_mailbox_records,
    target_phone_home_records,
    target_file_transfer_records,
    bridge_profiles,
    sessions,
):
    target_activity_feed_context = (
        target_activity_feed.target_activity_feed_status_context(
            targets,
            target_mailbox_records,
            target_phone_home_records,
            target_file_transfer_records,
            bridge_profiles,
            sessions,
        )
    )
    target_activity_records = target_activity_feed_context["records"]
    return {
        "target_activity_feed_context": target_activity_feed_context,
        "target_activity_records": target_activity_records,
        "target_activity_index_maps": target_activity_feed_context["index_maps"],
        "summary": target_activity_feed.target_activity_record_summary(
            target_activity_records
        ),
    }

def _build_target_attribution_status_context(uploads, fetches, sessions):
    target_attribution_status_doc = target_records.target_attribution_status(
        uploads,
        fetches,
        sessions,
    )
    target_attribution = target_attribution_status_doc["target_attribution"]
    target_attribution_records = target_attribution_status_doc[
        "target_attribution_records"
    ]
    return {
        "target_attribution_status_doc": target_attribution_status_doc,
        "target_attribution": target_attribution,
        "target_attribution_records": target_attribution_records,
        "target_attribution_index_maps": target_attribution_status_doc[
            "target_attribution_index_maps"
        ],
        "summary": target_records.target_attribution_record_summary(
            target_attribution_records,
            target_attribution,
        ),
    }

def _build_file_transfer_status_context(staged_records, uploads, fetches):
    file_transfer_context = file_transfers.file_transfer_status_context(
        uploads, fetches
    )
    target_file_transfer_context = target_file_transfer_records_module.target_file_transfer_status_context(
        staged_records,
        uploads,
        fetches,
    )
    return {
        "upload_index_maps": dict(zip(
            UPLOAD_INDEX_KEYS,
            file_transfer_context["upload_indexes"],
        )),
        "fetch_index_maps": dict(zip(
            FETCH_INDEX_KEYS,
            file_transfer_context["fetch_indexes"],
        )),
        "target_file_transfer_records": target_file_transfer_context["records"],
        "target_file_transfer_index_maps": target_file_transfer_context["index_maps"],
    }

def _build_file_service_workflow_status_context(
    cfg,
    services,
    staged_records,
    uploads,
    fetches,
    target_file_transfer_records,
    targets,
):
    file_service_row = next(
        (row for row in services if row.get("name") == "file-service"), {}
    )
    file_service_workflow_context = (
        file_service_workflow_actions_module.file_service_workflow_status_context(
            cfg,
            file_service_row,
            staged_records,
            uploads,
            fetches,
            target_file_transfer_records,
            targets,
            render_file_service_command_func=file_transfers.render_file_service_command,
        )
    )
    file_service_workflow_actions = file_service_workflow_context["actions"]
    return {
        "file_service_row": file_service_row,
        "file_service_workflow_context": file_service_workflow_context,
        "file_service_workflow_actions": file_service_workflow_actions,
        "file_service_workflow_action_index_maps": file_service_workflow_context[
            "index_maps"
        ],
        "summary": file_service_workflow_actions_module.file_service_workflow_status_summary(
            file_service_workflow_actions
        ),
    }

def _status_transfer_file_fields(file_transfer_context):
    return {
        "file_transfer_context": file_transfer_context,
        "upload_index_maps": file_transfer_context["upload_index_maps"],
        "fetch_index_maps": file_transfer_context["fetch_index_maps"],
        "target_file_transfer_records": file_transfer_context[
            "target_file_transfer_records"
        ],
        "target_file_transfer_index_maps": file_transfer_context[
            "target_file_transfer_index_maps"
        ],
    }

def _status_transfer_file_service_workflow_fields(file_service_workflow_context):
    return {
        "file_service_workflow_context": file_service_workflow_context,
        "file_service_row": file_service_workflow_context["file_service_row"],
        "file_service_workflow_actions": file_service_workflow_context[
            "file_service_workflow_actions"
        ],
        "file_service_workflow_action_index_maps": file_service_workflow_context[
            "file_service_workflow_action_index_maps"
        ],
    }

def _status_transfer_activity_feed_fields(target_activity_feed_context):
    return {
        "target_activity_feed_context": target_activity_feed_context,
        "target_activity_records": target_activity_feed_context[
            "target_activity_records"
        ],
        "target_activity_index_maps": target_activity_feed_context[
            "target_activity_index_maps"
        ],
    }

def _status_transfer_attribution_fields(target_attribution_context):
    return {
        "target_attribution_context": target_attribution_context,
        "target_attribution_status_doc": target_attribution_context[
            "target_attribution_status_doc"
        ],
        "target_attribution": target_attribution_context["target_attribution"],
        "target_attribution_records": target_attribution_context[
            "target_attribution_records"
        ],
        "target_attribution_index_maps": target_attribution_context[
            "target_attribution_index_maps"
        ],
    }

def _build_status_transfer_activity_context(
    cfg,
    *,
    foundation_context,
    activity_queue_context,
):
    f = foundation_context
    aq = activity_queue_context
    file_transfer_context = _build_file_transfer_status_context(
        f["staged_records"],
        f["uploads"],
        f["fetches"],
    )
    target_file_transfer_records = file_transfer_context[
        "target_file_transfer_records"
    ]
    file_service_workflow_context = _build_file_service_workflow_status_context(
        cfg,
        f["services"],
        f["staged_records"],
        f["uploads"],
        f["fetches"],
        target_file_transfer_records,
        f["targets"],
    )
    target_activity_feed_context = _build_target_activity_feed_status_context(
        f["targets"],
        aq["target_mailbox_records"],
        aq["target_phone_home_records"],
        target_file_transfer_records,
        aq["bridge_profiles"],
        aq["sessions"],
    )
    target_attribution_context = _build_target_attribution_status_context(
        f["uploads"],
        f["fetches"],
        aq["sessions"],
    )
    return {
        **_status_transfer_file_fields(file_transfer_context),
        **_status_transfer_file_service_workflow_fields(
            file_service_workflow_context
        ),
        **_status_transfer_activity_feed_fields(target_activity_feed_context),
        **_status_transfer_attribution_fields(target_attribution_context),
    }


def build_status_transfer_activity_context(*args, **kwargs):
    return _build_status_transfer_activity_context(*args, **kwargs)
