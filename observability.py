"""Structured logs and async operation tracing. Never log request bodies/arguments."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import itertools
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from urllib.parse import quote
import uuid

_context: ContextVar[dict] = ContextVar("log_context", default={})
_ids = itertools.count(1)
_RUN_ID = uuid.uuid4().hex[:12]
ACTIVE_OPERATIONS: dict[int, dict] = {}
logger = logging.getLogger("sheriff.operations")


def redact(value: str) -> str:
    # Read at formatting time: .env may have been loaded after logging setup.
    secrets = [value for key, value in os.environ.items() if value and (
        any(part in key.upper() for part in ("TOKEN", "PASSWORD", "SECRET"))
        or key == "DATABASE_URL"
    )]
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
        value = value.replace(quote(secret, safe=""), "[REDACTED]")
    value = re.sub(r"(?<!\d)\d{5,}:[A-Za-z0-9_-]{20,}\b", "[BOT_TOKEN]", value)
    value = re.sub(r"(://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    value = re.sub(r"(/players/name/)[^\s\"'?#]+", r"\1[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()
        self.run_id = _RUN_ID

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "pid": record.process,
            "run_id": self.run_id,
            **_context.get(),
            **getattr(record, "fields", {}),
            "event": record.getMessage(),
        }
        if record.exc_info:
            data["error_type"] = record.exc_info[0].__name__
            data["traceback"] = "".join(traceback.format_exception(*record.exc_info))
        if record.stack_info:
            data["stack"] = record.stack_info
        # Redact before JSON encoding, including exception messages and extra fields.
        def clean(item):
            if isinstance(item, str):
                return redact(item)
            if isinstance(item, dict):
                return {key: clean(val) for key, val in item.items()}
            if isinstance(item, (tuple, list)):
                return [clean(val) for val in item]
            if item is None or isinstance(item, (bool, int, float)):
                return item
            return redact(str(item))
        return json.dumps(clean(data), ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # These libraries log URLs, SQL parameters or whole Telegram payloads at DEBUG.
    for name in ("httpx", "httpcore", "telegram", "sqlalchemy", "aiosqlite"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.captureWarnings(True)


def install_exception_hooks() -> None:
    def uncaught(exc_type, exc, tb):
        logging.getLogger("sheriff.runtime").critical(
            "process.uncaught", exc_info=(exc_type, exc, tb)
        )
    sys.excepthook = uncaught

    def thread_error(args):
        logging.getLogger("sheriff.runtime").critical(
            "thread.uncaught",
            extra={"fields": {"thread": args.thread.name if args.thread else None}},
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    threading.excepthook = thread_error


def loop_exception_handler(loop, context) -> None:
    error = context.get("exception")
    # Do not render task/future/handle reprs: they can contain update payloads.
    logging.getLogger("sheriff.runtime").critical(
        "asyncio.uncaught",
        extra={"fields": {"reason": context.get("message", "unknown")}},
        exc_info=(type(error), error, error.__traceback__) if error else None,
    )


@contextmanager
def log_context(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def operation(name: str, *, level: int = logging.INFO, slow_seconds: float | None = 5, **fields):
    """Track a span even while suspended, so the heartbeat can name stuck work."""
    operation_id = next(_ids)
    started = time.monotonic()
    with log_context(operation=name, operation_id=operation_id, **fields):
        ACTIVE_OPERATIONS[operation_id] = {**_context.get(), "started": started}
        logger.log(level, "operation.started")
        try:
            yield
        except asyncio.CancelledError:
            logger.warning("operation.cancelled", extra={"fields": {
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }})
            raise
        except Exception:
            logger.exception("operation.failed", extra={"fields": {
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }})
            raise
        else:
            duration = (time.monotonic() - started) * 1000
            slow = slow_seconds is not None and duration >= slow_seconds * 1000
            logger.log(logging.WARNING if slow else level,
                       "operation.completed", extra={"fields": {"duration_ms": round(duration, 2)}})
        finally:
            ACTIVE_OPERATIONS.pop(operation_id, None)


def observed(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        with operation(f"{func.__module__}.{func.__name__}"):
            return await func(*args, **kwargs)
    return wrapper


def active_operations(now: float) -> list[dict]:
    return [
        {**{key: value for key, value in item.items() if key != "started"},
         "age_seconds": round(now - item["started"], 2)}
        for item in list(ACTIVE_OPERATIONS.values())
    ]
