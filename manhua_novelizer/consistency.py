# -*- coding: utf-8 -*-
"""S6.5 全本一致性审计：跨话检查时间、年龄、生死、外观（建模）漂移、未登记人名。"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
AGE_TOLERANCE = 1.5


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
                         "state": data.get("state") or {}})
    chapters.sort(key=lambda c: (c["chapter"] is None, c["chapter"] or 0))
    return chapters


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
        json_out: str | None = None) -> dict:
    chapters = load_chapters(work)
    if not chapters:
        return {"error": f"no outline.json under {work}"}
    baseline = bible_names(bible) if bible else {}
    issues: list[dict] = []
    missing_state(chapters, issues)
    check_timeline(chapters, issues)
    check_ageing(chapters, issues)
    check_death(chapters, issues)
    check_look(chapters, baseline, issues)
    check_names(chapters, baseline, issues)

    report = render_markdown(issues, chapters)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
    if json_out:
        os.makedirs(os.path.dirname(os.path.abspath(json_out)) or ".", exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump({"chapters": len(chapters), "issues": issues}, fh,
                      ensure_ascii=False, indent=1)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warns = sum(1 for i in issues if i["severity"] == "warn")
    return {"chapters": len(chapters), "errors": errors, "warnings": warns,
            "infos": len(issues) - errors - warns, "report": out or "(stdout)",
            "issues": issues, "markdown": report}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全本一致性审计")
    ap.add_argument("--work", default=".")
    ap.add_argument("--bible", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)
    result = run(args.work, args.bible, args.out, args.json_out)
    issues = result.pop("issues", [])
    markdown = result.pop("markdown", "")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not args.out and markdown:
        print()
        print(markdown)
    return 1 if result.get("errors") else (2 if result.get("error") else 0)


if __name__ == "__main__":
    sys.exit(main())
