"""Tests for save_provider_setting / list_provider_settings semantics.

The settings form used to overwrite the stored API key with an empty string
whenever the user re-saved config without retyping the key. The behavior we
want is: blank API key in the form preserves the existing key, and a new
non-empty key replaces it. ``clear_provider_setting`` remains the only way to
wipe the key from the DB.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models import ProviderSetting
from app.services.provider_settings_service import (
    SUPPORTED_PROVIDERS,
    clear_provider_setting,
    save_provider_setting,
)


def _db_row(session: Session, provider: str) -> ProviderSetting | None:
    return session.exec(
        select(ProviderSetting).where(ProviderSetting.provider == provider)
    ).first()


_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_ENGINE)


def _session() -> Session:
    return Session(_ENGINE)


def test_save_first_key_creates_row():
    s = _session()
    row = save_provider_setting(s, "minimax", api_key="sk-abcdef0123")
    s.expire_all()
    assert row is not None
    assert row.provider == "minimax"
    assert row.api_key == "sk-abcdef0123"
    assert row.model == ""
    assert row.base_url == ""
    assert row.group_id == ""


def test_blank_api_key_preserves_existing_key():
    s = _session()
    save_provider_setting(
        s,
        "minimax",
        api_key="sk-original-1234567890",
        base_url="https://api.example/v1",
        model="some-model",
    )
    save_provider_setting(s, "minimax", model="new-model", base_url="https://api2/v1")
    s.expire_all()
    row = _db_row(s, "minimax")
    assert row is not None
    assert row.api_key == "sk-original-1234567890"
    assert row.model == "new-model"
    assert row.base_url == "https://api2/v1"
    assert row.group_id == ""


def test_explicit_new_key_replaces_old_key():
    s = _session()
    save_provider_setting(s, "deepseek", api_key="sk-old-1234567890")
    save_provider_setting(s, "deepseek", api_key="  sk-new-9876543210  ")
    s.expire_all()
    row = _db_row(s, "deepseek")
    assert row is not None
    assert row.api_key == "sk-new-9876543210"


def test_whitespace_only_api_key_treated_as_blank():
    s = _session()
    save_provider_setting(s, "openrouter", api_key="sk-keep-1234567890")
    save_provider_setting(s, "openrouter", api_key="   ", model="new-model")
    s.expire_all()
    row = _db_row(s, "openrouter")
    assert row is not None
    assert row.api_key == "sk-keep-1234567890"
    assert row.model == "new-model"


def test_save_only_blank_does_not_create_row():
    s = _session()
    # Ensure the DB has no row for "deepseek" before this assertion.
    clear_provider_setting(s, "deepseek")
    s.expire_all()
    assert _db_row(s, "deepseek") is None
    result = save_provider_setting(s, "deepseek")
    s.expire_all()
    assert result is None
    assert _db_row(s, "deepseek") is None


def test_clear_removes_db_row():
    s = _session()
    save_provider_setting(s, "minimax", api_key="sk-temp-1234567890", model="x")
    clear_provider_setting(s, "minimax")
    s.expire_all()
    assert _db_row(s, "minimax") is None


def test_save_updates_timestamp():
    s = _session()
    clear_provider_setting(s, "minimax")
    first = save_provider_setting(s, "minimax", api_key="sk-1234567890")
    first_ts = first.updated_at
    # Force updated_at to a clearly older moment to detect the bump.
    first.updated_at = datetime(2000, 1, 1)
    s.add(first)
    s.commit()
    second = save_provider_setting(s, "minimax", model="some-new-model")
    assert second.updated_at > first_ts
    assert second.api_key == "sk-1234567890"


def test_unsupported_provider_raises():
    s = _session()
    try:
        save_provider_setting(s, "not-a-real-provider", api_key="x")
    except ValueError:
        return
    raise AssertionError("Expected ValueError for unsupported provider")


def test_supported_providers_contains_three_providers():
    assert set(SUPPORTED_PROVIDERS) == {"minimax", "openrouter", "deepseek"}


def _run_all():
    failures = []
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures.append((name, exc))
                print(f"FAIL {name}: {exc!r}")
    if failures:
        raise SystemExit(1)
    print(f"\nAll {sum(1 for n in globals() if n.startswith('test_') and callable(globals()[n]))} provider setting tests passed.")


if __name__ == "__main__":
    _run_all()
