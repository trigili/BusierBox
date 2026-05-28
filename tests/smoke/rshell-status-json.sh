#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-/tmp}/busierbox-rshell-status-$$
mkdir "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

mkdir -p "$tmp/guard"
cat >"$tmp/guard/rshell.status" <<'EOF'
state=running
transport=ssh
session_policy=reconnect
session_policy_valid=yes
retry_scope=pre-connect+post-disconnect
pre_connect_retry_count=2
post_disconnect_retry_count=2
stop_after_first_success=no
reconnect_after_disconnect=yes
persistent_lifecycle=no
fresh_session_on_reconnect=yes
session_resume_supported=no
rshell_pid=1234
dropbear_pid=2345
dbclient_pid=3456
started_at=1710000000
last_exit_reason=none
initial_attempts=2
reconnect_attempts=1
connected_once=yes
EOF

BB_RSHELL_RETRY_COUNT=9 BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json --transport ssh >"$tmp/status.json"
python3 -m json.tool "$tmp/status.json" >/dev/null
python3 - "$tmp/status.json" "$tmp/guard" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

for key in [
    "state",
    "transport",
    "encryption",
    "run_mode",
    "session_policy",
    "operator_host",
    "operator_shell_port",
    "operator_ssh_port",
    "remote_forward_port",
    "target_dropbear",
    "authkeys_mode",
    "shell_provider",
    "retry",
    "runtime_config",
    "runtime_counters",
    "zero_arg_autorun",
    "guard_path",
    "pids",
    "log_paths",
    "started_at",
    "last_exit_reason",
    "connect_hint",
    "server_hint",
    "server_listener",
    "connect_model",
]:
    if key not in data:
        raise SystemExit(f"missing rshell status key: {key}")

if data["guard_path"] != sys.argv[2]:
    raise SystemExit("guard path mismatch")
if data["state"] != "running":
    raise SystemExit("recorded state missing")
if data["session_policy"] != "reconnect":
    raise SystemExit("session policy from status file missing")
sem = data.get("session_semantics") or {}
summary = data.get("session_policy_summary") or {}
decisions = data.get("runtime_decisions") or {}
if sem.get("retry_until_first_connection") is not True:
    raise SystemExit("retry-until-first-connection semantic missing")
if sem.get("stop_after_first_success") is not False:
    raise SystemExit("reconnect policy should not stop after first success")
if sem.get("reconnect_after_disconnect") is not True:
    raise SystemExit("reconnect policy should reconnect after disconnect")
if sem.get("persistent_lifecycle") is not False:
    raise SystemExit("reconnect policy should not report persistent lifecycle")
if sem.get("fresh_session_on_reconnect") is not True:
    raise SystemExit("reconnect policy should report fresh sessions on reconnect")
if sem.get("session_resume_supported") is not False:
    raise SystemExit("rshell should not claim session resume")
if summary.get("valid") is not True:
    raise SystemExit("session policy summary should report valid reconnect policy")
if summary.get("retry_scope") != "pre-connect+post-disconnect":
    raise SystemExit("reconnect summary should report pre/post retry scope")
if summary.get("pre_connect_retry_count") != data["retry"].get("pre_connect_count"):
    raise SystemExit("summary pre-connect retry count mismatch")
if summary.get("post_disconnect_retry_count") != data["retry"].get("post_disconnect_count"):
    raise SystemExit("summary post-disconnect retry count mismatch")
if data["retry"].get("pre_connect_count") != "2" or data["retry"].get("post_disconnect_count") != "2":
    raise SystemExit("status JSON should prefer recorded retry counts over current environment")
if summary.get("reconnects_after_disconnect") is not True:
    raise SystemExit("summary should report reconnect after disconnect")
if summary.get("fresh_session_on_reconnect") is not True:
    raise SystemExit("summary should report fresh sessions on reconnect")
if summary.get("session_resume_supported") is not False:
    raise SystemExit("summary should not claim session resume")
if decisions.get("after_success_reconnect_attempt_0") is not True:
    raise SystemExit("reconnect policy should reconnect after successful disconnect attempt 0")
if decisions.get("after_success_reconnect_attempt_1") is not True:
    raise SystemExit("reconnect policy should reconnect after successful disconnect attempt 1 when retry_count=2")
if decisions.get("after_success_reconnect_attempt_2") is not False:
    raise SystemExit("reconnect policy should stop after bounded post-disconnect retry count")
if decisions.get("uses_fresh_sessions") is not True:
    raise SystemExit("reconnect policy should mark post-disconnect attempts as fresh sessions")
if decisions.get("session_resume_supported") is not False:
    raise SystemExit("runtime decisions should not claim session resume")
fields = data.get("fields") or {}
for key, expected in {
    "session_policy_valid": "yes",
    "retry_scope": "pre-connect+post-disconnect",
    "pre_connect_retry_count": "2",
    "post_disconnect_retry_count": "2",
    "stop_after_first_success": "no",
    "reconnect_after_disconnect": "yes",
    "persistent_lifecycle": "no",
    "fresh_session_on_reconnect": "yes",
    "session_resume_supported": "no",
}.items():
    if fields.get(key) != expected:
        raise SystemExit(f"status file semantic field mismatch: {key}")
if data["pids"].get("rshell") != "1234":
    raise SystemExit("rshell pid missing")
if data["pids"].get("dropbear") != "2345":
    raise SystemExit("dropbear pid missing")
if data["pids"].get("dbclient") != "3456":
    raise SystemExit("dbclient pid missing")
if data["started_at"] != "1710000000":
    raise SystemExit("started_at missing")
if data["last_exit_reason"] != "none":
    raise SystemExit("last_exit_reason missing")
counters = data.get("runtime_counters") or {}
if counters.get("initial_attempts") != "2":
    raise SystemExit("initial attempts missing")
if counters.get("reconnect_attempts") != "1":
    raise SystemExit("reconnect attempts missing")
if counters.get("connected_once") is not True:
    raise SystemExit("connected_once counter missing")
if "ssh -p" not in data["connect_hint"]:
    raise SystemExit("connect hint missing")
if not data["operator_ssh_port"]:
    raise SystemExit("operator ssh port missing")
if not data["operator_shell_port"]:
    raise SystemExit("operator shell port missing")
if not data["remote_forward_port"]:
    raise SystemExit("remote forward port missing")
for key in ["count", "interval_sec", "jitter_pct", "backoff", "max_interval_sec", "pre_connect_count", "post_disconnect_count"]:
    if key not in data["retry"]:
        raise SystemExit(f"retry field missing: {key}")
if data["runtime_config"].get("effective_config_source") != "cli":
    raise SystemExit("runtime config cli source missing")
if "trailer_override" not in data["runtime_config"]:
    raise SystemExit("trailer override usage missing")
if ":" not in data["target_dropbear"]:
    raise SystemExit("target dropbear endpoint missing")
if f"--ssh-port {data['operator_ssh_port']}" not in data["server_listener"]:
    raise SystemExit("ssh server listener missing")
if not data["zero_arg_autorun"] and "zero_arg_note" not in data:
    raise SystemExit("zero arg note missing for non-autorun artifact")
PY

BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --transport ssh >"$tmp/status-human.out"
grep -q '^operator_ssh_port=' "$tmp/status-human.out"
grep -q '^remote_forward_port=' "$tmp/status-human.out"
grep -q '^session_policy=' "$tmp/status-human.out"
grep -q '^session_policy_valid=yes$' "$tmp/status-human.out"
grep -q '^retry_scope=pre-connect+post-disconnect$' "$tmp/status-human.out"
grep -q '^retry_until_first_connection=yes$' "$tmp/status-human.out"
grep -q '^session_resume_supported=no$' "$tmp/status-human.out"
grep -q '^pre_connect_retry_count=' "$tmp/status-human.out"
grep -q '^pre_connect_retry_count=2$' "$tmp/status-human.out"
grep -q '^post_disconnect_retry_count=2$' "$tmp/status-human.out"
grep -q '^would_reconnect_after_success_attempt_0=' "$tmp/status-human.out"
grep -q '^would_reconnect_after_success_attempt_1=' "$tmp/status-human.out"
grep -q '^would_reconnect_after_success_attempt_2=' "$tmp/status-human.out"
grep -q '^target_dropbear=' "$tmp/status-human.out"
grep -q '^server_listener=scripts/busierbox-server --transport ssh --ssh-port ' "$tmp/status-human.out"
grep -q '^zero_arg_autorun=' "$tmp/status-human.out"

rm -f "$tmp/guard/rshell.status"
BB_RSHELL_SESSION_POLICY=reconnect BB_RSHELL_RETRY_COUNT=1 BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --transport ssh >"$tmp/status-human-reconnect.out"
grep -q '^session_policy=reconnect$' "$tmp/status-human-reconnect.out"
grep -q '^stop_after_first_success=no$' "$tmp/status-human-reconnect.out"
grep -q '^reconnect_after_disconnect=yes$' "$tmp/status-human-reconnect.out"
grep -q '^fresh_session_on_reconnect=yes$' "$tmp/status-human-reconnect.out"
grep -q '^session_resume_supported=no$' "$tmp/status-human-reconnect.out"
grep -q '^post_disconnect_retry_count=' "$tmp/status-human-reconnect.out"
grep -q '^would_reconnect_after_success_attempt_0=yes$' "$tmp/status-human-reconnect.out"
grep -q '^would_reconnect_after_success_attempt_1=no$' "$tmp/status-human-reconnect.out"

BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json >"$tmp/inactive.json"
python3 -m json.tool "$tmp/inactive.json" >/dev/null
python3 - "$tmp/inactive.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if data["state"] != "inactive":
    raise SystemExit("inactive state missing")
if data["pids"]["rshell"] is not None:
    raise SystemExit("inactive pid should be null")
sem = data.get("session_semantics") or {}
if data["session_policy"] == "single":
    if sem.get("stop_after_first_success") is not True or sem.get("reconnect_after_disconnect") is not False:
        raise SystemExit("inactive single policy semantics mismatch")
elif data["session_policy"] == "reconnect":
    if sem.get("reconnect_after_disconnect") is not True or sem.get("persistent_lifecycle") is not False:
        raise SystemExit("inactive reconnect policy semantics mismatch")
elif data["session_policy"] == "persistent":
    if sem.get("reconnect_after_disconnect") is not True or sem.get("persistent_lifecycle") is not True:
        raise SystemExit("inactive persistent policy semantics mismatch")
else:
    raise SystemExit(f"unexpected inactive session policy: {data['session_policy']}")
if sem.get("session_resume_supported") is not False:
    raise SystemExit("inactive status should not claim session resume")
PY

BB_RSHELL_SESSION_POLICY=single BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json >"$tmp/single.json"
python3 -m json.tool "$tmp/single.json" >/dev/null
python3 - "$tmp/single.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
sem = data.get("session_semantics") or {}
summary = data.get("session_policy_summary") or {}
decisions = data.get("runtime_decisions") or {}
if data["session_policy"] != "single":
    raise SystemExit("env single policy not reflected in status")
if sem.get("stop_after_first_success") is not True:
    raise SystemExit("single policy should stop after first success")
if sem.get("reconnect_after_disconnect") is not False:
    raise SystemExit("single policy should not reconnect after disconnect")
if data["retry"].get("post_disconnect_count") != "0":
    raise SystemExit("single policy should report zero post-disconnect retries")
if summary.get("retry_scope") != "pre-connect":
    raise SystemExit("single policy summary should only report pre-connect retry scope")
if summary.get("stops_after_success") is not True:
    raise SystemExit("single policy summary should report stop after success")
if summary.get("fresh_session_on_reconnect") is not False:
    raise SystemExit("single policy summary should not report fresh reconnect sessions")
if sem.get("session_resume_supported") is not False:
    raise SystemExit("single policy should not claim session resume")
if decisions.get("after_success_reconnect_attempt_0") is not False:
    raise SystemExit("single policy should not reconnect after successful disconnect")
if decisions.get("uses_fresh_sessions") is not False:
    raise SystemExit("single policy should not report fresh reconnect sessions")
PY
BB_RSHELL_SESSION_POLICY=single BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status >"$tmp/status-human-single.out"
grep -q '^session_policy=single$' "$tmp/status-human-single.out"
grep -q '^stop_after_first_success=yes$' "$tmp/status-human-single.out"
grep -q '^reconnect_after_disconnect=no$' "$tmp/status-human-single.out"
grep -q '^persistent_lifecycle=no$' "$tmp/status-human-single.out"
grep -q '^fresh_session_on_reconnect=no$' "$tmp/status-human-single.out"
grep -q '^session_resume_supported=no$' "$tmp/status-human-single.out"
grep -q '^post_disconnect_retry_count=0$' "$tmp/status-human-single.out"

BB_RSHELL_SESSION_POLICY=persistent BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json >"$tmp/persistent.json"
python3 -m json.tool "$tmp/persistent.json" >/dev/null
python3 - "$tmp/persistent.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
sem = data.get("session_semantics") or {}
summary = data.get("session_policy_summary") or {}
decisions = data.get("runtime_decisions") or {}
if data["session_policy"] != "persistent":
    raise SystemExit("env persistent policy not reflected in status")
if sem.get("persistent_lifecycle") is not True:
    raise SystemExit("persistent policy should report persistent lifecycle")
if sem.get("reconnect_after_disconnect") is not True:
    raise SystemExit("persistent policy should reconnect after disconnect")
if sem.get("fresh_session_on_reconnect") is not True:
    raise SystemExit("persistent policy should report fresh sessions")
if data["retry"].get("post_disconnect_count") != "-1":
    raise SystemExit("persistent policy should report unbounded post-disconnect retry")
if summary.get("retry_scope") != "pre-connect+post-disconnect":
    raise SystemExit("persistent policy summary should report pre/post retry scope")
if summary.get("persistent_lifecycle") is not True:
    raise SystemExit("persistent policy summary should report persistent lifecycle")
if summary.get("fresh_session_on_reconnect") is not True:
    raise SystemExit("persistent policy summary should report fresh sessions on reconnect")
if sem.get("session_resume_supported") is not False:
    raise SystemExit("persistent policy should not claim session resume")
if decisions.get("after_success_reconnect_attempt_0") is not True:
    raise SystemExit("persistent policy should reconnect after successful disconnect attempt 0")
if decisions.get("after_success_reconnect_attempt_2") is not True:
    raise SystemExit("persistent policy should keep reconnecting without a post-disconnect retry limit")
if decisions.get("uses_fresh_sessions") is not True:
    raise SystemExit("persistent policy should report fresh sessions on reconnect")
PY

BB_RSHELL_SESSION_POLICY=bogus BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status --json >"$tmp/invalid-policy.json"
python3 -m json.tool "$tmp/invalid-policy.json" >/dev/null
python3 - "$tmp/invalid-policy.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
if data["session_policy"] != "bogus":
    raise SystemExit("invalid policy value not reflected in status")
if data.get("session_policy_valid") is not False:
    raise SystemExit("invalid policy should report session_policy_valid=false")
if "unsupported rshell session policy" not in data.get("session_policy_errors", []):
    raise SystemExit("invalid policy error missing")
sem = data.get("session_semantics") or {}
summary = data.get("session_policy_summary") or {}
decisions = data.get("runtime_decisions") or {}
if summary.get("valid") is not False:
    raise SystemExit("invalid policy summary should report valid=false")
if summary.get("session_resume_supported") is not False:
    raise SystemExit("invalid policy summary should not claim session resume")
if sem.get("session_resume_supported") is not False:
    raise SystemExit("invalid policy should not claim session resume")
if decisions.get("after_success_reconnect_attempt_0") is not False:
    raise SystemExit("invalid policy should not reconnect after successful disconnect")
PY
BB_RSHELL_SESSION_POLICY=bogus BUSIERBOX_AUTORUN_GUARD_PATH="$tmp/guard" "$bb" rshell status >"$tmp/invalid-policy.txt"
grep -q '^session_policy_valid=no$' "$tmp/invalid-policy.txt"
grep -q '^session_policy_error=unsupported rshell session policy$' "$tmp/invalid-policy.txt"

printf '%s\n' "rshell-status-json ok"
