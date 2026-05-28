#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
[ -x "$bb" ] || {
    printf '%s\n' "recovery: missing executable $bb" >&2
    exit 1
}

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
tmp=$(mktemp -d "$tmp_root/recovery.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
case ${bb##*/} in
    busierbox*) ;;
    *)
        ln -s "$(cd "$(dirname "$bb")" && pwd)/$(basename "$bb")" "$tmp/busierbox"
        bb="$tmp/busierbox"
        ;;
esac

"$bb" persistence --help >/dev/null
"$bb" recovery --help >"$tmp/recovery-help"
grep -q 'deprecated compatibility alias for persistence' "$tmp/recovery-help"
grep -q 'evidence-push' "$tmp/recovery-help"
grep -q 'evidence-then-rshell' "$tmp/recovery-help"
grep -q 'dmesg-push' "$tmp/recovery-help"
"$bb" persistence --survey --json --root "$tmp/root" >"$tmp/survey.json"
python3 -m json.tool "$tmp/survey.json" >/dev/null
python3 - <<'PY' "$tmp/survey.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
summary = data["summary"]
assert summary["storage_count"] == len(data["storage"])
assert summary["method_count"] == len(data["methods"])
api = data["api_collections"]
assert api["storage"]["count_summary_key"] == "summary.storage_count"
assert api["methods"]["count_summary_key"] == "summary.method_count"
assert set(api["storage"]["indexes"]) >= {
    "storage_by_class",
    "storage_by_survives_reboot",
}
assert set(api["methods"]["indexes"]) >= {
    "methods_by_name",
    "methods_by_survives_reboot",
    "methods_by_intrusiveness",
    "methods_by_requires_external_write",
}
assert data["storage_by_class"]["persistent"] == [0, 1, 2, 3]
assert data["storage_by_class"]["volatile"] == [4, 6]
assert data["storage_by_class"]["usually-volatile"] == [5]
assert data["storage_by_survives_reboot"]["yes"] == [0, 1, 2, 3]
assert data["storage_by_survives_reboot"]["no"] == [4, 6]
assert data["storage_by_survives_reboot"]["maybe"] == [5]
assert data["methods_by_name"]["rc-local"] == [5]
assert data["methods_by_survives_reboot"]["yes"] == [0, 1, 2, 3, 5]
assert data["methods_by_survives_reboot"]["maybe"] == [4]
assert data["methods_by_survives_reboot"]["event"] == [6]
assert data["methods_by_survives_reboot"]["login-only"] == [7]
assert data["methods_by_intrusiveness"]["low"] == [5, 7]
assert data["methods_by_intrusiveness"]["medium"] == [0, 1, 2, 3, 6]
assert data["methods_by_intrusiveness"]["high"] == [4]
assert data["methods_by_requires_external_write"]["yes"] == list(range(len(data["methods"])))
assert data["methods_by_requires_external_write"]["no"] == []
PY
"$bb" recovery --survey --json --root "$tmp/root" | python3 -m json.tool >/dev/null
"$bb" persistence --plan --root "$tmp/root" >"$tmp/plan"
grep -q 'openwrt-procd' "$tmp/plan"
grep -q 'cron-reboot' "$tmp/plan"
grep -q 'Persistence survey' "$tmp/plan"
grep -q 'Safety policy' "$tmp/plan"
grep -q 'Storage candidates' "$tmp/plan"
grep -q 'Persistence methods' "$tmp/plan"
grep -Eq 'Path[[:space:]]+Class[[:space:]]+Present[[:space:]]+Writable[[:space:]]+Survives[[:space:]]+Notes' "$tmp/plan"
grep -Eq 'Method[[:space:]]+Path[[:space:]]+Present[[:space:]]+Intrusive[[:space:]]+Reversible' "$tmp/plan"
grep -q 'persistent' "$tmp/plan"
grep -q 'volatile' "$tmp/plan"
grep -q 'persistence_plan=choose one explicit method' "$tmp/plan"

mkdir -p "$tmp/root/etc"
printf '%s\n' '# existing rc.local' >"$tmp/root/etc/rc.local"
"$bb" persistence install --method rc-local --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/dry-run"
grep -q 'Would install persistence method=rc-local' "$tmp/dry-run"
grep -q 'Action: status-only' "$tmp/dry-run"
grep -q 'Generated command: /usr/bin/bbx_recovery persistence status' "$tmp/dry-run"
grep -q 'Would backup existing hook' "$tmp/dry-run"

if "$bb" persistence install --method rc-local --root "$tmp/root" --name bbx_recovery 2>"$tmp/err"; then
    printf '%s\n' "recovery: install without --apply unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'require --apply' "$tmp/err"

if "$bb" persistence install --method rc-local --apply --name bbx_recovery 2>"$tmp/real-root-install.err"; then
    printf '%s\n' "recovery: real-root install without --external unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'real-root install/uninstall requires --external --apply' "$tmp/real-root-install.err"

if "$bb" persistence uninstall --method rc-local --apply --name bbx_recovery 2>"$tmp/real-root-uninstall.err"; then
    printf '%s\n' "recovery: real-root uninstall without --external unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'real-root install/uninstall requires --external --apply' "$tmp/real-root-uninstall.err"

"$bb" persistence install --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test -x "$tmp/root/usr/bin/bbx_recovery"
grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"
grep -q 'action=status-only' "$tmp/root/etc/rc.local"
grep -q 'persistence status' "$tmp/root/etc/rc.local"
ls "$tmp/root/etc"/rc.local.busierbox.bak.* >/dev/null
"$bb" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/status"
grep -q 'installed_method=rc-local' "$tmp/status"
grep -q 'installed_kind=rc.local marked block' "$tmp/status"
grep -q "installed_binary=$tmp/root/usr/bin/bbx_recovery" "$tmp/status"
grep -q 'installed_binary_present=yes' "$tmp/status"
grep -q 'installed_requires_external_write=yes' "$tmp/status"
grep -q 'installed_action=status-only' "$tmp/status"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/status.json"
python3 -m json.tool "$tmp/status.json" >/dev/null
python3 - <<'PY' "$tmp/status.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["installed"] is True
summary = data["summary"]
assert summary["installation_count"] == 1
assert summary["evidence_action_count"] == 0
assert summary["evidence_upload_count"] == 0
assert summary["dmesg_action_count"] == 0
assert summary["rshell_action_count"] == 0
assert summary["rshell_after_evidence_count"] == 0
assert summary["command_action_count"] == 0
assert summary["script_action_count"] == 0
assert summary["operator_supplied_command_count"] == 0
assert summary["external_write_required_count"] == 1
assert summary["command_queue_enabled_count"] == 0
assert summary["hidden_control_channel_count"] == 0
assert summary["all_require_external_write"] is True
assert summary["any_operator_supplied_command"] is False
safety = data["safety"]
assert safety["visible_marked_hooks"] is True
assert safety["uninstall_removes_marked_blocks"] is True
assert safety["hidden_control_channel"] is False
assert safety["command_queue_enabled"] is False
assert safety["self_reinstall"] is False
assert safety["survives_factory_reset_claim"] is False
item = next(item for item in data["installations"] if item["method"] == "rc-local")
api = data["api_collections"]["installations"]
assert api["count_summary_key"] == "summary.installation_count"
assert set(api["indexes"]) >= {
    "installations_by_method",
    "installations_by_action",
    "installations_by_category",
    "installations_by_method_action",
    "installations_by_category_action",
}
assert data["installations_by_method"]["rc-local"] == [0]
assert data["installations_by_action"]["status-only"] == [0]
assert data["installations_by_category"]["status"] == [0]
assert data["installations_by_method_action"]["rc-local:status-only"] == [0]
assert data["installations_by_category_action"]["status:status-only"] == [0]
assert item["action"] == "status-only"
assert item["action_category"] == "status"
assert item["uploads_evidence"] is False
assert item["collects_dmesg"] is False
assert item["starts_rshell"] is False
assert item["starts_rshell_after_evidence"] is False
assert item["executes_operator_supplied_command"] is False
assert item["command_queue_enabled"] is False
assert item["hidden_control_channel"] is False
assert item["kind"] == "rc.local marked block"
assert item["hook_present"] is True
assert item["binary_present"] is True
assert item["script_present"] is False
assert item["requires_external_write"] == "yes"
assert item["survives_reboot"] == "yes"
PY
"$bb" cleanup-ledger --json | python3 -m json.tool >"$tmp/ledger.json"
python3 - <<'PY' "$tmp/ledger.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
details = "\n".join(item.get("detail", "") for item in data.get("entries", []))
for needle in [
    "recovery binary method=rc-local action=status-only name=bbx_recovery",
    "recovery marked hook method=rc-local action=status-only name=bbx_recovery",
]:
    if needle not in details:
        raise SystemExit(f"missing recovery ledger metadata: {needle}")
PY
"$tmp/root/usr/bin/bbx_recovery" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/copied-status"
grep -q 'installed_method=rc-local' "$tmp/copied-status"
"$tmp/root/usr/bin/bbx_recovery" recovery status --root "$tmp/root" --name bbx_recovery >"$tmp/copied-recovery-status"
grep -q 'installed_method=rc-local' "$tmp/copied-recovery-status"

"$bb" recovery install --method rcS --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/rcs-dry-run"
grep -q 'Would install persistence method=rcS' "$tmp/rcs-dry-run"

if "$bb" persistence install --method rc-local --action evidence-push --dry-run --root "$tmp/root" --name 'bad name' >"$tmp/bad-name.out" 2>"$tmp/bad-name.err"; then
    printf '%s\n' "recovery: invalid recovery name unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'recovery name must use letters' "$tmp/bad-name.err"

"$bb" persistence install --method rc-local --action evidence-push --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/evidence-dry-run"
grep -q 'Action: evidence-push' "$tmp/evidence-dry-run"
grep -q 'Generated command: /usr/bin/bbx_recovery evidence push --quiet' "$tmp/evidence-dry-run"
"$bb" persistence install --method rc-local --action evidence-push --apply --root "$tmp/root" --name bbx_recovery >/dev/null
grep -q 'action=evidence-push' "$tmp/root/etc/rc.local"
grep -q '/usr/bin/bbx_recovery evidence push --quiet' "$tmp/root/etc/rc.local"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/evidence-status.json"
python3 - <<'PY' "$tmp/evidence-status.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
summary = data["summary"]
assert summary["installation_count"] == 1
assert summary["evidence_action_count"] == 1
assert summary["evidence_upload_count"] == 1
assert summary["dmesg_action_count"] == 0
assert summary["rshell_action_count"] == 0
assert summary["operator_supplied_command_count"] == 0
assert summary["command_action_count"] == 0
assert summary["script_action_count"] == 0
item = next(item for item in data["installations"] if item["method"] == "rc-local")
assert data["installations_by_method"]["rc-local"] == [0]
assert data["installations_by_action"]["evidence-push"] == [0]
assert data["installations_by_category"]["evidence"] == [0]
assert data["installations_by_method_action"]["rc-local:evidence-push"] == [0]
assert data["installations_by_category_action"]["evidence:evidence-push"] == [0]
assert item["action"] == "evidence-push"
assert item["action_category"] == "evidence"
assert item["uploads_evidence"] is True
assert item["collects_dmesg"] is False
assert item["starts_rshell"] is False
assert item["starts_rshell_after_evidence"] is False
assert item["executes_operator_supplied_command"] is False
assert item["generated_command"] == "/usr/bin/bbx_recovery evidence push --quiet"
assert item["binary_present"] is True
PY
"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null

"$bb" persistence install --method rc-local --action evidence-then-rshell --apply --root "$tmp/root" --name bbx_recovery >/dev/null
grep -q 'action=evidence-then-rshell' "$tmp/root/etc/rc.local"
grep -q '/usr/bin/bbx_recovery evidence push --quiet && /usr/bin/bbx_recovery rshell start' "$tmp/root/etc/rc.local"
"$bb" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/evidence-rshell-status"
grep -q 'installed_action=evidence-then-rshell' "$tmp/evidence-rshell-status"
grep -q 'installed_command=/usr/bin/bbx_recovery evidence push --quiet && /usr/bin/bbx_recovery rshell start' "$tmp/evidence-rshell-status"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/evidence-rshell-status.json"
python3 - <<'PY' "$tmp/evidence-rshell-status.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
summary = data["summary"]
assert summary["evidence_upload_count"] == 1
assert summary["rshell_action_count"] == 1
assert summary["rshell_after_evidence_count"] == 1
item = next(item for item in data["installations"] if item["method"] == "rc-local")
assert data["installations_by_action"]["evidence-then-rshell"] == [0]
assert data["installations_by_category"]["evidence"] == [0]
assert data["installations_by_method_action"]["rc-local:evidence-then-rshell"] == [0]
assert data["installations_by_category_action"]["evidence:evidence-then-rshell"] == [0]
assert item["action"] == "evidence-then-rshell"
assert item["action_category"] == "evidence"
assert item["uploads_evidence"] is True
assert item["starts_rshell"] is True
assert item["starts_rshell_after_evidence"] is True
assert item["executes_operator_supplied_command"] is False
PY
"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null

"$bb" persistence install --method rc-local --action dmesg-push --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/dmesg-dry-run"
grep -q 'Action: dmesg-push' "$tmp/dmesg-dry-run"
grep -q 'bbx_dmesg_dir=' "$tmp/dmesg-dry-run"
grep -q 'dmesg >"$bbx_dmesg"' "$tmp/dmesg-dry-run"
grep -q -- '--dest bbx_recovery-dmesg.txt' "$tmp/dmesg-dry-run"
"$bb" persistence install --method rc-local --action dmesg-push --apply --root "$tmp/root" --name bbx_recovery >/dev/null
grep -q 'action=dmesg-push' "$tmp/root/etc/rc.local"
grep -q 'rm -f "$bbx_dmesg"' "$tmp/root/etc/rc.local"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/dmesg-status.json"
python3 - <<'PY' "$tmp/dmesg-status.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
summary = data["summary"]
assert summary["installation_count"] == 1
assert summary["evidence_action_count"] == 1
assert summary["evidence_upload_count"] == 1
assert summary["dmesg_action_count"] == 1
item = next(item for item in data["installations"] if item["method"] == "rc-local")
assert data["installations_by_action"]["dmesg-push"] == [0]
assert data["installations_by_category"]["evidence"] == [0]
assert data["installations_by_method_action"]["rc-local:dmesg-push"] == [0]
assert data["installations_by_category_action"]["evidence:dmesg-push"] == [0]
assert item["action"] == "dmesg-push"
assert item["action_category"] == "evidence"
assert item["uploads_evidence"] is True
assert item["collects_dmesg"] is True
assert item["starts_rshell"] is False
assert item["executes_operator_supplied_command"] is False
assert "bbx_dmesg_dir=" in item["generated_command"]
assert "dmesg >\"$bbx_dmesg\"" in item["generated_command"]
assert "--dest bbx_recovery-dmesg.txt" in item["generated_command"]
PY
"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null

"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test ! -e "$tmp/root/usr/bin/bbx_recovery"
if grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"; then
    printf '%s\n' "recovery: uninstall left marked block in rc.local" >&2
    exit 1
fi
grep -q '# existing rc.local' "$tmp/root/etc/rc.local"

mkdir -p "$tmp/root/etc/crontabs"
"$bb" persistence install --method cron-reboot --action command --apply --root "$tmp/root" --name bbx_recovery -- 'busierbox rshell start' >/dev/null
grep -q 'action=command' "$tmp/root/etc/crontabs/root"
grep -q 'busierbox rshell start' "$tmp/root/etc/crontabs/root"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/cron-status.json"
python3 - <<'PY' "$tmp/cron-status.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["installed"] is True
summary = data["summary"]
assert summary["installation_count"] == 1
assert summary["command_action_count"] == 1
assert summary["operator_supplied_command_count"] == 1
assert data["installations_by_method"]["cron-reboot"] == [0]
assert data["installations_by_action"]["command"] == [0]
assert data["installations_by_category"]["command"] == [0]
assert data["installations_by_method_action"]["cron-reboot:command"] == [0]
assert data["installations_by_category_action"]["command:command"] == [0]
assert summary["any_operator_supplied_command"] is True
assert any(item["method"] == "cron-reboot" and item["action"] == "command" and item["action_category"] == "command" and item["executes_operator_supplied_command"] is True and item["generated_command"] == "busierbox rshell start" for item in data["installations"])
PY
"$bb" persistence uninstall --method cron-reboot --apply --root "$tmp/root" --name bbx_recovery >/dev/null

printf '%s\n' '#!/bin/sh' 'echo recovery-script' >"$tmp/script.sh"
"$bb" persistence install --method rc-local --action script --file "$tmp/script.sh" --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/script-dry-run"
grep -q "Would copy script: $tmp/root/usr/bin/bbx_recovery.recovery.sh from $tmp/script.sh" "$tmp/script-dry-run"
grep -q 'Generated command: /usr/bin/bbx_recovery.recovery.sh' "$tmp/script-dry-run"
"$bb" persistence install --method rc-local --action script --file "$tmp/script.sh" --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test -x "$tmp/root/usr/bin/bbx_recovery.recovery.sh"
grep -q 'action=script' "$tmp/root/etc/rc.local"
grep -q '/usr/bin/bbx_recovery.recovery.sh' "$tmp/root/etc/rc.local"
"$bb" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/script-status"
grep -q 'installed_action=script' "$tmp/script-status"
grep -q "installed_script=$tmp/root/usr/bin/bbx_recovery.recovery.sh" "$tmp/script-status"
grep -q 'installed_script_present=yes' "$tmp/script-status"
"$bb" persistence status --json --root "$tmp/root" --name bbx_recovery >"$tmp/script-status.json"
python3 -m json.tool "$tmp/script-status.json" >/dev/null
python3 - <<'PY' "$tmp/script-status.json" "$tmp/root"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
root = sys.argv[2]
summary = data["summary"]
assert summary["installation_count"] == 1
assert summary["script_action_count"] == 1
assert summary["operator_supplied_command_count"] == 1
assert summary["any_operator_supplied_command"] is True
item = next(item for item in data["installations"] if item["method"] == "rc-local")
assert data["installations_by_method_action"]["rc-local:script"] == [0]
assert data["installations_by_category_action"]["script:script"] == [0]
assert item["action"] == "script"
assert item["action_category"] == "script"
assert item["executes_operator_supplied_command"] is True
assert item["generated_command"] == "/usr/bin/bbx_recovery.recovery.sh"
assert item["script_path"] == f"{root}/usr/bin/bbx_recovery.recovery.sh"
assert item["script_present"] is True
assert item["binary_present"] is True
PY
"$bb" cleanup-ledger --json | python3 -m json.tool >"$tmp/script-ledger.json"
python3 - <<'PY' "$tmp/script-ledger.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
details = "\n".join(item.get("detail", "") for item in data.get("entries", []))
if "recovery script method=rc-local action=script name=bbx_recovery source=" not in details:
    raise SystemExit("missing recovery script ledger metadata")
PY
"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test ! -e "$tmp/root/usr/bin/bbx_recovery.recovery.sh"

printf '%s\n' "recovery ok"
