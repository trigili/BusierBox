export GRIT_PAYLOAD_DIR="${GRIT_PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
export PATH="$GRIT_PAYLOAD_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=xterm-256color
[ -n "${HOME:-}" ] || export HOME="$GRIT_PAYLOAD_DIR/home"
[ -n "${ZDOTDIR:-}" ] || export ZDOTDIR="$HOME"
if [ -n "${GRIT_PAYLOAD_DIR:-}" ] && [ -d "$GRIT_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$GRIT_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi
echo "griTTYkit payload: ${GRIT_PAYLOAD_DIR:-unknown}" 2>/dev/null || true
