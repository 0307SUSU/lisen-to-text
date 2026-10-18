#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装验证 / GUI 轻量自检。"""

import importlib.util
import subprocess
import sys


def check_module(module_name, package_name=None):
    if package_name is None:
        package_name = module_name
    spec = importlib.util.find_spec(module_name)
    ok = spec is not None
    return ok, package_name


def summarize_dependencies() -> str:
    """供 GUI「关于」页展示的一行摘要。"""
    lines = []
    py_ok = sys.version_info >= (3, 8)
    lines.append(f"Python {sys.version.split()[0]}{' OK' if py_ok else ' 需≥3.8'}")
    for mod, name in (
        ("tkinter", "tkinter"),
        ("faster_whisper", "faster-whisper"),
        ("pyaudio", "PyAudio"),
        ("deep_translator", "deep-translator"),
        ("numpy", "numpy"),
    ):
        ok, _ = check_module(mod, name)
        lines.append(f"{'OK' if ok else 'MISSING'} {name}")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        lines.append("OK FFmpeg" if r.returncode == 0 else "OPT FFmpeg 未找到（非 WAV 可选）")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        lines.append("OPT FFmpeg 未找到（非 WAV 可选）")
    return "\n".join(lines)


def main():
    print("=" * 50)
    print("语音转文字工具 - 依赖检查")
    print("=" * 50)
    print()
    print(f"Python 版本: {sys.version}")
    all_ok = sys.version_info >= (3, 8)
    if not all_ok:
        print("MISSING Python 版本过低，需要 3.8 或更高")
    else:
        print("OK Python 版本符合要求")
    print()
    print("标准库:")
    for mod, name in (("tkinter", "tkinter (GUI)"), ("wave", "wave"), ("threading", "threading")):
        ok, _ = check_module(mod, name)
        print(f"{'OK' if ok else 'MISSING'} {name}")
        if not ok and mod == "tkinter":
            all_ok = False
    print()
    print("核心依赖:")
    for mod, name, required in (
        ("faster_whisper", "faster-whisper", True),
        ("pyaudio", "PyAudio", True),
        ("deep_translator", "deep-translator", True),
        ("numpy", "numpy", True),
        ("PyInstaller", "PyInstaller", False),
    ):
        ok, _ = check_module(mod, name)
        print(f"{'OK' if ok else 'MISSING'} {name:20} - {'已安装' if ok else '未安装'}")
        if required and not ok:
            all_ok = False
            print(f"  安装: pip install {name.lower() if name != 'PyAudio' else 'pyaudio'}")
    print()
    print("可选:")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        print("OK FFmpeg - 已安装" if r.returncode == 0 else "OPT FFmpeg - 未找到")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("OPT FFmpeg - 未找到（处理非 WAV 时需要）")
    print()
    print("=" * 50)
    if all_ok:
        print("✓ 核心依赖齐全，可运行: python main.py")
    else:
        print("✗ 有依赖缺失: pip install -r requirements.txt")
    print("=" * 50)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
