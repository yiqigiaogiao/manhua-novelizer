# -*- coding: utf-8 -*-
"""脚本共用的小工具：配置读写、front matter、字数统计。"""
from __future__ import annotations

import json
import os

DEFAULT_CONFIG = {
    "version": 2,
    "work": {
        "language": "zh",
        "reading_direction": "ltr",
        "nonstory_regex": "预告|公告|请假|通知|复刊|小结|获奖|目录|版权|后记",
        "strip_suffix": "",
    },
    "adaptation": {
        "pov": "third-limited",
        "tense": "past",
        "dialect": "keep",
        "forbid_meta_language": True,
        "style_config": "style.json",
    },
    "output": {
        "formats": ["md", "docx", "epub", "mobi"],
        "cover": True,
        "page_format": "jpg",
        # 页图是 S6.7 原图复检的事实源，成书后**不**自动删。
        # 彻底核对完成后由人显式执行 `clean_pages.py --work . --confirm`。
        "cleanup_after_build": False,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(work_dir: str) -> dict:
    path = os.path.join(work_dir, "config.json")
    if not os.path.isfile(path):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(path, encoding="utf-8") as fh:
        return deep_merge(DEFAULT_CONFIG, json.load(fh))


def save_config(work_dir: str, config: dict) -> str:
    path = os.path.join(work_dir, "config.json")
    os.makedirs(work_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    return path


def init_work(work_dir: str, force: bool = False) -> dict:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "config.json")
    if force or not os.path.isfile(path):
        save_config(work_dir, DEFAULT_CONFIG)
    for sub in ("audit", "build", "style_history"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    return load_config(work_dir)


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def list_dirs(path: str, prefix: str = "", suffix: str = "") -> list[str]:
    """列出子目录，按字面前后缀过滤。

    不要用 glob/fnmatch：路径里只要带方括号（中文下载目录常见
    「【完】」「[扫描]」这类），fnmatch 会把方括号当字符类，
    结果一条都匹配不到。实测 glob.glob 在带方括号的路径下返回空列表，
    而 os.scandir 正常。
    """
    out = []
    try:
        entries = list(os.scandir(path))
    except OSError:
        return out
    for e in entries:
        if not e.is_dir():
            continue
        if prefix and not e.name.startswith(prefix):
            continue
        if suffix and not e.name.endswith(suffix):
            continue
        out.append(e.path)
    return sorted(out)


def list_files(path: str, suffix: str = "") -> list[str]:
    out = []
    try:
        entries = list(os.scandir(path))
    except OSError:
        return out
    for e in entries:
        if not e.is_file():
            continue
        if suffix and not e.name.endswith(suffix):
            continue
        out.append(e.path)
    return sorted(out)


def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, parts[2]
