"""Mailbox timing helpers shared by target record/activity code."""

from gritlib.session_state import parse_utc_timestamp


def mailbox_wait_bucket(seconds):
    if seconds in ("", None):
        return ""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return ""
    if value < 60:
        return "under-minute"
    if value < 3600:
        return "under-hour"
    if value < 86400:
        return "under-day"
    return "day-plus"


def mailbox_elapsed_seconds(start, end):
    start_epoch = parse_utc_timestamp(str(start or ""))
    end_epoch = parse_utc_timestamp(str(end or ""))
    if start_epoch is None or end_epoch is None:
        return ""
    return max(int(end_epoch - start_epoch), 0)
