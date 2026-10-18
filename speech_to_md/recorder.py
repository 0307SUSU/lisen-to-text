#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦克风录音模块
Microphone Recording Module
"""

import os
import wave
import tempfile
from datetime import datetime
from pathlib import Path


class AudioRecorder:
    """麦克风录音器"""
    
    def __init__(self):
        self.is_recording = False
        self.frames = []
        self.sample_rate = 16000  # Whisper 推荐的采样率
        self.channels = 1  # 单声道
        self.chunk_size = 1024
        self.audio_format = None
        self.stream = None
        self.audio_interface = None
    
    def start_recording(self, device_index=None) -> str:
        """
        开始录音
        
        Args:
            device_index: 输入设备索引，None 为系统默认
        
        Returns:
            录音文件路径
        """
        try:
            import pyaudio
        except ImportError:
            raise ImportError(
                "未安装 PyAudio。请运行: pip install pyaudio"
            )
        
        self.is_recording = True
        self.frames = []
        
        # 初始化 PyAudio
        self.audio_interface = pyaudio.PyAudio()
        self.audio_format = pyaudio.paInt16
        
        # 打开音频流
        try:
            self.stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )
        except Exception as e:
            self.audio_interface.terminate()
            raise RuntimeError(f"无法打开麦克风: {str(e)}")
        
        print("开始录音...")
        
        # 录音循环
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
            except Exception as e:
                print(f"录音错误: {e}")
                break
        
        # 停止和关闭流
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio_interface:
            self.audio_interface.terminate()
        
        print("录音结束")
        
        # 保存录音文件
        return self.save_recording()
    
    def stop_recording(self):
        """停止录音"""
        self.is_recording = False
    
    def save_recording(self) -> str:
        """
        保存录音为 WAV 文件
        
        Returns:
            保存的文件路径
        """
        if not self.frames:
            raise ValueError("没有录音数据")
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
        
        # 保存到临时目录或用户文档目录
        try:
            output_dir = Path.home() / "Documents" / "SpeechToMd"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / filename
        except:
            # 如果无法创建文档目录，使用临时目录
            output_path = Path(tempfile.gettempdir()) / filename
        
        # 写入 WAV 文件
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.frames))
        
        print(f"录音已保存: {output_path}")
        return str(output_path)
