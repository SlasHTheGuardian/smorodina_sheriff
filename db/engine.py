"""Async-движок SQLAlchemy и фабрика сессий. Один и тот же код для SQLite и Postgres."""

from __future__ import annotations
import re

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import DATABASE_URL
from db.models import Base, Role
from db.logging import install_database_logging
from event_types import EVENT_TYPE_CHECK_SQL, EVENT_TYPE_LABELS
from observability import observed, operation

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, hide_parameters=True)
install_database_logging(engine)

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
        if "event_type" not in columns:
            sync_conn.execute(text(
                "ALTER TABLE events ADD COLUMN event_type "
                "VARCHAR(32) NOT NULL DEFAULT 'mafia' "
                f"CONSTRAINT ck_events_event_type CHECK ({EVENT_TYPE_CHECK_SQL})"
            ))
        if "price_rubles" not in columns:
            sync_conn.execute(text(
                "ALTER TABLE events ADD COLUMN price_rubles "
                "INTEGER NOT NULL DEFAULT 500"
            ))


def _outdated_event_type_check(sync_conn) -> str | None:
    inspector = inspect(sync_conn)
    if not inspector.has_table("events"):
        return None
    for constraint in inspector.get_check_constraints("events"):
        if constraint["name"] == "ck_events_event_type":
            sql = constraint["sqltext"]
            if not set(EVENT_TYPE_LABELS).issubset(re.findall(r"'([^']*)'", sql)):
                return sql
    return None


def _expand_event_type_check(sync_conn) -> None:
    old_check = _outdated_event_type_check(sync_conn)
    if old_check is None:
        return
    if sync_conn.dialect.name == "postgresql":
        sync_conn.execute(text(
            "ALTER TABLE events DROP CONSTRAINT ck_events_event_type"
        ))
        sync_conn.execute(text(
            "ALTER TABLE events ADD CONSTRAINT ck_events_event_type "
            f"CHECK ({EVENT_TYPE_CHECK_SQL})"
        ))
        return

    if sync_conn.dialect.name != "sqlite":
        raise RuntimeError("Не поддерживается обновление видов мероприятий")

    # SQLite не умеет изменять CHECK. Пересоздаём таблицу в одной транзакции,
    # сохраняя исходные столбцы, данные, индексы и триггеры.
    create_sql = sync_conn.scalar(text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='events'"
    ))
    if old_check not in create_sql:
        raise RuntimeError("Не удалось найти ограничение видов мероприятий")
    schema_sql = create_sql[create_sql.index("("):].replace(
        old_check, EVENT_TYPE_CHECK_SQL, 1
    )
    extra_sql = list(sync_conn.scalars(text(
        "SELECT sql FROM sqlite_master "
        "WHERE tbl_name='events' AND type IN ('index','trigger') AND sql IS NOT NULL"
    )))
    quote = sync_conn.dialect.identifier_preparer.quote
    columns = ", ".join(
        quote(column["name"]) for column in inspect(sync_conn).get_columns("events")
    )
    sync_conn.exec_driver_sql(f"CREATE TABLE events_type_upgrade {schema_sql}")
    sync_conn.exec_driver_sql(
        f"INSERT INTO events_type_upgrade ({columns}) SELECT {columns} FROM events"
    )
    sync_conn.exec_driver_sql("DROP TABLE events")
    sync_conn.exec_driver_sql("ALTER TABLE events_type_upgrade RENAME TO events")
    for sql in extra_sql:
        sync_conn.exec_driver_sql(sql)


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


@observed
async def init_models() -> None:
    """Создаёт/дополняет схему и обязательный справочник ролей."""
    async with engine.connect() as conn:
        restore_foreign_keys = False
        sqlite_upgrade = False
        if conn.dialect.name == "sqlite":
            sqlite_upgrade = bool(await conn.run_sync(_outdated_event_type_check))
            if sqlite_upgrade:
                restore_foreign_keys = bool(await conn.scalar(text("PRAGMA foreign_keys")))
            await conn.commit()
        try:
            # PRAGMA foreign_keys изменяется только вне транзакции. Это
            # предотвращает каскадное удаление записей при замене events.
            if restore_foreign_keys:
                await conn.execute(text("PRAGMA foreign_keys=OFF"))
                await conn.commit()
            async with conn.begin():
                if sqlite_upgrade:
                    # sqlite3 в legacy-режиме не начинает транзакцию на DDL.
                    await conn.execute(text("BEGIN"))
                for name, step in (
                    ("prepare_legacy_sqlite", _prepare_legacy_sqlite),
                    ("create_tables", Base.metadata.create_all),
                    ("ensure_indexes", _ensure_indexes),
                    ("add_compatible_columns", _add_compatible_columns),
                    ("expand_event_type_check", _expand_event_type_check),
                    ("seed_roles", _seed_roles),
                ):
                    with operation(f"db.schema.{name}"):
                        await conn.run_sync(step)
        finally:
            if restore_foreign_keys:
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                await conn.commit()


@observed
async def dispose() -> None:
    await engine.dispose()
