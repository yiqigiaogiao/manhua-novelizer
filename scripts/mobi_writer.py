# -*- coding: utf-8 -*-
"""极简 MOBI（PalmDOC，无压缩）写出器。

不依赖 calibre / kindlegen：直接生成 PalmDB + MOBI 6 头 + 纯文本记录，
Kindle / KOReader / Calibre 均可读取。图片不嵌入（封面另出 PNG）。
"""
from __future__ import annotations

import os
import struct
import time

RECORD_SIZE = 4096
EPOCH_1904 = 2082844800  # 1904-01-01 到 1970-01-01 的秒数


def _palm_time() -> int:
    return int(time.time()) + EPOCH_1904


def _exth(records: list[tuple[int, bytes]]) -> bytes:
    body = b"".join(struct.pack(">II", rtype, 8 + len(data)) + data for rtype, data in records)
    payload = struct.pack(">II", 12 + len(body), len(records)) + body
    out = b"EXTH" + payload
    pad = (-len(out)) % 4
    return out + b"\x00" * pad


def _mobi_header(full_name_offset: int, full_name_length: int, text_records: int) -> bytes:
    parts = [
        b"MOBI",
        struct.pack(">I", 232),          # header length
        struct.pack(">I", 2),            # mobi type: book
        struct.pack(">I", 65001),        # UTF-8
        struct.pack(">I", 0x12345678),   # unique id
        struct.pack(">I", 6),            # file version
        struct.pack(">I", 0xFFFFFFFF),   # orthographic index
        struct.pack(">I", 0xFFFFFFFF),   # inflection index
        struct.pack(">I", 0xFFFFFFFF),   # index names
        struct.pack(">I", 0xFFFFFFFF),   # index keys
    ]
    parts += [struct.pack(">I", 0xFFFFFFFF)] * 6      # extra indexes 0-5
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # first non-book index
    parts.append(struct.pack(">I", full_name_offset))
    parts.append(struct.pack(">I", full_name_length))
    parts.append(struct.pack(">I", 0x0804))           # locale zh-CN
    parts.append(struct.pack(">I", 0))                # input language
    parts.append(struct.pack(">I", 0))                # output language
    parts.append(struct.pack(">I", 6))                # min version
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # first image index
    parts += [struct.pack(">I", 0)] * 4               # huffman off/cnt/tbl off/tbl len
    parts.append(struct.pack(">I", 0x40))             # EXTH flags
    parts.append(b"\x00" * 32)
    parts.append(struct.pack(">I", 0xFFFFFFFF))
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # DRM offset
    parts.append(struct.pack(">I", 0))                # DRM count
    parts.append(struct.pack(">I", 0))                # DRM size
    parts.append(struct.pack(">I", 0))                # DRM flags
    parts.append(b"\x00" * 8)
    parts.append(struct.pack(">H", 1))                # first content record
    parts.append(struct.pack(">H", text_records))     # last content record
    parts.append(struct.pack(">I", 1))
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # FCIS
    parts.append(struct.pack(">I", 0))
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # FLIS
    parts.append(struct.pack(">I", 0))
    parts.append(b"\x00" * 8)
    parts.append(struct.pack(">I", 0xFFFFFFFF))
    parts.append(struct.pack(">I", 0))
    parts.append(struct.pack(">I", 0xFFFFFFFF))
    parts.append(struct.pack(">I", 0xFFFFFFFF))
    parts.append(struct.pack(">I", 0))                # extra record data flags
    parts.append(struct.pack(">I", 0xFFFFFFFF))       # INDX offset
    header = b"".join(parts)
    if len(header) != 232:
        raise ValueError(f"MOBI header must be 232 bytes, got {len(header)}")
    return header


def _pad4(data: bytes) -> bytes:
    return data + b"\x00" * ((-len(data)) % 4)


def build_mobi(chapters: list[dict], out_path: str, title: str, author: str = "") -> str:
    """chapters: [{"title","text"}]，纯文本段落。"""
    html_parts = ["<html><head><guide><reference type=\"toc\" title=\"目录\" filepos=0000000000 /></guide><body>"]
    for ch in chapters:
        html_parts.append(f"<h2>{_escape(ch['title'])}</h2>")
        for para in ch["text"].split("\n"):
            para = para.strip()
            if not para:
                continue
            html_parts.append(f"<p>{_escape(para)}</p>")
        html_parts.append("<mbp:pagebreak/>")
    html_parts.append("</body></html>")
    raw = "".join(html_parts).encode("utf-8")

    text_records = [raw[i:i + RECORD_SIZE] for i in range(0, len(raw), RECORD_SIZE)] or [b""]

    exth = _exth([
        (100, author.encode("utf-8") or b"Unknown"),
        (503, title.encode("utf-8")),
        (501, b"EBOK"),
    ])
    full_name = title.encode("utf-8")

    # record 0: PalmDOC header(16) + MOBI header(232) + EXTH + name
    # 先算出 name 偏移：16 + 232 + len(exth)
    name_offset = 16 + 232 + len(exth)
    mobi = _mobi_header(name_offset, len(full_name), len(text_records))
    doc_header = struct.pack(">HHIHHHH", 1, 0, len(raw), len(text_records), RECORD_SIZE, 0, 0)
    record0 = _pad4(doc_header + mobi + exth + full_name)

    records = [record0] + text_records
    num_records = len(records)

    # PalmDB header（固定 78 字节）
    palm = bytearray()
    palm += title.encode("utf-8")[:31].ljust(32, b"\x00")
    palm += struct.pack(">HH", 0, 0)                       # attributes, version
    palm += struct.pack(">IIIIII", _palm_time(), _palm_time(), 0, 0, 0, 0)
    palm += b"BOOK" + b"MOBI"                              # type, creator
    palm += struct.pack(">II", 0, 0)                       # uniqueIDseed, nextRecordListID
    palm += struct.pack(">H", num_records)
    if len(palm) != 78:
        raise ValueError(f"PalmDB header must be 78 bytes, got {len(palm)}")

    # 记录偏移表
    offset = 78 + 8 * num_records + 2
    table = bytearray()
    for i, rec in enumerate(records):
        table += struct.pack(">I", offset) + struct.pack(">I", i & 0xFFFFFF)
        offset += len(rec)
    palm += table + b"\x00\x00"

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(bytes(palm))
        for rec in records:
            fh.write(rec)
    return out_path


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def inspect(path: str) -> dict:
    """读回并校验自己的 MOBI 结构（不解码正文）。"""
    with open(path, "rb") as fh:
        data = fh.read()
    name = data[0:32].rstrip(b"\x00").decode("utf-8", "replace")
    num = struct.unpack(">H", data[76:78])[0]
    offsets = [struct.unpack(">I", data[78 + 8 * i:82 + 8 * i])[0] for i in range(num)]
    ok = all(offsets[i] < offsets[i + 1] for i in range(num - 1)) and offsets[0] == 78 + 8 * num + 2
    rec0 = data[offsets[0]:offsets[1] if num > 1 else len(data)]
    compression, _, text_len, text_recs = struct.unpack(">HHIH", rec0[:10])
    return {"title": name, "records": num, "offsets_ok": ok,
            "compression": compression, "text_bytes": text_len,
            "text_records": text_recs, "size": len(data)}
