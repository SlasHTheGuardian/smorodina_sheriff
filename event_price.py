MAX_EVENT_PRICE_RUBLES = 1_000_000


def parse_event_price(value: str) -> int:
    """Разбирает целую неотрицательную стоимость мероприятия в рублях."""
    normalized = value.strip().replace(" ", "")
    if not normalized.isascii() or not normalized.isdigit():
        raise ValueError("Некорректная стоимость мероприятия")
    price = int(normalized)
    if not 0 <= price <= MAX_EVENT_PRICE_RUBLES:
        raise ValueError("Некорректная стоимость мероприятия")
    return price


def format_event_price(price_rubles: int | None) -> str:
    """Форматирует стоимость для карточек и сообщений бота."""
    price = 500 if price_rubles is None else price_rubles
    if price == 0:
        return "Бесплатно"
    return f"{price:,}".replace(",", " ") + " ₽"
