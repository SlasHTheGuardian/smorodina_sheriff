"""
Мини-игра «Ночной детектив».

Бот показывает публичный ход завершённой партии (дневные посадки, ночные
убийства, заявления вскрывшихся шерифов) — роли скрыты. Игрок вычисляет всех
троих чёрных. Партия генерируется так, что расклад восстанавливается из хода
ОДНОЗНАЧНО (проверяется солвером).

Два уровня сложности:
  • "easy" — один настоящий вскрывшийся шериф, его проверки достоверны;
  • "hard" — ДВОЕ называют себя шерифом, один из них фейк (чёрный с ложными
    проверками). Надо понять, чьи проверки настоящие, и только потом считать.

Рычаги логики (часть унаследована из game/sawing_game.py):
  1. состав: ровно 3 чёрных (один Дон), 1 шериф, 6 мирных;
  2. ночью мафия стреляет только в красных → убитый ночью не чёрный;
  3. проверки НАСТОЯЩЕГО шерифа достоверны;
  4. фейк-шериф — чёрный; если он заявил проверок больше, чем было ночей, он
     спалился (шериф проверяет одного за ночь);
  5. финальный паритет согласован с результатом партии.

Публичный API:
    generate_puzzle(difficulty) -> dict
    format_puzzle(p) -> str
    explain(p) -> str
"""

from __future__ import annotations
import random
from itertools import combinations

N = 10
NUM_BLACK = 3


# ---------------------------------------------------------------------------
# Симуляция правило-согласованной партии
# ---------------------------------------------------------------------------

def _simulate() -> dict | None:
    players = list(range(1, N + 1))
    shuffled = players[:]
    random.shuffle(shuffled)
    black = set(shuffled[:NUM_BLACK])
    don = shuffled[0]
    sheriff = shuffled[NUM_BLACK]

    alive = set(players)
    events: list[tuple[str, int]] = []
    real_checks: dict[int, str] = {}
    unchecked = [p for p in players if p != sheriff]
    random.shuffle(unchecked)
    nights = 0

    def blacks_alive() -> int:
        return len(alive & black)

    def terminal() -> str | None:
        ba = blacks_alive()
        ra = len(alive) - ba
        if ba == 0:
            return "red"
        if ba >= ra:
            return "black"
        return None

    def pack(result: str) -> dict:
        eliminated = [p for _, p in events]
        return {
            "black":       black,
            "don":         don,
            "sheriff":     sheriff,
            "real_checks": real_checks,
            "events":      events,
            "result":      result,
            "nights":      nights,
            "night_kills": [p for t, p in events if t == "kill"],
            "day_votes":   [p for t, p in events if t == "vote"],
            "alive_final": [p for p in players if p not in eliminated],
        }

    for _ in range(1, 8):
        # День: голосование выводит случайного живого.
        if alive:
            voted = random.choice(sorted(alive))
            alive.discard(voted)
            events.append(("vote", voted))
            res = terminal()
            if res:
                return pack(res)

        # Ночь.
        nights += 1
        if sheriff in alive and random.random() < 0.8:
            while unchecked and unchecked[-1] not in alive:
                unchecked.pop()
            if unchecked:
                c = unchecked.pop()
                real_checks[c] = "black" if c in black else "red"

        red_targets = [p for p in alive if p not in black]
        if red_targets and random.random() < 0.85:
            victim = random.choice(red_targets)   # мафия не стреляет своих
            alive.discard(victim)
            events.append(("kill", victim))
            res = terminal()
            if res:
                return pack(res)

    return None


# ---------------------------------------------------------------------------
# Фейк-шериф для «сложного» уровня
# ---------------------------------------------------------------------------

def _build_fake(g: dict) -> tuple[int, dict[int, str], str]:
    """Возвращает (id фейка, его ложные проверки, тип уличающего рычага)."""
    fake_id = random.choice(list(g["black"]))
    nights = g["nights"]
    night_kills = g["night_kills"]
    others = [p for p in range(1, N + 1) if p != fake_id]
    random.shuffle(others)
    checks: dict[int, str] = {}

    mode = random.random()
    if night_kills and mode < 0.55:
        # Рычаг A: фейк записал в чёрные ночную жертву (а её мафия не убивала бы).
        for p in others[:random.randint(0, max(0, nights - 1))]:
            checks[p] = random.choice(["black", "red"])
        checks[random.choice(night_kills)] = "black"
        kind = "killed_black"
    elif mode < 0.8 or not night_kills:
        # Рычаг B: перебор проверок — больше, чем было ночей.
        for p in others[:nights + 1]:
            checks[p] = random.choice(["black", "red"])
        kind = "overcheck"
    else:
        # Рычаг C: правдоподобная ложь (≤ ночей), уличается счётом — самый трудный.
        for p in others[:random.randint(1, max(1, nights))]:
            checks[p] = random.choice(["black", "red"])
        kind = "counting"

    return fake_id, checks, kind


# ---------------------------------------------------------------------------
# Солвер: какие наборы из 3 чёрных совместимы с публичным ходом
# ---------------------------------------------------------------------------

def _valid_assignments(rec: dict) -> list[dict]:
    """Каждое решение: {B, real_id} — набор чёрных и кто настоящий шериф."""
    night_kills = set(rec["night_kills"])
    alive_final = set(rec["alive_final"])
    result = rec["result"]
    nights = rec["nights"]
    claims = rec["claims"]
    claim_ids = [c["id"] for c in claims]

    out: list[dict] = []
    for combo in combinations(range(1, N + 1), NUM_BLACK):
        B = set(combo)
        if B & night_kills:                                   # рычаг 2
            continue
        ba = len(B & alive_final)
        ra = len(alive_final) - ba
        if result == "red" and ba != 0:                       # рычаг 5
            continue
        if result == "black" and ba < ra:
            continue

        # Кто из заявившихся — настоящий шериф?
        for real in claims:
            rid = real["id"]
            if rid in B:                                       # настоящий шериф красный
                continue
            # Остальные заявившиеся обязаны быть фейками → чёрными (рычаг 4).
            if any(cid not in B for cid in claim_ids if cid != rid):
                continue
            if len(real["checks"]) > nights:                  # шериф не успел бы (рычаг 4)
                continue
            if any((p in B) != (c == "black") for p, c in real["checks"].items()):
                continue                                       # рычаг 3
            out.append({"B": B, "real_id": rid})
    return out


# ---------------------------------------------------------------------------
# Генерация головоломки с единственным решением
# ---------------------------------------------------------------------------

def generate_puzzle(difficulty: str = "hard", max_attempts: int = 30000) -> dict:
    for _ in range(max_attempts):
        g = _simulate()
        if not g:
            continue
        # Хотя бы один чёрный должен выводиться логикой, а не читаться с проверки.
        if sum(1 for c in g["real_checks"].values() if c == "black") >= NUM_BLACK:
            continue

        real_claim = {"id": g["sheriff"], "checks": dict(g["real_checks"])}
        fake_id = fake_kind = None
        if difficulty == "hard":
            fake_id, fake_checks, fake_kind = _build_fake(g)
            claims = [real_claim, {"id": fake_id, "checks": fake_checks}]
            random.shuffle(claims)
        else:
            claims = [real_claim]

        rec = {
            "difficulty":  difficulty,
            "claims":      claims,
            "fake":        fake_id,
            "fake_kind":   fake_kind,
            "events":      g["events"],
            "result":      g["result"],
            "nights":      g["nights"],
            "night_kills": g["night_kills"],
            "day_votes":   g["day_votes"],
            "alive_final": g["alive_final"],
            "don":         g["don"],
            "sheriff":     g["sheriff"],
        }

        assigns = _valid_assignments(rec)
        Bs = {frozenset(a["B"]) for a in assigns}
        if len(Bs) != 1:
            continue
        B = next(iter(Bs))
        if B != frozenset(g["black"]):       # единственное решение обязано быть истиной
            continue

        rec["blacks"] = sorted(B)
        rec["real_id"] = next(a["real_id"] for a in assigns if frozenset(a["B"]) == B)
        return rec

    raise RuntimeError("Не удалось сгенерировать однозначную партию")


# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------

def _nums(players) -> str:
    return ", ".join(f"№{p}" for p in players) if players else "никого"


def _fmt_checks(checks: dict[int, str]) -> str:
    if not checks:
        return "проверок нет"
    return ", ".join(
        f"№{p}—{'чёрный' if c == 'black' else 'красный'}"
        for p, c in sorted(checks.items())
    )


def format_puzzle(p: dict) -> str:
    lines = ["🕯️ <b>Ночной детектив</b>", "", "📜 <b>Ход партии:</b>"]
    for i, (t, player) in enumerate(p["events"], 1):
        verb = "🗳 Днём голосованием выведен" if t == "vote" else "🌙 Ночью убит"
        lines.append(f"  {i}. {verb} №{player}")
    lines.append("")

    claims = p["claims"]
    if len(claims) == 1:
        c = claims[0]
        lines.append(f"🔍 Вскрылся шериф №{c['id']}. Его проверки: {_fmt_checks(c['checks'])}")
    else:
        lines.append("🃏 <b>Двое называют себя шерифом — один фейк:</b>")
        for c in sorted(claims, key=lambda c: c["id"]):
            lines.append(f"  • Игрок №{c['id']}: {_fmt_checks(c['checks'])}")

    win = "красных" if p["result"] == "red" else "чёрных"
    lines.append(f"🏆 Итог партии: победа {win}")
    lines.append(f"🪑 Дожили до конца: {_nums(p['alive_final'])}")
    lines.append("")
    lines.append("❓ <b>Кто трое чёрных? Отметь троих и проверь.</b>")
    return "\n".join(lines)


def _closing(p: dict) -> str:
    if p["result"] == "red":
        # Все чёрные выведены днём (ночью бьют только красных). Из посаженных
        # вычёркиваем доказанных красных: настоящего шерифа и его красные проверки.
        real = next(c for c in p["claims"] if c["id"] == p["real_id"])
        red_checked = {pl for pl, c in real["checks"].items() if c == "red"}
        suspects = [v for v in p["day_votes"]
                    if v != p["real_id"] and v not in red_checked]
        base = ("🧩 Красные победили — все 3 чёрных выведены днём (ночью бьют "
                "только красных).")
        if len(suspects) == NUM_BLACK:
            return base + (f" Вычёркиваем настоящего шерифа и его красные проверки — "
                           f"остаются ровно трое: {_nums(suspects)}.")
        return base + (" Вычёркиваем настоящего шерифа, его красные проверки и прочих "
                       "доказанных красных — остаётся искомая тройка.")
    return ("🧩 Чёрные дожали стол до паритета. Исключив доказанных красных и "
            "сверившись с настоящими проверками, на трёх чёрных подходит "
            "единственный набор.")


def explain(p: dict) -> str:
    lines = [
        f"⚫ Чёрные: {_nums(p['blacks'])}.",
        f"👑 Дон — №{p['don']}.  🔍 Настоящий шериф — №{p['real_id']}.",
        "",
        "<b>Зацепки:</b>",
    ]

    # Уличение фейка (сложный уровень).
    if len(p["claims"]) > 1:
        fake_id = p["fake"]
        fake_claim = next(c for c in p["claims"] if c["id"] == fake_id)
        nights = p["nights"]
        nk = set(p["night_kills"])
        if len(fake_claim["checks"]) > nights:
            lines.append(
                f"🃏 №{fake_id} заявил {len(fake_claim['checks'])} проверок, а ночей "
                f"было {nights} — шериф проверяет одного за ночь, столько не успеть. "
                f"Значит №{fake_id} — фейк и сам чёрный.")
        elif any(c == "black" and pl in nk for pl, c in fake_claim["checks"].items()):
            x = next(pl for pl, c in fake_claim["checks"].items() if c == "black" and pl in nk)
            lines.append(
                f"🃏 №{fake_id} записал в чёрные №{x}, но №{x} убили ночью — мафия "
                f"своих не стреляет. Значит №{fake_id} соврал и сам чёрный.")
        else:
            lines.append(
                f"🃏 Если принять №{fake_id} за шерифа, его проверки не складываются "
                f"ни в один расклад, совместимый с убийствами и итогом партии. Фейк — он.")

    if p["night_kills"]:
        lines.append(f"🔴 Точно красные (убиты ночью): {_nums(p['night_kills'])}.")
    real_claim = next(c for c in p["claims"] if c["id"] == p["real_id"])
    real_reds = [pl for pl, c in real_claim["checks"].items() if c == "red"]
    real_blacks = [pl for pl, c in real_claim["checks"].items() if c == "black"]
    if real_reds:
        lines.append(f"🔴 Красные по проверке настоящего шерифа: {_nums(real_reds)}.")
    if real_blacks:
        lines.append(f"⚫ Чёрные по проверке настоящего шерифа: {_nums(real_blacks)}.")

    lines.append(_closing(p))
    return "\n".join(lines)
