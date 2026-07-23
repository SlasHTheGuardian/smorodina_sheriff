"""
Утилиты для локальной проверки записи на игры — БЕЗ Telegram.
Пишут в ту же БД, что и бот (по умолчанию sheriff.db рядом с кодом).

    python devtools.py add-game [--when "2026-07-05 19:00"] [--cap 10] [--loc "Клуб"]
    python devtools.py list
    python devtools.py demo      # игра + 5 «игроков»: показывает лист ожидания и продвижение
    python devtools.py mock      # две будущие игры с тестовыми записями для Telegram
    python devtools.py mock-results  # прошедшая встреча для ввода результатов
"""

from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timedelta

from config import club_tz, DATABASE_URL
from db.engine import Session, init_models, dispose
from db import repo
from gametime import parse_local, fmt


def _tomorrow_19() -> tuple[str, str]:
    d = datetime.now(club_tz()) + timedelta(days=1)
    return d.strftime("%Y-%m-%d"), "19:00"


async def add_game(when: str | None, cap: int, loc: str | None) -> None:
    await init_models()
    if when:
        date_str, time_str = when.split()
    else:
        date_str, time_str = _tomorrow_19()
    starts = parse_local(date_str, time_str)
    async with Session() as s:
        g = await repo.create_game(s, starts, cap, loc, None, host_id=None)
        print(f"✅ Создана игра #{g.id}: {fmt(g.starts_at)}, мест {cap}"
              + (f", {loc}" if loc else ""))
    await dispose()


async def list_games() -> None:
    await init_models()
    async with Session() as s:
        games = await repo.list_upcoming_games(s)
        if not games:
            print("Предстоящих игр нет. Создай: python devtools.py add-game")
        for g in games:
            active, wait = await repo.roster(s, g.id)
            capacity = g.capacity if g.capacity is not None else "∞"
            print(f"\n#{g.id}  {fmt(g.starts_at)}  [{g.status}]  "
                  f"мест {len(active)}/{capacity}"
                  + (f"  +{len(wait)} в ожидании" if wait else ""))
            for i, r in enumerate(active, 1):
                print(f"    {i}. {r.player.display}")
            if wait:
                print("    лист ожидания:")
                for i, r in enumerate(wait, 1):
                    print(f"      {i}. {r.player.display}")
    await dispose()


async def demo() -> None:
    await init_models()
    date_str, time_str = _tomorrow_19()
    async with Session() as s:
        g = await repo.create_game(s, parse_local(date_str, time_str), 3,
                                   "Демо-стол", None, host_id=None)
        print(f"Игра #{g.id} (вместимость 3). Записываю 5 игроков:")
        players = []
        for i in range(1, 6):
            p = await repo.get_or_create_player(s, 900000 + i, f"demo{i}", f"Демо {i}")
            players.append(p)
            code, st = await repo.register(s, g, p)
            print(f"  {p.display}: {st}")
        print("\nОтменяю запись Демо 1 (активного) — должен подняться первый из листа:")
        _, promoted = await repo.cancel_registration(s, g, players[0])
        print(f"  поднят: {promoted.display if promoted else '—'}")
        active, wait = await repo.roster(s, g.id)
        print(f"\nИтог игры #{g.id}: активны {[r.player.display for r in active]}, "
              f"ожидание {[r.player.display for r in wait]}")
    await dispose()


async def mock_games(date_str: str | None) -> None:
    """Создаёт два сценария для ручной проверки записи через Telegram."""
    await init_models()
    if date_str is None:
        date_str, _ = _tomorrow_19()

    scenarios = [
        {
            "time": "19:00",
            "capacity": 5,
            "registered": 4,
            "location": "МОК · одно свободное место",
        },
        {
            "time": "20:30",
            "capacity": 3,
            "registered": 5,
            "location": "МОК · заполнено + лист ожидания",
        },
    ]

    async with Session() as s:
        players = [
            await repo.get_or_create_player(
                s,
                # Заведомо вне диапазона Telegram-ID: уведомление мок-игроку
                # не сможет случайно попасть реальному пользователю.
                tg_id=9_000_000_000_000_000_000 + i,
                username=f"mock_player_{i}",
                full_name=f"Тестовый игрок {i}",
            )
            for i in range(1, 6)
        ]

        created: list[tuple[int, str, int, int]] = []
        for scenario in scenarios:
            game = await repo.create_game(
                s,
                starts_at=parse_local(date_str, scenario["time"]),
                capacity=scenario["capacity"],
                location=scenario["location"],
                note="Тестовая игра для проверки записи и отмены.",
                host_id=None,
            )
            for player in players[:scenario["registered"]]:
                await repo.register(s, game, player)

            active, waitlist = await repo.roster(s, game.id)
            created.append((game.id, fmt(game.starts_at), len(active), len(waitlist)))

    print("Созданы тестовые игры:")
    for game_id, when, active, wait in created:
        print(f"  #{game_id} · {when} · записано {active}" +
              (f" · в ожидании {wait}" if wait else ""))
    print("\nОткрой в боте «Запись на игры» и проверь оба сценария.")
    await dispose()


async def mock_results(date_str: str | None) -> None:
    """Создаёт прошедшую встречу с 12 участниками для админского мастера."""
    await init_models()
    if date_str is None:
        day = datetime.now(club_tz()) - timedelta(days=1)
        date_str = day.strftime("%Y-%m-%d")

    async with Session() as s:
        players = []
        for i in range(1, 13):
            player = await repo.get_or_create_player(
                s,
                tg_id=9_000_000_000_000_000_000 + i,
                username=f"mock_player_{i}",
                full_name=f"Тестовый игрок {i}",
            )
            if i % 2:
                player.game_nickname = f"Смородинка {i}"
                await s.commit()
            players.append(player)

        event = await repo.create_game(
            s,
            starts_at=parse_local(date_str, "19:00"),
            capacity=12,
            location="МОК · ввод результатов",
            note="Прошедшая тестовая встреча для админского раздела.",
            host_id=None,
        )
        for player in players:
            await repo.register(s, event, player)

    print(
        f"Создана встреча #{event.id}: {fmt(event.starts_at)}, "
        f"участников {len(players)}."
    )
    print("Открой в боте «Результаты игр» под аккаунтом администратора.")
    await dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальные утилиты записи на игры")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add-game", help="создать игру")
    p_add.add_argument("--when", help='"ГГГГ-ММ-ДД ЧЧ:ММ" (по умолчанию завтра 19:00)')
    p_add.add_argument("--cap", type=int, default=10, help="мест (по умолчанию 10)")
    p_add.add_argument("--loc", help="место проведения")

    sub.add_parser("list", help="список игр с ростерами")
    sub.add_parser("demo", help="демо записи и листа ожидания")
    p_mock = sub.add_parser(
        "mock", help="создать две будущие игры с тестовыми участниками"
    )
    p_mock.add_argument(
        "--date", help="дата игр ГГГГ-ММ-ДД (по умолчанию завтра)"
    )
    p_mock_results = sub.add_parser(
        "mock-results",
        help="создать прошедшую встречу с 12 участниками",
    )
    p_mock_results.add_argument(
        "--date", help="дата встречи ГГГГ-ММ-ДД (по умолчанию вчера)"
    )

    args = parser.parse_args()
    print(f"БД: {DATABASE_URL}\n")
    if args.cmd == "add-game":
        asyncio.run(add_game(args.when, args.cap, args.loc))
    elif args.cmd == "list":
        asyncio.run(list_games())
    elif args.cmd == "demo":
        asyncio.run(demo())
    elif args.cmd == "mock":
        asyncio.run(mock_games(args.date))
    elif args.cmd == "mock-results":
        asyncio.run(mock_results(args.date))


if __name__ == "__main__":
    main()
