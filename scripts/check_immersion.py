# -*- coding: utf-8 -*-
"""沉浸感质检：表情/神态、对白穿插、概括句。

判的是"这篇稿子是不是在写场景串烧"。

设计要点：
- **按段落判定，不按词频**。词频会把"看""停"这类单字重复计数，虚高到没有意义。
  这里判断"这一段里有没有表情或身体动作的成分"，是有没有的问题，不是多不多的问题。
- **纯对白段**：整段有引号、但没有任何表情/动作成分 → 人物只有台词没有脸。
- **连排**：连续 3 段以上都是纯对白 → 读起来像剧本。

用法：
    python check_immersion.py --draft work/ch001/draft.md
    python check_immersion.py --work work
退出码：0 通过；1 有 fail
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

# 表情 / 神态 / 身体动作（"脸上和身上发生的事"）
BODY = re.compile(
    "眼神|目光|视线|抬眼|低眼|垂眼|眯|睁|眨|盯|瞥|望|看了一眼|看向他|看向"
    "|嘴角|抿|咧|咬|笑|皱|眉|额"
    "|脸色|面色|腮|颊|下巴|脸上"
    "|手指|指节|手背|掌|拳|攥|握|松|垂|抬手|伸手|攥紧|松开"
    "|肩膀|肩|背|腰|胸口|喉|咽|吞咽|呼吸|喘|气息"
    "|汗|泪|抖|颤|僵|顿住|停住|愣|怔|沉默"
)
# 概括动词（写了就是在作弊）
SUMMARY = re.compile("讲述了|议论了一番|讨论了一番|发生了争执|经过一番|纷纷表示|陷入沉思")
# 说明语言
META = re.compile("画面中|镜头|这一格|读者")
# 心理独白（替人物下判断）
PSY = re.compile("感到一阵|心里清楚|心中一凛|不禁|仿佛在诉说|深知")
# 标点规范
BAD_QUOTES = re.compile("[\u300c\u300d\u300e\u300f]")
ELLIPSIS = re.compile(r"(?<!\.)\.\.(?!\.)")


def split_body(text: str) -> str:
    parts = text.split("---", 2)
    return parts[2] if len(parts) >= 3 else text


def paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def is_pure_dialog(p: str) -> bool:
    """有引号，但整段没有任何表情/身体动作成分。"""
    return "\u201c" in p and not BODY.search(p)


def check_one(path: str) -> dict:
    text = open(path, encoding="utf-8").read()
    body = split_body(text)
    paras = paragraphs(body)

    # 连续纯对白段
    run, max_run, sample = 0, 0, []
    for p in paras:
        if is_pure_dialog(p):
            run += 1
            sample.append(p[:28])
            max_run = max(max_run, run)
        else:
            run = 0
            sample = []

    dialog_paras = [p for p in paras if "\u201c" in p]
    pure = [p for p in dialog_paras if is_pure_dialog(p)]
    pure_ratio = len(pure) / len(dialog_paras) if dialog_paras else 0.0

    cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
    body_paras = [p for p in paras if BODY.search(p)]
    body_ratio = len(body_paras) / len(paras) if paras else 0.0

    problems = []
    if dialog_paras and pure_ratio > 0.5:
        problems.append(("fail", f"含对白的段落里 {pure_ratio:.0%} 没有任何表情/动作穿插（要求 ≤50%）"))
    elif dialog_paras and pure_ratio > 0.3:
        problems.append(("warn", f"纯对白段占比偏高 {pure_ratio:.0%}"))
    if max_run >= 3:
        problems.append(("fail", f"连续纯对白 {max_run} 段（要求 <3）"))
        if sample:
            problems.append(("info", "示例：" + " / ".join(sample[:3])))
    if cjk >= 300 and body_ratio < 0.25:
        problems.append(("fail", f"只有 {body_ratio:.0%} 的段落写到表情或身体动作（要求 ≥25%）"))
    elif cjk >= 300 and body_ratio < 0.4:
        problems.append(("warn", f"表情/动作覆盖偏低 {body_ratio:.0%}"))

    for name, pat, level in (("概括动词", SUMMARY, "fail"),
                             ("说明语言", META, "fail"),
                             ("心理独白", PSY, "warn")):
        hits = pat.findall(body)
        if hits:
            problems.append((level, f"{name}：{sorted(set(hits))[:5]}"))
    if BAD_QUOTES.search(body):
        problems.append(("fail", "存在「」『』角括号"))
    if ELLIPSIS.search(body):
        problems.append(("warn", "存在半角省略号"))

    return {
        "file": os.path.basename(os.path.dirname(path)) or os.path.basename(path),
        "cjk": cjk,
        "paragraphs": len(paras),
        "dialog_paras": len(dialog_paras),
        "pure_dialog_ratio": round(pure_ratio, 3),
        "body_paragraph_ratio": round(body_ratio, 3),
        "max_pure_dialog_run": max_run,
        "problems": [{"level": lv, "msg": m} for lv, m in problems],
        "fail": any(lv == "fail" for lv, _ in problems),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="沉浸感质检")
    ap.add_argument("--draft", help="单篇 draft.md")
    ap.add_argument("--work", help="工作目录，检查其下 ch*/draft.md")
    args = ap.parse_args(argv)

    if args.draft:
        paths = [args.draft]
    elif args.work:
        paths = sorted(glob.glob(os.path.join(args.work, "ch*", "draft.md")))
    else:
        ap.error("需要 --draft 或 --work")
    if not paths:
        ap.error("没有找到 draft.md")

    results = [check_one(p) for p in paths]
    print(json.dumps({"checked": len(results),
                      "failing": sum(1 for r in results if r["fail"]),
                      "results": results}, ensure_ascii=False, indent=1))
    return 1 if any(r["fail"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
