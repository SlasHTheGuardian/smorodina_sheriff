from html import escape

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from constants import (
    CB_GAMES, CB_MY_GAMES,
    CB_GAME_PREFIX, CB_GAME_REG_PREFIX, CB_GAME_PAID_PREFIX,
    CB_GAME_CANCEL_PREFIX, CB_GAME_CANCEL_CONFIRM_PREFIX,
)
from keyboards.games import (
    GAMES_GREETING, games_list_keyboard, game_card_keyboard, my_games_keyboard,
    payment_prompt, payment_keyboard,
    cancel_prompt, cancel_confirmation_keyboard,
)
from db.engine import Session
from db import repo
from db.models import GAME_OPEN, REG_ACTIVE, REG_WAITLIST
from event_price import format_event_price
from gametime import fmt


def _player_from_update(update: Update):
    u = update.effective_user
    name = " ".join(filter(None, [u.first_name, u.last_name])) or ""
    return u.id, u.username, name


# ---------------------------------------------------------------------------
# Рендер карточки игры
# ---------------------------------------------------------------------------

async def game_card_payload(
    session,
    game,
    player,
    back_callback: str = CB_GAMES,
    back_label: str = "К списку игр",
):
    active, waitlist = await repo.roster(session, game.id)
    my = await repo.get_registration(session, game.id, player.id)
    my_status = my.status if my and my.status in (REG_ACTIVE, REG_WAITLIST) else None

    lines = [
        f"🎲 <b>{escape(game.title)}</b>",
        f"📅 {fmt(game.starts_at)}",
        f"💳 Стоимость: <b>{format_event_price(game.price_rubles)}</b>",
    ]
    if game.location:
        lines.append(f"📍 {escape(game.location)}")
    if game.note:
        lines.append(f"📝 {escape(game.note)}")
    lines.append("")

    if game.status != GAME_OPEN:
        lines.append("🚫 <i>Запись закрыта.</i>")
        lines.append("")
    elif not repo.registration_is_open(game):
        lines.append(
            "👁 <i>Только просмотр. Запись закрывается "
            "за 3 суток до начала.</i>"
        )
        lines.append("")
    capacity = game.capacity if game.capacity is not None else "∞"
    lines.append(f"👥 Мест занято: <b>{len(active)}/{capacity}</b>"
                 + (f" · лист ожидания: {len(waitlist)}" if waitlist else ""))

    if active:
        lines.append("")
        lines.append("<b>Записаны:</b>")
        lines.extend(
            f"  {i}. {escape(r.player.game_display)}"
            for i, r in enumerate(active, 1)
        )
    if waitlist:
        lines.append("")
        lines.append("<b>Лист ожидания:</b>")
        lines.extend(
            f"  {i}. {escape(r.player.game_display)}"
            for i, r in enumerate(waitlist, 1)
        )

    if my_status == REG_ACTIVE:
        lines.append("\n✅ <b>Вы записаны.</b>")
    elif my_status == REG_WAITLIST:
        pos = next((i for i, r in enumerate(waitlist, 1) if r.player_id == player.id), "?")
        lines.append(f"\n🕓 <b>Вы в листе ожидания (№{pos}).</b>")

    return "\n".join(lines), game_card_keyboard(
        game,
        my_status,
        back_callback=back_callback,
        back_label=back_label,
    )


# ---------------------------------------------------------------------------
# Список игр
# ---------------------------------------------------------------------------

async def on_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    async with Session() as session:
        games = await repo.list_upcoming_games(session)
        counts = await repo.counts_for_games(session, [g.id for g in games])

    text = (
        GAMES_GREETING
        if games
        else GAMES_GREETING
        + "\n\nПока нет анонсированных игр. Загляни позже!"
    )
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=games_list_keyboard(games, counts)
    )


async def on_my_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        regs = await repo.list_player_games(session, player)

    if regs:
        lines = ["🧾 <b>Мои записи</b>", ""]
        for r in regs:
            mark = "✅ записан" if r.status == REG_ACTIVE else "🕓 лист ожидания"
            lines.append(
                f"🎲 <b>{escape(r.game.title)}</b> · "
                f"{fmt(r.game.starts_at)} — {mark}"
            )
        text = "\n".join(lines)
    else:
        text = "🧾 <b>Мои записи</b>\n\nТы пока никуда не записан."
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=my_games_keyboard(regs)
    )


# ---------------------------------------------------------------------------
# Карточка и действия
# ---------------------------------------------------------------------------

async def on_game_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    game_id = int(query.data[len(CB_GAME_PREFIX):])
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        game = await repo.get_game(session, game_id)
        if game is None:
            await query.edit_message_text("🚫 Игра не найдена.")
            return
        text, kb = await game_card_payload(session, game, player)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def on_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    game_id = int(query.data[len(CB_GAME_REG_PREFIX):])
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        game = await repo.get_game(session, game_id)
        if game is None:
            await query.answer()
            await query.edit_message_text("🚫 Игра не найдена.")
            return

        existing = await repo.get_registration(session, game.id, player.id)
        if existing and existing.status in (REG_ACTIVE, REG_WAITLIST):
            await query.answer("Вы уже записаны.", show_alert=False)
            text, kb = await game_card_payload(session, game, player)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return
        if not repo.registration_is_open(game):
            await query.answer(
                "Запись закрывается за 3 суток до начала.",
                show_alert=False,
            )
            text, kb = await game_card_payload(session, game, player)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return
        if game.price_rubles == 0:
            code, status = await repo.register(session, game, player)
            toast = (
                "Готово, вы записаны!"
                if status == REG_ACTIVE
                else "Мест нет — вы в листе ожидания."
            )
            if code not in ("registered", "waitlist"):
                toast = "Не удалось записаться на эту встречу."
            await query.answer(toast, show_alert=False)
            text, kb = await game_card_payload(session, game, player)
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=kb
            )
            return
        price_rubles = game.price_rubles

    await query.answer()
    await query.edit_message_text(
        payment_prompt(price_rubles),
        reply_markup=payment_keyboard(game_id),
    )


async def on_payment_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    game_id = int(query.data[len(CB_GAME_PAID_PREFIX):])
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        game = await repo.get_game(session, game_id)
        if game is None:
            await query.answer()
            await query.edit_message_text("🚫 Игра не найдена.")
            return

        code, status = await repo.register(session, game, player)
        toast = {
            "closed":  "Запись на эту игру закрыта.",
            "deadline": "Запись закрывается за 3 суток до начала.",
            "already": "Вы уже записаны.",
        }.get(code) or (
            "Готово, вы записаны!" if status == REG_ACTIVE
            else "Мест нет — вы в листе ожидания."
        )
        await query.answer(toast, show_alert=False)
        text, kb = await game_card_payload(session, game, player)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    game_id = int(query.data[len(CB_GAME_CANCEL_PREFIX):])
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        game = await repo.get_game(session, game_id)
        if game is None:
            await query.answer()
            await query.edit_message_text("🚫 Игра не найдена.")
            return

        existing = await repo.get_registration(session, game.id, player.id)
        if not existing or existing.status not in (REG_ACTIVE, REG_WAITLIST):
            await query.answer("Вы не были записаны.", show_alert=False)
            text, kb = await game_card_payload(session, game, player)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return

    await query.answer()
    await query.edit_message_text(
        cancel_prompt(game.price_rubles),
        reply_markup=cancel_confirmation_keyboard(game_id),
    )


async def on_cancel_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    game_id = int(query.data[len(CB_GAME_CANCEL_CONFIRM_PREFIX):])
    async with Session() as session:
        tg_id, username, name = _player_from_update(update)
        player = await repo.get_or_create_player(session, tg_id, username, name)
        game = await repo.get_game(session, game_id)
        if game is None:
            await query.answer()
            await query.edit_message_text("🚫 Игра не найдена.")
            return

        code, promoted = await repo.cancel_registration(session, game, player)
        await query.answer(
            "Запись отменена." if code == "cancelled" else "Вы не были записаны.",
            show_alert=False,
        )
        text, kb = await game_card_payload(session, game, player)
        promoted_tg = promoted.tg_id if promoted else None
        game_when = fmt(game.starts_at)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

    # Уведомляем поднятого из листа ожидания.
    if promoted_tg:
        try:
            await context.bot.send_message(
                promoted_tg,
                f"🎉 Освободилось место на игру {game_when} — вы записаны!",
            )
        except Exception:
            pass


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_games,     pattern=f"^{CB_GAMES}$"))
    app.add_handler(CallbackQueryHandler(on_my_games,  pattern=f"^{CB_MY_GAMES}$"))
    app.add_handler(CallbackQueryHandler(on_register,  pattern=f"^{CB_GAME_REG_PREFIX}"))
    app.add_handler(CallbackQueryHandler(
        on_payment_confirm, pattern=f"^{CB_GAME_PAID_PREFIX}"
    ))
    app.add_handler(CallbackQueryHandler(on_cancel,    pattern=f"^{CB_GAME_CANCEL_PREFIX}"))
    app.add_handler(CallbackQueryHandler(
        on_cancel_confirm, pattern=f"^{CB_GAME_CANCEL_CONFIRM_PREFIX}"
    ))
    app.add_handler(CallbackQueryHandler(on_game_card, pattern=f"^{CB_GAME_PREFIX}"))
