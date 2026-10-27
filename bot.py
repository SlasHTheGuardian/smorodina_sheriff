import os
import logging
import asyncio
import faulthandler
import platform
import signal

from observability import (
    configure_logging, install_exception_hooks, loop_exception_handler,
    log_context, operation,
)

# Install before third-party/application imports: import/config errors must be visible too.
if __name__ == "__main__":
    configure_logging()
    install_exception_hooks()
    faulthandler.enable(all_threads=True)
    faulthandler.dump_traceback_later(120, repeat=True)
    logging.getLogger("sheriff.runtime").info("process.boot")

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.error import BadRequest, Conflict, Forbidden, InvalidToken, NetworkError, RetryAfter
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import handlers.balance as balance
import handlers.learn as learn
import handlers.rules as rules
import handlers.sawing as sawing
import handlers.quiz as quiz
import handlers.detective as detective
import handlers.games as games
import handlers.admin as admin
import handlers.results as results
from handlers.common import cmd_start, handle_message
from db.engine import init_models, dispose, engine
from telegram_observability import ObservedApplication, ObservedRequest, instrument_handlers, update_fields
from healthcheck import health_path

load_dotenv()

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Вызвать бота"),
]


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    app = context.application
    if isinstance(app, ObservedApplication):
        app.errors_total += 1
    category = "unexpected"
    level = logging.ERROR
    if isinstance(err, Conflict):
        category = "polling_conflict_check_other_instances_or_webhook"
        level = logging.CRITICAL
    elif isinstance(err, InvalidToken):
        category = "invalid_token"
        level = logging.CRITICAL
    elif isinstance(err, Forbidden):
        category = "forbidden"
    elif isinstance(err, RetryAfter):
        category = "rate_limited"
    elif isinstance(err, BadRequest):
        category = "bad_request"
    elif isinstance(err, NetworkError):
        category = "network"
    with log_context(**update_fields(update)):
        logger.log(level, "telegram.error", extra={"fields": {
            "category": category,
            "source": "update" if update is not None else "polling_or_background_task",
            "retry_after": getattr(err, "retry_after", None),
            "job_name": context.job.name if context.job else None,
        }}, exc_info=(type(err), err, err.__traceback__) if err else None)


async def _post_init(app: Application) -> None:
    """Создаёт таблицы БД до старта поллинга."""
    with operation("startup.post_init"):
        await init_models()
        await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("startup.ready_for_polling")


async def _post_shutdown(app: Application) -> None:
    await dispose()
    logger.info("shutdown.completed")


def build_application(token: str) -> Application:
    poll_request = ObservedRequest(connection_pool_size=1)
    app = (Application.builder().token(token)
           .application_class(ObservedApplication, kwargs={"poll_request": poll_request})
           .request(ObservedRequest(connection_pool_size=256))
           .get_updates_request(poll_request)
           .post_init(_post_init).post_shutdown(_post_shutdown).build())

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))

    # Тематические модули — каждый регистрирует свои callback-обработчики
    balance.register(app)
    learn.register(app)
    rules.register(app)
    sawing.register(app)
    quiz.register(app)
    detective.register(app)
    games.register(app)
    admin.register(app)
    results.register(app)

    # Fallback: любое текстовое / медиа-сообщение → главное меню
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    app.add_error_handler(on_error)
    count = instrument_handlers(app)
    logger.info("handlers.registered", extra={"fields": {"handler_count": count}})
    return app


def main() -> None:
    configure_logging()
    install_exception_hooks()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(loop_exception_handler)
    faulthandler.enable(all_threads=True)
    faulthandler.dump_traceback_later(120, repeat=True)
    previous_signals = {}
    received_signal = None

    def stop_signal(signum, frame):
        nonlocal received_signal
        received_signal = signal.Signals(signum).name
        logger.warning("process.signal", extra={"fields": {"signal": received_signal}})
        raise KeyboardInterrupt

    exit_code = 1
    try:
        health_path().unlink(missing_ok=True)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_signals[signum] = signal.signal(signum, stop_signal)
        if hasattr(signal, "SIGUSR1"):
            faulthandler.register(signal.SIGUSR1, all_threads=True)
        logger.info("process.starting", extra={"fields": {
            "python_version": platform.python_version(),
            "database_driver": engine.url.drivername,
            "log_level": logging.getLevelName(logging.getLogger().level),
        }})
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("Переменная окружения TELEGRAM_BOT_TOKEN не задана. Проверь файл .env.")
        app = build_application(token)
        # PTB owns orderly shutdown. Our signal handlers record the actual stop reason.
        app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)
        exit_code = 0
    except KeyboardInterrupt:
        exit_code = 0
    except Exception:
        logger.critical("process.failed", exc_info=True)
        raise SystemExit(1)
    finally:
        faulthandler.cancel_dump_traceback_later()
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
        if not loop.is_closed():
            loop.close()
        logger.info("process.exited", extra={"fields": {
            "exit_code": exit_code, "signal": received_signal,
        }})


if __name__ == "__main__":
    main()
