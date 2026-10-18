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
    AppState.RECORDING: ("正在录音… · 可点「停止」", True),
    AppState.TRANSCRIBING: ("正在转写… · 请稍候", False),
    AppState.LIVE: ("正在实时转写… · 可点「停止」", True),
    AppState.VOICE: ("正在监听… · 可点「停止并转写」", True),
    AppState.VOICE_STARTING: ("正在启动监听… · 可点「停止并转写」取消", True),
    AppState.TRANSLATING: ("正在翻译（需网络）… · 请稍候", False),
    AppState.MODEL_LOADING: ("正在预加载模型… · 请稍候", False),
}

NEXT_HINT = {0: "开始监听", 1: "选择音频文件", 2: "开始实时转写"}


GUIDE_PAGES = [
    (
        "三模式分别干什么",
        "① 语音输入：点「开始监听」→「停止并转写」，整段存 WAV 并转写。\n"
        "② 文件转写：选已有音频文件再「开始转写」。\n"
        "③ 实时转写：边说边出字（约每几秒一段预览）。\n\n"
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
    """听写对照主窗口。"""

    def __init__(self, screenshot=None):
        self.screenshot = screenshot  # dev: (tab_index, show_translation, out_path)
        self.cfg = load_config()
        if screenshot:
            self.cfg.guide_seen = True
        self.root = tk.Tk()
        self.root.title("Listen to Text · 听写对照")
        self.root.geometry("1000x760")
        self.root.minsize(1000, 720)
        self._init_styles()

        self.transcriber = AudioTranscriber()
        self.recorder = AudioRecorder(output_dir=self.cfg.wav_record_dir)
        self.md_writer = MarkdownWriter()
        self.live_transcriber = LiveTranscriber(self.transcriber)
        self.voice_input = VoiceInput(self.transcriber)
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
        self._translate_failed = False

        self.model_var = tk.StringVar(value=self.cfg.model_size)
        self.language_var = tk.StringVar(value=self.cfg.language)
        self.target_lang_var = tk.StringVar(value=self.cfg.target_lang)
        self.device_var = tk.StringVar(value=self.cfg.input_device_label or "系统默认")
        self.show_translation_var = tk.BooleanVar(value=False)

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        if screenshot:
            self.root.after(300, self._do_screenshot)
        else:
            self.root.after(400, self._after_start)

    def _init_styles(self):
        st = ttk.Style(self.root)
        f = "Microsoft YaHei UI"
        st.configure(".", font=(f, 10))
        st.configure("TButton", font=(f, 10), padding=(10, 4))
        st.configure("Primary.TButton", font=(f, 11, "bold"), padding=(16, 6))
        st.configure("TNotebook.Tab", font=(f, 11), padding=(14, 5))
        st.configure("TLabelframe.Label", font=(f, 9))
        st.configure("Header.TLabel", font=(f, 13, "bold"))
        st.configure("Hint.TLabel", font=(f, 9), foreground="gray")
        st.configure("Status.TLabel", font=(f, 9), foreground="#444")

    # —— 启动 ——
    def _after_start(self):
        if not self.cfg.guide_seen:
            self.show_guide(force=True)
        self._preload_model()

    def _preload_model(self):
        size = self.model_var.get() or "tiny"

        def worker():
            self.root.after(0, lambda: self._set_state(AppState.MODEL_LOADING, f"正在预加载模型 {size}… · 请稍候"))
            try:
                self.transcriber.load_model(size)
                self.root.after(0, lambda: self._set_state(AppState.IDLE))
            except Exception as e:
                self.root.after(0, lambda: self._set_state(AppState.IDLE, f"模型预加载失败（可稍后重试）: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _do_screenshot(self):
        tab, show_tr, out = self.screenshot
        self.mode_nb.select(tab)
        if show_tr:
            self.show_translation_var.set(True)
            self._toggle_translation()
            self.text_area.insert("1.0", "大家好，今天我们讨论下一季度的产品计划。")
            self.translation_area.insert("1.0", "Hello everyone, today we discuss next quarter's product plan.")
            self._update_bottom()
        self.root.update()
        self.root.after(800, lambda: self._grab(out))

    def _grab(self, out):
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        try:
            from PIL import ImageGrab
            ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(out)
            print("saved", out)
        except ImportError:
            import subprocess
            d = chr(36)
            ps = ("Add-Type -AssemblyName System.Drawing;"
                  f"{d}b=New-Object System.Drawing.Bitmap({w},{h});"
                  f"{d}g=[System.Drawing.Graphics]::FromImage({d}b);"
                  f"{d}g.CopyFromScreen({x},{y},0,0,{d}b.Size);"
                  f"{d}b.Save('{out}');")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps])
            print("saved (ps)", out)
        except Exception as e:
            print("screenshot failed:", e)
        self.root.destroy()

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
        base, _can_stop = STATE_META[state]
        if detail:
            text = detail
        elif state == AppState.IDLE:
            text = f"就绪 · 下一步可点「{self._next_action()}」"
        else:
            text = base
        self.status_label.config(text=text)
        self._apply_busy_from_state()

    def _next_action(self):
        try:
            idx = self.mode_nb.index(self.mode_nb.select())
        except Exception:
            idx = 0
        if idx == 1 and self.current_audio_file:
            return "开始转写"
        return NEXT_HINT.get(idx, "开始")

    def _on_tab_changed(self, _evt=None):
        if self.state == AppState.IDLE:
            self._set_state(AppState.IDLE)

    def _apply_busy_from_state(self):
        s = self.state
        busy = s != AppState.IDLE
        N, D = tk.NORMAL, tk.DISABLED
        self.voice_btn.config(state=D if busy else N)
        self.voice_stop_btn.config(state=N if s in (AppState.VOICE, AppState.VOICE_STARTING) else D)
        self.live_btn.config(state=D if busy else N)
        self.live_stop_btn.config(state=N if s == AppState.LIVE else D)
        self.select_file_btn.config(state=D if busy else N)
        self.transcribe_btn.config(state=D if busy or not self.current_audio_file else N)
        for c in (self.device_combo, self.live_device_combo):
            c.config(state=D if busy else "readonly")
        self.settings_btn.config(state=N if s in (AppState.IDLE, AppState.MODEL_LOADING) else D)
        if busy and s != AppState.MODEL_LOADING:
            self.progress.grid()
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        self._update_bottom()

    def _update_bottom(self):
        has_src = bool(self.text_area.get("1.0", "end-1c").strip())
        idle = self.state == AppState.IDLE
        on = self.show_translation_var.get()
        self.translate_btn.config(state=tk.NORMAL if (on and has_src and idle) else tk.DISABLED)
        self.retry_translate_btn.config(state=tk.NORMAL if (on and self._translate_failed and idle) else tk.DISABLED)
        self.save_btn.config(state=tk.NORMAL if has_src else tk.DISABLED)
        self.copy_btn.config(state=tk.NORMAL if has_src else tk.DISABLED)

    # —— 布局 ——
    def create_widgets(self):
        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        head = ttk.Frame(main)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="听写对照", style="Header.TLabel").pack(side=tk.LEFT)
        self.settings_btn = ttk.Button(head, text="设置", command=self.open_settings)
        self.settings_btn.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(head, text="功能介绍", command=lambda: self.show_guide(True)).pack(side=tk.RIGHT)

        self.mode_nb = ttk.Notebook(main)
        self.mode_nb.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        tab_voice = ttk.Frame(self.mode_nb, padding=10)
        tab_file = ttk.Frame(self.mode_nb, padding=10)
        tab_live = ttk.Frame(self.mode_nb, padding=10)
        self.mode_nb.add(tab_voice, text="语音输入")
        self.mode_nb.add(tab_file, text="文件转写")
        self.mode_nb.add(tab_live, text="实时转写")
        self.mode_nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # 语音输入（仅本 Frame 控件）
        ttk.Label(tab_voice, text="听取麦克风，停止后整段保存 WAV 并转写。", style="Hint.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.voice_btn = ttk.Button(tab_voice, text="开始监听", style="Primary.TButton",
                                    command=self.toggle_voice_input)
        self.voice_btn.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.voice_stop_btn = ttk.Button(tab_voice, text="停止并转写", command=self._stop_voice_input,
                                         state=tk.DISABLED)
        self.voice_stop_btn.grid(row=1, column=1, sticky="w", padx=(0, 16))
        ttk.Label(tab_voice, text="输入设备:").grid(row=1, column=2, sticky="e", padx=(0, 6))
        dev_row = ttk.Frame(tab_voice)
        dev_row.grid(row=1, column=3, sticky="w")
        self.device_combo = ttk.Combobox(dev_row, textvariable=self.device_var, state="readonly", width=26)
        self.device_combo.pack(side=tk.LEFT)
        ttk.Button(dev_row, text="刷新", command=self._refresh_devices_ui).pack(side=tk.LEFT, padx=(6, 0))

        # 文件转写
        ttk.Label(tab_file, text="选择已有音频文件后转写；长音频显示进度，不承诺 1 秒。", style="Hint.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.transcribe_btn = ttk.Button(tab_file, text="开始转写", style="Primary.TButton",
                                         command=self.start_transcription, state=tk.DISABLED)
        self.transcribe_btn.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.select_file_btn = ttk.Button(tab_file, text="选择音频文件", command=self.select_audio_file)
        self.select_file_btn.grid(row=1, column=1, sticky="w", padx=(0, 12))
        self.file_label = ttk.Label(tab_file, text="未选择文件", style="Hint.TLabel")
        self.file_label.grid(row=1, column=2, sticky="w")

        # 实时转写
        ttk.Label(tab_live, text="边说边出字预览；短句停→出字目标 ≤1–2 秒（tiny 已加载时）。", style="Hint.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.live_btn = ttk.Button(tab_live, text="开始实时转写", style="Primary.TButton", command=self.toggle_live)
        self.live_btn.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.live_stop_btn = ttk.Button(tab_live, text="停止", command=self._stop_live, state=tk.DISABLED)
        self.live_stop_btn.grid(row=1, column=1, sticky="w", padx=(0, 16))
        ttk.Label(tab_live, text="输入设备:").grid(row=1, column=2, sticky="e", padx=(0, 6))
        dev_row2 = ttk.Frame(tab_live)
        dev_row2.grid(row=1, column=3, sticky="w")
        self.live_device_combo = ttk.Combobox(dev_row2, textvariable=self.device_var, state="readonly", width=26)
        self.live_device_combo.pack(side=tk.LEFT)
        ttk.Button(dev_row2, text="刷新", command=self._refresh_devices_ui).pack(side=tk.LEFT, padx=(6, 0))

        # 状态栏
        status_row = ttk.Frame(main)
        status_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, text="就绪", style="Status.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.summary_label = ttk.Label(status_row, text="", style="Hint.TLabel")
        self.summary_label.grid(row=0, column=1, sticky="e", padx=(8, 8))
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=2, sticky="e")

        # 文本区
        self.text_pane = ttk.Frame(main)
        self.text_pane.grid(row=3, column=0, sticky="nsew")
        main.rowconfigure(3, weight=1)
        self.text_pane.columnconfigure(0, weight=1)
        self.text_pane.rowconfigure(0, weight=1)
        src = ttk.LabelFrame(self.text_pane, text="原文", padding=6)
        src.grid(row=0, column=0, sticky="nsew")
        src.columnconfigure(0, weight=1)
        src.rowconfigure(0, weight=1)
        self.text_area = scrolledtext.ScrolledText(src, wrap=tk.WORD, font=("Microsoft YaHei UI", 11), height=12)
        self.text_area.grid(row=0, column=0, sticky="nsew")
        self.text_area.bind("<KeyRelease>", lambda e: self._update_bottom())
        self.dst_frame = ttk.LabelFrame(self.text_pane, text="译文", padding=6)
        self.dst_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.dst_frame.columnconfigure(0, weight=1)
        self.dst_frame.rowconfigure(0, weight=1)
        self.translation_area = scrolledtext.ScrolledText(self.dst_frame, wrap=tk.WORD,
                                                          font=("Microsoft YaHei UI", 11), height=8)
        self.translation_area.grid(row=0, column=0, sticky="nsew")
        self.dst_frame.grid_remove()

        # 底部栏
        bottom = ttk.Frame(main)
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(bottom, text="显示译文", variable=self.show_translation_var,
                        command=self._toggle_translation).pack(side=tk.LEFT, padx=(0, 12))
        self.translate_btn = ttk.Button(bottom, text="翻译", command=self.start_translation)
        self.retry_translate_btn = ttk.Button(bottom, text="重试翻译", command=self.start_translation)
        ttk.Button(bottom, text="清空", command=self.clear_text).pack(side=tk.RIGHT)
        self.save_btn = ttk.Button(bottom, text="保存 Markdown", style="Primary.TButton", command=self.save_markdown)
        self.save_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.copy_btn = ttk.Button(bottom, text="复制", command=self.copy_text)
        self.copy_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self._load_input_devices()
        self._update_summary()
        self._set_state(AppState.IDLE)

    def _toggle_translation(self):
        if self.show_translation_var.get():
            self.dst_frame.grid()
            self.text_pane.rowconfigure(1, weight=1)
            self.translate_btn.pack(side=tk.LEFT, padx=(0, 8))
            self.retry_translate_btn.pack(side=tk.LEFT, padx=(0, 8))
        else:
            self.dst_frame.grid_remove()
            self.text_pane.rowconfigure(1, weight=0)
            self.translate_btn.pack_forget()
            self.retry_translate_btn.pack_forget()
        self._update_bottom()

    def _update_summary(self):
        self.summary_label.config(
            text=f"模型 {self.model_var.get()} · 语言 {self.language_var.get()} · 译为 {self.target_lang_var.get()}")

    def _update_latency_hint(self):
        self._update_summary()

    def copy_text(self):
        text = self.text_area.get("1.0", "end-1c").strip()
        tr = self.translation_area.get("1.0", "end-1c").strip() if self.show_translation_var.get() else ""
        if tr:
            text = f"{text}\n\n{tr}"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.config(text="已复制到剪贴板")

    def open_settings(self):
        if self.state not in (AppState.IDLE, AppState.MODEL_LOADING):
            messagebox.showinfo("提示", "请先停止当前任务再打开设置")
            return
        SettingsDialog(self)

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
        self.live_device_combo["values"] = labels
        if self.device_var.get() not in mapping:
            self.device_var.set("系统默认")
        if len(labels) <= 1:
            self.status_label.config(text="未检测到输入设备 · 请检查麦克风后点「刷新」")

    def _refresh_devices_ui(self):
        self._load_input_devices()
        if len(self.device_combo["values"]) <= 1:
            messagebox.showwarning("设备", "未检测到输入设备。请到系统设置开启麦克风权限后重试。")

    def _selected_device_index(self):
        return self._device_map.get(self.device_var.get())

    # —— 文件 ——
    def select_audio_file(self):
        if self.state != AppState.IDLE:
            return
        filetypes = (("音频文件", "*.wav *.mp3 *.m4a *.flac *.ogg *.webm"), ("所有文件", "*.*"))
        filename = filedialog.askopenfilename(title="选择音频文件", filetypes=filetypes)
        if filename:
            self.current_audio_file = filename
            self.file_label.config(text=os.path.basename(filename))
            self._set_state(AppState.IDLE)

    def start_transcription(self):
        if not self.current_audio_file or self.state != AppState.IDLE:
            return
        path = self.current_audio_file
        model = self.model_var.get()
        lang = self.language_var.get()
        lang_arg = None if lang == "auto" else lang
        dur = audio_duration_seconds(path)
        if wants_progress_mode(model, dur):
            msg = f"正在转写（约 {dur:.0f}s 音频，不承诺 1 秒）… · 请稍候" if dur else "正在转写（不承诺 1 秒）… · 请稍候"
        else:
            msg = "正在转写短音频… · 请稍候"
        self._set_state(AppState.TRANSCRIBING, msg)

        def worker():
            try:
                text = self.transcriber.transcribe(path, model_size=model, language=lang_arg, beam_size=1)
                self.current_transcript = text or ""
                self.current_translation = ""

                def ok():
                    self._show_transcript()
                    self._set_state(AppState.IDLE, "转写完成 · 下一步可点「保存 Markdown」")

                self.root.after(0, ok)
            except Exception as e:
                err = str(e)

                def fail():
                    self._set_state(AppState.IDLE, "转写失败 · 可重新点「开始转写」")
                    messagebox.showerror("转写错误", err)

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    # —— 实时 ——
    def toggle_live(self):
        if self.state == AppState.LIVE:
            self._stop_live()
        elif self.state == AppState.IDLE:
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

        def worker():
            try:
                self.live_transcriber.start(callback=self._on_live_chunk, model_size=model,
                                            language=lang_arg, device_index=device)
            except Exception as e:
                err = str(e)

                def fail():
                    self._set_state(AppState.IDLE, "实时转写启动失败")
                    messagebox.showerror("实时转写错误", err)

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_live(self):
        if self.state != AppState.LIVE:
            return
        try:
            self.live_transcriber.stop()
        except Exception:
            pass
        text = self._compose_live_text(include_interim=False).strip()
        if text:
            self.current_transcript = text
            self._show_transcript()
        self._set_state(AppState.IDLE, "实时转写已停止 · 下一步可点「保存 Markdown」")

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
            self._update_bottom()

        self.root.after(0, apply)

    def _compose_live_text(self, include_interim: bool = True) -> str:
        parts = list(self.live_final_parts)
        if include_interim and self.live_interim:
            parts.append(self.live_interim)
        return "\n".join(p for p in parts if p)

    # —— 语音输入 ——
    def toggle_voice_input(self):
        if self.state == AppState.IDLE:
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

        def worker():
            try:
                self.voice_input.start(callback=self._on_live_chunk, model_size=self._voice_model,
                                       language=self._voice_language, device_index=device,
                                       should_continue=lambda: not self._voice_cancel)
                if self._voice_cancel:
                    return
                self.voice_ready = True
                self.root.after(0, lambda: self._set_state(AppState.VOICE))
            except Exception as e:
                err = str(e)

                def fail():
                    messagebox.showerror("语音输入错误", err)
                    self._set_state(AppState.IDLE, "监听启动失败")

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
        self._set_state(AppState.TRANSCRIBING, "正在保存语音… · 请稍候")
        start_thread = self._voice_start_thread

        def worker():
            if start_thread and start_thread.is_alive():
                start_thread.join()
            try:
                self.voice_input.set_output_dir(self.cfg.wav_record_dir)
                path = self.voice_input.stop()
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self._present_voice_result(None, "", err, False))
                return
            if not path:
                cancelled = not getattr(self.voice_input, "_capture_started", False)
                self.root.after(0, lambda c=cancelled: self._present_voice_result(None, "", None, c))
                return
            self.current_audio_file = path
            dur = audio_duration_seconds(path)
            msg = ("正在转写（不承诺 1 秒）… · 请稍候" if wants_progress_mode(self._voice_model, dur)
                   else "正在转写… · 请稍候")
            self.root.after(0, lambda: self.status_label.config(text=msg))
            try:
                transcript = self.transcriber.transcribe(path, model_size=self._voice_model,
                                                         language=self._voice_language, beam_size=1)
                final_text = (transcript or "").strip() or self._compose_live_text(False).strip()
                self.root.after(0, lambda p=path, t=final_text: self._present_voice_result(p, t, None, False))
            except Exception as e:
                preview = self._compose_live_text(False).strip()
                err = f"语音文件已保存:\n{path}\n\n转录失败: {e}"
                self.root.after(0, lambda p=path, t=preview, m=err: self._present_voice_result(p, t, m, False))

        threading.Thread(target=worker, daemon=True).start()

    def _present_voice_result(self, path, transcript, error, cancelled):
        if transcript:
            self.current_transcript = transcript
            self.current_translation = ""
            self._show_transcript()
        if error:
            messagebox.showerror("转录错误" if path else "语音输入错误", error)
            self._set_state(AppState.IDLE, "转写失败 · 语音已保存" if path else "监听失败 · 可重新点「开始监听」")
        elif not path:
            self._set_state(AppState.IDLE, "已取消" if cancelled else "没有采集到有效语音 · 可重新点「开始监听」")
        else:
            name = os.path.basename(path)
            self._set_state(AppState.IDLE, f"已转写（{name}）· 下一步可点「保存 Markdown」"
                            if transcript else f"已保存 {name}，未识别到文字")

    def _reset_voice_ui(self):
        self._set_state(AppState.IDLE)

    # —— 翻译 ——
    def start_translation(self):
        source = self.text_area.get("1.0", tk.END).strip()
        if not source or self.state != AppState.IDLE:
            return
        src = self.language_var.get()
        tgt = self.target_lang_var.get()
        if src == tgt and src != "auto":
            messagebox.showinfo("提示", "识别语言与翻译目标相同，无需翻译")
            return
        self._set_state(AppState.TRANSLATING)

        def worker():
            try:
                result = self.translator_engine.translate(source, source_lang=src, target_lang=tgt)
                self.current_transcript = source
                self.current_translation = result

                def ok():
                    self._translate_failed = False
                    self._show_bilingual()
                    self._set_state(AppState.IDLE, f"翻译完成：{Translator.get_language_name(src)} → "
                                    f"{Translator.get_language_name(tgt)} · 下一步可点「保存 Markdown」")

                self.root.after(0, ok)
            except Exception as e:
                err = str(e)

                def fail():
                    self._translate_failed = True
                    self.text_area.delete("1.0", tk.END)
                    self.text_area.insert("1.0", source)
                    self._set_state(AppState.IDLE, "翻译失败（原文已保留）· 可点「重试翻译」")
                    messagebox.showerror("翻译错误", err)

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    def _show_transcript(self):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", self.current_transcript)
        self.translation_area.delete("1.0", tk.END)
        self._update_bottom()

    def _show_bilingual(self):
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", self.current_transcript)
        self.translation_area.delete("1.0", tk.END)
        self.translation_area.insert("1.0", self.current_translation)
        self._update_bottom()

    def save_markdown(self):
        transcript = self.text_area.get("1.0", tk.END).strip()
        translation = self.translation_area.get("1.0", tk.END).strip() if self.show_translation_var.get() else ""
        if not transcript:
            return
        if self.current_audio_file:
            default_name = Path(self.current_audio_file).stem + ".md"
        else:
            default_name = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filename = filedialog.asksaveasfilename(
            title="保存 Markdown 文件", defaultextension=".md", initialfile=default_name,
            initialdir=self.cfg.md_export_dir or str(Path.home() / "Documents"),
            filetypes=(("Markdown 文件", "*.md"), ("所有文件", "*.*")))
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
            self.md_writer.save(filename, transcript, metadata=metadata, translation=translation or None,
                                source_lang=self.language_var.get(),
                                target_lang=self.target_lang_var.get() if translation else None)
            self.cfg.md_export_dir = str(Path(filename).parent)
            self._persist_config()
            self.status_label.config(text=f"已保存 {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("保存错误", f"保存失败: {e}")

    def clear_text(self):
        if self.state != AppState.IDLE:
            return
        if messagebox.askyesno("确认", "确定要清空原文和译文吗？"):
            self.text_area.delete("1.0", tk.END)
            self.translation_area.delete("1.0", tk.END)
            self.current_transcript = ""
            self.current_translation = ""
            self.live_final_parts = []
            self.current_audio_file = None
            self._translate_failed = False
            self.file_label.config(text="未选择文件")
            self._set_state(AppState.IDLE)

    def on_closing(self):
        self._voice_cancel = True
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
