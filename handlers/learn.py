from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import CB_LEARN, CB_MAIN
from keyboards.learn import learn_menu_keyboard, LEARN_GREETING
from keyboards.menu import main_menu_keyboard, GREETING
from config import is_admin


async def on_learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        LEARN_GREETING,
        parse_mode="HTML",
        reply_markup=learn_menu_keyboard(),
    )


async def on_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        GREETING,
        reply_markup=main_menu_keyboard(is_admin(update.effective_user.id)),
    )


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_learn,     pattern=f"^{CB_LEARN}$"))
    app.add_handler(CallbackQueryHandler(on_main_menu, pattern=f"^{CB_MAIN}$"))
