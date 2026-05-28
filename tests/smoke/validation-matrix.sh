#!/bin/sh
# Static guard for the hard validation cases called out in local/GOAL.md.
set -eu

menu=${1:-scripts/menuconfig}
pkg=${2:-scripts/package-target}
tmp=${TMPDIR:-local/tmp}/busierbox-validation-matrix-$$
mkdir -p "$tmp"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

[ -f "$menu" ] || { printf '%s\n' "validation-matrix: missing $menu" >&2; exit 1; }

body=$(awk '/^validate_config\(\)/,/^}/' "$menu")

require() {
    name=$1
    pattern=$2
    printf '%s\n' "$body" | grep -Eq "$pattern" || {
        printf '%s\n' "validation-matrix: missing check for $name" >&2
        exit 1
    }
}

require 'core-only + ssh/socat' 'core-only.*ssh|ssh.*core-only|core-only.*socat|socat.*core-only'
require 'core-only + heavy tools' 'BB_HEAVY_TOOLS'
require 'core-only + dotfiles' 'BB_DOTFILES_ENABLE'
require 'core-only + overlay' 'BB_USER_OVERLAY_ENABLE'
require 'rshell + transport none' 'BB_ZERO_ARG_MODE.*rshell|BB_RSHELL_TRANSPORT.*none'
require 'builtin plaintext unsupported' 'builtin.*encryption=none|BB_RSHELL_ENCRYPTION.*none|BB_RSHELL_ALLOW_PLAINTEXT'
require 'ssh without dropbear' 'dropbear'
require 'socat without socat' 'socat'
require 'custom zero-arg empty command' 'BB_ZERO_ARG_CUSTOM_COMMAND'
require 'custom shell provider empty command' 'BB_RSHELL_CUSTOM_SHELL'
require 'root authkeys without external writes' 'root-copy|root-merge|BB_RUNTIME_ALLOW_EXTERNAL_WRITES'
require 'invalid retry values' 'BB_RSHELL_RETRY_COUNT|BB_RSHELL_RETRY_INTERVAL_SEC|BB_RSHELL_RETRY_JITTER_PCT|BB_RSHELL_RETRY_MAX_INTERVAL_SEC'
require 'invalid run mode' 'BB_RSHELL_RUN_MODE'
require 'invalid session policy' 'BB_RSHELL_SESSION_POLICY'
require 'invalid shell provider' 'BB_RSHELL_SHELL_PROVIDER'
require 'invalid retry backoff' 'BB_RSHELL_RETRY_BACKOFF'
require 'invalid rshell transport' 'BB_RSHELL_TRANSPORT'
require 'aggressive no-residue fallback guard' 'aggressive no-residue.*BB_RUNTIME_ALLOW_FALLBACK_ROOT|BB_RUNTIME_ALLOW_FALLBACK_ROOT.*aggressive no-residue'
require 'invalid command queue policy' 'BB_COMMAND_QUEUE_ALLOWED_COMMANDS'
require 'invalid command queue execution mode' 'BB_COMMAND_QUEUE_EXECUTION'
require 'command queue arbitrary guard' 'BB_COMMAND_QUEUE_ALLOW_ARBITRARY'

grep -q 'validate_build_config' "$pkg" || {
    printf '%s\n' "validation-matrix: package-target must validate configs outside menuconfig" >&2
    exit 1
}
for pattern in \
    'zero-arg mode is.*rshell.*transport=none' \
    'builtin plaintext is not implemented' \
    'core-only runtime cannot stage heavy tools' \
    'transport=socat but socat is not in heavy tools' \
    'transport=ssh but dropbear is not in heavy tools' \
    'BB_RSHELL_RETRY_COUNT must be an integer' \
    'invalid rshell run mode' \
    'invalid rshell session policy' \
    'invalid shell provider' \
    'aggressive no-residue cannot use runtime fallback root' \
    'invalid command queue allowed commands policy' \
    'authkeys mode.*writes outside the runtime root'
do
    grep -q "$pattern" "$pkg" || {
        printf '%s\n' "validation-matrix: package-target missing hard error text matching $pattern" >&2
        exit 1
    }
done

grep -q 'TARGET_STATUS.*blank' "$pkg" || {
    printf '%s\n' "validation-matrix: package-target must reject blank default target" >&2
    exit 1
}

write_case_config() {
    out=$1
    shift
    {
        printf '%s\n' 'BB_PAYLOAD_PRESET="default"'
        printf '%s\n' 'BB_RUNTIME_MODE="extract"'
        printf '%s\n' 'BB_RUNTIME_ALLOW_EXTERNAL_WRITES="no"'
        printf '%s\n' 'BB_ZERO_ARG_MODE="help"'
        printf '%s\n' 'BB_RSHELL_TRANSPORT="none"'
        printf '%s\n' 'BB_RSHELL_ENCRYPTION="tls"'
        printf '%s\n' 'BB_RSHELL_ALLOW_PLAINTEXT="no"'
        printf '%s\n' 'BB_RSHELL_AUTHKEYS_MODE="disabled"'
        printf '%s\n' 'BB_RSHELL_RUN_MODE="auto"'
        printf '%s\n' 'BB_RSHELL_SESSION_POLICY="single"'
        printf '%s\n' 'BB_RSHELL_SHELL_PROVIDER="auto"'
        printf '%s\n' 'BB_RSHELL_RETRY_COUNT="1"'
        printf '%s\n' 'BB_RSHELL_RETRY_INTERVAL_SEC="5"'
        printf '%s\n' 'BB_RSHELL_RETRY_JITTER_PCT="20"'
        printf '%s\n' 'BB_RSHELL_RETRY_BACKOFF="none"'
        printf '%s\n' 'BB_RSHELL_RETRY_MAX_INTERVAL_SEC="300"'
        printf '%s\n' 'BB_DOTFILES_ENABLE="no"'
        printf '%s\n' 'BB_USER_OVERLAY_ENABLE="no"'
        printf '%s\n' 'BB_HEAVY_TOOLS=""'
        while [ $# -gt 0 ]; do
            printf '%s\n' "$1"
            shift
        done
    } >"$out"
}

expect_package_invalid() {
    name=$1
    pattern=$2
    shift 2
    cfg="$tmp/$name.conf"
    write_case_config "$cfg" "$@"
    if BUSIERBOX_CONFIG="$cfg" "$pkg" native >"$tmp/$name.out" 2>"$tmp/$name.err"; then
        printf '%s\n' "validation-matrix: package-target accepted invalid case $name" >&2
        exit 1
    fi
    grep -q 'package-target: invalid configuration:' "$tmp/$name.err" || {
        printf '%s\n' "validation-matrix: $name did not fail during package config validation" >&2
        cat "$tmp/$name.err" >&2
        exit 1
    }
    grep -q "$pattern" "$tmp/$name.err" || {
        printf '%s\n' "validation-matrix: $name missing expected error $pattern" >&2
        cat "$tmp/$name.err" >&2
        exit 1
    }
}

expect_package_invalid rshell-none 'zero-arg mode is.*rshell' \
    'BB_ZERO_ARG_MODE="rshell"'
expect_package_invalid builtin-plaintext 'builtin plaintext is not implemented' \
    'BB_RSHELL_TRANSPORT="builtin"' \
    'BB_RSHELL_ENCRYPTION="none"' \
    'BB_RSHELL_ALLOW_PLAINTEXT="yes"'
expect_package_invalid core-heavy 'core-only runtime cannot stage heavy tools' \
    'BB_RUNTIME_MODE="core-only"' \
    'BB_HEAVY_TOOLS="tmux"'
expect_package_invalid core-socat 'core-only + transport=socat' \
    'BB_RUNTIME_MODE="core-only"' \
    'BB_RSHELL_TRANSPORT="socat"'
expect_package_invalid custom-zero-empty 'zero-arg custom mode requires' \
    'BB_ZERO_ARG_MODE="custom"'
expect_package_invalid root-copy-no-external 'authkeys mode root-copy writes outside' \
    'BB_RSHELL_AUTHKEYS_MODE="root-copy"'
expect_package_invalid socat-missing 'transport=socat but socat is not in heavy tools' \
    'BB_RSHELL_TRANSPORT="socat"'
expect_package_invalid ssh-missing 'transport=ssh but dropbear is not in heavy tools' \
    'BB_RSHELL_TRANSPORT="ssh"'
expect_package_invalid invalid-retry 'BB_RSHELL_RETRY_COUNT must be an integer' \
    'BB_RSHELL_RETRY_COUNT="abc"'
expect_package_invalid invalid-run-mode 'invalid rshell run mode' \
    'BB_RSHELL_RUN_MODE="sideways"'
expect_package_invalid invalid-session-policy 'invalid rshell session policy' \
    'BB_RSHELL_SESSION_POLICY="resume"'
expect_package_invalid invalid-shell-provider 'invalid shell provider' \
    'BB_RSHELL_SHELL_PROVIDER="fish"'
expect_package_invalid invalid-runtime 'invalid runtime mode' \
    'BB_RUNTIME_MODE="forever"'
expect_package_invalid aggressive-fallback 'aggressive no-residue cannot use runtime fallback root' \
    'BB_RUNTIME_MODE="no-residue"' \
    'BB_NORESIDUE_LEVEL="aggressive"' \
    'BB_RUNTIME_ALLOW_FALLBACK_ROOT="yes"'
expect_package_invalid invalid-transport 'invalid rshell transport' \
    'BB_RSHELL_TRANSPORT="wireguard"'
expect_package_invalid invalid-command-queue-policy 'invalid command queue allowed commands policy' \
    'BB_COMMAND_QUEUE_ALLOWED_COMMANDS="everything"'
expect_package_invalid invalid-command-queue-execution 'invalid command queue execution mode' \
    'BB_COMMAND_QUEUE_EXECUTION="automatic"'
expect_package_invalid disabled-command-queue-execute 'command queue is disabled but execution mode is execute' \
    'BB_COMMAND_QUEUE_EXECUTION="execute"'
expect_package_invalid disabled-command-queue-arbitrary 'command queue is disabled but arbitrary execution is allowed' \
    'BB_COMMAND_QUEUE_ALLOW_ARBITRARY="yes"'

if "$pkg" default >"$tmp/default-target.out" 2>"$tmp/default-target.err"; then
    printf '%s\n' "validation-matrix: package-target accepted blank default target" >&2
    exit 1
fi
grep -q 'blank target configuration' "$tmp/default-target.err"

printf '%s\n' "validation-matrix ok"
