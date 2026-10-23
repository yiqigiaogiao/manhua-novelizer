# -*- coding: utf-8 -*-
"""S8 全本合并：把已出的各卷（含番外）合成一部完整小说。

用法
----
    python scripts/merge_books.py --books 出书目录 [--出书目录2 ...] \
        --out 全本.md --title "书名"
    python scripts/merge_books.py --books 出书目录 --out build --formats md docx epub

做什么
------
1. 扫描出书目录下每个「卷」的 stats.csv，得到全话索引（话号 -> 卷、标题、字数）。
2. 按目录行序从各卷 book.md 里**按顺序切块**（不是按标题匹配——标题有
   「第71話」「第七十一话」「谷风长道」等多种形态，匹配必然漏），
   目录第 N 行对应第 N 个正文块，与 stats.csv 第 N 行一一对应。
3. 按话号排序合成一部完整小说，输出 md；--formats 可加 docx / epub。
4. 对账：某卷 stats.csv 行数与 book.md 切出的块数对不上、或话号重复，直接拒绝合并。

为什么不能按标题匹配
--------------------
assemble.py 生成 book.md 时把每话的 `# 标题` 降级成 `## 标题`，标题就是
draft.md front matter 里的「标题:」——实际有「第71話」「第七十一话」
「谷风长道」三种形态，而且同一卷里可能重复。按标题匹配必漏。
块序才是可靠对应：目录行序 == 正文块序 == stats.csv 行序。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

# 确保同目录模块可被 import（被当模块 import 时脚本目录不会自动进 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import list_dirs  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")


def load_stats(book_dir: str) -> list[dict]:
    stats = os.path.join(book_dir, "stats.csv")
    if not os.path.isfile(stats):
        return []
    rows = []
    with open(stats, encoding="utf-8-sig") as fh:
        for r in csv.reader(fh):
            if len(r) < 3 or not r[0].strip().lstrip("-").isdigit():
                continue
            rows.append({
                "chapter": r[0].strip(),
                "title": r[1].strip() if len(r) > 1 else "",
                "words": int(r[2]) if r[2].strip().isdigit() else 0,
            })
    return rows


def split_blocks(md_text: str) -> list[str]:
    """把 book.md 切成全部 `## ` 块（去头部），保持顺序。

    **不能按 `---` 切**：正文里大量用 `---` 做分场线。
    也**不能把每个 `## ` 都当章节**：正文小节也用 `## `
    （第04卷第十九话的「一/二/三」、月刊的「## 篇名」）。
    所以这里只负责机械切块，真正的章节边界由 collect_volume
    用**目录标题做锚点**来定。
    """
    lines = md_text.splitlines()
    start = 0
    seen_toc = False
    for i, line in enumerate(lines):
        if line.strip() == "## 目录":
            seen_toc = True
            continue
        if seen_toc and line.startswith("## "):
            start = i
            break
    if not seen_toc:
        for i, line in enumerate(lines):
            if line.startswith("## ") and i > 0:
                start = i
                break

    blocks: list[str] = []
    cur: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ") and cur:
            blocks.append("\n".join(cur).strip())
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


# 常见繁简同字对（仅用于标题锚点匹配，不做全文转换）。
# 实测第15卷番外集：stats.csv 写「前日譚」（繁），book.md 块首是「前日谭」（简），
# 逐字比较失败导致锚点匹配整体放弃。这里把两侧都归一到简体侧再比。
TS_MAP = str.maketrans({
    "譚": "谭", "傳": "传", "話": "话", "卷": "卷", "衛": "卫", "風": "风",
    "戶": "户", "瀨": "濑", "齣": "出", "週": "周", "實": "实", "驗": "验",
})


def _norm_title(s: str) -> str:
    """标题规范化：去空白、间隔号、破折号，繁简归一，便于锚点匹配。"""
    s = (s or "").translate(TS_MAP)
    return re.sub(r"[\s\u3000·・\-—－―]+", "", s)


def _block_head(block: str) -> str:
    first = block.splitlines()[0] if block.splitlines() else ""
    return re.sub(r"^#+\s*", "", first).strip()


def anchor_blocks(toc: list[str], blocks: list[str]) -> list[int] | None:
    """目录第 N 项标题 -> 正文块序号。找不到就返回 None。

    目录行格式（assemble.py）：`- 第 71 话 · 第71話`，
    `·` 之后才是 draft 的标题；块首 `## 标题` 与它应一致。
    顺序扫描：每个锚点从上一个锚点之后找，防串位。
    """
    anchors = []
    for label in toc:
        title = label.split("·", 1)[1].strip() if "·" in label else label
        anchors.append(_norm_title(title))
    found: list[int] = []
    bi = 0
    for a in anchors:
        hit = None
        for j in range(bi, len(blocks)):
            head = _norm_title(_block_head(blocks[j]))
            if a and (a == head or a in head or head in a):
                hit = j
                break
        if hit is None:
            return None
        found.append(hit)
        bi = hit + 1
    return found


def toc_titles(md_text: str) -> list[str]:
    """从目录区抽标题列表（- 第 N 话 · 标题）。"""
    out = []
    lines = md_text.splitlines()
    in_toc = False
    for line in lines:
        if line.strip() == "## 目录":
            in_toc = True
            continue
        if in_toc:
            if line.startswith("## "):
                break
            m = re.match(r"^-\s+(.+)$", line)
            if m:
                out.append(m.group(1).strip())
    return out


def collect_volume(book_dir: str) -> tuple[list[dict], list[str]]:
    """一卷 -> (话列表, problems)。块序对齐 stats.csv 行序。"""
    name = os.path.basename(book_dir)
    rows = load_stats(book_dir)
    if not rows:
        return [], [f"{name}: 没有 stats.csv 或内容为空"]
    md_path = os.path.join(book_dir, "book.md")
    if not os.path.isfile(md_path):
        return [], [f"{name}: 没有 book.md"]
    md_text = open(md_path, encoding="utf-8").read()
    blocks = split_blocks(md_text)
    toc = toc_titles(md_text)

    problems: list[str] = []

    # 用目录标题做锚点定章节边界；锚点之间的块（含正文小节）归该话
    hits = anchor_blocks(toc, blocks)
    if hits is None:
        # 锚点失败再退回块数对齐
        if len(blocks) != len(rows):
            problems.append(
                f"{name}: 目录锚点匹配失败，且 book.md 切出 {len(blocks)} 块 "
                f"与 stats.csv {len(rows)} 行对不上")
            return [], problems
        spans = [(i, i) for i in range(len(rows))]
    else:
        spans = []
        for i in range(len(hits)):
            s = hits[i]
            e = hits[i + 1] - 1 if i + 1 < len(hits) else len(blocks) - 1
            spans.append((s, e))
        if len(spans) != len(rows):
            problems.append(
                f"{name}: 锚点定出 {len(spans)} 个章节，stats.csv 有 {len(rows)} 行，对不上")
            return [], problems

    out = []
    for (s, e), r in zip(spans, rows):
        body = "\n\n".join(blocks[s:e + 1])
        toc_label = toc[len(out)] if len(out) < len(toc) else r["title"]
        out.append({
            "chapter": r["chapter"],
            "title": r["title"] or toc_label,
            "words": r["words"],
            "volume": name,
            "body": body,
            "toc_label": toc_label,
        })
    return out, problems


def collect_all(books_dirs: list[str]) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    by_key: dict[float, dict] = {}
    for d in books_dirs:
        for book in list_dirs(d):
            name = os.path.basename(book)
            if not re.search(r"卷|集|番外", name):
                continue
            chs, probs = collect_volume(book)
            problems.extend(probs)
            for c in chs:
                try:
                    key = float(c["chapter"])
                except ValueError:
                    key = 9999.0
                if key in by_key:
                    prev = by_key[key]
                    if prev["volume"] == c["volume"]:
                        # 同卷同话号 = 前篇/续篇分章，正文合并而非丢弃
                        prev["body"] = prev["body"].rstrip() + "\n\n---\n\n" + c["body"]
                        prev["words"] += c["words"]
                        prev["title"] = prev["title"] if prev["title"] else c["title"]
                    else:
                        problems.append(
                            f"第{c['chapter']}话跨卷重复出书：{prev['volume']} 与 {c['volume']}")
                        if c["words"] > prev["words"]:
                            by_key[key] = c
                else:
                    by_key[key] = c
    ordered = [by_key[k] for k in sorted(by_key)]
    return ordered, problems


def write_merged_md(chapters: list[dict], out_path: str, title: str) -> str:
    lines = [f"# {title}", "", "## 目录", ""]
    for c in chapters:
        lines.append(f"- 第{c['chapter']}话 · {c['title']}")
    lines += ["", ""]
    for c in chapters:
        lines.append(f"## 第{c['chapter']}话 {c['title']}")
        lines.append("")
        body = re.sub(r"^##\s+.+?\s*$", "", c["body"], count=1, flags=re.M).strip()
        lines.append(body)
        lines.append("")
        lines.append("---")
        lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out_path


def write_merged_docx(chapters: list[dict], out_path: str, title: str) -> str | None:
    try:
        import docx
        from docx.shared import Pt
    except ImportError:
        return None
    doc = docx.Document()
    doc.add_heading(title, level=0)
    doc.add_heading("目录", level=1)
    for c in chapters:
        doc.add_paragraph(f"第{c['chapter']}话 · {c['title']}")
    for c in chapters:
        doc.add_page_break()
        doc.add_heading(f"第{c['chapter']}话 {c['title']}", level=1)
        body = re.sub(r"^##\s+.+?\s*$", "", c["body"], count=1, flags=re.M)
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if not p:
                continue
            if p.strip("◇ "):
                doc.add_paragraph(p).paragraph_format.first_line_indent = Pt(24)
            else:
                doc.add_paragraph("◇")
    doc.save(out_path)
    return out_path


def write_merged_epub(chapters: list[dict], out_path: str, title: str) -> str:
    import epub_writer as epub
    ch = []
    for c in chapters:
        body = re.sub(r"^##\s+.+?\s*$", "", c["body"], count=1, flags=re.M)
        html = []
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if not p:
                continue
            txt = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if p.strip("◇ "):
                html.append(f"<p>{txt}</p>")
            else:
                html.append("<p class='brk'>◇</p>")
        ch.append({"title": f"第{c['chapter']}话 {c['title']}", "html": "".join(html)})
    return epub.build_epub(ch, out_path, title, cover_png=None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全本合并：各卷 -> 一部完整小说")
    ap.add_argument("--books", required=True, nargs="+",
                    help="出书目录（可给多个，例如 小説 小说）")
    ap.add_argument("--out", required=True, help="输出 .md 文件路径，或 --formats 多格式时的目录")
    ap.add_argument("--title", default="全本")
    ap.add_argument("--formats", nargs="*", default=["md"],
                    help="md docx epub（默认只 md；mobi 体量大不默认）")
    args = ap.parse_args(argv)

    chapters, problems = collect_all(args.books)
    total_words = sum(c["words"] for c in chapters)

    report = {
        "chapters": len(chapters),
        "words": total_words,
        "chapter_range": f"{chapters[0]['chapter']}-{chapters[-1]['chapter']}" if chapters else "",
        "problems": problems,
    }
    if problems:
        report["error"] = "对账有问题，拒绝合并（先修卷内对不上的书）"
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1

    out = args.out
    made = {}
    if args.formats == ["md"]:
        path = out if out.lower().endswith(".md") else os.path.join(out, "全本.md")
        made["md"] = write_merged_md(chapters, path, args.title)
    else:
        os.makedirs(out, exist_ok=True)
        if "md" in args.formats:
            made["md"] = write_merged_md(chapters, os.path.join(out, "全本.md"), args.title)
        if "docx" in args.formats:
            p = write_merged_docx(chapters, os.path.join(out, "全本.docx"), args.title)
            made["docx"] = p or "skipped (pip install python-docx)"
        if "epub" in args.formats:
            made["epub"] = write_merged_epub(chapters, os.path.join(out, "全本.epub"), args.title)

    report["ok"] = True
    report["files"] = made
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
