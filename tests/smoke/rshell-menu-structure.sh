#!/bin/sh
# Source-level checks for grouped rshell menuconfig structure.
set -eu

menu=${1:-scripts/menuconfig}

[ -f "$menu" ] || {
    printf '%s\n' "rshell-menu-structure: missing $menu" >&2
    exit 1
}

for fn in \
    configure_rshell_enable_transport \
    configure_rshell_endpoint \
    configure_rshell_launch_behavior \
    configure_rshell_shell_provider \
    configure_rshell_ssh_settings \
    configure_rshell_credentials_policy \
    configure_rshell_retry_lifecycle \
    configure_rshell_summary_export
do
    grep -q "^$fn()" "$menu" || {
        printf '%s\n' "rshell-menu-structure: missing $fn" >&2
        exit 1
    }
done

for label in \
    'Enable / transport' \
    'Operator endpoint' \
    'Launch behavior' \
    'Shell provider' \
    'SSH tunnel settings' \
    'Credentials / authkeys policy' \
    'Retry / lifecycle' \
    'Summary / export'
do
    grep -q "$label" "$menu" || {
        printf '%s\n' "rshell-menu-structure: missing label $label" >&2
        exit 1
    }
done

grep -q 'Transport-specific pages are hidden unless they apply' "$menu"
grep -q 'SSH tunnel settings apply only when transport=ssh' "$menu"
grep -q 'authorized_keys policy only applies to SSH reverse access' "$menu"
grep -q 'Encryption is only shown for builtin/socat shell transports' "$menu"
grep -q 'Configure where the target connects' "$menu"
grep -q 'Zero-arg autorun remains separate' "$menu"

printf '%s\n' "rshell-menu-structure ok"
