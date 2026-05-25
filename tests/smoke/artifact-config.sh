#!/bin/sh
set -eu

artifact=${1:-}
if [ -z "$artifact" ]; then
    BUSIERBOX_CONFIG=presets/payload/default.conf BB_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
    artifact=dist/busierbox-native-full
elif [ ! -x "$artifact" ]; then
    printf '%s\n' "artifact-config smoke: missing artifact $artifact" >&2
    exit 1
fi

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/artifact-config.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

cp "$artifact" "$work/busierbox"
chmod 0755 "$work/busierbox"
base_size=$(wc -c <"$work/busierbox" | tr -d ' ')

scripts/artifact-config show "$work/busierbox" >"$work/show.none"
grep -q '^trailer_present=no$' "$work/show.none"
"$work/busierbox" config-info >"$work/config.none"
grep -q '^trailer_override_present=no$' "$work/config.none"

scripts/artifact-config set "$work/busierbox" \
    BB_OPERATOR_SERVER_HOST=198.51.100.7 \
    BB_OPERATOR_REMOTE_FORWARD_PORT=2299 \
    BB_ZERO_ARG_LOG_MODE=status >"$work/set.out"
test "$(wc -c <"$work/busierbox" | tr -d ' ')" -eq $((base_size + 4096))
scripts/artifact-config show "$work/busierbox" >"$work/show.set"
grep -q '^trailer_present=yes$' "$work/show.set"
grep -q '^trailer_valid=yes$' "$work/show.set"
grep -q '^BB_OPERATOR_SERVER_HOST=198.51.100.7$' "$work/show.set"
"$work/busierbox" config-info >"$work/config.set"
grep -q '^trailer_override_present=yes$' "$work/config.set"
grep -q '^trailer_override_valid=yes$' "$work/config.set"
grep -q '^effective_rshell_operator_host=198.51.100.7$' "$work/config.set"
"$work/busierbox" manifest --json >"$work/manifest.set.json"
python3 - "$work/manifest.set.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert m["trailer_override"]["present"] is True
assert m["trailer_override"]["valid"] is True
assert m["compiled_config"]["BB_OPERATOR_SERVER_HOST"] != "198.51.100.7"
assert m["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "198.51.100.7"
PY
scripts/inspect-artifact "$work/busierbox" | grep -q '^config_trailer_present=yes$'
scripts/verify-artifact "$work/busierbox" >/dev/null

cp "$work/busierbox" "$work/busierbox-bad"
python3 - "$work/busierbox-bad" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"sha256="
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("sha256 metadata not found")
pos += len(needle)
b[pos] = ord("0") if b[pos] != ord("0") else ord("1")
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad" >"$work/show.bad" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid checksum trailer unexpectedly passed" >&2
    exit 1
fi
"$work/busierbox-bad" config-info >"$work/config.bad"
grep -q '^trailer_override_present=yes$' "$work/config.bad"
grep -q '^trailer_override_valid=no$' "$work/config.bad"
grep -q '^effective_rshell_operator_host=$' "$work/config.bad"

if scripts/artifact-config set "$work/busierbox" BB_TARGET_ARCH=mipsel >"$work/unknown.out" 2>&1; then
    printf '%s\n' "artifact-config smoke: forbidden target key was accepted" >&2
    exit 1
fi
grep -q 'not trailer-overridable' "$work/unknown.out"

scripts/artifact-config set "$work/busierbox" BB_OPERATOR_SERVER_HOST=203.0.113.8 >/dev/null
test "$(wc -c <"$work/busierbox" | tr -d ' ')" -eq $((base_size + 4096))
scripts/artifact-config export "$work/busierbox" >"$work/export.env"
grep -q '^BB_OPERATOR_SERVER_HOST=203.0.113.8$' "$work/export.env"
printf '%s\n' 'BB_ZERO_ARG_MODE=survey' >"$work/import.env"
scripts/artifact-config import "$work/busierbox" "$work/import.env" >/dev/null
scripts/artifact-config export "$work/busierbox" >"$work/export2.env"
grep -q '^BB_ZERO_ARG_MODE=survey$' "$work/export2.env"

scripts/artifact-config clear "$work/busierbox" >/dev/null
test "$(wc -c <"$work/busierbox" | tr -d ' ')" -eq "$base_size"
scripts/artifact-config show "$work/busierbox" >"$work/show.clear"
grep -q '^trailer_present=no$' "$work/show.clear"

cp "$artifact" "$work/busierbox-xor"
BB_TRAILER_OBFUSCATION=xor scripts/artifact-config set "$work/busierbox-xor" BB_OPERATOR_SERVER_HOST=192.0.2.44 >"$work/xor.out"
grep -q 'not encryption' "$work/xor.out"
"$work/busierbox-xor" config-info | grep -q '^effective_rshell_operator_host=192.0.2.44$'

printf '%s\n' "artifact-config ok"
