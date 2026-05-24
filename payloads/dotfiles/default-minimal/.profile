export BUSIERBOX_PAYLOAD_DIR="${BUSIERBOX_PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
export PATH="$BUSIERBOX_PAYLOAD_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=vt100
[ -n "${HOME:-}" ] || export HOME="$BUSIERBOX_PAYLOAD_DIR/home"
[ -n "${ZDOTDIR:-}" ] || export ZDOTDIR="$HOME"
