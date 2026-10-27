"""Local Docker probe. Does not contact Telegram or consume updates."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def health_path() -> Path:
    return Path(os.environ.get("BOT_HEALTH_FILE", str(Path(tempfile.gettempdir()) / "sheriff-bot-health.json")))


def check_health(path: Path | None = None, now: float | None = None) -> tuple[bool, str]:
    try:
        state = json.loads((path or health_path()).read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return False, "heartbeat invalid"
        age = (time.time() if now is None else now) - state["timestamp"]
        if not 0 <= age <= 90:
            return False, "heartbeat missing or stale"
        if state["healthy"] is not True:
            return False, "bot unhealthy: " + ", ".join(state.get("reasons", []))
        return True, "bot healthy"
    except (OSError, ValueError, KeyError, TypeError):
        return False, "heartbeat unavailable or invalid"


if __name__ == "__main__":
    healthy, message = check_health()
    print(message)
    sys.exit(0 if healthy else 1)
