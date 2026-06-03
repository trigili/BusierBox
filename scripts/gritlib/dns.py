"""Small DNS packet helpers for grit-console probe serving."""


def dns_parse_qname(packet, offset=12):
    labels = []
    pos = offset
    while pos < len(packet):
        length = packet[pos]
        pos += 1
        if length == 0:
            return ".".join(labels), pos
        if length & 0xC0:
            return "", pos
        if pos + length > len(packet):
            return "", pos
        labels.append(packet[pos:pos + length].decode("ascii", errors="replace"))
        pos += length
    return "", pos


def dns_txt_answer_packet(query, txt_chunks, ttl=30):
    if len(query) < 12:
        return b""
    qname, qend = dns_parse_qname(query)
    if not qname or qend + 4 > len(query):
        return b""
    qtype = int.from_bytes(query[qend:qend + 2], "big")
    qclass = int.from_bytes(query[qend + 2:qend + 4], "big")
    qdcount = int.from_bytes(query[4:6], "big")
    if qdcount < 1:
        return b""
    question = query[12:qend + 4]
    answer_chunks = txt_chunks if qtype in (16, 255) and qclass in (1, 255) else []
    header = (
        query[:2] +
        b"\x81\x80" +
        b"\x00\x01" +
        len(answer_chunks).to_bytes(2, "big") +
        b"\x00\x00\x00\x00"
    )
    answers = []
    for chunk in answer_chunks:
        text = chunk.encode("ascii", errors="replace")[:255]
        rdata = bytes([len(text)]) + text
        answers.append(
            b"\xc0\x0c" +
            b"\x00\x10" +
            b"\x00\x01" +
            int(ttl).to_bytes(4, "big") +
            len(rdata).to_bytes(2, "big") +
            rdata
        )
    return header + question + b"".join(answers)
