from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from constants import (
    CB_ADMIN_RESULTS,
    CB_CANCEL_GAME_NICKNAME,
    CB_CREATE_GAME_NICKNAME,
    CB_MAIN,
    CB_MY_RATING,
    CB_MY_RESULTS,
    CB_STATS,
)
from db.models import Game, GamePlayer, PlayedGame, Registration
from gametime import fmt


CB_RESULT_EVENT_PREFIX = "res_ev:"
CB_RESULT_ADD_PREFIX = "res_add:"
CB_RESULT_GAMES_PREFIX = "res_games:"
CB_RESULT_GAME_PREFIX = "res_game:"
CB_RESULT_GAME_ADD_PREFIX = "res_game_add:"
CB_RESULT_GAME_DELETE_PREFIX = "res_game_delete:"
CB_RESULT_GAME_DELETE_CONFIRM_PREFIX = "res_game_delete_ok:"
CB_RESULT_PLAYER_PREFIX = "res_player:"
CB_RESULT_ROLE_PREFIX = "res_role:"
CB_RESULT_WINNER_PREFIX = "res_win:"
CB_RESULT_WINNER_MENU = "res_winner_menu"
CB_RESULT_TABLE = "res_table"
CB_RESULT_SKIPS = "res_skips"
CB_RESULT_HOST = "res_host"
CB_RESULT_SLOT_PREFIX = "res_slot:"
CB_RESULT_GUEST = "res_guest"
CB_RESULT_CANCEL_INPUT = "res_cancel_input"

ROLE_LABELS = {
    "civilian": "Мирный",
    "sheriff": "Шериф",
    "mafia": "Мафия",
    "don": "Дон",
    "host": "Ведущий",
    "skip": "Пропуск",
}

ROLE_EMOJIS = {
    "civilian": "🟥",
    "sheriff": "🔍",
    "mafia": "⬛",
    "don": "🎩",
    "host": "🎙️",
    "skip": "🚫",
}


def recent_events_keyboard(events: list[Game]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{fmt(event.starts_at)} · {event.title}",
            callback_data=f"{CB_RESULT_EVENT_PREFIX}{event.id}",
        )]
        for event in events
    ]
    rows.append([InlineKeyboardButton("Назад", callback_data=CB_MAIN)])
    return InlineKeyboardMarkup(rows)


def event_result_keyboard(
    event_id: int, has_games: bool
) -> InlineKeyboardMarkup:
    action = "Редактировать результаты" if has_games else "Добавить результаты"
    action_cb = (
        f"{CB_RESULT_GAMES_PREFIX}{event_id}"
        if has_games else f"{CB_RESULT_ADD_PREFIX}{event_id}"
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(action, callback_data=action_cb)],
        [InlineKeyboardButton(
            "Назад", callback_data=CB_ADMIN_RESULTS
        )],
    ])


def played_games_keyboard(
    games: list[PlayedGame], event_id: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for game in games:
        mark = "✅" if game.winner_side else "▫️"
        rows.append([
            InlineKeyboardButton(
                f"{mark} Игра №{game.game_number}",
                callback_data=f"{CB_RESULT_GAME_PREFIX}{game.id}",
            ),
            InlineKeyboardButton(
                "Удалить",
                callback_data=f"{CB_RESULT_GAME_DELETE_PREFIX}{game.id}",
            ),
        ])
    rows.append([InlineKeyboardButton(
        "Добавить игру",
        callback_data=f"{CB_RESULT_GAME_ADD_PREFIX}{event_id}",
    )])
    rows.append([InlineKeyboardButton(
        "Назад", callback_data=f"{CB_RESULT_EVENT_PREFIX}{event_id}"
    )])
    return InlineKeyboardMarkup(rows)


def confirm_delete_game_keyboard(
    game_id: int, event_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Удалить игру",
            callback_data=f"{CB_RESULT_GAME_DELETE_CONFIRM_PREFIX}{game_id}",
        )],
        [InlineKeyboardButton(
            "Отмена", callback_data=f"{CB_RESULT_GAMES_PREFIX}{event_id}"
        )],
    ])


def game_management_keyboard(game: PlayedGame) -> InlineKeyboardMarkup:
    winner = {
        "town": "Красные",
        "mafia": "Чёрные",
    }.get(game.winner_side, "не выбран")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Игроки за столом", callback_data=CB_RESULT_TABLE
        )],
        [InlineKeyboardButton(
            "Пропустившие", callback_data=CB_RESULT_SKIPS
        )],
        [InlineKeyboardButton(
            "Ведущий", callback_data=CB_RESULT_HOST
        )],
        [InlineKeyboardButton(
            f"Победитель: {winner}", callback_data=CB_RESULT_WINNER_MENU
        )],
        [InlineKeyboardButton(
            "Назад", callback_data=f"{CB_RESULT_GAMES_PREFIX}{game.event_id}"
        )],
    ])


def table_seats_keyboard(
    participants: list[Registration],
    assignments: dict[int, GamePlayer],
    game: PlayedGame,
) -> InlineKeyboardMarkup:
    registrations = {reg.player_id: reg for reg in participants}
    seated = {
        assignment.seat_number: assignment
        for assignment in assignments.values()
        if assignment.seat_number is not None
        and assignment.user_id in registrations
    }

    def seat_button(seat: int) -> InlineKeyboardButton:
        assignment = seated.get(seat)
        if assignment and assignment.role:
            user = registrations[assignment.user_id].player
            emoji = ROLE_EMOJIS.get(assignment.role.code, "▫️")
            label = f"{seat} {emoji} {user.game_display}"
        else:
            label = f"{seat} · Свободно"
        return InlineKeyboardButton(
            label, callback_data=f"{CB_RESULT_SLOT_PREFIX}{seat}"
        )

    rows = [
        [seat_button(left), seat_button(left + 5)]
        for left in range(1, 6)
    ]
    rows.append([InlineKeyboardButton(
        "Назад к игре", callback_data=f"{CB_RESULT_GAME_PREFIX}{game.id}"
    )])
    return InlineKeyboardMarkup(rows)


def participant_picker_keyboard(
    participants: list[Registration],
    assignments: dict[int, GamePlayer],
    game: PlayedGame,
    mode: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for registration in participants:
        user = registration.player
        assignment = assignments.get(user.id)
        if assignment and assignment.role and mode in ("seat", "skip"):
            label = f"🔒 {user.game_display}"
        elif assignment and assignment.seat_number is not None and assignment.role:
            emoji = ROLE_EMOJIS.get(assignment.role.code, "▫️")
            label = (
                f"✅ №{assignment.seat_number} {emoji} "
                f"{user.game_display}"
            )
        elif assignment and assignment.role:
            emoji = ROLE_EMOJIS.get(assignment.role.code, "▫️")
            label = f"{emoji} {user.game_display}"
        else:
            label = user.game_display
        rows.append([InlineKeyboardButton(
            label,
            callback_data=f"{CB_RESULT_PLAYER_PREFIX}{user.id}",
        )])

    rows.append([InlineKeyboardButton(
        "Добавить игрока", callback_data=CB_RESULT_GUEST
    )])
    back_callback = (
        CB_RESULT_TABLE
        if mode == "seat" else f"{CB_RESULT_GAME_PREFIX}{game.id}"
    )
    rows.append([InlineKeyboardButton(
        "Назад", callback_data=back_callback
    )])
    return InlineKeyboardMarkup(rows)


def winner_keyboard(game: PlayedGame) -> InlineKeyboardMarkup:
    town_mark = "✅ " if game.winner_side == "town" else ""
    mafia_mark = "✅ " if game.winner_side == "mafia" else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{town_mark}Победа красных",
            callback_data=f"{CB_RESULT_WINNER_PREFIX}town",
        )],
        [InlineKeyboardButton(
            f"{mafia_mark}Победа чёрных",
            callback_data=f"{CB_RESULT_WINNER_PREFIX}mafia",
        )],
        [InlineKeyboardButton(
            "Назад к игре", callback_data=f"{CB_RESULT_GAME_PREFIX}{game.id}"
        )],
    ])


def role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Мирный", callback_data=f"{CB_RESULT_ROLE_PREFIX}civilian"
            ),
            InlineKeyboardButton(
                "Шериф", callback_data=f"{CB_RESULT_ROLE_PREFIX}sheriff"
            ),
        ],
        [
            InlineKeyboardButton(
                "Мафия", callback_data=f"{CB_RESULT_ROLE_PREFIX}mafia"
            ),
            InlineKeyboardButton(
                "Дон", callback_data=f"{CB_RESULT_ROLE_PREFIX}don"
            ),
        ],
        [InlineKeyboardButton(
            "Назад", callback_data=CB_RESULT_CANCEL_INPUT
        )],
    ])


def cancel_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Отмена", callback_data=CB_RESULT_CANCEL_INPUT
        )],
    ])


def stats_keyboard(has_nickname: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not has_nickname:
        rows.append([InlineKeyboardButton(
            "Создать игровой ник",
            callback_data=CB_CREATE_GAME_NICKNAME,
        )])
    else:
        rows.append([InlineKeyboardButton(
            "Мой рейтинг", callback_data=CB_MY_RATING
        )])
    rows.append([InlineKeyboardButton(
        "Мои игры", callback_data=CB_MY_RESULTS
    )])
    if has_nickname:
        rows.append([InlineKeyboardButton(
            "Изменить игровой ник",
            callback_data=CB_CREATE_GAME_NICKNAME,
        )])
    rows.append([InlineKeyboardButton("Назад", callback_data=CB_MAIN)])
    return InlineKeyboardMarkup(rows)


def nickname_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Отмена", callback_data=CB_CANCEL_GAME_NICKNAME
        ),
    ]])


def rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад", callback_data=CB_STATS)],
        [InlineKeyboardButton("В главное меню", callback_data=CB_MAIN)],
    ])


def my_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад", callback_data=CB_STATS)],
        [InlineKeyboardButton("В главное меню", callback_data=CB_MAIN)],
    ])
