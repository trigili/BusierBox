#!/bin/sh
set -eu

stager=${1:-dist/busierbox-native-stager}
[ -x "$stager" ] || {
    printf '%s\n' "stager-server: missing native stager: $stager" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'kill "$server_pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT HUP INT TERM

artifact="$tmp/dummy-full"
received="$tmp/received-full"
cat >"$artifact" <<'EOF'
#!/bin/sh
case "${1:-}" in
    doctor) echo "dummy doctor ok"; exit 0 ;;
    survey) echo '{"ok":true}'; exit 0 ;;
    *) echo "dummy full"; exit 0 ;;
esac
EOF
chmod 0755 "$artifact"

port=${BUSIERBOX_STAGER_TEST_PORT:-45444}
token=smoke-token
log="$tmp/server.log"

scripts/busierbox-server --listen "127.0.0.1:$port" --token "$token" \
    --artifact "$artifact" --remote-path "$received" --send --exec-doctor --yes --once --timeout 20 \
    >"$log" 2>&1 &
server_pid=$!
sleep 1

"$stager" --callback-host 127.0.0.1 --callback-port "$port" --token "$token" --output "$received" --auto-exec doctor
wait "$server_pid"
server_pid=

[ -x "$received" ] || {
    printf '%s\n' "stager-server: received artifact missing or not executable" >&2
    cat "$log" >&2
    exit 1
}
grep -q 'Token OK' "$log"
grep -q 'dummy doctor ok' "$log"

compiled_stager="$tmp/compiled-default-stager"
compiled_received="$tmp/compiled-received-full"
compiled_log="$tmp/compiled-server.log"
compiled_port=${BUSIERBOX_STAGER_COMPILED_TEST_PORT:-45445}
BB_STAGER_CALLBACK_ENABLE=yes \
BB_STAGER_CALLBACK_HOST=127.0.0.1 \
BB_STAGER_CALLBACK_PORT="$compiled_port" \
BB_STAGER_TOKEN="$token" \
BB_STAGER_OUTPUT_PATH="$compiled_received" \
BB_STAGER_AUTO_EXEC=doctor \
OUT="$compiled_stager" \
scripts/build-stager >/dev/null

scripts/busierbox-server --listen "127.0.0.1:$compiled_port" --token "$token" \
    --artifact "$artifact" --remote-path "$compiled_received" --send --exec-doctor --yes --once --timeout 20 \
    >"$compiled_log" 2>&1 &
server_pid=$!
sleep 1

"$compiled_stager"
wait "$server_pid"
server_pid=

[ -x "$compiled_received" ] || {
    printf '%s\n' "stager-server: compiled-default stager did not receive artifact" >&2
    cat "$compiled_log" >&2
    exit 1
}
grep -q 'Token OK' "$compiled_log"
grep -q 'dummy doctor ok' "$compiled_log"
printf '%s\n' "stager-server ok"
