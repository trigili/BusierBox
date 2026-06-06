"""Target activity human-output helpers for grit-console."""

from gritlib.console_display import console_table
from gritlib.record_utils import format_counts


def print_target_activity_records(doc, target_id=None, limit=8):
    records = list((doc or {}).get("target_activity_records") or [])
    if target_id:
        records = [
            rec for rec in records
            if str(rec.get("target_id") or "") == str(target_id)
        ]
    shown = records[:limit]

    def _label(rec):
        return (
            rec.get("summary") or rec.get("filename") or rec.get("request_name")
            or rec.get("command_id") or rec.get("session_id") or "-"
        )

    def _fmt_time(iso):
        if iso and len(iso) >= 16 and "T" in iso:
            date, rest = iso.split("T", 1)
            return f"{date[5:]} {rest[:5]}"
        return iso or "-"

    cols = [
        ("Target",    lambda r: r.get("target_id") or "-"),
        ("Category",  lambda r: r.get("category") or "-"),
        ("Operation", lambda r: r.get("operation") or "-"),
        ("Status",    lambda r: r.get("status") or "-"),
        ("Label",     _label),
        ("At",        lambda r: _fmt_time(r.get("timestamp"))),
    ]
    console_table(
        f"Activity  ({len(shown)} shown of {len(records)})" if records else "Activity  (none)",
        shown, cols,
    )


def print_workbench_phone_home_attempts(snap, limit=5, include_work_details=False):
    def _count_map(counts):
        if not isinstance(counts, dict):
            return {}
        out = {}
        for key, value in counts.items():
            out[key] = len(value) if isinstance(value, list) else value
        return out

    print("Target phone-home attempts:")
    phone_home = snap.get("target_phone_home_records") or []
    if not isinstance(phone_home, list):
        phone_home = []
    if phone_home:
        summary = snap.get("summary") if isinstance(snap.get("summary"), dict) else {}
        status_counts = snap.get("target_phone_home_records_by_status") or summary.get("target_phone_home_status_counts") or {}
        failed_counts = snap.get("target_phone_home_records_by_failed") or summary.get("target_phone_home_failed_counts") or {}
        print(f"  total={len(phone_home)} statuses={format_counts(_count_map(status_counts))} failed={format_counts(_count_map(failed_counts))}")
        for rec in phone_home[:limit]:
            if not isinstance(rec, dict):
                continue
            target = rec.get("target_id", "") or "anonymous"
            reason = rec.get("pending_reason") or rec.get("reason") or ""
            suffix = f" reason={reason}" if reason else ""
            command = f" command={rec.get('command_id', '')}" if rec.get("command_id") else ""
            work = f" work={rec.get('work_kind', '')}" if include_work_details and rec.get("work_kind") else ""
            route = f" route={rec.get('route_kind', '')}" if include_work_details and rec.get("route_kind") else ""
            bridge = f" bridge={rec.get('bridge_profile', '')}" if include_work_details and rec.get("bridge_profile") else ""
            target_state = f" target_state={rec.get('target_connectivity_state', '')}" if rec.get("target_connectivity_state") else ""
            offline_age = f" offline_age={rec.get('target_offline_age_bucket', '')}" if rec.get("target_offline_age_bucket") else ""
            remaining = (
                f" queued_remaining={rec.get('queued_remaining_count')}"
                if rec.get("queued_remaining_count") != "" else ""
            )
            print(f"  {rec.get('timestamp', '')} {rec.get('kind', '')} status={rec.get('status', '')} target={target} via={rec.get('contact_path', '')}{target_state}{offline_age}{command}{work}{route}{bridge}{remaining}{suffix}")
    else:
        print("  none")
