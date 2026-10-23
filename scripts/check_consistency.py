# -*- coding: utf-8 -*-
"""S6.5 全本一致性审计：跨话检查时间、年龄、生死、外观（建模）漂移、未登记人名。

除了对账，本脚本还负责**证明自己不是在空跑**：

- 输入不完整（`bible.md` 空、`state` 大面积缺失）时，明确标
  `WARN: 输入不完整，结果不可信` 并以非零退出（`--lenient` 才放行）。
  否则"一路绿灯"可能只是因为根本没有可查的数据。
- 正文出现「回忆/往事/当年」等闪回信号、而 `state.timeline` 没标
  `flashback` 时主动提示——这正是死亡/年龄误报的根因。
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys

# 确保同目录模块可被 import（被当模块 import 时脚本目录不会自动进 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
AGE_TOLERANCE = 1.5

# state 缺失率超过这个比例就认为"输入不完整"
STATE_MISSING_RATIO = 0.5

# 正文里出现这些词，通常是闪回/回忆段
FLASHBACK_SIGNALS = ("回忆", "往事", "当年", "想起", "从前", "那一年",
                     "多年前", "十年前", "少年时", "年轻的时候")

# 闪回场景下 timeline 的推荐写法
FLASHBACK_HINT = ('把这一话的 state 标成 "flashback": true（或 '
                  'state.timeline = "flashback"），否则时间倒退会被当成矛盾上报')


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def bible_names(path: str | None) -> dict[str, str]:
    names: dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return names
    current = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"\s*-\s*名\s*[:：]\s*(.+)", line)
            if m:
                current = m.group(1).strip()
                names.setdefault(current, "")
                continue
            m = re.match(r"\s*别名\s*[:：]\s*\[(.*)\]", line)
            if m and current:
                for alias in m.group(1).split(","):
                    if alias.strip():
                        names.setdefault(alias.strip(), "")
                continue
            m = re.match(r"\s*外貌\s*[:：]\s*(.+)", line)
            if m and current:
                names[current] = m.group(1).strip()
    return names


def load_chapters(work: str) -> list[dict]:
    """扫 ch*/outline.json，同时带上同目录 draft.md 的正文（闪回信号要靠它）。"""
    chapters = []
    for path in glob.glob(os.path.join(work, "ch*", "outline.json")):
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        chapter = data.get("chapter")
        if chapter is None:
            m = re.search(r"ch(\d+)", path)
            chapter = int(m.group(1)) if m else None
        chapters.append({"chapter": chapter, "path": path, "data": data,
                         "state": data.get("state") or {},
                         "body": _chapter_body(path)})
    chapters.sort(key=lambda c: (c["chapter"] is None, c["chapter"] or 0))
    return chapters


def _chapter_body(outline_path: str) -> str:
    """同目录 draft.md 的正文；没有就返回空串（不影响其他检查）。"""
    draft = os.path.join(os.path.dirname(outline_path), "draft.md")
    if not os.path.isfile(draft):
        return ""
    try:
        with open(draft, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError:
        return ""
    # 剥 front matter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def add(issues: list[dict], severity: str, kind: str, chapter, message: str, **extra) -> None:
    issues.append({"severity": severity, "kind": kind, "chapter": chapter,
                   "message": message, **extra})


def check_timeline(chapters: list[dict], issues: list[dict]) -> None:
    previous = None
    for ch in chapters:
        state = ch["state"]
        year = state.get("year")
        if year is None:
            continue
        if previous is not None and not state.get("flashback"):
            prev_year = previous["state"].get("year")
            if prev_year is not None and year < prev_year:
                add(issues, "warn", "time", ch["chapter"],
                    f"故事年份从 {prev_year} 退到 {year}，但没有标 flashback")
        previous = ch


def check_ageing(chapters: list[dict], issues: list[dict]) -> None:
    history: dict[tuple[str, str], list[tuple[float, float, object]]] = {}
    for ch in chapters:
        state = ch["state"]
        year = state.get("year")
        if year is None:
            continue
        timeline = state.get("timeline", "main")
        for name, info in (state.get("cast") or {}).items():
            age = info.get("age") if isinstance(info, dict) else None
            if age is None:
                continue
            history.setdefault((timeline, name), []).append((year, float(age), ch["chapter"]))

    for (timeline, name), points in history.items():
        for (y0, a0, c0), (y1, a1, c1) in zip(points, points[1:]):
            dy, da = y1 - y0, a1 - a0
            if dy > 0.5 and da < -0.5:
                add(issues, "error", "ageing", c1,
                    f"{name} 年龄从 {a0:g} 倒退到 {a1:g}（时间前进 {dy:g} 年）", character=name)
            elif dy >= 2 and da < dy - AGE_TOLERANCE:
                add(issues, "warn", "ageing", c1,
                    f"{name} 时间前进 {dy:g} 年，年龄只涨 {da:g} 岁——是长大/建模改了，还是漏写？",
                    character=name)


def check_death(chapters: list[dict], issues: list[dict]) -> None:
    dead_at: dict[tuple[str, str], object] = {}
    for ch in chapters:
        state = ch["state"]
        timeline = state.get("timeline", "main")
        for name, info in (state.get("cast") or {}).items():
            status = (info or {}).get("status") if isinstance(info, dict) else None
            key = (timeline, name)
            if key in dead_at and status not in ("dead", "absent", "unknown"):
                add(issues, "error", "death", ch["chapter"],
                    f"{name} 在时间线「{timeline}」的第 {dead_at[key]} 话已死/退场，本话又活着出现",
                    character=name)
            if status in ("dead", "deceased"):
                dead_at.setdefault(key, ch["chapter"])


def check_look(chapters: list[dict], baseline: dict[str, str], issues: list[dict]) -> None:
    last: dict[str, tuple[str, object]] = {}
    for ch in chapters:
        for name, info in ((ch["state"].get("cast") or {})).items():
            look = (info or {}).get("look") if isinstance(info, dict) else None
            if not look:
                continue
            ref = baseline.get(name)
            if ref:
                ratio = difflib.SequenceMatcher(None, ref, look).ratio()
                if ratio < 0.5:
                    add(issues, "warn", "look", ch["chapter"],
                        f"{name} 的外貌与圣经基准差异较大（相似度 {ratio:.2f}）",
                        character=name, bible=ref, now=look)
            if name in last:
                prev_look, prev_ch = last[name]
                if prev_look != look:
                    add(issues, "info", "look", ch["chapter"],
                        f"{name} 的外貌从「{prev_look}」变成「{look}」（上一话 {prev_ch}）",
                        character=name, before=prev_look, after=look)
            last[name] = (look, ch["chapter"])


def check_names(chapters: list[dict], baseline: dict[str, str], issues: list[dict]) -> None:
    if not baseline:
        return
    for ch in chapters:
        for name in (ch["state"].get("cast") or {}):
            if name not in baseline:
                add(issues, "warn", "names", ch["chapter"],
                    f"「{name}」不在 bible.md 里——新角色请先补圣经", character=name)


def missing_state(chapters: list[dict], issues: list[dict]) -> None:
    for ch in chapters:
        if not ch["state"]:
            add(issues, "info", "state", ch["chapter"],
                "outline.json 没有 state 块，本话未参与一致性审计")


def check_flashback_signals(chapters: list[dict], issues: list[dict]) -> None:
    """正文出现闪回措辞但 state 没标 flashback -> 主动提示。

    死亡/年龄误报的根因就是"该标没标"：叙述跑回十年前，state.year 还是主线年份，
    于是审计把正常的回忆判成时间倒退。这类"该填没填"以前是静默的，
    脚本只会在结论上给出错误信号，这里改成在输入端就喊出来。
    """
    for ch in chapters:
        if not ch.get("body"):
            continue
        state = ch["state"]
        marked = bool(state.get("flashback")) or state.get("timeline") == "flashback"
        if marked:
            continue
        hits = sorted({w for w in FLASHBACK_SIGNALS if w in ch["body"]})
        if not hits:
            continue
        # 只有"明显在讲过去"才算：单押一个词可能是正常叙述
        if len(hits) < 2 and "回忆" not in hits and "往事" not in hits:
            continue
        add(issues, "warn", "flashback", ch["chapter"],
            f"正文出现闪回措辞（{'、'.join(hits)}），但 state 没标 flashback"
            f"——时间倒退与年龄倒退可能被误报；{FLASHBACK_HINT}",
            signals=hits)


def check_input_completeness(chapters: list[dict], bible: str | None,
                             issues: list[dict]) -> dict:
    """输入完整性：证明这次审计不是空跑。

    返回统计（也用于退出码判定）。判据：
    - `bible.md` 给了但文件不存在/内容为空 -> 人物外观与姓名检查失明；
    - `state` 缺失率超过 STATE_MISSING_RATIO -> 时间/年龄/死亡三项基本没数据。

    标 error 级（不是 warn）："一路绿灯但可能是空检查"比报错更危险，
    所以默认直接非零退出，`--lenient` 才降级为提示。
    """
    total = len(chapters)
    no_state = [c["chapter"] for c in chapters if not c["state"]]
    no_year = [c["chapter"] for c in chapters if c["state"].get("year") is None]
    no_cast = [c["chapter"] for c in chapters if not (c["state"].get("cast") or {})]

    bible_empty = False
    if bible:
        if not os.path.isfile(bible):
            bible_empty = True
        else:
            try:
                with open(bible, encoding="utf-8-sig") as fh:
                    content = fh.read().strip()
            except OSError:
                content = ""
            # 只有标题/空行的文件等于没有内容
            meaningful = [ln for ln in content.splitlines()
                          if ln.strip() and not ln.strip().startswith("#")]
            bible_empty = not meaningful

    state_missing_ratio = len(no_state) / total if total else 1.0
    incomplete = bible_empty or state_missing_ratio > STATE_MISSING_RATIO

    if incomplete:
        detail = []
        if bible_empty:
            detail.append(f"bible.md 为空或不存在（{bible}）——外观基准与姓名登记两项失明")
        if state_missing_ratio > STATE_MISSING_RATIO:
            detail.append(f"{len(no_state)}/{total} 话没有 state 块"
                          f"（{state_missing_ratio:.0%} > {STATE_MISSING_RATIO:.0%}）"
                          "——时间/年龄/死亡三项基本没数据")
        add(issues, "error", "input", None,
            "输入不完整，结果不可信：" + "；".join(detail) +
            "。先补 bible.md / outline.state，或确认这是有意为之后加 --lenient 放行")

    return {
        "bible_empty": bible_empty,
        "chapters": total,
        "state_missing": len(no_state),
        "state_missing_ratio": round(state_missing_ratio, 3),
        "year_missing": len(no_year),
        "cast_missing": len(no_cast),
        "incomplete": incomplete,
    }


def render_markdown(issues: list[dict], chapters: list[dict]) -> str:
    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in SEVERITY_ORDER}
    lines = ["# 一致性审计报告", "",
             f"扫描 {len(chapters)} 话；error {counts['error']} · warn {counts['warn']} · "
             f"info {counts['info']}", ""]
    if not issues:
        lines.append("没有发现冲突。")
        return "\n".join(lines)
    lines += ["| 级别 | 类型 | 话 | 说明 |", "|---|---|---|---|"]
    for issue in sorted(issues, key=lambda i: (SEVERITY_ORDER[i["severity"]], i["chapter"] or 0)):
        lines.append(f"| {issue['severity']} | {issue['kind']} | {issue['chapter']} | "
                     f"{issue['message']} |")
    return "\n".join(lines)


def run(work: str, bible: str | None = None, out: str | None = None,
        json_out: str | None = None, lenient: bool = False) -> dict:
    chapters = load_chapters(work)
    if not chapters:
        return {"error": f"no outline.json under {work}"}
    baseline = bible_names(bible) if bible else {}
    issues: list[dict] = []
    missing_state(chapters, issues)
    check_flashback_signals(chapters, issues)
    check_timeline(chapters, issues)
    check_ageing(chapters, issues)
    check_death(chapters, issues)
    check_look(chapters, baseline, issues)
    check_names(chapters, baseline, issues)

    completeness = check_input_completeness(chapters, bible, issues)
    if lenient:
        # 明确要求放行时，把"输入不完整"从 error 降成 warn
        for issue in issues:
            if issue["kind"] == "input" and issue["severity"] == "error":
                issue["severity"] = "warn"
                issue["message"] += "（--lenient 已放行）"

    report = render_markdown(issues, chapters)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
    if json_out:
        os.makedirs(os.path.dirname(os.path.abspath(json_out)) or ".", exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump({"chapters": len(chapters), "completeness": completeness,
                       "issues": issues}, fh, ensure_ascii=False, indent=1)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    return {"chapters": len(chapters), "errors": errors, "warnings": warns,
            "infos": len(issues) - errors - warns, "report": out or "(stdout)",
            "completeness": completeness,
            "issues": issues, "markdown": report}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全本一致性审计")
    ap.add_argument("--work", default=".")
    ap.add_argument("--bible", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--lenient", action="store_true",
                    help="输入不完整时只提示不拦截（默认：输入不完整即非零退出）")
    args = ap.parse_args(argv)
    result = run(args.work, args.bible, args.out, args.json_out, args.lenient)
    issues = result.pop("issues", [])
    markdown = result.pop("markdown", "")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not args.out and markdown:
        print()
        print(markdown)
    return 1 if result.get("errors") else (2 if result.get("error") else 0)


if __name__ == "__main__":
    sys.exit(main())
