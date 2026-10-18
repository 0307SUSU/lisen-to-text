#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音转文字桌面应用程序 - 主入口
Speech to Markdown Desktop Application - Main Entry Point
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speech_to_md.gui import SpeechToMdApp

def main():
    """主函数"""
    app = SpeechToMdApp()
    app.run()

if __name__ == "__main__":
    main()
