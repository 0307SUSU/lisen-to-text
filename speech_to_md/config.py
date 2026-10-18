#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用配置持久化（JSON）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


def default_config_path() -> Path:
    return Path.home() / ".speech_to_md" / "config.json"


def default_md_dir() -> str:
    return str(Path.home() / "Documents" / "SpeechToMd")


def default_wav_dir() -> str:
    return str(Path.home() / "Documents" / "SpeechToMd")


@dataclass
class AppConfig:
    model_size: str = "tiny"
    language: str = "zh"
    target_lang: str = "en"
    translator_backend: str = "google"
    md_export_dir: str = field(default_factory=default_md_dir)
    wav_record_dir: str = field(default_factory=default_wav_dir)
    input_device_label: str = "系统默认"
    guide_seen: bool = False
    ai_assist_enabled: bool = False  # 预留，P0 始终 False

    def ensure_dirs(self) -> None:
        for d in (self.md_export_dir, self.wav_record_dir):
            try:
                Path(d).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass


def load_config(path: Optional[Path] = None) -> AppConfig:
    cfg_path = path or default_config_path()
    if not cfg_path.exists():
        cfg = AppConfig()
        cfg.ensure_dirs()
        return cfg
    try:
        raw: Dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = AppConfig()
        cfg.ensure_dirs()
        return cfg
    known = {f.name for f in AppConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    data = {k: v for k, v in raw.items() if k in known}
    cfg = AppConfig(**data)
    # P0：强制 AI 辅助关闭
    cfg.ai_assist_enabled = False
    if cfg.translator_backend not in ("google",):
        cfg.translator_backend = "google"
    if cfg.model_size not in ("tiny", "base", "small", "medium", "large"):
        cfg.model_size = "tiny"
    cfg.ensure_dirs()
    return cfg


def save_config(cfg: AppConfig, path: Optional[Path] = None) -> None:
    cfg_path = path or default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(cfg)
    payload["ai_assist_enabled"] = False
    cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
