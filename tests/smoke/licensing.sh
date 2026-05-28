#!/bin/sh
set -eu

test -f LICENSE
grep -q 'GNU GENERAL PUBLIC LICENSE' LICENSE
grep -q 'Version 2, June 1991' LICENSE
test -f LICENSE.busierbox
grep -q 'SPDX-License-Identifier: GPL-2.0-or-later' LICENSE.busierbox
grep -q 'Unless a file states a different license' LICENSE.busierbox
test -f NOTICE
grep -q 'GPL-2.0-or-later' NOTICE
grep -q 'LICENSE.busierbox' NOTICE
test -f manifests/license-policy.json
scripts/check-licensing

tmp=${TMPDIR:-/tmp}/busierbox-licensing.$$
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp"
python3 - "$tmp/sources.lock.json" <<'PY'
import json
import sys

data = {
    "schema": 2,
    "sources": [
        {
            "name": "new-tool",
            "version": "1.0",
            "filename": "new-tool-1.0.tar.gz",
            "sha256": "0" * 64,
            "urls": ["https://example.invalid/new-tool-1.0.tar.gz"],
            "homepage": "https://example.invalid/new-tool",
        }
    ],
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(data, fh)
PY
if scripts/check-licensing manifests/license-policy.json "$tmp/sources.lock.json" >"$tmp/missing-license.out" 2>&1; then
    printf '%s\n' "licensing smoke: source without license metadata was accepted" >&2
    exit 1
fi
grep -q 'source lock new-tool missing license' "$tmp/missing-license.out"

grep -q 'GPL-2.0-or-later' README.md
grep -q 'LICENSE.busierbox' README.md
grep -q 'NOTICE' README.md
grep -q 'docs/licensing.md' README.md
grep -q 'manifests/license-policy.json' README.md
grep -q 'BusierBox is not a BusyBox replacement and is not a BusyBox fork' README.md

grep -q 'GPL-2.0-or-later' docs/licensing.md
grep -q 'LICENSE.busierbox' docs/licensing.md
grep -q 'GPL compatibility summary' docs/licensing.md
grep -q 'scripts/check-licensing' docs/licensing.md
grep -q 'manifests/license-policy.json' docs/licensing.md
grep -q 'BusyBox' docs/licensing.md
grep -q 'Buildroot' docs/licensing.md
grep -q 'doom-ascii' docs/licensing.md
grep -q 'miniz' docs/licensing.md
grep -q 'BB_DOOM_WAD_PATH' docs/licensing.md

python3 - <<'PY'
import json

with open("manifests/sources.lock.json", encoding="utf-8") as fh:
    data = json.load(fh)

sources = {src["name"]: src for src in data.get("sources", [])}
expected = {
    "buildroot": "GPL-2.0-or-later",
    "miniz": "MIT OR Unlicense",
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
