#!/bin/sh

qemu_system_serial_arg() {
    binary=$1
    case "$binary" in
        qemu-system-arm|qemu-system-aarch64)
            printf '%s\n' "-nographic"
            ;;
        *)
            printf '%s\n' "-nographic"
            ;;
    esac
}

prepare_payload_dir() {
    payload=$1
    grit=$2
    smoke_init=$3
    smoke_dir=$4

    rm -rf "$payload"
    mkdir -p "$payload"
    cp "$grit" "$payload/grit"
    cp "$smoke_init" "$payload/smoke-init.sh"
    cp "$smoke_dir/grit-smoke.sh" "$payload/grit-smoke.sh"
    cp "$smoke_dir/validate-survey-json.py" "$payload/validate-survey-json.py"
    chmod 0755 "$payload/grit" "$payload/smoke-init.sh" "$payload/grit-smoke.sh"
}

