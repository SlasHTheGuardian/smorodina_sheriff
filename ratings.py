from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from config import RATINGS_API_BASE_URL, RATINGS_API_TIMEOUT


class RatingsServiceError(Exception):
    """Рейтинговый сервис недоступен или вернул некорректный ответ."""


@dataclass(frozen=True)
class SeasonRating:
    season_id: int
    season_name: str
    rating: int | float


@dataclass(frozen=True)
class PlayerRating:
    global_rating: int | float
    current_season: int | float
    seasons: tuple[SeasonRating, ...]


def _number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RatingsServiceError(
            f"Некорректное поле рейтинга: {field}"
        )
    return value


def parse_player_rating(payload: object) -> PlayerRating:
    if not isinstance(payload, dict):
        raise RatingsServiceError("Некорректный ответ рейтингового сервиса")

    seasons_payload = payload.get("seasons")
    if not isinstance(seasons_payload, list):
        raise RatingsServiceError("Некорректный список сезонов")

    seasons: list[SeasonRating] = []
    for item in seasons_payload:
        if not isinstance(item, dict):
            raise RatingsServiceError("Некорректные данные сезона")
        season_id = item.get("seasonId")
        season_name = item.get("seasonName")
        if isinstance(season_id, bool) or not isinstance(season_id, int):
            raise RatingsServiceError("Некорректный идентификатор сезона")
        if not isinstance(season_name, str) or not season_name.strip():
            raise RatingsServiceError("Некорректное название сезона")
        seasons.append(SeasonRating(
            season_id=season_id,
            season_name=season_name.strip(),
            rating=_number(item.get("rating"), "seasons.rating"),
        ))

    return PlayerRating(
        global_rating=_number(payload.get("global"), "global"),
        current_season=_number(
            payload.get("currentSeason"), "currentSeason"
        ),
        seasons=tuple(seasons),
    )


async def fetch_player_rating(
    player_name: str,
    client: httpx.AsyncClient | None = None,
) -> PlayerRating | None:
    encoded_name = quote(player_name, safe="")
    url = f"{RATINGS_API_BASE_URL}/ratings/{encoded_name}"
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
