from __future__ import annotations

from html import escape
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import is_admin
from constants import (
    CB_ADMIN_RESULTS,
    CB_CANCEL_GAME_NICKNAME,
    CB_CREATE_GAME_NICKNAME,
    CB_MY_RATING,
    CB_MY_RESULTS,
    CB_STATS,
)
from db import repo
from db.engine import Session
from db.models import Player
from gametime import fmt
from keyboards.results import (
    CB_RESULT_ADD_PREFIX,
    CB_RESULT_CANCEL_INPUT,
    CB_RESULT_EVENT_PREFIX,
    CB_RESULT_GAME_PREFIX,
    CB_RESULT_GAME_ADD_PREFIX,
    CB_RESULT_GAME_DELETE_CONFIRM_PREFIX,
    CB_RESULT_GAME_DELETE_PREFIX,
    CB_RESULT_GAMES_PREFIX,
    CB_RESULT_GUEST,
    CB_RESULT_HOST,
    CB_RESULT_PLAYER_PREFIX,
    CB_RESULT_ROLE_PREFIX,
    CB_RESULT_SKIPS,
    CB_RESULT_SLOT_PREFIX,
    CB_RESULT_TABLE,
    CB_RESULT_WINNER_PREFIX,
    CB_RESULT_WINNER_MENU,
    ROLE_EMOJIS,
    ROLE_LABELS,
    cancel_input_keyboard,
    confirm_delete_game_keyboard,
    event_result_keyboard,
    game_management_keyboard,
    my_results_keyboard,
    nickname_input_keyboard,
    played_games_keyboard,
    participant_picker_keyboard,
    rating_keyboard,
    recent_events_keyboard,
    role_keyboard,
    stats_keyboard,
    table_seats_keyboard,
    winner_keyboard,
)
from ratings import RatingsServiceError, fetch_player_rating


logger = logging.getLogger(__name__)

(
    EVENTS,
    EVENT_DETAIL,
    WAIT_GAME_COUNT,
    GAMES,
    GAME_EDIT,
    ROLE_SELECT,
    WAIT_GUEST,
) = range(7)

STATS_VIEW, WAIT_GAME_NICKNAME = range(2)

_EVENT_ID = "result_event_id"
_GAME_ID = "result_game_id"
_USER_ID = "result_user_id"
_PICK_MODE = "result_pick_mode"
_TARGET_SEAT = "result_target_seat"


def _user_identity(update: Update) -> tuple[int, str | None, str]:
    user = update.effective_user
    name = " ".join(filter(None, [user.first_name, user.last_name])) or ""
    return user.id, user.username, name


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
            "Этот раздел доступен только администраторам."
        )
    return True


async def on_admin_results(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()

    async with Session() as session:
        events = await repo.list_recent_events(session)

    text = "📝 <b>Результаты игр</b>\n\nВстречи за последние 30 дней:"
    if not events:
        text += "\n\nПодходящих встреч пока нет."
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=recent_events_keyboard(events),
    )
    return EVENTS


async def on_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = int(query.data[len(CB_RESULT_EVENT_PREFIX):])
    context.user_data[_EVENT_ID] = event_id
    context.user_data.pop(_GAME_ID, None)

    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            await query.edit_message_text("Встреча не найдена.")
            return EVENTS
        participants = await repo.list_event_participants(session, event_id)
        played_games = await repo.list_event_played_games(session, event_id)

    capacity = event.capacity if event.capacity is not None else "∞"
    lines = [
        f"🎲 <b>{escape(event.title)}</b>",
        f"📅 {fmt(event.starts_at)}",
    ]
    if event.location:
        lines.append(f"📍 {escape(event.location)}")
    if event.note:
        lines.append(f"📝 {escape(event.note)}")
    lines.extend([
        "",
        f"Участников: <b>{len(participants)}/{capacity}</b>",
        f"Партий с результатами: <b>{sum(bool(g.winner_side) for g in played_games)}"
        f"/{len(played_games)}</b>",
    ])
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=event_result_keyboard(event_id, bool(played_games)),
    )
    return EVENT_DETAIL


async def on_add_results(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = int(query.data[len(CB_RESULT_ADD_PREFIX):])
    context.user_data[_EVENT_ID] = event_id
    context.user_data.pop(_GAME_ID, None)
    await query.edit_message_text(
        "Сколько игр было за эту встречу?\n\n"
        "Отправьте число сообщением. Обычно за вечер проходит 3–5 игр.",
        reply_markup=cancel_input_keyboard(),
    )
    return WAIT_GAME_COUNT


async def on_game_count(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    raw = update.message.text.strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 20:
        await update.message.reply_text(
            "Введите целое число от 1 до 20.",
            reply_markup=cancel_input_keyboard(),
        )
        return WAIT_GAME_COUNT

    event_id = context.user_data.get(_EVENT_ID)
    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            await update.message.reply_text("Встреча не найдена.")
            return ConversationHandler.END
        tg_id, username, name = _user_identity(update)
        host = await repo.get_or_create_player(
            session, tg_id, username, name
        )
        games = await repo.create_event_played_games(
            session, event, int(raw), host.id
        )

    await update.message.reply_text(
        f"Создано партий: {len(games)}. Выберите игру:",
        reply_markup=played_games_keyboard(games, event_id),
    )
    return GAMES


async def on_games(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = int(query.data[len(CB_RESULT_GAMES_PREFIX):])
    context.user_data[_EVENT_ID] = event_id
    context.user_data.pop(_GAME_ID, None)
    async with Session() as session:
        games = await repo.list_event_played_games(session, event_id)
    await query.edit_message_text(
        "Выберите игру:",
        reply_markup=played_games_keyboard(games, event_id),
    )
    return GAMES


async def on_add_game(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    event_id = int(query.data[len(CB_RESULT_GAME_ADD_PREFIX):])
    context.user_data[_EVENT_ID] = event_id

    async with Session() as session:
        event = await repo.get_game(session, event_id)
        if event is None:
            await query.edit_message_text("Встреча не найдена.")
            return EVENTS
        tg_id, username, name = _user_identity(update)
        host = await repo.get_or_create_player(
            session, tg_id, username, name
        )
        added = await repo.add_event_played_game(
            session, event, host.id
        )
        games = await repo.list_event_played_games(session, event_id)

    await query.edit_message_text(
        f"Игра №{added.game_number} добавлена.",
        reply_markup=played_games_keyboard(games, event_id),
    )
    return GAMES


async def on_delete_game_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    game_id = int(query.data[len(CB_RESULT_GAME_DELETE_PREFIX):])
    async with Session() as session:
        game = await repo.get_played_game(session, game_id)
    if game is None or game.event_id is None:
        await query.edit_message_text("Игра не найдена.")
        return GAMES
    await query.edit_message_text(
        f"Удалить игру №{game.game_number} вместе с её результатами?",
        reply_markup=confirm_delete_game_keyboard(
            game.id, game.event_id
        ),
    )
    return GAMES


async def on_delete_game_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    game_id = int(
        query.data[len(CB_RESULT_GAME_DELETE_CONFIRM_PREFIX):]
    )
    async with Session() as session:
        event_id = await repo.delete_played_game(session, game_id)
        games = (
            await repo.list_event_played_games(session, event_id)
            if event_id is not None else []
        )
    if event_id is None:
        await query.answer("Игра уже удалена.", show_alert=True)
        return GAMES
    await query.answer("Игра удалена.")
    context.user_data[_EVENT_ID] = event_id
    context.user_data.pop(_GAME_ID, None)
    await query.edit_message_text(
        "Игра удалена. Оставшиеся игры перенумерованы.",
        reply_markup=played_games_keyboard(games, event_id),
    )
    return GAMES


async def _game_data(context: ContextTypes.DEFAULT_TYPE):
    game_id = context.user_data.get(_GAME_ID)
    async with Session() as session:
        game = await repo.get_played_game(session, game_id)
        if game is None or game.event_id is None:
            return None
        participants = await repo.list_event_participants(
            session, game.event_id
        )
        assignment_list = await repo.game_assignments(session, game.id)
        assignments = {
            assignment.user_id: assignment
            for assignment in assignment_list
        }
    return game, participants, assignments


async def _game_payload(context: ContextTypes.DEFAULT_TYPE):
    data = await _game_data(context)
    if data is None:
        return None
    game, participants, assignments = data

    winner = {
        "town": "красные",
        "mafia": "чёрные",
    }.get(game.winner_side, "не выбран")
    assigned = sum(
        registration.player_id in assignments
        for registration in participants
    )
    text = (
        f"🎲 <b>Игра №{game.game_number}</b>\n"
        f"Распределено: <b>{assigned}/{len(participants)}</b> · "
        f"Победитель: <b>{winner}</b>\n\n"
        "Что заполняем?"
    )
    return text, game_management_keyboard(game)


async def _edit_game(
    query, context: ContextTypes.DEFAULT_TYPE
) -> int:
    payload = await _game_payload(context)
    if payload is None:
        await query.edit_message_text("Игра не найдена.")
        return GAMES
    text, keyboard = payload
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=keyboard
    )
    return GAME_EDIT


async def _edit_table(
    query, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = await _game_data(context)
    if data is None:
        await query.edit_message_text("Игра не найдена.")
        return GAMES
    game, participants, assignments = data
    await query.edit_message_text(
        f"🪑 <b>Игроки за столом · Игра №{game.game_number}</b>\n\n"
        "Выберите место:",
        parse_mode="HTML",
        reply_markup=table_seats_keyboard(
            participants, assignments, game
        ),
    )
    return GAME_EDIT


async def _edit_picker(
    query, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = await _game_data(context)
    if data is None:
        await query.edit_message_text("Игра не найдена.")
        return GAMES
    game, participants, assignments = data
    mode = context.user_data.get(_PICK_MODE)
    if mode == "seat":
        title = f"Кого посадить на место №{context.user_data.get(_TARGET_SEAT)}?"
    elif mode == "skip":
        title = "Кто пропустил эту игру?"
    else:
        title = "Кто был ведущим?"
    await query.edit_message_text(
        title,
        reply_markup=participant_picker_keyboard(
            participants, assignments, game, mode
        ),
    )
    return GAME_EDIT


async def on_game(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_GAME_ID] = int(
        query.data[len(CB_RESULT_GAME_PREFIX):]
    )
    context.user_data.pop(_PICK_MODE, None)
    context.user_data.pop(_TARGET_SEAT, None)
    return await _edit_game(query, context)


async def on_table(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_PICK_MODE] = "seat"
    return await _edit_table(query, context)


async def on_slot(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_PICK_MODE] = "seat"
    context.user_data[_TARGET_SEAT] = int(
        query.data[len(CB_RESULT_SLOT_PREFIX):]
    )
    return await _edit_picker(query, context)


async def on_skips(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_PICK_MODE] = "skip"
    context.user_data.pop(_TARGET_SEAT, None)
    return await _edit_picker(query, context)


async def on_host(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data[_PICK_MODE] = "host"
    context.user_data.pop(_TARGET_SEAT, None)
    return await _edit_picker(query, context)


async def on_winner_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    async with Session() as session:
        game = await repo.get_played_game(
            session, context.user_data.get(_GAME_ID)
        )
    if game is None:
        await query.edit_message_text("Игра не найдена.")
        return GAMES
    await query.edit_message_text(
        f"Кто победил в игре №{game.game_number}?",
        reply_markup=winner_keyboard(game),
    )
    return GAME_EDIT


async def on_player(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    user_id = int(query.data[len(CB_RESULT_PLAYER_PREFIX):])
    context.user_data[_USER_ID] = user_id
    mode = context.user_data.get(_PICK_MODE)

    if mode in ("skip", "host"):
        async with Session() as session:
            game = await repo.get_played_game(
                session, context.user_data.get(_GAME_ID)
            )
            if game is None:
                await query.answer()
                await query.edit_message_text("Игра не найдена.")
                return GAMES
            if mode == "skip":
                selected = await repo.toggle_game_skip(
                    session, game, user_id
                )
                message = (
                    "Добавлен в пропустившие."
                    if selected else "Убран из пропустивших."
                )
            else:
                selected = await repo.set_game_host(
                    session, game, user_id
                )
                message = (
                    "Ведущий выбран."
                    if selected else "Не удалось выбрать ведущего."
                )
        await query.answer(message)
        return await _edit_picker(query, context)

    async with Session() as session:
        player = await session.get(Player, user_id)
    if player is None:
        await query.answer()
        await query.edit_message_text("Игрок не найден.")
        return GAME_EDIT

    await query.answer()
    await query.edit_message_text(
        f"Выберите роль для <b>{escape(player.game_display)}</b>:",
        parse_mode="HTML",
        reply_markup=role_keyboard(),
    )
    return ROLE_SELECT


async def on_role(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    role_code = query.data[len(CB_RESULT_ROLE_PREFIX):]
    game_id = context.user_data.get(_GAME_ID)
    user_id = context.user_data.get(_USER_ID)
    seat = context.user_data.get(_TARGET_SEAT)

    async with Session() as session:
        error = await repo.role_limit_error(
            session,
            game_id,
            user_id,
            role_code,
            replacing_seat=seat,
        )
        game = await repo.get_played_game(session, game_id)
        if game is None:
            await query.answer()
            await query.edit_message_text("Игра не найдена.")
            return GAMES
        if error:
            await query.answer(error, show_alert=True)
            return ROLE_SELECT
        code, _ = await repo.assign_game_player(
            session,
            game,
            user_id,
            role_code,
            seat,
            replace_seat=True,
        )

    if code != "saved":
        await query.answer(
            "Не удалось сохранить роль.", show_alert=True
        )
        return ROLE_SELECT
    await query.answer("Сохранено.")
    context.user_data[_PICK_MODE] = "seat"
    return await _edit_table(query, context)


async def on_winner(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    winner = query.data[len(CB_RESULT_WINNER_PREFIX):]
    async with Session() as session:
        game = await repo.get_played_game(
            session, context.user_data.get(_GAME_ID)
        )
        if game is None:
            await query.answer()
            await query.edit_message_text("Игра не найдена.")
            return GAMES
        saved, reason = await repo.set_game_winner(
            session, game, winner
        )
    if not saved:
        await query.answer(reason, show_alert=True)
        return GAME_EDIT
    await query.answer("Результат сохранён.")
    return await _edit_game(query, context)


async def on_guest_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите игровой ник участника:",
        reply_markup=cancel_input_keyboard(),
    )
    return WAIT_GUEST


async def on_guest_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    nickname = " ".join(update.message.text.split())
    if not 2 <= len(nickname) <= 64:
        await update.message.reply_text(
            "Ник должен содержать от 2 до 64 символов.",
            reply_markup=cancel_input_keyboard(),
        )
        return WAIT_GUEST

    event_id = context.user_data.get(_EVENT_ID)
    async with Session() as session:
        await repo.add_guest_to_event(session, event_id, nickname)

    data = await _game_data(context)
    if data is None:
        await update.message.reply_text("Игра не найдена.")
        return GAMES
    game, participants, assignments = data
    mode = context.user_data.get(_PICK_MODE)
    await update.message.reply_text(
        f"Игрок «{escape(nickname)}» добавлен. Выберите участника:",
        parse_mode="HTML",
        reply_markup=participant_picker_keyboard(
            participants, assignments, game, mode
        ),
    )
    return GAME_EDIT


async def on_cancel_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    if context.user_data.get(_GAME_ID):
        if context.user_data.get(_PICK_MODE):
            return await _edit_picker(query, context)
        return await _edit_game(query, context)

    event_id = context.user_data.get(_EVENT_ID)
    async with Session() as session:
        event = await repo.get_game(session, event_id)
        games = await repo.list_event_played_games(session, event_id)
    if event is None:
        await query.edit_message_text("Встреча не найдена.")
        return EVENTS
    await query.edit_message_text(
        f"🎲 <b>{escape(event.title)}</b>\n📅 {fmt(event.starts_at)}",
        parse_mode="HTML",
        reply_markup=event_result_keyboard(event.id, bool(games)),
    )
    return EVENT_DETAIL


def _format_rating(value: int | float) -> str:
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _stats_payload(player: Player) -> tuple[str, bool]:
    nickname = (player.game_nickname or "").strip()
    if not nickname:
        return (
            "📊 <b>Моя статистика</b>\n\n"
            "Игровой ник: <b>не указан</b>\n\n"
            "Создайте игровой ник, чтобы увидеть рейтинг.",
            False,
        )

    return (
        "📊 <b>Моя статистика</b>\n\n"
        f"Игровой ник: <b>{escape(nickname)}</b>",
        True,
    )


async def _rating_payload(player: Player) -> str:
    nickname = (player.game_nickname or "").strip()
    header = (
        "🏆 <b>Мой рейтинг</b>\n\n"
        f"Игровой ник: <b>{escape(nickname)}</b>\n"
    )
    try:
        rating = await fetch_player_rating(nickname)
    except RatingsServiceError:
        logger.warning(
            "Не удалось получить рейтинг для игрового ника %r",
            nickname,
            exc_info=True,
        )
        return (
            header
            + "\nРейтинг временно недоступен. Попробуйте открыть раздел позже."
        )

    if rating is None:
        return header + "\nРейтинг для этого игрового ника пока не найден."

    lines = [
        header.rstrip(),
        f"Глобальный рейтинг: <b>{_format_rating(rating.global_rating)}</b>",
        f"Текущий сезон: <b>{_format_rating(rating.current_season)}</b>",
    ]
    if rating.seasons:
        lines.extend(["", "<b>Рейтинг по сезонам:</b>"])
        lines.extend(
            f"• {escape(season.season_name)}: "
            f"<b>{_format_rating(season.rating)}</b>"
            for season in rating.seasons
        )
    return "\n".join(lines)


async def _get_current_player(update: Update) -> Player:
    tg_id, username, name = _user_identity(update)
    async with Session() as session:
        return await repo.get_or_create_player(
            session, tg_id, username, name
        )


async def on_stats(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    player = await _get_current_player(update)
    text, has_nickname = _stats_payload(player)
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=stats_keyboard(has_nickname),
    )
    return (
        ConversationHandler.END
        if has_nickname else STATS_VIEW
    )


async def on_my_rating(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    player = await _get_current_player(update)
    if not (player.game_nickname or "").strip():
        text, has_nickname = _stats_payload(player)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=stats_keyboard(has_nickname),
        )
        return

    await query.edit_message_text(
        await _rating_payload(player),
        parse_mode="HTML",
        reply_markup=rating_keyboard(),
    )


async def on_create_game_nickname(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите игровой ник сообщением.\n\n"
        "Он будет использоваться для поиска вашего рейтинга.",
        reply_markup=nickname_input_keyboard(),
    )
    return WAIT_GAME_NICKNAME


async def on_game_nickname(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    nickname = " ".join(update.message.text.split())
    if not 2 <= len(nickname) <= 64:
        await update.message.reply_text(
            "Ник должен содержать от 2 до 64 символов.",
            reply_markup=nickname_input_keyboard(),
        )
        return WAIT_GAME_NICKNAME

    tg_id, username, name = _user_identity(update)
    async with Session() as session:
        player = await repo.get_or_create_player(
            session, tg_id, username, name
        )
        await repo.set_game_nickname(session, player, nickname)

    text, has_nickname = _stats_payload(player)
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=stats_keyboard(has_nickname),
    )
    return ConversationHandler.END


async def on_cancel_game_nickname(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    player = await _get_current_player(update)
    text, has_nickname = _stats_payload(player)
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=stats_keyboard(has_nickname),
    )
    return (
        ConversationHandler.END
        if has_nickname else STATS_VIEW
    )


async def on_my_results(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    tg_id, username, name = _user_identity(update)
    async with Session() as session:
        player = await repo.get_or_create_player(
            session, tg_id, username, name
        )
        rows = await repo.list_user_result_games(session, player.id)

    lines = ["🎲 <b>Мои игры за последние 30 дней</b>", ""]
    if not rows:
        lines.append("Завершённых игр с внесёнными результатами пока нет.")
    for game, assignment, event, role in rows:
        winner = "красные" if game.winner_side == "town" else "чёрные"
        if assignment.is_winner is None:
            outcome = "без результата"
        else:
            outcome = "победа" if assignment.is_winner else "поражение"
        seat = (
            f", место №{assignment.seat_number}"
            if assignment.seat_number is not None else ""
        )
        lines.append(
            f"• {fmt(event.starts_at)} · Игра №{game.game_number}\n"
            f"  {ROLE_EMOJIS.get(role.code, '▫️')} "
            f"{escape(ROLE_LABELS.get(role.code, role.name))}{seat} · "
            f"{winner} · <b>{outcome}</b>"
        )
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=my_results_keyboard(),
    )


def register(app: Application) -> None:
    conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                on_admin_results, pattern=f"^{CB_ADMIN_RESULTS}$"
            ),
        ],
        states={
            EVENTS: [
                CallbackQueryHandler(
                    on_event, pattern=f"^{CB_RESULT_EVENT_PREFIX}"
                ),
            ],
            EVENT_DETAIL: [
                CallbackQueryHandler(
                    on_add_results, pattern=f"^{CB_RESULT_ADD_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_games, pattern=f"^{CB_RESULT_GAMES_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_admin_results, pattern=f"^{CB_ADMIN_RESULTS}$"
                ),
            ],
            WAIT_GAME_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_game_count),
                CallbackQueryHandler(
                    on_cancel_input, pattern=f"^{CB_RESULT_CANCEL_INPUT}$"
                ),
            ],
            GAMES: [
                CallbackQueryHandler(
                    on_add_game, pattern=f"^{CB_RESULT_GAME_ADD_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_delete_game_confirm,
                    pattern=f"^{CB_RESULT_GAME_DELETE_CONFIRM_PREFIX}",
                ),
                CallbackQueryHandler(
                    on_delete_game_request,
                    pattern=f"^{CB_RESULT_GAME_DELETE_PREFIX}",
                ),
                CallbackQueryHandler(
                    on_game, pattern=f"^{CB_RESULT_GAME_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_event, pattern=f"^{CB_RESULT_EVENT_PREFIX}"
                ),
            ],
            GAME_EDIT: [
                CallbackQueryHandler(
                    on_table, pattern=f"^{CB_RESULT_TABLE}$"
                ),
                CallbackQueryHandler(
                    on_slot, pattern=f"^{CB_RESULT_SLOT_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_skips, pattern=f"^{CB_RESULT_SKIPS}$"
                ),
                CallbackQueryHandler(
                    on_host, pattern=f"^{CB_RESULT_HOST}$"
                ),
                CallbackQueryHandler(
                    on_winner_menu, pattern=f"^{CB_RESULT_WINNER_MENU}$"
                ),
                CallbackQueryHandler(
                    on_player, pattern=f"^{CB_RESULT_PLAYER_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_winner, pattern=f"^{CB_RESULT_WINNER_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_guest_request, pattern=f"^{CB_RESULT_GUEST}$"
                ),
                CallbackQueryHandler(
                    on_games, pattern=f"^{CB_RESULT_GAMES_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_game, pattern=f"^{CB_RESULT_GAME_PREFIX}"
                ),
            ],
            ROLE_SELECT: [
                CallbackQueryHandler(
                    on_role, pattern=f"^{CB_RESULT_ROLE_PREFIX}"
                ),
                CallbackQueryHandler(
                    on_cancel_input, pattern=f"^{CB_RESULT_CANCEL_INPUT}$"
                ),
            ],
            WAIT_GUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_guest_name),
                CallbackQueryHandler(
                    on_cancel_input, pattern=f"^{CB_RESULT_CANCEL_INPUT}$"
                ),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    stats_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_stats, pattern=f"^{CB_STATS}$"),
        ],
        states={
            STATS_VIEW: [
                CallbackQueryHandler(
                    on_create_game_nickname,
                    pattern=f"^{CB_CREATE_GAME_NICKNAME}$",
                ),
            ],
            WAIT_GAME_NICKNAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_game_nickname,
                ),
                CallbackQueryHandler(
                    on_cancel_game_nickname,
                    pattern=f"^{CB_CANCEL_GAME_NICKNAME}$",
                ),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(conversation)
    app.add_handler(stats_conversation)
    app.add_handler(CallbackQueryHandler(
        on_my_rating, pattern=f"^{CB_MY_RATING}$"
    ))
    app.add_handler(CallbackQueryHandler(
        on_my_results, pattern=f"^{CB_MY_RESULTS}$"
    ))
