#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S0 - build a chapter manifest from a folder of comic PDFs.

Parses filenames such as
    002：第一回 皓光当空 上-日月同错.pdf
    150：第七十三点五回 咚咚之道-日月同错.pdf
    081：第三十九回 一季小结-日月同错.pdf

and emits a CSV describing every file: chapter number, part, kind
(story / extra / non-story), page count, pixel size, and which file of a
duplicated chapter is canonical.

Usage:
    python build_manifest.py --dir pdf --out manifest.csv
    python build_manifest.py --dir pdf --out manifest.csv --strip-suffix "-日月同错"
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

import pymupdf

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# Filename typos seen in the wild; extend as needed.
TYPO_FIX = {"思": "四"}

DEFAULT_NONSTORY = r"预告|公告|请假|通知|复刊|小结|获奖|目录|版权|后记"

COLUMNS = ["seq", "chapter", "half", "part", "subtitle", "kind", "pages", "mb",
           "px", "tall", "canonical", "dup_group", "dup_note", "file"]

PART_ORDER = {"": 0, "上": 1, "中": 2, "下": 3}


def cn2int(text: str) -> int | None:
    """Convert a Chinese numeral (up to thousands) to int."""
    total = section = num = 0
    for ch in text:
        ch = TYPO_FIX.get(ch, ch)
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch == "十":
            section += (num or 1) * 10
            num = 0
        elif ch == "百":
            section += (num or 1) * 100
            num = 0
        elif ch == "千":
            section += (num or 1) * 1000
            num = 0
        else:
            return None
    return total + section + num


def parse_name(stem: str, strip_suffix: str) -> dict:
    """Extract seq / chapter / part / subtitle from a filename stem."""
    if strip_suffix:
        # strip the series suffix only at the end, so a chapter that is *titled*
        # after the series keeps its title
        variants = {strip_suffix, strip_suffix.lstrip("-"), "-" + strip_suffix.lstrip("-")}
        for variant in sorted(variants, key=len, reverse=True):
            if stem.endswith(variant):
                stem = stem[:-len(variant)]
                break

    seq = None
    m = re.match(r"^(\d+)\s*[：:_\-.)、]\s*(.*)$", stem)
    if m:
        seq = int(m.group(1))
        stem = m.group(2)

    chapter = None
    half = False
    prefix = ""
    mm = re.search(r"第\s*([零〇一二两三四五六七八九十百千思]+)\s*(点五|半)?\s*[回话章集篇]", stem)
    if mm:
        chapter = cn2int(mm.group(1))
        half = mm.group(2) is not None
        prefix = stem[:mm.start()]
        rest = stem[mm.end():]
    else:
        rest = stem

    rest = rest.strip(" -—·_：:\t")
    part = ""
    pm = re.search(r"(上|中|下)\s*$", rest)
    if pm:
        part = pm.group(1)
        rest = rest[:pm.start()]

    subtitle = re.sub(r"[\s_]+", "", rest).strip(" -—·_：:")
    if not subtitle and prefix:
        # title written before 第X回, e.g. "<series>第一百六十五回：<series>"
        subtitle = re.sub(r"^\d+\s*[：:_\-.]\s*", "", prefix).strip(" -—·_：:")
    return {"seq": seq, "chapter": chapter, "half": half, "part": part,
            "subtitle": subtitle}


def page_info(path: str) -> tuple[int, str, float]:
    doc = pymupdf.open(path)
    try:
        n = doc.page_count
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        px = ""
        imgs = page.get_images(full=True)
        if imgs:
            info = doc.extract_image(imgs[0][0])
            px = f"{info['width']}x{info['height']}"
        return n, px, round(h / max(w, 1), 2)
    finally:
        doc.close()


def build(pdf_dir: str, strip_suffix: str, nonstory: re.Pattern) -> list[dict]:
    rows = []
    for name in sorted(os.listdir(pdf_dir)):
        if not name.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, name)
        stem = os.path.splitext(name)[0]
        meta = parse_name(stem, strip_suffix)
        pages, px, tall = page_info(path)

        if nonstory.search(stem):
            kind = "非正文"
        elif meta["half"]:
            kind = "番外"
        else:
            kind = "正篇"

        rows.append({**meta, "kind": kind, "pages": pages, "px": px, "tall": tall,
                     "mb": round(os.path.getsize(path) / 1048576, 1), "file": name})
    return rows


def mark_duplicates(rows: list[dict]) -> None:
    """Mark the canonical encoding for chapters that exist as several files.

    Some sets ship both a "whole chapter" file and a 上/中/下 split, and the
    "whole" file is sometimes only a fragment -- so prefer whichever encoding
    covers more pages.
    """
    groups: dict[int, list[dict]] = {}
    for r in rows:
        if r["kind"] == "正篇" and r["chapter"] is not None:
            groups.setdefault(r["chapter"], []).append(r)
        else:
            r["dup_group"] = ""
            r["dup_note"] = ""
            r["canonical"] = "Y" if r["kind"] == "番外" else ""

    for ch, group in groups.items():
        if len(group) == 1:
            group[0].update(dup_group="", dup_note="", canonical="Y")
            continue

        whole = [r for r in group if not r["part"]]
        splits = [r for r in group if r["part"]]
        whole_pages = whole[0]["pages"] if whole else 0
        split_pages = sum(r["pages"] for r in splits)
        use_splits = bool(splits) and split_pages >= whole_pages * 1.15
        note = (f"{len(group)} files: " +
                ", ".join(f"{r['part'] or 'whole'}{r['pages']}p"
                          for r in sorted(group, key=lambda x: PART_ORDER.get(x["part"], 9))))
        for r in group:
            keep = (r in splits) if use_splits else (bool(whole) and r is whole[0])
            r.update(dup_group=f"ch{ch:03d}", dup_note=note + (" [selected]" if keep else ""),
                     canonical="Y" if keep else "N")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a chapter manifest from comic PDFs.")
    ap.add_argument("--dir", required=True, help="folder containing the PDFs")
    ap.add_argument("--out", default="manifest.csv", help="output CSV path")
    ap.add_argument("--strip-suffix", default="", help='series suffix to strip, e.g. "日月同错" or "-日月同错"')
    ap.add_argument("--nonstory", default=DEFAULT_NONSTORY, help="regex of non-story filenames")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        ap.error(f"not a directory: {args.dir}")

    rows = build(args.dir, args.strip_suffix, re.compile(args.nonstory))
    mark_duplicates(rows)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in sorted(rows, key=lambda r: (r["chapter"] is None, r["chapter"] or 0,
                                            r["half"], PART_ORDER.get(r["part"], 9),
                                            r["seq"] or 0)):
            writer.writerow({k: r.get(k, "") for k in COLUMNS})

    story = [r for r in rows if r["kind"] == "正篇"]
    extra = [r for r in rows if r["kind"] == "番外"]
    non = [r for r in rows if r["kind"] == "非正文"]
    canonical = [r for r in rows if r["canonical"] == "Y"]
    chapters = sorted({r["chapter"] for r in story if r["chapter"] is not None})

    summary = {
        "files": len(rows),
        "story_files": len(story),
        "story_pages": sum(r["pages"] for r in story),
        "extra_files": len(extra),
        "extra_pages": sum(r["pages"] for r in extra),
        "nonstory_files": len(non),
        "canonical_files": len(canonical),
        "canonical_pages": sum(r["pages"] for r in canonical),
        "chapters": f"{min(chapters)}-{max(chapters)}" if chapters else "0",
        "chapter_count": len(chapters),
        "missing_chapters": [i for i in range(1, max(chapters) + 1) if i not in chapters] if chapters else [],
        "duplicate_groups": len({r["dup_group"] for r in rows if r["dup_group"]}),
        "low_res_files": sum(1 for r in rows if r["px"] and int(r["px"].split("x")[0]) < 1000),
        "tall_pages_files": sum(1 for r in rows if r["tall"] > 2.6),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"manifest -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
