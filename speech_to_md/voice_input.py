#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音输入模块
听取外部音频输入，保留完整音频，并按段给出预览转录。
停止后把整段保存为 16 kHz 单声道 WAV。
"""

import os
import queue
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


def _normalize_device_name(name: str) -> str:
    """整理设备名。部分 Windows 设备名是把 UTF-8 按 GBK 解开的，这里改回来。"""
    name = " ".join(str(name).replace("\x00", " ").split())
    if not name:
        return name
    try:
        repaired = name.encode("gbk").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    repaired = " ".join(repaired.split())
    return repaired or name


def list_input_devices() -> List[Tuple[int, str]]:
    """列出可用的音频输入设备。PyAudio 不可用时返回空列表。"""
    try:
        import pyaudio
    except ImportError:
        return []

    audio = pyaudio.PyAudio()
    devices = []
    try:
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels") or 0) > 0:
                name = _normalize_device_name(info.get("name") or f"设备 {index}")
                devices.append((index, name or f"设备 {index}"))
    finally:
        audio.terminate()
    return devices


def _resample_int16(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    dst_len = max(1, int(round(len(samples) * float(dst_rate) / float(src_rate))))
    if len(samples) == 1:
        return np.repeat(samples, dst_len)
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=dst_len, endpoint=False)
    resampled = np.interp(x_new, x_old, samples.astype(np.float32))
    return np.clip(np.rint(resampled), -32768, 32767).astype(np.int16)


def to_mono_16k(data: bytes, channels: int, sample_rate: int) -> bytes:
    """把采集到的 PCM16 转成 16 kHz 单声道，供保存和 Whisper 使用。"""
    if not data or channels <= 0 or sample_rate <= 0:
        return b""
    if len(data) < 2:
        return b""
    if len(data) % 2:
        data = data[:-1]
    samples = np.frombuffer(data, dtype=np.int16).copy()
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        if usable <= 0:
            return b""
        multi = samples[:usable].reshape(-1, channels).astype(np.int32)
        samples = (multi.sum(axis=1) // channels).astype(np.int16)
    samples = _resample_int16(samples, sample_rate, 16000)
    return samples.tobytes()


class VoiceInput:
    """听取输入设备，边听边预览文字，停止后保存完整语音文件。"""

    def __init__(self, transcriber):
        self.transcriber = transcriber
        self.is_running = False
        self.sample_rate = 16000
        self.chunk_duration = 3.0
        self.overlap = 0.5
        self.frames = []
        self._frames_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self.audio_queue = queue.Queue()
        self.capture_rate = 16000
        self.capture_channels = 1
        self.stream = None
        self.audio_interface = None
        self.worker = None
        self.callback = None
        self.language = None
        self._started_at = None
        self._pcm_buffer = bytearray()
        self._stopping = False
        self._saved_path = None
        self._capture_started = False
        self._stop_event = threading.Event()
        self._pa_continue = 0
        self._generation = 0

    def elapsed_seconds(self) -> float:
        if not self._started_at:
            return 0.0
        return max(0.0, time.monotonic() - self._started_at)

    def start(self, callback, model_size: str = "base", language: Optional[str] = None,
              device_index: Optional[int] = None, should_continue=None):
        """
        开始听取语音。

        Args:
            callback: (text, is_final) 预览转录回调
            model_size: Whisper 模型
            language: 语言代码，None 为自动检测
            device_index: 输入设备索引，None 为系统默认
            should_continue: 返回 False 时放弃本次启动（用户已取消）
        """
        try:
            import pyaudio
        except ImportError:
            raise ImportError("未安装 PyAudio。请运行: pip install pyaudio")

        with self._state_lock:
            if should_continue and not should_continue():
                return
            self._generation += 1
            generation = self._generation
            self.is_running = True
            self._stopping = False
            self._saved_path = None
            self._capture_started = False
            self._stop_event = threading.Event()
            self.frames = []
            self._pcm_buffer = bytearray()
            self.audio_queue = queue.Queue()
            self.callback = callback
            self.language = language
            self._started_at = time.monotonic()

        self.transcriber.load_model(model_size)

        if not self._session_alive(generation, should_continue):
            return

        audio = pyaudio.PyAudio()
        self._pa_continue = pyaudio.paContinue
        try:
            stream = self._open_stream(pyaudio, audio, device_index)
        except Exception:
            audio.terminate()
            self._session_alive(generation, lambda: False)
            raise

        with self._state_lock:
            if not self._session_alive_locked(generation, should_continue):
                self.stream = stream
                self.audio_interface = audio
                self._close_stream_locked()
                return
            self.audio_interface = audio
            self.stream = stream
            self._capture_started = True
            self.worker = threading.Thread(target=self._worker, daemon=True)
            self.worker.start()
        try:
            stream.start_stream()
        except Exception:
            if not self.is_running:
                return
            raise

    def _session_alive(self, generation, should_continue) -> bool:
        with self._state_lock:
            return self._session_alive_locked(generation, should_continue)

    def _session_alive_locked(self, generation, should_continue) -> bool:
        cancelled = bool(should_continue and not should_continue())
        alive = self._generation == generation and self.is_running and not cancelled
        if not alive and self._generation == generation:
            self.is_running = False
        return alive

    def _open_stream(self, pyaudio, audio, device_index):
        rates = []
        native = self._native_rate(audio, device_index)
        for rate in (16000, native, 48000, 44100, 32000, 22050):
            if rate and int(rate) not in rates:
                rates.append(int(rate))

        last_error = None
        for channels in (1, 2):
            for rate in rates:
                try:
                    stream = audio.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=max(256, int(rate * 0.1)),
                        stream_callback=self._audio_callback,
                    )
                    self.capture_rate = rate
                    self.capture_channels = channels
                    return stream
                except Exception as exc:
                    last_error = exc
        raise RuntimeError(f"无法打开音频输入设备: {last_error}")

    def _native_rate(self, audio, device_index):
        try:
            if device_index is None:
                info = audio.get_default_input_device_info()
            else:
                info = audio.get_device_info_by_index(device_index)
            return int(info.get("defaultSampleRate") or 0)
        except Exception:
            return 0

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if in_data:
            self.audio_queue.put(bytes(in_data))
        return (None, self._pa_continue)

    def _worker(self):
        chunk_bytes = int(self.sample_rate * self.chunk_duration) * 2
        overlap_bytes = int(self.sample_rate * self.overlap) * 2
        try:
            while self.is_running:
                try:
                    raw = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._append_pcm(raw)
                while len(self._pcm_buffer) >= chunk_bytes and self.is_running:
                    current = bytes(self._pcm_buffer[:chunk_bytes])
                    del self._pcm_buffer[: chunk_bytes - overlap_bytes]
                    self._transcribe_pcm(current)
        finally:
            self._drain_queue()

    def _append_pcm(self, raw: bytes):
        pcm = to_mono_16k(raw, self.capture_channels, self.capture_rate)
        if not pcm:
            return
        with self._frames_lock:
            self.frames.append(pcm)
        self._pcm_buffer.extend(pcm)

    def _drain_queue(self):
        while True:
            try:
                raw = self.audio_queue.get_nowait()
            except queue.Empty:
                break
            pcm = to_mono_16k(raw, self.capture_channels, self.capture_rate)
            if pcm:
                with self._frames_lock:
                    self.frames.append(pcm)

    def _transcribe_pcm(self, pcm: bytes):
        if not pcm or not self.callback:
            return
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            self._write_wav(tmp_path, pcm)
            transcript = self.transcriber.transcribe(
                tmp_path,
                model_size=self.transcriber.current_model_size,
                language=self.language,
            )
            text = (transcript or "").strip()
            if text and self.callback:
                self.callback(text, False)
        except Exception as exc:
            print(f"语音输入预览转录错误: {exc}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def stop(self) -> Optional[str]:
        """停止听取并保存 WAV。没有有效语音时返回 None。"""
        with self._state_lock:
            if self._stopping:
                wait_for_other = True
            else:
                wait_for_other = False
                self._stopping = True
                self._generation += 1
                self.is_running = False
                stream = self.stream
                interface = self.audio_interface
                self.stream = None
                self.audio_interface = None

        if wait_for_other:
            self._stop_event.wait()
            return self._saved_path

        try:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if interface is not None:
                try:
                    interface.terminate()
                except Exception:
                    pass
            if self.worker and self.worker.is_alive():
                self.worker.join()
            self._drain_queue()
            self._saved_path = self._save()
            return self._saved_path
        finally:
            self._stop_event.set()

    def _close_stream_locked(self):
        stream = self.stream
        interface = self.audio_interface
        self.stream = None
        self.audio_interface = None
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if interface is not None:
            try:
                interface.terminate()
            except Exception:
                pass

    def _save(self) -> Optional[str]:
        with self._frames_lock:
            pcm = b"".join(self.frames)
        # 短于 0.3 秒视为没有有效语音
        if len(pcm) < self.sample_rate * 2 * 0.3:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"voice_{timestamp}.wav"
        try:
            output_dir = Path.home() / "Documents" / "SpeechToMd"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / filename
        except OSError:
            output_path = Path(tempfile.gettempdir()) / filename
        self._write_wav(str(output_path), pcm)
        print(f"语音输入已保存: {output_path}")
        return str(output_path)

    @staticmethod
    def _write_wav(path: str, pcm: bytes):
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm)
