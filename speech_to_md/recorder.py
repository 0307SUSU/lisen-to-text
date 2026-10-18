#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦克风录音模块。"""

import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional


class AudioRecorder:
    """麦克风录音器。"""

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir
        self.is_recording = False
        self.frames = []
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        self.audio_format = None
        self.stream = None
        self.audio_interface = None

    def set_output_dir(self, path: Optional[str]) -> None:
        self.output_dir = path

    def start_recording(self, device_index=None, output_dir: Optional[str] = None) -> str:
        try:
            import pyaudio
        except ImportError as exc:
            raise ImportError("未安装 PyAudio。请运行: pip install pyaudio") from exc

        if output_dir is not None:
            self.output_dir = output_dir

        self.is_recording = True
        self.frames = []
        self.audio_interface = pyaudio.PyAudio()
        self.audio_format = pyaudio.paInt16
        try:
            self.stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
            )
        except Exception as e:
            self.audio_interface.terminate()
            raise RuntimeError(f"无法打开麦克风: {e}") from e

        print("开始录音...")
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
            except Exception as e:
                print(f"录音错误: {e}")
                break

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio_interface:
            self.audio_interface.terminate()
        print("录音结束")
        return self.save_recording()

    def stop_recording(self):
        self.is_recording = False

    def save_recording(self) -> str:
        if not self.frames:
            raise ValueError("没有录音数据")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
        try:
            base = Path(self.output_dir) if self.output_dir else (Path.home() / "Documents" / "SpeechToMd")
            base.mkdir(parents=True, exist_ok=True)
            output_path = base / filename
        except OSError:
            output_path = Path(tempfile.gettempdir()) / filename
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(self.frames))
        print(f"录音已保存: {output_path}")
        return str(output_path)
