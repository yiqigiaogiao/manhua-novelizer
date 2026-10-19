#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S1 - turn a comic PDF into page images ready for a vision model.

* extracts the embedded JPEG when possible (no recompression -> text stays sharp)
* falls back to rendering at --dpi for vector / multi-image pages
* upscales narrow pages (default: anything below 1100 px wide)
* slices extreme long-strip pages into overlapping bands

Usage:
    python prep_pages.py --pdf "pdf/001.pdf" --out work/ch001/pages
    python prep_pages.py --pdf 001.pdf --out pages --limit 3 --force
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import pymupdf
from PIL import Image


def save_jpeg(img: Image.Image, path: str, quality: int = 92) -> None:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(path, "JPEG", quality=quality, subsampling=0)


def page_image(doc: pymupdf.Document, page: pymupdf.Page, dpi: int) -> tuple[Image.Image, str]:
    """Return the page as a PIL image, preferring the embedded JPEG."""
    images = page.get_images(full=True)
    if len(images) == 1:
        info = doc.extract_image(images[0][0])
        try:
            img = Image.open(io.BytesIO(info["image"]))
            img.load()
            return img, "native"
        except Exception:  # corrupt stream -> render instead
            pass
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("jpeg"))), f"render{dpi}"


def process(pdf_path: str, out_dir: str, min_width: int, tile_ratio: float,
            overlap: float, dpi: int, quality: int, limit: int | None,
            force: bool, first_page: int = 1, last_page: int | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "pages.json")
    if os.path.exists(manifest_path) and not force:
        with open(manifest_path, encoding="utf-8") as fh:
            existing = json.load(fh)
        if existing.get("source") == os.path.basename(pdf_path):
            print(json.dumps({"skipped": True, "out": out_dir}, ensure_ascii=False))
            return existing

    doc = pymupdf.open(pdf_path)
    total = doc.page_count
    start = max(1, first_page)
    end = min(last_page or total, total)
    selected = [(pno, doc[pno - 1]) for pno in range(start, end + 1)]
    if limit:
        selected = selected[:limit]

    manifest = {"source": os.path.basename(pdf_path), "range": [start, end],
                "pages": []}
    try:
        for pno, page in selected:
            img, mode = page_image(doc, page, dpi)
            width, height = img.size
            if width < min_width:
                scale = min_width / width
                img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
                mode += "+upscale"
            width, height = img.size

            entry = {"page": pno, "w": width, "h": height, "mode": mode, "tiles": []}
            if height / max(width, 1) > tile_ratio:
                band = int(width * 1.55)
                step = max(1, int(band * (1 - overlap)))
                y, k = 0, 0
                while y < height:
                    k += 1
                    box = (0, y, width, min(y + band, height))
                    name = f"p{pno:04d}_t{k}.jpg"
                    save_jpeg(img.crop(box), os.path.join(out_dir, name), quality)
                    entry["tiles"].append({"file": name, "y0": y, "y1": box[3]})
                    if box[3] >= height:
                        break
                    y += step
            else:
                name = f"p{pno:04d}.jpg"
                save_jpeg(img, os.path.join(out_dir, name), quality)
                entry["tiles"].append({"file": name, "y0": 0, "y1": height})
            manifest["pages"].append(entry)
    finally:
        doc.close()

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Comic PDF -> page images for vision models.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True, help="output folder for page images")
    ap.add_argument("--min-width", type=int, default=1100, help="upscale pages narrower than this")
    ap.add_argument("--tile-ratio", type=float, default=2.6, help="height/width above which a page is sliced")
    ap.add_argument("--overlap", type=float, default=0.12, help="overlap between slices (0-0.4)")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI when no embedded JPEG is usable")
    ap.add_argument("--quality", type=int, default=92, help="JPEG quality for output")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N selected pages (smoke test)")
    ap.add_argument("--first-page", type=int, default=1, help="first page of a range (1-based, inclusive)")
    ap.add_argument("--last-page", type=int, default=None, help="last page of a range (1-based, inclusive)")
    ap.add_argument("--force", action="store_true", help="rebuild even if pages.json exists")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf):
        ap.error(f"no such file: {args.pdf}")

    manifest = process(args.pdf, args.out, args.min_width, args.tile_ratio,
                       max(0.0, min(0.4, args.overlap)), args.dpi, args.quality,
                       args.limit, args.force, args.first_page, args.last_page)
    tiles = sum(len(p["tiles"]) for p in manifest["pages"])
    print(json.dumps({"pages": len(manifest["pages"]), "tiles": tiles,
                      "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
