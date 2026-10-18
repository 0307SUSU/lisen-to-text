#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时转录模块 - 使用流式音频处理
Live Transcription Module - Using streaming audio processing
"""

import queue
import threading
import time
import numpy as np
from typing import Optional, Callable


class LiveTranscriber:
    """实时转录器 - 在录音时同步转录"""
    
    def __init__(self, transcriber):
        """
        初始化实时转录器
        
        Args:
            transcriber: AudioTranscriber 实例
        """
        self.transcriber = transcriber
        self.is_running = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_duration = 3  # 每个音频块的秒数
        self.overlap = 0.5  # 重叠秒数
        self.audio_buffer = []
        self.transcription_thread = None
        self.callback = None
        self.stream = None
        self.audio_interface = None
        
    def start(self, callback: Callable[[str, bool], None], model_size: str = "base", 
              language: Optional[str] = None, device_index: Optional[int] = None):
        """
        开始实时转录
        
        Args:
            callback: 回调函数 (transcript_text, is_final) - is_final 表示是否为最终文本
            model_size: 模型大小
            language: 语言代码
            device_index: 输入设备索引，None 为系统默认
        """
        try:
            import pyaudio
        except ImportError:
            raise ImportError("未安装 PyAudio。请运行: pip install pyaudio")
        
        # 加载模型
        self.transcriber.load_model(model_size)
        
        self.is_running = True
        self.callback = callback
        self.audio_buffer = []
        self.language = language
        
        # 初始化 PyAudio
        self.audio_interface = pyaudio.PyAudio()
        chunk_size = int(self.sample_rate * 0.1)  # 100ms 块
        
        try:
            self.stream = self.audio_interface.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
                stream_callback=self._audio_callback
            )
        except Exception as e:
            self.audio_interface.terminate()
            raise RuntimeError(f"无法打开麦克风: {str(e)}")
        
        # 启动转录线程
        self.transcription_thread = threading.Thread(
            target=self._transcription_worker,
            daemon=True
        )
        self.transcription_thread.start()
        
        self.stream.start_stream()
        print("实时转录已启动")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio 音频回调"""
        if self.is_running:
            # 将音频数据放入队列
            audio_chunk = np.frombuffer(in_data, dtype=np.int16)
            self.audio_queue.put(audio_chunk)
        return (in_data, 0)  # pyaudio.paContinue = 0
    
    def _transcription_worker(self):
        """转录工作线程"""
        import tempfile
        import wave
        
        chunk_frames = int(self.sample_rate * self.chunk_duration)
        overlap_frames = int(self.sample_rate * self.overlap)
        
        while self.is_running:
            try:
                # 收集音频数据
                while len(self.audio_buffer) < chunk_frames:
                    if not self.is_running:
                        break
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                        self.audio_buffer.extend(chunk)
                    except queue.Empty:
                        continue
                
                if not self.is_running:
                    break
                
                # 处理足够的音频数据
                if len(self.audio_buffer) >= chunk_frames:
                    # 提取当前块
                    current_chunk = self.audio_buffer[:chunk_frames]
                    
                    # 保留重叠部分
                    self.audio_buffer = self.audio_buffer[chunk_frames - overlap_frames:]
                    
                    # 保存为临时 WAV 文件
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                        tmp_path = tmp_file.name
                    
                    try:
                        # 写入 WAV
                        with wave.open(tmp_path, 'wb') as wf:
                            wf.setnchannels(self.channels)
                            wf.setsampwidth(2)  # 16-bit
                            wf.setframerate(self.sample_rate)
                            wf.writeframes(np.array(current_chunk, dtype=np.int16).tobytes())
                        
                        # 转录
                        try:
                            transcript = self.transcriber.transcribe(
                                tmp_path,
                                model_size=self.transcriber.current_model_size,
                                language=self.language
                            )
                            
                            if transcript.strip() and self.callback:
                                # 回调通知新的转录文本
                                self.callback(transcript.strip(), False)
                        except Exception as e:
                            print(f"转录错误: {e}")
                    finally:
                        # 删除临时文件
                        try:
                            import os
                            os.unlink(tmp_path)
                        except:
                            pass
            
            except Exception as e:
                print(f"实时转录工作线程错误: {e}")
                time.sleep(0.1)
        
        # 处理剩余的音频
        if len(self.audio_buffer) > self.sample_rate:  # 至少1秒
            self._process_final_chunk()
    
    def _process_final_chunk(self):
        """处理最后的音频块"""
        import tempfile
        import wave
        
        if not self.audio_buffer:
            return
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(np.array(self.audio_buffer, dtype=np.int16).tobytes())
            
            transcript = self.transcriber.transcribe(
                tmp_path,
                model_size=self.transcriber.current_model_size,
                language=self.language
            )
            
            if transcript.strip() and self.callback:
                self.callback(transcript.strip(), True)  # 最终文本
        except Exception as e:
            print(f"最终块转录错误: {e}")
        finally:
            try:
                import os
                os.unlink(tmp_path)
            except:
                pass
    
    def stop(self):
        """停止实时转录"""
        self.is_running = False
        
        # 停止音频流
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio_interface:
            self.audio_interface.terminate()
        
        # 等待转录线程结束
        if self.transcription_thread and self.transcription_thread.is_alive():
            self.transcription_thread.join(timeout=2)
        
        print("实时转录已停止")
