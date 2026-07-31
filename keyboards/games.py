from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from constants import (
    CB_GAMES, CB_MAIN, CB_MY_GAMES,
    CB_GAME_PREFIX, CB_GAME_REG_PREFIX, CB_GAME_PAID_PREFIX,
    CB_GAME_CANCEL_PREFIX, CB_GAME_CANCEL_CONFIRM_PREFIX,
)
from db.models import Game, Registration, GAME_OPEN, REG_ACTIVE, REG_WAITLIST
from db.repo import registration_is_open
from event_price import format_event_price
from gametime import fmt

GAMES_GREETING = "📅 <b>Запись на игры</b>"


def payment_prompt(price_rubles: int) -> str:
    return (
        "Для участия в игровом вечере необходимо перевести "
        f"{format_event_price(price_rubles)} "
        "по номеру +79175361453 (Яндекс Банк)."
    )


def cancel_prompt(price_rubles: int) -> str:
    common = (
        "Внимание, Смородинка!\n\n"
        "При отмене записи ваше место будет освобождено для других "
        "участников, и вы не сможете посетить игровой вечер."
    )
    if price_rubles == 0:
        return common + "\n\nТочно отменяем?"
    return (
        common
        + " Деньги будут возвращены только при отмене записи не позже, "
        "чем за три дня до мероприятия.\n\nТочно отменяем?"
    )


# Оставлены для совместимости с существующими импортами.
PAYMENT_PROMPT = payment_prompt(500)
CANCEL_PROMPT = cancel_prompt(500)


def _compact_title(title: str, limit: int = 28) -> str:
    return title if len(title) <= limit else title[:limit - 1] + "…"


def games_list_keyboard(
    games: list[Game], counts: dict[int, tuple[int, int]]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    sections = (
        ([
            game for game in games if registration_is_open(game)
        ], "📝"),
        ([
            game for game in games if not registration_is_open(game)
        ], "🔒"),
    )
    for section_games, mark in sections:
        for game in section_games:
            active, wait = counts.get(game.id, (0, 0))
            tail = f" +{wait}🕓" if wait else ""
            capacity = game.capacity if game.capacity is not None else "∞"
            rows.append([InlineKeyboardButton(
                f"{mark} {_compact_title(game.title)} · "
                f"{fmt(game.starts_at)} · {active}/{capacity}{tail}",
                callback_data=f"{CB_GAME_PREFIX}{game.id}",
            )])
    rows.append([InlineKeyboardButton("🧾 Мои записи", callback_data=CB_MY_GAMES)])
    rows.append([InlineKeyboardButton("◀️ В главное меню", callback_data=CB_MAIN)])
    return InlineKeyboardMarkup(rows)


def game_card_keyboard(
    game: Game,
    player_status: str | None,
    back_callback: str = CB_GAMES,
    back_label: str = "К списку игр",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if game.status == GAME_OPEN:
        if player_status in (REG_ACTIVE, REG_WAITLIST):
            rows.append([InlineKeyboardButton(
                "❌ Отменить запись",
                callback_data=f"{CB_GAME_CANCEL_PREFIX}{game.id}")])
        elif registration_is_open(game):
            rows.append([InlineKeyboardButton(
                "✅ Записаться",
                callback_data=f"{CB_GAME_REG_PREFIX}{game.id}")])
    rows.append([InlineKeyboardButton(
        f"◀️ {back_label}", callback_data=back_callback
    )])
    return InlineKeyboardMarkup(rows)


def payment_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Отправил!", callback_data=f"{CB_GAME_PAID_PREFIX}{game_id}"
        )],
        [InlineKeyboardButton(
            "Назад", callback_data=f"{CB_GAME_PREFIX}{game_id}"
        )],
    ])


def cancel_confirmation_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Отменяем запись!",
            callback_data=f"{CB_GAME_CANCEL_CONFIRM_PREFIX}{game_id}",
        )],
        [InlineKeyboardButton(
            "Пока подумаю...", callback_data=f"{CB_GAME_PREFIX}{game_id}"
        )],
    ])


def my_games_keyboard(regs: list[Registration]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in regs:
        mark = "✅" if r.status == REG_ACTIVE else "🕓"
        rows.append([InlineKeyboardButton(
            f"{mark} {_compact_title(r.game.title)} · "
            f"{fmt(r.game.starts_at)}",
            callback_data=f"{CB_GAME_PREFIX}{r.game_id}")])
    rows.append([InlineKeyboardButton("◀️ К списку игр", callback_data=CB_GAMES)])
    return InlineKeyboardMarkup(rows)
