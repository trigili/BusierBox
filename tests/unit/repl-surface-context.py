#!/usr/bin/env python3
"""Regression tests for line REPL context command routing."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gritlib.line_repl_runtime import contextual_line_command  # noqa: E402
from gritlib.line_show import parse_line_show_resource  # noqa: E402


def expect_case(cmd, args, module, expected):
    actual = contextual_line_command(cmd, args, module=module)
    if actual != expected:
        print(
            f"contextual_line_command({cmd!r}, {args!r}, module={module!r}) "
            f"returned {actual!r}, expected {expected!r}",
            file=sys.stderr,
        )
        return False
    return True


def expect_show_resource(resource, expected):
    actual = parse_line_show_resource(resource)
    subset = {key: actual[key] for key in expected}
    if subset != expected:
        print(
            f"parse_line_show_resource({resource!r}) returned {subset!r}, "
            f"expected {expected!r}",
            file=sys.stderr,
        )
        return False
    return True


def main():
    cases = [
        # Plain listener context must not steal global service-control commands.
        ("start", ["1"], "listener", ("start", ["1"])),
        ("stop", ["1"], "listener", ("stop", ["1"])),
        ("show", ["routes", "-v"], "listener", ("show", ["routes", "-v"])),
        ("route", ["start", "1"], "listener", ("route", ["start", "1"])),
        # Probe workflow shorthands are only contextual inside listener/probe.
        ("start", [], "listener/probe", ("listener", ["probe", "start"])),
        ("queue", [], "listener/probe", ("listener", ["probe", "queue"])),
        ("delivery", [], "listener/probe", ("listener", ["probe", "delivery"])),
        ("probe", ["queue"], "listener/probe", ("listener", ["probe", "queue"])),
        # Non-probe global commands remain available even inside listener/probe.
        ("retrieve", ["queue", "/etc/config/network"], "listener/probe", ("retrieve", ["queue", "/etc/config/network"])),
    ]
    ok = True
    for cmd, args, module, expected in cases:
        ok = expect_case(cmd, args, module, expected) and ok
    show_cases = [
        ("", {"kind": "", "kind_filter": "", "filter_text": ""}),
        ("service modules", {"kind": "module-kind", "kind_filter": "service", "filter_text": ""}),
        ("modules service", {"kind": "module-kind", "kind_filter": "service", "filter_text": ""}),
        ("modules daemon", {"kind": "module-kind", "kind_filter": "daemon", "filter_text": ""}),
        ("modules daemon status", {"kind": "module-kind", "kind_filter": "daemon", "filter_text": "status"}),
        ("modules file-service", {"kind": "modules", "kind_filter": "", "filter_text": "file-service"}),
    ]
    for resource, expected in show_cases:
        ok = expect_show_resource(resource, expected) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
