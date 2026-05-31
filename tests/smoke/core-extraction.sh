#!/bin/sh
set -eu

bb=${1:-dist/grit-native-full}

[ -x "$bb" ] || {
    printf '%s\n' "core-extraction: missing executable $bb" >&2
    exit 1
}

case "$bb" in
    /*) bb_abs=$bb ;;
    *) bb_abs=$(pwd)/$bb ;;
esac

tmp_parent=${TMPDIR:-local/tmp}
mkdir -p "$tmp_parent"
tmp=$(mktemp -d "$tmp_parent/grit-core-extraction.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

cp "$bb_abs" "$tmp/grit"
chmod 0755 "$tmp/grit"

(
    cd "$tmp"

    ./grit cp --help >/dev/null 2>&1

    test -x .grit/payload/bin/busybox
    test ! -e .grit/payload/bin/sh
    test "$(cat .grit/payload/.grit-extract-mode)" = core
    ./grit config-info | grep -q '^payload_extraction_mode=core$'
    ./grit doctor | grep -q '^payload_extraction_mode=core$'

    if command -v python3 >/dev/null 2>&1; then
        ./grit doctor --json >doctor-core.json
        python3 -m json.tool doctor-core.json >/dev/null
        python3 - doctor-core.json <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    doc = json.load(fh)
payload = doc.get("extracted_payload", {})
if payload.get("extraction_mode") != "core":
    raise SystemExit(f"expected core extraction mode, got {payload.get('extraction_mode')!r}")
PY
    fi

    ./grit extract >/dev/null
    test "$(cat .grit/payload/.grit-extract-mode)" = full
    test -e .grit/payload/bin/sh
    ./grit config-info | grep -q '^payload_extraction_mode=full$'

    if command -v python3 >/dev/null 2>&1; then
        ./grit doctor --json >doctor-full.json
        python3 -m json.tool doctor-full.json >/dev/null
        python3 - doctor-full.json <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    doc = json.load(fh)
payload = doc.get("extracted_payload", {})
if payload.get("extraction_mode") != "full":
    raise SystemExit(f"expected full extraction mode, got {payload.get('extraction_mode')!r}")
PY
    fi
)

printf '%s\n' "core-extraction ok"
