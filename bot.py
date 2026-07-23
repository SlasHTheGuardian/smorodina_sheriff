import os
import logging
from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.error import NetworkError, TimedOut
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
from db.engine import init_models

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Вызвать бота"),
]


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("Сетевая ошибка (игнорируем): %s", err)
        return
    logger.error("Необработанная ошибка:", exc_info=err)


async def _post_init(app: Application) -> None:
    """Создаёт таблицы БД до старта поллинга."""
    await init_models()
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Схема БД инициализирована.")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения TELEGRAM_BOT_TOKEN не задана. "
            "Проверь файл .env."
        )

    app = Application.builder().token(token).post_init(_post_init).build()

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

    logger.info("Бот запущен. Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
