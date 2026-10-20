# -*- coding: utf-8 -*-
"""S6 单话质检：只查"是否忠实"，不设字数上下限、不设禁用词表。

核心指标是**台词覆盖**（原文对白是否逐字落到正文）与**人物白名单**，
因为改编的第一优先级是原作事实与人物声音，而不是篇幅或某几个词。
"""
from __future__ import annotations

import argparse
import difflib
import json
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


def run(draft: str, outline: str, bible: str | None = None, out: str | None = None,
        min_coverage: float = 1.0, match_ratio: float = 0.8) -> dict:
    text = read_text(draft)
    _, body = split_front_matter(text)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    data = json.loads(read_text(outline))
    quotes = data.get("quotes", [])

    cov, missing = coverage(quotes, body, match_ratio)
    names = load_bible_names(bible)
    suspects = unknown_names(body, names)

    checks = {
        "quote_coverage": {"pass": cov >= min_coverage, "value": cov, "missing": missing},
        "name_whitelist": {"pass": True, "suspects": suspects, "whitelist_size": len(names),
                           "advisory": True},
    }
    qa = {"chapter": data.get("chapter"), "checks": checks,
          "words": count_chars(body), "fixes": [],
          "score": round(100 * min(cov / max(min_coverage, 1e-6), 1.0))}
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(qa, fh, ensure_ascii=False, indent=1)
    return qa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="单话质检（只看忠实度）")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--outline", required=True)
    ap.add_argument("--bible", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-coverage", type=float, default=1.0,
                    help="台词覆盖合格线，默认 1.0（对白必须 100%% 落地）")
    ap.add_argument("--match-ratio", type=float, default=0.8)
    args = ap.parse_args(argv)
    qa = run(args.draft, args.outline, args.bible, args.out, args.min_coverage, args.match_ratio)
    print(json.dumps(qa, ensure_ascii=False, indent=1))
    return 0 if qa["checks"]["quote_coverage"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
