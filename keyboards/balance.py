from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import CB_BALANCE_FOR, CB_BALANCE_AGST, CB_BALANCE, CB_LEARN

BALANCE_GREETING = "⚖️ <b>Баланс и противовес</b>\n\nЧто изучаем?"


def back_to_balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data=CB_BALANCE)],
    ])


def balance_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Игра в баланс",      callback_data=CB_BALANCE_FOR)],
        [InlineKeyboardButton("⚡ Игра в противовес",  callback_data=CB_BALANCE_AGST)],
        [InlineKeyboardButton("◀️ Назад к обучению",  callback_data=CB_LEARN)],
    ])
