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
    busierbox=$2
    smoke_init=$3
    smoke_dir=$4

    rm -rf "$payload"
    mkdir -p "$payload"
    cp "$busierbox" "$payload/busierbox"
    cp "$smoke_init" "$payload/smoke-init.sh"
    cp "$smoke_dir/busierbox-smoke.sh" "$payload/busierbox-smoke.sh"
    cp "$smoke_dir/validate-survey-json.py" "$payload/validate-survey-json.py"
    chmod 0755 "$payload/busierbox" "$payload/smoke-init.sh" "$payload/busierbox-smoke.sh"
}

