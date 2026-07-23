from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import (
    CB_SAWING, CB_THEORY, CB_PRACTICE, CB_NEXT_1, CB_NEXT_2, CB_SKIP, CB_TRY,
    CB_SAWING_PLAY, CB_SAWING_ANS_YES, CB_SAWING_ANS_NO,
)
from keyboards.sawing import (
    know_sawing_keyboard, next_keyboard, after_theory_keyboard,
    game_question_keyboard, game_result_keyboard,
)
from keyboards.learn import learn_menu_keyboard, LEARN_GREETING
from game.sawing_game import generate_situation, format_situation

_GAME_KEY = "sawing_game"


# ---------------------------------------------------------------------------
# Теория
# ---------------------------------------------------------------------------

async def on_sawing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🪚 <b>Пилим стол</b>\n\n"
        "Уже знаете, что такое распил стола, и зачем он нужен?",
        parse_mode="HTML",
        reply_markup=know_sawing_keyboard(),
    )


async def on_theory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 <b>Теория · Часть 1</b>\n\n"
        "Распил стола — это заранее предложенная и согласованная схема голосования, при которой голоса намеренно распределяются поровну между двумя или несколькими выставленными кандидатами. В мафиозном сленге также употребляется слово «попил». Само равенство голосов называется «автокатастрофой», однако распил — именно тактический замысел, а не случайная ничья. По правилам спортивной мафии кандидаты, набравшие одинаковое число голосов, получают по 30 дополнительных секунд, после чего проводится переголосование. Если голоса вновь делятся поровну между теми же кандидатами, судья предлагает столу решить, должны ли все они одновременно покинуть игру: при большинстве «за» они уходят, а при большинстве «против» или равенстве остаются. Таким образом, один и тот же распил может использоваться как для сохранения всех кандидатов, так и для их совместного вывода.",
        parse_mode="HTML",
        reply_markup=next_keyboard(CB_NEXT_1),
    )


async def on_next_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 <b>Теория · Часть 2</b>\n\n"
        "Наиболее часто встречается распил на первом, или «нулевом», круге при десяти игроках: например, два кандидата получают по пять голосов, затем равенство повторяется, а стол не поддерживает их совместный вывод. Чаще всего на нулевом кругу первый игрок пилится с тем, кто ему понравился меньше всего. Делается это для трех вещей. \nВо-первых, вместо 10 минут, город получает 11, что в целом дает больше информации мирным. \nВо-вторых, город получают возможность послушать аналитику от первого игрока, речь которого была потрачена на открытие стола. \nВ-третьих, город может переслушать одного подозрительного игрока, чью речь город посчитал плохой.",
        parse_mode="HTML",
        reply_markup=next_keyboard(CB_NEXT_2),
    )


async def on_next_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 <b>Теория · Часть 3</b>\n\n"
        "Главная опасность распила — слом голосования, когда один из игроков ставит руку не в заранее обозначенную кандидатуру, а в любого другого участника голосования, из-за чего равенство исчезает и один из участников получает большинство голосов. Так как распил стола дает дополнительную информацию для города, его можно считать красным ходом. Именно поэтому слом - нарушение общей договоренности - является черным ходом. Чаще всего, игрок сломавший попил, будет удален голосованием на следующем кругу.",
        parse_mode="HTML",
    )
    await query.message.reply_text(
        "💡 Попробуем попрактиковаться?",
        reply_markup=after_theory_keyboard(),
    )


async def on_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        LEARN_GREETING,
        parse_mode="HTML",
        reply_markup=learn_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Мини-игра «Пилим стол»
# ---------------------------------------------------------------------------

async def _start_game(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Генерирует ситуацию и показывает вопрос."""
    game = generate_situation()
    context.user_data[_GAME_KEY] = game
    await query.edit_message_text(
        format_situation(game),
        parse_mode="HTML",
        reply_markup=game_question_keyboard(),
    )


async def on_practice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _start_game(query, context)


async def on_sawing_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _start_game(query, context)


async def on_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    game = context.user_data.get(_GAME_KEY)
    if not game:
        await _start_game(query, context)
        return

    user_said_yes = query.data == CB_SAWING_ANS_YES
    correct       = game["correct_answer"]
    reason        = game["reason"]
    is_correct    = user_said_yes == correct

    if is_correct:
        verdict = "✅ <b>Верно!</b>"
    else:
        verdict = "❌ <b>Не верно!</b>"

    sheriff_note = "\n\n⚠️ Только аккуратно! Вы — шериф!" if (is_correct and game["player_role"] == "шериф") else ""

    await query.edit_message_text(
        f"{verdict} {reason.capitalize()}{sheriff_note}",
        parse_mode="HTML",
        reply_markup=game_result_keyboard(),
    )


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------

def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_sawing,      pattern=f"^{CB_SAWING}$"))
    app.add_handler(CallbackQueryHandler(on_theory,      pattern=f"^{CB_THEORY}$"))
    app.add_handler(CallbackQueryHandler(on_next_1,      pattern=f"^{CB_NEXT_1}$"))
    app.add_handler(CallbackQueryHandler(on_next_2,      pattern=f"^{CB_NEXT_2}$"))
    app.add_handler(CallbackQueryHandler(on_practice,    pattern=f"^{CB_PRACTICE}$"))
    app.add_handler(CallbackQueryHandler(on_practice,    pattern=f"^{CB_TRY}$"))
    app.add_handler(CallbackQueryHandler(on_skip,        pattern=f"^{CB_SKIP}$"))
    app.add_handler(CallbackQueryHandler(on_sawing_play, pattern=f"^{CB_SAWING_PLAY}$"))
    app.add_handler(CallbackQueryHandler(on_answer,      pattern=f"^{CB_SAWING_ANS_YES}$"))
    app.add_handler(CallbackQueryHandler(on_answer,      pattern=f"^{CB_SAWING_ANS_NO}$"))
