@echo off
REM 语音转文字工具 Windows 构建脚本
REM Speech to Markdown Windows Build Script

echo ========================================
echo 语音转文字工具 - Windows EXE 构建
echo Speech to Markdown - Windows EXE Build
echo ========================================
echo.

REM 检查是否安装了 PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [错误] 未安装 PyInstaller
    echo [Error] PyInstaller not installed
    echo.
    echo 正在安装 PyInstaller...
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo 安装失败！请手动运行: pip install pyinstaller
        pause
        exit /b 1
    )
)

echo.
echo [1/3] 清理旧的构建文件...
echo [1/3] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [2/3] 开始构建 EXE 文件...
echo [2/3] Building EXE file...
echo.

REM 使用 spec 文件构建
if exist speech_to_md.spec (
    pyinstaller --clean speech_to_md.spec
) else (
    REM 如果 spec 文件不存在，使用命令行参数构建
    pyinstaller ^
        --name=SpeechToMd ^
        --onedir ^
        --windowed ^
        --icon=NONE ^
        --add-data="speech_to_md;speech_to_md" ^
        --hidden-import=tkinter ^
        --hidden-import=faster_whisper ^
        --hidden-import=pyaudio ^
        --collect-all=faster_whisper ^
        --collect-all=ctranslate2 ^
        --noconfirm ^
        main.py
)

if errorlevel 1 (
    echo.
    echo [错误] 构建失败！
    echo [Error] Build failed!
    pause
    exit /b 1
)

echo.
echo [3/3] 构建完成！
echo [3/3] Build completed!
echo.
echo ========================================
echo 输出目录: dist\SpeechToMd\
echo Output directory: dist\SpeechToMd\
echo 可执行文件: dist\SpeechToMd\SpeechToMd.exe
echo Executable: dist\SpeechToMd\SpeechToMd.exe
echo ========================================
echo.
echo 注意事项 / Notes:
echo 1. 首次运行需要联网下载 Whisper 模型
echo    First run requires internet to download Whisper models
echo 2. 需要安装 FFmpeg 才能处理非 WAV 格式
echo    FFmpeg is required for non-WAV formats
echo 3. 可以将整个 dist\SpeechToMd 文件夹打包分发
echo    You can distribute the entire dist\SpeechToMd folder
echo.
pause
