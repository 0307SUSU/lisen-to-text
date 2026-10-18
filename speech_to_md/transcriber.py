#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频转录模块 - 使用 faster-whisper
Audio Transcription Module - Using faster-whisper
"""

import os
from typing import Optional


class AudioTranscriber:
    """音频转录器"""
    
    def __init__(self):
        self.model = None
        self.current_model_size = None
    
    def load_model(self, model_size: str = "base"):
        """
        加载 Whisper 模型
        
        Args:
            model_size: 模型大小 (tiny, base, small, medium, large)
        """
        if self.model is not None and self.current_model_size == model_size:
            return  # 模型已加载
        
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "未安装 faster-whisper。请运行: pip install faster-whisper"
            )
        
        # 加载模型（首次会自动下载）
        # 使用 CPU，如果有 CUDA GPU 可以改为 "cuda"
        device = "cpu"
        compute_type = "int8"  # CPU 使用 int8，GPU 可用 float16
        
        print(f"正在加载模型: {model_size}...")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=None  # 使用默认缓存目录
        )
        self.current_model_size = model_size
        print("模型加载完成！")
    
    def transcribe(
        self,
        audio_file: str,
        model_size: str = "base",
        language: Optional[str] = None
    ) -> str:
        """
        转录音频文件
        
        Args:
            audio_file: 音频文件路径
            model_size: 模型大小
            language: 语言代码 (zh, en 等)，None 表示自动检测
        
        Returns:
            转录文本
        """
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"音频文件不存在: {audio_file}")
        
        # 加载模型
        self.load_model(model_size)
        
        # 转录参数
        transcribe_options = {
            "beam_size": 5,
            "best_of": 5,
            "temperature": 0.0,
        }
        
        if language:
            transcribe_options["language"] = language
        
        # 执行转录
        print(f"正在转录: {audio_file}")
        segments, info = self.model.transcribe(
            audio_file,
            **transcribe_options
        )
        
        # 检测到的语言
        detected_language = info.language
        print(f"检测到的语言: {detected_language}")
        
        # 收集所有片段的文本
        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text)
        
        # 合并文本
        full_transcript = " ".join(transcript_parts).strip()
        
        return full_transcript
