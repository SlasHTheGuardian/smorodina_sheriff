from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import (
    CB_QUIZ_START, CB_QUIZ_NEXT, CB_QUIZ_FINISH, CB_QUIZ_ANS_PREFIX, CB_LEARN,
)
from game.quiz_data import CATEGORY_ORDER, CATEGORIES, CATEGORY_HINTS


def _intro_text() -> str:
    lines = [
        "🚫 <b>Квиз: фолы и наказания</b>",
        "",
        "Покажу нарушение — выбери, что назначит Судья:",
        "",
    ]
    lines += [f"{CATEGORIES[k]} — {CATEGORY_HINTS[k]}" for k in CATEGORY_ORDER]
    lines += ["", "Готов проверить себя?"]
    return "\n".join(lines)


QUIZ_INTRO = _intro_text()


def quiz_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Начать",            callback_data=CB_QUIZ_START)],
        [InlineKeyboardButton("◀️ Назад к обучению", callback_data=CB_LEARN)],
    ])


def quiz_answer_keyboard() -> InlineKeyboardMarkup:
    """По кнопке на каждую категорию наказания."""
    rows = [
        [InlineKeyboardButton(CATEGORIES[k], callback_data=f"{CB_QUIZ_ANS_PREFIX}{k}")]
        for k in CATEGORY_ORDER
    ]
    return InlineKeyboardMarkup(rows)


def quiz_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data=CB_QUIZ_NEXT)],
        [InlineKeyboardButton("🏁 Завершить",         callback_data=CB_QUIZ_FINISH)],
    ])


def quiz_finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Ещё раз",          callback_data=CB_QUIZ_START)],
        [InlineKeyboardButton("🏠 В меню обучения", callback_data=CB_LEARN)],
    ])
