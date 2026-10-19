#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S7 - assemble chapter drafts into a book.

Reads <work>/ch*/draft.md (and <work>/*.md as a fallback), sorts by 话号,
and writes:
    <out>/book.md      full text with a table of contents
    <out>/stats.csv    per-chapter pages / words / scenes / characters
    <out>/index.csv    per-chapter scene and cast index
    <out>/book.docx    optional, requires python-docx

Usage:
    python assemble.py --work . --out book --title "书名"
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, parts[2]


def chapter_key(meta: dict, path: str) -> float:
    for field in ("话", "chapter"):
        if field in meta:
            try:
                return float(str(meta[field]).strip())
            except ValueError:
                pass
    m = re.search(r"(\d+(?:\.\d+)?)", os.path.basename(path))
    return float(m.group(1)) if m else 9999.0


def collect(work: str) -> list[dict]:
    paths = glob.glob(os.path.join(work, "ch*", "draft.md"))
    if not paths:
        paths = glob.glob(os.path.join(work, "*.md"))
    items = []
    for path in paths:
        meta, body = split_front_matter(read_text(path))
        title = meta.get("标题") or meta.get("title") or os.path.basename(os.path.dirname(path))
        items.append({"path": path, "meta": meta, "body": body.strip(),
                      "title": title, "key": chapter_key(meta, path)})
    items.sort(key=lambda x: x["key"])
    return items


def count_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def write_markdown(items: list[dict], out_dir: str, title: str) -> str:
    lines = [f"# {title}", "", "## 目录", ""]
    for item in items:
        num = item["meta"].get("话", item["key"])
        lines.append(f"- 第 {num} 话 · {item['title']}")
    lines += ["", ""]
    for item in items:
        # keep the chapter heading, demoted so the book has a single H1
        body = re.sub(r"^#\s+(.*)$", r"## \1", item["body"], count=1, flags=re.M)
        lines += [body.strip(), "", "---", ""]
    path = os.path.join(out_dir, "book.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def write_tables(items: list[dict], out_dir: str) -> None:
    with open(os.path.join(out_dir, "stats.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chapter", "title", "pages", "words", "scenes", "characters"])
        for it in items:
            meta = it["meta"]
            scenes = meta.get("场景") or []
            chars = meta.get("人物") or []
            w.writerow([meta.get("话", it["key"]), it["title"],
                        meta.get("页数", ""), meta.get("字数", count_chars(it["body"])) or count_chars(it["body"]),
                        len(scenes), len(chars)])
    with open(os.path.join(out_dir, "index.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chapter", "type", "value"])
        for it in items:
            meta = it["meta"]
            ch = meta.get("话", it["key"])
            for s in meta.get("场景") or []:
                w.writerow([ch, "scene", s])
            for c in meta.get("人物") or []:
                w.writerow([ch, "character", c])


def write_docx(items: list[dict], out_dir: str, title: str) -> str | None:
    try:
        import docx
        from docx.shared import Pt
    except ImportError:
        return None
    doc = docx.Document()
    doc.add_heading(title, level=0)
    doc.add_heading("目录", level=1)
    for it in items:
        doc.add_paragraph(f"第 {it['meta'].get('话', it['key'])} 话 · {it['title']}")
    for it in items:
        doc.add_page_break()
        doc.add_heading(it["title"], level=1)
        for para in re.split(r"\n\s*\n", it["body"]):
            para = para.strip()
            if not para or para.startswith("#"):
                continue
            if para.strip("◇ "):
                p = doc.add_paragraph(para.strip())
                p.paragraph_format.first_line_indent = Pt(24)
    path = os.path.join(out_dir, "book.docx")
    doc.save(path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble chapter drafts into a book.")
    ap.add_argument("--work", default=".", help="work folder containing ch*/draft.md")
    ap.add_argument("--out", default="book", help="output folder")
    ap.add_argument("--title", default="漫画小说化", help="book title")
    ap.add_argument("--no-docx", action="store_true", help="skip docx export")
    args = ap.parse_args()

    items = collect(args.work)
    if not items:
        print(json.dumps({"error": f"no draft.md found under {args.work}"}, ensure_ascii=False))
        return 1

    os.makedirs(args.out, exist_ok=True)
    md_path = write_markdown(items, args.out, args.title)
    write_tables(items, args.out)
    docx_path = None if args.no_docx else write_docx(items, args.out, args.title)

    print(json.dumps({
        "chapters": len(items),
        "words": sum(count_chars(it["body"]) for it in items),
        "book_md": md_path,
        "book_docx": docx_path or "skipped (pip install python-docx to enable)",
        "stats": os.path.join(args.out, "stats.csv"),
        "index": os.path.join(args.out, "index.csv"),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
