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
"$work/busierbox" runtime-config >"$work/runtime.none"
grep -q '^effective_config_source=compiled$' "$work/runtime.none"
grep -q '^trailer_present=no$' "$work/runtime.none"
"$work/busierbox" runtime-config --json >"$work/runtime.none.json"
python3 -m json.tool "$work/runtime.none.json" >/dev/null

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
grep -q '^trailer_override_encoding=plain$' "$work/config.set"
grep -q '^effective_config_source=trailer$' "$work/config.set"
grep -q '^effective_rshell_operator_host=198.51.100.7$' "$work/config.set"
"$work/busierbox" runtime-config >"$work/runtime.set"
grep -q '^effective_config_source=trailer$' "$work/runtime.set"
grep -q '^trailer_encoding=plain$' "$work/runtime.set"
grep -q '^effective_BB_OPERATOR_SERVER_HOST=198.51.100.7$' "$work/runtime.set"
"$work/busierbox" runtime-config --json >"$work/runtime.set.json"
python3 - "$work/runtime.set.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "trailer"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is True
assert r["trailer_override"]["encoding"] == "plain"
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "198.51.100.7"
PY
BB_OPERATOR_SERVER_HOST=203.0.113.9 "$work/busierbox" runtime-config --json >"$work/runtime.env.json"
python3 - "$work/runtime.env.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "env"
assert r["environment_override_count"] >= 1
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "203.0.113.9"
PY
"$work/busierbox" manifest --json >"$work/manifest.set.json"
python3 - "$work/manifest.set.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert m["trailer_override"]["present"] is True
assert m["trailer_override"]["valid"] is True
assert m["trailer_override"]["encoding"] == "plain"
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
grep -q '^effective_config_source=compiled$' "$work/config.bad"
if grep -q '^effective_rshell_operator_host=198.51.100.7$' "$work/config.bad"; then
    printf '%s\n' "artifact-config smoke: invalid trailer override was applied" >&2
    exit 1
fi
"$work/busierbox-bad" runtime-config --json >"$work/runtime.bad.json"
python3 - "$work/runtime.bad.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
PY

cp "$work/busierbox" "$work/busierbox-bad-magic"
python3 - "$work/busierbox-bad-magic" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
b[start:start + len(b"BBXCONFIGv1")] = b"BADCONFIGv1"
p.write_bytes(b)
PY
scripts/artifact-config show "$work/busierbox-bad-magic" >"$work/show.bad-magic"
grep -q '^trailer_present=no$' "$work/show.bad-magic"
"$work/busierbox-bad-magic" runtime-config --json >"$work/runtime.bad-magic.json"
python3 - "$work/runtime.bad-magic.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is False
assert r["trailer_override"]["valid"] is False
PY

cp "$work/busierbox" "$work/busierbox-bad-version"
python3 - "$work/busierbox-bad-version" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"version=1\n"
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("version metadata not found")
b[pos:pos + len(needle)] = b"version=2\n"
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad-version" >"$work/show.bad-version" 2>&1; then
    printf '%s\n' "artifact-config smoke: unsupported version trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=unsupported version$' "$work/show.bad-version"
"$work/busierbox-bad-version" runtime-config --json >"$work/runtime.bad-version.json"
python3 - "$work/runtime.bad-version.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["status"] == "unsupported version"
PY

cp "$work/busierbox" "$work/busierbox-bad-bounds"
python3 - "$work/busierbox-bad-bounds" <<'PY'
import hashlib, pathlib, sys
MAGIC = b"BBXCONFIGv1"
TRAILER_SIZE = 4096
p = pathlib.Path(sys.argv[1])
payload = b"BB_OPERATOR_SERVER_HOST=192.0.2.99\n"
sha = hashlib.sha256(payload).hexdigest()
meta = (
    MAGIC.decode() + "\n"
    "version=1\n"
    "encoding=plain\n"
    "size=999999\n"
    f"sha256={sha}\n"
    "key_hex=\n"
    "payload_offset=120\n"
    "ENDMETA\n"
).encode("ascii")
trailer = meta + payload
if len(trailer) > TRAILER_SIZE:
    raise SystemExit("trailer too large")
data = p.read_bytes()
p.write_bytes(data[:-TRAILER_SIZE] + trailer + b"\0" * (TRAILER_SIZE - len(trailer)))
PY
if scripts/artifact-config show "$work/busierbox-bad-bounds" >"$work/show.bad-bounds" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid bounds trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=payload bounds invalid$' "$work/show.bad-bounds"
"$work/busierbox-bad-bounds" runtime-config --json >"$work/runtime.bad-bounds.json"
python3 - "$work/runtime.bad-bounds.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["status"] == "payload bounds invalid"
PY

cp "$artifact" "$work/busierbox-unknown-runtime"
python3 - "$work/busierbox-unknown-runtime" <<'PY'
import hashlib, pathlib, sys
MAGIC = b"BBXCONFIGv1"
TRAILER_SIZE = 4096
p = pathlib.Path(sys.argv[1])
payload = b"BB_OPERATOR_SERVER_HOST=192.0.2.88\nBB_TARGET_ARCH=mipsel\n"
sha = hashlib.sha256(payload).hexdigest()
meta_prefix = (
    MAGIC.decode() + "\n"
    "version=1\n"
    "encoding=plain\n"
    f"size={len(payload)}\n"
    f"sha256={sha}\n"
    "key_hex=\n"
)
offset = 0
while True:
    next_offset = len((meta_prefix + f"payload_offset={offset}\nENDMETA\n").encode("ascii"))
    if next_offset == offset:
        break
    offset = next_offset
trailer = (meta_prefix + f"payload_offset={offset}\nENDMETA\n").encode("ascii") + payload
if len(trailer) > TRAILER_SIZE:
    raise SystemExit("trailer too large")
p.write_bytes(p.read_bytes() + trailer + b"\0" * (TRAILER_SIZE - len(trailer)))
PY
scripts/artifact-config show "$work/busierbox-unknown-runtime" >"$work/show.unknown-runtime"
grep -q '^trailer_valid=yes$' "$work/show.unknown-runtime"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.88$' "$work/show.unknown-runtime"
if grep -q '^BB_TARGET_ARCH=' "$work/show.unknown-runtime"; then
    printf '%s\n' "artifact-config smoke: unknown trailer key was exported" >&2
    exit 1
fi
"$work/busierbox-unknown-runtime" runtime-config --json >"$work/runtime.unknown-runtime.json"
python3 - "$work/runtime.unknown-runtime.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "trailer"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is True
assert r["trailer_override"]["override_count"] == 1
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "192.0.2.88"
assert "BB_TARGET_ARCH" not in r["effective_config"]
PY

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
"$work/busierbox-xor" runtime-config --json >"$work/runtime.xor.json"
python3 - "$work/runtime.xor.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "trailer"
assert r["trailer_override"]["encoding"] == "xor"
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "192.0.2.44"
PY

printf '%s\n' "artifact-config ok"
