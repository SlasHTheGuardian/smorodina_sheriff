from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from config import RATINGS_API_BASE_URL, RATINGS_API_TIMEOUT


class RatingsServiceError(Exception):
    """Рейтинговый сервис недоступен или вернул некорректный ответ."""


@dataclass(frozen=True)
class SeasonStats:
    season_id: int
    season_name: str
    rating: int | float
    games_played: int
    wins: int
    losses: int
    win_rate: int | float


@dataclass(frozen=True)
class PlayerRating:
    player_id: int
    name: str
    global_stats: SeasonStats
    current_season_stats: SeasonStats | None
    seasons_ratings: tuple[SeasonStats, ...]


def _number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RatingsServiceError(
            f"Некорректное поле рейтинга: {field}"
        )
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RatingsServiceError(
            f"Некорректное целочисленное поле: {field}"
        )
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RatingsServiceError(
            f"Некорректное текстовое поле: {field}"
        )
    return value.strip()


def _parse_season_stats(payload: object, field: str) -> SeasonStats:
    if not isinstance(payload, dict):
        raise RatingsServiceError(f"Некорректные данные: {field}")

    win_rate = _number(payload.get("winRate"), f"{field}.winRate")
    if not 0 <= win_rate <= 1:
        raise RatingsServiceError(
            f"Некорректное поле доли побед: {field}.winRate"
        )

    stats = SeasonStats(
        season_id=_integer(payload.get("seasonId"), f"{field}.seasonId"),
        season_name=_text(
            payload.get("seasonName"), f"{field}.seasonName"
        ),
        rating=_number(payload.get("rating"), f"{field}.rating"),
        games_played=_integer(
            payload.get("gamesPlayed"), f"{field}.gamesPlayed"
        ),
        wins=_integer(payload.get("wins"), f"{field}.wins"),
        losses=_integer(payload.get("losses"), f"{field}.losses"),
        win_rate=win_rate,
    )
    if min(stats.games_played, stats.wins, stats.losses) < 0:
        raise RatingsServiceError(
            f"Отрицательная статистика: {field}"
        )
    return stats


def parse_player_rating(payload: object) -> PlayerRating:
    if not isinstance(payload, dict):
        raise RatingsServiceError("Некорректный ответ рейтингового сервиса")

    seasons_payload = payload.get("seasonsRatings")
    if not isinstance(seasons_payload, list):
        raise RatingsServiceError("Некорректный список сезонов")

    current_payload = payload.get("currentSeasonStats")
    current_stats = (
        None
        if current_payload is None
        else _parse_season_stats(current_payload, "currentSeasonStats")
    )

    return PlayerRating(
        player_id=_integer(payload.get("playerId"), "playerId"),
        name=_text(payload.get("name"), "name"),
        global_stats=_parse_season_stats(
            payload.get("globalStats"), "globalStats"
        ),
        current_season_stats=current_stats,
        seasons_ratings=tuple(
            _parse_season_stats(item, f"seasonsRatings[{index}]")
            for index, item in enumerate(seasons_payload)
        ),
    )


async def fetch_player_rating(
    player_name: str,
    client: httpx.AsyncClient | None = None,
) -> PlayerRating | None:
    encoded_name = quote(player_name, safe="")
    url = f"{RATINGS_API_BASE_URL}/players/name/{encoded_name}"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=RATINGS_API_TIMEOUT)

    try:
        response = await client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return parse_player_rating(response.json())
    except RatingsServiceError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise RatingsServiceError(
            "Не удалось получить рейтинг"
        ) from error
    finally:
        if owns_client:
            await client.aclose()
