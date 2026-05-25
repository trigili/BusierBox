#!/bin/sh
# Verify rshell PID-based stop/start/restart lifecycle in busierbox.c source.
# These are source-level checks; full integration requires a running target.
set -eu

src=${1:-src/busierbox.c}

[ -f "$src" ] || {
    printf '%s\n' "rshell-lifecycle: missing $src" >&2
    exit 1
}

# stop must read PID files and send SIGTERM — not pkill -f
if grep -q 'pkill.*-f.*dropbear\|pkill.*-f.*dbclient' "$src"; then
    printf '%s\n' "rshell-lifecycle: stop still uses pkill -f dropbear/dbclient" >&2
    exit 1
fi
grep -q 'SIGTERM' "$src"
grep -q 'dbclient\.pid\|dropbear\.pid' "$src"

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

# BB_ZERO_ARG_LOG_MODE=none redirects to /dev/null
grep -q 'BB_ZERO_ARG_LOG_MODE.*none\|none.*BB_ZERO_ARG_LOG_MODE' "$src"
grep -q '/dev/null' "$src"

# autorun guard path uses runtime root, not /tmp
if grep 'BB_AUTORUN_GUARD_PATH' "$src" | grep -q '"/tmp/busierbox-autorun"'; then
    printf '%s\n' "rshell-lifecycle: BB_AUTORUN_GUARD_PATH default still uses /tmp/busierbox-autorun" >&2
    exit 1
fi
grep -q 'BB_RUNTIME_ROOT.*run\|BB_AUTORUN_GUARD_PATH.*run' "$src"

if [ -f src/rshell_tls.c ]; then
    if grep -q 'wolfSSL_get_error(ssl, 0)' src/rshell_tls.c; then
        printf '%s\n' "rshell-lifecycle: wolfSSL_connect error path ignores actual return code" >&2
        exit 1
    fi
    grep -q 'SIGPIPE, SIG_IGN' src/rshell_tls.c
fi

printf '%s\n' "rshell-lifecycle ok"
