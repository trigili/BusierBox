"""Shared record/index helpers for grit-console and gritlib modules."""

def records_by_session(records):
    grouped = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        session_id = str(rec.get("session_id") or "")
        if not session_id:
            continue
        grouped.setdefault(session_id, []).append(rec)
    return grouped


def int_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def record_count_by_key(records, key):
    counts = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        value = rec.get(key)
        if value in (None, ""):
            continue
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return counts


def count_records_with_key(records, key):
    return len([
        rec for rec in records or []
        if isinstance(rec, dict) and rec.get(key) not in (None, "")
    ])


def records_by_key(records, key):
    grouped = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        value = rec.get(key)
        if value in (None, ""):
            continue
        grouped.setdefault(str(value), []).append(rec)
    return grouped


def records_by_composite(records, keys):
    grouped = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        parts = []
        missing = False
        for key in keys:
            value = rec.get(key)
            if value in (None, ""):
                missing = True
                break
            parts.append(str(value))
        if missing:
            continue
        grouped.setdefault(":".join(parts), []).append(rec)
    return grouped


def list_merge_unique(existing, values):
    out = [str(item) for item in (existing or []) if str(item)]
    seen = set(out)
    for value in values or []:
        value = str(value or "")
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def nested_index_key(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)



def records_by_nested_key(records, parent_key, child_key):
    grouped = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        parent = rec.get(parent_key)
        if not isinstance(parent, dict):
            continue
        value = parent.get(child_key)
        if value in (None, ""):
            continue
        grouped.setdefault(nested_index_key(value), []).append(rec)
    return grouped


def records_by_list_item(records, key):
    grouped = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        values = rec.get(key) or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            if value in (None, ""):
                continue
            grouped.setdefault(str(value), []).append(rec)
    return grouped


def latest_record_value(records, keys):
    latest = ""
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        for key in keys:
            value = str(rec.get(key) or "")
            if value:
                if value > latest:
                    latest = value
                break
    return latest


def record_bool_counts(records, key):
    true_count = 0
    false_count = 0
    for rec in records or []:
        if not isinstance(rec, dict) or key not in rec:
            continue
        if rec.get(key) is True:
            true_count += 1
        elif rec.get(key) is False:
            false_count += 1
    return true_count, false_count


def records_by_bool(records, key):
    grouped = {"yes": [], "no": []}
    for rec in records or []:
        if not isinstance(rec, dict) or key not in rec:
            continue
        grouped["yes" if rec.get(key) is True else "no"].append(rec)
    return grouped


def format_counts(counts, limit=6):
    if not counts:
        return "none"
    parts = []
    for key, value in sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))[:limit]:
        parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "none"

