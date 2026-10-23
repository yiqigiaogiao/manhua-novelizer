# -*- coding: utf-8 -*-
"""原作叙事风格配置：八个维度，可编辑、可版本化、需用户确认。

配置文件默认位于 <work>/style.json，结构见 references/style-config.md。
每次修改都会把上一版快照到 <work>/style_history/style.vN.json，
便于比较"改风格前后"的差异。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from typing import Any

# 确保同目录模块可被 import（被当模块 import 时脚本目录不会自动进 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DIMENSIONS = [
    ("rhythm", "叙事节奏"),
    ("emotion", "情绪表达方式"),
    ("dialogue", "对白特征"),
    ("visual", "画面转译方式"),
    ("reveal", "信息揭示策略"),
    ("density", "段落与描写密度"),
    ("signature", "作品特有的表达习惯"),
    ("forbidden", "禁止破坏的特征"),
]

EMPTY_STYLE: dict[str, Any] = {
    "version": 1,
    "confirmed": False,
    "source": "",
    "updated_at": "",
    "dimensions": {
        key: {"label": label, "summary": "", "evidence": [], "status": "尚未确认"}
        for key, label in DIMENSIONS
    },
}


def style_path(work_dir: str) -> str:
    return os.path.join(work_dir, "style.json")


def load_style(work_dir: str) -> dict:
    path = style_path(work_dir)
    if not os.path.isfile(path):
        return json.loads(json.dumps(EMPTY_STYLE))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    merged = json.loads(json.dumps(EMPTY_STYLE))
    merged.update({k: v for k, v in data.items() if k != "dimensions"})
    for key, _ in DIMENSIONS:
        item = (data.get("dimensions") or {}).get(key)
        if item:
            merged["dimensions"][key].update(item)
    return merged


def save_style(work_dir: str, style: dict, snapshot: bool = True) -> str:
    path = style_path(work_dir)
    if snapshot and os.path.isfile(path):
        _snapshot(work_dir)
    style["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(style, fh, ensure_ascii=False, indent=2)
    return path


def _snapshot(work_dir: str) -> str:
    hist = os.path.join(work_dir, "style_history")
    os.makedirs(hist, exist_ok=True)
    existing = [f for f in os.listdir(hist) if f.startswith("style.v")]
    index = len(existing) + 1
    dst = os.path.join(hist, f"style.v{index}.json")
    shutil.copy2(style_path(work_dir), dst)
    return dst


def pending_dimensions(style: dict) -> list[str]:
    """尚未确认或内容为空的维度。"""
    out = []
    for key, _ in DIMENSIONS:
        item = style["dimensions"].get(key) or {}
        if item.get("status") == "尚未确认" or not item.get("summary"):
            out.append(key)
    return out


def render_markdown(style: dict) -> str:
    """把风格配置渲染成可读的 Markdown，供写作 agent 直接读取。"""
    lines = ["# 原作叙事风格配置", ""]
    lines.append(f"- 版本：v{style.get('version', 1)}")
    lines.append(f"- 用户确认：{'是' if style.get('confirmed') else '否（未确认前不要开始批量写作）'}")
    if style.get("source"):
        lines.append(f"- 依据：{style['source']}")
    lines.append("")
    for key, label in DIMENSIONS:
        item = style["dimensions"].get(key) or {}
        lines.append(f"## {label}（`{key}`）")
        lines.append("")
        lines.append(item.get("summary") or "（尚未确认）")
        evidence = item.get("evidence") or []
        if evidence:
            lines.append("")
            lines.append("依据：")
            for ev in evidence:
                lines.append(f"- {ev}")
        lines.append("")
    lines.append("> 使用方法：逐场判断，不要把配置机械套到每个段落。")
    lines.append("> 整体偏慢的作品，战斗场仍应快；常用留白的作品，也不是每场都要留白。")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="叙事风格配置")
    ap.add_argument("--work", default="work")
    ap.add_argument("--action", choices=["init", "show", "render", "confirm", "check"],
                    default="show")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.action == "init":
        import _shared
        _shared.init_work(args.work)
        st = load_style(args.work)
        if not __import__("os").path.isfile(style_path(args.work)):
            save_style(args.work, st, snapshot=False)
        print(json.dumps({"style": style_path(args.work), "dimensions": len(DIMENSIONS)},
                         ensure_ascii=False, indent=1))
        return 0

    st = load_style(args.work)
    if args.action == "render":
        out = args.out or __import__("os").path.join(args.work, "style.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(st))
        print(json.dumps({"rendered": out}, ensure_ascii=False))
        return 0
    if args.action == "confirm":
        st["confirmed"] = True
        print(json.dumps({"saved": save_style(args.work, st), "confirmed": True},
                         ensure_ascii=False))
        return 0
    if args.action == "check":
        pending = pending_dimensions(st)
        print(json.dumps({"pending": pending, "confirmed": st.get("confirmed", False)},
                         ensure_ascii=False, indent=1))
        return 0 if (st.get("confirmed") and not pending) else 1
    print(json.dumps(st, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
