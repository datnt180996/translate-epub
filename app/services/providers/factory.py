from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from ...config import get_settings
from ..provider_settings_service import (
    SUPPORTED_PROVIDERS,
    get_default_provider_name,
    get_provider_config,
)
from .base import TranslationProvider
from .minimax import DeepSeekProvider, MinimaxProvider, OpenRouterProvider


_provider_cache: dict[str, TranslationProvider] = {}


def _build_provider(name: str, cfg: dict) -> TranslationProvider:
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model", "")
    group_id = cfg.get("group_id", "")

    if name == "minimax":
        if not api_key:
            raise RuntimeError("API key cho Minimax chưa được cấu hình")
        return MinimaxProvider(
            api_key=api_key,
            base_url=base_url,
            model=model or "MiniMax-M2.7-highspeed",
            group_id=group_id,
        )
    if name == "deepseek":
        if not api_key:
            raise RuntimeError("API key cho DeepSeek chưa được cấu hình")
        return DeepSeekProvider(
            api_key=api_key,
            base_url=base_url,
            model=model or "deepseek-chat",
        )
    if name == "openrouter":
        if not api_key:
            raise RuntimeError("API key cho OpenRouter chưa được cấu hình")
        return OpenRouterProvider(
            api_key=api_key,
            base_url=base_url,
            model=model or "deepseek/deepseek-v4-pro",
        )
    raise ValueError(f"Provider không hỗ trợ: {name}")


def get_provider(session: Session, name: str) -> TranslationProvider:
    """Return a provider using saved DB config (fallback to .env).

    Uses the DB-backed factory path so the user-managed API key wins over .env.
    """
    name = (name or "minimax").lower()
    if name in _provider_cache:
        return _provider_cache[name]
    cfg = get_provider_config(session, name)
    if not cfg["api_key"]:
        raise RuntimeError(f"API key cho {name} chưa được cấu hình")
    provider = _build_provider(name, cfg)
    _provider_cache[name] = provider
    return provider


def get_provider_no_session(name: str) -> TranslationProvider:
    """Backward-compatible getter that reads .env only (no DB).

    Some legacy callers don't have a session. Prefer ``get_provider(session, ...)``
    when a session is available.
    """
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
    elif name == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY chưa được cấu hình trong .env")
        provider = OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model or "deepseek/deepseek-v4-pro",
        )
    else:
        raise ValueError(f"Provider không hỗ trợ: {name}")
    _provider_cache[name] = provider
    return provider


def _any_configured(session: Session, name: str) -> bool:
    cfg = get_provider_config(session, name)
    return bool(cfg["api_key"])


def available_providers(session: Optional[Session] = None) -> list[str]:
    if session is None:
        from ...db import get_session

        with next(get_session()) as s:
            avail = [n for n in SUPPORTED_PROVIDERS if _any_configured(s, n)]
        return avail
    return [n for n in SUPPORTED_PROVIDERS if _any_configured(session, n)]


def default_provider(session: Optional[Session] = None) -> Optional[str]:
    """Return the user-selected default provider name.

    The user must explicitly set the default via "Đặt làm mặc định"
    in the API Settings page. We only return the chosen provider if it is
    currently configured (has an API key from DB or .env). Otherwise None.
    """
    if session is None:
        from ...db import get_session
        with next(get_session()) as s:
            return _resolve_default(s)
    return _resolve_default(session)


def _resolve_default(session: Session) -> Optional[str]:
    chosen = get_default_provider_name(session)
    if not chosen:
        return None
    if chosen not in SUPPORTED_PROVIDERS:
        return None
    if not _any_configured(session, chosen):
        return None
    return chosen


def invalidate_cache(name: Optional[str] = None) -> None:
    if name is None:
        _provider_cache.clear()
        return
    _provider_cache.pop((name or "").lower(), None)
