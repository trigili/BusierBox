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
plan = doc.get("residue_plan")
if not isinstance(plan, dict):
    raise SystemExit("clean dry-run json missing residue plan")
api = (plan.get("api_collections") or {}).get("ledgered_cleanup_paths") or {}
if api.get("count") != plan.get("ledgered_cleanup_path_count"):
    raise SystemExit("residue plan cleanup path API count mismatch")
if api.get("primary_key") != "path":
    raise SystemExit("residue plan cleanup path API primary key missing")
if "ledgered_cleanup_paths_by_scope" not in api.get("indexes", []):
    raise SystemExit("residue plan cleanup path API indexes missing scope lookup")
if doc.get("writes_attempted") != 0 or doc.get("paths_cleaned") != 0 or doc.get("cleanup_complete") is not False:
    raise SystemExit("clean dry-run json cleanup result counters are wrong")
if doc.get("cleanup_warning") != "dry-run only":
    raise SystemExit("clean dry-run json missing dry-run cleanup warning")
if "busierbox clean --ledger --json" not in plan.get("cleanup_commands", []):
    raise SystemExit("clean dry-run residue plan missing cleanup command")
if plan.get("forensic_no_trace") is not False:
    raise SystemExit("clean dry-run residue plan made forensic no-trace claim")
if not isinstance(doc.get("external_entries"), list):
    raise SystemExit("clean dry-run external_entries must be a list")
PY

    ./busierbox extract >/dev/null
    test -d .busierbox/payload
    ./busierbox cleanup-ledger --json >ledger-after-extract.json
    python3 -m json.tool ledger-after-extract.json >/dev/null
    python3 - ledger-after-extract.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("schema") != 1:
    raise SystemExit("cleanup ledger json schema missing")
if not doc.get("path", "").endswith("cleanup-ledger.jsonl"):
    raise SystemExit("cleanup ledger path missing")
entries = doc.get("entries")
if not isinstance(entries, list) or not entries:
    raise SystemExit("cleanup ledger entries missing after extract")
details = "\n".join(item.get("detail", "") for item in entries if isinstance(item, dict))
ops = {item.get("op") for item in entries if isinstance(item, dict)}
scopes = {item.get("scope") for item in entries if isinstance(item, dict)}
if "embedded payload extracted" not in details:
    raise SystemExit("cleanup ledger missing extraction detail")
if "extract" not in ops or "write" not in ops:
    raise SystemExit("cleanup ledger missing extract/write operations")
if "payload" not in scopes:
    raise SystemExit("cleanup ledger missing payload scope")
PY
    ./busierbox clean --dry-run --json >dry-run-after-extract.json
    python3 -m json.tool dry-run-after-extract.json >/dev/null
    python3 - dry-run-after-extract.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
plan = doc.get("residue_plan") or {}
paths = plan.get("ledgered_cleanup_paths")
if not isinstance(paths, list) or not paths:
    raise SystemExit("residue plan missing ledgered cleanup paths after extract")
if plan.get("ledgered_cleanup_path_count") != len(paths):
    raise SystemExit("residue plan ledgered cleanup path count mismatch")
joined = "\n".join(item.get("path", "") for item in paths if isinstance(item, dict))
if ".busierbox/payload" not in joined:
    raise SystemExit("residue plan missing extracted payload path")
scopes = {item.get("scope") for item in paths if isinstance(item, dict)}
if "payload" not in scopes:
    raise SystemExit("residue plan missing payload cleanup scope")
actions = {item.get("cleanup_action") for item in paths if isinstance(item, dict)}
if "remove_with_runtime_root" not in actions:
    raise SystemExit("residue plan missing runtime-root cleanup action")
by_scope = plan.get("ledgered_cleanup_paths_by_scope") or {}
if not by_scope.get("payload"):
    raise SystemExit("residue plan missing cleanup paths by scope")
if paths[by_scope["payload"][0]].get("scope") != "payload":
    raise SystemExit("residue plan scope index points at wrong cleanup path")
by_action = plan.get("ledgered_cleanup_paths_by_cleanup_action") or {}
if "remove_with_runtime_root" not in by_action:
    raise SystemExit("residue plan missing cleanup paths by action")
by_path = plan.get("ledgered_cleanup_paths_by_path") or {}
if not any(".busierbox/payload" in key for key in by_path):
    raise SystemExit("residue plan missing cleanup paths by path")
api = (plan.get("api_collections") or {}).get("ledgered_cleanup_paths") or {}
if api.get("count") != len(paths):
    raise SystemExit("residue plan cleanup path API count mismatch after extract")
if "ledgered_cleanup_paths_by_cleanup_action" not in api.get("indexes", []):
    raise SystemExit("residue plan cleanup path API missing action index")
resources = plan.get("api_resources_by_name") or {}
if resources.get("ledgered_cleanup_paths", {}).get("records_key") != "ledgered_cleanup_paths":
    raise SystemExit("residue plan cleanup path API resource missing")
if plan.get("external_blocked_count") != 0:
    raise SystemExit("residue plan unexpectedly blocked external entries")
PY
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
if doc.get("writes_attempted", 0) < 1:
    raise SystemExit("clean json missing writes_attempted")
if doc.get("paths_failed") != 0:
    raise SystemExit("clean json reported path failures")
if doc.get("cleanup_complete") is not True:
    raise SystemExit("clean json did not report complete cleanup")
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
if doc.get("writes_blocked") != 1:
    raise SystemExit("blocked external ledger did not increment writes_blocked")
plan = doc.get("residue_plan") or {}
if "/root/.ssh/authorized_keys" not in plan.get("uncleanable_paths", []):
    raise SystemExit("blocked external ledger path missing from residue plan")
if plan.get("external_blocked_count") != 1:
    raise SystemExit("blocked external ledger count missing from residue plan")
if plan.get("ledgered_cleanup_path_count") != 0:
    raise SystemExit("external-only ledger should not create runtime cleanup paths")
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

    mkdir -p .busierbox/run
    cat >.busierbox/run/cleanup-ledger.jsonl <<'EOF'
{"op":"modify","path":"/opt/vendor/state","scope":"external","detail":"unsupported external ledger","mode":"vendor-file"}
EOF
    ./busierbox clean --external --apply --json >external-unsupported-apply.json
    python3 -m json.tool external-unsupported-apply.json >/dev/null
    python3 - external-unsupported-apply.json <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("dry_run") is not False or doc.get("external_cleanup_applied") is not True:
    raise SystemExit("unsupported external apply json did not identify applied external cleanup")
if doc.get("writes_attempted", 0) < 2:
    raise SystemExit("unsupported external apply did not count external and runtime attempts")
if doc.get("writes_blocked") != 1:
    raise SystemExit("unsupported external apply did not count blocked entry")
if doc.get("paths_cleaned") != 1:
    raise SystemExit("unsupported external apply should only count runtime root cleaned")
if doc.get("cleanup_complete") is not False:
    raise SystemExit("unsupported external apply overclaimed complete cleanup")
if doc.get("cleanup_warning") != "unsupported external ledger entries require manual cleanup":
    raise SystemExit("unsupported external apply warning missing")
PY
)

printf '%s\n' "clean-json ok"
