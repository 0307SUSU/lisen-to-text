#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown 文件写入模块
Markdown File Writer Module
"""

import os
from datetime import datetime
from typing import Dict, Optional


class MarkdownWriter:
    """Markdown 文件写入器"""
    
    def save(
        self,
        filepath: str,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        translation: Optional[str] = None,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None
    ):
        """
        保存内容为 Markdown 文件（支持双语）
        
        Args:
            filepath: 保存路径
            content: 主要内容（原文）
            title: 文档标题（可选）
            metadata: 元数据字典（可选）
            translation: 译文（可选）
            source_lang: 源语言（可选）
            target_lang: 目标语言（可选）
        """
        # 准备标题
        if not title:
            filename = os.path.basename(filepath)
            title = os.path.splitext(filename)[0]
        
        # 构建 Markdown 内容
        md_lines = []
        
        # 添加标题
        md_lines.append(f"# {title}")
        md_lines.append("")
        
        # 添加元数据
        if metadata:
            md_lines.append("## 元数据")
            md_lines.append("")
            for key, value in metadata.items():
                # 格式化键名
                key_display = self._format_key(key)
                md_lines.append(f"- **{key_display}**: {value}")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
        
        # 如果有翻译，使用双语格式
        if translation and translation.strip():
            # 原文
            source_label = f"原文 ({source_lang})" if source_lang else "原文"
            md_lines.append(f"## {source_label}")
            md_lines.append("")
            md_lines.append(content)
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
            
            # 译文
            target_label = f"译文 ({target_lang})" if target_lang else "译文"
            md_lines.append(f"## {target_label}")
            md_lines.append("")
            md_lines.append(translation)
            md_lines.append("")
        else:
            # 只有原文
            md_lines.append("## 转录内容")
            md_lines.append("")
            md_lines.append(content)
            md_lines.append("")
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        
        print(f"Markdown 文件已保存: {filepath}")
    
    def _format_key(self, key: str) -> str:
        """格式化元数据键名"""
        key_map = {
            "source_file": "源文件",
            "model": "模型",
            "language": "语言",
            "timestamp": "转录时间",
            "duration": "时长",
        }
        return key_map.get(key, key.replace('_', ' ').title())
