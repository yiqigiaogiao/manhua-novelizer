# -*- coding: utf-8 -*-
"""S6.7b 原图复检闸门：一话必须过了原图核对，才算写完。

用法：
    python scripts/check_verify.py --work work
    python scripts/check_verify.py --work work --chapter 12
    python scripts/check_verify.py --work work --strict   # expression 未处理也拦

退出码：
    0  全部通过
    1  有章缺 verify.json / 有 major 问题未修订 / （--strict）有 expression 未补

判据（每条单独成立）：
1. 每个 ch*/ 有 draft.md 却缺 verify.json         → 这类章没过原图核对
2. verify.json 的 pages_checked 为空                → 等于没核
3. drift 里 severity in (major, minor) 的条目，
   在 revisions 里找不到对应 before                 → 未修订
4. expression_preserved in (lost, thin) 的场，
   在 revisions 里找不到 type=expression 的条目     → 未补（仅 --strict 拦）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import list_dirs  # noqa: E402

BLOCKING_SEVERITY = ("major", "minor")


def load_json(path: str):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def norm(s) -> str:
    return (s or "").strip() if isinstance(s, str) else str(s or "").strip()


def check_chapter(folder: str, strict: bool) -> list[str]:
    name = os.path.basename(folder)
    problems: list[str] = []
    vpath = os.path.join(folder, "verify.json")
    if not os.path.isfile(vpath):
        problems.append(f"{name}: 缺 verify.json（没过原图复检）")
        return problems

    verify = load_json(vpath)
    if verify is None:
        problems.append(f"{name}: verify.json 不是合法 JSON")
        return problems

    checked = verify.get("pages_checked") or []
    if not checked:
        problems.append(f"{name}: pages_checked 为空（没读任何原图）")

    revisions = verify.get("revisions") or []
    rev_before = {norm(r.get("before")) for r in revisions if r.get("before")}
    rev_types = {r.get("type") for r in revisions}

    for sc in verify.get("scene_checks") or []:
        sid = sc.get("scene", "?")
        for d in sc.get("drift") or []:
            sev = d.get("severity", "")
            if sev in BLOCKING_SEVERITY and norm(d.get("draft_says")) not in rev_before:
                problems.append(
                    f"{name}/{sid}: drift p{d.get('page')}（{sev}）未修订——"
                    f"{norm(d.get('draft_says'))[:40]}")
        if strict and sc.get("expression_preserved") in ("lost", "thin"):
            if "expression" not in rev_types:
                problems.append(
                    f"{name}/{sid}: 原作表达力 {sc.get('expression_preserved')}，未补回")

    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="原图复检闸门")
    ap.add_argument("--work", required=True)
    ap.add_argument("--chapter", type=int, default=None,
                    help="只查某一话（按 front matter 的「话」字段，省略则全部）")
    ap.add_argument("--strict", action="store_true",
                    help="expression=lost/thin 未补回也算不过")
    args = ap.parse_args(argv)

    problems: list[str] = []
    chapters = list_dirs(args.work, prefix="ch")
    checked = 0
    for folder in chapters:
        if not os.path.isfile(os.path.join(folder, "draft.md")):
            continue
        if args.chapter is not None:
            verify = load_json(os.path.join(folder, "verify.json")) or {}
            if int(verify.get("chapter", -1)) != args.chapter:
                continue
        checked += 1
        problems.extend(check_chapter(folder, args.strict))

    report = {
        "ok": not problems,
        "chapters_with_draft": checked,
        "checked": checked,
        "strict": args.strict,
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
