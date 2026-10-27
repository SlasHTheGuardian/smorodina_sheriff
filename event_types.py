"""Виды мероприятий и их названия в интерфейсе."""

EVENT_TYPE_MAFIA = "mafia"

EVENT_TYPE_LABELS = {
    EVENT_TYPE_MAFIA: "Мафия",
    "board_games": "Настолки",
    "online_meeting": "Онлайн-встреча",
    "meetup": "Сходка",
    "other": "Другое",
}

EVENT_TYPE_CHECK_SQL = (
    "event_type IN (" + ",".join(f"'{code}'" for code in EVENT_TYPE_LABELS) + ")"
)
