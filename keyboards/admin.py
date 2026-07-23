from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from constants import (
    CB_ADMIN_EVENTS,
    CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX,
    CB_ADMIN_EVENT_DELETE_PREFIX,
    CB_ADMIN_EVENT_EDIT_CLEAR,
    CB_ADMIN_EVENT_EDIT_FIELD_PREFIX,
    CB_ADMIN_EVENT_EDIT_PREFIX,
    CB_ADMIN_EVENT_VIEW_PREFIX,
    CB_ADMIN_EVENT_CANCEL,
    CB_ADMIN_EVENT_CONFIRM,
    CB_ADMIN_EVENT_SKIP_LOCATION,
    CB_ADMIN_EVENT_SKIP_NOTE,
    CB_GAME_PREFIX,
    CB_MAIN,
)
from db.models import Game
from gametime import fmt


def _compact_title(title: str, limit: int = 24) -> str:
    return title if len(title) <= limit else title[:limit - 1] + "…"


def admin_events_keyboard(events: list[Game]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for event in events:
        rows.append([InlineKeyboardButton(
            f"{_compact_title(event.title)} · {fmt(event.starts_at)}",
            callback_data=f"{CB_ADMIN_EVENT_VIEW_PREFIX}{event.id}",
        )])
    rows.append([InlineKeyboardButton(
        "В главное меню", callback_data=CB_MAIN
    )])
    return InlineKeyboardMarkup(rows)


def admin_event_detail_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Изменить",
            callback_data=f"{CB_ADMIN_EVENT_EDIT_PREFIX}{event_id}",
        )],
        [InlineKeyboardButton(
            "Удалить",
            callback_data=f"{CB_ADMIN_EVENT_DELETE_PREFIX}{event_id}",
        )],
        [InlineKeyboardButton(
            "Назад", callback_data=CB_ADMIN_EVENTS
        )],
    ])


def event_edit_fields_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Название",
                callback_data=f"{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}title",
            ),
            InlineKeyboardButton(
                "Дата и время",
                callback_data=(
                    f"{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}starts_at"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                "Количество мест",
                callback_data=(
                    f"{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}capacity"
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                "Место проведения",
                callback_data=(
                    f"{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}location"
                ),
            ),
            InlineKeyboardButton(
                "Описание",
                callback_data=f"{CB_ADMIN_EVENT_EDIT_FIELD_PREFIX}note",
            ),
        ],
        [InlineKeyboardButton(
            "Назад к встрече",
            callback_data=f"{CB_ADMIN_EVENT_VIEW_PREFIX}{event_id}",
        )],
    ])


def event_edit_input_keyboard(
    event_id: int, can_clear: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_clear:
        rows.append([InlineKeyboardButton(
            "Очистить", callback_data=CB_ADMIN_EVENT_EDIT_CLEAR
        )])
    rows.append([InlineKeyboardButton(
        "Отмена",
        callback_data=f"{CB_ADMIN_EVENT_EDIT_PREFIX}{event_id}",
    )])
    return InlineKeyboardMarkup(rows)


def delete_event_confirmation_keyboard(
    event_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Удалить встречу",
            callback_data=(
                f"{CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX}{event_id}"
            ),
        )],
        [InlineKeyboardButton(
            "Отмена",
            callback_data=f"{CB_ADMIN_EVENT_VIEW_PREFIX}{event_id}",
        )],
    ])


def event_creation_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Отмена", callback_data=CB_ADMIN_EVENT_CANCEL
        ),
    ]])


def event_location_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Не указывать",
            callback_data=CB_ADMIN_EVENT_SKIP_LOCATION,
        )],
        [InlineKeyboardButton(
            "Отмена", callback_data=CB_ADMIN_EVENT_CANCEL
        )],
    ])


def event_note_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Без описания",
            callback_data=CB_ADMIN_EVENT_SKIP_NOTE,
        )],
        [InlineKeyboardButton(
            "Отмена", callback_data=CB_ADMIN_EVENT_CANCEL
        )],
    ])


def event_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Создать встречу",
            callback_data=CB_ADMIN_EVENT_CONFIRM,
        )],
        [InlineKeyboardButton(
            "Отмена", callback_data=CB_ADMIN_EVENT_CANCEL
        )],
    ])


def event_created_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Открыть встречу",
            callback_data=f"{CB_GAME_PREFIX}{event_id}",
        )],
        [InlineKeyboardButton(
            "В главное меню", callback_data=CB_MAIN
        )],
    ])
