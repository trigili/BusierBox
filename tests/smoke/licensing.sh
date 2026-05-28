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
test -f LICENSES/miniz.txt
grep -q 'third_party/miniz/LICENSE' LICENSES/miniz.txt
test -f LICENSES/busybox.txt
grep -q 'third_party/busybox/LICENSE' LICENSES/busybox.txt
test -f LICENSES/buildroot.txt
grep -q 'manifests/sources.lock.json' LICENSES/buildroot.txt
test -f LICENSES/doom-ascii.txt
grep -q 'BB_DOOM_WAD_PATH' LICENSES/doom-ascii.txt
test -f manifests/license-policy.json
scripts/check-licensing
make check-licensing

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
grep -q 'make check-licensing' docs/licensing.md
grep -q 'manifests/license-policy.json' docs/licensing.md
grep -q 'BusyBox' docs/licensing.md
grep -q 'Buildroot' docs/licensing.md
grep -q 'doom-ascii' docs/licensing.md
grep -q 'miniz' docs/licensing.md
grep -q 'BB_DOOM_WAD_PATH' docs/licensing.md
grep -q 'GPLv2-compatible combined distributions' docs/licensing.md
grep -q 'Buildroot-selected package keeps its own upstream' docs/licensing.md
grep -q "not part of BusierBox's license grant" docs/licensing.md
grep -q 'release bundles include it as both `sources.lock.json` and' docs/licensing.md
grep -q 'Release bundles always copy' docs/release-bundles.md

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

policy = json.load(open("manifests/license-policy.json", encoding="utf-8"))
artifact_distribution = policy.get("artifact_distribution") or {}
if artifact_distribution.get("busierbox_project_terms") != "GPL-2.0-or-later":
    raise SystemExit("artifact distribution project terms missing")
if artifact_distribution.get("ok_for_current_default_stack") is not True:
    raise SystemExit("artifact distribution compatibility flag missing")
for key, needle in {
    "combined_release_terms_when_busybox_included": "GPL-2.0",
    "buildroot_role": "selected packages keep their own licenses",
    "payload_license_rule": "every bundled payload component",
    "user_supplied_data_rule": "Doom WAD",
}.items():
    if needle not in str(artifact_distribution.get(key, "")):
        raise SystemExit(f"artifact distribution {key} missing {needle}")
guidance = "\n".join(policy.get("distribution_guidance") or [])
for expected_text in ("LICENSE.busierbox", "LICENSES/", "manifests/sources.lock.json", "sources.lock.json"):
    if expected_text not in guidance:
        raise SystemExit(f"license policy guidance missing {expected_text}")

print("licensing ok")
PY
