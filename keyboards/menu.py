from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import (
    CB_ADMIN_CREATE_EVENT,
    CB_ADMIN_EVENTS,
    CB_ADMIN_RESULTS,
    CB_GAMES,
    CB_LEARN,
    CB_RULES,
    CB_STATS,
)

GREETING = "🤠 Шериф на связи! Чем займемся сегодня?"


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📅 Запись на игры", callback_data=CB_GAMES)],
        [InlineKeyboardButton("📊 Моя статистика", callback_data=CB_STATS)],
        [InlineKeyboardButton("📚 Обучение",       callback_data=CB_LEARN)],
        [InlineKeyboardButton("📖 Правила игры",   callback_data=CB_RULES)],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(
            "➕ Создать встречу", callback_data=CB_ADMIN_CREATE_EVENT
        )])
        rows.append([InlineKeyboardButton(
            "🗓 Управление встречами", callback_data=CB_ADMIN_EVENTS
        )])
        rows.append([InlineKeyboardButton(
            "📝 Результаты игр", callback_data=CB_ADMIN_RESULTS
        )])
    return InlineKeyboardMarkup(rows)
