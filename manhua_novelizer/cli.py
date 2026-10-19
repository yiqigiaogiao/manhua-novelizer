# -*- coding: utf-8 -*-
"""命令行入口：mnv <command>。"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, build, config, consistency, manifest, pages, qa, split, style


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def cmd_init(args) -> int:
    cfg = config.init_work(args.work, force=args.force)
    st = style.load_style(args.work)
    if not os.path.isfile(style.style_path(args.work)):
        style.save_style(args.work, st, snapshot=False)
    _print({"work": os.path.abspath(args.work), "config": cfg,
            "style": style.style_path(args.work),
            "next": "先跑 mnv style init，再让 agent 完成叙事风格分析"})
    return 0


def cmd_manifest(args) -> int:
    _print(manifest.run(args.dir, args.out, args.strip_suffix, args.nonstory))
    return 0


def cmd_split(args) -> int:
    result = split.run(args.pdf, args.out, args.map, args.dry_run, args.toc_regex)
    _print(result)
    return 2 if result.get("error") else (1 if result.get("problems") else 0)


def cmd_pages(args) -> int:
    result = pages.process(args.pdf, args.out, args.min_width, args.tile_ratio,
                           args.overlap, args.dpi, args.quality, args.limit, args.force,
                           args.first_page, args.last_page, args.format, args.renumber)
    tiles = sum(len(p["tiles"]) for p in result["pages"])
    _print({"pages": len(result["pages"]), "tiles": tiles,
            "format": args.format, "out": args.out})
    return 0


def cmd_clean(args) -> int:
    _print(pages.cleanup(args.work, args.dry_run, args.keep))
    return 0


def cmd_qa(args) -> int:
    result = qa.run(args.draft, args.outline, args.bible, args.out,
                    args.min_coverage, args.match_ratio)
    _print(result)
    return 0 if result["checks"]["quote_coverage"]["pass"] else 1


def cmd_audit(args) -> int:
    result = consistency.run(args.work, args.bible, args.out, args.json_out)
    result.pop("issues", None)
    result.pop("markdown", None)
    _print(result)
    return 1 if result.get("errors") else (2 if result.get("error") else 0)


def cmd_build(args) -> int:
    formats = args.formats or ["md", "docx", "epub", "mobi"]
    result = build.run(args.work, args.out, args.title, formats, not args.no_cover)
    _print(result)
    if result.get("error"):
        return 1
    if args.cleanup:
        _print({"cleanup": pages.cleanup(args.work)})
    return 0


def cmd_style(args) -> int:
    st = style.load_style(args.work)
    if args.action == "render":
        out = args.out or os.path.join(args.work, "style.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(style.render_markdown(st))
        _print({"rendered": out})
        return 0
    if args.action == "confirm":
        st["confirmed"] = True
        _print({"saved": style.save_style(args.work, st), "confirmed": True})
        return 0
    if args.action == "check":
        _print({"pending": style.pending_dimensions(st),
                "confirmed": st.get("confirmed", False)})
        return 0
    # show / init
    _print(st)
    return 0


def cmd_order(args) -> int:
    from . import reading_order
    if args.set_dir:
        path = reading_order.apply(args.work, args.set_dir)
        _print({"direction": args.set_dir, "saved": path})
        return 0
    result = reading_order.detect(args.pages, args.sample)
    if args.work:
        result["work"] = args.work
    _print(result)
    return 0


def cmd_gui(args) -> int:
    from . import gui
    gui.main(work=args.work)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mnv", description="漫画转小说工具（漫画小说化流水线）")
    ap.add_argument("--version", action="version", version=f"manhua-novelizer {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="建立工作目录")
    p.add_argument("--work", default="work")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("manifest", help="建章节清单")
    p.add_argument("--dir", required=True)
    p.add_argument("--out", default="manifest.csv")
    p.add_argument("--strip-suffix", default="")
    p.add_argument("--nonstory", default=manifest.DEFAULT_NONSTORY)
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("split", help="合本 PDF 拆章")
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--map", default=None)
    p.add_argument("--toc-regex",
                   default=r"第\s*[零〇一二两三四五六七八九十百千]+\s*(点五|半)?\s*[回话章]|番外|序章|终章")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("pages", help="PDF 拆页")
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--format", choices=["jpg", "png"], default="jpg")
    p.add_argument("--min-width", type=int, default=1100)
    p.add_argument("--tile-ratio", type=float, default=2.6)
    p.add_argument("--overlap", type=float, default=0.12)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--quality", type=int, default=92)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--first-page", type=int, default=1)
    p.add_argument("--last-page", type=int, default=None)
    p.add_argument("--renumber", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_pages)

    p = sub.add_parser("clean", help="清理中间页图（jpg/png）")
    p.add_argument("--work", default="work")
    p.add_argument("--keep", default=None, help="保留该目录下的图片")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("qa", help="单话质检（台词覆盖）")
    p.add_argument("--draft", required=True)
    p.add_argument("--outline", required=True)
    p.add_argument("--bible", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--min-coverage", type=float, default=0.95)
    p.add_argument("--match-ratio", type=float, default=0.8)
    p.set_defaults(func=cmd_qa)

    p = sub.add_parser("audit", help="全本一致性审计")
    p.add_argument("--work", default="work")
    p.add_argument("--bible", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--json", dest="json_out", default=None)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("build", help="汇编成书（md/docx/epub/mobi + png 封面）")
    p.add_argument("--work", default="work")
    p.add_argument("--out", default="build")
    p.add_argument("--title", default="漫画小说化")
    p.add_argument("--formats", nargs="*", default=None)
    p.add_argument("--no-cover", action="store_true")
    p.add_argument("--cleanup", action="store_true", help="成书后清理中间页图")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("style", help="叙事风格配置")
    p.add_argument("--work", default="work")
    p.add_argument("--action", choices=["show", "render", "confirm", "check"], default="show")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_style)

    p = sub.add_parser("order", help="检测/设置阅读顺序（ltr/rtl/ttb）")
    p.add_argument("--pages", default=None, help="页图目录（检测用）")
    p.add_argument("--work", default="work", help="写入 config.json 的工作目录")
    p.add_argument("--set", dest="set_dir", choices=["ltr", "rtl", "ttb"], default=None)
    p.add_argument("--sample", type=int, default=6)
    p.set_defaults(func=cmd_order)

    p = sub.add_parser("gui", help="打开图形界面")
    p.add_argument("--work", default="work")
    p.set_defaults(func=cmd_gui)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.makedirs(args.work, exist_ok=True) if hasattr(args, "work") and args.work else None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
