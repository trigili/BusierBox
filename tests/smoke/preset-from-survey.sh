#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/preset-from-survey.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

survey=tests/fixtures/survey/glinet-mt7621.json
preset_name=glinet-mt1300-lab

scripts/lib/preset-from-survey --survey "$survey" --name "$preset_name" --json >"$work/preset.json"
python3 -m json.tool "$work/preset.json" >/dev/null
python3 - "$work/preset.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
expected = {
    "name": "glinet-mt1300-lab",
    "arch": "mipsel",
    "endian": "little",
    "libc": "musl",
    "kernel_floor": "4.x",
    "cpu": "mips32r2-24kc",
    "abi": "default",
}
for key, value in expected.items():
    if data.get(key) != value:
        raise SystemExit(f"{key} mismatch: {data.get(key)!r}")
for forbidden in (
    "payload_preset",
    "runtime_mode",
    "rshell_transport",
    "operator_host",
    "zero_arg_mode",
    "GRIT_PAYLOAD_PRESET",
    "GRIT_RUNTIME_MODE",
    "GRIT_RSHELL_TRANSPORT",
):
    if forbidden in data:
        raise SystemExit(f"target preset leaked runtime field: {forbidden}")
if data.get("source", {}).get("type") != "survey":
    raise SystemExit("missing survey provenance")
if len(data.get("source", {}).get("survey_sha256", "")) != 64:
    raise SystemExit("missing survey hash")
if data.get("confidence", {}).get("arch") not in {"high", "medium"}:
    raise SystemExit("missing confidence metadata")
compat = data.get("compatibility") or {}
if compat.get("label") != "exact":
    raise SystemExit(f"unexpected compatibility label: {compat!r}")
reasons = compat.get("reasons") or []
if "arch inferred from survey evidence" not in reasons:
    raise SystemExit(f"missing compatibility reasons: {reasons!r}")
if "payload/runtime compatibility is scored separately" not in compat.get("note", ""):
    raise SystemExit("missing target-only compatibility note")
evidence = data.get("evidence") or {}
if evidence.get("machine") != "mipsel":
    raise SystemExit(f"missing survey evidence machine: {evidence!r}")
if (evidence.get("recommendations") or {}).get("libc_guess") != "musl":
    raise SystemExit(f"missing recommendation evidence: {evidence!r}")
if not data.get("notes"):
    raise SystemExit("missing review notes")
PY

scripts/lib/preset-from-survey \
    --survey "$survey" \
    --name "$preset_name" \
    --write-local \
    --output-dir "$work/presets" >"$work/write.out"
grep -q "wrote $work/presets/$preset_name.json" "$work/write.out"

if scripts/lib/preset-from-survey --survey "$survey" --name "$preset_name" --write-local --output-dir "$work/presets" >"$work/dup.out" 2>"$work/dup.err"; then
    printf '%s\n' "preset-from-survey: duplicate write unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'preset name already exists' "$work/dup.err"

GRIT_LOCAL_TARGET_PRESETS="$work/presets" scripts/lib/resolve-target "$preset_name" >"$work/resolved"
grep -q '^TARGET_ARCH=mipsel$' "$work/resolved"
grep -q '^TARGET_ENDIAN=little$' "$work/resolved"
grep -q '^TARGET_LIBC=musl$' "$work/resolved"
grep -q '^TARGET_KERNEL_FLOOR=4.x$' "$work/resolved"
grep -q '^TARGET_CPU=mips32r2-24kc$' "$work/resolved"

GRIT_LOCAL_TARGET_PRESETS="$work/presets" scripts/lib/resolve-target --list >"$work/list"
grep -q "^$preset_name	" "$work/list"

scripts/lib/preset-from-survey \
    --survey tests/fixtures/survey/bigendian-mips-uclibc-2.6.json \
    --name mipseb-uclibc-lab \
    --json >"$work/mipseb.json"
python3 - "$work/mipseb.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["arch"] == "mips"
assert data["endian"] == "big"
assert data["libc"] == "uclibc"
assert data["kernel_floor"] == "2.6"
assert data["cpu"] == "mips32"
compat = data["compatibility"]
assert compat["label"] == "exact"
assert "arch inferred from survey evidence" in compat["reasons"]
assert "libc inferred from survey evidence" in compat["reasons"]
assert "kernel floor inferred from survey evidence" in compat["reasons"]
assert "payload/runtime compatibility is scored separately" in compat["note"]
evidence = data["evidence"]
assert evidence["machine"] == "mips"
assert evidence["endianness"] == "big"
assert evidence["recommendations"]["target_cpu_guess"] == "mips32"
PY

scripts/lib/preset-from-survey \
    --survey tests/fixtures/survey/non-openwrt-armv7-glibc.json \
    --name debian-armv7-lab \
    --json >"$work/non-openwrt.json"
python3 - "$work/non-openwrt.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["arch"] == "armv7"
assert data["endian"] == "little"
assert data["libc"] == "glibc"
assert data["kernel_floor"] == "4.x"
assert data["cpu"] == "cortex-a9"
assert data["openwrt"] == {}
compat = data["compatibility"]
assert compat["label"] == "exact"
assert "arch inferred from survey evidence" in compat["reasons"]
assert "libc inferred from survey evidence" in compat["reasons"]
assert "kernel floor inferred from survey evidence" in compat["reasons"]
assert "OpenWrt release hints present" not in compat["reasons"]
assert "payload/runtime compatibility is scored separately" in compat["note"]
evidence = data["evidence"]
assert evidence["machine"] == "armv7l"
assert evidence["recommendations"]["target_arch_guess"] == "armv7"
PY

printf '%s\n' "preset-from-survey ok"
