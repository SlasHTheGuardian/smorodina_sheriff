import logging

from telegram import Update
from telegram.ext import ContextTypes
from keyboards.menu import main_menu_keyboard, GREETING
from config import is_admin
from db.engine import Session
from db import repo

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Заводим/обновляем профиль игрока (нужно для записи на игры).
    try:
        u = update.effective_user
        name = " ".join(filter(None, [u.first_name, u.last_name])) or ""
        async with Session() as session:
            await repo.get_or_create_player(session, u.id, u.username, name)
    except Exception:
        logger.exception("Не удалось сохранить профиль игрока")

    await update.message.reply_text(
        GREETING,
        reply_markup=main_menu_keyboard(is_admin(update.effective_user.id)),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        GREETING,
        reply_markup=main_menu_keyboard(is_admin(update.effective_user.id)),
    )
