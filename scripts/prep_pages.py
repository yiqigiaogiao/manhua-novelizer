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


def process(pdf_path: str, out_dir: str, min_width: int = 1100, tile_ratio: float = 2.6,
            overlap: float = 0.12, dpi: int = 200, quality: int = 92,
            limit: int | None = None, force: bool = False,
            first_page: int = 1, last_page: int | None = None,
            fmt: str = "jpg", renumber: bool = False) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "pages.json")
    if os.path.exists(manifest_path) and not force:
        with open(manifest_path, encoding="utf-8") as fh:
            existing = json.load(fh)
        if existing.get("source") == os.path.basename(pdf_path):
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
                "format": fmt, "pages": []}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PDF 拆页")
    ap.add_argument("--pdf", required=True)
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
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pdf):
        ap.error(f"no such file: {args.pdf}")
    manifest = process(args.pdf, args.out, args.min_width, args.tile_ratio,
                       max(0.0, min(0.4, args.overlap)), args.dpi, args.quality,
                       args.limit, args.force, args.first_page, args.last_page,
                       args.format, args.renumber)
    tiles = sum(len(p["tiles"]) for p in manifest["pages"])
    print(json.dumps({"pages": len(manifest["pages"]), "tiles": tiles,
                      "format": args.format, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
