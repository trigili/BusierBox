"""Line-console show/module argument parsing helpers."""

import shlex


VERBOSE_FLAGS = {"-v", "--verbose", "verbose", "details"}


def split_line_verbose_args(args):
    parts = list(args or [])
    verbose = any(str(part).lower() in VERBOSE_FLAGS for part in parts)
    filtered_parts = [
        part for part in parts
        if str(part).lower() not in VERBOSE_FLAGS
    ]
    return verbose, filtered_parts


def parse_line_show_resource(resource):
    parts = shlex.split(str(resource or "").strip()) if str(resource or "").strip() else []
    verbose, filtered_parts = split_line_verbose_args(parts)
    key = (filtered_parts[0] if filtered_parts else "").lower()
    filter_text = " ".join(filtered_parts[1:]).strip()
    return {
        "key": key,
        "filtered_key": key,
        "filtered_parts": filtered_parts,
        "filter_text": filter_text,
        "verbose": verbose,
    }
