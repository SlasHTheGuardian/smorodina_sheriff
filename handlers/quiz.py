from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import (
    CB_QUIZ, CB_QUIZ_START, CB_QUIZ_NEXT, CB_QUIZ_FINISH, CB_QUIZ_ANS_PREFIX,
)
from keyboards.quiz import (
    QUIZ_INTRO, quiz_intro_keyboard, quiz_answer_keyboard,
    quiz_result_keyboard, quiz_finish_keyboard,
)
from game.quiz_game import new_deck, format_question, grade, final_text

# Ключи состояния в context.user_data
_DECK     = "quiz_deck"      # оставшиеся индексы вопросов
_IDX      = "quiz_idx"       # текущий вопрос
_CORRECT  = "quiz_correct"   # сколько верных
_ANSWERED = "quiz_answered"  # сколько отвечено


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

async def _serve_question(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Берёт следующий вопрос из колоды (пополняя её) и показывает его."""
    deck = context.user_data.get(_DECK) or new_deck()
    idx = deck.pop()
    context.user_data[_DECK] = deck
    context.user_data[_IDX] = idx

    await query.edit_message_text(
        format_question(
            idx,
            context.user_data.get(_ANSWERED, 0),
            context.user_data.get(_CORRECT, 0),
        ),
        parse_mode="HTML",
        reply_markup=quiz_answer_keyboard(),
    )


def _reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[_DECK] = new_deck()
    context.user_data[_CORRECT] = 0
    context.user_data[_ANSWERED] = 0
    context.user_data[_IDX] = None


# ---------------------------------------------------------------------------
# Обработчики
# ---------------------------------------------------------------------------

async def on_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        QUIZ_INTRO,
        parse_mode="HTML",
        reply_markup=quiz_intro_keyboard(),
    )


async def on_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _reset(context)
    await _serve_question(query, context)


async def on_quiz_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _serve_question(query, context)


async def on_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    idx = context.user_data.get(_IDX)
    if idx is None:
        # Состояние потеряно (например, после рестарта бота) — начинаем заново.
        _reset(context)
        await _serve_question(query, context)
        return

    chosen_key = query.data[len(CB_QUIZ_ANS_PREFIX):]
    result = grade(idx, chosen_key)

    context.user_data[_ANSWERED] = context.user_data.get(_ANSWERED, 0) + 1
    if result["is_correct"]:
        context.user_data[_CORRECT] = context.user_data.get(_CORRECT, 0) + 1

    verdict = "✅ <b>Верно!</b>" if result["is_correct"] else "❌ <b>Неверно.</b>"
    await query.edit_message_text(
        f"{verdict}\n\n"
        f"Правильный ответ: {result['correct_label']}\n"
        f"📌 Пункт {result['rule']} регламента\n\n"
        f"📊 Счёт: {context.user_data[_CORRECT]}/{context.user_data[_ANSWERED]}",
        parse_mode="HTML",
        reply_markup=quiz_result_keyboard(),
    )


async def on_quiz_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        final_text(
            context.user_data.get(_CORRECT, 0),
            context.user_data.get(_ANSWERED, 0),
        ),
        parse_mode="HTML",
        reply_markup=quiz_finish_keyboard(),
    )


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------

def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_quiz,        pattern=f"^{CB_QUIZ}$"))
    app.add_handler(CallbackQueryHandler(on_quiz_start,  pattern=f"^{CB_QUIZ_START}$"))
    app.add_handler(CallbackQueryHandler(on_quiz_next,   pattern=f"^{CB_QUIZ_NEXT}$"))
    app.add_handler(CallbackQueryHandler(on_quiz_finish, pattern=f"^{CB_QUIZ_FINISH}$"))
    app.add_handler(CallbackQueryHandler(on_quiz_answer, pattern=f"^{CB_QUIZ_ANS_PREFIX}"))
