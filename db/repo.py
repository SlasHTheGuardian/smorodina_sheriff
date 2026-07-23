"""
Доступ к данным и бизнес-правила записи на игры.

Главное правило: на игру есть `capacity` активных мест; сверх — лист ожидания
(порядок по времени записи). При отмене активного места первый из листа
ожидания автоматически продвигается в активные.
"""

from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Player, Game, Registration, PlayedGame, GamePlayer, Role,
    GAME_PLANNED, GAME_OPEN, GAME_CLOSED, GAME_CANCELLED, GAME_FINISHED,
    REG_ACTIVE, REG_WAITLIST, REG_CANCELLED, REG_ATTENDED,
)

REGISTRATION_CLOSE_BEFORE = timedelta(days=3)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def registration_is_open(
    game: Game, now: datetime | None = None
) -> bool:
    current = _as_utc(now or _utcnow())
    starts_at = _as_utc(game.starts_at)
    return (
        game.status == GAME_OPEN
        and starts_at > current + REGISTRATION_CLOSE_BEFORE
    )


# ---------------------------------------------------------------------------
# Игроки
# ---------------------------------------------------------------------------

async def get_or_create_player(
    session: AsyncSession, tg_id: int, username: str | None, full_name: str
) -> Player:
    player = await session.scalar(select(Player).where(Player.tg_id == tg_id))
    if player is None:
        player = Player(tg_id=tg_id, username=username, full_name=full_name)
        session.add(player)
        await session.commit()
    elif player.username != username or player.full_name != full_name:
        player.username = username
        player.full_name = full_name
        await session.commit()
    return player


async def set_game_nickname(
    session: AsyncSession, player: Player, nickname: str
) -> None:
    player.game_nickname = nickname
    await session.commit()


# ---------------------------------------------------------------------------
# Игры
# ---------------------------------------------------------------------------

async def create_game(
    session: AsyncSession, starts_at: datetime, capacity: int,
    location: str | None, note: str | None, host_id: int | None,
    title: str = "Игровой вечер",
) -> Game:
    game = Game(
        starts_at=starts_at,
        capacity=capacity,
        location=location,
        note=note,
        host_id=host_id,
        title=title,
        status=GAME_OPEN,
    )
    session.add(game)
    await session.commit()
    return game


async def get_game(session: AsyncSession, game_id: int) -> Game | None:
    return await session.get(Game, game_id)


async def set_game_status(session: AsyncSession, game: Game, status: str) -> None:
    game.status = status
    await session.commit()


async def delete_event(session: AsyncSession, event_id: int) -> bool:
    """Удаляет встречу, регистрации и все связанные результаты."""
    played_game_ids = select(PlayedGame.id).where(
        PlayedGame.event_id == event_id
    )
    await session.execute(
        delete(GamePlayer).where(
            GamePlayer.game_id.in_(played_game_ids)
        )
    )
    await session.execute(
        delete(PlayedGame).where(PlayedGame.event_id == event_id)
    )
    await session.execute(
        delete(Registration).where(Registration.game_id == event_id)
    )
    result = await session.execute(
        delete(Game).where(Game.id == event_id)
    )
    await session.commit()
    return bool(result.rowcount)


async def list_upcoming_games(session: AsyncSession) -> list[Game]:
    """Предстоящие встречи для записи или просмотра состава."""
    stmt = (
        select(Game)
        .where(
            Game.status.in_([GAME_PLANNED, GAME_OPEN, GAME_CLOSED]),
            Game.starts_at >= _utcnow(),
        )
        .order_by(Game.starts_at)
    )
    return list(await session.scalars(stmt))


async def counts_for_games(
    session: AsyncSession, game_ids: list[int]
) -> dict[int, tuple[int, int]]:
    """game_id -> (активных, в листе ожидания)."""
    if not game_ids:
        return {}
    stmt = (
        select(Registration.game_id, Registration.status, func.count())
        .where(
            Registration.game_id.in_(game_ids),
            Registration.status.in_([REG_ACTIVE, REG_WAITLIST]),
        )
        .group_by(Registration.game_id, Registration.status)
    )
    out: dict[int, tuple[int, int]] = {gid: (0, 0) for gid in game_ids}
    for gid, status, cnt in await session.execute(stmt):
        active, wait = out[gid]
        if status == REG_ACTIVE:
            out[gid] = (cnt, wait)
        else:
            out[gid] = (active, cnt)
    return out


async def active_count(session: AsyncSession, game_id: int) -> int:
    return await session.scalar(
        select(func.count()).select_from(Registration).where(
            Registration.game_id == game_id, Registration.status == REG_ACTIVE
        )
    ) or 0


async def roster(
    session: AsyncSession, game_id: int
) -> tuple[list[Registration], list[Registration]]:
    """Возвращает (активные, лист ожидания) с подгруженными игроками, по порядку записи."""
    stmt = (
        select(Registration)
        .where(
            Registration.game_id == game_id,
            Registration.status.in_([REG_ACTIVE, REG_WAITLIST]),
        )
        .order_by(Registration.created_at, Registration.id)
        .options(selectinload(Registration.player))
    )
    regs = list(await session.scalars(stmt))
    active = [r for r in regs if r.status == REG_ACTIVE]
    waitlist = [r for r in regs if r.status == REG_WAITLIST]
    return active, waitlist


# ---------------------------------------------------------------------------
# Записи
# ---------------------------------------------------------------------------

async def get_registration(
    session: AsyncSession, game_id: int, player_id: int
) -> Registration | None:
    return await session.scalar(
        select(Registration).where(
            Registration.game_id == game_id,
            Registration.player_id == player_id,
        )
    )


async def register(
    session: AsyncSession, game: Game, player: Player
) -> tuple[str, str | None]:
    """
    Возвращает (code, status):
      ('closed',     None)            — игра закрыта/отменена;
      ('deadline',   None)            — до начала осталось не более 3 суток;
      ('already',    REG_ACTIVE|REG_WAITLIST) — уже записан;
      ('registered', REG_ACTIVE|REG_WAITLIST) — записали (или в лист ожидания).
    """
    if game.status != GAME_OPEN:
        return ("closed", None)
    if not registration_is_open(game):
        return ("deadline", None)

    existing = await get_registration(session, game.id, player.id)
    if existing and existing.status in (REG_ACTIVE, REG_WAITLIST):
        return ("already", existing.status)

    active = await active_count(session, game.id)
    has_space = game.capacity is None or active < game.capacity
    new_status = REG_ACTIVE if has_space else REG_WAITLIST

    if existing:                       # повторная запись после отмены — в конец очереди
        existing.status = new_status
        existing.created_at = _utcnow()
    else:
        session.add(Registration(
            game_id=game.id, player_id=player.id, status=new_status,
        ))
    await session.commit()
    return ("registered", new_status)


async def cancel_registration(
    session: AsyncSession, game: Game, player: Player
) -> tuple[str, Player | None]:
    """
    Отменяет запись. Возвращает (code, promoted_player):
      ('not_registered', None) — записи не было;
      ('cancelled', player|None) — отменено; player — кого подняли из листа ожидания.
    """
    existing = await get_registration(session, game.id, player.id)
    if not existing or existing.status == REG_CANCELLED:
        return ("not_registered", None)

    was_active = existing.status == REG_ACTIVE
    existing.status = REG_CANCELLED

    promoted: Player | None = None
    if was_active and registration_is_open(game):
        next_in_line = await session.scalar(
            select(Registration)
            .where(
                Registration.game_id == game.id,
                Registration.status == REG_WAITLIST,
            )
            .order_by(Registration.created_at, Registration.id)
            .options(selectinload(Registration.player))
            .limit(1)
        )
        if next_in_line is not None:
            next_in_line.status = REG_ACTIVE
            promoted = next_in_line.player

    await session.commit()
    return ("cancelled", promoted)


async def list_player_games(
    session: AsyncSession, player: Player
) -> list[Registration]:
    """Предстоящие игры игрока (активные и лист ожидания), с подгруженной игрой."""
    stmt = (
        select(Registration)
        .join(Game)
        .where(
            Registration.player_id == player.id,
            Registration.status.in_([REG_ACTIVE, REG_WAITLIST]),
            Game.status != GAME_CANCELLED,
            Game.starts_at >= _utcnow(),
        )
        .order_by(Game.starts_at)
        .options(selectinload(Registration.game))
    )
    return list(await session.scalars(stmt))


# ---------------------------------------------------------------------------
# Результаты игровых вечеров
# ---------------------------------------------------------------------------

async def list_recent_events(
    session: AsyncSession, days: int = 30
) -> list[Game]:
    """Прошедшие неотменённые встречи за указанное число дней."""
    now = _utcnow()
    stmt = (
        select(Game)
        .where(
            Game.starts_at >= now - timedelta(days=days),
            Game.starts_at <= now,
            Game.status != GAME_CANCELLED,
        )
        .order_by(Game.starts_at.desc())
    )
    return list(await session.scalars(stmt))


async def list_event_participants(
    session: AsyncSession, event_id: int
) -> list[Registration]:
    """Участники вечера, которых нужно распределить по партиям."""
    stmt = (
        select(Registration)
        .where(
            Registration.game_id == event_id,
            Registration.status.in_([REG_ACTIVE, REG_ATTENDED]),
        )
        .order_by(Registration.created_at, Registration.id)
        .options(selectinload(Registration.player))
    )
    return list(await session.scalars(stmt))


async def list_event_played_games(
    session: AsyncSession, event_id: int
) -> list[PlayedGame]:
    stmt = (
        select(PlayedGame)
        .where(PlayedGame.event_id == event_id)
        .order_by(PlayedGame.game_number, PlayedGame.id)
    )
    return list(await session.scalars(stmt))


async def create_event_played_games(
    session: AsyncSession, event: Game, count: int, host_id: int | None
) -> list[PlayedGame]:
    """Создаёт недостающие партии 1..count, не затирая введённые результаты."""
    existing = await list_event_played_games(session, event.id)
    by_number = {game.game_number: game for game in existing}
    for number in range(1, count + 1):
        if number not in by_number:
            game = PlayedGame(
                event_id=event.id,
                host_id=host_id,
                game_number=number,
                started_at=event.starts_at,
            )
            session.add(game)
    await session.commit()
    return await list_event_played_games(session, event.id)


async def add_event_played_game(
    session: AsyncSession, event: Game, host_id: int | None
) -> PlayedGame:
    existing = await list_event_played_games(session, event.id)
    next_number = max(
        (game.game_number or 0 for game in existing),
        default=0,
    ) + 1
    game = PlayedGame(
        event_id=event.id,
        host_id=host_id,
        game_number=next_number,
        started_at=event.starts_at,
    )
    session.add(game)
    await session.commit()
    return game


async def delete_played_game(
    session: AsyncSession, played_game_id: int
) -> int | None:
    """Удаляет партию с составом и перенумеровывает оставшиеся."""
    game = await session.get(PlayedGame, played_game_id)
    if game is None or game.event_id is None:
        return None
    event_id = game.event_id
    await session.delete(game)
    await session.flush()

    remaining = await list_event_played_games(session, event_id)
    for number, item in enumerate(remaining, 1):
        item.game_number = number
    await session.commit()
    return event_id


async def get_played_game(
    session: AsyncSession, played_game_id: int
) -> PlayedGame | None:
    return await session.get(PlayedGame, played_game_id)


async def game_assignments(
    session: AsyncSession, played_game_id: int
) -> list[GamePlayer]:
    stmt = (
        select(GamePlayer)
        .where(GamePlayer.game_id == played_game_id)
        .order_by(GamePlayer.seat_number, GamePlayer.id)
        .options(
            selectinload(GamePlayer.user),
            selectinload(GamePlayer.role),
        )
    )
    return list(await session.scalars(stmt))


async def role_limit_error(
    session: AsyncSession,
    played_game_id: int,
    user_id: int,
    role_code: str,
    replacing_seat: int | None = None,
) -> str | None:
    """Возвращает понятную ошибку, если роль уже занята допустимое число раз."""
    limits = {
        "don": 1,
        "sheriff": 1,
        "mafia": 2,
        "civilian": 6,
    }
    limit = limits.get(role_code)
    if limit is None:
        return None

    stmt = (
        select(GamePlayer)
        .join(Role, Role.id == GamePlayer.role_id)
        .where(
            GamePlayer.game_id == played_game_id,
            GamePlayer.user_id != user_id,
            Role.code == role_code,
        )
        .order_by(GamePlayer.seat_number, GamePlayer.id)
        .options(selectinload(GamePlayer.user))
    )
    assigned = list(await session.scalars(stmt))
    if replacing_seat is not None:
        assigned = [
            item for item in assigned
            if item.seat_number != replacing_seat
        ]
    if len(assigned) < limit:
        return None

    references = [
        str(item.seat_number)
        if item.seat_number is not None else item.user.game_display
        for item in assigned
    ]
    if role_code == "don":
        return f"Что-то не так: Доном уже назначен игрок {references[0]}"
    if role_code == "sheriff":
        return f"Что-то не так: Шерифом уже назначен игрок {references[0]}"

    role_name = "Мафия" if role_code == "mafia" else "Мирный"
    count_word = "двум" if role_code == "mafia" else "шести"
    return (
        f"Что-то не так: роль «{role_name}» уже назначена {count_word} "
        f"игрокам: {', '.join(references)}"
    )


async def assign_game_player(
    session: AsyncSession,
    game: PlayedGame,
    user_id: int,
    role_code: str,
    seat_number: int | None,
    replace_seat: bool = False,
) -> tuple[str, GamePlayer | None]:
    role = await session.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        return ("unknown_role", None)

    if await role_limit_error(
        session,
        game.id,
        user_id,
        role_code,
        replacing_seat=seat_number if replace_seat else None,
    ):
        return ("role_limit", None)

    if role_code in ("host", "skip"):
        seat_number = None
    elif seat_number is None or not 1 <= seat_number <= 10:
        return ("invalid_seat", None)

    if seat_number is not None:
        occupied = await session.scalar(
            select(GamePlayer).where(
                GamePlayer.game_id == game.id,
                GamePlayer.seat_number == seat_number,
                GamePlayer.user_id != user_id,
            ).options(selectinload(GamePlayer.user))
        )
        if occupied is not None:
            if not replace_seat:
                return ("seat_taken", occupied)
            occupied.role = None
            occupied.seat_number = None
            occupied.is_winner = None
            await session.flush()

    assignment = await session.scalar(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id,
            GamePlayer.user_id == user_id,
        )
    )
    if assignment is None:
        assignment = GamePlayer(game_id=game.id, user_id=user_id)
        session.add(assignment)

    assignment.role = role
    assignment.seat_number = seat_number
    assignment.is_winner = _is_role_winner(role_code, game.winner_side)
    await session.commit()
    return ("saved", assignment)


async def clear_game_player_assignment(
    session: AsyncSession, game_id: int, user_id: int
) -> None:
    assignment = await session.scalar(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    if assignment is not None:
        assignment.role = None
        assignment.seat_number = None
        assignment.is_winner = None
        await session.commit()


async def toggle_game_skip(
    session: AsyncSession, game: PlayedGame, user_id: int
) -> bool:
    """Переключает пропуск. Возвращает новое состояние."""
    assignment = await session.scalar(
        select(GamePlayer)
        .where(
            GamePlayer.game_id == game.id,
            GamePlayer.user_id == user_id,
        )
        .options(selectinload(GamePlayer.role))
    )
    if assignment and assignment.role and assignment.role.code == "skip":
        await clear_game_player_assignment(session, game.id, user_id)
        return False
    code, _ = await assign_game_player(
        session, game, user_id, "skip", None
    )
    return code == "saved"


async def set_game_host(
    session: AsyncSession, game: PlayedGame, user_id: int
) -> bool:
    """Назначает одного ведущего, снимая прежнего."""
    host_role = await session.scalar(
        select(Role).where(Role.code == "host")
    )
    if host_role is None:
        return False

    current_hosts = list(await session.scalars(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id,
            GamePlayer.role_id == host_role.id,
            GamePlayer.user_id != user_id,
        )
    ))
    for assignment in current_hosts:
        assignment.role = None
        assignment.seat_number = None
        assignment.is_winner = None
    await session.flush()

    code, _ = await assign_game_player(
        session, game, user_id, "host", None
    )
    return code == "saved"


def _is_role_winner(
    role_code: str, winner_side: str | None
) -> bool | None:
    if winner_side is None or role_code in ("host", "skip"):
        return None
    role_side = "mafia" if role_code in ("mafia", "don") else "town"
    return role_side == winner_side


async def validate_game_setup(
    session: AsyncSession, game: PlayedGame
) -> tuple[bool, str]:
    if game.event_id is None:
        return (False, "Партия не привязана к игровому вечеру.")

    participants = await list_event_participants(session, game.event_id)
    assignments = await game_assignments(session, game.id)
    assigned_ids = {assignment.user_id for assignment in assignments}
    missing = [reg.player.display for reg in participants
               if reg.player_id not in assigned_ids]
    if missing:
        return (False, "Не выбрана роль: " + ", ".join(missing[:5]))

    seated = [
        assignment for assignment in assignments
        if assignment.role and assignment.role.code not in ("host", "skip")
    ]
    seats = {assignment.seat_number for assignment in seated}
    if len(seated) != 10 or seats != set(range(1, 11)):
        return (False, "Нужно заполнить все места за столом: 1–10.")

    role_counts = Counter(assignment.role.code for assignment in seated)
    expected = {"civilian": 6, "sheriff": 1, "mafia": 2, "don": 1}
    if role_counts != expected:
        return (
            False,
            "Состав ролей должен быть: 6 мирных, 1 шериф, 2 мафии и 1 дон.",
        )
    return (True, "")


async def set_game_winner(
    session: AsyncSession, game: PlayedGame, winner_side: str
) -> tuple[bool, str]:
    if winner_side not in ("town", "mafia"):
        return (False, "Неизвестная победившая команда.")

    valid, reason = await validate_game_setup(session, game)
    if not valid:
        return (False, reason)

    game.winner_side = winner_side
    game.finished_at = _utcnow()
    assignments = await game_assignments(session, game.id)
    for assignment in assignments:
        assignment.is_winner = _is_role_winner(
            assignment.role.code, winner_side
        )
    await session.commit()

    if game.event_id is not None:
        event_games = await list_event_played_games(session, game.event_id)
        if event_games and all(item.winner_side for item in event_games):
            event = await get_game(session, game.event_id)
            if event and event.status != GAME_CANCELLED:
                event.status = GAME_FINISHED
                await session.commit()
    return (True, "")


async def add_guest_to_event(
    session: AsyncSession, event_id: int, nickname: str
) -> Player:
    guest = Player(
        tg_id=None,
        username=None,
        full_name=nickname,
        game_nickname=nickname,
    )
    session.add(guest)
    await session.flush()
    session.add(Registration(
        game_id=event_id,
        player_id=guest.id,
        status=REG_ATTENDED,
    ))
    await session.commit()
    return guest


async def list_user_result_games(
    session: AsyncSession, user_id: int, days: int = 30
) -> list[tuple[PlayedGame, GamePlayer, Game, Role]]:
    cutoff = _utcnow() - timedelta(days=days)
    stmt = (
        select(PlayedGame, GamePlayer, Game, Role)
        .join(GamePlayer, GamePlayer.game_id == PlayedGame.id)
        .join(Game, Game.id == PlayedGame.event_id)
        .join(Role, Role.id == GamePlayer.role_id)
        .where(
            GamePlayer.user_id == user_id,
            PlayedGame.winner_side.is_not(None),
            Game.starts_at >= cutoff,
            Role.code != "skip",
        )
        .order_by(Game.starts_at.desc(), PlayedGame.game_number)
    )
    return list((await session.execute(stmt)).tuples())
