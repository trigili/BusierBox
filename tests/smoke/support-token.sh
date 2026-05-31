#!/bin/sh
set -eu

bb=${1:-dist/grit-native-full}
tmp=${TMPDIR:-local/tmp}/support-token

[ -x "$bb" ] || {
    printf '%s\n' "support-token: missing executable $bb" >&2
    exit 1
}

rm -rf "$tmp"
mkdir -p "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$bb" manifest --base64 >"$tmp/manifest.b64"
python3 - "$tmp/manifest.b64" <<'PY'
import base64
import json
import sys

token = open(sys.argv[1], encoding="utf-8").read()
doc = json.loads(base64.b64decode(token).decode("utf-8"))
if doc.get("schema") != 1:
    raise SystemExit("manifest base64 did not decode to schema 1 JSON")
PY

"$bb" config-export --json >"$tmp/config-export.json"
python3 -m json.tool "$tmp/config-export.json" >/dev/null
python3 - "$tmp/config-export.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
manifest = doc.get("manifest", {})
payload = manifest.get("payload", {})
if "gdbserver_provider" not in payload:
    raise SystemExit("config-export manifest missing payload.gdbserver_provider")
PY
scripts/lib/config-from-manifest "$tmp/config-export.json" >"$tmp/from-export.conf"
grep -q '^GRIT_PAYLOAD_PRESET=' "$tmp/from-export.conf"
grep -q '^GRIT_GDBSERVER_PROVIDER=' "$tmp/from-export.conf"
grep -q '^GRIT_HEAVY_TOOLS=' "$tmp/from-export.conf"
grep -q '^GRIT_DOTFILE_BASH_MODE=' "$tmp/from-export.conf"
grep -q '^GRIT_RUNTIME_MODE=' "$tmp/from-export.conf"
grep -q '^GRIT_NORESIDUE_LEVEL=' "$tmp/from-export.conf"
grep -q '^GRIT_OPERATOR_SERVER_SSH_PORT=' "$tmp/from-export.conf"
grep -q '^GRIT_RSHELL_SESSION_POLICY=' "$tmp/from-export.conf"
grep -q '^GRIT_RSHELL_RETRY_BACKOFF=' "$tmp/from-export.conf"

"$bb" config-export --base64 >"$tmp/config-export.b64"
python3 - "$tmp/config-export.b64" <<'PY'
import base64
import json
import sys

token = open(sys.argv[1], encoding="utf-8").read()
doc = json.loads(base64.b64decode(token).decode("utf-8"))
if doc.get("kind") != "grit-config-export":
    raise SystemExit("config-export base64 kind mismatch")
PY

"$bb" doctor --support-token >"$tmp/support-token.b64"
python3 - "$tmp/support-token.b64" <<'PY'
import base64
import json
import sys

token = open(sys.argv[1], encoding="utf-8").read()
doc = json.loads(base64.b64decode(token).decode("utf-8"))
if doc.get("kind") != "grit-support-token":
    raise SystemExit("support token kind mismatch")
if "manifest" not in doc:
    raise SystemExit("support token missing manifest")
PY
scripts/lib/config-from-support-token "$(cat "$tmp/support-token.b64")" >"$tmp/from-token.conf"
grep -q '^GRIT_PAYLOAD_PRESET=' "$tmp/from-token.conf"
grep -q '^GRIT_GDBSERVER_PROVIDER=' "$tmp/from-token.conf"
grep -q '^GRIT_HEAVY_TOOLS=' "$tmp/from-token.conf"
grep -q '^GRIT_DOTFILE_BASH_MODE=' "$tmp/from-token.conf"
grep -q '^GRIT_RSHELL_TRANSPORT=' "$tmp/from-token.conf"
grep -q '^GRIT_RSHELL_SESSION_POLICY=' "$tmp/from-token.conf"
grep -q '^GRIT_OPERATOR_REMOTE_FORWARD_PORT=' "$tmp/from-token.conf"
grep -q '^GRIT_RSHELL_AUTHKEYS_MODE=' "$tmp/from-token.conf"

printf '%s\n' "support-token ok"
