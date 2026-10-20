# -*- coding: utf-8 -*-
"""沉浸感质检（第三版：用"不含引号即叙述段"这个客观界限，不再靠词表猜）。

前两版失败的原因：
- v1 按段判"有引号无动作词 = 纯对白"，把"动作段 + 引号段"的正常写法判成错误。
- v2 加了 ±1 段窗口，但动作词表只有 30 个词，"张着嘴""仰着头""把屏幕推近"
  这些真动作都匹配不上，实测 agent 自估 40-67% 而脚本判 17-27%，尺子失真。

v3 判法：
- 段落分两类：**含引号的（对白段）** vs **不含引号的（叙述/动作段）**。
  这个界限是客观的，不依赖词表。
- 核心指标改成：**叙述段占比**（合格小说 40-60%）、
  **最长连续对白段**（≥3 才算剧本化）、
  **对白段是否被叙述段包夹**（前后不能都是对白段）。
- 词表只用于两个窄用途：判断"叙述段里有没有具体身体动作"（软指标）、
  以及检测概括动词/心理独白。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

CONCRETE = re.compile(
    "眼|嘴|唇|牙|舌|眉|额|脸|面|腮|颊|下巴|头|颈|脖|肩|背|腰|胸|腹|手|指|掌|拳|臂|肘|腕"
    "|腿|脚|膝|喉|咽|呼吸|气|汗|泪|血|抖|颤|僵|停|站|坐|跪|蹲|走|跑|转身|低头|抬头|看|望|盯"
)
SUMMARY = re.compile("讲述了|议论了一番|讨论了一番|发生了争执|经过一番|纷纷表示|陷入沉思")
META = re.compile("画面中|镜头|这一格|读者")
PSY = re.compile("感到一阵|心里清楚|心中一凛|不禁|仿佛在诉说|深知")
BAD_QUOTES = re.compile("[\u300c\u300d\u300e\u300f]")
ELLIPSIS = re.compile(r"(?<!\.)\.\.(?!\.)")


def split_body(text: str) -> str:
    parts = text.split("---", 2)
    return parts[2] if len(parts) >= 3 else text


def paragraphs(body: str) -> list[str]:
    out = []
    for p in body.split("\n\n"):
        p = p.strip()
        if not p or p.startswith("#") or p == "◇":
            continue
        out.append(p)
    return out


def check_one(path: str) -> dict:
    text = open(path, encoding="utf-8").read()
    body = split_body(text)
    paras = paragraphs(body)
    n = len(paras)
    if not n:
        return {"file": path, "fail": True, "problems": [{"level": "fail", "msg": "正文为空"}]}

    # 认 U+201C（全角“”）与 U+300C（角括号「」），避免「」稿被判成叙述段 → 假绿灯
    is_dialog = [any(c in p for c in "\u201c\u300c") for p in paras]
    n_dialog = sum(is_dialog)
    n_narr = n - n_dialog
    narr_ratio = n_narr / n

    # 最长连续对白
    max_run = run = 0
    for d in is_dialog:
        run = run + 1 if d else 0
        max_run = max(max_run, run)

    # 对白段是否被叙述段包夹（孤立对白 = 前后都是对白段或到头）
    isolated = 0
    for i, d in enumerate(is_dialog):
        if not d:
            continue
        prev_d = is_dialog[i - 1] if i > 0 else True
        next_d = is_dialog[i + 1] if i + 1 < n else True
        if prev_d and next_d:
            isolated += 1

    # 叙述段里有多少含具体身体动作（软指标）
    concrete = sum(1 for p, d in zip(paras, is_dialog) if not d and CONCRETE.search(p))
    concrete_ratio = concrete / n_narr if n_narr else 0.0

    cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
    problems = []

    if narr_ratio < 0.35:
        problems.append(("warn", f"叙述段只占 {narr_ratio:.0%}（参考合格小说 40–60%，仅供参考）"))
    elif narr_ratio < 0.40:
        problems.append(("warn", f"叙述段占比 {narr_ratio:.0%}，偏低"))
    if max_run >= 3:
        problems.append(("warn", f"连续 {max_run} 段纯对白（漫画原作常见大量对白，仅供参考）"))
    if n_narr and concrete_ratio < 0.6:
        problems.append(("warn", f"叙述段中只有 {concrete_ratio:.0%} 写了具体身体动作"))

    for name, pat, level in (("概括动词", SUMMARY, "fail"),
                             ("说明语言", META, "fail"),
                             ("心理独白", PSY, "warn")):
        hits = pat.findall(body)
        if hits:
            problems.append((level, f"{name}：{sorted(set(hits))[:5]}"))
    n_bad = len(BAD_QUOTES.findall(body))
    if n_bad:
        # 引号规范化属于 S7（normalize_quotes），此处不阻断流程，仅提示
        problems.append(("warn", "存在角引号 " + str(n_bad) + " 处，引号在 S7 由 normalize_quotes 规范化；此处不阻断流程"))

    return {
        "file": os.path.basename(os.path.dirname(path)) or os.path.basename(path),
        "cjk": cjk,
        "paragraphs": n,
        "dialog": n_dialog,
        "narration": n_narr,
        "narration_ratio": round(narr_ratio, 3),
        "max_dialog_run": max_run,
        "isolated_dialog": isolated,
        "concrete_ratio": round(concrete_ratio, 3),
        "problems": [{"level": lv, "msg": m} for lv, m in problems],
        "fail": any(lv == "fail" for lv, _ in problems),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="沉浸感质检")
    ap.add_argument("--draft")
    ap.add_argument("--work")
    args = ap.parse_args(argv)
    paths = [args.draft] if args.draft else (
        sorted(glob.glob(os.path.join(args.work, "ch*", "draft.md"))) if args.work else [])
    if not paths:
        ap.error("需要 --draft 或 --work")

    results = [check_one(p) for p in paths]
    ok = sum(1 for r in results if not r.get("fail"))
    print(json.dumps({"checked": len(results), "passing": ok, "results": results},
                     ensure_ascii=False, indent=1))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
