"""Async-движок SQLAlchemy и фабрика сессий. Один и тот же код для SQLite и Postgres."""

from __future__ import annotations
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import DATABASE_URL
from db.models import Base, Role

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _prepare_legacy_sqlite(sync_conn) -> None:
    """Освобождает имя games, не удаляя старые локальные данные."""
    if sync_conn.dialect.name != "sqlite":
        return

    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "games" in tables:
        columns = {column["name"] for column in inspector.get_columns("games")}
        if "event_id" not in columns:
            if "legacy_games" in tables:
                raise RuntimeError(
                    "Найдены одновременно legacy_games и старая таблица games. "
                    "Автоматическая миграция остановлена."
                )

            if "game_players" in tables:
                if "legacy_game_players" in tables:
                    raise RuntimeError(
                        "Найдены одновременно game_players и legacy_game_players. "
                        "Автоматическая миграция остановлена."
                    )
                sync_conn.execute(text(
                    "ALTER TABLE game_players RENAME TO legacy_game_players"
                ))
            sync_conn.execute(text("ALTER TABLE games RENAME TO legacy_games"))

    # В SQLite имена индексов глобальны. После переименования таблицы старые
    # индексы сохраняют имена и мешают создать индексы новой game_players.
    legacy_indexes = sync_conn.execute(text(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'index' AND tbl_name = 'legacy_game_players' "
        "AND name IN ('idx_game_players_user', 'idx_game_players_game')"
    )).scalars()
    for index_name in legacy_indexes:
        sync_conn.execute(text(f'DROP INDEX "{index_name}"'))


def _ensure_indexes(sync_conn) -> None:
    """Досоздаёт индексы после частичной или legacy-миграции."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(sync_conn, checkfirst=True)


def _add_compatible_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        columns = {
            column["name"] for column in inspector.get_columns("users")
        }
        if "game_nickname" not in columns:
            sync_conn.execute(text(
                "ALTER TABLE users ADD COLUMN game_nickname TEXT"
            ))

    if "events" in tables:
        columns = {
            column["name"] for column in inspector.get_columns("events")
        }
        if "price_rubles" not in columns:
            sync_conn.execute(text(
                "ALTER TABLE events ADD COLUMN price_rubles "
                "INTEGER NOT NULL DEFAULT 500"
            ))


def _seed_roles(sync_conn) -> None:
    roles = [
        ("civilian", "Мирный", "town"),
        ("sheriff", "Шериф", "town"),
        ("mafia", "Мафия", "mafia"),
        ("don", "Дон", "mafia"),
        # side ограничен исходной схемой; при расчёте победы эти две роли
        # обрабатываются отдельно и не считаются игроками команды.
        ("host", "Ведущий", "town"),
        ("skip", "Пропуск", "town"),
    ]
    for code, name, side in roles:
        exists = sync_conn.execute(
            select(Role.id).where(Role.code == code)
        ).first()
        if exists is None:
            sync_conn.execute(
                Role.__table__.insert().values(code=code, name=name, side=side)
            )


async def init_models() -> None:
    """Создаёт/дополняет схему и обязательный справочник ролей."""
    async with engine.begin() as conn:
        await conn.run_sync(_prepare_legacy_sqlite)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_indexes)
        await conn.run_sync(_add_compatible_columns)
        await conn.run_sync(_seed_roles)


async def dispose() -> None:
    await engine.dispose()
