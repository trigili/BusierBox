#!/bin/sh
# Test the package-target wolfSSL cross-compile preflight.
# Simulates the failure mode where pkg-config returns empty cflags
# (wolfSSL headers in /usr/include) but the cross-compiler can't
# see them because it uses its own sysroot.
set -eu

pkg=${1:-scripts/package-target}
build=${2:-scripts/build-native}

[ -f "$pkg" ] || {
    printf '%s\n' "wolfssl-cross-preflight: missing $pkg" >&2
    exit 1
}
[ -f "$build" ] || {
    printf '%s\n' "wolfssl-cross-preflight: missing $build" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

# -------------------------------------------------------------------
# Test 1: package-target preflight probe present in source
# -------------------------------------------------------------------
grep -q 'GRIT_BUILTIN_TLS_ENABLE.*yes\|builtin.*wolfSSL' "$pkg"
grep -q 'cross_cc\|WOLFSSL_CFLAGS' "$pkg"
grep -q 'cross sysroot\|cross-compiler' "$pkg"

# -------------------------------------------------------------------
# Test 2: build-native error message mentions the override hint
#         when pkg-config is consulted but probe fails
# -------------------------------------------------------------------
# Simulate: pkg-config says wolfssl exists with empty cflags,
# but fake cross-cc can't find the headers
fake_pkgconfig="$tmp/fake-pkg-config"
cat >"$fake_pkgconfig" <<'EOF'
#!/bin/sh
# Simulate pkg-config: wolfssl known, empty cflags (header in /usr/include)
case "$*" in
    *"--exists wolfssl"*|*"wolfssl"*"--exists"*) exit 0 ;;
    *"--cflags wolfssl"*|*"wolfssl"*"--cflags"*) printf ''; exit 0 ;;
    *"--libs wolfssl"*|*"wolfssl"*"--libs"*) printf '-lwolfssl\n'; exit 0 ;;
    *) exec /usr/bin/pkg-config "$@" 2>/dev/null || exit 1 ;;
esac
EOF
chmod 0755 "$fake_pkgconfig"

fake_cc="$tmp/fake-cross-cc"
printf '#!/bin/sh\nexit 1\n' >"$fake_cc"
chmod 0755 "$fake_cc"

# Run build-native with the fake pkg-config and cross-like CC
out=$(PATH="$tmp:$PATH" CC="$fake_cc" \
    GRIT_RSHELL_TRANSPORT=builtin GRIT_BUILTIN_TLS_ENABLE=yes \
    OUT="$tmp/probe-out" \
    scripts/build-native 2>&1) && {
    printf '%s\n' "wolfssl-cross-preflight: build-native should have failed" >&2
    exit 1
}

# Must name the detection method and include override hint
printf '%s\n' "$out" | grep -q 'wolfSSL compile probe failed'
printf '%s\n' "$out" | grep -q 'pkg-config'
printf '%s\n' "$out" | grep -q 'WOLFSSL_CFLAGS\|WOLFSSL_LIBS'
# Must mention the override mechanism
printf '%s\n' "$out" | grep -q 'export WOLFSSL_CFLAGS\|WOLFSSL_CFLAGS=\|To override'

# -------------------------------------------------------------------
# Test 3: WOLFSSL_CFLAGS/WOLFSSL_LIBS bypass avoids the probe failure
# -------------------------------------------------------------------
# Fake CC that succeeds when -I and -L flags are present (simulates
# wolfSSL available in a non-default cross sysroot path)
fake_cc_check="$tmp/fake-cross-cc-check"
cat >"$fake_cc_check" <<'EOF'
#!/bin/sh
# Succeed only if -I flag is present (cross-sysroot wolfSSL found)
for a; do
    case "$a" in
        -I*wolfssl*|-I*/cross/*) touch_out=1 ;;
        -o) shift; out="$1" ;;
    esac
done
[ "${touch_out:-0}" = 1 ] && [ -n "${out:-}" ] && { touch "$out"; exit 0; }
exit 1
EOF
chmod 0755 "$fake_cc_check"

out3=$(CC="$fake_cc_check" \
    GRIT_RSHELL_TRANSPORT=builtin GRIT_BUILTIN_TLS_ENABLE=yes \
    WOLFSSL_CFLAGS="-I$tmp/cross/wolfssl/include" \
    WOLFSSL_LIBS="-L$tmp/cross/wolfssl/lib -lwolfssl" \
    OUT="$tmp/s3.out" \
    scripts/build-native 2>&1) && true
# The wolfSSL detection step should succeed (probe passes with the -I flag)
if printf '%s\n' "$out3" | grep -q 'wolfSSL compile probe failed'; then
    printf '%s\n' "wolfssl-cross-preflight: WOLFSSL_CFLAGS override did not reach probe" >&2
    exit 1
fi
printf '%s\n' "$out3" | grep -q 'wolfSSL detected\|env WOLFSSL_CFLAGS\|WOLFSSL_CFLAGS/WOLFSSL_LIBS'

printf '%s\n' "wolfssl-cross-preflight ok"
