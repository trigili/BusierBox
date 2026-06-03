"""Small TFTP packet helpers for grit-console probe serving."""

import socket


def parse_tftp_rrq(packet):
    if len(packet) < 4 or packet[:2] != b"\x00\x01":
        return "", ""
    parts = packet[2:].split(b"\0")
    if len(parts) < 2:
        return "", ""
    try:
        filename = parts[0].decode("utf-8", errors="replace").strip()
        mode = parts[1].decode("ascii", errors="replace").strip().lower()
    except UnicodeDecodeError:
        return "", ""
    return filename.lstrip("/"), mode


def tftp_error_packet(code, message):
    return b"\x00\x05" + int(code).to_bytes(2, "big") + str(message).encode("ascii", errors="replace") + b"\0"


def tftp_data_packet(block, payload):
    return b"\x00\x03" + int(block).to_bytes(2, "big") + payload


def tftp_ack_block(packet):
    if len(packet) >= 4 and packet[:2] == b"\x00\x04":
        return int.from_bytes(packet[2:4], "big")
    return -1


def send_tftp_file(sock, addr, payload, timeout=3.0):
    block = 1
    offset = 0
    sock.settimeout(timeout)
    while True:
        chunk = payload[offset:offset + 512]
        packet = tftp_data_packet(block, chunk)
        for _attempt in range(5):
            sock.sendto(packet, addr)
            try:
                ack, ack_addr = sock.recvfrom(516)
            except socket.timeout:
                continue
            if ack_addr == addr and tftp_ack_block(ack) == block:
                break
        else:
            raise TimeoutError(f"timeout waiting for TFTP ACK block {block}")
        offset += len(chunk)
        if len(chunk) < 512:
            return block
        block = (block + 1) & 0xFFFF
        if block == 0:
            block = 1
