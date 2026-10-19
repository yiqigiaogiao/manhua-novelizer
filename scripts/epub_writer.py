# -*- coding: utf-8 -*-
"""极简 EPUB 3 写出器（仅标准库）。"""
from __future__ import annotations

import html
import os
import uuid
import zipfile
from datetime import datetime, timezone

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def build_epub(chapters: list[dict], out_path: str, title: str,
               author: str = "", cover_png: str | None = None) -> str:
    """chapters: [{"id","title","html"}...]"""
    book_id = f"urn:uuid:{uuid.uuid4()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    manifest_items, spine_items, nav_items, files = [], [], [], []
    for i, ch in enumerate(chapters, start=1):
        name = f"chap{i:03d}.xhtml"
        files.append((f"OEBPS/{name}", _xhtml(ch["title"], ch["html"])))
        manifest_items.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="c{i}"/>')
        nav_items.append(f'<li><a href="{name}">{_esc(ch["title"])}</a></li>')

    cover_meta = ""
    cover_item = ""
    if cover_png and os.path.isfile(cover_png):
        with open(cover_png, "rb") as fh:
            files.append(("OEBPS/cover.png", fh.read()))
        manifest_items.append('<item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>')
        cover_meta = '<meta name="cover" content="cover"/>'

    nav = ("<?xml version='1.0' encoding='utf-8'?>\n"
           "<html xmlns='http://www.w3.org/1999/xhtml' xmlns:epub='http://www.idpf.org/2007/ops'>"
           f"<head><title>{_esc(title)}</title></head><body>"
           f"<nav epub:type='toc' id='toc'><h1>{_esc(title)}</h1><ol>"
           + "".join(nav_items) + "</ol></nav></body></html>")
    files.append(("OEBPS/nav.xhtml", nav))
    manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{_esc(title)}</dc:title>
    <dc:language>zh</dc:language>
    <dc:creator>{_esc(author)}</dc:creator>
    <meta property="dcterms:modified">{now}</meta>
    {cover_meta}
  </metadata>
  <manifest>
    {''.join(manifest_items)}
  </manifest>
  <spine>
    {''.join(spine_items)}
  </spine>
</package>"""

    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files:
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
    return out_path


def _xhtml(title: str, body_html: str) -> str:
    return ("<?xml version='1.0' encoding='utf-8'?>\n"
            "<html xmlns='http://www.w3.org/1999/xhtml'>"
            f"<head><title>{_esc(title)}</title>"
            "<style>body{font-family:serif;line-height:1.8;margin:1em}"
            "h2{font-size:1.2em;margin:1.4em 0 .8em}p{text-indent:2em;margin:.5em 0}"
            ".brk{text-align:center;text-indent:0;margin:1.2em 0}</style>"
            f"</head><body><h2>{_esc(title)}</h2>{body_html}</body></html>")
