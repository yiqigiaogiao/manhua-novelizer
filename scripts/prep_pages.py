# -*- coding: utf-8 -*-
"""S1 拆页：PDF → 页图（jpg/png），长条页切片，低清放大，并负责清理。"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import pymupdf
from PIL import Image


def save_image(img: Image.Image, path: str, fmt: str, quality: int = 92) -> None:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if fmt == "png":
        img.save(path, "PNG", optimize=True)
    else:
        img.save(path, "JPEG", quality=quality, subsampling=0)


def page_image(doc: pymupdf.Document, page: pymupdf.Page, dpi: int) -> tuple[Image.Image, str]:
    images = page.get_images(full=True)
    if len(images) == 1:
        info = doc.extract_image(images[0][0])
        try:
            img = Image.open(io.BytesIO(info["image"]))
            img.load()
            return img, "native"
        except Exception:
            pass
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("jpeg"))), f"render{dpi}"


def manifest_is_valid(manifest: dict, out_dir: str, source: str, params: dict) -> bool:
    """判断已有 pages.json 能否直接复用 —— 修复「只比 source」的三个硬伤：
    1. 不比图片哈希（图片被替换成新扫描件仍命中旧 manifest）
    2. 不比预处理参数（改 --min-width 后静默返回旧结果
    3. 不校验页图是否还在磁盘（clean_pages 删图后不重建 → S3 因缺图失败）

    判据 = source 一致 + 参数一致 + 所有切片文件都真实存在。
    """
    if manifest.get("source") != source:
        return False
    # 旧 manifest 无 params → 无法校验参数，保守重建
    if not manifest.get("params"):
        return False
    for key, want in params.items():
        if manifest["params"].get(key) != want:
            return False
    # 页图存在性
    for page in manifest.get("pages", []):
        for tile in page.get("tiles", []) or []:
            if not os.path.isfile(os.path.join(out_dir, tile["file"])):
                return False
    return True


def process(pdf_path: str, out_dir: str, min_width: int = 1100, tile_ratio: float = 2.6,
            overlap: float = 0.12, dpi: int = 200, quality: int = 92,
            limit: int | None = None, force: bool = False,
            first_page: int = 1, last_page: int | None = None,
            fmt: str = "jpg", renumber: bool = False) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "pages.json")
    params = {"min_width": min_width, "tile_ratio": tile_ratio, "overlap": overlap,
              "dpi": dpi, "quality": quality, "format": fmt}
    if os.path.exists(manifest_path) and not force:
        with open(manifest_path, encoding="utf-8") as fh:
            existing = json.load(fh)
        if manifest_is_valid(existing, out_dir, os.path.basename(pdf_path), params):
            return existing
    ext = ".png" if fmt == "png" else ".jpg"
    doc = pymupdf.open(pdf_path)
    total = doc.page_count
    start = max(1, first_page)
    end = min(last_page or total, total)
    selected = [(pno, doc[pno - 1]) for pno in range(start, end + 1)]
    if limit:
        selected = selected[:limit]

    manifest = {"source": os.path.basename(pdf_path), "range": [start, end],
                "format": fmt, "params": params, "pages": []}
    try:
        for index, (pno, page) in enumerate(selected, start=1):
            img, mode = page_image(doc, page, dpi)
            width, height = img.size
            if width < min_width:
                scale = min_width / width
                img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
                mode += "+upscale"
            width, height = img.size
            label = index if renumber else pno

            entry = {"page": pno, "label": label, "w": width, "h": height,
                     "mode": mode, "tiles": []}
            if height / max(width, 1) > tile_ratio:
                band = int(width * 1.55)
                step = max(1, int(band * (1 - overlap)))
                y, k = 0, 0
                while y < height:
                    k += 1
                    box = (0, y, width, min(y + band, height))
                    name = f"p{label:04d}_t{k}{ext}"
                    save_image(img.crop(box), os.path.join(out_dir, name), fmt, quality)
                    entry["tiles"].append({"file": name, "y0": y, "y1": box[3]})
                    if box[3] >= height:
                        break
                    y += step
            else:
                name = f"p{label:04d}{ext}"
                save_image(img, os.path.join(out_dir, name), fmt, quality)
                entry["tiles"].append({"file": name, "y0": 0, "y1": height})
            manifest["pages"].append(entry)
    finally:
        doc.close()

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    return manifest


def cleanup(work_dir: str, dry_run: bool = False, keep: str | None = None) -> dict:
    """删除中间页图（jpg/png）与空目录，保留正文与 JSON。

    keep: 可选，保留某个子路径（如 ch001/pages）不删。
    """
    removed, freed = 0, 0
    kept = 0
    for root, dirs, files in os.walk(work_dir):
        if keep and os.path.abspath(root).startswith(os.path.abspath(keep)):
            kept += len([f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))])
            continue
        for name in files:
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            path = os.path.join(root, name)
            size = os.path.getsize(path)
            if not dry_run:
                os.remove(path)
            removed += 1
            freed += size
    for root, dirs, files in os.walk(work_dir, topdown=False):
        if os.path.basename(root) == "pages" and not os.listdir(root):
            if not dry_run:
                os.rmdir(root)
    return {"removed": removed, "freed_mb": round(freed / 1048576, 1),
            "kept": kept, "dry_run": dry_run}


def process_images(src_dir: str, out_dir: str, min_width: int = 1100,
                   tile_ratio: float = 2.6, overlap: float = 0.12,
                   quality: int = 92, limit: int | None = None,
                   force: bool = False, fmt: str = "jpg",
                   split_spread: bool = False, direction: str = "ltr") -> dict:
    """图片目录 → 规范化页图（按文件名自然排序）。

    split_spread: 把横长的双页扫描拆成左右两半。
    direction:    rtl 时右半页先读，ltr 时左半页先读。
    """
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "pages.json")
    if os.path.exists(manifest_path) and not force:
        with open(manifest_path, encoding="utf-8") as fh:
            existing = json.load(fh)
        if existing.get("source") == os.path.abspath(src_dir):
            return existing

    import re

    def natural(name: str):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]

    files = [f for f in os.listdir(src_dir)
             if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    files.sort(key=natural)
    if limit:
        files = files[:limit]

    ext = ".png" if fmt == "png" else ".jpg"
    manifest = {"source": os.path.abspath(src_dir), "mode": "images", "format": fmt,
                "split_spread": split_spread, "direction": direction, "pages": []}
    counter = 0

    def emit(img, source, half, page_no):
        nonlocal counter
        counter += 1
        width, height = img.size
        mode = "native"
        if width < min_width:
            scale = min_width / width
            img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
            mode = "upscale"
        width, height = img.size
        entry = {"page": page_no, "source": source, "half": half,
                 "w": width, "h": height, "mode": mode, "tiles": []}
        if height / max(width, 1) > tile_ratio:
            band = int(width * 1.55)
            step = max(1, int(band * (1 - overlap)))
            y, k = 0, 0
            while y < height:
                k += 1
                box = (0, y, width, min(y + band, height))
                out_name = f"p{page_no:04d}_t{k}{ext}"
                save_image(img.crop(box), os.path.join(out_dir, out_name), fmt, quality)
                entry["tiles"].append({"file": out_name, "y0": y, "y1": box[3]})
                if box[3] >= height:
                    break
                y += step
        else:
            out_name = f"p{page_no:04d}{ext}"
            save_image(img, os.path.join(out_dir, out_name), fmt, quality)
            entry["tiles"].append({"file": out_name, "y0": 0, "y1": height})
        manifest["pages"].append(entry)
        return counter

    for name in files:
        img = Image.open(os.path.join(src_dir, name))
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if split_spread and w / max(h, 1) > 1.15:
            left = img.crop((0, 0, w // 2, h))
            right = img.crop((w // 2, 0, w, h))
            halves = [("right", right), ("left", left)] if direction == "rtl" else \
                     [("left", left), ("right", right)]
            for half, part in halves:
                emit(part, name, half, counter + 1)
        else:
            emit(img, name, "full", counter + 1)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PDF / 图片目录 → 规范化页图")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="PDF 文件")
    src.add_argument("--images", help="图片目录")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-width", type=int, default=1100)
    ap.add_argument("--tile-ratio", type=float, default=2.6)
    ap.add_argument("--overlap", type=float, default=0.12)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--first-page", type=int, default=1)
    ap.add_argument("--last-page", type=int, default=None)
    ap.add_argument("--format", choices=["jpg", "png"], default="jpg")
    ap.add_argument("--renumber", action="store_true")
    ap.add_argument("--split-spread", action="store_true",
                    help="双页扫描拆成左右两半")
    ap.add_argument("--direction", choices=["ltr", "rtl"], default="ltr",
                    help="拆跨页后哪半先读")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.pdf:
        if not os.path.isfile(args.pdf):
            ap.error(f"no such file: {args.pdf}")
        manifest = process(args.pdf, args.out, args.min_width, args.tile_ratio,
                           max(0.0, min(0.4, args.overlap)), args.dpi, args.quality,
                           args.limit, args.force, args.first_page, args.last_page,
                           args.format, args.renumber)
    else:
        if not os.path.isdir(args.images):
            ap.error(f"no such directory: {args.images}")
        manifest = process_images(args.images, args.out, args.min_width, args.tile_ratio,
                                  max(0.0, min(0.4, args.overlap)), args.quality,
                                  args.limit, args.force, args.format,
                                  args.split_spread, args.direction)

    tiles = sum(len(p["tiles"]) for p in manifest["pages"])
    print(json.dumps({"pages": len(manifest["pages"]), "tiles": tiles,
                      "format": args.format, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
