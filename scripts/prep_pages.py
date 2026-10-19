#!/usr/bin/env python3
"""兼容旧路径：等价于 `mnv pages`。"""
import sys

from manhua_novelizer.pages import main

if __name__ == "__main__":
    sys.exit(main())
