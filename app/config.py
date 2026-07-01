from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ebook-translator"
    database_url: str = "sqlite:///./ebook_translator.db"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    minimax_api_key: str = ""
    minimax_group_id: str = ""
    minimax_model: str = "MiniMax-M2.7-highspeed"
    minimax_base_url: str = "https://api.minimax.io/v1"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-pro"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    request_timeout: int = 30
    use_curl_cffi_fallback: bool = True
    use_playwright_fallback: bool = False

    translation_max_chunk_chars: int = 1000
    translation_concurrency: int = 2
    translation_timeout: int = 600
    translation_max_retries: int = 2
    auto_extract_glossary: bool = True
    auto_summarize_chapter: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
