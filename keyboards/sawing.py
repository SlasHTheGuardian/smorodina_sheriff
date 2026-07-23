from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import (
    CB_THEORY, CB_PRACTICE, CB_NEXT_1, CB_NEXT_2, CB_SKIP, CB_TRY,
    CB_SAWING, CB_SAWING_PLAY, CB_SAWING_ANS_YES, CB_SAWING_ANS_NO,
    CB_LEARN,
)


def know_sawing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Нет, давай начнем с теории",  callback_data=CB_THEORY)],
        [InlineKeyboardButton("✅ Да, хочу попрактиковаться!", callback_data=CB_PRACTICE)],
    ])


def next_keyboard(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Далее", callback_data=cb)],
    ])


def after_theory_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚪 Не сейчас",  callback_data=CB_SKIP)],
        [InlineKeyboardButton("🎯 Да, давай!", callback_data=CB_TRY)],
    ])


def game_question_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data=CB_SAWING_ANS_YES),
            InlineKeyboardButton("❌ Нет", callback_data=CB_SAWING_ANS_NO),
        ]
    ])


def game_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Ещё раз",       callback_data=CB_SAWING_PLAY)],
        [InlineKeyboardButton("◀️ Назад",          callback_data=CB_SAWING)],
        [InlineKeyboardButton("🏠 В меню обучения", callback_data=CB_LEARN)],
    ])
