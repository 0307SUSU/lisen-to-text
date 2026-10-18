#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音频转录：TranscriberBackend + post_process 钩子（AI 辅助仅留口）。"""

from __future__ import annotations

import os
import wave
from typing import Callable, Optional, Protocol, runtime_checkable


def identity_post_process(transcript: str) -> str:
    """默认恒等钩子；AI 辅助识别挂载点（P0 不接真实实现）。"""
    return transcript


def audio_duration_seconds(audio_file: str) -> Optional[float]:
    """尽量读取时长（WAV）；失败返回 None。"""
    try:
        with wave.open(audio_file, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return frames / float(rate)
    except Exception:
        try:
            size = os.path.getsize(audio_file)
            # 粗估：16kHz 16bit mono ≈ 32000 bytes/s
            return max(0.0, size / 32000.0)
        except OSError:
            return None


def wants_progress_mode(model_size: str, duration_sec: Optional[float]) -> bool:
    """>15s 或 base+ → 进度条模式，不承诺 1s。"""
    if model_size and model_size != "tiny":
        return True
    if duration_sec is not None and duration_sec > 15.0:
        return True
    return False


@runtime_checkable
class TranscriberBackend(Protocol):
    def load_model(self, model_size: str = "tiny") -> None:
        ...

    def transcribe(
        self,
        audio_file: str,
        model_size: str = "tiny",
        language: Optional[str] = None,
        beam_size: int = 1,
    ) -> str:
        ...


class FasterWhisperBackend:
    """默认 faster-whisper 实现。"""

    def __init__(self):
        self.model = None
        self.current_model_size = None

    def load_model(self, model_size: str = "tiny") -> None:
        if self.model is not None and self.current_model_size == model_size:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError("未安装 faster-whisper。请运行: pip install faster-whisper") from exc

        print(f"正在加载模型: {model_size}...")
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=None,
        )
        self.current_model_size = model_size
        print("模型加载完成")

    def transcribe(
        self,
        audio_file: str,
        model_size: str = "tiny",
        language: Optional[str] = None,
        beam_size: int = 1,
    ) -> str:
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"音频文件不存在: {audio_file}")
        self.load_model(model_size)
        options = {
            "beam_size": max(1, int(beam_size)),
            "best_of": 1 if beam_size <= 1 else max(1, int(beam_size)),
            "temperature": 0.0,
        }
        if language:
            options["language"] = language
        print(f"正在转录: {audio_file} (beam={options['beam_size']})")
        segments, info = self.model.transcribe(audio_file, **options)
        print(f"检测到的语言: {info.language}")
        parts = [segment.text for segment in segments]
        return " ".join(parts).strip()


class AudioTranscriber:
    """对外转录器：后端 + post_process 钩子。"""

    def __init__(
        self,
        backend: Optional[TranscriberBackend] = None,
        post_process: Optional[Callable[[str], str]] = None,
    ):
        self.backend: TranscriberBackend = backend or FasterWhisperBackend()
        self.post_process: Callable[[str], str] = post_process or identity_post_process

    @property
    def model(self):
        return getattr(self.backend, "model", None)

    @property
    def current_model_size(self):
        return getattr(self.backend, "current_model_size", None)

    def load_model(self, model_size: str = "tiny") -> None:
        self.backend.load_model(model_size)

    def transcribe(
        self,
        audio_file: str,
        model_size: str = "tiny",
        language: Optional[str] = None,
        beam_size: Optional[int] = None,
        apply_post_process: bool = True,
    ) -> str:
        if beam_size is None:
            # 短句体感优先：默认 beam=1
            beam_size = 1
        text = self.backend.transcribe(
            audio_file,
            model_size=model_size,
            language=language,
            beam_size=beam_size,
        )
        if apply_post_process and self.post_process:
            text = self.post_process(text or "")
        return text or ""
