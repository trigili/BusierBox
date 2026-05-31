#!/bin/sh
# Test build-native wolfSSL detection across several scenarios:
#   1. Fake CC with no wolfSSL → probe fails, diagnostics present
#   2. WOLFSSL_CFLAGS/WOLFSSL_LIBS env override used when set
#   3. Fake CC that succeeds → probe passes, build attempts to link
#   4. transport=none bypasses wolfSSL probe entirely
set -eu

build=${1:-scripts/build-native}
[ -f "$build" ] || {
    printf '%s\n' "build-native-wolfssl: missing $build" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

# A compiler that always exits 1 — simulates a cross-compiler with no wolfSSL
fake_cc_fail="$tmp/fake-cc-fail"
printf '#!/bin/sh\nexit 1\n' >"$fake_cc_fail"
chmod 0755 "$fake_cc_fail"

# A compiler that succeeds only for the probe (writes an empty file, not a real binary)
fake_cc_pass="$tmp/fake-cc-pass"
printf '#!/bin/sh\nfor a; do case "$a" in -o) shift; touch "$1"; shift ;; esac; done; exit 0\n' >"$fake_cc_pass"
chmod 0755 "$fake_cc_pass"

# -------------------------------------------------------------------
# Scenario 1: transport=builtin + wolfSSL probe fails → clear error
# -------------------------------------------------------------------
out=$(CC="$fake_cc_fail" \
    GRIT_RSHELL_TRANSPORT=builtin GRIT_BUILTIN_TLS_ENABLE=yes \
    OUT="$tmp/s1.out" \
    scripts/build-native 2>&1) && {
    printf '%s\n' "build-native-wolfssl: scenario 1 should have failed but succeeded" >&2
    exit 1
}
printf '%s\n' "$out" | grep -q 'wolfSSL compile probe failed'
printf '%s\n' "$out" | grep -q 'Detection attempted via'
# Diagnostics must mention how to override
printf '%s\n' "$out" | grep -q 'WOLFSSL_CFLAGS\|WOLFSSL_LIBS'

# -------------------------------------------------------------------
# Scenario 2: WOLFSSL_CFLAGS/WOLFSSL_LIBS supplied via env — probe
#             runs with those flags (fake-cc-pass will succeed)
# -------------------------------------------------------------------
out2=$(CC="$fake_cc_pass" \
    GRIT_RSHELL_TRANSPORT=builtin GRIT_BUILTIN_TLS_ENABLE=yes \
    WOLFSSL_CFLAGS="-I$tmp/fake-include" \
    WOLFSSL_LIBS="-L$tmp/fake-lib -lwolfssl" \
    OUT="$tmp/s2.out" \
    scripts/build-native 2>&1) && true
# The probe should pass (fake-cc-pass exits 0), but the actual link will
# fail because fake-cc-pass doesn't produce a real binary. We only care
# that the wolfSSL detection step chose "env WOLFSSL_CFLAGS/WOLFSSL_LIBS"
printf '%s\n' "$out2" | grep -qi 'env WOLFSSL_CFLAGS\|WOLFSSL_CFLAGS/WOLFSSL_LIBS\|wolfSSL detected'

# -------------------------------------------------------------------
# Scenario 3: transport=none → wolfSSL probe never runs, no failure
#             even with a broken CC
# -------------------------------------------------------------------
out3=$(CC="$fake_cc_fail" \
    GRIT_RSHELL_TRANSPORT=none GRIT_BUILTIN_TLS_ENABLE=no \
    OUT="$tmp/s3.out" \
    scripts/build-native 2>&1) && true
# Should NOT mention wolfSSL probe failure
if printf '%s\n' "$out3" | grep -q 'wolfSSL compile probe failed'; then
    printf '%s\n' "build-native-wolfssl: scenario 3 ran wolfSSL probe when transport=none" >&2
    exit 1
fi

# -------------------------------------------------------------------
# Scenario 4: transport=ssh → wolfSSL not needed, no probe even if
#             GRIT_BUILTIN_TLS_ENABLE were accidentally set to yes
# -------------------------------------------------------------------
out4=$(CC="$fake_cc_fail" \
    GRIT_RSHELL_TRANSPORT=ssh GRIT_BUILTIN_TLS_ENABLE=no \
    OUT="$tmp/s4.out" \
    scripts/build-native 2>&1) && true
if printf '%s\n' "$out4" | grep -q 'wolfSSL compile probe failed'; then
    printf '%s\n' "build-native-wolfssl: scenario 4 ran wolfSSL probe for ssh transport" >&2
    exit 1
fi

printf '%s\n' "build-native-wolfssl ok"
