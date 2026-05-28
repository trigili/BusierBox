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
grep -q '^command_queue_execution_mode=metadata-only$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_metadata_only_default=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
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
"$bb" command-queue poll --state-file "$poll_state" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; ms=d["mode_summary"]; st=d["daemon_state"]; stop=d["stop_result"]; assert d["enabled"] is False; assert d["dry_run"] is True; assert d["policy_valid"] is True; assert d["policy_errors"] == []; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["execution_mode"] == "metadata-only"; assert d["metadata_only_default"] is True; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["arbitrary_policy_requested"] is False; assert d["arbitrary_execution_allowed"] is False; assert d["delivery_supported"] is False; assert d["poll_transport_supported"] is False; assert d["poll_interval_sec"] == 5; assert d["poll_jitter_pct"] == 0; assert d["poll_backoff"] == "none"; assert d["poll_max_interval_sec"] == 300; assert d["queued_command"] is None; assert st["present"] is False; assert st["running"] is False; assert stop["status"] == "not_run"; assert p["mode"] == "poll"; assert p["dry_run_only"] is True; assert p["requires_explicit_target_action"] is True; assert p["would_contact_operator"] is False; assert p["queued_command_available"] is False; assert p["operator_supplied_command_execution"] is False; assert p["execution_supported"] is False; assert p["active_control_channel"] is False; assert m["status"]["selected"] is False; assert m["status"]["requires_operator_host"] is False; assert m["status"]["would_poll_if_configured"] is False; assert m["status"]["lifecycle"] == "inspect"; assert m["poll"]["selected"] is True; assert m["poll"]["requires_operator_host"] is True; assert m["poll"]["would_poll_if_configured"] is True; assert m["poll"]["lifecycle"] == "single-poll"; assert m["once"]["lifecycle"] == "single-cycle"; assert m["daemon"]["lifecycle"] == "long-running"; assert m["stop"]["lifecycle"] == "stop"; assert m["stop"]["requires_operator_host"] is False; assert m["stop"]["would_poll_if_configured"] is False; assert all(v["execution_supported"] is False and v["executes_commands"] is False and v["active_control_channel"] is False and v["operator_supplied_command_execution"] is False for v in m.values()); assert ms["mode_count"] == 5; assert ms["polling_mode_count"] == 3; assert ms["operator_host_required_mode_count"] == 3; assert ms["delivery_supported_mode_count"] == 0; assert ms["result_upload_supported_mode_count"] == 0; assert ms["execution_supported_mode_count"] == 0; assert ms["active_control_channel_mode_count"] == 0; assert ms["operator_supplied_command_execution_mode_count"] == 0; assert s["execution_mode"] == "metadata-only"; assert s["metadata_only_default"] is True; assert s["enabled"] is False; assert s["default_enabled"] is False; assert s["valid"] is True; assert s["error_count"] == 0; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["execution_supported"] is False; assert s["executes_commands"] is False; assert s["active_control_channel"] is False; assert s["safe_disabled_default"] is True'
"$bb" command-queue poll --state-file "$poll_state" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); records=d["mode_records"]; api=d["api_collections"]["mode_records"]; assert len(records) == 5; assert records[1]["mode"] == "poll"; assert records[1]["selected"] is True; assert records[3]["lifecycle"] == "long-running"; assert d["mode_records_by_mode"]["poll"] == [1]; assert d["mode_records_by_lifecycle"]["single-poll"] == [1]; assert d["mode_records_by_would_poll_if_configured"]["true"] == [1,2,3]; assert d["mode_records_by_live_supported"]["true"] == []; assert d["mode_records_by_live_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_delivery_supported"]["true"] == []; assert d["mode_records_by_delivery_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_result_upload_supported"]["true"] == []; assert d["mode_records_by_result_upload_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_execution_supported"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_active_control_channel"]["false"] == [0,1,2,3,4]; assert d["mode_records_by_operator_supplied_command_execution"]["false"] == [0,1,2,3,4]; assert api["count"] == 5; assert api["summary_key"] == "mode_summary.mode_count"; assert api["count_summary_key"] == "mode_summary.mode_count"; assert api["primary_key"] == "mode"; assert "mode_records_by_lifecycle" in api["indexes"]; assert "mode_records_by_delivery_supported" in api["indexes"]; assert "mode_records_by_result_upload_supported" in api["indexes"]; assert "mode_records_by_operator_supplied_command_execution" in api["indexes"]'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 BB_COMMAND_QUEUE_POLL_BACKOFF=linear BB_COMMAND_QUEUE_POLL_JITTER_PCT=7 BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC=19 "$bb" command-queue daemon --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["poll_backoff"] == "linear"; assert d["poll_jitter_pct"] == 7; assert d["poll_max_interval_sec"] == 19; assert d["max_polls"] == 0'
"$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); m=d["mode_semantics"]; assert d["enabled"] is False; assert d["dry_run"] is False; assert d["would_poll"] is False; assert d["active_control_channel"] is False; assert d["delivery_supported"] is False; assert d["poll_plan"]["active_control_channel"] is False; assert m["poll"]["selected"] is True; assert m["poll"]["would_contact_operator"] is False; assert m["poll"]["delivery_supported"] is False; assert m["poll"]["active_control_channel"] is False; assert all(v["active_control_channel"] is False for v in m.values())'
"$bb" command-queue poll --live >"${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_status=disabled$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
grep -q '^command_queue_modes_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-disabled-live.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" command-queue poll --operator-host '' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is True; assert d["would_poll"] is False; assert d["status"] == "missing_operator_host"; assert p["status"] == "missing_operator_host"; assert p["missing_operator_host"] is True; assert p["would_contact_operator"] is False; assert s["enabled"] is True; assert s["valid"] is True; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is False; assert "enabled command queue requires BB_COMMAND_QUEUE_TOKEN when token requirement is yes" in d["policy_errors"]; assert d["token_required"] is True; assert d["token_configured"] is False; assert d["would_poll"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TOKEN=smoke-token BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is True; assert d["token_required"] is True; assert d["token_configured"] is True; assert d["would_poll"] is True'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; ms=d["mode_summary"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is True; assert d["missing_operator_host"] is False; assert d["mode"] == "once"; assert d["status"] == "once_dry_run"; assert d["would_poll"] is True; assert d["endpoint"] == "127.0.0.1:22205"; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["delivery_supported"] is False; assert d["result_upload_supported"] is False; assert d["queued_command"] is None; assert p["mode"] == "once"; assert p["configured_for_polling"] is True; assert p["would_poll"] is True; assert p["would_contact_operator"] is False; assert p["endpoint"] == "127.0.0.1:22205"; assert p["delivery_supported"] is False; assert p["result_upload_supported"] is False; assert p["executes_commands"] is False; assert m["once"]["selected"] is True; assert m["once"]["requires_operator_host"] is True; assert m["once"]["would_poll_if_configured"] is True; assert m["once"]["lifecycle"] == "single-cycle"; assert ms["mode_count"] == 5; assert ms["polling_mode_count"] == 3; assert ms["delivery_supported_mode_count"] == 0; assert ms["active_control_channel_mode_count"] == 0; assert ms["execution_supported_mode_count"] == 0; assert s["configured_for_polling"] is True; assert s["would_poll"] is True; assert s["delivery_supported"] is False; assert s["result_upload_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=custom BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["policy_valid"] is True; assert d["arbitrary_policy_requested"] is True; assert d["arbitrary_execution_allowed"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert s["arbitrary_policy_requested"] is True; assert s["arbitrary_execution_allowed"] is False; assert s["execution_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=maybe BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["enabled"] is False; assert d["policy_valid"] is False; assert "invalid command queue enable value" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["status"] == "invalid_policy"; assert s["valid"] is False; assert s["error_count"] == len(d["policy_errors"]); assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
BB_COMMAND_QUEUE_POLL_BACKOFF=weird "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is False; assert "invalid command queue poll backoff" in d["policy_errors"]; assert d["would_poll"] is False'
BB_COMMAND_QUEUE_EXECUTION=execute "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is False; assert "disabled command queue must keep execution mode metadata-only" in d["policy_errors"]; assert d["would_poll"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=none BB_COMMAND_QUEUE_EXECUTION=execute BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["policy_valid"] is False; assert "command queue execution mode execute requires a non-none allowed commands policy" in d["policy_errors"]; assert d["execution_mode"] == "execute"'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["enabled"] is False; assert d["policy_valid"] is False; assert "disabled command queue must keep allowed commands policy none" in d["policy_errors"]; assert d["would_poll"] is False; assert d["status"] == "invalid_policy"; assert s["valid"] is False; assert s["error_count"] == len(d["policy_errors"])'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=allowlist BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon >"${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_policy_valid=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_policy_error=arbitrary command queue execution requires allowed commands policy custom$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_would_poll=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
grep -q '^command_queue_status=invalid_policy$' "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-invalid.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon >"${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_policy_valid=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_status=daemon_dry_run$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_would_poll=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_endpoint=127.0.0.1:22205$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_execution_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_executes_commands=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$"
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon --live --max-polls 2 --poll-interval-sec 0 --event-log "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; assert d["dry_run"] is False; assert r["attempted"] is True; assert r["attempts"] == 2; assert r["successes"] == 0; assert r["failures"] == 2; assert "requires BB_COMMAND_QUEUE_TLS=no" in r["last_error"]; assert r["event_count"] == 5; assert r["event_warning_count"] == 2; assert r["event_info_count"] == 3; assert r["event_counts_by_event"]["command_queue_poll_attempt"] == 2; assert r["event_counts_by_event"]["command_queue_poll_error"] == 2; assert r["event_counts_by_event"]["command_queue_poll_shutdown"] == 1; assert r["event_counts_by_level"]["warning"] == 2'
python3 - "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" <<'PY'
import json
import sys

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
names = [event["event"] for event in events]
assert all(event.get("id", "").startswith("cqevt-") for event in events)
assert all(event.get("session", None) == "" for event in events)
assert all("remote" in event for event in events)
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
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon --live --poll-interval-sec 5 --state-file "$cq_state" --event-log "$cq_stop_events" --json >"$cq_daemon_out" &
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
assert all(event.get("id", "").startswith("cqevt-") for event in events)
assert all(event.get("session", None) == "" for event in events)
assert all("remote" in event for event in events)
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
    "command_queue_require_token": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$cq_cfg" --transport command-queue --timeout 10 --one-shot >"$cq_out" 2>"$cq_err" &
cq_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --event-log "$cq_events" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; ms=d["mode_summary"]; assert d["dry_run"] is False; assert d["status"] == "polling"; assert d["poll_transport_supported"] is True; assert d["delivery_supported"] is True; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert ms["delivery_supported_mode_count"] == 3; assert ms["active_control_channel_mode_count"] == 1; assert ms["execution_supported_mode_count"] == 0; assert r["attempted"] is True; assert r["attempts"] == 1; assert r["successes"] == 1; assert r["failures"] == 0; assert r["last_status"] == "no-command"; assert r["event_count"] == 3; assert r["event_warning_count"] == 0; assert r["event_counts_by_event"]["command_queue_poll_attempt"] == 1; assert r["event_counts_by_event"]["command_queue_poll_no_command"] == 1; assert r["event_counts_by_event"]["command_queue_poll_shutdown"] == 1'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); api=d["api_collections"]["mode_records"]; assert d["mode_records_by_live_supported"]["true"] == [1,2,3]; assert d["mode_records_by_delivery_supported"]["true"] == [1,2,3]; assert d["mode_records_by_result_upload_supported"]["true"] == [1,2,3]; assert d["mode_records_by_active_control_channel"]["true"] == [1]; assert d["mode_records_by_active_control_channel"]["false"] == [0,2,3,4]; assert "mode_records_by_delivery_supported" in api["indexes"]; assert "mode_records_by_result_upload_supported" in api["indexes"]'
wait "$cq_pid"
grep -q 'command-queue poll no-command' "$cq_out"
python3 - "$cq_events" "$cq_cfg" <<'PY'
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert all(event.get("id", "").startswith("cqevt-") for event in events)
assert all(event.get("session", None) == "" for event in events)
assert all("remote" in event for event in events)
assert any(event["event"] == "command_queue_poll_no_command" for event in events)
assert all(event["details"]["delivery_supported"] is True for event in events)
assert all(event["details"]["result_upload_supported"] is True for event in events)
assert all(event["details"]["executes_commands"] is False for event in events)
cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
operator_events = Path(cfg["operator_session_dir"]) / "events.jsonl"
operator = [json.loads(line) for line in operator_events.open(encoding="utf-8")]
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll_no_command" and event["details"].get("status") == "no-command" for event in operator)
PY
rm -f "$cq_cfg" "$cq_out" "$cq_err" "$cq_events"
token_port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
token_cfg="${TMPDIR:-/tmp}/busierbox-command-queue-token.$$.json"
token_out="${TMPDIR:-/tmp}/busierbox-command-queue-token.$$.out"
token_err="${TMPDIR:-/tmp}/busierbox-command-queue-token.$$.err"
python3 - "$token_cfg" "$token_port" <<'PY'
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
    "command_queue_require_token": "yes",
    "command_queue_token": "server-token",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$token_cfg" --transport command-queue --timeout 10 --one-shot >"$token_out" 2>"$token_err" &
token_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_TOKEN=wrong-token BB_COMMAND_QUEUE_PORT="$token_port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; assert d["policy_valid"] is True; assert r["attempted"] is True; assert r["failures"] == 1; assert r["last_status"] == "error"; assert "unexpected poll response" in r["last_error"]'
wait "$token_pid"
grep -q 'command-queue poll rejected' "$token_out"
python3 - "$token_cfg" <<'PY'
import json
import sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
events = [
    json.loads(line)
    for line in (Path(cfg["operator_session_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
]
assert any(event.get("service") == "command-queue" and event.get("event") == "command_queue_poll" and event.get("details", {}).get("status") == "rejected" for event in events)
assert any(event.get("service") == "command-queue" and event.get("event") == "command_queue_poll_rejected" and event.get("details", {}).get("reason") == "invalid token" for event in events)
PY
scripts/busierbox-server --config "$token_cfg" --transport command-queue --timeout 10 --one-shot >"$token_out" 2>"$token_err" &
token_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_TOKEN=server-token BB_COMMAND_QUEUE_PORT="$token_port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; assert d["policy_valid"] is True; assert d["token_configured"] is True; assert r["attempted"] is True; assert r["successes"] == 1; assert r["last_status"] == "no-command"'
wait "$token_pid"
rm -f "$token_cfg" "$token_out" "$token_err"
bad_port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
bad_cfg="${TMPDIR:-/tmp}/busierbox-command-queue-bad.$$.json"
bad_out="${TMPDIR:-/tmp}/busierbox-command-queue-bad.$$.out"
bad_err="${TMPDIR:-/tmp}/busierbox-command-queue-bad.$$.err"
python3 - "$bad_cfg" "$bad_port" <<'PY'
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
    "command_queue_require_token": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$bad_cfg" --transport command-queue --timeout 10 --one-shot >"$bad_out" 2>"$bad_err" &
bad_pid=$!
sleep 0.5
python3 - "$bad_port" <<'PY'
import socket
import sys

with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5) as sock:
    sock.sendall(b"bad-request\r\n\r\n")
    try:
        sock.recv(1024)
    except OSError:
        pass
PY
wait "$bad_pid"
grep -q 'command-queue poll failed: malformed HTTP request' "$bad_err"
python3 - "$bad_cfg" <<'PY'
import json
import sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
events = [
    json.loads(line)
    for line in (Path(cfg["operator_session_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
]
assert any(event.get("service") == "command-queue" and event.get("event") == "command_queue_poll" and event.get("details", {}).get("status") == "error" for event in events)
assert any(event.get("service") == "command-queue" and event.get("event") == "command_queue_poll_error" and event.get("level") == "error" and event.get("details", {}).get("reason") == "malformed HTTP request" for event in events)
assert any(event.get("service") == "command-queue" and event.get("event") == "request_error" for event in events)
PY
rm -f "$bad_cfg" "$bad_out" "$bad_err"
split_port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
split_ready="${TMPDIR:-/tmp}/busierbox-command-queue-split.$$.ready"
split_seen="${TMPDIR:-/tmp}/busierbox-command-queue-split.$$.seen"
rm -f "$split_ready" "$split_seen"
python3 - "$split_port" "$split_ready" "$split_seen" <<'PY' &
import json
import socket
import sys
import time
from pathlib import Path

port = int(sys.argv[1])
ready = Path(sys.argv[2])
seen = Path(sys.argv[3])

def read_http(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    headers, _, body = data.partition(b"\r\n\r\n")
    content_length = 0
    for line in headers.decode("iso-8859-1", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
    while len(body) < content_length:
        chunk = conn.recv(4096)
        if not chunk:
            break
        body += chunk
    return headers.decode("iso-8859-1", errors="replace"), body

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port))
server.listen(2)
ready.write_text("ready\n", encoding="utf-8")

poll, _ = server.accept()
with poll:
    read_http(poll)
    body = json.dumps({
        "schema": 1,
        "id": "cq-split-response",
        "command": "busierbox list",
        "timeout_sec": 7,
        "max_output_bytes": 321,
    }).encode("utf-8")
    head = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"X-BusierBox-Command-Id: cq-split-response\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
    )
    poll.sendall(head[:23])
    time.sleep(0.05)
    poll.sendall(head[23:])
    time.sleep(0.05)
    poll.sendall(body[:11])
    time.sleep(0.05)
    poll.sendall(body[11:])

result, _ = server.accept()
with result:
    headers, body = read_http(result)
    if b"cq-split-response" not in body:
        raise SystemExit("result upload did not include command id")
    seen.write_text(headers + "\n" + body.decode("utf-8", errors="replace"), encoding="utf-8")
    result.sendall(b"HTTP/1.1 2")
    time.sleep(0.05)
    result.sendall(b"00 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\nok\n")
server.close()
PY
split_pid=$!
i=0
while [ ! -s "$split_ready" ] && [ "$i" -lt 50 ]; do
    sleep 0.1
    i=$((i + 1))
done
[ -s "$split_ready" ] || {
    kill "$split_pid" 2>/dev/null || true
    wait "$split_pid" 2>/dev/null || true
    printf '%s\n' "command-queue: split-response test server did not start" >&2
    exit 1
}
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$split_port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --json | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d["poll_run"]; q=d["queued_command"]; assert r["attempted"] is True; assert r["successes"] == 1; assert r["failures"] == 0; assert r["delivered_commands"] == 1; assert r["result_uploads"] == 1; assert r["last_command_id"] == "cq-split-response"; assert r["last_command"] == "busierbox list"; assert r["last_timeout_sec"] == 7; assert r["last_max_output_bytes"] == 321; assert q["id"] == "cq-split-response"; assert q["command"] == "busierbox list"; assert q["timeout_sec"] == 7; assert q["max_output_bytes"] == 321'
wait "$split_pid"
grep -q 'cq-split-response' "$split_seen"
rm -f "$split_ready" "$split_seen"
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
    "command_queue_require_token": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$queued_cfg" --queue-command 'busierbox reality-test --json' >/dev/null
scripts/busierbox-server --config "$queued_cfg" --transport command-queue --timeout 2 >"$queued_out" 2>"$queued_err" &
queued_pid=$!
sleep 0.5
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_REQUIRE_TOKEN=no BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_COMMAND_QUEUE_TLS=no BB_COMMAND_QUEUE_PORT="$queued_port" BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --live --event-log "$queued_events" --json | python3 -c 'import hashlib,json,sys; d=json.load(sys.stdin); expected=hashlib.sha256(b"busierbox reality-test --json").hexdigest(); r=d["poll_run"]; p=d["poll_plan"]; q=d["queued_command"]; assert d["dry_run"] is False; assert d["status"] == "polling"; assert d["poll_transport_supported"] is True; assert d["delivery_supported"] is True; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["result_upload_supported"] is True; assert p["result_upload_supported"] is True; assert p["queued_command_available"] is True; assert q["id"].startswith("cq-"); assert q["command"] == "busierbox reality-test --json"; assert q["command_sha256"] == expected; assert q["timeout_sec"] == 30; assert q["max_output_bytes"] == 65536; assert q["execution_supported"] is False; assert q["executes_commands"] is False; assert r["queued_command_available"] is True; assert r["execution_decision"] == "rejected"; assert r["attempted"] is True; assert r["attempts"] == 1; assert r["successes"] == 1; assert r["failures"] == 0; assert r["delivered_commands"] == 1; assert r["rejected_commands"] == 1; assert r["result_uploads"] == 1; assert r["result_upload_failures"] == 0; assert r["last_status"] == "delivered-rejected"; assert r["last_error"] == ""; assert r["last_command_id"] == q["id"]; assert r["last_command_sha256"] == expected; assert r["last_command"] == q["command"]; assert r["last_timeout_sec"] == 30; assert r["last_max_output_bytes"] == 65536; assert r["event_count"] == 5; assert r["event_info_count"] == 4; assert r["event_warning_count"] == 1; assert r["event_counts_by_event"]["command_queue_poll_attempt"] == 1; assert r["event_counts_by_event"]["command_queue_poll_complete"] == 1; assert r["event_counts_by_event"]["command_queue_execution_decision"] == 1; assert r["event_counts_by_event"]["command_queue_result_upload"] == 1; assert r["event_counts_by_event"]["command_queue_poll_shutdown"] == 1'
wait "$queued_pid"
grep -q 'command-queue poll delivered' "$queued_out"
python3 - "$queued_events" "$queued_cfg" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
queue = json.loads(Path(cfg["command_queue_file"]).read_text(encoding="utf-8"))
command = queue["commands"][0]
expected_sha = hashlib.sha256(command["command"].encode("utf-8")).hexdigest()
assert all(event.get("id", "").startswith("cqevt-") for event in events)
assert all(event.get("session", None) == "" for event in events)
assert all("remote" in event for event in events)
assert any(event["event"] == "command_queue_poll_complete" and event["details"]["status"] == "delivered" for event in events)
assert any(event["event"] == "command_queue_execution_decision" and event["details"]["status"] == "rejected" for event in events)
assert any(event["event"] == "command_queue_result_upload" and event["details"]["status"] == "result-uploaded" for event in events)
for event in events:
    if event["event"] in {"command_queue_poll_complete", "command_queue_execution_decision", "command_queue_result_upload"}:
        assert event["details"]["command_id"] == command["id"]
        assert event["details"]["command_sha256"] == expected_sha
        assert event["details"]["command"] == command["command"]
        assert event["details"]["timeout_sec"] == 30
        assert event["details"]["max_output_bytes"] == 65536
assert any(event["details"]["delivery_supported"] is True for event in events)
assert all(event["details"]["executes_commands"] is False for event in events)
assert command["status"] == "result-received"
assert command["execution_supported"] is False
assert command["execution_decision"] == "rejected"
queue_policy = command["queue_policy_snapshot"]
delivery_policy = command["delivery_policy_snapshot"]
assert queue_policy["enabled"] is True
assert queue_policy["allowed_commands"] == "busierbox-only"
assert queue_policy["execution_mode"] == "metadata-only"
assert queue_policy["execution_supported"] is False
assert queue_policy["executes_commands"] is False
assert queue_policy["active_control_channel"] is False
assert delivery_policy["enabled"] is True
assert delivery_policy["valid"] is True
assert delivery_policy["delivery_supported"] is True
assert delivery_policy["result_upload_supported"] is True
assert delivery_policy["execution_supported"] is False
assert delivery_policy["executes_commands"] is False
assert delivery_policy["active_control_channel"] is True
assert delivery_policy["operator_queue_records_only"] is False
assert delivery_policy["delivery_mode"] == "metadata-only"
assert delivery_policy["arbitrary_execution_allowed"] is False
assert command["delivery_supported"] is True
assert command["result_upload_supported"] is True
assert command["result"]["status"] == "rejected"
assert command["result_output_bytes"] == 0
assert command["result_output_exceeded_limit"] is False
assert command["delivered_at"]
assert command["delivered_to"]
operator_events = Path(cfg["operator_session_dir"]) / "events.jsonl"
operator = [json.loads(line) for line in operator_events.open(encoding="utf-8")]
assert any(event["service"] == "command-queue" and event["event"] == "command_delivered" and event["details"]["delivery_supported"] is True and event["details"]["result_upload_supported"] is True and event["details"]["policy_snapshot"]["delivery_supported"] is True and event["details"]["policy_snapshot"]["execution_supported"] is False for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll" and event["details"].get("command_sha256") == expected_sha for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll_delivered" and event["details"].get("command_sha256") == expected_sha for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_result_received" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_result_upload" for event in operator)
assert any(event["service"] == "command-queue" and event["event"] == "command_queue_poll" and event["details"].get("status") == "delivered" for event in operator)
PY
scripts/busierbox-server --config "$queued_cfg" --json-command-queue | python3 -c 'import json,sys; q=json.load(sys.stdin)["command_queue"]; commands=q["commands"]; assert len(commands) == 1; command_id=commands[0]["id"]; assert q["execution_decision_counts"]["rejected"] == 1; assert q["commands_by_execution_decision"]["rejected"][0]["id"] == command_id'
queued_status_file="${TMPDIR:-/tmp}/busierbox-command-queue-status.$$.json"
scripts/busierbox-server --config "$queued_cfg" --json-status >"$queued_status_file"
python3 - "$queued_status_file" <<'PY'
import hashlib
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
q = d["command_queue"]
summary = d["summary"]
api = d["api_collections"]["command_queue_commands"]
events_api = d["api_collections"]["events"]
commands = q["commands"]
assert len(commands) == 1
command_id = commands[0]["id"]
command_sha = hashlib.sha256(commands[0]["command"].encode("utf-8")).hexdigest()
assert commands[0]["command_sha256"] == command_sha
assert summary["command_queue_execution_decision_counts"]["rejected"] == 1
assert summary["command_queue_queue_policy_enabled_counts"]["true"] == 1
assert summary["command_queue_queue_policy_valid_counts"]["true"] == 1
assert summary["command_queue_queue_policy_execution_mode_counts"]["metadata-only"] == 1
assert summary["command_queue_queue_policy_allowed_commands_counts"]["busierbox-only"] == 1
assert summary["command_queue_delivery_policy_enabled_counts"]["true"] == 1
assert summary["command_queue_delivery_policy_valid_counts"]["true"] == 1
assert summary["command_queue_delivery_policy_execution_mode_counts"]["metadata-only"] == 1
assert summary["command_queue_delivery_policy_delivery_supported_counts"]["true"] == 1
assert summary["command_queue_delivery_policy_result_upload_supported_counts"]["true"] == 1
assert summary["command_queue_delivery_policy_active_control_channel_counts"]["true"] == 1
assert q["commands_by_execution_decision"]["rejected"][0]["id"] == command_id
assert q["commands_by_queue_policy_enabled"]["true"][0]["id"] == command_id
assert q["commands_by_queue_policy_valid"]["true"][0]["id"] == command_id
assert q["commands_by_queue_policy_execution_mode"]["metadata-only"][0]["id"] == command_id
assert q["commands_by_queue_policy_allowed_commands"]["busierbox-only"][0]["id"] == command_id
assert q["commands_by_delivery_policy_enabled"]["true"][0]["id"] == command_id
assert q["commands_by_delivery_policy_valid"]["true"][0]["id"] == command_id
assert q["commands_by_delivery_policy_execution_mode"]["metadata-only"][0]["id"] == command_id
assert q["commands_by_delivery_policy_delivery_supported"]["true"][0]["id"] == command_id
assert q["commands_by_delivery_policy_result_upload_supported"]["true"][0]["id"] == command_id
assert q["commands_by_delivery_policy_active_control_channel"]["true"][0]["id"] == command_id
assert d["commands_by_queue_policy_execution_mode"]["metadata-only"][0]["id"] == command_id
assert d["commands_by_delivery_policy_valid"]["true"][0]["id"] == command_id
assert d["commands_by_delivery_policy_delivery_supported"]["true"][0]["id"] == command_id
assert d["commands_by_delivery_policy_result_upload_supported"]["true"][0]["id"] == command_id
assert d["commands_by_delivery_policy_active_control_channel"]["true"][0]["id"] == command_id
assert any(event["event"] == "command_queue_result_upload" for event in d["events_by_detail_command_sha256"][command_sha])
assert d["events_by_event_detail_command_sha256"][f"command_queue_poll:{command_sha}"][0]["details"]["status"] == "delivered"
assert d["events_by_service_detail_command_sha256"][f"command-queue:{command_sha}"]
assert "commands_by_execution_decision" in api["indexes"]
assert "commands_by_queue_policy_execution_mode" in api["indexes"]
assert "commands_by_delivery_policy_valid" in api["indexes"]
assert "commands_by_delivery_policy_delivery_supported" in api["indexes"]
assert "commands_by_delivery_policy_result_upload_supported" in api["indexes"]
assert "commands_by_delivery_policy_active_control_channel" in api["indexes"]
assert "events_by_detail_command_sha256" in events_api["indexes"]
assert "events_by_event_detail_command_sha256" in events_api["indexes"]
assert "events_by_service_detail_command_sha256" in events_api["indexes"]
PY
rm -f "$queued_status_file"
queued_text_file="${TMPDIR:-/tmp}/busierbox-command-queue-status.$$.txt"
scripts/busierbox-server --config "$queued_cfg" --list-command-queue >"$queued_text_file"
grep -q '^  delivery_policy_counts: .*delivery_supported=true=1.*result_upload_supported=true=1.*active_control_channel=true=1' "$queued_text_file"
grep -q '^  delivery_policy: enabled=yes valid=yes execution_mode=metadata-only delivery_supported=yes result_upload_supported=yes active_control_channel=yes$' "$queued_text_file"
rm -f "$queued_text_file"
rm -f "$queued_cfg" "$queued_out" "$queued_err" "$queued_events"
term_port=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
term_cfg="${TMPDIR:-/tmp}/busierbox-command-queue-term.$$.json"
term_out="${TMPDIR:-/tmp}/busierbox-command-queue-term.$$.out"
term_err="${TMPDIR:-/tmp}/busierbox-command-queue-term.$$.err"
python3 - "$term_cfg" "$term_port" <<'PY'
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
    "command_queue_require_token": "no",
    "command_queue_allowed_commands": "busierbox-only",
    "command_queue_allow_arbitrary": "no",
}
Path(sys.argv[1]).write_text(json.dumps(cfg), encoding="utf-8")
PY
scripts/busierbox-server --config "$term_cfg" --transport command-queue --timeout 20 >"$term_out" 2>"$term_err" &
term_pid=$!
python3 - "$term_cfg" <<'PY'
import json
import sys
import time
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
state_path = Path(cfg["server_state"])
for _ in range(50):
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    service = (state.get("services") or {}).get("command-queue") or {}
    if service.get("status") == "listening":
        break
    time.sleep(0.1)
else:
    raise SystemExit("command-queue SIGTERM fixture did not reach listening state")
PY
kill -TERM "$term_pid"
term_rc=0
wait "$term_pid" || term_rc=$?
case "$term_rc" in
    0|143) ;;
    *) printf '%s\n' "command-queue SIGTERM listener exited with $term_rc" >&2; exit 1 ;;
esac
if grep -q 'Traceback' "$term_err"; then
    printf '%s\n' "command-queue SIGTERM listener tracebacked" >&2
    cat "$term_err" >&2
    exit 1
fi
python3 - "$term_cfg" <<'PY'
import json
import sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
events = [
    json.loads(line)
    for line in (Path(cfg["operator_session_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
]
if not any(event.get("service") == "command-queue" and event.get("event") == "shutdown" and event.get("details", {}).get("reason") == "SIGTERM" for event in events):
    raise SystemExit("command-queue SIGTERM did not record structured shutdown event")
if not any(event.get("service") == "command-queue" and event.get("event") == "service_stop" and event.get("details", {}).get("reason") == "SIGTERM" for event in events):
    raise SystemExit("command-queue SIGTERM did not record service_stop reason")
state = json.loads(Path(cfg["server_state"]).read_text(encoding="utf-8"))
service = (state.get("services") or {}).get("command-queue") or {}
if service.get("status") != "stopped" or service.get("stopped_reason") != "SIGTERM":
    raise SystemExit("command-queue SIGTERM did not persist stopped state")
PY
scripts/busierbox-server --config "$term_cfg" --json-status | python3 -c 'import json,sys; d=json.load(sys.stdin); summary=d["summary"]; by_reason=d["services_by_stopped_reason"]; api=d["api_collections"]["services"]; assert summary["service_stopped_reason_counts"]["SIGTERM"] == 1; assert by_reason["SIGTERM"][0]["name"] == "command-queue"; assert "services_by_stopped_reason" in api["indexes"]'
scripts/busierbox-server --config "$term_cfg" --status >"$term_out"
grep -q 'service lifecycle: .*stopped_reasons=SIGTERM=1' "$term_out"
rm -f "$term_cfg" "$term_out" "$term_err"
"$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["execution_supported"] is False; assert d["requires_external_writes"] is False; assert d["poll_interval_sec"] == "5"; assert d["poll_jitter_pct"] == "0"; assert d["poll_backoff"] == "none"; assert d["poll_max_interval_sec"] == "300"; assert d["daemon_state_file"].endswith("/run/command-queue-daemon.state"); assert d["daemon_state_file_supported"] is True; assert d["daemon_status_supported"] is True; assert d["daemon_stop_supported"] is True; assert d["result_upload_supported"] is True'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["policy_valid"] is False; assert "disabled command queue must keep allowed commands policy none" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_start"] == []; assert d["would_connect"] == []'
"$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["effective_config"]; p=d["command_queue_policy"]; assert c["BB_COMMAND_QUEUE_ENABLE"] == "no"; assert c["BB_COMMAND_QUEUE_ALLOWED_COMMANDS"] == "none"; assert c["BB_COMMAND_QUEUE_EXECUTION"] == "metadata-only"; assert c["BB_COMMAND_QUEUE_ALLOW_ARBITRARY"] == "no"; assert c["BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"] == "5"; assert c["BB_COMMAND_QUEUE_POLL_JITTER_PCT"] == "0"; assert c["BB_COMMAND_QUEUE_POLL_BACKOFF"] == "none"; assert c["BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC"] == "300"; assert c["BB_COMMAND_QUEUE_MAX_POLLS"] == "0"; assert p["valid"] is True; assert p["errors"] == []; assert p["execution_mode"] == "metadata-only"; assert p["metadata_only_default"] is True; assert p["enabled"] is False; assert p["configured_for_polling"] is False; assert p["missing_operator_host"] is False; assert p["poll_transport_supported"] is True; assert p["live_polling_supported"] is True; assert p["delivery_supported"] is False; assert p["result_upload_supported"] is True; assert p["execution_supported"] is False; assert p["executes_commands"] is False; assert p["active_control_channel"] is False; assert p["operator_supplied_command_execution"] is False; assert p["arbitrary_policy_requested"] is False; assert p["arbitrary_execution_allowed"] is False; assert p["safe_disabled_default"] is True'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["command_queue_policy"]; assert p["valid"] is False; assert p["result_upload_supported"] is True; assert p["execution_supported"] is False; assert p["executes_commands"] is False; assert "disabled command queue must keep allowed commands policy none" in p["errors"]'
"$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["enabled"] == "no"; assert q["policy_valid"] is True; assert q["policy_errors"] == []; assert q["poll_interval_sec"] == "5"; assert q["poll_jitter_pct"] == "0"; assert q["poll_backoff"] == "none"; assert q["poll_max_interval_sec"] == "300"; assert q["max_polls"] == "0"; assert q["daemon_state_file"].endswith("/run/command-queue-daemon.state"); assert q["daemon_state_file_supported"] is True; assert q["daemon_status_supported"] is True; assert q["daemon_stop_supported"] is True; assert q["result_upload_supported"] is True; assert q["executes_commands"] is False; assert q["default_enabled"] is False'
BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes "$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["policy_valid"] is False; assert "disabled command queue must not allow arbitrary execution" in q["policy_errors"]'
"$bb" config-info | grep -q '^effective_command_queue_enable=no$'
"$bb" config-info | grep -q '^compiled_command_queue_require_token=yes$'
"$bb" config-info | grep -q '^compiled_command_queue_token_source=manual$'
"$bb" config-info | grep -q '^compiled_command_queue_token_configured=no$'
"$bb" config-info | grep -q '^compiled_command_queue_execution=metadata-only$'
"$bb" config-info | grep -q '^effective_command_queue_require_token=yes$'
"$bb" config-info | grep -q '^effective_command_queue_token_source=manual$'
"$bb" config-info | grep -q '^effective_command_queue_token_configured=no$'
"$bb" config-info | grep -q '^effective_command_queue_execution=metadata-only$'
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
