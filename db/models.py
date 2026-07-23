"""ORM-модели клубной БД из db_schema.sql.

В интерфейсе бота исторически используются имена Player, Game и Registration.
Они сохранены в Python, но отображаются на новые таблицы users, events и
event_registrations.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _big_id_type():
    # SQLite выдаёт авто-ID только для INTEGER PRIMARY KEY. В PostgreSQL
    # остаётся BIGINT, как в целевой схеме.
    return BigInteger().with_variant(Integer, "sqlite")


def _small_id_type():
    return SmallInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


# Статусы игрового вечера (events)
GAME_PLANNED = "planned"
GAME_OPEN = "open"
GAME_CLOSED = "closed"
GAME_FINISHED = "finished"
GAME_CANCELLED = "cancelled"

# Статусы записи (event_registrations)
REG_ACTIVE = "registered"
REG_WAITLIST = "waitlist"
REG_CANCELLED = "cancelled"
REG_ATTENDED = "attended"
REG_NO_SHOW = "no_show"


class Player(Base):
    """Пользователь клуба (таблица users)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "club_role IN ('player','host','admin')",
            name="ck_users_club_role",
        ),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(
        "telegram_id", BigInteger, unique=True, index=True
    )
    username: Mapped[str | None] = mapped_column(Text)
    game_nickname: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(
        "display_name", Text, nullable=False, default=""
    )
    club_role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="player"
    )
    rating_main: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    rating_season: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    rating_alt_1: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    rating_alt_2: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    rating_alt_3: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="player"
    )

    @property
    def display(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.full_name or f"id{self.tg_id}"

    @property
    def game_display(self) -> str:
        telegram_name = f"@{self.username}" if self.username else None
        if self.game_nickname and telegram_name:
            return f"{self.game_nickname} ({telegram_name})"
        return self.game_nickname or telegram_name or self.full_name or f"id{self.id}"


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    time_name: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("side IN ('town','mafia')", name="ck_roles_side"),
    )

    id: Mapped[int] = mapped_column(_small_id_type(), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)


class Game(Base):
    """Игровой вечер (таблица events)."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','open','closed','finished','cancelled')",
            name="ck_events_status",
        ),
        Index("idx_events_host", "host_id"),
        Index("idx_events_season", "season_id"),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    season_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="SET NULL")
    )
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, default="Игровой вечер"
    )
    note: Mapped[str | None] = mapped_column("description", Text)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    location: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int | None] = mapped_column("max_players", Integer)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GAME_OPEN, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class Registration(Base):
    """Запись пользователя на игровой вечер."""

    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_event_user"),
        CheckConstraint(
            "status IN ('registered','waitlist','cancelled','attended','no_show')",
            name="ck_event_registrations_status",
        ),
        Index("idx_reg_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    game_id: Mapped[int] = mapped_column(
        "event_id", ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        "user_id", ForeignKey("users.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REG_ACTIVE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "registered_at", DateTime(timezone=True), nullable=False, default=_utcnow
    )

    game: Mapped[Game] = relationship(back_populates="registrations")
    player: Mapped[Player] = relationship(back_populates="registrations")


class PlayedGame(Base):
    """Отдельная сыгранная партия (таблица games)."""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "winner_side IN ('town','mafia')",
            name="ck_games_winner_side",
        ),
        Index("idx_games_event", "event_id"),
        Index("idx_games_host", "host_id"),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    game_number: Mapped[int | None] = mapped_column(Integer)
    winner_side: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    event: Mapped[Game | None] = relationship()
    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", name="uq_game_user"),
        UniqueConstraint("game_id", "seat_number", name="uq_game_seat"),
        CheckConstraint(
            "final_status IN ('alive','shot_down','jailed')",
            name="ck_game_players_final_status",
        ),
        CheckConstraint(
            "left_at_count BETWEEN 1 AND 10",
            name="ck_game_players_left_at_count",
        ),
        Index("idx_game_players_user", "user_id"),
        Index("idx_game_players_game", "game_id"),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    seat_number: Mapped[int | None] = mapped_column(Integer)
    final_status: Mapped[str | None] = mapped_column(String(16))
    left_at_count: Mapped[int | None] = mapped_column(Integer)
    is_winner: Mapped[bool | None] = mapped_column(Boolean)
    points: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    game: Mapped[PlayedGame] = relationship(back_populates="players")
    user: Mapped[Player] = relationship()
    role: Mapped[Role | None] = relationship()


class PlayerSeasonRating(Base):
    __tablename__ = "player_season_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "season_id", name="uq_user_season"),
        Index("idx_psr_season", "season_id"),
    )

    id: Mapped[int] = mapped_column(_big_id_type(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE")
    )
    rating: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
