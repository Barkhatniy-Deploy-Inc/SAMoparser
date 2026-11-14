from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Параметры запуска, загруженные из переменных окружения."""

    database_url: str
    app_env: str = "development"


def get_settings() -> Settings:
    """Загрузить настройки, не раскрывая секреты в логах и исходном коде."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://sam:sam@localhost:5432/sam",
        ),
        app_env=os.getenv("APP_ENV", "development"),
    )
