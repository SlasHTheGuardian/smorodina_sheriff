from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import CB_SAWING, CB_BALANCE, CB_QUIZ, CB_DETECTIVE, CB_MAIN

LEARN_GREETING = "📚 <b>Обучение</b>\n\nЧему будем учиться сегодня?"


def learn_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪚 Пилим стол",           callback_data=CB_SAWING)],
        [InlineKeyboardButton("⚖️ Баланс и противовес",  callback_data=CB_BALANCE)],
        [InlineKeyboardButton("🚫 Фолы и наказания",     callback_data=CB_QUIZ)],
        [InlineKeyboardButton("🕯️ Ночной детектив",      callback_data=CB_DETECTIVE)],
        [InlineKeyboardButton("◀️ Обратно в меню",       callback_data=CB_MAIN)],
    ])
