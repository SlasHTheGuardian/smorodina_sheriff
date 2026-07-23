"""
Логика квиза «Фолы и наказания».

Публичный API:
    new_deck() -> list[int]                       — перемешанная колода индексов вопросов
    format_question(idx, answered, correct) -> str — текст вопроса с прогрессом
    grade(idx, chosen_key) -> dict                — проверка ответа
    final_text(correct, answered) -> str          — итог квиза
"""

from __future__ import annotations
import random

from game.quiz_data import VIOLATIONS, CATEGORIES


def new_deck() -> list[int]:
    """Перемешанная колода всех вопросов — чтобы не повторялись подряд."""
    deck = list(range(len(VIOLATIONS)))
    random.shuffle(deck)
    return deck


def format_question(idx: int, answered: int, correct: int) -> str:
    v = VIOLATIONS[idx]
    lines: list[str] = []
    if answered:
        lines.append(f"📊 Счёт: {correct}/{answered}")
        lines.append("")
    lines.append("🚫 <b>Нарушение:</b>")
    lines.append(f"«{v['text']}»")
    lines.append("")
    lines.append("⚖️ Что назначит Судья?")
    return "\n".join(lines)


def grade(idx: int, chosen_key: str) -> dict:
    v = VIOLATIONS[idx]
    correct_key = v["category"]
    return {
        "is_correct":    chosen_key == correct_key,
        "correct_label": CATEGORIES[correct_key],
        "rule":          v["rule"],
    }


def final_text(correct: int, answered: int) -> str:
    if answered == 0:
        return "🏁 Квиз завершён."

    ratio = correct / answered
    if ratio == 1:
        remark = "🏆 Идеально! Судейский глаз!"
    elif ratio >= 0.8:
        remark = "🔥 Отличный результат!"
    elif ratio >= 0.5:
        remark = "👍 Неплохо, но регламент стоит перечитать."
    else:
        remark = "📖 Стоит заглянуть в раздел «Дисциплинарный регламент»."

    return (
        f"🏁 <b>Квиз завершён!</b>\n\n"
        f"Верных ответов: <b>{correct} из {answered}</b>.\n\n"
        f"{remark}"
    )
