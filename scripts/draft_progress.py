# -*- coding: utf-8 -*-
"""S5 正文写作的分段自愈编排（对应 S3 的 transcribe_progress.py）。

为什么需要这个
--------------
S3 早就改成"小段 + 单页落盘 + 文件验收 + 双层重试"了，但 S5 写正文仍然
**一话一个 draft.md**：agent 写一半挂掉，磁盘上就留半截稿，而半截稿
和完成稿长得一模一样——`check_ready.py` 的静置检查只按 mtime 判，
根本分不出"写完了"和"写到一半断了"。

实测：几百话批量时，S5 是比 S3 更大的失败面。所以照搬 S3 的模式：

1. **按场景分段**：`outline.json` 的 `scenes[]` 每场一段，一段一个文件
   `draft_seg_001.md`、`draft_seg_002.md`……
2. **写完一段就落盘**：中断只丢当前这一段，前面全在。
3. **以文件为验收**：重跑扫磁盘已存在的段，只跑缺失的。
4. **合并成稿**：所有段齐了才拼回 `draft.md`（**原子写**：先写临时文件
   再 `os.replace`，避免半截稿被当成完成稿）。

用法
----
    # 看写到哪了、缺哪几段（自愈的输入）
    python scripts/draft_progress.py --work work --ch ch001

    # 所有段齐了就合并成 draft.md（原子写）
    python scripts/draft_progress.py --work work --ch ch001 --merge

    # 全量扫一遍，给批量编排用
    python scripts/draft_progress.py --work work

段文件的约定
------------
- `draft_seg_001.md` 起编，与 `outline.json` 的 `scenes` 下标一一对应
  （第 1 段 = scenes[0]）。
- 段文件**只放正文**，不放 front matter、不放一级标题——front matter 和
  `# 标题` 由合并步骤统一加，避免每个 agent 各写一份格式不同的头。
- 段文件为空或只有空白 = 视为缺失（agent 建了文件却没内容，不能算完成）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEG_PREFIX = "draft_seg_"
SEG_SUFFIX = ".md"
MIN_SEG_CHARS = 1          # 少于这个字数就当作没写


def seg_name(index: int) -> str:
    """1 起编号，补零到 3 位：draft_seg_001.md"""
    return f"{SEG_PREFIX}{index:03d}{SEG_SUFFIX}"


def seg_index(path: str) -> int | None:
    m = re.search(rf"{SEG_PREFIX}(\d+){re.escape(SEG_SUFFIX)}$",
                  os.path.basename(path))
    return int(m.group(1)) if m else None


def chapter_dir(work: str, ch: str) -> str:
    return os.path.join(work, ch)


def expected_scenes(folder: str) -> int:
    """本话该有几段：以 outline.json 的 scenes 为准。

    没有 outline.json 时退回 1（整话一段）——至少保证"原子写"这一层还在。
    """
    path = os.path.join(folder, "outline.json")
    if not os.path.isfile(path):
        return 1
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 1
    scenes = data.get("scenes")
    if isinstance(scenes, list) and scenes:
        return len(scenes)
    return 1


def existing_segments(folder: str) -> dict[int, str]:
    """已落盘的段 -> {index: path}。空文件不算。"""
    out: dict[int, str] = {}
    for path in glob.glob(os.path.join(folder, f"{SEG_PREFIX}*{SEG_SUFFIX}")):
        idx = seg_index(path)
        if idx is None:
            continue
        try:
            with open(path, encoding="utf-8-sig") as fh:
                body = fh.read().strip()
        except OSError:
            continue
        if len(body) < MIN_SEG_CHARS:
            continue
        out[idx] = path
    return out


def chapter_status(folder: str) -> dict:
    total = expected_scenes(folder)
    have = existing_segments(folder)
    missing = [i for i in range(1, total + 1) if i not in have]
    return {
        "chapter": os.path.basename(folder),
        "total": total,
        "done": len([i for i in have if i <= total]),
        "missing": missing,
        "segments": sorted(have),
        "draft_exists": os.path.isfile(os.path.join(folder, "draft.md")),
    }


def scan(work: str, only: str | None = None) -> dict:
    """扫所有 ch* 目录，返回每话的段进度。"""
    report: dict[str, dict] = {}
    for folder in sorted(glob.glob(os.path.join(work, "ch[0-9][0-9][0-9]"))):
        name = os.path.basename(folder)
        if only and name != only:
            continue
        if not os.path.isdir(folder):
            continue
        report[name] = chapter_status(folder)
    return report


def _read_seg(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read().strip()


def _front_matter(folder: str, ch_number: str | None) -> str:
    """从 outline.json 生成 draft.md 的 front matter。

    话号/标题优先取 outline.json，其次取目录名 chNNN。
    """
    chapter, title, scenes = ch_number, "", []
    path = os.path.join(folder, "outline.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
            chapter = data.get("chapter", chapter)
            title = (data.get("title") or "").strip()
            scenes = [s.get("place", "") for s in (data.get("scenes") or [])
                      if isinstance(s, dict)]
        except (OSError, json.JSONDecodeError):
            pass
    if chapter is None:
        m = re.search(r"ch(\d+)", os.path.basename(folder))
        chapter = int(m.group(1)) if m else ""
    scene_list = "[" + ", ".join(s for s in scenes if s) + "]"
    lines = ["---", f"话: {chapter}", f"标题: {title}", f"场景: {scene_list}",
             "人物: []", "---", "", f"# {title or f'第{chapter}话'}", ""]
    return "\n".join(lines)


def merge_chapter(work: str, ch: str, force: bool = False) -> dict:
    """所有段齐了才拼 draft.md（原子写：临时文件 -> os.replace）。"""
    folder = chapter_dir(work, ch)
    if not os.path.isdir(folder):
        return {"error": f"没有目录 {folder}"}
    status = chapter_status(folder)
    if status["missing"]:
        return {"error": "段落不齐，拒绝合并（半截稿不能当完成稿）",
                "missing": status["missing"], "total": status["total"],
                "done": status["done"]}

    have = existing_segments(folder)
    bodies = [_read_seg(have[i]) for i in range(1, status["total"] + 1)]
    body = "\n\n".join(b for b in bodies if b)

    draft_path = os.path.join(folder, "draft.md")
    if os.path.isfile(draft_path) and not force:
        # 已有 draft.md 时，若它比所有段都新，可能是人工改过——先别覆盖
        newest_seg = max(os.path.getmtime(p) for p in have.values())
        if os.path.getmtime(draft_path) > newest_seg:
            return {"skipped": "draft.md 比所有段都新，可能已人工改过；"
                               "确认要覆盖请加 --force",
                    "draft": draft_path, "segments": status["total"]}

    text = _front_matter(folder, None) + "\n" + body + "\n"

    # 原子写：同目录临时文件 -> os.replace，避免半截稿被当成完成稿
    fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=".draft.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, draft_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {"merged": draft_path, "segments": status["total"],
            "words": len(re.findall(r"[\u4e00-\u9fff]", body)),
            "atomic": True}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S5 分段写作进度与合并（自愈）")
    ap.add_argument("--work", default=".", help="work 目录")
    ap.add_argument("--ch", default=None, help="只处理某一话，如 ch001")
    ap.add_argument("--merge", action="store_true",
                    help="段落齐了就合并成 draft.md（原子写）")
    ap.add_argument("--force", action="store_true",
                    help="draft.md 比段新时也覆盖（默认跳过）")
    args = ap.parse_args(argv)

    if args.merge:
        if not args.ch:
            ap.error("--merge 需要 --ch")
        result = merge_chapter(args.work, args.ch, args.force)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1 if result.get("error") else 0

    rep = scan(args.work, args.ch)
    if args.ch and not rep:
        print(json.dumps({"error": f"{args.work} 下没有 {args.ch}"},
                         ensure_ascii=False))
        return 1
    done = sum(v["done"] for v in rep.values())
    total = sum(v["total"] for v in rep.values())
    print(json.dumps({
        "chapters": len(rep),
        "segments_done": done,
        "segments_total": total,
        "pct": round(100 * done / total, 1) if total else 0,
        "chapters_incomplete": {k: v["missing"] for k, v in rep.items() if v["missing"]},
        "detail": rep,
    }, ensure_ascii=False, indent=1))
    return 0 if done == total else 1


if __name__ == "__main__":
    sys.exit(main())
