export PATH="${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin:$PATH"
[ -n "${TERM:-}" ] || export TERM=vt100
autoload -Uz compinit 2>/dev/null && compinit 2>/dev/null

