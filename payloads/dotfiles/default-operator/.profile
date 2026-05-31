export GRIT_PAYLOAD_DIR="${GRIT_PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
case ":$PATH:" in
    *":$GRIT_PAYLOAD_DIR/bin:"*) ;;
    *) export PATH="$GRIT_PAYLOAD_DIR/bin:$PATH" ;;
esac
export PATH="$GRIT_PAYLOAD_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=xterm-256color
[ -n "${HOME:-}" ] || export HOME="$GRIT_PAYLOAD_DIR/home"
[ -n "${ZDOTDIR:-}" ] || export ZDOTDIR="$HOME"
if [ -d "$GRIT_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$GRIT_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi
alias grit-list='grit list --plain'
alias grit-doctor='grit doctor'
