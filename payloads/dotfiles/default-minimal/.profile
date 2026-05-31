export GRIT_PAYLOAD_DIR="${GRIT_PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
export PATH="$GRIT_PAYLOAD_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=vt100
[ -n "${HOME:-}" ] || export HOME="$GRIT_PAYLOAD_DIR/home"
[ -n "${ZDOTDIR:-}" ] || export ZDOTDIR="$HOME"
