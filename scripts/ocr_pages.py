# -*- coding: utf-8 -*-
"""用本地 OCR 提取页面对白（廉价转录，不消耗视觉 token）。

依赖二选一：
    pip install rapidocr-onnxruntime     # 轻量 ONNX，推荐
    pip install paddleocr paddlepaddle   # 精度更高，体积大

用法：
    python ocr_pages.py --pages work/ch001/pages --out work/ch001/ocr.json --direction rtl
    python ocr_pages.py --pages ... --out ... --engine paddle --min-conf 0.6

输出：
{"pages":[{"page":1,"coverage":0.18,"lines":[{"text":"…","bbox":[x0,y0,x1,y1],"conf":0.93}]}]}
bbox 为归一化坐标；行按阅读顺序排序（rtl 时同一行先右后左）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys


def load_engine(name: str):
    if name == "rapidocr":
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise SystemExit(
                "未安装 rapidocr-onnxruntime。\n"
                "  pip install rapidocr-onnxruntime\n"
                "或改用 --engine paddle（需 paddleocr + paddlepaddle）"
            ) from exc
        return RapidOCR()

    if name == "paddle":
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise SystemExit(
                "未安装 paddleocr。\n  pip install paddleocr paddlepaddle"
            ) from exc
        return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    raise SystemExit(f"未知引擎：{name}")


def run_rapidocr(engine, path: str):
    result, _ = engine(path)
    lines = []
    for item in result or []:
        box, text, conf = item[0], item[1], item[2]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append({"text": text, "conf": float(conf),
                      "bbox": [min(xs), min(ys), max(xs), max(ys)]})
    return lines


def run_paddle(engine, path: str):
    result = engine.ocr(path, cls=True)
    lines = []
    for page in result or []:
        for item in page or []:
            box, (text, conf) = item
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append({"text": text, "conf": float(conf),
                          "bbox": [min(xs), min(ys), max(xs), max(ys)]})
    return lines


def normalize_and_sort(lines, width: int, height: int, direction: str, min_conf: float):
    out = []
    for line in lines:
        if line["conf"] < min_conf:
            continue
        x0, y0, x1, y1 = line["bbox"]
        out.append({"text": line["text"], "conf": round(line["conf"], 3),
                    "bbox": [round(x0 / width, 3), round(y0 / height, 3),
                             round(x1 / width, 3), round(y1 / height, 3)]})
    # 按行聚类：y 中心相近视为同一行
    out.sort(key=lambda l: (l["bbox"][1] + l["bbox"][3]) / 2)
    rows, current = [], []
    for line in out:
        cy = (line["bbox"][1] + line["bbox"][3]) / 2
        if not current:
            current = [line]
            continue
        prev_cy = (current[0]["bbox"][1] + current[0]["bbox"][3]) / 2
        if abs(cy - prev_cy) < 0.04:
            current.append(line)
        else:
            rows.append(current)
            current = [line]
    if current:
        rows.append(current)
    ordered = []
    for row in rows:
        row.sort(key=lambda l: l["bbox"][0], reverse=(direction == "rtl"))
        ordered.extend(row)
    return ordered


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="本地 OCR 提取对白（廉价转录）")
    ap.add_argument("--pages", required=True, help="页图目录")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", choices=["rapidocr", "paddle"], default="rapidocr")
    ap.add_argument("--direction", choices=["ltr", "rtl"], default="ltr")
    ap.add_argument("--min-conf", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.pages, "p*.[jJ][pP][gG]")))
    files += sorted(glob.glob(os.path.join(args.pages, "p*.[pP][nN][gG]")))
    files = sorted(set(files), key=lambda p: os.path.basename(p))
    if args.limit:
        files = files[: args.limit]
    if not files:
        ap.error(f"没有页图：{args.pages}")

    engine = load_engine(args.engine)
    from PIL import Image

    pages = []
    for path in files:
        with Image.open(path) as img:
            width, height = img.size
        raw = run_rapidocr(engine, path) if args.engine == "rapidocr" else run_paddle(engine, path)
        lines = normalize_and_sort(raw, width, height, args.direction, args.min_conf)
        area = sum((l["bbox"][2] - l["bbox"][0]) * (l["bbox"][3] - l["bbox"][1]) for l in lines)
        pages.append({"page": int(os.path.basename(path)[1:5]), "coverage": round(min(area, 1.0), 3),
                      "lines": lines})
        print(f"{os.path.basename(path)} lines={len(lines)} coverage={pages[-1]['coverage']}",
              file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"pages": pages, "engine": args.engine, "direction": args.direction},
                  fh, ensure_ascii=False, indent=1)
    print(json.dumps({"pages": len(pages), "out": args.out,
                      "avg_coverage": round(sum(p["coverage"] for p in pages) / max(len(pages), 1), 3)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
