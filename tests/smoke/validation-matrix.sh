#!/bin/sh
# Static guard for the hard validation cases called out in local/GOAL.md.
set -eu

menu=${1:-scripts/menuconfig}
pkg=${2:-scripts/package-target}
tmp=${TMPDIR:-local/tmp}/grit-validation-matrix-$$
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
require 'core-only + heavy tools' 'GRIT_HEAVY_TOOLS'
require 'core-only + dotfiles' 'GRIT_DOTFILES_ENABLE'
require 'core-only + overlay' 'GRIT_USER_OVERLAY_ENABLE'
require 'rshell + transport none' 'GRIT_ZERO_ARG_MODE.*rshell|GRIT_RSHELL_TRANSPORT.*none'
require 'builtin plaintext unsupported' 'builtin.*encryption=none|GRIT_RSHELL_ENCRYPTION.*none|GRIT_RSHELL_ALLOW_PLAINTEXT'
require 'ssh without dropbear' 'dropbear'
require 'socat without socat' 'socat'
require 'custom zero-arg empty command' 'GRIT_ZERO_ARG_CUSTOM_COMMAND'
require 'custom shell provider empty command' 'GRIT_RSHELL_CUSTOM_SHELL'
require 'root authkeys without external writes' 'root-copy|root-merge|GRIT_RUNTIME_ALLOW_EXTERNAL_WRITES'
require 'invalid retry values' 'GRIT_RSHELL_RETRY_COUNT|GRIT_RSHELL_RETRY_INTERVAL_SEC|GRIT_RSHELL_RETRY_JITTER_PCT|GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC'
require 'invalid run mode' 'GRIT_RSHELL_RUN_MODE'
require 'invalid session policy' 'GRIT_RSHELL_SESSION_POLICY'
require 'invalid shell provider' 'GRIT_RSHELL_SHELL_PROVIDER'
require 'invalid retry backoff' 'GRIT_RSHELL_RETRY_BACKOFF'
require 'invalid rshell transport' 'GRIT_RSHELL_TRANSPORT'
require 'aggressive no-residue fallback guard' 'aggressive no-residue.*GRIT_RUNTIME_ALLOW_FALLBACK_ROOT|GRIT_RUNTIME_ALLOW_FALLBACK_ROOT.*aggressive no-residue'
require 'invalid command queue policy' 'GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS'
require 'invalid command queue execution mode' 'GRIT_COMMAND_QUEUE_EXECUTION'
require 'command queue arbitrary guard' 'GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY'

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
    'GRIT_RSHELL_RETRY_COUNT must be an integer' \
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
        printf '%s\n' 'GRIT_PAYLOAD_PRESET="default"'
        printf '%s\n' 'GRIT_RUNTIME_MODE="extract"'
        printf '%s\n' 'GRIT_RUNTIME_ALLOW_EXTERNAL_WRITES="no"'
        printf '%s\n' 'GRIT_ZERO_ARG_MODE="help"'
        printf '%s\n' 'GRIT_RSHELL_TRANSPORT="none"'
        printf '%s\n' 'GRIT_RSHELL_ENCRYPTION="tls"'
        printf '%s\n' 'GRIT_RSHELL_ALLOW_PLAINTEXT="no"'
        printf '%s\n' 'GRIT_RSHELL_AUTHKEYS_MODE="disabled"'
        printf '%s\n' 'GRIT_RSHELL_RUN_MODE="auto"'
        printf '%s\n' 'GRIT_RSHELL_SESSION_POLICY="single"'
        printf '%s\n' 'GRIT_RSHELL_SHELL_PROVIDER="auto"'
        printf '%s\n' 'GRIT_RSHELL_RETRY_COUNT="1"'
        printf '%s\n' 'GRIT_RSHELL_RETRY_INTERVAL_SEC="5"'
        printf '%s\n' 'GRIT_RSHELL_RETRY_JITTER_PCT="20"'
        printf '%s\n' 'GRIT_RSHELL_RETRY_BACKOFF="none"'
        printf '%s\n' 'GRIT_RSHELL_RETRY_MAX_INTERVAL_SEC="300"'
        printf '%s\n' 'GRIT_DOTFILES_ENABLE="no"'
        printf '%s\n' 'GRIT_USER_OVERLAY_ENABLE="no"'
        printf '%s\n' 'GRIT_HEAVY_TOOLS=""'
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
    if GRIT_CONFIG="$cfg" "$pkg" native >"$tmp/$name.out" 2>"$tmp/$name.err"; then
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
    'GRIT_ZERO_ARG_MODE="rshell"'
expect_package_invalid builtin-plaintext 'builtin plaintext is not implemented' \
    'GRIT_RSHELL_TRANSPORT="builtin"' \
    'GRIT_RSHELL_ENCRYPTION="none"' \
    'GRIT_RSHELL_ALLOW_PLAINTEXT="yes"'
expect_package_invalid core-heavy 'core-only runtime cannot stage heavy tools' \
    'GRIT_RUNTIME_MODE="core-only"' \
    'GRIT_HEAVY_TOOLS="tmux"'
expect_package_invalid core-socat 'core-only + transport=socat' \
    'GRIT_RUNTIME_MODE="core-only"' \
    'GRIT_RSHELL_TRANSPORT="socat"'
expect_package_invalid custom-zero-empty 'zero-arg custom mode requires' \
    'GRIT_ZERO_ARG_MODE="custom"'
expect_package_invalid root-copy-no-external 'authkeys mode root-copy writes outside' \
    'GRIT_RSHELL_AUTHKEYS_MODE="root-copy"'
expect_package_invalid socat-missing 'transport=socat but socat is not in heavy tools' \
    'GRIT_RSHELL_TRANSPORT="socat"'
expect_package_invalid ssh-missing 'transport=ssh but dropbear is not in heavy tools' \
    'GRIT_RSHELL_TRANSPORT="ssh"'
expect_package_invalid invalid-retry 'GRIT_RSHELL_RETRY_COUNT must be an integer' \
    'GRIT_RSHELL_RETRY_COUNT="abc"'
expect_package_invalid invalid-run-mode 'invalid rshell run mode' \
    'GRIT_RSHELL_RUN_MODE="sideways"'
expect_package_invalid invalid-session-policy 'invalid rshell session policy' \
    'GRIT_RSHELL_SESSION_POLICY="resume"'
expect_package_invalid invalid-shell-provider 'invalid shell provider' \
    'GRIT_RSHELL_SHELL_PROVIDER="fish"'
expect_package_invalid invalid-runtime 'invalid runtime mode' \
    'GRIT_RUNTIME_MODE="forever"'
expect_package_invalid aggressive-fallback 'aggressive no-residue cannot use runtime fallback root' \
    'GRIT_RUNTIME_MODE="no-residue"' \
    'GRIT_NORESIDUE_LEVEL="aggressive"' \
    'GRIT_RUNTIME_ALLOW_FALLBACK_ROOT="yes"'
expect_package_invalid invalid-transport 'invalid rshell transport' \
    'GRIT_RSHELL_TRANSPORT="wireguard"'
expect_package_invalid invalid-command-queue-policy 'invalid command queue allowed commands policy' \
    'GRIT_COMMAND_QUEUE_ALLOWED_COMMANDS="everything"'
expect_package_invalid invalid-command-queue-execution 'invalid command queue execution mode' \
    'GRIT_COMMAND_QUEUE_EXECUTION="automatic"'
expect_package_invalid disabled-command-queue-execute 'command queue is disabled but execution mode is execute' \
    'GRIT_COMMAND_QUEUE_EXECUTION="execute"'
expect_package_invalid disabled-command-queue-arbitrary 'command queue is disabled but arbitrary execution is allowed' \
    'GRIT_COMMAND_QUEUE_ALLOW_ARBITRARY="yes"'

if "$pkg" default >"$tmp/default-target.out" 2>"$tmp/default-target.err"; then
    printf '%s\n' "validation-matrix: package-target accepted blank default target" >&2
    exit 1
fi
grep -q 'blank target configuration' "$tmp/default-target.err"

printf '%s\n' "validation-matrix ok"
