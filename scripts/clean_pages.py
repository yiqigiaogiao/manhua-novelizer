# -*- coding: utf-8 -*-
"""清理中间页图（jpg/png），保留正文与 JSON。

**默认不再自动删。** 页图是 S6.7 原图复检的事实源——一旦删掉，
"描述与画面不一致"就永远没机会核对，只能靠记忆赌。
所以删图必须是**明确的最后动作**，由人下指令。

用法：
    python clean_pages.py --work work --dry-run          # 先看会删什么、占多少
    python clean_pages.py --work work --confirm          # 真的要删
    python clean_pages.py --work work --keep work/ch001/pages   # 保留某一话
    python clean_pages.py --work work --confirm --after-verify   # 只删"已过复检"的话

安全约束：
- 没有 --confirm 一律只报不删（dry-run 与不带 confirm 的调用等价）。
- --after-verify 会读每话 verify.json：没过的章不删（还能补核）。
"""
from __future__ import annotations

import argparse
import json
import os

IMAGE_EXT = (".jpg", ".jpeg", ".png")


def verify_passed(folder: str) -> bool:
    """这一话是否过了原图复检。没 verify.json 或 pages_checked 为空 → 没过。"""
    vpath = os.path.join(folder, "verify.json")
    if not os.path.isfile(vpath):
        return False
    try:
        with open(vpath, encoding="utf-8-sig") as fh:
            verify = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    return bool(verify.get("pages_checked"))


def cleanup(work_dir: str, confirm: bool = False, keep: str | None = None,
            after_verify: bool = False) -> dict:
    removed, freed, kept, skipped = 0, 0, 0, 0
    skipped_list: list[str] = []
    for root, dirs, files in os.walk(work_dir):
        if keep and os.path.abspath(root).startswith(os.path.abspath(keep)):
            kept += sum(1 for f in files if f.lower().endswith(IMAGE_EXT))
            continue
        if after_verify and os.path.basename(root) == "pages":
            chapter_dir = os.path.dirname(root)
            if not verify_passed(chapter_dir):
                # 删掉整个 pages 目录下未过复检的图是不可逆的，跳过整章
                n = sum(1 for f in files if f.lower().endswith(IMAGE_EXT))
                if n:
                    skipped += n
                    skipped_list.append(os.path.relpath(chapter_dir, work_dir))
                dirs[:] = []
                continue
        for name in files:
            if not name.lower().endswith(IMAGE_EXT):
                continue
            path = os.path.join(root, name)
            size = os.path.getsize(path)
            if confirm:
                os.remove(path)
            removed += 1
            freed += size

    if confirm:
        for root, dirs, files in os.walk(work_dir, topdown=False):
            if os.path.basename(root) == "pages" and not os.listdir(root):
                os.rmdir(root)

    return {
        "removed": removed,
        "freed_mb": round(freed / 1048576, 1),
        "kept": kept,
        "skipped_unverified": skipped,
        "skipped_chapters": sorted(set(skipped_list)),
        "confirmed": confirm,
        "dry_run": not confirm,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="清理中间页图（默认只报不删）")
    ap.add_argument("--work", default="work")
    ap.add_argument("--keep", default=None)
    ap.add_argument("--confirm", action="store_true",
                    help="真的删除。没加这个参数时只报告不动文件。")
    ap.add_argument("--after-verify", action="store_true",
                    help="只删已过 S6.7 原图复检的话；没过复检的章保留")
    args = ap.parse_args(argv)
    if not args.confirm:
        args.confirm = False
    print(json.dumps(cleanup(args.work, args.confirm, args.keep,
                             args.after_verify),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
