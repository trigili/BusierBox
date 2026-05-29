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
grep -q '^command_queue_policy_valid=yes$' "$work/runtime.none"
grep -q '^command_queue_result_upload_supported=yes$' "$work/runtime.none"
grep -q '^command_queue_execution_supported=no$' "$work/runtime.none"
grep -q '^command_queue_safe_disabled_default=yes$' "$work/runtime.none"
"$work/busierbox" runtime-config --json >"$work/runtime.none.json"
python3 -m json.tool "$work/runtime.none.json" >/dev/null
python3 - "$work/runtime.none.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
p = r["noresidue_policy"]
assert p["active"] is False
assert p["runtime_mode"] == r["effective_config"]["BB_RUNTIME_MODE"]
assert p["level"] == r["effective_config"]["BB_NORESIDUE_LEVEL"]
assert p["best_effort"] is True
assert p["aggressive_minimizes_runtime_residue"] is False
assert p["forensic_no_trace"] is False
assert p["external_writes_require_explicit_apply"] is True
assert "BusierBox-owned runtime roots" in p["cleanup_scope"]
rshell = r["rshell_readiness"]
assert rshell["session_policy"] == r["effective_config"]["BB_RSHELL_SESSION_POLICY"]
assert rshell["session_policy_valid"] is True
assert rshell["session_policy_errors"] == []
policy = r["effective_config"]["BB_RSHELL_SESSION_POLICY"]
reconnects = policy in ("reconnect", "persistent")
persistent = policy == "persistent"
post_disconnect_count = "-1" if persistent else ("0" if policy == "single" else r["effective_config"]["BB_RSHELL_RETRY_COUNT"])
assert rshell["session_semantics"]["retry_until_first_connection"] is True
assert rshell["session_semantics"]["stop_after_first_success"] is (policy == "single")
assert rshell["session_semantics"]["reconnect_after_disconnect"] is reconnects
assert rshell["session_semantics"]["persistent_lifecycle"] is persistent
assert rshell["session_semantics"]["fresh_session_on_reconnect"] is reconnects
assert rshell["session_semantics"]["session_resume_supported"] is False
assert rshell["session_policy_summary"]["valid"] is True
assert rshell["session_policy_summary"]["errors"] == []
assert rshell["session_policy_summary"]["retry_scope"] == ("pre-connect+post-disconnect" if reconnects else "pre-connect")
assert rshell["session_policy_summary"]["pre_connect_retry_count"] == r["effective_config"]["BB_RSHELL_RETRY_COUNT"]
assert rshell["session_policy_summary"]["post_disconnect_retry_count"] == post_disconnect_count
assert rshell["session_policy_summary"]["stops_after_success"] is (policy == "single")
assert rshell["session_policy_summary"]["reconnects_after_disconnect"] is reconnects
assert rshell["session_policy_summary"]["session_resume_supported"] is False
assert rshell["retry"]["count"] == r["effective_config"]["BB_RSHELL_RETRY_COUNT"]
assert rshell["retry"]["pre_connect_count"] == r["effective_config"]["BB_RSHELL_RETRY_COUNT"]
assert rshell["retry"]["post_disconnect_count"] == post_disconnect_count
assert rshell["operator_host"] == r["effective_config"]["BB_OPERATOR_SERVER_HOST"]
cq = r["command_queue_policy"]
assert cq["valid"] is True
assert cq["enabled"] is False
assert cq["default_enabled"] is False
assert cq["configured_for_polling"] is False
assert cq["missing_operator_host"] is False
assert cq["poll_transport_supported"] is True
assert cq["live_polling_supported"] is True
assert cq["delivery_supported"] is False
assert cq["result_upload_supported"] is True
assert cq["execution_supported"] is False
assert cq["executes_commands"] is False
assert cq["active_control_channel"] is False
assert cq["operator_supplied_command_execution"] is False
assert cq["arbitrary_policy_requested"] is False
assert cq["arbitrary_execution_allowed"] is False
assert cq["safe_disabled_default"] is True
records = r["config_records"]
summary = r["config_record_summary"]
api = r["api_collections"]["config_records"]
by_key = r["config_records_by_key"]
by_source = r["config_records_by_source"]
by_changed = r["config_records_by_changed"]
by_category = r["config_records_by_category"]
assert summary["total_count"] == len(records)
assert summary["changed_count"] == 0
assert api["count"] == len(records)
assert api["summary_key"] == "config_record_summary.total_count"
assert api["count_summary_key"] == "config_record_summary.total_count"
assert api["primary_key"] == "key"
assert "config_records_by_source" in api["indexes"]
assert by_source["compiled"] == list(range(len(records)))
assert by_source["trailer"] == []
assert by_source["env"] == []
assert by_changed["yes"] == []
assert len(by_changed["no"]) == len(records)
runtime_mode_record = records[by_key["BB_RUNTIME_MODE"][0]]
assert runtime_mode_record["category"] == "runtime"
assert runtime_mode_record["source"] == "compiled"
assert runtime_mode_record["compiled"] == runtime_mode_record["effective"]
assert by_category["command_queue"]
PY

scripts/artifact-config set "$work/busierbox" \
    BB_RSHELL_TRANSPORT=ssh \
    BB_RSHELL_SESSION_POLICY=reconnect \
    BB_RSHELL_RETRY_COUNT=3 \
    BB_OPERATOR_SERVER_HOST=198.51.100.7 \
    BB_OPERATOR_REMOTE_FORWARD_PORT=2299 \
    BB_OPERATOR_SERVER_SSH_PORT=22022 \
    BB_OPERATOR_FILE_SERVICE_ENABLE=yes \
    BB_OPERATOR_FILE_SERVICE_PORT=22244 \
    BB_OPERATOR_FILE_SERVICE_TLS=no \
    BB_NORESIDUE_LEVEL=aggressive \
    BB_ZERO_ARG_LOG_MODE=status >"$work/set.out"
test "$(wc -c <"$work/busierbox" | tr -d ' ')" -eq $((base_size + 4096))
scripts/artifact-config show "$work/busierbox" >"$work/show.set"
grep -q '^trailer_present=yes$' "$work/show.set"
grep -q '^trailer_valid=yes$' "$work/show.set"
grep -q '^BB_OPERATOR_SERVER_HOST=198.51.100.7$' "$work/show.set"
grep -q '^BB_OPERATOR_FILE_SERVICE_PORT=22244$' "$work/show.set"
grep -q '^BB_NORESIDUE_LEVEL=aggressive$' "$work/show.set"
"$work/busierbox" config-info >"$work/config.set"
grep -q '^trailer_override_present=yes$' "$work/config.set"
grep -q '^trailer_override_valid=yes$' "$work/config.set"
grep -q '^trailer_override_encoding=plain$' "$work/config.set"
grep -q '^effective_config_source=trailer$' "$work/config.set"
grep -q '^effective_rshell_operator_host=198.51.100.7$' "$work/config.set"
"$work/busierbox" runtime-config >"$work/runtime.set"
grep -q '^effective_config_source=trailer$' "$work/runtime.set"
grep -q '^trailer_encoding=plain$' "$work/runtime.set"
grep -q '^effective_BB_NORESIDUE_LEVEL=aggressive$' "$work/runtime.set"
grep -q '^effective_BB_OPERATOR_SERVER_HOST=198.51.100.7$' "$work/runtime.set"
grep -q '^effective_BB_OPERATOR_FILE_SERVICE_ENABLE=yes$' "$work/runtime.set"
"$work/busierbox" runtime-config --json >"$work/runtime.set.json"
python3 - "$work/runtime.set.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "trailer"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is True
assert r["trailer_override"]["encoding"] == "plain"
assert r["effective_config"]["BB_RSHELL_TRANSPORT"] == "ssh"
assert r["effective_config"]["BB_RSHELL_SESSION_POLICY"] == "reconnect"
assert r["effective_config"]["BB_RSHELL_RETRY_COUNT"] == "3"
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "198.51.100.7"
assert r["effective_config"]["BB_OPERATOR_REMOTE_FORWARD_PORT"] == "2299"
assert r["effective_config"]["BB_OPERATOR_SERVER_SSH_PORT"] == "22022"
assert r["effective_config"]["BB_OPERATOR_FILE_SERVICE_ENABLE"] == "yes"
assert r["effective_config"]["BB_OPERATOR_FILE_SERVICE_PORT"] == "22244"
assert r["effective_config"]["BB_OPERATOR_FILE_SERVICE_TLS"] == "no"
assert r["effective_config"]["BB_NORESIDUE_LEVEL"] == "aggressive"
p = r["noresidue_policy"]
assert p["active"] is False
assert p["runtime_mode"] == r["effective_config"]["BB_RUNTIME_MODE"]
assert p["level"] == "aggressive"
assert p["aggressive_minimizes_runtime_residue"] is True
assert p["forensic_no_trace"] is False
rshell = r["rshell_readiness"]
assert rshell["transport"] == "ssh"
assert rshell["operator_host"] == "198.51.100.7"
assert rshell["remote_forward_port"] == "2299"
assert rshell["operator_ssh_port"] == "22022"
assert "--ssh-port 22022" in rshell["server_listener"]
assert "2299" in rshell["connect_hint"]
assert rshell["session_policy_valid"] is True
assert rshell["session_semantics"]["stop_after_first_success"] is False
assert rshell["session_semantics"]["reconnect_after_disconnect"] is True
assert rshell["session_semantics"]["persistent_lifecycle"] is False
assert rshell["session_semantics"]["fresh_session_on_reconnect"] is True
assert rshell["session_semantics"]["session_resume_supported"] is False
assert rshell["session_policy_summary"]["retry_scope"] == "pre-connect+post-disconnect"
assert rshell["session_policy_summary"]["pre_connect_retry_count"] == "3"
assert rshell["session_policy_summary"]["post_disconnect_retry_count"] == "3"
assert rshell["session_policy_summary"]["stops_after_success"] is False
assert rshell["session_policy_summary"]["reconnects_after_disconnect"] is True
assert rshell["session_policy_summary"]["fresh_session_on_reconnect"] is True
assert rshell["session_policy_summary"]["session_resume_supported"] is False
assert rshell["retry"]["pre_connect_count"] == "3"
assert rshell["retry"]["post_disconnect_count"] == "3"
cq = r["command_queue_policy"]
assert cq["valid"] is True
assert cq["result_upload_supported"] is True
assert cq["execution_supported"] is False
assert cq["executes_commands"] is False
records = r["config_records"]
summary = r["config_record_summary"]
by_key = r["config_records_by_key"]
by_source = r["config_records_by_source"]
by_changed = r["config_records_by_changed"]
host_record = records[by_key["BB_OPERATOR_SERVER_HOST"][0]]
level_record = records[by_key["BB_NORESIDUE_LEVEL"][0]]
assert summary["trailer_override_count"] >= 1
assert summary["changed_count"] >= 1
assert host_record["source"] == "trailer"
assert host_record["compiled"] != host_record["effective"]
assert host_record["effective"] == "198.51.100.7"
assert level_record["source"] == "trailer"
assert level_record["effective"] == "aggressive"
assert by_key["BB_OPERATOR_SERVER_HOST"][0] in by_source["trailer"]
assert by_key["BB_OPERATOR_SERVER_HOST"][0] in by_changed["yes"]
PY
"$work/busierbox" rshell status --json >"$work/rshell.status.trailer.json"
python3 - "$work/rshell.status.trailer.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["runtime_config"]["effective_config_source"] == "trailer"
assert r["transport"] == "ssh"
assert r["operator_host"] == "198.51.100.7"
assert r["remote_forward_port"] == "2299"
assert r["operator_ssh_port"] == "22022"
assert "--ssh-port 22022" in r["server_listener"]
assert "2299" in r["connect_hint"]
PY
BB_OPERATOR_SERVER_HOST=203.0.113.9 "$work/busierbox" runtime-config --json >"$work/runtime.env.json"
python3 - "$work/runtime.env.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "env"
assert r["environment_override_count"] >= 1
assert r["effective_config"]["BB_OPERATOR_SERVER_HOST"] == "203.0.113.9"
assert r["noresidue_policy"]["level"] == r["effective_config"]["BB_NORESIDUE_LEVEL"]
assert r["rshell_readiness"]["operator_host"] == "203.0.113.9"
assert r["rshell_readiness"]["operator_host_set"] is True
records = r["config_records"]
by_key = r["config_records_by_key"]
by_source = r["config_records_by_source"]
host_index = by_key["BB_OPERATOR_SERVER_HOST"][0]
host_record = records[host_index]
assert host_record["source"] == "env"
assert host_record["effective"] == "203.0.113.9"
assert host_index in by_source["env"]
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

cp "$work/busierbox" "$work/busierbox-bad-offset"
python3 - "$work/busierbox-bad-offset" <<'PY'
import hashlib, pathlib, sys
MAGIC = b"BBXCONFIGv1"
TRAILER_SIZE = 4096
p = pathlib.Path(sys.argv[1])
payload = b"BB_OPERATOR_SERVER_HOST=192.0.2.77\n"
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
bad_offset = TRAILER_SIZE - len(payload) + 1
trailer = (meta_prefix + f"payload_offset={bad_offset}\nENDMETA\n").encode("ascii") + payload
if len(trailer) > TRAILER_SIZE:
    raise SystemExit("trailer too large")
data = p.read_bytes()
p.write_bytes(data[:-TRAILER_SIZE] + trailer + b"\0" * (TRAILER_SIZE - len(trailer)))
PY
if scripts/artifact-config show "$work/busierbox-bad-offset" >"$work/show.bad-offset" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid payload offset trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=payload bounds invalid$' "$work/show.bad-offset"
"$work/busierbox-bad-offset" runtime-config --json >"$work/runtime.bad-offset.json"
python3 - "$work/runtime.bad-offset.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["status"] == "payload bounds invalid"
PY

cp "$work/busierbox" "$work/busierbox-bad-encoding"
python3 - "$work/busierbox-bad-encoding" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"encoding=plain\n"
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("encoding metadata not found")
b[pos:pos + len(needle)] = b"encoding=rot13\n"
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad-encoding" >"$work/show.bad-encoding" 2>&1; then
    printf '%s\n' "artifact-config smoke: unsupported encoding trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=unsupported encoding rot13$' "$work/show.bad-encoding"
"$work/busierbox-bad-encoding" runtime-config --json >"$work/runtime.bad-encoding.json"
python3 - "$work/runtime.bad-encoding.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["encoding"] == "rot13"
assert r["trailer_override"]["status"] == "unsupported encoding"
PY

cp "$work/busierbox" "$work/busierbox-bad-payload-format"
python3 - "$work/busierbox-bad-payload-format" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"payload_format=raw\n"
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("payload_format metadata not found")
b[pos:pos + len(needle)] = b"payload_format=b64\n"
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad-payload-format" >"$work/show.bad-payload-format" 2>&1; then
    printf '%s\n' "artifact-config smoke: unsupported payload format trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=unsupported payload format b64$' "$work/show.bad-payload-format"
"$work/busierbox-bad-payload-format" runtime-config --json >"$work/runtime.bad-payload-format.json"
python3 - "$work/runtime.bad-payload-format.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["status"] == "unsupported payload format"
PY

cp "$artifact" "$work/busierbox-bad-hex-payload"
BB_TRAILER_OBFUSCATION=xor scripts/artifact-config set "$work/busierbox-bad-hex-payload" BB_OPERATOR_SERVER_HOST=192.0.2.46 >/dev/null
python3 - "$work/busierbox-bad-hex-payload" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"ENDMETA\n"
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("trailer payload marker not found")
payload_pos = pos + len(needle)
b[payload_pos:payload_pos + 2] = b"zz"
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad-hex-payload" >"$work/show.bad-hex-payload" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid hex payload trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=invalid hex payload$' "$work/show.bad-hex-payload"
"$work/busierbox-bad-hex-payload" runtime-config --json >"$work/runtime.bad-hex-payload.json"
python3 - "$work/runtime.bad-hex-payload.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["encoding"] == "xor"
assert r["trailer_override"]["status"] == "invalid hex payload"
PY

cp "$artifact" "$work/busierbox-bad-xor-key"
BB_TRAILER_OBFUSCATION=xor scripts/artifact-config set "$work/busierbox-bad-xor-key" BB_OPERATOR_SERVER_HOST=192.0.2.45 >/dev/null
python3 - "$work/busierbox-bad-xor-key" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
b = bytearray(p.read_bytes())
start = len(b) - 4096
needle = b"key_hex="
pos = b.find(needle, start)
if pos < 0:
    raise SystemExit("xor key metadata not found")
pos += len(needle)
b[pos:pos + 2] = b"zz"
p.write_bytes(b)
PY
if scripts/artifact-config show "$work/busierbox-bad-xor-key" >"$work/show.bad-xor-key" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid xor key trailer unexpectedly passed" >&2
    exit 1
fi
grep -q '^trailer_status=invalid xor key$' "$work/show.bad-xor-key"
"$work/busierbox-bad-xor-key" runtime-config --json >"$work/runtime.bad-xor-key.json"
python3 - "$work/runtime.bad-xor-key.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["encoding"] == "xor"
assert r["trailer_override"]["status"] == "invalid xor key"
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

if scripts/artifact-config set "$work/busierbox" BB_NORESIDUE_LEVEL=maximum >"$work/bad-noresidue.out" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid no-residue level was accepted" >&2
    exit 1
fi
grep -q 'invalid value for BB_NORESIDUE_LEVEL' "$work/bad-noresidue.out"

if scripts/artifact-config set "$work/busierbox" BB_RUNTIME_MODE=temporary >"$work/bad-runtime-mode.out" 2>&1; then
    printf '%s\n' "artifact-config smoke: invalid runtime mode was accepted" >&2
    exit 1
fi
grep -q 'invalid value for BB_RUNTIME_MODE' "$work/bad-runtime-mode.out"

if scripts/artifact-config set "$work/busierbox" 'BB_ZERO_ARG_CUSTOM_COMMAND=TOKEN=abc123' >"$work/secret.out" 2>&1; then
    printf '%s\n' "artifact-config smoke: secret-like trailer value was accepted" >&2
    exit 1
fi
grep -q 'refusing secret-like trailer value' "$work/secret.out"

cp "$artifact" "$work/busierbox-secret-runtime"
python3 - "$work/busierbox-secret-runtime" <<'PY'
import hashlib, pathlib, sys
MAGIC = b"BBXCONFIGv1"
TRAILER_SIZE = 4096
p = pathlib.Path(sys.argv[1])
payload = b"BB_ZERO_ARG_CUSTOM_COMMAND=echo TOKEN=abc123\n"
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
p.write_bytes(p.read_bytes() + trailer + b"\0" * (TRAILER_SIZE - len(trailer)))
PY
"$work/busierbox-secret-runtime" runtime-config --json >"$work/runtime.secret.json"
python3 - "$work/runtime.secret.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert r["effective_config_source"] == "compiled"
assert r["trailer_override"]["present"] is True
assert r["trailer_override"]["valid"] is False
assert r["trailer_override"]["status"] == "secret-like trailer value"
assert r["effective_config"]["BB_ZERO_ARG_CUSTOM_COMMAND"] == ""
PY

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
