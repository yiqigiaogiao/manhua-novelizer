# -*- coding: utf-8 -*-
"""清理中间页图（jpg/png），保留正文与 JSON。

用法：
    python clean_pages.py --work work --dry-run
    python clean_pages.py --work work --keep work/ch001/pages
"""
from __future__ import annotations

import argparse
import json
import os

IMAGE_EXT = (".jpg", ".jpeg", ".png")


def cleanup(work_dir: str, dry_run: bool = False, keep: str | None = None) -> dict:
    removed, freed, kept = 0, 0, 0
    for root, dirs, files in os.walk(work_dir):
        if keep and os.path.abspath(root).startswith(os.path.abspath(keep)):
            kept += sum(1 for f in files if f.lower().endswith(IMAGE_EXT))
            continue
        for name in files:
            if not name.lower().endswith(IMAGE_EXT):
                continue
            path = os.path.join(root, name)
            size = os.path.getsize(path)
            if not dry_run:
                os.remove(path)
            removed += 1
            freed += size
    for root, dirs, files in os.walk(work_dir, topdown=False):
        if os.path.basename(root) == "pages" and not os.listdir(root) and not dry_run:
            os.rmdir(root)
    return {"removed": removed, "freed_mb": round(freed / 1048576, 1),
            "kept": kept, "dry_run": dry_run}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="清理中间页图")
    ap.add_argument("--work", default="work")
    ap.add_argument("--keep", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    print(json.dumps(cleanup(args.work, args.dry_run, args.keep), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
