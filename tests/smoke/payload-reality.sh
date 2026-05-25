#!/bin/sh
set -eu

[ -x runtime/payload/bin/busybox ] || {
    printf '%s\n' "payload-reality: missing runtime/payload/bin/busybox; run package-native first" >&2
    exit 1
}

tmp=${TMPDIR:-/tmp}/busierbox-payload-reality.$$
trap 'rm -f "$tmp"' EXIT HUP INT TERM

cat >"$tmp" <<'EOF'
BB_HEAVY_TOOLS="definitely-not-a-tool"
BB_DROPBEAR_SERVER_MODE="no"
EOF

BUSIERBOX_CONFIG="$tmp" scripts/build-payload >/dev/null

python3 - <<'PY'
import json
import pathlib

m = json.load(open("runtime/payload/manifest.json", "r", encoding="utf-8"))
assert "definitely-not-a-tool" in m["requested_payload_tools"]
assert "definitely-not-a-tool" in m["missing_payload_tools"]
assert "definitely-not-a-tool" not in m["staged_payload_tools"]
assert not pathlib.Path("runtime/payload/bin/definitely-not-a-tool").exists()
PY

if find runtime/payload/bin -maxdepth 1 -type f -exec grep -l 'mock heavy tool\|payload is not staged' {} + 2>/dev/null | grep . >/dev/null; then
    printf '%s\n' "placeholder payload tool found" >&2
    exit 1
fi

printf '%s\n' "payload-reality ok"
