#!/bin/sh
# Source-level regression checks for rshell external filesystem writes.
set -eu

src=${1:-src/busierbox.c}
menu=${2:-scripts/menuconfig}
payload=${3:-src/applet_clean.c}

[ -f "$src" ] || {
    printf '%s\n' "rshell-external-writes: missing $src" >&2
    exit 1
}
[ -f "$menu" ] || {
    printf '%s\n' "rshell-external-writes: missing $menu" >&2
    exit 1
}
[ -f "$payload" ] || {
    printf '%s\n' "rshell-external-writes: missing $payload" >&2
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

root_copy_start = text.find('BB_RSHELL_AUTHKEYS_MODE, "root-copy"')
root_merge_start = text.find('BB_RSHELL_AUTHKEYS_MODE, "root-merge"')
hostkey_start = text.find('BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING', root_merge_start)
if root_copy_start < 0 or root_merge_start < 0 or hostkey_start < 0:
    raise SystemExit("rshell-external-writes: authkeys mode blocks not found")

root_copy = text[root_copy_start:root_merge_start]
root_merge = text[root_merge_start:hostkey_start]

for needle in [
    'append_rshell_ledger_setup(cmd, sizeof(cmd));',
    'bbx_ledger write /root/.ssh/authorized_keys external root-copy',
]:
    if needle not in root_copy:
        raise SystemExit(f"rshell-external-writes: root-copy missing {needle}")

for needle in [
    'append_rshell_ledger_setup(cmd, sizeof(cmd));',
    'bak=/root/.ssh/authorized_keys.busierbox.bak.$$',
    'bbx_ledger backup',
    'bbx_ledger modify /root/.ssh/authorized_keys external root-merge',
]:
    if needle not in root_merge:
        raise SystemExit(f"rshell-external-writes: root-merge missing {needle}")

if 'cleanup-ledger.jsonl' not in text:
    raise SystemExit("rshell-external-writes: rshell ledger path not generated")
PY

python3 - "$payload" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
for needle in [
    'clean_external_from_ledger',
    'bb_clean_external_from_ledger',
    'remove_rshell_marked_block',
    '"/root/.ssh/authorized_keys"',
    '"root-merge"',
    '"root-copy"',
    'external && apply && clean_external_from_ledger(',
]:
    if needle not in text:
        raise SystemExit(f"rshell-external-writes: clean external path missing {needle}")
PY

grep -q 'bb_clean_external_from_ledger()' "$src"
awk '/subcmd, "cleanup"/,/subcmd, "stop"/' "$src" | grep -q 'bb_clean_external_from_ledger'
awk '/subcmd, "cleanup"/,/subcmd, "stop"/' "$src" | grep -q 'external && apply'

awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'BB_RUNTIME_ALLOW_EXTERNAL_WRITES'
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'root-copy|root-merge'
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'disabled|payload-home'

printf '%s\n' "rshell-external-writes ok"
