from __future__ import annotations
from dataclasses import dataclass, field
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import CB_RULE_PREFIX, CB_RSUB_PREFIX, CB_RULES, CB_MAIN
from data.rules_loader import load as _load_sections

# ---------------------------------------------------------------------------
# Контент: загружаем sections один раз при старте
# ---------------------------------------------------------------------------
_sections_list = _load_sections()  # [(key, title, body), ...]
SECTIONS: dict[str, tuple[str, str]] = {k: (t, b) for k, t, b in _sections_list}

# Индекс section_key → title (для подстановки в кнопки)
_title: dict[str, str] = {k: t for k, t, _ in _sections_list}

# ---------------------------------------------------------------------------
# Дерево меню
# Каждый узел: title, back_cb, back_label, items [(cb, label)]
# cb начинается с "rule:" (контент) или "rsub:" (подменю)
# ---------------------------------------------------------------------------

@dataclass
class MenuNode:
    title: str
    back_cb: str
    back_label: str
    items: list[tuple[str, str]] = field(default_factory=list)


def _r(key: str) -> str:
    """Коллбэк для контентного раздела."""
    return f"{CB_RULE_PREFIX}{key}"


def _s(name: str) -> str:
    """Коллбэк для подменю."""
    return f"{CB_RSUB_PREFIX}{name}"


MENU: dict[str, MenuNode] = {
    # Корень "Правила игры"
    CB_RULES: MenuNode(
        title="📖 <b>Правила игры</b>\n\nВыбери раздел:",
        back_cb=CB_MAIN,
        back_label="◀️ Обратно в меню",
        items=[
            (_s("general"),    "Общие положения"),
            (_r("9"),          "Нарушения"),
            (_s("discipline"), "Дисциплинарный регламент"),
            (_r("16"),         "Особые ситуации"),
        ],
    ),

    # Подменю «Общие положения»
    _s("general"): MenuNode(
        title="📖 <b>Общие положения</b>\n\nВыбери раздел:",
        back_cb=CB_RULES,
        back_label="◀️ Назад к разделам",
        items=[
            (_r("0"), _title.get("0", "Основные понятия")),
            (_r("1"), _title.get("1", "Игровая площадка, инвентарь и официальный язык игры")),
            (_r("2"), _title.get("2", "Игроки")),
            (_s("gameplay"), "Ход игры"),
        ],
    ),

    # Подменю «Ход игры» (подразделы 4.1–4.6)
    _s("gameplay"): MenuNode(
        title="📖 <b>Ход игры</b>\n\nВыбери раздел:",
        back_cb=_s("general"),
        back_label="◀️ Назад",
        items=[
            (_r("3"), _title.get("3", "4.1. Начало игры")),
            (_r("4"), _title.get("4", "4.2. Первая игровая «ночь»")),
            (_r("5"), _title.get("5", "4.3. Игровой «день»")),
            (_r("6"), _title.get("6", "4.4. Голосование")),
            (_r("7"), _title.get("7", "4.5. Вторая и последующие «ночи»")),
            (_r("8"), _title.get("8", "4.6. Дальнейший ход игры")),
        ],
    ),

    # Подменю «Дисциплинарный регламент»
    _s("discipline"): MenuNode(
        title="📖 <b>Дисциплинарный регламент</b>\n\nВыбери раздел:",
        back_cb=CB_RULES,
        back_label="◀️ Назад к разделам",
        items=[
            (_r("10"), "Основные положения дисциплинарного регламента"),
            (_r("11"), "Фолы"),
            (_r("12"), "Удаление со стола"),
            (_r("13"), "Присуждение победы противоположной команде (ППК)"),
            (_r("14"), "Удаление с игрового дня"),
            (_r("15"), "Удаление с турнира"),
        ],
    ),
}

# Откуда возвращаться с каждой контентной страницы
RULE_BACK: dict[str, str] = {
    _r("0"):  _s("general"),
    _r("1"):  _s("general"),
    _r("2"):  _s("general"),
    _r("3"):  _s("gameplay"),
    _r("4"):  _s("gameplay"),
    _r("5"):  _s("gameplay"),
    _r("6"):  _s("gameplay"),
    _r("7"):  _s("gameplay"),
    _r("8"):  _s("gameplay"),
    _r("9"):  CB_RULES,
    _r("10"): _s("discipline"),
    _r("11"): _s("discipline"),
    _r("12"): _s("discipline"),
    _r("13"): _s("discipline"),
    _r("14"): _s("discipline"),
    _r("15"): _s("discipline"),
    _r("16"): CB_RULES,
}

# ---------------------------------------------------------------------------
# Генераторы клавиатур
# ---------------------------------------------------------------------------

def menu_keyboard(node_cb: str) -> InlineKeyboardMarkup:
    node = MENU[node_cb]
    rows = [
        [InlineKeyboardButton(label, callback_data=cb)]
        for cb, label in node.items
    ]
    rows.append([InlineKeyboardButton(node.back_label, callback_data=node.back_cb)])
    return InlineKeyboardMarkup(rows)


def back_keyboard(rule_cb: str) -> InlineKeyboardMarkup:
    """Кнопка «Назад» для страницы с контентом."""
    dest = RULE_BACK.get(rule_cb, CB_RULES)
    node = MENU.get(dest)
    label = node.back_label if node else "◀️ Назад"
    # Для контента "back" ведёт в родительское подменю — используем его заголовок кнопки
    back_labels = {
        _s("general"):    "◀️ Назад к общим положениям",
        _s("gameplay"):   "◀️ Назад к ходу игры",
        _s("discipline"): "◀️ Назад к дисциплинарному регламенту",
        CB_RULES:         "◀️ Назад к разделам",
    }
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(back_labels.get(dest, "◀️ Назад"), callback_data=dest)],
    ])
