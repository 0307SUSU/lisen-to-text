# 语音转文字工具（实时转录 / 双语翻译）

## 新功能
- **语音输入**：点「语音输入」，从麦克风或所选输入设备听取外部语音。原文区会边听边更新；点「停止并保存」后，整段保存为 WAV（`文档/SpeechToMd/voice_时间.wav`），并转录成文本
- **实时转录**：点「实时转录」，对着麦克风说话，原文区会持续更新（约每 3 秒一段）
- **双语翻译**：选好「翻译目标」后点「翻译（双语）」；上方保留原文，下方显示译文；保存 Markdown 时两者都会写入
- 仍支持：选音频文件转录、先录音再转录

## 运行
```bash
cd D:\github\lisen-to-text
pip install -r requirements.txt
python main.py
```

## 说明
- 识别仍是本地 Whisper（faster-whisper）
- 翻译使用 Google（`deep-translator`），**需要联网**，无需 API 密钥
- 建议模型先选 `base`
- MP3/M4A 等非 WAV 需要本机安装 FFmpeg
