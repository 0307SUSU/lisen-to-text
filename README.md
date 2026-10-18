# lisen-to-text（语音转 Markdown）

本地自用工具：语音输入 / 实时转录 / 文件转写 + 双语翻译。

## 运行

```bash
cd D:\GitHub\lisen-to-text
pip install -r requirements.txt
python main.py
```

## 要点

- 三模式 Tab；设置分「识别 / 翻译 / 存储 / 关于」
- 默认模型 **tiny**，启动预加载；实时短句停→出字目标 **≤1–2s**（已加载时）
- 整段文件 / 长音频 **不承诺 1s**，走进度提示
- 翻译：Google（免费需联网）；DeepL 等仅预留
- AI 辅助识别：仅留接口，本轮不做
- 路径（MD/WAV）可改，写入 `~/.speech_to_md/config.json`

## 检查依赖

```bash
python check_dependencies.py
```

非 WAV（MP3/M4A）需本机 FFmpeg。
