#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}

[ -x "$bb" ] || {
    printf '%s\n' "command-queue: missing executable $bb" >&2
    exit 1
}

"$bb" command-queue --help >/dev/null
"$bb" command-queue status >"${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
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
grep -q '^command_queue_mode_status_lifecycle=inspect$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_status_would_poll_if_configured=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_poll_lifecycle=single-poll$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_poll_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_once_lifecycle=single-cycle$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_once_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_daemon_lifecycle=long-running$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_mode_daemon_would_poll_if_configured=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_modes_execute_commands=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_modes_active_control_channel=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"

"$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; assert d["enabled"] is False; assert d["dry_run"] is True; assert d["policy_valid"] is True; assert d["policy_errors"] == []; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["arbitrary_policy_requested"] is False; assert d["arbitrary_execution_allowed"] is False; assert d["delivery_supported"] is False; assert d["poll_transport_supported"] is False; assert d["queued_command"] is None; assert p["mode"] == "poll"; assert p["dry_run_only"] is True; assert p["requires_explicit_target_action"] is True; assert p["would_contact_operator"] is False; assert p["queued_command_available"] is False; assert p["operator_supplied_command_execution"] is False; assert p["execution_supported"] is False; assert p["active_control_channel"] is False; assert m["status"]["selected"] is False; assert m["status"]["requires_operator_host"] is False; assert m["status"]["would_poll_if_configured"] is False; assert m["status"]["lifecycle"] == "inspect"; assert m["poll"]["selected"] is True; assert m["poll"]["requires_operator_host"] is True; assert m["poll"]["would_poll_if_configured"] is True; assert m["poll"]["lifecycle"] == "single-poll"; assert m["once"]["lifecycle"] == "single-cycle"; assert m["daemon"]["lifecycle"] == "long-running"; assert all(v["execution_supported"] is False and v["executes_commands"] is False and v["active_control_channel"] is False and v["operator_supplied_command_execution"] is False for v in m.values()); assert s["enabled"] is False; assert s["default_enabled"] is False; assert s["valid"] is True; assert s["error_count"] == 0; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["execution_supported"] is False; assert s["executes_commands"] is False; assert s["active_control_channel"] is False; assert s["safe_disabled_default"] is True'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" command-queue poll --operator-host '' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is True; assert d["would_poll"] is False; assert d["status"] == "missing_operator_host"; assert p["status"] == "missing_operator_host"; assert p["missing_operator_host"] is True; assert p["would_contact_operator"] is False; assert s["enabled"] is True; assert s["valid"] is True; assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; p=d["poll_plan"]; m=d["mode_semantics"]; assert d["enabled"] is True; assert d["policy_valid"] is True; assert d["configured_for_polling"] is True; assert d["missing_operator_host"] is False; assert d["mode"] == "once"; assert d["status"] == "once_dry_run"; assert d["would_poll"] is True; assert d["endpoint"] == "127.0.0.1:22205"; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert d["delivery_supported"] is False; assert d["result_upload_supported"] is False; assert d["queued_command"] is None; assert p["mode"] == "once"; assert p["configured_for_polling"] is True; assert p["would_poll"] is True; assert p["would_contact_operator"] is False; assert p["endpoint"] == "127.0.0.1:22205"; assert p["delivery_supported"] is False; assert p["result_upload_supported"] is False; assert p["executes_commands"] is False; assert m["once"]["selected"] is True; assert m["once"]["requires_operator_host"] is True; assert m["once"]["would_poll_if_configured"] is True; assert m["once"]["lifecycle"] == "single-cycle"; assert s["configured_for_polling"] is True; assert s["would_poll"] is True; assert s["delivery_supported"] is False; assert s["result_upload_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=custom BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["policy_valid"] is True; assert d["arbitrary_policy_requested"] is True; assert d["arbitrary_execution_allowed"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is False; assert s["arbitrary_policy_requested"] is True; assert s["arbitrary_execution_allowed"] is False; assert s["execution_supported"] is False'
BB_COMMAND_QUEUE_ENABLE=maybe BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["policy_summary"]; assert d["enabled"] is False; assert d["policy_valid"] is False; assert "invalid command queue enable value" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_poll"] is False; assert d["status"] == "invalid_policy"; assert s["valid"] is False; assert s["error_count"] == len(d["policy_errors"]); assert s["configured_for_polling"] is False; assert s["would_poll"] is False; assert s["safe_disabled_default"] is False'
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
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon --live --max-polls 2 --poll-interval-sec 0 --event-log "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["poll_plan"]; r=d["poll_run"]; s=d["policy_summary"]; assert d["enabled"] is True; assert d["dry_run"] is False; assert d["policy_valid"] is True; assert d["status"] == "polling"; assert d["poll_transport_supported"] is True; assert d["delivery_supported"] is False; assert d["result_upload_supported"] is False; assert d["execution_supported"] is False; assert d["executes_commands"] is False; assert d["active_control_channel"] is True; assert d["poll_interval_sec"] == 0; assert d["max_polls"] == 2; assert p["dry_run_only"] is False; assert p["would_contact_operator"] is True; assert p["queued_command_available"] is False; assert p["operator_supplied_command_execution"] is False; assert s["poll_transport_supported"] is True; assert s["active_control_channel"] is True; assert r["attempted"] is True; assert r["attempts"] == 2; assert r["successes"] + r["failures"] == 2; assert r["stopped_by_limit"] is True; assert r["delivery_supported"] is False; assert r["executes_commands"] is False'
python3 - "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$" <<'PY'
import json
import sys

events = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
names = [event["event"] for event in events]
assert names.count("command_queue_poll_attempt") == 2
assert "command_queue_poll_shutdown" in names
assert all(event["service"] == "command-queue" for event in events)
assert all(event["details"]["executes_commands"] is False for event in events)
assert all(event["details"]["delivery_supported"] is False for event in events)
PY
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-events.$$"
"$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["execution_supported"] is False; assert d["requires_external_writes"] is False'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["policy_valid"] is False; assert "disabled command queue must keep allowed commands policy none" in d["policy_errors"]; assert d["configured_for_polling"] is False; assert d["missing_operator_host"] is False; assert d["would_start"] == []; assert d["would_connect"] == []'
"$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["effective_config"]; p=d["command_queue_policy"]; assert c["BB_COMMAND_QUEUE_ENABLE"] == "no"; assert c["BB_COMMAND_QUEUE_ALLOWED_COMMANDS"] == "none"; assert c["BB_COMMAND_QUEUE_ALLOW_ARBITRARY"] == "no"; assert c["BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"] == "5"; assert c["BB_COMMAND_QUEUE_MAX_POLLS"] == "0"; assert p["valid"] is True; assert p["errors"] == []'
BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only "$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["command_queue_policy"]; assert p["valid"] is False; assert "disabled command queue must keep allowed commands policy none" in p["errors"]'
"$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["enabled"] == "no"; assert q["policy_valid"] is True; assert q["policy_errors"] == []; assert q["poll_interval_sec"] == "5"; assert q["max_polls"] == "0"; assert q["executes_commands"] is False; assert q["default_enabled"] is False'
BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes "$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["policy_valid"] is False; assert "disabled command queue must not allow arbitrary execution" in q["policy_errors"]'
"$bb" config-info | grep -q '^effective_command_queue_enable=no$'
"$bb" config-info | grep -q '^effective_command_queue_policy_valid=yes$'
"$bb" config-info | grep -q '^effective_command_queue_poll_interval_sec=5$'
"$bb" config-info | grep -q '^effective_command_queue_max_polls=0$'
BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes "$bb" config-info | grep -q '^effective_command_queue_policy_error=disabled command queue must not allow arbitrary execution$'

grep -q 'BB_COMMAND_QUEUE_ENABLE="no"' configs/busierbox.conf.example
grep -q 'Advanced / Explicit command queue' scripts/menuconfig
grep -q 'target-side polling for operator-supplied commands' scripts/menuconfig
grep -q 'execute queued commands' docs/command-queue.md
grep -q 'BB_COMMAND_QUEUE_ALLOWED_COMMANDS' scripts/menuconfig
grep -q 'BB_COMMAND_QUEUE_POLL_INTERVAL_SEC' scripts/menuconfig
grep -q 'invalid command queue allowed commands policy' scripts/package-target

printf '%s\n' "command-queue ok"
