#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI — P0：三模式 Tab、状态机、引导、设置（识别/翻译/存储/关于）、路径持久化。
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from .config import AppConfig, load_config, save_config
from .live_transcriber import LiveTranscriber
from .markdown_writer import MarkdownWriter
from .recorder import AudioRecorder
from .transcriber import AudioTranscriber, audio_duration_seconds, wants_progress_mode
from .translator import Translator
from .voice_input import VoiceInput, list_input_devices


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    LIVE = "live"
    VOICE = "voice"
    VOICE_STARTING = "voice_starting"
    TRANSLATING = "translating"
    MODEL_LOADING = "model_loading"


# 状态栏文案 + 是否允许停止
STATE_META = {
    AppState.IDLE: ("就绪", False),
    AppState.RECORDING: ("正在录音… 可点「停止」", True),
    AppState.TRANSCRIBING: ("正在转写…", False),
    AppState.LIVE: ("实时转录中… 可点「停止」", True),
    AppState.VOICE: ("语音输入听取中… 可点「停止」", True),
    AppState.VOICE_STARTING: ("正在启动语音输入… 可点「停止」取消", True),
    AppState.TRANSLATING: ("正在翻译（需网络）…", False),
    AppState.MODEL_LOADING: ("正在预加载模型…", False),
}


GUIDE_PAGES = [
    (
        "三模式分别干什么",
        "① 语音输入：听麦克风 → 停止后整段存 WAV 并转写。\n"
        "② 实时转录：边说边出字（约每几秒一段预览）。\n"
        "③ 文件转写：选已有音频文件再转写。\n\n"
        "主按钮：各模式 Tab 内的「开始 / 停止」；下方「翻译」把原文译成目标语言。",
    ),
    (
        "时延与模型",
        "默认模型 tiny + 启动预加载，实时短句「停→出字」目标尽量 ≤1–2 秒。\n"
        "整段文件 / 长于约 15 秒 / 选用 base 及以上：走进度条，不承诺 1 秒。\n"
        "真流式边说边出、GPU、云 ASR 本轮不做。",
    ),
    (
        "设置与路径",
        "设置分四块：识别 / 翻译 / 存储 / 关于。\n"
        "存储可改 MD 导出目录与 WAV 录音目录，会记住。\n"
        "翻译默认 Google（免费需联网）；DeepL 等灰显预留。\n"
        "「AI 辅助识别」灰显预留，本轮不接、不花钱。\n\n"
        "随时可在设置 → 关于 里「再看引导」。",
    ),
]


class GuideDialog(tk.Toplevel):
    def __init__(self, master, on_done=None):
        super().__init__(master)
        self.title("使用引导 / 功能介绍")
        self.geometry("520x360")
        self.transient(master)
        self.grab_set()
        self.on_done = on_done
        self.page = 0
        self.title_var = tk.StringVar()
        self.body = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=12)
        ttk.Label(self, textvariable=self.title_var, font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor=tk.W, padx=16, pady=(16, 8)
        )
        self.body.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
        self.body.configure(state=tk.DISABLED)
        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, padx=16, pady=12)
        ttk.Button(btn_row, text="跳过", command=self._finish).pack(side=tk.LEFT)
        self.prev_btn = ttk.Button(btn_row, text="上一页", command=self._prev)
        self.prev_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.next_btn = ttk.Button(btn_row, text="下一页", command=self._next)
        self.next_btn.pack(side=tk.RIGHT)
        self._render()

    def _render(self):
        title, body = GUIDE_PAGES[self.page]
        self.title_var.set(f"{self.page + 1}/{len(GUIDE_PAGES)}  {title}")
        self.body.configure(state=tk.NORMAL)
        self.body.delete("1.0", tk.END)
        self.body.insert("1.0", body)
        self.body.configure(state=tk.DISABLED)
        self.prev_btn.config(state=tk.NORMAL if self.page > 0 else tk.DISABLED)
        self.next_btn.config(text="完成" if self.page >= len(GUIDE_PAGES) - 1 else "下一页")

    def _prev(self):
        if self.page > 0:
            self.page -= 1
            self._render()

    def _next(self):
        if self.page >= len(GUIDE_PAGES) - 1:
            self._finish()
        else:
            self.page += 1
            self._render()

    def _finish(self):
        if self.on_done:
            self.on_done()
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: "SpeechToMdApp"):
        super().__init__(app.root)
        self.app = app
        self.title("设置")
        self.geometry("560x420")
        self.transient(app.root)
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # —— 识别 ——
        tab_asr = ttk.Frame(nb, padding=10)
        nb.add(tab_asr, text="识别")
        ttk.Label(tab_asr, text="模型大小:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.model_var = tk.StringVar(value=app.model_var.get())
        ttk.Combobox(
            tab_asr,
            textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large"],
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(tab_asr, text="tiny=速度优先（1s 目标）；base+=更准更慢", foreground="gray").grid(
            row=1, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Label(tab_asr, text="识别语言:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.language_var = tk.StringVar(value=app.language_var.get())
        ttk.Combobox(
            tab_asr,
            textvariable=self.language_var,
            values=["auto", "zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=14,
        ).grid(row=2, column=1, sticky=tk.W)
        ttk.Label(tab_asr, text="输入设备:").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.device_var = tk.StringVar(value=app.device_var.get())
        self.device_combo = ttk.Combobox(tab_asr, textvariable=self.device_var, state="readonly", width=40)
        self.device_combo.grid(row=3, column=1, sticky=tk.W)
        self.device_combo["values"] = app.device_combo["values"]
        ttk.Button(tab_asr, text="刷新设备", command=self._refresh_devices).grid(row=3, column=2, padx=6)
        self.ai_var = tk.BooleanVar(value=False)
        ai_chk = ttk.Checkbutton(
            tab_asr,
            text="AI 辅助识别（预留口，本轮不做）",
            variable=self.ai_var,
            state=tk.DISABLED,
        )
        ai_chk.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(12, 0))

        # —— 翻译 ——
        tab_tr = ttk.Frame(nb, padding=10)
        nb.add(tab_tr, text="翻译")
        ttk.Label(tab_tr, text="翻译目标:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.target_lang_var = tk.StringVar(value=app.target_lang_var.get())
        ttk.Combobox(
            tab_tr,
            textvariable=self.target_lang_var,
            values=["zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(tab_tr, text="提供商:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.translator_var = tk.StringVar(value="google")
        self.tr_combo = ttk.Combobox(tab_tr, textvariable=self.translator_var, state="readonly", width=28)
        # 仅 Google 可选；其它写入 values 但用绑定拦截
        self._tr_labels = {
            "google": "Google（免费）",
            "deepl": "DeepL（预留）",
            "other": "其它（预留）",
        }
        self.tr_combo["values"] = ["Google（免费）", "DeepL（预留）", "其它（预留）"]
        self.tr_combo.set("Google（免费）")
        self.tr_combo.grid(row=1, column=1, sticky=tk.W)
        self.tr_combo.bind("<<ComboboxSelected>>", self._on_tr_select)
        ttk.Label(tab_tr, text="本轮仅 Google 可用；DeepL/其它灰显预留。", foreground="gray").grid(
            row=2, column=0, columnspan=2, sticky=tk.W, pady=4
        )

        # —— 存储 ——
        tab_st = ttk.Frame(nb, padding=10)
        nb.add(tab_st, text="存储")
        ttk.Label(tab_st, text="MD 导出默认目录:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.md_dir_var = tk.StringVar(value=app.cfg.md_export_dir)
        ttk.Entry(tab_st, textvariable=self.md_dir_var, width=42).grid(row=0, column=1, sticky=tk.W)
        ttk.Button(tab_st, text="浏览…", command=lambda: self._browse(self.md_dir_var)).grid(row=0, column=2, padx=4)
        ttk.Label(tab_st, text="WAV 录音默认目录:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.wav_dir_var = tk.StringVar(value=app.cfg.wav_record_dir)
        ttk.Entry(tab_st, textvariable=self.wav_dir_var, width=42).grid(row=1, column=1, sticky=tk.W)
        ttk.Button(tab_st, text="浏览…", command=lambda: self._browse(self.wav_dir_var)).grid(row=1, column=2, padx=4)
        ttk.Label(tab_st, text="重启后仍记住上述路径。", foreground="gray").grid(
            row=2, column=0, columnspan=3, sticky=tk.W, pady=8
        )

        # —— 关于 ——
        tab_ab = ttk.Frame(nb, padding=10)
        nb.add(tab_ab, text="关于")
        about = (
            "lisen-to-text · P0 自用\n"
            "默认 tiny + 预加载；实时短句停→出字目标 ≤1–2s。\n"
            "整段文件不承诺 1s。翻译 Google；AI 辅助仅留口。\n\n"
            "依赖自检："
        )
        ttk.Label(tab_ab, text=about, justify=tk.LEFT).pack(anchor=tk.W)
        self.dep_label = ttk.Label(tab_ab, text="（点击下方检查）", foreground="gray")
        self.dep_label.pack(anchor=tk.W, pady=4)
        row = ttk.Frame(tab_ab)
        row.pack(anchor=tk.W, pady=8)
        ttk.Button(row, text="检查依赖", command=self._check_deps).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row, text="再看引导", command=self._reopen_guide).pack(side=tk.LEFT)

        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(bottom, text="保存", command=self._save).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bottom, text="取消", command=self.destroy).pack(side=tk.RIGHT)

    def _on_tr_select(self, _evt=None):
        label = self.tr_combo.get()
        if "预留" in label:
            messagebox.showinfo("预留", "该提供商本轮未接入，仍使用 Google（免费）。", parent=self)
            self.tr_combo.set("Google（免费）")
            self.translator_var.set("google")
        else:
            self.translator_var.set("google")

    def _browse(self, var: tk.StringVar):
        path = filedialog.askdirectory(title="选择目录", initialdir=var.get() or str(Path.home()))
        if path:
            var.set(path)

    def _refresh_devices(self):
        self.app._load_input_devices()
        self.device_combo["values"] = self.app.device_combo["values"]
        if not self.app.device_combo["values"] or self.app.device_combo["values"] == ("系统默认",):
            messagebox.showwarning("设备", "未检测到输入设备。请检查麦克风权限后重试。", parent=self)
        if self.device_var.get() not in self.device_combo["values"]:
            self.device_var.set("系统默认")

    def _check_deps(self):
        try:
            from check_dependencies import summarize_dependencies

            text = summarize_dependencies()
        except Exception as e:
            text = f"自检失败: {e}"
        self.dep_label.config(text=text, foreground="black")

    def _reopen_guide(self):
        self.destroy()
        self.app.show_guide(force=True)

    def _save(self):
        self.app.model_var.set(self.model_var.get())
        self.app.language_var.set(self.language_var.get())
        self.app.target_lang_var.set(self.target_lang_var.get())
        self.app.device_var.set(self.device_var.get())
        self.app.cfg.model_size = self.model_var.get()
        self.app.cfg.language = self.language_var.get()
        self.app.cfg.target_lang = self.target_lang_var.get()
        self.app.cfg.translator_backend = "google"
        self.app.cfg.md_export_dir = self.md_dir_var.get().strip() or self.app.cfg.md_export_dir
        self.app.cfg.wav_record_dir = self.wav_dir_var.get().strip() or self.app.cfg.wav_record_dir
        self.app.cfg.input_device_label = self.device_var.get()
        self.app.cfg.ai_assist_enabled = False
        self.app.cfg.ensure_dirs()
        self.app.recorder.set_output_dir(self.app.cfg.wav_record_dir)
        if hasattr(self.app.voice_input, "set_output_dir"):
            self.app.voice_input.set_output_dir(self.app.cfg.wav_record_dir)
        self.app.translator_engine.set_backend("google")
        self.app._persist_config()
        self.app._update_latency_hint()
        self.destroy()


class SpeechToMdApp:
    """语音转文字主窗口。"""

    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("语音转文字工具 — 语音输入 / 实时转录 / 文件转写")
        self.root.geometry("1100x820")
        self.root.resizable(True, True)

        self.transcriber = AudioTranscriber()
        self.recorder = AudioRecorder(output_dir=self.cfg.wav_record_dir)
        self.md_writer = MarkdownWriter()
        self.live_transcriber = LiveTranscriber(self.transcriber)
        self.voice_input = VoiceInput(self.transcriber)
        if hasattr(self.voice_input, "set_output_dir"):
            self.voice_input.set_output_dir(self.cfg.wav_record_dir)
        self.translator_engine = Translator(self.cfg.translator_backend)

        self.state = AppState.IDLE
        self._device_map = {"系统默认": None}
        self.current_transcript = ""
        self.current_translation = ""
        self.current_audio_file = None
        self.live_final_parts = []
        self.live_interim = ""
        self._voice_cancel = False
        self._voice_start_thread = None
        self.voice_ready = False

        self.model_var = tk.StringVar(value=self.cfg.model_size)
        self.language_var = tk.StringVar(value=self.cfg.language)
        self.target_lang_var = tk.StringVar(value=self.cfg.target_lang)
        self.device_var = tk.StringVar(value=self.cfg.input_device_label or "系统默认")

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(200, self._poll_live_ui)
        self.root.after(400, self._after_start)

    # —— 启动 ——
    def _after_start(self):
        if not self.cfg.guide_seen:
            self.show_guide(force=True)
        self._preload_model()

    def _preload_model(self):
        size = self.model_var.get() or "tiny"

        def worker():
            self.root.after(0, lambda: self._set_state(AppState.MODEL_LOADING, f"预加载模型 {size}…"))
            try:
                self.transcriber.load_model(size)
                self.root.after(0, lambda: self._set_state(AppState.IDLE, f"模型已就绪（{size}）"))
            except Exception as e:
                self.root.after(0, lambda: self._set_state(AppState.IDLE, f"模型预加载失败（可稍后重试）: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def show_guide(self, force: bool = False):
        def done():
            self.cfg.guide_seen = True
            self._persist_config()

        GuideDialog(self.root, on_done=done)

    def _persist_config(self):
        self.cfg.model_size = self.model_var.get()
        self.cfg.language = self.language_var.get()
        self.cfg.target_lang = self.target_lang_var.get()
        self.cfg.input_device_label = self.device_var.get()
        save_config(self.cfg)

    # —— 状态机 ——
    def _set_state(self, state: AppState, detail: Optional[str] = None):
        self.state = state
        base, can_stop = STATE_META[state]
        text = detail or base
        if can_stop and "停止" not in text:
            text = f"{text} · 可停止"
        self.status_label.config(text=text)
        self.stop_hint_var.set("停止：可用" if can_stop else "停止：不可用")
        self._apply_busy_from_state()

    def _apply_busy_from_state(self):
        busy = self.state != AppState.IDLE
        keep_voice = self.state in (AppState.VOICE, AppState.VOICE_STARTING)
        keep_live = self.state == AppState.LIVE
        keep_record = self.state == AppState.RECORDING
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
        self.settings_btn.config(state=tk.DISABLED if busy and self.state not in (AppState.IDLE,) else tk.NORMAL)

    # —— 布局 ——
    def create_widgets(self):
        main = ttk.Frame(self.root, padding="10")
        main.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        main.rowconfigure(4, weight=1)

        head = ttk.Frame(main)
        head.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        ttk.Label(head, text="语音转文字工具", font=("Microsoft YaHei UI", 14, "bold")).pack(side=tk.LEFT)
        self.settings_btn = ttk.Button(head, text="设置", command=self.open_settings, width=8)
        self.settings_btn.pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(head, text="功能介绍", command=lambda: self.show_guide(True), width=10).pack(side=tk.RIGHT)

        # 三模式 Tab
        self.mode_nb = ttk.Notebook(main)
        self.mode_nb.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=4)

        tab_voice = ttk.Frame(self.mode_nb, padding=8)
        tab_live = ttk.Frame(self.mode_nb, padding=8)
        tab_file = ttk.Frame(self.mode_nb, padding=8)
        self.mode_nb.add(tab_voice, text="语音输入")
        self.mode_nb.add(tab_live, text="实时转录")
        self.mode_nb.add(tab_file, text="文件转写")

        ttk.Label(tab_voice, text="听取麦克风 → 停止后保存 WAV 并转写。", foreground="gray").pack(anchor=tk.W)
        self.voice_btn = ttk.Button(tab_voice, text="开始语音输入", command=self.toggle_voice_input, width=18)
        self.voice_btn.pack(anchor=tk.W, pady=6)

        ttk.Label(tab_live, text="边说边出字预览；停止可定稿。短句目标 ≤1–2s（tiny 已加载时）。", foreground="gray").pack(
            anchor=tk.W
        )
        self.live_btn = ttk.Button(tab_live, text="开始实时转录", command=self.toggle_live, width=18)
        self.live_btn.pack(anchor=tk.W, pady=6)

        ttk.Label(tab_file, text="选择音频文件后转写；长音频走进度条，不承诺 1 秒。", foreground="gray").pack(anchor=tk.W)
        row_f = ttk.Frame(tab_file)
        row_f.pack(anchor=tk.W, pady=6)
        self.select_file_btn = ttk.Button(row_f, text="选择音频文件", command=self.select_audio_file, width=16)
        self.select_file_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.record_btn = ttk.Button(row_f, text="开始录音", command=self.toggle_recording, width=12)
        self.record_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.transcribe_btn = ttk.Button(
            row_f, text="开始转写", command=self.start_transcription, width=12, state=tk.DISABLED
        )
        self.transcribe_btn.pack(side=tk.LEFT)

        # 快捷设置条
        quick = ttk.LabelFrame(main, text="快捷设置", padding=8)
        quick.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=4)
        ttk.Label(quick, text="模型:").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(
            quick,
            textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large"],
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky=tk.W, padx=(4, 12))
        ttk.Label(quick, text="语言:").grid(row=0, column=2, sticky=tk.W)
        ttk.Combobox(
            quick,
            textvariable=self.language_var,
            values=["auto", "zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=8,
        ).grid(row=0, column=3, sticky=tk.W, padx=(4, 12))
        ttk.Label(quick, text="翻译目标:").grid(row=0, column=4, sticky=tk.W)
        ttk.Combobox(
            quick,
            textvariable=self.target_lang_var,
            values=["zh", "en", "ja", "ko", "fr", "de", "es"],
            state="readonly",
            width=8,
        ).grid(row=0, column=5, sticky=tk.W, padx=(4, 12))
        ttk.Label(quick, text="输入设备:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.device_combo = ttk.Combobox(quick, textvariable=self.device_var, state="readonly", width=50)
        self.device_combo.grid(row=1, column=1, columnspan=4, sticky=tk.W, pady=(6, 0))
        ttk.Button(quick, text="刷新", command=self._refresh_devices_ui, width=8).grid(
            row=1, column=5, sticky=tk.W, pady=(6, 0)
        )
        self.latency_hint = ttk.Label(quick, text="", foreground="gray")
        self.latency_hint.grid(row=2, column=0, columnspan=6, sticky=tk.W, pady=(6, 0))
        self.model_var.trace_add("write", lambda *_: self._update_latency_hint())
        self._load_input_devices()
        self._update_latency_hint()

        # 状态栏
        status_row = ttk.Frame(main)
        status_row.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=4)
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, text="就绪", font=("Microsoft YaHei UI", 10))
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        self.stop_hint_var = tk.StringVar(value="停止：不可用")
        ttk.Label(status_row, textvariable=self.stop_hint_var, foreground="gray").grid(row=0, column=1, padx=8)
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=200)
        self.progress.grid(row=0, column=2, sticky=tk.E)

        # 文本区（放在状态栏之上：调整 grid）
        src = ttk.LabelFrame(main, text="原文 / 实时转录", padding=5)
        src.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(8, 4))
        src.columnconfigure(0, weight=1)
        src.rowconfigure(0, weight=1)
        self.text_area = scrolledtext.ScrolledText(src, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=12)
        self.text_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        dst = ttk.LabelFrame(main, text="译文（与原文对照）", padding=5)
        dst.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(4, 4))
        dst.columnconfigure(0, weight=1)
        dst.rowconfigure(0, weight=1)
        self.translation_area = scrolledtext.ScrolledText(
            dst, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=8
        )
        self.translation_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 底部操作
        bottom = ttk.Frame(main)
        bottom.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=6)
        self.translate_btn = ttk.Button(bottom, text="翻译（双语）", command=self.start_translation, width=14)
        self.translate_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.retry_translate_btn = ttk.Button(
            bottom, text="重试翻译", command=self.start_translation, width=10, state=tk.DISABLED
        )
        self.retry_translate_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.save_btn = ttk.Button(
            bottom, text="保存为 Markdown（双语）", command=self.save_markdown, width=24, state=tk.DISABLED
        )
        self.save_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bottom, text="清空", command=self.clear_text, width=10).pack(side=tk.LEFT)

        self._set_state(AppState.IDLE)

    def open_settings(self):
        if self.state not in (AppState.IDLE, AppState.MODEL_LOADING):
            messagebox.showinfo("提示", "请先停止当前任务再打开设置")
            return
        SettingsDialog(self)

    def _update_latency_hint(self):
        m = self.model_var.get()
        if m == "tiny":
            self.latency_hint.config(text="时延：tiny — 实时短句停→出字目标 ≤1–2s（模型已预加载时）")
        else:
            self.latency_hint.config(text=f"时延：{m} — 非 1s 目标，长段/整段走进度条")

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
        if len(labels) <= 1:
            self.status_label.config(text="未检测到输入设备，请检查麦克风后点「刷新」")

    def _refresh_devices_ui(self):
        self._load_input_devices()
        if len(self.device_combo["values"]) <= 1:
            messagebox.showwarning("设备", "未检测到输入设备。请到系统设置开启麦克风权限后重试。")

    def _selected_device_index(self):
        return self._device_map.get(self.device_var.get())

    # —— 文件 / 录音 ——
    def select_audio_file(self):
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
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
        if self.state == AppState.RECORDING:
            self.recorder.stop_recording()
            return
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
            return
        self._set_state(AppState.RECORDING)
        self.record_btn.config(text="停止录音")
        self.progress.start(10)
        self._record_device = self._selected_device_index()
        threading.Thread(target=self.record_audio, daemon=True).start()

    def record_audio(self):
        try:
            output_file = self.recorder.start_recording(
                device_index=self._record_device,
                output_dir=self.cfg.wav_record_dir,
            )
            if output_file:
                self.current_audio_file = output_file

                def done():
                    self.progress.stop()
                    self.record_btn.config(text="开始录音")
                    self._set_state(AppState.IDLE, f"录音完成: {os.path.basename(output_file)}")
                    self.transcribe_btn.config(state=tk.NORMAL)

                self.root.after(0, done)
        except Exception as e:
            def fail():
                self.progress.stop()
                self.record_btn.config(text="开始录音")
                self._set_state(AppState.IDLE, "录音失败")
                messagebox.showerror("录音错误", f"录音失败: {e}")

            self.root.after(0, fail)

    def start_transcription(self):
        if not self.current_audio_file:
            messagebox.showwarning("警告", "请先选择或录制音频")
            return
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
            return
        self._set_state(AppState.TRANSCRIBING)
        self.progress.start(10)
        path = self.current_audio_file
        model = self.model_var.get()
        lang = self.language_var.get()
        lang_arg = None if lang == "auto" else lang
        dur = audio_duration_seconds(path)
        progress_mode = wants_progress_mode(model, dur)

        def worker():
            try:
                if progress_mode:
                    msg = f"转写中（进度模式，不承诺 1s）… 约 {dur:.0f}s" if dur else "转写中（进度模式，不承诺 1s）…"
                else:
                    msg = "转写中（短句体感目标）…"
                self.root.after(0, lambda: self.status_label.config(text=msg))
                text = self.transcriber.transcribe(path, model_size=model, language=lang_arg, beam_size=1)
                self.current_transcript = text or ""
                self.current_translation = ""

                def ok():
                    self.progress.stop()
                    self._show_transcript()
                    self._set_state(AppState.IDLE, "转写完成")

                self.root.after(0, ok)
            except Exception as e:
                def fail():
                    self.progress.stop()
                    self._set_state(AppState.IDLE, "转写失败")
                    messagebox.showerror("转写错误", str(e))

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    # —— 实时 ——
    def toggle_live(self):
        if self.state == AppState.LIVE:
            self._stop_live()
            return
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
            return
        self._start_live()

    def _start_live(self):
        self.live_final_parts = []
        self.live_interim = ""
        self.current_translation = ""
        model = self.model_var.get()
        lang = self.language_var.get()
        lang_arg = None if lang == "auto" else lang
        device = self._selected_device_index()
        self._set_state(AppState.LIVE)
        self.live_btn.config(text="停止实时转录")
        self.progress.start(10)

        def worker():
            try:
                self.live_transcriber.start(
                    callback=self._on_live_chunk,
                    model_size=model,
                    language=lang_arg,
                    device_index=device,
                )
            except Exception as e:
                def fail():
                    self.progress.stop()
                    self.live_btn.config(text="开始实时转录")
                    self._set_state(AppState.IDLE, "实时转录启动失败")
                    messagebox.showerror("实时转录错误", str(e))

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_live(self):
        try:
            self.live_transcriber.stop()
        except Exception:
            pass
        self.progress.stop()
        self.live_btn.config(text="开始实时转录")
        text = self._compose_live_text(include_interim=False).strip()
        if text:
            self.current_transcript = text
            self._show_transcript()
        self._set_state(AppState.IDLE, "实时转录已停止")

    def _on_live_chunk(self, text: str, is_final: bool):
        def apply():
            if is_final:
                if text:
                    self.live_final_parts.append(text)
                self.live_interim = ""
            else:
                self.live_interim = text or ""
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", self._compose_live_text(True))

        self.root.after(0, apply)

    def _compose_live_text(self, include_interim: bool = True) -> str:
        parts = list(self.live_final_parts)
        if include_interim and self.live_interim:
            parts.append(self.live_interim)
        return "\n".join(p for p in parts if p)

    def _poll_live_ui(self):
        # 轻量轮询占位（兼容旧逻辑）；状态机已驱动按钮
        self.root.after(200, self._poll_live_ui)

    # —— 语音输入 ——
    def toggle_voice_input(self):
        if self.state in (AppState.VOICE, AppState.VOICE_STARTING):
            self._stop_voice_input()
            return
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
            return
        self._start_voice_input()

    def _start_voice_input(self):
        self._voice_cancel = False
        self.voice_ready = False
        self.live_final_parts = []
        self.live_interim = ""
        self.current_translation = ""
        self._voice_model = self.model_var.get()
        self._voice_language = None if self.language_var.get() == "auto" else self.language_var.get()
        device = self._selected_device_index()
        self._set_state(AppState.VOICE_STARTING)
        self.voice_btn.config(text="停止语音输入")
        self.progress.start(10)

        def worker():
            try:
                self.voice_input.start(
                    callback=self._on_live_chunk,
                    model_size=self._voice_model,
                    language=self._voice_language,
                    device_index=device,
                    should_continue=lambda: not self._voice_cancel,
                )
                if self._voice_cancel:
                    try:
                        self.voice_input.stop()
                    except Exception:
                        pass
                    self.root.after(0, self._reset_voice_ui)
                    return
                self.voice_ready = True

                def ready():
                    self._set_state(AppState.VOICE, "语音输入听取中… 可点「停止」")

                self.root.after(0, ready)
            except Exception as e:
                err = str(e)

                def fail():
                    messagebox.showerror("语音输入错误", err)
                    self._reset_voice_ui()

                self.root.after(0, fail)
                try:
                    self.voice_input.stop()
                except Exception:
                    pass

        self._voice_start_thread = threading.Thread(target=worker, daemon=True)
        self._voice_start_thread.start()

    def _stop_voice_input(self):
        if self.state not in (AppState.VOICE, AppState.VOICE_STARTING):
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
                if hasattr(self.voice_input, "set_output_dir"):
                    self.voice_input.set_output_dir(self.cfg.wav_record_dir)
                path = self.voice_input.stop()
            except Exception as e:
                self.root.after(0, lambda: self._present_voice_result(None, "", str(e), False))
                return
            if not path:
                cancelled = not getattr(self.voice_input, "_capture_started", False)
                self.root.after(0, lambda c=cancelled: self._present_voice_result(None, "", None, c))
                return
            self.current_audio_file = path
            self.root.after(
                0,
                lambda p=path: self.status_label.config(text=f"语音已保存，正在转录: {os.path.basename(p)}"),
            )
            try:
                dur = audio_duration_seconds(path)
                progress_mode = wants_progress_mode(self._voice_model, dur)
                if progress_mode:
                    self.root.after(0, lambda: self.status_label.config(text="转写中（进度模式，不承诺 1s）…"))
                transcript = self.transcriber.transcribe(
                    path,
                    model_size=self._voice_model,
                    language=self._voice_language,
                    beam_size=1,
                )
                final_text = (transcript or "").strip() or self._compose_live_text(include_interim=False).strip()
                self.current_transcript = final_text
                self.current_translation = ""
                self.root.after(0, lambda p=path, t=final_text: self._present_voice_result(p, t, None, False))
            except Exception as e:
                preview = self._compose_live_text(include_interim=False).strip()
                self.current_transcript = preview
                err = f"语音文件已保存:\n{path}\n\n转录失败: {e}"
                self.root.after(0, lambda p=path, t=preview, m=err: self._present_voice_result(p, t, m, False))

        threading.Thread(target=worker, daemon=True).start()

    def _present_voice_result(self, path, transcript, error, cancelled):
        if transcript:
            self.current_transcript = transcript
            self.current_translation = ""
            self._show_transcript()
        if error:
            title = "转录错误" if path else "语音输入错误"
            messagebox.showerror(title, error)
            self._set_state(AppState.IDLE, "语音输入失败" if not path else f"语音已保存，转录失败")
        elif not path:
            if cancelled:
                self._set_state(AppState.IDLE, "语音输入已取消")
            else:
                messagebox.showinfo("提示", "没有采集到有效语音")
                self._set_state(AppState.IDLE, "没有采集到有效语音")
        else:
            if transcript:
                messagebox.showinfo(
                    "语音输入完成",
                    f"语音文件已保存:\n{path}\n\n转录文本已显示在原文区",
                )
                self._set_state(AppState.IDLE, f"已保存并转录: {os.path.basename(path)}")
            else:
                messagebox.showinfo("已保存语音", f"语音文件已保存:\n{path}\n\n没有识别到文字")
                self._set_state(AppState.IDLE, f"语音已保存: {os.path.basename(path)}")
        self._reset_voice_ui()

    def _reset_voice_ui(self):
        self.progress.stop()
        self.voice_ready = False
        self.voice_btn.config(text="开始语音输入", state=tk.NORMAL)
        if self.state in (AppState.VOICE, AppState.VOICE_STARTING):
            self._set_state(AppState.IDLE)

    # —— 翻译 ——
    def start_translation(self):
        source = self.text_area.get("1.0", tk.END).strip()
        if not source:
            messagebox.showwarning("警告", "请先完成转录，再翻译")
            return
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务再翻译")
            return
        src = self.language_var.get()
        tgt = self.target_lang_var.get()
        if src == tgt and src != "auto":
            messagebox.showinfo("提示", "识别语言与翻译目标相同，无需翻译")
            return
        self._set_state(AppState.TRANSLATING)
        self.progress.start(10)
        self.retry_translate_btn.config(state=tk.DISABLED)

        def worker():
            try:
                result = self.translator_engine.translate(source, source_lang=src, target_lang=tgt)
                self.current_transcript = source
                self.current_translation = result

                def ok():
                    self.progress.stop()
                    self._show_bilingual()
                    src_name = Translator.get_language_name(src)
                    tgt_name = Translator.get_language_name(tgt)
                    self._set_state(AppState.IDLE, f"翻译完成：{src_name} → {tgt_name}")
                    self.retry_translate_btn.config(state=tk.DISABLED)

                self.root.after(0, ok)
            except Exception as e:
                # E5：保留原文 + 可重试
                self.current_transcript = source

                def fail():
                    self.progress.stop()
                    self.text_area.delete("1.0", tk.END)
                    self.text_area.insert("1.0", source)
                    self._set_state(AppState.IDLE, "翻译失败（原文已保留，可重试）")
                    self.retry_translate_btn.config(state=tk.NORMAL)
                    messagebox.showerror("翻译错误", str(e))

                self.root.after(0, fail)

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
        else:
            default_name = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        initial_dir = self.cfg.md_export_dir or str(Path.home() / "Documents")
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
            # 记住用户选的目录
            self.cfg.md_export_dir = str(Path(filename).parent)
            self._persist_config()
            messagebox.showinfo("成功", f"已保存到:\n{filename}")
            self.status_label.config(text=f"已保存: {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("保存错误", f"保存失败: {e}")

    def clear_text(self):
        if self.state != AppState.IDLE:
            messagebox.showinfo("提示", "请先停止当前任务")
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
            self.retry_translate_btn.config(state=tk.DISABLED)
            self._set_state(AppState.IDLE)

    def on_closing(self):
        self._voice_cancel = True
        if self.state == AppState.RECORDING:
            try:
                self.recorder.stop_recording()
            except Exception:
                pass
        if self.state == AppState.LIVE:
            try:
                self.live_transcriber.stop()
            except Exception:
                pass
        if self.state in (AppState.VOICE, AppState.VOICE_STARTING):
            try:
                self.voice_input.stop()
            except Exception:
                pass
        try:
            self._persist_config()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
