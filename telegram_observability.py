"""Instrumentation for python-telegram-bot 21.6 public extension points."""
from __future__ import annotations

import asyncio
import faulthandler
from functools import wraps
import json
import logging
import os
import time

from telegram import Update
from telegram.ext import Application, ConversationHandler
from telegram.request import HTTPXRequest

from healthcheck import health_path
from observability import active_operations, log_context, operation

logger = logging.getLogger("sheriff.telegram")
HEARTBEAT_INTERVAL = 30
STALL_TIMEOUT = 120


def update_fields(update: object) -> dict:
    if not isinstance(update, Update):
        return {"update_type": type(update).__name__}
    kind = next((name for name in Update.ALL_TYPES if getattr(update, name, None) is not None), "unknown")
    return {
        "update_id": update.update_id,
        "update_type": kind,
        "user_id": update.effective_user.id if update.effective_user else None,
        "chat_id": update.effective_chat.id if update.effective_chat else None,
    }


def instrument_handlers(app: Application) -> int:
    """Wrap leaves, including all conversation states; preserve callback return values."""
    seen = set()
    def visit(handler):
        if id(handler) in seen:
            return 0
        seen.add(id(handler))
        if isinstance(handler, ConversationHandler):
            children = [*handler.entry_points, *handler.fallbacks]
            for state_handlers in handler.states.values():
                children.extend(state_handlers)
            return sum(visit(child) for child in children)
        callback = handler.callback
        if getattr(callback, "_instrumented", False):
            return 0
        name = f"{callback.__module__}.{callback.__name__}"
        @wraps(callback)
        async def traced(update, context):
            with log_context(**update_fields(update), handler=name):
                with operation(name):
                    result = await callback(update, context)
                    if isinstance(result, int):
                        logger.info("handler.state", extra={"fields": {"next_state": result}})
                    return result
        traced._instrumented = True
        handler.callback = traced
        return 1
    return sum(visit(handler) for group in app.handlers.values() for handler in group)


class ObservedRequest(HTTPXRequest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_poll_success: float | None = None
        self.poll_failures = 0
        self.poll_count = 0

    async def do_request(self, url, method, **kwargs):
        api_method = url.rsplit("/", 1)[-1].split("?", 1)[0]
        polling = api_method == "getUpdates"
        level = logging.DEBUG if polling else logging.INFO
        with operation(f"telegram.{api_method}", level=level, slow_seconds=None if polling else 5):
            try:
                status, payload = await super().do_request(url=url, method=method, **kwargs)
            except Exception:
                if polling:
                    self.poll_failures += 1
                raise
            if not 200 <= status < 300:
                if polling:
                    self.poll_failures += 1
                logger.error("telegram.http_error", extra={"fields": {
                    "api_method": api_method, "status_code": status,
                    "consecutive_poll_failures": self.poll_failures if polling else None,
                }})
            elif polling:
                self._record_poll_response(payload)
            logger.log(level, "telegram.response", extra={"fields": {
                "api_method": api_method, "status_code": status,
            }})
            return status, payload

    def _record_poll_response(self, payload: bytes) -> None:
        # A proxy can return HTML or an error envelope with HTTP 200. That is not
        # a successful poll. Leave parsing/error propagation to PTB as before.
        try:
            envelope = json.loads(payload)
            valid = (isinstance(envelope, dict) and envelope.get("ok") is True
                     and isinstance(envelope.get("result"), list)
                     and all(isinstance(item, dict) and isinstance(item.get("update_id"), int)
                             for item in envelope["result"]))
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            self.poll_failures += 1
            logger.error("telegram.invalid_poll_response", extra={"fields": {
                "consecutive_poll_failures": self.poll_failures,
            }})
            return
        first = self.last_poll_success is None
        previous_failures = self.poll_failures
        self.last_poll_success = time.monotonic()
        self.poll_count += 1
        self.poll_failures = 0
        if first or previous_failures:
            logger.info("polling.connected" if first else "polling.recovered",
                        extra={"fields": {"previous_failures": previous_failures}})


class ObservedApplication(Application):
    def __init__(self, *, poll_request, **kwargs):
        super().__init__(**kwargs)
        self.poll_request = poll_request
        self.monitor_task = None
        self.started_at = time.monotonic()
        self.updates_started = 0
        self.updates_finished = 0
        self.errors_total = 0
        self.queue_wait_since = None
        self.background_tasks = []

    async def initialize(self):
        with operation("application.initialize"):
            await super().initialize()

    async def start(self):
        with operation("application.start"):
            await super().start()
        self.started_at = time.monotonic()
        # Public asyncio inspection; task names are those of pinned PTB 21.6.
        self.background_tasks = [task for task in asyncio.all_tasks()
                                 if task.get_name().startswith(("Application:", "Updater:"))]
        for task in self.background_tasks:
            task.add_done_callback(self._background_done)
        self.monitor_task = asyncio.create_task(self._monitor(), name="sheriff-heartbeat")
        self.monitor_task.add_done_callback(self._monitor_done)
        logger.info("bot.started", extra={"fields": {"bot_id": self.bot.id}})

    def _background_done(self, task):
        with log_context(task_name=task.get_name()):
            if task.cancelled():
                logger.warning("background_task.cancelled")
            else:
                error = task.exception()
                if error:
                    logger.critical("background_task.failed", exc_info=(type(error), error, error.__traceback__))
                else:
                    logger.info("background_task.stopped")

    def _monitor_done(self, task):
        if task.cancelled():
            return
        error = task.exception()
        if error:
            logger.critical("heartbeat.failed", exc_info=(type(error), error, error.__traceback__))

    async def stop(self):
        logger.info("bot.stopping")
        try:
            with operation("application.stop"):
                await super().stop()
        finally:
            if self.monitor_task:
                self.monitor_task.cancel()
                # Its exception is already logged by _monitor_done; keep shutdown working.
                await asyncio.gather(self.monitor_task, return_exceptions=True)
            self._write_health({"healthy": False, "reasons": ["stopped"]})
        logger.info("bot.stopped")

    async def shutdown(self):
        with operation("application.shutdown"):
            await super().shutdown()

    async def process_update(self, update):
        self.updates_started += 1
        self.queue_wait_since = None
        with log_context(**update_fields(update)):
            with operation("update.dispatch"):
                try:
                    # PTB routes callback exceptions to process_error; finished != successful.
                    await super().process_update(update)
                finally:
                    self.updates_finished += 1

    def health_snapshot(self, now: float) -> dict:
        request = self.poll_request
        last_poll = request.last_poll_success
        poll_age = now - (last_poll if last_poll is not None else self.started_at)
        active = active_operations(now)
        queue_size = self.update_queue.qsize()
        if queue_size and self.queue_wait_since is None:
            self.queue_wait_since = now
        elif not queue_size:
            self.queue_wait_since = None
        reasons = []
        if not self.running:
            reasons.append("application_not_running")
        if not self.updater or not self.updater.running:
            reasons.append("polling_not_running")
        if any(task.done() for task in self.background_tasks):
            reasons.append("background_task_stopped")
        if last_poll is None:
            reasons.append("polling_not_connected")
        elif poll_age > STALL_TIMEOUT:
            reasons.append("polling_stalled")
        if any(item["age_seconds"] > STALL_TIMEOUT for item in active):
            reasons.append("operation_stalled")
        if self.queue_wait_since is not None and now - self.queue_wait_since > STALL_TIMEOUT:
            reasons.append("update_queue_stalled")
        return {
            "healthy": not reasons, "reasons": reasons,
            "uptime_seconds": round(now - self.started_at, 1),
            "poll_age_seconds": round(poll_age, 1),
            "poll_count": request.poll_count, "poll_failures": request.poll_failures,
            "queue_size": queue_size, "updates_started": self.updates_started,
            "updates_finished": self.updates_finished, "errors_total": self.errors_total,
            "active_operations": active,
        }

    @staticmethod
    def _write_health(snapshot):
        path = health_path()
        try:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "timestamp": time.time(), "pid": os.getpid(),
                "healthy": snapshot["healthy"], "reasons": snapshot["reasons"],
            }), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            logger.exception("health_file.write_failed")

    async def _monitor(self):
        expected = time.monotonic()
        previous_reasons = None
        while True:
            now = time.monotonic()
            snapshot = self.health_snapshot(now)
            snapshot["loop_lag_seconds"] = round(max(0, now - expected), 3)
            snapshot["asyncio_tasks"] = len(asyncio.all_tasks())
            connecting = (snapshot["reasons"] == ["polling_not_connected"]
                          and snapshot["uptime_seconds"] < STALL_TIMEOUT)
            logger.log(logging.INFO if snapshot["healthy"] or connecting else logging.ERROR,
                       "bot.heartbeat", extra={"fields": snapshot})
            if previous_reasons and snapshot["healthy"]:
                logger.info("bot.recovered")
            if snapshot["reasons"] and not connecting and snapshot["reasons"] != previous_reasons:
                # Locations only: no coroutine repr, source text, locals or payloads.
                for task in asyncio.all_tasks():
                    frames = [{"file": frame.f_code.co_filename, "line": frame.f_lineno,
                               "function": frame.f_code.co_name} for frame in task.get_stack(limit=8)]
                    logger.error("asyncio.task_stack", extra={"fields": {
                        "task_name": task.get_name(), "frames": frames,
                    }})
            previous_reasons = [] if connecting else snapshot["reasons"]
            self._write_health(snapshot)
            # Independent native timer still dumps stacks if the event loop is blocked.
            faulthandler.dump_traceback_later(STALL_TIMEOUT, repeat=True)
            expected = time.monotonic() + HEARTBEAT_INTERVAL
            await asyncio.sleep(HEARTBEAT_INTERVAL)
