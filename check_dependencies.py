#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装验证脚本
用于检查所有依赖是否正确安装
"""

import sys
import importlib.util

def check_module(module_name, package_name=None):
    """检查模块是否已安装"""
    if package_name is None:
        package_name = module_name
    
    spec = importlib.util.find_spec(module_name)
    if spec is not None:
        print(f"✓ {package_name:20} - 已安装")
        return True
    else:
        print(f"✗ {package_name:20} - 未安装")
        return False

def main():
    print("=" * 50)
    print("语音转文字工具 - 依赖检查")
    print("Speech to Markdown - Dependency Check")
    print("=" * 50)
    print()
    
    all_ok = True
    
    # 检查 Python 版本
    print(f"Python 版本: {sys.version}")
    if sys.version_info < (3, 8):
        print("✗ Python 版本过低，需要 3.8 或更高版本")
        all_ok = False
    else:
        print("✓ Python 版本符合要求")
    print()
    
    # 检查标准库
    print("标准库检查:")
    check_module("tkinter", "tkinter (GUI)")
    check_module("wave", "wave (音频)")
    check_module("threading", "threading (多线程)")
    print()
    
    # 检查核心依赖
    print("核心依赖检查:")
    has_whisper = check_module("faster_whisper", "faster-whisper")
    has_pyaudio = check_module("pyaudio", "PyAudio")
    has_pyinstaller = check_module("PyInstaller", "PyInstaller")
    
    if not has_whisper:
        print("  安装: pip install faster-whisper")
        all_ok = False
    
    if not has_pyaudio:
        print("  安装: pip install pyaudio")
        print("  Windows 如遇问题: pip install pipwin && pipwin install pyaudio")
        all_ok = False
    
    if not has_pyinstaller:
        print("  安装: pip install pyinstaller")
    
    print()
    
    # 检查 FFmpeg
    print("可选依赖检查:")
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✓ FFmpeg              - 已安装")
        else:
            print("✗ FFmpeg              - 未找到")
            print("  用于处理非 WAV 格式音频文件")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("✗ FFmpeg              - 未找到")
        print("  用于处理非 WAV 格式音频文件")
        print("  安装: https://ffmpeg.org/download.html")
    
    print()
    print("=" * 50)
    
    if all_ok:
        print("✓ 所有核心依赖已正确安装！")
        print("✓ 可以运行: python main.py")
    else:
        print("✗ 部分依赖缺失，请先安装")
        print("  运行: pip install -r requirements.txt")
    
    print("=" * 50)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
