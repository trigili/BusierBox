export PATH="${BUSIERBOX_PAYLOAD_DIR:-/mnt/busierbox}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=vt100
[ -n "${HOME:-}" ] || export HOME="${BUSIERBOX_PAYLOAD_DIR:-/mnt/busierbox}/home"

