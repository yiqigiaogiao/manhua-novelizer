# -*- coding: utf-8 -*-
"""打包入口：无参数启动 GUI，带参数走命令行。

用法：
    ManhuaNovelizer.exe                     # 打开图形界面
    ManhuaNovelizer.exe --selftest          # 自检（打包后验证依赖是否齐全）
    ManhuaNovelizer.exe build --work ...    # 命令行模式
"""
import sys


def selftest() -> int:
    import json
    import tkinter

    import docx  # noqa: F401
    import fitz
    import PIL
    from PIL import Image  # noqa: F401

    from manhua_novelizer import __version__, build, mobi, pages

    info = {
        "version": __version__,
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "tkinter": tkinter.TkVersion,
        "pymupdf": fitz.__doc__ or "ok",
        "pillow": PIL.__version__,
        "mobi": hasattr(mobi, "build_mobi"),
        "build": hasattr(build, "run"),
        "pages": hasattr(pages, "cleanup"),
    }
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if len(sys.argv) > 1:
        from manhua_novelizer.cli import main as cli_main
        return cli_main()
    from manhua_novelizer import gui
    gui.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
