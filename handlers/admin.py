"""Команды администратора/судьи: создание и управление играми. Доступ по ADMIN_IDS."""

from __future__ import annotations
from datetime import datetime, timezone
from functools import wraps
from html import escape

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import club_tz, is_admin
from constants import (
    CB_ADMIN_CREATE_EVENT,
    CB_ADMIN_EVENTS,
    CB_ADMIN_EVENT_CANCEL,
    CB_ADMIN_EVENT_CONFIRM,
    CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX,
    CB_ADMIN_EVENT_DELETE_PREFIX,
    CB_ADMIN_EVENT_EDIT_CLEAR,
    CB_ADMIN_EVENT_EDIT_FIELD_PREFIX,
    CB_ADMIN_EVENT_EDIT_PREFIX,
    CB_ADMIN_EVENT_VIEW_PREFIX,
    CB_ADMIN_EVENT_SKIP_LOCATION,
    CB_ADMIN_EVENT_SKIP_NOTE,
)
from db.engine import Session
from db import repo
from db.models import GAME_CLOSED, GAME_CANCELLED
from gametime import as_utc, parse_local, fmt
from handlers.games import game_card_payload
from keyboards.admin import (
    admin_event_detail_keyboard,
    admin_events_keyboard,
    delete_event_confirmation_keyboard,
    event_confirmation_keyboard,
    event_created_keyboard,
    event_creation_cancel_keyboard,
    event_edit_fields_keyboard,
    event_edit_input_keyboard,
    event_location_keyboard,
    event_note_keyboard,
)
from keyboards.menu import GREETING, main_menu_keyboard


(
    EVENT_TITLE,
    EVENT_DATETIME,
    EVENT_CAPACITY,
    EVENT_LOCATION,
    EVENT_NOTE,
    EVENT_CONFIRM,
) = range(6)

EVENT_EDIT_MENU, EVENT_EDIT_VALUE = range(2)

_EVENT_TITLE = "admin_event_title"
_EVENT_STARTS_AT = "admin_event_starts_at"
_EVENT_CAPACITY = "admin_event_capacity"
_EVENT_LOCATION = "admin_event_location"
_EVENT_NOTE = "admin_event_note"
_EVENT_KEYS = (
    _EVENT_TITLE,
    _EVENT_STARTS_AT,
    _EVENT_CAPACITY,
    _EVENT_LOCATION,
    _EVENT_NOTE,
)
_EDIT_EVENT_ID = "admin_edit_event_id"
_EDIT_FIELD = "admin_edit_field"


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Команда только для администраторов.")
            return
        return await func(update, context)
    return wrapper


async def _deny_admin(update: Update) -> bool:
    if is_admin(update.effective_user.id):
        return False
    if update.callback_query:
        await update.callback_query.answer(
            "Этот раздел доступен только администраторам.",
            show_alert=True,
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Этот раздел доступен только администраторам."
        )
    return True


def _clear_event_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in _EVENT_KEYS:
        context.user_data.pop(key, None)


def parse_event_datetime(value: str) -> datetime:
    normalized = " ".join(value.split())
    for pattern in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            local = datetime.strptime(normalized, pattern).replace(
                tzinfo=club_tz()
            )
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("Не удалось разобрать дату и время")


def _confirmation_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    title = escape(context.user_data[_EVENT_TITLE])
    starts_at = context.user_data[_EVENT_STARTS_AT]
    capacity = context.user_data[_EVENT_CAPACITY]
    location = context.user_data.get(_EVENT_LOCATION)
    note = context.user_data.get(_EVENT_NOTE)
    lines = [
        "Проверьте встречу перед созданием:",
        "",
        f"🎲 <b>{title}</b>",
        f"📅 {fmt(starts_at)}",
        f"👥 Мест: <b>{capacity}</b>",
        f"📍 {escape(location) if location else 'не указано'}",
    ]
    if note:
        lines.append(f"📝 {escape(note)}")
    return "\n".join(lines)


async def on_create_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    _clear_event_draft(context)
    await query.edit_message_text(
        "Как будет называться игровая встреча?\n\n"
        "Отправьте название сообщением.",
        reply_markup=event_creation_cancel_keyboard(),
    )
    return EVENT_TITLE


async def on_event_title(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    title = " ".join(update.message.text.split())
    if not 2 <= len(title) <= 100:
        await update.message.reply_text(
            "Название должно содержать от 2 до 100 символов.",
            reply_markup=event_creation_cancel_keyboard(),
        )
        return EVENT_TITLE
    context.user_data[_EVENT_TITLE] = title
    await update.message.reply_text(
        "Когда состоится встреча?\n\n"
        "Введите дату и время в формате "
        "<code>25.07.2026 19:00</code>.",
        parse_mode="HTML",
        reply_markup=event_creation_cancel_keyboard(),
    )
    return EVENT_DATETIME


async def on_event_datetime(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    try:
        starts_at = parse_event_datetime(update.message.text)
    except ValueError:
        await update.message.reply_text(
            "Не удалось разобрать дату и время. Используйте формат "
            "<code>25.07.2026 19:00</code>.",
            parse_mode="HTML",
            reply_markup=event_creation_cancel_keyboard(),
        )
        return EVENT_DATETIME
    if starts_at <= datetime.now(timezone.utc):
        await update.message.reply_text(
            "Встреча должна быть назначена на будущее.",
            reply_markup=event_creation_cancel_keyboard(),
        )
        return EVENT_DATETIME

    context.user_data[_EVENT_STARTS_AT] = starts_at
    await update.message.reply_text(
        "Сколько участников смогут записаться?\n\n"
        "Введите число от 1 до 100.",
        reply_markup=event_creation_cancel_keyboard(),
    )
    return EVENT_CAPACITY


async def on_event_capacity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    raw = update.message.text.strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 100:
        await update.message.reply_text(
            "Введите целое число от 1 до 100.",
            reply_markup=event_creation_cancel_keyboard(),
        )
        return EVENT_CAPACITY
    context.user_data[_EVENT_CAPACITY] = int(raw)
    await update.message.reply_text(
        "Где пройдёт встреча?\n\n"
        "Отправьте место проведения или нажмите «Не указывать».",
        reply_markup=event_location_keyboard(),
    )
    return EVENT_LOCATION


async def on_event_location(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    location = " ".join(update.message.text.split())
    if not 2 <= len(location) <= 200:
        await update.message.reply_text(
            "Место проведения должно содержать от 2 до 200 символов.",
            reply_markup=event_location_keyboard(),
        )
        return EVENT_LOCATION
    context.user_data[_EVENT_LOCATION] = location
    await update.message.reply_text(
        "Добавьте описание встречи или нажмите «Без описания».",
        reply_markup=event_note_keyboard(),
    )
    return EVENT_NOTE


async def on_skip_event_location(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_EVENT_LOCATION] = None
    await query.edit_message_text(
        "Добавьте описание встречи или нажмите «Без описания».",
        reply_markup=event_note_keyboard(),
    )
    return EVENT_NOTE


async def on_event_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    note = " ".join(update.message.text.split())
    if len(note) > 1000:
        await update.message.reply_text(
            "Описание должно быть не длиннее 1000 символов.",
            reply_markup=event_note_keyboard(),
        )
        return EVENT_NOTE
    context.user_data[_EVENT_NOTE] = note
    await update.message.reply_text(
        _confirmation_text(context),
        parse_mode="HTML",
        reply_markup=event_confirmation_keyboard(),
    )
    return EVENT_CONFIRM


async def on_skip_event_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_EVENT_NOTE] = None
    await query.edit_message_text(
        _confirmation_text(context),
        parse_mode="HTML",
        reply_markup=event_confirmation_keyboard(),
    )
    return EVENT_CONFIRM


async def on_confirm_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    if any(key not in context.user_data for key in _EVENT_KEYS):
        await query.edit_message_text(
            "Черновик встречи устарел. Начните создание заново.",
            reply_markup=main_menu_keyboard(True),
        )
        _clear_event_draft(context)
        return ConversationHandler.END

    async with Session() as session:
        user = update.effective_user
        name = " ".join(filter(
            None, [user.first_name, user.last_name]
        )) or ""
        host = await repo.get_or_create_player(
            session, user.id, user.username, name
        )
        event = await repo.create_game(
            session,
            starts_at=context.user_data[_EVENT_STARTS_AT],
            capacity=context.user_data[_EVENT_CAPACITY],
            location=context.user_data[_EVENT_LOCATION],
            note=context.user_data[_EVENT_NOTE],
            host_id=host.id,
            title=context.user_data[_EVENT_TITLE],
        )
        event_id = event.id
        event_title = event.title
        event_starts_at = event.starts_at

    _clear_event_draft(context)
    await query.edit_message_text(
        f"✅ Встреча <b>{escape(event_title)}</b> создана.\n\n"
        f"Она уже доступна для записи всем пользователям: "
        f"<b>{fmt(event_starts_at)}</b>.",
        parse_mode="HTML",
        reply_markup=event_created_keyboard(event_id),
    )
    return ConversationHandler.END


async def on_cancel_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    _clear_event_draft(context)
    await query.edit_message_text(
        GREETING,
        reply_markup=main_menu_keyboard(True),
    )
    return ConversationHandler.END


async def on_admin_events(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await _deny_admin(update):
        return
    query = update.callback_query
    await query.answer()
    async with Session() as session:
        events = await repo.list_upcoming_games(session)

    text = "🗓 <b>Управление встречами</b>"
    if not events:
        text += "\n\nПредстоящих встреч нет."
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_events_keyboard(events),
    )


async def on_admin_event_view(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await _deny_admin(update):
        return
    query = update.callback_query
    await query.answer()
    event_id = int(
        query.data[len(CB_ADMIN_EVENT_VIEW_PREFIX):]
    )
    async with Session() as session:
        user = update.effective_user
        name = " ".join(filter(
            None, [user.first_name, user.last_name]
        )) or ""
        player = await repo.get_or_create_player(
            session, user.id, user.username, name
        )
        event = await repo.get_game(session, event_id)
        if event is None:
            events = await repo.list_upcoming_games(session)
            await query.edit_message_text(
                "Встреча не найдена.",
                reply_markup=admin_events_keyboard(events),
            )
            return
        text, _ = await game_card_payload(
            session,
            event,
            player,
        )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_event_detail_keyboard(event.id),
    )


def _event_edit_text(event) -> str:
    capacity = event.capacity if event.capacity is not None else "без лимита"
    location = escape(event.location) if event.location else "не указано"
    note = escape(event.note) if event.note else "не указано"
    return (
        "✏️ <b>Изменение встречи</b>\n\n"
        f"🎲 {escape(event.title)}\n"
        f"📅 {fmt(event.starts_at)}\n"
        f"👥 Мест: {capacity}\n"
        f"📍 {location}\n"
        f"📝 {note}\n\n"
        "Что изменить?"
    )


async def on_edit_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = int(
        query.data[len(CB_ADMIN_EVENT_EDIT_PREFIX):]
    )
    context.user_data[_EDIT_EVENT_ID] = event_id
    context.user_data.pop(_EDIT_FIELD, None)
    async with Session() as session:
        event = await repo.get_game(session, event_id)
    if event is None:
        await query.edit_message_text("Встреча не найдена.")
        return ConversationHandler.END
    await query.edit_message_text(
        _event_edit_text(event),
        parse_mode="HTML",
        reply_markup=event_edit_fields_keyboard(event.id),
    )
    return EVENT_EDIT_MENU


async def on_edit_event_field(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get(_EDIT_EVENT_ID)
    field = query.data[len(CB_ADMIN_EVENT_EDIT_FIELD_PREFIX):]
    prompts = {
        "title": "Введите новое название встречи.",
        "starts_at": (
            "Введите новую дату и время в формате "
            "<code>25.07.2026 19:00</code>."
        ),
        "capacity": "Введите новое количество мест от 1 до 100.",
        "location": "Введите новое место проведения.",
        "note": "Введите новое описание встречи.",
    }
    if event_id is None or field not in prompts:
        await query.edit_message_text("Не удалось открыть редактор.")
        return ConversationHandler.END
    context.user_data[_EDIT_FIELD] = field
    await query.edit_message_text(
        prompts[field],
        parse_mode="HTML",
        reply_markup=event_edit_input_keyboard(
            event_id, can_clear=field in ("location", "note")
        ),
    )
    return EVENT_EDIT_VALUE


async def on_edit_event_value(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    event_id = context.user_data.get(_EDIT_EVENT_ID)
    field = context.user_data.get(_EDIT_FIELD)
    if event_id is None or field is None:
        await update.message.reply_text("Черновик изменения устарел.")
        return ConversationHandler.END

    raw = " ".join(update.message.text.split())
    can_clear = field in ("location", "note")
    keyboard = event_edit_input_keyboard(event_id, can_clear=can_clear)
    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            await update.message.reply_text("Встреча не найдена.")
            return ConversationHandler.END

        if field == "title":
            if not 2 <= len(raw) <= 100:
                await update.message.reply_text(
                    "Название должно содержать от 2 до 100 символов.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            event.title = raw
        elif field == "starts_at":
            try:
                starts_at = parse_event_datetime(raw)
            except ValueError:
                await update.message.reply_text(
                    "Не удалось разобрать дату и время. Используйте формат "
                    "<code>25.07.2026 19:00</code>.",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            if starts_at <= datetime.now(timezone.utc):
                await update.message.reply_text(
                    "Встреча должна быть назначена на будущее.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            event.starts_at = starts_at
        elif field == "capacity":
            if not raw.isdigit() or not 1 <= int(raw) <= 100:
                await update.message.reply_text(
                    "Введите целое число от 1 до 100.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            capacity = int(raw)
            active = await repo.active_count(session, event.id)
            if capacity < active:
                await update.message.reply_text(
                    f"Сейчас записано участников: {active}. "
                    "Количество мест не может быть меньше.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            event.capacity = capacity
        elif field == "location":
            if not 2 <= len(raw) <= 200:
                await update.message.reply_text(
                    "Место проведения должно содержать "
                    "от 2 до 200 символов.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            event.location = raw
        elif field == "note":
            if not 2 <= len(raw) <= 1000:
                await update.message.reply_text(
                    "Описание должно содержать от 2 до 1000 символов.",
                    reply_markup=keyboard,
                )
                return EVENT_EDIT_VALUE
            event.note = raw
        await session.commit()

    context.user_data.pop(_EDIT_FIELD, None)
    await update.message.reply_text(
        "✅ Изменения сохранены.\n\n" + _event_edit_text(event),
        parse_mode="HTML",
        reply_markup=event_edit_fields_keyboard(event.id),
    )
    return EVENT_EDIT_MENU


async def on_clear_event_field(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = context.user_data.get(_EDIT_EVENT_ID)
    field = context.user_data.get(_EDIT_FIELD)
    if event_id is None or field not in ("location", "note"):
        await query.edit_message_text("Не удалось очистить поле.")
        return ConversationHandler.END

    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            await query.edit_message_text("Встреча не найдена.")
            return ConversationHandler.END
        setattr(event, field, None)
        await session.commit()

    context.user_data.pop(_EDIT_FIELD, None)
    await query.edit_message_text(
        "✅ Поле очищено.\n\n" + _event_edit_text(event),
        parse_mode="HTML",
        reply_markup=event_edit_fields_keyboard(event.id),
    )
    return EVENT_EDIT_MENU


async def on_finish_event_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.pop(_EDIT_EVENT_ID, None)
    context.user_data.pop(_EDIT_FIELD, None)
    await on_admin_event_view(update, context)
    return ConversationHandler.END


async def on_delete_event_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await _deny_admin(update):
        return
    query = update.callback_query
    await query.answer()
    event_id = int(
        query.data[len(CB_ADMIN_EVENT_DELETE_PREFIX):]
    )
    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            events = await repo.list_upcoming_games(session)
            await query.edit_message_text(
                "Встреча уже удалена.",
                reply_markup=admin_events_keyboard(events),
            )
            return
        active, waitlist = await repo.roster(session, event.id)

    await query.edit_message_text(
        f"Удалить встречу <b>{escape(event.title)}</b> "
        f"({fmt(event.starts_at)})?\n\n"
        f"Записано участников: <b>{len(active)}</b>"
        + (
            f", в листе ожидания: <b>{len(waitlist)}</b>"
            if waitlist else ""
        )
        + "\n\nБудут удалены все регистрации и внесённые результаты.",
        parse_mode="HTML",
        reply_markup=delete_event_confirmation_keyboard(event.id),
    )


async def on_delete_event_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await _deny_admin(update):
        return
    query = update.callback_query
    await query.answer()
    event_id = int(
        query.data[len(CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX):]
    )
    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            events = await repo.list_upcoming_games(session)
            await query.edit_message_text(
                "Встреча уже удалена.",
                reply_markup=admin_events_keyboard(events),
            )
            return
        if as_utc(event.starts_at) <= datetime.now(timezone.utc):
            await query.edit_message_text(
                "Прошедшую встречу нельзя удалить из этого раздела.",
                reply_markup=admin_events_keyboard(
                    await repo.list_upcoming_games(session)
                ),
            )
            return

        active, waitlist = await repo.roster(session, event.id)
        notify_ids = {
            registration.player.tg_id
            for registration in active + waitlist
            if registration.player.tg_id is not None
        }
        event_title = event.title
        event_when = fmt(event.starts_at)
        await repo.delete_event(session, event.id)
        events = await repo.list_upcoming_games(session)

    await query.edit_message_text(
        f"✅ Встреча <b>{escape(event_title)}</b> удалена.",
        parse_mode="HTML",
        reply_markup=admin_events_keyboard(events),
    )
    for tg_id in notify_ids:
        try:
            await context.bot.send_message(
                tg_id,
                f"⚠️ Встреча «{event_title}» ({event_when}) удалена.",
            )
        except Exception:
            pass


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.message.reply_text(
        f"Ваш Telegram-ID: <code>{u.id}</code>\n"
        "Добавьте его в переменную окружения ADMIN_IDS, чтобы создавать игры.",
        parse_mode="HTML",
    )


@admin_only
async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    usage = (
        "Формат:\n"
        "<code>/newgame ГГГГ-ММ-ДД ЧЧ:ММ [мест] [место проведения]</code>\n\n"
        "Пример: <code>/newgame 2026-07-05 19:00 10 Клуб на Ленина</code>"
    )
    if len(args) < 2:
        await update.message.reply_text(usage, parse_mode="HTML")
        return
    try:
        starts_at = parse_local(args[0], args[1])
    except ValueError:
        await update.message.reply_text("🚫 Не разобрал дату/время.\n\n" + usage,
                                        parse_mode="HTML")
        return

    rest = args[2:]
    capacity = 10
    if rest and rest[0].isdigit():
        capacity = int(rest[0])
        rest = rest[1:]
    location = " ".join(rest) or None

    async with Session() as session:
        u = update.effective_user
        name = " ".join(filter(None, [u.first_name, u.last_name])) or ""
        host = await repo.get_or_create_player(session, u.id, u.username, name)
        game = await repo.create_game(
            session, starts_at=starts_at, capacity=capacity,
            location=location, note=None, host_id=host.id,
        )
        game_id, when = game.id, fmt(game.starts_at)

    await update.message.reply_text(
        f"✅ Игра #{game_id} создана: <b>{when}</b>, мест {capacity}"
        + (f", {location}" if location else ""),
        parse_mode="HTML",
    )


@admin_only
async def cmd_roster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Формат: <code>/roster ID</code>", parse_mode="HTML")
        return
    game_id = int(context.args[0])
    async with Session() as session:
        game = await repo.get_game(session, game_id)
        if game is None:
            await update.message.reply_text("🚫 Игра не найдена.")
            return
        active, waitlist = await repo.roster(session, game_id)
        when = fmt(game.starts_at)

    capacity = game.capacity if game.capacity is not None else "∞"
    lines = [f"🎲 <b>Игра #{game_id} — {when}</b> ({game.status})",
             f"👥 {len(active)}/{capacity}"]
    if active:
        lines.append("\n<b>Записаны:</b>")
        lines.extend(
            f"  {i}. {escape(r.player.game_display)}"
            for i, r in enumerate(active, 1)
        )
    if waitlist:
        lines.append("\n<b>Лист ожидания:</b>")
        lines.extend(
            f"  {i}. {escape(r.player.game_display)}"
            for i, r in enumerate(waitlist, 1)
        )
    if not active and not waitlist:
        lines.append("\nПока никто не записан.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def cmd_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with Session() as session:
        games = await repo.list_upcoming_games(session)
        counts = await repo.counts_for_games(session, [g.id for g in games])

    if not games:
        await update.message.reply_text("Нет предстоящих игр.")
        return
    lines = ["📋 <b>Предстоящие игры</b>", ""]
    for g in games:
        active, wait = counts.get(g.id, (0, 0))
        capacity = g.capacity if g.capacity is not None else "∞"
        lines.append(f"#{g.id} · {fmt(g.starts_at)} · {active}/{capacity}"
                     + (f" +{wait}🕓" if wait else ""))
    lines.append("\nРостер: <code>/roster ID</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _set_status_and_notify(update, context, status: str, verb: str) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            f"Формат: <code>/{update.message.text.split()[0].lstrip('/')} ID</code>",
            parse_mode="HTML")
        return
    game_id = int(context.args[0])
    async with Session() as session:
        game = await repo.get_game(session, game_id)
        if game is None:
            await update.message.reply_text("🚫 Игра не найдена.")
            return
        active, waitlist = await repo.roster(session, game_id)
        notify_ids = [r.player.tg_id for r in active + waitlist]
        when = fmt(game.starts_at)
        await repo.set_game_status(session, game, status)

    await update.message.reply_text(f"✅ Игра #{game_id} ({when}) — {verb}.")

    if status == GAME_CANCELLED:
        for tg_id in notify_ids:
            try:
                await context.bot.send_message(tg_id, f"⚠️ Игра {when} отменена.")
            except Exception:
                pass


@admin_only
async def cmd_closegame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_status_and_notify(update, context, GAME_CLOSED, "запись закрыта")


@admin_only
async def cmd_cancelgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_status_and_notify(update, context, GAME_CANCELLED, "отменена")


def register(app) -> None:
    creation_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                on_create_event,
                pattern=f"^{CB_ADMIN_CREATE_EVENT}$",
            ),
        ],
        states={
            EVENT_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_event_title,
                ),
            ],
            EVENT_DATETIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_event_datetime,
                ),
            ],
            EVENT_CAPACITY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_event_capacity,
                ),
            ],
            EVENT_LOCATION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_event_location,
                ),
                CallbackQueryHandler(
                    on_skip_event_location,
                    pattern=f"^{CB_ADMIN_EVENT_SKIP_LOCATION}$",
                ),
            ],
            EVENT_NOTE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_event_note,
                ),
                CallbackQueryHandler(
                    on_skip_event_note,
                    pattern=f"^{CB_ADMIN_EVENT_SKIP_NOTE}$",
                ),
            ],
            EVENT_CONFIRM: [
                CallbackQueryHandler(
                    on_confirm_event,
                    pattern=f"^{CB_ADMIN_EVENT_CONFIRM}$",
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(
                on_cancel_event,
                pattern=f"^{CB_ADMIN_EVENT_CANCEL}$",
            ),
        ],
        allow_reentry=True,
    )
    edit_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                on_edit_event,
                pattern=f"^{CB_ADMIN_EVENT_EDIT_PREFIX}",
            ),
        ],
        states={
            EVENT_EDIT_MENU: [
                CallbackQueryHandler(
                    on_edit_event_field,
                    pattern=f"^{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}",
                ),
                CallbackQueryHandler(
                    on_finish_event_edit,
                    pattern=f"^{CB_ADMIN_EVENT_VIEW_PREFIX}",
                ),
            ],
            EVENT_EDIT_VALUE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_edit_event_value,
                ),
                CallbackQueryHandler(
                    on_clear_event_field,
                    pattern=f"^{CB_ADMIN_EVENT_EDIT_CLEAR}$",
                ),
                CallbackQueryHandler(
                    on_edit_event,
                    pattern=f"^{CB_ADMIN_EVENT_EDIT_PREFIX}",
                ),
                CallbackQueryHandler(
                    on_finish_event_edit,
                    pattern=f"^{CB_ADMIN_EVENT_VIEW_PREFIX}",
                ),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(creation_conversation)
    app.add_handler(edit_conversation)
    app.add_handler(CallbackQueryHandler(
        on_admin_events, pattern=f"^{CB_ADMIN_EVENTS}$"
    ))
    app.add_handler(CallbackQueryHandler(
        on_admin_event_view,
        pattern=f"^{CB_ADMIN_EVENT_VIEW_PREFIX}",
    ))
    app.add_handler(CallbackQueryHandler(
        on_delete_event_confirm,
        pattern=f"^{CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX}",
    ))
    app.add_handler(CallbackQueryHandler(
        on_delete_event_request,
        pattern=f"^{CB_ADMIN_EVENT_DELETE_PREFIX}",
    ))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("games", cmd_games))
    app.add_handler(CommandHandler("roster", cmd_roster))
    app.add_handler(CommandHandler("closegame", cmd_closegame))
    app.add_handler(CommandHandler("cancelgame", cmd_cancelgame))
