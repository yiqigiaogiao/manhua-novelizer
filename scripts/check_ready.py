# -*- coding: utf-8 -*-
"""成书前闸门：确认所有话都写完了，且最近一段时间没有改动。

用法：
    python scripts/check_ready.py --work work
    python scripts/check_ready.py --work work --quiet-minutes 10 --require outline.json

退出码：
    0  可以成书
    1  还不能（缺文件 / 还在改 / 质检过期）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import list_dirs  # noqa: E402


def collect_chapters(work: str) -> list[str]:
    return list_dirs(work, prefix="ch")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="成书前闸门：草稿齐了且不再变动")
    ap.add_argument("--work", required=True)
    ap.add_argument("--quiet-minutes", type=float, default=10.0,
                    help="草稿最后修改距今至少多少分钟（默认 10）")
    ap.add_argument("--require", nargs="*", default=["draft.md"],
                    help="每话必须具备的文件（默认 draft.md）")
    ap.add_argument("--check-qa", action="store_true",
                    help="要求 qa.json 存在且不早于 draft.md")
    ap.add_argument("--chapter-map", default=None,
                    help="话级覆盖清单 chapter-map.csv；给了就核对「源里几话都写了吗」")
    args = ap.parse_args(argv)

    chapters = collect_chapters(args.work)
    if not chapters:
        print(json.dumps({"ready": False, "reason": f"{args.work} 下没有 ch* 目录"},
                         ensure_ascii=False))
        return 1

    now = time.time()
    quiet_limit = args.quiet_minutes * 60
    problems, newest = [], 0.0

    for folder in chapters:
        name = os.path.basename(folder)
        for required in args.require:
            path = os.path.join(folder, required)
            if not os.path.isfile(path):
                problems.append(f"{name}: 缺 {required}")
                continue
            mtime = os.path.getmtime(path)
            newest = max(newest, mtime)
            age = now - mtime
            if age < quiet_limit:
                problems.append(
                    f"{name}: {required} {int(age // 60)} 分钟前才改过"
                    f"（要求静置 {args.quiet_minutes:g} 分钟）")
        if args.check_qa:
            draft = os.path.join(folder, "draft.md")
            qa = os.path.join(folder, "qa.json")
            if os.path.isfile(draft):
                if not os.path.isfile(qa):
                    problems.append(f"{name}: 缺 qa.json")
                elif os.path.getmtime(qa) < os.path.getmtime(draft):
                    problems.append(f"{name}: qa.json 早于 draft.md，质检过期")

    coverage = None
    if args.chapter_map:
        import check_coverage
        expected, _ = check_coverage.load_map(args.chapter_map)
        work_map = check_coverage.work_chapters(args.work)
        missing = sorted(ch for ch in expected if ch not in work_map)
        no_draft = sorted(ch for ch, ok in work_map.items() if not ok and ch in expected)
        for ch in missing:
            problems.append(f"第{ch}话: 源清单里有，work 里却没有 ch{ch:03d}（整本会少这一话）")
        for ch in no_draft:
            problems.append(f"第{ch}话: ch{ch:03d} 没有 draft.md")
        coverage = {
            "expected": len(expected),
            "have_draft": len(expected) - len(missing) - len(no_draft),
            "missing": missing,
        }

    ready = not problems
    report = {
        "ready": ready,
        "chapters": len(chapters),
        "quiet_minutes_required": args.quiet_minutes,
        "newest_draft_age_min": round((now - newest) / 60, 1) if newest else None,
        "coverage": coverage,
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
