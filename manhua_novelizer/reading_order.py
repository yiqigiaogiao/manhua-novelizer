# -*- coding: utf-8 -*-
"""阅读顺序检测：从左往右（ltr）/ 从右往左（rtl）/ 竖屏条漫（ttb）。

不做"黑盒猜测"：给出方向的同时给出置信度和依据，用户可以一键覆盖。
依据两类信号：

1. 气泡文字的排布方向：竖排文字（日式漫画常见）→ rtl；横排 → ltr。
2. 首格气泡的横向位置：右起漫画的第一句台词通常偏右。
"""
from __future__ import annotations

import glob
import json
import os
from collections import deque

import numpy as np
from PIL import Image

MAX_SIDE = 320


def _components(mask: np.ndarray) -> list[dict]:
    """两遍扫描的连通域标记，返回面积合格的块的 bbox。"""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    boxes: list[dict] = []
    current = 0
    for y in range(h):
        row = mask[y]
        for x in range(w):
            if not row[x] or labels[y, x]:
                continue
            current += 1
            q = deque([(y, x)])
            labels[y, x] = current
            minx = maxx = x
            miny = maxy = y
            count = 0
            while q:
                cy, cx = q.popleft()
                count += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        q.append((ny, nx))
            boxes.append({"area": count, "x0": minx, "x1": maxx, "y0": miny, "y1": maxy})
    return boxes


def _bubble_stats(img: Image.Image) -> dict:
    """找纯白气泡，统计其位置与内部文字的排布方向。"""
    img = img.convert("RGB")
    w, h = img.size
    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)))
    a = np.asarray(img).astype(np.int16)
    white = (a[:, :, 0] >= 246) & (a[:, :, 1] >= 246) & (a[:, :, 2] >= 246)
    hh, ww = white.shape
    total = hh * ww

    boxes = _components(white)
    bubbles = []
    for b in boxes:
        bw = b["x1"] - b["x0"] + 1
        bh = b["y1"] - b["y0"] + 1
        area = b["area"]
        if area < total * 0.002 or area > total * 0.18:
            continue
        if bw < 8 or bh < 8:
            continue
        if bw / bh > 8 or bh / bw > 8:
            continue
        # 气泡内应有深色文字
        patch = a[b["y0"]:b["y1"] + 1, b["x0"]:b["x1"] + 1]
        dark = (patch[:, :, 0] < 90) & (patch[:, :, 1] < 90) & (patch[:, :, 2] < 90)
        if dark.mean() < 0.02:
            continue
        col_ink = dark.any(axis=0).sum()
        row_ink = dark.any(axis=1).sum()
        bubbles.append({
            "cx": (b["x0"] + b["x1"]) / 2 / ww,
            "cy": (b["y0"] + b["y1"]) / 2 / hh,
            "w": bw / ww,
            "h": bh / hh,
            "vertical_text": bool(row_ink >= col_ink * 1.6),
            "horizontal_text": bool(col_ink >= row_ink * 1.6),
        })
    return {"bubbles": bubbles, "aspect": hh / max(ww, 1)}


def detect(pages_dir: str, sample: int = 6) -> dict:
    files = sorted(glob.glob(os.path.join(pages_dir, "p*.[jp][pn]g")))
    if not files:
        return {"direction": "ltr", "confidence": 0.0,
                "reason": "没有找到页图", "evidence": {}}
    picks = files[:sample]

    vertical = horizontal = 0
    cx_values = []
    aspects = []
    used = 0
    for path in picks:
        try:
            img = Image.open(path)
            img.load()
        except OSError:
            continue
        stats = _bubble_stats(img)
        used += 1
        aspects.append(stats["aspect"])
        for b in stats["bubbles"]:
            if b["vertical_text"]:
                vertical += 1
            elif b["horizontal_text"]:
                horizontal += 1
            if b["cy"] < 0.45:            # 只看上半页（先读的区域）
                cx_values.append(b["cx"])

    tall = float(np.median(aspects)) if aspects else 1.0
    if tall > 2.6:
        return {"direction": "ttb", "confidence": 0.8,
                "reason": "页面为长条（高/宽 > 2.6），按纵向滚动阅读",
                "evidence": {"pages": used, "aspect": round(tall, 2)}}

    text_total = vertical + horizontal
    v_ratio = vertical / text_total if text_total else 0.0
    right_bias = float(np.mean([c > 0.5 for c in cx_values])) if cx_values else 0.5

    # 竖排文字是右起漫画的强信号；横排文字 + 气泡偏左是左起信号
    score = 0.0
    if text_total >= 3:
        score += (v_ratio - 0.5) * 1.4
    score += (right_bias - 0.5) * 0.8

    if score > 0.08:
        direction = "rtl"
    elif score < -0.08:
        direction = "ltr"
    else:
        direction = "ltr"
    confidence = round(min(1.0, abs(score) * 2.2 + (0.25 if text_total >= 3 else 0.0)), 2)

    return {
        "direction": direction,
        "confidence": confidence,
        "reason": (f"竖排气泡 {vertical} / 横排气泡 {horizontal}；"
                   f"上半页气泡偏右比例 {right_bias:.0%}；采样 {used} 页"),
        "evidence": {"vertical_bubbles": vertical, "horizontal_bubbles": horizontal,
                     "first_row_right_bias": round(right_bias, 2),
                     "pages": used, "aspect": round(tall, 2)},
    }


def apply(work_dir: str, direction: str) -> str:
    from . import config
    cfg = config.load_config(work_dir)
    cfg.setdefault("work", {})["reading_direction"] = direction
    config.save_config(work_dir, cfg)
    return os.path.join(work_dir, "config.json")
