#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译模块 - 支持多语言翻译
Translation Module - Multi-language translation support
"""

from typing import Optional


class Translator:
    """翻译器 - 使用 deep-translator"""
    
    def __init__(self):
        self.translator = None
    
    def translate(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "en"
    ) -> str:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
        
        Returns:
            翻译后的文本
        """
        if not text or not text.strip():
            return ""
        
        # 如果源语言和目标语言相同，不翻译
        if source_lang == target_lang and source_lang != "auto":
            return text
        
        try:
            from deep_translator import GoogleTranslator
        except ImportError:
            raise ImportError(
                "未安装 deep-translator。请运行: pip install deep-translator"
            )
        
        # 语言代码映射
        lang_map = {
            "zh": "zh-CN",
            "ja": "ja",
            "ko": "ko",
            "en": "en",
            "fr": "fr",
            "de": "de",
            "es": "es",
            "auto": "auto"
        }
        
        src = lang_map.get(source_lang, source_lang)
        tgt = lang_map.get(target_lang, target_lang)
        
        try:
            # 使用 Google Translator（免费，无需 API 密钥）
            translator = GoogleTranslator(source=src, target=tgt)
            
            # 分段翻译以避免长文本问题
            max_length = 4500  # Google Translator 限制
            if len(text) <= max_length:
                result = translator.translate(text)
            else:
                # 分段处理
                segments = self._split_text(text, max_length)
                translated_segments = []
                for segment in segments:
                    if segment.strip():
                        translated = translator.translate(segment)
                        translated_segments.append(translated)
                result = " ".join(translated_segments)
            
            return result
        
        except Exception as e:
            raise RuntimeError(f"翻译失败: {str(e)}\n提示: 翻译需要网络连接")
    
    def _split_text(self, text: str, max_length: int) -> list:
        """
        将长文本分段
        
        Args:
            text: 要分段的文本
            max_length: 每段最大长度
        
        Returns:
            分段后的文本列表
        """
        # 按句子分割
        import re
        sentences = re.split(r'([。！？.!?])', text)
        
        segments = []
        current_segment = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punctuation
            
            if len(current_segment) + len(full_sentence) <= max_length:
                current_segment += full_sentence
            else:
                if current_segment:
                    segments.append(current_segment)
                current_segment = full_sentence
        
        if current_segment:
            segments.append(current_segment)
        
        return segments if segments else [text]
    
    @staticmethod
    def get_language_name(code: str) -> str:
        """获取语言名称"""
        names = {
            "zh": "中文",
            "en": "English",
            "ja": "日本語",
            "ko": "한국어",
            "fr": "Français",
            "de": "Deutsch",
            "es": "Español",
            "auto": "自动检测"
        }
        return names.get(code, code)
