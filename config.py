"""Конфигурация из переменных окружения (.env)."""

from __future__ import annotations
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Важно: грузим .env здесь, до чтения переменных. Иначе при импорте config
# раньше bot.py значения из .env (ADMIN_IDS, CLUB_TZ, DATABASE_URL) не подхватятся.
load_dotenv()

# Подключение к БД. По умолчанию — локальный SQLite рядом с кодом (одинаковый путь
# для bot.py и devtools.py независимо от рабочей папки). На сервере — задать
# DATABASE_URL=postgresql+asyncpg://user:pass@host/db
_DEFAULT_DB = (Path(__file__).resolve().parent / "sheriff.db").as_posix()
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", f"sqlite+aiosqlite:///{_DEFAULT_DB}"
)

# HTTP API рейтингов работает на той же машине, что и бот. Адрес можно
# переопределить, если сервис запущен на другом порту или с префиксом пути.
RATINGS_API_BASE_URL: str = os.environ.get(
    "RATINGS_API_BASE_URL", "http://127.0.0.1:8080"
).rstrip("/")
try:
    RATINGS_API_TIMEOUT: float = float(
        os.environ.get("RATINGS_API_TIMEOUT", "5")
    )
except ValueError:
    RATINGS_API_TIMEOUT = 5.0

# Таймзона клуба — в ней вводятся и показываются даты игр (в БД храним UTC).
CLUB_TZ_NAME: str = os.environ.get("CLUB_TZ", "Europe/Moscow")


def club_tz() -> ZoneInfo:
    return ZoneInfo(CLUB_TZ_NAME)


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids)


# Telegram-ID администраторов/судей (создают игры). Пример: ADMIN_IDS=12345,67890
ADMIN_IDS: frozenset[int] = _parse_admin_ids(os.environ.get("ADMIN_IDS", ""))


def is_admin(tg_id: int | None) -> bool:
    return tg_id is not None and tg_id in ADMIN_IDS
