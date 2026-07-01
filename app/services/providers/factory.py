from __future__ import annotations

from typing import Optional

from ...config import get_settings
from .base import TranslationProvider
from .minimax import DeepSeekProvider, MinimaxProvider


_provider_cache: dict[str, TranslationProvider] = {}


def get_provider(name: str) -> TranslationProvider:
    name = (name or "minimax").lower()
    if name in _provider_cache:
        return _provider_cache[name]

    settings = get_settings()

    if name == "minimax":
        if not settings.minimax_api_key:
            raise RuntimeError("MINIMAX_API_KEY chưa được cấu hình trong .env")
        provider: TranslationProvider = MinimaxProvider(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            model=settings.minimax_model,
            group_id=settings.minimax_group_id,
        )
    elif name == "deepseek":
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY chưa được cấu hình trong .env")
        provider = DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
    else:
        raise ValueError(f"Provider không hỗ trợ: {name}")

    _provider_cache[name] = provider
    return provider


def available_providers() -> list[str]:
    settings = get_settings()
    out: list[str] = []
    if settings.minimax_api_key:
        out.append("minimax")
    if settings.deepseek_api_key:
        out.append("deepseek")
    return out


def default_provider() -> Optional[str]:
    avail = available_providers()
    if "minimax" in avail:
        return "minimax"
    if avail:
        return avail[0]
    return None
