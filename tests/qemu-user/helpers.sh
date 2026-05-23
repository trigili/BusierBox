#!/bin/sh

repo_root() {
    cd "$(dirname "$0")/../.." && pwd
}

find_qemu_user() {
    interp=$1
    if [ "$interp" = "native" ]; then
        printf '%s\n' native
        return 0
    fi
    if command -v "$interp" >/dev/null 2>&1; then
        command -v "$interp"
        return 0
    fi
    if command -v "${interp%-static}" >/dev/null 2>&1; then
        command -v "${interp%-static}"
        return 0
    fi
    return 1
}

copy_artifacts_note() {
    artifact_dir=$1
    shift
    mkdir -p "$artifact_dir"
    printf '%s\n' "$*" >>"$artifact_dir/skip.txt"
}

