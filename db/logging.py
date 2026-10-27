"""SQL timings and connection failures without SQL text or bound parameters."""
import logging
import time

from sqlalchemy import event

logger = logging.getLogger("sheriff.database")


def install_database_logging(engine) -> None:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_execute(conn, cursor, statement, parameters, context, executemany):
        context._log_started = time.monotonic()
        first_word = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "UNKNOWN"
        context._log_command = first_word if first_word in {
            "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "PRAGMA"
        } else "OTHER"
        logger.debug("db.query.started", extra={"fields": {"sql_command": context._log_command}})

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_execute(conn, cursor, statement, parameters, context, executemany):
        elapsed = (time.monotonic() - context._log_started) * 1000
        logger.log(logging.WARNING if elapsed >= 500 else logging.DEBUG,
                   "db.query.completed", extra={"fields": {
                       "sql_command": context._log_command,
                       "duration_ms": round(elapsed, 2), "row_count": cursor.rowcount,
                   }})

    @event.listens_for(engine.sync_engine, "handle_error")
    def handle_error(context):
        error = context.original_exception
        logger.error("db.query.failed", extra={"fields": {
            "disconnected": context.is_disconnect,
            "sql_command": getattr(context.execution_context, "_log_command", None),
        }}, exc_info=(type(error), error, error.__traceback__))

    @event.listens_for(engine.sync_engine, "connect")
    def connected(dbapi_connection, connection_record):
        logger.info("db.connection.opened")

    @event.listens_for(engine.sync_engine, "invalidate")
    def invalidated(dbapi_connection, connection_record, exception):
        logger.warning("db.connection.invalidated", exc_info=(
            type(exception), exception, exception.__traceback__
        ) if exception else None)

    @event.listens_for(engine.sync_engine, "commit")
    def commit(conn):
        # Engine event fires before the driver's commit; avoid claiming success here.
        logger.debug("db.commit.started")

    @event.listens_for(engine.sync_engine, "rollback")
    def rollback(conn):
        logger.debug("db.rollback.started")
