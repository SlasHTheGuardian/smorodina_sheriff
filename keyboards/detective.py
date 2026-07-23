from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import (
    CB_DET_NEW_PREFIX, CB_DET_CHECK, CB_DET_TOGGLE_PREFIX, CB_LEARN,
)
from game.detective_game import N, NUM_BLACK

_EASY = f"{CB_DET_NEW_PREFIX}easy"
_HARD = f"{CB_DET_NEW_PREFIX}hard"

DETECTIVE_INTRO = (
    "🕯️ <b>Ночной детектив</b>\n\n"
    "Перед тобой — публичный ход завершённой партии: кого выводили днём, "
    "кого убивали ночью, заявления вскрывшихся шерифов. Роли скрыты.\n\n"
    "Твоя задача — вычислить всех троих чёрных.\n\n"
    "<b>Зацепки:</b>\n"
    "• ночью мафия стреляет только в красных — убитый ночью не чёрный;\n"
    "• проверки <b>настоящего</b> шерифа достоверны;\n"
    "• фейк-шериф — чёрный; если он заявил проверок больше, чем было ночей, "
    "он спалился;\n"
    "• чёрных ровно трое, и счёт стола в финале сходится с результатом.\n\n"
    "<b>Полегче</b> — один честный шериф.\n"
    "<b>Посложнее</b> — двое называют себя шерифом, один фейк.\n\n"
    "С чего начнём?"
)


def detective_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Полегче",   callback_data=_EASY),
         InlineKeyboardButton("🔴 Посложнее", callback_data=_HARD)],
        [InlineKeyboardButton("◀️ Назад к обучению", callback_data=CB_LEARN)],
    ])


def puzzle_keyboard(selection: set[int]) -> InlineKeyboardMarkup:
    """Сетка из N игроков-переключателей (по 5 в ряд) + кнопки действий."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in range(1, N + 1):
        mark = "✅" if n in selection else "▫️"
        row.append(InlineKeyboardButton(f"{mark} {n}",
                                        callback_data=f"{CB_DET_TOGGLE_PREFIX}{n}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton(
        f"🔎 Проверить ({len(selection)}/{NUM_BLACK})", callback_data=CB_DET_CHECK)])
    rows.append([InlineKeyboardButton("🏁 Завершить", callback_data=CB_LEARN)])
    return InlineKeyboardMarkup(rows)


def result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Полегче",   callback_data=_EASY),
         InlineKeyboardButton("🔴 Посложнее", callback_data=_HARD)],
        [InlineKeyboardButton("🏠 В меню обучения", callback_data=CB_LEARN)],
    ])
