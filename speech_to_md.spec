# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件
用于构建 SpeechToMd.exe
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('speech_to_md', 'speech_to_md'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'faster_whisper',
        'pyaudio',
        'ctranslate2',
        'wave',
        'threading',
        'pathlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 收集 faster-whisper 和 ctranslate2 的所有数据文件
from PyInstaller.utils.hooks import collect_all

datas_fw, binaries_fw, hiddenimports_fw = collect_all('faster_whisper')
a.datas += datas_fw
a.binaries += binaries_fw
a.hiddenimports += hiddenimports_fw

datas_ct, binaries_ct, hiddenimports_ct = collect_all('ctranslate2')
a.datas += datas_ct
a.binaries += binaries_ct
a.hiddenimports += hiddenimports_ct

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpeechToMd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口（GUI 应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如有图标文件，可以指定路径
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpeechToMd',
)
