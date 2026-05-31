#!/bin/sh
# Verify wolfSSL detection logic in build-native: env vars → pkg-config → -lwolfssl fallback.
set -eu

build=${1:-scripts/lib/build-native}

[ -f "$build" ] || {
    printf '%s\n' "wolfssl-detection: missing $build" >&2
    exit 1
}

# Priority 1: WOLFSSL_CFLAGS / WOLFSSL_LIBS env vars are tried first
awk '/GRIT_BUILTIN_TLS_ENABLE.*yes/,/wolfssl_ok=1/' "$build" | grep -q 'WOLFSSL_CFLAGS\|WOLFSSL_LIBS'

# Priority 2: pkg-config is tried second
awk '/GRIT_BUILTIN_TLS_ENABLE.*yes/,/wolfssl_ok=1/' "$build" | grep -q 'pkg-config'

# Fallback: -lwolfssl with no cflags
grep -q 'lwolfssl' "$build"

# Compile probe must be used to validate detection
grep -q '_probe_dir\|probe\.c\|wolfSSL_Init' "$build"

# On probe failure, diagnostic output must mention pkg-config state and header path
grep -q 'pkg-config.*wolfssl\|wolfssl/ssl.h' "$build"

# On probe failure, override hint must be present
grep -q 'WOLFSSL_CFLAGS\|WOLFSSL_LIBS' "$build"

# package-target must pass WOLFSSL_CFLAGS / WOLFSSL_LIBS through to build-native
pkg=${2:-scripts/lib/package-target}
[ -f "$pkg" ] || {
    printf '%s\n' "wolfssl-detection: missing $pkg" >&2
    exit 1
}
grep -q 'WOLFSSL_CFLAGS' "$pkg"
grep -q 'WOLFSSL_LIBS' "$pkg"

printf '%s\n' "wolfssl-detection ok"
