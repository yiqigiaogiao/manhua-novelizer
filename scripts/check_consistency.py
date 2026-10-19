#!/usr/bin/env python3
"""兼容旧路径：等价于 `mnv audit`。"""
import sys

from manhua_novelizer.consistency import main

if __name__ == "__main__":
    sys.exit(main())
