#!/bin/sh
# Static guard for the hard validation cases called out in local/GOAL.md.
set -eu

menu=${1:-scripts/menuconfig}
pkg=${2:-scripts/package-target}

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
require 'invalid shell provider' 'BB_RSHELL_SHELL_PROVIDER'
require 'invalid retry backoff' 'BB_RSHELL_RETRY_BACKOFF'

grep -q 'TARGET_STATUS.*blank' "$pkg" || {
    printf '%s\n' "validation-matrix: package-target must reject blank default target" >&2
    exit 1
}

printf '%s\n' "validation-matrix ok"
