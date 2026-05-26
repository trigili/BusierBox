#!/bin/sh
set -eu

test -f LICENSE
grep -q 'GNU GENERAL PUBLIC LICENSE' LICENSE
grep -q 'Version 2, June 1991' LICENSE

grep -q 'GPL-2.0-or-later' README.md
grep -q 'docs/licensing.md' README.md
grep -q 'BusierBox is not a BusyBox replacement and is not a BusyBox fork' README.md

grep -q 'GPL-2.0-or-later' docs/licensing.md
grep -q 'BusyBox' docs/licensing.md
grep -q 'Buildroot' docs/licensing.md
grep -q 'doom-ascii' docs/licensing.md
grep -q 'miniz' docs/licensing.md

python3 - <<'PY'
import json

with open("manifests/sources.lock.json", encoding="utf-8") as fh:
    data = json.load(fh)

sources = {src["name"]: src for src in data.get("sources", [])}
expected = {
    "buildroot": "GPL-2.0-or-later",
    "miniz": "Unlicense",
    "doom-ascii": "GPL-2.0-or-later",
}
for name, license_id in expected.items():
    src = sources.get(name)
    if not src:
        raise SystemExit(f"missing source metadata for {name}")
    if src.get("license") != license_id:
        raise SystemExit(f"{name}: expected {license_id}, got {src.get('license')!r}")
    if not src.get("homepage"):
        raise SystemExit(f"{name}: missing homepage")

print("licensing ok")
PY
