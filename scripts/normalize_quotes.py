# -*- coding: utf-8 -*-
"""把日式/台版引号统一成中文全角引号。

    「」 → “”
    『』 → ‘’
    ﹁﹂ ﹃﹄ → “” ‘’

用法：
    python normalize_quotes.py --work work          # 处理 work/ch*/draft.md
    python normalize_quotes.py --paths a.md b.md
    python normalize_quotes.py --work work --check  # 只报告，不改
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

PAIRS = [
    ("「", "“"), ("」", "”"),
    ("『", "‘"), ("』", "’"),
    ("﹁", "“"), ("﹂", "”"),
    ("﹃", "‘"), ("﹄", "’"),
]
PATTERN = re.compile("|".join(re.escape(src) for src, _ in PAIRS))


def convert(text: str) -> str:
    table = dict(PAIRS)
    return PATTERN.sub(lambda m: table[m.group(0)], text)


def process(path: str, check: bool = False) -> dict:
    text = open(path, encoding="utf-8").read()
    new = convert(text)
    hits = len(PATTERN.findall(text))
    if hits and not check:
        open(path, "w", encoding="utf-8").write(new)
    return {"file": path, "replaced": hits, "changed": text != new}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="统一引号为中文全角")
    ap.add_argument("--work", default=None, help="工作目录，处理其下 ch*/draft.md")
    ap.add_argument("--paths", nargs="*", default=None, help="显式文件列表")
    ap.add_argument("--check", action="store_true", help="只报告，不修改")
    args = ap.parse_args(argv)

    paths = list(args.paths or [])
    if args.work:
        paths += sorted(glob.glob(os.path.join(args.work, "ch*", "draft.md")))
        paths += sorted(glob.glob(os.path.join(args.work, "*.md")))
    paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p)]
    if not paths:
        ap.error("没有找到文件：请给 --work 或 --paths")

    results = [process(p, args.check) for p in paths]
    print(json.dumps({"files": len(results),
                      "replaced": sum(r["replaced"] for r in results),
                      "detail": results}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
