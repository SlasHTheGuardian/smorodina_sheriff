"""
Генератор игровых ситуаций для мини-игры «Пилим стол».

Публичный API:
    generate_situation() -> dict   — создать новую ситуацию
    format_situation(game) -> str  — отформатировать текст для Telegram
"""

from __future__ import annotations
import random
from typing import Optional


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _night_word(n: int) -> str:
    if n == 1:
        return "1 ночь"
    if n in (2, 3, 4):
        return f"{n} ночи"
    return f"{n} ночей"


def _nums(players: list[int]) -> str:
    return ", ".join(f"№{p}" for p in players)


# ---------------------------------------------------------------------------
# Генератор ситуации
# ---------------------------------------------------------------------------

def generate_situation() -> dict:
    # 1. Назначаем роли
    players = list(range(1, 11))
    shuffled = players[:]
    random.shuffle(shuffled)

    black_players: list[int] = shuffled[:3]
    sheriff: int              = shuffled[3]
    red_players: list[int]    = shuffled[4:]

    roles: dict[int, str] = {}
    for p in black_players:
        roles[p] = "чёрный"
    roles[sheriff] = "шериф"
    for p in red_players:
        roles[p] = "красный"

    # 2. Количество ночей
    nights: int = random.randint(0, 3)

    # 3. Отстрел (только не-чёрные игроки)
    eligible_shot = [p for p in players if roles[p] != "чёрный"]
    shot_count    = random.randint(0, nights)
    dead_by_shot: list[int] = random.sample(
        eligible_shot, min(shot_count, len(eligible_shot))
    )  # порядок имеет значение

    # Количество проверок шерифа
    if sheriff in dead_by_shot:
        num_sheriff_checks = dead_by_shot.index(sheriff) + 1
    else:
        num_sheriff_checks = nights

    # 4. Посадки (0 … nights-1)
    alive_after_shots = [p for p in players if p not in dead_by_shot]
    num_jailed        = random.randint(0, max(0, nights - 1))
    jailed: list[int] = sorted(
        random.sample(alive_after_shots, min(num_jailed, len(alive_after_shots)))
    )

    dead  = set(dead_by_shot) | set(jailed)
    alive = sorted(p for p in players if p not in dead)

    # 5. Роль пользователя (нужна до проверок, чтобы шериф всегда видел свои проверки)
    player_num: int  = random.choice(alive)
    player_role: str = roles[player_num]

    # 6. Проверки шерифа
    has_sheriff_checks: bool = (num_sheriff_checks > 0) and (
        True if player_role == "шериф" else random.choice([True, False])
    )

    sheriff_checks_dict: dict[int, str] = {}
    if has_sheriff_checks:
        eligible_check = [p for p in players if p != sheriff]
        for p in random.sample(eligible_check, min(num_sheriff_checks, len(eligible_check))):
            sheriff_checks_dict[p] = "чёрный" if roles[p] == "чёрный" else "красный"

    # 7. Кандидаты на попил
    number_of_candidates: int = random.choice([2, 3])
    if len(alive) < number_of_candidates:
        number_of_candidates = len(alive)
    list_of_candidates: list[int] = sorted(random.sample(alive, number_of_candidates))

    # 8. Фейковый шериф (только если есть настоящие проверки)
    has_fake_sheriff: bool           = False
    fake_sheriff_player: Optional[int] = None
    fake_sheriff_checks_dict: dict[int, str] = {}

    if has_sheriff_checks:
        alive_blacks = [p for p in alive if roles[p] == "чёрный"]
        if alive_blacks:
            has_fake_sheriff = random.choice([True, False])
            if has_fake_sheriff:
                fake_sheriff_player = random.choice(alive_blacks)
                eligible_fake = [p for p in players if p != fake_sheriff_player]
                num_fake = random.randint(1, min(nights + 1, len(eligible_fake)))
                for p in random.sample(eligible_fake, num_fake):
                    fake_sheriff_checks_dict[p] = random.choice(["красный", "чёрный"])

    # ---------------------------------------------------------------------------
    # Определяем правильный ответ
    # ---------------------------------------------------------------------------
    alive_blacks = [p for p in alive if roles[p] == "чёрный"]
    alive_count  = len(alive)
    cands        = set(list_of_candidates)

    correct_answer: bool = False
    reason: str          = ""

    # Фейк спалился, если кол-во его проверок > ночей в игре
    fake_exposed = has_fake_sheriff and len(fake_sheriff_checks_dict) > nights
    exposed_suffix = " Фейковый шериф спалился — ночей было меньше" if fake_exposed else ""

    # Правило 1: чёрных >= половины живых → победа чёрных
    if len(alive_blacks) >= alive_count / 2:
        correct_answer = False
        reason = "Такой игровой ситуации не может быть — это победа чёрных!"

    # Правило 2: живые не делятся нацело на кандидатов (для 2 и для 3)
    elif alive_count % number_of_candidates != 0:
        correct_answer = False
        reason = (
            f"Мы не попилим, кандидатов — {number_of_candidates}, "
            f"а нас {alive_count}"
        )

    # Правило: игрок — чёрный
    elif player_role == "чёрный":
        blacks_in_cands = [p for p in list_of_candidates if roles[p] == "чёрный"]
        if blacks_in_cands:
            correct_answer = False
            reason = "Мы не соглашаемся на попил чёрных. А если снимут?"
        else:
            correct_answer = True
            reason = "Пилим и сносим красных!"

    # Правило: пустой стол (никто не убит, не посажен, нет проверок) → смело пилим
    elif not has_sheriff_checks and not dead_by_shot and not jailed and alive_count == 10:
        correct_answer = True
        reason = "Почему бы и не попилить при десятерых?"

    # Два шерифа — только если фейк НЕ спалился
    elif has_fake_sheriff and not fake_exposed:
        # Правило 5: оба шерифа в кандидатах
        if sheriff in cands and fake_sheriff_player in cands:
            correct_answer = True
            reason = "С кайфом пилим шерифов!"

        # Правило 6: настоящий шериф + его чёрная проверка
        elif sheriff in cands:
            real_blacks = {p for p, c in sheriff_checks_dict.items() if c == "чёрный"}
            if real_blacks & cands:
                correct_answer = True
                reason = "Поднимаем шерифа и чёрную проверку!"
            else:
                correct_answer = True
                reason = "Почему бы и не попилить?"

        # Правило 6: фейковый шериф + его «чёрная» проверка
        elif fake_sheriff_player in cands:
            fake_blacks = {p for p, c in fake_sheriff_checks_dict.items() if c == "чёрный"}
            if fake_blacks & cands:
                correct_answer = True
                reason = "Поднимаем шерифа и чёрную проверку!"
            else:
                correct_answer = True
                reason = "Почему бы и не попилить?"

        else:
            correct_answer = True
            reason = "Почему бы и не попилить?"

    # Один шериф: проверки известны, или фейк спалился → работаем только с настоящим шерифом
    elif has_sheriff_checks:
        checked_reds   = {p for p, c in sheriff_checks_dict.items() if c == "красный"}
        checked_blacks = {p for p, c in sheriff_checks_dict.items() if c == "чёрный"}

        # Проверенный красный в кандидатах
        if checked_reds & cands:
            correct_answer = False
            reason = "Проверенные красные не пилятся!" + exposed_suffix

        # Все кандидаты — подтверждённые чёрные проверки шерифа
        elif cands <= checked_blacks:
            correct_answer = True
            reason = f"Поднимем всех {number_of_candidates}!" + exposed_suffix

        # Есть хотя бы одна чёрная проверка, но не все кандидаты — чёрные
        elif checked_blacks:
            correct_answer = False
            reason = "Безопаснее просто снимать чёрных по очереди" + exposed_suffix

        else:
            correct_answer = True
            reason = "Почему бы и не попилить?"

    # Нет информации о шерифе
    else:
        correct_answer = True
        reason = "Почему бы и не попилить?"

    return {
        "roles":                    roles,
        "nights":                   nights,
        "dead_by_shot":             dead_by_shot,
        "jailed":                   jailed,
        "alive":                    alive,
        "has_sheriff_checks":       has_sheriff_checks,
        "sheriff":                  sheriff,
        "sheriff_checks_dict":      sheriff_checks_dict,
        "has_fake_sheriff":         has_fake_sheriff,
        "fake_sheriff_player":      fake_sheriff_player,
        "fake_sheriff_checks_dict": fake_sheriff_checks_dict,
        "number_of_candidates":     number_of_candidates,
        "list_of_candidates":       list_of_candidates,
        "player_num":               player_num,
        "player_role":              player_role,
        "correct_answer":           correct_answer,
        "reason":                   reason,
        # Порядок отображения шерифов (True = настоящий первый)
        "first_is_real":            random.choice([True, False]) if has_fake_sheriff else True,
    }


# ---------------------------------------------------------------------------
# Форматирование текста ситуации
# ---------------------------------------------------------------------------

def format_situation(game: dict) -> str:
    lines: list[str] = []

    lines.append(f"🎮 <b>Вы — игрок №{game['player_num']} ({game['player_role']}).</b>")
    lines.append("")

    nights = game["nights"]
    lines.append(f"🌙 Ночей прошло: {_night_word(nights)}." if nights else "🌙 Ночей ещё не было.")

    shot = game["dead_by_shot"]
    if shot:
        lines.append("💀 Убиты выстрелами:")
        lines.extend(f"   • №{p}" for p in shot)
    else:
        lines.append("💀 Убиты выстрелами: никто")

    jailed = game["jailed"]
    if jailed:
        lines.append("🔒 Посажены:")
        lines.extend(f"   • №{p}" for p in jailed)
    else:
        lines.append("🔒 Посажены: никто")

    if game["player_role"] == "чёрный":
        # Чёрные знают расклад: шериф показывается как «красный»
        lines.append("🪑 За столом:")
        lines.extend(
            f"   • №{p} ({'чёрный' if game['roles'][p] == 'чёрный' else 'красный'})"
            for p in game["alive"]
        )
    else:
        lines.append("🪑 За столом:")
        lines.extend(f"   • №{p}" for p in game["alive"])
    lines.append("")
    lines.append(f"🎯 Предлагается попилить: {_nums(game['list_of_candidates'])}")
    lines.append("")

    if game["has_sheriff_checks"]:
        real_c  = game["sheriff_checks_dict"]
        fake_c  = game["fake_sheriff_checks_dict"]

        def _fmt(checks: dict[int, str]) -> list[str]:
            return [f"   • №{p} — {c}" for p, c in sorted(checks.items())]

        is_sheriff = game["player_role"] == "шериф"
        real_num   = game["sheriff"]
        fake_num   = game["fake_sheriff_player"]

        if game["has_fake_sheriff"] and fake_c:
            first_is_real_first = game["first_is_real"]
            first_c  = real_c  if first_is_real_first else fake_c
            second_c = fake_c  if first_is_real_first else real_c
            first_num  = real_num if first_is_real_first else fake_num
            second_num = fake_num if first_is_real_first else real_num
            first_is_real  = first_is_real_first
            second_is_real = not first_is_real_first
            if first_c:
                if is_sheriff and first_is_real:
                    label = f"Вы (№{first_num}) сделали проверки:"
                elif is_sheriff and not first_is_real:
                    label = f"Проверки фейкового шерифа №{first_num}:"
                else:
                    label = f"Первый шериф №{first_num} сделал проверки:"
                lines.append(f"🔍 {label}")
                lines.extend(_fmt(first_c))
            if second_c:
                if is_sheriff and second_is_real:
                    label = f"Вы (№{second_num}) сделали проверки:"
                elif is_sheriff and not second_is_real:
                    label = f"Проверки фейкового шерифа №{second_num}:"
                else:
                    label = f"Второй шериф №{second_num} сделал проверки:"
                lines.append(f"🔍 {label}")
                lines.extend(_fmt(second_c))
        elif real_c:
            if is_sheriff:
                label = f"Вы (№{real_num}) сделали проверки:"
            else:
                label = f"Шериф №{real_num} сделал проверки:"
            lines.append(f"🔍 {label}")
            lines.extend(_fmt(real_c))

    lines.append("")
    lines.append("❓ <b>Пилим?</b>")
    return "\n".join(lines)
