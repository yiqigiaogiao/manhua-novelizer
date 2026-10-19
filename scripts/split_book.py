#!/usr/bin/env python3
"""兼容旧路径：等价于 `mnv split`。"""
import sys

from manhua_novelizer.split import main

if __name__ == "__main__":
    sys.exit(main())
