"""
Парсит data/rules.md и возвращает разделы в порядке документа.
Ключ раздела — его порядковый номер в виде строки ("0", "1", ...).
Добавить или убрать раздел — достаточно отредактировать rules.md.
"""

from __future__ import annotations
import re
from pathlib import Path

_MD_PATH = Path(__file__).parent / "rules.md"


def load() -> list[tuple[str, str, str]]:
    """Возвращает список (key, title, body) в порядке документа."""
    text = _MD_PATH.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    result: list[tuple[str, str, str]] = []
    i = 1
    idx = 0
    while i + 1 < len(parts):
        title = parts[i].strip()
        body = parts[i + 1].strip()
        result.append((str(idx), title, body))
        idx += 1
        i += 2
    return result
