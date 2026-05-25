#!/usr/bin/env python3
import json
import sys

if len(sys.argv) != 2:
    print("usage: validate-survey-json.py survey.json", file=sys.stderr)
    raise SystemExit(2)

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

required = ["arch", "kernel", "writable_dirs", "recommendations"]
missing = [key for key in required if key not in data]
if missing:
    print("missing keys: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)

if not isinstance(data["writable_dirs"], list):
    print("writable_dirs must be a list", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(data["recommendations"], dict):
    print("recommendations must be an object", file=sys.stderr)
    raise SystemExit(1)

recommendation_keys = [
    "target_arch_guess",
    "endian_guess",
    "kernel_floor_guess",
    "libc_guess",
    "payload_preset_recommendation",
    "runtime_mode_recommendation",
    "runtime_root_recommendation",
    "external_writes_recommendation",
    "rshell_transport_recommendation",
    "warnings",
]
missing_recs = [key for key in recommendation_keys if key not in data["recommendations"]]
if missing_recs:
    print("missing recommendation keys: " + ", ".join(missing_recs), file=sys.stderr)
    raise SystemExit(1)

print("survey json ok")
