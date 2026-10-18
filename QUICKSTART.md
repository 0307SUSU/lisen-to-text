# 快速开始指南

## 🚀 5分钟快速上手

### Windows 用户

#### 方法一：从源代码运行（推荐）

1. **安装 Python 3.8+**
   - 下载: https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **安装 FFmpeg**（可选，用于 MP3/M4A 等格式）
   ```bash
   # 使用 winget
   winget install ffmpeg
   
   # 或使用 Chocolatey
   choco install ffmpeg
   ```

3. **安装 Python 依赖**
   ```bash
   cd speech_to_md
   pip install -r requirements.txt
   ```
   
   如果 PyAudio 安装失败：
   ```bash
   pip install pipwin
   pipwin install pyaudio
   ```

4. **运行程序**
   ```bash
   python main.py
   ```

5. **首次使用**
   - 选择模型大小（推荐 `base`）
   - 第一次运行会自动下载模型（约 140MB）
   - 等待下载完成后即可使用

#### 方法二：构建 EXE（适合分发）

```bash
# 运行构建脚本
build_windows.bat

# 生成的 EXE 位于
dist\SpeechToMd\SpeechToMd.exe
```

---

## 📖 基本使用流程

### 1. 选择输入方式

**选项 A: 从文件转录**
1. 点击 「📁 选择音频文件」
2. 选择音频文件（支持 WAV、MP3、M4A、FLAC、OGG、WebM）
3. 点击 「▶️ 开始转录」

**选项 B: 麦克风录音**
1. 点击 「🎙️ 开始录音」
2. 对着麦克风说话
3. 点击 「⏹️ 停止录音」
4. 点击 「▶️ 开始转录」

### 2. 等待转录完成
- 首次使用会下载模型（请耐心等待）
- 转录时间取决于音频长度和电脑性能
- 进度条显示处理状态

### 3. 查看和保存结果
- 转录文本显示在下方文本框
- 点击 「💾 保存为 Markdown」保存文件
- 可以选择保存位置和文件名

---

## ⚙️ 设置说明

### 模型大小
| 模型 | 大小 | 速度 | 质量 | 适用场景 |
|------|------|------|------|----------|
| tiny | 40MB | 最快 | 基础 | 测试 |
| **base** | 140MB | 快 | 良好 | **日常使用** |
| small | 460MB | 中 | 很好 | 高质量 |
| medium | 1.5GB | 慢 | 优秀 | 专业 |
| large | 3GB | 最慢 | 最佳 | 最高质量 |

### 语言选择
- **auto**: 自动检测（推荐）
- **zh**: 中文
- **en**: 英文
- **ja**: 日语
- **ko**: 韩语
- 等等...

---

## ❓ 常见问题

### Q: PyAudio 安装失败？
**A:** Windows 用户使用：
```bash
pip install pipwin
pipwin install pyaudio
```

或从这里下载预编译版本：
https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

### Q: 不支持 MP3/M4A 格式？
**A:** 需要安装 FFmpeg：
```bash
winget install ffmpeg
```

验证安装：
```bash
ffmpeg -version
```

### Q: 模型下载很慢？
**A:** 
- 使用 VPN 或代理
- 或手动下载模型放到缓存目录：
  - Windows: `C:\Users\你的用户名\.cache\huggingface\hub\`

### Q: 转录不准确？
**A:**
- 使用更大的模型（small 或 medium）
- 确保音频清晰，噪音少
- 正确设置语言

### Q: 录音功能无法使用？
**A:**
- 检查麦克风权限（Windows 设置 → 隐私 → 麦克风）
- 确保麦克风未被其他程序占用
- 重启应用程序

---

## 🔧 检查依赖

运行依赖检查脚本：
```bash
python check_dependencies.py
```

这会显示所有已安装和缺失的依赖。

---

## 📦 构建分发包

### 创建 EXE
```bash
# 运行构建脚本
build_windows.bat

# 或手动构建
pyinstaller --clean speech_to_md.spec
```

### 分发给其他用户
1. 压缩 `dist\SpeechToMd\` 文件夹
2. 提供 FFmpeg 安装说明
3. 告知用户首次运行需联网下载模型

---

## 💡 使用技巧

1. **首次使用 base 模型**
   - 平衡速度和质量
   - 大小适中（140MB）
   
2. **处理长音频**
   - 建议使用 small 或 base 模型
   - 确保有足够内存
   
3. **提高准确率**
   - 使用高质量音频（清晰、低噪音）
   - 选择正确的语言
   - 使用更大的模型

4. **批量处理**
   - 可以连续选择和转录多个文件
   - 每个文件分别保存

---

## 📞 获取帮助

遇到问题？检查：
1. ✅ Python 版本 >= 3.8
2. ✅ 所有依赖已安装（运行 `python check_dependencies.py`）
3. ✅ FFmpeg 已安装并在 PATH 中
4. ✅ 防火墙未阻止程序

详细文档请参考 README.md
