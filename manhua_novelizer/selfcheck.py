# -*- coding: utf-8 -*-
"""自检：把交付要求转成可验证的断言，输出逐条结论。

用法：mnv selfcheck
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "pyproject.toml",
    "references/principles.md",
    "references/style-config.md",
    "references/pipeline.md",
    "references/schemas.md",
    "prompts/00-style-analysis.md",
    "prompts/01-page-script.md",
    "prompts/02-chapter-outline.md",
    "prompts/03-prose.md",
    "prompts/04-qa.md",
    "prompts/05-bible.md",
    "prompts/06-consistency-audit.md",
    "prompts/07-web-research.md",
    "prompts/08-reading-order.md",
    "manhua_novelizer/__init__.py",
    "manhua_novelizer/cli.py",
    "manhua_novelizer/gui.py",
    "manhua_novelizer/style.py",
    "manhua_novelizer/build.py",
    "manhua_novelizer/epub.py",
    "manhua_novelizer/mobi.py",
    "manhua_novelizer/reading_order.py",
]


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def check_files() -> dict:
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(ROOT, f))]
    return {"pass": not missing, "missing": missing}


def check_no_length_limit() -> dict:
    """配置与质检里不应再有字数上下限。"""
    cfg = _read("manhua_novelizer/config.py")
    qa = _read("manhua_novelizer/qa.py")
    hits = []
    if "length_per_page" in cfg:
        hits.append("config.py 仍有 length_per_page")
    if "words_range" in qa or '"length"' in qa:
        hits.append("qa.py 仍有长度检查")
    return {"pass": not hits, "hits": hits}


def check_no_banned_words() -> dict:
    cfg = _read("manhua_novelizer/config.py")
    qa = _read("manhua_novelizer/qa.py")
    hits = []
    if "banned_words" in cfg:
        hits.append("config.py 仍有 banned_words")
    if "banned" in qa:
        hits.append("qa.py 仍有禁用词检查")
    return {"pass": not hits, "hits": hits}


def check_formats() -> dict:
    build = _read("manhua_novelizer/build.py")
    pages = _read("manhua_novelizer/pages.py")
    return {
        "pass": all(k in build for k in ("epub", "mobi", "cover.png")) and "png" in pages,
        "mobi": "mobi" in build,
        "epub": "epub" in build,
        "cover_png": "cover.png" in build,
        "page_png": 'choices=["jpg", "png"]' in pages,
    }


def check_cleanup() -> dict:
    pages = _read("manhua_novelizer/pages.py")
    return {
        "pass": "def cleanup" in pages and ".png" in pages and "dry_run" in pages,
        "dry_run": "dry_run" in pages,
        "keep": "keep" in pages,
        "removes_png": ".png" in pages,
    }


def check_software_form() -> dict:
    pyproject = _read("pyproject.toml")
    cli = _read("manhua_novelizer/cli.py")
    commands = re.findall(r'sub\.add_parser\("([a-z]+)"', cli)
    return {
        "pass": 'mnv = "manhua_novelizer.cli:main"' in pyproject and "gui" in commands,
        "console_script": "mnv" in pyproject,
        "commands": sorted(commands),
        "gui": "gui" in commands,
    }


def check_style_profile() -> dict:
    style = _read("manhua_novelizer/style.py")
    dims = re.findall(r'\("([a-z]+)", "([^"]+)"\)', style)
    prose = _read("prompts/03-prose.md")
    cfg = _read("manhua_novelizer/config.py")
    return {
        "pass": len(dims) == 8 and "style.md" in prose and "confirmed" in style,
        "dimensions": len(dims),
        "gate_confirmed": "confirmed" in style,
        "versioned": "style_history" in style,
        "prose_reads_style": "style.md" in prose,
        "config_points_to_style": "style.json" in cfg,
    }


def check_principles() -> dict:
    text = _read("references/principles.md")
    markers = ["核心任务", "优先级", "先理解", "视觉信息", "分镜节奏", "对白",
               "AI 式补写", "必要补写", "自检", "输出"]
    missing = [m for m in markers if m not in text]
    return {"pass": not missing, "missing_sections": missing, "chars": len(text)}


def check_git() -> dict:
    import subprocess
    try:
        out = subprocess.run(["git", "log", "--oneline", "-1"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8")
        head = out.stdout.strip()
        remote = subprocess.run(["git", "rev-parse", "--short", "origin/main"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8")
        return {"pass": bool(head), "head": head, "origin": remote.stdout.strip()}
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "error": str(exc)}


def run() -> dict:
    checks = {
        "1. 交付文件齐全": check_files(),
        "2. 取消字数上下限": check_no_length_limit(),
        "3. 取消禁用词": check_no_banned_words(),
        "4. 支持 mobi / png": check_formats(),
        "5. PNG 及时清理": check_cleanup(),
        "6. 软件形式（CLI+GUI）": check_software_form(),
        "7. 叙事风格配置（八维度/确认/版本）": check_style_profile(),
        "8. 改编原则齐备": check_principles(),
        "9. Git 提交": check_git(),
    }
    ok = all(c.get("pass") for c in checks.values())
    return {"pass": ok, "checks": checks}


def main() -> int:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    failed = [k for k, v in result["checks"].items() if not v.get("pass")]
    if failed:
        print("\n未通过：", "；".join(failed), file=sys.stderr)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
