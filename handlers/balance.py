from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import CB_BALANCE, CB_BALANCE_FOR, CB_BALANCE_AGST
from keyboards.balance import balance_menu_keyboard, back_to_balance_keyboard, BALANCE_GREETING


async def on_balance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        BALANCE_GREETING,
        parse_mode="HTML",
        reply_markup=balance_menu_keyboard(),
    )


async def on_balance_for(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 <b>Игра в баланс</b>\n\n"
        "Баланс — это последовательный вывод игроков из взаимоисключающих шерифских версий, при котором среди выбранных кандидатур гарантированно находится как минимум один представитель чёрной команды. Обычно баланс применяется при двух вскрывшихся шерифах: город поочерёдно голосует их чёрные проверки либо самих шерифов, чтобы независимо от истинности одной из версий сократить количество мафии. Эффективность баланса основана не на субъективной оценке речей, а на игровой математике и наличии проверок.",
        parse_mode="HTML",
        reply_markup=back_to_balance_keyboard(),
    )


async def on_balance_against(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚡ <b>Игра в противовес</b>\n\n"
        "Противовес — это последовательный вывод двух конфликтующих игроков или представителей противоположных игровых версий без математической гарантии, что среди них обязательно есть мафия. Он применяется, когда город располагает только логическими аргументами, речами, голосованиями и поведением участников. Противовес помогает упорядочить игру и проверить конфликт через роли выбывших игроков, однако требует постоянной переоценки, поскольку оба кандидата могут оказаться мирными.",
        parse_mode="HTML",
        reply_markup=back_to_balance_keyboard(),
    )


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_balance_menu,    pattern=f"^{CB_BALANCE}$"))
    app.add_handler(CallbackQueryHandler(on_balance_for,     pattern=f"^{CB_BALANCE_FOR}$"))
    app.add_handler(CallbackQueryHandler(on_balance_against, pattern=f"^{CB_BALANCE_AGST}$"))
