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

"$bb" recovery --help >/dev/null
"$bb" recovery --survey --json --root "$tmp/root" | python3 -m json.tool >/dev/null
"$bb" recovery --plan --root "$tmp/root" >"$tmp/plan"
grep -q 'openwrt-procd' "$tmp/plan"
grep -q 'cron-reboot' "$tmp/plan"
grep -q 'recovery_plan=choose one explicit method' "$tmp/plan"

"$bb" recovery install --method rc-local --dry-run --root "$tmp/root" --name bbx_recovery >"$tmp/dry-run"
grep -q 'Would install recovery method=rc-local' "$tmp/dry-run"

if "$bb" recovery install --method rc-local --root "$tmp/root" --name bbx_recovery 2>"$tmp/err"; then
    printf '%s\n' "recovery: install without --apply unexpectedly succeeded" >&2
    exit 1
fi
grep -q 'require --apply' "$tmp/err"

"$bb" recovery install --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test -x "$tmp/root/usr/bin/bbx_recovery"
grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"
"$bb" recovery status --root "$tmp/root" --name bbx_recovery >"$tmp/status"
grep -q 'installed_method=rc-local' "$tmp/status"

"$bb" recovery uninstall --method rc-local --apply --root "$tmp/root" --name bbx_recovery >/dev/null
test ! -e "$tmp/root/usr/bin/bbx_recovery"
if grep -q 'BEGIN BUSIERBOX RECOVERY bbx_recovery' "$tmp/root/etc/rc.local"; then
    printf '%s\n' "recovery: uninstall left marked block in rc.local" >&2
    exit 1
fi

printf '%s\n' "recovery ok"
