"""Target attribution status helpers for grit-console."""

from gritlib.record_utils import (
    count_records_with_key, record_count_by_key, records_by_key,
)


def target_attribution_record_indexes(records):
    return {
        "target_attribution_records_by_scope": {
            rec["scope"]: rec for rec in records
        },
        "target_attribution_records_by_has_targeted_activity": records_by_key(
            records, "has_targeted_activity"
        ),
        "target_attribution_records_by_has_legacy_activity": records_by_key(
            records, "has_legacy_activity"
        ),
        "target_attribution_records_by_legacy_single_target_activity_present": records_by_key(
            records, "legacy_single_target_activity_present"
        ),
        "target_attribution_records_by_all_activity_has_target_id": records_by_key(
            records, "all_activity_has_target_id"
        ),
        "target_attribution_records_by_no_activity": records_by_key(
            records, "no_activity"
        ),
    }


def target_attribution_record_summary(records, attribution=None):
    records = records or []
    attribution = attribution or {}
    return {
        "target_attribution_record_count": len(records),
        "target_attribution_scope_counts": record_count_by_key(records, "scope"),
        "target_attribution_legacy_scope_count": len([
            rec for rec in records if rec.get("has_legacy_activity")
        ]),
        "target_attribution_targeted_scope_count": len([
            rec for rec in records if rec.get("has_targeted_activity")
        ]),
        "target_attribution_with_target_count": attribution.get("with_target_count", 0),
        "target_attribution_without_target_count": attribution.get(
            "without_target_count", 0
        ),
        "target_legacy_single_target_activity_present": attribution.get(
            "legacy_single_target_activity_present", False
        ),
    }


def target_attribution_status(uploads=None, fetches=None, sessions=None):
    uploads = uploads or []
    fetches = fetches or []
    sessions = sessions or []
    upload_with_target_count = count_records_with_key(uploads, "target_id")
    fetch_with_target_count = count_records_with_key(fetches, "target_id")
    session_with_target_count = count_records_with_key(sessions, "target_id")
    attribution = {
        "upload_with_target_count": upload_with_target_count,
        "upload_without_target_count": max(len(uploads) - upload_with_target_count, 0),
        "fetch_with_target_count": fetch_with_target_count,
        "fetch_without_target_count": max(len(fetches) - fetch_with_target_count, 0),
        "session_with_target_count": session_with_target_count,
        "session_without_target_count": max(
            len(sessions) - session_with_target_count, 0
        ),
    }
    attribution["with_target_count"] = (
        attribution["upload_with_target_count"] +
        attribution["fetch_with_target_count"] +
        attribution["session_with_target_count"]
    )
    attribution["without_target_count"] = (
        attribution["upload_without_target_count"] +
        attribution["fetch_without_target_count"] +
        attribution["session_without_target_count"]
    )
    attribution["legacy_single_target_activity_present"] = (
        attribution["without_target_count"] > 0
    )
    records = []
    for scope, with_count, without_count in (
        (
            "uploads",
            attribution["upload_with_target_count"],
            attribution["upload_without_target_count"],
        ),
        (
            "fetches",
            attribution["fetch_with_target_count"],
            attribution["fetch_without_target_count"],
        ),
        (
            "sessions",
            attribution["session_with_target_count"],
            attribution["session_without_target_count"],
        ),
        (
            "all",
            attribution["with_target_count"],
            attribution["without_target_count"],
        ),
    ):
        total = with_count + without_count
        records.append({
            "scope": scope,
            "with_target_count": with_count,
            "without_target_count": without_count,
            "total_count": total,
            "has_targeted_activity": with_count > 0,
            "has_legacy_activity": without_count > 0,
            "legacy_single_target_activity_present": without_count > 0,
            "all_activity_has_target_id": total > 0 and without_count == 0,
            "no_activity": total == 0,
        })
    return {
        "target_attribution": attribution,
        "target_attribution_records": records,
        "target_attribution_index_maps": target_attribution_record_indexes(records),
    }
