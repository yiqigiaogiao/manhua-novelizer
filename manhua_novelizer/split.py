# -*- coding: utf-8 -*-
"""S0b 合本拆章：按 PDF 书签或手写页表，把一个多话合本切成单话 PDF。"""
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


def safe_name(text: str, limit: int = 40) -> str:
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    return re.sub(r"\s+", "", text)[:limit]


def chapters_from_toc(doc: pymupdf.Document, pattern: re.Pattern) -> list[dict]:
    toc = doc.get_toc(simple=True)
    hits = [item for item in toc if pattern.search(item[1])]
    if not hits:
        return []
    level = min(item[0] for item in hits)
    hits = [item for item in hits if item[0] == level]
    hits.sort(key=lambda item: item[2])
    chapters = []
    for i, (_, title, page) in enumerate(hits):
        start = page
        end = hits[i + 1][2] - 1 if i + 1 < len(hits) else doc.page_count
        if end < start:
            continue
        m = re.search(r"第\s*([零〇一二两三四五六七八九十百千思]+)\s*(点五|半)?\s*[回话章]", title)
        number = cn2int(m.group(1)) + (0.5 if m and m.group(2) else 0) if m else None
        chapters.append({"chapter": number, "title": title.strip(),
                         "start": start, "end": end, "source": "toc"})
    return chapters


def chapters_from_map(path: str) -> list[dict]:
    chapters = []
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            chapters.append({
                "chapter": float(row["chapter"]) if row.get("chapter") else None,
                "title": (row.get("title") or f"ch{row['chapter']}").strip(),
                "start": int(row["start"]), "end": int(row["end"]), "source": "map",
            })
    return chapters


def validate(chapters: list[dict], total: int) -> tuple[list[dict], list[str]]:
    problems = []
    chapters = [c for c in chapters if 1 <= c["start"] <= total]
    chapters.sort(key=lambda c: c["start"])
    for i, c in enumerate(chapters):
        if c["end"] > total:
            problems.append(f"{c['title']}: end {c['end']} > page count {total}")
            c["end"] = total
        if c["end"] < c["start"]:
            problems.append(f"{c['title']}: end < start")
        if i and c["start"] <= chapters[i - 1]["end"]:
            problems.append(f"{c['title']}: overlaps previous chapter")
    return chapters, problems


def coverage(chapters: list[dict], total: int) -> list[str]:
    covered = set()
    for c in chapters:
        covered.update(range(c["start"], c["end"] + 1))
    gaps = [p for p in range(1, total + 1) if p not in covered]
    ranges, start = [], None
    for i, p in enumerate(gaps):
        if start is None:
            start = p
        if i + 1 == len(gaps) or gaps[i + 1] != p + 1:
            ranges.append(f"{start}-{p}" if p > start else str(start))
            start = None
    return ranges


def run(pdf: str, out: str, map_csv: str | None = None, dry_run: bool = False,
        toc_regex: str = r"第\s*[零〇一二两三四五六七八九十百千]+\s*(点五|半)?\s*[回话章]|番外|序章|终章") -> dict:
    doc = pymupdf.open(pdf)
    total = doc.page_count
    try:
        chapters = chapters_from_map(map_csv) if map_csv else chapters_from_toc(doc, re.compile(toc_regex))
        if not chapters:
            return {"error": "no chapter boundaries found", "pages": total,
                    "hint": "无书签时请提供 --map chapter-map.csv（chapter,title,start,end）"}
        chapters, problems = validate(chapters, total)
        previous = 0
        for c in chapters:
            if c["chapter"] is None:
                if "番外" in c["title"]:
                    c["chapter"] = previous + 0.5
            else:
                previous = int(c["chapter"])
        gaps = coverage(chapters, total)
        if not dry_run:
            os.makedirs(out, exist_ok=True)
        report = []
        for i, c in enumerate(chapters, start=1):
            number = c["chapter"]
            if number is not None:
                name = f"ch{int(number):03d}" + ("_5" if abs(number % 1) > 0 else "")
            else:
                name = f"ch{i:03d}"
            filename = f"{name}_{safe_name(c['title'])}.pdf"
            c["file"] = filename
            c["pages"] = c["end"] - c["start"] + 1
            report.append({"chapter": number, "title": c["title"], "start": c["start"],
                           "end": c["end"], "pages": c["pages"], "file": filename})
            if not dry_run:
                part = pymupdf.open()
                part.insert_pdf(doc, from_page=c["start"] - 1, to_page=c["end"] - 1)
                part.save(os.path.join(out, filename))
                part.close()
    finally:
        doc.close()

    if not dry_run:
        with open(os.path.join(out, "chapter-index.csv"), "w",
                  encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["chapter", "title", "start", "end",
                                                   "pages", "file"])
            writer.writeheader()
            writer.writerows(report)

    return {"chapters": len(report), "pages": total, "uncovered_ranges": gaps,
            "problems": problems, "dry_run": dry_run, "out": out,
            "first": report[0] if report else None,
            "last": report[-1] if report else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="合本 PDF 拆章")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--map", dest="map_csv", default=None)
    ap.add_argument("--toc-regex", default=r"第\s*[零〇一二两三四五六七八九十百千]+\s*(点五|半)?\s*[回话章]|番外|序章|终章")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pdf):
        ap.error(f"no such file: {args.pdf}")
    result = run(args.pdf, args.out, args.map_csv, args.dry_run, args.toc_regex)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 2 if result.get("error") else (1 if result.get("problems") else 0)


if __name__ == "__main__":
    sys.exit(main())
