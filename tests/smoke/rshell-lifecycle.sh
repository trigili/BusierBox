#!/bin/sh
# Verify rshell PID-based stop/start/restart lifecycle in split sources.
# These are source-level checks; full integration requires a running target.
set -eu

src=${1:-src/applet_rshell.c}
autorun_src=${2:-src/busierbox.c}
config_src=${3:-src/effective_config.h}
all_src="$src $autorun_src $config_src"

[ -f "$src" ] || {
    printf '%s\n' "rshell-lifecycle: missing $src" >&2
    exit 1
}
[ -f "$autorun_src" ] || {
    printf '%s\n' "rshell-lifecycle: missing $autorun_src" >&2
    exit 1
}
[ -f "$config_src" ] || {
    printf '%s\n' "rshell-lifecycle: missing $config_src" >&2
    exit 1
}

# stop must read PID files and send SIGTERM — not pkill -f
if grep -q 'pkill.*-f.*dropbear\|pkill.*-f.*dbclient' $all_src; then
    printf '%s\n' "rshell-lifecycle: stop still uses pkill -f dropbear/dbclient" >&2
    exit 1
fi
grep -q 'SIGTERM' "$src"
grep -q 'dbclient\.pid\|dropbear\.pid' "$src"
grep -q 'rshell\.pid' "$src"
grep -q 'BB_RSHELL_RUN_MODE' "$src"
grep -q 'BB_RSHELL_SESSION_POLICY' "$src"
grep -q 'should_reconnect_after_success' "$src"
grep -q '"single"' "$src"
grep -q '"reconnect"' "$src"
grep -q '"persistent"' "$src"
grep -q 'BUSIERBOX_ZERO_ARG_CONTEXT' "$src"
grep -q 'BUSIERBOX_RSHELL_BACKGROUND_CHILD' "$src"
grep -q 'LD_LIBRARY_PATH' "$src"
grep -q 'payload_lib' "$src"

# start must check existing PID before launching (not pkill)
# The start path should reference the pid file check
grep -q 'dbclient.pid' "$src"

# PID files go under guard path, not /tmp directly
if grep 'dropbear\.pid\|dbclient\.pid' "$src" | grep -vq 'autorun_guard_path\|guard_path\|_guard\|_gp\|gp\b'; then
    # Allow if all references are through a path variable
    # Just verify no hardcoded /tmp paths for pid files
    if grep 'dropbear\.pid\|dbclient\.pid' "$src" | grep -q '"/tmp/'; then
        printf '%s\n' "rshell-lifecycle: PID file path hardcodes /tmp" >&2
        exit 1
    fi
fi

# Log paths use guard path, not hardcoded /tmp
if grep 'dropbear\.log\|dbclient\.log' "$src" | grep -q '"/tmp/'; then
    printf '%s\n' "rshell-lifecycle: log file path hardcodes /tmp" >&2
    exit 1
fi

# rshell.status is written
grep -q 'rshell\.status' "$src"
grep -q 'bb_ledger_record("write".*rshell status' "$src"
grep -q 'bb_ledger_record("write".*rshell pid' "$src"
grep -q 'bb_ledger_record("write".*rshell log' "$src"
grep -q 'connection_was_established' "$src"
grep -q 'write_rshell_runtime_status' "$src"
grep -q 'initial_attempts' "$src"
grep -q 'reconnect_attempts' "$src"
grep -q 'retry_scope' "$src"
grep -q 'post_disconnect_retry_count' "$src"
grep -q 'fresh_session_on_reconnect' "$src"
grep -q 'policy-single-complete' "$src"
grep -q 'dbclient-supervisor\.sh' "$src"
grep -q 'bbx_reconnect_attempt' "$src"
grep -q 'post-disconnect-retry-limit' "$src"
grep -q 'bbx_dbclient.*-K 30 -N -R' "$src"
grep -q 'rshell dbclient supervisor' "$src"
grep -q 'bb_ledger_record("write".*autorun lock' "$autorun_src"
grep -q 'bb_ledger_record("write".*autorun status' "$autorun_src"

# BB_ZERO_ARG_LOG_MODE=none redirects to /dev/null
grep -q 'BB_ZERO_ARG_LOG_MODE.*none\|none.*BB_ZERO_ARG_LOG_MODE' "$src"
grep -q '/dev/null' "$src"

# autorun guard path uses runtime root, not /tmp
if grep 'BB_AUTORUN_GUARD_PATH' $all_src | grep -q '"/tmp/busierbox-autorun"'; then
    printf '%s\n' "rshell-lifecycle: BB_AUTORUN_GUARD_PATH default still uses /tmp/busierbox-autorun" >&2
    exit 1
fi
grep -q 'BB_RUNTIME_ROOT.*run\|BB_AUTORUN_GUARD_PATH.*run' $all_src

if [ -f src/rshell_tls.c ]; then
    if grep -q 'wolfSSL_get_error(ssl, 0)' src/rshell_tls.c; then
        printf '%s\n' "rshell-lifecycle: wolfSSL_connect error path ignores actual return code" >&2
        exit 1
    fi
    grep -q 'SIGPIPE, SIG_IGN' src/rshell_tls.c
fi

printf '%s\n' "rshell-lifecycle ok"
