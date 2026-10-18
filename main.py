#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Listen to Text · 听写对照 — 主入口。

开发用隐藏参数: --screenshot <tab 0/1/2> <show_tr 0/1> <out.png>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speech_to_md.gui import SpeechToMdApp


def _enable_dpi_awareness():
    """Windows 高 DPI 下避免模糊（截图坐标也随之正确）。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _enable_dpi_awareness()
    shot = None
    if len(sys.argv) >= 5 and sys.argv[1] == "--screenshot":
        shot = (int(sys.argv[2]), sys.argv[3] == "1", sys.argv[4])
    SpeechToMdApp(screenshot=shot).run()


if __name__ == "__main__":
    main()
