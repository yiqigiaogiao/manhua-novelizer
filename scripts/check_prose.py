# -*- coding: utf-8 -*-
"""S6 单话质检：只查"是否忠实"，不设字数上下限、不设禁用词表。

核心指标是**台词覆盖**（原文对白是否逐字落到正文）与**人物白名单**，
因为改编的第一优先级是原作事实与人物声音，而不是篇幅或某几个词。

另外还有一道**转录完整性**检查：拿 `page_script.json` 里所有对白格和
`outline.quotes` 的条数对账。台词覆盖率只对 outline 负责，上游漏记一句
对白，outline 里就没有这一条，覆盖率照样 100%——QA 永远发现不了。
这道检查堵的就是这个盲区。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]")
NON_WORD = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")
SPEECH_VERBS = "说道问喊答叫骂笑哭吼"
STOP_NAMES = {"他们", "她们", "我们", "你们", "众人", "有人", "那人", "这人", "两人", "一人",
              "所有人", "其他人", "对方", "自己", "大家", "二人", "三人", "老者", "少年", "少女"}
STOP_CHARS = set("又没才便就也都却再正刚已仍还只更最很不把被让使得地着过吗呢吧啊要会能可应"
                 "想说问答道看听走来去上下里外中间后前时天年日月人的了是我你他她们这那有在"
                 "到从对给和与向为以于之其停站坐跑哭笑喊叫骂打杀")


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, parts[2]


def normalize(text: str) -> str:
    """剔非中英数字符 + 繁→简归一。

    繁简归一不是锦上添花：台版/港版原稿保留繁体（「話」「來」），而正文按简体写，
    不归一时 `q in body_norm` 直接失败，只能靠 difflib 0.8 兜底——既可能误放
    （0.8 以上就放行）也可能误杀（差一字就整句判漏）。

    `zhconv` 是**可选**依赖：没装时只做字符清洗，行为退化但不报错。
    装它：`pip install zhconv`（README / SKILL.md 已注明）。
    """
    try:
        import zhconv
        text = zhconv.convert(text, "zh-cn")
    except ImportError:
        pass  # 没有 zhconv 就不转换，行为退化但不报错
    return NON_WORD.sub("", text)


def count_chars(text: str) -> int:
    return len(CJK.findall(text))


def coverage(quotes: list[dict], body: str, min_ratio: float = 0.8) -> tuple[float, list[dict]]:
    # 标点型引语（「……」「？」）没有可核对的内容，不进分母
    content = [(q, normalize(q.get("text", ""))) for q in quotes]
    content = [(q, norm) for q, norm in content if norm]
    if not content:
        return 1.0, []
    body_norm = normalize(body)
    missing, hits = [], 0
    for quote, q in content:
        if q in body_norm:
            hits += 1
            continue
        sm = difflib.SequenceMatcher(None, q, body_norm, autojunk=False)
        block = sm.find_longest_match(0, len(q), 0, len(body_norm))
        if block.size / max(len(q), 1) >= min_ratio:
            hits += 1
        else:
            missing.append({"page": quote.get("page"), "speaker": quote.get("speaker"),
                            "text": quote.get("text")})
    return round(hits / len(content), 3), missing


def load_bible_names(path: str | None) -> set[str]:
    names: set[str] = set()
    if not path or not path.endswith(".md"):
        return names
    try:
        text = read_text(path)
    except OSError:
        return names
    for line in text.splitlines():
        m = re.match(r"\s*-\s*名\s*[:：]\s*(.+)", line)
        if m:
            names.add(m.group(1).strip())
        m = re.match(r"\s*别名\s*[:：]\s*\[(.*)\]", line)
        if m:
            names.update(v.strip() for v in m.group(1).split(",") if v.strip())
    return names


def unknown_names(body: str, whitelist: set[str]) -> list[str]:
    """启发式：说话动词前的人名，未登记则提示（仅提示，不判失败）。"""
    if not whitelist:
        return []
    pattern = re.compile(rf"([\u4e00-\u9fff]{{2,4}})(?=[{SPEECH_VERBS}])")
    suspects: set[str] = set()
    for match in pattern.finditer(body):
        name = match.group(1)
        if any(name.startswith(w) for w in whitelist):
            continue
        if len(name) < 2 or name in STOP_NAMES:
            continue
        if any(ch in STOP_CHARS for ch in name):
            continue
        suspects.add(name)
    return sorted(suspects)


# page_script.json 里算"对白"的格类型。narration/sfx/sign 不是台词，
# thought（心声）算——正文同样要落地，否则改写时最容易被悄悄吃掉。
TRANSCRIBED_SPEECH_TYPES = {"speech", "dialogue", "spoken", "thought", "monologue"}


def transcribed_dialogues(page_script_path: str) -> list[dict]:
    """从 page_script.json 抽出所有对白型的格。

    page_script 有两种形态：单页（`panels[].text[]`）或整话（`pages[].panels[].text[]`），
    这里都支持。返回 [{"page","speaker","text"}]。
    """
    if not page_script_path or not os.path.isfile(page_script_path):
        return []
    try:
        with open(page_script_path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []

    pages = data.get("pages")
    if isinstance(pages, list):          # 整话合并形态
        containers = [p for p in pages if isinstance(p, dict)]
        page_of = lambda i, p: p.get("page", i + 1)
    else:                                # 单页形态
        containers = [data]
        page_of = lambda i, p: p.get("page", 1)

    out: list[dict] = []
    for i, page in enumerate(containers):
        panels = page.get("panels") or []
        if not isinstance(panels, list):
            continue
        for panel in panels:
            if not isinstance(panel, dict):
                continue
            for cell in (panel.get("text") or []):
                if not isinstance(cell, dict):
                    continue
                ctype = str(cell.get("type", "")).strip().lower()
                if ctype not in TRANSCRIBED_SPEECH_TYPES:
                    continue
                txt = (cell.get("text") or "").strip()
                if not txt:
                    continue
                out.append({"page": page_of(i, page),
                            "speaker": cell.get("speaker"),
                            "text": txt})
    return out


def transcription_integrity(page_script_path: str, quotes: list[dict]) -> dict:
    """转录完整性：上游到底记了多少句对白？outline.quotes 有没有漏记？

    为什么必须有这一条
    ------------------
    台词覆盖率只对 `outline.quotes` 负责。上游转录（S3）漏记一句对白，
    outline 里就没有这一条，S6 的覆盖率照样 100%——**QA 永远发现不了**。
    这是比繁简归一更根本的盲区：归一只影响比对精度，漏记直接让闸门失明。

    判据（宽松但有效）：`page_script.json` 的对白格数 vs `outline.quotes` 条数。
    数量明显更少 = outline 漏记。用数量而不是逐条匹配，是因为 outline 允许
    合并同格多句、剔除非正文拟声，逐条对不上是常态。
    """
    cells = transcribed_dialogues(page_script_path)
    if not cells:
        return {"pass": True, "value": None, "advisory": True,
                "note": "找不到 page_script.json 或没有对白格，跳过转录完整性检查",
                "transcribed": 0, "in_outline": len(quotes or [])}

    # 归一后去重：同一句话在页脚本里可能因跨页切片重复出现
    uniq = {normalize(c["text"]) for c in cells if normalize(c["text"])}
    outline_norm = {normalize(q.get("text", "")) for q in (quotes or [])
                    if normalize(q.get("text", ""))}
    transcribed, in_outline = len(uniq), len(outline_norm)

    # outline 比转录还多 = 正常（允许 outline 收窄）；反过来就是漏记
    if in_outline >= transcribed:
        return {"pass": True, "value": 1.0,
                "transcribed": transcribed, "in_outline": in_outline,
                "missing": []}
    return {
        "pass": False,
        "value": round(in_outline / transcribed, 3),
        "transcribed": transcribed,
        "in_outline": in_outline,
        "missing_count": transcribed - in_outline,
        "hint": ("outline.quotes 比 page_script.json 的对白格少——"
                 "上游转录或 S4 摘录漏记了对白，S6 的台词覆盖率会因此失真。"
                 "先补 page_script.json 的漏格，再重跑 S4 生成 outline.json。"),
    }


def run(draft: str, outline: str, bible: str | None = None, out: str | None = None,
        min_coverage: float = 1.0, match_ratio: float = 0.8,
        page_script: str | None = None) -> dict:
    text = read_text(draft)
    _, body = split_front_matter(text)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    data = json.loads(read_text(outline))
    quotes = data.get("quotes", [])

    cov, missing = coverage(quotes, body, match_ratio)
    names = load_bible_names(bible)
    suspects = unknown_names(body, names)

    # page_script.json 默认就在 outline.json 旁边（同目录），不用显式传
    if page_script is None:
        page_script = os.path.join(os.path.dirname(os.path.abspath(outline)),
                                   "page_script.json")
    integrity = transcription_integrity(page_script, quotes)

    checks = {
        "quote_coverage": {"pass": cov >= min_coverage, "value": cov, "missing": missing},
        "transcription_integrity": integrity,
        "name_whitelist": {"pass": True, "suspects": suspects, "whitelist_size": len(names),
                           "advisory": True},
    }
    qa = {"chapter": data.get("chapter"), "checks": checks,
          "words": count_chars(body), "fixes": [],
          "score": round(100 * min(cov / max(min_coverage, 1e-6), 1.0))}
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(qa, fh, ensure_ascii=False, indent=1)
    return qa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="单话质检（只看忠实度）")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--outline", required=True)
    ap.add_argument("--bible", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--page-script", default=None,
                    help="page_script.json 路径；默认取 outline.json 同目录下的同名文件")
    ap.add_argument("--min-coverage", type=float, default=1.0,
                    help="台词覆盖合格线，默认 1.0（对白必须 100%% 落地）")
    ap.add_argument("--match-ratio", type=float, default=0.8)
    args = ap.parse_args(argv)
    qa = run(args.draft, args.outline, args.bible, args.out,
             args.min_coverage, args.match_ratio, args.page_script)
    print(json.dumps(qa, ensure_ascii=False, indent=1))
    coverage_ok = qa["checks"]["quote_coverage"]["pass"]
    integrity_ok = qa["checks"]["transcription_integrity"]["pass"]
    return 0 if (coverage_ok and integrity_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
