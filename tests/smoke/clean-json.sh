#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}

[ -x "$bb" ] || {
    printf '%s\n' "clean-json: missing executable $bb" >&2
    exit 1
}

case "$bb" in
    /*) bb_abs=$bb ;;
    *) bb_abs=$(pwd)/$bb ;;
esac

tmp_parent=${TMPDIR:-local/tmp}
mkdir -p "$tmp_parent"
tmp=$(mktemp -d "$tmp_parent/busierbox-clean-json.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

cp "$bb_abs" "$tmp/busierbox"
chmod 0755 "$tmp/busierbox"

(
    cd "$tmp"

    ./busierbox clean --dry-run --json >dry-run.json
    python3 -m json.tool dry-run.json >/dev/null
    python3 - dry-run.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("command") != "clean" or doc.get("dry_run") is not True:
    raise SystemExit("clean dry-run json did not identify clean dry-run")
if ".busierbox" not in " ".join(doc.get("would_remove", [])):
    raise SystemExit("clean dry-run json missing runtime root")
if "cleanup_ledger_path" not in doc:
    raise SystemExit("clean dry-run json missing ledger path")
if not isinstance(doc.get("external_entries"), list):
    raise SystemExit("clean dry-run external_entries must be a list")
PY

    ./busierbox extract >/dev/null
    test -d .busierbox/payload
    ./busierbox clean --ledger --json >clean.json
    python3 -m json.tool clean.json >/dev/null
    python3 - clean.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("command") != "clean" or doc.get("dry_run") is not False:
    raise SystemExit("clean json did not identify applied clean")
if ".busierbox" not in " ".join(doc.get("removed", [])):
    raise SystemExit("clean json missing removed runtime root")
PY
    test ! -d .busierbox

    mkdir -p .busierbox/run
    cat >.busierbox/run/cleanup-ledger.jsonl <<'EOF'
{"op":"modify","path":"/root/.ssh/authorized_keys","scope":"external","detail":"test external ledger","mode":"root-merge"}
EOF
    ./busierbox clean --dry-run --json >external-blocked.json
    python3 -m json.tool external-blocked.json >/dev/null
    python3 - external-blocked.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
entries = doc.get("external_entries", [])
if not entries or entries[0].get("blocked_without_external_apply") is not True:
    raise SystemExit("external ledger entry was not blocked without --external")
if entries[0].get("entry", {}).get("scope") != "external":
    raise SystemExit("blocked external ledger entry missing original entry")
PY
    ./busierbox clean --dry-run --external --json >external-included.json
    python3 -m json.tool external-included.json >/dev/null
    python3 - external-included.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
entries = doc.get("external_entries", [])
if not entries or entries[0].get("scope") != "external":
    raise SystemExit("--external dry-run did not expose external ledger entry")
if entries[0].get("blocked_without_external_apply"):
    raise SystemExit("--external dry-run incorrectly marked entry blocked")
PY
    if ./busierbox clean --external >external-no-apply.out 2>external-no-apply.err; then
        printf '%s\n' "clean-json: --external without --apply unexpectedly succeeded" >&2
        exit 1
    fi
    grep -q 'external cleanup requires --external --apply' external-no-apply.err
)

printf '%s\n' "clean-json ok"
