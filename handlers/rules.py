from __future__ import annotations

import re
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from constants import CB_RULES, CB_RULE_PREFIX, CB_RSUB_PREFIX
from keyboards.rules import MENU, SECTIONS, RULE_BACK, menu_keyboard, back_keyboard

_MAX_LEN = 4000


def _split_text(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\n+", text):
        candidate = (current + "\n\n" + paragraph).strip() if current else paragraph
        if len(candidate) <= _MAX_LEN:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(paragraph) > _MAX_LEN:
                for i in range(0, len(paragraph), _MAX_LEN):
                    chunks.append(paragraph[i:i + _MAX_LEN])
                current = ""
            else:
                current = paragraph
    if current:
        chunks.append(current)
    return chunks


async def _show_menu(query, node_cb: str) -> None:
    node = MENU[node_cb]
    await query.edit_message_text(
        node.title,
        parse_mode="HTML",
        reply_markup=menu_keyboard(node_cb),
    )


async def on_rules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _show_menu(query, CB_RULES)


async def on_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _show_menu(query, query.data)


async def on_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    rule_cb = query.data
    key = rule_cb[len(CB_RULE_PREFIX):]
    if key not in SECTIONS:
        return

    title, body = SECTIONS[key]
    chunks = _split_text(body)
    header = f"📖 <b>{title}</b>\n\n"

    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        msg_text = (header + chunk) if i == 0 else chunk

        if i == 0:
            await query.edit_message_text(
                msg_text,
                parse_mode="HTML",
                reply_markup=back_keyboard(rule_cb) if is_last else None,
            )
        else:
            await query.message.reply_text(
                msg_text,
                parse_mode="HTML",
                reply_markup=back_keyboard(rule_cb) if is_last else None,
            )


def register(app) -> None:
    app.add_handler(CallbackQueryHandler(on_rules_menu, pattern=f"^{CB_RULES}$"))
    app.add_handler(CallbackQueryHandler(on_submenu,    pattern=f"^{CB_RSUB_PREFIX}"))
    app.add_handler(CallbackQueryHandler(on_section,    pattern=f"^{CB_RULE_PREFIX}"))
