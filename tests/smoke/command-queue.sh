#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}

[ -x "$bb" ] || {
    printf '%s\n' "command-queue: missing executable $bb" >&2
    exit 1
}

"$bb" command-queue --help >/dev/null
status_state="${TMPDIR:-/tmp}/busierbox-command-queue-status.$$.state"
rm -f "$status_state"
"$bb" command-queue status --state-file "$status_state" >"${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_enable=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_policy_valid=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_configured_for_polling=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_missing_operator_host=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_would_poll=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_allowed_commands=none$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_allow_arbitrary=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_arbitrary_policy_requested=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_arbitrary_execution_allowed=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_execution_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_executes_commands=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_delivery_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_transport_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_plan_dry_run_only=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_plan_requires_explicit_target_action=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_plan_would_contact_operator=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_plan_queued_command_available=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_plan_operator_supplied_command_execution=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_jitter_pct=0$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_backoff=none$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_max_interval_sec=300$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_daemon_state_present=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_daemon_running=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_stop_status=not_run$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_status_lifecycle=inspect$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_status_would_poll_if_configured=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_poll_lifecycle=single-poll$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_poll_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_once_lifecycle=single-cycle$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_once_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_daemon_lifecycle=long-running$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_daemon_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_stop_lifecycle=stop$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_stop_would_poll_if_configured=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_modes_execute_commands=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_modes_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"

poll_state="${TMPDIR:-/tmp}/busierbox-command-queue-poll.$$.state"
rm -f "$poll_state"
"$bb" command-queue poll --state-file "$poll_state" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; ms=d["mode_summary"]; st=d["daemon_state"]; stop=d["stop_result"]; assert d["enabled"] is False; assert d["dry_run"] is True; assert d["policy_valid"] is True; assert d["policy_errors"] == []; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["arbitrary_policy_requested"] is False; assert d["arbitrary_execution_allowed"] is False; assert d["delivery_supported"] is False; assert d["poll_transport_supported"] is False; assert d["poll_interval_sec"] == 5; assert d["poll_jitter_pct"] == 0; assert d["poll_backoff"] == "none"; assert d["poll_max_interval_sec"] == 300; assert d["queued_command"] is None; assert st["present"] is False; assert st["running"] is False; assert stop["status"] == "not_run"; assert p["mode"] == "poll"; assert p["dry_run_only"] is True; assert p["requires_explicit_target_action"] is True; assert p["would_contact_operator"] is False; assert p["queued_command_available"] is False; assert p["operator_supplied_command_execution"] is False; assert p["execution_supported"] is False; assert p["active_control_channel"] is False; assert m["status"]["selected"] is False; assert m["status"]["requires_operator_host"] is False; assert m["status"]["would_poll_if_configured"] is False; assert m["status"]["lifecycle"] == "inspect"; assert m["poll"]["selected"] is True; assert m["poll"]["requires_operator_host"] is True; assert m["poll"]["would_poll_if_configured"] is True; assert m["poll"]["lifecycle"] == "single-poll"; assert m["once"]["lifecycle"] == "single-cycle"; assert m["daemon"]["lifecycle"] == "long-running"; assert m["stop"]["lifecycle"] == "stop"; assert m["stop"]["requires_operator_host"] is False; assert m["stop"]["would_poll_if_configured"] is False; assert all(v["execution_supported"] is False and v["executes_commands"] is False and v["active_control_channel"] is False and v["operator_supplied_command_execution"] is False for v in m.values()); assert ms["mode_count"] == 5; assert ms["polling_mode_count"] == 3; assert ms["operator_host_required_mode_count"] == 3; assert ms["delivery_supported_mode_count"] == 0; assert ms["result_upload_supported_mode_count"] == 0; assert ms["execution_supported_mode_count"] == 0; assert ms["active_control_channel_mode_count"] == 0; assert ms["operator_supplied_command_execution_mode_count"] == 0; assert s["enabled"] is False; assert s["default_enabled"] is False; assert s["valid"] is True; assert s["error_count"] == 0; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["execution_supported"] is False; assert s["executes_commands"] is False; assert s["active_control_channel"] is False; assert s["safe_disabled_default"] is True'
"$bb" command-queue poll --state-file "$poll_state" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); records=d["mode_records"]; api=d["api_collections"]["mode_records"]; assert len(records) == 5; assert records[1]["mode"] == "poll"; assert records[1]["selected"] is True; assert records[3]["lifecycle"] == "long-running"; assert d["mode_records_by_mode"]["poll"] == [1]; assert d["mode_records_by_lifecycle"]["single-poll"] == [1]; assert d["mode_records_by_would_poll_if_configured"]["true"] == [1,2,3]; assert d["mode_records_by_live_supported"]["true"] == []; assert d["mode_records_by_live_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_execution_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_active_control_channel"]["false"] == [0,1,2,3,4]; assert api["count"] == 5; assert api["summary_key"] == "mode_summary.mode_count"; assert api["count_summary_key"] == "mode_summary.mode_count"; assert api["primary_key"] == "mode"; assert "mode_records_by_lifecycle" in api["indexes"]'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 BB_COMMAND_QUEUE_POLL_BACKOFF=linear BB_COMMAND_QUEUE_POLL_JITTER_PCT=7 BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC=19 "$bb" command-queue daemon --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["poll_backoff"] == "linear"; assert d["poll_jitter_pct"] == 7; assert d["poll_max_interval_sec"] == 19; assert d["max_polls"] == 0'
"$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); m=d["mode_semantics"]; assert d["enabled"] is False; assert d["dry_run"] is False; assert d["would_poll"] is False; assert d["active_control_channel"] is False; assert d["delivery_supported"] is False; assert d["poll_plan"]["active_control_channel"] is False; assert m["poll"]["selected"] is True; assert m["poll"]["would_contact_operator"] is False; assert m["poll"]["delivery_supported"] is False; assert m["poll"]["active_control_channel"] is False; assert all(v["active_control_channel"] is False for v in m.values())'
"$bb" command-queue poll --live >"${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_status=disabled$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_modes_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" command-queue poll --operator-host '' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is True; assert d["would_poll"] is False; assert d["status"] == "missing_operator_host"; assert p["status"] == "missing_operator_host"; assert p["missing_operator_host"] is True; assert p["would_contact_operator"] is False; assert s["enabled"] is True; assert s["valid"] is True; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; ms=d["mode_summary"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is True; assert d["missing_operator_host"] is False; assert d["mode"] == "once"; assert d["status"] == "once_dry_run"; assert d["would_poll"] is True; assert d["endpoint"] == "127.0.0.1:22205"; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["delivery_supported"] is False; assert d["result_upload_supported"] is False; assert d["queued_command"] is None; assert p["mode"] == "once"; assert p["configured_for_polling"] is True; assert p["would_poll"] is True; assert p["would_contact_operator"] is False; assert p["endpoint"] == "127.0.0.1:22205"; assert p["delivery_supported"] is False; assert p["result_upload_supported"] is False; assert p["executes_commands"] is False; assert m["once"]["selected"] is True; assert m["once"]["requires_operator_host"] is True; assert m["once"]["would_poll_if_configured"] is True; assert m["once"]["lifecycle"] == "single-cycle"; assert ms["mode_count"] == 5; assert ms["polling_mode_count"] == 3; assert ms["delivery_supported_mode_count"] == 0; assert ms["active_control_channel_mode_count"] == 0; assert ms["execution_supported_mode_count"] == 0; assert s["configured_for_polling"] is True; assert s["would_poll"] is True; assert s["delivery_supported"] is False; assert s["result_upload_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=custom BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["policy_valid"] is True; assert d["arbitrary_policy_requested"] is True; assert d["arbitrary_execution_allowed"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert s["arbitrary_policy_requested"] is True; assert s["arbitrary_execution_allowed"] is False; assert s["execution_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=maybe BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["enabled"] is False; assert d["policy_valid"] is False; assert "invalid command queue enable value" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["status"] == "invalid_policy"; assert s["valid"] is False; assert s["error_count"] == len(d["policy_errors"]); assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
BB_COMMAND_QUEUE_POLL_BACKOFF=weird "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is False; assert "invalid command queue poll backoff" in d["policy_errors"]; assert d["would_poll"] is False'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["enabled"] is False; assert d["policy_valid"] is False; assert "disabled command queue must keep allowed commands policy none" in d["policy_errors"]; assert d["would_poll"] is False; assert d["status"] == "invalid_policy"; assert s["valid"] is False; assert s["error_count"] == len(d["policy_errors"])'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=allowlist BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon >"${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_policy_valid=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_policy_error=arbitrary command queue execution requires allowed commands policy custom$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_would_poll=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_status=invalid_policy$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon >"${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_policy_valid=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_status=daemon_dry_run$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_would_poll=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_endpoint=127.0.0.1:22205$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_execution_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_executes_commands=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon --live --max-polls 2 --poll-interval-sec 0 --event-log "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; assert d["dry_run"] is False; assert r["attempted"] is True; assert r["attempts"] == 2; assert r["successes"] == 0; assert r["failures"] == 2; assert "requires BB_COMMAND_QUEUE_TLS=no" in r["last_error"]'
python3 - "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" <<'PY'
import json
import sys

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
names = [event["event"] for event in events]
assert names.count("command_queue_poll_attempt") == 2
assert names.count("command_queue_poll_error") == 2
assert "command_queue_poll_shutdown" in names
assert all(event["service"] == "command-queue" for event in events)
assert all(event["details"]["executes_commands"] is False for event in events)
assert all(event["details"]["delivery_supported"] is False for event in events)
PY
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$"
cq_state="${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$.state"
cq_daemon_out="${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$.json"
cq_stop_events="${TMPDIR:-/tmp}/busierbox-command-queue-stop-events.$$.jsonl"
rm -f "$cq_state" "$cq_daemon_out" "$cq_stop_events"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon --live --poll-interval-sec 5 --state-file "$cq_state" --event-log "$cq_stop_events" --json >"$cq_daemon_out" &
cq_daemon_pid=$!
i=0
while [ ! -s "$cq_state" ] && [ "$i" -lt 50 ]; do
    sleep 0.1
    i=$((i + 1))
done
[ -s "$cq_state" ] || {
    kill "$cq_daemon_pid" 2>/dev/null || true
    wait "$cq_daemon_pid" 2>/dev/null || true
    printf '%s\n' "command-queue: daemon state was not written" >&2
    exit 1
}
"$bb" command-queue status --state-file "$cq_state" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); st=d["daemon_state"]; assert st["present"] is True; assert st["valid"] is True; assert st["running"] is True; assert st["ownership_verified"] is True; assert st["pid"] > 1'
"$bb" command-queue stop --state-file "$cq_state" --event-log "$cq_stop_events" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); st=d["daemon_state"]; stop=d["stop_result"]; assert d["mode"] == "stop"; assert stop["attempted"] is True; assert stop["signaled"] is True; assert stop["skipped"] is False; assert st["valid"] is True; assert st["ownership_verified"] is True'
wait "$cq_daemon_pid"
python3 - "$cq_daemon_out" <<'PY'
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["poll_run"]["stopped_by_signal"] is True
PY
python3 - "$cq_stop_events" <<'PY'
import json
import sys

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert any(event["event"] == "command_queue_daemon_stop" for event in events)
assert any(event["event"] == "command_queue_poll_shutdown" and event["details"]["status"] == "signal" for event in events)
PY
rm -f "$cq_state" "$cq_daemon_out" "$cq_stop_events"
port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
cq_cfg="${TMPDIR:-/tmp}/busierbox-command-queue-server.$$.json"
cq_out="${TMPDIR:-/tmp}/busierbox-command-queue-server.$$.out"
cq_err="${TMPDIR:-/tmp}/busierbox-command-queue-server.$$.err"
cq_events="${TMPDIR:-/tmp}/busierbox-command-queue-live-events.$$.jsonl"
python3 - "$cq_cfg" "$port" <<'PY'
import json
import sys
from pathlib import Path

cfg = {
    "listen_host": "127.0.0.1",
    "operator_session_dir": str(Path(sys.argv[1]).with_suffix(".session")),
    "server_state": str(Path(sys.argv[1]).with_suffix(".state.json")),
    "command_queue_file": str(Path(sys.argv[1]).with_suffix(".queue.json")),
    "command_queue_enable": "yes",
    "command_queue_port": sys.argv[2],
    "command_queue_tls": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$cq_cfg" --transport command-queue --timeout 10 --one-shot >"$cq_out" 2>"$cq_err" &
cq_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --event-log "$cq_events" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; ms=d["mode_summary"]; assert d["dry_run"] is False; assert d["status"] == "polling"; assert d["poll_transport_supported"] is True; assert d["delivery_supported"] is True; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert ms["delivery_supported_mode_count"] == 3; assert ms["active_control_channel_mode_count"] == 1; assert ms["execution_supported_mode_count"] == 0; assert r["attempted"] is True; assert r["attempts"] == 1; assert r["successes"] == 1; assert r["failures"] == 0; assert r["last_status"] == "no-command"'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["mode_records_by_live_supported"]["true"] == [1,2,3]; assert d["mode_records_by_active_control_channel"]["true"] == [1]; assert d["mode_records_by_active_control_channel"]["false"] == [0,2,3,4]'
wait "$cq_pid"
grep -q 'command-queue poll no-command' "$cq_out"
python3 - "$cq_events" "$cq_cfg" <<'PY'
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert any(event["event"] == "command_queue_poll_no_command" for event in events)
cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
operator_events = Path(cfg["operator_session_dir"]) / "events.jsonl"
operator = [json.loads(line) for line in operator_events.open(encoding="utf-8")]
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll" for event in operator)
assert any(event["service"] == "command-queue" and event["details"].get("status") == "no-command" for event in operator)
PY
rm -f "$cq_cfg" "$cq_out" "$cq_err" "$cq_events"
queued_port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
queued_cfg="${TMPDIR:-/tmp}/busierbox-command-queue-delivery.$$.json"
queued_out="${TMPDIR:-/tmp}/busierbox-command-queue-delivery.$$.out"
queued_err="${TMPDIR:-/tmp}/busierbox-command-queue-delivery.$$.err"
queued_events="${TMPDIR:-/tmp}/busierbox-command-queue-delivery-events.$$.jsonl"
python3 - "$queued_cfg" "$queued_port" <<'PY'
import json
import sys
from pathlib import Path

cfg = {
    "listen_host": "127.0.0.1",
    "operator_session_dir": str(Path(sys.argv[1]).with_suffix(".session")),
    "server_state": str(Path(sys.argv[1]).with_suffix(".state.json")),
    "command_queue_file": str(Path(sys.argv[1]).with_suffix(".queue.json")),
    "command_queue_enable": "yes",
    "command_queue_port": sys.argv[2],
    "command_queue_tls": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$queued_cfg" --queue-command 'busierbox reality-test --json' >/dev/null
scripts/busierbox-server --config "$queued_cfg" --transport command-queue --timeout 2 >"$queued_out" 2>"$queued_err" &
queued_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$queued_port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --event-log "$queued_events" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; p=d["poll_plan"]; assert d["dry_run"] is False; assert d["status"] == "polling"; assert d["poll_transport_supported"] is True; assert d["delivery_supported"] is True; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["result_upload_supported"] is True; assert p["result_upload_supported"] is True; assert p["queued_command_available"] is True; assert r["queued_command_available"] is True; assert r["execution_decision"] == "rejected"; assert r["attempted"] is True; assert r["attempts"] == 1; assert r["successes"] == 1; assert r["failures"] == 0; assert r["delivered_commands"] == 1; assert r["rejected_commands"] == 1; assert r["result_uploads"] == 1; assert r["result_upload_failures"] == 0; assert r["last_status"] == "delivered-rejected"; assert r["last_error"] == ""; assert r["last_command_id"].startswith("cq-")'
wait "$queued_pid"
grep -q 'command-queue poll delivered' "$queued_out"
python3 - "$queued_events" "$queued_cfg" <<'PY'
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert any(event["event"] == "command_queue_poll_complete" and event["details"]["status"] == "delivered" for event in events)
assert any(event["event"] == "command_queue_execution_decision" and event["details"]["status"] == "rejected" for event in events)
assert any(event["event"] == "command_queue_result_upload" and event["details"]["status"] == "result-uploaded" for event in events)
assert any(event["details"]["delivery_supported"] is True for event in events)
assert all(event["details"]["executes_commands"] is False for event in events)
cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
queue = json.loads(Path(cfg["command_queue_file"]).read_text(encoding="utf-8"))
command = queue["commands"][0]
assert command["status"] == "result-received"
assert command["execution_supported"] is False
assert command["execution_decision"] == "rejected"
assert command["result"]["status"] == "rejected"
assert command["result_output_bytes"] == 0
assert command["result_output_exceeded_limit"] is False
assert command["delivered_at"]
assert command["delivered_to"]
operator_events = Path(cfg["operator_session_dir"]) / "events.jsonl"
operator = [json.loads(line) for line in operator_events.open(encoding="utf-8")]
assert any(event["service"] == "command-queue" and event["event"] == "command_delivered" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_result_received" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_result_upload" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll" and event["details"].get("status") == "delivered" for event in operator)
PY
rm -f "$queued_cfg" "$queued_out" "$queued_err" "$queued_events"
"$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["execution_supported"] is False; assert d["requires_external_writes"] is False; assert d["poll_interval_sec"] == "5"; assert d["poll_jitter_pct"] == "0"; assert d["poll_backoff"] == "none"; assert d["poll_max_interval_sec"] == "300"; assert d["daemon_state_file"].endswith("/run/command-queue-daemon.state"); assert d["daemon_state_file_supported"] is True; assert d["daemon_status_supported"] is True; assert d["daemon_stop_supported"] is True; assert d["result_upload_supported"] is True'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["policy_valid"] is False; assert "disabled command queue must keep allowed commands policy none" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_start"] == []; assert d["would_connect"] == []'
"$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["effective_config"]; p=d["command_queue_policy"]; assert c["BB_COMMAND_QUEUE_ENABLE"] == "no"; assert c["BB_COMMAND_QUEUE_ALLOWED_COMMANDS"] == "none"; assert c["BB_COMMAND_QUEUE_ALLOW_ARBITRARY"] == "no"; assert c["BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"] == "5"; assert c["BB_COMMAND_QUEUE_POLL_JITTER_PCT"] == "0"; assert c["BB_COMMAND_QUEUE_POLL_BACKOFF"] == "none"; assert c["BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC"] == "300"; assert c["BB_COMMAND_QUEUE_MAX_POLLS"] == "0"; assert p["valid"] is True; assert p["errors"] == []; assert p["enabled"] is False; assert p["configured_for_polling"] is False; assert p["missing_operator_host"] is False; assert p["poll_transport_supported"] is True; assert p["live_polling_supported"] is True; assert p["delivery_supported"] is False; assert p["result_upload_supported"] is True; assert p["execution_supported"] is False; assert p["executes_commands"] is False; assert p["active_control_channel"] is False; assert p["operator_supplied_command_execution"] is False; assert p["arbitrary_policy_requested"] is False; assert p["arbitrary_execution_allowed"] is False; assert p["safe_disabled_default"] is True'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["command_queue_policy"]; assert p["valid"] is False; assert p["result_upload_supported"] is True; assert p["execution_supported"] is False; assert p["executes_commands"] is False; assert "disabled command queue must keep allowed commands policy none" in p["errors"]'
"$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["enabled"] == "no"; assert q["policy_valid"] is True; assert q["policy_errors"] == []; assert q["poll_interval_sec"] == "5"; assert q["poll_jitter_pct"] == "0"; assert q["poll_backoff"] == "none"; assert q["poll_max_interval_sec"] == "300"; assert q["max_polls"] == "0"; assert q["daemon_state_file"].endswith("/run/command-queue-daemon.state"); assert q["daemon_state_file_supported"] is True; assert q["daemon_status_supported"] is True; assert q["daemon_stop_supported"] is True; assert q["result_upload_supported"] is True; assert q["executes_commands"] is False; assert q["default_enabled"] is False'
BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes "$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["policy_valid"] is False; assert "disabled command queue must not allow arbitrary execution" in q["policy_errors"]'
"$bb" config-info | grep -q '^effective_command_queue_enable=no$'
"$bb" config-info | grep -q '^effective_command_queue_policy_valid=yes$'
"$bb" config-info | grep -q '^effective_command_queue_poll_interval_sec=5$'
"$bb" config-info | grep -q '^effective_command_queue_poll_jitter_pct=0$'
"$bb" config-info | grep -q '^effective_command_queue_poll_backoff=none$'
"$bb" config-info | grep -q '^effective_command_queue_poll_max_interval_sec=300$'
"$bb" config-info | grep -q '^effective_command_queue_max_polls=0$'
BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes "$bb" config-info | grep -q '^effective_command_queue_policy_error=disabled command queue must not allow arbitrary execution$'

grep -q 'BB_COMMAND_QUEUE_ENABLE="no"' configs/busierbox.conf.example
grep -q 'Advanced / Explicit command queue' scripts/menuconfig
grep -q 'target-side polling for operator-supplied commands' scripts/menuconfig
grep -q 'execute queued commands' docs/command-queue.md
grep -q '`--live` metadata polling' docs/command-queue.md
grep -q 'active_control_channel=false' docs/command-queue.md
grep -q 'BB_COMMAND_QUEUE_ALLOWED_COMMANDS' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_INTERVAL_SEC' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_BACKOFF' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_JITTER_PCT' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_BACKOFF="none"' configs/busierbox.conf.example
grep -q 'invalid command queue allowed commands policy' scripts/package-target
grep -q 'invalid command queue poll backoff' scripts/package-target

printf '%s\n' "command-queue ok"
