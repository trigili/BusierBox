#!/bin/sh
set -eu

artifact=${1:-dist/busierbox-native-full}
if [ ! -x "$artifact" ] || ! "$artifact" list --plain 2>/dev/null | grep -q '^native plan$'; then
    BUSIERBOX_CONFIG=presets/payload/default.conf BB_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
fi

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/plan-json.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

cp "$artifact" "$work/busierbox"
chmod 0755 "$work/busierbox"
scripts/artifact-config set "$work/busierbox" \
    BB_RUNTIME_ROOT="$work/runtime" \
    BB_OPERATOR_SERVER_HOST=192.0.2.77 \
    BB_RSHELL_TRANSPORT=builtin >/dev/null

"$work/busierbox" plan --json | python3 -m json.tool >/dev/null
"$work/busierbox" plan extract --json >"$work/extract.json"
"$work/busierbox" plan rshell --json >"$work/rshell.json"
"$work/busierbox" plan clean --json >"$work/clean.json"
"$work/busierbox" plan recovery install --method openwrt-procd --action rshell --json >"$work/recovery.json"
"$work/busierbox" plan recovery install --method cron-reboot --action command --json -- 'busierbox rshell start' >"$work/recovery-command.json"

for json in "$work"/*.json; do
    python3 -m json.tool "$json" >/dev/null
done

python3 - "$work" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
extract = json.loads((root / "extract.json").read_text())
rshell = json.loads((root / "rshell.json").read_text())
clean = json.loads((root / "clean.json").read_text())
recovery = json.loads((root / "recovery.json").read_text())
command = json.loads((root / "recovery-command.json").read_text())

assert extract["command"] == "extract"
assert extract["runtime_root"].endswith("/runtime")
assert extract["config"]["effective_config_source"] == "trailer"
assert extract["config"]["trailer_present"] is True
assert extract["config"]["trailer_valid"] is True
assert any(path.endswith("/runtime") for path in extract["would_create"])

assert rshell["command"] == "rshell"
assert rshell["transport"] == "builtin"
assert rshell["operator_host"] == "192.0.2.77"
assert rshell["requires_external_writes"] is False
assert "192.0.2.77" in rshell["would_connect"][0]

assert clean["command"] == "clean"
assert any(path.endswith("/runtime") for path in clean["would_remove"])

assert recovery["command"] == "recovery install"
assert recovery["method"] == "openwrt-procd"
assert recovery["action"] == "rshell"
assert recovery["requires_external_writes"] is True
assert recovery["binary_path"].endswith("/usr/bin/busierbox_recovery")
assert recovery["generated_command"] == "/usr/bin/busierbox_recovery rshell start"
assert recovery["generated_command"].endswith("rshell start")

assert command["action"] == "command"
assert command["binary_path"].endswith("/usr/bin/busierbox_recovery")
assert command["generated_command"] == "busierbox rshell start"
PY

"$work/busierbox" plan extract >"$work/extract.txt"
grep -q '^Plan: extract$' "$work/extract.txt"
grep -q '^effective_config_source=trailer$' "$work/extract.txt"

printf '%s\n' "plan-json ok"
