# -*- coding: utf-8 -*-
"""项目配置：流水线参数 + 叙事风格配置的读写。"""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
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
        "cleanup_after_build": True,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(work_dir: str) -> dict:
    path = os.path.join(work_dir, "config.json")
    if not os.path.isfile(path):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return deep_merge(DEFAULT_CONFIG, data)


def save_config(work_dir: str, config: dict) -> str:
    path = os.path.join(work_dir, "config.json")
    os.makedirs(work_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    return path


def init_work(work_dir: str, force: bool = False) -> dict:
    """建立工作目录骨架，不覆盖已有配置。"""
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "config.json")
    if force or not os.path.isfile(path):
        save_config(work_dir, DEFAULT_CONFIG)
    for sub in ("audit", "build", "style_history"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    return load_config(work_dir)
