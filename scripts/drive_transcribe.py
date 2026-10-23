# -*- coding: utf-8 -*-
"""卡住接管驱动器：算缺口 -> 生成 workflow args -> 反复调用直到零缺口。

设计（对应「子 agent 无响应一段时间后启动新 agent 接管」的要求）：
1. 每轮只发 N 个小任务（默认 24 段 × 4 页 = 96 页），2-3 分钟内必回。
2. 回来后**扫磁盘**（不信 agent 汇报），算出仍缺的页。
3. 缺页重新切段，下一轮再发。任何一段超时/丢失，下一轮自动被新 agent 接管。
4. 直到缺口为 0，或达到最大轮数。

用法：
    python drive_transcribe.py --work 大剑_work --rounds 60 --pages-per-task 4 --parallel 24
输出：
    每轮打印 gap JSON（供 workflow 的 args.gap 使用）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def scan_gap(work: pathlib.Path, only: list[str] | None = None) -> dict:
    gap = {}
    for ch in sorted(work.glob('ch[0-9][0-9][0-9]')):
        if only and ch.name not in only:
            continue
        pj = ch / 'pages' / 'pages.json'
        if not pj.is_file():
            continue
        total = len(json.loads(pj.read_text(encoding='utf-8-sig')).get('pages', []))
        if total == 0:
            continue
        have = set()
        for f in ch.glob('ps_p*.json'):
            try:
                have.add(int(json.loads(f.read_text(encoding='utf-8-sig'))['page']))
            except Exception:
                pass
        miss = [p for p in range(1, total + 1) if p not in have]
        if miss:
            # chNNN -> episode：大剑 ch001 = 第1卷
            ep = int(ch.name[2:])
            gap[ch.name] = {'ep': ep, 'total': total, 'missing': miss}
    return gap


def chunk(missing: list[int], size: int) -> list[list[int]]:
    """把缺页切成交替的小段（首尾交替，避免全挤在开头）。"""
    out = []
    i = 0
    while i < len(missing):
        out.append(missing[i:i + size])
        i += size
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='卡住接管驱动器：算缺口')
    ap.add_argument('--work', required=True)
    ap.add_argument('--chapters', nargs='*', default=None,
                    help='只处理这些话，如 ch001 ch002；省略则全部')
    ap.add_argument('--pages-per-task', type=int, default=4)
    ap.add_argument('--max-tasks', type=int, default=24,
                    help='本轮最多派出多少段（控制单轮时长）')
    args = ap.parse_args()

    work = pathlib.Path(args.work)
    gap = scan_gap(work, args.chapters)
    if not gap:
        print(json.dumps({'done': True, 'gap': {}, 'tasks': 0}, ensure_ascii=False))
        return 0

    # 本轮只取 max_tasks 段。**轮转分配**：每话先各取一段，
    # 取完一轮再回头取第二轮，避免把整个配额都压在某一话上
    order = sorted(gap.items(), key=lambda kv: len(kv[1]['missing']))
    queues = {ch: chunk(info['missing'], args.pages_per_task) for ch, info in order}
    picked: dict[str, dict] = {}
    tasks = 0
    while tasks < args.max_tasks:
        progressed = False
        for ch, info in order:
            if tasks >= args.max_tasks:
                break
            q = queues.get(ch)
            if not q:
                continue
            take = q.pop(0)
            picked.setdefault(ch, {'ep': info['ep'], 'pages': []})
            picked[ch]['pages'].extend(take)
            tasks += 1
            progressed = True
        if not progressed:
            break

    total_gap = sum(len(v['missing']) for v in gap.values())
    total_pages = sum(v['total'] for v in gap.values())
    print(json.dumps({
        'done': False,
        'chapters_with_gap': len(gap),
        'total_gap_pages': total_gap,
        'this_round_tasks': tasks,
        'this_round_pages': sum(len(v['pages']) for v in picked.values()),
        'gap': picked,
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
