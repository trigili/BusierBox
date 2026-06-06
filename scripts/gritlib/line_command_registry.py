"""Shared command registry helpers for line-console domain parsers."""


def line_command_records(family, specs):
    records = []
    for spec in specs or ():
        commands = tuple(str(item).strip().lower() for item in spec.get("commands") or ())
        commands = tuple(item for item in commands if item)
        if not commands:
            continue
        rec = {
            "family": str(family or ""),
            "action": spec.get("action", ""),
            "commands": list(commands),
            "primary": commands[0],
            "aliases": list(commands[1:]),
        }
        for key, value in spec.items():
            if key in {"action", "commands"}:
                continue
            rec[key] = value
        records.append(rec)
    return records


def matching_line_command_records(cmd, records):
    command = str(cmd or "").strip().lower()
    if not command:
        return []
    return [
        rec for rec in list(records or [])
        if command in set(rec.get("commands") or ())
    ]


def first_matching_line_command_record(cmd, records):
    matches = matching_line_command_records(cmd, records)
    return matches[0] if matches else {}
