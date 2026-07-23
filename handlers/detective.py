from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import (
    CB_DETECTIVE, CB_DET_NEW_PREFIX, CB_DET_CHECK, CB_DET_TOGGLE_PREFIX,
)
from keyboards.detective import (
    DETECTIVE_INTRO, detective_intro_keyboard, puzzle_keyboard, result_keyboard,
)
from game.detective_game import generate_puzzle, format_puzzle, explain, NUM_BLACK

_PUZZLE = "det_puzzle"   # текущая головоломка
_SEL    = "det_sel"      # множество отмеченных игроков
_DIFF   = "det_diff"     # последняя выбранная сложность


async def _serve_new(query, context: ContextTypes.DEFAULT_TYPE, difficulty: str) -> None:
    if difficulty not in ("easy", "hard"):
        difficulty = "hard"
    context.user_data[_DIFF] = difficulty
    puzzle = generate_puzzle(difficulty)
    context.user_data[_PUZZLE] = puzzle
    context.user_data[_SEL] = set()
    await query.edit_message_text(
        format_puzzle(puzzle),
        parse_mode="HTML",
        reply_markup=puzzle_keyboard(set()),
    )


async def on_detective(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        DETECTIVE_INTRO,
        parse_mode="HTML",
        reply_markup=detective_intro_keyboard(),
    )


async def on_det_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _serve_new(query, context, query.data[len(CB_DET_NEW_PREFIX):])


async def on_det_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if _PUZZLE not in context.user_data:
        await query.answer()
        await _serve_new(query, context, context.user_data.get(_DIFF, "hard"))
        return

    n = int(query.data[len(CB_DET_TOGGLE_PREFIX):])
    sel: set[int] = context.user_data.setdefault(_SEL, set())

    if n in sel:
        sel.discard(n)
    elif len(sel) >= NUM_BLACK:
        await query.answer(f"Уже отмечено {NUM_BLACK}. Сними лишнего.", show_alert=False)
        return
    else:
        sel.add(n)

    await query.answer()
    await query.edit_message_reply_markup(reply_markup=puzzle_keyboard(sel))


async def on_det_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    puzzle = context.user_data.get(_PUZZLE)
    sel: set[int] = context.user_data.get(_SEL, set())

    if not puzzle:
        await query.answer()
        await _serve_new(query, context, context.user_data.get(_DIFF, "hard"))
        return

    if len(sel) != NUM_BLACK:
        await query.answer(f"Отметь ровно {NUM_BLACK} игроков.", show_alert=False)
        return

    await query.answer()
    is_correct = sel == set(puzzle["blacks"])
    verdict = "✅ <b>Раскрыто!</b>" if is_correct else "❌ <b>Не сошлось.</b>"

    await query.edit_message_text(
        f"{verdict}\n\n{explain(puzzle)}",
        parse_mode="HTML",
        reply_markup=result_keyboard(),
    )


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_detective, pattern=f"^{CB_DETECTIVE}$"))
    app.add_handler(CallbackQueryHandler(on_det_new,    pattern=f"^{CB_DET_NEW_PREFIX}"))
    app.add_handler(CallbackQueryHandler(on_det_check,  pattern=f"^{CB_DET_CHECK}$"))
    app.add_handler(CallbackQueryHandler(on_det_toggle, pattern=f"^{CB_DET_TOGGLE_PREFIX}"))
