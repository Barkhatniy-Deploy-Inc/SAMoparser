from __future__ import annotations

import os
from dataclasses import dataclass
from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    """Параметры запуска, загруженные из переменных окружения."""

    database_url: str
    app_env: str = "development"


def get_settings() -> Settings:
    """Загрузить настройки, не раскрывая секреты в логах и исходном коде."""
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        database_url = URL.create(
            "postgresql+psycopg",
            username=os.getenv("DB_USER", "sam"),
            password=os.getenv("DB_PASSWORD", "sam"),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "sam"),
        ).render_as_string(hide_password=False)
    if app_env in {"prod", "production"} and not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("В production требуется DATABASE_URL с драйвером postgresql+psycopg")
    return Settings(database_url=database_url, app_env=app_env)
