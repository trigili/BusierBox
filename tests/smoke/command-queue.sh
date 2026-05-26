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
grep -q '^command_queue_would_poll=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_allowed_commands=none$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_allow_arbitrary=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_execution_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_delivery_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
grep -q '^command_queue_poll_transport_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-status.$$"

"$bb" command-queue poll --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["enabled"] is False; assert d["dry_run"] is True; assert d["would_poll"] is False; assert d["execution_supported"] is False; assert d["delivery_supported"] is False; assert d["poll_transport_supported"] is False; assert d["queued_command"] is None'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue once --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["enabled"] is True; assert d["mode"] == "once"; assert d["status"] == "once_dry_run"; assert d["would_poll"] is True; assert d["endpoint"] == "127.0.0.1:22205"; assert d["execution_supported"] is False; assert d["delivery_supported"] is False; assert d["result_upload_supported"] is False; assert d["queued_command"] is None'
BB_COMMAND_QUEUE_ENABLE=yes BB_COMMAND_QUEUE_ALLOWED_COMMANDS=busierbox-only BB_OPERATOR_SERVER_HOST=127.0.0.1 "$bb" command-queue daemon >"${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_status=daemon_dry_run$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_would_poll=yes$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_endpoint=127.0.0.1:22205$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
grep -q '^command_queue_execution_supported=no$' "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
rm -f "${TMPDIR:-/tmp}/busierbox-command-queue-daemon.$$"
"$bb" plan command-queue --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["command"] == "command-queue"; assert d["execution_supported"] is False; assert d["requires_external_writes"] is False'
"$bb" runtime-config --json | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["effective_config"]; assert c["BB_COMMAND_QUEUE_ENABLE"] == "no"; assert c["BB_COMMAND_QUEUE_ALLOWED_COMMANDS"] == "none"; assert c["BB_COMMAND_QUEUE_ALLOW_ARBITRARY"] == "no"'
"$bb" manifest --json | python3 -c 'import json,sys; d=json.load(sys.stdin); q=d["operator_services"]["command_queue"]; assert q["enabled"] == "no"; assert q["executes_commands"] is False; assert q["default_enabled"] is False'
"$bb" config-info | grep -q '^effective_command_queue_enable=no$'

grep -q 'BB_COMMAND_QUEUE_ENABLE="no"' configs/busierbox.conf.example
grep -q 'Advanced / Explicit command queue' scripts/menuconfig
grep -q 'target-side polling for operator-supplied commands' scripts/menuconfig
grep -q 'execute queued commands' docs/command-queue.md
grep -q 'BB_COMMAND_QUEUE_ALLOWED_COMMANDS' scripts/menuconfig
grep -q 'invalid command queue allowed commands policy' scripts/package-target

printf '%s\n' "command-queue ok"
