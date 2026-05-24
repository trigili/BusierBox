#!/bin/sh
set -eu

menu=${1:-scripts/menuconfig}
[ -f "$menu" ] || {
    printf '%s\n' "menuconfig-autoexec: missing $menu" >&2
    exit 1
}

grep -q 'BB_STAGER_ZERO_ARG_MODE=' "$menu"
grep -q 'BB_STAGER_POST_RECEIVE_ACTION=' "$menu"
grep -q 'BB_FULL_ZERO_ARG_MODE=' "$menu"
grep -q 'BB_FULL_BOOTSTRAP_OPERATOR_SESSION=' "$menu"
grep -q 'BB_AUTORUN_GUARD_PATH=' "$menu"
grep -q 'BB_STAGER_AUTO_EXEC:-doctor' "$menu"
grep -q 'zero-arg:' "$menu"
grep -q 'Post-receive behavior is configured under' "$menu"
grep -q 'scripts/busierbox-server --wait-operator-tunnel' "$menu"

if awk '
    /operator_session_enabled\(\)/ { in_fn=1 }
    in_fn && /BB_FULL_BOOTSTRAP_CALLBACK/ { found=1 }
    in_fn && /^}/ { in_fn=0 }
    END { exit found ? 0 : 1 }
' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: callback-only config would trigger SSH catch instructions" >&2
    exit 1
fi

printf '%s\n' "menuconfig-autoexec ok"
