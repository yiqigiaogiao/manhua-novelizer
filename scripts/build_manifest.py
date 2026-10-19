# -*- coding: utf-8 -*-
"""S0 建清单：解析漫画 PDF 文件名，去重、剔非正文。"""
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
TYPO_FIX = {"思": "四"}
DEFAULT_NONSTORY = "预告|公告|请假|通知|复刊|小结|获奖|目录|版权|后记"

COLUMNS = ["seq", "chapter", "half", "part", "subtitle", "kind", "pages", "mb",
           "px", "tall", "canonical", "dup_group", "dup_note", "file"]
PART_ORDER = {"": 0, "上": 1, "中": 2, "下": 3}


def cn2int(text: str) -> int | None:
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
    if strip_suffix:
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
        cm = re.match(r"^ch(\d+)(_5)?[_\-\s]*(.*)$", stem, re.I)
        if cm:
            chapter = int(cm.group(1))
            half = bool(cm.group(2))
            rest = cm.group(3)
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


def build_rows(pdf_dir: str, strip_suffix: str, nonstory: str) -> list[dict]:
    pattern = re.compile(nonstory)
    rows = []
    for name in sorted(os.listdir(pdf_dir)):
        if not name.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, name)
        stem = os.path.splitext(name)[0]
        meta = parse_name(stem, strip_suffix)
        pages, px, tall = page_info(path)
        if pattern.search(stem):
            kind = "非正文"
        elif meta["half"]:
            kind = "番外"
        else:
            kind = "正篇"
        rows.append({**meta, "kind": kind, "pages": pages, "px": px, "tall": tall,
                     "mb": round(os.path.getsize(path) / 1048576, 1), "file": name})
    return rows


def mark_duplicates(rows: list[dict]) -> None:
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


def write_manifest(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in sorted(rows, key=lambda r: (r["chapter"] is None, r["chapter"] or 0,
                                            r["half"], PART_ORDER.get(r["part"], 9),
                                            r["seq"] or 0)):
            writer.writerow({k: r.get(k, "") for k in COLUMNS})


def summarize(rows: list[dict]) -> dict:
    story = [r for r in rows if r["kind"] == "正篇"]
    extra = [r for r in rows if r["kind"] == "番外"]
    non = [r for r in rows if r["kind"] == "非正文"]
    canonical = [r for r in rows if r["canonical"] == "Y"]
    chapters = sorted({r["chapter"] for r in story if r["chapter"] is not None})
    return {
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
    }


def run(pdf_dir: str, out: str, strip_suffix: str = "", nonstory: str = DEFAULT_NONSTORY) -> dict:
    rows = build_rows(pdf_dir, strip_suffix, nonstory)
    mark_duplicates(rows)
    write_manifest(rows, out)
    return summarize(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="建章节清单 manifest.csv")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="manifest.csv")
    ap.add_argument("--strip-suffix", default="")
    ap.add_argument("--nonstory", default=DEFAULT_NONSTORY)
    args = ap.parse_args(argv)
    if not os.path.isdir(args.dir):
        ap.error(f"not a directory: {args.dir}")
    summary = run(args.dir, args.out, args.strip_suffix, args.nonstory)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
