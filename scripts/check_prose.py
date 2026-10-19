#!/usr/bin/env python3
"""兼容旧路径：等价于 `mnv qa`（已取消字数与禁用词检查）。"""
import sys

from manhua_novelizer.qa import main

if __name__ == "__main__":
    sys.exit(main())
