# -*- coding: utf-8 -*-
"""S6.8 覆盖闸门：源里有几话，就必须有几话写完、几话出书。

为什么要有这个闸门
------------------
`check_ready.py` 只检查 **work 目录里已经存在** 的 ch*。
源里压根没建目录的话 → 没有 ch 目录 → 没有 problem → 闸门全绿 → 成书少十几话。
实测就是这么漏掉 18 话的：整本只写了 60/78，闸门一直报 ready。

本脚本以 **源清单**（`chapter-map.csv`）为准，去对账：
- 每话在 work 里有没有 draft.md
- 每话在已出书的书里有没有出现（用各卷 stats.csv 的 chapter 列）
- 有没有哪话被写了两遍（跨卷重复出书）

用法
----
    python scripts/check_coverage.py --map chapter-map.csv --work work
    python scripts/check_coverage.py --map chapter-map.csv --books 小说
    python scripts/check_coverage.py --map chapter-map.csv --work work --books 小说

退出码
------
    0  覆盖完整
    1  有缺失 / 有重复 / 有对不上的孤儿
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

# 确保同目录模块可被 import（被当模块 import 时脚本目录不会自动进 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import list_dirs  # noqa: E402


def load_map(path: str) -> tuple[dict[int, dict], list[dict]]:
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                r["chapter"] = int(r["chapter"])
            except (TypeError, ValueError):
                continue
            rows.append(r)
    expected = {r["chapter"]: r for r in rows if r.get("kind") == "chapter"}
    return expected, rows


def draft_chapter(folder: str) -> int | None:
    """从 draft.md 的 front matter 读话号（`话: 60`）；读不到就退回目录名 chNNN。"""
    draft = os.path.join(folder, "draft.md")
    if os.path.isfile(draft):
        try:
            with open(draft, encoding="utf-8-sig") as fh:
                head = fh.read(2048)
        except OSError:
            head = ""
        if head.startswith("---"):
            parts = head.split("---", 2)
            block = parts[1] if len(parts) >= 3 else head
            for line in block.splitlines():
                if line.strip().startswith("话"):
                    k, _, v = line.partition(":")
                    if k.strip() in ("话", "話", "chapter"):
                        try:
                            return int(float(v.strip()))
                        except ValueError:
                            pass
    m = re.search(r"ch(\d+)", os.path.basename(folder))
    return int(m.group(1)) if m else None


def work_chapters(work: str) -> dict[int, bool]:
    """话号 -> 是否有 draft.md（话号取自 front matter，其次目录名）"""
    out: dict[int, bool] = {}
    for folder in list_dirs(work, prefix="ch"):
        ch = draft_chapter(folder)
        if ch is None:
            continue
        out[ch] = os.path.isfile(os.path.join(folder, "draft.md"))
    return out


def book_chapters(books_dirs: list[str]) -> tuple[dict[int, list[str]], list[str]]:
    """已出书各卷 -> {chapter: [卷名]}"""
    index: dict[int, list[str]] = {}
    problems: list[str] = []
    for books_dir in books_dirs:
        for book in list_dirs(books_dir, suffix="卷"):
            csv_path = os.path.join(book, "stats.csv")
            if not os.path.isfile(csv_path):
                continue
            with open(csv_path, encoding="utf-8-sig") as fh:
                for row in csv.reader(fh):
                    if not row or not row[0].strip().isdigit():
                        continue
                    index.setdefault(int(row[0].strip()), []).append(os.path.basename(book))
    return index, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="覆盖闸门：源里几话就得有几话")
    ap.add_argument("--map", required=True, help="chapter-map.csv")
    ap.add_argument("--work", help="work 目录（检查 chNNN/draft.md）")
    ap.add_argument("--books", nargs="*", default=None,
                    help="已出书目录（可给多个），检查各卷 stats.csv")
    ap.add_argument("--require-books", action="store_true",
                    help="要求每一话都已经在书里出过分")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.map):
        print(json.dumps({"ok": False, "error": f"找不到清单 {args.map}"}, ensure_ascii=False))
        return 1

    expected, all_rows = load_map(args.map)
    problems: list[str] = []

    if not expected:
        print(json.dumps({"ok": False, "error": "清单里没有 kind=chapter 的行"},
                         ensure_ascii=False))
        return 1

    work_map = work_chapters(args.work) if args.work else {}
    book_index, _ = book_chapters(args.books) if args.books else ({}, [])

    missing_work = sorted(ch for ch in expected if args.work and ch not in work_map)
    no_draft = sorted(ch for ch, ok in work_map.items() if not ok)
    missing_book = sorted(ch for ch in expected if args.books and ch not in book_index)
    orphans = sorted(ch for ch in work_map if ch not in expected)

    dupes = {ch: vols for ch, vols in book_index.items() if len(vols) > 1}

    for ch in missing_work:
        problems.append(f"第{ch}话: work 里没有 ch{ch:03d} 目录（源里有，这一话还没开工）")
    for ch in no_draft:
        problems.append(f"第{ch}话: ch{ch:03d} 没有 draft.md")
    for ch in missing_book:
        problems.append(f"第{ch}话: 还没出书")
    for ch in orphans:
        problems.append(f"第{ch}话: work 里有但源清单里没有（多写的，或清单没登记）")
    for ch, vols in sorted(dupes.items()):
        problems.append(f"第{ch}话: 重复出书于 {'、'.join(vols)}")

    if args.require_books and missing_book:
        pass  # 已在 problems 里

    nums = sorted(expected)
    report = {
        "ok": not problems,
        "expected_chapters": len(expected),
        "chapter_range": f"{nums[0]}-{nums[-1]}",
        "work_drafts": sum(1 for v in work_map.values() if v),
        "published": len(book_index),
        "missing_work": missing_work,
        "missing_draft": no_draft,
        "missing_books": missing_book,
        "orphans": orphans,
        "duplicates": {str(k): v for k, v in sorted(dupes.items())},
        "extras": sorted(r["chapter"] for r in all_rows if r.get("kind") == "extra"),
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
