#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译模块：可插拔 TranslatorBackend（P0 默认 Google）。"""

from __future__ import annotations

import re
from typing import Dict, Optional, Protocol, runtime_checkable


LANG_MAP = {
    "zh": "zh-CN",
    "ja": "ja",
    "ko": "ko",
    "en": "en",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "auto": "auto",
}

LANG_NAMES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "auto": "自动检测",
}


@runtime_checkable
class TranslatorBackend(Protocol):
    """翻译后端协议。"""

    name: str
    display_name: str
    available: bool

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        ...


class GoogleTranslatorBackend:
    """deep-translator Google（免费，需联网）。"""

    name = "google"
    display_name = "Google（免费）"
    available = True

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        if not text or not text.strip():
            return ""
        if source_lang == target_lang and source_lang != "auto":
            return text
        try:
            from deep_translator import GoogleTranslator
        except ImportError as exc:
            raise ImportError("未安装 deep-translator。请运行: pip install deep-translator") from exc

        src = LANG_MAP.get(source_lang, source_lang)
        tgt = LANG_MAP.get(target_lang, target_lang)
        translator = GoogleTranslator(source=src, target=tgt)
        max_length = 4500
        if len(text) <= max_length:
            return translator.translate(text)
        segments = _split_text(text, max_length)
        out = []
        for segment in segments:
            if segment.strip():
                out.append(translator.translate(segment))
        return " ".join(out)


class PlaceholderTranslatorBackend:
    """预留后端（DeepL 等），P0 不可选。"""

    available = False

    def __init__(self, name: str, display_name: str):
        self.name = name
        self.display_name = display_name

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> str:
        raise RuntimeError(f"{self.display_name} 为本轮预留口，尚未接入")


def _split_text(text: str, max_length: int) -> list:
    sentences = re.split(r"([。！？.!?])", text)
    segments = []
    current = ""
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ""
        full = sentence + punct
        if len(current) + len(full) <= max_length:
            current += full
        else:
            if current:
                segments.append(current)
            current = full
    if current:
        segments.append(current)
    return segments if segments else [text]


BACKEND_REGISTRY: Dict[str, TranslatorBackend] = {
    "google": GoogleTranslatorBackend(),
    "deepl": PlaceholderTranslatorBackend("deepl", "DeepL（预留）"),
    "other": PlaceholderTranslatorBackend("other", "其它（预留）"),
}


def get_backend(name: str = "google") -> TranslatorBackend:
    backend = BACKEND_REGISTRY.get(name) or BACKEND_REGISTRY["google"]
    if not backend.available:
        return BACKEND_REGISTRY["google"]
    return backend


class Translator:
    """兼容旧调用：委托给 TranslatorBackend。"""

    def __init__(self, backend_name: str = "google"):
        self.set_backend(backend_name)

    def set_backend(self, backend_name: str) -> None:
        self.backend_name = backend_name if backend_name in BACKEND_REGISTRY else "google"
        self.backend = get_backend(self.backend_name)

    def translate(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "en",
    ) -> str:
        try:
            return self.backend.translate(text, source_lang=source_lang, target_lang=target_lang)
        except Exception as e:
            raise RuntimeError(f"翻译失败: {e}\n提示: 翻译需要网络连接；原文已保留，可重试") from e

    @staticmethod
    def get_language_name(code: str) -> str:
        return LANG_NAMES.get(code, code)

    @staticmethod
    def list_backends_for_ui():
        """返回 [(value, label, enabled), ...]。"""
        rows = []
        for key, backend in BACKEND_REGISTRY.items():
            label = backend.display_name
            if not backend.available:
                label = f"{label}（灰显预留）"
            rows.append((key, label, backend.available))
        return rows
