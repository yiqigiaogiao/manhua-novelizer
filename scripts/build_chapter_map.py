# -*- coding: utf-8 -*-
"""S0c 建「话级」覆盖清单：把源目录里每一话（以及每一卷）登记成可核对的表。

背景
----
`build_manifest.py` 只登记 PDF 文件，`check_ready.py` 只检查 **work 目录里已经存在**
的 ch* 是否写完。于是"源里根本没建目录的话"永远不会变成一条 problem——
整本少掉十几话，成书闸门依然全绿。

本脚本补上这一层：以 **源目录** 为准，产出 `chapter-map.csv`，
每行一话，写明它来自哪个源目录、有多少页；再由 `check_coverage.py` 拿它去对账。

用法
----
    # 1. 只有单话目录时，章号是现成的
    python scripts/build_chapter_map.py --src 源目录 --out chapter-map.csv

    # 2. 源里是整卷（卷里含多话）时，声明每卷覆盖哪些话
    python scripts/build_chapter_map.py --src 源目录 --out chapter-map.csv \
        --volumes "1:1-5,2:6-10,3:11-15"

    # 3. 声明放在源目录的 volume-map.csv 里也可以，格式同上

输出列
------
    chapter, title, kind, source, pages, notes

    kind: chapter（正篇话） / extra（番外、前日谭、月刊等） / volume（整卷，未展开）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

# 番外 / 非正篇的识别
EXTRA_PAT = re.compile(r"外传|前日谭|前曰谭|番外|短篇|月刊|別篇|别篇|特別篇|特别篇|序章|后日谈")
CHAPTER_PAT = re.compile(r"第\s*([0-9]+|[零〇一二两三四五六七八九十百千]+)\s*[話话回回章話]")
VOLUME_PAT = re.compile(r"第\s*([0-9]+|[零〇一二两三四五六七八九十百千]+)\s*卷")

COLUMNS = ["chapter", "title", "kind", "source", "pages", "notes"]


def cn2int(text: str) -> int | None:
    total = section = num = 0
    for ch in text:
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


def to_int(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return cn2int(token)


def count_pages(folder: str) -> int:
    n = 0
    try:
        for name in os.listdir(folder):
            if os.path.splitext(name)[1].lower() in IMG_EXT:
                n += 1
    except OSError:
        pass
    return n


def parse_volume_spec(spec: str) -> dict[int, list[int]]:
    """'1:1-5,2:6-10' -> {1: [1,2,3,4,5], 2: [6,...,10]}"""
    out: dict[int, list[int]] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"卷映射格式错：{item!r}（应为 '卷号:起-止'）")
        vol_s, rng = item.split(":", 1)
        vol = to_int(vol_s)
        if vol is None:
            raise ValueError(f"卷号读不出来：{vol_s!r}")
        nums: list[int] = []
        for piece in rng.split("+"):
            piece = piece.strip()
            if not piece:
                continue
            if "-" in piece:
                a, b = piece.split("-", 1)
                lo, hi = to_int(a), to_int(b)
                if lo is None or hi is None:
                    raise ValueError(f"话号读不出来：{piece!r}")
                nums.extend(range(lo, hi + 1))
            else:
                v = to_int(piece)
                if v is None:
                    raise ValueError(f"话号读不出来：{piece!r}")
                nums.append(v)
        out.setdefault(vol, []).extend(nums)
    return out


def read_volume_map(src: str) -> dict[int, list[int]]:
    path = os.path.join(src, "volume-map.csv")
    if not os.path.isfile(path):
        return {}
    spec = []
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            spec.append(f"{row[0].strip()}:{row[1].strip()}")
    return parse_volume_spec(",".join(spec))


def scan_source(src: str) -> tuple[list[dict], list[dict]]:
    """返回 (chapter_rows, volume_rows)"""
    chapter_rows: list[dict] = []
    volume_rows: list[dict] = []
    for name in sorted(os.listdir(src)):
        path = os.path.join(src, name)
        if not os.path.isdir(path):
            continue
        pages = count_pages(path)
        if pages == 0:
            continue
        stem = name
        vm = VOLUME_PAT.search(stem)
        cm = CHAPTER_PAT.search(stem)
        if cm and (not vm or cm.start() < vm.start()):
            num = to_int(cm.group(1))
            if num is None:
                continue
            title = stem[cm.end():].strip(" -_—·・：:（）()") or ""
            kind = "extra" if EXTRA_PAT.search(stem) else "chapter"
            chapter_rows.append({
                "chapter": num, "title": title, "kind": kind,
                "source": name, "pages": pages, "notes": "",
                "source_kind": "chapter",
            })
        elif vm:
            num = to_int(vm.group(1))
            if num is None:
                continue
            title = stem[vm.end():].strip(" -_—·・：:（）()") or ""
            volume_rows.append({
                "chapter": num, "title": title, "kind": "volume",
                "source": name, "pages": pages, "notes": "",
                "source_kind": "volume",
            })
        else:
            # 前日谭 / 外传 / 月刊少年…：有图但没有话号，算 extra
            title = stem.strip(" -_—·・：:（）()")
            chapter_rows.append({
                "chapter": 0, "title": title, "kind": "extra",
                "source": name, "pages": pages, "notes": "无话号，按番外处理",
                "source_kind": "chapter",
            })
    return chapter_rows, volume_rows


def expand_volumes(volume_rows: list[dict], mapping: dict[int, list[int]]) -> list[dict]:
    """把整卷按声明展开成一话一行的 chapter 行。"""
    out = []
    for v in volume_rows:
        chapters = mapping.get(v["chapter"])
        if not chapters:
            continue
        for ch in chapters:
            out.append({
                "chapter": ch, "title": "", "kind": "chapter",
                "source": v["source"], "pages": "",
                "notes": f"来自第{v['chapter']:02d}卷",
                "source_kind": "volume",
            })
    return out


def merge_rows(*groups: list[dict]) -> list[dict]:
    """同一话号可能有多个来源（整卷 + 单话）。单话优先；都要记下来。

    extra（无话号的番外）按 source 独立成行，不按话号合并。
    """
    by_ch: dict[int, list[dict]] = {}
    extras: list[dict] = []
    for g in groups:
        for r in g:
            if r.get("kind") == "extra":
                extras.append(r)
            else:
                by_ch.setdefault(r["chapter"], []).append(r)
    out = []
    for ch in sorted(by_ch):
        rows = by_ch[ch]
        # 单话目录优先于整卷
        rows.sort(key=lambda r: (r.get("source_kind") == "volume", r["source"]))
        primary = rows[0]
        note = primary.get("notes", "")
        if len(rows) > 1:
            extra = ", ".join(r["source"] for r in rows[1:])
            note = (note + "; " if note else "") + f"另有来源: {extra}"
        out.append({**primary, "notes": note})
    out.extend(extras)
    return out


def write_map(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in COLUMNS})


def summarize(rows: list[dict]) -> dict:
    chapters = [r for r in rows if r["kind"] == "chapter"]
    extras = [r for r in rows if r["kind"] == "extra"]
    volumes = [r for r in rows if r["kind"] == "volume"]
    nums = sorted(r["chapter"] for r in chapters)
    gaps = []
    if nums:
        for i in range(min(nums), max(nums) + 1):
            if i not in nums:
                gaps.append(i)
    return {
        "chapters": len(chapters),
        "chapter_range": f"{min(nums)}-{max(nums)}" if nums else "0",
        "gaps_in_range": gaps,
        "extras": len(extras),
        "volumes_unexpanded": len(volumes),
        "total_pages": sum(r["pages"] for r in rows if isinstance(r["pages"], int)),
    }


def run(src: str, out: str, volumes_spec: str) -> dict:
    chapter_rows, volume_rows = scan_source(src)
    mapping = read_volume_map(src)
    if volumes_spec:
        mapping.update(parse_volume_spec(volumes_spec))
    expanded = expand_volumes(volume_rows, mapping)

    # 合并：单话目录优先；未被声明的整卷保留为 volume 行
    merged = merge_rows(chapter_rows, expanded)
    covered = {r["chapter"] for r in merged}
    leftover_volumes = [v for v in volume_rows
                        if v["chapter"] not in covered or not mapping.get(v["chapter"])]
    for v in leftover_volumes:
        v = dict(v)
        v["notes"] = "未展开为话（用 --volumes 声明覆盖范围）"
        merged.append(v)

    merged.sort(key=lambda r: (r["kind"] == "volume", r["kind"] == "extra", r["chapter"]))
    write_map(merged, out)
    return summarize(merged)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="建话级覆盖清单 chapter-map.csv")
    ap.add_argument("--src", required=True, help="源目录（里面是 各话/各卷 的图片子目录）")
    ap.add_argument("--out", default="chapter-map.csv")
    ap.add_argument("--volumes", default="",
                    help="整卷覆盖的话号，如 '1:1-5,2:6-10'")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.src):
        ap.error(f"not a directory: {args.src}")
    try:
        summary = run(args.src, args.out, args.volumes)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
