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
"$bb" persistence --survey --json --root "$tmp/root" | python3 -m json.tool >/dev/null
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
grep -q 'Would backup existing hook' "$tmp/dry-run"

if "$bb" persistence install --method rc-local --root "$tmp/root" --name bbx_recovery 2>"$tmp/err"; then
    printf '%s\n' "recovery: install without --apply unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'require --apply' "$tmp/err"

"$bb" persistence install --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test -x "$tmp/root/usr/bin/bbx_recovery"
grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"
grep -q 'persistence status' "$tmp/root/etc/rc.local"
ls "$tmp/root/etc"/rc.local.busierbox.bak.* >/dev/null
"$bb" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/status"
grep -q 'installed_method=rc-local' "$tmp/status"
"$tmp/root/usr/bin/bbx_recovery" persistence status --root "$tmp/root" --name bbx_recovery >"$tmp/copied-status"
grep -q 'installed_method=rc-local' "$tmp/copied-status"
"$tmp/root/usr/bin/bbx_recovery" recovery status --root "$tmp/root" --name bbx_recovery >"$tmp/copied-recovery-status"
grep -q 'installed_method=rc-local' "$tmp/copied-recovery-status"

"$bb" recovery install --method rcS --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/rcs-dry-run"
grep -q 'Would install persistence method=rcS' "$tmp/rcs-dry-run"

"$bb" persistence uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test ! -e "$tmp/root/usr/bin/bbx_recovery"
if grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"; then
    printf '%s\n' "recovery: uninstall left marked block in rc.local" >&2
    exit 1
fi
grep -q '# existing rc.local' "$tmp/root/etc/rc.local"

printf '%s\n' "recovery ok"
