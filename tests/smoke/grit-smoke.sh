#!/bin/sh
set -u

BB=${GRIT:-./grit}
ARTIFACT_DIR=${ARTIFACT_DIR:-.}

mkdir -p "$ARTIFACT_DIR" || exit 1

run() {
    name=$1
    shift
    printf '%s\n' "== $name ==" >>"$ARTIFACT_DIR/smoke.log"
    "$@" >"$ARTIFACT_DIR/$name.stdout" 2>"$ARTIFACT_DIR/$name.stderr"
    rc=$?
    printf '%s %s\n' "$name" "$rc" >>"$ARTIFACT_DIR/status.txt"
    return "$rc"
}

run_optional() {
    name=$1
    shift
    run "$name" "$@" || true
}

: >"$ARTIFACT_DIR/status.txt"
: >"$ARTIFACT_DIR/smoke.log"

run list "$BB" list || exit 1
run help "$BB" --help || exit 1
run survey "$BB" survey || exit 1
"$BB" survey --json >"$ARTIFACT_DIR/survey.json" 2>"$ARTIFACT_DIR/survey-json.stderr" || exit 1
run envfix "$BB" envfix || exit 1
run extract "$BB" extract || exit 1
run extract-reuse "$BB" extract || exit 1
run sh "$BB" sh -c "echo ok" || exit 1
run cp-help "$BB" cp --help || exit 1
run dd-help "$BB" dd --help || exit 1
run nc-help "$BB" nc --help || exit 1
run_optional tmux-help "$BB" tmux --help
run_optional strace-help "$BB" strace --help
run_optional gdbserver-help "$BB" gdbserver --help
run config-info "$BB" config-info || exit 1
run uname "$BB" uname -a || exit 1
run id "$BB" id || exit 1
run df "$BB" df . || exit 1
run_optional free "$BB" free
run_optional ps "$BB" ps

if command -v python3 >/dev/null 2>&1; then
    python3 "$(dirname "$0")/validate-survey-json.py" "$ARTIFACT_DIR/survey.json" >"$ARTIFACT_DIR/survey-validation.txt"
fi

printf '%s\n' "smoke ok" | tee "$ARTIFACT_DIR/result.txt"
