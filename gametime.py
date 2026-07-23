"""Парсинг и форматирование времени игр. В Python работаем с aware-UTC."""

from __future__ import annotations
from datetime import datetime, timezone

from config import club_tz

_RU_WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def as_utc(dt: datetime) -> datetime:
    """Гарантирует aware-UTC (SQLite возвращает naive — считаем его UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_local(date_str: str, time_str: str) -> datetime:
    """'YYYY-MM-DD' + 'HH:MM' в таймзоне клуба → aware-UTC. Бросает ValueError."""
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    local = naive.replace(tzinfo=club_tz())
    return local.astimezone(timezone.utc)


def fmt(dt: datetime) -> str:
    """UTC → строка в таймзоне клуба, напр. 'Сб 05.07 19:00'."""
    local = as_utc(dt).astimezone(club_tz())
    return f"{_RU_WD[local.weekday()]} {local.strftime('%d.%m %H:%M')}"
