#!/bin/sh
# Verify transport naming: builtin/socat/ssh (not builtin-tls/socat-tls).
# BB_RSHELL_ENCRYPTION is a separate orthogonal config.
set -eu

menu=${1:-scripts/menuconfig}
build=${2:-scripts/build-native}

[ -f "$menu" ] || {
    printf '%s\n' "rshell-transport-names: missing $menu" >&2
    exit 1
}
[ -f "$build" ] || {
    printf '%s\n' "rshell-transport-names: missing $build" >&2
    exit 1
}

# menuconfig must not contain old -tls transport names as primary options
if grep -q '"builtin-tls"' "$menu" || grep -q '"socat-tls"' "$menu"; then
    printf '%s\n' "rshell-transport-names: old -tls transport names still appear as options in menuconfig" >&2
    exit 1
fi

# menuconfig must define BB_RSHELL_ENCRYPTION and BB_RSHELL_ALLOW_PLAINTEXT
grep -q 'BB_RSHELL_ENCRYPTION=' "$menu"
grep -q 'BB_RSHELL_ALLOW_PLAINTEXT=' "$menu"
grep -q 'BB_RSHELL_SHELL_PROVIDER=' "$menu"
grep -q 'BB_RSHELL_RUN_MODE=' "$menu"
grep -q 'BB_RSHELL_SESSION_POLICY=' "$menu"
grep -q 'BB_RSHELL_RETRY_COUNT=' "$menu"
grep -q 'single|reconnect|persistent' "$menu"
grep -q 'payload-zsh' "$menu"

# menuconfig transport choices are builtin, socat, ssh
grep -q '"ssh"' "$menu"
grep -q '"socat"' "$menu"
grep -q '"builtin"' "$menu"

# build-native must default BB_RSHELL_ENCRYPTION and normalize old names
grep -q 'BB_RSHELL_ENCRYPTION' "$build"
grep -q 'BB_RSHELL_ALLOW_PLAINTEXT' "$build"
# old name normalization is present
grep -q 'builtin-tls.*builtin\|builtin.*builtin-tls' "$build"
grep -q 'socat-tls.*socat\|socat.*socat-tls' "$build"

# build-native must emit BB_RSHELL_ENCRYPTION and BB_RSHELL_ALLOW_PLAINTEXT as -D flags
grep -q 'DBB_RSHELL_ENCRYPTION' "$build"
grep -q 'DBB_RSHELL_ALLOW_PLAINTEXT' "$build"
grep -q 'DBB_RSHELL_SHELL_PROVIDER' "$build"
grep -q 'DBB_RSHELL_RUN_MODE' "$build"
grep -q 'DBB_RSHELL_SESSION_POLICY' "$build"
grep -q 'DBB_RSHELL_RETRY_COUNT' "$build"

stale_server_pattern='--r''shell\|wait-operator''-tunnel\|shell-''again'
if grep -q -- "$stale_server_pattern" "$menu"; then
    printf '%s\n' "rshell-transport-names: stale reverse-access command text found" >&2
    exit 1
fi

# _rshell_save_info must use BB_RSHELL_TRANSPORT not BB_RSHELL_MODE
if grep -q 'BB_RSHELL_MODE}' "$menu"; then
    # Allow BB_RSHELL_MODE in compat/assignment contexts but not in the table output
    if grep -A2 '| Transport |' "$menu" | grep -q 'BB_RSHELL_MODE}'; then
        printf '%s\n' "rshell-transport-names: _rshell_save_info table still uses BB_RSHELL_MODE" >&2
        exit 1
    fi
fi

grep -q '_rshell_server_command()' "$menu"
grep -q '_rshell_operator_connect_command()' "$menu"
grep -q 'plain-shell --shell-port' "$menu"
grep -q 'tls-shell --shell-port' "$menu"
grep -q 'ssh --ssh-port' "$menu"
grep -q 'This artifact will not initiate reverse access when run with no arguments' "$menu"
grep -q './busierbox rshell start' "$menu"
grep -q 'plaintext shell transport is insecure/debug-only' "$menu"
grep -q 'Zero-arg mode: ${BB_ZERO_ARG_MODE}' "$menu"
grep -q 'Explicit reverse access:' "$menu"
grep -q 'Scripted smoke test' "$menu"
grep -q -- '--script - --session-timeout 20' "$menu"

printf '%s\n' "rshell-transport-names ok"
