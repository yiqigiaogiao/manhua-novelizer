# -*- coding: utf-8 -*-
"""转录编排运行器（S3 批量 + 自愈补位）。

设计目标（对应用户反馈："一个子 agent 挂掉，后续应该自动补上"）：
1. 每 3 页一段小任务 —— 粒度小到 agent 在上下文耗尽前就能落盘。
2. **单页独立文件** `ps_pNNNN.json` —— agent 每读一页立刻写一页，
   即使中途挂掉，已读的页全部保留（这是自愈的前提）。
3. **以文件为验收**：重跑自动跳过已存在的页，只补缺失的。
4. 批内并发、批间串行 —— 控制并发度，避免像全并发那样拖垮 agent。

用法：
    python run_transcribe.py --work 极度恐慌_work --ch ch001
    python run_transcribe.py --work 极度恐慌_work --ch ch001 --dry-run
    python run_transcribe.py --work 极度恐慌_work --resume

依赖：`workflow` 工具进行 agent 编排。本脚本只负责：
  - 扫描已存在的页，算出缺失页
  - 生成可直接喂给 workflow 的编排脚本
流程分两步：先用本脚本生成 missing 列表，再用 workflow 跑。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

SEG_SIZE = 3          # 每段页数：3 页一段，兼顾吞吐与落盘可靠性
BATCH = 4             # 批内并发数


def pages_dir_status(folder: pathlib.Path) -> tuple[int, list[int], list[int]]:
    """返回 (页图总数, 已转录页, 缺失页)。"""
    pages = folder / "pages"
    imgs = sorted(p for p in pages.iterdir()
                  if p.suffix.lower() in (".jpg", ".png")) if pages.exists() else []
    total = len(imgs)
    have = set()
    for f in folder.glob("ps_p*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
            have.add(int(d["page"]))
        except Exception:
            pass
    # 兼容旧的整段文件
    for f in folder.glob("page_script*.json"):
        if ".bak" in f.name or "backup" in f.name:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for p in d.get("pages", []):
            if "page" in p:
                have.add(int(p["page"]))
    missing = [p for p in range(1, total + 1) if p not in have]
    return total, sorted(have), missing


def scan(work: pathlib.Path, only: str | None = None) -> dict:
    report = {}
    for c in sorted(work.glob("ch[0-9][0-9][0-9]")):
        total, have, missing = pages_dir_status(c)
        if only and c.name != only:
            continue
        if total == 0:
            continue
        report[c.name] = {"total": total, "done": len(have), "missing": missing}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="转录编排：算缺失页（给 workflow 用）")
    ap.add_argument("--work", required=True)
    ap.add_argument("--ch", help="只算某一话，如 ch001")
    args = ap.parse_args()
    work = pathlib.Path(args.work)
    rep = scan(work, args.ch)
    done = sum(v["done"] for v in rep.values())
    total = sum(v["total"] for v in rep.values())
    print(json.dumps({
        "chapters": len(rep),
        "pages_done": done,
        "pages_total": total,
        "pct": round(100 * done / total, 1) if total else 0,
        "chapters_incomplete": {k: v["missing"] for k, v in rep.items() if v["missing"]},
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
