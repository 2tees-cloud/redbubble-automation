"""Ядро: AI-роутеры текста и картинок с автоматическим переключением провайдеров."""
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import book, cover, metadata, pipeline, postprocess, quality
from .base import AllProvidersFailed, BadOutput
from .image_router import ImageRouter
from .state import State
from .text_router import TextRouter

ROOT = Path(__file__).resolve().parent.parent

__all__ = ["load_routers", "book", "cover", "metadata", "pipeline", "postprocess", "quality", "TextRouter", "ImageRouter", "State", "AllProvidersFailed", "BadOutput"]


def load_routers(config_path: str | Path = ROOT / "config.yaml") -> tuple[TextRouter, ImageRouter]:
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    logging.basicConfig(level=cfg.get("log_level", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    state = State(ROOT / cfg.get("state_db", "data/router_state.db"))
    text = TextRouter(cfg["text_providers"], state, timeout=cfg.get("timeout", 120))
    image = ImageRouter(cfg["image_providers"], state, timeout=cfg.get("timeout", 120))
    return text, image
