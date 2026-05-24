export BUSIERBOX_PAYLOAD_DIR="${BUSIERBOX_PAYLOAD_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
case ":$PATH:" in
    *":$BUSIERBOX_PAYLOAD_DIR/bin:"*) ;;
    *) export PATH="$BUSIERBOX_PAYLOAD_DIR/bin:$PATH" ;;
esac
export PATH="$BUSIERBOX_PAYLOAD_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
[ -n "${TERM:-}" ] || export TERM=xterm-256color
[ -n "${HOME:-}" ] || export HOME="$BUSIERBOX_PAYLOAD_DIR/home"
[ -n "${ZDOTDIR:-}" ] || export ZDOTDIR="$HOME"
if [ -d "$BUSIERBOX_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$BUSIERBOX_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi
alias bbx-list='busierbox list --plain'
alias bbx-doctor='busierbox doctor'
