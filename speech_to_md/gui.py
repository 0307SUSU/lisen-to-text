#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI界面模块 - 实时转录 + 双语翻译
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
from datetime import datetime
from pathlib import Path

from .transcriber import AudioTranscriber
from .recorder import AudioRecorder
from .markdown_writer import MarkdownWriter
from .live_transcriber import LiveTranscriber
from .translator import Translator
from .voice_input import VoiceInput, list_input_devices


class SpeechToMdApp:
    """语音转文字应用程序主窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("语音转文字工具 - 语音输入 / 实时转录 / 双语翻译")
        self.root.geometry("1100x800")
        self.root.resizable(True, True)

        self.transcriber = AudioTranscriber()
        self.recorder = AudioRecorder()
        self.md_writer = MarkdownWriter()
        self.live_transcriber = LiveTranscriber(self.transcriber)
        self.voice_input = VoiceInput(self.transcriber)
        self.translator_engine = Translator()

        self.is_recording = False
        self.is_transcribing = False
        self.is_live = False
        self.is_voice = False
        self.voice_ready = False
        self._voice_cancel = False
        self._voice_start_thread = None
        self._device_map = {"系统默认": None}
        self.current_transcript = ""
        self.current_translation = ""
        self.current_audio_file = None
        self.live_final_parts = []
        self.live_interim = ""

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(200, self._poll_live_ui)

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)
        main_frame.rowconfigure(5, weight=1)

        ttk.Label(
            main_frame,
            text="语音转文字工具（语音输入 / 实时转录 / 双语翻译）",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, pady=(0, 10), sticky=tk.W)

        self.create_settings_frame(main_frame)
        self.create_button_frame(main_frame)

        status_row = ttk.Frame(main_frame)
        status_row.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, text="就绪", font=("Microsoft YaHei UI", 10))
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=220)
        self.progress.grid(row=0, column=1, sticky=tk.E)

        self.create_text_areas(main_frame)
        self.create_save_frame(main_frame)

    def create_settings_frame(self, parent):
        settings = ttk.LabelFrame(parent, text="设置", padding="10")
        settings.grid(row=1, column=0, pady=8, sticky=(tk.W, tk.E))

        ttk.Label(settings, text="模型大小:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        self.model_var = tk.StringVar(value="base")
        ttk.Combobox(
            settings,
            textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large"],
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(settings, text="识别语言:").grid(row=0, column=2, sticky=tk.W, padx=(16, 6))
        self.language_var = tk.StringVar(value="zh")
        ttk.Combobox(
            settings,
            textvariable=self.language_var,
            values=["auto", "zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky=tk.W)

        ttk.Label(settings, text="翻译目标:").grid(row=0, column=4, sticky=tk.W, padx=(16, 6))
        self.target_lang_var = tk.StringVar(value="en")
        ttk.Combobox(
            settings,
            textvariable=self.target_lang_var,
            values=["zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=10,
        ).grid(row=0, column=5, sticky=tk.W)

        ttk.Label(
            settings,
            text="语音输入会听取所选设备，停止后保存整段 WAV 并转录成文本。翻译需要联网（Google，无需密钥）。",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(8, 0))

        ttk.Label(settings, text="输入设备:").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.device_var = tk.StringVar(value="系统默认")
        self.device_combo = ttk.Combobox(
            settings,
            textvariable=self.device_var,
            state="readonly",
            width=56,
        )
        self.device_combo.grid(row=2, column=1, columnspan=5, sticky=(tk.W, tk.E), pady=(8, 0))
        self.device_combo["values"] = ["系统默认"]
        self._load_input_devices()

    def create_button_frame(self, parent):
        row = ttk.Frame(parent)
        row.grid(row=2, column=0, pady=8, sticky=(tk.W, tk.E))

        self.select_file_btn = ttk.Button(row, text="选择音频文件", command=self.select_audio_file, width=16)
        self.select_file_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.voice_btn = ttk.Button(row, text="语音输入", command=self.toggle_voice_input, width=14)
        self.voice_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.record_btn = ttk.Button(row, text="开始录音", command=self.toggle_recording, width=12)
        self.record_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.transcribe_btn = ttk.Button(
            row, text="开始转录", command=self.start_transcription, width=12, state=tk.DISABLED
        )
        self.transcribe_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.live_btn = ttk.Button(row, text="实时转录", command=self.toggle_live, width=12)
        self.live_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.translate_btn = ttk.Button(row, text="翻译（双语）", command=self.start_translation, width=14)
        self.translate_btn.pack(side=tk.LEFT, padx=(0, 8))

    def create_text_areas(self, parent):
        src = ttk.LabelFrame(parent, text="原文 / 实时转录", padding="5")
        src.grid(row=4, column=0, pady=(8, 4), sticky=(tk.W, tk.E, tk.N, tk.S))
        src.columnconfigure(0, weight=1)
        src.rowconfigure(0, weight=1)
        self.text_area = scrolledtext.ScrolledText(src, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=12)
        self.text_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        dst = ttk.LabelFrame(parent, text="译文（与原文对照）", padding="5")
        dst.grid(row=5, column=0, pady=(4, 8), sticky=(tk.W, tk.E, tk.N, tk.S))
        dst.columnconfigure(0, weight=1)
        dst.rowconfigure(0, weight=1)
        self.translation_area = scrolledtext.ScrolledText(
            dst, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=8
        )
        self.translation_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    def create_save_frame(self, parent):
        row = ttk.Frame(parent)
        row.grid(row=6, column=0, pady=6, sticky=(tk.W, tk.E))
        self.save_btn = ttk.Button(
            row, text="保存为 Markdown（双语）", command=self.save_markdown, width=28, state=tk.DISABLED
        )
        self.save_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row, text="清空", command=self.clear_text, width=10).pack(side=tk.LEFT)

    def _load_input_devices(self):
        try:
            devices = list_input_devices()
        except Exception:
            devices = []
        labels = ["系统默认"]
        mapping = {"系统默认": None}
        for index, name in devices:
            label = f"{name.strip()}  [{index}]"
            if label in mapping:
                continue
            mapping[label] = index
            labels.append(label)
        self._device_map = mapping
        self.device_combo["values"] = labels
        if self.device_var.get() not in mapping:
            self.device_var.set("系统默认")

    def _selected_device_index(self):
        return self._device_map.get(self.device_var.get())

    def select_audio_file(self):
        if self.is_live or self.is_voice:
            messagebox.showinfo("提示", "请先停止当前的语音听取")
            return
        filetypes = (
            ("音频文件", "*.wav *.mp3 *.m4a *.flac *.ogg *.webm"),
            ("所有文件", "*.*"),
        )
        filename = filedialog.askopenfilename(title="选择音频文件", filetypes=filetypes)
        if filename:
            self.current_audio_file = filename
            self.status_label.config(text=f"已选择: {os.path.basename(filename)}")
            self.transcribe_btn.config(state=tk.NORMAL)

    def toggle_recording(self):
        if self.is_live or self.is_voice:
            messagebox.showinfo("提示", "请先停止当前的语音听取")
            return
        if not self.is_recording:
            self.is_recording = True
            self.record_btn.config(text="停止录音")
            self._set_busy(True, keep_record=True)
            self.status_label.config(text="正在录音…")
            self._record_device = self._selected_device_index()
            threading.Thread(target=self.record_audio, daemon=True).start()
        else:
            self.recorder.stop_recording()
            self.is_recording = False
            self.record_btn.config(text="开始录音")
            self._set_busy(False)

    def record_audio(self):
        try:
            output_file = self.recorder.start_recording(device_index=self._record_device)
            if output_file:
                self.current_audio_file = output_file
                self.root.after(0, lambda: self.status_label.config(
                    text=f"录音完成: {os.path.basename(output_file)}"
                ))
                self.root.after(0, lambda: self.transcribe_btn.config(state=tk.NORMAL))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("录音错误", f"录音失败: {e}"))
            self.root.after(0, lambda: self.status_label.config(text="录音失败"))
        finally:
            self.root.after(0, lambda: self.record_btn.config(text="开始录音"))
            self.is_recording = False
            self.root.after(0, lambda: self._set_busy(False))

    def start_transcription(self):
        if self.is_live or self.is_voice:
            return
        if not self.current_audio_file:
            messagebox.showwarning("警告", "请先选择音频文件或录音")
            return
        if self.is_transcribing:
            return
        self.is_transcribing = True
        self._set_busy(True)
        self.status_label.config(text="正在加载模型…")
        self.progress.start(10)
        threading.Thread(target=self.transcribe_audio, args=(self.current_audio_file,), daemon=True).start()

    def transcribe_audio(self, audio_file):
        try:
            model_size = self.model_var.get()
            language = self.language_var.get()
            if language == "auto":
                language = None
            self.root.after(0, lambda: self.status_label.config(text="正在转录…"))
            transcript = self.transcriber.transcribe(audio_file, model_size=model_size, language=language)
            self.current_transcript = transcript
            self.current_translation = ""
            self.root.after(0, self._show_transcript)
            self.root.after(0, lambda: self.status_label.config(text="转录完成"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "转录错误",
                f"转录失败: {e}\n\n非 WAV 格式需要安装 FFmpeg。",
            ))
            self.root.after(0, lambda: self.status_label.config(text="转录失败"))
        finally:
            self.is_transcribing = False
            self.root.after(0, self.progress.stop)
            self.root.after(0, lambda: self._set_busy(False))

    def toggle_live(self):
        if self.is_transcribing or self.is_recording or self.is_voice:
            messagebox.showinfo("提示", "请先结束当前录音、转录或语音输入")
            return
        if not self.is_live:
            self._start_live()
        else:
            self._stop_live()

    def _start_live(self):
        self.live_final_parts = []
        self.live_interim = ""
        self.current_translation = ""
        self.translation_area.delete("1.0", tk.END)
        self.text_area.delete("1.0", tk.END)
        self.is_live = True
        self.live_btn.config(text="停止实时转录")
        self._set_busy(True, keep_live=True)
        self.status_label.config(text="正在加载模型并启动实时转录…")
        self.progress.start(10)
        language = self.language_var.get()
        if language == "auto":
            language = None
        model_size = self.model_var.get()
        device_index = self._selected_device_index()

        def worker():
            try:
                self.live_transcriber.start(
                    callback=self._on_live_chunk,
                    model_size=model_size,
                    language=language,
                    device_index=device_index,
                )
                self.root.after(0, lambda: self.status_label.config(text="正在实时转录…对着麦克风说话即可"))
            except Exception as e:
                self.is_live = False
                self.root.after(0, lambda: messagebox.showerror("实时转录错误", str(e)))
                self.root.after(0, self._reset_live_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_live(self):
        self.status_label.config(text="正在停止实时转录…")

        def worker():
            try:
                self.live_transcriber.stop()
            except Exception as e:
                print(e)
            self.is_live = False
            text = self._compose_live_text(include_interim=False).strip()
            self.current_transcript = text
            self.root.after(0, self._reset_live_ui)
            self.root.after(0, lambda: self.status_label.config(text="实时转录已结束"))
            if text:
                self.root.after(0, lambda: self.save_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _on_live_chunk(self, text, is_final):
        # Called from worker thread — only store; UI polled on main thread
        text = (text or "").strip()
        if not text:
            return
        if is_final:
            if not self.live_final_parts or self.live_final_parts[-1] != text:
                self.live_final_parts.append(text)
            self.live_interim = ""
        else:
            # rolling window result: treat as a new committed segment if clearly new
            if self.live_final_parts and (
                text in self.live_final_parts[-1] or self.live_final_parts[-1] in text
            ):
                self.live_final_parts[-1] = text if len(text) >= len(self.live_final_parts[-1]) else self.live_final_parts[-1]
            elif not self.live_final_parts or text != self.live_final_parts[-1]:
                # avoid dumping near-duplicates from overlap
                if self.live_final_parts:
                    last = self.live_final_parts[-1]
                    if text.startswith(last) or last.startswith(text):
                        self.live_final_parts[-1] = text if len(text) > len(last) else last
                    else:
                        self.live_final_parts.append(text)
                else:
                    self.live_final_parts.append(text)
            self.live_interim = ""

    def _compose_live_text(self, include_interim=True):
        parts = list(self.live_final_parts)
        if include_interim and self.live_interim:
            parts.append(self.live_interim)
        return "\n".join(parts)

    def _poll_live_ui(self):
        if self.is_live or self.is_voice:
            composed = self._compose_live_text()
            current = self.text_area.get("1.0", tk.END).rstrip("\n")
            if composed != current:
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert("1.0", composed)
                self.text_area.see(tk.END)
                self.current_transcript = composed
                if composed.strip():
                    self.save_btn.config(state=tk.NORMAL)
            if self.is_voice and self.voice_ready:
                elapsed = int(self.voice_input.elapsed_seconds())
                self.status_label.config(
                    text=f"正在听取语音… {elapsed} 秒。停止后保存为音频文件并转录。"
                )
        self.root.after(200, self._poll_live_ui)

    def _reset_live_ui(self):
        self.progress.stop()
        self.live_btn.config(text="实时转录")
        self._set_busy(False)
        composed = self._compose_live_text(include_interim=False)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", composed)
        self.current_transcript = composed

    def toggle_voice_input(self):
        if self.is_transcribing or self.is_recording or self.is_live:
            messagebox.showinfo("提示", "请先结束当前录音、转录或实时转录")
            return
        if not self.is_voice:
            self._start_voice_input()
        else:
            self._stop_voice_input()

    def _start_voice_input(self):
        self.live_final_parts = []
        self.live_interim = ""
        self.current_translation = ""
        self.translation_area.delete("1.0", tk.END)
        self.text_area.delete("1.0", tk.END)
        self._voice_cancel = False
        self.is_voice = True
        self.voice_ready = False
        self.voice_btn.config(text="停止并保存")
        self._set_busy(True, keep_voice=True)
        self.status_label.config(text="正在加载模型并打开输入设备…")
        self.progress.start(10)
        language = self.language_var.get()
        if language == "auto":
            language = None
        self._voice_model = self.model_var.get()
        self._voice_language = language
        device_index = self._selected_device_index()

        def worker():
            try:
                self.voice_input.start(
                    callback=self._on_live_chunk,
                    model_size=self._voice_model,
                    language=self._voice_language,
                    device_index=device_index,
                    should_continue=lambda: not self._voice_cancel,
                )
                if self._voice_cancel:
                    return
                if not self.is_voice or not self.voice_input.is_running:
                    self.is_voice = False
                    self.root.after(0, self._reset_voice_ui)
                    return
                self.voice_ready = True
                self.root.after(0, lambda: self.status_label.config(text="正在听取语音…"))
            except Exception as e:
                self.is_voice = False
                self.voice_ready = False
                if self._voice_cancel:
                    return
                err = str(e)
                self.root.after(0, lambda m=err: messagebox.showerror("语音输入错误", m))
                self.root.after(0, self._reset_voice_ui)
                try:
                    self.voice_input.stop()
                except Exception:
                    pass

        self._voice_start_thread = threading.Thread(target=worker, daemon=True)
        self._voice_start_thread.start()

    def _stop_voice_input(self):
        if not self.is_voice:
            return
        self._voice_cancel = True
        self.voice_ready = False
        self.voice_btn.config(state=tk.DISABLED)
        self.status_label.config(text="正在保存语音…")
        start_thread = self._voice_start_thread

        def worker():
            if start_thread and start_thread.is_alive():
                start_thread.join()
            try:
                path = self.voice_input.stop()
            except Exception as e:
                self.is_voice = False
                err = str(e)
                self.root.after(0, lambda m=err: self._present_voice_result(None, "", m, False))
                return

            self.is_voice = False
            if not path:
                cancelled = not self.voice_input._capture_started
                self.root.after(0, lambda c=cancelled: self._present_voice_result(None, "", None, c))
                return

            self.current_audio_file = path
            self.root.after(0, lambda p=path: self.status_label.config(
                text=f"语音已保存，正在转录: {os.path.basename(p)}"
            ))
            try:
                transcript = self.transcriber.transcribe(
                    path,
                    model_size=self._voice_model,
                    language=self._voice_language,
                )
                final_text = (transcript or "").strip() or self._compose_live_text(include_interim=False).strip()
                self.current_transcript = final_text
                self.current_translation = ""
                self.root.after(
                    0,
                    lambda p=path, t=final_text: self._present_voice_result(p, t, None, False),
                )
            except Exception as e:
                preview = self._compose_live_text(include_interim=False).strip()
                self.current_transcript = preview
                err = f"语音文件已保存:\n{path}\n\n转录失败: {e}"
                self.root.after(
                    0,
                    lambda p=path, t=preview, m=err: self._present_voice_result(p, t, m, False),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _present_voice_result(self, path, transcript, error, cancelled):
        if transcript:
            self.current_transcript = transcript
            self.current_translation = ""
            self._show_transcript()
        if error:
            title = "转录错误" if path else "语音输入错误"
            messagebox.showerror(title, error)
            if path:
                self.status_label.config(text=f"语音已保存，转录失败: {os.path.basename(path)}")
            else:
                self.status_label.config(text="语音输入失败")
        elif not path:
            if cancelled:
                self.status_label.config(text="语音输入已取消")
            else:
                messagebox.showinfo("提示", "没有采集到有效语音")
                self.status_label.config(text="没有采集到有效语音")
        else:
            self._voice_saved(path, transcript)
        self._reset_voice_ui()

    def _voice_saved(self, path, transcript):
        if transcript:
            messagebox.showinfo(
                "语音输入完成",
                f"语音文件已保存:\n{path}\n\n转录文本已显示在原文区。",
            )
            self.status_label.config(text=f"已保存并转录: {path}")
        else:
            messagebox.showinfo(
                "已保存语音",
                f"语音文件已保存:\n{path}\n\n没有识别到文字。",
            )
            self.status_label.config(text=f"语音已保存: {path}")

    def _reset_voice_ui(self):
        self.progress.stop()
        self.voice_ready = False
        self.voice_btn.config(text="语音输入")
        self._set_busy(False)

    def start_translation(self):
        source = self.text_area.get("1.0", tk.END).strip()
        if not source:
            messagebox.showwarning("警告", "请先完成转录，再翻译")
            return
        if self.is_live or self.is_voice:
            messagebox.showinfo("提示", "请先停止语音听取再翻译")
            return
        src = self.language_var.get()
        tgt = self.target_lang_var.get()
        if src == tgt and src != "auto":
            messagebox.showinfo("提示", "识别语言与翻译目标相同，无需翻译")
            return
        self.status_label.config(text="正在翻译（需要网络）…")
        self.progress.start(10)
        self.translate_btn.config(state=tk.DISABLED)

        def worker():
            try:
                result = self.translator_engine.translate(source, source_lang=src, target_lang=tgt)
                self.current_transcript = source
                self.current_translation = result
                self.root.after(0, self._show_bilingual)
                src_name = Translator.get_language_name(src)
                tgt_name = Translator.get_language_name(tgt)
                self.root.after(0, lambda: self.status_label.config(
                    text=f"翻译完成：{src_name} → {tgt_name}"
                ))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("翻译错误", str(e)))
                self.root.after(0, lambda: self.status_label.config(text="翻译失败"))
            finally:
                self.root.after(0, self.progress.stop)
                self.root.after(0, lambda: self.translate_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _show_transcript(self):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", self.current_transcript)
        self.translation_area.delete("1.0", tk.END)
        self.save_btn.config(state=tk.NORMAL)

    def _show_bilingual(self):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", self.current_transcript)
        self.translation_area.delete("1.0", tk.END)
        self.translation_area.insert("1.0", self.current_translation)
        self.save_btn.config(state=tk.NORMAL)

    def save_markdown(self):
        transcript = self.text_area.get("1.0", tk.END).strip()
        translation = self.translation_area.get("1.0", tk.END).strip()
        if not transcript:
            messagebox.showwarning("警告", "没有可保存的内容")
            return
        if self.current_audio_file:
            default_name = Path(self.current_audio_file).stem + ".md"
            initial_dir = os.path.dirname(self.current_audio_file)
        else:
            default_name = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            initial_dir = str(Path.home() / "Documents")
        filename = filedialog.asksaveasfilename(
            title="保存 Markdown 文件",
            defaultextension=".md",
            initialfile=default_name,
            initialdir=initial_dir,
            filetypes=(("Markdown 文件", "*.md"), ("所有文件", "*.*")),
        )
        if not filename:
            return
        try:
            metadata = {
                "source_file": os.path.basename(self.current_audio_file) if self.current_audio_file else "实时/麦克风",
                "model": self.model_var.get(),
                "language": self.language_var.get(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if translation:
                metadata["target_language"] = self.target_lang_var.get()
            self.md_writer.save(
                filename,
                transcript,
                metadata=metadata,
                translation=translation or None,
                source_lang=self.language_var.get(),
                target_lang=self.target_lang_var.get() if translation else None,
            )
            messagebox.showinfo("成功", f"已保存到:\n{filename}")
            self.status_label.config(text=f"已保存: {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("保存错误", f"保存失败: {e}")

    def clear_text(self):
        if self.is_live or self.is_voice:
            messagebox.showinfo("提示", "请先停止当前的语音听取")
            return
        if messagebox.askyesno("确认", "确定要清空原文和译文吗？"):
            self.text_area.delete("1.0", tk.END)
            self.translation_area.delete("1.0", tk.END)
            self.current_transcript = ""
            self.current_translation = ""
            self.live_final_parts = []
            self.current_audio_file = None
            self.save_btn.config(state=tk.DISABLED)
            self.transcribe_btn.config(state=tk.DISABLED)
            self.status_label.config(text="就绪")

    def _set_busy(self, busy, keep_record=False, keep_live=False, keep_voice=False):
        state = tk.DISABLED if busy else tk.NORMAL
        self.select_file_btn.config(state=state)
        if not keep_record:
            self.record_btn.config(state=state)
        self.transcribe_btn.config(
            state=tk.DISABLED if busy else (tk.NORMAL if self.current_audio_file else tk.DISABLED)
        )
        if not keep_live:
            self.live_btn.config(state=state)
        if not keep_voice:
            self.voice_btn.config(state=state)
        self.device_combo.config(state=tk.DISABLED if busy else "readonly")
        self.translate_btn.config(state=tk.DISABLED if busy else tk.NORMAL)

    def on_closing(self):
        if self.is_recording:
            try:
                self.recorder.stop_recording()
            except Exception:
                pass
        if self.is_live:
            try:
                self.live_transcriber.stop()
            except Exception:
                pass
        if self.is_voice:
            self._voice_cancel = True
            try:
                self.voice_input.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
