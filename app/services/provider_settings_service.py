from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..models import AppSetting, ProviderSetting
from ..config import get_settings


SUPPORTED_PROVIDERS = ("minimax", "openrouter", "deepseek")


def _defaults_for(provider: str) -> dict:
    s = get_settings()
    if provider == "minimax":
        return {
            "api_key": s.minimax_api_key,
            "base_url": s.minimax_base_url,
            "model": s.minimax_model,
            "group_id": s.minimax_group_id,
        }
    if provider == "deepseek":
        return {
            "api_key": s.deepseek_api_key,
            "base_url": s.deepseek_base_url,
            "model": s.deepseek_model,
            "group_id": "",
        }
    if provider == "openrouter":
        return {
            "api_key": s.openrouter_api_key,
            "base_url": s.openrouter_base_url,
            "model": s.openrouter_model or "deepseek/deepseek-v4-pro",
            "group_id": "",
        }
    return {"api_key": "", "base_url": "", "model": "", "group_id": ""}


def mask_key(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:3]}...{v[-4:]}"


def list_provider_settings(session: Session) -> list[dict]:
    rows = list(session.exec(select(ProviderSetting)).all())
    by_provider = {r.provider: r for r in rows}
    out: list[dict] = []
    for name in SUPPORTED_PROVIDERS:
        row = by_provider.get(name)
        if row is not None:
            api_key = row.api_key
            base_url = row.base_url
            model = row.model
            group_id = row.group_id
            configured = bool(api_key.strip())
            source = "web"
            updated_at = row.updated_at
        else:
            defaults = _defaults_for(name)
            api_key = defaults["api_key"] if defaults["api_key"] else ""
            base_url = defaults["base_url"]
            model = defaults["model"]
            group_id = defaults["group_id"]
            configured = bool(api_key.strip())
            source = "env"
            updated_at = None
        out.append(
            {
                "provider": name,
                "configured": configured,
                "source": source,
                "masked_key": mask_key(api_key) if configured else "",
                "base_url": base_url,
                "model": model,
                "group_id": group_id,
                "has_key": bool(api_key.strip()),
                "updated_at": updated_at,
            }
        )
    return out


def get_provider_config(session: Session, provider: str) -> dict:
    name = (provider or "").lower()
    row = session.exec(select(ProviderSetting).where(ProviderSetting.provider == name)).first()
    if row is not None:
        return {
            "api_key": row.api_key.strip(),
            "base_url": row.base_url.strip(),
            "model": row.model.strip(),
            "group_id": (row.group_id or "").strip(),
        }
    defaults = _defaults_for(name)
    return {
        "api_key": defaults["api_key"].strip(),
        "base_url": defaults["base_url"].strip(),
        "model": defaults["model"].strip(),
        "group_id": defaults["group_id"].strip(),
    }


def save_provider_setting(
    session: Session,
    provider: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    group_id: Optional[str] = None,
) -> Optional[ProviderSetting]:
    """Persist provider overrides.

    Semantics: ``api_key`` (and other fields) that are ``None`` or empty after
    ``strip()`` mean "leave the existing value untouched". This lets the
    settings form save just the model/base URL without forcing the user to
    re-enter the API key, and lets ``clear_provider_setting`` remain the only
    way to wipe an API key from the DB.
    """
    name = (provider or "").lower()
    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Provider không hỗ trợ: {name}")
    row = session.exec(select(ProviderSetting).where(ProviderSetting.provider == name)).first()

    key_value = api_key.strip() if api_key is not None and api_key.strip() else None
    base_value = base_url.strip() if base_url is not None and base_url.strip() else None
    model_value = model.strip() if model is not None and model.strip() else None
    group_value = group_id.strip() if group_id is not None and group_id.strip() else None

    if row is None and key_value is None and base_value is None and model_value is None and group_value is None:
        return None

    if row is None:
        row = ProviderSetting(provider=name)
    if key_value is not None:
        row.api_key = key_value
    if base_value is not None:
        row.base_url = base_value
    if model_value is not None:
        row.model = model_value
    if group_value is not None:
        row.group_id = group_value
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def clear_provider_setting(session: Session, provider: str) -> None:
    name = (provider or "").lower()
    row = session.exec(select(ProviderSetting).where(ProviderSetting.provider == name)).first()
    if row is None:
        return
    session.delete(row)
    session.commit()
    default = get_default_provider_name(session)
    if default == name:
        set_default_provider_name(session, "")


DEFAULT_PROVIDER_KEY = "default_provider"


def get_default_provider_name(session: Session) -> str:
    row = session.get(AppSetting, DEFAULT_PROVIDER_KEY)
    return (row.value or "").strip().lower() if row else ""


def set_default_provider_name(session: Session, name: str) -> AppSetting:
    from datetime import datetime
    value = (name or "").strip().lower()
    row = session.get(AppSetting, DEFAULT_PROVIDER_KEY)
    if row is None:
        row = AppSetting(key=DEFAULT_PROVIDER_KEY, value=value)
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
