#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S6 - automated checks for one novelized chapter.

Checks the things a script can check reliably:
  1. dialogue coverage  - every key quote from outline.json appears in draft.md
  2. banned words       - panel/frame vocabulary leaked into prose
  3. length             - Chinese character count against pages * [min,max]
  4. name whitelist     - names used before 说/道/问 must exist in bible.md

Faithfulness and continuity are left to an agent (see prompts/04-qa.md);
this script writes them as {"pass": true, "manual": true} placeholders.

Usage:
    python check_prose.py --draft ch001/draft.md --outline ch001/outline.json \
        --bible bible.md --pages 29 --out ch001/qa.json
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys

DEFAULT_BANNED = ["画面", "镜头", "分镜", "这一格", "格子", "读者", "漫画", "对话框", "旁白框"]
CJK = re.compile(r"[\u4e00-\u9fff]")
NON_WORD = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")
SPEECH_VERBS = "说道问喊答叫骂笑哭吼"
STOP_NAMES = {"他们", "她们", "我们", "你们", "众人", "有人", "那人", "这人", "两人", "一人",
              "所有人", "其他人", "对方", "自己", "大家", "二人", "三人", "老者", "少年", "少女"}

# Characters that almost never appear inside a person's name in this genre.
# Used to reject heuristic candidates such as "陈松又" or "停下来".
STOP_CHARS = set("又没才便就也都却再正刚已仍还只更最很不把被让使得地着过吗呢吧啊要会能可应"
                 "想说问答道看听走来去上下里外中间后前时天年日月人的了是我你他她们这那有在"
                 "到从对给和与向为以于之其停站坐跑哭笑喊叫骂打杀")


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_front_matter(text: str) -> tuple[dict, str]:
    """Split a minimal YAML front matter block from the body."""
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


def coverage(quotes: list[dict], body: str, min_ratio: float) -> tuple[float, list[dict]]:
    """Fraction of quotes that appear in the body (longest common block)."""
    if not quotes:
        return 1.0, []
    body_norm = normalize(body)
    missing = []
    hits = 0
    for quote in quotes:
        q = normalize(quote.get("text", ""))
        if not q:
            continue
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
    return round(hits / len(quotes), 3), missing


def load_bible_names(path: str | None) -> set[str]:
    """Collect character names from bible.md and glossary.csv."""
    names: set[str] = set()
    if not path:
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
    csv_path = path.replace(".md", "") + ".csv"
    try:
        with open(csv_path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if "人物" in (row.get("type") or "") and row.get("term"):
                    names.add(row["term"].strip())
    except OSError:
        pass
    # bare names written as "- 名：X  （备注）"
    return {n for n in names if n}


def unknown_names(body: str, whitelist: set[str]) -> list[str]:
    """Heuristically flag person names used before a speech verb.

    This is advisory by design: Chinese has no capitalisation, so a perfect
    detector is not possible. It catches the common failure -- a name the
    bible never defined -- while rejecting function words and cases where a
    known name is merely followed by an adverb ("陈松又说").
    """
    if not whitelist:
        return []
    pattern = re.compile(rf"([\u4e00-\u9fff]{{2,4}})(?=[{SPEECH_VERBS}])")
    suspects: set[str] = set()
    for match in pattern.finditer(body):
        name = match.group(1)
        # a known name plus trailing adverb/negation is not a new name
        if any(name.startswith(w) for w in whitelist):
            continue
        if len(name) < 2 or name in STOP_NAMES:
            continue
        if any(ch in STOP_CHARS for ch in name):
            continue
        suspects.add(name)
    return sorted(suspects)


def main() -> int:
    ap = argparse.ArgumentParser(description="Automated QA for one chapter draft.")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--outline", required=True)
    ap.add_argument("--bible", default=None)
    ap.add_argument("--pages", type=int, required=True, help="page count of the chapter")
    ap.add_argument("--out", default=None, help="qa.json output path")
    ap.add_argument("--min-coverage", type=float, default=0.95)
    ap.add_argument("--match-ratio", type=float, default=0.8)
    ap.add_argument("--length-per-page", type=int, nargs=2, default=[100, 220],
                    metavar=("MIN", "MAX"))
    ap.add_argument("--banned", nargs="*", default=None)
    args = ap.parse_args()

    draft = read_text(args.draft)
    meta, body = split_front_matter(draft)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)

    outline = json.loads(read_text(args.outline))
    quotes = outline.get("quotes", [])

    banned = args.banned if args.banned is not None else DEFAULT_BANNED
    hits = {w: body.count(w) for w in banned if w in body}

    cov, missing = coverage(quotes, body, args.match_ratio)
    words = count_chars(body)
    lo, hi = args.pages * args.length_per_page[0], args.pages * args.length_per_page[1]
    whitelist = load_bible_names(args.bible)
    unknown = unknown_names(body, whitelist)

    checks = {
        "quote_coverage": {"pass": cov >= args.min_coverage, "value": cov, "missing": missing},
        "name_whitelist": {"pass": not unknown, "unknown": unknown,
                           "whitelist_size": len(whitelist)},
        "banned_words": {"pass": not hits, "hits": hits},
        "length": {"pass": lo <= words <= hi, "value": words, "range": [lo, hi]},
        "faithfulness": {"pass": True, "manual": True, "issues": []},
        "continuity": {"pass": True, "issues": []},
    }

    score = 100
    score -= len(missing) * 3
    score -= sum(hits.values()) * 2
    if not checks["length"]["pass"]:
        score -= 5
    score = max(0, score)

    qa = {"chapter": outline.get("chapter"), "checks": checks,
          "fixes": [], "score": score}

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(qa, fh, ensure_ascii=False, indent=1)

    print(json.dumps({
        "chapter": qa["chapter"],
        "words": words,
        "words_range": [lo, hi],
        "quote_coverage": cov,
        "missing_quotes": len(missing),
        "banned_hits": sum(hits.values()),
        "unknown_names": unknown[:10],
        "score": score,
    }, ensure_ascii=False, indent=1))

    ok = (cov >= args.min_coverage and not hits and checks["length"]["pass"]
          and not unknown and score >= 80)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
