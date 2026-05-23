#!/bin/sh
set -u

if [ "$#" -lt 4 ]; then
    printf '%s\n' "usage: smoke.sh TARGET QEMU|native BINARY ARTIFACT_DIR" >&2
    exit 2
fi

target=$1
qemu=$2
binary=$3
artifact_dir=$4

mkdir -p "$artifact_dir" || exit 1
cp "$binary" "$artifact_dir/busierbox" || exit 1
chmod 0755 "$artifact_dir/busierbox"

run_bb() {
    if [ "$qemu" = "native" ]; then
        "$artifact_dir/busierbox" "$@"
    else
        "$qemu" "$artifact_dir/busierbox" "$@"
    fi
}

run() {
    name=$1
    shift
    printf '%s\n' "== $target / $name ==" >>"$artifact_dir/smoke.log"
    run_bb "$@" >"$artifact_dir/$name.stdout" 2>"$artifact_dir/$name.stderr"
    rc=$?
    printf '%s %s\n' "$name" "$rc" >>"$artifact_dir/status.txt"
    return "$rc"
}

run_optional() {
    name=$1
    shift
    run "$name" "$@" || true
}

: >"$artifact_dir/status.txt"
: >"$artifact_dir/smoke.log"

run list list || exit 1
run help --help || exit 1
run survey survey || exit 1
run_bb survey --json >"$artifact_dir/survey.json" 2>"$artifact_dir/survey-json.stderr" || exit 1
run envfix envfix || exit 1
run nc-help nc --help || exit 1
run http-help http --help || exit 1
run serve-help serve --help || exit 1
run uname uname -a || exit 1
run id id || exit 1
run df df || exit 1
run_optional free free
run_optional ps ps

if command -v python3 >/dev/null 2>&1; then
    python3 "$(dirname "$0")/../smoke/validate-survey-json.py" "$artifact_dir/survey.json" >"$artifact_dir/survey-validation.txt"
    scripts/config-from-survey "$artifact_dir/survey.json" >"$artifact_dir/recommended-config.txt"
else
    printf '%s\n' "skip: python3 unavailable for JSON/config validation" >"$artifact_dir/survey-validation.txt"
fi

printf '%s\n' "pass" >"$artifact_dir/result.txt"

