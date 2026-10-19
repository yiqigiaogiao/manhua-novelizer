#!/usr/bin/env python3
"""兼容旧路径：等价于 `mnv build`。"""
import argparse
import json
import sys

from manhua_novelizer.build import run

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="汇编成书")
    ap.add_argument("--work", default=".")
    ap.add_argument("--out", default="build")
    ap.add_argument("--title", default="漫画小说化")
    ap.add_argument("--formats", nargs="*", default=["md", "docx", "epub", "mobi"])
    ap.add_argument("--no-cover", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(args.work, args.out, args.title, args.formats, not args.no_cover),
                     ensure_ascii=False, indent=1))
    sys.exit(0)
