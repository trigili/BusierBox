#!/bin/sh
# Source-level regression checks for rshell external filesystem writes.
set -eu

src=${1:-src/busierbox.c}
menu=${2:-scripts/menuconfig}

[ -f "$src" ] || {
    printf '%s\n' "rshell-external-writes: missing $src" >&2
    exit 1
}
[ -f "$menu" ] || {
    printf '%s\n' "rshell-external-writes: missing $menu" >&2
    exit 1
}

python3 - "$src" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
needle = 'shquote_append(cmd, sizeof(cmd), rootssh);'
idx = text.find(needle)
if idx < 0:
    raise SystemExit("rshell-external-writes: rootssh mkdir not found")

prev_root_copy = text.rfind('BB_RSHELL_AUTHKEYS_MODE, "root-copy"', 0, idx)
prev_root_merge = text.rfind('BB_RSHELL_AUTHKEYS_MODE, "root-merge"', 0, idx)
prev_disabled = text.rfind('BB_RSHELL_AUTHKEYS_MODE, "disabled"', 0, idx)
prev_payload_home = text.rfind('BB_RSHELL_AUTHKEYS_MODE, "payload-home"', 0, idx)

if max(prev_root_copy, prev_root_merge) < 0:
    raise SystemExit("rshell-external-writes: /root/.ssh creation is not gated by root authkeys modes")
if max(prev_disabled, prev_payload_home) > max(prev_root_copy, prev_root_merge):
    raise SystemExit("rshell-external-writes: disabled/payload-home appear to gate /root/.ssh creation")
PY

awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'BB_RUNTIME_ALLOW_EXTERNAL_WRITES'
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'root-copy|root-merge'
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'disabled|payload-home'

printf '%s\n' "rshell-external-writes ok"
